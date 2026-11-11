"""Create an evidence-linked blameless postmortem draft."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv


def summarize_evidence(analysis: list[dict[str, Any]], replay: dict[str, Any]) -> tuple[str, str]:
    metrics = replay["comparison_metrics"]
    supported = sorted(
        (item for item in analysis if item["status"] == "supported"),
        key=lambda item: item["priority"],
    )
    leading = supported[0] if supported else None
    observed = leading["supporting"] if leading else []
    evidence_summary = "; ".join(
        f"{item['path']} observed {json.dumps(item['observed'], sort_keys=True)}"
        for item in observed[:3]
    ) or "No causal observation has enough supporting evidence."
    if metrics["divergence_count"]:
        agents = ", ".join(item["agent"] for item in replay["divergences"])
        root_cause = (
            f"Replay detected {metrics['divergence_count']} prompt divergence(s) for {agents}; "
            "the causal statement remains bounded to the observed comparison evidence."
        )
    elif (
        leading and metrics["prompt_match_rate"] == 1.0
        and metrics["tool_step_count"] > 0
        and metrics["tool_mock_response_count"] == metrics["tool_step_count"]
    ):
        root_cause = (
            f"{leading['statement']} Evidence: {evidence_summary}. Replay matched "
            f"{metrics['prompt_count']} prompt(s), used {metrics['tool_mock_response_count']}/"
            f"{metrics['tool_step_count']} captured tool response(s), and preserved "
            f"{metrics['failed_step_count']} failed step(s)."
        )
    else:
        root_cause = "Root cause is not yet established because replay or comparison evidence is incomplete."
    return root_cause, evidence_summary


def upload_report(content: str, operation_id: str, credential: Any) -> str:
    service = BlobServiceClient(account_url=os.environ["BLOB_ACCOUNT_URL"], credential=credential)
    blob_name = f"{operation_id}.postmortem.md"
    service.get_blob_client(
        container=os.getenv("REPORT_CONTAINER", "incident-reports"), blob=blob_name
    ).upload_blob(content, overwrite=True)
    return blob_name


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
    replay = json.loads(args.replay.read_text(encoding="utf-8"))
    root_cause, evidence_summary = summarize_evidence(analysis, replay)
    template = Path("assets/postmortem-template.md").read_text(encoding="utf-8")
    rendered = (
        template.replace("{{operation_id}}", snapshot["operation_id"])
        .replace("{{root_cause}}", root_cause)
        .replace("{{replay_metrics}}", json.dumps(replay["comparison_metrics"], sort_keys=True))
        .replace("{{evidence_summary}}", evidence_summary)
    )
    output = Path("reports") / f"{snapshot['operation_id']}.postmortem.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    blob_name = upload_report(rendered, snapshot["operation_id"], credential)
    print(json.dumps({"local_report": str(output), "blob": blob_name}, indent=2))


if __name__ == "__main__":
    main()