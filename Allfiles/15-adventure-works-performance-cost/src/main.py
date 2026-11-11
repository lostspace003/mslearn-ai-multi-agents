"""Run control and optimized policies against live Foundry deployments."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from .cache import ResultCache

SYSTEM_PROMPT = """You are an Adventure Works customer-service agent. Use only the supplied synthetic context. Return a concise answer and identify missing information. Never invent or execute an order action."""


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def classify_tier(request: dict[str, Any]) -> int:
    """Classify request complexity without spending model tokens."""
    message = request["message"].lower()
    if (
        request.get("policy_exception")
        or float(request.get("transaction_amount", 0)) > 200
        or any(term in message for term in ("legal", "regulatory", "chargeback"))
    ):
        return 3
    if "compare" in message or len(request.get("dependencies", [])) > 1:
        return 2
    return 1


def apply_context_budget(request: dict[str, Any], budget: int) -> str:
    """Build context that preserves required facts within a character proxy budget."""
    context = request["context"]
    required = set(request.get("required_context_fields", context.keys())) - {"unused_fields"}
    selected = {key: context[key] for key in context if key in required}
    rendered = json.dumps(selected, sort_keys=True, separators=(",", ":"))
    character_limit = budget * 4
    if len(rendered) > character_limit:
        raise ValueError(
            f"Required context needs {len(rendered)} characters; tier budget allows {character_limit}."
        )
    return rendered


def invoke(openai_client: Any, deployment: str, request: dict[str, Any], context: str) -> dict[str, Any]:
    started = time.perf_counter()
    response = openai_client.responses.create(
        model=deployment,
        input=f"{SYSTEM_PROMPT}\n\nContext: {context}\nRequest: {request['message']}",
        text={
            "format": {
                "type": "json_schema",
                "name": "customer_service_response",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string", "minLength": 1},
                        "missing_information": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["answer", "missing_information"],
                    "additionalProperties": False,
                },
            }
        },
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    payload = json.loads(response.output_text)
    return {
        "response": payload,
        "elapsed_ms": elapsed_ms,
        "input_tokens": int(response.usage.input_tokens),
        "output_tokens": int(response.usage.output_tokens),
    }


def evaluate_quality(request: dict[str, Any], response: dict[str, Any]) -> int:
    """Score synthetic assertions independently from the model response."""
    answer = str(response["answer"]).casefold()
    required = [str(term).casefold() for term in request.get("quality_required_terms", [])]
    forbidden = [str(term).casefold() for term in request.get("quality_forbidden_terms", [])]
    if any(term in answer for term in forbidden):
        return 0
    if not required:
        raise ValueError(f"Request {request['request_id']} has no quality assertions")
    matched = sum(term in answer for term in required)
    return round(matched / len(required) * 100)


def calculate_cost(tokens: dict[str, int], prices: dict[str, float]) -> float:
    return round(
        tokens["input_tokens"] / 1_000_000 * prices["input_per_million"]
        + tokens["output_tokens"] / 1_000_000 * prices["output_per_million"],
        6,
    )


def percentile(values: list[float], percentile_value: float) -> float:
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * percentile_value), len(ordered) - 1)
    return ordered[index]


def cache_rates(evidence: list[dict[str, Any]]) -> dict[str, float]:
    request_count = len(evidence)
    exact_hits = sum(row["cache_level"] == "exact_result" for row in evidence)
    prompt_hits = sum(row["cache_level"] == "prompt" for row in evidence)
    return {
        "cache_hit_rate": (exact_hits + prompt_hits) / request_count,
        "exact_result_cache_hit_rate": exact_hits / request_count,
        "prompt_cache_hit_rate": prompt_hits / request_count,
    }


def create_cache(config: dict[str, Any], credential: Any) -> ResultCache:
    return ResultCache(
        host=os.environ["REDIS_HOST"],
        port=int(os.environ["REDIS_PORT"]),
        principal_id=os.environ["AZURE_PRINCIPAL_ID"],
        credential=credential,
        ttl_seconds=config["cache_ttl_seconds"],
    )


def invalidate_exact(request_id: str) -> dict[str, Any]:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    config = json.loads(Path("assets/optimization-config.json").read_text(encoding="utf-8"))
    requests = read_jsonl(Path("assets/requests.jsonl"))
    request = next((item for item in requests if item["request_id"] == request_id), None)
    if request is None:
        raise ValueError(f"Unknown request_id: {request_id}")
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    result = create_cache(config, credential).delete_exact(
        request,
        config["agent_version"],
        config["policy_version"],
    )
    return {"request_id": request_id, **result}


def run(policy: str, output_path: Path) -> dict[str, Any]:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    config = json.loads(Path("assets/optimization-config.json").read_text(encoding="utf-8"))
    requests = read_jsonl(Path("assets/requests.jsonl"))
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    project = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential)
    openai_client = project.get_openai_client()
    cache = create_cache(config, credential)
    evidence_path = Path("reports/evidence.jsonl")
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence: list[dict[str, Any]] = []

    for request in requests:
        initial_tier = 3 if policy == "control" else classify_tier(request)
        tier = initial_tier
        result_cache_key = cache.result_key(request, config["agent_version"], config["policy_version"])
        cached = cache.get(result_cache_key) if policy == "optimized" else None
        if cached and "quality_score" not in cached.get("metadata", {}):
            cached = None
        if cached:
            cache_metadata = cached.get("metadata", {})
            tier = int(cache_metadata.get("tier", initial_tier))
            tier_config = config["tiers"][str(tier)]
            row = {
                "request_id": request["request_id"],
                "policy": policy,
                "initial_tier": initial_tier,
                "final_tier": tier,
                "cache_hit": True,
                "cache_level": "exact_result",
                "prompt_cache_hit": False,
                "deployment": cache_metadata.get("deployment", os.environ[tier_config["deployment_env"]]),
                "price_version": cache_metadata.get("price_version", config["price_version"]),
                "elapsed_ms": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "quality_score": int(cache_metadata["quality_score"]),
                "retry_count": 0,
            }
        else:
            retry_count = 0
            total_elapsed_ms = 0.0
            total_input_tokens = 0
            total_output_tokens = 0
            total_cost_usd = 0.0
            attempts = []
            prompt_cache_hit = False
            while True:
                tier_config = config["tiers"][str(tier)]
                deployment = os.environ[tier_config["deployment_env"]]
                prompt_cache_key = cache.prompt_key(
                    request,
                    tier,
                    tier_config["input_budget"],
                    config["agent_version"],
                    config["policy_version"],
                )
                context = cache.get_prompt(prompt_cache_key) if policy == "optimized" else None
                attempt_prompt_cache_hit = context is not None
                if context is None:
                    context = apply_context_budget(request, tier_config["input_budget"])
                    if policy == "optimized":
                        cache.put_prompt(prompt_cache_key, context, request["dependencies"])
                else:
                    prompt_cache_hit = True
                result = invoke(openai_client, deployment, request, context)
                quality_score = evaluate_quality(request, result["response"])
                attempt_cost = calculate_cost(result, tier_config["prices_usd"])
                total_elapsed_ms += result["elapsed_ms"]
                total_input_tokens += result["input_tokens"]
                total_output_tokens += result["output_tokens"]
                total_cost_usd += attempt_cost
                attempts.append(
                    {
                        "tier": tier,
                        "deployment": deployment,
                        "price_version": config["price_version"],
                        "prompt_cache_hit": attempt_prompt_cache_hit,
                        "elapsed_ms": result["elapsed_ms"],
                        "input_tokens": result["input_tokens"],
                        "output_tokens": result["output_tokens"],
                        "cost_usd": attempt_cost,
                        "quality_score": quality_score,
                    }
                )
                if quality_score >= tier_config["quality_floor"] or tier == 3:
                    break
                tier += 1
                retry_count += 1
            row = {
                "request_id": request["request_id"],
                "policy": policy,
                "initial_tier": initial_tier,
                "final_tier": tier,
                "cache_hit": False,
                "cache_level": "prompt" if prompt_cache_hit else "miss",
                "prompt_cache_hit": prompt_cache_hit,
                "deployment": deployment,
                "price_version": config["price_version"],
                "elapsed_ms": round(total_elapsed_ms, 1),
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "cost_usd": round(total_cost_usd, 6),
                "quality_score": quality_score,
                "retry_count": retry_count,
                "attempts": attempts,
                "needs_human_review": tier == 3 and quality_score < tier_config["quality_floor"],
            }
            if policy == "optimized" and not row["needs_human_review"]:
                cache.put(
                    result_cache_key,
                    result,
                    request["dependencies"],
                    {
                        "tier": tier,
                        "deployment": deployment,
                        "price_version": config["price_version"],
                        "quality_score": quality_score,
                    },
                )
        evidence.append(row)
        with evidence_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")

    latencies = [row["elapsed_ms"] for row in evidence]
    summary = {
        "policy": policy,
        "request_count": len(evidence),
        "successful_count": sum(not row.get("needs_human_review", False) for row in evidence),
        "total_cost_usd": round(sum(row["cost_usd"] for row in evidence), 6),
        "total_input_tokens": sum(row["input_tokens"] for row in evidence),
        "total_output_tokens": sum(row["output_tokens"] for row in evidence),
        "retry_rate": sum(row["retry_count"] > 0 for row in evidence) / len(evidence),
        "quality_mean": round(statistics.mean(row["quality_score"] for row in evidence), 2),
        "latency_p50_ms": percentile(latencies, 0.50),
        "latency_p95_ms": percentile(latencies, 0.95),
        "price_version": config["price_version"],
        "evidence": evidence,
        **cache_rates(evidence),
    }
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", choices=["control", "optimized"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--invalidate-exact", metavar="REQUEST_ID")
    args = parser.parse_args()
    if args.invalidate_exact:
        print(json.dumps(invalidate_exact(args.invalidate_exact), indent=2))
        return
    if not args.policy or not args.output:
        parser.error("--policy and --output are required unless --invalidate-exact is used")
    print(json.dumps(run(args.policy, args.output), indent=2))


if __name__ == "__main__":
    main()