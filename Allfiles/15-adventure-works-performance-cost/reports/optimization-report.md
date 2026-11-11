# Optimization evidence report

## Configuration and price version
- Resource group `rg-lab15-c52d90c3` (westus3). All three tiers map to the `gpt-5.4-mini` (2026-03-17, GlobalStandard) deployment.
- Price version `verified-2026-10-01-global-standard`: $0.75 input / $4.50 output per 1M tokens, the same for every tier.
- Agent `aw-cip-v3`, policy `optimization-v1`, cache TTL 3600 s. The workload is the 3 supplied synthetic requests.

## Control evidence (`control-summary.json`)
- All requests ran at tier 3. Cost $0.001455, 404 input / 256 output tokens.
- p50 2027.7 ms, p95 6175.9 ms. Quality mean 77.67. 2 of 3 successful; SYN-EXCEPTION-003 needs human review (quality 33).

## Optimized evidence
| Run | Cost USD | In/Out tokens | p95 ms | Quality | cache_hit_rate (exact / prompt) |
|---|---|---|---|---|---|
| optimized (cold) | 0.001522 | 404 / 271 | 3549.9 | 66.67 | 0.00 (0.00 / 0.00) |
| optimized-cached | 0.000556 | 129 / 102 | 4038.0 | 66.67 | 1.00 (0.67 / 0.33) |
| optimized-prompt-cached | 0.000783 | 246 / 133 | 3628.1 | 77.67 | 1.00 (0.33 / 0.67) |

Routing: LOOKUP and COMPARE go to tier 2. LOOKUP has two dependencies, so the classifier puts it in tier 2 rather than tier 1. EXCEPTION goes to tier 3 (policy exception, USD 850). Retries: 0 in every run.

## Quality, cost, and latency comparison (`comparison.json`)
- Cold optimized vs control: +$0.000067 (output-token variance), 0 input-token delta, p95 -2626 ms, quality -11.
- Warm (exact cache) vs control: -$0.000899 (-62%), -275 input tokens, p95 -2138 ms, quality -11.
- The quality delta comes entirely from SYN-EXCEPTION-003. It scored 33 in control and 0 in the optimized runs, and 33 again in the last run. That is model variance on the same deployment, not a routing effect. The request is flagged `needs_human_review` in every run, so its savings are excluded.

## Cache and invalidation evidence
- Warm run: LOOKUP and COMPARE return `exact_result` with no model call. EXCEPTION is never result-cached because it needs review, so it returns `prompt`.
- `--invalidate-exact SYN-LOOKUP-001` returned `exact_result_key aw:result:093d1500…033a` and `deleted: 1`. In the next run LOOKUP showed `cache_level: prompt` (model called with cached context) and COMPARE was still `exact_result`.
- Redis held 5 keys (3 `aw:prompt:*`, 2 `aw:result:*`). All contain synthetic context and answers only, with no credentials.

## Recommendation and rollback trigger
Adopt the optimized policy (deterministic routing, budgeted context, versioned exact-result and prompt caches) for lookup and compare traffic. Measured savings come only from observed exact-result hits on successful requests (about 62% lower cost on the warm run). Keep exception and high-value requests on tier 3 with mandatory human review.

Roll back to control if any of these happen:
- Segment quality drops below its SLO floor (standard 85, gold 90) on successful requests.
- p95 latency exceeds the segment SLO (standard 6000 ms, gold 3000 ms).
- A stale exact hit is detected after a dependency or version change.

Before claiming routing savings, re-benchmark with separately priced tier deployments.
