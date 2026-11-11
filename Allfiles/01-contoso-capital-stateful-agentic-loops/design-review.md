# Lab 01 design review

- **Conversation vs `previous_response_id`:** Use a conversation when one durable, multi-turn thread must accumulate history that later turns (and auditors) read as a single context. Use `previous_response_id` chaining for short-lived "what-if" branches that must not mutate the main thread.
- **Completion signal vs limit:** The `STATUS: COMPLETE|CONTINUE` signal belongs in model instructions. The maximum iteration count (`MAX_LOOP_ITERATIONS`) must stay in application code so a misbehaving model cannot loop forever.
- **Migrating v1 thread state:** Export v1 thread messages with the v1 SDK, then replay them as items into new v2 conversations (or store a summary as the first item). Keep a mapping table from v1 thread ID to v2 conversation ID, and validate message counts.
- **Branch audit metadata:** Keep the parent response ID, branch response ID, conversation ID, agent name and version, timestamps, status, and a hash or label of the branch assumption. Do not keep the raw prompt or answer text.
