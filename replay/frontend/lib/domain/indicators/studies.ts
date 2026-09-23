/**
 * PurpleReplay v2 — études de prix
 * EMA (20/50) et VWAP de séance + bandes ±1σ/±2σ, ancrage Globex (22:00 UTC) ou RTH (13:30–20:00 UTC),
 * avec état incrémental pour la bougie en formation. Calcul pur, testable.
 */
import type { Candle } from '../market/types';

export interface Point { time: number; value: number; }
export type VwapMode = 'globex' | 'rth' | 'off';

export function ema(candles: readonly Candle[], period: number): Point[] {
	const out: Point[] = [];
	if (!candles.length) return out;
	const k = 2 / (period + 1);
	const seedN = Math.min(period, candles.length);
	let sum = 0;
	for (let i = 0; i < seedN; i++) sum += candles[i].close;
	let v = sum / seedN;
	out.push({ time: candles[seedN - 1].time, value: v });
	for (let i = seedN; i < candles.length; i++) { v = candles[i].close * k + v * (1 - k); out.push({ time: candles[i].time, value: v }); }
	return out;
}

export class EmaTracker {
	private k: number; private prev: number | null = null; private cur: number | null = null; private curTime: number | null = null;
	constructor(readonly period: number) { this.k = 2 / (period + 1); }
	seed(candles: readonly Candle[]): Point[] {
		const pts = ema(candles, this.period);
		this.curTime = candles.length ? candles[candles.length - 1].time : null;
		this.cur = pts.length ? pts[pts.length - 1].value : null;
		this.prev = pts.length >= 2 ? pts[pts.length - 2].value : this.cur;
		return pts;
	}
	update(c: Candle): Point | null {
		if (this.prev == null) return null;
		if (this.curTime != null && c.time < this.curTime) return null;
		if (this.curTime == null || c.time > this.curTime) { if (this.cur != null) this.prev = this.cur; this.curTime = c.time; }
		this.cur = c.close * this.k + this.prev * (1 - this.k);
		return { time: c.time, value: this.cur };
	}
}

export function vwapSessionKey(t: number, mode: VwapMode): number | null {
	if (mode === 'rth') {
		const tod = ((t % 86400) + 86400) % 86400;
		if (tod < 48600 || tod >= 72000) return null;
		return Math.floor(t / 86400);
	}
	return Math.floor((t - 79200) / 86400);
}

export interface VwapSeries { vwap: Point[]; up1: Point[]; dn1: Point[]; up2: Point[]; dn2: Point[]; }

export class VwapTracker {
	mode: VwapMode = 'globex';
	private commitPV = 0; private commitV = 0; private commitPV2 = 0;
	private curPV = 0; private curV = 0; private curPV2 = 0; private curTime: number | null = null; private sess: number | null = null;

	seed(candles: readonly Candle[]): VwapSeries {
		const r: VwapSeries = { vwap: [], up1: [], dn1: [], up2: [], dn2: [] };
		this.commitPV = this.commitV = this.commitPV2 = 0; this.curPV = this.curV = this.curPV2 = 0; this.curTime = null; this.sess = null;
		if (this.mode === 'off') return r;
		let sumPV = 0, sumV = 0, sumPV2 = 0;
		for (const c of candles) {
			const k = vwapSessionKey(c.time, this.mode);
			if (k == null) continue;
			if (k !== this.sess) { sumPV = sumV = sumPV2 = 0; this.commitPV = this.commitV = this.commitPV2 = 0; this.sess = k; }
			else { this.commitPV = sumPV; this.commitV = sumV; this.commitPV2 = sumPV2; }
			const tp = (c.high + c.low + c.close) / 3, v = c.volume || 0;
			this.curPV = tp * v; this.curV = v; this.curPV2 = tp * tp * v;
			sumPV += this.curPV; sumV += this.curV; sumPV2 += this.curPV2; this.curTime = c.time;
			if (sumV > 0) push(r, c.time, sumPV / sumV, Math.sqrt(Math.max(0, sumPV2 / sumV - (sumPV / sumV) ** 2)));
		}
		return r;
	}

	update(c: Candle): { time: number; vw: number; sg: number } | null {
		if (this.mode === 'off') return null;
		if (this.curTime != null && c.time < this.curTime) return null;
		const k = vwapSessionKey(c.time, this.mode);
		if (k == null) return null;
		if (this.sess == null) this.sess = k;
		if (k !== this.sess) { this.commitPV = this.commitV = this.commitPV2 = 0; this.sess = k; this.curTime = null; }
		if (this.curTime == null || c.time > this.curTime) {
			if (this.curTime != null) { this.commitPV += this.curPV; this.commitV += this.curV; this.commitPV2 += this.curPV2; }
			this.curTime = c.time;
		}
		const tp = (c.high + c.low + c.close) / 3, v = c.volume || 0;
		this.curPV = tp * v; this.curV = v; this.curPV2 = tp * tp * v;
		const PV = this.commitPV + this.curPV, V = this.commitV + this.curV, PV2 = this.commitPV2 + this.curPV2;
		if (V <= 0) return null;
		const vw = PV / V;
		return { time: c.time, vw, sg: Math.sqrt(Math.max(0, PV2 / V - vw * vw)) };
	}
}

function push(r: VwapSeries, time: number, vw: number, sg: number): void {
	r.vwap.push({ time, value: vw }); r.up1.push({ time, value: vw + sg }); r.dn1.push({ time, value: vw - sg });
	r.up2.push({ time, value: vw + 2 * sg }); r.dn2.push({ time, value: vw - 2 * sg });
}
