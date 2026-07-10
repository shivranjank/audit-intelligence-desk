import pytest

from app.services.moody import MoodyDecision, _resolve_flagged


@pytest.mark.parametrize(
    ("original_flagged", "decision", "expected"),
    [
        (True, "confirm", True),
        (True, "route_to_human_review", True),
        (True, "overturn", False),
        (False, "confirm", False),
        (False, "route_to_human_review", False),
        (False, "overturn", False),
    ],
)
def test_resolve_flagged(original_flagged: bool, decision: MoodyDecision, expected: bool) -> None:
    assert _resolve_flagged(original_flagged, decision) is expected
