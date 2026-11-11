# Lab 02 - Design review (Task 7)

**Why does `pattern` remain `parallel` in both runs?**
`select_execution_pattern` looks only at the task graph: none of the three spokes declares a `depends_on` on another spoke in the batch. The optional-failure input differs only in `simulate_optional_failure`, which is applied *after* the live calls. Failure handling does not change the dependency graph, so the pattern stays the same.

**Why must optional failure leave quorum ready, while removing compliance evidence and adding a caveat?**
Quorum is defined by the required set (`market-spoke`, `risk-spoke`). Both succeeded, so the brief can still be produced. Failed output is not evidence. Leaving it out stops the supervisor from treating a missing or invalid answer as fact. Listing `compliance-spoke` in `missing_agents` makes the supervisor disclose the gap, so the brief does not look complete when it is not.

**Which decisions belong in deterministic code rather than agent judgment?**
- Choosing parallel or sequential execution from declared dependencies.
- The concurrency bound (semaphore) and per-call timeouts.
- Turning failures into one normalized shape, which keeps exceptions and secrets out of the payload.
- Which agents are required and whether quorum is met.
- Blocking synthesis (failing closed) when required evidence is missing.
- What goes into the supervisor payload.

Agents own only the analysis and the synthesis wording.

**When would these specialists justify their coordination cost over a single agent, and what would you measure?**
They pay off when:
- the specialties need separate instructions, tools, data access or owners;
- the independent work is slow enough that running it in parallel saves real wall-clock time;
- each contribution needs its own audit trail.

To support the decision, compare the specialists with a single-agent baseline on the same scenarios:
- **Quality:** evaluator or rubric scores, caveat or omission rate, and hallucination rate.
- **Latency:** p50/p95 end-to-end latency.
- **Cost:** tokens per run, number of calls and price per brief.
- **Reliability:** failure and timeout rates per spoke.
- **Scale:** quorum-failure frequency and throttling (429s) under concurrency.

## Optional challenge - failure investigation
Run: `portfolio-request-high-risk-failure.json`, where `compliance-spoke` was forced to fail after its live call on the sequential guarded route.

The quorum output shows `status=ready`, `missing_agents=[compliance-spoke]` and `missing_required=[]`. The orchestrator therefore **continued**. It did not fall back and it did not fail closed. The supervisor stated that compliance evidence was missing.

Note: the dependent spokes still ran, even though their prerequisite (compliance) had failed. The runner orders the calls but does not gate them on the success of their dependencies. A production guarded route should either make `compliance-spoke` required for that route, which makes it fail closed, or skip dependents when a prerequisite fails.
