"""État de séance : profil, CVD, delta minute, bougies, seuil adaptatif, DOM synthétique."""

from app.domain.instruments import instrument_for
from app.domain.replay.state import SessionState


def trade(t, price, vol, side):
    return {"symbol": "NQ", "t": t, "timestamp": "x", "price": price, "volume": vol, "side": side}


def test_apply_accumulates_profile_cvd_delta_and_candles():
    s = SessionState("NQ", instrument_for("NQ"), ring=10, max_delta=5)
    s.set_candle(60, None)
    s.apply(trade(1000.0, 100.0, 5, "buy"))
    s.apply(trade(1010.0, 100.25, 3, "sell"))
    s.apply(trade(1070.0, 99.75, 2, "buy"))
    assert s.stats == {"cvd": 4, "buys": 7, "sells": 3, "total": 3}
    assert s.profile[100.0] == [5, 0] and s.profile[100.25] == [0, 3]
    assert s.session_low == 99.75 and s.session_high == 100.25
    assert [d["t"] for d in s.delta] == [960, 1020]
    assert s.delta[0]["delta"] == 2 and s.delta[0]["high"] == 100.25 and s.delta[0]["low"] == 100.0
    c = s.candle(60)
    assert c == {"time": 1020, "open": 99.75, "high": 99.75, "low": 99.75, "close": 99.75, "volume": 2.0}
    assert [tr["seq"] for tr in s.recent] == [1, 2, 3]


def test_candle_rollover_and_ring_cap():
    s = SessionState("NQ", instrument_for("NQ"), ring=3)
    s.set_candle(300, {"time": 900, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1})
    for i in range(6):
        s.apply(trade(1000 + i, 10 + i, 1, "buy"))
    assert len(s.recent) == 3 and s.recent[-1]["seq"] == 6
    c = s.candle(300)  # bougie amorcée depuis l'archive : l'open reste celui du seed
    assert c["time"] == 900 and c["open"] == 1 and c["high"] == 15 and c["close"] == 15 and c["volume"] == 7
    s.apply(trade(1200, 20, 1, "sell"))  # nouveau bucket -> nouvelle bougie
    assert s.candle(300) == {"time": 1200, "open": 20, "high": 20, "low": 20, "close": 20, "volume": 1.0}


def test_delta_buckets_are_bounded():
    s = SessionState("NQ", instrument_for("NQ"), max_delta=3)
    for i in range(10):
        s.apply(trade(i * 60, 1, 1, "buy"))
    assert len(s.delta) == 3 and s.delta[-1]["t"] == 540


def test_big_threshold_reacts_to_volume_regime():
    s = SessionState("NQ", instrument_for("NQ"))
    base = s.big_threshold()
    for i in range(2000):
        s.apply(trade(i, 1, 200, "buy"))
    assert s.big_threshold() > base


def test_dom_payload_uses_last_side_and_profile():
    s = SessionState("US30.cash", instrument_for("US30.cash"))
    assert s.dom_payload(0) is None
    s.apply(trade(1, 100.0, 4, "sell"))
    s.apply(trade(2, 101.0, 6, "buy"))
    s.apply(trade(3, 100.0, 2, "sell"))
    dom = s.dom_payload(3)
    assert dom["last"] == 100.0 and dom["bid"] == 100.0 and dom["ask"] == 101.0
    assert dom["bids"] == [{"price": 100.0, "vol": 6}] and dom["asks"] == [{"price": 101.0, "vol": 6}]
    assert dom["profile"] == [[100.0, 6], [101.0, 6]] and dom["spread"] == 1 and dom["digits"] == 0
    assert dom["features"]["imbalance"] == 0.0


def test_seed_from_archive_rows():
    s = SessionState("NQ", instrument_for("NQ"))
    s.seed(
        profile_rows=[(100.0, 10, 4), (100.25, 0, 7)],
        stats_row=(10, 11, 5),
        delta_rows=[(960, 10, 11, 5, 100.25, 100.0)],
        volumes=[1, 2, 3],
        last_row=(100.25, 7, "sell"),
    )
    assert s.stats["cvd"] == -1 and s.session_high == 100.25 and s.last_side == "sell"
    assert s.delta[0]["delta"] == -1 and abs(s.vol_mean - 2.0) < 1e-9
