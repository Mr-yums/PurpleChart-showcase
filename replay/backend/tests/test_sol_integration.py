"""[Sol] Regression proofs: deterministic fills, bounded prefetch, restart and archives."""

import time

import pytest

from app.bootstrap import build_container
from app.core.config import AppConfig, DataConfig, ReplayConfig
from app.domain.instruments import instrument_for
from app.domain.paper.book import PaperBook
from app.domain.replay.regimes import RegimeClassifier
from app.domain.replay.sources import ArchiveSource
from app.domain.replay.state import SessionState
from app.infra.hub import Hub
from app.services.replay_engine import ReplayEngine


async def run_speed(speed):
    book = PaperBook(
        starting_balance=50000, account_name="test", max_contracts=20, min_bracket_ticks=4, default_risk=250
    )
    book.place(symbol="NQ", side="buy", size=1, sl=99, tp=101, fill=100, cursor=0, wall=0)
    results = []

    class Listener:
        async def on_prices(self, lo, hi, last, cursor):
            result = book.check_stops(lo, hi, last, cursor, 0)
            if result:
                results.append((result.reason, result.pnl_net, result.cursor))

    class Source:
        def __init__(self):
            self.rows = [
                dict(t=0.1, price=101, volume=1, side="buy"),
                dict(t=0.4, price=99, volume=1, side="sell"),
            ]

        buffering = False

        def take_until(self, t):
            rows = [r for r in self.rows if r["t"] <= t]
            self.rows = [r for r in self.rows if r["t"] > t]
            return rows

        def next_time(self):
            return self.rows[0]["t"] if self.rows else None

        @property
        def exhausted(self):
            return not self.rows

        def stop(self):
            pass

    engine = ReplayEngine(ReplayConfig(), Hub(), listener=Listener())
    await engine.start_archive("NQ", SessionState("NQ", instrument_for("NQ")), Source(), 0, speed, 0)
    await engine.stop_loop()
    engine.play()
    for _ in range(10):
        await engine.step()
    await engine.stop()
    return results


@pytest.mark.asyncio
async def test_same_fills_at_every_speed():
    baseline = await run_speed(0.5)
    assert baseline == [("tp", 16.22, 0.1)]
    for speed in [1, 2, 5, 10, 25, 50]:
        assert await run_speed(speed) == baseline


def test_bounded_reader_without_consumption():
    fetched = []

    def fetch(t):
        fetched.append(t)
        if t >= 100000:
            return []
        return [dict(t=t + i + 1) for i in range(1000)]

    src = ArchiveSource(fetch, 0, prefetch_chunks=1)
    try:
        for _ in range(50):
            time.sleep(0.001)
            assert src.pending <= 1000
        assert len(fetched) <= 3
        collected = []
        for _ in range(200):
            collected += src.take_until(100000)
            if src.exhausted:
                break
            time.sleep(0.001)
        assert [r["t"] for r in collected] == list(range(1, 100001))
    finally:
        src.stop()


@pytest.mark.asyncio
async def test_checkpoint_restores_paused_account_and_position(archive, tmp_path):
    cfg = AppConfig(
        data=DataConfig(data_dir=tmp_path, archive_path=archive["path"]),
        replay=ReplayConfig(min_symbol_rows=1),
    )
    c = build_container(cfg)
    await c.replay.load("NQ", archive["t0"] + 120, 5)
    fill = c.engine.last_price
    await c.paper.place("NQ", "buy", 1, fill - 10, fill + 20, fill, None)
    c.paper.book.realized_pnl = 37.25
    c.paper.book.realized_fees = 3.78
    cursor = c.engine.cursor
    await c.replay.shutdown()
    await c.hub.close_all()
    reopened = build_container(cfg)
    await reopened.replay.resume()
    assert not reopened.engine.clock.playing
    assert reopened.engine.cursor == cursor
    assert reopened.paper.book.position.entry == fill
    assert reopened.paper.book.realized_pnl == 37.25
    assert reopened.paper.book.realized_fees == 3.78
    await reopened.replay.shutdown()
    await reopened.hub.close_all()


@pytest.mark.asyncio
async def test_wrong_symbol_fill_is_rejected(archive, tmp_path):
    cfg = AppConfig(
        data=DataConfig(data_dir=tmp_path, archive_path=archive["path"]),
        replay=ReplayConfig(min_symbol_rows=1),
    )
    c = build_container(cfg)
    await c.replay.load("NQ", archive["t0"] + 120, 5)
    with pytest.raises(Exception, match="symbole"):
        await c.paper.place("MGC", "buy", 1, None, None, 123, None)
    assert c.paper.book.position is None
    await c.replay.shutdown()


def test_catalogue_keeps_direction_and_range():
    up = [[i * 300, 100 + i * 5, 105 + i * 5, 95 + i * 5, 100 + i * 5] for i in range(96)]
    down = [[i * 300, 1000 - i * 5, 1005 - i * 5, 995 - i * 5, 1000 - i * 5] for i in range(96)]
    flat = [[i * 300, 100, 101, 99, 100 + (-1) ** i] for i in range(96)]
    assert {s["classe"] for s in RegimeClassifier.classify(up, 1)} == {"DIR_UP"}
    assert {s["classe"] for s in RegimeClassifier.classify(down, 1)} == {"DIR_DOWN"}
    assert {s["classe"] for s in RegimeClassifier.classify(flat, 1)} == {"RANGE"}
