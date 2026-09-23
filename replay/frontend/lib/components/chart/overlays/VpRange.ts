/**
 * PurpleReplay v2 — VP de mesure (Fixed-Range Volume Profile)
 * L'utilisateur tire une zone sur le cours -> profil borné à cette plage : POC, VAH/VAL (70 %), extrêmes H/L des
 * bougies, delta net par niveau (couloir gauche), dégradé spectral. Une plage finissant sur la dernière bougie est
 * LIVE et s'accroche à la bougie courante. Réservoir = trades du tape (normalisés) + repli sur le volume des bougies
 * (triangle centré sur hlc3) pour la portion antérieure au tape. Plages persistées par symbole (localStorage).
 * Port de vprange.js (V1), logique pure hors DOM sauf le canvas et la souris.
 */
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { addCell, estimateTick, profileStats, type Cell, type Level, normalizeCell } from '$replay/domain/profile/valueArea';
import type { Candle } from '$replay/domain/market/types';

const MAX_CELLS = 80000, LS_KEY = 'pr2-vprange', LIVE_EDGE_SEC = 30, TARGET_PITCH = 5;
const STOPS: [number, [number, number, number]][] = [[0, [150, 92, 196]], [0.28, [231, 76, 60]], [0.5, [230, 126, 34]], [0.74, [241, 196, 15]], [1, [46, 204, 113]]];

export interface Range {
	id: number; t1: number; t2: number | null; live: boolean; vp: Map<number, Level>; poc: number | null; vah: number | null; val: number | null;
	hi: number | null; lo: number | null; totVol: number; netDelta: number; hasTape: boolean; closeBox?: { x: number; y: number; w: number; h: number } | null;
}

function ramp(t: number): [number, number, number] {
	t = Math.max(0, Math.min(1, t));
	for (let i = 1; i < STOPS.length; i++) if (t <= STOPS[i][0]) {
		const [ta, ca] = STOPS[i - 1], [tb, cb] = STOPS[i], f = (t - ta) / Math.max(1e-9, tb - ta);
		return [Math.round(ca[0] + (cb[0] - ca[0]) * f), Math.round(ca[1] + (cb[1] - ca[1]) * f), Math.round(ca[2] + (cb[2] - ca[2]) * f)];
	}
	return STOPS[STOPS.length - 1][1];
}

export class VpRange {
	private cells: Cell[] = [];
	private candles: Candle[] = [];
	private tfSec = 0;
	private lastT = 0;
	ranges: Range[] = [];
	private store: Record<string, { t1: number; t2: number | null; live: boolean }[]> = this.loadStore();
	private ctxKey: string | null = null;
	private seq = 1;
	armed = false;
	drag: { x0: number; x1: number } | null = null;
	onChange: () => void = () => {};

	constructor(private chart: IChartApi, private series: ISeriesApi<'Candlestick'>) {}

	// ---------------- données
	seed(cells: Parameters<typeof normalizeCell>[0][]): void {
		const out: Cell[] = [];
		for (const c of cells || []) { const n = normalizeCell(c); if (n) out.push(n); }
		this.cells = out.slice(-MAX_CELLS);
		this.lastT = this.cells.reduce((m, c) => Math.max(m, c.t), 0);
		for (const r of this.ranges) this.recompute(r);
		this.onChange();
	}
	push(cells: Parameters<typeof normalizeCell>[0][]): void {
		const added: Cell[] = [];
		for (const c of cells || []) { const n = normalizeCell(c); if (!n) continue; this.cells.push(n); added.push(n); if (n.t > this.lastT) this.lastT = n.t; }
		if (!added.length) return;
		if (this.cells.length > MAX_CELLS) this.cells = this.cells.slice(-MAX_CELLS);
		for (const r of this.ranges) { if (!r.live) continue; let touched = false; for (const n of added) if (n.t >= r.t1) { this.addCell(r, n); touched = true; } if (touched) this.stats(r); }
		this.onChange();
	}
	setCandles(candles: Candle[]): void {
		this.candles = candles.filter((c) => c && typeof c.time === 'number');
		this.tfSec = this.guessTf();
		for (const r of this.ranges) this.recompute(r);
		this.onChange();
	}
	pushCandle(c: Candle): void {
		const a = this.candles;
		if (a.length && a[a.length - 1].time === c.time) a[a.length - 1] = { ...c };
		else if (!a.length || c.time > a[a.length - 1].time) a.push({ ...c });
		else for (let i = a.length - 1; i >= 0; i--) { if (a[i].time === c.time) { a[i] = { ...c }; break; } if (a[i].time < c.time) break; }
		let touched = false;
		for (const r of this.ranges) if (r.live) { this.candleExtremes(r); touched = true; }
		if (touched) this.onChange();
	}
	private guessTf(): number {
		const a = this.candles;
		if (a.length < 2) return this.tfSec || 60;
		const d: number[] = [];
		for (let i = 1; i < Math.min(a.length, 30); i++) { const x = a[i].time - a[i - 1].time; if (x > 0) d.push(x); }
		d.sort((x, y) => x - y);
		return d.length ? d[d.length >> 1] : this.tfSec || 60;
	}

