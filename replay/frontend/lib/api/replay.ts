// Contrôle du replay et catalogue des régimes.
import { api, qs } from './client';
import type { ReplayStatus, SessionInfo, RegimeCatalogue } from '$replay/domain/market/types';

export class ReplayApi {
	static sessions() { return api.get<{ sessions: SessionInfo[] }>('/replay/sessions').then((r) => r.sessions); }
	static load(symbol: string, start_ts: number, speed: number, source = 'legacy') { return api.post<{ ok: boolean; cursor: number; speed: number }>('/replay/load', { symbol, start_ts, speed, source }); }
	static play() { return api.post<{ ok: boolean; playing: boolean }>('/replay/play'); }
	static pause() { return api.post<{ ok: boolean; playing: boolean }>('/replay/pause'); }
	static speed(speed: number, source = 'legacy') { return api.post<{ ok: boolean; speed: number }>('/replay/speed', { speed }); }
	static status() { return api.get<ReplayStatus>('/replay/status'); }
	static regimes() { return api.get<RegimeCatalogue>('/replay/regimes'); }
	static health() { return api.get<{ status: string; archive: string }>(`/health${qs({})}`); }
}
