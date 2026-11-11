"""Evaluator definitions for the Adventure Works journey dataset."""

from __future__ import annotations

import json
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.core.credentials import TokenCredential


class JourneyCoherenceEvaluator:
    """Score end-to-end consistency and handoff quality with a model judge."""

    def __init__(
        self,
        project_endpoint: str,
        deployment_name: str,
        credential: TokenCredential,
    ) -> None:
        self._deployment_name = deployment_name
        self._client = AIProjectClient(
            endpoint=project_endpoint,
            credential=credential,
        ).get_openai_client()

    def __call__(
        self,
        *,
        query: str,
        response: str,
        context: str,
        expected_behavior: str,
    ) -> dict[str, Any]:
        prompt = f"""Evaluate this synthetic multi-agent customer journey.

Rubric:
5 - The journey is coherent, handoffs preserve all required facts, and the expected behavior is complete.
4 - The journey succeeds with one minor omission that does not affect the outcome.
3 - The journey is usable but has a confusing handoff or a meaningful omission.
2 - A contradiction or lost handoff detail prevents reliable completion.
1 - The journey fails the customer's goal or invents unsupported facts.

Customer query: {query}
Grounding context: {context}
Expected behavior: {expected_behavior}
Candidate journey: {response}

Return JSON only with integer field `score` from 1 through 5 and string field `reason`.
"""
        completion = self._client.responses.create(
            model=self._deployment_name,
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "journey_coherence",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "score": {"type": "integer", "minimum": 1, "maximum": 5},
                            "reason": {"type": "string", "minLength": 1},
                        },
                        "required": ["score", "reason"],
                        "additionalProperties": False,
                    },
                }
            },
            timeout=60.0,
        )
        if completion.status != "completed" or not completion.output_text:
            raise RuntimeError(
                f"Journey judge did not complete successfully: {completion.status}"
            )
        result = json.loads(completion.output_text)
        score = int(result["score"])
        if not 1 <= score <= 5:
            raise ValueError(f"Journey judge returned an out-of-range score: {score}")
        return {
            "journey_coherence": score,
            "journey_coherence_reason": str(result["reason"]),
        }


class ResponsesMetricEvaluator:
    """Base for structured model judges using the current Responses API."""

    def __init__(
        self,
        project_endpoint: str,
        deployment_name: str,
        credential: TokenCredential,
    ) -> None:
        self._deployment_name = deployment_name
        self._client = AIProjectClient(
            endpoint=project_endpoint,
            credential=credential,
        ).get_openai_client()

    def _score(
        self,
        metric: str,
        rubric: str,
        evidence: str,
        minimum: int,
        maximum: int,
    ) -> dict[str, Any]:
        completion = self._client.responses.create(
            model=self._deployment_name,
            input=(
                f"Evaluate this synthetic multi-agent journey.\n\nMetric: {metric}\n"
                f"Rubric: {rubric}\nEvidence:\n{evidence}\n\n"
                f"Return JSON only with integer field `score` from {minimum} through "
                f"{maximum} and non-empty string field `reason`. Treat the supplied "
                "record as offline evidence; do not require external tool telemetry."
            ),
            text={
                "format": {
                    "type": "json_schema",
                    "name": metric,
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "score": {
                                "type": "integer",
                                "minimum": minimum,
                                "maximum": maximum,
                            },
                            "reason": {"type": "string", "minLength": 1},
                        },
                        "required": ["score", "reason"],
                        "additionalProperties": False,
                    },
                }
            },
            timeout=60.0,
        )
        if completion.status != "completed" or not completion.output_text:
            raise RuntimeError(f"{metric} judge did not complete: {completion.status}")
        result = json.loads(completion.output_text)
        score = int(result["score"])
        if not minimum <= score <= maximum:
            raise ValueError(f"{metric} judge returned out-of-range score {score}")
        return {metric: score, f"{metric}_reason": str(result["reason"])}


class IntentResolutionEvaluator(ResponsesMetricEvaluator):
    def __call__(self, *, query: str, response: str) -> dict[str, Any]:
        return self._score(
            "intent_resolution",
            "Score 1-5 for how fully the response resolves the customer intent.",
            f"Customer query: {query}\nCandidate journey: {response}",
            1,
            5,
        )


class TaskAdherenceEvaluator(ResponsesMetricEvaluator):
    def __call__(self, *, query: str, response: str) -> dict[str, Any]:
        return self._score(
            "task_adherence",
            "Return 1 only when the journey follows the requested task, otherwise 0.",
            f"Customer query: {query}\nCandidate journey: {response}",
            0,
            1,
        )


class ResponseCompletenessEvaluator(ResponsesMetricEvaluator):
    def __call__(self, *, response: str, ground_truth: str) -> dict[str, Any]:
        return self._score(
            "response_completeness",
            "Score 1-5 for coverage of every behavior in the reference.",
            f"Required behavior: {ground_truth}\nCandidate journey: {response}",
            1,
            5,
        )


def create_evaluators(
    model_config: dict[str, str], credential: TokenCredential
) -> dict[str, Any]:
    """Create Responses-based evaluators for the batch run."""
    judge_options = {
        "project_endpoint": model_config["project_endpoint"],
        "deployment_name": model_config["azure_deployment"],
        "credential": credential,
    }
    return {
        "intent_resolution": IntentResolutionEvaluator(**judge_options),
        "task_adherence": TaskAdherenceEvaluator(**judge_options),
        "response_completeness": ResponseCompletenessEvaluator(**judge_options),
        "journey_coherence": JourneyCoherenceEvaluator(**judge_options),
    }
