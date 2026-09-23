/**
 * PurpleReplay v2 — contrôleur du graphique
 * Cycle de vie des données du chart (séparé de la présentation, comme PurpleChart v2) :
 *  - historique REST (plafonné au curseur côté serveur), rechargé à chaque snapshot (nouvelle séance) ;
 *  - bougie en formation alimentée par le tape (temps réel), réconciliée par les trames `candle` ;
 *  - séries volume, delta agresseur, EMA 20/50, VWAP ±σ ;
 *  - temps réels des bougies (snap exact des marques, y compris 4h/6h) et OHLC pour le « die on touch ».
 */
import {
	CandlestickSeries, HistogramSeries, LineSeries, LineStyle,
	type IChartApi, type ISeriesApi, type UTCTimestamp
} from 'lightweight-charts';
import { get } from 'svelte/store'; // [Sol]
import { MarketApi } from '$replay/api/market';
import { market } from '$replay/application/MarketStore';
import { tfSeconds } from '$replay/domain/timeframes';
import { EmaTracker, VwapTracker, type VwapMode } from '$replay/domain/indicators/studies';
import type { Candle, DeltaBucket, Trade } from '$replay/domain/market/types';

export interface ChartView { state(text: string): void; }
type Listener = () => void;

export class ChartController {
	readonly candle: ISeriesApi<'Candlestick'>;
	private line: ISeriesApi<'Line'>;
	private vol: ISeriesApi<'Histogram'>;
	private delta: ISeriesApi<'Histogram'>;
	private ema20: ISeriesApi<'Line'>;
	private ema50: ISeriesApi<'Line'>;
	private vwapLines: ISeriesApi<'Line'>[];
	private ema20T = new EmaTracker(20);
	private ema50T = new EmaTracker(50);
	private vwapT = new VwapTracker();
	private bandsOn = true;
	private emaOn = true;
	barTimes: number[] = [];
	bars = new Map<number, Candle>();
	candles: Candle[] = [];
	curBar: Candle | null = null;
	readonly tfSec: number;
	private off: (() => void)[] = [];
	private disposed = false;
	private loading = false;
	private retry: ReturnType<typeof setTimeout> | null = null;
	private deltaTimes: number[] = [];
	private listeners = new Set<Listener>();
	private queue: Trade[] = [];
	private frame = 0;

