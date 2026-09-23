"""Contrats ciblés des services, sans dépendance HTTP, SQLite ou FastAPI."""

from typing import Protocol


class SessionCatalogue(Protocol):
    @property
    def cached_symbols(self) -> set[str]: ...
    async def sessions(self) -> list[dict]: ...
    async def ensure(self, symbol: str, cursor: float) -> None: ...


class GammaProjection(Protocol):
    def context_at(self, symbol: str, cursor: float) -> tuple | None: ...


class GammaHistory(Protocol):
    def levels_between(self, iso_from: str, iso_to: str) -> list[tuple]: ...
    def last_level_before(self, iso_to: str) -> tuple | None: ...


class PriceHistory(Protocol):
    def last_trade_before(self, symbol: str, t: float) -> tuple | None: ...


class ReplayCursor(Protocol):
    def cap(self, symbol: str, to: float) -> float: ...
