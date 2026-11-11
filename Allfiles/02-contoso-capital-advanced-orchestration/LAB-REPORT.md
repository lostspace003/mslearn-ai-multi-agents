# Lab 02 report: Advanced multi-agent orchestration (fan-out/fan-in, quorum)

**Result: PASS**

| Item | Value |
|---|---|
| Resource group | `rg-lab02-d019fdcf` |
| Region | eastus2 |
| Subscription | Visual Studio Subscription |
| Foundry account / project | `fdrygpsajvgyekq46` / `lab02-lab02-d019fd` |
| Model | `gpt-5.4-mini` (2026-03-17) |
| App Insights | `appi-lab02-gpsajvgyekq46` |

Provisioning used the Azure CLI (`deploy_lab.py`) instead of `azd`. The upstream `.env` pointed at another subscription; it was replaced. The stale upstream artifacts were overwritten by this run's artifacts.

## Tasks

| Task | What was done | Result |
|---|---|---|
| 1. Prepare | Reviewed the architecture: 3 spokes; market and risk required, compliance optional; quorum is evaluated in code before synthesis. | Done |
| 2. Virtual environment | Ran `scripts/setup.ps1`, which created `.venv` (azure-ai-projects 2.10.0). | Done |
| 3. Deploy | Ran `az bicep build` and `deploy_lab.py . lab02 --location eastus2`. | Done |
| 4. Implement | Filled placeholders 1-3 in `src/main.py`. | See below |
| 5. Run | Ran the normal input and the optional-failure input. | Both exited 0 |
| 6. Validate | See the acceptance criteria and agent checks below. | Done |
| 7. Design review | Answers are in `design-review.md`. | Done |
| Optional challenge | See the optional challenge section below. | Done |
| 8. Cleanup | Skipped on purpose; resources are kept. | Skipped |

**Task 3 details**
- `.env` contains `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_PROJECT_ID`, `FOUNDRY_MODEL_NAME`, `APPLICATIONINSIGHTS_RESOURCE_ID` and `LOG_ANALYTICS_WORKSPACE_ID`.
- `.env` contains no keys.
- The Foundry account has public network access set to `Enabled` and the default network action set to `Allow` (checked with `az`).

**Task 4 details**
- `py_compile` passed.
- Preflight reported 4 PASS lines.
- 3 `LAB PLACEHOLDER` markers remain.
- 0 `NotImplementedError` remain.

**Task 5 output files:** `artifacts-normal.txt`, `artifacts-optional-failure.txt`, and the combined `artifacts-lab02-evidence.txt`.

**Task 6 output files:** `artifacts-lab02-agent-validation.txt` and `artifacts-lab02-traces.txt`.

**Optional challenge files:**
- Inputs: `assets/portfolio-request-high-risk*.json`
- Outputs: `artifacts-challenge-*.txt`

## Acceptance criteria (Task 6.1)

| Field | Normal input | Optional-failure input | Pass |
|---|---|---|---|
| `pattern` | `parallel` | `parallel` | PASS |
| `compliance-spoke.status` | `success` | `failed`; market and risk `success` | PASS |
| `quorum.status` | `ready` | `ready` | PASS |
| `missing_agents` | `[]` | `["compliance-spoke"]` | PASS |
| `missing_required` | `[]` | `[]` | PASS |
| `accepted_evidence` | market, risk, compliance | market, risk | PASS |
| `supervisor_response_id` | `resp_00ba5866…a0c961` | `resp_0802676c…db3b1cd` | PASS |
| Supervisor answer | Uses only the spoke evidence | States: "Compliance-spoke is missing: no compliance-specific review was provided…" | PASS |

**Task 6.2:** In the normal run, all 3 spokes succeeded with response IDs, text and `elapsed_ms`:

| Spoke | Response ID | `elapsed_ms` |
|---|---|---|
| market | `resp_0b22e549…` | 7222 |
| risk | `resp_09f4d8a7…` | 8002 |
| compliance | `resp_0734030f…` | 7091 |

