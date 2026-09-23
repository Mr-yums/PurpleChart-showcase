// Timeframes alignés sur l'epoch, identiques au backend (domain/replay/timeframes.py).
export const TIMEFRAMES = ['15s', '1m', '5m', '15m', '30m', '1h', '4h', '6h', '1D'] as const;
const UNITS: Record<string, number> = { s: 1, m: 60, h: 3600, D: 86400 };

export function tfSeconds(tf: string): number {
	const m = tf.match(/^(\d+)([smhD])$/);
	if (!m) throw new Error(`timeframe non supporté: ${tf}`);
	return Number(m[1]) * UNITS[m[2]];
}
export function bucketStart(t: number, step: number): number { return Math.floor(t / step) * step; }
