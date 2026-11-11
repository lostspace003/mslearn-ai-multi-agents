"""Atomic quota, rate, usage-metering, and chargeback records in Azure Cosmos DB."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from azure.core import MatchConditions
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import (
    CosmosHttpResponseError,
    CosmosResourceExistsError,
    CosmosResourceNotFoundError,
)
from azure.identity import DefaultAzureCredential


def create_usage_container() -> Any:
    endpoint = os.environ.get("COSMOS_ENDPOINT", "")
    if not endpoint:
        raise RuntimeError("COSMOS_ENDPOINT is required")
    credential = DefaultAzureCredential(
        managed_identity_client_id=os.environ.get("USAGE_IDENTITY_CLIENT_ID")
    )
    client = CosmosClient(endpoint, credential=credential)
    return client.get_database_client(
        os.environ.get("COSMOS_DATABASE", "lifecycle")
    ).get_container_client(os.environ.get("COSMOS_CONTAINER", "usage-meters"))


def enforce_and_meter_usage(
    container: Any,
    request: dict[str, Any],
    policy: dict[str, Any],
    max_attempts: int = 5,
) -> dict[str, Any]:
    """Atomically enforce one rate window and monthly token quota, then meter cost."""
    # LAB PLACEHOLDER 2: Replace this line with the Task 2 sample.
    controls = policy["usage_governance"]
    token_count = int(request["token_count"])
    if token_count <= 0:
        raise ValueError("token_count must be positive")
    tenant_id = str(request["tenant_id"])
    cost_center = str(request["cost_center"])
    if not tenant_id or not cost_center:
        raise ValueError("tenant_id and cost_center are required")

    now = datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    rate_window = now.strftime("%Y-%m-%dT%H:%M")
    allocation_key = f"{tenant_id}:{cost_center}"
    meter_id = f"{allocation_key}:{month}"

    for _ in range(max_attempts):
        try:
            meter = container.read_item(item=meter_id, partition_key=allocation_key)
        except CosmosResourceNotFoundError:
            meter = {
                "id": meter_id,
                "allocation_key": allocation_key,
                "tenant_id": tenant_id,
                "cost_center": cost_center,
                "month": month,
                "monthly_tokens": 0,
                "request_count": 0,
                "estimated_charge": 0.0,
                "rate_window": rate_window,
                "rate_window_requests": 0,
            }
            try:
                container.create_item(meter)
            except CosmosResourceExistsError:
                continue
            meter = container.read_item(item=meter_id, partition_key=allocation_key)

        window_requests = (
            int(meter["rate_window_requests"])
            if meter["rate_window"] == rate_window
            else 0
        )
        if window_requests + 1 > int(controls["requests_per_minute"]):
            raise PermissionError("Per-minute request limit exceeded")
        new_monthly_tokens = int(meter["monthly_tokens"]) + token_count
        if new_monthly_tokens > int(controls["monthly_token_quota"]):
            raise PermissionError("Monthly token quota exceeded")

        charge = token_count / 1000 * float(controls["price_per_1000_tokens"])
        meter.update(
            {
                "monthly_tokens": new_monthly_tokens,
                "request_count": int(meter["request_count"]) + 1,
                "estimated_charge": round(
                    float(meter["estimated_charge"]) + charge,
                    6,
                ),
                "rate_window": rate_window,
                "rate_window_requests": window_requests + 1,
                "last_metered_at": now.isoformat(),
                "currency": str(controls["currency"]),
                "agent_id": str(request["agent_id"]),
                "agent_version": str(request["agent_version"]),
            }
        )
        try:
            saved = container.replace_item(
                item=meter_id,
                body=meter,
                etag=meter["_etag"],
                match_condition=MatchConditions.IfNotModified,
            )
            return {
                "decision": "allow",
                "meter_id": saved["id"],
                "allocation_key": allocation_key,
                "monthly_tokens": saved["monthly_tokens"],
                "monthly_token_quota": int(controls["monthly_token_quota"]),
                "rate_window_requests": saved["rate_window_requests"],
                "requests_per_minute": int(controls["requests_per_minute"]),
                "estimated_charge": saved["estimated_charge"],
                "currency": saved["currency"],
                "metered_at": saved["last_metered_at"],
            }
        except CosmosHttpResponseError as error:
            if error.status_code != 412:
                raise

    raise RuntimeError("Usage meter update conflicted too many times")