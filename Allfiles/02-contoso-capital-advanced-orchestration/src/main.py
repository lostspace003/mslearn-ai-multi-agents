"""Live Agents v2 fan-out/fan-in orchestration starter."""
from __future__ import annotations
import argparse, asyncio, json, logging, os, time
from pathlib import Path
from typing import Any
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

LOGGER = logging.getLogger("orchestration")

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

def select_execution_pattern(tasks: list[dict[str, Any]]) -> str:
    """Learner task: return parallel only when this batch has no dependencies."""
    # LAB PLACEHOLDER 1: Replace this line with the Task 1 sample.
    task_names = {task["name"] for task in tasks}
    has_in_round_dependency = any(
        task_names.intersection(task.get("depends_on", []))
        for task in tasks
    )
    return "sequential" if has_in_round_dependency else "parallel"

def evaluate_quorum(results: list[dict[str, Any]], required: list[str]) -> dict[str, Any]:
    """Learner task: enforce critical-agent quorum and normalize evidence."""
    # LAB PLACEHOLDER 2: Replace this line with the Task 2 sample.
    successful = {
        result["agent"]: result
        for result in results
        if isinstance(result, dict) and result.get("status") == "success"
    }
    all_agents = [
        result.get("agent", "unknown")
        for result in results
        if isinstance(result, dict)
    ]
    missing_agents = [name for name in all_agents if name not in successful]
    missing_required = [name for name in required if name not in successful]
    accepted_evidence = [
        {
            "agent": name,
            "response_id": result["response_id"],
            "text": result["text"],
            "elapsed_ms": result["elapsed_ms"],
        }
        for name, result in successful.items()
    ]
    return {
        "status": "ready" if not missing_required else "insufficient_quorum",
        "required_agents": required,
        "successful_count": len(successful),
        "missing_agents": missing_agents,
        "missing_required": missing_required,
        "accepted_evidence": accepted_evidence,
    }

def text_from_response(response: Any) -> str:
    return "\n".join(getattr(part, "text", "") for item in response.output if getattr(item, "type", None) == "message" for part in getattr(item, "content", [])).strip()

async def invoke(openai: Any, agent_name: str, prompt: str, timeout: float, semaphore: asyncio.Semaphore) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        async def call_with_capacity() -> Any:
            async with semaphore:
                return await asyncio.to_thread(
                    openai.responses.create,
                    input=prompt,
                )

        response = await asyncio.wait_for(call_with_capacity(), timeout)
        return {"agent": agent_name, "status": "success", "response_id": response.id, "text": text_from_response(response), "elapsed_ms": round((time.perf_counter()-started)*1000)}
    except Exception as exc:
        LOGGER.warning("Spoke failed agent=%s category=%s", agent_name, type(exc).__name__)
        return {"agent": agent_name, "status": "failed", "response_id": None, "text": None, "elapsed_ms": round((time.perf_counter()-started)*1000)}

def synthesize(openai: Any, request: str, quorum: dict[str, Any]) -> Any:
    """Learner task: invoke the supervisor with accepted evidence and caveats."""
    # LAB PLACEHOLDER 3: Replace this line with the Task 3 sample.
    if quorum["status"] != "ready":
        missing = ", ".join(quorum["missing_required"])
        raise RuntimeError(f"Critical quorum was not met: {missing}")

    payload = {
        "request": request,
        "accepted_evidence": quorum["accepted_evidence"],
        "missing_agents": quorum["missing_agents"],
    }
    return openai.responses.create(
        input=(
            "Synthesize the supplied specialist evidence. State a caveat for "
            "every missing agent, do not invent facts, and do not provide "
            "investment advice.\n"
            + json.dumps(payload)
        ),
    )

async def run(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    project = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=DefaultAzureCredential())
    names = {}
    clients = {}
    for spec in data["agents"] + [data["supervisor"]]:
        version = project.agents.create_version(agent_name=spec["name"], definition=PromptAgentDefinition(model=os.environ["FOUNDRY_MODEL_NAME"], instructions=spec["instructions"]))
        names[spec["name"]] = version.name
        clients[spec["name"]] = project.get_openai_client(agent_name=version.name)
    pattern = select_execution_pattern(data["agents"])
    semaphore = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENCY", "3")))
    tasks = [invoke(clients[item["name"]], names[item["name"]], f"Request: {data['request']}\nAssignment: {item['assignment']}", float(os.getenv("AGENT_TIMEOUT_SECONDS", "45")), semaphore) for item in data["agents"]]
    started = time.perf_counter()
    if pattern == "parallel":
        results = await asyncio.gather(*tasks)
    else:
        results = [await task for task in tasks]
    if data.get("simulate_optional_failure"):
        results[-1] = {**results[-1], "status": "failed", "text": None}
    # Optional challenge: force a named spoke to fail after its live call.
    if data.get("simulate_failure_agent"):
        results = [{**r, "status": "failed", "text": None} if r["agent"] == data["simulate_failure_agent"] else r for r in results]
    quorum = evaluate_quorum(results, data["required_agents"])
    supervisor = synthesize(clients[data["supervisor"]["name"]], data["request"], quorum)
    return {"route": data.get("route", "standard"), "pattern": pattern, "quorum": quorum, "spokes": results, "supervisor_response_id": supervisor.id, "answer": text_from_response(supervisor), "elapsed_ms": round((time.perf_counter()-started)*1000)}

def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--input", type=Path, default=Path("assets/portfolio-request.json")); args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(json.dumps(asyncio.run(run(args.input)), indent=2))
if __name__ == "__main__": main()
