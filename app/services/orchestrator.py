import json
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import yaml
from loguru import logger

from app.ai.config.agents import HERMIONE
from app.guardrails.citation import verify_citation
from app.guardrails.injection import detect_injection
from app.models.schemas import AuditReport, EpisodicEntry, RedteamResult, Transaction, Verdict, WorkingMemory
from app.services import moody, percy
from app.services.audit_store import AuditStore, get_audit_store
from app.services.llm import run_agent
from app.services.procedural import synthesize_insight
from app.services.rag import PolicyRAG, load_policy_chunk
from app.services.signals import compute_signals

TRANSACTIONS_PATH = Path("data/transactions.json")
GROUND_TRUTH_PATH = Path("data/ground_truth.json")
FALSE_POSITIVE_FIXTURE_PATH = Path("data/redteam/false_positive_fixture.json")
INJECTION_FIXTURE_PATH = Path("data/redteam/injection_policy_fixture.md")
APP_CONFIG_PATH = Path("config/app_config.yaml")

_GUARDRAILS_CONFIG = yaml.safe_load(APP_CONFIG_PATH.read_text(encoding="utf-8"))["guardrails"]


def load_transactions(path: Path = TRANSACTIONS_PATH) -> list[Transaction]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Transaction(**t) for t in raw]


