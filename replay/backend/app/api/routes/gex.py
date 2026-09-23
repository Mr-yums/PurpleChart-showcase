"""Niveaux GEX et vanna, forward-fill sans look-ahead, plafonnés au curseur replay."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import Container, get_container

router = APIRouter(prefix="/gex", tags=["gex"])


@router.get("/levels")
async def levels(
    symbol: str = Query("NQ"),
    t_from: float = Query(0.0, alias="from"),
    to: float = Query(0.0),
    c: Container = Depends(get_container),
) -> dict:
    return await c.gex.levels(symbol, t_from, to)


@router.get("/vanna")
async def vanna(symbol: str = Query("NDX"), to: float = Query(0.0), c: Container = Depends(get_container)):
    # [Sol] No snapshot is a normal nullable value, especially for V2 sessions.
    return await c.gex.vanna(symbol, to)