	/** Contexte = symbole seul : les bornes sont temporelles, une plage tracée en 1h reste visible en 1m. */
	setContext(symbol: string): void {
		const key = String(symbol || '?');
		if (key === this.ctxKey) return;
		this.persist();
		this.ctxKey = key;
		const saved = this.store[key] || [];
		this.ranges = saved.map((s) => this.mkRange(s.t1, s.t2, s.live));
		for (const r of this.ranges) this.recompute(r);
		this.onChange();
	}

	// ---------------- plages
	private mkRange(t1: number, t2: number | null, live: boolean): Range {
		return { id: this.seq++, t1: +t1, t2: t2 == null ? null : +t2, live: !!live, vp: new Map(), poc: null, vah: null, val: null, hi: null, lo: null, totVol: 0, netDelta: 0, hasTape: false };
	}
	private effEnd(r: Range): number { return r.live ? this.lastT || Number.MAX_SAFE_INTEGER : r.t2 == null ? this.lastT : r.t2; }
	private addCell(r: Range, n: Cell): void { if (n.t < r.t1 || n.t > this.effEnd(r)) return; addCell(r.vp, n.price, n.volume, n.side); r.hasTape = true; }

	/** Portion antérieure au tape : volume des bougies réparti en triangle centré sur hlc3, delta estimé par la position du close. */
	private synthFromCandles(r: Range): void {
		if (!this.candles.length) return;
		const tf = this.tfSec || 60, end = this.effEnd(r), tapeStart = this.cells.length ? this.cells[0].t : Infinity, tick = estimateTick(this.cells.map((c) => c.price));
		for (const c of this.candles) {
			if (c.time > end || c.time + tf <= r.t1 || c.time + tf > tapeStart) continue;
			const vol = +c.volume || 0; if (!vol) continue;
			const lo = Math.min(c.low, c.high), hi = Math.max(c.low, c.high);
			if (!Number.isFinite(lo) || !Number.isFinite(hi)) continue;
			const cl = Number.isFinite(+c.close) ? +c.close : (hi + lo) / 2, rng = hi - lo;
			const bullFrac = rng > 0 ? Math.min(1, Math.max(0, (cl - lo) / rng)) : 0.5, tp = (hi + lo + cl) / 3, half = Math.max(tick, rng / 2);
			const k0 = Math.round(lo / tick), k1 = Math.round(hi / tick);
			let step = 1; const nlv = Math.max(1, k1 - k0 + 1); if (nlv > 400) step = Math.ceil(nlv / 400);
			let wsum = 0;
			for (let k = k0; k <= k1; k += step) wsum += Math.max(0.05, 1 - Math.abs(k * tick - tp) / half);
			if (!(wsum > 0)) wsum = 1;
			for (let k = k0; k <= k1; k += step) {
				const price = k * tick, w = Math.max(0.05, 1 - Math.abs(price - tp) / half), add = vol * (w / wsum);
				addCell(r.vp, price, add * bullFrac, 'buy'); addCell(r.vp, price, add * (1 - bullFrac), 'sell');
			}
		}
	}
	private candleExtremes(r: Range): void {
		if (!this.candles.length) return;
		const tf = this.tfSec || 60, end = this.effEnd(r);
		let hi = -Infinity, lo = Infinity;
		for (const c of this.candles) { if (c.time > end || c.time + tf <= r.t1) continue; if (c.high > hi) hi = c.high; if (c.low < lo) lo = c.low; }
		if (Number.isFinite(hi) && Number.isFinite(lo)) { r.hi = hi; r.lo = lo; }
	}
	private recompute(r: Range): void {
		r.vp.clear(); r.hasTape = false;
		const end = this.effEnd(r);
		for (const n of this.cells) if (n.t >= r.t1 && n.t <= end) this.addCell(r, n);
		this.synthFromCandles(r);
		this.stats(r);
	}
	private stats(r: Range): void {
		const s = profileStats(r.vp);
		r.totVol = s.total; r.netDelta = s.netDelta; r.poc = s.poc; r.vah = s.vah; r.val = s.val; r.hi = s.hi; r.lo = s.lo;
		this.candleExtremes(r);   // les bougies tracées priment pour H/L
	}

