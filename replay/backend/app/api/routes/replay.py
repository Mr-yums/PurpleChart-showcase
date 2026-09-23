"""Contrôle du replay : séances, chargement, démo live, lecture, vitesse, statut, catalogue des régimes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import Container, get_container
from app.schemas.replay import LoadRequest, ReplayStatus, SpeedRequest

router = APIRouter(prefix="/replay", tags=["replay"])


@router.get("/sessions")
async def sessions(c: Container = Depends(get_container)) -> dict:
    return {"sessions": await c.market.sessions()}


@router.post("/load")
async def load(payload: LoadRequest, c: Container = Depends(get_container)) -> dict:
    return await c.replay.load(payload.symbol, payload.start_ts, payload.speed, payload.source)


@router.post("/play")
async def play(c: Container = Depends(get_container)) -> dict:
    return c.replay.play()


@router.post("/pause")
async def pause(c: Container = Depends(get_container)) -> dict:
    return c.replay.pause()


@router.post("/speed")
async def speed(payload: SpeedRequest, c: Container = Depends(get_container)) -> dict:
    return c.replay.speed(payload.speed)


@router.get("/status", response_model=ReplayStatus)
async def status(c: Container = Depends(get_container)) -> ReplayStatus:
    return ReplayStatus(**c.replay.status())


@router.get("/regimes")
async def regimes(c: Container = Depends(get_container)) -> dict:
    return await c.regimes.catalogue()


# [Sol] Explicit resume retains cursor, simulated position, balance and fees across full shutdown.
@router.get("/checkpoint")
async def checkpoint(c: Container = Depends(get_container)) -> dict:
    return await c.replay.saved()


@router.post("/resume")
async def resume(c: Container = Depends(get_container)) -> dict:
    return await c.replay.resume()
