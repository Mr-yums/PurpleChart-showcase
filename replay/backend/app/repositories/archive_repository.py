"""
PurpleReplay v2 — Archive Repository (replay_archive.sqlite, lecture seule)
— toutes les requêtes SQL sur l'archive. Zéro logique métier : les lignes brutes sont
rendues aux services/domaine. Toutes les méthodes sont BLOQUANTES et doivent être appelées
hors de la boucle asyncio (thread lecteur ou `asyncio.to_thread`).
Index exploités : idx_tape_trades_symbol_t (symbol, t), idx_tape_events_symbol_t.
"""

from __future__ import annotations

from pathlib import Path

from app.domain.replay.merge import EVENT_FIELDS
from app.domain.sessions import ANCHOR_OFFSET, DAY
from app.infra.sqlite import ThreadLocalConnection

_EVENT_COLS = ", ".join(EVENT_FIELDS)


class ArchiveRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._db = ThreadLocalConnection(self.path, readonly=True)

    @property
    def conn(self):
        return self._db.get()

    def close(self) -> None:
        self._db.close()

    # ---------------- symboles / bornes
    def symbols(self, min_rows: int, candidates: list[str] | None = None) -> list[str]:
        """DISTINCT = skip-scan de l'index (~ms) ; le seuil de lignes passe par LIMIT/OFFSET sur l'index,
        jamais par COUNT(*) (23 s à chaud / 144 s à froid sur 56 M lignes)."""
        # [Sol] The persisted legacy session catalogue avoids scanning 56 million index entries on each launch.
        if candidates is not None:
            cands = candidates
        elif self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='replay_symbols'"
        ).fetchone():
            cands = [r[0] for r in self.conn.execute("SELECT symbol FROM replay_symbols ORDER BY symbol")]
        elif self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='imports'"
        ).fetchone():
            cands = [r[0] for r in self.conn.execute("SELECT DISTINCT symbol FROM imports WHERE complete=1")]
        else:
            cands = [r[0] for r in self.conn.execute("SELECT DISTINCT symbol FROM tape_trades")]
        return [
            s
            for s in cands
            if self.conn.execute(
                "SELECT 1 FROM tape_trades WHERE symbol=? LIMIT 1 OFFSET ?", (s, max(0, min_rows - 1))
            ).fetchone()
        ]

    def time_range(self, symbol: str) -> tuple[float, float] | None:
        lo = self.conn.execute(
            "SELECT t FROM tape_trades WHERE symbol=? ORDER BY t ASC LIMIT 1", (symbol,)
        ).fetchone()
        hi = self.conn.execute(
            "SELECT t FROM tape_trades WHERE symbol=? ORDER BY t DESC LIMIT 1", (symbol,)
        ).fetchone()
        if not lo or not hi:
            return None
        return float(lo[0]), float(hi[0])

    def max_time(self, symbol: str) -> float | None:
        row = self.conn.execute(
            "SELECT t FROM tape_trades WHERE symbol=? ORDER BY t DESC LIMIT 1", (symbol,)
        ).fetchone()
        return float(row[0]) if row else None

    # ---------------- flux de trades
    def trades_after(self, symbol: str, after_t: float, limit: int) -> list[tuple]:
        """Lot ordonné par t strictement > after_t ; complété par TOUS les trades du dernier t
        (sinon un t partagé par plusieurs prints serait tronqué entre deux lots)."""
        rows = self.conn.execute(
            "SELECT t, id, timestamp, price, volume, side FROM tape_trades"
            " WHERE symbol=? AND t>? ORDER BY t LIMIT ?",
            (symbol, after_t, limit),
        ).fetchall()
        if len(rows) == limit:
            last_t = rows[-1][0]
            seen = {r[1] for r in rows if r[0] == last_t}
            extra = self.conn.execute(
                "SELECT t, id, timestamp, price, volume, side FROM tape_trades WHERE symbol=? AND t=?",
                (symbol, last_t),
            ).fetchall()
            rows.extend(r for r in extra if r[1] not in seen)
        return rows

    def events_between(self, symbol: str, t0: float, t1: float) -> list[tuple]:
        return self.conn.execute(
            f"SELECT trade_id, kind, {_EVENT_COLS} FROM tape_events WHERE symbol=? AND t>=? AND t<=?",
            (symbol, t0, t1),
        ).fetchall()

    def events_history(self, symbol: str, t0: float, t1: float, limit: int) -> list[dict]:
        """Marques historiques (les `limit` plus récentes de la fenêtre), rendues du plus ancien au plus récent."""
        rows = self.conn.execute(
            f"SELECT t, price, side, kind, volume, {_EVENT_COLS} FROM tape_events"
            " WHERE symbol=? AND t>=? AND t<=? ORDER BY t DESC LIMIT ?",
            (symbol, t0, t1, limit),
        ).fetchall()
        out = []
        for r in reversed(rows):
            item = {
                "t": r[0],
                "price": r[1],
                "side": r[2],
                "kind": r[3],
                "volume": r[5] if r[5] is not None else r[4],
            }
            for name, val in zip(EVENT_FIELDS, r[5:]):
                item[name] = val
            out.append(item)
        return out

    # ---------------- contexte de séance (amorçage) — bornes INCLUSIVES [t0, t1] : le flux reprend en t > t1
    def profile(self, symbol: str, t0: float, t1: float) -> list[tuple]:
        return self.conn.execute(
            "SELECT price, SUM(CASE WHEN side='buy' THEN volume ELSE 0 END),"
            " SUM(CASE WHEN side='sell' THEN volume ELSE 0 END)"
            " FROM tape_trades WHERE symbol=? AND t>=? AND t<=? GROUP BY price",
            (symbol, t0, t1),
        ).fetchall()

    def stats(self, symbol: str, t0: float, t1: float) -> tuple | None:
        return self.conn.execute(
            "SELECT SUM(CASE WHEN side='buy' THEN volume ELSE 0 END),"
            " SUM(CASE WHEN side='sell' THEN volume ELSE 0 END), COUNT(*)"
            " FROM tape_trades WHERE symbol=? AND t>=? AND t<=?",
            (symbol, t0, t1),
        ).fetchone()

    def delta_minutes(self, symbol: str, t0: float, t1: float) -> list[tuple]:
        return self.conn.execute(
            "SELECT CAST(t/60 AS INT)*60, SUM(CASE WHEN side='buy' THEN volume ELSE 0 END),"
            " SUM(CASE WHEN side='sell' THEN volume ELSE 0 END), COUNT(*), MAX(price), MIN(price)"
            " FROM tape_trades WHERE symbol=? AND t>=? AND t<=? GROUP BY 1 ORDER BY 1",
            (symbol, t0, t1),
        ).fetchall()

    def recent_volumes(self, symbol: str, before_t: float, n: int = 400) -> list[float]:
        return [
            r[0]
            for r in self.conn.execute(
                "SELECT volume FROM tape_trades WHERE symbol=? AND t<=? ORDER BY t DESC LIMIT ?",
                (symbol, before_t, n),
            )
        ]

    def last_trade_before(self, symbol: str, t: float) -> tuple | None:
        return self.conn.execute(
            "SELECT price, volume, side FROM tape_trades WHERE symbol=? AND t<=? ORDER BY t DESC LIMIT 1",
            (symbol, t),
        ).fetchone()

    # ---------------- bougies (agrégation à la volée depuis le tape)
    def candle_buckets(self, symbol: str, step: int, t0: float, t1: float) -> list[tuple]:
        """(bucket, low, high, volume, t_min, t_max) par bucket dans [t0, t1]."""
        return self.conn.execute(
            "SELECT CAST(t/? AS INT)*? AS b, MIN(price), MAX(price), SUM(volume), MIN(t), MAX(t)"
            " FROM tape_trades WHERE symbol=? AND t>=? AND t<=? GROUP BY b ORDER BY b",
            (step, step, symbol, t0, t1),
        ).fetchall()

    def open_close(self, symbol: str, t_min: float, t_max: float) -> tuple[float, float] | None:
        o = self.conn.execute(
            "SELECT price FROM tape_trades WHERE symbol=? AND t>=? ORDER BY t LIMIT 1", (symbol, t_min)
        ).fetchone()
        c = self.conn.execute(
            "SELECT price FROM tape_trades WHERE symbol=? AND t<=? AND t>=? ORDER BY t DESC LIMIT 1",
            (symbol, t_max, t_min),
        ).fetchone()
        if not o or not c:
            return None
        return float(o[0]), float(c[0])

    def bucket_ticks(self, symbol: str, step: int, t0: float, t1: float) -> list[tuple]:
        """(bucket, price, volume) ordonnés par t — sert au régime (clôtures) et au contexte d'entrée."""
        return self.conn.execute(
            "SELECT CAST(t/? AS INT)*? AS b, price, volume FROM tape_trades"
            " WHERE symbol=? AND t>=? AND t<? ORDER BY t",
            (step, step, symbol, t0, t1),
        ).fetchall()

    # ---------------- séances (vue matérialisée incrémentale)
    def session_buckets(self, symbol: str, since_t: float) -> list[tuple]:
        """(bucket_session, min_t, max_t) pour t > since_t — balayage borné par l'index (symbol, t)."""
        return self.conn.execute(
            "SELECT CAST((t-?)/? AS INT) AS b, MIN(t), MAX(t) FROM tape_trades"
            " WHERE symbol=? AND t>? GROUP BY b",
            (ANCHOR_OFFSET, DAY, symbol, since_t),
        ).fetchall()

    # [Sol] Calendar ranges for the retrospective session catalogue.
    def calendar_days(self, symbol):
        return self.conn.execute(
            "SELECT CAST(t/86400 AS INT)*86400 FROM tape_trades WHERE symbol=? GROUP BY 1 ORDER BY 1",
            (symbol,),
        ).fetchall()

    def session_ranges(self, symbol: str) -> list[tuple]:
        """[Sol] Two index seeks per populated session, independent of transaction count."""
        rows = []
        after = 0.0
        while True:
            first = self.conn.execute(
                "SELECT t FROM tape_trades WHERE symbol=? AND t>=? ORDER BY t LIMIT 1", (symbol, after)
            ).fetchone()
            if not first:
                break
            lo = float(first[0])
            bucket = int((lo - ANCHOR_OFFSET) // DAY)
            after = (bucket + 1) * DAY + ANCHOR_OFFSET
            last = self.conn.execute(
                "SELECT t FROM tape_trades WHERE symbol=? AND t>=? AND t<? ORDER BY t DESC LIMIT 1",
                (symbol, lo, after),
            ).fetchone()
            rows.append((bucket, lo, float(last[0])))
        return rows
