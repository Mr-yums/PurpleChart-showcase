import math

from app.domain.replay.volume_profile import volume_profile
from app.repositories.jsonl_repository import JsonFileRepository
from app.services.regimes_service import RegimesService


def test_volume_conservation_poc_and_contiguous_value_area():
    profile = volume_profile({100.0: 10, 101.0: 50, 102.0: 30, 104.0: 10}, 4)
    assert profile["bins"] == [10, 50, 30, 10]
    assert profile["volume"] == 100
    assert profile["poc"] == 101.5
    assert (profile["val"], profile["vah"]) == (101, 103)


def test_empty_single_price_and_invalid_volumes():
    assert volume_profile({}) is None
    assert volume_profile({1: 0, 2: -1, math.nan: 2, 3: math.inf}) is None
    profile = volume_profile({100: 75})
    assert profile["bins"] == [75]
    assert profile["low"] == profile["high"] == profile["poc"] == profile["val"] == profile["vah"] == 100


def test_catalogue_profiles_use_all_ticks_and_separate_hour_boundaries(tmp_path):
    class Archive:
        def symbols(self, minimum):
            return ["ES"]

        def calendar_days(self, symbol):
            return [(0,)]

        def bucket_ticks(self, symbol, step, start, end):
            return [(i * 300, 100 + i, 2) for i in range(24)] + [(7200, 200, 10)]

    service = RegimesService(JsonFileRepository(tmp_path / "regimes.json"), modern=Archive())
    day = service._build_modern()["ES"]["1970-01-01"]
    assert day["vp"]["volume"] == 58  # Includes incomplete hour, unlike regimes.
    assert len(day["segments"]) == 2
    assert [s["vp"]["volume"] for s in day["segments"]] == [24, 24]
    assert day["segments"][0]["vp"]["high"] == 111
    assert day["segments"][1]["vp"]["low"] == 112
