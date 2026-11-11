# Agents v1 to v2 migration notes

| Agents v1 construct | Agents v2 replacement |
|---|---|
| `AgentsClient` | `AIProjectClient` plus `get_openai_client(agent_name=agent.name)` |
| Shared project OpenAI endpoint plus `extra_body.agent_reference` | Agent-bound OpenAI client using the agent's dedicated endpoint |
| Thread | A project OpenAI `conversation` |
| Run creation and status polling | Synchronous `responses.create()` calls bounded by application code |
| `requires_action` run state | Typed response output items and tool-call handling when tools are configured |
| GUID agent ID | Stable agent name plus an immutable agent version |
| New thread for an alternate path | `previous_response_id` without a conversation ID |

The migration changes both the client API and the state model. Conversations retain
multi-turn history, while response chaining creates an auditable alternate branch.
Application code, rather than the model, owns the maximum iteration count.
