# Architecture Block Diagram

## End-to-end request flow

```mermaid
flowchart TD
    Client["Client"]
    API["FastAPI\nGET /api/v1/audit/run (SSE)\nGET /api/v1/audit/reports/{id}\nPOST .../verdicts/{id}/correct (requires session_id)"]
    AuthGate["Optional AUDIT_API_KEY gate"]
    Decompose["Hermione: decompose_batch()\napp/services/hermione.py\nonce per run - reads batch + aggregate procedural insights\n-> batch_plan"]

    Client --> API
    API --> AuthGate --> Decompose

    subgraph PerTransaction ["Per transaction (WorkingMemory, incl. batch_plan)"]
        direction TB
        Signals["Static Procedural Memory\napp/services/signals.py\nduplicate / structuring / off-hours checks"]
        Procedural["Dynamic Procedural Memory\nprocedural_insights table\nTTL'd advisories from corrections"]
        Rita["Rita: Semantic Memory retrieval\napp/services/rag.py\nFAISS + BM25 -> RRF -> MMR"]
        Percy["Percy: Analyst\napp/services/percy.py\nschema-constrained verdict"]
        Escalate["Hermione: decide_escalation()\napp/services/hermione.py\nskip_moody / escalate_to_moody\n(replaces a hardcoded rule)"]
        Moody["Moody: Fact-Checker\napp/services/moody.py\nconfirm / overturn / route_to_human_review"]
        GuardEnforce["Guardrails (enforcing, not logging)\napp/guardrails/injection.py + citation.py\nany hit forces flagged=True + records guardrail_flags"]

        Signals --> Percy
        Procedural --> Percy
        Rita --> Percy
        Percy -->|"if flagged"| Escalate
        Escalate -->|"escalate_to_moody"| Moody
        Escalate -->|"skip_moody"| GuardEnforce
        Moody --> GuardEnforce
        Percy -->|"if not flagged"| GuardEnforce
    end

    Decompose --> PerTransaction
    GuardEnforce --> Episodic["Episodic Memory\nepisodic_verdicts table (scoped by session_id)"]
    Episodic --> Hermione["Hermione: synthesize_summary()\nonce at the end"]

    PolicyCorpus["data/policies/*.md\n(5 policy docs)"] --> Rita
    Transactions["data/transactions.json\n(50 transactions)"] --> Decompose
    GroundTruth["data/ground_truth.json"] --> Score["Scoring\naccuracy / false pos / false neg / moody_escalations / moody_skipped"]

    Hermione --> Score
    Hermione --> Redteam["Redteam fixtures\nfalse_positive_fixture.json\ninjection_policy_fixture.md"]
    Redteam --> PerTransaction

    Score --> Report["AuditReport\n(+ batch_plan + Hermione's executive summary)"]
    Hermione --> Report
    Report --> Store["AuditStore\nSupabase / Postgres / InMemory\napp/services/audit_store.py"]
    Store --> API
```

## Config & prompt resolution

```mermaid
flowchart LR
    ModelConfig["config/model_config.yaml\nmodel + effort per agent"]
    PromptConfig["config/prompt_config.yaml\nprompt version per agent"]
    AppConfig["config/app_config.yaml\nRAG params, guardrail toggles"]

    PromptLoader["app/ai/config/prompt_loader.py\nversion fallback -> v1"]
    PromptFiles["app/ai/prompt/&lt;agent&gt;/&lt;version&gt;/prompt.yaml"]
    AgentsPy["app/ai/config/agents.py\nAgentConfig per role"]

    PromptConfig --> PromptLoader --> PromptFiles --> AgentsPy
    ModelConfig --> AgentsPy
    AppConfig --> Rita["Rita (rag.py)"]
    AppConfig --> Guardrails["Guardrail checks (orchestrator.py)"]
```

## Persistence resolution (`DATABASE_URL` priority)

```mermaid
flowchart TD
    Start["get_audit_store()"] --> Backend{"DB_BACKEND"}
    Backend -->|"supabase"| ResolveS["_resolve_dsn(\"supabase\")"]
    Backend -->|"postgres"| ResolveP["_resolve_dsn(\"postgres\")"]
    Backend -->|"unset"| InMem["InMemoryAuditStore\n(local/dev/test default)"]

    ResolveS --> CheckS{"DATABASE_URL set?"}
    CheckS -->|"yes"| UseS["Use DATABASE_URL"]
    CheckS -->|"no"| FallbackS["Use SUPABASE_DB_DSN"]

    ResolveP --> CheckP{"DATABASE_URL set?"}
    CheckP -->|"yes"| UseP["Use DATABASE_URL"]
    CheckP -->|"no"| FallbackP["Use POSTGRES_DSN"]
```
