from datetime import UTC, datetime, timedelta

from app.models.schemas import EpisodicEntry, ProceduralInsight

INSIGHT_TTL_DAYS = 7
MIN_CORRECTIONS_FOR_INSIGHT = 2


def synthesize_insight(scope_key: str, episodes: list[EpisodicEntry]) -> ProceduralInsight | None:
    """Derive a soft advisory from past human corrections for one vendor scope.

    If enough flagged episodes for this scope were later corrected (a human overturned
    the flag) with the same anomaly_type, surface that as historical context for
    Percy/Moody to weigh — not a rule, and never a substitute for evaluating the
    current transaction on its own merits.
    """
    corrected = [e for e in episodes if e.flagged and e.corrected_by_human and e.anomaly_type]
    if len(corrected) < MIN_CORRECTIONS_FOR_INSIGHT:
        return None

    counts: dict[str, int] = {}
    for entry in corrected:
        counts[entry.anomaly_type] = counts.get(entry.anomaly_type, 0) + 1

    top_type, count = max(counts.items(), key=lambda kv: kv[1])
    if count < MIN_CORRECTIONS_FOR_INSIGHT:
        return None

    now = datetime.now(UTC)
    return ProceduralInsight(
        scope_key=scope_key,
        insight_text=(
            f"Historical note: {count} prior '{top_type}' flags for {scope_key} were corrected by a "
            "human reviewer as false positives. Weigh this context, but still evaluate this "
            "transaction strictly on its own merits and policy citations."
        ),
        created_at=now,
        expires_at=now + timedelta(days=INSIGHT_TTL_DAYS),
    )
