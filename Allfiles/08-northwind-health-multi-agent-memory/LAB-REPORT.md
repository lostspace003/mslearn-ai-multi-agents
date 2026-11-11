# Lab 08 report - Build persistent shared memory for Foundry agents

**Result: PASS.** Every task and acceptance criterion passes. The one exception is the wording of "ascending vector_distance", which is a lab documentation issue (see below). The hosted agent first failed with 401 because its identity had no data-plane roles. After the user approved the role grants and the coordinator applied them, the re-invoke passed.

- Resource group: `rg-lab08-021aff3d`, region `eastus2`, subscription "Visual Studio Subscription"
- Cosmos DB: `coslab08memoryalokeuqq` (serverless, vector search, Session consistency)
- Foundry account: `aiflab08memoryalokeuqq`; project: `northwind-memory-alokeuqq`
- Deployments: `gpt-5.4-mini` (2026-03-17), `text-embedding-3-small` (1)
- Hosted agent: `northwind-health-memory-coordinator:1`, status active

## What was done, per task
| Task | Done |
|---|---|
| 1 Prepare | Tools and az login checked. Architecture reviewed: Cosmos DB is the memory authority, and memory and audit live in separate containers. |
| 2 venv | `scripts/setup.ps1` was run. Python 3.13 venv created. |
| 3 Deploy | **Azure CLI instead of azd provision**: `az bicep build`, then the `deploy_lab.py` helper (`az deployment group create`) wrote `.env`. All required keys are present. No keys or secrets are stored. |
| 4 Implement | All 6 LAB PLACEHOLDERs filled from the md, re-indented from 2 to 4 spaces, with the markers kept. Preflight: `Preflight passed`. |
| 5 Run | ingest, recall, consistency, prune --dry-run, consolidate dry-run and apply: `artifacts-lab08-run.txt`. Local agent: `artifacts-lab08-agent-local.txt`. Hosted deploy and invoke: `artifacts-lab08-agent-hosted.txt`. |
| 6 Validate | Consolidate retry and prune apply are in `artifacts-lab08-run.txt`. Portal Data Explorer and Foundry checks were replaced by SDK/az reads in `artifacts-lab08-cosmos-inspect.txt`. |
| Optional challenge | Done: `artifacts-lab08-challenge.txt` (details below). |
| 7 Design review | `design-review.md` |
| 8 Clean up | **Not run**, per the brief. Resources, `.env` and the azd env are kept. |

For azd agent commands, an azd env `lab08-memory-dev` (in `.azure/`) was filled from `.env` using `azd env set`. `azd provision` was **not** used. Provisioning was done with the Azure CLI only. azd was used only for `azd ai agent run/invoke` and `azd deploy memory-coordinator`.

