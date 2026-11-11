"""Fail-closed authorization controls for the Fabrikam Foundry agent graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VerifiedCaller:
    """Claims accepted only after the API boundary validates the JWT."""

    agent_id: str
    tenant_id: str


def enforce_tenant(requested_tenant_id: str, verified_tenant_id: str) -> None:
    """Reject missing or mismatched tenant context before any downstream call."""
    # LAB PLACEHOLDER 1: Replace this line with the Task 1 sample.
    if not requested_tenant_id:
        raise PermissionError("Tenant context is required")
    if requested_tenant_id != verified_tenant_id:
        raise PermissionError("Tenant context does not match the verified caller")


def authorize_handoff(
    caller: VerifiedCaller,
    target_agent: str,
    requested_tenant_id: str,
    policy: dict[str, Any],
) -> None:
    """Authorize one edge in the multi-agent graph after tenant validation."""
    enforce_tenant(requested_tenant_id, caller.tenant_id)
    allowed_targets = policy["agentCallGraph"].get(caller.agent_id, [])
    if target_agent not in allowed_targets:
        raise PermissionError(
            f"Agent call denied: {caller.agent_id} cannot call {target_agent}"
        )


def minimize_for_agent(target_agent: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Send each specialist only the fields required for its function."""
    common = {
        "requestId": payload["requestId"],
        "tenantId": payload["tenantId"],
    }
    if target_agent == "security-scanner":
        return {**common, "sourceCode": payload["sourceCode"]}
    if target_agent == "compliance-agent":
        return {
            **common,
            "repositoryRegion": payload["repositoryRegion"],
            "dataClassification": payload["dataClassification"],
            "consentRecorded": payload["consentRecorded"],
        }
    raise ValueError(f"Unknown target agent: {target_agent}")


def select_authentication_flow(operation: dict[str, Any]) -> str:
    """Select an authentication flow without silently escalating privileges."""
    if operation.get("requiresUserPermissions"):
        resource = operation.get("resourceType")
        if resource == "microsoft":
            return "on_behalf_of"
        if resource == "third_party":
            return "oauth2_pkce"
    if operation.get("supportsManagedIdentity"):
        return "managed_identity"
    if operation.get("keyStoredInKeyVault") and operation.get("rotationDays", 0) <= 90:
        return "key_vault_fallback"
    raise PermissionError("No zero-trust authentication flow satisfies this operation")


def validate_production_controls(policy: dict[str, Any]) -> list[str]:
    """Validate controls represented as architecture evidence in this lab."""
    failures: list[str] = []
    network = policy["productionNetwork"]
    if network.get("defaultAction") != "Deny":
        failures.append("production network must deny by default")
    if not network.get("privateEndpointsRequired"):
        failures.append("production data services require private endpoints")
    if not network.get("mutualTlsBetweenExternalAgents"):
        failures.append("external agent services require mutual TLS")
    secrets = policy["secretsLifecycle"]
    if secrets.get("storage") != "key_vault" or secrets.get("maximumRotationDays", 999) > 90:
        failures.append("fallback credentials require Key Vault and rotation within 90 days")
    compliance = policy["compliance"]
    for field in ("tenantId", "agentId", "action", "decision", "correlationId"):
        if field not in compliance.get("requiredAuditFields", []):
            failures.append(f"audit schema is missing {field}")
    return failures