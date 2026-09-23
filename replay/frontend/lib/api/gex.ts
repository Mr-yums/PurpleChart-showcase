// Niveaux gamma / vanna, forward-fill sans look-ahead côté serveur.
import { api, qs } from './client';
import type { GexLevel, VannaSnapshot } from '$replay/domain/market/types';

export class GexApi {
	static levels(symbol: string, from: number, to: number) {
		return api.get<{ levels: GexLevel[]; stale: boolean; count: number }>(`/gex/levels${qs({ symbol, from, to })}`);
	}
	static async vanna(symbol = 'NDX', to?: number): Promise<VannaSnapshot | null> {
		try { return await api.get<VannaSnapshot>(`/gex/vanna${qs({ symbol, to })}`); } catch { return null; }
	}
}