The supervisor has its own, separate response ID.

**Task 6.3:** The wall-clock `elapsed_ms` was 15554, against a sum of spoke durations of 22315. That is consistent with concurrent calls (the barrier waits for the slowest spoke, about 8 s, then the supervisor runs).

**Task 6.4:** I reviewed the required-failure path in code:
- `evaluate_quorum` returns `insufficient_quorum` when a required agent is missing.
- `synthesize` then raises `RuntimeError` before any supervisor call.

**Tasks 6.5-6.11 (portal agent checks):** done with the SDK instead of the portal. Output is in `artifacts-lab02-agent-validation.txt`.
- All 4 agents exist as prompt agents (`kind=prompt`).
- Each one's model is `gpt-5.4-mini`, and its instructions match `assets/portfolio-request.json`.
- The service kept version 1 across runs, because the definitions were identical.
- I ran the Playground prompts through the agent Responses endpoint. Role boundaries held:
  - market returned assumptions and evidence gaps;
  - risk returned drivers and limits, with no advice;
  - compliance returned only caveats.
- The supervisor, given the synthetic fan-in payload, used only the two records and listed "Compliance review input from the missing `compliance-spoke`". It invented no holdings, exposure values or shock magnitude.

**Tasks 6.12-6.14 (traces):** queried with KQL through `az monitor app-insights query`; output is in `artifacts-lab02-traces.txt`. The traces are `invoke_agent` spans, keyed by `gen_ai.response.id`.

| Run | Spoke spans | Supervisor span starts |
|---|---|---|
| Normal | All 3 start within 13:24:57.08-57.42 UTC and overlap (end 58.9-59.9) | 13:25:04.87, after the spokes |
| Optional-failure | All 3 start within 13:25:27.9-28.3 and overlap | 13:25:35.10 |

In the optional-failure run, a compliance trace exists (`resp_003d5cda…`), as expected, because the fault is injected after the live call.

## Optional challenge

**Guarded route** (`portfolio-request-high-risk.json`, `route=guarded-high-risk`): market and risk declare `depends_on: [compliance-spoke]`.
- The output shows `"pattern": "sequential"` and `"route": "guarded-high-risk"`.
- Compliance (`resp_0a5c80af…`, 5412 ms) finished before market started. The trace shows compliance at 13:28:15.5-17.6.
- Total time was 25342 ms, about the sum of the spoke durations, which is what sequential execution should give.
- The supervisor opens with "Compliance caveats first".

**Failure investigation** (`portfolio-request-high-risk-failure.json`, which forces `compliance-spoke` to fail):
- Quorum was `ready`, with `missing_agents=[compliance-spoke]` and `missing_required=[]`.
- The orchestrator **continued**. It did not fall back or fail closed, and the supervisor disclosed the missing compliance evidence.
- Finding: the dependent spokes still ran even though their prerequisite failed. The details are in `design-review.md`.

Some challenge-run spans had not yet appeared in App Insights when I queried (ingestion lag). This does not affect the core criteria.

## Code changes and deviations

**Placeholders.** Placeholders 1-3 were filled exactly as the lab's snippets give them. No shipped-code bugs were found.

**Optional challenge additions to `src/main.py`.** Both are additive:
- an optional `simulate_failure_agent` fault injection for a named spoke;
- a `route` field in the output, defaulting to `"standard"`.

  Because of this, the normal and optional-failure artifacts, which were captured before the change, have no `route` field.

**Tooling.** I used Azure CLI with `deploy_lab.py` instead of `azd`. I also used the SDK and KQL in place of the portal Playground and Traces UI.

## Left for the user

- **Optional portal check:** look at the agents, Playground and Traces in the Foundry portal (**New Foundry**, project `lab02-lab02-d019fd`).
- **Cleanup (Task 8):** not done, on request. To remove everything later, run `az group delete -n rg-lab02-d019fdcf`, then purge the Foundry account.
