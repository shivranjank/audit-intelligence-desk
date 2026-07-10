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
