#!/usr/bin/env bash
# Lab 16 end-to-end run (synthetic data). Usage: bash run16.sh > artifacts-lab16.txt 2>&1
set -u
P=.venv/Scripts/python
RG=$(grep AZURE_RESOURCE_GROUP .env | cut -d'"' -f2)
NS=$(grep SERVICE_BUS_NAMESPACE .env | cut -d'"' -f2 | cut -d. -f1)
qc(){ echo "--- queue counts ($1)"; for q in approval-requests approval-decisions; do echo -n "$q: "; az servicebus queue show -g $RG --namespace-name $NS -n $q --query "countDetails.{active:activeMessageCount,dead:deadLetterMessageCount}" -o json | tr -d '\n '; echo; done; }
wid(){ $P -c "import json,sys;print(json.load(open(sys.argv[1]))['id'])" "$1"; }
run(){ echo; echo ">>> python -m src.main $*"; $P -m src.main "$@"; }
submit(){ $P -m src.main submit --input "$1" > "$2"; echo ">>> submit $1 -> $(wid $2) state=$($P -c "import json,sys;print(json.load(open(sys.argv[1]))['state'])" $2)"; }

echo "=== A: approved -> executed, then duplicate"
A=$(wid artifacts-submit-A.json); echo "A=$A (submitted earlier, see artifacts-submit-A.json)"
run status --workflow-id $A
run decide --workflow-id $A --decision approved --reviewer SYN-REVIEWER-01 --comment "Within exception authority" --category within_authority
run resume
run decide --workflow-id $A --decision approved --reviewer SYN-REVIEWER-01 --comment "Duplicate redelivery test" --category within_authority
run resume

echo "=== B: rejected -> closed"
submit assets/refund-request.json artifacts-submit-B.json; B=$(wid artifacts-submit-B.json)
run decide --workflow-id $B --decision rejected --reviewer SYN-REVIEWER-02 --comment "Carrier delay evidence insufficient" --category insufficient_evidence
run resume

echo "=== C: overridden -> executed"
submit assets/refund-request.json artifacts-submit-C.json; C=$(wid artifacts-submit-C.json)
run decide --workflow-id $C --decision overridden --reviewer SYN-REVIEWER-03 --comment "Supervisor override for gold tier" --category supervisor_override
run resume

echo "=== E: cancelled -> no execution"
submit assets/refund-request.json artifacts-submit-E.json; E=$(wid artifacts-submit-E.json)
run decide --workflow-id $E --decision cancelled --reviewer SYN-REVIEWER-01 --comment "Customer withdrew request" --category customer_withdrew
run resume

echo "=== D: overdue -> escalated"
submit assets/refund-request-overdue.json artifacts-submit-D.json; D=$(wid artifacts-submit-D.json)
sleep 2
run escalate
run status --workflow-id $D

echo "=== W: webhook reviewer path"
submit assets/refund-request.json artifacts-submit-W.json; W=$(wid artifacts-submit-W.json)
$P -m src.reviewer_webhook --port 8080 > artifacts-webhook-server.txt 2>&1 &
WPID=$!; sleep 4
qc "before webhook POST"
echo ">>> POST /api/reviewer-decisions (X-MS-CLIENT-PRINCIPAL-ID: SYN-REVIEWER-01)"
curl -s -w '\nHTTP %{http_code}\n' -X POST http://127.0.0.1:8080/api/reviewer-decisions \
  -H 'X-MS-CLIENT-PRINCIPAL-ID: SYN-REVIEWER-01' -H 'Content-Type: application/json' \
  -d "{\"workflow_id\":\"$W\",\"decision\":\"APPROVED\",\"comment\":\"Synthetic local reviewer test\",\"category\":\"within_authority\"}"
echo ">>> POST without principal header (expect 401)"
curl -s -w '\nHTTP %{http_code}\n' -X POST http://127.0.0.1:8080/api/reviewer-decisions -H 'Content-Type: application/json' -d '{}'
sleep 3
qc "after webhook POST, before resume"
run resume
sleep 3
qc "after resume"
kill $WPID 2>/dev/null

echo "=== Active learning"
echo ">>> python -m src.active_learning"
$P -m src.active_learning --output reports/active-learning.jsonl --evaluation reports/active-learning-evaluation.json
echo "IDS A=$A B=$B C=$C D=$D E=$E W=$W"
