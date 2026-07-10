# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Skill restrictions

Do not invoke the `/product-review` skill on this codebase, even if it seems applicable to a request. This
has been explicitly opted out of for this project.

## Commands

```bash
uv sync                                                # install deps
cp .env.example .env                                   # then fill in ANTHROPIC_API_KEY / DB settings

uv run uvicorn app.main:app --reload                   # run the dev server

uv run ruff check .                                    # lint

uv run pytest --ignore=tests/test_integration_agents.py  # deterministic tests - free, always safe
uv run pytest tests/test_integration_agents.py         # live-LLM tests - costs real money (~$1/run);
                                                        # auto-skip if the `claude` CLI isn't installed/authenticated

uv run pytest tests/test_signals.py::test_structuring_band  # single test
uv run pytest -k "<keyword>"                           # pattern-based selection
```

## Architecture

This is a multi-agent transaction-audit system on the Claude Agent SDK + FastAPI. The pieces below require
reading multiple files to piece together — see `README.md`, `ADR.md`, and `architecture_block_diagram.md`
for the full picture; this section is the parts that aren't obvious from any single file.

**The pipeline is not as symmetric as the "4-agent" framing suggests.** Percy (`app/services/percy.py`) is
the only agent that makes an unconditional LLM call on every transaction. Moody (`app/services/moody.py`)
only runs when a hardcoded rule fires (`if verdict.flagged:` in `orchestrator.py::_audit_one`) — not an
agent decision. Rita (`app/services/rag.py`) makes zero LLM calls; she's a pure FAISS+BM25+RRF+MMR
retrieval function. Hermione's only LLM call today is the closing executive summary
(`orchestrator.py::_synthesize_summary`), written after every real decision is already locked in. Don't
assume symmetry between the four from naming alone — see GitHub issue #8 for the in-progress plan to give
Hermione real per-transaction and per-batch decision authority.

**`WorkingMemory`** (`app/models/schemas.py`) is the object threaded through Percy → Moody, replacing
implicit function-argument passing. The five memory tiers are scattered across files with no single entry
point: static procedural = `app/services/signals.py`, semantic = `app/services/rag.py`, episodic =
`app/services/audit_store.py` (`episodic_verdicts` table), dynamic procedural =
`app/services/procedural.py` + `procedural_insights` table. Sensory buffer and working memory are not
persisted — they're the raw transaction and the `WorkingMemory` object's lifetime within one `_audit_one`
call.

**Config resolution chain**: `config/model_config.yaml` (per-agent model/effort) + `config/prompt_config.yaml`
(per-agent prompt version) feed `app/ai/config/prompt_loader.py`'s version-fallback logic (configured
version → `v1`), which loads `app/ai/prompt/<agent>/<version>/prompt.yaml`. `config/app_config.yaml` holds
RAG/retrieval parameters and guardrail toggles, read directly by `rag.py` and `orchestrator.py`.

**`DATABASE_URL` takes priority** over `SUPABASE_DB_DSN`/`POSTGRES_DSN` in `audit_store.py::_resolve_dsn` —
all three vars are kept (not a breaking rename); precedence isn't obvious from any single call site.

**Caching asymmetry is deliberate**: `get_policy_rag()` (`orchestrator.py`) is process-cached via
`lru_cache` since building the FAISS index loads an embedding model (~3-4s). `get_audit_store()` is
deliberately *not* cached the same way — tests monkeypatch `DB_BACKEND` and expect a fresh read each call.
Don't "fix" this asymmetry without checking `tests/test_audit_store.py` first.

**Known open gaps**, tracked as GitHub issues rather than code comments:
- #6 — the injection-detection guardrail (`app/guardrails/injection.py`) only logs a warning; it never
  actually gates or overrides a verdict. There is no structural backstop if an injection ever succeeds.
- #7 — `record_correction()` (`audit_store.py`) resolves "most recent episode for this transaction_id,"
  which can silently attach a human correction to the wrong audit run if `/api/v1/audit/run` is re-triggered
  between review and correction.
- #8-#12 — the roadmap toward a genuine multi-agent system (Hermione decompose/escalation authority, Rita
  as an MCP tool, inter-agent retrieval requests, adaptive per-transaction pipeline depth, a portfolio-level
  cross-transaction agent).

**Redteam fixtures** (`data/redteam/`) are wired into `orchestrator.py::_run_false_positive_redteam` /
`_run_injection_redteam`, which reuse `_audit_one`'s pipeline but force-expose the injection fixture
alongside real policy chunks rather than relying on retrieval ranking to surface it.
