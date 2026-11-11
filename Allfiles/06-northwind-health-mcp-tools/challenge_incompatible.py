"""Optional challenge: reject an incompatible tool version; bounded retry on dependency timeout.

Runs offline. Adds an incompatible catalog entry in memory only (assets/tool-catalog.json is unchanged).
"""
from __future__ import annotations

import asyncio
import copy
import json
from unittest import mock

from src import catalog
from src.client import discover_tools

base = catalog.load_catalog()
incompatible = copy.deepcopy(base["tools"][0])
incompatible.update(version="2.0.0", protocol="mcp-2026-draft", lifecycle="active")
patched = copy.deepcopy(base)
# Replace the v1 entry so only the incompatible v2 entry is a candidate.
patched["tools"] = [incompatible] + base["tools"][1:]


def compatibility_reasons(entry: dict, required_major: int) -> list[str]:
    reasons = []
    if entry["lifecycle"] != "active":
        reasons.append(f"lifecycle={entry['lifecycle']}")
    major = int(entry["version"].split(".", 1)[0])
    if major != required_major:
        reasons.append(f"major {major} != required {required_major}")
    return reasons


invoked = []
with mock.patch.object(catalog, "load_catalog", return_value=patched):
    print("Reasons:", compatibility_reasons(incompatible, 1))
    try:
        catalog.select_compatible_tool({"lookup_drug_interaction"}, "lookup_drug_interaction", 1)
        invoked.append("lookup_drug_interaction")
        print("UNEXPECTED: incompatible entry selected")
    except ValueError as error:
        print("Selection rejected:", error)
print("Tool invocations:", invoked)


async def bounded_retry(url: str, attempts: int = 3, timeout_s: float = 2.0) -> dict:
    for attempt in range(1, attempts + 1):
        try:
            return {"status": "ok", "tools": await asyncio.wait_for(discover_tools(url), timeout_s)}
        except Exception as error:  # noqa: BLE001 - simulated dependency failure
            print(f"attempt {attempt}/{attempts} failed: {type(error).__name__}")
            await asyncio.sleep(0.2 * 2 ** (attempt - 1))
    return {"status": "unavailable", "reason": "dependency_timeout", "fallback": "consult_pharmacist"}


# Port 8999 has nothing listening, which simulates the dependency being down.
print(json.dumps(asyncio.run(bounded_retry("http://127.0.0.1:8999/mcp")), indent=2))
