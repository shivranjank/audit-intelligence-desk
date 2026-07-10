from datetime import UTC, datetime

from app.models.schemas import AuditReport
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
