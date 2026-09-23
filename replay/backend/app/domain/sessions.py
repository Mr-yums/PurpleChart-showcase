"""
PurpleReplay v2 — Séances de trading
— une "session" replay = journée CME ancrée à l'ouverture Globex (~22:00 UTC).
Le label de date est celui de la clôture (jour suivant), comme dans la V1.
"""

from __future__ import annotations

import math

from app.core.time import utc_date

ANCHOR_OFFSET = 22 * 3600
DAY = 86400


def anchor_session(ts: float) -> float:
    """Début de journée de trading CME la plus récente <= ts."""
    return math.floor((ts - ANCHOR_OFFSET) / DAY) * DAY + ANCHOR_OFFSET


def session_bucket(ts: float) -> int:
    return int((ts - ANCHOR_OFFSET) // DAY)


def session_start(bucket: int) -> float:
    return bucket * DAY + ANCHOR_OFFSET


def session_label(sstart: float) -> str:
    """Date affichée = jour de clôture (sstart + 24 h), en UTC."""
    return utc_date(sstart + DAY)
