"""
PurpleReplay v2 — Paper Trading Service
— expose le carnet simulé : ticket, compte, positions, ordres (place/flatten/BE/partiel/modify/
reset). Écoute les prix du moteur (`on_prices`) pour déclencher SL/TP et échantillonner le PnL latent.
Persistance (JSONL + journal d'edge) en thread, diffusion des positions via le hub.
"""

from __future__ import annotations

import asyncio

from app.core.config import PaperConfig
from app.core.exceptions import ConflictError
from app.core.logging import get_logger
from app.core.time import wall as wall_clock
from app.domain.instruments import instrument_for
from app.domain.paper.book import Close, PaperBook
from app.infra.hub import Hub
from app.repositories.jsonl_repository import JsonlRepository
from app.services.edge_service import EdgeService
from app.services.replay_engine import ReplayEngine

log = get_logger("paper")


class PaperService:
    def __init__(
        self,
        cfg: PaperConfig,
        book: PaperBook,
        engine: ReplayEngine,
        hub: Hub,
        edge: EdgeService,
        demo_trades: JsonlRepository,
        wall=wall_clock,
    ) -> None:
        self._cfg = cfg
        self.book = book
        self._engine = engine
        self._hub = hub
        self._edge = edge
        self._demo = demo_trades
        self._wall = wall
        self._lock = asyncio.Lock()

    # ---------------- lectures
    @property
    def mode(self) -> str:
        return "live" if self._engine.live else "replay"

    def ticket(self, symbol: str) -> dict:
        return {"ok": True, **self.book.ticket_spec(symbol)}

    def account(self) -> dict:
        return self.book.account_payload()

    def positions(self) -> list[dict]:
        return self.book.positions_payload(self._engine.last_price)

    def _push_positions(self) -> None:
        symbol = self._engine.symbol or (self.book.position.symbol if self.book.position else None)
        self._hub.broadcast(
            {
                "type": "positions",
                "symbol": symbol,
                "data": {"positions": self.positions(), "account": self.account()},
            }
        )

    def drop_position(self) -> None:
        """Nouvelle session chargée : la position simulée n'a plus de marché, elle est abandonnée sans PnL."""
        if self.book.position is not None:
            self.book.position = None
            self._push_positions()

    # ---------------- ordres
    async def place(
        self,
        symbol: str | None,
        side: str,
        size: int,
        sl: float | None,
        tp: float | None,
        entry_ref: float | None,
        entry_tag: str | None,
    ) -> dict:
        symbol = symbol or self._engine.symbol or "US100.cash"
        if symbol != self._engine.symbol or not self._engine.loaded:  # [Sol]
            raise ConflictError("le symbole doit correspondre à la séance chargée")
        fill = self._engine.last_price if self._engine.last_price is not None else entry_ref
        if fill is None:
            raise ConflictError("aucun prix courant (charge une session)")
        cursor = self._engine.cursor
        async with self._lock:
            ctx = {}
            if self.book.position is None:
                ctx = await asyncio.to_thread(
                    self._edge.entry_snapshot, symbol, cursor, float(fill), entry_tag, self._engine.live
                )
            pos = self.book.place(
                symbol=symbol,
                side=side,
                size=size,
                sl=sl,
                tp=tp,
                fill=float(fill),
                cursor=cursor,
                wall=self._wall(),
                entry_tag=ctx.get("tag"),
                regime=ctx.get("regime"),
                context=ctx,
            )
        self._push_positions()
        digits = instrument_for(symbol).digits
        return {
            "ok": True,
            "fill": pos.entry,
            "side": pos.side,
            "size": pos.size,
            "sl_points": round(abs(pos.entry - pos.sl), digits) if pos.sl is not None else 0,
            "tp_points": round(abs(pos.entry - pos.tp), digits) if pos.tp is not None else 0,
            "regime": pos.regime,
            "entry_tag": pos.entry_tag,
            "setup": ctx.get("setup"),
            "dry_run": True,
        }

    async def flatten(self) -> dict:
        async with self._lock:
            had = self.book.position is not None
            close = self.book.flatten(self._engine.last_price, self._engine.cursor, self._wall())
        if close:
            await self._on_close(close)
        self._push_positions()
        return {
            "ok": True,
            "closed": had,
            "cancelled_orders": 0,
            "pnl": close.pnl if close else 0.0,
            "dry_run": True,
        }

    async def breakeven(self, offset_ticks: float = 0.0) -> dict:
        async with self._lock:
            p = self.book.position
            if not p:
                raise ConflictError("aucune position")
            new_sl = self.book.breakeven(self._engine.last_price, offset_ticks)
            entry = p.entry
        self._push_positions()
        return {"ok": True, "entry": entry, "price": new_sl, "sl": new_sl, "action": "moved", "dry_run": True}

    async def partial_close(self, size: int) -> dict:
        async with self._lock:
            if self.book.position is None:
                raise ConflictError("aucune position")
            exit_p = self._engine.last_price
            if exit_p is None:
                raise ConflictError("prix indisponible")
            close = self.book.partial(size, exit_p, self._engine.cursor, self._wall())
            remaining = self.book.position.size if self.book.position else 0
        await self._on_close(close)
        self._push_positions()
        return {
            "ok": True,
            "closed": close.size_closed,
            "remaining": remaining,
            "pnl": close.pnl,
            "dry_run": True,
        }

    async def modify(self, which: str, price: float) -> dict:
        async with self._lock:
            price = self.book.modify(which, price)
        self._push_positions()
        return {"ok": True, "kind": which, "price": price, "dry_run": True}

    async def reset(self) -> dict:
        async with self._lock:
            self.book.reset()
        self._push_positions()
        return {"ok": True, "account": self.account()}

    # ---------------- hook du moteur
    async def on_prices(self, lo: float, hi: float, last: float, cursor: float) -> None:
        p = self.book.position
        if p is None:
            return
        sample = self.book.sample(last, cursor, self._cfg.pnl_sample_seconds)
        if sample:
            self._spawn(self._edge.record_sample, sample, self.mode, cursor, "tick")
        close = self.book.check_stops(lo, hi, last, cursor, self._wall())
        if close:
            await self._on_close(close)
            self._push_positions()

    async def _on_close(self, close: Close) -> None:
        p = close.position
        record = {
            "ts_wall": round(close.wall, 3),
            "ts_market": round(close.cursor, 3),
            "mode": self.mode,
            "symbol": p.symbol,
            "side": p.side,
            "size": close.size_closed,
            "entry": p.entry,
            "exit": close.exit,
            "sl": p.sl,
            "tp": p.tp,
            "point_value": instrument_for(p.symbol).point_value,
            "pnl": close.pnl,
            "fees": close.fees,
            "pnl_net": close.pnl_net,
            "reason": close.reason,
            "opened_ts": p.opened_ts,
            "opened_wall": p.opened_wall,
            "realized_after": round(self.book.realized_pnl, 2),
            "entry_tag": p.entry_tag,
            "regime": p.regime,
        }
        final = self.book.sample(close.exit, close.cursor, 0.0)
        await asyncio.to_thread(self._persist_close, record, close, final)

    def _persist_close(self, record: dict, close: Close, final_sample: dict | None) -> None:
        """BLOQUANT (thread) : trade démo JSONL + journal d'edge. Une erreur d'écriture n'annule jamais un trade."""
        try:
            self._demo.append(record)
        except Exception:  # noqa: BLE001
            log.exception("écriture demo_trades")
        try:
            if final_sample:
                self._edge.record_sample(final_sample, record["mode"], close.cursor, "close:" + close.reason)
            self._edge.record_close(close, record["mode"], self.book.realized_pnl)
        except Exception:  # noqa: BLE001
            log.exception("écriture journal d'edge")

    def _spawn(self, fn, *args) -> None:
        async def run() -> None:
            try:
                await asyncio.to_thread(fn, *args)
            except Exception:  # noqa: BLE001
                log.exception("tâche paper en arrière-plan")

        asyncio.create_task(run())
