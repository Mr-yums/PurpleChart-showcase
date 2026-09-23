"""API HTTP + WebSocket de bout en bout sur la mini-archive (TestClient Starlette)."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import AppConfig, DataConfig, ReplayConfig
from app.main import create_app


@pytest.fixture()
def client(archive, gex_db, tmp_path):
    cfg = AppConfig(
        data=DataConfig(data_dir=tmp_path, archive_path=archive["path"], gex_path=gex_db),
        replay=ReplayConfig(tick_seconds=0.05, chunk=500, min_symbol_rows=10, dom_every_ticks=2),
    )
    app = create_app(cfg)
    with TestClient(app) as c:
        yield c


def test_health_instruments_sessions_and_status(client, archive):
    assert client.get("/api/health").json()["archive"] == "ok"
    inst = client.get("/api/market/instruments").json()
    assert inst["instruments"][0]["symbol"] == "NQ" and "5m" in inst["timeframes"]
    sessions = client.get("/api/replay/sessions").json()["sessions"]
    assert (
        len(sessions) == 1
        and sessions[0]["date"] == "2026-08-27"
        and sessions[0]["first_ts"] == archive["session_start"]
    )
    st = client.get("/api/replay/status").json()
    assert st["loaded"] is False and st["clients"] == 0
    assert client.post("/api/replay/play").status_code == 409
    assert client.post("/api/replay/load", json={"symbol": "ZZ", "start_ts": 1}).status_code == 422
    assert client.get("/api/replay/regimes").json()["ok"] is False


def test_load_candles_events_and_paper_over_http(client, archive):
    r = client.post(
        "/api/replay/load", json={"symbol": "NQ", "start_ts": archive["t0"] + 700, "speed": 3}
    ).json()
    assert r["ok"] and r["speed"] == 3
    st = client.get("/api/replay/status").json()
    assert (
        st["loaded"] and st["symbol"] == "NQ" and not st["playing"] and st["cursor_ts"] == archive["t0"] + 700
    )
    cd = client.get("/api/market/candles", params={"symbol": "NQ", "tf": "1m", "n": 50}).json()
    assert cd["count"] > 5 and cd["candles"][-1]["time"] <= st["cursor_ts"]
    ev = client.get("/api/market/events", params={"symbol": "NQ", "from": 0, "to": 9e9, "limit": 100}).json()
    assert ev["returned"] and all(e["t"] <= st["cursor_ts"] for e in ev["big_prints"])
    assert client.get("/api/market/recorded-trades").status_code == 404
    assert client.post("/api/replay/speed", json={"speed": 999}).json()["speed"] == 50
    assert client.post("/api/replay/play").json()["playing"] is True
    assert client.post("/api/replay/pause").json()["playing"] is False
    tk = client.get("/api/paper/ticket", params={"symbol": "NQ"}).json()
    assert tk["tick_value"] == 5.0 and tk["dry_run"] is True
    px = client.get("/api/market/candles", params={"symbol": "NQ", "tf": "15s", "n": 10}).json()["candles"][
        -1
    ]["close"]
    p = client.post(
        "/api/paper/place",
        json={"symbol": "NQ", "side": "buy", "size": 1, "sl_price": px - 3, "tp_price": px + 6},
    ).json()
    assert p["ok"] and p["sl_points"] == 3.0
    assert (
        client.post("/api/paper/place", json={"symbol": "NQ", "side": "sell", "size": 1}).status_code == 409
    )
    assert client.get("/api/paper/positions").json()["positions"][0]["side"] == "LONG"
    assert client.post("/api/paper/modify", json={"which": "sl", "price": px - 2}).json()["price"] == px - 2
    assert client.post("/api/paper/flatten").json()["closed"] is True
    assert client.get("/api/paper/account").json()["account"]["fees_total"] == 3.78
    assert client.post("/api/edge/tag", json={"symbol": "NQ", "tag": "figure"}).json()["tag"] == "FIGURE"
    assert client.get("/api/edge/sticky", params={"symbol": "NQ"}).json()["tag"] == "FIGURE"
    assert client.post("/api/edge/tag", json={"symbol": "NQ", "tag": "nope"}).json()["ok"] is False
    assert client.get("/api/edge/journal").json()["trades"][0]["reason"] == "flatten"
    assert client.get("/api/edge/stats").json()["total_trades"] == 1
    assert client.get("/api/edge/gex-stats").json()["ok"]
    j = client.get("/api/journal", params={"all": 1}).json()
    assert j["overall"]["count"] == 1 and all(t["source"] == "replay" for t in j["trades"])
    assert client.get("/api/journal/demo-trades").json()["trades"][0]["source"] == "replay"
    assert client.post("/api/journal/sessions/save", json={"label": "x"}).json()["ok"]
    assert client.get("/api/journal/sessions").json()["aggregate"]["sessions"] == 1
    g = client.get("/api/gex/levels", params={"symbol": "NQ", "from": 0, "to": 9e9}).json()
    assert g["count"] == 1 and g["levels"][-1]["regime"] == "EXPANSION" and g["stale"] is False
    assert client.get("/api/gex/vanna", params={"symbol": "NDX"}).json() is None
    absent = client.get("/api/gex/vanna", params={"symbol": "SPX"})
    assert (
        absent.status_code == 200 and absent.json() is None
    )  # [Sol] Expected absence is not an HTTP failure.
    assert client.post("/api/paper/reset").json()["ok"]


def test_websocket_snapshot_status_and_resubscribe(client, archive):
    client.post("/api/replay/load", json={"symbol": "NQ", "start_ts": archive["t0"] + 300, "speed": 1})
    with client.websocket_connect("/ws?symbol=NQ&tf=5m") as ws:
        snap = ws.receive_json()
        assert (
            snap["type"] == "snapshot"
            and snap["data"]["status"]["loaded"]
            and snap["data"]["dom"]["last"] > 0
        )
        assert snap["data"]["marks"] and snap["data"]["account"]["balance"] == 50000
        client.post("/api/replay/speed", json={"speed": 50})
        client.post("/api/replay/play")
        kinds = set()
        for _ in range(40):
            m = ws.receive_json()
            kinds.add(m["type"])
            if {"tape", "dom", "status"} <= kinds:
                break
        assert {"tape", "dom", "status"} <= kinds
        client.post(
            "/api/replay/pause"
        )  # stoppe le flot avant le ré-abonnement (le TestClient tamponne sans limite)
        ws.send_json({"symbol": "NQ", "tf": "1m"})
        for _ in range(3000):
            m = ws.receive_json()
            if m["type"] == "snapshot":
                break
        assert m["type"] == "snapshot"
        ws.send_json({"symbol": "NQ", "tf": "bad"})
        for _ in range(3000):
            m = ws.receive_json()
            if m["type"] == "error":
                break
        assert m["type"] == "error"
    client.post("/api/replay/pause")
