/**
 * PurpleReplay v2 — desk de paper-trading
 * État du setup (armement au clic ou aux boutons, lignes SL/TP glissables, sizing live), envoi au
 * serveur, positions/compte reçus par WebSocket. Un seul desk pour tous les montages du graphique.
 */
import { get, writable, type Writable } from 'svelte/store';
import { PaperApi } from '$replay/api/paper';
import { EdgeApi } from '$replay/api/edge';
import { market } from './MarketStore';
import { RiskCalculator, type Setup, type Sizing } from '$replay/domain/orders/RiskCalculator';
import type { TicketSpec } from '$replay/domain/market/types';

export interface DeskState {
	symbol: string; spec: TicketSpec | null; setup: Setup | null; sizing: Sizing | null; qty: number; budget: number;
	rr: number; busy: boolean; sending: boolean; status: string; statusOk: boolean; tag: string | null; pendingPrice: number | null;
}

export class PaperDesk {
	private value: DeskState = { symbol: 'NQ', spec: null, setup: null, sizing: null, qty: 1, budget: 250, rr: 1, busy: false, sending: false, status: '', statusOk: true, tag: null, pendingPrice: null };
	private store: Writable<DeskState> = writable(this.value);
	subscribe = this.store.subscribe;
	private budgetTouched = false;
	private statusTimer: ReturnType<typeof setTimeout> | null = null;
	private lastPrice: number | null = null;
	private off: (() => void)[] = [];
	private lifecycle = 0;

	get calc(): RiskCalculator | null { return this.value.spec ? new RiskCalculator(this.value.spec) : null; }
	get price(): number | null { return this.lastPrice; }

	private commit(): void {
		const s = this.value;
		s.sizing = s.setup && s.spec && this.lastPrice != null ? new RiskCalculator(s.spec).evaluate(s.setup, this.lastPrice, s.budget) : null;
		if (s.sizing) s.qty = s.sizing.qty;
		this.store.set({ ...s });
	}

	async start(symbol: string): Promise<void> {
		const lifecycle = ++this.lifecycle;
		this.cancel();
		this.value.symbol = symbol; this.value.spec = null;
		this.commit();
		if (!this.off.length) this.off = [market.lastPrice.subscribe((p) => { this.lastPrice = p; if (this.value.setup) this.commit(); })];
		try {
			const [spec, sticky] = await Promise.all([PaperApi.ticket(symbol), EdgeApi.sticky(symbol).catch(() => ({ tag: null }))]);
			if (lifecycle !== this.lifecycle) return;
			this.value.spec = spec;
			this.value.tag = sticky.tag ?? null;
			if (!this.budgetTouched && spec.default_risk_usd) this.value.budget = spec.default_risk_usd;
		} catch (e) { this.setStatus('ticket indisponible : ' + (e as Error).message, false); }
		this.commit();
	}

	stop(): void { if (this.statusTimer) { clearTimeout(this.statusTimer);this.statusTimer=null; } this.cancel(); this.lifecycle++; this.off.forEach((f) => f()); this.off = []; }

	setQty(q: number): void { this.value.qty = Math.max(1, Math.floor(q || 1)); this.commit(); }
	setBudget(b: number): void { this.budgetTouched = true; this.value.budget = Math.max(1, b || 1); this.commit(); }
	setRR(rr: number): void {
		this.value.rr = rr;
		const s = this.value.setup, c = this.calc;
		if (s && c && this.lastPrice != null) s.tp = c.target(s.side, this.lastPrice, s.sl, rr);
		this.commit();
	}

	/** Armement : SL au prix donné, ou SL auto au budget (boutons). TP miroir selon le R:R. */
	arm(side: 'buy' | 'sell', slPrice: number | null = null): void {
		const c = this.calc, entry = this.lastPrice;
		if (!c || entry == null) { this.setStatus('pas de prix — charge une session', false); return; }
		const sl = c.snap(slPrice ?? c.autoStop(side, entry, this.value.qty, this.value.budget));
		this.value.setup = { side, sl, tp: c.target(side, entry, sl, this.value.rr) };
		this.commit();
	}

