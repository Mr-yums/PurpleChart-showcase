"""
PurpleReplay v2 — Edge Journal Repository (edge_journal.sqlite, lecture/écriture)
— journal SQLite des trades paper (tag, régime, contexte, R, frais, GEX/vanna, MAE/MFE) et
échantillons de PnL latent. Schéma additif auto-migré (ALTER ADD COLUMN idempotent) : le fichier
existant de la V1 est repris tel quel, colonnes manquantes ajoutées et journalisées.
Bloquant : à appeler via `asyncio.to_thread`.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from app.core.logging import get_logger
from app.infra.sqlite import ThreadLocalConnection

log = get_logger("edge-journal")

TRADE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("ts_wall", "REAL"),
    ("ts_market", "REAL"),
    ("mode", "TEXT"),
    ("symbol", "TEXT"),
    ("side", "TEXT"),
    ("size", "INTEGER"),
    ("entry", "REAL"),
    ("exit", "REAL"),
    ("sl", "REAL"),
    ("tp", "REAL"),
    ("point_value", "REAL"),
    ("pnl", "REAL"),
    ("reason", "TEXT"),
    ("opened_ts", "REAL"),
    ("opened_wall", "REAL"),
    ("realized_after", "REAL"),
    ("entry_tag", "TEXT"),
    ("regime", "TEXT"),
    ("risk_usd", "REAL"),
    ("result_r", "REAL"),
    ("ctx_poc", "REAL"),
    ("ctx_poc_dist", "REAL"),
    ("ctx_vp_zone", "TEXT"),
    ("ctx_absorb", "REAL"),
    ("ctx_setup", "TEXT"),
    ("ctx_coherence", "TEXT"),
    ("sl_orig", "REAL"),
    ("fees", "REAL"),
    ("pnl_net", "REAL"),
    ("gex_regime", "TEXT"),
    ("vanna_regime", "TEXT"),
    ("above_flip", "TEXT"),
    ("dist_to_flip", "REAL"),
    ("dist_to_wall", "REAL"),
    ("mfe_usd", "REAL"),
    ("mae_usd", "REAL"),
    ("mfe_r", "REAL"),
    ("mae_r", "REAL"),
)
TRADE_COLUMN_NAMES = tuple(c for c, _ in TRADE_COLUMNS)
SAMPLE_COLUMNS = (
    "open_id",
    "ts_wall",
    "ts_market",
    "mode",
    "symbol",
    "side",
    "size",
    "entry",
    "last_price",
    "unrealized_pnl",
    "unrealized_r",
    "reason",
)


class EdgeJournalRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._db = ThreadLocalConnection(self.path, readonly=False)
        self._lock = threading.Lock()
        self._ready = False

    @property
    def conn(self) -> sqlite3.Connection:
        return self._db.get()

    def ensure_schema(self) -> None:
        with self._lock:
            if self._ready:
                return
            c = self.conn
            c.execute("CREATE TABLE IF NOT EXISTS paper_trades(id INTEGER PRIMARY KEY AUTOINCREMENT)")
            have = {r[1] for r in c.execute("PRAGMA table_info(paper_trades)")}
            for name, typ in TRADE_COLUMNS:
                if name not in have:
                    c.execute(f'ALTER TABLE paper_trades ADD COLUMN "{name}" {typ}')
                    log.info("schéma edge : +colonne paper_trades.%s %s", name, typ)
            c.execute(
                "CREATE TABLE IF NOT EXISTS trade_pnl_live(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " open_id REAL, ts_wall REAL, ts_market REAL, mode TEXT, symbol TEXT, side TEXT, size INTEGER,"
                " entry REAL, last_price REAL, unrealized_pnl REAL, unrealized_r REAL, reason TEXT)"
            )
            c.execute("CREATE INDEX IF NOT EXISTS idx_pnl_live_open ON trade_pnl_live(open_id)")
            c.commit()
            self._ready = True

    def insert_trade(self, row: dict) -> int:
        self.ensure_schema()
        cols = [k for k in TRADE_COLUMN_NAMES if k in row]
        with self._lock:
            cur = self.conn.execute(
                f"INSERT INTO paper_trades ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                [row[k] for k in cols],
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def insert_sample(self, row: dict) -> None:
        self.ensure_schema()
        with self._lock:
            self.conn.execute(
                f"INSERT INTO trade_pnl_live ({','.join(SAMPLE_COLUMNS)}) VALUES ({','.join('?' * len(SAMPLE_COLUMNS))})",
                [row.get(k) for k in SAMPLE_COLUMNS],
            )
            self.conn.commit()

    def list_trades(self, limit: int) -> list[dict]:
        self.ensure_schema()
        cols = ("id",) + TRADE_COLUMN_NAMES
        rows = self.conn.execute(
            f"SELECT {','.join(cols)} FROM paper_trades ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def tag_regime_rows(self) -> list[tuple]:
        self.ensure_schema()
        return self.conn.execute("SELECT entry_tag, regime, pnl, result_r FROM paper_trades").fetchall()

    def gex_rows(self) -> list[tuple]:
        self.ensure_schema()
        return self.conn.execute(
            "SELECT gex_regime, above_flip, side, pnl, result_r FROM paper_trades"
        ).fetchall()

    def count(self) -> int:
        self.ensure_schema()
        return int(self.conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0])
