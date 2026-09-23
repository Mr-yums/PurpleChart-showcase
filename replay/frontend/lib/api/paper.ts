// Paper-trading : mutations explicites, jamais rejouées automatiquement en cas de timeout.
import { api, qs } from './client';
import type { Account, Position, TicketSpec } from '$replay/domain/market/types';

export interface PlacePayload {
	symbol: string; side: 'buy' | 'sell'; size: number; sl_price: number | null; tp_price: number | null;
	entry_ref: number | null; risk_usd: number; entry_tag?: string | null;
}
export interface PlaceResult { ok: boolean; fill: number; sl_points: number; tp_points: number; regime: string | null; setup: string | null; dry_run: boolean; }

export class PaperApi {
	static ticket(symbol: string) { return api.get<TicketSpec>(`/paper/ticket${qs({ symbol })}`); }
	static account() { return api.get<{ account: Account }>('/paper/account').then((r) => r.account); }
	static positions() { return api.get<{ positions: Position[] }>('/paper/positions').then((r) => r.positions); }
	static place(payload: PlacePayload) { return api.post<PlaceResult>('/paper/place', payload); }
	static flatten() { return api.post<{ ok: boolean; closed: boolean; pnl: number }>('/paper/flatten'); }
	static breakeven(offset_ticks = 0) { return api.post<{ ok: boolean; entry: number; sl: number }>('/paper/breakeven', { offset_ticks }); }
	static partialClose(size: number) { return api.post<{ ok: boolean; closed: number; remaining: number; pnl: number }>('/paper/partial-close', { size }); }
	static modify(which: 'sl' | 'tp', price: number) { return api.post<{ ok: boolean; price: number }>('/paper/modify', { which, price }); }
	static reset() { return api.post<{ ok: boolean; account: Account }>('/paper/reset'); }
}
