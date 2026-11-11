# Lab 11 - Govern a Foundry multi-agent code review: Lab report

**Result: PASS.** All checks that can be scripted pass. A few portal-only screens are left for you to view.

| Item | Value |
|---|---|
| Resource group | `rg-lab11-d0b8f6c1` |
| Region | eastus2 |
| Deployment | `lab11-main`: Succeeded |
| Foundry account | `fdryzncrpbetm3dg4` (public network access Enabled, default action Allow, as the lab requires) |
| Model deployment | `gpt-5.4-mini` (gpt-5.4-mini 2026-03-17, GlobalStandard), RAI policy `Microsoft.DefaultV2` |
| Application Insights | `appi-lab11-zncrpbetm3dg4` (workspace-based) |
| Evidence | `artifacts-lab11.txt` and `evidence/governance-evidence.jsonl` |

## Tasks

- **Task 1:** Reviewed the architecture. The default run is deterministic; only `--live` calls Foundry.
- **Task 2:** Created the venv with the same steps as `scripts/setup.ps1`: `python -m venv .venv` and `pip install -r requirements.txt`. The script itself was not invoked because the `-ExecutionPolicy Bypass` call was blocked by the local permission policy.
- **Task 3:** Provisioned with Azure CLI instead of azd, using `deploy_lab.py`, which runs `az deployment group create` with `infra/main.bicep`.
  - `.env` was generated from the deployment outputs.
  - `APPLICATIONINSIGHTS_CONNECTION_STRING` was appended separately, because the helper skips `*CONNECTION_STRING` keys. The lab requires it, and it is not a model key.
  - `.env` contains no model keys or tokens.
  - Role assignments: Foundry User, Cognitive Services OpenAI User, Azure AI Developer, Monitoring Metrics Publisher, and Log Analytics Reader on App Insights.
- **Task 4:** Filled LAB PLACEHOLDER 1, the fail-closed `requires_human_review`, in `src/governance.py`. Only one placeholder exists in this lab.
  - py_compile OK.
  - Preflight: every check PASS, ending `READY (Azure configured)`.
  - `NotImplementedError`: 0 matches. `chain_of_thought|raw_prompt`: 0 matches.
  - Hash and attribution fields are present.
- **Task 5:**
  - Deterministic run: mode `deterministic`, python 1.0 / node 0.5, disparity 0.5, `human_review_required` true, 3 local response IDs, purpose-specific `payloadFields`.
  - Evidence record: `evidence_scope=single_process_local_jsonl`, policy `fabrikam-rai-code-review` 1.0.0, tenant hash `37c81e061dfd143e`. The raw tenant value and source fragment are absent.
  - Live run succeeded, with 3 Foundry responses:
    - security-reviewer `resp_031f53a356840cd7006af46ccd1a8481908b4b3321b19ed7e5`
    - fairness-auditor `resp_0521e4df09501371006af46cd2f154819598d531864cff8a67`
    - governance-orchestrator `resp_031b15a473811548006af46cd9f05c8190af022ae616eb039d`
- **Task 6:** Validation checks; see the acceptance criteria below.
- **Optional challenge:** Run in memory; no files were changed.
  - Balanced probes give disparity 0.0, so the gate passes ("continue").
  - Adding a synthetic `node-c=0` probe gives node 0.667 and disparity 0.3333 against a threshold of 0.1, so the gate becomes "human review required". Both the value and the threshold are recorded.
  - Fail-closed checks: missing `fairness`, missing `max_disparity`, and a malformed value each return True. The missing-evidence reason lists `['fairness', 'agent_response_ids']`.
- **Task 7:** See `design-review.md`.
- **Task 8, cleanup:** Not run, as instructed. Resources, `.env`, and the evidence files are kept.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Preflight READY (Azure configured); no NotImplementedError | PASS | artifacts: preflight section |
| No raw_prompt or chain_of_thought in the code | PASS | 0 matches |
| Deterministic run: rates 1.0/0.5, disparity 0.5, human review true, 3 IDs, payloadFields | PASS | Task 5.1 section |
| Evidence record minimized (no raw tenant or source), has scope, policy, hashes, IDs | PASS | Task 5.3 section |
| Live run: 3 agents invoked, response IDs printed, evidence appended, trace emitted | PASS | Task 5.4 section |
| 3 Foundry agents exist with a version and narrow instructions; orchestrator forbids raw source, tenant, and hidden reasoning | PASS | Each agent is at version 1. Checked with the SDK `agents.list()` (Task 6.1-5 section) |
| Only security-reviewer receives `sourceCode`; no agent receives the tenant | PASS | Responses API `input_items` for each response ID (Task 6.7-10 section) |
| Deployment uses the default guardrail, not an unfiltered custom policy | PASS | `raiPolicyName = Microsoft.DefaultV2` |
| Fairness boundary: node-b=1 gives rates 1.0/1.0, disparity 0.0, review false; then restored | PASS | Task 6.17-18 section. The file was restored with `git checkout`, so it is unchanged |
| KQL summary: policy 1.0.0, at least 1 review and escalation, MaxDisparity 0.5, 3 response IDs | PASS | 1 review, 1 escalation, 0.5, all 3 `resp_` IDs |
| Privacy query returns zero rows | PASS with note | See the note below |

**Note on the privacy query.** The KQL in the lab returns 1 row. This is a false positive, not a privacy leak. The `has` operator splits text on `_`, so `has_any("tenant_id")` matches the hashed key `tenant_id_hash`. Stricter queries all return 0:
- The other three terms each return 0 rows.
- The exact-key check with `bag_keys(Properties)` returns 0 rows for every prohibited key.
- A search for the raw tenant value or source fragment returns 0 rows.

To get a literal zero-row result, the lab's KQL should use `bag_keys` or `has_cs` with exact keys, for example `Properties has "\"tenant_id\":"`. Lab content was not modified.

## Deviations and fixes

- Provisioned with Azure CLI instead of azd. Log Analytics was queried through the REST API with `az rest`, because the `log-analytics` CLI extension needs an interactive install.
- The shipped code needed no fixes. Only the placeholder was filled.
- Portal Traces and Agents views were checked through SDK equivalents. `GenAI tracing is not enabled` was printed, because the app does not set `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING`.
- In `artifacts-lab11.txt`, the subscription ID and the client geolocation from the App Insights row are redacted.

## Left for you (portal only)

- In Foundry, open Agents, then **Traces**, and search by response ID to see the trace views. Foundry trace spans may be sparse because GenAI tracing was not enabled.
- In Foundry, open Build, then Models, then `gpt-5.4-mini`, to see the guardrail screen. The CLI already confirms `Microsoft.DefaultV2`.
- Take any screenshots you want for the governance evidence set.
- Task 8 cleanup, when you are done: `az group delete -n rg-lab11-d0b8f6c1`.

## Setup approval (2026-11-11)
The user approved `scripts/setup.ps1` for this lab and it was re-run with exit code 0. All requirements were already satisfied, so the existing `.venv` (first built by running the same steps from bash) is now sanctioned. No results changed.
