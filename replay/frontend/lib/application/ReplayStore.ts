/**
 * PurpleReplay v2 — magasin du replay
 * Sessions disponibles, instruments, sélection courante et actions de contrôle. Le statut vient des
 * trames WebSocket (MarketStore.status) : plus aucun sondage HTTP à 1 s comme dans la V1.
 */
import { get, writable, type Writable } from 'svelte/store';
import {sessionTime} from '$replay/domain/replay/sessionTime';
import { ReplayApi } from '$replay/api/replay';
import { MarketApi } from '$replay/api/market';
import { market } from './MarketStore';
import type { Instrument, SessionInfo } from '$replay/domain/market/types';

export interface ReplaySelection { symbol: string; tf: string; }

export class ReplayStore {
 private offStatus: (() => void) | null = null;
 private generation = 0;
 stop(): void { this.generation++; this.offStatus?.(); this.offStatus=null; market.stop(); } // [Sol]
	readonly sessions: Writable<SessionInfo[]> = writable([]);
	readonly instruments: Writable<Instrument[]> = writable([]);
	readonly timeframes: Writable<string[]> = writable(['15s', '1m', '5m', '15m', '30m', '1h', '4h', '6h', '1D']);
	readonly selection: Writable<ReplaySelection> = writable({ symbol: 'NQ', tf: '5m' });
	readonly message: Writable<string> = writable('');
	readonly status = market.status;

	async init(): Promise<void> {
        const gen = ++this.generation;
        this.offStatus?.();
		try {
			const meta = await MarketApi.instruments();
            if (gen !== this.generation) return; // [Sol] Late response cannot restart a retired mode.
			this.instruments.set(meta.instruments);
			this.timeframes.set(meta.timeframes);
			const saved = this.readSelection();
			const symbols = meta.instruments.map((i) => i.symbol);
			const symbol = saved && symbols.includes(saved.symbol) ? saved.symbol : symbols[0] ?? 'NQ';
			const tf = saved && meta.timeframes.includes(saved.tf) ? saved.tf : '5m';
			this.selection.set({ symbol, tf });
			market.start(symbol, tf);
			// Le symbole affiché suit la séance chargée côté serveur (une seule session à la fois).
			this.offStatus = market.status.subscribe((st) => {
				const cur = get(this.selection);
				if (st.loaded && st.symbol && st.symbol !== cur.symbol && symbols.includes(st.symbol)) this.select(st.symbol, cur.tf);
			});
		} catch (e) {
			this.message.set('API instruments indisponible : ' + (e as Error).message);
		}
		await this.refreshSessions();
	}

	async refreshSessions(): Promise<void> {
		try { this.sessions.set(await ReplayApi.sessions()); } catch { this.message.set('erreur /api/replay/sessions'); }
	}

	select(symbol: string, tf: string): void {
		this.selection.set({ symbol, tf });
		this.saveSelection(symbol, tf);
		market.select(symbol, tf);
	}

	instrument(symbol: string): Instrument | undefined { return get(this.instruments).find((i) => i.symbol === symbol); }

	/** Charge une séance à une heure UTC ; le front se réinitialise entièrement via le snapshot serveur. */
	async load(session: SessionInfo, hh: number, mm: number, speed: number): Promise<boolean> {
		const start = sessionTime(session, hh, mm);
		this.message.set('chargement…');
		try {
			const r = await ReplayApi.load(session.symbol, start, speed,session.source);
			if (!r.ok) { this.message.set('erreur de chargement'); return false; }
			const tf = get(this.selection).tf;
			this.select(session.symbol, tf);
			this.message.set('');
			return true;
		} catch (e) { this.message.set('erreur: ' + (e as Error).message); return false; }
	}

	async loadAt(symbol: string, startTs: number, speed: number): Promise<boolean> {
		const s = get(this.sessions).find((x) => x.symbol === symbol && startTs >= x.first_ts && startTs <= x.last_ts);
		if (!s) { this.message.set('séance absente de l’archive'); return false; }
		const d = new Date(startTs * 1000);
		return this.load(s, d.getUTCHours(), d.getUTCMinutes(), speed);
	}

	async toggle(): Promise<void> {
		const st = get(this.status);
		try { if (st.playing) await ReplayApi.pause(); else await ReplayApi.play(); } catch (e) { this.message.set((e as Error).message); }
	}
	async speed(v: number): Promise<void> { try { await ReplayApi.speed(v); } catch { /* statut suivra */ } }

	private readSelection(): ReplaySelection | null {
		try { const raw = localStorage.getItem('pr2-selection'); return raw ? JSON.parse(raw) : null; } catch { return null; }
	}
	private saveSelection(symbol: string, tf: string): void {
		try { localStorage.setItem('pr2-selection', JSON.stringify({ symbol, tf })); } catch { /* stockage indisponible */ }
	}
}

export const replay = new ReplayStore();
