/**
 * PurpleReplay v2 — client WebSocket du replay
 * Une socket partagée, même origine (Vite proxifie /replay-ws vers /ws), reconnexion bornée,
 * réabonnement {symbol, tf} sans reconnexion, et chien de garde de fraîcheur : un TCP « à moitié
 * ouvert » (veille Windows, VPN) n'émet jamais onclose ; au-delà de STALE_MS sans trame on force
 * la fermeture, ce qui déclenche la reconnexion (anti-freeze hérité de la V1, conservé).
 */
import { isFrame, type Frame } from '$replay/domain/market/types';

type Handler = (frame: Frame) => void;
const STALE_MS = 40000;

export class ReplayFeed {
	private ws: WebSocket | null = null;
	private timer: ReturnType<typeof setTimeout> | null = null;
	private stale: ReturnType<typeof setTimeout> | null = null;
	private retry = 500;
	private active = false;
	private symbol = 'NQ';
	private tf = '5m';
	private listeners = new Map<string, Set<Handler>>();
	constructor(private path = '/ws') {}

	get isConnected(): boolean { return this.ws?.readyState === WebSocket.OPEN; }
	get subscription() { return { symbol: this.symbol, tf: this.tf }; }

	connect(symbol?: string, tf?: string): void {
		if (symbol) this.symbol = symbol;
		if (tf) this.tf = tf;
		this.active = true;
		if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return;
		if (this.timer) { clearTimeout(this.timer); this.timer = null; }
		const url = new URL(this.path, window.location.href);
		url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
		url.searchParams.set('symbol', this.symbol);
		url.searchParams.set('tf', this.tf);
		const ws = new WebSocket(url);
		this.ws = ws;
		ws.onopen = () => { this.retry = 500; this.bump(); this.emit({ type: 'connected' } as unknown as Frame); };
		ws.onmessage = (e) => {
			this.bump();
			let data: unknown;
			try { data = JSON.parse(e.data); } catch { return; }
			if (isFrame(data)) this.emit(data);
		};
		ws.onclose = () => {
			if (this.ws !== ws) return;
			this.ws = null;
			if (this.stale) { clearTimeout(this.stale); this.stale = null; }
			this.emit({ type: 'disconnected' } as unknown as Frame);
			if (this.active) { this.timer = setTimeout(() => this.connect(), this.retry); this.retry = Math.min(this.retry * 2, 10000); }
		};
		ws.onerror = () => ws.close();
	}

	/** Change symbole/TF : envoi sur la socket ouverte (le serveur renvoie un snapshot), sinon mémorisé pour la reconnexion. */
	subscribe(symbol: string, tf: string): void {
		this.symbol = symbol; this.tf = tf;
		if (this.isConnected) this.ws!.send(JSON.stringify({ symbol, tf }));
		else this.connect();
	}

	disconnect(): void {
		this.active = false;
		if (this.timer) clearTimeout(this.timer);
		if (this.stale) clearTimeout(this.stale);
		const ws = this.ws; this.ws = null; ws?.close();
	}

	on(type: string, fn: Handler): () => void {
		if (!this.listeners.has(type)) this.listeners.set(type, new Set());
		this.listeners.get(type)!.add(fn);
		return () => { this.listeners.get(type)?.delete(fn); };
	}

	private emit(frame: Frame): void { this.listeners.get(frame.type)?.forEach((fn) => fn(frame)); }

	private bump(): void {
		if (this.stale) clearTimeout(this.stale);
		this.stale = setTimeout(() => { try { this.ws?.close(); } catch { /* déjà fermée */ } }, STALE_MS);
	}
}

export const feed = new ReplayFeed();
