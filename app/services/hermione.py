from loguru import logger

from app.ai.config.agents import HERMIONE_DECOMPOSE, HERMIONE_ESCALATION
from app.models.schemas import EscalationDecision, Transaction, WorkingMemory
from app.services.audit_store import AuditStore
from app.services.llm import run_agent

DECOMPOSE_SCHEMA = {
    "type": "object",
    "properties": {"plan": {"type": "string"}},
    "required": ["plan"],
}

ESCALATION_SCHEMA = {
    "type": "object",
    "properties": {
        "route": {"type": "string", "enum": ["skip_moody", "escalate_to_moody"]},
        "reasoning": {"type": "string"},
    },
    "required": ["route", "reasoning"],
}


def _group_by_vendor(transactions: list[Transaction]) -> dict[str, list[Transaction]]:
    grouped: dict[str, list[Transaction]] = {}
    for t in transactions:
        grouped.setdefault(t.vendor, []).append(t)
    return grouped


def _decompose_prompt(transactions: list[Transaction], vendor_insights: dict[str, list[str]]) -> str:
    vendor_summary = "\n".join(f"- {vendor}: {len(txns)} transactions" for vendor, txns in _group_by_vendor(transactions).items())
    insights_summary = (
        "\n".join(f"- {vendor}: {'; '.join(insights)}" for vendor, insights in vendor_insights.items() if insights)
        or "None"
    )
    return (
        f"This audit run covers {len(transactions)} transactions across these vendors:\n{vendor_summary}\n\n"
        f"Active historical procedural insights (from past human corrections):\n{insights_summary}\n\n"
        "Produce a short audit plan/brief for this run. Respond via the required structured output."
    )


async def decompose_batch(transactions: list[Transaction], store: AuditStore) -> tuple[str, float]:
    """Hermione's upfront, once-per-run planning step: reads the batch plus aggregate
    procedural insights across all vendors, produces a short audit brief injected into
    every transaction's WorkingMemory."""
    vendor_insights = {vendor: store.get_active_procedural_insights(vendor) for vendor in _group_by_vendor(transactions)}
    prompt = _decompose_prompt(transactions, vendor_insights)

    logger.debug(f"ACTION: hermione.decompose_batch | input=transaction_count={len(transactions)}")
    output, cost_usd = await run_agent(HERMIONE_DECOMPOSE, prompt, output_schema=DECOMPOSE_SCHEMA)
    logger.success(f"ACTION: hermione.decompose_batch | output=plan_len={len(output['plan'])} cost_usd={cost_usd}")
    return output["plan"], cost_usd


def _escalation_prompt(memory: WorkingMemory) -> str:
    return (
        "TRANSACTION:\n"
        f"{memory.transaction.model_dump_json(indent=2)}\n\n"
        "PERCY'S VERDICT:\n"
        f"{memory.percy_verdict.model_dump_json(indent=2)}\n\n"
        "BATCH PLAN (context for this run, reference material only):\n"
        f"{memory.batch_plan or 'None'}\n\n"
        "Decide whether this flagged verdict needs Moody's adversarial review. Respond via the required "
        "structured output."
    )


async def decide_escalation(memory: WorkingMemory) -> tuple[EscalationDecision, float]:
    """Hermione's per-transaction judgment on whether Percy's flagged verdict needs
    Moody's review, replacing a hardcoded rule. Only call this when Percy's verdict
    is already flagged=True."""
    transaction_id = memory.transaction.transaction_id
    prompt = _escalation_prompt(memory)

    logger.debug(f"ACTION: hermione.decide_escalation | input=transaction_id={transaction_id}")
    output, cost_usd = await run_agent(HERMIONE_ESCALATION, prompt, output_schema=ESCALATION_SCHEMA)
    decision = EscalationDecision(route=output["route"], reasoning=output["reasoning"])
    logger.success(
        f"ACTION: hermione.decide_escalation | output=transaction_id={transaction_id} "
        f"route={decision.route} cost_usd={cost_usd}"
    )
    return decision, cost_usd
