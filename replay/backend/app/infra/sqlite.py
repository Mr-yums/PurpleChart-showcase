"""
PurpleReplay v2 — Connexions SQLite
— une connexion PAR THREAD (thread-local) : le lecteur de replay, le pool `to_thread`
et les tests ont chacun la leur ; jamais de connexion partagée entre threads, jamais d'accès
depuis la boucle asyncio. L'archive est ouverte en lecture seule (mode=ro), le journal d'edge
en WAL.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


def _uri(path: Path, mode: str) -> str:
    return "file:" + str(path).replace("\\", "/") + f"?mode={mode}"


def connect_ro(path: Path, *, cache_kb: int = 16384, mmap_bytes: int = 33554432) -> sqlite3.Connection:
    conn = sqlite3.connect(_uri(path, "ro"), uri=True, timeout=15, check_same_thread=False)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute(f"PRAGMA cache_size=-{int(cache_kb)}")
    conn.execute(f"PRAGMA mmap_size={int(mmap_bytes)}")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA query_only=1")
    return conn


def connect_rw(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15, check_same_thread=False)
    conn.execute("PRAGMA busy_timeout=8000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


class ThreadLocalConnection:
    """Fabrique paresseuse : `get()` renvoie la connexion du thread courant (créée au besoin)."""

    def __init__(self, path: Path, *, readonly: bool = True) -> None:
        self.path = Path(path)
        self.readonly = readonly
        self._local = threading.local()

    def get(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = connect_ro(self.path) if self.readonly else connect_rw(self.path)
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
