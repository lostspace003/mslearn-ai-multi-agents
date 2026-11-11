# Lab 13 - Trace multi-agent workflows with OpenTelemetry - Lab report

**Status:** PASS (portal-only views listed at the end)
**Resource group:** `rg-lab13-c59c747d`, **Region:** `eastus2` (provisioned with Azure CLI rather than azd; resources were kept)

Resources: Log Analytics `log-aw-otel-p6ayjdwzzwra2`, Application Insights `appi-aw-otel-p6ayjdwzzwra2` (DisableLocalAuth=true),
user-assigned identity `id-aw-telemetry-p6ayjdwzzwra2` (Monitoring Metrics Publisher), action group
`ag-aw-agent-anomaly-p6ayjdwzzwra2`, scheduled-query rule `alert-aw-agent-policy-anomaly-p6ayjdwzzwra2`.

## What I did, task by task

| Task | Result |
|---|---|
| 1 Prepare | Checked the tools. Reviewed telemetry.py, the policy, the scenario, the KQL and the Bicep. |
| 2 venv | Ran `scripts/setup.ps1`, which created `.venv`. The scenario contains none of the 5 prohibited fields (grep count 0 for each). |
| 3 Deploy | Ran `deploy_lab.py . lab13 --location eastus2 --set ALERT_EMAIL=<subscription account email>`, which uses `az deployment group create`. The helper skips any key ending in CONNECTION_STRING, so I added `APPLICATIONINSIGHTS_CONNECTION_STRING` to `.env` from `az resource show`. That value is an ingestion endpoint and iKey, not a credential, because local auth is disabled. `.env` holds `APPLICATIONINSIGHTS_RESOURCE_ID`, `LOG_ANALYTICS_WORKSPACE_ID`, `TELEMETRY_IDENTITY_CLIENT_ID`, `ANOMALY_ALERT_RULE_ID` and `ANOMALY_ACTION_GROUP_ID`, and no secrets. I gave the signed-in user **Monitoring Metrics Publisher** on the App Insights resource. Local-key ingestion was not enabled. |
| 4 Implement | Filled LAB PLACEHOLDER 1 (`build_next_carrier` injects W3C context). py_compile passed. Preflight ended with `READY (local)`. No `NotImplementedError` remains. |
| 5 Run | **Console run** (`evidence/console-run.txt`): 3 spans share trace `8101251477f2619079f877e062ea4b2f`. Parent chain: router (root) -> recommendation -> inventory. Recommendation has `latency.anomaly` and `token.anomaly` events. error_rate = 0.333 and error_rate_anomaly = true. **Azure run** (`evidence/azure-run-default.txt`, `evidence/trace-evidence.json`): recorded trace ID **`824b6706e186868311d096a6925702b0`**, with all transmissions returning 200. |
| 6 Validate | See the acceptance criteria below. |
| Optional challenge | Done. See below. |
| 7 Review | Answers are in `design-review.md`. |
| 8 Clean up | **Not run**, as instructed. The resources, `.env` and `evidence/` were kept. |

