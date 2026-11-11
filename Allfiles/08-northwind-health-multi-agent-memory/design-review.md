# Lab 08 - Task 7 design review

**Which memory fields should be immutable after creation?**
`id`, `patientId` (it is also the partition key, so it cannot change anyway), `content`, `memoryType`, `timestamp`, `schemaVersion`, `embedding` (it must match `content`), and lineage fields such as `sourceMemoryIds` and `reviewerId`. Only lifecycle metadata should change: `consolidatedInto`/`consolidatedAt`, `supersededBy`, `ttl` and status flags. A correction is written as a new record, never as an in-place edit.

**How should a contradiction supersede an older memory without destroying audit history?**
Write a new memory that has `supersedes: <oldId>` and a reason. In the same partition-scoped transactional batch, patch the old record with `supersededBy`/`supersededAt`, using an ETag condition. Write a content-free audit event that names both IDs. Recall leaves out superseded records by default (`NOT IS_DEFINED(c.supersededBy)`). The old record is kept, or is TTL-expired by the retention policy, so the audit container still shows the full chain.

**When is explicit session-token transfer required instead of client-local token management?**
When the read happens on a different `CosmosClient` instance or process from the write. For example: a separate agent or specialist, a different hosted-agent replica, a request routed to another worker, or a reader after a process restart. The SDK only tracks session tokens inside one client. Readers outside that client must get the token from the write response, as `consistency.py` does, or they may get an eventually consistent (stale) read.

**What would a right-to-deletion verification query need to prove?**
For the patient's partition, it must show:
(1) `SELECT VALUE COUNT(1) FROM c WHERE c.patientId=@p` returns 0 in `patient-memories`, including semantic records derived from that patient and vector/embedding data;
(2) no other partition or container holds the patient's content, for example a cross-partition `CONTAINS`/ID check of `sourceMemoryIds`;
(3) the audit container has a content-free deletion event that lists the deleted IDs, actor/reason and timestamp, while the audit records themselves hold no content;
(4) the check runs with a session token taken after the deletes, or at strong consistency, so a stale replica cannot hide leftover items.
