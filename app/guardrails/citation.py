from app.models.schemas import PolicyChunk, Verdict


def verify_citation(verdict: Verdict, policy_chunks: list[PolicyChunk]) -> bool:
    """Anti-hallucinated-citation guardrail: a flagged verdict must cite a policy_ref
    that was actually present in the chunks it was given."""
    if not verdict.flagged:
        return True
    if verdict.policy_ref is None:
        return False
    return any(chunk.policy_ref == verdict.policy_ref for chunk in policy_chunks)
