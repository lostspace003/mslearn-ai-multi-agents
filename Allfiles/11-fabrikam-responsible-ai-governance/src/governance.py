"""Deterministic controls and evidence for a Foundry multi-agent review."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import yaml
from azure.identity import DefaultAzureCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry._logs import get_logger_provider

_telemetry_connection_string: str | None = None
_telemetry_lock = Lock()


def load_policy(path: str) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def calculate_fairness_evidence(probes: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[float]] = {}
    for probe in probes:
        group = str(probe["group"])
        groups.setdefault(group, []).append(float(probe["positive_outcome"]))
    rates = {name: sum(values) / len(values) for name, values in groups.items()}
    disparity = max(rates.values()) - min(rates.values())
    return {"group_positive_rates": rates, "max_disparity": round(disparity, 4)}


def requires_human_review(policy: dict[str, Any], evidence: dict[str, Any]) -> bool:
    """Apply the fairness threshold to complete governance evidence."""
    # LAB PLACEHOLDER 1: Replace this line with the Task 1 sample.
    fairness = evidence.get("fairness")
    if not isinstance(fairness, dict) or "max_disparity" not in fairness:
        return True

    try:
        return (
            float(fairness["max_disparity"])
            > float(policy["thresholds"]["max_fairness_disparity"])
        )
    except (KeyError, TypeError, ValueError):
        return True


def build_agent_payload(
    agent_name: str,
    scenario: dict[str, Any],
    evidence: dict[str, Any],
    specialist_outputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_id = str(scenario["request_id"])
    if agent_name == "security-reviewer":
        return {
            "requestId": request_id,
            "sourceCode": scenario["source_code"],
            "evidenceReference": scenario["evidence_reference"],
        }
    if agent_name == "fairness-auditor":
        return {
            "requestId": request_id,
            "groupPositiveRates": evidence["fairness"]["group_positive_rates"],
            "maxDisparity": evidence["fairness"]["max_disparity"],
            "policyThreshold": evidence["fairness_threshold"],
        }
    if agent_name == "governance-orchestrator":
        return {
            "requestId": request_id,
            "policyVersion": evidence["policy_version"],
            "fairness": evidence["fairness"],
            "humanReviewRequired": evidence["human_review_required"],
            "specialistResults": specialist_outputs or {},
        }
    raise ValueError(f"Unsupported agent: {agent_name}")


def build_governance_evidence(
    scenario: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    fairness = calculate_fairness_evidence(list(scenario["fairness_probes"]))
    evidence = {
        "schema_version": "2.0",
        "evidence_scope": "single_process_local_jsonl",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": scenario["correlation_id"],
        "tenant_id_hash": _sha256(str(scenario["tenant_id"]))[:16],
        "input_sha256": _sha256(str(scenario["source_code"])),
        "purpose": scenario["purpose"],
        "policy_id": policy["policy_id"],
        "policy_version": policy["version"],
        "fairness_threshold": policy["thresholds"]["max_fairness_disparity"],
        "fairness": fairness,
    }
    evidence["human_review_required"] = requires_human_review(policy, evidence)
    return evidence


def append_evidence(path: str, record: dict[str, Any]) -> None:
    """Append single-process local evidence; use a central sink for concurrent writers."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, separators=(",", ":")) + "\n")


def emit_evidence_to_azure_monitor(
    record: dict[str, Any],
) -> None:
    """Export one minimized governance decision to Application Insights."""
    connection_string = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
    if not connection_string:
        raise RuntimeError("APPLICATIONINSIGHTS_CONNECTION_STRING is required")

    global _telemetry_connection_string
    with _telemetry_lock:
        if _telemetry_connection_string is None:
            configure_azure_monitor(
                connection_string=connection_string,
                credential=DefaultAzureCredential(),
                logger_name="fabrikam.governance",
                enable_live_metrics=False,
            )
            _telemetry_connection_string = connection_string
        elif _telemetry_connection_string != connection_string:
            raise RuntimeError(
                "Azure Monitor telemetry is already configured with a different connection string"
            )
    logger = logging.getLogger("fabrikam.governance")
    logger.setLevel(logging.INFO)
    logger.info(
        "fabrikam.governance.evidence",
        extra={
            "policy_id": str(record["policy_id"]),
            "policy_version": str(record["policy_version"]),
            "correlation_id": str(record["correlation_id"]),
            "tenant_id_hash": str(record["tenant_id_hash"]),
            "input_sha256": str(record["input_sha256"]),
            "purpose": str(record["purpose"]),
            "human_review_required": bool(record["human_review_required"]),
            "max_fairness_disparity": float(record["fairness"]["max_disparity"]),
            "agent_response_ids_json": json.dumps(record["agent_response_ids"], separators=(",", ":")),
            "evidence_schema_version": str(record["schema_version"]),
        },
    )
    provider = get_logger_provider()
    if hasattr(provider, "force_flush") and not provider.force_flush(timeout_millis=10000):
        raise RuntimeError("Azure Monitor exporter did not flush governance evidence")