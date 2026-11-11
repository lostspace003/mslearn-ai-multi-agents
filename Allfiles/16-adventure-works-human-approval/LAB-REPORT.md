# Lab 16 - Implement durable human approval workflows - LAB REPORT

**Result: PASS** (all runnable tasks and acceptance criteria met; portal-only viewing replaced by az CLI equivalents)

- Resource group: `rg-lab16-fbdf8faa` (subscription "Visual Studio Subscription"), region **eastus2**
- Resources: Cosmos DB `awapprovalawhwfwl7x6qsc` (serverless, local auth disabled; db `approvals`, containers `workflow-state`, `approval-audit`), Service Bus `awapproval-awhwfwl7x6qsc` (Standard, local auth disabled; queues `approval-requests`, `approval-decisions` with duplicate detection)
- Provisioned with Azure CLI (`deploy_lab.py` -> `az deployment group create`) instead of azd. The Bicep already grants Cosmos Built-in Data Contributor and Azure Service Bus Data Owner to the signed-in user. `.env` contains only endpoints/names (no keys).
- Resources retained; Task 8 cleanup deliberately **not** run (per instructions).

## Tasks

| Task | Done |
|---|---|
| 1 Prepare | Tools verified (az, python 3.13, bicep). azd not used (CLI substitution). |
| 2 venv | `scripts/setup.ps1` -> `.venv` |
| 3 Deploy | `az bicep build` OK; deployment succeeded; `.env` written with COSMOS_ENDPOINT, COSMOS_DATABASE, STATE/AUDIT_CONTAINER, SERVICE_BUS_NAMESPACE, REQUEST/DECISION_QUEUE, principal values |
| 4 Implement | Placeholders 1-6 filled in `src/workflow.py` and `src/main.py` (calibration, calibrated risk, idempotent audit, CANCELLED branch, CLI `cancelled`, durable escalation). py_compile silent; `preflight --require-complete` all `ready` (`artifacts-preflight.txt`) |
| 5 Run | submit/status/decide/resume/escalate/webhook/active_learning run end-to-end (`artifacts-lab16.txt`, driver `run16.sh`) |
| 6 Validate | `validate16.py` -> `artifacts-validation.txt`; Azure state + metrics -> `artifacts-azure-state.txt` |
| Optional challenge | Reviewer band + replay test (`challenge16.py` -> `artifacts-challenge.txt`) |
| 7 Review | `design-review.md` (also contains the Durable Functions comparison, Task 6 steps 15-18) |
| 8 Clean up | Skipped intentionally (keep resources, .env, artifacts) |

## Workflow IDs (synthetic)

| ID | Path | Final state |
|---|---|---|
| 72ec1293-7ec7-4c35-a3d5-b4579e86e21a | approved, then duplicate approval | EXECUTED (2nd resume -> `duplicate: true`) |
| f573a4d5-e0f3-4101-bcf0-818ceab38b9f | rejected | REJECTED, execution null |
| cf061d75-0d22-4311-9e0f-62911c7c9853 | overridden | EXECUTED (`completed_after_override`) |
| efa66631-84d2-4454-8d3a-ff7978172bf0 | cancelled | CANCELLED (`cancelled_before_execution`, executed_at null) |
| d4a546b8-afb6-46a7-b19a-f4a7ebcda80d | overdue (timeout 0 min) -> `escalate` | ESCALATED |
| 137515d4-8bed-4088-ae6a-bc300ff27dae | webhook POST -> resume | EXECUTED |
| 47f371bb-... / af3ef65a-... | optional challenge bands | WAITING_FOR_REVIEW (tier1) / EXECUTED (senior) |

Risk evidence for the supplied request: raw 0.91 -> calibrated 0.78 (nearest curve point), `exception` tier, required 1.0 -> `WAITING_FOR_REVIEW`.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Compile silent; preflight all ready after provisioning | PASS | `artifacts-preflight.txt` |
| State durable across restarts | PASS | every CLI command is a new process; `status`/`resume` read state written by earlier processes; validate16 re-reads all 8 records from Cosmos |
| Every audit record (submitted, duplicate, decision, escalation) has workflow ID, event ID, UTC timestamp, actor hash, previous/new state, rationale category, policy version, trace ID, state_etag, state_version | PASS | 16 audit records {submitted 8, decision_applied 6, duplicate_decision 1, escalated 1}; missing/non-UTC: none (previous_state null only for `submitted`) |
| State linked to audit (last_transition event_id -> audit record with same etag + version) | PASS | unlinked: none |
| Webhook returns 202 `status: queued`; unauthenticated -> 401 | PASS | `HTTP 202` `{"status":"queued",...}`; no principal header -> `HTTP 401` |
| Decision queue count increases after POST, decreases after resume, linked audit event | PASS | approval-decisions active 0 -> 1 -> 0; workflow 137515d4 EXECUTED with decision_applied audit |
| Service Bus metrics observable | PASS | IncomingMessages requests 7 / decisions 6; CompleteMessage decisions 6 (`artifacts-azure-state.txt`) |
| Approved+executed, rejected+closed, overridden+executed, overdue+escalated demonstrated | PASS | table above |
| Active-learning file counts match Cosmos rejected/overridden | PASS | Cosmos {REJECTED 1, OVERRIDDEN 1} = jsonl 2 lines = evaluation decision_counts |
| No execution from pending/rejected state | PASS | executions from WAITING/REJECTED/ESCALATED/CANCELLED: none |
| Azure resources: Cosmos account, `approvals` db + 2 containers, SB namespace + 2 queues | PASS (az CLI instead of portal) | `artifacts-azure-state.txt` |
| Optional: band records threshold + reviewer group, correct durable state; replay after timeout does not duplicate action/audit | PASS | near_threshold/0.75/SYN-REVIEW-TIER1 and low_confidence/0.0/SYN-REVIEW-SENIOR; replay of same event -> `duplicate: true`, executed_at unchanged, version 2, audit count unchanged (2) |

## Deviations / changes

- azd replaced by Azure CLI deployment (per brief).
- `LAB PLACEHOLDER` comments removed (the lab text says to remove them and `preflight --require-complete` requires zero markers in `src/`).
- md snippets used 2-space indent; inserted with the file's 4-space indent.
- Added synthetic test payloads `assets/refund-request-overdue.json` (timeout 0 min, to show the escalation path without waiting 30 min) and `assets/refund-request-lowband.json` (optional challenge).
- Optional challenge: added `REVIEWER_BANDS` / `select_reviewer_band()` to `src/workflow.py`; `assess_risk()` now also returns `review_band`, `band_threshold`, `reviewer_group`.
- Helper scripts in lab folder: `run16.sh`, `validate16.py`, `challenge16.py`.
- No shipped-code bugs found. Note: `approval-requests` has 9 active messages left by design (no consumer in this lab; it feeds a reviewer surface). The webhook only accepts APPROVED/REJECTED/OVERRIDDEN (CANCELLED goes through the CLI), which is how the lab ships it.
- Nothing was blocked by permissions.

## Left for the user

- Portal view of resources/metrics (optional; az CLI equivalents done).
- Optional Teams / Power Automate reviewer surface (not provisioned by the lab).
- Task 8 cleanup when you're finished: `az group delete -n rg-lab16-fbdf8faa` (and remove `.env`).