	/** Clic sur le graphique : sous le prix = achat (SL au clic), au-dessus = vente. */
	clickAt(price: number): void {
		if (this.value.setup || !this.value.spec || this.lastPrice == null || price === this.lastPrice) return;
		this.arm(price < this.lastPrice ? 'buy' : 'sell', price);
	}

	move(kind: 'sl' | 'tp', price: number): void {
		const s = this.value.setup, c = this.calc;
		if (!s || !c) return;
		if (kind === 'sl') s.sl = c.snap(price); else s.tp = c.snap(price);
		this.commit();
	}

	cancel(): void { if (!this.value.setup) return; this.value.setup = null; this.commit(); }

	async confirm(): Promise<void> {
		const s = this.value.setup, z = this.value.sizing;
		if (this.value.sending || !s || !z) return;
		if (!z.valid) { this.setStatus('REFUS : ' + z.reason, false); return; }
		const lbl = s.side === 'buy' ? 'ACHAT' : 'VENTE';
		this.value.sending = true; this.value.busy = true; this.value.pendingPrice = z.entry;
		this.setStatus(`${lbl} ×${z.qty} — envoi…`, true);
		try {
			const d = await PaperApi.place({ symbol: this.value.symbol, side: s.side, size: z.qty, sl_price: s.sl, tp_price: s.tp, entry_ref: z.entry, risk_usd: z.budget });
			this.setStatus(`${lbl} ×${z.qty} @ ${d.fill} — SL ${d.sl_points} pts (−${Math.round(z.risk)} $)` + (d.tp_points ? ` · TP ${d.tp_points} pts` : '') + (d.regime ? ` · ${d.regime}` : ''), true);
			this.value.setup = null;
		} catch (e) { this.setStatus('REFUS : ' + (e as Error).message, false); }
		this.value.sending = false; this.value.busy = false; this.value.pendingPrice = null;
		this.commit();
	}

	async flatten(): Promise<void> { await this.run('FLAT — envoi…', async () => { const d = await PaperApi.flatten(); return d.closed ? `Position fermée · ${d.pnl >= 0 ? '+' : ''}${d.pnl.toFixed(2)} $` : 'Aucune position'; }); }
	async breakeven(): Promise<void> { await this.run('SL → BE — envoi…', async () => { const d = await PaperApi.breakeven(); return `SL → BE @ ${d.sl} (entrée ${d.entry})`; }); }
	async partial(n: number): Promise<void> { await this.run(`−${n} contrat(s) — envoi…`, async () => { const d = await PaperApi.partialClose(n); return `−${d.closed} contrat(s) · reste ${d.remaining} · ${d.pnl >= 0 ? '+' : ''}${d.pnl.toFixed(2)} $`; }); }
	async modify(kind: 'sl' | 'tp', price: number): Promise<void> { await this.run(`${kind.toUpperCase()} → ${price}…`, async () => { const d = await PaperApi.modify(kind, price); return `${kind.toUpperCase()} déplacé → ${d.price}`; }); }
	async reset(): Promise<void> { await this.run('reset…', async () => { await PaperApi.reset(); return 'Compte remis à 50 000 $'; }); }
	async setTag(tag: string | null): Promise<void> {
		try { const r = await EdgeApi.setTag(this.value.symbol, tag); this.value.tag = r.ok ? r.tag : this.value.tag; } catch { /* tag inchangé */ }
		this.commit();
	}

	private async run(label: string, fn: () => Promise<string>): Promise<void> {
		if (this.value.busy) return;
		this.value.busy = true; this.setStatus(label, true); this.commit();
		try { this.setStatus(await fn(), true); } catch (e) { this.setStatus('Refusé : ' + (e as Error).message, false); }
		this.value.busy = false; this.commit();
	}

	private setStatus(msg: string, ok: boolean): void {
		this.value.status = msg; this.value.statusOk = ok; this.store.set({ ...this.value });
		if (this.statusTimer) clearTimeout(this.statusTimer);
		this.statusTimer = setTimeout(() => { this.value.status = ''; this.store.set({ ...this.value }); }, 10000);
	}

	snapshot(): DeskState { return get(this.store); }
}

export const desk = new PaperDesk();
