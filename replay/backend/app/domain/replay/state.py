"""
PurpleReplay v2 — État de séance
— tout ce que le replay accumule en rejouant les trades : profil volume-par-prix,
CVD/compteurs, delta par minute, seuil "gros lot" (EWMA), extrêmes de séance, bougies en cours,
anneau des derniers trades. Pure Python, sans I/O : la même classe sert l'archive et la démo live.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Iterable, Sequence

from app.domain.instruments import Instrument


def _delta_bucket(t: int, price: float) -> dict:
    return {"t": t, "buy_volume": 0, "sell_volume": 0, "delta": 0, "trades": 0, "high": price, "low": price}


class SessionState:
    EWMA_ALPHA = 1.0 / 400.0

    def __init__(
        self, symbol: str, instrument: Instrument, *, ring: int = 2500, max_delta: int = 600
    ) -> None:
        self.symbol = symbol
        self.instrument = instrument
        self.max_delta = max_delta
        self.profile: dict[float, list[int]] = {}  # price -> [buy_vol, sell_vol]
        self.stats = {"cvd": 0, "buys": 0, "sells": 0, "total": 0}
        self.delta: list[dict] = []  # buckets minute
        self.recent: deque = deque(maxlen=ring)  # derniers trades émis (seed WS)
        self.candles: dict[int, dict | None] = {}  # tf_sec -> bougie en cours
        self.last_price: float | None = None
        self.last_size = 0
        self.last_side = "buy"
        self.session_low: float | None = None
        self.session_high: float | None = None
        self.vol_mean = 10.0
        self.vol_var = 100.0
        self.seq = 0

    # ---------------- amorçage depuis l'archive (contexte < début de replay)
    def seed(
        self,
        profile_rows: Iterable[Sequence],
        stats_row: Sequence | None,
        delta_rows: Iterable[Sequence],
        volumes: Sequence[float],
        last_row: Sequence | None,
    ) -> None:
        for price, bv, sv in profile_rows:
            self.profile[float(price)] = [int(bv or 0), int(sv or 0)]
        if self.profile:
            self.session_low = min(self.profile)
            self.session_high = max(self.profile)
        if stats_row:
            buys, sells, total = int(stats_row[0] or 0), int(stats_row[1] or 0), int(stats_row[2] or 0)
            self.stats = {"cvd": buys - sells, "buys": buys, "sells": sells, "total": total}
        for b, bv, sv, n, hi, lo in delta_rows:
            self.delta.append(
                {
                    "t": int(b),
                    "buy_volume": int(bv or 0),
                    "sell_volume": int(sv or 0),
                    "delta": int(bv or 0) - int(sv or 0),
                    "trades": int(n),
                    "high": hi,
                    "low": lo,
                }
            )
        self.delta = self.delta[-self.max_delta :]
        if volumes:
            m = sum(volumes) / len(volumes)
            v = sum((x - m) ** 2 for x in volumes) / len(volumes)
            self.vol_mean, self.vol_var = float(m), float(v)
        if last_row:
            self.last_price = float(last_row[0])
            self.last_size = int(last_row[1] or 0)
            self.last_side = last_row[2] or "buy"

    # ---------------- application d'un trade
    def apply(self, tr: dict) -> None:
        p, v, side, t = tr["price"], tr["volume"], tr["side"], tr["t"]
        self.seq += 1
        tr["seq"] = self.seq
        self.last_price, self.last_size, self.last_side = p, v, side
        slot = self.profile.setdefault(p, [0, 0])
        if side == "buy":
            slot[0] += v
            self.stats["buys"] += v
            self.stats["cvd"] += v
        elif side == "sell":
            slot[1] += v
            self.stats["sells"] += v
            self.stats["cvd"] -= v
        self.stats["total"] += 1
        if self.session_low is None or p < self.session_low:
            self.session_low = p
        if self.session_high is None or p > self.session_high:
            self.session_high = p
        a = self.EWMA_ALPHA
        self.vol_mean += a * (v - self.vol_mean)
        self.vol_var += a * ((v - self.vol_mean) ** 2 - self.vol_var)
        b = int(t // 60) * 60
        if not self.delta or self.delta[-1]["t"] != b:
            self.delta.append(_delta_bucket(b, p))
            if len(self.delta) > self.max_delta:
                del self.delta[: len(self.delta) - self.max_delta]
        d = self.delta[-1]
        if side == "buy":
            d["buy_volume"] += v
        elif side == "sell":
            d["sell_volume"] += v
        d["delta"] = d["buy_volume"] - d["sell_volume"]
        d["trades"] += 1
        if p > d["high"]:
            d["high"] = p
        if p < d["low"]:
            d["low"] = p
        for tf_s, c in self.candles.items():
            bucket = int(t // tf_s) * tf_s
            if c is None or c["time"] != bucket:
                self.candles[tf_s] = {
                    "time": bucket,
                    "open": p,
                    "high": p,
                    "low": p,
                    "close": p,
                    "volume": float(v),
                }
            else:
                if p > c["high"]:
                    c["high"] = p
                if p < c["low"]:
                    c["low"] = p
                c["close"] = p
                c["volume"] += float(v)
        self.recent.append(tr)

    # ---------------- lectures
    def big_threshold(self) -> float:
        return max(15.0, self.vol_mean + 3.0 * math.sqrt(max(0.0, self.vol_var)))

    def stats_payload(self) -> dict:
        s = dict(self.stats)
        s["big_threshold"] = round(self.big_threshold(), 1)
        return s

    def has_candle(self, tf_s: int) -> bool:
        return tf_s in self.candles

    def set_candle(self, tf_s: int, candle: dict | None) -> None:
        self.candles[tf_s] = candle

    def candle(self, tf_s: int) -> dict | None:
        c = self.candles.get(tf_s)
        return dict(c) if c else None

    def dom_payload(self, cursor: float) -> dict | None:
        """Carnet synthétique : volume réellement traité par prix (aucun L2 en archive)."""
        last = self.last_price
        if last is None:
            return None
        inst = self.instrument
        tick, digits = inst.tick, inst.digits
        if self.last_side == "buy":
            ask, bid = last, last - tick
        else:
            bid, ask = last, last + tick
        prices = sorted(self.profile)
        bids = [
            {"price": p, "vol": self.profile[p][1]}
            for p in reversed(prices)
            if p <= bid and self.profile[p][1] > 0
        ][:30]
        asks = [
            {"price": p, "vol": self.profile[p][0]} for p in prices if p >= ask and self.profile[p][0] > 0
        ][:30]
        profile = [[p, self.profile[p][0] + self.profile[p][1]] for p in prices]
        bid_vol = sum(x["vol"] for x in bids)
        ask_vol = sum(x["vol"] for x in asks)
        tot = bid_vol + ask_vol
        spread = round(ask - bid, digits)
        return {
            "symbol": self.symbol,
            "source": "replay_archive",
            "kind": "volume_by_price",
            "bids": bids,
            "asks": asks,
            "profile": profile,
            "bid": bid,
            "ask": ask,
            "bid_size": self.last_size,
            "ask_size": self.last_size,
            "spread": spread,
            "mid": round((ask + bid) / 2.0, digits + 1),
            "last": last,
            "last_size": self.last_size,
            "session_low": self.session_low,
            "session_high": self.session_high,
            "tick": tick,
            "digits": digits,
            "ts": cursor,
            "features": {
                "bid_vol": bid_vol,
                "ask_vol": ask_vol,
                "imbalance": round((bid_vol - ask_vol) / tot, 4) if tot else 0.0,
                "spread": spread,
                "mid": (ask + bid) / 2.0,
                "levels": len(profile),
                "best_bid_size": self.last_size,
                "best_ask_size": self.last_size,
                "ts": cursor,
            },
        }
