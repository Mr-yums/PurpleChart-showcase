import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.test_engine_and_services import make_config


def test_visitors_have_independent_replays_and_journals(archive, gex_db, tmp_path, monkeypatch):
    monkeypatch.setenv("PR_VISITOR_WORKSPACES", "1")
    app = create_app(make_config(tmp_path, archive["path"], gex_db))
    with TestClient(app) as client:
        assert not client.get("/api/replay/status").json()["loaded"]
        alice = client.cookies.get("pr_workspace")
        client.post(
            "/api/replay/load", json={"symbol": "NQ", "start_ts": archive["t0"] + 700, "speed": 1}
        ).raise_for_status()
        client.post("/api/edge/tag", json={"symbol": "NQ", "tag": "figure"}).raise_for_status()
        client.cookies.clear()
        assert not client.get("/api/replay/status").json()["loaded"]
        bob = client.cookies.get("pr_workspace")
        assert alice != bob
        assert client.get("/api/edge/sticky?symbol=NQ").json()["tag"] is None
        assert client.get("/api/edge/journal").json()["trades"] == []
        client.cookies.set("pr_workspace", alice)
        assert client.get("/api/replay/status").json()["loaded"]
        assert client.get("/api/edge/sticky?symbol=NQ").json()["tag"] == "FIGURE"
        assert client.post("/api/replay/live", json={"symbol": "NQ"}).status_code == 404
        assert client.get("/api/gex/vanna").json() is None
        assert (
            client.post("/api/replay/play", headers={"origin": "https://external.example"}).status_code == 403
        )


def test_gamma_projects_at_snapshot_without_future_prices(archive, gex_db, tmp_path):
    from app.bootstrap import build_container

    c = build_container(make_config(tmp_path, archive["path"], gex_db))
    when = archive["t0"] + 600
    levels, _ = c.gex._levels_blocking("NQ", 0, when)
    last = levels[-1]
    anchor = c.archive.last_trade_before("NQ", when)[0]
    assert last["time"] == when
    assert last["spot"] == anchor
    assert abs(last["spot"] * (1 + last["cw_d"]) - anchor * 512 / 502) < 1e-8
    assert last["time"] <= when


@pytest.mark.asyncio
async def test_switching_archives_invalidates_market_cache(archive, tmp_path):
    import shutil
    import sqlite3

    from app.bootstrap import build_container

    modern = tmp_path / "modern.sqlite"
    shutil.copy2(archive["path"], modern)
    with sqlite3.connect(modern) as db:
        db.execute("UPDATE tape_trades SET price=price+1000")
    cfg = make_config(tmp_path, archive["path"])
    cfg.data.modern_archive_path = modern
    container = build_container(cfg)
    cursor = archive["t0"] + 700
    try:
        await container.replay.load("NQ", cursor, 1, "legacy")
        legacy = await container.market.candles("NQ", "1m", 20)
        await container.replay.load("NQ", cursor, 1, "v2")
        recent = await container.market.candles("NQ", "1m", 20)
        assert recent[-1]["close"] == legacy[-1]["close"] + 1000
        await container.replay.load("NQ", cursor, 1, "legacy")
        assert await container.market.candles("NQ", "1m", 20) == legacy
    finally:
        await container.replay.shutdown()


def test_public_headers_and_host_boundary(archive, tmp_path, monkeypatch):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>Public replay</html>")
    monkeypatch.setenv("PR_WEB_DIR", str(web))
    monkeypatch.setenv("PR_VISITOR_WORKSPACES", "1")
    app = create_app(make_config(tmp_path, archive["path"]))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "connect-src 'self'" in response.headers["content-security-policy"]
        assert client.get("/api/health", headers={"host": "outside.invalid"}).status_code == 400
        assert client.post("/api/replay/live", json={"symbol": "NQ"}).status_code in (404, 405)
        # The fixture deliberately includes fictitious broker trades: none may leak.
        journal = client.get("/api/journal?all=1").json()
        assert journal["trades"] == []
        assert set(journal["per_source"]) == {"replay"}
        assert client.get("/api/market/recorded-trades").status_code == 404
