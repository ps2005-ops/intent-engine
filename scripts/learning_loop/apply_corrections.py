"""Append the approved grade invalidations and OLO corrections to production, under the
market cycle lock, idempotently. Never rewrites a line. Usage: apply_corrections.py ROOT"""
import json, sys, pathlib, datetime as dt
from intent_engine.runtime.locks import JobLock
from intent_engine.market import cycle as C, outcome_resolver as OR, learning_store as LS
root = pathlib.Path(sys.argv[1]); today = dt.date.today().isoformat()
inv = [json.loads(l) for l in open("reports/learning_loop/APPLIED_grade_invalidations_2026-11-25.jsonl")]
olo = [json.loads(l) for l in open("reports/learning_loop/PROPOSED_olo_ineligible_corrections.jsonl")]
with JobLock(C.LOCK_NAME, root=root):
    led = root / LS.DEFAULT_PATH
    raw = [json.loads(l) for l in led.read_text().splitlines() if l.strip()]
    done = {r["expectation_id"] for r in raw if r.get("record") == LS.GRADE_INVALIDATION}
    new_inv = [dict(r, processed_on=today) for r in inv if r["expectation_id"] not in done]
    with open(led, "a") as fh:
        for r in new_inv: fh.write(json.dumps(r, sort_keys=True) + "\n")
    out = root / OR.OUTCOMES_FILE
    cur = OR.latest_by_key(OR.read_outcomes(root))
    new_olo = []
    for c in olo:
        p = cur.get(c["record_key"])
        if p and p.get("state") == OR.UNRESOLVABLE and c["corrects_state"] == OR.UNRESOLVABLE:
            new_olo.append(dict(c, processed_on=today))
    with open(out, "a") as fh:
        for r in new_olo: fh.write(json.dumps(r, sort_keys=True) + "\n")
print(json.dumps({"grade_invalidations_appended": len(new_inv), "already_applied": len(done),
                  "olo_corrections_appended": len(new_olo)}))
