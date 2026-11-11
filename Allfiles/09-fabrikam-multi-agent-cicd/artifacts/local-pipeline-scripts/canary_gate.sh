#!/usr/bin/env bash
# Local emulation of canary-quality-gate.yml (+ dispatch of rollback-agents.yml on rollback).
# Usage: canary_gate.sh <metric_profile> <failed_agent> <candidate_evidence_dir> <output_dir>
set -euo pipefail
S=$(cygpath -u "$TEMP/claude/726b3d4a15383912/af0c9777-47be-46f5-9799-a39e98667458/scratchpad"); SW=$(cygpath -w $S/lab09)
export MSYS_NO_PATHCONV=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8
P=/c/Users/<user>/Desktop/mslearn-ai-multi-agents/Allfiles/09-fabrikam-multi-agent-cicd/.venv/Scripts/python.exe
W="$P $SW\winrun.py run"
PROFILE=$1; FAILED=$2; CAND=$3; OUT=$4; ENVN=development; RG=rg-lab09-a00d677d
STORE=$S/lab09/verified-releases/$ENVN
jqp() { $P -c "import json,sys;d=json.load(open(sys.argv[1]))
for k in sys.argv[2].split('.'): d=d[k]
print('' if d is None else d,end='')" "$1" "$2"; }
rm -rf artifacts; mkdir -p artifacts/candidate artifacts/verified
cp "$CAND/release-set.json" "$CAND/evaluation-evidence.json" artifacts/candidate/
cp "$STORE/release-set.json" artifacts/verified/release-set.json
$P scripts/release_manifest.py --manifest artifacts/verified/release-set.json --environment $ENVN
test "$(jqp artifacts/candidate/release-set.json environment)" = $ENVN
test "$(jqp artifacts/candidate/release-set.json status)" = candidate
test "$(jqp artifacts/candidate/evaluation-evidence.json status)" = passed
echo "candidate evidence OK: $(jqp artifacts/candidate/release-set.json release_set_id) evaluation=passed"
$P -m src.main quality --quality "assets/quality-metrics-$PROFILE.json" --output artifacts/quality-decision.json > /dev/null
ACTION=$(jqp artifacts/quality-decision.json action); echo "policy action=$ACTION reasons=$(jqp artifacts/quality-decision.json reasons)"
if [ "$ACTION" = promote ]; then
  APP=$(jqp artifacts/candidate/release-set.json dashboard.app_name)
  CREV=$(jqp artifacts/candidate/release-set.json dashboard.revision)
  SREV=$(jqp artifacts/verified/release-set.json dashboard.revision)
  $W scripts/apply_canary_decision.py --decision artifacts/quality-decision.json --resource-group $RG --app $APP --stable-revision "$SREV" --strategy blue-green > artifacts/promotion-traffic.raw.json
  $P "$SW\lastjson.py" artifacts/promotion-traffic.raw.json $'{\n  "action"'
  URL=$(jqp artifacts/candidate/release-set.json dashboard.url)
  $P scripts/finalize_release_set.py --manifest artifacts/candidate/release-set.json --output artifacts/release-set.json --app-name $APP --revision "$CREV" --release-channel stable --url $URL --routing-evidence artifacts/promotion-traffic.json --status verified
  SL=$(jqp artifacts/release-set.json dashboard.stable_label_url)
  curl -s --fail --retry 12 --retry-delay 10 --retry-all-errors "$SL/metadata" > artifacts/promoted-dashboard.json
  test "$(jqp artifacts/promoted-dashboard.json release_channel)" = stable
  test "$(jqp artifacts/promoted-dashboard.json orchestrator_version)" = "$(jqp artifacts/release-set.json agents.orchestrator.hosted_deployment.version)"
  $P scripts/release_manifest.py --manifest artifacts/release-set.json --environment $ENVN --app-name $APP
  cp artifacts/release-set.json "$STORE/release-set.json"
  echo "promoted $CREV to stable 100%; persisted verified-$ENVN = $(jqp artifacts/release-set.json release_set_id)"
elif [ "$ACTION" = rollback ]; then
  echo "dispatch quality-regression-detected environment=$ENVN agent_name=$FAILED"
  mkdir -p "$OUT"; cp -r artifacts/. "$OUT/"
  bash $S/lab09/rollback.sh "$FAILED" "$CAND" "$OUT/rollback"
fi
mkdir -p "$OUT"; cp -r artifacts/. "$OUT/"
