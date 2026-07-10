# Changelog

## Session 2026-07-10 — Phase 0 (Git & GitHub setup)

- `.gitignore` — added: standard Python/uv ignores, `.env`, logs, vector_db artifacts, IDE/OS files.
- `.github/workflows/ci.yml` — added: runs `uv sync`, `ruff check`, `pytest` on PRs and pushes to `main`.
- `.github/workflows/cd.yml` — added: builds and pushes a Docker image to GHCR on merge to `main` (tagged with commit SHA + `latest`). Depends on a `Dockerfile` that will be added in Phase 1.
- `README.md` — added: project overview and agent roster (Hermione, Rita, Percy, Moody).
- `changelog.md` — added: this file.

## Session 2026-07-10 — Base dataset

- `data/transactions.json` — copied from `../FinalProject/data`: 50 synthetic expense/payment transactions (fictional vendors, initials-only approvers, no real PII).
- `data/ground_truth.json` — copied: labels for the above (40 clean, 10 true anomalies across 5 types).
- `data/policies/*.md` (5 files) — copied: written internal policies defining duplicate payment, structuring, off-hours approval, vendor banking verification, and approver-vendor relationship rules.
- `data/redteam/false_positive_fixture.json` — copied: a policy-compliant edge case the audit agent must clear, not flag.
- `data/redteam/injection_policy_fixture.md` — copied: a fake policy doc containing a prompt-injection attempt; the audit agent must resist it.
- Project reframed based on this data from a generic web-research system to a **policy-grounded transaction audit agent** (Rita's role repurposed from web search to RAG-based policy retrieval; see README).

## Session 2026-07-10 — Phase 1 (project scaffolding)

- `pyproject.toml`, `uv.lock` — added: `uv init` (flat `app/` layout, no `src/`); deps `claude-agent-sdk`, `fastapi`, `uvicorn[standard]`, `loguru`, `sqlalchemy`, `supabase`, `psycopg2-binary`; dev deps `ruff`, `pytest`, `pytest-asyncio`, `playwright`.
- `app/` — scaffolded per folder template: `ai/{config,prompt,tasks}`, `api/{v1,v2}/endpoints`, `models/`, `services/`, `static/`, `templates/`, `utils/`, with `__init__.py` where the template specifies one.
- `app/main.py` — added: minimal FastAPI app with loguru sink (`logs/app.log`, 10MB rotation, 7-day retention) and a `/health` endpoint. Verified: boots via `uv run uvicorn app.main:app`, `/health` returns `{"status":"ok"}`, log line written correctly.
- `app/ai/prompt/all_sample_prompt.yaml` — added: placeholder keys for the four agent prompts (Hermione, Rita, Percy, Moody), to be filled in Phase 2.
- `.env.example` — added: template for `ANTHROPIC_API_KEY`, `DB_BACKEND` (supabase/postgres), Supabase and Postgres connection vars. Real `.env` is gitignored and untouched.
- `graph_kb/`, `vector_db/`, `logs/`, `tests/queries/` — scaffolded with `.gitkeep` (vector_db contents gitignored except `.gitkeep`, per `.gitignore`).
- Verified: `uv run ruff check .` passes clean.

## Session 2026-07-10 — Phases 2-6 (agent implementation, API, tests)

Architecture note: orchestration is plain async Python control flow calling the Claude Agent SDK's
`query()` once per specialist per transaction (single-shot, tool-free, schema-constrained JSON output) —
not the SDK's autonomous Agent-tool subagent delegation, which suits open-ended agentic tasks more than
this deterministic batch-audit pipeline. `query()` shells out to the local `claude` CLI; no separate
`ANTHROPIC_API_KEY` was needed in this dev environment since the CLI is already authenticated.

- `pyproject.toml` — added deps: `sentence-transformers`, `faiss-cpu`, `rank-bm25`, `einops` (RAG stack; `einops` required by nomic's custom model code). Removed `supabase` (unused — Supabase is accessed as plain Postgres via SQLAlchemy, not its REST client). Added `[tool.pytest.ini_options]` (`pythonpath = ["."]`, `asyncio_mode = "auto"`) so pytest resolves the `app` package and async tests run without per-test marks.
- `app/models/schemas.py` — added: `Transaction`, `PolicyChunk`, `Signals`, `Verdict`, `RedteamResult`, `AuditReport` Pydantic models.
- `app/services/rag.py` — added: `PolicyRAG` — semantic chunking (cosine-similarity threshold over sentence embeddings), `nomic-ai/nomic-embed-text-v1.5` embeddings, FAISS dense index, BM25 sparse index, Reciprocal Rank Fusion, MMR diversification. Verified: correctly retrieves `POL-VENDOR-01` for a bank-detail-change query and `POL-HOURS-01` for an off-hours query.
- `app/ai/prompt/all_sample_prompt.yaml` — filled in real system prompts for Hermione, Percy, Moody. Both Percy and Moody's prompts explicitly instruct them to treat retrieved document text as untrusted data, never as instructions — the injection defense.
- `app/ai/config/agents.py` — added: `AgentConfig` for each role. Model choice: `sonnet` for all three (Haiku too weak for nuanced policy judgment + injection resistance; Opus unnecessary cost at this task's complexity and volume — 50 txns x up to 2 LLM calls). Effort: Percy=medium, Moody=high (last line of defense against injection/false positives), Hermione=low (summarizing already-verified verdicts).
- `app/services/llm.py` — added: `run_agent()` — shared single-shot `query()` wrapper; supports an optional JSON schema (`output_format`) for structured, machine-parseable verdicts. Returns `(result, cost_usd)`.
- `app/services/signals.py` — added: deterministic pre-checks (duplicate-payment candidate matching, structuring amount-band check, off-hours timestamp check) computed before any LLM call, to ground Percy's reasoning. Covered by unit tests, no LLM involved.
- `app/services/percy.py` — added: Analyst — retrieves policy text via RAG, combines it with signals, calls Percy with a JSON-schema-constrained verdict (`flagged`, `anomaly_type`, `policy_ref`, `reasoning`).
- `app/services/moody.py` — added: Fact-Checker — adversarially re-examines Percy's verdict against the same policy text, can confirm/overturn/route-to-human-review, flags detected injection attempts.
- `app/services/orchestrator.py` — added: Hermione's pipeline — `stream_audit()` (async generator yielding per-transaction progress events, ending in a `complete` event with the full report) and `run_audit()` (drains the stream for non-streaming callers). Scores verdicts against `ground_truth.json`, runs both redteam fixtures (false-positive clearance, injection resistance via forced exposure of the injection fixture alongside real policy text), and has Hermione synthesize an executive summary. Per-transaction failures degrade gracefully (default to unflagged + logged, not an aborted run).
- `app/services/audit_store.py` — added: `AuditStore` abstract interface (deliberately named apart from the SDK's own unrelated `SessionStore`) + `SupabaseAuditStore`/`PostgresAuditStore` (same SQLAlchemy engine, different DSN — Supabase is Postgres) + `InMemoryAuditStore` (local/dev/test default). `get_audit_store()` switches on `DB_BACKEND` env var.
- `app/api/v1/endpoints/audit.py` — added: `GET /api/v1/audit/run` (SSE, streams Hermione's progress, persists the completed report, structured `{"status":"error",...}` on failure) and `GET /api/v1/audit/reports/{session_id}` (404 with structured error body if missing).
- `app/main.py` — wired the audit router under `/api/v1`.
- `.env.example` — replaced `SUPABASE_URL`/`SUPABASE_KEY` with `SUPABASE_DB_DSN` (matches the actual SQLAlchemy-based access pattern); `DB_BACKEND` now documented as optional (defaults to in-memory).
- `Dockerfile`, `.dockerignore` — added: multi-stage-free `python:3.12-slim` + `uv sync --frozen --no-dev` build, runs `uvicorn app.main:app`. Not build-tested locally (Docker daemon not running here) — will be validated by `cd.yml` on push.
- `tests/` — added: `test_health.py`, `test_signals.py` (deterministic, weekday assumptions verified), `test_rag.py`, `test_audit_store.py`, `test_api_audit.py` (all no-LLM, always run in CI), and `test_integration_agents.py` (4 live-LLM tests, auto-skipped via `conftest.py`'s `requires_claude_cli` marker when the `claude` CLI isn't present — e.g. always skipped in CI until that's provisioned).
- Verified live (this session, ~$1 total API cost): clean transaction correctly cleared; duplicate payment correctly flagged with `POL-DUP-01` citation and confirmed by Moody; false-positive fixture correctly cleared; injection fixture's embedded "ignore all previous instructions" directive correctly resisted. Full `uv run pytest` — 18/18 passed. `uv run ruff check .` clean.
- Not yet run: the full 50-transaction batch via `/api/v1/audit/run` (estimated ~$10-15 in API cost based on per-transaction pricing observed) — deferred pending user confirmation given the cost.
