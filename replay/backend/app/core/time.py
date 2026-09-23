"""
PurpleReplay v2 — Utilitaires temps
— tout le domaine parle en epoch UTC (secondes, float). Les ISO sont tz-aware.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def wall() -> float:
    """Horloge murale (epoch s). Isolée pour être remplaçable dans les tests."""
    return time.time()


def to_iso_z(epoch: float) -> str:
    """Epoch -> ISO 'YYYY-MM-DDTHH:MM:SS.000Z' (format des snapshots GEX)."""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def from_iso(value: str) -> float:
    """ISO (avec ou sans fraction, 'Z' ou offset, ou naïf = UTC) -> epoch s."""
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def utc_date(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")
