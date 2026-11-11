"""Contoso Capital stateful loop starter using Microsoft Foundry Agents v2."""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv


LOGGER = logging.getLogger("stateful_loop")
AGENT_NAME = "contoso-investment-researcher"

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@dataclass(frozen=True)
class LoopConfig:
    project_endpoint: str
    model_deployment: str
    max_iterations: int


def load_config() -> LoopConfig:
    """Load non-secret configuration from the environment."""
    return LoopConfig(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model_deployment=os.environ["FOUNDRY_MODEL_NAME"],
        max_iterations=int(os.getenv("MAX_LOOP_ITERATIONS", "3")),
    )


def build_agent_definition(config: LoopConfig) -> PromptAgentDefinition:
    """Build the versioned v2 agent definition."""
    # LAB PLACEHOLDER 1: Replace this line with the Task 1 sample.
    return PromptAgentDefinition(
        model=config.model_deployment,
        instructions=(
            "You are Contoso Capital's investment research agent. Use only the "
            "evidence provided in the request and conversation. Do not invent facts, "
            "recommend trades, or reveal hidden chain-of-thought. Return concise, "
            "visible planning and review summaries using exactly these headings:\n"
            "PLAN: <brief approach>\n"
            "REFLECTION: <evidence gaps or checks performed>\n"
            "STATUS: <COMPLETE or CONTINUE>\n"
            "ANSWER: <evidence-based answer or the next information needed>\n"
            "Use COMPLETE only when the request is fully answered from supplied "
            "evidence. Otherwise use CONTINUE."
        ),
    )


def extract_text(response: Any) -> str:
    """Return visible text from typed Responses API output items."""
    parts: list[str] = []
    for item in response.output:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", []):
            text = getattr(content, "text", None)
            if text:
                parts.append(text)
    return "\n".join(parts)


def run_reflection_cycle(
    openai_client: Any,
    conversation_id: str,
    request: str,
    max_iterations: int,
) -> dict[str, Any]:
    """Run a bounded visible-summary reflection cycle."""
    # LAB PLACEHOLDER 2: Replace this line with the Task 2 sample.
    if max_iterations <= 0:
        raise ValueError("max_iterations must be greater than zero")

    iterations: list[dict[str, Any]] = []
    next_input = request
    last_response_id = ""

    for iteration_number in range(1, max_iterations + 1):
        response = openai_client.responses.create(
            conversation=conversation_id,
            input=next_input,
        )
        visible_text = extract_text(response).strip()
        status = "MISSING"

        for line in visible_text.splitlines():
            label, separator, value = line.partition(":")
            if separator and label.strip().strip("*").upper() == "STATUS":
                status = value.strip().strip("* .").upper()
                break

        last_response_id = response.id
        iterations.append(
            {
                "iteration": iteration_number,
                "response_id": response.id,
                "status": status,
                "visible_summary": visible_text,
            }
        )
        LOGGER.info(
            "Iteration completed iteration=%d response_id=%s status=%s",
            iteration_number,
            response.id,
            status,
        )

        if status == "COMPLETE":
            return {
                "iterations": iterations,
                "last_response_id": last_response_id,
            }

        next_input = (
            "Review the previous visible answer for unsupported claims, missing "
            "evidence, and incomplete coverage. Return a revised response with the "
            "required PLAN, REFLECTION, STATUS, and ANSWER headings."
        )

    raise RuntimeError(
        f"Reflection cycle exhausted its {max_iterations}-iteration budget "
        "without STATUS: COMPLETE"
    )


def fork_with_previous_response(
    openai_client: Any,
    previous_response_id: str,
    branch_request: str,
) -> Any:
    """Create a branch with previous_response_id instead of mutating history."""
    # LAB PLACEHOLDER 3: Replace this line with the Task 3 sample.
    if not previous_response_id:
        raise ValueError("previous_response_id is required")

    return openai_client.responses.create(
        previous_response_id=previous_response_id,
        input=branch_request,
    )


def run(input_path: Path, retain_resources: bool = True) -> dict[str, Any]:
    config = load_config()
    request_data = json.loads(input_path.read_text(encoding="utf-8"))

    project = AIProjectClient(
        endpoint=config.project_endpoint,
        credential=DefaultAzureCredential(),
    )
    agent = project.agents.create_version(
        agent_name=AGENT_NAME,
        definition=build_agent_definition(config),
    )
    openai_client = None
    conversation = None

    try:
        openai_client = project.get_openai_client(agent_name=agent.name)
        conversation = openai_client.conversations.create()
        loop_result = run_reflection_cycle(
            openai_client=openai_client,
            conversation_id=conversation.id,
            request=request_data["research_request"],
            max_iterations=config.max_iterations,
        )
        branch = fork_with_previous_response(
            openai_client=openai_client,
            previous_response_id=loop_result["last_response_id"],
            branch_request=request_data["branch_request"],
        )

        return {
            "agent_name": agent.name,
            "agent_version": agent.version,
            "conversation_id": conversation.id,
            "resources_retained": retain_resources,
            "iterations": loop_result["iterations"],
            "branch_response_id": branch.id,
            "branch_text": extract_text(branch),
        }
    finally:
        if not retain_resources:
            LOGGER.info(
                "Deleting conversation=%s and agent=%s version=%s",
                getattr(conversation, "id", None),
                agent.name,
                agent.version,
            )
            try:
                if openai_client is not None and conversation is not None:
                    openai_client.conversations.delete(conversation_id=conversation.id)
            finally:
                project.agents.delete_version(
                    agent_name=agent.name,
                    agent_version=agent.version,
                    force=True,
                )
        else:
            LOGGER.info(
                "Retained conversation=%s and agent=%s version=%s for inspection",
                getattr(conversation, "id", None),
                agent.name,
                agent.version,
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("assets/research-request.json"))
    parser.add_argument("--log-level", default="INFO")
    resource_group = parser.add_mutually_exclusive_group()
    resource_group.add_argument(
        "--retain-resources",
        dest="retain_resources",
        action="store_true",
        help="Retain the conversation and created agent version (default).",
    )
    resource_group.add_argument(
        "--cleanup-resources",
        dest="retain_resources",
        action="store_false",
        help="Delete the conversation and exact agent version created by this run.",
    )
    parser.set_defaults(retain_resources=True)
    args = parser.parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(message)s")
    result = run(args.input, retain_resources=args.retain_resources)
    LOGGER.info(
        "Loop completed agent=%s version=%s iterations=%d",
        result["agent_name"],
        result["agent_version"],
        len(result["iterations"]),
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()