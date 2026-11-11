from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


def _run_json(arguments: list[str]) -> Any:
    completed = subprocess.run(arguments, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def _active_revisions(resource_group: str, app: str) -> list[dict[str, str]]:
    revisions = _run_json(
        [
            "az", "containerapp", "revision", "list",
            "--resource-group", resource_group,
            "--name", app,
            "--query", "[?properties.active].{name:name,created:properties.createdTime,fqdn:properties.fqdn}",
            "--output", "json",
        ]
    )
    ordered = sorted(revisions, key=lambda revision: revision.get("created") or "")
    if not ordered:
        raise RuntimeError(f"{app} has no active revisions")
    return [
        {"name": str(revision["name"]), "fqdn": str(revision.get("fqdn") or "")}
        for revision in ordered
    ]


def select_traffic(
    revisions: list[dict[str, str]],
    *,
    stable_revision: str | None,
    strategy: str,
    initial_revision: str | None = None,
) -> dict[str, Any]:
    if initial_revision:
        by_name = {revision["name"]: revision for revision in revisions}
        if initial_revision not in by_name:
            raise ValueError(f"Initial dashboard revision is not active: {initial_revision}")
        return {
            "strategy": "initial",
            "weights": {
                revision["name"]: 100 if revision["name"] == initial_revision else 0
                for revision in revisions
            },
            "stable": by_name[initial_revision],
            "candidate": None,
        }
    if len(revisions) == 1:
        revision = revisions[0]
        return {
            "strategy": "initial",
            "weights": {revision["name"]: 100},
            "stable": revision,
            "candidate": None,
        }
    if not stable_revision:
        raise ValueError("A persisted stable revision is required when multiple revisions are active")
    by_name = {revision["name"]: revision for revision in revisions}
    if stable_revision not in by_name:
        raise ValueError(f"Persisted stable revision is not active: {stable_revision}")
    candidates = [revision for revision in revisions if revision["name"] != stable_revision]
    candidate = candidates[-1]
    weights = (
        {stable_revision: 75, candidate["name"]: 25}
        if strategy == "canary"
        else {stable_revision: 0, candidate["name"]: 100}
    )
    return {
        "strategy": strategy,
        "weights": weights,
        "stable": by_name[stable_revision],
        "candidate": candidate,
    }


def _set_traffic(resource_group: str, app: str, weights: dict[str, int]) -> None:
    subprocess.run(
        [
            "az", "containerapp", "ingress", "traffic", "set",
            "--resource-group", resource_group,
            "--name", app,
            "--revision-weight",
            *[f"{revision}={weight}" for revision, weight in weights.items()],
            "--output", "none",
        ],
        check=True,
    )


def _set_label(resource_group: str, app: str, revision: str, label: str) -> None:
    subprocess.run(
        [
            "az", "containerapp", "revision", "label", "add",
            "--resource-group", resource_group,
            "--name", app,
            "--revision", revision,
            "--label", label,
            "--yes",
            "--output", "none",
        ],
        check=True,
    )


def _routing_evidence(resource_group: str, app: str) -> dict[str, Any]:
    app_state = _run_json(
        [
            "az", "containerapp", "show",
            "--resource-group", resource_group,
            "--name", app,
            "--query", "properties.configuration.ingress.{fqdn:fqdn,traffic:traffic}",
            "--output", "json",
        ]
    )
    fqdn = str(app_state.get("fqdn") or "")
    if not fqdn:
        raise RuntimeError("Container Apps did not report the dashboard ingress FQDN")
    labels = {
        str(item["label"]): str(item["revisionName"])
        for item in app_state.get("traffic") or []
        if item.get("label") and item.get("revisionName")
    }
    return {
        "fqdn": fqdn,
        "labels": labels,
        # Container Apps label hostnames are <app>---<label>.<environment-domain>.
        "label_urls": {
            label: "https://{0}---{1}.{2}".format(*fqdn.split(".", 1)[:1], label, fqdn.split(".", 1)[1])
            for label in labels
        },
        "traffic": app_state.get("traffic") or [],
    }


def _verify_labels(evidence: dict[str, Any], expected: dict[str, str]) -> None:
    actual = evidence["labels"]
    for label, revision in expected.items():
        if actual.get(label) != revision:
            raise RuntimeError(
                f"Container Apps label {label!r} maps to {actual.get(label)!r}, expected {revision!r}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--app", required=True)
    parser.add_argument("--stable-revision")
    parser.add_argument("--initial-revision")
    parser.add_argument("--strategy", choices=("canary", "blue-green"), default="canary")
    args = parser.parse_args()
    decision = json.loads(args.decision.read_text(encoding="utf-8"))
    if decision["action"] == "rollback":
        print("Quality regression detected; traffic is unchanged pending rollback dispatch.")
        return 2
    if decision["action"] == "hold":
        print("Quality gate is on hold; traffic is unchanged.")
        return 0

    plan = select_traffic(
        _active_revisions(args.resource_group, args.app),
        stable_revision=args.stable_revision,
        strategy=args.strategy,
        initial_revision=args.initial_revision,
    )
    _set_traffic(args.resource_group, args.app, plan["weights"])
    expected_labels: dict[str, str]
    if plan["candidate"] and args.strategy == "blue-green":
        _set_label(args.resource_group, args.app, plan["candidate"]["name"], "stable")
        _set_label(args.resource_group, args.app, plan["stable"]["name"], "previous")
        expected_labels = {
            "stable": plan["candidate"]["name"],
            "previous": plan["stable"]["name"],
        }
    else:
        _set_label(args.resource_group, args.app, plan["stable"]["name"], "stable")
        expected_labels = {"stable": plan["stable"]["name"]}
    if plan["candidate"] and args.strategy == "canary":
        _set_label(args.resource_group, args.app, plan["candidate"]["name"], "candidate")
        expected_labels["candidate"] = plan["candidate"]["name"]
    routing = _routing_evidence(args.resource_group, args.app)
    _verify_labels(routing, expected_labels)
    print(json.dumps({"action": "promote", **plan, "routing": routing}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
