from datetime import UTC, datetime, timedelta

from app.models.schemas import AuditReport, EpisodicEntry, ProceduralInsight
from app.services.audit_store import InMemoryAuditStore, get_audit_store


def test_in_memory_store_round_trip() -> None:
    store = InMemoryAuditStore()
    report = AuditReport(session_id="abc-123", started_at=datetime.now(UTC))

    assert store.get("abc-123") is None
    store.save(report)
    fetched = store.get("abc-123")

    assert fetched is not None
    assert fetched.session_id == "abc-123"


def test_get_audit_store_defaults_to_in_memory(monkeypatch) -> None:
    monkeypatch.delenv("DB_BACKEND", raising=False)
    store = get_audit_store()
    assert isinstance(store, InMemoryAuditStore)


def test_episodic_record_and_retrieve() -> None:
    store = InMemoryAuditStore()
    now = datetime.now(UTC)
    store.record_episode(
        EpisodicEntry(
            transaction_id="TXN-A",
            vendor="Acme Co",
            approver="A. Test",
            anomaly_type="off_hours_approval",
            flagged=True,
            moody_decision="confirm",
            created_at=now,
        )
    )
    store.record_episode(
        EpisodicEntry(
            transaction_id="TXN-B",
            vendor="Other Vendor",
            approver="B. Test",
            flagged=False,
            created_at=now,
        )
    )

    episodes = store.get_episodes("Acme Co")
    assert len(episodes) == 1
    assert episodes[0].transaction_id == "TXN-A"
    assert store.get_episodes("Other Vendor")[0].transaction_id == "TXN-B"
    assert store.get_episodes("Nonexistent Vendor") == []


def test_record_correction_updates_matching_episode() -> None:
    store = InMemoryAuditStore()
    store.record_episode(
        EpisodicEntry(
            transaction_id="TXN-A",
            vendor="Acme Co",
            approver="A. Test",
            flagged=True,
            created_at=datetime.now(UTC),
        )
    )
    store.record_correction("TXN-A", "Cleared after review, email jane@acme.com confirmed context")

    episode = store.get_episodes("Acme Co")[0]
    assert episode.corrected_by_human is True
    assert "REDACTED_EMAIL" in episode.correction_notes
    assert "jane@acme.com" not in episode.correction_notes


def test_procedural_insight_active_vs_expired() -> None:
    store = InMemoryAuditStore()
    now = datetime.now(UTC)
    store.save_procedural_insight(
        ProceduralInsight(
            scope_key="Acme Co", insight_text="active insight", created_at=now, expires_at=now + timedelta(days=1)
        )
    )
    store.save_procedural_insight(
        ProceduralInsight(
            scope_key="Acme Co", insight_text="expired insight", created_at=now, expires_at=now - timedelta(days=1)
        )
    )

    active = store.get_active_procedural_insights("Acme Co")
    assert active == ["active insight"]
