# Lab completion summary

All 17 labs were run end to end on 2026-11-11 against subscription "Visual Studio Subscription".
Infrastructure was deployed with Azure CLI (`az deployment group create`) instead of `azd provision`.
Resources were kept on purpose: no lab's cleanup task was run.
Each lab folder has a `LAB-REPORT.md` (evidence per acceptance criterion) and a `design-review.md`.

| Lab | Result | Resource group (region) | Notes |
|---|---|---|---|
| [01 Stateful agentic loops](Allfiles/01-contoso-capital-stateful-agentic-loops/LAB-REPORT.md) | Pass | rg-lab01-5f0e58e9 (eastus2) | |
| [02 Advanced orchestration](Allfiles/02-contoso-capital-advanced-orchestration/LAB-REPORT.md) | Pass | rg-lab02-d019fdcf (eastus2) | Tracked `.env`/artifacts overwritten; challenge flags added to `src/main.py` |
| [03 Task decomposition](Allfiles/03-contoso-capital-task-decomposition/LAB-REPORT.md) | Pass | rg-lab03-bb4dd21c (eastus2) | |
| [04 A2A communication](Allfiles/04-contoso-capital-a2a-communication/LAB-REPORT.md) | Pass | rg-lab04-339fd13d (eastus2) | |
| [05 Advanced prompting](Allfiles/05-northwind-health-advanced-prompting/LAB-REPORT.md) | Pass | rg-lab05-60140848 (eastus2) | Candidate prompt 1.1.0 promoted |
| [06 MCP tools](Allfiles/06-northwind-health-mcp-tools/LAB-REPORT.md) | Pass | rg-lab06-d88283ac (eastus2) | Extra ACR; Azure CLI pre-authorized on the lab's Entra API |
| [07 Advanced RAG](Allfiles/07-northwind-health-advanced-rag/LAB-REPORT.md) | Pass | rg-lab07-80fce608 (eastus) | eastus2 had no AI Search capacity |
| [08 Multi-agent memory](Allfiles/08-northwind-health-multi-agent-memory/LAB-REPORT.md) | Pass | rg-lab08-021aff3d (eastus2) | Hosted agent identity needed extra roles; lab text wrong on `vector_distance` order |
| [09 Multi-agent CI/CD](Allfiles/09-fabrikam-multi-agent-cicd/LAB-REPORT.md) | Pass locally/Azure; GitHub pipeline in progress | rg-lab09-a00d677d + rg-lab09-{dev,stg,prod}-09d06da4 (eastus2) | 8 lab bugs found; no approval gates on free private repo |
| [10 Zero-trust security](Allfiles/10-fabrikam-zero-trust-security/LAB-REPORT.md) | Pass | rg-lab10-198dc6fb (eastus2) | |
| [11 Responsible AI governance](Allfiles/11-fabrikam-responsible-ai-governance/LAB-REPORT.md) | Pass | rg-lab11-d0b8f6c1 (eastus2) | Lab's privacy query has a false positive |
| [12 Agent lifecycle governance](Allfiles/12-fabrikam-agent-lifecycle-governance/LAB-REPORT.md) | Pass | rg-lab12-a575c861 (eastus2) | |
| [13 Distributed observability](Allfiles/13-adventure-works-distributed-observability/LAB-REPORT.md) | Pass | rg-lab13-c59c747d (eastus2) | Confirm the action-group email subscription |
| [14 Evaluation frameworks](Allfiles/14-adventure-works-evaluation-frameworks/LAB-REPORT.md) | Pass | rg-lab14-aed663e6 (eastus2) | Model capacity raised to 100K TPM |
| [15 Performance and cost](Allfiles/15-adventure-works-performance-cost/LAB-REPORT.md) | Pass | rg-lab15-c52d90c3 (westus3) | Redis failed in eastus2 |
| [16 Human approval](Allfiles/16-adventure-works-human-approval/LAB-REPORT.md) | Pass | rg-lab16-fbdf8faa (eastus2) | |
| [17 Incident response](Allfiles/17-adventure-works-incident-response/LAB-REPORT.md) | Pass | rg-lab17-8ea5486e (eastus2) | |

## Things to know

- **Cost:** every resource group above is still running. Lab 06 also has an Entra app registration; Lab 09 has the Entra app `fabrikam-agent-github` and the private repo `lostspace003/fabrikam-agent-cicd`.
- **Secrets:** `.env` in labs 11, 13 and 17 holds an Application Insights connection string. Don't commit `.env` files.
- **Roles granted:** the signed-in user has Foundry/Azure AI roles on each lab resource group; Lab 08 and 09 agent identities and the Lab 09 GitHub app have extra roles described in their reports.
