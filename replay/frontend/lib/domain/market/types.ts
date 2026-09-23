// Contrats de données partagés entre l'API, le WebSocket, le domaine et la présentation.
export type Side = 'buy' | 'sell' | 'unknown';
export type MarkKind = 'block' | 'sweep' | 'absorb' | 'exhaustion' | 'stacked_imbalance';

export interface Trade {
	symbol: string; t: number; timestamp: string; price: number; volume: number; side: Side; seq?: number;
	kind?: MarkKind; trigger_volume?: number; weight?: number; speed?: number; lots_per_sec?: number;
	dominance?: number; confidence?: number; score?: number; reason?: string;
}
export interface Mark {
	t: number; price: number; side: Side; kind: MarkKind; volume: number; trigger_volume?: number | null;
	weight?: number | null; speed?: number | null; lots_per_sec?: number | null; dominance?: number | null;
	confidence?: number | null; score?: number | null; reason?: string | null;
}
export interface DeltaBucket { t: number; buy_volume: number; sell_volume: number; delta: number; trades: number; high: number; low: number; }
export interface TapeStats { cvd: number; buys: number; sells: number; total: number; big_threshold: number; }
export interface DomLevel { price: number; vol: number; }
export interface DomBook {
	symbol: string; bids: DomLevel[]; asks: DomLevel[]; profile: [number, number][]; bid: number; ask: number;
	bid_size: number; ask_size: number; spread: number; mid: number; last: number; last_size: number;
	session_low: number | null; session_high: number | null; tick: number; digits: number; ts: number;
	features: { bid_vol: number; ask_vol: number; imbalance: number; spread: number; mid: number; levels: number };
}
export interface Candle { time: number; open: number; high: number; low: number; close: number; volume: number; }
export interface Instrument { symbol: string; label: string; tick: number; digits: number; point_value: number; fee_round_trip: number; }
export interface SessionInfo {
 source?: 'legacy' | 'v2'; // [Sol] Distinct archives, same training controls.
 symbol: string; session_start: number; first_ts: number; last_ts: number; date: string; }

export interface ReplayStatus {
	loaded: boolean; playing: boolean; ended: boolean; live: boolean; buffering: boolean; symbol: string | null;
	speed: number; cursor_ts: number; start_ts: number; context_start: number; seq: number; pending: number;
	clients: number; feed_connected: boolean;
}

export interface Position {
	symbol: string; side: 'LONG' | 'SHORT'; size: number; entry: number; sl: number | null; tp: number | null;
	sl_orig: number | null; point_value: number; pnl: number | null; opened_ts: number; entry_tag: string | null; regime: string | null;
}
export interface Account {
	id: number; name: string; balance: number; starting_balance: number; canTrade: boolean; fees_total: number;
	realized_net: number; realized_gross: number; simulated: boolean;
}
export interface TicketSpec {
	symbol: string; tick_size: number; tick_value: number; point_value: number; fee_round_trip: number;
	max_contracts: number; min_bracket_ticks: number; default_risk_usd: number; dry_run: boolean;
}


// ---- trames WebSocket
export interface TapeFrame { type: 'tape'; symbol: string; data: { seq: number; trades: Trade[]; delta_minutes: DeltaBucket[]; stats: TapeStats } }
export interface SnapshotFrame {
	type: 'snapshot'; symbol: string;
	data: { seq: number; cursor: number; trades: Trade[]; marks: Mark[]; delta_minutes: DeltaBucket[]; stats: TapeStats;
		dom: DomBook | null; positions: Position[]; account: Account; status: ReplayStatus };
}
export interface DomFrame { type: 'dom'; symbol: string; data: DomBook }
export interface CandleFrame { type: 'candle'; symbol: string; tf: string; data: Candle }
export interface PositionsFrame { type: 'positions'; symbol: string | null; data: { positions: Position[]; account: Account } }
export interface StatusFrame { type: 'status'; data: ReplayStatus }
export interface ErrorFrame { type: 'error'; data: { detail: string } }
export type Frame = TapeFrame | SnapshotFrame | DomFrame | CandleFrame | PositionsFrame | StatusFrame | ErrorFrame;

// ---- GEX / edge / journal
export interface GexLevel { time: number; spot: number; netGamma: number; cw_d: number | null; pw_d: number | null; fl_d: number | null; regime: 'RANGE' | 'EXPANSION'; }
export interface VannaSnapshot {
	ts: string; symbol: string; totalVanna: number; totalCharm: number; vannaFlip: number | null; vannaRegime: string | null;
	vannaFlipUnstable: boolean; bullDriftTarget: number | null; bearMaxDanger: number | null; bullBearRatio: number | null;
	stockPrice: number; vannaFlip_d: number | null; bullDrift_d: number | null; bearDanger_d: number | null;
}
export interface EdgeTrade {
	id: number; ts_wall: number; ts_market: number; mode: string; symbol: string; side: string; size: number; entry: number;
	exit: number; sl: number | null; tp: number | null; pnl: number; fees: number | null; pnl_net: number | null; reason: string;
	entry_tag: string | null; regime: string | null; risk_usd: number | null; result_r: number | null; ctx_setup: string | null;
	ctx_coherence: string | null; gex_regime: string | null; mfe_usd: number | null; mae_usd: number | null;
}
export interface EdgeGroup { entry_tag: string; regime: string; n: number; wins: number; winrate: number; avg_r: number | null; sum_r: number | null; profit_factor: number | null; sum_usd: number; }
export interface GexGroup { gex_regime: string; above_flip: string; side: string; n: number; winrate: number; avg_r: number | null; sum_r: number | null; profit_factor: number | null; sum_usd: number; }
export interface TradeStats {
	count: number; wins: number; losses: number; scratches: number; win_rate: number; total_pnl: number; gross_win: number; gross_loss: number;
	avg_win: number; avg_loss: number; profit_factor: number | null; profit_factor_inf: boolean; best_trade: number; worst_trade: number;
	symbols: string[]; contracts: number; total_fees: number; total_pnl_net: number;
}
export interface UnifiedTrade { source: 'replay'; ts: number; symbol: string | null; side: string | null; size: number | null; entry: number | null; exit: number | null; pnl: number; fees: number | null; reason: string | null; }
export interface JournalPayload { ok: boolean; since: number; generated_at: number; trades: UnifiedTrade[]; per_source: Record<'replay', TradeStats>; overall: TradeStats; }
export interface SessionRecord extends TradeStats { session_id: number; saved_at_wall: number; label: string; mode: string; first_trade_wall: number | null; last_trade_wall: number | null; }
export interface SessionsPayload {
	ok: boolean; sessions: SessionRecord[];
	aggregate: { sessions: number; winning_sessions: number; total_pnl: number; total_trades: number; wins: number; losses: number; win_rate: number; best_session_pnl: number | null };
	pending: { count: number; stats: TradeStats | null };
}
export interface VolumeProfile { low: number; high: number; poc: number; vah: number; val: number; bins: number[]; volume?: number; }
export interface RegimeSegment { classe: string; debut_s: number; fin_s: number; debut: string; fin: string; net: number; er: number; duree_min: number; vp?: VolumeProfile | null; }
export interface RegimeDay { vp?: VolumeProfile | null; source?: string; jour: string; n_m5: number; day_net: number; day_range: number; segments: RegimeSegment[]; }
export interface RegimeCatalogue { ok: boolean; symbols: Record<string, Record<string, RegimeDay>>; message?: string; }

export function isFrame(v: unknown): v is Frame {
	return !!v && typeof v === 'object' && typeof (v as Frame).type === 'string';
}
