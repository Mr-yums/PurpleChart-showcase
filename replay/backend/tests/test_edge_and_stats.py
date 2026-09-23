"""Régime, contexte d'entrée, cohérence des tags, GEX/vanna et agrégats de journal."""

import pytest

from app.domain.edge.context import coherence, entry_context, gex_vanna_context, normalize_tag
from app.domain.edge.regime import closes_from_ticks, regime_from_ticks, window_class
from app.domain.journal.stats import compute_stats, group_stats


def test_window_class():
    assert window_class([100, 110, 120, 131, 140], 1.0) == "DIR_UP"
    assert window_class([100, 90, 80, 70, 60], 1.0) == "DIR_DOWN"
    assert window_class([100, 101, 100, 101, 100], 1.0) == "RANGE"
    assert window_class([100, 120, 105, 125, 118], 1.0) == "BATARD"
    assert window_class([100], 1.0) == "UNKNOWN"


def test_regime_from_ticks_uses_bucket_closes():
    rows = [(0, 100), (0, 101), (300, 110), (300, 111), (600, 120), (900, 131), (1200, 140), (1200, 141)]
    assert closes_from_ticks(rows) == [101, 111, 120, 131, 141]
    assert regime_from_ticks("NQ", rows) == "DIR_UP"
    assert regime_from_ticks("NQ", rows[:3]) == "UNKNOWN"


def test_entry_context_keeps_standard_poc_without_private_setup():
    ctx = entry_context([(100, 50, 40), (101, 1, 2)], [], 100, 0.25)
    assert ctx["poc"] == 100 and ctx["poc_dist"] == 0
    assert ctx["absorb"] is None and ctx["setup"] == "NONE"
    assert coherence("VP", ctx) == ""


def test_gex_vanna_context_and_tags():
    ctx = gex_vanna_context((5.0, 105.0, 95.0, 101.0), ("BULL", 100.0), 100.0)
    assert ctx == {
        "gex_regime": "RANGE",
        "vanna_regime": "BULL",
        "above_flip": "BELOW",
        "dist_to_flip": -1.0,
        "dist_to_wall": 5.0,
    }
    assert gex_vanna_context(None, None, 1.0)["gex_regime"] is None
    assert normalize_tag(" vp ") == "VP" and normalize_tag("none") is None and normalize_tag("") is None
    with pytest.raises(ValueError):
        normalize_tag("FOO")


def test_compute_stats_and_groups():
    trades = [
        {"symbol": "NQ", "pnl": 100, "size": 1, "fees": 3.78},
        {"symbol": "NQ", "pnl": -50, "size": 2},
        {"symbol": "NQ", "pnl": 0, "size": 1, "source": "real"},
    ]
    s = compute_stats(trades)
    assert s["count"] == 3 and s["wins"] == 1 and s["losses"] == 1 and s["scratches"] == 1
    assert s["profit_factor"] == 2.0 and s["total_fees"] == 3.78 + 7.56 and s["total_pnl_net"] == 50 - 11.34
    assert compute_stats([{"pnl": 10}])["profit_factor_inf"] is True and compute_stats([])["win_rate"] == 0.0
    g = group_stats(
        [("A", "RANGE", 10, 1.0), ("A", "RANGE", -5, -0.5), (None, "DIR_UP", 3, None)],
        ("entry_tag", "regime"),
    )
    a = next(x for x in g if x["entry_tag"] == "A")
    assert a["n"] == 2 and a["winrate"] == 50.0 and a["avg_r"] == 0.25 and a["profit_factor"] == 2.0
    assert next(x for x in g if x["entry_tag"] == "NA")["avg_r"] is None
