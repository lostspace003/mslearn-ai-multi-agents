"""Optional challenge: reviewer band + replay of the same decision event after a simulated timeout."""
import json, uuid
from pathlib import Path
from src.main import create_workflow
from src.workflow import utc_now
wf = create_workflow()
for path in ["assets/refund-request.json", "assets/refund-request-lowband.json"]:
    item = wf.submit(json.loads(Path(path).read_text()))
    r = item["risk"]
    print(f"{path}: id={item['id']} state={item['state']} calibrated={r['calibrated_confidence']} required={r['required_confidence']} band={r['review_band']} threshold={r['band_threshold']} group={r['reviewer_group']}")
low = item
event = {"event_id": str(uuid.uuid4()), "workflow_id": low["id"], "decision": "APPROVED", "reviewer": "SYN-REVIEW-SENIOR-01",
         "comment": "Senior band approval", "category": "within_authority", "reviewed_at": utc_now()}
audit = wf._audit
count = lambda: len(list(audit.query_items("SELECT c.id FROM c WHERE c.workflow_id=@w", parameters=[{"name":"@w","value":low["id"]}], partition_key=low["id"])))
first = wf.apply_decision(event)
print("first apply:", first["state"], "executed_at=", first["execution"]["executed_at"], "audit records=", count())
# Simulated timeout: worker crashed before completing the message, so the SAME event is redelivered.
second = wf.apply_decision(event)
after = wf.get(low["id"])
print("replay of same event:", second, "| executed_at unchanged:", after["execution"]["executed_at"] == first["execution"]["executed_at"],
      "| version:", after["version"], "| audit records=", count())
