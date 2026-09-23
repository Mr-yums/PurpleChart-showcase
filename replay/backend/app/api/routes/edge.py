"""Journal d'edge : trades journalisés, agrégats tag×régime, agrégats GEX, tag manuel sticky."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import Container, get_container
from app.schemas.paper import TagRequest

router = APIRouter(prefix="/edge", tags=["edge"])


@router.get("/journal")
async def journal(limit: int = Query(500, ge=1, le=5000), c: Container = Depends(get_container)) -> dict:
    return await c.edge.journal(limit)


@router.get("/stats")
async def stats(c: Container = Depends(get_container)) -> dict:
    return await c.edge.stats()


@router.get("/gex-stats")
async def gex_stats(c: Container = Depends(get_container)) -> dict:
    return await c.edge.gex_stats()


@router.post("/tag")
async def set_tag(payload: TagRequest, c: Container = Depends(get_container)) -> dict:
    return c.edge.set_tag(payload.symbol, payload.tag)


@router.get("/sticky")
async def sticky(symbol: str = Query("US100.cash"), c: Container = Depends(get_container)) -> dict:
    return c.edge.get_tag(symbol)
