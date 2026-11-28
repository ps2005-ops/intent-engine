"""What a run's independent family discovered, approved and read (store events)."""
import json, sys
store, company = sys.argv[1], sys.argv[2].lower()
rid = None
ev = [json.loads(l) for l in open(store)]
for d in ev:
    if d["event_type"] == "ci.run_created" and d["payload"].get("company_name", "").lower().startswith(company):
        rid = d["run_id"]
approved = set()
for d in ev:
    if d.get("run_id") == rid and d["event_type"] == "ci.approval_recorded":
        approved = set(d["payload"].get("approved_candidate_ids") or d["payload"].get("candidate_ids") or [])
        print("approval keys", list(d["payload"].keys()))
cands = {}
for d in ev:
    if d.get("run_id") != rid: continue
    p = d["payload"]
    if d["event_type"] == "ci.candidate_discovered":
        cands[p["candidate_id"]] = p
    if d["event_type"] in ("ci.source_retrieved", "ci.retrieval_failed") and p.get("candidate_id") in cands:
        cands[p["candidate_id"]]["_outcome"] = d["event_type"].split(".")[1] + ":" + str(p.get("failure_type") or "")
for cid, p in cands.items():
    if p.get("source_class") in ("independent_reporting", "customer_voice", "competitor"):
        print("A" if cid in approved else " ", p.get("source_class")[:12], p.get("discovery_method")[:16],
              p.get("relevance") or p.get("mention_relevance"), (p.get("url") or "")[:80], p.get("_outcome", ""))
print("approved total", len(approved), "classes", sorted({cands[c].get('source_class') for c in approved if c in cands}))
