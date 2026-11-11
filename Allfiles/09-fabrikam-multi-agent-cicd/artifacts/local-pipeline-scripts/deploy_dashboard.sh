#!/usr/bin/env bash
# Local emulation of "azd deploy dashboard": az acr build (no local Docker daemon) + az containerapp update.
# Usage: deploy_dashboard.sh <bound-manifest> <revision-suffix>
set -euo pipefail
export MSYS_NO_PATHCONV=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8
P=/c/Users/<user>/Desktop/mslearn-ai-multi-agents/Allfiles/09-fabrikam-multi-agent-cicd/.venv/Scripts/python.exe
RG=rg-lab09-a00d677d; APP=fabrikam-release-lab09-cicd-d; ACR=acrqytjyfbxugnmi2cy
TAG=$(git rev-parse --short HEAD)
get() { $P -c "import json,sys;d=json.load(open(sys.argv[1]));o=d['agents']['orchestrator']['hosted_deployment'];print({'id':d['release_set_id'],'n':o['name'],'v':o['version'],'e':o['responses_endpoint']}[sys.argv[2]],end='')" "$1" "$2"; }
RSID=$(get "$1" id); ON=$(get "$1" n); OV=$(get "$1" v); OE=$(get "$1" e)
if ! az acr repository show-tags -n $ACR --repository fabrikam-dashboard -o tsv 2>/dev/null | grep -qx "$TAG"; then
  az acr build -r $ACR -t fabrikam-dashboard:$TAG -f dashboard/Dockerfile . --no-logs -o none
fi
az containerapp update -g $RG -n $APP --image $ACR.azurecr.io/fabrikam-dashboard:$TAG --revision-suffix "$2" \
  --set-env-vars "RELEASE_SET_ID=$RSID" "ORCHESTRATOR_AGENT_NAME=$ON" "ORCHESTRATOR_AGENT_VERSION=$OV" "ORCHESTRATOR_RESPONSES_ENDPOINT=$OE" PORT=8000 -o none
echo "deployed $APP--$2 image=$TAG release_set=$RSID orchestrator=$ON:$OV"
