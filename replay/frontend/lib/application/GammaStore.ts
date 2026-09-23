import {get, writable, type Readable} from 'svelte/store';
import type {GexLevel, ReplayStatus} from '$replay/domain/market/types';
import {GexApi} from '$replay/api/gex';
import {market} from './MarketStore';

type GammaResult = {levels: GexLevel[]; stale: boolean};
type FetchLevels = (symbol: string, from: number, to: number) => Promise<GammaResult>;
export interface GammaState {
 symbol: string | null;
 phase: 'idle' | 'loading' | 'ready' | 'empty' | 'unsupported' | 'error';
 level: GexLevel | null;
 stale: boolean;
}

/** Une source commune pour la carte et les lignes, indexée sur la séance réellement chargée. */
export class GammaStore {
 private store = writable<GammaState>({symbol: null, phase: 'idle', level: null, stale: false});
 subscribe = this.store.subscribe;
 private off: (() => void) | null = null;
 private timer: ReturnType<typeof setInterval> | null = null;
 private generation = 0;
 private key = '';
 private lastCursor = 0;
 private lastAttempt = 0;
 private pending = false;
 constructor(private status: Readable<ReplayStatus>, private fetchLevels: FetchLevels, private now = Date.now) {}

 start() {
  this.stop();
  this.off = this.status.subscribe(() => this.refresh());
  this.timer = setInterval(() => this.refresh(), 4000);
 }
 stop() {
  this.off?.(); this.off = null;
  if (this.timer) clearInterval(this.timer);
  this.timer = null; this.generation++; this.pending = false; this.key = '';
 }
 refresh(force = false) {
  const st = get(this.status);
  const key = st.loaded ? `${st.symbol}:${st.context_start}:${st.start_ts}` : '';
  const changed = key !== this.key || st.cursor_ts < this.lastCursor;
  if (changed || !st.loaded) {
   this.generation++; this.pending = false; this.key = key;
   this.store.set({symbol: st.symbol, phase: 'idle', level: null, stale: false});
  }
  if (!st.loaded || !st.symbol) return;
  if (!['NQ', 'MNQ'].includes(st.symbol)) {
   this.store.set({symbol: st.symbol, phase: 'unsupported', level: null, stale: false});
   return;
  }
  const age = this.now() - this.lastAttempt;
  const state = get(this.store);
  if (this.pending && !changed && !force) return;
  if (!force && !changed && state.phase !== 'idle' && age < 60000 &&
      !(state.phase === 'error' && age >= 4000) && !(Math.abs(st.cursor_ts - this.lastCursor) >= 300 && age >= 2000)) return;
  const generation = ++this.generation;
  this.pending = true; this.lastAttempt = this.now(); this.lastCursor = st.cursor_ts;
  this.store.set({symbol: st.symbol, phase: 'loading', level: state.level, stale: state.stale});
  void this.fetchLevels(st.symbol, st.cursor_ts - 86400, st.cursor_ts).then(result => {
   if (generation !== this.generation) return;
   const level = result.levels.filter(level => level.time <= st.cursor_ts).at(-1) ?? null;
   this.store.set({symbol: st.symbol, phase: level ? 'ready' : 'empty', level, stale: result.stale});
  }).catch(() => {
   if (generation === this.generation) this.store.set({symbol: st.symbol, phase: 'error', level: null, stale: false});
  }).finally(() => {if (generation === this.generation) this.pending = false;});
 }
}

export const gamma = new GammaStore(market.status, (symbol, from, to) => GexApi.levels(symbol, from, to));
