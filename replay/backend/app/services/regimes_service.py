"""
PurpleReplay v2 — Catalogue des régimes de séance
— lit `regimes.json` (produit par scripts/gen_regimes.py) : phases DIRECTIONNEL / RANGE /
RANGE PIÉGEUX par jour et par symbole, avec mini profil de volume. Relu si le fichier change.
"""

from __future__ import annotations

import asyncio
import copy
import datetime as dt
from collections import defaultdict

from app.domain.replay.regimes import DAYS, NET_SCALE, RegimeClassifier
from app.domain.replay.volume_profile import volume_profile
from app.repositories.jsonl_repository import JsonFileRepository


class RegimesService:
    def __init__(self, repo: JsonFileRepository, *, modern=None) -> None:
        self._repo = repo
        self.modern = modern
        self._modern_cache = None

    async def catalogue(self) -> dict:
        data = await asyncio.to_thread(self._repo.read, None)
        if not isinstance(data, dict) or not isinstance(data.get("symbols"), dict):
            data = {"symbols": {}, "genere": "PurpleChart V2 / OXIO"}
        data = copy.deepcopy(data)
        if self.modern is not None:
            size = self.modern.path.stat().st_mtime_ns
            if not self._modern_cache or self._modern_cache[0] != size:
                self._modern_cache = (size, await asyncio.to_thread(self._build_modern))
            for symbol, days in self._modern_cache[1].items():
                data["symbols"].setdefault(symbol, {}).update(days)
        if not any(data["symbols"].values()):
            return {"ok": False, "symbols": {}, "message": "Aucune séance classifiée disponible."}
        return {"ok": True, "generated": data.get("genere"), "symbols": data["symbols"]}

    def _build_modern(self):
        result = {}
        for symbol in self.modern.symbols(1):
            days = {}
            for (start,) in self.modern.calendar_days(symbol):
                raw = self.modern.bucket_ticks(symbol, 300, start, start + 86400)
                candles = []
                day_prices = defaultdict(float)
                block_prices = defaultdict(lambda: defaultdict(float))
                for t, p, volume in raw:
                    day_prices[p] += volume
                    block_prices[int(t // 3600)][p] += volume
                    if not candles or candles[-1][0] != t:
                        candles.append([t, p, p, p, p])
                    else:
                        c = candles[-1]
                        c[2] = max(c[2], p)
                        c[3] = min(c[3], p)
                        c[4] = p
                if len(candles) < 24:
                    continue
                date = dt.datetime.fromtimestamp(start, dt.timezone.utc)
                segs = RegimeClassifier.classify(candles, NET_SCALE.get(symbol, 1.0))
                for segment in segs:
                    segment["vp"] = volume_profile(block_prices[int(segment["debut_s"] // 3600)])
                days[date.strftime("%Y-%m-%d")] = {
                    "jour": DAYS[date.weekday()],
                    "n_m5": len(candles),
                    "day_net": round(candles[-1][4] - candles[0][4], 1),
                    "day_range": round(max(c[2] for c in candles) - min(c[3] for c in candles), 1),
                    "segments": segs,
                    "vp": volume_profile(day_prices),
                    "source": "v2",
                }
            result[symbol] = days
        return result
