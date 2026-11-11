# Lab 15 report: Optimize multi-agent performance and cost (Adventure Works)

**Result: PASS.** Provisioning used Azure CLI instead of azd. Resources are kept; Task 8 cleanup was not run.

- **Resource group:** `rg-lab15-c52d90c3`. **Region:** westus3.
- **Resources:**
  - Foundry account `awoptbtdjtstq6y4ey` with project `aw-optimization`
  - Deployment `gpt-5.4-mini` (2026-03-17, GlobalStandard), used for TIER1/2/3
  - Azure Managed Redis `awopt-cache-btdjtstq6y4ey` (Balanced_B0), database `default` on port 10000, access keys disabled, Entra `default` access policy assigned to the signed-in user
- **Failed attempt:** `rg-lab15-fc40004b` (eastus2). Redis Enterprise creation failed twice with a generic `OperationFailed`; the Foundry account succeeded. The RG was kept as the brief requires and holds a Failed (`CreateFailed`) Redis cluster. **The user should delete it.**

## Tasks
| Task | What was done |
|---|---|
| 1 Prepare | Reviewed assets, src, infra. The request path is: classify tier → budget context → result-cache lookup → invoke model or return cache → quality floor/escalation → evidence row. |
| 2 venv | `scripts/setup.ps1` created `.venv`. `.env` was written by the deploy helper instead of being copied from `.env.example`. |
| 3 Deploy | `deploy_lab.py` (az deployment group create) with the default model values. `.env` contains FOUNDRY_PROJECT_ENDPOINT, REDIS_HOST, REDIS_PORT, TIER1-3_DEPLOYMENT and AZURE_PRINCIPAL_ID, with no keys. |
| 4 Implement | Placeholders 1-4 filled by hand, because the helper's pattern doesn't match this md: `classify_tier`, `apply_context_budget` (src/main.py) and `result_key`, `prompt_key` (src/cache.py). `py_compile` printed nothing; `preflight --require-complete` reported all 11 checks `ready` and exited 0. |
| 5 Run | Ran control, optimized ×2, invalidate, optimized again and compare_runs, all exit 0. Outputs are in `reports/`; a consolidated copy is in `artifacts-lab15.txt`. Workload: the 3 supplied synthetic requests only. |
| 6 Validate | See the next section. |
| Optional challenge | Added `scripts/tenant_challenge.py`, with tenant-scoped result and prompt keys, run against Redis without model calls (output in `reports/tenant-challenge.json`). It **passed**: keys for tenants A and B differ, targeted invalidation deleted 1 key (A gone, B present), and stale `agent_version` invalidation deleted 0. Diagnosis: the defect is in key construction, not scope. The script removes its own keys. |
| 7 Design review | Answered in `design-review.md`. The recommendation is in `reports/optimization-report.md`. |
| 8 Clean up | **Not run**, per the brief (resources and `.env` kept). |

## Acceptance criteria
| Criterion | Result | Evidence |
|---|---|---|
| Every row has deployment, price_version, initial/final tier, cache_level, prompt_cache_hit, retry_count, cost, quality (exact hits included) | PASS | Scripted check over all 4 summaries returned True. |
| Non-cached rows have measured elapsed_ms and actual input/output tokens | PASS | All `miss` and `prompt` rows have values > 0 (for example control LOOKUP: 6175.9 ms, 117/41 tokens). |
| Second optimized run shows `exact_result` | PASS | `optimized-cached-summary.json`: LOOKUP and COMPARE are `exact_result` with 0 tokens and $0. |
| Invalidate output recorded | PASS | `exact_result_key: aw:result:093d15004890fe1ba7541d513c0c1fd48af2de68e2d337b0502683a0920d033a`, `deleted: 1`. |
| Rerun shows SYN-LOOKUP-001 `cache_level: prompt` | PASS | `optimized-prompt-cached-summary.json`: LOOKUP is `prompt` with prompt_cache_hit true; COMPARE is still `exact_result`, so only the selected result was invalidated. |
| cache_hit_rate counts exact + prompt | PASS | Warm run: 1.0 = 0.667 exact + 0.333 prompt. Final run: 1.0 = 0.333 + 0.667. |
| Redis contains only synthetic data, no credentials | PASS | `reports/redis-inspection.txt`: 5 keys (3 `aw:prompt`, 2 `aw:result`), synthetic AW-*/SYN-* data, credential regex returned False for all. |
| Foundry account, project and deployment (Task 6.8) | PASS (az CLI instead of portal) | `reports/azure-validation.txt`: account and project Succeeded; deployment `gpt-5.4-mini` Succeeded, matching TIER1/2/3_DEPLOYMENT. |
| Redis `default` database and Entra `default` access policy assignment (Task 6.9) | PASS (az rest instead of portal) | Database `default` Succeeded, port 10000, accessKeysAuthentication Disabled. Assignment `mkg57rzomtuhi` uses policy `default` for the signed-in user and is Succeeded. |
| Route by complexity | PASS | EXCEPTION-003 has initial_tier 3. LOOKUP-001 and COMPARE-002 have initial_tier 2 vs 3 under control. No supplied request reaches tier 1: LOOKUP has 2 dependencies, and the lab's rule `> 1 dependency → tier 2` applies. |
| Cache separation and invalidation | PASS | Prompt and result keys use separate `aw:prompt`/`aw:result` namespaces and digests; invalidation removed only LOOKUP's exact result. |
| Context budgets | PASS | Function is implemented; all runs succeeded with no budget errors; `unused_fields` is excluded from the cached context. |
| Compare measured performance and cost | PASS | `reports/comparison.json`: warm run vs control is -$0.000899 (-62%), -275 input tokens, p95 -2138 ms. |

Notes on the measurements:
- SYN-EXCEPTION-003 stays below the tier-3 floor (quality 0-33) in every run and is correctly flagged `needs_human_review` and never result-cached. That accounts for all of the quality-mean delta (-11), and its savings are excluded from the recommendation.
- `retry_rate` was 0 in every run.

## Deviations and fixes
- Provisioned with `az` through the deploy helper instead of `azd`.
- Moved from eastus2 to westus3 after the Redis create failure described above.
- `LAB PLACEHOLDER` comments were **removed**, not kept. The lab says to remove them, and `preflight.py --require-complete` checks `learner_code_complete` by requiring zero markers.
- No changes to the shipped lab code. The only addition is `scripts/tenant_challenge.py` for the optional challenge.
- Portal checks were done with az CLI/REST equivalents.

## Left for the user
- Delete the failed eastus2 resource group `rg-lab15-fc40004b`, which holds a Redis cluster in Failed state.
- Task 8 cleanup when finished: delete `rg-lab15-c52d90c3`, which contains billable Managed Redis, and remove `.env`.
- No commands were blocked by permissions.
