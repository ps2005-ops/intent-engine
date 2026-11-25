"""Phase 3: event-level audit of every historical expectation grade (read-only).
Writes the audit and PROPOSED append-only invalidation events; never touches the ledger."""
import json, re, sys, collections, datetime as dt
from intent_engine.market import demand_reading as DR
LED = "/Users/prathamsharma/intent-engine-market/reports/market/learning_ledger.jsonl"
recs = [json.loads(l) for l in open(LED)]
ev = {}
for r in recs:
    if r.get("record") == "evidence": ev.setdefault(r["evidence_id"], r)
exp = {r["expectation_id"]: r for r in recs if r.get("record") == "expectation"}
grades = collections.OrderedDict()
for r in recs:
    if r.get("record") == "reconciliation": grades.setdefault(r["expectation_id"], r)
_P = re.compile(r"\b(?:Q([1-4])|(first|second|third|fourth)[- ]quarter)\b[^0-9]{0,12}((?:19|20)\d\d)?|\bfy\s?((?:19|20)\d\d)\b", re.I)
_W = {"first": "1", "second": "2", "third": "3", "fourth": "4"}
def period(text):
    m = _P.search(text or "")
    if not m: return None
    q = m.group(1) or _W.get((m.group(2) or "").lower())
    return f"Q{q} {m.group(3) or ''}".strip() if q else f"FY{m.group(4)}"
d_ = lambda s: dt.date.fromisoformat(s[:10])
by_subject = collections.defaultdict(list)
for e in ev.values(): by_subject[e.get("subject_company") or e.get("actor")].append(e)
out = []; props = []
for xid, g in grades.items():
    x = exp.get(xid, {}); b = [ev[i] for i in x.get("evidence_basis", []) if i in ev]
    gd = [ev[i] for i in g.get("evidence_ids", []) if i in ev]
    if not b or not gd:
        out.append({"expectation_id": xid, "subject": g["subject"], "verdict": "UNAUDITABLE", "why": "evidence text missing"}); continue
    B, G = b[0], gd[0]; pb, pg = period(B["fact"]), period(G["fact"])
    gap = (d_(G["observed_at"]) - d_(B["observed_at"])).days
    same = (pb is not None and pb == pg) or gap < DR.MIN_PERIOD_GAP_DAYS
    later = [e for e in by_subject.get(B.get("subject_company") or B.get("actor"), [])
             if e["evidence_type"] in ("EARNINGS_RESULT", "GUIDANCE_REVISION", "EARNINGS_SURPRISE")
             and (d_(e["observed_at"]) - d_(B["observed_at"])).days >= DR.MIN_PERIOD_GAP_DAYS
             and (period(e["fact"]) is None or period(e["fact"]) != pb)]
    rd_b = DR.read(B["fact"]).family
    row = {"expectation_id": xid, "subject": g["subject"], "metric": x.get("metric"),
           "expected": x.get("expected_direction"), "original_grade": g["outcome"],
           "basis": {"date": B["observed_at"], "period": pb, "fact": B["fact"][:140], "v2_reading": rd_b},
           "grading": {"date": G["observed_at"], "period": pg, "fact": G["fact"][:140]},
           "gap_days": gap, "same_event": same,
           "later_period_candidates": [{"date": e["observed_at"], "fact": e["fact"][:110]} for e in sorted(later, key=lambda e: e["observed_at"])[:3]],
           "window_ends": x.get("evaluation_window_ends")}
    if not same:
        row["verdict"] = "VALID_LATER_PERIOD"
    else:
        row["verdict"] = "INVALID_SAME_EVENT"
        row["status_after_invalidation"] = ("REGRADE_CANDIDATE_NEEDS_REVIEW" if later else
                                            f"OPEN_AWAITING_NEXT_REPORT (window to {x.get('evaluation_window_ends')})")
        props.append({"contract": "expectation_grade_invalidation.v1", "record": "grade_invalidation",
                      "expectation_id": xid, "invalidates": {"outcome": g["outcome"], "evaluated_at": g["evaluated_at"],
                                                             "evidence_ids": g["evidence_ids"]},
                      "reason": f"grading evidence describes the same event as the basis (period {pb or '?'} vs {pg or '?'}, {gap} days apart); the falsifier names the NEXT reported figure",
                      "restores_state": "OPEN", "processed_on": "(on approval)"})
    out.append(row)
json.dump(out, open(sys.argv[1], "w"), indent=1)
open(sys.argv[2], "w").write("".join(json.dumps(p, sort_keys=True) + "\n" for p in props))
c = collections.Counter((r.get("metric"), r["verdict"], r.get("original_grade")) for r in out)
for k, v in sorted(c.items(), key=str): print(k, v)
valid = [r for r in out if r["verdict"] == "VALID_LATER_PERIOD"]
print("\nVALID grades by mechanism:", dict(collections.Counter((r["metric"], r["original_grade"]) for r in valid)))
print("invalid -> status:", dict(collections.Counter(r.get("status_after_invalidation", "")[:30] for r in out if r["verdict"] == "INVALID_SAME_EVENT")))
print("v2 reading of the basis of VALID grades:", dict(collections.Counter((r["metric"], r["basis"]["v2_reading"], r["original_grade"]) for r in valid)))
