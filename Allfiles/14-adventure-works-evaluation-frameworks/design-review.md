# Lab 14 - Design review (Task 7)

**Which system-level metric would expose a successful agent response followed by a failed handoff?**
`journey_coherence` (the journey-level judge). It scores the whole multi-agent trace against the grounding context and
expected behavior, so a fluent final answer that dropped a fact during a handoff (for example, regression-handoff-002,
where SKU-SYN-B is never confirmed) scores low there even if a component metric such as `intent_resolution` stays high.
`response_completeness` against `expected_behavior` is the supporting signal; journey-level task success is the gate.

**What calibration sample size would you require before a judge can block production?**
Three labelled rows (this lab) only demonstrate the mechanism. Before a judge can block production I would require at
least ~100 human-labelled rows, stratified across partitions and score levels (including several 1-2 failures), with
two raters and measured inter-rater agreement. Agreement should be reported with a confidence interval, and the lower
bound must exceed the 0.67 threshold. Recalibrate whenever the judge model, prompt, or rubric changes.

**Which cases belong in canary, regression, and historical-failure partitions?**
- Canary: small, stable, high-traffic happy paths (e.g. a damaged-item return within policy) that must always pass. They
  run on every change as a smoke test.
- Regression: targeted cases for previously fixed or known-fragile behavior, such as multi-item handoffs and preserving
  amounts or shipping options across agents. They guard against reintroducing old bugs.
- Historical failure: anonymised, synthetic reproductions of real incidents, such as out-of-window returns that must
  route to human approval and must not auto-approve, and grounding contradictions. They prove that past production
  failures stay fixed.
