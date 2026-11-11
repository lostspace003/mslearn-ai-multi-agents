"""Cosmos DB discovery, shared-state, and audit boundaries."""
from __future__ import annotations
import os, time, uuid
from pathlib import Path
from typing import Any
from azure.core import MatchConditions
from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

class Registry:
    def __init__(self) -> None:
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        endpoint=os.getenv("COSMOS_ENDPOINT")
        if not endpoint:
            raise RuntimeError("COSMOS_ENDPOINT is missing; generate the lab-root .env file with azd env get-values")
        client=CosmosClient(endpoint,credential=DefaultAzureCredential())
        database=client.get_database_client(os.getenv("COSMOS_DATABASE_NAME","agent-ecosystem"))
        self.registry=database.get_container_client("registry");self.tasks=database.get_container_client("tasks");self.audit=database.get_container_client("audit")
    def register(self, card: dict[str,Any], tenant_id: str) -> dict[str,Any]:
        """Learner task: validate and upsert a tenant-owned card with TTL."""
        # LAB PLACEHOLDER 1: Replace this line with the Task 1 sample.
        required_fields = ("id", "url", "capabilities")
        if any(not card.get(field) for field in required_fields):
            raise ValueError("Agent card requires id, url, and capabilities")
        if not isinstance(card["capabilities"], list):
            raise ValueError("Agent card capabilities must be a list")

        entry = {
            **card,
            "tenantId": tenant_id,
            "health": "healthy",
            "heartbeat": int(time.time()),
            "ttl": int(os.getenv("REGISTRY_TTL_SECONDS", "300")),
        }
        return self.registry.upsert_item(entry)
    def discover(self, tenant_id: str, capability: str) -> list[dict[str,Any]]:
        """Learner task: parameterized tenant/capability/health query and ranking."""
        # LAB PLACEHOLDER 2: Replace this line with the Task 2 sample.
        cutoff = int(time.time()) - int(os.getenv("HEARTBEAT_MAX_AGE_SECONDS", "120"))
        query = """
        SELECT * FROM c
        WHERE c.tenantId = @tenant
            AND ARRAY_CONTAINS(c.capabilities, @capability)
            AND c.health = "healthy"
            AND c.heartbeat >= @cutoff
        """
        parameters = [
            {"name": "@tenant", "value": tenant_id},
            {"name": "@capability", "value": capability},
            {"name": "@cutoff", "value": cutoff},
        ]
        candidates = list(
            self.registry.query_items(
                query=query,
                parameters=parameters,
                partition_key=tenant_id,
                enable_cross_partition_query=False,
            )
        )
        return sorted(candidates, key=lambda item: float(item.get("load", 1.0)))[:1]
    def update_task(self, tenant_id: str, task_id: str, agent_id: str, contribution: dict[str,Any]) -> dict[str,Any]:
        """Learner task: bounded ETag retry and agent-owned merge."""
        _ = MatchConditions.IfNotModified
        # LAB PLACEHOLDER 3: Replace this line with the Task 3 sample.
        for _ in range(3):
            try:
                current = self.tasks.read_item(item=task_id, partition_key=tenant_id)
            except exceptions.CosmosResourceNotFoundError:
                initial = {
                    "id": task_id,
                    "tenantId": tenant_id,
                    "contributions": {agent_id: contribution},
                    "updatedAt": int(time.time()),
                }
                try:
                    return self.tasks.create_item(initial)
                except exceptions.CosmosResourceExistsError:
                    continue

            current.setdefault("contributions", {})[agent_id] = contribution
            current["updatedAt"] = int(time.time())
            try:
                return self.tasks.replace_item(
                    item=current["id"],
                    body=current,
                    etag=current["_etag"],
                    match_condition=MatchConditions.IfNotModified,
                )
            except exceptions.CosmosHttpResponseError as exc:
                if exc.status_code != 412:
                    raise

        raise RuntimeError("Task update failed after three ETag attempts")
    def resolve_and_audit(self, tenant_id: str, conflict: dict[str,Any]) -> dict[str,Any]:
        """Learner task: deterministic priority/escalation plus audit create_item."""
        # LAB PLACEHOLDER 4: Replace this line with the Task 4 sample.
        candidates = conflict.get("candidates", [])
        if len(candidates) < 2:
            raise ValueError("A conflict requires at least two candidates")

        priority = {"compliance": 3, "risk": 2, "analysis": 1}
        highest = max(priority.get(item.get("role", ""), 0) for item in candidates)
        winners = [
            item
            for item in candidates
            if priority.get(item.get("role", ""), 0) == highest
        ]
        if highest == 0 or len(winners) != 1:
            resolution = "escalated"
            chosen_agent = None
        else:
            resolution = "priority"
            chosen_agent = winners[0]["agent_id"]

        audit_record = {
            "id": str(uuid.uuid4()),
            "tenantId": tenant_id,
            "taskId": conflict["task_id"],
            "timestamp": int(time.time()),
            "resolution": resolution,
            "chosenAgent": chosen_agent,
            "candidates": [
                {"agent_id": item["agent_id"], "role": item["role"]}
                for item in candidates
            ],
        }
        self.audit.create_item(audit_record)
        return {
            "status": resolution,
            "chosen_agent": chosen_agent,
            "audit_id": audit_record["id"],
        }