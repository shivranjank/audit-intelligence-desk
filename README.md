# LVAgenticAI Final Project — Policy-Grounded Transaction Audit Agent

Multi-agent system built on the Claude Agent SDK, exposed via FastAPI (WebSocket/SSE), that audits expense/payment
transactions against written internal policies — and is evaluated for both accuracy and adversarial robustness
(prompt-injection resistance, false-positive avoidance).

## Agents

| Name | Role |
|---|---|
| Hermione | Editor-in-Chief — orchestrates the audit run, delegates per transaction, synthesizes the final report |
| Rita | Policy Retrieval — pulls the relevant policy section per transaction via RAG (hybrid search + RRF + MMR) |
| Percy | Analyst — applies rule logic per policy (duplicate-payment matching, structuring bands, off-hours timestamps, vendor-detail timing, approver-vendor conflicts) |
| Moody | Fact-Checker — resists prompt injection, clears documented false positives, requires a policy citation before any flag stands |

## Data (`data/`)

- `transactions.json` — 50 synthetic transactions to audit
- `ground_truth.json` — expected verdicts (40 clean, 10 anomalies across 5 types)
- `policies/*.md` — 5 internal policy documents the agents must ground every verdict in
- `redteam/false_positive_fixture.json` — a compliant edge case that must **not** be flagged
- `redteam/injection_policy_fixture.md` — a fake policy doc containing a prompt-injection attempt the agents must resist

See `changelog.md` for a per-file history of changes.
