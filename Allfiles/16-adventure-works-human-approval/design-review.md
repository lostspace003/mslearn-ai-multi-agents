# Lab 16 - Design review

## Task 7 questions

**Which signal should override high model confidence?**
Business and policy signals override confidence. A policy exception (`requires_exception`), detected ambiguity, irreversibility, or high financial/customer impact forces review regardless of model confidence. In the synthetic request the raw confidence is 0.91, but the calibrated (observed) accuracy is only 0.78 and the request needs a policy exception, so it goes to `WAITING_FOR_REVIEW` (required confidence 1.0). Raw confidence is never trusted directly; it is mapped through the versioned calibration curve first.

**Why does the resume worker own execution rather than the reviewer endpoint?**
The reviewer endpoint (webhook / `decide`) only authenticates the reviewer and queues an event on Service Bus. The resume worker is the single place that reads durable state, checks the state machine (terminal / allowed source states), writes the transition with an ETag (`IfNotModified`), executes the protected action, and appends audit evidence. This gives exactly-once state change under retries and duplicate deliveries, survives process restarts (the event waits in the queue), keeps the public HTTP surface free of Cosmos/execution permissions, and makes the reviewer path asynchronous and observable via queue metrics.

**How would you prove that human oversight is substantive rather than rubber-stamping?**
Measure it from the audit and state evidence: rejection and override rates (`active-learning-evaluation.json`), distribution of rationale categories, non-trivial comments, time-to-decision versus request complexity, and whether reviewers disagree with the model on calibration-band items. Seed known-bad synthetic "canary" requests and check they are rejected. Track whether human corrections feed active learning and change calibration/policy over time. Approval rates near 100% with near-zero review time would signal rubber-stamping.

## Task 6 step 15-18: comparison with Durable Functions human-interaction pattern

| Durable pattern concept | This lab |
|---|---|
| `WaitForExternalEvent("Approval")` | Decision event on the `approval-decisions` Service Bus queue |
| Orchestration state / history (replay) | `workflow-state` Cosmos container (state, `version`, `_etag`, `review_deadline`, `last_transition`) |
| Durable timer for deadline | `review_deadline` field + `escalate` scan (timer-equivalent) |
| `Task.WhenAny(approval, timer)` race; cancel timer on approval | `apply_decision` accepts `WAITING_FOR_REVIEW`/`ESCALATED`; ETag conflict resolves races; escalation only targets still-waiting items |
| Orchestrator applies event exactly once | `resume` + optimistic concurrency + terminal-state duplicate detection + idempotent audit IDs |

**Tradeoff:** The hand-rolled design exposes queue and state mechanics explicitly and works without rewriting the app as Durable Functions, but the application now owns replay safety, scheduling the deadline scan, duplicate handling and race resolution that a durable orchestrator coordinates for you. Durable Functions would reduce custom code but couple the workflow to that runtime and hide the mechanics.
