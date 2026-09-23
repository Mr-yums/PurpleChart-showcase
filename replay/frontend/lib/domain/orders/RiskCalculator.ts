/**
 * PurpleReplay v2 — sizing d'un setup
 * Risque fixe + SL libre => taille déduite : contrats = floor(budget / (ticks_SL × valeur_tick)),
 * plancher 1 contrat (risque réel affiché et signalé), plafond serveur. Mêmes règles que le ticket V1.
 * Calcul pur : aucun DOM, aucun réseau.
 */
import type { TicketSpec } from '../market/types';

export interface Setup { side: 'buy' | 'sell'; sl: number; tp: number | null; }
export interface Sizing {
	entry: number; qty: number; slTicks: number; budget: number; risk: number; tooClose: boolean; minTicks: number;
	floored: boolean; capped: boolean; tpTicks: number | null; gain: number | null; rr: number | null;
	badSL: boolean; badTP: boolean; valid: boolean; reason: string;
}

export class RiskCalculator {
	constructor(readonly spec: TicketSpec) {}

	snap(price: number): number {
		const t = this.spec.tick_size || 0.25;
		return Number((Math.round(price / t) * t).toFixed(10));
	}

	/** SL automatique à la distance du budget pour `qty` contrats (boutons ACHAT / VENTE). */
	autoStop(side: 'buy' | 'sell', entry: number, qty: number, budget: number): number {
		const sp = this.spec, dir = side === 'buy' ? 1 : -1;
		const ticks = Math.max(sp.min_bracket_ticks || 4, Math.floor(budget / (Math.max(1, qty) * sp.tick_value)));
		return this.snap(entry - dir * ticks * sp.tick_size);
	}

	target(side: 'buy' | 'sell', entry: number, sl: number, rr: number): number | null {
		if (!(rr > 0)) return null;
		const dir = side === 'buy' ? 1 : -1;
		const dist = Math.max(Math.abs(entry - sl), this.spec.tick_size);
		return this.snap(entry + dir * dist * rr);
	}

	evaluate(setup: Setup, entry: number, budget: number): Sizing {
		const sp = this.spec, dir = setup.side === 'buy' ? 1 : -1;
		const minTicks = sp.min_bracket_ticks || 4;
		const slTicks = Math.max(1, Math.round(Math.abs(entry - setup.sl) / sp.tick_size));
		budget = Math.max(1, budget || sp.default_risk_usd || 250);
		const maxQ = sp.max_contracts || 10;
		const rawQ = Math.floor(budget / (slTicks * sp.tick_value));
		const qty = Math.min(Math.max(1, rawQ), maxQ);
		const badSL = (entry - setup.sl) * dir <= 0;
		const badTP = setup.tp != null && (setup.tp - entry) * dir <= 0;
		const out: Sizing = {
			entry, qty, slTicks, budget, risk: qty * slTicks * sp.tick_value, tooClose: slTicks < minTicks, minTicks,
			floored: rawQ < 1, capped: rawQ > maxQ, tpTicks: null, gain: null, rr: null, badSL, badTP, valid: false, reason: ''
		};
		if (setup.tp != null) {
			out.tpTicks = Math.max(1, Math.round(Math.abs(setup.tp - entry) / sp.tick_size));
			out.gain = qty * out.tpTicks * sp.tick_value;
			out.rr = out.tpTicks / slTicks;
		}
		if (badSL || badTP) out.reason = 'SL/TP du mauvais côté de l’entrée — replace la ligne';
		else if (out.tooClose) out.reason = `SL trop proche : minimum ${minTicks} ticks`;
		else if (out.floored) out.reason = `Risque trop haut : ${Math.round(out.risk)} $ > budget ${Math.round(budget)} $ avec 1 contrat`;
		else if (out.capped) out.reason = `Plafonné à ${qty} contrats (limite serveur)`;
		out.valid = !badSL && !badTP && !out.tooClose && !out.floored;
		return out;
	}
}
