# Lab 03 report: Task decomposition and agent collaboration (Contoso Capital)

**Result: PASS**. All tasks were completed with live Foundry runs. Only the portal UI clicks were replaced with CLI/REST/KQL equivalents. Cleanup (Task 8) was skipped as instructed.

- **Resource group:** `rg-lab03-bb4dd21c`
- **Region:** eastus2
- **Subscription:** Visual Studio Subscription
- **Foundry account:** `fdry2oor6hpbx2yki`
- **Project:** `lab03-lab03-bb4dd2`
- **Model deployment:** `gpt-5.4-mini` (2026-03-17)
- **Provisioning:** Azure CLI (`az deployment group create` via the `deploy_lab.py` helper) instead of `azd`. The helper generated `.env` (no keys or secrets).

## Tasks

| Task | What was done |
|---|---|
| 1 Prepare | Reviewed `infra/main.bicep`, `assets/research-query.json`, `src/main.py`. Az CLI is logged in and Python is 3.13 (the venv). |
| 2 Venv | `scripts/setup.ps1` created `.venv` and installed the requirements (azure-ai-projects 2.10.0). |
| 3 Deploy | `az bicep build` passed and the deployment succeeded. `.env` contains `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_PROJECT_ID`, `FOUNDRY_MODEL_NAME`, `APPLICATIONINSIGHTS_RESOURCE_ID`, `LOG_ANALYTICS_WORKSPACE_ID`. Foundry networking: publicNetworkAccess=Enabled, defaultAction=Allow (checked with `az cognitiveservices account list`). |
| 4 Implement | Filled LAB PLACEHOLDERs 1-4 (`validate_plan`, `ready_tasks`, `build_handoff`, `should_replan`) exactly as given in the lab. `py_compile` passed. Preflight returned 4x PASS. All 4 `LAB PLACEHOLDER` markers are kept and there are 0 `NotImplementedError`. |
| 5 Run | Ran the complex run (`run-complex.txt`). Changed `complexity_hint` to `simple` in `assets/research-query.json` and ran again (`run-simple.txt`). |
| 6 Validate | Re-ran `py_compile` and the validation command. `artifacts-lab03.txt` holds the complex run followed by the Task 6 simple run. Agents and traces were verified via REST and App Insights KQL (`traces-lab03.txt`). |
| Optional challenge | `optional_challenge.py` writes its output to `challenge-output.txt`. Coarse DAG: 2 tasks. Fine DAG: 6 tasks. Both are validated by the lab's own `validate_plan`. The fine DAG was selected against explicit quality, latency and envelope constraints. Lowering `MAX_HANDOFF_CHARS` makes envelopes fail at 1200 chars (they pass at 1500). The rejection is classified as decomposition granularity (fan-in envelopes), caught by dispatch validation. |
| 7 Review | Answers are in `design-review.md`. |
| 8 Clean up | **Not run, per the brief.** Resources and `.env` are kept. |

## Run evidence

**Complex run** (`complexity_hint=complex`):

- **planner_response_id:** `resp_0f84fbe14a87d9a0006af46cb7e368819786969b904a77c46f`
- **Counts:** task_count 4, handoff_count 4, replan_count 1, coordination_ratio 1.0, elapsed_ms 77793
- **Plan:** T1 financial-data [], T2 macro-risk [], T3 compliance-review [], T4 thesis-synthesis [T1, T2, T3]
- **Results:**
  - T1 `resp_0b2c391e...f670`
  - T2 `resp_067b01e1...5c4a95`
  - T3 `resp_00ff6d33...944e00`
  - T4 `resp_06a868b3...f505c`
  - All four have status success.

**Simple run, Task 6 artifact** (`complexity_hint=simple`):

- **planner_response_id:** `resp_0cbaa994e9e79b86006af46d1d74608194adeeeb0bd623bc5d`
- **Counts:** task_count 2, handoff_count 2, replan_count 1, coordination_ratio 1.0, elapsed_ms 22226
- **Plan:** T1 financial-data [], T2 thesis-synthesis [T1]
- **Results:** T1 `resp_0d7e4c18...847725`, T2 `resp_0555ea3c...f1dfe`

**Simple run, Task 5** (`run-simple.txt`): planner `resp_01fd7c0d...0111`. It has the same 2-task shape and took 22398 ms.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Preflight: 4 PASS, 4 markers kept, no NotImplementedError | PASS | Preflight output. `grep` counts are 4 and 0. |
| Every dependency refers to an earlier completed task | PASS | The order in `results` is T1..T4 and T1..T2. Synthesis is last in both runs. |
| Every specialist exists in the registry | PASS | The agents used are financial-data, macro-risk, compliance-review and thesis-synthesis, all in the registry. `validate_plan` passed. |
| All task results have live Foundry response IDs | PASS | Every result has a `resp_...` ID, and each one matches an App Insights span with `gen_ai.response.id`. |
| One simple and one complex plan demonstrated | PASS | Simple has 2 tasks (1 evidence + synthesis). Complex has 4 tasks (3 through 6 required). Both are in `artifacts-lab03.txt`. |
| Agents present: `research-planner` + each specialist | PASS | REST `GET {project}/agents` lists research-planner, financial-data, macro-risk, compliance-review and thesis-synthesis, each at latest version 1. |
| Planner trace: name, version, success, timestamp | PASS | Complex: `invoke_agent research-planner:1`, success True, 2026-11-11T13:25:12Z. Simple: `research-planner:1`, success True, 13:26:53Z. |
| Each result response ID is traced | PASS | All 11 response IDs have `invoke_agent` spans (`traces-lab03.txt`). |
| Dependent specialists start after prerequisites complete | PASS | Complex: T3 ends 13:25:36.40, then T4 synthesis starts 13:25:41.78. Simple: T1 ends 13:27:01.37, then T2 starts 13:27:04.81. |
| Simple run has fewer specialist traces than complex | PASS | Simple: 2 specialist spans. Complex: 4 specialist spans. |

## Deviations and notes

- Azure CLI and the deploy helper were used instead of `azd` (as briefed). `AZURE_DEV_USER_AGENT` was not used.
- Portal steps (Agents page, Traces search) were done via the REST agents list and App Insights KQL on `dependencies` (`customDimensions['gen_ai.response.id']`). A visual check in the portal is optional for the user.
- There were no code fixes. The shipped runner and the lab snippets worked as given.
- `replan_count` was 1 in every run. Specialists report `missing_evidence` because the query is synthetic-only, so the bounded single-signal policy fired once and was capped.
- `artifacts-lab03.txt` combines both runs (complex section first, then the exact Task 6 command output for simple). Logs show `Authorization: REDACTED`, and there are no secrets in the artifacts.
- `assets/research-query.json` is left with `complexity_hint` set to `simple`, as the lab's Task 5 instructs. Change it back to `complex` to restore the default.
- Extra files written by this run:
  - `run-complex.txt`
  - `run-simple.txt`
  - `traces-lab03.txt`
  - `optional_challenge.py`
  - `challenge-output.txt`
  - `design-review.md`
  - `LAB-REPORT.md`

## Left for the user

- Optional: a visual confirmation in the Foundry portal (Agents and Traces).
- Task 8 cleanup (`az group delete -n rg-lab03-bb4dd21c` plus purging the Foundry account), when you are finished.
