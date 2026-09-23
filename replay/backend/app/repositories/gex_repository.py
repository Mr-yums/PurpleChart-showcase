"""
PurpleReplay v2 — GEX Repository (gex_qqq.db, lecture seule)
— snapshots gamma QQQ (table `gex`) et vanna/charm (table `vanna`) écrits par le poller Cboe.
Les timestamps sont des ISO 'Z' : les bornes sont passées déjà converties par le service.
Base absente ou table manquante = listes vides, jamais d'exception vers le client.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.infra.sqlite import ThreadLocalConnection


class GexRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._db = ThreadLocalConnection(self.path, readonly=True)

    def _query(self, sql: str, params: tuple) -> list[tuple]:
        if not self.path.exists():
            return []
        try:
            return self._db.get().execute(sql, params).fetchall()
        except sqlite3.Error:
            return []

    def levels_between(self, iso_from: str, iso_to: str) -> list[tuple]:
        return self._query(
            "SELECT ts, spot, netGamma, callWall, putWall, inflection FROM gex"
            " WHERE ts>? AND ts<=? ORDER BY ts",
            (iso_from, iso_to),
        )

    def last_level_before(self, iso_to: str) -> tuple | None:
        rows = self._query(
            "SELECT ts, spot, netGamma, callWall, putWall, inflection FROM gex"
            " WHERE ts<=? ORDER BY ts DESC LIMIT 1",
            (iso_to,),
        )
        return rows[0] if rows else None

    def gex_context(self, iso_to: str) -> tuple | None:
        rows = self._query(
            "SELECT netGamma, callWall, putWall, inflection FROM gex WHERE ts<=? ORDER BY ts DESC LIMIT 1",
            (iso_to,),
        )
        return rows[0] if rows else None

    def last_vanna(self, symbol, iso_to):
        return None

    def vanna_context(self, iso_to):
        return None
