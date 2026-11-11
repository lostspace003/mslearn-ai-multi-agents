"""OpenTelemetry instrumentation for an Adventure Works agent chain."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import baggage, trace
from opentelemetry import context as otel_context
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.trace import Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


LOGGER_NAME = "adventureworks.observability"
logger = logging.getLogger(LOGGER_NAME)
propagator = TraceContextTextMapPropagator()
# Optional challenge: synthetic request classification travels as W3C baggage.
baggage_propagator = W3CBaggagePropagator()
CLASSIFICATION_KEY = "request.classification"


def configure_telemetry(policy: dict[str, Any]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    connection_string = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if connection_string:
        configure_azure_monitor(
            connection_string=connection_string,
            credential=DefaultAzureCredential(
                managed_identity_client_id=os.environ.get("TELEMETRY_IDENTITY_CLIENT_ID")
            ),
            logger_name=LOGGER_NAME,
            enable_live_metrics=False,
            sampling_ratio=float(policy["sampling"]["lab_export_ratio"]),
        )
        return

    provider = TracerProvider(
        resource=Resource.create({"service.name": "adventure-works-agent-lab"})
    )
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)


def build_next_carrier() -> dict[str, str]:
    """Inject the active W3C context into an outgoing carrier."""
    # LAB PLACEHOLDER 1: Replace this line with the Task 1 sample.
    carrier: dict[str, str] = {}
    propagator.inject(carrier)
    baggage_propagator.inject(carrier)  # Optional challenge
    return carrier


def _context_ids() -> tuple[str, str]:
    context = trace.get_current_span().get_span_context()
    return format(context.trace_id, "032x"), format(context.span_id, "016x")


def _structured_log(
    agent: dict[str, Any],
    session_id: str,
    status: str,
    anomaly_types: list[str],
    classification: object = None,
) -> dict[str, Any]:
    trace_id, span_id = _context_ids()
    agent_id = f"{agent['name']}:{agent['version']}"
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "span_id": span_id,
        "agent_id": agent["name"],
        "agent_version": agent["version"],
        "session_id_hash": hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16],
        "operation_type": agent["operation"],
        "latency_ms": agent["latency_ms"],
        "input_token_count": agent["input_tokens"],
        "output_token_count": agent["output_tokens"],
        "total_token_count": int(agent["input_tokens"]) + int(agent["output_tokens"]),
        "token_anomaly": "token" in anomaly_types,
        "is_error": status == "error",
        "anomaly_types": ",".join(anomaly_types),
        "decision_summary": agent["decision_summary"],
        "status": status,
        "gen_ai.operation.name": agent["operation"],
        "gen_ai.agent.name": agent["name"],
        "gen_ai.agent.id": agent_id,
        "gen_ai.provider.name": "azure.ai.inference",
        "gen_ai.conversation.id": session_id,
        "gen_ai.usage.input_tokens": agent["input_tokens"],
        "gen_ai.usage.output_tokens": agent["output_tokens"],
    }
    if classification:
        record[CLASSIFICATION_KEY] = str(classification)
    if status == "error":
        record["error.type"] = "SyntheticAgentError"
    logger.info("adventureworks.agent.observation", extra=record)
    return record


def execute_agent(
    agent: dict[str, Any],
    session_id: str,
    incoming_carrier: dict[str, str],
    alert_policy: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    parent_context = propagator.extract(incoming_carrier)
    parent_context = baggage_propagator.extract(incoming_carrier, context=parent_context)
    classification = baggage.get_baggage(CLASSIFICATION_KEY, parent_context)
    tracer = trace.get_tracer("adventureworks.agent-chain")
    with tracer.start_as_current_span(
        f"agent.{agent['name']}",
        context=parent_context,
    ) as span:
        agent_id = f"{agent['name']}:{agent['version']}"
        span.set_attribute("gen_ai.operation.name", agent["operation"])
        span.set_attribute("gen_ai.agent.name", agent["name"])
        span.set_attribute("gen_ai.agent.id", agent_id)
        span.set_attribute("gen_ai.provider.name", "azure.ai.inference")
        span.set_attribute("gen_ai.conversation.id", session_id)
        span.set_attribute("gen_ai.usage.input_tokens", agent["input_tokens"])
        span.set_attribute("gen_ai.usage.output_tokens", agent["output_tokens"])
        span.set_attribute("agent.id", agent["name"])
        span.set_attribute("agent.version", agent["version"])
        span.set_attribute("operation.type", agent["operation"])
        span.set_attribute("llm.input_tokens", agent["input_tokens"])
        span.set_attribute("llm.output_tokens", agent["output_tokens"])
        if classification:
            span.set_attribute(CLASSIFICATION_KEY, str(classification))
        time.sleep(float(agent["latency_ms"]) / 1000.0)
        anomaly_types = []
        latency_threshold_ms = int(alert_policy["latency_threshold_ms"])
        if int(agent["latency_ms"]) > latency_threshold_ms:
            anomaly_types.append("latency")
            span.add_event("latency.anomaly", {"threshold_ms": latency_threshold_ms})
        token_count = int(agent["input_tokens"]) + int(agent["output_tokens"])
        token_threshold = float(agent["expected_tokens"]) + (
            float(alert_policy["token_anomaly_sigma"]) * float(agent["token_stddev"])
        )
        if token_count > token_threshold:
            anomaly_types.append("token")
            span.add_event(
                "token.anomaly",
                {"threshold_tokens": token_threshold, "observed_tokens": token_count},
            )
        status = "error" if agent.get("error") is True else ("anomaly" if anomaly_types else "success")
        if status == "error":
            span.set_attribute("error.type", "SyntheticAgentError")
            span.set_status(Status(StatusCode.ERROR, f"Synthetic {status} signal"))
        elif anomaly_types:
            span.set_attribute("agent.anomaly_detected", True)
        record = _structured_log(agent, session_id, status, anomaly_types, classification)
        if classification:
            # Optional challenge: keep the baggage active (with this span) for the next hop.
            token = otel_context.attach(baggage.set_baggage(CLASSIFICATION_KEY, classification))
            try:
                return record, build_next_carrier()
            finally:
                otel_context.detach(token)
        return record, build_next_carrier()


def run_chain(scenario: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    configure_telemetry(policy)
    alert_policy = policy["alerts"]
    records = []
    carrier: dict[str, str] = {}
    classification = scenario.get("request_classification", "synthetic.product_recommendation")
    baggage_propagator.inject(carrier, context=baggage.set_baggage(CLASSIFICATION_KEY, str(classification)))
    for agent in scenario["agents"]:
        record, carrier = execute_agent(
            agent,
            str(scenario["session_id"]),
            carrier,
            alert_policy,
        )
        records.append(record)
    errors = sum(1 for record in records if record["is_error"])
    error_rate = errors / len(records)
    error_rate_anomalous = error_rate > float(alert_policy["error_rate_threshold"])
    logger.info(
        "adventureworks.chain.summary",
        extra={
            "error_count": errors,
            "agent_count": len(records),
            "error_rate": error_rate,
            "error_rate_threshold": float(alert_policy["error_rate_threshold"]),
            "error_rate_anomaly": error_rate_anomalous,
            "policy_id": str(policy["policy_id"]),
            "policy_version": str(policy["version"]),
        },
    )
    tracer_provider = trace.get_tracer_provider()
    if hasattr(tracer_provider, "force_flush"):
        tracer_provider.force_flush(timeout_millis=10000)
    trace_ids = {record["trace_id"] for record in records}
    return {
        "correlation_complete": len(trace_ids) == 1,
        "trace_id": next(iter(trace_ids)) if len(trace_ids) == 1 else None,
        "span_count": len(records),
        "anomalies": [record["agent_id"] for record in records if record["status"] != "success"],
        "error_rate": error_rate,
        "error_rate_anomaly": error_rate_anomalous,
        "records": records,
    }