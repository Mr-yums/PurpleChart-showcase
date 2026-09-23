// Journal d'edge, agrégats et tag manuel sticky.
import { api, qs } from './client';
import type { EdgeGroup, EdgeTrade, GexGroup } from '$replay/domain/market/types';

export class EdgeApi {
	static journal(limit = 500) { return api.get<{ ok: boolean; trades: EdgeTrade[] }>(`/edge/journal${qs({ limit })}`); }
	static stats() { return api.get<{ ok: boolean; groups: EdgeGroup[]; total_trades: number }>('/edge/stats'); }
	static gexStats() { return api.get<{ ok: boolean; groups: GexGroup[]; total_trades: number }>('/edge/gex-stats'); }
	static setTag(symbol: string, tag: string | null) { return api.post<{ ok: boolean; tag: string | null; error?: string }>('/edge/tag', { symbol, tag }); }
	static sticky(symbol: string) { return api.get<{ ok: boolean; tag: string | null }>(`/edge/sticky${qs({ symbol })}`); }
}
