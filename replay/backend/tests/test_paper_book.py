"""Carnet paper : fills, agrégation, SL/TP sur intervalle, BE gardé, partiel, frais, R."""

import pytest

from app.core.exceptions import ConflictError, ValidationError
from app.domain.paper.book import PaperBook


def book():
    return PaperBook(
        starting_balance=50000,
        account_name="50K Practice",
        max_contracts=20,
        min_bracket_ticks=4,
        default_risk=250,
    )


def test_place_snaps_validates_and_aggregates():
    b = book()
    p = b.place(symbol="NQ", side="buy", size=2, sl=99.0, tp=103.1, fill=100.12, cursor=10, wall=20)
    assert p.side == "LONG" and p.entry == 100.0 and p.sl == 99.0 and p.tp == 103.0 and p.sl_orig == 99.0
    p2 = b.place(symbol="NQ", side="buy", size=2, sl=None, tp=None, fill=101.0, cursor=11, wall=21)
    assert p2 is p and p.size == 4 and p.entry == 100.5
    with pytest.raises(ConflictError):
        b.place(symbol="NQ", side="sell", size=1, sl=None, tp=None, fill=101.0, cursor=12, wall=22)
    with pytest.raises(ValidationError):
        book().place(symbol="NQ", side="buy", size=1, sl=101.0, tp=None, fill=100.0, cursor=1, wall=1)
    with pytest.raises(ValidationError):
        book().place(symbol="NQ", side="buy", size=99, sl=None, tp=None, fill=100.0, cursor=1, wall=1)


def test_stop_hit_on_wick_within_same_batch_and_sl_has_priority():
    b = book()
    b.place(symbol="NQ", side="buy", size=1, sl=99.0, tp=101.0, fill=100.0, cursor=1, wall=1)
    assert b.check_stops(lo=99.5, hi=100.5, last=100.2, cursor=2, wall=2) is None
    close = b.check_stops(lo=98.9, hi=101.2, last=100.5, cursor=3, wall=3)
    assert close.reason == "sl" and close.exit == 99.0 and close.pnl == -20.0 and close.fees == 3.78
    assert close.pnl_net == -23.78 and b.position is None
    assert b.account_payload()["balance"] == 50000 - 23.78 and b.account_payload()["fees_total"] == 3.78


def test_short_take_profit_and_partial_close():
    b = book()
    b.place(symbol="US100.cash", side="sell", size=3, sl=101.0, tp=98.0, fill=100.0, cursor=1, wall=1)
    close = b.partial(2, exit_price=99.0, cursor=2, wall=2)
    assert close.reason == "partial" and close.size_closed == 2 and close.pnl == 4.0 and close.fees == 2.44
    assert b.position.size == 1
    tp = b.check_stops(lo=97.9, hi=99.5, last=98.5, cursor=3, wall=3)
    assert tp.reason == "tp" and tp.exit == 98.0 and tp.pnl == 4.0 and b.position is None
    assert b.realized_pnl == pytest.approx(8.0 - 2.44 - 1.22)


def test_breakeven_requires_profit_and_freezes_original_stop():
    b = book()
    b.place(symbol="NQ", side="buy", size=1, sl=99.0, tp=None, fill=100.0, cursor=1, wall=1)
    with pytest.raises(ConflictError):
        b.breakeven(100.2)
    assert b.breakeven(100.5, offset_ticks=1) == 100.25 and b.position.sl_orig == 99.0
    assert b.modify("tp", 102.1) == 102.0 and b.position.tp == 102.0
    assert b.positions_payload(101.0)[0]["pnl"] == 20.0
    assert b.position.risk_usd(20.0) == 20.0


def test_flatten_and_reset():
    b = book()
    assert b.flatten(None, 0, 0) is None
    b.place(symbol="NQ", side="buy", size=1, sl=None, tp=None, fill=100.0, cursor=1, wall=1)
    close = b.flatten(100.5, 2, 2)
    assert close.reason == "flatten" and close.pnl == 10.0
    b.reset()
    assert b.realized_pnl == 0 and b.position is None and b.ticket_spec("NQ")["tick_value"] == 5.0


def test_sample_tracks_mae_mfe_and_throttles():
    b = book()
    b.place(symbol="NQ", side="buy", size=1, sl=99.0, tp=None, fill=100.0, cursor=1, wall=1)
    s1 = b.sample(99.5, cursor=1.0, min_gap=3)
    assert s1["unrealized_pnl"] == -10.0 and s1["unrealized_r"] == -0.5
    assert b.sample(100.5, cursor=2.0, min_gap=3) is None
    assert b.position.mfe_usd == 10.0 and b.position.mae_usd == -10.0
    assert b.sample(100.5, cursor=4.5, min_gap=3)["unrealized_pnl"] == 10.0
