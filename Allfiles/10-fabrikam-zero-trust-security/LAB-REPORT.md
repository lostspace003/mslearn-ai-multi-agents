# Lab 10 report - Apply zero trust to a Microsoft Foundry multi-agent workflow

**Result: PASS** (one portal-only trace inspection step is left for the user)

- Resource group: `rg-lab10-198dc6fb` (eastus2), subscription "Visual Studio Subscription"
- Foundry account `fdryqfx4h6llfuyi2`, project `lab10-lab10-198dc6`, model deployment `gpt-5.4-mini` (2026-03-17)
- Cosmos DB `cosmosqfx4h6llfuyi2`, database `fabrikam-review`, containers `tenant-policies`, `security-audit`
- App Insights `appi-lab10-qfx4h6llfuyi2` + Log Analytics workspace, connected to the project for tracing
- Provisioned with Azure CLI (`az deployment group create` through the deploy_lab.py helper) instead of `azd provision`. `.env` was generated from the deployment outputs and contains no keys.

## Tasks

| Task | What was done | Evidence |
|---|---|---|
| 1 Prepare | Tools checked. Azure CLI was already signed in. | - |
| 2 venv | `scripts/setup.ps1` created `.venv` (azure-ai-projects 2.10.0, azure-cosmos 4.17.1) | - |
| 3 Tenant handoffs | Filled LAB PLACEHOLDER 1 in `src/security.py` `enforce_tenant`, which fails closed on a missing or mismatched tenant. Ran the decisions, minimization, auth-flow and validation script. | `artifacts-task3-deterministic.json`, `artifacts-task3-validation.txt` (`READY (local)`, `TASK_1_VALIDATION_PASSED`) |
| 4 Provision | Bicep compiled and the deployment succeeded. Preflight shows all PASS and `READY (local)`. | `.env`, `artifacts-task5-least-privilege.txt` (preflight at top) |
| 5 Least privilege | Checked disableLocalAuth, the network settings and the Cosmos SQL role assignments with `az` (values come from `.env` instead of `azd env get-values`) | `artifacts-task5-least-privilege.txt` |
| 6 Live run | `python -m src.main --live` created and invoked 3 Foundry agents, with no 403 errors | `artifacts-task6-live.json` |
| 7 Evidence | Ran the tenant/audit validation and checked the agent versions. Re-ran the deterministic checks. | `artifacts-task7-evidence.txt` |
| Optional challenge | Sent a cross-tenant request (verified tenant-a asking for tenant-b) and ran a partition probe | `artifacts-challenge-cross-tenant.txt`, `design-review.md` |
| 8 Cleanup | **Not run, on purpose**: the brief says to keep the resources | - |

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Decisions are allow, deny (tenant mismatch), deny (agent call), allow | PASS | Reasons: "Tenant context does not match the verified caller" and "Agent call denied: security-scanner cannot call compliance-agent" |
| Compliance handoff forwards only consentRecorded, dataClassification, repositoryRegion, requestId, tenantId (no sourceCode) | PASS | task3 artifacts |
| Auth flows are managed_identity, on_behalf_of, oauth2_pkce, key_vault_fallback | PASS | task3 artifacts |
| Preflight shows `READY (local)` and `TASK_1_VALIDATION_PASSED` | PASS | task3 validation |
| Bicep compiles, provisioning succeeds, .env has no secrets | PASS | `.env` |
| disableLocalAuth: true on Foundry and Cosmos (declared in Bicep and effective in Azure) | PASS | main.bicep lines 43 and 77; az shows `disableLocalAuth: true` on both |
| Foundry: publicNetworkAccess Enabled, defaultAction Allow. Cosmos: publicNetworkAccess Enabled. Recorded as residual network trust. | PASS (as designed) | task5 artifact |
| Exactly 2 Cosmos assignments for the principal, scoped to `/colls/tenant-policies` and `/colls/security-audit` (Built-in Data Contributor `...0002`), with no account, RG or subscription scope | PASS | task5 artifact |
| Foundry versions exist for review-orchestrator, security-scanner, compliance-agent | PASS | version 1 of each |
| Specialist response IDs exist | PASS | scanner `resp_00ee7923...209a32`, compliance `resp_06bee8e7...e3f9da0` |
| Orchestrator synthesis response | PASS | `resp_0e00e200...ffdd8ef` |
| crossTenantHandoffDenied = true | PASS | live JSON |
| Audit event has tenantId, agentId, action, decision, correlationId and no sourceCode | PASS | `TENANT_AND_AUDIT_EVIDENCE_VALIDATED` (audit id `c654c6df-e842-4dfa-9db5-ff21ae0f859c`) |
| Tenant policy belongs to tenant-a | PASS | live JSON |
| Rerun: productionControlFailures empty, decisions allow,deny,deny,allow | PASS | task7 artifact |
| Optional challenge: cross-tenant request denied before any Cosmos or model call | PASS | the denial comes from tenant policy. A partition probe shows review-policy returns 404 under the tenant-b partition. |

## Code fixes and deviations
- No fixes to the shipped code were needed. The only code change is the LAB PLACEHOLDER 1 fill. The md snippet uses 2-space indentation; I used 4 spaces to match the source.
- I used Azure CLI instead of azd for Tasks 4 and 5. `$values` came from `.env`.
- Task 8 cleanup was skipped on purpose.

## Left for the user
- **Portal step (Task 7, steps 2-7):** in the Foundry portal, open project `lab10-lab10-198dc6`, go to Agents > Traces, find the three response IDs above, and check the inputs. Scanner input should be `print('synthetic')` only. Compliance input should have metadata and no sourceCode. Orchestrator input should have tenant-a, req-001 and both specialist results. tenant-b should not appear anywhere. A KQL query against App Insights returned no rows yet: the local Python client does not export OpenTelemetry, so trace inspection is done in the portal.
- Delete `rg-lab10-198dc6fb` when it is no longer needed. It contains billable Foundry, Cosmos DB and App Insights resources.
