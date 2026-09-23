"""Les nombres non finis sont rejetés avant d'atteindre le moteur et le compte."""

import pytest
from pydantic import ValidationError

from app.schemas.paper import BreakevenRequest
from app.schemas.replay import LoadRequest, SpeedRequest


@pytest.mark.parametrize("value", ["Infinity", "-Infinity", "NaN"])
def test_replay_and_breakeven_reject_non_finite_values(value):
    for model, payload in [
        (LoadRequest, {"symbol": "NQ", "start_ts": value}),
        (LoadRequest, {"symbol": "NQ", "start_ts": 1789743600, "speed": value}),
        (SpeedRequest, {"speed": value}),
        (BreakevenRequest, {"offset_ticks": value}),
    ]:
        with pytest.raises(ValidationError):
            model(**payload)