## Acceptance criteria

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | The 3 spans share one 32-character trace ID and form a parent-child chain | PASS | Console run: router has no parent, recommendation's parent is `0xf98e31ca50356cb1` (router), and inventory's parent is `0xb430c7b1a9045a99` (recommendation) |
| 2 | Recommendation has a latency anomaly (85 > 60) and a token anomaly (516 > 500); chain error rate is 1/3 | PASS | console-run.txt / trace-evidence.json |
| 3 | Export through Entra auth with the waterfall under one operation | PASS | `evidence/kql-trace-waterfall.txt`: for OperationId `824b6706...`, there are 3 AppDependencies (router `bc1db6c3...` -> recommendation `a39191bb...` -> inventory `5a8aedd9...`, Success=False) plus the correlated AppTraces rows (including 2 span-event rows) |
| 4 | `agent-health.kql` shows recommendation with the highest P95 and token anomalies, and inventory in error | PASS | `evidence/kql-agent-health.txt`: recommendation P95 = 85 ms with TokenAnomalies = 5/5; inventory P95 = 22 ms with Anomalies = 5 (status error); router P95 = 15 ms with 0 anomalies |
| 5 | Boundaries: 60 ms / 80 tokens is not anomalous | PASS | `evidence/policy-variants.txt` (boundary-60ms-80tok): recommendation = success |
| 6 | Back to 96 tokens: token anomaly returns and latency at 60 ms stays clean | PASS | boundary-60ms-96tok: anomaly_types = `token` |
| 7 | With every error set to false, error_rate_anomaly is false | PASS | no-errors: err_rate_anom = False |
| 8 | YAML changes alter decisions without any KQL edit | PASS | latency_threshold_ms=100 drops latency; error_rate_threshold=0.5 gives err_rate_anom=False; token_anomaly_sigma=4 drops token (threshold 550) |
| 9 | Action group is enabled, uses the email receiver and the common alert schema | PASS | `evidence/alert-config.json`: enabled=true, useCommonAlertSchema=true, receiver status Enabled |
| 10 | Scheduled-query rule: enabled, sev 2, PT5M, linked to the action group, scoped to the workspace | PASS | `evidence/alert-config.json`: scope `log-aw-otel-p6ayjdwzzwra2`, autoResolved PT5M |
| 11 | A severity-2 alert fires, linked to the workspace and the action group | PASS | `evidence/alert-fired.json`, `evidence/alert-history.json`: "Adventure Works agent policy anomaly", Sev2, Fired 2026-11-11T13:31:16Z on the workspace target; history shows "Action group ag-aw-agent-anomaly-p6ayjdwzzwra2 executed" |
| 12 | Policy decisions can be queried (the alert's input) | PASS | `evidence/kql-policy-decisions.txt`: observation rows with status/anomaly_types/token_anomaly, and chain.summary rows with error_rate 0.333 / error_rate_anomaly True |
| 13 | A no-anomaly run leads to auto-mitigation | PASS | Alert monitorCondition went from Fired to **Resolved at 2026-11-11T13:42:14Z** (autoResolved, PT5M). Evidence: `evidence/no-anomaly-azure.txt` (trace `273e9591bc0601e1196bc259289f61b4`: no anomalies, error_rate 0.0), `evidence/alert-resolved.json` |

## Optional challenge

- `src/telemetry.py` creates a synthetic `request.classification` value (`synthetic.product_recommendation`, which can be overridden by an optional scenario key `request_classification`). The value travels as **W3C baggage** alongside `traceparent`. Each agent extracts it and sets it as a span attribute and a log field. Request content is never added.
- Console evidence (`evidence/challenge-console.txt`): all 3 spans carry the attribute in one trace.
- Azure evidence (`evidence/kql-challenge-classification.json`, from `az monitor app-insights query`): trace `1a50937fe21e580ed6c9794ebe7982dc` contains router, recommendation and inventory, each with `customDimensions['request.classification'] = synthetic.product_recommendation`.
- **Failure investigation** (`evidence/challenge-broken-handoff.txt`): I dropped the carrier at the recommendation -> inventory handoff, using a scratch monkeypatch that left the lab code unchanged. Router and recommendation kept trace `952c01ff...`. **Inventory** was the first span to leave the original trace (`af746b8f...`), and correlation_complete was False.

## Code changes and deviations

- Filled placeholder 1 only, with no fixes to shipped code. The optional challenge adds clearly commented code in `telemetry.py`: a baggage propagator, extract and inject, and re-attaching the baggage context before `build_next_carrier`. Without the re-attach, `start_as_current_span(context=...)` would not make the extracted baggage current, and only the router would get the attribute.
- I used azure CLI and `deploy_lab.py` instead of azd.
- Policy variants ran against copies in `evidence/variants/` through `--scenario` / `--policy`. The shipped asset and YAML were never edited, so there was nothing to restore.
- `az monitor scheduled-query show` needs the `scheduled-query` CLI extension, which isn't installed. I didn't install it and used `az resource show --api-version 2023-12-01` instead. Workspace KQL (AppTraces/AppDependencies) ran through the Log Analytics query REST API (`az rest`) because the `log-analytics` extension isn't installed. App Insights checks used `az monitor app-insights query`.
- The Monitoring Metrics Publisher role took about 6 minutes to propagate, so the first export attempts returned 403. The exporter's retry and offline storage later delivered those logs as well.
- Nothing was blocked by permissions.

## Left for the user (portal-only)

- Application Insights **Agents (Preview)** view and the **Transaction search** waterfall UI. The same data was verified with KQL above.
- Confirm the action-group subscription email, and check that the notification email uses the common alert schema. The rule is configured with useCommonAlertSchema=true, but the inbox can't be checked from here.
- Screenshots of the live evidence set (Agents view, waterfall, fired and resolved alert, email).
- Task 8 cleanup is deliberately not done. Run `az group delete -n rg-lab13-c59c747d` when finished to stop ingestion charges.
