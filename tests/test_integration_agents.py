"""Live LLM integration tests. Cost real money per run; skipped automatically
when the claude CLI isn't available (e.g. in CI)."""

import uuid

import pytest

from app.services.audit_store import InMemoryAuditStore
from app.services.orchestrator import _audit_one, _run_false_positive_redteam, _run_injection_redteam, load_transactions
from app.services.rag import PolicyRAG
from tests.conftest import requires_claude_cli


@pytest.fixture(scope="module")
def rag() -> PolicyRAG:
    instance = PolicyRAG()
    instance.build_index()
    return instance


@pytest.fixture()
def store() -> InMemoryAuditStore:
    return InMemoryAuditStore()


@pytest.fixture(scope="module")
def transactions():
    return load_transactions()


@requires_claude_cli
@pytest.mark.asyncio
async def test_clean_transaction_not_flagged(transactions, rag: PolicyRAG, store: InMemoryAuditStore) -> None:
    txn = next(t for t in transactions if t.transaction_id == "TXN-0001")
    verdict, _cost, escalation_route = await _audit_one(txn, transactions, rag, store, str(uuid.uuid4()))
    assert verdict.flagged is False
    assert escalation_route is None  # never flagged, so Hermione's escalation call never ran


@requires_claude_cli
@pytest.mark.asyncio
async def test_duplicate_payment_flagged(transactions, rag: PolicyRAG, store: InMemoryAuditStore) -> None:
    txn = next(t for t in transactions if t.transaction_id == "TXN-0041")
    verdict, _cost, escalation_route = await _audit_one(txn, transactions, rag, store, str(uuid.uuid4()))
    assert verdict.flagged is True
    assert verdict.anomaly_type == "duplicate_payment"
    assert verdict.policy_ref == "POL-DUP-01"
    assert escalation_route in ("skip_moody", "escalate_to_moody")
    # If Hermione escalated, Moody must have actually confirmed (not overturned) this genuine duplicate.
    if escalation_route == "escalate_to_moody":
        assert verdict.confirmed_by_moody is True


@requires_claude_cli
@pytest.mark.asyncio
async def test_false_positive_redteam_cleared(rag: PolicyRAG, store: InMemoryAuditStore) -> None:
    result, _cost = await _run_false_positive_redteam(rag, store, str(uuid.uuid4()))
    assert result.passed is True, result.detail


@requires_claude_cli
@pytest.mark.asyncio
async def test_injection_redteam_resisted(rag: PolicyRAG, transactions) -> None:
    result, _cost = await _run_injection_redteam(rag, transactions)
    assert result.passed is True, result.detail
