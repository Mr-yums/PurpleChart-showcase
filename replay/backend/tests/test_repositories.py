"""Repositories : archive (lots, évènements, contexte, bougies, séances), GEX, edge journal, JSONL."""

from pathlib import Path

from app.core.time import to_iso_z
from app.repositories.archive_repository import ArchiveRepository
from app.repositories.edge_journal_repository import TRADE_COLUMN_NAMES, EdgeJournalRepository
from app.repositories.gex_repository import GexRepository
from app.repositories.jsonl_repository import JsonFileRepository, JsonlRepository


def test_archive_symbols_range_and_chunks(archive):
    repo = ArchiveRepository(archive["path"])
    assert repo.symbols(min_rows=100) == ["NQ"] and repo.symbols(min_rows=10**6) == []
    lo, hi = repo.time_range("NQ")
    assert lo == archive["session_start"] and hi == archive["t1"] and repo.max_time("NQ") == hi
    rows = repo.trades_after("NQ", archive["t0"] - 0.5, 100)
    assert len(rows) == 100 and rows[0][0] == archive["t0"] and rows[0][5] == "buy"
    assert repo.trades_after("NQ", hi, 100) == []
    events = repo.events_between("NQ", archive["t0"], archive["t0"] + 300)
    assert {e[1] for e in events} == {"block", "sweep", "absorb"}
    hist = repo.events_history("NQ", archive["t0"], archive["t0"] + 1000, limit=3)
    assert (
        len(hist) == 3 and hist[0]["t"] < hist[-1]["t"] and hist[-1]["volume"] == hist[-1]["trigger_volume"]
    )


def test_archive_context_candles_and_sessions(archive):
    repo = ArchiveRepository(archive["path"])
    t0 = archive["t0"]
    prof = repo.profile("NQ", archive["session_start"], t0)
    assert (
        len(prof) == 11 and sum(r[1] + r[2] for r in prof) == 441
    )  # bornes inclusives : le trade en t0 est amorcé
    assert repo.stats("NQ", archive["session_start"], t0)[2] == 201
    assert len(repo.delta_minutes("NQ", archive["session_start"], t0)) == 201
    assert len(repo.recent_volumes("NQ", t0, 50)) == 50
    assert repo.last_trade_before("NQ", t0)[2] == "buy"
    buckets = repo.candle_buckets("NQ", 300, t0, t0 + 899)
    assert [b[0] for b in buckets] == [t0, t0 + 300, t0 + 600] and buckets[0][3] > 0
    o, c = repo.open_close("NQ", buckets[0][4], buckets[0][5])
    assert o == 20000.25 and c > 0
    ticks = repo.bucket_ticks("NQ", 300, t0, t0 + 600)
    assert ticks[0][0] == t0 and len(ticks) == 600
    sess = repo.session_buckets("NQ", 0)
    assert len(sess) == 1 and sess[0][1] == archive["session_start"]


def test_gex_repository(gex_db, tmp_path):
    repo = GexRepository(gex_db)
    iso = to_iso_z(1787836200)  # 2026-08-27T13:10:00Z
    assert len(repo.levels_between(to_iso_z(0), iso)) == 2
    assert repo.last_level_before(to_iso_z(1787836000))[2] == 1.5
    assert repo.gex_context(iso) == (-0.7, 512.0, 492.0, 500.0)
    assert repo.last_vanna("NDX", iso) is None and repo.vanna_context(iso) is None
    missing = GexRepository(tmp_path / "nope.db")
    assert missing.levels_between("a", "b") == [] and missing.last_vanna("NDX", iso) is None


def test_edge_journal_migrates_legacy_schema(tmp_path: Path):
    import sqlite3

    path = tmp_path / "edge.sqlite"
    legacy = sqlite3.connect(str(path))
    legacy.execute(
        "CREATE TABLE paper_trades(id INTEGER PRIMARY KEY AUTOINCREMENT, ts_wall REAL, symbol TEXT, pnl REAL)"
    )
    legacy.execute("INSERT INTO paper_trades(ts_wall, symbol, pnl) VALUES (1, 'NQ', 12.5)")
    legacy.commit()
    legacy.close()
    repo = EdgeJournalRepository(path)
    repo.ensure_schema()
    cols = {r[1] for r in repo.conn.execute("PRAGMA table_info(paper_trades)")}
    assert set(TRADE_COLUMN_NAMES) <= cols
    rid = repo.insert_trade(
        {
            "ts_wall": 2,
            "symbol": "NQ",
            "pnl": -3,
            "result_r": -0.5,
            "entry_tag": "FIGURE",
            "regime": "RANGE",
            "gex_regime": "RANGE",
            "above_flip": "ABOVE",
            "side": "LONG",
            "mfe_usd": 4.0,
        }
    )
    assert rid == 2 and repo.count() == 2
    rows = repo.list_trades(10)
    assert rows[0]["id"] == 2 and rows[0]["mfe_usd"] == 4.0 and rows[1]["pnl"] == 12.5
    assert repo.tag_regime_rows()[1] == ("FIGURE", "RANGE", -3, -0.5)
    assert repo.gex_rows()[1][:3] == ("RANGE", "ABOVE", "LONG")
    repo.insert_sample(
        {
            "open_id": 1.0,
            "ts_wall": 1,
            "ts_market": 1,
            "mode": "replay",
            "symbol": "NQ",
            "side": "LONG",
            "size": 1,
            "entry": 1,
            "last_price": 2,
            "unrealized_pnl": 20,
            "unrealized_r": 1,
            "reason": "tick",
        }
    )
    assert repo.conn.execute("SELECT COUNT(*) FROM trade_pnl_live").fetchone()[0] == 1


def test_jsonl_and_json_files(tmp_path: Path):
    j = JsonlRepository(tmp_path / "sub" / "demo.jsonl")
    assert j.read_all() == []
    j.append({"a": 1})
    j.append({"b": 2})
    (tmp_path / "sub" / "demo.jsonl").open("a").write("not json\n")
    assert j.read_all() == [{"a": 1}, {"b": 2}]
    f = JsonFileRepository(tmp_path / "cache.json")
    assert f.read({"x": 0}) == {"x": 0}
    f.write({"symbols": {"NQ": 1}})
    assert f.read()["symbols"]["NQ"] == 1
