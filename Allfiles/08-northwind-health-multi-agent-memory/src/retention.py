from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .memory_store import PatientMemoryStore


async def prune_memories(
    store: PatientMemoryStore,
    patient_id: str,
    memories: list[dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    """Apply importance and age policy while preserving critical memories."""
    # LAB PLACEHOLDER 6: Replace this line with the Task 6 sample.
    store._authorize(patient_id)
    eligible_ids = sorted(
        str(memory["id"])
        for memory in memories
        if memory.get("patientId") == patient_id
        and not bool(memory.get("critical"))
        and int(memory.get("ttl", -1)) > 0
        and datetime.fromisoformat(
            str(memory["timestamp"]).replace("Z", "+00:00")
        ) + timedelta(seconds=int(memory["ttl"])) <= datetime.now(UTC)
        and float(memory.get("importance", 0)) <= 4.0
    )
    if dry_run:
        return {"status": "dry_run", "eligible_ids": eligible_ids, "deleted_count": 0}
    for memory_id in eligible_ids:
        await store._memories.delete_item(item=memory_id, partition_key=patient_id)
    if eligible_ids:
        await store.write_audit(
            patient_id,
            "retention_prune",
            eligible_ids,
            "expired noncritical memory with finite TTL and importance at or below 4.0",
        )
    return {
        "status": "applied",
        "eligible_ids": eligible_ids,
        "deleted_count": len(eligible_ids),
    }