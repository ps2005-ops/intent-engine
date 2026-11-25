"""RECONSTRUCTED historical evaluation (not a forward prediction): what baseline_momentum.v1
would have said at each resolved decision, using closes <= as_of only, graded on the
already-written signal_outcomes.jsonl. Prints decision-level and non-overlapping results."""
import json, random, sys, collections
from intent_engine.market import outcome_resolver as OR, steps as ST
from intent_engine.market.strategy_library import baseline_momentum
ROOT = "/Users/prathamsharma/intent-engine-market"
ev = [e for e in OR.latest_by_key(OR.read_outcomes(ROOT)).values() if e["state"] == "RESOLVED"]
dec = {}
for e in ev: dec.setdefault(tuple(e["decision_key"]), e)
dec = sorted(dec.values(), key=lambda e: (e["instrument"], e["as_of"]))
cache = {}
spy = ST._live_series("SPY")
def regime(as_of):
    s = [v for d, v in sorted(spy.items()) if d[:10] <= as_of]
    return "SPY_up63" if len(s) > 63 and s[-1] > s[-64] else "SPY_down63"
out = []
for e in dec:
    sym = e["instrument"]
    if sym not in cache: cache[sym] = ST._live_series(sym)
    closes = {d[:10]: v for d, v in cache[sym].items() if d[:10] <= e["as_of"]}
    sig = baseline_momentum(closes, security=sym, as_of=e["as_of"])
    out.append({"instrument": sym, "as_of": e["as_of"], "dir": sig.direction, "fired": sig.fired,
                "trailing": sig.value, "ret": e["realized_return"], "regime": regime(e["as_of"])})
json.dump(out, open(sys.argv[1], "w"), indent=0)
def hit(r): return (r["ret"] > 0) == (r["dir"] == "long")
def stats(rows, label):
    f = [r for r in rows if r["fired"]]
    h = sum(hit(r) for r in f)
    up = sum(r["ret"] > 0 for r in rows)
    print(f"{label:28s} decisions={len(rows):3d} fired={len(f):3d} hits={h:3d} "
          f"hit_rate={h/len(f) if f else float('nan'):.3f}  up_base_rate={up/len(rows) if rows else float('nan'):.3f}")
stats(out, "ALL (overlapping)")
# non-overlapping: per instrument, keep a decision only if >= 21 days after the last kept
import datetime as dt
no = []; last = {}
for r in out:
    d = dt.date.fromisoformat(r["as_of"])
    if r["instrument"] not in last or (d - last[r["instrument"]]).days >= 21:
        no.append(r); last[r["instrument"]] = d
stats(no, "NON-OVERLAPPING")
for k in sorted({r["instrument"] for r in out}): stats([r for r in out if r["instrument"] == k], f"  {k}")
for k in ("SPY_up63", "SPY_down63"): stats([r for r in out if r["regime"] == k], f"  regime {k}")
for k in ("long", "short"): stats([r for r in out if r["dir"] == k], f"  direction {k}")
# block bootstrap over instrument-months on fired hits
f = [r for r in out if r["fired"]]
blocks = collections.defaultdict(list)
for r in f: blocks[(r["instrument"], r["as_of"][:7])].append(hit(r))
keys = list(blocks); random.seed(0); bs = []
for _ in range(4000):
    s = [x for k in random.choices(keys, k=len(keys)) for x in blocks[k]]
    bs.append(sum(s) / len(s))
bs.sort(); print(f"block-bootstrap 95% CI on hit rate ({len(keys)} instrument-month blocks): {bs[100]:.3f}-{bs[3900]:.3f}")
