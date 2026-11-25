"""One-off production resolve_outcomes run (approved item B). Usage: prod_resolve.py ROOT dry|write"""
import sys, json, hashlib, pathlib, datetime as dt
from intent_engine.market import outcome_resolver as OR, steps as ST
root = pathlib.Path(sys.argv[1]); mode = sys.argv[2]
audit = root / ST.AUDIT_FILE
h0 = hashlib.sha256(audit.read_bytes()).hexdigest()
rows = ST.read_audit(root)
today = dt.date.today().isoformat()
cache = {}
def fetch(sym):
    if sym not in cache: cache[sym] = ST._live_series(sym)
    return cache[sym]
r = OR.resolve(rows, root=root, today=today, series_fn=fetch, write=(mode == "write"))
h1 = hashlib.sha256(audit.read_bytes()).hexdigest()
by_state = {}
for e in r["events"]: by_state[e["state"]] = by_state.get(e["state"], 0) + 1
print(json.dumps({"mode": mode, "today": today, "audit_rows": len(rows),
  "counts": r["counts"], "would_append": r["would_append"], "appended": r["appended"],
  "events_by_state": by_state, "audit_unchanged": h0 == h1,
  "summary": OR.summarise(OR.read_outcomes(root) + (r["events"] if mode == "dry" else []))}, indent=1, default=str))
