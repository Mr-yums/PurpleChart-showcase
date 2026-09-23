"""
PurpleReplay v2 — Market Service
— instruments rejouables, bougies (agrégées depuis le tape avec cache des buckets clos),
marques orderflow historiques, séances disponibles (vue matérialisée incrémentale), trades réels.
Garde anti-spoiler : tout est plafonné au curseur du replay pour le symbole rejoué.
Les données viennent exclusivement des archives locales. Zéro SQL ici.
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field

from app.core.config import ReplayConfig
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.domain.instruments import instrument_for
from app.domain.replay.timeframes import TIMEFRAMES, bucket_start, tf_seconds
from app.domain.sessions import session_label, session_start
from app.repositories.archive_repository import ArchiveRepository
from app.repositories.jsonl_repository import JsonFileRepository
from app.services.ports import SessionCatalogue
from app.services.replay_engine import ReplayEngine

log = get_logger("market")
MAX_CANDLES = 1000
MAX_EVENTS = 5000


@dataclass
class _CandleCache:
    """Buckets clos d'un couple (symbol, step). Le bucket contenant le curseur n'est jamais mis en cache."""

    first: int | None = None
    until: int | None = None  # borne exclusive : tous les buckets [first, until) sont cachés
    candles: dict[int, dict] = field(default_factory=dict)

    def reset(self) -> None:
        self.first = self.until = None
        self.candles.clear()


class MarketService:
    def __init__(
        self,
        archive: ArchiveRepository,
        cfg: ReplayConfig,
        engine: ReplayEngine,
        sessions_cache: JsonFileRepository,
        *,
        catalogue: SessionCatalogue | None = None,
    ) -> None:
        self._archive = archive
        self._cfg = cfg
        self._engine = engine
        self._sessions_cache = sessions_cache
        self._symbols: tuple[float, list[str]] = (0.0, [])
        self._sessions: tuple[float, list[dict] | None] = (0.0, None)
        self._sessions_lock = threading.Lock()
        self._candles: dict[tuple[str, int], _CandleCache] = {}
        self.importer = catalogue

    def invalidate_archive_cache(self) -> None:
        """À appeler après avoir arrêté le lecteur et sélectionné une autre archive."""
        self._candles.clear()
        self._symbols = (0.0, [])

    # ---------------- instruments
    def _symbols_blocking(self) -> list[str]:
        ts, syms = self._symbols
        if syms and time.time() - ts < self._cfg.symbols_ttl:
            return syms
        legacy = getattr(self._archive, "legacy", self._archive)
        known = self._sessions_cache.read({}).get("symbols", {})
        syms = legacy.symbols(self._cfg.min_symbol_rows, list(known) if known else None)
        if self.importer:
            syms = list(set(syms) | self.importer.cached_symbols | set(self._archive.modern.symbols(1)))
        syms.sort(key=lambda s: (s != "US100.cash", s != "NQ", s))
        self._symbols = (time.time(), syms)
        return syms

    async def symbols(self) -> list[str]:
        return await asyncio.to_thread(self._symbols_blocking)

    async def instruments(self) -> dict:
        if self.importer:
            await self.importer.sessions()
            self._symbols = (0.0, [])
        syms = await self.symbols()
        items = []
        for s in syms:
            inst = instrument_for(s)
            items.append(
                {
                    "symbol": s,
                    "label": inst.label,
                    "tick": inst.tick,
                    "digits": inst.digits,
                    "point_value": inst.point_value,
                    "fee_round_trip": inst.fee_round_trip,
                }
            )
        return {"instruments": items, "timeframes": TIMEFRAMES}

    async def require_symbol(self, symbol: str) -> None:
        if symbol not in await self.symbols():
            raise ValidationError(f"symbole absent de l'archive: {symbol}")

    # ---------------- bougies
    def current_candle(self, symbol: str, tf_s: int, cursor: float) -> dict | None:
        """Bougie en cours au curseur (BLOQUANT — appelé par le moteur via to_thread)."""
        bucket = bucket_start(cursor, tf_s)
        rows = self._archive.candle_buckets(symbol, tf_s, bucket, cursor)
        if not rows:
            return None
        b, lo, hi, vol, tmin, tmax = rows[0]
        oc = self._archive.open_close(symbol, tmin, tmax)
        if not oc:
            return None
        return {
            "time": int(b),
            "open": oc[0],
            "high": float(hi),
            "low": float(lo),
            "close": oc[1],
            "volume": float(vol or 0),
        }

    def _candles_blocking(self, symbol: str, tf: str, n: int) -> list[dict]:
        step = tf_seconds(tf)
        view = self._engine.view()
        if view.loaded and not view.live and view.symbol == symbol:
            end = view.cursor_ts
        else:
            end = self._archive.max_time(symbol) or time.time()
        start = bucket_start(max(end - n * step, end - 7 * 86400), step)
        last_closed = bucket_start(end, step)  # bucket contenant `end` = partiel, jamais caché
        cache = self._candles.setdefault((symbol, step), _CandleCache())
        if cache.first is None or start < cache.first or cache.until > last_closed:
            cache.reset()
            query_from = start
        else:
            query_from = cache.until
        if query_from <= end:
            for b, lo, hi, vol, tmin, tmax in self._archive.candle_buckets(symbol, step, query_from, end):
                oc = self._archive.open_close(symbol, tmin, tmax)
                if not oc:
                    continue
                candle = {
                    "time": int(b),
                    "open": oc[0],
                    "high": float(hi),
                    "low": float(lo),
                    "close": oc[1],
                    "volume": float(vol or 0),
                }
                if b < last_closed:
                    cache.candles[int(b)] = candle
                else:
                    cache.candles.pop(int(b), None)
                    partial = candle
                    break
            else:
                partial = None
            if cache.first is None:
                cache.first = start
            cache.until = last_closed
        else:
            partial = None
        out = [c for t, c in sorted(cache.candles.items()) if t >= start]
        if partial:
            out.append(partial)
        return out[-n:]

    async def candles(self, symbol: str, tf: str, n: int) -> list[dict]:
        n = max(10, min(MAX_CANDLES, int(n)))
        tf_seconds(tf)
        return await asyncio.to_thread(self._candles_blocking, symbol, tf, n)

    # ---------------- marques historiques
    async def events(self, symbol: str, t_from: float, t_to: float, limit: int) -> dict:
        limit = max(1, min(MAX_EVENTS, int(limit)))
        if not t_to:
            t_to = time.time()
        t_to = self._engine.cap(symbol, t_to)
        rows = await asyncio.to_thread(self._archive.events_history, symbol, t_from, t_to, limit)
        return {
            "big_prints": rows,
            "total": len(rows),
            "returned": len(rows),
            "truncated": len(rows) >= limit,
        }

    async def marks_for_snapshot(
        self, symbol: str, t_from: float, t_to: float, limit: int = 400
    ) -> list[dict]:
        return await asyncio.to_thread(self._archive.events_history, symbol, t_from, t_to, limit)

    # ---------------- trades réels (anti-spoiler)

    # ---------------- séances (vue matérialisée persistée, delta uniquement)
    def _build_sessions_blocking(self) -> list[dict]:
        state = self._sessions_cache.read({"symbols": {}})
        if not isinstance(state, dict) or not isinstance(state.get("symbols"), dict):
            state = {"symbols": {}}
        per_symbol: dict = state["symbols"]
        legacy = getattr(self._archive, "legacy", self._archive)
        for sym in legacy.symbols(self._cfg.min_symbol_rows, list(per_symbol) if per_symbol else None):
            ss = per_symbol.setdefault(sym, {"max_ts": 0.0, "buckets": {}})
            last = float(ss.get("max_ts") or 0.0)
            newmax = last
            for b, mn, mx in legacy.session_buckets(sym, last):
                if mn is None:
                    continue
                key = str(int(b))
                cur = ss["buckets"].get(key)
                ss["buckets"][key] = [min(cur[0], mn), max(cur[1], mx)] if cur else [mn, mx]
                if mx is not None and mx > newmax:
                    newmax = mx
            ss["max_ts"] = newmax
        self._sessions_cache.write(state)
        out = []
        for sym, ss in per_symbol.items():
            for key, (mn, mx) in ss["buckets"].items():
                sstart = session_start(int(key))
                out.append(
                    {
                        "symbol": sym,
                        "session_start": sstart,
                        "first_ts": mn,
                        "last_ts": mx,
                        "date": session_label(sstart),
                        "source": "legacy",
                    }
                )
        out.sort(
            key=lambda r: (r["symbol"] != "US100.cash", r["symbol"] != "NQ", r["symbol"], r["session_start"])
        )
        return out

    def _sessions_blocking(self) -> list[dict]:
        with self._sessions_lock:
            ts, data = self._sessions
            if data is not None and time.time() - ts < self._cfg.sessions_ttl:
                return data
            data = self._build_sessions_blocking()
            self._sessions = (time.time(), data)
            return data

    async def _legacy_sessions(self) -> list[dict]:
        ts, data = self._sessions
        if data is not None:
            if time.time() - ts >= self._cfg.sessions_ttl:
                asyncio.create_task(asyncio.to_thread(self._sessions_blocking))  # stale-while-revalidate
            return data
        return await asyncio.to_thread(self._sessions_blocking)

    async def sessions(self) -> list[dict]:
        legacy = await self._legacy_sessions()
        if not self.importer:
            return legacy
        modern = await self.importer.sessions()
        return sorted(legacy + modern, key=lambda s: (s["session_start"], s["symbol"], s["source"]))

    def prewarm(self) -> threading.Thread:
        """Pré-chauffe symboles + séances au démarrage (thread), pour que le 1er appel du front soit instantané."""

        def run() -> None:
            try:
                self._sessions_blocking()
            except Exception:  # noqa: BLE001
                log.exception("pré-chauffe des séances")

        t = threading.Thread(target=run, name="sessions-prewarm", daemon=True)
        t.start()
        return t
