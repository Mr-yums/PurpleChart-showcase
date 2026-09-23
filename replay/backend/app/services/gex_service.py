"""Niveaux gamma historiques PW/CW/FL, projetés sans anticipation."""

from __future__ import annotations

import asyncio
import time

from app.core.time import from_iso, to_iso_z
from app.services.ports import GammaHistory, PriceHistory, ReplayCursor


class GexService:
    def __init__(self, repo: GammaHistory, engine: ReplayCursor, archive: PriceHistory | None = None) -> None:
        self._repo = repo
        self._engine = engine
        self._archive = archive

    def _levels_blocking(self, symbol: str, t_from: float, t_to: float) -> tuple[list[dict], bool]:
        rows = self._repo.levels_between(to_iso_z(t_from), to_iso_z(t_to))
        stale = False
        if not rows:
            last = self._repo.last_level_before(to_iso_z(t_to))
            rows = [last] if last else []
            stale = bool(rows)
        out = []
        for ts, spot, ng, cw, pw, fl in rows:
            if not spot:
                continue
            raw_spot = spot
            if self._archive is not None:
                anchor = self._archive.last_trade_before(symbol, from_iso(ts))
                if not anchor:
                    continue
                future = float(anchor[0])
                if getattr(self._repo, "is_modern", False):
                    cw = future + cw - spot if cw else None
                    pw = future + pw - spot if pw else None
                    fl = future + fl - spot if fl else None
                else:
                    cw = future * cw / spot if cw else None
                    pw = future * pw / spot if pw else None
                    fl = future * fl / spot if fl else None
                spot = future
            out.append(
                {
                    "time": int(from_iso(ts)),
                    "spot": spot,
                    "underlying_spot": raw_spot,
                    "projection": "NDX basis"
                    if getattr(self._repo, "is_modern", False)
                    else "ratio sous-jacent",
                    "netGamma": ng,
                    "cw_d": (cw - spot) / spot if cw else None,
                    "pw_d": (pw - spot) / spot if pw else None,
                    "fl_d": (fl - spot) / spot if fl else None,
                    "regime": "RANGE" if (ng or 0) > 0 else "EXPANSION",
                }
            )
        return out, stale

    def context_at(self, symbol: str, cursor: float) -> tuple | None:
        """Contexte gamma projeté pour le journal ; appel bloquant hors boucle asyncio."""
        levels, _ = self._levels_blocking(symbol, cursor - 86400, cursor)
        if not levels:
            return None
        level = levels[-1]
        spot = level["spot"]
        return (
            level["netGamma"],
            *(spot * (1 + level[k]) if level[k] is not None else None for k in ("cw_d", "pw_d", "fl_d")),
        )

    async def levels(self, symbol: str, t_from: float, t_to: float) -> dict:
        t_to = self._engine.cap(symbol, t_to or time.time())
        if symbol not in ("NQ", "MNQ"):
            return {"symbol": symbol, "count": 0, "levels": [], "stale": False}
        levels, stale = await asyncio.to_thread(self._levels_blocking, symbol, t_from, t_to)
        return {"symbol": symbol, "count": len(levels), "levels": levels, "stale": stale}

    async def vanna(self, symbol: str, t_to: float):
        return None