## Acceptance criteria
| Criterion | Result | Evidence |
|---|---|---|
| ingest reports ID, patientId, RU and session token, with no content | PASS | mem-100-1..5, about 25.5 RU each, tokens `0:-1#3..#7`. mem-200-1 is correctly skipped because the store is bound to patient-100. |
| recall returns only patient-100 records | PASS | 5 records, all `synthetic-patient-100` |
| recall `vector_distance` ascending | **FAIL as worded (lab doc issue, not a code bug)** | Values are 0.452, 0.435, 0.398, 0.373, 0.315, which is *descending*. The container uses `distanceFunction: cosine`. For cosine, Cosmos `VectorDistance` returns a **similarity** score, and `ORDER BY VectorDistance` returns the most similar result first. So the ordering is correct, but the field name and the lab text ("ascending") are misleading. A side effect: `context_budget` uses `1/(1+distance)`, which slightly favours *less* similar records. The md code was left unchanged. |
| each record has the same query `request_charge` | PASS | 3.3 RU on every record |
| `bounded_context.token_count` <= 500 | PASS | 132 tokens; 5 selected IDs |
| consistency: write_id == read_id, token transferred, RU reported | PASS | `consistency-1794403465.588119`, `session_token_transferred: true`, 25.51 RU |
| prune dry-run: dry_run, deleted_count 0, eligible IDs, critical kept | PASS | eligible mem-100-3/4/5. mem-100-2 (critical, ttl -1) and mem-100-1 (importance 7) are not eligible. |
| consolidation dry-run: 3 sources, no writes | PASS | `source_count: 3`, `semantic-c6b8c2798801c14c` |
| consolidation apply: consolidated, semantic ID, 3 sources, batch diagnostics | PASS | `transactional_batch: true`, `operation_count: 4` |
| Retry gives `already_consolidated` with no duplicate | PASS | Same semantic ID and sources. The audit event `audit-semantic-c6b8c2798801c14c` is idempotent. |
| prune apply: applied, nonzero deleted_count | PASS | `deleted_count: 3`. Reads now return 404 for mem-100-3/4/5. |
| `retention_prune` audit has patientId, operation, IDs, reason and timestamp, with no content or embedding | PASS | audit `a83d1462-02da-4d65-bdb6-19ab6c652b56`, `has_content_or_embedding: false` |
| Persisted memory has the schema fields and a 1536-dim embedding | PASS | mem-100-1 has every field; `embedding_dimensions: 1536`; policy is 1536 float32 cosine with a quantizedFlat index |
| Semantic doc: sourceMemoryIds = 3 sources, reviewerId reviewer-07 | PASS | `semantic-c6b8c2798801c14c` |
| All 3 sources hold the same `consolidatedInto` | PASS (indirect) | These were not dumped before pruning. However, `already_consolidated` is only returned when *every* source's `consolidatedInto` equals the semantic ID, so the retry proves it. The sources were then pruned on purpose, as Task 6 requires. |
| Foundry deployments exist and the agent has a deployed version | PASS | `az cognitiveservices account deployment list` shows both Succeeded; agent version 1 is active |
| Local agent calls `recall_patient_memory`, cites IDs and stays grounded | PASS | Server log has `Function recall_patient_memory succeeded`. The answer cites semantic-c6b8..., mem-100-5/4/3/1 and says which evidence is missing. |
| Deployed agent calls `recall_patient_memory`, cites IDs and stays grounded | PASS (after role grant) | First invoke: 401, because the hosted agent runs as its own instance identity `10d585ec-ba6a-414a-91f6-593a1a245c2e`, not the project managed identity that the Bicep grants roles to. After the user-approved grants (Cognitive Services OpenAI User on the Foundry account and Cosmos Built-in Data Contributor), the re-invoke succeeded: hosted log shows `Function recall_patient_memory succeeded` with embeddings 200 OK. Response `caresp_0897f5c9ee7950fa00969KnfRnWgOeitpZSVUB6njBrB9bO0Vr` cites semantic-6de83a71c0d6fac6, mem-100-c1, semantic-c6b8c2798801c14c, mem-100-1 and mem-100-c3, and marks the low-confidence c3 as unreliable. |
| `_authorize` raises `PermissionError` before embedding or I/O | PASS (code review) | It is the first statement in upsert, recall, audit and consolidate, and in prune via `store._authorize` |

## Code changes and deviations
- The 6 placeholders were filled exactly from the md. No fixes to the shipped code were needed.
- `azd ai agent run` (extension 1.0.0-beta.23) could not find the entry point from `codeConfiguration.entryPoint`, so it was run with `--start-command "python agent.py"`.
- In Git Bash, `azd env set` turned the ARM IDs into `C:/Program Files/Git/subscriptions/...`. They were re-set with `MSYS_NO_PATHCONV=1`; this only affects the local azd env.
- The optional challenge added an optional `min_confidence` parameter to `consolidate_episodic_memories` and `--min-confidence` to `src/main.py`, plus `assets/challenge-memories.json`. Behaviour is unchanged when the flag is not passed. Result at threshold 0.8: c1 (0.92) and c2 (0.85) were consolidated into `semantic-6de83a71c0d6fac6`, which records `confidenceThreshold` 0.8, `rejectedSourceIds` [c3] and reviewer-07. c3 (0.40) is kept with no `consolidatedInto`. A repeat run returned `already_consolidated` thanks to the deterministic ID, so there is no duplicate.
- The challenge records (mem-100-c1/c2/c3 and the semantic record) remain in Cosmos, along with the consistency record (ttl 3600).

## Left for the user
1. Done: the role grants for the hosted agent identity were approved by the user and applied by the coordinator. This is a gap in the lab's Bicep: it should grant these roles to the agent instance identity, not only to the project identity.
2. Portal visual checks (Data Explorer, Foundry agent page) are optional. Equivalent SDK and az evidence is in `artifacts-lab08-cosmos-inspect.txt`.
3. Task 8 cleanup (`az group delete -n rg-lab08-021aff3d`, or `azd down`) was not run on purpose.
