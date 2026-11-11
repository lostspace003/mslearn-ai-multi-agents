#!/usr/bin/env bash
# Local emulation of rollback-agents.yml. Usage: rollback.sh <failed_agent> <candidate_evidence_dir> <output_dir>
set -euo pipefail
S=$(cygpath -u "$TEMP/claude/726b3d4a15383912/af0c9777-47be-46f5-9799-a39e98667458/scratchpad"); SW=$(cygpath -w $S/lab09)
export MSYS_NO_PATHCONV=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8 AZD_SKIP_UPDATE_CHECK=true AZURE_DEV_USER_AGENT=microsoft_foundry_skill NO_COLOR=1
P=/c/Users/<user>/Desktop/mslearn-ai-multi-agents/Allfiles/09-fabrikam-multi-agent-cicd/.venv/Scripts/python.exe
W="$P $SW\winrun.py"
FAILED=$1; CAND=$2; OUT=$3; ENVN=development; RG=rg-lab09-a00d677d
STORE=$S/lab09/verified-releases/$ENVN
jqp() { $P -c "import json,sys;d=json.load(open(sys.argv[1]))
for k in sys.argv[2].split('.'): d=d[k]
print('' if d is None else d,end='')" "$1" "$2"; }
rm -rf artifacts; mkdir -p artifacts/candidate artifacts/verified
cp "$CAND/release-set.json" artifacts/candidate/; cp "$STORE/release-set.json" artifacts/verified/
$P scripts/release_manifest.py --manifest artifacts/verified/release-set.json --environment $ENVN
test "$(jqp artifacts/candidate/release-set.json environment)" = $ENVN
$P -m src.main rollback-set --manifest artifacts/candidate/release-set.json --failed-agent "$FAILED" --output artifacts/rollback-set.json > /dev/null
echo "rollback closure: $(jqp artifacts/rollback-set.json agents)"
APP=$(jqp artifacts/verified/release-set.json dashboard.app_name)
$W -m scripts.restore_verified_release --verified-manifest artifacts/verified/release-set.json --resource-group $RG --app $APP --environment $ENVN --output artifacts/rollback-evidence.json > artifacts/restore.log 2>&1
SU=$(jqp artifacts/verified/release-set.json dashboard.stable_label_url)
OV=$(jqp artifacts/verified/release-set.json agents.orchestrator.hosted_deployment.version)
RS=$(jqp artifacts/verified/release-set.json release_set_id)
curl -s --fail --retry 12 --retry-delay 10 --retry-all-errors "$SU/metadata" > artifacts/restored-dashboard.json
test "$(jqp artifacts/restored-dashboard.json release_set_id)" = "$RS"
test "$(jqp artifacts/restored-dashboard.json orchestrator_version)" = "$OV"
azd ai agent invoke orchestrator --version "$OV" --protocol responses --new-session "Return a one-line rollback verification response." > artifacts/restored-orchestrator-smoke.txt 2>&1
grep -q "^Version: *$OV" artifacts/restored-orchestrator-smoke.txt
$P -c "import json,sys;e=json.load(open('artifacts/rollback-evidence.json'));c=json.load(open('artifacts/rollback-set.json'))
open('artifacts/incident-issue.md','w').write(f'# Automated compatible-set rollback: {sys.argv[1]}\n\nEnvironment: {sys.argv[2]}\nRestored release set: {e[\"restored_release_set_id\"]}\nReverse-dependency closure: {\", \".join(c[\"agents\"])}\n\n(GitHub issue not created: local emulation; no GitHub repository.)\n')" "$FAILED" $ENVN
echo "restored $RS dashboard=$(jqp artifacts/rollback-evidence.json dashboard_revision) orchestrator=$OV traffic=$(jqp artifacts/rollback-evidence.json traffic_weight)"
mkdir -p "$OUT"; cp -r artifacts/. "$OUT/"
