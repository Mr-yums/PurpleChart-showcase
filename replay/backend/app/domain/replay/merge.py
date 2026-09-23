"""
PurpleReplay v2 — Fusion trades / évènements orderflow
— les marques (block/sweep/absorb/exhaustion/stacked) ne sont JAMAIS recalculées :
elles sont celles stockées par le live (table tape_events), rattachées au trade par trade_id.
Un trade ne porte qu'une marque : la plus prioritaire.
"""

from __future__ import annotations

from typing import Iterable, Sequence

KIND_PRIORITY = {"exhaustion": 5, "stacked_imbalance": 4, "sweep": 3, "block": 2, "absorb": 1}
EVENT_FIELDS = (
    "trigger_volume",
    "weight",
    "speed",
    "lots_per_sec",
    "dominance",
    "confidence",
    "score",
    "reason",
)


def index_events(events: Iterable[Sequence]) -> dict[str, tuple[str, tuple]]:
    """rows = (trade_id, kind, *EVENT_FIELDS) -> {trade_id: (kind, fields)} en gardant la priorité max."""
    kinds: dict[str, tuple[str, tuple]] = {}
    for row in events:
        tid, kind = row[0], row[1]
        if not tid:
            continue
        cur = kinds.get(tid)
        if cur is None or KIND_PRIORITY.get(kind, 0) > KIND_PRIORITY.get(cur[0], 0):
            kinds[tid] = (kind, tuple(row[2:]))
    return kinds


def build_trade(symbol: str, row: Sequence, kinds: dict[str, tuple[str, tuple]]) -> dict:
    """row = (t, id, timestamp_iso, price, volume, side) -> trade dict émis tel quel sur le WS."""
    t, tid, ts_iso, price, vol, side = row[:6]
    trade = {
        "symbol": symbol,
        "price": float(price),
        "volume": int(vol or 0),
        "timestamp": ts_iso,
        "t": float(t),
        "side": side or "unknown",
    }
    ev = kinds.get(tid)
    if ev:
        trade["kind"] = ev[0]
        for name, val in zip(EVENT_FIELDS, ev[1]):
            if val is not None:
                trade[name] = val
    return trade


def attach_events(symbol: str, rows: Sequence[Sequence], events: Iterable[Sequence]) -> list[dict]:
    kinds = index_events(events)
    return [build_trade(symbol, r, kinds) for r in rows]
