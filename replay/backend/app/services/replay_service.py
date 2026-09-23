"""
PurpleReplay v2 — Replay Service
— chargement d'une séance (amorçage de l'état depuis l'archive en thread, source préchargée),
bascule démo live (relais du feed v2), play/pause/vitesse/statut, snapshot WS. Le moteur ne connaît
ni l'archive ni le relais : ce service les assemble.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict
from typing import Any, Callable

from app.core.config import ReplayConfig
from app.core.exceptions import ConflictError, ValidationError
from app.core.logging import get_logger
from app.domain.instruments import instrument_for
from app.domain.paper.book import Position
from app.domain.replay.merge import attach_events
from app.domain.replay.sources import ArchiveSource, LiveSource
from app.domain.replay.state import SessionState
from app.domain.replay.timeframes import tf_seconds
from app.domain.sessions import anchor_session
from app.infra.hub import Hub

LiveRelay = Any
from app.repositories.archive_repository import ArchiveRepository
from app.services.market_service import MarketService
from app.services.replay_engine import ReplayEngine

log = get_logger("replay")


class ReplayService:
    def __init__(
        self,
        cfg: ReplayConfig,
        archive: ArchiveRepository,
        market: MarketService,
        engine: ReplayEngine,
        hub: Hub,
        relay_factory: Callable[..., LiveRelay] | None,
        paper,
        *,
        checkpoint_repo=None,
    ) -> None:
        self._cfg = cfg
        self._archive = archive
        self._market = market
        self._engine = engine
        self._hub = hub
        self._relay_factory = relay_factory
        self._relay: LiveRelay | None = None
        self._paper = paper
        self._heartbeat: asyncio.Task | None = None
        self.checkpoint_repo = checkpoint_repo
        self._load_lock = asyncio.Lock()

    # ---------------- battement de statut (rien de chargé : le moteur ne tourne pas, le front doit quand même
    # recevoir un statut régulier, sinon son chien de garde de fraîcheur reconnecterait la socket)
    def start_heartbeat(self, interval: float = 2.0) -> None:
        if self._heartbeat is None or self._heartbeat.done():
            self._heartbeat = asyncio.create_task(self._heartbeat_loop(interval), name="status-heartbeat")

    async def _heartbeat_loop(self, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            if not self._engine.running and self._hub.count:
                self._hub.broadcast({"type": "status", "data": self._engine.status_payload()})

    # ---------------- archive
    def _seed_state(self, symbol: str, context_start: float, start_ts: float) -> SessionState:
        """BLOQUANT : profil, stats, delta, EWMA, dernier prix depuis l'ouverture Globex jusqu'au départ."""
        repo = self._archive
        state = SessionState(
            symbol, instrument_for(symbol), ring=self._cfg.recent_ring, max_delta=self._cfg.delta_buckets
        )
        state.seed(
            profile_rows=repo.profile(symbol, context_start, start_ts),
            stats_row=repo.stats(symbol, context_start, start_ts),
            delta_rows=repo.delta_minutes(symbol, context_start, start_ts),
            volumes=repo.recent_volumes(symbol, start_ts, 400),
            last_row=repo.last_trade_before(symbol, start_ts),
        )
        return state

    def _fetch_chunk(self, symbol: str, until: float = float("inf")):
        repo, chunk = getattr(self._archive, "active", self._archive), self._cfg.chunk

        def fetch(after_t: float) -> list[dict]:
            rows = [r for r in repo.trades_after(symbol, after_t, chunk) if r[0] < until]
            if not rows:
                return []
            events = repo.events_between(symbol, rows[0][0], rows[-1][0])
            return attach_events(symbol, rows, events)

        return fetch

    async def load(self, symbol: str, start_ts: float, speed: float | None, source: str = "legacy") -> dict:
        async with self._load_lock:  # [Sol] Sources cannot switch underneath an active reader.
            return await self._load(symbol, start_ts, speed, source)

    async def _load(self, symbol: str, start_ts: float, speed: float | None, source: str) -> dict:
        if self._paper.book.position is not None:
            raise ConflictError("Ferme la position simulée avant de changer de séance.")
        if self._market.importer:
            await self._engine.stop()
            if source == "v2":
                await self._market.importer.ensure(symbol, start_ts)
            self._archive.select(source)
            self._market.invalidate_archive_cache()
        await self._market.require_symbol(symbol)
        rng = await asyncio.to_thread(self._archive.time_range, symbol)
        if not rng:
            raise ValidationError("aucune donnée pour ce symbole")
        lo, hi = rng
        start_ts = max(lo, min(float(start_ts), hi))
        context_start = anchor_session(start_ts)
        await self._stop_relay()
        state = await asyncio.to_thread(self._seed_state, symbol, context_start, start_ts)
        source = ArchiveSource(
            self._fetch_chunk(symbol, context_start + 86400),
            start_ts,
            prefetch_chunks=self._cfg.prefetch_chunks,
        )
        await self._engine.start_archive(
            symbol, state, source, start_ts, speed or self._cfg.default_speed, context_start
        )
        self._paper.drop_position()
        log.info("replay chargé %s @ %.0f (x%.2f)", symbol, start_ts, self._engine.clock.speed)
        await self.broadcast_snapshots()
        return {
            "ok": True,
            "symbol": symbol,
            "cursor": self._engine.cursor,
            "speed": self._engine.clock.speed,
            "context_start": context_start,
        }

    # ---------------- démo live
    async def live(self, symbol: str, tf: str) -> dict:
        if self._relay_factory is None:
            raise ConflictError("démo live indisponible (relais non configuré)")
        tf_seconds(tf)
        now = time.time()
        state = SessionState(
            symbol, instrument_for(symbol), ring=self._cfg.recent_ring, max_delta=self._cfg.delta_buckets
        )
        await self._engine.start_live(symbol, state, LiveSource(), now, anchor_session(now))
        self._paper.drop_position()
        await self._stop_relay()
        self._relay = self._relay_factory(on_trades=self._engine.feed_live, on_status=self._on_live_status)
        self._relay.start(symbol)
        log.info("démo live %s", symbol)
        await self.broadcast_snapshots()
        return {"ok": True, "live": True, "symbol": symbol, "tf": tf}

    def _on_live_status(self, status: dict) -> None:
        self._engine.feed_connected = bool(status.get("connected"))

    async def _stop_relay(self) -> None:
        relay, self._relay = self._relay, None
        if relay:
            await relay.stop()

    # ---------------- contrôle
    def play(self) -> dict:
        if not self._engine.loaded:
            raise ConflictError("aucune session chargée")
        return {"ok": True, "playing": self._engine.play()}

    def pause(self) -> dict:
        self._engine.pause()
        return {"ok": True, "playing": False}

    def speed(self, speed: float) -> dict:
        return {"ok": True, "speed": self._engine.set_speed(speed)}

    def status(self) -> dict:
        return self._engine.status_payload()

    async def checkpoint(self) -> dict:
        self._engine.pause()
        await self._engine.stop_loop()
        if not self.checkpoint_repo or not self._engine.loaded:
            return {"saved": False}
        book = self._paper.book
        payload = {
            "symbol": self._engine.symbol,
            "cursor": self._engine.cursor,
            "speed": self._engine.clock.speed,
            "source": getattr(self._archive, "kind", "legacy"),
            "realized_pnl": book.realized_pnl,
            "realized_fees": book.realized_fees,
            "position": asdict(book.position) if book.position else None,
        }
        await asyncio.to_thread(self.checkpoint_repo.write, payload)
        return {"saved": True}

    async def saved(self) -> dict:
        data = await asyncio.to_thread(self.checkpoint_repo.read, None) if self.checkpoint_repo else None
        return {"checkpoint": data}

    async def resume(self) -> dict:
        data = (await self.saved())["checkpoint"]
        if not data:
            raise ConflictError("Aucune séance enregistrée à reprendre.")
        result = await self.load(data["symbol"], data["cursor"], data["speed"], data.get("source", "legacy"))
        book = self._paper.book
        book.realized_pnl = float(data.get("realized_pnl", 0))
        book.realized_fees = float(data.get("realized_fees", 0))
        book.position = Position(**data["position"]) if data.get("position") else None
        await self.broadcast_snapshots()
        return result

    async def shutdown(self) -> None:
        await self.checkpoint()
        if self._heartbeat:
            self._heartbeat.cancel()
            self._heartbeat = None
        await self._stop_relay()
        await self._engine.stop()

    # ---------------- abonnements WS
    async def snapshot(self, symbol: str) -> dict:
        view = self._engine.view()
        marks: list[dict] = []
        if view.loaded and view.symbol == symbol and not view.live:
            marks = await self._market.marks_for_snapshot(symbol, view.context_start, view.cursor_ts)
        return self._engine.snapshot_payload(symbol, marks, self._paper.positions(), self._paper.account())

    async def broadcast_snapshots(self) -> None:
        for symbol in {s for s, _ in self._hub.pairs()}:
            self._hub.broadcast(await self.snapshot(symbol), symbol=symbol)

    async def subscribe(self, ws, symbol: str, tf: str) -> None:
        tf_seconds(tf)
        new = not self._hub.has(ws)
        self._hub.add(ws, symbol, tf)
        if self._engine.live and self._relay is not None and symbol != self._engine.symbol:
            if new:
                self._hub.prime(ws, await self.snapshot(symbol))
            await self.live(symbol, tf)  # en démo live, le symbole affiché est celui relayé
            return
        snap = await self.snapshot(symbol)
        if new:
            self._hub.prime(ws, snap)  # le snapshot précède toute trame diffusée
        else:
            self._hub.send(ws, snap)
