from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from scripts.apply_canary_decision import _routing_evidence, _verify_labels
from scripts.release_manifest import validate_verified_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore a persisted, verified dashboard release")
    parser.add_argument("--verified-manifest", type=Path, required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--app", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    release_set = json.loads(args.verified_manifest.read_text(encoding="utf-8"))
    validate_verified_manifest(release_set, environment=args.environment, app_name=args.app)
    dashboard = release_set["dashboard"]
    revision = dashboard["revision"]
    if not revision:
        raise ValueError("Verified release manifest does not contain a dashboard revision")

    active = subprocess.run(
        [
            "az", "containerapp", "revision", "show",
            "--resource-group", args.resource_group,
            "--name", args.app,
            "--revision", revision,
            "--query", "properties.active",
            "--output", "tsv",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()
    # Azure rejects activating an already-active revision (RevisionAlreadyInRequestedState).
    if active != "true":
        subprocess.run(
            [
                "az", "containerapp", "revision", "activate",
                "--resource-group", args.resource_group,
                "--name", args.app,
                "--revision", revision,
            ],
            check=True,
        )
    subprocess.run(
        [
            "az", "containerapp", "ingress", "traffic", "set",
            "--resource-group", args.resource_group,
            "--name", args.app,
            "--revision-weight", f"{revision}=100",
        ],
        check=True,
    )
    subprocess.run(
        [
            "az", "containerapp", "revision", "label", "add",
            "--resource-group", args.resource_group,
            "--name", args.app,
            "--revision", revision,
            "--label", "stable",
            "--yes",
        ],
        check=True,
    )
    routing = _routing_evidence(args.resource_group, args.app)
    _verify_labels(routing, {"stable": revision})
    evidence = {
        "restored_release_set_id": release_set["release_set_id"],
        "dashboard_revision": revision,
        "orchestrator": dashboard["target_orchestrator"],
        "traffic_weight": 100,
        "routing": routing,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