	// ---------------- persistance
	private loadStore() { try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}') || {}; } catch { return {}; } }
	private persist(): void {
		if (!this.ctxKey) return;
		this.store[this.ctxKey] = this.ranges.map((r) => ({ t1: r.t1, t2: r.t2, live: r.live }));
		try { localStorage.setItem(LS_KEY, JSON.stringify(this.store)); } catch { /* stockage indisponible */ }
	}

	// ---------------- interaction (coordonnées relatives au host)
	arm(): void { this.armed = true; }
	disarm(): void { this.armed = false; this.drag = null; }
	clearAll(): void { this.ranges = []; this.persist(); this.onChange(); }
	blocksChart(x: number, y: number): boolean {
		if (this.armed || this.drag) return true;
		return this.ranges.some((r) => r.closeBox && x >= r.closeBox.x && x <= r.closeBox.x + r.closeBox.w && y >= r.closeBox.y && y <= r.closeBox.y + r.closeBox.h);
	}
	beginDrag(x: number): void { this.drag = { x0: x, x1: x }; }
	moveDrag(x: number): void { if (this.drag) { this.drag.x1 = x; this.onChange(); } }
	endDrag(): void {
		const d = this.drag; this.drag = null; this.disarm();
		if (!d) return;
		const xa = Math.min(d.x0, d.x1), xb = Math.max(d.x0, d.x1);
		if (xb - xa < 8) { this.onChange(); return; }
		let t1 = this.xToTime(xa), t2 = this.xToTime(xb);
		if (t1 == null) t1 = this.candles.length ? +this.candles[0].time : this.cells.length ? this.cells[0].t : this.lastT - 3600;
		let live = false;
		if (t2 == null) live = true; else if (this.lastT && t2 >= this.lastT - LIVE_EDGE_SEC) live = true;
		const r = this.mkRange(t1, live ? null : t2, live);
		this.recompute(r); this.ranges.push(r); this.persist(); this.onChange();
	}
	/** Clic sur la croix d'une plage : suppression. Retourne true si consommé. */
	clickAt(x: number, y: number): boolean {
		for (let i = 0; i < this.ranges.length; i++) {
			const hb = this.ranges[i].closeBox;
			if (hb && x >= hb.x && x <= hb.x + hb.w && y >= hb.y && y <= hb.y + hb.h) { this.ranges.splice(i, 1); this.persist(); this.onChange(); return true; }
		}
		return false;
	}
	private xToTime(x: number): number | null { try { const t = this.chart.timeScale().coordinateToTime(x); return t == null ? null : +t; } catch { return null; } }
	private timeToX(t: number): number | null { try { const x = this.chart.timeScale().timeToCoordinate(t as never); return x == null ? null : x; } catch { return null; } }
	private liveEdgeX(): number | null {
		const a = this.candles; if (!a.length) return null;
		const xc = this.timeToX(a[a.length - 1].time); if (xc == null) return null;
		let half = 3;
		if (a.length >= 2) { const xp = this.timeToX(a[a.length - 2].time); if (xp != null && xc > xp) half = (xc - xp) / 2; }
		return xc + half;
	}

	// ---------------- rendu
	draw(ctx: CanvasRenderingContext2D, W: number, H: number, axisW: number): void {
		if (this.drag) {
			const xa = Math.min(this.drag.x0, this.drag.x1), xb = Math.max(this.drag.x0, this.drag.x1);
			ctx.fillStyle = 'rgba(150,110,240,0.08)'; ctx.fillRect(xa, 0, xb - xa, H);
			ctx.strokeStyle = 'rgba(185,155,250,0.7)'; ctx.setLineDash([5, 4]); ctx.lineWidth = 1; ctx.strokeRect(xa, 0, xb - xa, H); ctx.setLineDash([]);
		}
		for (const r of this.ranges) this.drawRange(ctx, W, H, axisW, r);
	}

