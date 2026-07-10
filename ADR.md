# Architecture Decision Records

Each ADR: Context, Decision, Consequences. Numbered in the order the decision was made, not necessarily
the order components execute at runtime.

---

## ADR-001: Plain async orchestration, not autonomous subagent delegation

**Context:** The Claude Agent SDK supports two orchestration styles — a single Claude session
autonomously invoking an `Agent`/`Task` tool to delegate to subagents, or a host application calling
`query()` directly per specialist with its own control flow.

**Decision:** Hermione's orchestration is plain async Python (`app/services/orchestrator.py`) calling
`query()` once per specialist per transaction. No agent decides *whether* to delegate — the pipeline
(Rita → Percy → Moody) is fixed and deterministic for every transaction.

**Consequences:** Fully predictable, testable control flow; per-transaction failures are caught and
degrade gracefully instead of derailing an entire agentic loop. Trade-off: this doesn't generalize to
open-ended tasks where the right sequence of specialists isn't known in advance — that's a different
architecture, not needed here since every transaction goes through the same fixed audit steps.

---

## ADR-002: Hybrid RAG (dense + sparse + RRF + MMR) for policy retrieval, not a single method

**Context:** Rita needs to retrieve the right policy text per transaction from a 5-document corpus.

**Decision:** Semantic chunking (cosine-similarity threshold over sentence embeddings) → `nomic-embed-text-v1.5`
dense embeddings in FAISS + BM25 sparse index → Reciprocal Rank Fusion → MMR diversification.

**Consequences:** Matches the project's standard RAG default; verified empirically to surface the
correct policy for representative queries (`POL-VENDOR-01` for a bank-detail query, `POL-HOURS-01` for
an off-hours query). Overhead (embedding model load, hybrid fusion) is real but irrelevant at this
corpus size (~6 chunks) — the pattern is proven out for when the corpus grows.

---

## ADR-003: Sonnet for every agent, effort tiered by role

**Context:** Model/effort choice affects both judgment quality (nuanced policy reasoning, injection
resistance) and cost (50 transactions × up to 2-3 LLM calls per run).

**Decision:** `sonnet` for Hermione, Percy, and Moody. Effort: Hermione=low (summarizing
already-verified verdicts), Percy=medium, Moody=high (last line of defense against injection and false
positives).

**Consequences:** Haiku was judged too weak for citation-bound policy judgment and adversarial
robustness; Opus was judged unnecessary cost at this task's complexity and batch volume. Verified live:
Moody correctly resisted the injection fixture and correctly cleared the false-positive fixture at this
tier.

---

## ADR-004: Episodic and Procedural Memory reuse the existing Postgres/Supabase store

**Context:** A reference project (`The Secure Agent`) implements Episodic Memory as a separate SQLite
file. Adding tiered memory here raised the same choice: a new dedicated store, or the existing
`AuditStore` already used for audit reports.

**Decision:** Extend the existing `AuditStore` (`app/services/audit_store.py`) with
`episodic_verdicts`/`procedural_insights` tables on the same SQLAlchemy engine/DSN, rather than
introducing SQLite or any second database. Explicit user choice, made to avoid a third persistence
mechanism in a project that already has Postgres/Supabase wired up.

**Consequences:** One connection, one migration surface, one backend to operate. Trade-off: loses the
reference project's SQLite-specific conveniences (single-file portability, zero-setup local dev) — the
`InMemoryAuditStore` fallback covers that gap for local/test use instead.

---

## ADR-005: Config split three ways (`model_config.yaml` / `prompt_config.yaml` / `app_config.yaml`)

**Context:** The reference project proves out a single `app_config.yaml` with sections. The user asked
for three separate files instead.

**Decision:** Three files as requested, at root-level `config/`, distinct from `app/ai/config/` (which
holds the Python loader code, not data).

**Consequences:** More files to keep in sync than the reference's single-file pattern, but a cleaner
separation of concerns (which model, which prompt version, which runtime parameters) if any one of
these needs independent versioning or a different owner later.

---

## ADR-006: `DATABASE_URL` takes priority, old vars kept

**Context:** The user's actual local Postgres instance is addressed via `DATABASE_URL`
(`postgresql://user:pass@host:port/`) rather than the project's original `SUPABASE_DB_DSN`/`POSTGRES_DSN`
naming.

**Decision:** `_resolve_dsn()` in `audit_store.py` checks `DATABASE_URL` first; falls back to the
backend-specific var (`SUPABASE_DB_DSN` or `POSTGRES_DSN` per `DB_BACKEND`) only if unset. All three
vars are kept — explicit user choice, not a breaking rename.

**Consequences:** One canonical var for the common case, zero migration burden for anything already
relying on the older two.

---

## ADR-007: Custom guardrails, not a guardrails library

**Context:** Guardrails AI and NeMo Guardrails exist as off-the-shelf options; the reference project
instead implements its own regex/heuristic layer.

**Decision:** Followed the reference project's pattern: small, focused, hand-written checks
(`app/guardrails/pii.py`, `injection.py`, `citation.py`) rather than a general-purpose framework.

**Consequences:** No new heavy dependency, checks are trivially readable and testable as pure functions
(see `tests/test_guardrails.py`). Trade-off: doesn't get a framework's broader out-of-the-box coverage —
acceptable here since the threat model (prompt injection via retrieved policy text, hallucinated
citations, PII in free-text correction notes) is narrow and well understood for this specific system.

---

## ADR-008: SSE, not WebSocket, for the audit-run endpoint

**Context:** The project's default rule is WebSocket/SSE for agent endpoints (never plain REST).

**Decision:** Server-Sent Events (`GET /api/v1/audit/run`), not WebSocket.

**Consequences:** The audit run is one-directional (server streams progress; the client never needs to
send anything mid-run), so SSE's simpler request/response-shaped semantics fit without the added
complexity of a bidirectional WebSocket connection.

---

## ADR-009: Moody's `route_to_human_review` counts as flagged, not cleared

**Context:** Found via code review: `POL-APPROVER-01` explicitly directs approver-vendor conflicts to
human review rather than a confirmed violation — Moody legitimately returns
`"route_to_human_review"` for exactly this case, but the original scoring logic cleared `flagged`
whenever the decision wasn't `"confirm"`, silently undercounting accuracy on those ground-truth
anomalies.

**Decision:** `_resolve_flagged()` in `moody.py`: `flagged` stays as Percy set it unless Moody's decision
is `"overturn"`. Both `"confirm"` and `"route_to_human_review"` keep it surfaced for a human.

**Consequences:** Accuracy scoring now correctly credits "correctly escalated for human review" as a
match against `is_anomaly: true`, not a miss. `confirmed_by_moody` (unchanged) still distinguishes fully
confirmed from flagged-but-escalated.
