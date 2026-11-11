# Lab 04 - Task 7: Review the design

**Why does tenant ownership come from the trusted caller rather than the agent card?**
The card is self-declared data supplied by the agent being registered. If it could set `tenantId`, any agent could
place itself in another tenant's partition and be discovered for that tenant's requests. `Registry.register` therefore
overwrites `tenantId` with the value from the trusted caller (in production, derived from verified identity claims),
and the same principle drives the `/a2a` check against `A2A_TENANT_ID` instead of trusting request JSON.

**Why can the discovery registry expire while the audit container remains durable?**
Registry entries describe live, routable instances; a card without a recent heartbeat is stale and must stop receiving
traffic, so the heartbeat filter (120 s) plus the container TTL (300 s) self-clean abandoned registrations. Audit records
are evidence of decisions that were made; compliance and investigations need them long after the agents are gone, so the
`tasks` and `audit` containers use TTL -1 and are only removed deliberately.

**How do ETags prevent one agent from silently overwriting another agent's contribution?**
Each replace is conditional on the `_etag` read (`IfNotModified`). If another agent wrote in between, Cosmos DB returns
HTTP 412 instead of applying a last-writer-wins overwrite. `update_task` then rereads the latest document and reapplies
only the caller's own `contributions[agent_id]` entry (bounded to three attempts), so other agents' entries are kept.
Verified in this lab: the stale write was rejected with 412 and `stale_writer` never persisted.

**Which conflict decisions must remain deterministic rather than being delegated to an agent?**
Precedence between roles (compliance > risk > analysis), escalation when there is a tie or no recognised role, tenant
boundary enforcement, and what is written to the audit record. These must be reproducible, explainable and not
susceptible to prompt injection or model variance; agents may supply the candidate outputs, but the policy that picks a
winner or escalates to a human is code.