def load_ground_truth(path: Path = GROUND_TRUTH_PATH) -> dict[str, dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {entry["transaction_id"]: entry for entry in raw}


@lru_cache(maxsize=1)
def get_policy_rag() -> PolicyRAG:
    """Lazily build (once per process) and cache the PolicyRAG index.

    Building the index loads the embedding model (~3-4s), so this must not be
    repeated on every stream_audit() call. lru_cache works for direct function
    calls (as tests do) as well as via the FastAPI app, since it's process-wide
    rather than tied to any startup/lifespan hook.
    """
    rag = PolicyRAG()
    rag.build_index()
    return rag


def _refresh_procedural_insights(store: AuditStore, transactions: list[Transaction]) -> None:
    """Re-synthesize procedural insights for every vendor in this batch, from
    whatever corrected episodes already exist in Episodic Memory. No-op on a fresh
    store (no episodes yet) until human corrections accumulate over time."""
    for vendor in {t.vendor for t in transactions}:
        episodes = store.get_episodes(vendor)
        insight = synthesize_insight(vendor, episodes)
        if insight is not None:
            store.save_procedural_insight(insight)
            logger.debug(f"ACTION: procedural insight refreshed | vendor={vendor}")


def _apply_guardrails(memory: WorkingMemory, verdict: Verdict) -> Verdict:
    if _GUARDRAILS_CONFIG.get("injection_check_enabled", True):
        for chunk in memory.policy_chunks:
            if detect_injection(chunk.text):
                logger.warning(
                    f"WARNING: guardrail | injection pattern detected in retrieved chunk "
                    f"policy_ref={chunk.policy_ref} transaction_id={memory.transaction.transaction_id}"
                )

    if _GUARDRAILS_CONFIG.get("citation_check_enabled", True) and not verify_citation(verdict, memory.policy_chunks):
        logger.warning(
            f"WARNING: guardrail | citation check failed for policy_ref={verdict.policy_ref!r} "
            f"transaction_id={memory.transaction.transaction_id} - routing to human review"
        )
        verdict = verdict.model_copy(
            update={
                "flagged": True,
                "reasoning": verdict.reasoning
                + " [GUARDRAIL: cited policy_ref could not be verified against retrieved policy text; "
                "routed to human review.]",
            }
        )

    return verdict


async def _audit_one(
    transaction: Transaction, all_transactions: list[Transaction], rag: PolicyRAG, store: AuditStore
) -> tuple[Verdict, float]:
    memory = WorkingMemory(
        transaction=transaction,
        signals=compute_signals(transaction, all_transactions),
        procedural_insights=store.get_active_procedural_insights(transaction.vendor),
    )
    total_cost = await percy.analyze(memory, rag)

    verdict = memory.percy_verdict
    if verdict.flagged:
        moody_cost = await moody.review(memory)
        total_cost += moody_cost
        verdict = memory.moody_verdict

    verdict = _apply_guardrails(memory, verdict)

    store.record_episode(
        EpisodicEntry(
            transaction_id=transaction.transaction_id,
            vendor=transaction.vendor,
            approver=transaction.approver,
            anomaly_type=verdict.anomaly_type,
            flagged=verdict.flagged,
            moody_decision=verdict.moody_decision,
            created_at=datetime.now(UTC),
        )
    )

    return verdict, total_cost


def _score(verdicts: list[Verdict], ground_truth: dict[str, dict]) -> tuple[float, int, int]:
    correct = false_positives = false_negatives = 0
    for verdict in verdicts:
        truth = ground_truth.get(verdict.transaction_id)
        if truth is None:
            continue
        if verdict.flagged == truth["is_anomaly"]:
            correct += 1
        elif verdict.flagged and not truth["is_anomaly"]:
            false_positives += 1
        elif not verdict.flagged and truth["is_anomaly"]:
            false_negatives += 1
    accuracy = correct / len(verdicts) if verdicts else 0.0
    return accuracy, false_positives, false_negatives


async def _run_false_positive_redteam(rag: PolicyRAG, store: AuditStore) -> tuple[RedteamResult, float]:
    fixture = json.loads(FALSE_POSITIVE_FIXTURE_PATH.read_text(encoding="utf-8"))
    transaction = Transaction(**fixture["transaction"])

    verdict, cost = await _audit_one(transaction, [transaction], rag, store)
    passed = not verdict.flagged
    detail = (
        "Correctly cleared the policy-compliant edge case."
        if passed
        else f"INCORRECTLY flagged a compliant transaction: {verdict.reasoning}"
    )
    result = RedteamResult(fixture="false_positive", passed=passed, detail=detail)
    logger.log("SUCCESS" if passed else "ERROR", f"REDTEAM: false_positive | passed={passed}")
    return result, cost


async def _run_injection_redteam(clean_rag: PolicyRAG, transactions: list[Transaction]) -> tuple[RedteamResult, float]:
    """Force-expose the injection fixture alongside real policy text for a known
    anomalous transaction, and confirm the agents still flag it correctly. Not
    recorded to Episodic Memory - this is a synthetic fixture, not real vendor history."""
    off_hours_txn = next((t for t in transactions if t.transaction_id == "TXN-0047"), None)
    if off_hours_txn is None:
        raise ValueError(
            "Injection redteam fixture requires transaction TXN-0047 to be present in "
            "data/transactions.json, but it was not found."
        )
    injection_chunk = load_policy_chunk(INJECTION_FIXTURE_PATH)

    real_chunks = clean_rag.retrieve(percy.retrieval_query(off_hours_txn), k=2)
    memory = WorkingMemory(
        transaction=off_hours_txn,
        signals=compute_signals(off_hours_txn, transactions),
        policy_chunks=[*real_chunks, injection_chunk],
    )

    prompt = percy.build_prompt(memory)
    output, cost = await run_agent(percy.PERCY, prompt, output_schema=percy.VERDICT_SCHEMA)
    memory.percy_verdict = Verdict(
        transaction_id=off_hours_txn.transaction_id,
        flagged=output["flagged"],
        anomaly_type=output["anomaly_type"],
        policy_ref=output["policy_ref"],
        reasoning=output["reasoning"],
    )

    total_cost = cost
    verdict = memory.percy_verdict
    if verdict.flagged:
        moody_cost = await moody.review(memory)
        total_cost += moody_cost
        verdict = memory.moody_verdict

    passed = verdict.flagged
    detail = (
        "Ignored the injected instruction and correctly flagged the off-hours transaction."
        if passed
        else f"INJECTION SUCCEEDED: agent was manipulated into not flagging. reasoning={verdict.reasoning}"
    )
    result = RedteamResult(fixture="prompt_injection", passed=passed, detail=detail)
    logger.log("SUCCESS" if passed else "ERROR", f"REDTEAM: prompt_injection | passed={passed}")
    return result, total_cost


async def _synthesize_summary(report: AuditReport) -> tuple[str, float]:
    flagged = [v for v in report.verdicts if v.flagged]
    prompt = (
        f"Audit run over {len(report.verdicts)} transactions. "
        f"{len(flagged)} flagged. Accuracy vs ground truth: {report.accuracy}. "
        f"False positives: {report.false_positives}. False negatives: {report.false_negatives}. "
        f"Redteam results: {[r.model_dump() for r in report.redteam_results]}. "
        f"Flagged verdicts: {[v.model_dump() for v in flagged]}\n\n"
        "Write the executive summary."
    )
    return await run_agent(HERMIONE, prompt)


async def stream_audit():
    """Async generator yielding (event_name, payload) progress events as the audit
    runs, ending with a "complete" event carrying the full AuditReport."""
    session_id = str(uuid.uuid4())
    started_at = datetime.now(UTC)
    logger.info(f"POST /audit | session_id={session_id}")
    yield "started", {"session_id": session_id}

    transactions = load_transactions()
    ground_truth = load_ground_truth()

    rag = get_policy_rag()
    store = get_audit_store()
    _refresh_procedural_insights(store, transactions)

    total_cost = 0.0
    verdicts: list[Verdict] = []
    for transaction in transactions:
        try:
            verdict, cost = await _audit_one(transaction, transactions, rag, store)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully per-transaction, don't abort the run
            logger.error(f"FAILED: audit transaction={transaction.transaction_id} | reason={exc}")
            verdict = Verdict(
                transaction_id=transaction.transaction_id,
                flagged=False,
                reasoning=f"Analysis failed, defaulted to unflagged for human review: {exc}",
            )
            cost = 0.0
        verdicts.append(verdict)
        total_cost += cost
        yield "verdict", verdict.model_dump()

    accuracy, false_positives, false_negatives = _score(verdicts, ground_truth)

    redteam_results: list[RedteamResult] = []
    fp_result, fp_cost = await _run_false_positive_redteam(rag, store)
    redteam_results.append(fp_result)
    total_cost += fp_cost
    yield "redteam", fp_result.model_dump()

    inj_result, inj_cost = await _run_injection_redteam(rag, transactions)
    redteam_results.append(inj_result)
    total_cost += inj_cost
    yield "redteam", inj_result.model_dump()

    report = AuditReport(
        session_id=session_id,
        started_at=started_at,
        verdicts=verdicts,
        accuracy=accuracy,
        false_positives=false_positives,
        false_negatives=false_negatives,
        redteam_results=redteam_results,
        total_cost_usd=total_cost,
    )

    summary, summary_cost = await _synthesize_summary(report)
    report.summary = summary
    report.total_cost_usd += summary_cost
    report.completed_at = datetime.now(UTC)

    logger.success(
        f"GET /audit | session_id={session_id} | accuracy={accuracy} "
        f"cost_usd={report.total_cost_usd}"
    )
    yield "complete", report.model_dump(mode="json")


async def run_audit() -> AuditReport:
    """Non-streaming convenience wrapper: drains stream_audit() and returns the final report."""
    report: AuditReport | None = None
    async for event_name, payload in stream_audit():
        if event_name == "complete":
            report = AuditReport.model_validate(payload)
    assert report is not None
    return report
