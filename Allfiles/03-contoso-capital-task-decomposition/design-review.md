# Lab 03 - Task 7: Review the design

**Which plan invariants must never be delegated to a model?**
The ones `validate_plan` and the dispatcher enforce in code: a bounded task count (1-6), unique non-empty task IDs, only registry-known agents, dependencies that point to existing tasks (no self-references), an acyclic graph, exactly one `thesis-synthesis` task that depends on every terminal evidence branch with nothing depending on it, dispatch only after every prerequisite succeeds, a deadlock error instead of an endless loop, a size cap on each handoff envelope, and a replan budget of one. The model can propose a plan. Code decides whether the plan is admissible.

**When is a fixed chain cheaper and safer?**
When the query shape is known and stable, for example a simple lookup or a fixed "one evidence source, then synthesis" path. A fixed chain skips the planner call and its latency and tokens (about 1.7-1.9 s and one extra response per run here). It also has no plan-validation failure mode and gives the same trace shape on every run, which makes auditing simpler. Dynamic decomposition pays off only when queries vary enough that a fixed chain would over-process simple work or miss dependencies in complex work.

**What context can be summarized without breaking downstream evidence?**
Narrative reasoning, restated assumptions, and verbose observations can be truncated to the per-dependency `summary_limit`. These items must be preserved verbatim:
- the `task_id`
- the `response_id`/`source_response_ids` that trace each claim back to a live response
- the objective and `expected_schema`
- the correlation ID
- explicit `missing_evidence` and confidence fields

Without these, synthesis cannot caveat correctly and the replan signal is lost. In practice, truncating a JSON summary can cut off the trailing `missing_evidence` keys, so specialists should put gaps and confidence first.

**Which signal justifies the single replan budget?**
Use an evidence-driven signal from a completed specialist: a non-success status, a structured `status` of `missing_evidence` or `capability_unavailable`, a non-empty `missing_evidence` field, or a numeric confidence below 0.5. Stylistic dissatisfaction or a long answer does not justify a replan. Even then, the replan should cover only the remaining DAG and must pass `validate_plan` again. In this lab both live runs raised the signal (`replan_count: 1`) because the synthetic-only query makes specialists report missing evidence. This shows the budget caps the signal at one instead of letting it loop.
