# Lab 15 – Task 7 design review

Evidence: `reports/*-summary.json`, `reports/evidence.jsonl`, `artifacts-lab15.txt` (rg-lab15-c52d90c3, westus3, all tiers = `gpt-5.4-mini` GlobalStandard, price version `verified-2026-10-01-global-standard`).

**When did a cheaper initial route cost more because it retried?**
It didn't happen in this run. `retry_rate` was 0.0 in all four summaries. SYN-LOOKUP-001 and SYN-COMPARE-002 started at tier 2 and scored 100, above the tier-2 floor of 85. SYN-EXCEPTION-003 started at tier 3, so it had no higher tier to escalate to. The cold optimized run did cost slightly more than control ($0.001522 vs $0.001455, +$0.000067), but that came from output-token variance: SYN-COMPARE-002 used 141 output tokens vs 114 in control. It was not a retry. All three tiers map to the same deployment and price, so routing alone cannot save money per token. A retry would cost more only if a tier-1/2 attempt fell below its floor, because the run then pays for both attempts (summary cost includes every attempt). To see that case you would need tiers backed by separately priced models, or a stricter floor.

**Which context fields consumed tokens without changing quality?**
`unused_fields` (`warehouse_notes`, `supplier_history`) on SYN-LOOKUP-001. It does not contribute to any quality assertion. `apply_context_budget()` drops it, and the prompt-cache entry for AW-1001 contains only `carrier`, `eta`, `order_id` and `status`, while the lookup still scored 100. Control also builds context with `apply_context_budget()`, so the input-token delta between policies was 0 (404 vs 404). To measure exactly how many tokens those fields cost, you would need an extra run with the raw, unfiltered context. On the exception request, `customer_tier` is not part of any required term either, but it is a policy-relevant fact, so it should stay.

**What evidence would justify adding semantic caching rather than exact result caching?**
- Request logs showing a high share of paraphrased duplicates: same context, dependencies and intent but different wording, so the exact cache misses them.
- A measured exact-hit ceiling well below the observed near-duplicate rate. In this lab the warm run reached `exact_result_cache_hit_rate` 0.67 with no paraphrases in the set, so there is no such evidence yet.
- An offline replay where semantic hits keep quality at or above each segment's floor, with a measured false-hit rate near zero. Wrong reuse matters most for order and exception facts.
- Cost and latency savings that remain after paying for embedding calls.

Semantic matching should also never apply to tier-3/exception requests, and it should keep the same dependency, version and tenant invalidation metadata as the exact cache.
