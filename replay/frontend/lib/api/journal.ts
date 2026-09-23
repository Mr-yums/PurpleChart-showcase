// Journal unifié et sessions d'entraînement.
import { api, qs } from './client';
import type { JournalPayload, SessionsPayload, SessionRecord, UnifiedTrade, TradeStats } from '$replay/domain/market/types';

export class JournalApi {
	static unified(opts: { since?: number; all?: boolean } = {}) {
		return api.get<JournalPayload>(`/journal${qs({ since: opts.since, all: opts.all ? 1 : undefined })}`);
	}
	static sessions() { return api.get<SessionsPayload>('/journal/sessions'); }
	static save(label: string) { return api.post<{ ok: boolean; session?: SessionRecord; message?: string }>('/journal/sessions/save', { label }); }
	static demoTrades(limit = 0, mode = '') {
		return api.get<{ ok: boolean; trades: UnifiedTrade[]; summary: Record<string, TradeStats> }>(`/journal/demo-trades${qs({ limit, mode })}`);
	}
}
