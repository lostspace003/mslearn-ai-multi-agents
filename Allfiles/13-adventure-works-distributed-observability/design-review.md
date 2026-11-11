# Lab 13 - Design review (Task 7)

**What breaks when context injection is omitted at one boundary?**
The next agent extracts an empty carrier and starts a new root span with a new trace ID. The waterfall splits into two
transactions at that hop, `correlation_complete` becomes false, `OperationId`-based KQL (trace-waterfall.kql) only
returns part of the chain, and an alert on a downstream agent can no longer be attributed to the upstream request.

**Which structured fields are useful without exposing customer content?**
Trace/span IDs, `gen_ai.agent.name`/`gen_ai.agent.id`, `agent.version`, `gen_ai.operation.name`, provider name, token
counts (input/output/total), latency, status, `error.type`, anomaly flags/types, policy ID/version, error-rate values, and a
hashed session ID. A short, curated decision summary is acceptable when it is synthetic or template text. Raw prompts,
model reasoning, customer IDs, emails and payment data are excluded (policy `prohibited_fields`).

**Why would errors and slow traces require collector-side tail sampling rather than head sampling?**
Head sampling decides at the root span, before latency or errors are known, so a 5% ratio discards ~95% of the rare
failing/slow traces. A tail-sampling collector buffers whole traces and keeps them based on outcome (error status,
duration > threshold, anomaly attribute) while sampling healthy traffic down, preserving the evidence needed for incidents.

**How would you correlate simultaneous anomalies into one incident?**
Group signals by trace ID / operation ID first (one chain = one incident), then by agent ID + version and time window.
In Azure Monitor, a single scheduled-query rule evaluating all three signals produces one alert per evaluation window;
use alert processing rules / smart grouping (or ITSM dedup keys built from trace ID + agent) so latency, token and
error-rate signals from the same chain surface as one incident with the earliest failing span as probable root cause.

**Why does the alert consume emitted policy decisions instead of repeating thresholds in KQL?**
The policy (`config/telemetry-policy.yaml`) is the single source of truth: thresholds change in one place, are versioned
(`policy_id`/`policy_version` in the logs), and the alert stays valid without redeploying the rule. Duplicated thresholds in
KQL drift from the runtime decision and produce alerts that disagree with what the agent recorded. Verified in this lab:
changing `latency_threshold_ms`, `error_rate_threshold` and `token_anomaly_sigma` changed decisions with no KQL edit.
