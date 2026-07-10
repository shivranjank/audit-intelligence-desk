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


class RedteamResult(BaseModel):
    fixture: str
    passed: bool
    detail: str


class AuditReport(BaseModel):
    session_id: str
    started_at: datetime
    completed_at: datetime | None = None
    verdicts: list[Verdict] = []
    accuracy: float | None = None
    false_positives: int = 0
    false_negatives: int = 0
    redteam_results: list[RedteamResult] = []
    summary: str | None = None
    total_cost_usd: float = 0.0
