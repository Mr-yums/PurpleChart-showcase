"""Contrats d'entrée/sortie du contrôle de replay."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LoadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    source: str = Field(default="legacy", pattern="^(legacy|v2)$")  # [Sol]
    symbol: str = Field(min_length=1, max_length=20)
    start_ts: float = Field(gt=0)
    speed: float | None = Field(default=None, gt=0)


class LiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    symbol: str = Field(default="NQ", min_length=1, max_length=20)
    tf: str = Field(default="5m", min_length=2, max_length=4)


class SpeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    speed: float = Field(gt=0)


class ReplayStatus(BaseModel):
    loaded: bool
    playing: bool
    ended: bool
    live: bool
    buffering: bool
    symbol: str | None
    speed: float
    cursor_ts: float
    start_ts: float
    context_start: float
    seq: int
    pending: int
    clients: int
    feed_connected: bool
