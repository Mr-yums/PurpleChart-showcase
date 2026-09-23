/**
 * PurpleReplay v2 — profil de volume
 * Agrégation volume-par-prix (achat/vente), POC, Value Area 70 % (extension depuis le POC, méthode
 * Market Profile / Valentini), tick estimé. Partagé par le VP de mesure, le VP Valentini et la
 * stratégie. Calcul pur.
 */
export interface Level { price: number; vol: number; buy: number; sell: number; }
export interface Cell { t: number; price: number; volume: number; side?: string; }
export interface ProfileStats { poc: number | null; vah: number | null; val: number | null; hi: number | null; lo: number | null; total: number; netDelta: number; }

export function keyOf(price: number): number { return Math.round(price * 100); }

export function addCell(map: Map<number, Level>, price: number, volume: number, side?: string): void {
	const k = keyOf(price);
	let e = map.get(k);
	if (!e) { e = { price, vol: 0, buy: 0, sell: 0 }; map.set(k, e); }
	e.vol += volume;
	if (side === 'buy') e.buy += volume; else if (side === 'sell') e.sell += volume;
}

export function profileStats(map: Map<number, Level>): ProfileStats {
	const arr = [...map.values()];
	let total = 0, buy = 0, sell = 0;
	for (const e of arr) { total += e.vol; buy += e.buy; sell += e.sell; }
	if (!arr.length) return { poc: null, vah: null, val: null, hi: null, lo: null, total, netDelta: buy - sell };
	arr.sort((a, b) => a.price - b.price);
	let poc = arr[0], pocIdx = 0;
	for (let i = 0; i < arr.length; i++) if (arr[i].vol > poc.vol) { poc = arr[i]; pocIdx = i; }
	const target = total * 0.7;
	let lo = pocIdx, hi = pocIdx, acc = arr[pocIdx].vol;
	while (acc < target && (lo > 0 || hi < arr.length - 1)) {
		const vd = lo > 0 ? arr[lo - 1].vol : -1;
		const vu = hi < arr.length - 1 ? arr[hi + 1].vol : -1;
		if (vu >= vd) { hi++; acc += arr[hi].vol; } else { lo--; acc += arr[lo].vol; }
	}
	return { poc: poc.price, vah: arr[hi].price, val: arr[lo].price, hi: arr[arr.length - 1].price, lo: arr[0].price, total, netDelta: buy - sell };
}

/** Tick réel = plus petit écart entre niveaux (fallback 0.25). */
export function estimateTick(prices: Iterable<number>, fallback = 0.25): number {
	const a = [...new Set([...prices].map(keyOf))].sort((x, y) => x - y);
	let tick = Infinity;
	for (let i = 1; i < a.length; i++) { const d = (a[i] - a[i - 1]) / 100; if (d > 1e-9 && d < tick) tick = d; }
	return Number.isFinite(tick) && tick > 0 ? tick : fallback;
}

/** Regroupe les niveaux en bins de `binSize` (multiple du tick) pour garantir des barres lisibles à l'écran. */
export function binLevels(levels: Iterable<Level>, binSize: number): Level[] {
	const bins = new Map<number, Level>();
	for (const l of levels) {
		const k = Math.round(l.price / binSize);
		let b = bins.get(k);
		if (!b) { b = { price: k * binSize, vol: 0, buy: 0, sell: 0 }; bins.set(k, b); }
		b.vol += l.vol; b.buy += l.buy; b.sell += l.sell;
	}
	return [...bins.values()];
}

export function normalizeCell(c: Partial<Cell> & { timestamp?: string; recv_ts?: number }): Cell | null {
	if (!c) return null;
	let t = Number(c.t);
	if (!Number.isFinite(t) || t <= 0) {
		if (c.timestamp) { const p = Date.parse(c.timestamp); t = Number.isFinite(p) ? p / 1000 : NaN; }
		if ((!Number.isFinite(t) || t <= 0) && c.recv_ts != null) t = Number(c.recv_ts);
	}
	const price = Number(c.price), vol = Number(c.volume) || 0;
	if (!Number.isFinite(t) || t <= 0 || !Number.isFinite(price) || !vol) return null;
	return { t, price, volume: vol, side: c.side };
}
