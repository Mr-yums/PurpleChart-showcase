"""Moteur + services sur une mini-archive : chargement, trames, anti-spoiler, fin de données, paper via le hub."""

import asyncio
import time

import pytest

from app.bootstrap import build_container
from app.core.config import AppConfig, DataConfig, PaperConfig, ReplayConfig


class FakeWS:
    def __init__(self):
        self.sent = []
        self.closed = False

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self, code=1000):
        self.closed = True

    def of(self, kind):
        return [m for m in self.sent if m.get("type") == kind]


def make_config(tmp_path, archive_path, gex_path=None):
    data = DataConfig(data_dir=tmp_path, archive_path=archive_path, gex_path=gex_path)
    return AppConfig(
        data=data,
        replay=ReplayConfig(
            tick_seconds=0.01,
            chunk=500,
            prefetch_chunks=2,
            min_symbol_rows=10,
            tape_batch_cap=50,
            dom_every_ticks=2,
            candle_every_ticks=2,
        ),
        paper=PaperConfig(pnl_sample_seconds=1.0),
    )


async def wait_for(pred, timeout=3.0):
    deadline = time.time() + timeout
    while not pred():
        if time.time() > deadline:
            raise AssertionError("délai dépassé")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_load_step_frames_and_end_of_data(archive, tmp_path):
    c = build_container(make_config(tmp_path, archive["path"]))
    ws = FakeWS()
    await c.replay.subscribe(ws, "NQ", "1m")
    await asyncio.sleep(0.02)
    snap = ws.of("snapshot")[0]["data"]
    assert snap["seq"] == 0 and snap["trades"] == [] and snap["status"]["loaded"] is False
    start = archive["t0"] + 600
    res = await c.replay.load("NQ", start, 50)
    assert res["ok"] and res["speed"] == 50 and c.engine.context_start == archive["session_start"]
    await c.engine.stop_loop()  # on pilote la boucle à la main
    engine = c.engine
    assert engine.loaded and engine.state.stats["total"] == 200 + 601 and engine.last_price is not None
    await wait_for(lambda: not engine.source.buffering)
    engine.play()
    ws.sent.clear()
    engine.hub.add(ws, "NQ", "1m")
    engine.hub.prime(ws, {"type": "snapshot"})
    for _ in range(8):
        await engine.step()
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)
    tape = ws.of("tape")
    assert tape and tape[0]["data"]["trades"][0]["seq"] == 1
    assert all(t["t"] <= engine.cursor for m in tape for t in m["data"]["trades"])
    assert ws.of("dom") and ws.of("status")
    await wait_for(lambda: engine.state.has_candle(60))
    for _ in range(4):
        await engine.step()
    await asyncio.sleep(0.05)
    candles = ws.of("candle")
    assert (
        candles and candles[-1]["tf"] == "1m" and candles[-1]["data"]["time"] == int(engine.cursor // 60) * 60
    )
    # anti-spoiler : bougies et marques plafonnées au curseur
    rows = await c.market.candles("NQ", "1m", 200)
    assert rows[-1]["time"] <= engine.cursor and rows[0]["time"] >= archive["session_start"]
    ev = await c.market.events("NQ", 0, time.time(), 500)
    assert ev["big_prints"] and max(e["t"] for e in ev["big_prints"]) <= engine.cursor
    # fin des données : le curseur avale le reste (cadence x50)
    engine.set_speed(50)
    for _ in range(6000):
        await engine.step()
        if engine.clock.ended:
            break
        await asyncio.sleep(0)
    assert engine.clock.ended and not engine.clock.playing and engine.source.exhausted
    assert engine.state.stats["total"] == 200 + archive["n"]


@pytest.mark.asyncio
async def test_candle_cache_is_incremental_and_invalidated(archive, tmp_path):
    c = build_container(make_config(tmp_path, archive["path"]))
    await c.replay.load("NQ", archive["t0"] + 900, 1)
    await c.engine.stop_loop()
    first = await c.market.candles("NQ", "5m", 100)
    assert [x["time"] for x in first] == [
        archive["t0"],
        archive["t0"] + 300,
        archive["t0"] + 600,
        archive["t0"] + 900,
    ]
    key = ("NQ", 300)
    assert c.market._candles[key].until == archive["t0"] + 900 and len(c.market._candles[key].candles) == 3
    c.engine.clock.jump(archive["t0"] + 1300)
    again = await c.market.candles("NQ", "5m", 100)
    assert again[-1]["time"] == archive["t0"] + 1200 and len(c.market._candles[key].candles) == 4
    await c.replay.load("NQ", archive["t0"] + 100, 1)  # retour en arrière -> cache invalidé
    await c.engine.stop_loop()
    back = await c.market.candles("NQ", "5m", 100)
    assert back[-1]["time"] == archive["t0"] and len(c.market._candles[key].candles) == 0


@pytest.mark.asyncio
async def test_paper_lifecycle_through_engine(archive, tmp_path, gex_db):
    c = build_container(make_config(tmp_path, archive["path"], gex_db))
    ws = FakeWS()
    c.hub.add(ws, "NQ", "5m")
    c.hub.prime(ws, {"type": "snapshot"})
    with pytest.raises(Exception):
        await c.paper.place("NQ", "buy", 1, None, None, None, None)
    await c.replay.load("NQ", archive["t0"] + 1200, 10)
    await c.engine.stop_loop()
    engine = c.engine
    px = engine.last_price
    c.edge.set_tag("NQ", "vp")
    res = await c.paper.place("NQ", "buy", 2, px - 0.5, px + 0.5, None, None)
    assert (
        res["ok"]
        and res["fill"] == px
        and res["entry_tag"] == "VP"
        and res["regime"] in ("RANGE", "BATARD", "DIR_UP", "DIR_DOWN", "UNKNOWN")
    )
    pos = c.paper.positions()[0]
    assert pos["size"] == 2 and pos["sl"] == px - 0.5 and pos["regime"] == res["regime"]
    await wait_for(lambda: not engine.source.buffering)
    engine.play()
    for _ in range(300):
        await engine.step()
        await asyncio.sleep(0)
        if c.paper.book.position is None:
            break
    assert c.paper.book.position is None, "le SL ou le TP doit être touché en rejouant"
    await asyncio.sleep(0.1)
    acct = c.paper.account()
    assert acct["fees_total"] == 7.56 and acct["balance"] != 50000
    frames = ws.of("positions")
    assert frames and frames[-1]["data"]["positions"] == []
    demo = c.config.data.demo_trades.read_text(encoding="utf-8").strip().splitlines()
    assert len(demo) == 1 and '"reason"' in demo[0]
    j = await c.edge.journal(10)
    row = j["trades"][0]
    assert (
        row["entry_tag"] == "VP"
        and row["result_r"] is not None
        and row["gex_regime"] in ("RANGE", "EXPANSION")
    )
    assert row["mfe_usd"] is not None and row["fees"] == 7.56
    st = await c.edge.stats()
    assert st["total_trades"] == 1 and st["groups"][0]["entry_tag"] == "VP"
    u = await c.journal.unified(0, True)
    assert u["per_source"]["replay"]["count"] == 1 and set(u["per_source"]) == {"replay"}
    saved = await c.journal.session_save("test")
    assert saved["ok"] and saved["session"]["count"] == 1
    lst = await c.journal.session_list()
    assert lst["aggregate"]["sessions"] == 1 and lst["pending"]["count"] == 0
    assert (await c.journal.session_save(""))["ok"] is False


@pytest.mark.asyncio
async def test_breakeven_partial_modify_flatten_and_reset(archive, tmp_path):
    c = build_container(make_config(tmp_path, archive["path"]))
    await c.replay.load("NQ", archive["t0"] + 60, 1)
    await c.engine.stop_loop()
    px = c.engine.last_price
    await c.paper.place("NQ", "sell", 3, px + 5, None, None, None)
    from app.core.exceptions import ConflictError

    with pytest.raises(ConflictError):
        await c.paper.breakeven()
    c.engine.state.last_price = px - 2
    be = await c.paper.breakeven(1)
    assert be["sl"] == px - 0.25
    part = await c.paper.partial_close(1)
    assert part["remaining"] == 2 and part["pnl"] == 40.0
    mod = await c.paper.modify("tp", px - 10.1)
    assert mod["price"] == px - 10.0
    flat = await c.paper.flatten()
    assert flat["closed"] and flat["pnl"] == 80.0
    await asyncio.sleep(0.05)
    assert c.paper.account()["realized_net"] == pytest.approx(120 - 3 * 3.78)
    assert (await c.paper.reset())["account"]["balance"] == 50000
    gex = await c.gex.levels("NQ", 0, time.time())
    assert gex["count"] == 0 and gex["stale"] is False
