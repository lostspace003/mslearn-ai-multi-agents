"""Microsoft Foundry prompt-agent topology lifecycle operations."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import DefaultAzureCredential
from packaging.specifiers import SpecifierSet
from packaging.version import Version


def create_client() -> AIProjectClient:
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
    if not endpoint:
        raise RuntimeError("FOUNDRY_PROJECT_ENDPOINT is required")
    return AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())


def load_manifest(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as stream:
        return yaml.safe_load(stream)["release_manifest"]


def definition_from_spec(spec: dict[str, Any], model: str) -> PromptAgentDefinition:
    return PromptAgentDefinition(model=model, instructions=str(spec["instructions"]))


def validate_promotion(manifest: dict[str, Any]) -> None:
    """Fail closed unless approval, evaluation, and technical-file gates pass."""
    # LAB PLACEHOLDER 1: Replace this line with the Task 1 sample.
    failures: list[str] = []
    evaluation = manifest.get("evaluation") or {}
    approval = manifest.get("approval") or {}
    compliance = manifest.get("compliance") or {}
    topology = manifest.get("topology") or {}
    agent_specs = {
        str(item.get("agent_id")): item
        for item in topology.get("agents") or []
    }
    compatibility = topology.get("compatibility") or {}

    if manifest.get("status") != "approved":
        failures.append("manifest status is not approved")
    if approval.get("status") != "approved":
        failures.append("approval status is not approved")
    if set(agent_specs) != {"scanner", "reviewer", "orchestrator"}:
        failures.append("topology must contain scanner, reviewer, and orchestrator")

    try:
        scanner_schema = Version(str(compatibility["scanner_output_schema"]))
        reviewer_requirement = SpecifierSet(
            str(compatibility["reviewer_requires_scanner_schema"])
        )
        if scanner_schema not in reviewer_requirement:
            failures.append("scanner output schema is incompatible with reviewer")
    except (KeyError, TypeError, ValueError):
        failures.append("scanner-to-reviewer compatibility evidence is invalid")

    try:
        reviewer_version = Version(str(agent_specs["reviewer"]["version"]))
        orchestrator_requirement = SpecifierSet(
            str(compatibility["orchestrator_requires_reviewer_version"])
        )
        if reviewer_version not in orchestrator_requirement:
            failures.append("reviewer version is incompatible with orchestrator")
    except (KeyError, TypeError, ValueError):
        failures.append("reviewer-to-orchestrator compatibility evidence is invalid")

    try:
        if float(evaluation["precision"]) < float(evaluation["minimum_precision"]):
            failures.append("precision is below its minimum")
    except (KeyError, TypeError, ValueError):
        failures.append("precision evidence is missing or invalid")

    try:
        if float(evaluation["recall"]) < float(evaluation["minimum_recall"]):
            failures.append("recall is below its minimum")
    except (KeyError, TypeError, ValueError):
        failures.append("recall evidence is missing or invalid")

    if compliance.get("material_change_assessment") is not True:
        failures.append("material change assessment is missing")
    technical_file = str(compliance.get("technical_file_reference", "")).strip()
    if not technical_file or not Path(technical_file).is_file():
        failures.append("technical file reference is missing or unavailable")

    if failures:
        raise PermissionError("Promotion denied: " + "; ".join(failures))


def list_inventory(client: AIProjectClient) -> list[dict[str, Any]]:
    inventory = []
    for agent in client.agents.list():
        versions = [
            {"version": item.version, "status": item["status"]}
            for item in client.agents.list_versions(agent_name=agent.name)
        ]
        inventory.append({"agent": agent.name, "versions": versions})
    return inventory


def promote_topology(
    client: AIProjectClient,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    validate_promotion(manifest)
    model = os.environ.get(
        "FOUNDRY_MODEL_NAME",
        str(manifest["configuration"]["model_deployment"]),
    )
    created: list[tuple[str, str]] = []
    versions: dict[str, dict[str, str]] = {}
    try:
        for spec in manifest["topology"]["agents"]:
            agent_name = str(spec["agent_id"])
            version = client.agents.create_version(
                agent_name=agent_name,
                definition=definition_from_spec(spec, model),
                description=f"Fabrikam governed release {manifest['release_id']}",
            )
            foundry_version = str(version.version)
            created.append((agent_name, foundry_version))
            versions[agent_name] = {
                "logical_version": str(spec["version"]),
                "foundry_version": foundry_version,
                "status": str(version["status"]),
            }
    except Exception as promotion_error:
        cleanup_failures: list[str] = []
        for agent_name, foundry_version in reversed(created):
            try:
                client.agents.delete_version(
                    agent_name=agent_name,
                    agent_version=foundry_version,
                )
            except Exception as cleanup_error:
                cleanup_failures.append(
                    f"{agent_name}:{foundry_version} "
                    f"({type(cleanup_error).__name__}: {cleanup_error})"
                )
        if cleanup_failures:
            original = f"{type(promotion_error).__name__}: {promotion_error}"
            raise RuntimeError(
                f"Promotion failed with {original}; rollback cleanup also failed for "
                + "; ".join(cleanup_failures)
            ) from promotion_error
        raise
    return {"release_id": str(manifest["release_id"]), "versions": versions}


def reconcile_orphaned_versions(
    client: AIProjectClient,
    targets: list[tuple[str, str]],
    confirmed: bool,
) -> dict[str, Any]:
    """Idempotently delete exact agent versions reported by failed rollback cleanup."""
    if not confirmed:
        raise RuntimeError("Orphan reconciliation requires --confirm-delete-orphans")
    normalized = sorted(
        {
            (agent_name.strip(), agent_version.strip())
            for agent_name, agent_version in targets
        }
    )
    if not normalized or any(not agent_name or not agent_version for agent_name, agent_version in normalized):
        raise ValueError("At least one non-empty agent:version target is required")

    versions_by_agent: dict[str, set[str]] = {}
    deleted: list[str] = []
    already_absent: list[str] = []
    failures: list[str] = []
    for agent_name, agent_version in normalized:
        if agent_name not in versions_by_agent:
            versions_by_agent[agent_name] = {
                str(item.version)
                for item in client.agents.list_versions(agent_name=agent_name)
            }
        target = f"{agent_name}:{agent_version}"
        if agent_version not in versions_by_agent[agent_name]:
            already_absent.append(target)
            continue
        try:
            client.agents.delete_version(
                agent_name=agent_name,
                agent_version=agent_version,
            )
            deleted.append(target)
            versions_by_agent[agent_name].remove(agent_version)
        except Exception as cleanup_error:
            failures.append(
                f"{target} ({type(cleanup_error).__name__}: {cleanup_error})"
            )
    if failures:
        raise RuntimeError(
            "Orphan reconciliation incomplete; "
            f"deleted={deleted}; already_absent={already_absent}; failures={failures}"
        )
    return {
        "status": "reconciled",
        "deleted": deleted,
        "already_absent": already_absent,
    }


def retire_version(
    client: AIProjectClient,
    agent_name: str,
    agent_version: str,
    request: dict[str, Any],
    policy: dict[str, Any],
    confirmed: bool,
) -> dict[str, Any]:
    """Delete only after every retirement request and policy gate passes."""
    if not confirmed:
        raise RuntimeError("Retirement requires --confirm-delete-version")
    retirement_policy = policy["retirement"]
    failures = []
    if request.get("agent_id") != agent_name or str(request.get("version")) != agent_version:
        failures.append("request target does not match agent name and version")
    notice_days = (
        date.fromisoformat(str(request["deletion_date"]))
        - date.fromisoformat(str(request["deprecated_date"]))
    ).days
    if notice_days < int(retirement_policy["minimum_notice_days"]):
        failures.append("minimum retirement notice not met")
    if date.today() < date.fromisoformat(str(request["deletion_date"])):
        failures.append("retirement effective date has not been reached")
    if retirement_policy["require_zero_active_consumers"] and int(request["active_consumers"]) != 0:
        failures.append("active consumers remain")
    if retirement_policy["require_zero_active_pins"] and int(request["active_pins"]) != 0:
        failures.append("active version pins remain")
    if retirement_policy["require_archive_complete"] and request.get("archive_complete") is not True:
        failures.append("archive is incomplete")
    if retirement_policy["require_deprecation_recorded"] and request.get("deprecation_recorded") is not True:
        failures.append("deprecation is not recorded")
    if request.get("governance_approval") != retirement_policy["required_approval_status"]:
        failures.append("governance approval is missing")
    if failures:
        raise PermissionError("Retirement denied: " + "; ".join(failures))
    client.agents.delete_version(agent_name=agent_name, agent_version=agent_version)
    return {
        "agent": agent_name,
        "version": agent_version,
        "retired": True,
        "notice_days": notice_days,
        "active_consumers": 0,
        "active_pins": 0,
        "archive_complete": True,
        "deprecation_recorded": True,
        "governance_approval": request["governance_approval"],
    }