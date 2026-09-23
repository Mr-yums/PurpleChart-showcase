"""
PurpleReplay v2 — Fichiers JSONL (trades démo, sessions) et JSON (cache, catalogue)
— append-only avec verrou ; lecture tolérante (lignes corrompues ignorées) ; écriture JSON atomique.
Bloquant : à appeler via `asyncio.to_thread`.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


class JsonlRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        out: list[dict] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
        return out

    def append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()


class JsonFileRepository:
    """Document JSON unique, relu si le fichier change (mtime) et écrit de façon atomique."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._cache: Any = None
        self._mtime: float | None = None

    def read(self, default: Any = None) -> Any:
        if not self.path.exists():
            return default
        mtime = self.path.stat().st_mtime
        if self._cache is not None and mtime == self._mtime:
            return self._cache
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except ValueError, OSError:
            return default
        self._cache, self._mtime = data, mtime
        return data

    def write(self, data: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with self._lock:
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(data, fh)
            os.replace(tmp, self.path)
            self._cache, self._mtime = data, self.path.stat().st_mtime
