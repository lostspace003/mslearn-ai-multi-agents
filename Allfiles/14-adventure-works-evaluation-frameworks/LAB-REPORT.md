# Lab 14 - Build a multi-agent evaluation quality gate: report

- **Resource group:** rg-lab14-aed663e6 (eastus2), kept
- **Resources:** Foundry account `awevalxsd6kyllhab7m` (AIServices, S0, Succeeded), project `aw-evaluation`,
  model deployment `gpt-5.4-mini` (GlobalStandard, model version 2026-03-17)
- **Provisioning:** Azure CLI via `deploy_lab.py` instead of azd. `.env` holds FOUNDRY_ACCOUNT_ENDPOINT,
  FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL_NAME, principal and subscription values, and no keys.
- **Overall:** PASS. The lab works end to end. The release gate correctly blocks release; this is expected because the
  data deliberately contains failing cases.

## Tasks

| Task | What was done |
|---|---|
| 1 Prepare | The repo and tools were already present. az was logged in. Inputs were reviewed. |
| 2 venv | `scripts/setup.ps1` created `.venv`. |
| 3 Deploy | Used az bicep build plus `az deployment group create` (helper). Roles: Azure AI Developer and Cognitive Services OpenAI User at RG scope, plus the roles from the Bicep template. |
| 4 Implement | Filled placeholders 1-5 by hand (helper found 0). `py_compile` was clean. `preflight --require-complete`: all 7 checks `ready`, exit 0 (`artifacts-lab14-preflight.txt`). |
| 5 Run | Ran `python -m src.main --data assets/evaluation-data.jsonl --output reports/evaluation-result.json`, exit 0 (`artifacts-lab14-run1.txt`). |
| 6 Validate | Checked the evidence, ran the contradiction re-run and the optional grounding challenge, and checked Azure resources with az CLI (below). |
| 7 Design | Answers are in `design-review.md`. |
| 8 Cleanup | **Not run, on purpose** (resources and local files are kept, per instructions). |

## Results

| Run | intent_resolution | task_adherence | response_completeness | journey_coherence | calibration | gate |
|---|---|---|---|---|---|---|
| Baseline (`reports/evaluation-result.json`) | 3.0 | 0.333 | 4.0 | 4.0 | 0.667 | **blocked**: journey_coherence (delta -0.4 > 0.3), intent_resolution, task_adherence, judge_calibration (0.667 < 0.67) |
| Contradiction (`reports/evaluation-result-contradiction.json`) | 1.667 | 0.0 | 2.667 | 3.0 | 0.667 | **blocked**: all 4 metrics + judge_calibration |
| Grounding challenge (`reports/evaluation-result-grounding-challenge.json`, 4 rows) | 3.0 | 0.25 | 3.0 | 3.5 | 1.0 | **blocked**: all 4 metrics |

Row-level scores (IR / TA / RC / JC, then the human label):
- Baseline: canary-001 5/1/5/5 (human 5). regression-handoff-002 2/0/2/2 (human 3). historical-policy-003 2/0/5/5 (human 5).
- Contradiction: in canary-001, the returns agent denies eligibility after the policy agent confirmed the USD 49.00
  refund. The row dropped to **1/0/1/1**. The other rows stayed about the same.
- Challenge: challenge-grounding-004 (wrong amount USD 210 vs 120, customer pays shipping, gift card under policy v3,
  human 1) scored **3/0/1/1**. The judge's reason names each contradiction with the grounding.

### Low-scoring rows (Task 6.2)
- **regression-handoff-002: handoff-level failure.** Inventory confirmed both SKUs, but the order agent only applied
  SKU-SYN-A. The fact was lost between agents.
- **historical-policy-003: component-level judge artefact, not a journey failure.** `intent_resolution` (2) and
  `task_adherence` (0) score literally against "return my order". The correct, policy-required behavior is to escalate to a
  human, and RC and JC score it 5. The query-only judges have no context or expected behavior, so they penalise correct
  policy refusals. This is why the aggregate `task_adherence` fails even on the shipped data.
