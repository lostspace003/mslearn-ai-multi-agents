# Lab 12 - Design review (Task 7)

**Why is a prompt hash part of an agent version?**
Foundry versions are immutable, but a version number alone does not show *what* changed. The `prompt_sha256` in the manifest ties the logical release (2.4.0) to the exact instructions that were evaluated and approved. Auditors can recompute the hash to prove that the deployed prompt is the one that passed evaluation. Any prompt edit changes the hash, so it needs a new version and a new approval.

**Which changes require manual or customer approval?**
Material changes do. These include prompt or instruction edits, a model or model-version change, output-schema or compatibility changes between agents (scanner to reviewer to orchestrator), evaluation thresholds or datasets, and anything that changes the EU AI Act risk classification or the technical file. Retiring or deleting a version also needs governance approval. Customers must be notified, or must consent, when they pin a version or consume its contract.

**Why should deprecation and consumer migration precede deletion of one topology component?**
Other components and tenants call or pin specific versions. Deleting a version first breaks those consumers immediately and leaves no rollback target. A recorded deprecation, a notice period (at least 90 days here), a published replacement version and completed migration let consumers move safely. After that, deletion is a non-event and the rest of the topology keeps working. In this lab, the reviewer and orchestrator survived the scanner's retirement.

**What proves a retired version has no remaining consumers?**
Evidence, not assumption: zero active consumers and zero active pins in the retirement request, backed by usage telemetry or metering (no recent requests for that `agent_id`/`agent_version`), plus the topology manifests that reference the version. A completed archive and a recorded deprecation complete the record. The gate fails closed if any of these values is non-zero or missing.

**Why must quota enforcement and meter increments use one conditional update?**
If the check and the increment are separate writes, two concurrent requests can both read the same counter, both pass the limit, and both write. That loses an increment and lets usage exceed the quota or the rate limit. Doing the check on the read item and then calling `replace_item` with `IfNotModified` on its `_etag` makes check-and-increment atomic. A concurrent writer gets HTTP 412 and retries against fresh values, and a denied request never writes.

**How does chargeback evidence differ from an Azure invoice?**
Chargeback is an internal allocation. Estimated USD is computed from application-metered tokens using a governance price (0.005 USD per 1,000 tokens in `promotion-policy.yaml`) and assigned to a tenant and cost center. An Azure invoice is the provider's actual bill for the subscription's resources, at Azure list or contract prices, and it is not split by internal tenant. The two will not match exactly, and chargeback records are not a billing document.
