# Lab 11 - Design review (Task 7)

**Why is the human-review gate deterministic instead of delegated to the orchestrator agent?**
The release decision has to be repeatable, auditable and tied to a versioned policy threshold (`max_fairness_disparity: 0.10`). The same evidence should always give the same answer. A model can vary its wording, misread the numbers, or be steered by prompt content. With the deterministic gate it also fails closed: missing or malformed evidence forces human review. The orchestrator only explains a decision that has already been made; it cannot override it.

**How could bias compound if the fairness auditor received a security review framed with developer metadata?**
The auditor would be anchored by findings that are not about fairness, such as severity or confidence. It would also see proxy signals like names, tenant, region or stack preference. It could then justify or inflate the gap between stacks, for example "Node code is riskier," instead of measuring the paired probes alone. Its output then feeds the orchestrator, so one biased framing is repeated downstream and looks like independent confirmation. Purpose-specific payloads break that feedback loop.

**Which additional controls would be required before processing real customer source code?**
- A data processing agreement, customer consent, and a documented purpose limitation.
- Secret and PII scanning and redaction before any model call.
- Data residency and region pinning.
- Private endpoints with public network access disabled, and customer-managed keys.
- Retention and deletion policies for the evidence and trace stores.
- Prompt-injection defenses (Prompt Shields) and a reviewed custom guardrail policy. Do not rely on default guardrails alone.
- Least-privilege managed identities in place of user credentials, plus access reviews.
- A red-team and evaluation pass for each language stack, with a larger set of fairness probes.
- A concurrency-safe, tamper-evident central evidence sink in place of local JSONL.
- A documented human-review workflow with SLAs and an appeal path.

**When should an audit store retain full specialist output instead of response IDs and minimized policy evidence?**
Retain full output only when a specific obligation needs it: a legal hold or regulatory investigation, an incident or dispute where the exact recommendation must be reproduced, or a period of model evaluation and quality review. Even then, store it in an access-controlled, encrypted store with a defined retention period, and redact any customer code or identity. The source system's response retention can expire, so response IDs alone may not let you reconstruct the record. In every other case, response IDs, hashes and policy metadata are sufficient and minimize exposure.
