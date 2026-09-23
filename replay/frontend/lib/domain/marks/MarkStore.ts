/**
 * PurpleReplay v2 — magasin des marques orderflow
 * Normalisation + dédoublonnage des évènements classifiés (snapshot, flux live, historique SQLite chargé
 * par tranches horaires à la demande de la plage visible). Le cache est monotone pendant la session :
 * une réponse tardive ne fait jamais disparaître une marque déjà vue. Logique pure, testable sans DOM.
 */
import type { Mark, MarkKind, Side, Trade } from '../market/types';

export interface StoredMark {
	t: number; price: number; vol: number; side: 'buy' | 'sell'; kind: MarkKind;
	score?: number | null; reason?: string | null; confidence?: number | null; dominance?: number | null;
	speed?: number | null; lots_per_sec?: number | null; weight?: number | null; liveUntil: number;
}
export type Fetcher = (symbol: string, from: number, to: number, limit: number) => Promise<{ big_prints: Mark[]; truncated: boolean }>;

const LIVE_TTL = 10 * 60 * 1000;

export function normalizeMark(m: Partial<Mark & Trade> & { t?: number; epoch?: number; _live?: boolean }, now = Date.now()): StoredMark | null {
	if (!m || m.price == null) return null;
	const t = typeof m.t === 'number' ? m.t : typeof m.epoch === 'number' ? m.epoch : m.timestamp ? Date.parse(m.timestamp) / 1000 : NaN;
	if (!Number.isFinite(t)) return null;
	const vol = Number(m.trigger_volume != null ? m.trigger_volume : m.volume != null ? m.volume : 0) || 0;
	return {
		t: Math.floor(t), price: Number(m.price), vol, side: (m.side as Side) === 'sell' ? 'sell' : 'buy',
		kind: (m.kind as MarkKind) || 'block', score: m.score ?? null, reason: m.reason ?? null, confidence: m.confidence ?? null,
		dominance: m.dominance ?? null, speed: m.speed ?? null, lots_per_sec: m.lots_per_sec ?? null, weight: m.weight ?? null,
		liveUntil: m._live ? now + LIVE_TTL : 0
	};
}

export function markKey(m: StoredMark): string {
	return [m.t, m.price.toFixed(5), m.side, m.kind, Math.round(m.vol), m.score != null ? Math.round(m.score) : ''].join('|');
}

export class MarkStore {
	marks: StoredMark[] = [];
	private map = new Map<string, StoredMark>();
	private symbol: string | null = null;
	private loaded = new Set<string>();
	private queued = new Set<string>();
	private queue: { from: number; to: number; key: string }[] = [];
	private inFlight: string | null = null;
	private timer: ReturnType<typeof setTimeout> | null = null;
	private cursorCap = Infinity;
	chunkSec = 3600;
	minChunkSec = 300;
	limit = 5000; // [Sol] Same contract as the API;
	onChange: () => void = () => {};

	constructor(private fetcher: Fetcher | null) {}

	setSymbol(symbol: string): void {
		if (this.symbol === symbol) return;
		this.symbol = symbol;
		this.clear();
	}
	/** Anti-spoiler : aucune tranche au-delà du curseur n'est demandée. */
	setCursorCap(t: number): void { this.cursorCap = t; }

    stop(): void { this.clear(); this.symbol=null; this.onChange=()=>{}; } // [Sol]
	clear(): void {
        if (this.timer) { clearTimeout(this.timer); this.timer=null; }
		this.map.clear(); this.marks = []; this.loaded.clear(); this.queued.clear(); this.queue = []; this.inFlight = null;
	}

	seed(list: Mark[]): void { this.clear(); this.merge(list); }

	merge(list: (Mark | Trade)[], live = false): boolean {
		let changed = false;
		const now = Date.now();
		for (const raw of list) {
			const m = normalizeMark({ ...(raw as Mark), _live: live } as never, now);
			if (!m) continue;
			const key = markKey(m);
			const prev = this.map.get(key);
			if (prev && prev.liveUntil && !m.liveUntil) m.liveUntil = prev.liveUntil;
			this.map.set(key, m);
			changed = true;
		}
		if (changed) { this.marks = [...this.map.values()].sort((a, b) => a.t - b.t); this.onChange(); }
		return changed;
	}

	/** Trades du flux : seuls les prints classifiés deviennent des marques (jamais les bulles brutes). */
	pushTrades(trades: Trade[]): void {
		const marked = trades.filter((t) => t.kind);
		if (marked.length) this.merge(marked, true);
	}

	/** Demande (debounce) l'historique couvrant la plage visible, par tranches horaires. */
	requestRange(from: number, to: number): void {
		if (!this.fetcher || !this.symbol) return;
		if (this.timer) clearTimeout(this.timer);
		this.timer = setTimeout(() => { this.enqueueWindow(from, to); void this.drain(); }, 220);
	}

	private enqueueWindow(from: number, to: number): void {
		const width = Math.max(60, to - from);
		const pad = Math.max(900, Math.min(6 * 3600, width * 0.25));
		const start = Math.floor((from - pad) / this.chunkSec) * this.chunkSec;
		const end = Math.min(Math.floor((to + pad) / this.chunkSec) * this.chunkSec, Math.floor(this.cursorCap / this.chunkSec) * this.chunkSec);
		const chunks: { from: number; to: number }[] = [];
		for (let c = start; c <= end; c += this.chunkSec) chunks.push({ from: c, to: c + this.chunkSec - 1 });
		chunks.sort((a, b) => b.from - a.from); // le plus récent d'abord
		for (const c of chunks) this.enqueue(c.from, c.to, false);
	}

	private enqueue(from: number, to: number, front: boolean): void {
		const key = `${this.symbol}|${Math.floor(from)}|${Math.floor(to)}`;
		if (this.loaded.has(key) || this.queued.has(key) || this.inFlight === key) return;
		const item = { from: Math.floor(from), to: Math.floor(to), key };
		if (front) this.queue.unshift(item); else this.queue.push(item);
		this.queued.add(key);
	}

	private async drain(): Promise<void> {
		if (this.inFlight || !this.fetcher || !this.symbol) return;
		const item = this.queue.shift();
		if (!item) return;
		this.queued.delete(item.key);
		this.inFlight = item.key;
		const symbol = this.symbol;
		try {
			const data = await this.fetcher(symbol, item.from, Math.min(item.to, this.cursorCap), this.limit);
			if (this.inFlight !== item.key || this.symbol !== symbol) return;
			this.merge(data.big_prints || []);
			this.loaded.add(item.key);
			if (data.truncated && item.to - item.from > this.minChunkSec) {
				const mid = Math.floor((item.from + item.to) / 2);
				this.enqueue(item.from, mid, true); this.enqueue(mid + 1, item.to, true);
			}
		} catch { /* historique indisponible : on retentera au prochain mouvement */ } finally {
			if (this.inFlight === item.key) this.inFlight = null;
			if (this.queue.length) this.timer = setTimeout(() => { void this.drain(); }, 25);
		}
	}
}
