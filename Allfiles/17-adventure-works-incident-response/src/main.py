"""Query Application Insights and persist sanitized replay snapshots."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv


def query_rows(client: LogsQueryClient, workspace_id: str, query: str) -> list[dict[str, Any]]:
    response = client.query_workspace(workspace_id, query, timespan=timedelta(hours=24))
    if response.status == LogsQueryStatus.PARTIAL:
        raise RuntimeError(f"Partial KQL result: {response.partial_error}")
    rows = []
    for table in response.tables:
        columns = [
            column if isinstance(column, str) else column.name
            for column in table.columns
        ]
        rows.extend(dict(zip(columns, row, strict=True)) for row in table.rows)
    return rows


def sanitize_rows(rows: list[dict[str, Any]], operation_id: str) -> dict[str, Any]:
    """Transform query rows into the replay snapshot contract without sensitive content."""
    spans = []
    deployments = {}
    configurations = {}
    prompts = {}
    prompt_hashes = {}
    tool_mocks = {}
    for row in rows:
        properties = row.get("Properties") or {}
        if isinstance(properties, str):
            properties = json.loads(properties)
        span = {
            "time_generated": row.get("TimeGenerated"),
            "span_id": row.get("Id"),
            "parent_id": row.get("ParentId"),
            "span_name": row.get("SpanName"),
            "duration_ms": row.get("DurationMs"),
            "success": row.get("Success"),
            "result_code": row.get("ResultCode"),
            "model_version": properties.get("gen_ai.request.model"),
            "configuration_version": properties.get("agent.configuration.version"),
            "prompt_hash": properties.get("gen_ai.prompt.hash"),
            "error_type": properties.get("incident.error.type"),
            "tool_name": properties.get("tool.name"),
            "tool_mock_id": properties.get("tool.mock_id"),
            "tool_mock_response_available": properties.get("tool.mock_response") is not None,
        }
        spans.append(span)
        if span["model_version"]:
            deployments[span["span_name"]] = {
                "agent": span["span_name"], "version": span["model_version"]
            }
        if span["configuration_version"]:
            configurations[span["span_name"]] = {
                "component": span["span_name"], "version": span["configuration_version"]
            }
        if properties.get("gen_ai.prompt.hash"):
            prompt_hashes[span["span_name"]] = properties["gen_ai.prompt.hash"]
        if properties.get("gen_ai.prompt.template"):
            prompts[span["span_name"]] = properties["gen_ai.prompt.template"]
        if span["tool_name"]:
            mock_response = properties.get("tool.mock_response")
            tool_success = properties.get("tool.response.success")
            if isinstance(tool_success, str) and tool_success.lower() in {"true", "false"}:
                tool_success = tool_success.lower() == "true"
            tool_mocks[span["tool_name"]] = {
                "mock_id": span["tool_mock_id"],
                "response": json.loads(mock_response) if isinstance(mock_response, str) else mock_response,
                "success": tool_success,
                "synthetic": True,
            }
    return {
        "schema_version": "1.0",
        "operation_id": operation_id,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "spans": spans,
        "model_deployments": list(deployments.values()),
        "configuration_versions": list(configurations.values()),
        "prompts": prompts,
        "prompt_hashes": prompt_hashes,
        "tool_mocks": tool_mocks,
        "replay_mode": True,
    }


def upload_snapshot(snapshot: dict[str, Any], account_url: str, container: str, credential: Any) -> str:
    service = BlobServiceClient(account_url=account_url, credential=credential)
    name = f"{snapshot['operation_id']}.snapshot.json"
    service.get_blob_client(container=container, blob=name).upload_blob(
        json.dumps(snapshot, indent=2, default=str), overwrite=True
    )
    return name


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    candidates = commands.add_parser("candidates")
    candidates.add_argument("--query", type=Path, required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("--operation-id", required=True)
    capture.add_argument("--query", type=Path, required=True)
    args = parser.parse_args()

    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    client = LogsQueryClient(credential)
    query = args.query.read_text(encoding="utf-8")
    if args.command == "candidates":
        print(json.dumps(query_rows(client, os.environ["LOG_ANALYTICS_WORKSPACE_ID"], query), indent=2, default=str))
        return

    safe_operation_id = args.operation_id.replace("'", "''")
    rows = query_rows(
        client,
        os.environ["LOG_ANALYTICS_WORKSPACE_ID"],
        query.replace("__OPERATION_ID__", safe_operation_id),
    )
    snapshot = sanitize_rows(rows, args.operation_id)
    report_path = Path("reports") / f"{args.operation_id}.snapshot.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
    blob_name = upload_snapshot(
        snapshot,
        os.environ["BLOB_ACCOUNT_URL"],
        os.getenv("SNAPSHOT_CONTAINER", "trace-snapshots"),
        credential,
    )
    print(json.dumps({"local_snapshot": str(report_path), "blob": blob_name}, indent=2))


if __name__ == "__main__":
    main()