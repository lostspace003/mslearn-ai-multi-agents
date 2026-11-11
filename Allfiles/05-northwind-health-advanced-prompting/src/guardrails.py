"""Learner-owned deterministic guardrail interventions."""
from __future__ import annotations
import re
from typing import Any

INJECTION_PATTERNS = (
    r"ignore\s+(?:previous|prior|all)\s+instructions",
    r"(?:system|developer)\s+(?:message|prompt|override)",
    r"disregard\s+(?:previous|prior|all)",
    r"reveal\s+(?:the\s+)?system\s+prompt",
    r"skip\s+(?:safety|contraindication)\s+checks",
)

def _contains_injection(value:str)->bool:
    return any(re.search(pattern,value,flags=re.IGNORECASE) for pattern in INJECTION_PATTERNS)

def guard_input(case:dict[str,Any])->dict[str,Any]:
    """Validate and delimit untrusted input; fail closed on injection signals."""
    # LAB PLACEHOLDER 1: Replace this line with the Task 1 sample.
    required = {
        "id": str,
        "reviewed": bool,
        "reviewer_id": str,
        "deidentified": bool,
        "consent": str,
        "provenance": str,
        "patient_text": str,
        "expected": str,
    }
    if any(key not in case or not isinstance(case[key], value_type) for key, value_type in required.items()):
        raise ValueError("Case does not match the required schema")
    if case["consent"] != "synthetic" or not case["deidentified"]:
        raise ValueError("Only deidentified synthetic cases are allowed")
    if case["expected"] not in {"allow", "block"}:
        raise ValueError("Case expected value must be allow or block")
    if _contains_injection(case["patient_text"]):
        raise ValueError("Potential prompt injection detected")

    escaped = (
        case["patient_text"]
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    safe = dict(case)
    safe["patient_text"] = f"<untrusted-patient-text>{escaped}</untrusted-patient-text>"
    return safe
def guard_tool_call(name:str,arguments:dict[str,Any])->dict[str,Any]:
    """Enforce tool allow-list, parameter schema, content, and ranges."""
    # LAB PLACEHOLDER 2: Replace this line with the Task 2 sample.
    if name != "lookup_clinical_evidence":
        raise ValueError("Tool is not allowed")
    if set(arguments) != {"topic"} or not isinstance(arguments.get("topic"), str):
        raise ValueError("Tool arguments must contain only a string topic")
    topic = arguments["topic"].strip()
    if not 1 <= len(topic) <= 120:
        raise ValueError("Tool topic must contain 1 to 120 characters")
    if _contains_injection(topic):
        raise ValueError("Potential tool-argument injection detected")
    return {"topic": topic}
def guard_tool_response(name:str,response:dict[str,Any])->dict[str,Any]:
    """Enforce response schema, redaction, scanning, and value ranges."""
    # LAB PLACEHOLDER 3: Replace this line with the Task 3 sample.
    if name != "lookup_clinical_evidence":
        raise ValueError("Tool response source is not allowed")
    allowed = ("topic", "source", "evidence_gap", "clinician_review_required")
    if any(field not in response for field in allowed):
        raise ValueError("Tool response is missing a required field")
    if response["clinician_review_required"] is not True:
        raise ValueError("Tool response must require clinician review")
    if any(
        not isinstance(response[field], str)
        for field in ("topic", "source", "evidence_gap")
    ):
        raise ValueError("Tool response text fields must be strings")
    if any(_contains_injection(response[field]) for field in ("topic", "source", "evidence_gap")):
        raise ValueError("Potential tool-response injection detected")

    safe = {field: response[field] for field in allowed}
    identifier_pattern = r"\b(?:patient|member|record)[-_ ]?id\s*[:=]\s*\S+"
    for field in ("topic", "source", "evidence_gap"):
        safe[field] = re.sub(
            identifier_pattern,
            "[REDACTED]",
            safe[field],
            flags=re.IGNORECASE,
        )
    return safe
def guard_output(text:str)->dict[str,Any]:
    """Validate advisory language, evidence gaps, escalation, and output schema."""
    # LAB PLACEHOLDER 4: Replace this line with the Task 4 sample.
    try:
        payload = __import__("json").loads(text)
    except (ValueError, TypeError) as exc:
        raise ValueError("Output must be valid JSON") from exc

    required = {"summary", "evidence_gaps", "uncertainty", "clinician_review_required"}
    if set(payload) != required:
        raise ValueError("Output does not match the required schema")
    if not isinstance(payload["summary"], str) or not payload["summary"].strip():
        raise ValueError("Output summary is required")
    if not isinstance(payload["uncertainty"], str) or not payload["uncertainty"].strip():
        raise ValueError("Output uncertainty is required")
    if not isinstance(payload["evidence_gaps"], (str, list)) or not payload["evidence_gaps"]:
        raise ValueError("Output evidence gaps are required")
    if payload["clinician_review_required"] is not True:
        raise ValueError("Output must require clinician review")

    unsafe = (
        r"\bdiagnosis\s+is\b",
        r"\bdiagnosed\s+with\b",
        r"\bprescrib(?:e|ed|ing)\b",
        r"\btake\s+\d+(?:\.\d+)?\s*(?:mg|ml|tablet)s?\b",
    )
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in unsafe):
        raise ValueError("Output crosses the clinical advisory boundary")
    return payload