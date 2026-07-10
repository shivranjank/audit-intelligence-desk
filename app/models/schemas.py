from datetime import datetime
from typing import Literal

from pydantic import BaseModel

AnomalyType = Literal[
    "duplicate_payment",
    "structuring",
    "off_hours_approval",
    "mismatched_vendor_details",
    "unusual_approver_pairing",
]


class Transaction(BaseModel):
    transaction_id: str
    date: datetime
    vendor: str
    amount: float
    department: str
    account_code: str
    approver: str
    description: str


class PolicyChunk(BaseModel):
    policy_ref: str
    title: str
    anomaly_type: str | None
    text: str


class Signals(BaseModel):
    """Deterministic pre-checks computed before any LLM call."""

    duplicate_candidate_ids: list[str] = []
    in_structuring_band: bool = False
    is_off_hours: bool = False


class Verdict(BaseModel):
    transaction_id: str
    flagged: bool
    anomaly_type: AnomalyType | None = None
    policy_ref: str | None = None
    reasoning: str
    confirmed_by_moody: bool | None = None
    moody_notes: str | None = None
    moody_decision: str | None = None  # raw "confirm"|"overturn"|"route_to_human_review", for Episodic Memory
    guardrail_flags: list[str] = []  # e.g. "injection_detected:POL-X", "citation_check_failed" - non-empty means a guardrail forced flagged=True


class EscalationDecision(BaseModel):
    """Hermione's per-transaction judgment on whether Percy's flagged verdict needs
    Moody's adversarial review, replacing a hardcoded escalation rule."""

    route: Literal["skip_moody", "escalate_to_moody"]
    reasoning: str


class WorkingMemory(BaseModel):
    """Explicit per-transaction state threaded through Percy -> Moody, replacing
    implicit function-argument passing (Working Memory tier)."""

    transaction: Transaction
    signals: Signals | None = None
    policy_chunks: list[PolicyChunk] = []
    procedural_insights: list[str] = []
    batch_plan: str | None = None
    percy_verdict: Verdict | None = None
    escalation_decision: EscalationDecision | None = None
    moody_verdict: Verdict | None = None


class EpisodicEntry(BaseModel):
    """One past audit outcome, persisted for future recall (Episodic Memory tier)."""

    session_id: str
    transaction_id: str
    vendor: str
    approver: str
    anomaly_type: AnomalyType | None = None
    flagged: bool
    moody_decision: str | None = None
    created_at: datetime
    corrected_by_human: bool = False
    correction_notes: str | None = None


class ProceduralInsight(BaseModel):
    """A learned, TTL'd advisory synthesized from Episodic Memory corrections
    (dynamic Procedural Memory tier — the static tier is app/services/signals.py)."""

    scope_key: str
    insight_text: str
    created_at: datetime
    expires_at: datetime


class RedteamResult(BaseModel):
    fixture: str
    passed: bool
    detail: str


class AuditReport(BaseModel):
    session_id: str
    started_at: datetime
    completed_at: datetime | None = None
    batch_plan: str | None = None
    verdicts: list[Verdict] = []
    accuracy: float | None = None
    false_positives: int = 0
    false_negatives: int = 0
    moody_escalations: int = 0
    moody_skipped: int = 0
    redteam_results: list[RedteamResult] = []
    summary: str | None = None
    total_cost_usd: float = 0.0
