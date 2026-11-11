# Lab 10 design review - Fabrikam zero trust

## Task 3 - handoff policy trace

| Request | Tenant matches? | Caller may invoke target? | Fields the target needs | Result |
|---|---|---|---|---|
| allowed-orchestrator-to-scanner | yes (tenant-a) | yes (orchestrator -> scanner) | requestId, tenantId, sourceCode | allow |
| denied-cross-tenant | no (requests tenant-b, caller is tenant-a) | not evaluated (fails `enforce_tenant` first) | none | deny |
| denied-specialist-lateral-movement | yes | no (scanner -> compliance not in call graph) | none | deny |
| allowed-minimized-compliance-handoff | yes | yes (orchestrator -> compliance) | requestId, tenantId, repositoryRegion, dataClassification, consentRecorded (no sourceCode) | allow |

`enforce_tenant` fails closed: an empty tenant and a mismatched tenant both raise `PermissionError` before the
call-graph check, model call, or Cosmos DB access.

## Task 5 - least-privilege boundaries

- Foundry and Cosmos DB set `disableLocalAuth: true`; no keys are used by the app (Entra ID / DefaultAzureCredential only).
- Network: Foundry `publicNetworkAccess: Enabled`, `defaultAction: Allow`; Cosmos `publicNetworkAccess: Enabled`.
  This is residual sandbox network trust, not zero network trust. Production needs private endpoints, private DNS,
  deny-by-default ACLs and a chosen Foundry managed-network isolation mode (decided at creation time).
- Cosmos data-plane RBAC: the learner gets exactly two assignments, scoped to `/colls/tenant-policies` and
  `/colls/security-audit`, not to the account, resource group or subscription.
- The project managed identity authenticates the agent identity blueprint; downstream tool permissions belong on the
  agent's `agentIdentityId` (and a published agent gets a separate identity).

## Optional challenge - failure investigation

| Boundary | Evidence that distinguishes it |
|---|---|
| Identity (authentication / RBAC) | HTTP 401/403 from Foundry or Cosmos data plane (e.g. `Forbidden ... does not have required RBAC permissions`); the request reached the service. |
| Network | Connection refused / timeout / DNS failure or 403 "public network access disabled" / "request originated from IP not allowed" before any RBAC evaluation. |
| Tenant policy | Local `PermissionError: Tenant context does not match the verified caller` - raised in-process, no outbound call, no Foundry trace, no audit write. |
| Agent call graph | Local `PermissionError: Agent call denied: X cannot call Y` - tenant check passed, call graph failed. |
| Data partition | Cosmos read with another partition key returns 404 NotFound (item lives in `tenant-a` partition); no cross-partition leakage. |