	constructor(readonly chart: IChartApi, readonly symbol: string, readonly tf: string, private view: ChartView) {
		this.tfSec = tfSeconds(tf);
		this.candle = chart.addSeries(CandlestickSeries, { upColor: '#26a69a', downColor: '#ef5350', borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350' });
		this.line = chart.addSeries(LineSeries, { color: '#4da6ff', lineWidth: 2, visible: false, lastValueVisible: true, priceLineVisible: true });
		this.vol = chart.addSeries(HistogramSeries, { priceScaleId: '', priceFormat: { type: 'volume' }, color: '#2a3947' });
		this.vol.priceScale().applyOptions({ scaleMargins: { top: 0.88, bottom: 0 } });
		this.delta = chart.addSeries(HistogramSeries, { priceScaleId: 'delta', priceFormat: { type: 'volume' } });
		chart.priceScale('delta').applyOptions({ scaleMargins: { top: 0.72, bottom: 0.14 } });
		const study = (color: string, width: 1 | 2, style = LineStyle.Solid) => chart.addSeries(LineSeries, { color, lineWidth: width, lineStyle: style, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
		this.ema20 = study('#ffb020', 2);
		this.ema50 = study('#7b61ff', 2);
		this.vwapLines = [study('#00e5ff', 2), study('rgba(0,229,255,0.55)', 1, LineStyle.Dashed), study('rgba(0,229,255,0.55)', 1, LineStyle.Dashed),
			study('rgba(0,229,255,0.30)', 1, LineStyle.Dashed), study('rgba(0,229,255,0.30)', 1, LineStyle.Dashed)];
	}

	// ---------------- cycle de vie
	start(): void {
		this.off = [
			market.onSnapshot(() => { void this.reload(); }),
			market.onTrades((trades, snapshot) => { if (!snapshot) this.enqueue(trades); }),
			market.onCandle((c) => this.updateCandle(c)),
			market.delta.subscribe((buckets) => this.setDelta(buckets))
		];
		void this.reload();
	}

	dispose(): void {
		this.disposed = true;
		this.off.forEach((fn) => fn()); this.off = [];
		if (this.retry) clearTimeout(this.retry);
		if (this.frame) cancelAnimationFrame(this.frame);
		this.listeners.clear();
	}

	onBars(fn: Listener): () => void { this.listeners.add(fn); return () => this.listeners.delete(fn); }
	private notify(): void { this.listeners.forEach((fn) => fn()); }

	async reload(): Promise<void> {
        if (!get(market.status).loaded) { this.view.state('Choisis une séance ou reprends la dernière séance.'); return; } // [Sol]
		if (this.disposed || this.loading) return;
		this.loading = true;
		this.view.state('Chargement des bougies…');
		try {
			const rows = await MarketApi.candles(this.symbol, this.tf, 500);
			if (this.disposed) return;
			this.setCandles(rows);
			this.view.state(rows.length ? '' : 'Aucune bougie : charge une séance');
		} catch {
			if (!this.disposed) { this.view.state('Historique indisponible — nouvelle tentative…'); this.retry = setTimeout(() => { void this.reload(); }, 5000); }
		} finally { this.loading = false; }
	}

	// ---------------- données
	setCandles(rows: Candle[]): void {
		this.candles = rows.slice();
		this.bars.clear();
		for (const c of rows) this.bars.set(c.time, c);
		this.barTimes = rows.map((c) => c.time).sort((a, b) => a - b);
		this.candle.setData(rows.map(asCandle));
		this.line.setData(rows.map((c) => ({ time: c.time as UTCTimestamp, value: c.close })));
		this.vol.setData(rows.map(asVolume));
		this.ema20.setData(this.ema20T.seed(rows).map(asPoint));
		this.ema50.setData(this.ema50T.seed(rows).map(asPoint));
		this.applyVwap(rows);
		this.curBar = rows.length ? { ...rows[rows.length - 1] } : null;
		if (rows.length) this.chart.timeScale().fitContent();
		this.notify();
	}

	/** Trame `candle` serveur = réconciliation ; entre deux trames la bougie vit via les trades. */
	updateCandle(c: Candle): void {
		if (!c || typeof c.time !== 'number') return;
		const cur = this.curBar;
		if (cur && c.time < cur.time) return;
		let merged = c;
		if (cur && c.time === cur.time) {
			merged = { time: c.time, open: c.open, high: Math.max(c.high, cur.high), low: Math.min(c.low, cur.low), close: cur.close, volume: Math.max(c.volume || 0, cur.volume || 0) };
		}
		this.curBar = { ...merged };
		this.registerBar(merged);
		this.renderBar(merged);
	}

	private enqueue(trades: Trade[]): void {
		this.queue.push(...trades);
		if (!this.frame) this.frame = requestAnimationFrame(() => { this.frame = 0; const q = this.queue; this.queue = []; this.applyTrades(q); });
	}

	/** Fusionne les trades du tape dans la bougie en formation (rollover local pour les TF <= 1h). */
	applyTrades(trades: Trade[]): void {
		if (!this.curBar || !trades.length) return;
		let bar = this.curBar, dirty = false;
		const step = this.tfSec;
		for (const t of trades) {
			if (t.price == null) continue;
			const ep = t.t;
			if (!Number.isFinite(ep) || ep < bar.time) continue;
			if (ep < bar.time + step) {
				if (t.price > bar.high) bar.high = t.price;
				if (t.price < bar.low) bar.low = t.price;
				bar.close = t.price; bar.volume = (bar.volume || 0) + (t.volume || 0); dirty = true;
			} else if (step <= 3600) {
				const bucket = ep - (ep % step);
				bar = this.curBar = { time: bucket, open: t.price, high: t.price, low: t.price, close: t.price, volume: t.volume || 0 };
				dirty = true;
			}
		}
		if (dirty) { this.registerBar(bar); this.renderBar(bar); }
	}

	private registerBar(c: Candle): void {
		const known = this.bars.has(c.time);
		this.bars.set(c.time, { ...c });
		if (!known) {
			if (!this.barTimes.length || c.time > this.barTimes[this.barTimes.length - 1]) this.barTimes.push(c.time);
			this.candles.push({ ...c });
		} else if (this.candles.length && this.candles[this.candles.length - 1].time === c.time) this.candles[this.candles.length - 1] = { ...c };
		this.notify();
	}

	private renderBar(c: Candle): void {
		this.candle.update(asCandle(c));
		this.line.update({ time: c.time as UTCTimestamp, value: c.close });
		this.vol.update(asVolume(c));
		const e20 = this.ema20T.update(c), e50 = this.ema50T.update(c);
		if (e20) this.ema20.update(asPoint(e20));
		if (e50) this.ema50.update(asPoint(e50));
		const v = this.vwapT.update(c);
		if (v) {
			const t = v.time as UTCTimestamp;
			this.vwapLines[0].update({ time: t, value: v.vw });
			this.vwapLines[1].update({ time: t, value: v.vw + v.sg }); this.vwapLines[2].update({ time: t, value: v.vw - v.sg });
			this.vwapLines[3].update({ time: t, value: v.vw + 2 * v.sg }); this.vwapLines[4].update({ time: t, value: v.vw - 2 * v.sg });
		}
	}

	private applyVwap(rows: Candle[]): void {
		const r = this.vwapT.seed(rows);
		const series = [r.vwap, r.up1, r.dn1, r.up2, r.dn2];
		series.forEach((pts, i) => this.vwapLines[i].setData(pts.map(asPoint)));
	}

	/** Delta agresseur : buckets minute agrégés en buckets du TF (snap sur le temps réel des bougies). */
	setDelta(minuteBars: DeltaBucket[]): void {
		if (!minuteBars.length) { if (this.deltaTimes.length) this.delta.setData([]); this.deltaTimes = []; return; }
		const step = this.tfSec, agg = new Map<number, number>();
		for (const b of minuteBars) {
			const t = this.barFor(b.t) ?? Math.floor(b.t / step) * step;
			agg.set(t, (agg.get(t) || 0) + (b.delta || 0));
		}
		const times = [...agg.keys()].sort((a, b) => a - b);
		const mk = (t: number) => ({ time: t as UTCTimestamp, value: agg.get(t)!, color: agg.get(t)! >= 0 ? 'rgba(38,166,106,.65)' : 'rgba(224,82,75,.65)' });
		const prev = this.deltaTimes;
		const incremental = prev.length && times.length >= prev.length && times.length - prev.length <= 1 && times[0] === prev[0];
		if (incremental) for (let i = Math.max(0, prev.length - 1); i < times.length; i++) this.delta.update(mk(times[i]));
		else this.delta.setData(times.map(mk));
		this.deltaTimes = times;
	}

	// ---------------- réglages
	setStyle(style: 'candles' | 'line'): void {
		this.candle.applyOptions({ visible: style === 'candles' });
		this.line.applyOptions({ visible: style === 'line' });
	}
	setEma(on: boolean): void { this.emaOn = on; this.ema20.applyOptions({ visible: on }); this.ema50.applyOptions({ visible: on }); }
	setVwap(mode: VwapMode, bands: boolean): void {
		this.vwapT.mode = mode; this.bandsOn = bands;
		const vis = mode !== 'off';
		this.vwapLines[0].applyOptions({ visible: vis });
		for (let i = 1; i < 5; i++) this.vwapLines[i].applyOptions({ visible: vis && bands });
		this.applyVwap(this.candles);
	}

	// ---------------- helpers géométrie temps
	/** Plus grand temps de bougie <= t (recherche binaire). */
	barFor(t: number): number | null {
		const a = this.barTimes;
		if (!a.length || t < a[0]) return null;
		let lo = 0, hi = a.length - 1;
		while (lo < hi) { const m = (lo + hi + 1) >> 1; if (a[m] <= t) lo = m; else hi = m - 1; }
		return a[lo];
	}
	/** Première bougie strictement après `t` dont la mèche touche `price`. */
	touchBarTime(t: number, price: number): number | null {
		const a = this.barTimes;
		if (!a.length || !this.bars.size) return null;
		let lo = 0, hi = a.length;
		while (lo < hi) { const mid = (lo + hi) >> 1; if (a[mid] <= t) lo = mid + 1; else hi = mid; }
		for (let i = lo; i < a.length; i++) { const b = this.bars.get(a[i]); if (b && b.low <= price && price <= b.high) return a[i]; }
		return null;
	}
	axisWidth(): number {
		try { const w = this.chart.priceScale('right').width(); if (w > 0) return w; } catch { /* échelle absente */ }
		return 70;
	}
	barSpacing(): number {
		try { const b = this.chart.timeScale().options().barSpacing; if (b > 0) return b; } catch { /* défaut */ }
		return 6;
	}
}

const asCandle = (c: Candle) => ({ time: c.time as UTCTimestamp, open: c.open, high: c.high, low: c.low, close: c.close });
const asVolume = (c: Candle) => ({ time: c.time as UTCTimestamp, value: c.volume || 0, color: c.close >= c.open ? 'rgba(38,166,106,.4)' : 'rgba(224,82,75,.4)' });
const asPoint = (p: { time: number; value: number }) => ({ time: p.time as UTCTimestamp, value: p.value });
