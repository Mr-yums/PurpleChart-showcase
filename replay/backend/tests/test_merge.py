"""Rattachement des marques orderflow aux trades (priorité des kinds, champs optionnels)."""

from app.domain.replay.merge import attach_events, index_events


def test_highest_priority_kind_wins_and_fields_are_attached():
    events = [
        ("a", "absorb", 10, 1.5, None, None, 0.2, 0.9, 80, "why"),
        ("a", "sweep", 12, 2.0, 3.0, 4, None, None, None, None),
        (None, "block", 1, 1, 1, 1, 1, 1, 1, "orphan"),
    ]
    kinds = index_events(events)
    assert kinds["a"][0] == "sweep" and None not in kinds
    rows = [
        (1.0, "a", "2026-08-27T13:00:00Z", 100.0, 3, "buy"),
        (2.0, "b", "2026-08-27T13:00:01Z", 100.25, 1, "sell"),
    ]
    trades = attach_events("NQ", rows, events)
    assert (
        trades[0]["kind"] == "sweep" and trades[0]["trigger_volume"] == 12 and trades[0]["lots_per_sec"] == 4
    )
    assert "dominance" not in trades[0] and "kind" not in trades[1]
    assert trades[1] == {
        "symbol": "NQ",
        "price": 100.25,
        "volume": 1,
        "timestamp": "2026-08-27T13:00:01Z",
        "t": 2.0,
        "side": "sell",
    }
