import json

from fastapi import APIRouter, HTTPException
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.models.schemas import AuditReport
from app.services.audit_store import get_audit_store
from app.services.orchestrator import stream_audit

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/run")
async def run_audit_stream() -> EventSourceResponse:
    logger.info("GET /api/v1/audit/run")

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
