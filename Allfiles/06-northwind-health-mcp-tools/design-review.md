# Lab 06 - Design review answers

**Which errors should be retried, and which should immediately return a structured permanent failure?**
Retry, with bounded exponential backoff and a circuit breaker, only on transient transport or dependency faults: connection resets, timeouts, HTTP 429/502/503/504 (for example, the Container App cold-start 504 seen in this lab), and token-endpoint throttling. Return the catalog's structured fallback right away, with no retry, for permanent faults: no compatible active tool version, schema-validation failure, a `not_found` handler result, invalid arguments, and 401/403 consent or authorization errors. Retrying these cannot change the outcome and only adds load.

**What catalog fields are required to support a 90-day deprecation window?**
`version` (semver), `lifecycle` (active / deprecated / retired), `deprecated_on`, `sunset_date` (deprecated_on + 90 days), `replacement` (tool name plus version), `min_client_major` or a compatibility range, an owner/contact, and a changelog or migration link. Selection should warn on `deprecated`, refuse after `sunset_date`, and telemetry should count callers still using the deprecated version.

**How would per-user OAuth passthrough change the authorization boundary?**
Today the Container App validates a token for `api://<app>` and the server trusts the caller as a whole. With per-user passthrough, the server would receive the user's delegated token, or an on-behalf-of token exchanged from it, and pass it to downstream systems. Authorization would then be enforced per user and per scope at each dependency, not at the MCP edge alone. That brings in consent management, audience restriction, token-forwarding risk (the confused-deputy problem), and per-user audit. The workload managed identity would be used only for non-user-scoped resources.

**Which telemetry fields support diagnosis without disclosing clinical inputs?**
`event`, `tool_name`, tool `version`, `correlation_id`, `status` / error class, latency, retry count, fallback reason, catalog version, server revision, and a caller app or tenant ID. Never log drug names, sites tied to patients, patient identifiers, tool arguments or results, or tokens. The lab server logs only event, tool_name, correlation_id and status; the local log was checked and contains 0 medication values.