- **canary-001 in the contradiction run: system-level failure.** Each agent's output looks plausible, but the journey
  contradicts itself.

## Acceptance criteria

| Objective | Evidence | Result |
|---|---|---|
| Define component, journey and system metrics | `evaluators` = 4 names. `gate.comparisons` has all 4 configured metrics with measured, baseline, delta, minimum and maximum_drop. The missing-metric branch adds `"<name>: missing measured metric"` to `failed_gates`, so a missing metric fails the gate (code review). | PASS |
| Run Responses-based evaluators through the SDK batch framework | `azure.ai.evaluation.evaluate` batch run. `*.rows.jsonl` has every row with all 4 scores and `_reason` fields (3/3, 3/3 and 4/4 rows on clean runs). | PASS |
| Use synthetic coverage cases | Dataset partitions canary, regression and historical_failure. Only supplied cases plus my synthetic copies (`assets/evaluation-data-contradiction.jsonl`, `assets/evaluation-data-grounding-challenge.jsonl`). | PASS |
| Produce an auditable recommendation | `gate.passed` = false, with `failed_gates` listed, calibration 0.667 vs 0.67, and `deployment` = `gpt-5.4-mini` read from `.env`. | PASS |
| Regression gate uses measured results (6.3-6.5) | One response was changed. The scores and the gate changed: RC newly fails, and the canary row fell from 5 to 1. No scenario label is used. | PASS |
| Optional challenge: grounding failure blocks release | The new row has RC=1 and JC=1. The aggregates dropped and the gate blocked release. | PASS |
| Challenge: judge vs human disagreement | Baseline row 002: JC 2 vs human 3. Agreement 0.667 < 0.67 adds `judge_calibration` to the failed gates. This is a calibration failure, separate from the task-result failures. In the challenge run, row 002 got JC=3, agreement rose to 1.0 and `judge_calibration` passed while the task gates still failed. Judge scores vary from run to run. | PASS |
| Azure resources (6.6) | `az resource list` / `az cognitiveservices account show` / `deployment list`: account, project and deployment all Succeeded. | PASS (via CLI) |

## Deviations and fixes
1. **I removed the `LAB PLACEHOLDER` comments.** The lab says to remove them, and `preflight --require-complete` needs zero
   markers. This overrides the brief's "keep the marker". The snippets were re-indented from 2 to 4 spaces.
2. **I raised deployment capacity from 10 to 100 (K TPM) with `az cognitiveservices account deployment create`.** At the
   Bicep default of 10, the 4 parallel evaluators got HTTP 429. It took a few minutes to take effect, so runs 2 and 3
   were retried until a run had no 429s. The output files are from clean runs. `infra/main.bicep` is unchanged.
3. **Robustness gap in the lab-supplied `calibration_agreement()` (not changed).** When a judge row fails (for example
   with a 429), the score is NaN and `round(float(nan))` raises `ValueError`, so the run aborts. This fails closed, which
   is acceptable for a gate. A possible fix is to skip NaN scores and record them as missing.
4. **SDK file format.** `evaluate(output_path=...rows.jsonl)` writes one JSON document (`rows`, `metrics`, `studio_url`),
   not line-delimited JSONL as the lab text says. The row evidence is still all there.

## Artifacts
`artifacts-lab14-preflight.txt`, `artifacts-lab14-run1.txt`, `artifacts-lab14-run2-contradiction.txt`,
`artifacts-lab14-run3-challenge.txt`, `reports/evaluation-result*.json`, `reports/evaluation-result*.rows.jsonl`,
`design-review.md`.

## Left for the user
- Portal visual check of the Foundry account, project and deployment (the CLI equivalent is done).
- Task 8 cleanup is not run on purpose. Delete rg-lab14-aed663e6 when you are finished, because the deployment
  (now 100K TPM) costs money per token only.
- Nothing was blocked by permissions.
