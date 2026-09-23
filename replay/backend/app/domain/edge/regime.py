"""
PurpleReplay v2 — Régime de marché à l'entrée
— classification DIR_UP / DIR_DOWN / RANGE / BATARD sur les clôtures M5 précédant l'entrée
(efficiency ratio + déplacement net), identique au catalogue des séances (gen_regimes). Pur.
"""

from __future__ import annotations

from typing import Iterable, Sequence


def window_class(closes: Sequence[float], scale: float = 1.0) -> str:
    """Description publique par efficiency ratio : >= 0,6 direction ; <= 0,2 range.

    Ces seuils de lecture ne reprennent pas le classifieur privé et ne prédisent rien.
    """
    if len(closes) < 2:
        return "UNKNOWN"
    net = closes[-1] - closes[0]
    distance = sum(abs(b - a) for a, b in zip(closes, closes[1:]))
    ratio = abs(net) / distance if distance else 0.0
    if ratio >= 0.6:
        return "DIR_UP" if net > 0 else "DIR_DOWN"
    return "RANGE" if ratio <= 0.2 else "BATARD"


def closes_from_ticks(rows: Iterable[Sequence]) -> list[float]:
    """rows = (bucket, price) triés par t -> clôture de chaque bucket."""
    closes: list[float] = []
    cur_b = None
    cur_c = None
    for b, p in rows:
        if b != cur_b:
            if cur_b is not None:
                closes.append(cur_c)
            cur_b, cur_c = b, p
        else:
            cur_c = p
    if cur_b is not None:
        closes.append(cur_c)
    return closes


def regime_from_ticks(symbol: str, rows: Iterable[Sequence], min_bars: int = 4) -> str:
    closes = closes_from_ticks(rows)
    if len(closes) < min_bars:
        return "UNKNOWN"
    return window_class(closes)
