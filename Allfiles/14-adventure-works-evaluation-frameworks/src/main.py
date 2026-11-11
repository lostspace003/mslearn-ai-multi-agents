"""Run live multi-agent evaluation and apply deterministic quality gates."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from azure.ai.evaluation import evaluate
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from .evaluators import create_evaluators


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def calibration_agreement(rows: list[dict[str, Any]]) -> float:
    """Return exact agreement between rounded judge scores and human labels."""
    labeled = []
    for row in rows:
        human_label = (
            row.get("human_label")
            or row.get("data.human_label")
            or row.get("inputs.human_label")
        )
        judge_score = row.get("outputs.journey_coherence.journey_coherence")
        if human_label is not None and judge_score is not None:
            labeled.append(int(human_label) == round(float(judge_score)))
    return sum(labeled) / len(labeled) if labeled else 0.0


def apply_regression_gate(
    metrics: dict[str, float], agreement: float, config: dict[str, Any]
) -> dict[str, Any]:
    """Compare measured metrics with absolute, delta, and calibration gates."""
    comparisons = []
    failed_gates = []
    for name, policy in config["metrics"].items():
        measured = metrics.get(name)
        if measured is None:
            failed_gates.append(f"{name}: missing measured metric")
            comparisons.append({"metric": name, "status": "missing"})
            continue
        delta = measured - float(policy["baseline"])
        passed = measured >= float(policy["minimum"]) and delta >= -float(policy["maximum_drop"])
        comparisons.append({
            "metric": name,
            "measured": measured,
            "baseline": policy["baseline"],
            "delta": round(delta, 4),
            "minimum": policy["minimum"],
            "maximum_drop": policy["maximum_drop"],
            "passed": passed,
        })
        if not passed:
            failed_gates.append(name)
    if agreement < float(config["minimum_calibration_agreement"]):
        failed_gates.append("judge_calibration")
    return {
        "passed": not failed_gates,
        "failed_gates": failed_gates,
        "comparisons": comparisons,
        "calibration_agreement": agreement,
        "minimum_calibration_agreement": config["minimum_calibration_agreement"],
    }


def run(data_path: Path, output_path: Path) -> dict[str, Any]:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    endpoint = os.environ["FOUNDRY_ACCOUNT_ENDPOINT"]
    deployment = os.environ["FOUNDRY_MODEL_NAME"]
    api_version = os.getenv("FOUNDRY_API_VERSION", "2024-10-21")
    config = load_json(Path("assets/evaluation-config.json"))
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    model_config = {
        "azure_endpoint": endpoint,
        "azure_deployment": deployment,
        "api_version": api_version,
        "project_endpoint": os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    }
    evaluators = create_evaluators(model_config, credential)

    evaluation = evaluate(
        data=str(data_path),
        evaluators=evaluators,
        evaluator_config={
            "intent_resolution": {
                "column_mapping": {
                    "query": "${data.query}",
                    "response": "${data.response}",
                }
            },
            "task_adherence": {
                "column_mapping": {
                    "query": "${data.query}",
                    "response": "${data.response}",
                }
            },
            "response_completeness": {
                "column_mapping": {
                    "response": "${data.response}",
                    "ground_truth": "${data.expected_behavior}",
                }
            },
            "journey_coherence": {
                "column_mapping": {
                    "query": "${data.query}",
                    "response": "${data.response}",
                    "context": "${data.context}",
                    "expected_behavior": "${data.expected_behavior}",
                }
            }
        },
        output_path=str(output_path.with_suffix(".rows.jsonl")),
    )
    rows = list(evaluation["rows"])
    metrics = {name: float(value) for name, value in evaluation["metrics"].items()}
    agreement = calibration_agreement(rows)
    report = {
        "dataset": str(data_path),
        "deployment": deployment,
        "evaluators": sorted(evaluators),
        "metrics": metrics,
        "gate": apply_regression_gate(metrics, agreement, config),
        "row_count": len(rows),
    }
    if not rows:
        raise RuntimeError("Evaluation returned no rows; no release decision can be made.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("assets/evaluation-data.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("reports/evaluation-result.json"))
    args = parser.parse_args()
    print(json.dumps(run(args.data, args.output), indent=2))


if __name__ == "__main__":
    main()