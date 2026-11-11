# Lab 17 - Design review (Task 7)

**Which observable failure differed most between successful and failed cohorts?**
The pricing span. In `kql/03-hypothesis-comparison.kql` the failed cohort has `PricingFailureRate = 1`, model version
`synthetic-pricing-v2`, error type `SyntheticPriceFormatError`, and an average pricing duration of 350.5 ms. The successful
cohort has failure rate 0, `synthetic-pricing-v1`, no error types, and 51 ms. The payment span also fails in the failed trace,
but it is downstream. Its captured tool response is `approved: true, success: true`, so the payment failure is a symptom of the
bad amount and not an independent fault.

**What evidence would falsify the leading hypothesis (pricing model-version regression)?**
- A failed checkout whose pricing span ran `synthetic-pricing-v1`, or a successful checkout on `synthetic-pricing-v2`. Either one
  breaks the version/outcome correlation in the cohort query.
- A failed trace with no `SyntheticPriceFormatError` on the pricing span. The failure would then come from somewhere else.
- A prompt-hash divergence during replay, or a captured tool mock with `success: false`. Either one points to a prompt or tool
  cause instead of the model. The lab showed the first case: editing the prompt text gives `divergence_count = 1`, and the
  postmortem then stops claiming the model-version cause.
- Multiple `configuration_versions` in the failed operation, which would mean a configuration change happened alongside it.

**Which preventive action changes the system rather than only treating the symptom?**
Gate model-version rollouts. Pin the pricing agent's model deployment version. Add a contract test that validates the output
format of each candidate version against the payment amount schema, using replayed snapshots with captured catalog mocks. Ship
new versions through a canary that rolls back automatically when the version-split pricing failure rate (the cohort query) goes
above a threshold. Retrying payments or muting the alert only treats the symptom.

## Durable checkpoints (Task 6.22-6.26)
A production consumer should use `EventProcessorClient` with a Blob checkpoint store. Give each consumer group its own container
(for example, `$Default` gets a dedicated container) and keep the storage account in the same region as the namespace. Each
partition keeps its own checkpoint, so after a restart the partitions resume from different positions. Write idempotent
evidence first, keyed by alert ID the way `persist_evidence` does, and only then advance that partition's checkpoint. That way
duplicates, late fragments and partitions that lag behind cannot corrupt the reconstruction.
