// Données marché rejouées : instruments, bougies, marques (plafonnés au curseur côté serveur).
import { api, qs } from './client';
import type { Candle, Instrument, Mark } from '$replay/domain/market/types';

export class MarketApi {
	static instruments() { return api.get<{ instruments: Instrument[]; timeframes: string[] }>('/market/instruments'); }
	static candles(symbol: string, tf: string, n = 500) {
		return api.get<{ candles: Candle[] }>(`/market/candles${qs({ symbol, tf, n })}`).then((r) => r.candles);
	}
	static events(symbol: string, from: number, to: number, limit = 2000) {
		return api.get<{ big_prints: Mark[]; truncated: boolean; returned: number }>(`/market/events${qs({ symbol, from, to, limit })}`);
	}

}
