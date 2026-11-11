from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_catalog() -> dict[str, Any]:
    return json.loads((ROOT / "assets" / "tool-catalog.json").read_text(encoding="utf-8"))


def select_compatible_tool(
    discovered_names: set[str],
    requested_name: str,
    required_major: int,
) -> dict[str, Any]:
    """Select an active, discovered tool with a compatible semantic version."""
    # LAB PLACEHOLDER 3: Replace this line with the Task 3 sample.
    candidates = [
        entry
        for entry in load_catalog()["tools"]
        if entry["name"] == requested_name
        and entry["name"] in discovered_names
        and entry["lifecycle"] == "active"
        and int(entry["version"].split(".", maxsplit=1)[0]) == required_major
    ]
    if not candidates:
        raise ValueError(
            f"No active discovered {requested_name!r} tool supports major {required_major}"
        )
    return min(candidates, key=lambda entry: entry["p95_latency_ms"])