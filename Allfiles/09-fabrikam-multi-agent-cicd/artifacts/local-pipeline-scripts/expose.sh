#!/usr/bin/env bash
# Local emulation of deploy-environment.yml "Resolve stable dashboard evidence" + "Apply dashboard-only 75/25 exposure"
# + "Persist proven first-release baseline". GitHub release verified-<env> is emulated by $STORE/release-set.json.
set -euo pipefail
S=$(cygpath -u "$TEMP/claude/726b3d4a15383912/af0c9777-47be-46f5-9799-a39e98667458/scratchpad"); SW=$(cygpath -w $S/lab09)
export MSYS_NO_PATHCONV=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8
P=/c/Users/<user>/Desktop/mslearn-ai-multi-agents/Allfiles/09-fabrikam-multi-agent-cicd/.venv/Scripts/python.exe
W="$P $SW\winrun.py run"
ENVN=development; RG=rg-lab09-a00d677d; APP=fabrikam-release-lab09-cicd-d
URL=https://fabrikam-release-lab09-cicd-d.victoriouscliff-2501048e.eastus2.azurecontainerapps.io
STORE=$S/lab09/verified-releases/$ENVN
jqp() { $P -c "import json,sys;d=json.load(open(sys.argv[1]))
for k in sys.argv[2].split('.'): d=d[k] if k else d
print('' if d is None else d,end='')" "$1" "$2"; }
mkdir -p artifacts/previous-verified
if [ -s "$STORE/release-set.json" ]; then
  cp "$STORE/release-set.json" artifacts/previous-verified/release-set.json
  $P scripts/release_manifest.py --manifest artifacts/previous-verified/release-set.json --environment $ENVN --app-name $APP
  STABLE_REV=$(jqp artifacts/previous-verified/release-set.json dashboard.revision); CHANNEL=candidate; BOOT=false
else
  STABLE_REV=; CHANNEL=stable; BOOT=true
fi
REV=$(az containerapp revision list -g $RG -n $APP --query "sort_by([?properties.active], &properties.createdTime)[-1].name" -o tsv | tr -d '\r')
echo "new revision=$REV stable=$STABLE_REV bootstrap=$BOOT"
$P -m src.main quality --quality assets/quality-metrics-healthy.json --output artifacts/quality-decision.json > /dev/null
if [ -n "$STABLE_REV" ]; then TA=(--stable-revision "$STABLE_REV"); else TA=(--initial-revision "$REV"); fi
$W scripts/apply_canary_decision.py --decision artifacts/quality-decision.json --resource-group $RG --app $APP --strategy canary "${TA[@]}" > artifacts/traffic-after-deploy.raw.json
$P "$SW\lastjson.py" artifacts/traffic-after-deploy.raw.json $'{\n  "action"'
STATUS=candidate; [ "$BOOT" = true ] && STATUS=verified
$P scripts/finalize_release_set.py --manifest artifacts/release-set-bound.json --output artifacts/release-set.json --app-name $APP --revision "$REV" --release-channel $CHANNEL --url $URL --routing-evidence artifacts/traffic-after-deploy.json --status $STATUS
SL=$(jqp artifacts/release-set.json dashboard.stable_label_url); CL=$(jqp artifacts/release-set.json dashboard.candidate_label_url)
C="curl -s --fail --retry 12 --retry-delay 10 --retry-all-errors"
$C "$URL/metadata" > artifacts/dashboard-weighted-route.json
$C "$SL/metadata" > artifacts/dashboard-stable-route.json
test "$(jqp artifacts/dashboard-stable-route.json release_channel)" = stable
if [ -n "$STABLE_REV" ]; then
  $C "$CL/metadata" > artifacts/dashboard-candidate-route.json
  test "$(jqp artifacts/dashboard-candidate-route.json release_channel)" = candidate
  TARGET=$CL
else TARGET=$SL; fi
EV=$(jqp artifacts/release-set.json agents.orchestrator.hosted_deployment.version)
$C --max-time 240 --data-urlencode repository=fabrikam/payments-api --data-urlencode commit=0123456789abcdef \
  --data-urlencode "change_summary=Verify immutable release binding." "$TARGET/invoke" > artifacts/dashboard-invocation.html
grep -q "&quot;served_version&quot;: &quot;$EV&quot;" artifacts/dashboard-invocation.html
echo "dashboard invocation served_version=$EV OK"
if [ "$BOOT" = true ]; then
  $P scripts/release_manifest.py --manifest artifacts/release-set.json --environment $ENVN
  mkdir -p "$STORE"; cp artifacts/release-set.json "$STORE/release-set.json"
  echo "persisted first verified baseline to $STORE"
fi
echo "release_set=$(jqp artifacts/release-set.json release_set_id) status=$(jqp artifacts/release-set.json status) stable_label_url=$SL candidate_label_url=$CL"
