"""Command-line driver for the durable approval workflow."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from .workflow import ApprovalWorkflow, send_decision_event


def create_workflow() -> ApprovalWorkflow:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    return ApprovalWorkflow(
        cosmos_endpoint=os.environ["COSMOS_ENDPOINT"],
        database_name=os.getenv("COSMOS_DATABASE", "approvals"),
        state_container=os.getenv("STATE_CONTAINER", "workflow-state"),
        audit_container=os.getenv("AUDIT_CONTAINER", "approval-audit"),
        service_bus_namespace=os.environ["SERVICE_BUS_NAMESPACE"],
        request_queue=os.getenv("REQUEST_QUEUE", "approval-requests"),
        decision_queue=os.getenv("DECISION_QUEUE", "approval-decisions"),
        credential=credential,
    )


def queue_decision(
    workflow_id: str,
    decision: str,
    reviewer: str,
    comment: str,
    category: str,
) -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    send_decision_event(
        os.environ["SERVICE_BUS_NAMESPACE"],
        os.getenv("DECISION_QUEUE", "approval-decisions"),
        DefaultAzureCredential(exclude_interactive_browser_credential=True),
        workflow_id,
        decision,
        reviewer,
        comment,
        category,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("--input", type=Path, required=True)
    status = commands.add_parser("status")
    status.add_argument("--workflow-id", required=True)
    decide = commands.add_parser("decide")
    decide.add_argument("--workflow-id", required=True)
    decide.add_argument(
        "--decision",
        choices=["approved", "rejected", "overridden", "cancelled"],
        required=True,
    )
    decide.add_argument("--reviewer", required=True)
    decide.add_argument("--comment", required=True)
    decide.add_argument("--category", default="other")
    commands.add_parser("resume")
    commands.add_parser("escalate")
    args = parser.parse_args()
    if args.command == "decide":
        queue_decision(
            args.workflow_id,
            args.decision,
            args.reviewer,
            args.comment,
            args.category,
        )
        result = {"decision_event": "queued", "workflow_id": args.workflow_id}
        print(json.dumps(result, indent=2, default=str))
        return
    workflow = create_workflow()
    if args.command == "submit":
        result = workflow.submit(json.loads(args.input.read_text(encoding="utf-8")))
    elif args.command == "status":
        result = workflow.get(args.workflow_id)
    elif args.command == "resume":
        result = workflow.resume()
    else:
        result = {"escalated": workflow.escalate_expired()}
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()