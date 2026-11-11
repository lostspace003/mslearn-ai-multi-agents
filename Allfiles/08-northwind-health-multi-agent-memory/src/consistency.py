from __future__ import annotations

from typing import Any

from .memory_store import PatientMemoryStore


async def validate_read_your_writes(
    store: PatientMemoryStore,
    memory: dict[str, Any],
) -> dict[str, Any]:
    """Write a memory and point-read it using the returned session token."""
    # LAB PLACEHOLDER 4: Replace this line with the Task 4 sample.
    diagnostics = await store.upsert_memory(memory)
    session_token = diagnostics.get("session_token")
    if not session_token:
        raise RuntimeError("The write response did not include a session token")
    item = await store._memories.read_item(
        item=memory["id"],
        partition_key=memory["patientId"],
        session_token=session_token,
    )
    return {
        "write_id": diagnostics["id"],
        "read_id": item["id"],
        "patientId": item["patientId"],
        "session_token_transferred": True,
        "request_charge": diagnostics["request_charge"],
    }