"""Evaluate configured incident hypotheses against snapshot evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def values_at_path(document: Any, path: str) -> list[Any]:
    values = [document]
    for segment in path.split("."):
        expanded = []
        for value in values:
            if segment == "*" and isinstance(value, list):
                expanded.extend(value)
            elif segment == "*" and isinstance(value, dict):
                expanded.extend(value.values())
            elif isinstance(value, dict) and segment in value:
                expanded.append(value[segment])
        values = expanded
    return values


def evaluate_hypothesis(snapshot: dict[str, Any], hypothesis: dict[str, Any]) -> dict[str, Any]:
    """Apply all required generic predicates and preserve contradictory evidence."""
    supporting = []
    contradicting = []
    missing = []
    for predicate in hypothesis["predicates"]:
        values = values_at_path(snapshot, predicate["path"])
        if not values:
            missing.append(predicate["path"])
            continue
        operator = predicate["operator"]
        expected = predicate["expected"]
        if operator == "equals":
            passed = any(value == expected for value in values)
        elif operator == "contains":
            passed = any(
                value == expected
                or (isinstance(value, list) and expected in value)
                or (
                    isinstance(value, str)
                    and isinstance(expected, str)
                    and expected in value
                )
                for value in values
            )
        elif operator == "greater_than":
            passed = any(float(value) > float(expected) for value in values)
        elif operator == "less_than":
            passed = any(float(value) < float(expected) for value in values)
        elif operator == "changed":
            passed = (len({json.dumps(value, sort_keys=True) for value in values}) > 1) is bool(expected)
        else:
            raise ValueError(f"Unsupported predicate operator: {operator}")
        evidence = {"path": predicate["path"], "operator": operator, "expected": expected, "observed": values}
        (supporting if passed else contradicting).append(evidence)
    if contradicting:
        status = "rejected"
    elif missing:
        status = "insufficient_evidence"
    else:
        status = "supported"
    return {
        "hypothesis_id": hypothesis["id"],
        "statement": hypothesis["statement"],
        "priority": hypothesis["priority"],
        "status": status,
        "supporting": supporting,
        "contradicting": contradicting,
        "missing": missing,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--hypotheses", type=Path, required=True)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    hypotheses = json.loads(args.hypotheses.read_text(encoding="utf-8"))["hypotheses"]
    results = [evaluate_hypothesis(snapshot, hypothesis) for hypothesis in hypotheses]
    output = Path("reports/hypothesis-results.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()