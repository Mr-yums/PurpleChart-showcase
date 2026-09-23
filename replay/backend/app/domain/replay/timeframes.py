"""
PurpleReplay v2 — Timeframes
— clés identiques à PurpleChart v2 ('1m', '5m', '1h', '1D'...) pour partager le front et
proxifier l'API v2 en démo live. Les buckets sont alignés sur l'epoch (CAST(t/step)*step),
comme les requêtes SQLite de l'archive.
"""

from __future__ import annotations

from app.core.exceptions import ValidationError

_UNITS = {"s": 1, "m": 60, "h": 3600, "D": 86400}

TIMEFRAMES: list[str] = ["15s", "1m", "5m", "15m", "30m", "1h", "4h", "6h", "1D"]


def tf_seconds(tf: str) -> int:
    if not tf or tf[-1] not in _UNITS or not tf[:-1].isdigit():
        raise ValidationError(f"timeframe non supporté: {tf}")
    return int(tf[:-1]) * _UNITS[tf[-1]]


def bucket_start(t: float, step: int) -> int:
    return int(t // step) * step
