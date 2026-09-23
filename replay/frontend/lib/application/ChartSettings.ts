/**
 * PurpleReplay v2 — réglages du graphique
 * Style, études, filtres des marques, fenêtre d'historique, overlays. Persistés dans le navigateur.
 */
import { writable } from 'svelte/store';
import type { MarkKind } from '$replay/domain/market/types';
import type { VwapMode } from '$replay/domain/indicators/studies';

export type Weight = 'normal' | 'fort' | 'extreme';
export interface ChartSettings {
	style: 'candles' | 'line';
	ema: boolean;
	vwap: VwapMode;
	bands: boolean;
	sides: ('buy' | 'sell')[];
	kinds: MarkKind[];
	weights: Weight[];
	historySec: number;
	gexLines: boolean;
	profile: boolean;
}

const KEY = 'pr2-chart-settings';
const DEFAULTS: ChartSettings = {
	style: 'candles', ema: true, vwap: 'globex', bands: true, sides: ['buy', 'sell'],
	kinds: [], weights: ['fort', 'extreme'],
	historySec: 21600, gexLines: true, profile: true
};

function load(): ChartSettings {
	try {
		const raw = typeof localStorage !== 'undefined' ? localStorage.getItem(KEY) : null;
		return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : { ...DEFAULTS };
	} catch { return { ...DEFAULTS }; }
}

function createStore() {
	const store = writable<ChartSettings>(load());
	return {
		subscribe: store.subscribe,
		update(patch: Partial<ChartSettings>) {
			store.update((s) => {
				const next = { ...s, ...patch };
				try { localStorage.setItem(KEY, JSON.stringify(next)); } catch { /* stockage indisponible */ }
				return next;
			});
		},
		toggle<K extends 'sides' | 'kinds' | 'weights'>(key: K, value: ChartSettings[K][number]) {
			store.update((s) => {
				const list = s[key] as string[];
				const next = list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
				const out = { ...s, [key]: next } as ChartSettings;
				try { localStorage.setItem(KEY, JSON.stringify(out)); } catch { /* stockage indisponible */ }
				return out;
			});
		}
	};
}
export const chartSettings = createStore();
