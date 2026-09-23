"""Données marché rejouées : instruments, bougies, marques orderflow (plafonnées au curseur)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import Container, get_container

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/instruments")
async def instruments(c: Container = Depends(get_container)) -> dict:
    return await c.market.instruments()


@router.get("/candles")
async def candles(
    symbol: str = Query("NQ"),
    tf: str = Query("5m"),
    n: int = Query(500, ge=10, le=1000),
    c: Container = Depends(get_container),
) -> dict:
    rows = await c.market.candles(symbol, tf, n)
    return {"symbol": symbol, "tf": tf, "count": len(rows), "candles": rows}


@router.get("/events")
async def events(
    symbol: str = Query("NQ"),
    t_from: float = Query(0.0, alias="from"),
    to: float = Query(0.0),
    limit: int = Query(2000, ge=1, le=5000),
    c: Container = Depends(get_container),
) -> dict:
    return await c.market.events(symbol, t_from, to, limit)
