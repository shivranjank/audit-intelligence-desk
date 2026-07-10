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

## Session 2026-07-10 — Code review fixes

Fixed the 5 issues found by the code review of Phase 1-6 (`/code-review` against this branch). Fix 1 mandatory (user-approved); fixes 2-5 optional/best-effort (all applied — none felt like overreach).

- `app/services/moody.py` — **fixed (mandatory)**: `review()` was computing `"flagged": verdict.flagged and decision == "confirm"`, which cleared `flagged` whenever Moody chose `"route_to_human_review"`. But POL-APPROVER-01 (`data/policies/approver_relationship_policy.md`) explicitly directs approver-vendor conflicts to be routed to human review rather than confirmed as fraud, so Moody legitimately returns `route_to_human_review` for the `unusual_approver_pairing` ground-truth cases (TXN-0049/TXN-0050) — those were silently scored as unflagged in `_score()`, undercounting accuracy for cases the system correctly surfaced. Extracted the decision into a pure `_resolve_flagged(original_flagged, decision) -> bool` helper: `return original_flagged and decision != "overturn"` — both `"confirm"` and `"route_to_human_review"` now keep `flagged` as-is; only `"overturn"` clears it. `confirmed_by_moody` is unchanged (`decision == "confirm"`), so it still distinguishes "fully confirmed" from "flagged but routed to human." Reasoned through (and confirmed via a live rerun) that the false-positive redteam path is unaffected: its correct outcome is `"overturn"`, which still clears `flagged` under the new logic.
- `tests/test_moody.py` — added: parametrized unit test for `_resolve_flagged` covering all 3 `MoodyDecision` values x both `original_flagged` states (6 cases). Pure logic, no LLM call, always runs (not gated by `requires_claude_cli`).
- `app/api/v1/endpoints/audit.py` — fixed (optional #2): `GET /api/v1/audit/run` had no auth and triggers a ~$10-15 LLM batch run on any request. Added an optional shared-secret gate: if the `AUDIT_API_KEY` env var is unset, behavior is unchanged (no auth, current local/dev default); if set, callers must send a matching `X-Audit-Api-Key` header or get a structured 401. Also added a docstring on the endpoint spelling out the cost and exposure risk.
- `.env.example` — added: documented the new optional `AUDIT_API_KEY` var.
- `app/services/orchestrator.py` — fixed (optional #3): `stream_audit()` was constructing a fresh `PolicyRAG()` and calling `build_index()` (loads the embedding model, ~3-4s) on every call instead of once per process. Added `get_policy_rag()`, an `lru_cache(maxsize=1)`-wrapped builder, and pointed `stream_audit()` at it. Works for both the FastAPI app and tests that call `stream_audit()`/`_audit_one()` directly, since the cache is process-wide, not tied to a lifespan hook.
- `app/services/orchestrator.py` — fixed (optional #5): `_run_injection_redteam`'s `next(t for t in transactions if t.transaction_id == "TXN-0047")` had no default and would raise an opaque `StopIteration`/`RuntimeError` if that transaction were ever missing from `data/transactions.json`. Added a `None` default and a clear `ValueError` with the transaction ID and file it expects it in.
- `app/services/llm.py` — fixed (optional #4): `run_agent()` silently returned `("", 0.0)` if `query()` never yielded a `ResultMessage` (e.g. an edge-case process failure), which surfaced downstream as a confusing `TypeError` (indexing a string) rather than a clear error. Now tracks whether a `ResultMessage` was ever seen and raises `RuntimeError` with a clear message if not.
- Verified: `uv run ruff check .` clean. `uv run pytest` — 24/24 passed (18 pre-existing + 6 new `test_moody.py` cases), including all 4 live-LLM integration tests (~$1 total cost, same as prior sessions). One live-LLM redteam test failed on a first pass due to inherent LLM judgment variance on an edge-case fixture (Moody chose "confirm" over "overturn" for a borderline structuring/off-hours case) — unrelated to the code changes (both old and new `flagged` logic agree when `decision == "confirm"`) — and passed cleanly on rerun, confirmed flaky rather than regressed.

## Session 2026-07-10 — Phases 7-12 (config/prompt restructuring, memory tiers, guardrails)

Research phase (a Plan-only agent, no code changes) explored the user's reference project
(`../29062026/The Secure Agent`) to ground these additions in a proven pattern rather than
inventing one from scratch — see that agent's findings for the exact prompt-loader,
memory-tiering, and guardrails conventions adopted here.

**Phase 7 — Config & prompt restructuring**
- `app/ai/prompt/{hermione,percy,moody}/v1/prompt.yaml` — added: one YAML file per agent per version (`name`/`version`/`description`/`system` keys), replacing the single `app/ai/prompt/all_sample_prompt.yaml` (removed).
- `app/ai/config/prompt_loader.py` — added: `load_prompt(agent_name)` with version-fallback (configured version → `v1`), driven by `config/prompt_config.yaml`.
- `config/model_config.yaml`, `config/prompt_config.yaml`, `config/app_config.yaml` — added (root-level, 3-way split as requested rather than the reference project's single-file pattern): per-agent model/effort, per-agent prompt version, and RAG/guardrail parameters respectively.
- `app/ai/config/agents.py` — rewritten to build each `AgentConfig` from `model_config.yaml` + `prompt_loader.load_prompt()` instead of a direct single-file `yaml.safe_load`.
- `app/services/rag.py` — `SEMANTIC_CHUNK_THRESHOLD`, `EMBED_MODEL_NAME`, and `retrieve()`/`_mmr()`'s default `k`/`rrf_k`/`fetch_n`/`mmr_lambda` now read from `config/app_config.yaml`'s `rag` section instead of hardcoded literals.
- Verified: agent configs and RAG retrieval both load and work correctly from the new config files.

**Phase 8 — Working Memory**
- `app/models/schemas.py` — added `WorkingMemory` (transaction, signals, policy_chunks, procedural_insights, percy_verdict, moody_verdict), replacing implicit function-argument passing between Percy and Moody.
- `app/services/percy.py`, `app/services/moody.py` — refactored `analyze()`/`review()` and their `build_prompt()`s to take and mutate a single `WorkingMemory` object in place, returning just the call cost.

**Phase 9+10 — Episodic + Procedural Memory (reuses the existing Postgres/Supabase infra, per user's explicit choice — no third persistence mechanism)**
- `app/services/audit_store.py` — added `EpisodicVerdictRecord`/`ProceduralInsightRecord` SQLAlchemy tables and `record_episode()`/`get_episodes()`/`record_correction()`/`save_procedural_insight()`/`get_active_procedural_insights()` on `AuditStore` (both the SQL-backed and `InMemoryAuditStore` implementations).
- `app/services/procedural.py` — added `synthesize_insight()`: a pure function that derives a TTL'd advisory (7 days) from a vendor's corrected-false-positive history (needs 2+ corrections of the same anomaly_type before it fires) — the dynamic Procedural Memory tier. Static Procedural Memory remains `app/services/signals.py`, unchanged.
- `app/services/orchestrator.py` — `_audit_one()` now fetches active procedural insights for the transaction's vendor before analysis, and records an `EpisodicEntry` (including Moody's raw decision) after every transaction. `_refresh_procedural_insights()` re-synthesizes insights per unique vendor at the start of each run (no-op until corrections accumulate). Redteam fixture runs are intentionally *not* recorded to Episodic Memory (synthetic data, not real vendor history).
- `app/models/schemas.py` — added `EpisodicEntry`, `ProceduralInsight` models; added `moody_decision: str | None` to `Verdict` so the raw decision (not just the `confirmed_by_moody` bool) is available for episodic recording.
- `app/api/v1/endpoints/audit.py` — added `POST /api/v1/audit/verdicts/{transaction_id}/correct` so a human reviewer can record a correction, which feeds the next run's procedural insight synthesis.

**Phase 11 — Guardrails**
- `app/guardrails/` — added: `pii.py::scrub_pii()` (redacts email/phone/account-number-shaped patterns, applied to correction notes before persistence), `injection.py::detect_injection()` (regex pre-check on retrieved policy text, logs a warning — supplements, does not replace, the existing prompt-level anti-injection instructions), `citation.py::verify_citation()` (rejects/routes-to-human-review a flagged verdict whose `policy_ref` doesn't actually appear in the retrieved chunks — anti-hallucinated-citation check).
- `app/services/orchestrator.py::_apply_guardrails()` — wires both checks in after Percy/Moody's verdict, gated by `config/app_config.yaml`'s `guardrails.injection_check_enabled`/`citation_check_enabled`.

**Phase 12 — `DATABASE_URL`**
- `app/services/audit_store.py::_resolve_dsn()` — `DATABASE_URL` now takes priority if set, falling back to `SUPABASE_DB_DSN`/`POSTGRES_DSN` per `DB_BACKEND` — all three vars kept, per user's explicit choice.
- `.env.example` — added `DATABASE_URL` with a safe placeholder shape (`postgresql://postgres:<password>@localhost:5433/<dbname>`) and a comment noting it's never a real committed credential.

**Tests added**: `test_procedural.py` (4 cases, pure), `test_guardrails.py` (7 cases, pure), 4 new cases in `test_audit_store.py` (episodic/procedural round-trips, PII scrubbing on correction notes) — all deterministic, no LLM. Updated `test_integration_agents.py` call sites for the new `_audit_one(..., store)`/`_run_false_positive_redteam(..., store)` signatures.

**Verified**: `uv run ruff check .` clean. `uv run pytest --ignore=tests/test_integration_agents.py` — 34/34 passed. `uv run pytest tests/test_integration_agents.py` (live-LLM, ~$1) — 4/4 passed against the fully refactored pipeline (WorkingMemory, Episodic Memory recording, guardrails all active).
