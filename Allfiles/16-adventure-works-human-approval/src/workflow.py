"""Durable approval state and messaging implementation."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from azure.core import MatchConditions
from azure.core.credentials import TokenCredential
from azure.cosmos import CosmosClient, exceptions
from azure.servicebus import ServiceBusClient, ServiceBusMessage

TERMINAL_STATES = {"EXECUTED", "REJECTED", "CANCELLED"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def calibrate_confidence(raw_confidence: float, curve_path: Path) -> float:
    """Map raw confidence to observed accuracy using the nearest calibration point."""
    curve = json.loads(curve_path.read_text(encoding="utf-8"))
    nearest = min(
        curve["points"],
        key=lambda point: abs(float(point["raw_confidence"]) - raw_confidence),
    )
    return float(nearest["observed_accuracy"])


def assess_risk(request: dict[str, Any]) -> dict[str, Any]:
    """Return risk tier, calibrated confidence requirement, and review decision."""
    if request.get("requires_exception"):
        risk_level = "exception"
        required_confidence = 1.0
        reason = "policy_exception"
    elif request.get("ambiguity_detected"):
        risk_level = "high"
        required_confidence = 0.88
        reason = "ambiguity_detected"
    elif (
        float(request.get("financial_amount", 0)) > 200
        or int(request.get("customers_affected", 1)) > 10
        or not bool(request.get("reversible", True))
    ):
        risk_level = "high"
        required_confidence = 0.88
        reason = "high_business_impact"
    elif float(request.get("financial_amount", 0)) > 50 or int(request.get("customers_affected", 1)) > 1:
        risk_level = "moderate"
        required_confidence = 0.75
        reason = "moderate_business_impact"
    else:
        risk_level = "low"
        required_confidence = 0.60
        reason = "low_business_impact"
    calibrated = calibrate_confidence(
        float(request["raw_confidence"]),
        Path("assets/calibration-curve.json"),
    )
    requires_review = risk_level == "exception" or request.get("ambiguity_detected", False) or calibrated < required_confidence
    return {
        "risk_level": risk_level,
        "required_confidence": required_confidence,
        "calibrated_confidence": calibrated,
        "requires_review": requires_review,
        "reason": reason if requires_review else "confidence_sufficient",
        # Optional challenge: second confidence band routes to a different reviewer group.
        **select_reviewer_band(calibrated, requires_review),
    }


REVIEWER_BANDS = [
    # (minimum calibrated confidence, band name, synthetic reviewer group)
    (0.75, "near_threshold", "SYN-REVIEW-TIER1"),
    (0.0, "low_confidence", "SYN-REVIEW-SENIOR"),
]


def select_reviewer_band(calibrated: float, requires_review: bool) -> dict[str, Any]:
    """Optional challenge: pick a reviewer group by calibrated-confidence band."""
    if not requires_review:
        return {"review_band": None, "band_threshold": None, "reviewer_group": None}
    for threshold, band, group in REVIEWER_BANDS:
        if calibrated >= threshold:
            return {"review_band": band, "band_threshold": threshold, "reviewer_group": group}
    return {"review_band": None, "band_threshold": None, "reviewer_group": None}


def send_decision_event(
    service_bus_namespace: str,
    decision_queue: str,
    credential: TokenCredential,
    workflow_id: str,
    decision: str,
    reviewer: str,
    comment: str,
    category: str,
) -> None:
    event = {
        "event_id": str(uuid.uuid4()),
        "workflow_id": workflow_id,
        "decision": decision.upper(),
        "reviewer": reviewer,
        "comment": comment,
        "category": category,
        "reviewed_at": utc_now(),
    }
    with ServiceBusClient(service_bus_namespace, credential=credential) as bus:
        with bus.get_queue_sender(decision_queue) as sender:
            sender.send_messages(
                ServiceBusMessage(json.dumps(event), message_id=event["event_id"])
            )


class ApprovalWorkflow:
    def __init__(
        self,
        cosmos_endpoint: str,
        database_name: str,
        state_container: str,
        audit_container: str,
        service_bus_namespace: str,
        request_queue: str,
        decision_queue: str,
        credential: TokenCredential,
    ) -> None:
        cosmos = CosmosClient(cosmos_endpoint, credential=credential)
        database = cosmos.get_database_client(database_name)
        self._state = database.get_container_client(state_container)
        self._audit = database.get_container_client(audit_container)
        self._bus = ServiceBusClient(service_bus_namespace, credential=credential)
        self._request_queue = request_queue
        self._decision_queue = decision_queue

    def append_audit(
        self,
        workflow_id: str,
        event_type: str,
        actor: str,
        previous_state: str | None,
        new_state: str,
        details: dict[str, Any],
        *,
        policy_version: str,
        trace_id: str,
        rationale_category: str,
        event_id: str,
        state_etag: str,
        state_version: int,
    ) -> None:
        actor_hash = hashlib.sha256(actor.encode()).hexdigest()
        record = {
            "id": event_id,
            "event_id": event_id,
            "workflow_id": workflow_id,
            "event_type": event_type,
            "timestamp": utc_now(),
            "actor_hash": actor_hash,
            "previous_state": previous_state,
            "new_state": new_state,
            "policy_version": policy_version,
            "trace_id": trace_id,
            "rationale_category": rationale_category,
            "state_etag": state_etag,
            "state_version": state_version,
            "details": details,
        }
        try:
            self._audit.create_item(record)
        except exceptions.CosmosResourceExistsError:
            existing = self._audit.read_item(
                item=event_id,
                partition_key=workflow_id,
            )
            identity_fields = ("event_id", "workflow_id", "policy_version", "trace_id")
            if any(existing.get(field) != record.get(field) for field in identity_fields):
                raise RuntimeError(
                    f"Audit event ID {event_id} already belongs to different evidence"
                )

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        workflow_id = str(uuid.uuid4())
        risk = assess_risk(request)
        state = "WAITING_FOR_REVIEW" if risk["requires_review"] else "READY_TO_EXECUTE"
        submission_event_id = str(uuid.uuid4())
        submitted_at = utc_now()
        item = {
            "id": workflow_id,
            "workflow_id": workflow_id,
            "state": state,
            "request": request,
            "risk": risk,
            "policy_version": request["policy_version"],
            "trace_id": request["trace_id"],
            "review_deadline": (
                datetime.now(timezone.utc)
                + timedelta(minutes=int(request["review_timeout_minutes"]))
            ).isoformat(),
            "version": 1,
            "updated_at": submitted_at,
            "last_transition": {
                "event_id": submission_event_id,
                "event_type": "submitted",
                "actor_hash": hashlib.sha256(b"agent").hexdigest(),
                "previous_state": None,
                "new_state": state,
                "timestamp": submitted_at,
            },
        }
        created = self._state.create_item(item)
        self.append_audit(
            workflow_id,
            "submitted",
            "agent",
            None,
            state,
            {"risk": risk},
            policy_version=created["policy_version"],
            trace_id=created["trace_id"],
            rationale_category=risk["reason"],
            event_id=submission_event_id,
            state_etag=created["_etag"],
            state_version=created["version"],
        )
        if risk["requires_review"]:
            with self._bus.get_queue_sender(self._request_queue) as sender:
                sender.send_messages(ServiceBusMessage(json.dumps(created), message_id=workflow_id))
        return created

    def get(self, workflow_id: str) -> dict[str, Any]:
        return self._state.read_item(item=workflow_id, partition_key=workflow_id)

    def send_decision(
        self, workflow_id: str, decision: str, reviewer: str, comment: str, category: str
    ) -> None:
        event = {
            "event_id": str(uuid.uuid4()),
            "workflow_id": workflow_id,
            "decision": decision.upper(),
            "reviewer": reviewer,
            "comment": comment,
            "category": category,
            "reviewed_at": utc_now(),
        }
        with self._bus.get_queue_sender(self._decision_queue) as sender:
            sender.send_messages(ServiceBusMessage(json.dumps(event), message_id=event["event_id"]))

    def apply_decision(self, event: dict[str, Any]) -> dict[str, Any]:
        """Apply one external decision using optimistic concurrency."""
        item = self.get(event["workflow_id"])
        previous = item["state"]
        if previous in TERMINAL_STATES:
            self.append_audit(
                item["id"],
                "duplicate_decision",
                event["reviewer"],
                previous,
                previous,
                {"comment": event["comment"]},
                policy_version=item["policy_version"],
                trace_id=item["trace_id"],
                rationale_category=event["category"],
                event_id=event["event_id"],
                state_etag=item["_etag"],
                state_version=item["version"],
            )
            return {"workflow_id": item["id"], "state": previous, "duplicate": True}
        if previous not in {"WAITING_FOR_REVIEW", "ESCALATED"}:
            raise ValueError(f"Cannot apply a reviewer decision from state {previous}")
        decision = event["decision"].upper()
        if decision == "APPROVED":
            new_state = "EXECUTED"
            execution = {"mode": "synthetic", "status": "completed", "executed_at": utc_now()}
        elif decision == "OVERRIDDEN":
            new_state = "EXECUTED"
            execution = {
                "mode": "synthetic",
                "status": "completed_after_override",
                "executed_at": utc_now(),
            }
        elif decision == "REJECTED":
            new_state = "REJECTED"
            execution = None
        elif decision == "CANCELLED":
            new_state = "CANCELLED"
            execution = {
                "mode": "synthetic",
                "status": "cancelled_before_execution",
                "executed_at": None,
            }
        else:
            raise ValueError(f"Unsupported decision {decision}")
        item["state"] = new_state
        item["version"] += 1
        item["updated_at"] = utc_now()
        item["human_review"] = {
            "decision": decision,
            "category": event["category"],
            "comment": event["comment"],
            "reviewed_at": event["reviewed_at"],
        }
        item["execution"] = execution
        item["last_transition"] = {
            "event_id": event["event_id"],
            "event_type": "decision_applied",
            "actor_hash": hashlib.sha256(event["reviewer"].encode()).hexdigest(),
            "previous_state": previous,
            "new_state": new_state,
            "timestamp": item["updated_at"],
        }
        updated = self._state.replace_item(
            item=item["id"],
            body=item,
            etag=item["_etag"],
            match_condition=MatchConditions.IfNotModified,
        )
        self.append_audit(
            item["id"],
            "decision_applied",
            event["reviewer"],
            previous,
            new_state,
            {"comment": event["comment"]},
            policy_version=updated["policy_version"],
            trace_id=updated["trace_id"],
            rationale_category=event["category"],
            event_id=event["event_id"],
            state_etag=updated["_etag"],
            state_version=updated["version"],
        )
        return updated

    def resume(self, max_messages: int = 10) -> list[dict[str, Any]]:
        outcomes = []
        with self._bus.get_queue_receiver(
            self._decision_queue, max_wait_time=5
        ) as receiver:
            for message in receiver.receive_messages(max_message_count=max_messages):
                event = json.loads(str(message))
                try:
                    outcomes.append(self.apply_decision(event))
                    receiver.complete_message(message)
                except Exception:
                    receiver.abandon_message(message)
                    raise
        return outcomes

    def escalate_expired(self) -> list[str]:
        now = utc_now()
        query = "SELECT * FROM c WHERE c.state = 'WAITING_FOR_REVIEW' AND c.review_deadline < @now"
        expired = self._state.query_items(
            query=query,
            parameters=[{"name": "@now", "value": now}],
            enable_cross_partition_query=True,
        )
        escalated = []
        for item in expired:
            previous = item["state"]
            item["state"] = "ESCALATED"
            item["version"] += 1
            item["updated_at"] = now
            escalation_event_id = str(uuid.uuid4())
            item["last_transition"] = {
                "event_id": escalation_event_id,
                "event_type": "escalated",
                "actor_hash": hashlib.sha256(b"scheduler").hexdigest(),
                "previous_state": previous,
                "new_state": "ESCALATED",
                "timestamp": now,
            }
            updated = self._state.replace_item(
                item=item["id"],
                body=item,
                etag=item["_etag"],
                match_condition=MatchConditions.IfNotModified,
            )
            self.append_audit(
                item["id"], "escalated", "scheduler", previous, "ESCALATED", {},
                policy_version=updated["policy_version"],
                trace_id=updated["trace_id"],
                rationale_category="review_deadline_expired",
                event_id=escalation_event_id,
                state_etag=updated["_etag"],
                state_version=updated["version"],
            )
            with self._bus.get_queue_sender(self._request_queue) as sender:
                sender.send_messages(
                    ServiceBusMessage(json.dumps(updated), message_id=str(uuid.uuid4()))
                )
            escalated.append(item["id"])
        return escalated

    def select_active_learning_examples(self, max_items: int = 100) -> list[dict[str, Any]]:
        query = """SELECT TOP @maxItems * FROM c
        WHERE c.human_review.decision IN ('REJECTED', 'OVERRIDDEN')
        ORDER BY c.updated_at DESC"""
        return list(
            self._state.query_items(
                query=query,
                parameters=[{"name": "@maxItems", "value": max_items}],
                enable_cross_partition_query=True,
            )
        )