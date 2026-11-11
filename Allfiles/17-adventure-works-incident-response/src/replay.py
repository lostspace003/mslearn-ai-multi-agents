"""Reconstruct a captured span sequence without live side effects."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def reconstruct_trace(snapshot: dict[str, Any]) -> dict[str, Any]:
    if snapshot.get("replay_mode") is not True:
        raise ValueError("Snapshot must explicitly enable replay mode")
    prompt_checks = []
    for agent, prompt in snapshot.get("prompts", {}).items():
        actual = hashlib.sha256(prompt.encode()).hexdigest()
        expected = snapshot.get("prompt_hashes", {}).get(agent)
        prompt_checks.append({
            "agent": agent, "expected_hash": expected,
            "actual_hash": actual, "matches": actual == expected,
        })
    steps = []
    for index, span in enumerate(snapshot.get("spans", []), start=1):
        tool_name = span.get("tool_name")
        mock = snapshot.get("tool_mocks", {}).get(tool_name) if tool_name else None
        status = span.get("success", span.get("status", span.get("Success")))
        duration_ms = span.get("duration_ms", span.get("DurationMs"))
        steps.append({
            "sequence": index,
            "span_name": span.get("span_name") or span.get("Name"),
            "status": status,
            "mock_used": mock is not None,
            "mock_response": mock.get("response") if mock else None,
            "duration_ms": duration_ms,
        })
    divergences = [check for check in prompt_checks if not check["matches"]]
    tool_steps = [step for step in steps if step["mock_used"]]
    metrics = {
        "prompt_count": len(prompt_checks),
        "prompt_match_rate": round(
            sum(check["matches"] for check in prompt_checks) / len(prompt_checks), 4
        ) if prompt_checks else 0.0,
        "tool_step_count": len(tool_steps),
        "tool_mock_response_count": sum(step["mock_response"] is not None for step in tool_steps),
        "failed_step_count": sum(step["status"] is False for step in steps),
        "divergence_count": len(divergences),
    }
    return {
        "operation_id": snapshot["operation_id"],
        "side_effects_enabled": False,
        "prompt_checks": prompt_checks,
        "steps": steps,
        "divergences": divergences,
        "comparison_metrics": metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = reconstruct_trace(json.loads(args.snapshot.read_text(encoding="utf-8")))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()