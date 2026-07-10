import pytest

from app.services.rag import PolicyRAG, load_policy_chunk


@pytest.fixture(scope="module")
def rag() -> PolicyRAG:
    instance = PolicyRAG()
    instance.build_index()
    return instance


def test_build_index_produces_chunks(rag: PolicyRAG) -> None:
    assert len(rag._chunks) >= 5  # one per policy doc, some split into more


def test_retrieve_top_result_matches_expected_policy(rag: PolicyRAG) -> None:
    results = rag.retrieve("payment routed to bank details updated same day as invoice, unverified", k=1)
    assert len(results) == 1
    assert results[0].policy_ref == "POL-VENDOR-01"


def test_retrieve_off_hours_query(rag: PolicyRAG) -> None:
    results = rag.retrieve("approval timestamped late at night with no business justification", k=2)
    refs = [c.policy_ref for c in results]
    assert "POL-HOURS-01" in refs


def test_load_injection_fixture_chunk() -> None:
    from pathlib import Path

    chunk = load_policy_chunk(Path("data/redteam/injection_policy_fixture.md"))
    assert chunk.policy_ref == "POL-REDTEAM-INJECTION"
    assert "ignore all previous instructions" in chunk.text.lower()
