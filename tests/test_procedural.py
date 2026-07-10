from datetime import UTC, datetime

from app.models.schemas import EpisodicEntry
from app.services.procedural import MIN_CORRECTIONS_FOR_INSIGHT, synthesize_insight


def _episode(anomaly_type: str, flagged: bool, corrected: bool) -> EpisodicEntry:
    return EpisodicEntry(
        transaction_id="TXN-X",
        vendor="Acme Co",
        approver="A. Test",
        anomaly_type=anomaly_type,
        flagged=flagged,
        created_at=datetime.now(UTC),
        corrected_by_human=corrected,
    )


def test_no_insight_below_correction_threshold() -> None:
    episodes = [_episode("off_hours_approval", True, True)]
    assert synthesize_insight("Acme Co", episodes) is None


def test_insight_synthesized_at_threshold() -> None:
    episodes = [_episode("off_hours_approval", True, True) for _ in range(MIN_CORRECTIONS_FOR_INSIGHT)]
    insight = synthesize_insight("Acme Co", episodes)
    assert insight is not None
    assert insight.scope_key == "Acme Co"
    assert "off_hours_approval" in insight.insight_text
    assert insight.expires_at > insight.created_at


def test_uncorrected_flags_dont_count() -> None:
    episodes = [_episode("off_hours_approval", True, False) for _ in range(5)]
    assert synthesize_insight("Acme Co", episodes) is None


def test_unflagged_episodes_dont_count() -> None:
    episodes = [_episode("off_hours_approval", False, True) for _ in range(5)]
    assert synthesize_insight("Acme Co", episodes) is None
