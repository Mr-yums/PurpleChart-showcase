"""Journal des trades simulés et sessions d'entraînement."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import Container, get_container
from app.schemas.paper import SessionSaveRequest

router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("")
async def journal(
    since: float = Query(0.0, ge=0), all: int = Query(0, ge=0, le=1), c: Container = Depends(get_container)
) -> dict:
    return await c.journal.unified(since, bool(all))


@router.get("/sessions")
async def sessions(c: Container = Depends(get_container)) -> dict:
    return await c.journal.session_list()


@router.post("/sessions/save")
async def save(payload: SessionSaveRequest | None = None, c: Container = Depends(get_container)) -> dict:
    return await c.journal.session_save((payload or SessionSaveRequest()).label)


@router.get("/demo-trades")
async def demo_trades(
    limit: int = Query(0, ge=0), mode: str = Query(""), c: Container = Depends(get_container)
) -> dict:
    data = await c.journal.unified(0.0, True)
    rows = [t for t in data["trades"] if not mode or mode == "replay"]
    rows.reverse()
    return {"ok": True, "trades": rows[-limit:] if limit else rows, "summary": data["per_source"]}
