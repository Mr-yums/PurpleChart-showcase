/**
 * PurpleReplay v2 — magasin marché
 * Point unique de routage des trames WebSocket. Expose des stores Svelte pour l'état lent
 * (dom, stats, statut, positions, compte, dernier prix) et des abonnements impératifs pour les
 * flux denses (trades, bougies, snapshot) afin que chart/tape reçoivent des lots sans churn de store.
 * Dédoublonnage par `seq` : un broadcast qui recouvre le snapshot est ignoré.
 */
import { writable, type Writable } from 'svelte/store';
import { feed } from '$replay/websocket/feed';
import { MarketApi } from '$replay/api/market';
import { MarkStore } from '$replay/domain/marks/MarkStore';
import type { Account, Candle, DeltaBucket, DomBook, Frame, Position, ReplayStatus, SnapshotFrame, TapeFrame, TapeStats, Trade } from '$replay/domain/market/types';

type TradeListener = (trades: Trade[], snapshot: boolean) => void;
type CandleListener = (candle: Candle, tf: string) => void;
type SnapshotListener = (snapshot: SnapshotFrame['data']) => void;

const EMPTY_STATS: TapeStats = { cvd: 0, buys: 0, sells: 0, total: 0, big_threshold: 50 };
const DEFAULT_STATUS: ReplayStatus = {
	loaded: false, playing: false, ended: false, live: false, buffering: false, symbol: null, speed: 5, cursor_ts: 0,
	start_ts: 0, context_start: 0, seq: 0, pending: 0, clients: 0, feed_connected: false
};

export class MarketStore {
	symbol = 'NQ';
	tf = '5m';
	readonly dom: Writable<DomBook | null> = writable(null);
	readonly stats: Writable<TapeStats> = writable(EMPTY_STATS);
	readonly status: Writable<ReplayStatus> = writable(DEFAULT_STATUS);
	readonly positions: Writable<Position[]> = writable([]);
	readonly account: Writable<Account | null> = writable(null);
	readonly lastPrice: Writable<number | null> = writable(null);
	readonly connected: Writable<boolean> = writable(false);
	readonly delta: Writable<DeltaBucket[]> = writable([]);
	readonly marks = new MarkStore((symbol, from, to, limit) => MarketApi.events(symbol, from, to, limit));
	trades: Trade[] = [];
	private seq = 0;
	private deltaMap = new Map<number, DeltaBucket>();
	private tradeListeners = new Set<TradeListener>();
	private candleListeners = new Set<CandleListener>();
	private snapshotListeners = new Set<SnapshotListener>();
	private off: (() => void)[] = [];
	private started = false;

	start(symbol: string, tf: string): void {
		this.symbol = symbol; this.tf = tf;
		this.marks.setSymbol(symbol);
		if (!this.started) {
			this.started = true;
			this.off = [
				feed.on('connected', () => this.connected.set(true)),
				feed.on('disconnected', () => this.connected.set(false)),
				feed.on('snapshot', (f) => this.handleSnapshot(f as SnapshotFrame)),
				feed.on('tape', (f) => this.handleTape(f as TapeFrame)),
				feed.on('dom', (f) => { if (f.type === 'dom' && f.symbol === this.symbol) { this.dom.set(f.data); this.setLast(f.data.last); } }),
				feed.on('candle', (f) => { if (f.type === 'candle' && f.symbol === this.symbol && f.tf === this.tf) this.candleListeners.forEach((fn) => fn(f.data, f.tf)); }),
				feed.on('positions', (f) => { if (f.type === 'positions') { this.positions.set(f.data.positions); this.account.set(f.data.account); } }),
				feed.on('status', (f) => { if (f.type === 'status') this.applyStatus(f.data); })
			];
		}
		feed.connect(symbol, tf);
	}

	stop(): void {
		this.off.forEach((fn) => fn()); this.off = []; this.started = false;
		feed.disconnect();
        this.marks.stop(); this.reset(); this.status.set(DEFAULT_STATUS); this.connected.set(false);
        this.tradeListeners.clear();this.candleListeners.clear();this.snapshotListeners.clear();
	}

	/** Changement de symbole ou de TF : purge locale, le serveur renvoie un snapshot. */
	select(symbol: string, tf: string): void {
		const symbolChanged = symbol !== this.symbol;
		this.symbol = symbol; this.tf = tf;
		if (symbolChanged) { this.reset(); this.marks.setSymbol(symbol); }
		feed.subscribe(symbol, tf);
	}

	private reset(): void {
		this.trades = []; this.seq = 0; this.deltaMap.clear();
		this.delta.set([]); this.stats.set(EMPTY_STATS); this.dom.set(null); this.lastPrice.set(null);
	}

	private applyStatus(s: ReplayStatus): void {
		this.status.set(s);
		if (s.loaded && !s.live && s.symbol === this.symbol) this.marks.setCursorCap(s.cursor_ts);
		else this.marks.setCursorCap(Infinity);
	}

	private setLast(price: number | null | undefined): void {
		if (price != null && Number.isFinite(price)) this.lastPrice.set(price);
	}

	private handleSnapshot(f: SnapshotFrame): void {
		if (f.symbol !== this.symbol) return;
		const d = f.data;
		this.seq = d.seq || 0;
		this.trades = d.trades.slice(-2500);
		this.deltaMap.clear();
		for (const b of d.delta_minutes) this.deltaMap.set(b.t, b);
		this.delta.set([...this.deltaMap.values()].sort((a, b) => a.t - b.t));
		this.stats.set(d.stats);
		this.dom.set(d.dom);
		if (d.dom) this.setLast(d.dom.last);
		this.positions.set(d.positions); this.account.set(d.account);
		this.applyStatus(d.status);
		this.marks.seed(d.marks);
		this.marks.pushTrades(d.trades);
		this.tradeListeners.forEach((fn) => fn(this.trades, true));
		this.snapshotListeners.forEach((fn) => fn(d));
	}

	private handleTape(f: TapeFrame): void {
		if (f.symbol !== this.symbol) return;
		const d = f.data;
		const fresh = d.trades.filter((t) => t.seq == null || t.seq > this.seq);
		if (d.seq != null && d.seq > this.seq) this.seq = d.seq;
		if (fresh.length) {
			this.trades.push(...fresh);
			if (this.trades.length > 2500) this.trades.splice(0, this.trades.length - 2500);
			this.marks.pushTrades(fresh);
			this.setLast(fresh[fresh.length - 1].price);
			this.tradeListeners.forEach((fn) => fn(fresh, false));
		}
		this.stats.set(d.stats);
		let touched = false;
		for (const b of d.delta_minutes) { this.deltaMap.set(b.t, b); touched = true; }
		if (touched) {
			const sorted = [...this.deltaMap.values()].sort((a, b) => a.t - b.t);
			if (sorted.length > 1600) { for (const b of sorted.splice(0, sorted.length - 1500)) this.deltaMap.delete(b.t); }
			this.delta.set(sorted);
		}
	}

	onTrades(fn: TradeListener): () => void { this.tradeListeners.add(fn); return () => this.tradeListeners.delete(fn); }
	onCandle(fn: CandleListener): () => void { this.candleListeners.add(fn); return () => this.candleListeners.delete(fn); }
	onSnapshot(fn: SnapshotListener): () => void { this.snapshotListeners.add(fn); return () => this.snapshotListeners.delete(fn); }
}

export const market = new MarketStore();
