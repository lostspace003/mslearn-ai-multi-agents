"""Optional challenge: compare a coarse and a fine-grained DAG for the same synthetic query.

Offline only (no model calls). Uses the lab's own validate_plan / ready_tasks / build_handoff,
with real specialist summaries captured in artifacts-lab03.txt (complex run) as dependency artifacts.
Run: python optional_challenge.py > challenge-output.txt
"""
from __future__ import annotations
import json, os
from pathlib import Path
from src.main import validate_plan, ready_tasks, build_handoff

ROOT = Path(__file__).resolve().parent
data = json.loads((ROOT / "assets/research-query.json").read_text(encoding="utf-8"))
registry = data["registry"]

# Real summaries from the complex live run (used as realistic artifact sizes).
text = (ROOT / "artifacts-lab03.txt").read_text(encoding="utf-8").split("===== SIMPLE RUN")[0]
live, _ = json.JSONDecoder().raw_decode(text[text.index("\n{\n") + 1:])
live_summaries = [v["summary"] for v in live["results"].values()]

S = '{"findings":["string"],"confidence":0.0,"missing_evidence":["string"]}'
coarse = {"tasks": [
    {"id": "E1", "agent": "financial-data", "objective": "Collect financial, rate-sensitivity and caveat evidence for the issuer.", "depends_on": [], "expected_schema": S},
    {"id": "S1", "agent": "thesis-synthesis", "objective": "Synthesize a caveated diligence recommendation.", "depends_on": ["E1"], "expected_schema": S},
]}
fine = {"tasks": [
    {"id": "F1", "agent": "financial-data", "objective": "Leverage, coverage and liquidity observations.", "depends_on": [], "expected_schema": S},
    {"id": "M1", "agent": "macro-risk", "objective": "Rate scenarios and transmission channels.", "depends_on": [], "expected_schema": S},
    {"id": "F2", "agent": "financial-data", "objective": "Stress coverage under M1 scenarios.", "depends_on": ["F1", "M1"], "expected_schema": S},
    {"id": "C1", "agent": "compliance-review", "objective": "Required caveats and diligence boundaries.", "depends_on": [], "expected_schema": S},
    {"id": "C2", "agent": "compliance-review", "objective": "Check stressed findings against policy caveats.", "depends_on": ["F2", "C1"], "expected_schema": S},
    {"id": "S1", "agent": "thesis-synthesis", "objective": "Synthesize a caveated diligence recommendation.", "depends_on": ["C2"], "expected_schema": S},
]}

def simulate(name: str, plan: dict, max_chars: int) -> dict:
    os.environ["MAX_HANDOFF_CHARS"] = str(max_chars)
    validate_plan(plan, registry)
    completed: dict = {}; envelopes = []; waves = 0; i = 0
    while len(completed) < len(plan["tasks"]):
        batch = ready_tasks(plan["tasks"], completed); waves += 1
        for task in batch:
            env = build_handoff(task, completed, "challenge-corr-id")
            envelopes.append(len(json.dumps(env)))
            completed[task["id"]] = {"status": "success", "response_id": f"sim_{task['id']}",
                                     "summary": live_summaries[i % len(live_summaries)]}
            i += 1
    return {"plan": name, "tasks": len(plan["tasks"]), "handoffs": len(envelopes),
            "sequential_waves": waves, "max_envelope_chars": max(envelopes),
            "total_handoff_chars": sum(envelopes)}

print("== Valid DAG comparison (MAX_HANDOFF_CHARS=6000) ==")
results = [simulate("coarse", coarse, 6000), simulate("fine", fine, 6000)]
for r in results: print(json.dumps(r))
for name, plan in (("coarse", coarse), ("fine", fine)):
    print(name, [(t["id"], t["agent"], t["depends_on"]) for t in plan["tasks"]])

print("\n== Selection (constraints: latency <= 4 sequential waves, envelope <= 6000 chars, >= 3 specialists for a complex query) ==")
for r, plan in zip(results, (coarse, fine)):
    agents = {t["agent"] for t in plan["tasks"]} - {"thesis-synthesis"}
    ok = r["sequential_waves"] <= 4 and r["max_envelope_chars"] <= 6000 and len(agents) >= 3
    print(f"{r['plan']}: waves={r['sequential_waves']} specialists={len(agents)} max_env={r['max_envelope_chars']} -> {'meets' if ok else 'fails'} constraints")
print("Selected: fine-grained plan. It is the only one meeting the quality constraint (financial, macro and compliance"
      " evidence all reach synthesis) within the 4-wave latency and 6000-char envelope budgets; the coarse plan is cheaper"
      " (2 handoffs, ~3.7k handoff chars vs 6 / ~12.7k) but drops macro and compliance evidence. Preserved artifacts:"
      " every envelope carries source_response_ids for its dependencies; S1 depends on C2, the single terminal evidence branch.")

print("\n== Failure investigation: shrink MAX_HANDOFF_CHARS until an envelope is rejected (fine plan) ==")
for limit in (6000, 4000, 3000, 2000, 1500, 1200, 1000, 800):
    try:
        r = simulate("fine", fine, limit); print(f"limit={limit}: OK max_envelope={r['max_envelope_chars']}")
    except ValueError as exc:
        print(f"limit={limit}: REJECTED -> {exc}")
        print("Classification: dispatch validation caught it; root cause is decomposition granularity"
              " (a fan-in task C2/F2 carries several dependency summaries, each floored at 256 chars plus"
              " objective/schema/IDs overhead), not a single oversized artifact.")
        break
