# LVAgenticAI Final Project — Policy-Grounded Transaction Audit Agent

Multi-agent system built on the Claude Agent SDK, exposed via FastAPI (SSE), that audits expense/payment
transactions against written internal policies — evaluated for both accuracy (vs. ground truth) and
adversarial robustness (prompt-injection resistance, false-positive avoidance).

See [`architecture_block_diagram.md`](architecture_block_diagram.md) for the end-to-end data flow, and
[`ADR.md`](ADR.md) for the reasoning behind the major design decisions. `changelog.md` has a per-file
history of every change, session by session.

## Agents

| Name | Role |
|---|---|
| Hermione | Editor-in-Chief — orchestrates the audit run (plain async Python, not autonomous subagent delegation), scores verdicts against ground truth, runs the redteam fixtures, synthesizes the final executive summary |
| Rita | Policy Retrieval — pulls the relevant policy section per transaction via hybrid RAG (FAISS dense + BM25 sparse, fused with RRF, diversified with MMR); no LLM call, pure retrieval |
| Percy | Analyst — decides whether a transaction violates a policy, grounded in deterministic signals + retrieved policy text + procedural-memory advisories |
| Moody | Fact-Checker — adversarially re-examines Percy's verdict, resists prompt injection in retrieved text, requires a policy citation before any flag stands, can confirm / overturn / route to human review |

## Memory architecture (five tiers)

| Tier | Where |
|---|---|
| Sensory Buffer | The raw transaction as it enters the pipeline — ephemeral, no persistence |
| Working Memory | `WorkingMemory` (`app/models/schemas.py`) — explicit per-transaction state threaded through Percy → Moody |
| Episodic Memory | `episodic_verdicts` table (`app/services/audit_store.py`) — past verdicts + human corrections, scoped by vendor |
| Semantic Memory | Rita's FAISS+BM25 policy corpus (`app/services/rag.py`) |
| Procedural Memory (static) | `app/services/signals.py` — deterministic pre-checks (duplicate/structuring/off-hours) |
| Procedural Memory (dynamic) | `procedural_insights` table + `app/services/procedural.py` — TTL'd advisories synthesized from corrected false positives |

Episodic and Procedural Memory reuse the same Postgres/Supabase-backed `AuditStore` as audit reports — no
separate database.

## Guardrails (`app/guardrails/`)

- `pii.py` — redacts email/phone/account-number-shaped patterns from human correction notes before persistence
- `injection.py` — regex pre-check on retrieved policy text, logs a detection (supplements, doesn't replace, Percy/Moody's own prompt-level anti-injection instructions)
- `citation.py` — rejects/routes-to-human-review a flagged verdict whose cited `policy_ref` doesn't actually appear in the retrieved chunks

Toggled via `config/app_config.yaml`'s `guardrails` section.

## Config & prompts

- `config/model_config.yaml` — per-agent model + reasoning effort
- `config/prompt_config.yaml` — per-agent prompt version selection
- `config/app_config.yaml` — RAG/retrieval parameters, guardrail toggles
- `app/ai/prompt/<agent>/<version>/prompt.yaml` — one system prompt file per agent per version, with fallback to `v1` if a configured version is missing (`app/ai/config/prompt_loader.py`)

## Data (`data/`)

- `transactions.json` — 50 synthetic transactions to audit
- `ground_truth.json` — expected verdicts (40 clean, 10 anomalies across 5 types)
- `policies/*.md` — 5 internal policy documents the agents must ground every verdict in
- `redteam/false_positive_fixture.json` — a compliant edge case that must **not** be flagged
- `redteam/injection_policy_fixture.md` — a fake policy doc containing a prompt-injection attempt the agents must resist

## API

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness check |
| `GET /api/v1/audit/run` | SSE stream of a full audit run (~50 transactions + 2 redteam fixtures); optionally gated by `AUDIT_API_KEY` |
| `GET /api/v1/audit/reports/{session_id}` | Fetch a persisted audit report |
| `POST /api/v1/audit/verdicts/{transaction_id}/correct` | Record a human correction (feeds Procedural Memory) |

## Running locally

```bash
uv sync
cp .env.example .env   # fill in ANTHROPIC_API_KEY and DB settings
uv run uvicorn app.main:app --reload
```

## Testing

```bash
uv run ruff check .
uv run pytest --ignore=tests/test_integration_agents.py   # deterministic, free, always safe
uv run pytest tests/test_integration_agents.py             # live LLM calls, costs real money
```
