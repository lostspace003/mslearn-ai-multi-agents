"""Lab 16 validation: inspect Cosmos state + audit evidence (read-only)."""
import json, os
from collections import Counter
from pathlib import Path
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient
load_dotenv(".env")
db = CosmosClient(os.environ["COSMOS_ENDPOINT"], DefaultAzureCredential(exclude_interactive_browser_credential=True)).get_database_client("approvals")
state = list(db.get_container_client("workflow-state").query_items("SELECT * FROM c", enable_cross_partition_query=True))
audit = list(db.get_container_client("approval-audit").query_items("SELECT * FROM c", enable_cross_partition_query=True))
print("== workflow-state records:", len(state))
for s in sorted(state, key=lambda x: x["updated_at"]):
    hr = (s.get("human_review") or {}).get("decision")
    ex = s.get("execution")
    print(f"{s['id']} state={s['state']:<18} v={s['version']} decision={hr} execution={ex and ex['status']} trace={s['trace_id']}")
req = ["workflow_id","event_id","timestamp","actor_hash","previous_state","new_state","rationale_category","policy_version","trace_id","state_etag","state_version"]
print("\n== approval-audit records:", len(audit), dict(Counter(a["event_type"] for a in audit)))
bad = [a["id"] for a in audit if any(k not in a or (a[k] is None and k != "previous_state") for k in req) or not a["timestamp"].endswith("+00:00")]
print("audit records missing required fields / non-UTC:", bad or "none")
print("submitted records with previous_state None (expected):", sum(1 for a in audit if a["event_type"]=="submitted" and a["previous_state"] is None))
# linkage: each state's last_transition.event_id has an audit record whose state_version == state version
ids = {a["id"]: a for a in audit}
unlinked = [s["id"] for s in state if s["last_transition"]["event_id"] not in ids or ids[s["last_transition"]["event_id"]]["state_version"] != s["version"] or ids[s["last_transition"]["event_id"]]["state_etag"] != s["_etag"]]
print("states whose last_transition is not linked to an audit record (etag+version):", unlinked or "none")
# no execution from pending/rejected
viol = [s["id"] for s in state if s["state"] in ("WAITING_FOR_REVIEW","REJECTED","ESCALATED","CANCELLED") and s.get("execution") and s["execution"].get("executed_at")]
print("executions from pending/rejected/escalated/cancelled states:", viol or "none")
rej_ovr = Counter(s["human_review"]["decision"] for s in state if (s.get("human_review") or {}).get("decision") in ("REJECTED","OVERRIDDEN"))
jsonl = [json.loads(l) for l in Path("reports/active-learning.jsonl").read_text().splitlines() if l.strip()]
ev = json.loads(Path("reports/active-learning-evaluation.json").read_text())
print("\n== active learning: cosmos rejected/overridden =", dict(rej_ovr), "| jsonl lines =", len(jsonl), dict(Counter(j["human_decision"] for j in jsonl)), "| evaluation =", ev["decision_counts"], "example_count", ev["example_count"])
print("active-learning counts match:", dict(rej_ovr) == ev["decision_counts"] == dict(Counter(j["human_decision"] for j in jsonl)))
