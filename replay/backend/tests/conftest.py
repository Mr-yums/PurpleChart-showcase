"""Fixtures : mini-archive SQLite synthétique (schéma identique à l'archive réelle) + chemins temporaires."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

# Les tests ne lisent jamais backend/.env (config de dev locale) : chemins explicites uniquement.
os.environ.setdefault("PR_ENV_FILE", "/nonexistent/.env")

SCHEMA = """
CREATE TABLE tape_trades (id TEXT PRIMARY KEY, symbol TEXT NOT NULL, t REAL NOT NULL, timestamp TEXT,
  recv_ts REAL NOT NULL, price REAL NOT NULL, volume INTEGER NOT NULL, side TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'live', inserted_at REAL NOT NULL);
CREATE INDEX idx_tape_trades_symbol_t ON tape_trades(symbol, t);
CREATE TABLE tape_events (id TEXT PRIMARY KEY, trade_id TEXT NOT NULL, symbol TEXT NOT NULL, t REAL NOT NULL,
  price REAL NOT NULL, volume INTEGER NOT NULL, side TEXT NOT NULL, kind TEXT NOT NULL, inserted_at REAL NOT NULL,
  trigger_volume INTEGER, weight REAL, speed REAL, lots_per_sec INTEGER, dominance REAL, confidence REAL,
  score INTEGER, reason TEXT);
CREATE INDEX idx_tape_events_symbol_t ON tape_events(symbol, t);
CREATE TABLE recorded_trades (id TEXT PRIMARY KEY, topstep_id TEXT, order_id TEXT, contract_id TEXT, symbol TEXT,
  t REAL NOT NULL, timestamp TEXT, side TEXT, size REAL, price REAL, pnl REAL, fees REAL, commissions REAL,
  is_exit INTEGER, source TEXT NOT NULL DEFAULT 'topstep', context_json TEXT, inserted_at REAL NOT NULL, account_id INTEGER);
CREATE INDEX idx_recorded_trades_symbol_t ON recorded_trades(symbol, t);
"""

# Séance synthétique : ouverture Globex 22:00 UTC le 26/08/2026 -> trades toutes les secondes 13:00-13:30 UTC le 27/08.
SESSION_START = 1787781600.0  # 2026-08-26T22:00:00Z
T0 = SESSION_START + 15 * 3600  # 2026-08-27T13:00:00Z = 1787835600


def build_archive(path: Path, symbol: str = "NQ", n: int = 1800, step: float = 1.0) -> dict:
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA)
    trades, events = [], []
    price = 20000.0
    for i in range(n):
        t = T0 + i * step
        price += 0.25 if (i % 7) in (0, 1, 3) else -0.25
        side = "buy" if (i % 3) != 2 else "sell"
        vol = 1 + (i % 5) + (40 if i % 97 == 0 else 0)
        tid = f"{symbol}-{i}"
        trades.append(
            (
                tid,
                symbol,
                t,
                f"2026-08-27T{13 + (i // 3600):02d}:{(i // 60) % 60:02d}:{i % 60:02d}+00:00",
                t,
                price,
                vol,
                side,
                "live",
                t,
            )
        )
        if i % 97 == 0:
            events.append(
                (
                    f"ev-{i}",
                    tid,
                    symbol,
                    t,
                    price,
                    vol,
                    side,
                    "block",
                    t,
                    vol,
                    2.5,
                    3.0,
                    12,
                    0.6,
                    0.8,
                    70,
                    "gros lot",
                )
            )
        if i % 101 == 0:
            events.append(
                (
                    f"ev-s{i}",
                    tid,
                    symbol,
                    t,
                    price,
                    vol,
                    side,
                    "sweep",
                    t,
                    vol + 5,
                    3.1,
                    8.0,
                    30,
                    -0.4,
                    0.7,
                    55,
                    "rafale",
                )
            )
        if i % 211 == 0:
            events.append(
                (
                    f"ev-a{i}",
                    tid,
                    symbol,
                    t,
                    price,
                    vol,
                    side,
                    "absorb",
                    t,
                    vol + 9,
                    2.0,
                    1.0,
                    5,
                    0.9,
                    0.9,
                    88,
                    "absorption",
                )
            )
    # contexte de séance avant T0 (profil) : quelques trades clairsemés depuis l'ouverture Globex
    for j in range(200):
        t = SESSION_START + j * 60
        trades.append(
            (
                f"{symbol}-ctx{j}",
                symbol,
                t,
                "2026-08-26T22:00:00+00:00",
                t,
                19990.0 + (j % 10) * 0.25,
                2,
                "buy" if j % 2 else "sell",
                "live",
                t,
            )
        )
    conn.executemany("INSERT INTO tape_trades VALUES (?,?,?,?,?,?,?,?,?,?)", trades)
    conn.executemany("INSERT INTO tape_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", events)
    conn.executemany(
        "INSERT INTO recorded_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                "rt1",
                "1",
                "o1",
                "CON.F.US.MNQ",
                symbol,
                T0 + 100,
                "2026-08-27T13:01:40+00:00",
                "BUY",
                2,
                20001.0,
                None,
                1.22,
                0,
                0,
                "topstep",
                None,
                T0,
                123,
            ),
            (
                "rt2",
                "2",
                "o2",
                "CON.F.US.MNQ",
                symbol,
                T0 + 400,
                "2026-08-27T13:06:40+00:00",
                "SELL",
                2,
                20011.0,
                40.0,
                1.22,
                0,
                1,
                "topstep",
                None,
                T0,
                123,
            ),
            (
                "rt3",
                "3",
                "o3",
                "CON.F.US.MNQ",
                symbol,
                T0 + 3000,
                "2026-08-27T13:50:00+00:00",
                "SELL",
                1,
                20030.0,
                -15.0,
                1.22,
                0,
                1,
                "topstep",
                None,
                T0,
                123,
            ),
        ],
    )
    conn.commit()
    conn.close()
    return {"symbol": symbol, "t0": T0, "t1": T0 + (n - 1) * step, "n": n, "session_start": SESSION_START}


@pytest.fixture()
def archive(tmp_path: Path) -> dict:
    path = tmp_path / "archive.sqlite"
    meta = build_archive(path)
    meta["path"] = path
    return meta


@pytest.fixture()
def gex_db(tmp_path: Path) -> Path:
    path = tmp_path / "gex.db"
    conn = sqlite3.connect(str(path))
    conn.executescript("""
    CREATE TABLE gex (ts TEXT, spot REAL, netGamma REAL, callWall REAL, putWall REAL, inflection REAL);
    CREATE TABLE vanna (ts TEXT, symbol TEXT, totalVanna REAL, totalCharm REAL, vannaFlip REAL, vannaRegime TEXT,
      vannaFlipUnstable INTEGER, bullDriftTarget REAL, bearMaxDanger REAL, bullBearRatio REAL, stockPrice REAL);
    INSERT INTO gex VALUES ('2026-08-26T20:00:00.000Z', 500.0, 1.5, 510.0, 490.0, 498.0);
    INSERT INTO gex VALUES ('2026-08-27T13:10:00.000Z', 502.0, -0.7, 512.0, 492.0, 500.0);
    INSERT INTO vanna VALUES ('2026-08-27T13:05:00.000Z', 'NDX', 1.0, 0.5, 20050.0, 'BULL', 0, 20100.0, 19900.0, 1.4, 20000.0);
    """)
    conn.commit()
    conn.close()
    return path
