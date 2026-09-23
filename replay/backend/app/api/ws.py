"""
PurpleReplay v2 — Endpoint WebSocket
— `/ws?symbol=NQ&tf=5m`. Le client reçoit un `snapshot`, puis les trames `tape`, `dom`,
`candle`, `positions`, `status`. Il peut se réabonner en envoyant `{"symbol": ..., "tf": ...}`.
L'écriture passe par la file du hub : la lecture ici ne bloque jamais la diffusion.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.exceptions import DomainError
from app.core.logging import get_logger

router = APIRouter()
log = get_logger("ws")


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket, symbol: str = Query("NQ"), tf: str = Query("5m")) -> None:
    c = getattr(ws.state, "visitor_container", ws.app.state.container)
    await ws.accept()
    try:
        await c.replay.subscribe(ws, symbol, tf)
        while True:
            msg = await ws.receive_json()
            if not isinstance(msg, dict):
                continue
            symbol = str(msg.get("symbol") or symbol)
            tf = str(msg.get("tf") or tf)
            try:
                await c.replay.subscribe(ws, symbol, tf)
            except DomainError as exc:
                c.hub.send(ws, {"type": "error", "data": {"detail": exc.message}})
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        log.info("ws fermé: %s", exc)
    finally:
        c.hub.remove(ws)
        if c.hub.count == 0 and c.engine.loaded:
            c.replay.pause()
            await c.replay.checkpoint()