	private drawRange(ctx: CanvasRenderingContext2D, W: number, H: number, axisW: number, r: Range): void {
		r.closeBox = null;
		const ps = this.series, rightEdge = W - axisW;
		let x1 = this.timeToX(r.t1) ?? 0;
		let x2 = r.live ? null : this.timeToX(r.t2!);
		if (x2 == null) x2 = this.liveEdgeX() ?? rightEdge;
		x1 = Math.max(0, Math.min(x1, rightEdge)); x2 = Math.max(x1 + 4, Math.min(x2, rightEdge));
		const boxW = x2 - x1, accent = r.live ? 'rgba(38,200,130,' : 'rgba(150,110,240,';
		if (!r.vp.size || r.poc == null || r.hi == null || r.lo == null) {
			ctx.strokeStyle = accent + '0.40)'; ctx.setLineDash([4, 4]); ctx.lineWidth = 1; ctx.strokeRect(x1, 4, boxW, H - 8); ctx.setLineDash([]);
			this.header(ctx, r, x1, x2, '(aucune donnée sur la plage)', 14); return;
		}
		const yHi = ps.priceToCoordinate(r.hi), yLo = ps.priceToCoordinate(r.lo);
		if (yHi == null || yLo == null) { this.header(ctx, r, x1, x2, '', 14); return; }
		const yTop = Math.max(-2, Math.min(yHi, yLo) - 5), yBot = Math.min(H + 2, Math.max(yHi, yLo) + 5), boxH = yBot - yTop;
		if (boxH < 8) { this.header(ctx, r, x1, x2, '', 14); return; }
		ctx.fillStyle = accent + '0.06)'; ctx.fillRect(x1, yTop, boxW, boxH);
		ctx.strokeStyle = accent + '0.55)'; ctx.lineWidth = 1; ctx.strokeRect(x1 + 0.5, yTop + 0.5, boxW - 1, boxH - 1);
		const raw = [...r.vp.values()].filter((e) => e.price >= r.lo! - 1e-9 && e.price <= r.hi! + 1e-9);
		if (!raw.length) { this.header(ctx, r, x1, x2, '', Math.max(12, yTop - 8)); return; }
		const tick = estimateTick(raw.map((e) => e.price));
		const yA = ps.priceToCoordinate(r.lo), yB = ps.priceToCoordinate(r.lo + tick);
		if (yA == null || yB == null) { this.header(ctx, r, x1, x2, '', Math.max(12, yTop - 8)); return; }
		const tickPx = Math.max(Math.abs(yB - yA), 0.0001), binTicks = Math.max(1, Math.ceil(TARGET_PITCH / tickPx)), binSize = tick * binTicks, pitch = tickPx * binTicks;
		const bins = new Map<number, Level & { y: number }>();
		for (const e of raw) { const k = Math.round(e.price / binSize); let b = bins.get(k); if (!b) { b = { price: k * binSize, vol: 0, buy: 0, sell: 0, y: 0 }; bins.set(k, b); } b.vol += e.vol; b.buy += e.buy; b.sell += e.sell; }
		const levels: (Level & { y: number })[] = []; let maxVol = 0;
		for (const b of bins.values()) { const y = ps.priceToCoordinate(b.price); if (y == null) continue; b.y = y; levels.push(b); if (b.vol > maxVol) maxVol = b.vol; }
		if (!levels.length || maxVol <= 0) { this.header(ctx, r, x1, x2, '', Math.max(12, yTop - 8)); return; }
		const gap = Math.max(1, Math.floor(pitch * 0.22)), bh = Math.max(3, pitch - gap), xL = x1 + 2, maxW = Math.max(24, x2 - xL - 3);
		let poc = levels[0]; for (const l of levels) if (l.vol > poc.vol) poc = l;
		const span = Math.max(1e-9, r.hi - r.lo);
		for (const l of levels) {
			const yr = l.y - bh / 2; if (yr + bh < yTop || yr > yBot) continue;
			const w = Math.max(2, (l.vol / maxVol) * maxW), c = ramp((l.price - r.lo) / span);
			ctx.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},${l === poc ? 0.98 : 0.9})`; ctx.fillRect(xL, yr, w, bh);
			if (l === poc) { ctx.fillStyle = 'rgba(255,255,255,0.85)'; ctx.fillRect(xL, yr, w, Math.max(1, Math.min(2, bh * 0.2))); }
		}
		let maxDelta = 0; for (const l of levels) maxDelta = Math.max(maxDelta, Math.abs(l.buy - l.sell));
		if (maxDelta > 0) {
			const dMaxW = Math.min(70, Math.max(18, maxW * 0.33));
			for (const l of levels) {
				const yr = l.y - bh / 2; if (yr + bh < yTop || yr > yBot) continue;
				const d = l.buy - l.sell; if (d === 0) continue;
				const w = Math.max(1, (Math.abs(d) / maxDelta) * dMaxW);
				ctx.fillStyle = d >= 0 ? 'rgba(46,204,113,0.92)' : 'rgba(168,92,214,0.92)'; ctx.fillRect(x1 - w, yr, w, bh);
			}
		}
		const yp = ps.priceToCoordinate(r.poc);
		if (yp != null && yp >= yTop && yp <= yBot) {
			ctx.strokeStyle = 'rgba(255,196,0,0.75)'; ctx.setLineDash([4, 4]); ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x1, yp); ctx.lineTo(x2, yp); ctx.stroke(); ctx.setLineDash([]);
			ctx.fillStyle = 'rgba(255,210,60,0.95)'; ctx.font = '10px system-ui,sans-serif'; ctx.textAlign = 'right'; ctx.fillText('POC ' + r.poc.toFixed(2), x2 - 4, yp - 3);
		}
		if (r.vah != null && r.val != null) {
			const yVAH = ps.priceToCoordinate(r.vah), yVAL = ps.priceToCoordinate(r.val);
			if (yVAH != null && yVAL != null) {
				ctx.strokeStyle = accent + '0.55)'; ctx.lineWidth = 1; ctx.setLineDash([2, 3]);
				ctx.beginPath(); ctx.moveTo(x1, yVAH); ctx.lineTo(x2, yVAH); ctx.stroke(); ctx.beginPath(); ctx.moveTo(x1, yVAL); ctx.lineTo(x2, yVAL); ctx.stroke(); ctx.setLineDash([]);
				ctx.fillStyle = 'rgba(185,155,250,0.9)'; ctx.font = '9px system-ui,sans-serif'; ctx.textAlign = 'right';
				ctx.fillText('VAH ' + r.vah.toFixed(2), x2 - 4, yVAH - 2); ctx.fillText('VAL ' + r.val.toFixed(2), x2 - 4, yVAL + 9);
			}
		}
		ctx.font = '9px system-ui,sans-serif'; ctx.textAlign = 'left'; ctx.fillStyle = 'rgba(200,210,220,0.95)';
		ctx.fillText('H ' + r.hi.toFixed(2), x1 + 4, yTop + 10); ctx.fillText('L ' + r.lo.toFixed(2), x1 + 4, yBot - 3);
		this.header(ctx, r, x1, x2, null, yTop >= 30 ? yTop - 20 : yTop + 12);
	}

	private header(ctx: CanvasRenderingContext2D, r: Range, x1: number, x2: number, note: string | null, y: number): void {
		ctx.textAlign = 'left'; ctx.font = '11px system-ui,sans-serif';
		const title = r.live ? 'VP LIVE' : 'VP';
		ctx.fillStyle = r.live ? 'rgba(80,220,150,0.95)' : 'rgba(185,155,250,0.95)'; ctx.fillText(title, x1 + 4, y + 4);
		let tx = x1 + 4 + ctx.measureText(title).width + 10;
		if (note) { ctx.fillStyle = 'rgba(160,175,190,0.85)'; ctx.font = '10px system-ui,sans-serif'; ctx.fillText(note, tx, y + 4); }
		else if (r.poc != null) {
			const span = r.hi != null && r.lo != null ? (r.hi - r.lo).toFixed(2) : '-';
			ctx.font = '10px system-ui,sans-serif'; ctx.fillStyle = 'rgba(190,200,212,0.95)';
			const s1 = 'Vol ' + fmt(r.totVol) + '   H-L ' + span + 'pt   '; ctx.fillText(s1, tx, y + 4); tx += ctx.measureText(s1).width;
			if (r.hasTape) { ctx.fillStyle = r.netDelta >= 0 ? 'rgba(80,220,150,0.98)' : 'rgba(190,130,255,0.98)'; ctx.fillText('Δ ' + (r.netDelta > 0 ? '+' : '') + fmt(r.netDelta), tx, y + 4); }
		}
		const cx = x2 - 15, cy = y - 6;
		r.closeBox = { x: cx, y: cy, w: 12, h: 12 };
		ctx.strokeStyle = 'rgba(200,120,120,0.85)'; ctx.lineWidth = 1.4;
		ctx.beginPath(); ctx.moveTo(cx + 2, cy + 2); ctx.lineTo(cx + 10, cy + 10); ctx.moveTo(cx + 10, cy + 2); ctx.lineTo(cx + 2, cy + 10); ctx.stroke();
	}
}

function fmt(n: number): string { const a = Math.abs(n); return a >= 1e6 ? (n / 1e6).toFixed(2) + 'M' : a >= 1e3 ? (n / 1e3).toFixed(1) + 'k' : String(Math.round(n)); }
