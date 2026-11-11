# Lab 01 report: stateful agentic loops

- Resource group: `rg-lab01-5f0e58e9` (eastus2), deployed with `az deployment group create` (Azure CLI, no azd)
- Roles granted to signed-in user at RG scope: Azure AI User, Cognitive Services OpenAI User, Azure AI Developer
- Code: placeholders 1-3 filled in `src/main.py`; `migration-notes.md` created; preflight `READY (local)`
- Run: `python -m src.main --input assets/research-request.json --retain-resources` -> `artifacts-lab01.txt`

| Criterion | Result |
|---|---|
| agent_name/agent_version | PASS: contoso-investment-researcher v1 |
| conversation_id starts `conv_` | PASS |
| resources_retained true | PASS |
| iterations 1-3 with resp_ IDs, headings, final COMPLETE | PASS: 1 iteration, COMPLETE |
| branch_response_id `resp_` and distinct | PASS |
| branch_text addresses 250 bp assumption | PASS |

Left for the user (portal only): check the agent version history and traces at https://ai.azure.com.
Resources were kept on purpose. Cleanup task 8 was skipped.
