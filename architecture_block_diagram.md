# Architecture Block Diagram

## End-to-end request flow

```mermaid
flowchart TD
    Client["Client"]
    API["FastAPI\nGET /api/v1/audit/run (SSE)\nGET /api/v1/audit/reports/{id}\nPOST .../verdicts/{id}/correct"]
    AuthGate["Optional AUDIT_API_KEY gate"]
    Hermione["Hermione\n(Orchestrator)\napp/services/orchestrator.py"]

    Client --> API
    API --> AuthGate --> Hermione

    subgraph PerTransaction ["Per transaction (WorkingMemory)"]
        direction TB
        Signals["Static Procedural Memory\napp/services/signals.py\nduplicate / structuring / off-hours checks"]
        Procedural["Dynamic Procedural Memory\nprocedural_insights table\nTTL'd advisories from corrections"]
        Rita["Rita: Semantic Memory retrieval\napp/services/rag.py\nFAISS + BM25 -> RRF -> MMR"]
        Percy["Percy: Analyst\napp/services/percy.py\nschema-constrained verdict"]
        GuardInj["Guardrail: injection pattern check\napp/guardrails/injection.py"]
        Moody["Moody: Fact-Checker\napp/services/moody.py\nconfirm / overturn / route_to_human_review"]
        GuardCite["Guardrail: citation check\napp/guardrails/citation.py"]

        Signals --> Percy
        Procedural --> Percy
        Rita --> Percy
        Percy --> GuardInj
        GuardInj -->|"if flagged"| Moody
        Moody --> GuardCite
        GuardInj -->|"if not flagged"| GuardCite
    end

    Hermione --> PerTransaction
    GuardCite --> Episodic["Episodic Memory\nepisodic_verdicts table"]
    Episodic --> Hermione

    PolicyCorpus["data/policies/*.md\n(5 policy docs)"] --> Rita
    Transactions["data/transactions.json\n(50 transactions)"] --> Hermione
    GroundTruth["data/ground_truth.json"] --> Score["Scoring\naccuracy / false pos / false neg"]

    Hermione --> Score
    Hermione --> Redteam["Redteam fixtures\nfalse_positive_fixture.json\ninjection_policy_fixture.md"]
    Redteam --> PerTransaction

    Score --> Report["AuditReport\n(+ Hermione's executive summary)"]
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
