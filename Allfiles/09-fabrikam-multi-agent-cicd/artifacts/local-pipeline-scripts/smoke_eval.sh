#!/usr/bin/env bash
# Local emulation of the "Run version-bound smoke evaluation" workflow step (jq replaced by python).
set -e
P=/c/Users/<user>/Desktop/mslearn-ai-multi-agents/Allfiles/09-fabrikam-multi-agent-cicd/.venv/Scripts/python.exe
export MSYS_NO_PATHCONV=1 AZD_SKIP_UPDATE_CHECK=true AZURE_DEV_USER_AGENT=microsoft_foundry_skill NO_COLOR=1 PYTHONUTF8=1
: > artifacts/evaluation-results.jsonl
ver=$($P -c "import json;print(json.load(open('artifacts/release-set-bound.json'))['agents']['orchestrator']['hosted_deployment']['version'])")
while IFS= read -r sample; do
  [ -z "$sample" ] && continue
  id=$($P -c "import json,sys;print(json.loads(sys.argv[1])['id'])" "$sample")
  prompt=$($P -c "import json,sys;print(json.loads(sys.argv[1])['input'])" "$sample")
  response=$(azd ai agent invoke orchestrator --version "$ver" --protocol responses --new-session "$prompt")
  $P -c "import json,sys;print(json.dumps({'id':sys.argv[1],'status':'passed','response':sys.argv[2]}))" "$id" "$response" >> artifacts/evaluation-results.jsonl
done < assets/evaluation/smoke-v1.jsonl
$P scripts/evaluation_evidence.py --manifest artifacts/release-set-bound.json --dataset assets/evaluation/smoke-v1.jsonl --results artifacts/evaluation-results.jsonl --output artifacts/evaluation-evidence.json
