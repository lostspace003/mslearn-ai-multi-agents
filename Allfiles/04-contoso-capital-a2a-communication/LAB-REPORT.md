# Lab 04 - Contoso Capital A2A communication: run report

**Result: PASS** (all runnable tasks and acceptance criteria met; portal UI views replaced by SDK/CLI equivalents)

- Resource group: `rg-lab04-339fd13d` (subscription "Visual Studio Subscription")
- Region: `eastus2`
- Resources: Foundry `fdrys2sx7bnj3e4nk` (project `lab04-lab04`, model deployment `gpt-5.4-mini` 2026-03-17),
  Cosmos DB `cosmoss2sx7bnj3e4nk` (db `agent-ecosystem`), App Insights `appi-lab04-s2sx7bnj3e4nk`, Log Analytics (30 days)
- Provisioned with Azure CLI (`az deployment group create` via the deploy helper) in place of `azd`; `.env` generated
  with no keys or connection strings. Resources are kept (Task 8 clean-up was not run, as instructed).

## Tasks

| Task | What was done | Evidence |
|---|---|---|
| 1 Prepare | Tools checked; I reviewed the Bicep and source files (tenant PK `/tenantId`, registry TTL 300, tasks/audit TTL -1, ETag update path, Foundry invocation) | `infra/main.bicep` |
| 2 venv | `scripts/setup.ps1` → `.venv` | packages installed (azure-ai-projects 2.10.0, azure-cosmos 4.17.1) |
| 3 Deploy | Azure CLI deployment. `.env` contains COSMOS_ENDPOINT, FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_PROJECT_ID, FOUNDRY_MODEL_NAME, APPLICATIONINSIGHTS_RESOURCE_ID, LOG_ANALYTICS_WORKSPACE_ID | Foundry publicNetworkAccess=Enabled, defaultAction=Allow; Cosmos publicNetworkAccess=Enabled, disableLocalAuth=true. The Cosmos data-contributor role comes from the Bicep |
| 4 Implement | Placeholders 1-5 filled from the lab snippets | py_compile OK; preflight 4x PASS; 5 `LAB PLACEHOLDER` markers kept (4 registry.py + 1 a2a_server.py); no `NotImplementedError` |
| 5 Run | Card registered, uvicorn started on 127.0.0.1:8000 (background), then the client commands were run | `artifacts-lab04-register.txt`, `artifacts-lab04-task5.txt`, `artifacts-lab04-uvicorn.log` |
| 6 Validate | Syntax, agent card, send, ETag/state script, new-process persistence, Cosmos item checks, cross-tenant rejection, trace check | `artifacts-lab04-task6.txt`, `artifacts-lab04-task6b.txt`, `artifacts-lab04-foundry.txt`, `artifacts-lab04-traces.txt` |
| Optional challenge | Two writers with the same starting ETag, then conflict decision and audit. Stale ETag resubmitted | `artifacts-lab04-challenge.txt` |
| 7 Review | Answers written | `design-review.md` |
| 8 Clean up | Uvicorn stopped. `azd down` **not** run (resources kept, as instructed) | - |

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| register returns id/tenant/health/ttl/heartbeat | PASS | `risk-east-v1`, `contoso`, `healthy`, `ttl 300`, heartbeat 1794403529 |
| HTTP log: `/`, agent card, `/a2a` return 200 | PASS | uvicorn log shows 200 OK for all three |
| Readiness | PASS | `status: ready`, `/.well-known/agent-card.json`, `/a2a` |
| Agent card | PASS | `contoso-risk-agent`, `url http://127.0.0.1:8000/a2a`, no Cosmos/Foundry endpoint or secret |
| Discovery returns one healthy `risk-analysis` doc for contoso | PASS | one doc, `risk-east-v1` |
| Send: JSON-RPC 2.0, `request-001`, tenant contoso, response_id, risk text | PASS | `resp_01415204a6d935e7006af46cf053dc81948e4ba7c6dbc09da9` (Task 5), `resp_0298df934bcee748006af46d0915788197a57fd3abc98e0eb9` (Task 6) |
| Stale write rejected with 412 | PASS | `stale_write_rejected: 412` |
| first/second/recovered ETags populated and all different | PASS | `3b000b12…`, `3b002312…`, `3b003012…` |
| Decision priority / compliance-agent / audit_id | PASS | audit_id `ad793c4d-b5cc-4be7-830b-fe148db81a66` |
| Persistence in a new process; 3 contributions; no `stale_writer` | PASS | risk-agent, compliance-agent, supervisor-agent; `stale_writer_present: False`; current_etag = recovered_etag |
| Foundry agent version exists | PASS | `contoso-risk-agent` version 1 (SDK `agents.list_versions`) |
| Server-side trace for the response_id with agent name, version, success, timing | PASS | App Insights `dependencies`: `invoke_agent contoso-risk-agent:1`, success=True, about 1.5 s, gen_ai.response.id matches both response IDs |
| Registry item fields in Cosmos (Data Explorer) | PASS (SDK) | tenantId contoso, healthy, heartbeat, ttl 300, A2A URL |
| task-001 item in Cosmos | PASS (SDK) | 3 contributions, no stale_writer |
| Audit item in Cosmos | PASS (SDK) | resolution `priority`, chosenAgent `compliance-agent` |
| Cross-tenant request returns `{"detail": "Tenant is unavailable"}` with no response_id | PASS | client output |
| Uvicorn logs `POST /a2a` 400 Bad Request | PASS | uvicorn log |
| Rejected request makes no Foundry trace and no cross-tenant Cosmos result | PASS | exactly 2 `invoke_agent` spans, one per accepted request; `fabrikam` partitions in registry, tasks and audit are empty |
| Optional: one of two same-ETag updates wins, one conflicts; audit holds both proposals | PASS | risk-agent succeeded, compliance-agent got 412; decision audit `429b0ae3-ba6d-4a67-a6b8-9fea3987f596`; proposals audit `f33b3165-322b-434f-898c-661a443e4dbf` (task `task-challenge-001`, tenant contoso only) |

## Deviations and fixes
- No changes to the lab code were needed. All 5 placeholders use the lab snippets verbatim, re-indented to 4 spaces.
- I used Azure CLI in place of `azd` (as the user asked). On Windows the Task 6 here-string scripts ran as `python -` with stdin from
  scratchpad copies of the same code. The persistence script adds one extra line that prints `stale_writer_present`.
- I checked the portal steps through the SDK/CLI instead: Cosmos Data Explorer with Cosmos SDK reads, and Foundry Traces with an App Insights
  KQL query (`az monitor app-insights query`).
- Optional challenge: the lab's `resolve_and_audit` stores only agent IDs and roles. A second audit item (`type:
  concurrent-proposals`) records both proposed values. I wrote it from a scratchpad script; the lab code was not changed.
- The agent version stays at 1 across both sends because the definition did not change.

## Left for the user
- Optional visual checks in the portal: Foundry **Agents > Traces** (search for the response IDs above) and Cosmos **Data Explorer**.
  The registry item expires about 5 minutes after the last register. Run `python -m src.main register --card assets/risk-agent-card.json` again to see it.
- When you are finished, delete resource group `rg-lab04-339fd13d` (Task 8), which was deliberately not done here.
