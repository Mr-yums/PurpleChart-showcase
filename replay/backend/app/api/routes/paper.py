"""Paper-trading : ticket, compte, positions, ordres simulés (toujours dry_run, aucun broker)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import Container, get_container
from app.schemas.paper import BreakevenRequest, ModifyRequest, PartialRequest, PlaceRequest

router = APIRouter(prefix="/paper", tags=["paper"])


@router.get("/ticket")
async def ticket(symbol: str = Query("NQ"), c: Container = Depends(get_container)) -> dict:
    return c.paper.ticket(symbol)


@router.get("/account")
async def account(c: Container = Depends(get_container)) -> dict:
    return {"ok": True, "account": c.paper.account()}


@router.get("/positions")
async def positions(c: Container = Depends(get_container)) -> dict:
    return {"positions": c.paper.positions(), "orders": []}


@router.post("/place")
async def place(payload: PlaceRequest, c: Container = Depends(get_container)) -> dict:
    return await c.paper.place(
        payload.symbol,
        payload.side,
        payload.size,
        payload.sl_price,
        payload.tp_price,
        payload.entry_ref,
        payload.entry_tag,
    )


@router.post("/flatten")
async def flatten(c: Container = Depends(get_container)) -> dict:
    return await c.paper.flatten()


@router.post("/breakeven")
async def breakeven(payload: BreakevenRequest | None = None, c: Container = Depends(get_container)) -> dict:
    return await c.paper.breakeven((payload or BreakevenRequest()).offset_ticks)


@router.post("/partial-close")
async def partial_close(payload: PartialRequest, c: Container = Depends(get_container)) -> dict:
    return await c.paper.partial_close(payload.size)


@router.post("/modify")
async def modify(payload: ModifyRequest, c: Container = Depends(get_container)) -> dict:
    return await c.paper.modify(payload.which, payload.price)


@router.post("/reset")
async def reset(c: Container = Depends(get_container)) -> dict:
    return await c.paper.reset()
