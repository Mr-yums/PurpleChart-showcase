"""
PurpleReplay v2 — Sources de trades
— le moteur ne lit JAMAIS l'archive dans la boucle asyncio. `ArchiveSource` possède un thread
lecteur qui précharge des lots dans une file bornée ; la boucle ne fait que `take_until(cursor)`.
`LiveSource` reçoit les trades poussés par le relais du feed Go (démo live). Même interface.
"""

from __future__ import annotations

import queue
import threading
from typing import Callable, Protocol


class TradeSource(Protocol):
    def take_until(self, cursor: float) -> list[dict]: ...
    def next_time(self) -> float | None: ...
    @property
    def exhausted(self) -> bool: ...
    @property
    def buffering(self) -> bool: ...
    def stop(self) -> None: ...


class ArchiveSource:
    """Lecture en avance de phase (thread) ; consommation non bloquante côté boucle."""

    def __init__(
        self,
        fetch_chunk: Callable[[float], list[dict]],
        start_t: float,
        *,
        prefetch_chunks: int = 3,
        name: str = "replay-reader",
    ) -> None:
        self._fetch = fetch_chunk
        self._last_t = float(start_t)
        self._queue: "queue.Queue[list[dict]]" = queue.Queue(maxsize=max(1, prefetch_chunks))
        self._buffer: list[dict] = []
        self._pos = 0
        self._dry = threading.Event()
        self._stop = threading.Event()
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._thread.start()

    # ---------------- thread lecteur
    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                rows = self._fetch(self._last_t)
                if not rows:
                    self._dry.set()
                    return
                self._last_t = rows[-1]["t"]
                while not self._stop.is_set():
                    try:
                        self._queue.put(rows, timeout=0.25)
                        break
                    except queue.Full:
                        continue
        except BaseException as exc:  # noqa: BLE001 — remonté à la boucle via `error`
            self._error = exc
            self._dry.set()

    # ---------------- côté boucle asyncio
    def _drain(self) -> None:
        # [Sol] At most one chunk outside the bounded queue.
        if self._pos < len(self._buffer):
            return
        self._buffer, self._pos = [], 0
        try:
            self._buffer = self._queue.get_nowait()
        except queue.Empty:
            pass

    def take_until(self, cursor: float) -> list[dict]:
        out = []
        while True:
            self._drain()
            if self._pos >= len(self._buffer):
                break
            start = self._pos
            while self._pos < len(self._buffer) and self._buffer[self._pos]["t"] <= cursor:
                self._pos += 1
            out.extend(self._buffer[start : self._pos])
            if self._pos < len(self._buffer):
                break
        return out

    def next_time(self) -> float | None:
        self._drain()
        if self._pos < len(self._buffer):
            return self._buffer[self._pos]["t"]
        return None

    @property
    def pending(self) -> int:
        self._drain()
        return len(self._buffer) - self._pos

    @property
    def exhausted(self) -> bool:
        return self._dry.is_set() and self.pending == 0

    @property
    def buffering(self) -> bool:
        return not self._dry.is_set() and self.pending == 0

    @property
    def error(self) -> BaseException | None:
        return self._error

    def stop(self) -> None:
        self._stop.set()


class LiveSource:
    """Trades poussés par le relais live (boucle asyncio) ; jamais épuisée, jamais en attente."""

    def __init__(self) -> None:
        self._buffer: list[dict] = []

    def push(self, trades: list[dict]) -> None:
        self._buffer.extend(trades)

    def take_until(self, cursor: float) -> list[dict]:
        out, self._buffer = self._buffer, []
        return out

    def next_time(self) -> float | None:
        return self._buffer[0]["t"] if self._buffer else None

    @property
    def pending(self) -> int:
        return len(self._buffer)

    @property
    def exhausted(self) -> bool:
        return False

    @property
    def buffering(self) -> bool:
        return False

    def stop(self) -> None:
        self._buffer = []
