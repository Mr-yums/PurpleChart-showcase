"""
PurpleReplay v2 — Hub WebSocket
— un client = une file bornée + une tâche d'écriture. La boucle du moteur ne fait que
`put_nowait` : un navigateur lent ou une socket à moitié morte ne bloque jamais le replay ni les
autres clients (il est déconnecté, même patron que le hub Go de PurpleChart v2).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.logging import get_logger

log = get_logger("hub")


class Socket(Protocol):
    async def send_json(self, data: Any) -> None: ...
    async def close(self, code: int = 1000) -> None: ...


@dataclass(slots=True)
class Client:
    ws: Any
    symbol: str
    tf: str
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=512))
    writer: asyncio.Task | None = None
    ready: asyncio.Event = field(
        default_factory=asyncio.Event
    )  # levé par `prime()` : le snapshot part avant tout
    primer: dict | None = None


class Hub:
    def __init__(self) -> None:
        self._clients: dict[Any, Client] = {}

    # ---------------- cycle de vie des clients
    def add(self, ws: Any, symbol: str, tf: str) -> Client:
        """Enregistre (ou ré-abonne) un client. Un NOUVEAU client ne reçoit rien tant que `prime()` n'a pas
        fourni son snapshot : les trames diffusées entre-temps s'accumulent derrière lui (les trades déjà couverts
        par le snapshot sont ignorés côté front grâce à `seq`)."""
        c = self._clients.get(ws)
        if c is None:
            c = Client(ws=ws, symbol=symbol, tf=tf)
            c.writer = asyncio.create_task(self._write_loop(c))
            self._clients[ws] = c
        else:
            c.symbol, c.tf = symbol, tf
        return c

    def has(self, ws: Any) -> bool:
        return ws in self._clients

    def prime(self, ws: Any, snapshot: dict) -> None:
        c = self._clients.get(ws)
        if not c:
            return
        if c.ready.is_set():
            self._enqueue(c, snapshot)
        else:
            c.primer = snapshot
            c.ready.set()

    def remove(self, ws: Any) -> None:
        c = self._clients.pop(ws, None)
        if c and c.writer:
            c.writer.cancel()

    def subscription(self, ws: Any) -> tuple[str, str] | None:
        c = self._clients.get(ws)
        return (c.symbol, c.tf) if c else None

    def pairs(self) -> set[tuple[str, str]]:
        return {(c.symbol, c.tf) for c in self._clients.values()}

    def tfs_for(self, symbol: str) -> set[str]:
        return {c.tf for c in self._clients.values() if c.symbol == symbol}

    @property
    def count(self) -> int:
        return len(self._clients)

    # ---------------- diffusion
    def send(self, ws: Any, message: dict) -> None:
        c = self._clients.get(ws)
        if c:
            self._enqueue(c, message)

    def broadcast(self, message: dict, *, symbol: str | None = None, tf: str | None = None) -> int:
        n = 0
        for c in list(self._clients.values()):
            if symbol is not None and c.symbol != symbol:
                continue
            if tf is not None and c.tf != tf:
                continue
            self._enqueue(c, message)
            n += 1
        return n

    def _enqueue(self, c: Client, message: dict) -> None:
        try:
            c.queue.put_nowait(message)
        except asyncio.QueueFull:
            log.warning("client lent déconnecté (%s %s)", c.symbol, c.tf)
            self.remove(c.ws)
            asyncio.create_task(self._close(c.ws))

    async def _close(self, ws: Any) -> None:
        try:
            await ws.close(code=1013)
        except Exception:  # noqa: BLE001
            pass

    async def _write_loop(self, c: Client) -> None:
        try:
            await c.ready.wait()
            if c.primer is not None:
                await c.ws.send_json(c.primer)
                c.primer = None
            while True:
                msg = await c.queue.get()
                await c.ws.send_json(msg)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — socket fermée côté client
            self._clients.pop(c.ws, None)

    async def close_all(self) -> None:
        for ws in list(self._clients):
            self.remove(ws)
            await self._close(ws)
