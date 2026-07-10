import json
import os

from fastapi import APIRouter, Header, HTTPException
from loguru import logger
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.models.schemas import AuditReport
from app.services.audit_store import get_audit_store
from app.services.orchestrator import stream_audit

router = APIRouter(prefix="/audit", tags=["audit"])


def _check_audit_api_key(x_audit_api_key: str | None) -> None:
    """Optional shared-secret gate for the costly /audit/run endpoint.

    If AUDIT_API_KEY is unset, no auth is enforced (preserves current local/dev
    behavior). If set, callers must send a matching X-Audit-Api-Key header.
    """
    expected = os.getenv("AUDIT_API_KEY")
    if not expected:
        return
    if x_audit_api_key != expected:
        logger.warning("WARNING: /api/v1/audit/run | rejected request with missing/invalid AUDIT_API_KEY")
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "code": "UNAUTHORIZED", "detail": "Missing or invalid X-Audit-Api-Key header."},
        )


@router.get("/run")
async def run_audit_stream(x_audit_api_key: str | None = Header(default=None)) -> EventSourceResponse:
    """Runs the full transaction audit batch (~50 transactions, several LLM calls each).

    Costs real money (~$10-15 per run) and has no auth by default. Set the AUDIT_API_KEY
    env var to require a matching X-Audit-Api-Key header; if unset, this endpoint is
    open to anyone who can reach it — do not expose it beyond localhost/dev without
    setting AUDIT_API_KEY.
    """
    logger.info("GET /api/v1/audit/run")
    _check_audit_api_key(x_audit_api_key)

    async def event_generator():
        try:
            async for event_name, payload in stream_audit():
                if event_name == "complete":
                    get_audit_store().save(AuditReport.model_validate(payload))
                yield {"event": event_name, "data": json.dumps(payload, default=str)}
        except Exception as exc:  # noqa: BLE001 - surface as a structured SSE error event
            logger.error(f"FAILED: /api/v1/audit/run | reason={exc}")
            yield {
                "event": "error",
                "data": json.dumps({"status": "error", "code": "AUDIT_RUN_FAILED", "detail": str(exc)}),
            }

    return EventSourceResponse(event_generator())


@router.get("/reports/{session_id}")
async def get_audit_report(session_id: str) -> AuditReport:
    logger.info(f"GET /api/v1/audit/reports/{session_id}")
    report = get_audit_store().get(session_id)
    if report is None:
        logger.warning(f"WARNING: report not found | session_id={session_id}")
        raise HTTPException(
            status_code=404,
            detail={"status": "error", "code": "REPORT_NOT_FOUND", "detail": f"No report for session_id={session_id}"},
        )
    logger.success(f"GET /api/v1/audit/reports/{session_id} | status=200")
    return report


class CorrectionRequest(BaseModel):
    session_id: str  # required: disambiguates which audit run's episode this corrects
    notes: str


@router.post("/verdicts/{transaction_id}/correct")
async def record_correction(transaction_id: str, body: CorrectionRequest) -> dict:
    """Records a human correction to a past verdict (Episodic Memory), which feeds
    dynamic Procedural Memory's advisory synthesis on the next audit run.

    session_id is required so a correction can never silently attach to the wrong
    audit run if /audit/run was re-triggered since the verdict was reviewed.
    """
    logger.info(f"POST /api/v1/audit/verdicts/{transaction_id}/correct | session_id={body.session_id}")
    found = get_audit_store().record_correction(transaction_id, body.session_id, body.notes)
    if not found:
        logger.warning(
            f"WARNING: /api/v1/audit/verdicts/{transaction_id}/correct | "
            f"no episode found for session_id={body.session_id}"
        )
        raise HTTPException(
            status_code=404,
            detail={
                "status": "error",
                "code": "EPISODE_NOT_FOUND",
                "detail": f"No episode for transaction_id={transaction_id} session_id={body.session_id}",
            },
        )
    logger.success(f"POST /api/v1/audit/verdicts/{transaction_id}/correct | status=200")
    return {"status": "ok"}
