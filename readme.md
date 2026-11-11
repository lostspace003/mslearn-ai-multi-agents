# Multi-Agent AI Labs (Microsoft Foundry)

**What this is:** 17 hands-on labs on building teams of AI agents that work together, with finished code and step-by-step guides.

## Start here
- Open a guide in `Lab-Guide/Word` or `Lab-Guide/PDF`. Start with Lab 01.
- Each guide has every command and code block ready to copy and paste, plus screenshots.
- You need: an Azure subscription, Azure CLI, Python 3.11+, VS Code.

## How each lab works
- Deploy the Azure resources with Azure CLI.
- Paste the missing code into the marked `LAB PLACEHOLDER` spots.
- Run it, then check the result against the guide.
- Delete the resource group when you finish, to stop charges.

## What the labs cover
- **01–04:** agent loops, orchestration, splitting tasks, agents talking to each other.
- **05–08:** prompting, tools (MCP), search (RAG), shared memory.
- **09–12:** automated releases, security, responsible AI, agent lifecycle.
- **13–17:** monitoring, evaluation, speed and cost, human approval, incident response.

## What was changed from the original Microsoft repo
- Completed the missing code in all 17 labs (`Allfiles/`).
- Deployed with Azure CLI instead of `azd`.
- Fixed lab bugs and added missing permission steps (details in each `LAB-REPORT.md`).
- Added the Word and PDF guides in `Lab-Guide/`.
- Added `LABS-SUMMARY.md`: results for every lab.

Original labs: [MicrosoftLearning/mslearn-ai-multi-agents](https://github.com/MicrosoftLearning/mslearn-ai-multi-agents)
