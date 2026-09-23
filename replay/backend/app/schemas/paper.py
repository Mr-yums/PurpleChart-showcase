"""Contrats du paper-trading : intentions explicites, prix strictement positifs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PlaceRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    symbol: str | None = Field(default=None, max_length=20)
    side: Literal["buy", "sell"]
    size: int = Field(default=1, ge=1, le=1000)
    sl_price: float | None = Field(default=None, gt=0)
    tp_price: float | None = Field(default=None, gt=0)
    entry_ref: float | None = Field(default=None, gt=0)
    entry_tag: str | None = Field(default=None, max_length=20)
    risk_usd: float | None = Field(default=None, ge=0)  # trace : le sizing est fait côté front


class BreakevenRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    offset_ticks: float = Field(default=0.0, ge=0)


class PartialRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    size: int = Field(default=1, ge=1, le=1000)


class ModifyRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    which: Literal["sl", "tp"]
    price: float = Field(gt=0)


class TagRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    symbol: str = Field(default="US100.cash", max_length=20)
    tag: str | None = Field(default=None, max_length=20)


class SessionSaveRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    label: str = Field(default="", max_length=120)
