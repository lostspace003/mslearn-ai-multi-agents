#!/usr/bin/env bash
# Local emulation of deploy-environment.yml agent steps: serial azd deploy + show + version-pinned smoke, then capture.
set -euo pipefail
export MSYS_NO_PATHCONV=1 AZD_SKIP_UPDATE_CHECK=true AZURE_DEV_USER_AGENT=microsoft_foundry_skill NO_COLOR=1 PYTHONUTF8=1
P=/c/Users/<user>/Desktop/mslearn-ai-multi-agents/Allfiles/09-fabrikam-multi-agent-cicd/.venv/Scripts/python.exe
mkdir -p artifacts
for svc in scanner reviewer orchestrator; do
  azd deploy $svc --no-prompt > artifacts/$svc-deploy.log 2>&1
  v=$(azd env get-value AGENT_${svc^^}_VERSION | tr -d '\r')
  azd ai agent show $svc --output json > artifacts/$svc-show.json
  msg="Return a one-line readiness response."
  [ $svc = orchestrator ] && msg="Review fabrikam/payments-api commit 0123456789abcdef: validate payment amount bounds."
  azd ai agent invoke $svc --version "$v" --protocol responses --new-session "$msg" > artifacts/$svc-smoke.txt 2>&1
  echo "$svc deployed version=$v"
done
SOURCE_COMMIT=$(git rev-parse HEAD); echo $SOURCE_COMMIT > artifacts/source-commit.txt
$P scripts/export_release.py --agents agents --manifest artifacts/release-set-source.json --contracts artifacts/current-contracts.json --source-commit "$SOURCE_COMMIT" --environment development --status validated
azd env get-values --output json > artifacts/azd-values.json
PYTHONPATH=. $P scripts/capture_release_set.py --manifest artifacts/release-set-source.json --azd-values artifacts/azd-values.json --output artifacts/release-set-bound.json
