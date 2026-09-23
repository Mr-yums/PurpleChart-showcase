"""
PurpleReplay v2 — Moteur de replay
— boucle asyncio cadencée (tick 250 ms) qui avance le curseur, consomme les trades déjà
préchargés par la source (jamais d'I/O ici), met à jour l'état de séance, diffuse tape/dom/bougies/
statut via le hub et notifie le paper-trading de l'intervalle de prix traversé.
Une seule session à la fois. `step()` est public : les tests l'appellent sans attendre l'horloge.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Callable, Protocol

from app.core.config import ReplayConfig
from app.core.logging import get_logger
from app.core.time import wall as wall_clock
from app.domain.replay.clock import ReplayClock
from app.domain.replay.sources import LiveSource, TradeSource
from app.domain.replay.state import SessionState
from app.domain.replay.timeframes import tf_seconds
from app.infra.hub import Hub

log = get_logger("replay-engine")

CandleLoader = Callable[
    [str, int, float], "dict | None"
]  # (symbol, tf_s, cursor) -> bougie en cours, BLOQUANT


class PriceListener(Protocol):
    async def on_prices(self, lo: float, hi: float, last: float, cursor: float) -> None: ...


@dataclass(slots=True)
class ReplayView:
    loaded: bool = False
    playing: bool = False
    ended: bool = False
    live: bool = False
    buffering: bool = False
    symbol: str | None = None
    speed: float = 5.0
    cursor_ts: float = 0.0
    start_ts: float = 0.0
    context_start: float = 0.0
    seq: int = 0
    pending: int = 0
    clients: int = 0
    feed_connected: bool = False


class ReplayEngine:
    def __init__(
        self,
        cfg: ReplayConfig,
        hub: Hub,
        *,
        candle_loader: CandleLoader | None = None,
        listener: PriceListener | None = None,
        wall: Callable[[], float] = wall_clock,
    ) -> None:
        self.cfg = cfg
        self.hub = hub
        self._candle_loader = candle_loader
        self._listener = listener
        self._wall = wall
        self.clock = ReplayClock(min_speed=cfg.min_speed, max_speed=cfg.max_speed, speed=cfg.default_speed)
        self.state: SessionState | None = None
        self.source: TradeSource | None = None
        self.symbol: str | None = None
        self.context_start = 0.0
        self.live = False
        self.feed_connected = False
        self._task: asyncio.Task | None = None
        self._beat = 0
        self._loading_candles: set[int] = set()
        self._generation = 0

    def bind(self, *, candle_loader: CandleLoader, listener: PriceListener) -> None:
        """Achever l'assemblage cyclique avant le démarrage du moteur."""
        if self.loaded:
            raise RuntimeError("Impossible de recâbler un replay chargé")
        self._candle_loader = candle_loader
        self._listener = listener

    # ---------------- lectures
    @property
    def loaded(self) -> bool:
        return self.state is not None and self.symbol is not None

    @property
    def last_price(self) -> float | None:
        return self.state.last_price if self.state else None

    @property
    def cursor(self) -> float:
        return self.clock.cursor

    def view(self) -> ReplayView:
        src = self.source
        return ReplayView(
            loaded=self.loaded,
            playing=self.clock.playing,
            ended=self.clock.ended,
            live=self.live,
            buffering=bool(src and src.buffering and self.clock.playing),
            symbol=self.symbol,
            speed=self.clock.speed,
            cursor_ts=self.clock.cursor,
            start_ts=self.clock.start,
            context_start=self.context_start,
            seq=self.state.seq if self.state else 0,
            pending=getattr(src, "pending", 0) if src else 0,
            clients=self.hub.count,
            feed_connected=self.feed_connected,
        )

    def status_payload(self) -> dict:
        return asdict(self.view())

    def cap(self, symbol: str, to: float) -> float:
        """Garde anti-spoiler : borne `to` au curseur si le replay archive concerne ce symbole."""
        if self.loaded and not self.live and symbol == self.symbol:
            return min(to, self.clock.cursor)
        return to

    # ---------------- cycle de vie
    async def start_archive(
        self,
        symbol: str,
        state: SessionState,
        source: TradeSource,
        start_ts: float,
        speed: float,
        context_start: float,
    ) -> None:
        await self.stop()
        self.symbol, self.state, self.source = symbol, state, source
        self.context_start = context_start
        self.live = False
        self.clock.reset(start_ts, speed)
        self._start_loop()

    async def start_live(
        self, symbol: str, state: SessionState, source: LiveSource, now: float, context_start: float
    ) -> None:
        await self.stop()
        self.symbol, self.state, self.source = symbol, state, source
        self.context_start = context_start
        self.live = True
        self.clock.reset(now, 1.0)
        self.clock.play()
        self._start_loop()

    def _start_loop(self) -> None:
        self._beat = 0
        self._generation += 1
        self._loading_candles.clear()
        self._task = asyncio.create_task(self._run(), name="replay-loop")

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def stop_loop(self) -> None:
        """Arrête la tâche cadencée sans toucher à l'état (tests : `step()` piloté à la main)."""
        task, self._task = self._task, None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError, Exception:  # noqa: BLE001
                pass

    async def stop(self) -> None:
        await self.stop_loop()
        if self.source:
            self.source.stop()
        self.source = None
        self.state = None
        self.symbol = None
        self.live = False
        self.feed_connected = False
        self.clock.pause()

    def play(self) -> bool:
        if not self.loaded:
            return False
        return self.clock.play()

    def pause(self) -> None:
        self.clock.pause()

    def set_speed(self, speed: float) -> float:
        return self.clock.set_speed(speed)

    def feed_live(self, trades: list[dict]) -> None:
        """Trades du relais live -> source live (consommés au prochain step)."""
        if self.live and isinstance(self.source, LiveSource):
            self.source.push(trades)

    # ---------------- boucle
    async def _run(self) -> None:
        tick = self.cfg.tick_seconds
        try:
            while True:
                await asyncio.sleep(tick)
                try:
                    await self.step()
                except Exception:  # noqa: BLE001 — la boucle ne meurt jamais sur une trame
                    log.exception("erreur dans la boucle de replay")
        except asyncio.CancelledError:
            raise

    async def step(self) -> None:
        state, source = self.state, self.source
        if state is None or source is None:
            return
        if getattr(source, "error", None) is not None:  # [Sol]
            self.clock.pause()
            self.hub.broadcast({"type": "error", "data": {"detail": "Lecture de l’archive interrompue"}})
            self._send_status()
            return
        self._beat += 1
        beat, cfg, clock, symbol = self._beat, self.cfg, self.clock, self.symbol
        if not clock.playing:
            if beat % (cfg.dom_every_ticks * 2) == 0:
                self._send_dom()
                self._send_status()
            return
        if self.live:
            batch = source.take_until(float("inf"))
            if batch:
                clock.jump(batch[-1]["t"])
            else:
                clock.advance(cfg.tick_seconds)  # horloge marché suit le temps réel entre deux trades
        else:
            if source.buffering:
                if beat % cfg.dom_every_ticks == 0:
                    self._send_status()
                return  # lecteur en retard : on ne saute rien, on attend
            clock.advance(cfg.tick_seconds)
            batch = source.take_until(clock.cursor)
            if not batch:
                nxt = source.next_time()
                if nxt is not None and nxt > clock.cursor + cfg.gap_skip_seconds:
                    clock.jump(nxt - cfg.tick_seconds)  # trou de flux (nuit, panne) : pas d'air mort
            if source.exhausted:
                clock.finish()
        for tr in batch:
            state.apply(tr)
            if self._listener is not None:  # [Sol] Ordered fills, never batch min/max.
                await self._listener.on_prices(tr["price"], tr["price"], tr["price"], tr["t"])
        if batch:
            self._send_tape(batch)
        elif state.last_price is not None and self._listener is not None:
            await self._notify_prices(state.last_price, state.last_price, state.last_price)
        if beat % cfg.dom_every_ticks == 0:
            self._send_dom()
            self._send_status()
        if beat % cfg.candle_every_ticks == 0:
            self._send_candles()
        if clock.ended:
            self._send_status()

    async def _notify_prices(self, lo: float, hi: float, last: float) -> None:
        if self._listener is not None:
            await self._listener.on_prices(lo, hi, last, self.clock.cursor)

    # ---------------- diffusion
    def _send_tape(self, batch: list[dict]) -> None:
        state = self.state
        cap = self.cfg.tape_batch_cap
        if len(batch) > cap:
            # les prints classifiés (marques) passent toujours ; le bruit est plafonné
            marked = [t for t in batch[:-cap] if t.get("kind")]
            trades = marked + batch[-cap:]
        else:
            trades = batch
        self.hub.broadcast(
            {
                "type": "tape",
                "symbol": self.symbol,
                "data": {
                    "symbol": self.symbol,
                    "seq": state.seq,
                    "trades": trades,
                    "delta_minutes": state.delta[-3:],
                    "stats": state.stats_payload(),
                },
            },
            symbol=self.symbol,
        )

    def _send_dom(self) -> None:
        dom = self.state.dom_payload(self.clock.cursor) if self.state else None
        if dom:
            self.hub.broadcast({"type": "dom", "symbol": self.symbol, "data": dom}, symbol=self.symbol)

    def _send_status(self) -> None:
        self.hub.broadcast({"type": "status", "data": self.status_payload()})

    def _send_candles(self) -> None:
        state, symbol = self.state, self.symbol
        for tf in self.hub.tfs_for(symbol):
            try:
                tf_s = tf_seconds(tf)
            except Exception:  # noqa: BLE001
                continue
            if not state.has_candle(tf_s):
                self._request_candle(tf_s)
                continue
            c = state.candle(tf_s)
            if c:
                self.hub.broadcast(
                    {"type": "candle", "symbol": symbol, "tf": tf, "data": c}, symbol=symbol, tf=tf
                )

    def _request_candle(self, tf_s: int) -> None:
        """Bougie en cours inconnue pour ce TF : chargée hors boucle, puis suivie par `state.apply`."""
        if tf_s in self._loading_candles:
            return
        self._loading_candles.add(tf_s)
        if self.live or self._candle_loader is None:
            self.state.set_candle(tf_s, None)
            self._loading_candles.discard(tf_s)
            return
        gen, symbol, cursor, loader = self._generation, self.symbol, self.clock.cursor, self._candle_loader

        async def load() -> None:
            try:
                candle = await asyncio.to_thread(loader, symbol, tf_s, cursor)
            except Exception:  # noqa: BLE001
                log.exception("chargement bougie %ss", tf_s)
                candle = None
            if gen == self._generation and self.state is not None and not self.state.has_candle(tf_s):
                self.state.set_candle(tf_s, candle)
            self._loading_candles.discard(tf_s)

        asyncio.create_task(load())

    def snapshot_payload(self, symbol: str, marks: list[dict], positions: list[dict], account: dict) -> dict:
        state = self.state
        if state is not None and symbol == self.symbol:
            dom = state.dom_payload(self.clock.cursor)
            data = {
                "symbol": symbol,
                "seq": state.seq,
                "cursor": self.clock.cursor,
                "trades": list(state.recent)[-2000:],
                "marks": marks,
                "delta_minutes": state.delta,
                "stats": state.stats_payload(),
                "dom": dom,
            }
        else:
            data = {
                "symbol": symbol,
                "seq": 0,
                "cursor": 0.0,
                "trades": [],
                "marks": [],
                "delta_minutes": [],
                "stats": {"cvd": 0, "buys": 0, "sells": 0, "total": 0, "big_threshold": 50},
                "dom": None,
            }
        data["positions"] = positions
        data["account"] = account
        data["status"] = self.status_payload()
        return {"type": "snapshot", "symbol": symbol, "data": data}
