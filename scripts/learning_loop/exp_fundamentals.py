"""PHASE 4/9 bounded experiment: company-specific, point-in-time fundamentals (SEC XBRL, walled on `filed`)
vs the price-only reference, on matched rows. Dev <2015 | validation 2015-2020 | holdout 2021+ (run once).
Consensus expectations are UNAVAILABLE historically; 'acceleration' is change vs the company's own trajectory."""
import json, pickle, sys, collections, datetime as dt
import numpy as np
from intent_engine.paper_validation import model as MD, policies as PL, universe as U
D = pickle.load(open(sys.argv[1], "rb")); XB = sys.argv[2]
rows = [o for o in D["rows"] if o.universe == U.COMPANY]
REV = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
       "RevenuesNetOfInterestExpense", "RevenueFromContractWithCustomerIncludingAssessedTax")
CAPEX = ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets")
d_ = dt.date.fromisoformat
def facts(sym, concepts, quarterly):
    j = json.load(open(f"{XB}/{sym}.json")); g = j.get("facts", {}).get("us-gaap", {}); out = []
    for c in concepts:
        for unit, vals in (g.get(c, {}).get("units", {}) or {}).items():
            if unit != "USD": continue
            for v in vals:
                if "start" not in v or v.get("form") not in ("10-Q", "10-K", "10-Q/A", "10-K/A"): continue
                dur = (d_(v["end"]) - d_(v["start"])).days
                if (quarterly and 80 <= dur <= 100) or (not quarterly and 350 <= dur <= 380):
                    out.append((v["end"], v["filed"], float(v["val"])))
    return out
def asof(fs, d):
    """latest-filed value per period end, among facts filed strictly before d"""
    best = {}
    for end, filed, val in fs:
        if filed < d and (end not in best or filed >= best[end][0]): best[end] = (filed, val)
    return sorted((e, f, v) for e, (f, v) in best.items())
def yoy(series, i):
    e, _, v = series[i]
    for e2, _, v2 in series[:i][::-1]:
        gap = (d_(e) - d_(e2)).days
        if 350 <= gap <= 380: return v / v2 - 1 if v2 > 0 else None
    return None
cache = {}
def feats(sym, d):
    if sym not in cache: cache[sym] = (facts(sym, REV, True), facts(sym, CAPEX, False))
    rq, cf = cache[sym]
    s = asof(rq, d)
    if len(s) < 6: return None
    g0, g1 = yoy(s, len(s) - 1), yoy(s, len(s) - 2)
    if g0 is None or g1 is None: return None
    c = asof(cf, d); cy = None
    if len(c) >= 2 and c[-2][2] > 0 and 350 <= (d_(c[-1][0]) - d_(c[-2][0])).days <= 380: cy = c[-1][2] / c[-2][2] - 1
    fresh = 1.0 if (d_(d) - d_(s[-1][1])).days <= 30 else 0.0
    clip = lambda x: max(-1.0, min(1.0, x))
    return {"rev_yoy": clip(g0), "rev_accel": clip(g0 - g1), "capex_yoy": clip(cy) if cy is not None else 0.0,
            "capex_known": 1.0 if cy is not None else 0.0, "fresh": fresh, "fresh_x_accel": fresh * clip(g0 - g1)}
F_E = ["rev_yoy", "rev_accel", "capex_yoy", "capex_known", "fresh", "fresh_x_accel"]
M = []
for o in rows:
    f = feats(o.symbol, o.decision_date)
    if f: o.fund = f; M.append(o)
print(f"company rows {len(rows)}, with point-in-time fundamentals {len(M)} "
      f"({len({o.symbol for o in M})} companies, first {min(o.decision_date for o in M)})")
A = list(PL.A_CO); E = A + F_E
def mat(rs, names, shuf=None): return MD.matrix([{**o.feats, **(shuf.get(id(o), o.fund) if shuf else o.fund)} for o in rs], names)
def run(tr, te, label):
    ytr = np.array([o.y for o in tr], float); yte = np.array([o.y for o in te], float)
    ma = MD.fit(mat(tr, A), ytr, A); me = MD.fit(mat(tr, E), ytr, E)
    pa = MD.predict(ma, mat(te, A)); pe = MD.predict(me, mat(te, E)); base = np.full(len(te), ytr.mean())
    g = collections.defaultdict(list)
    for o, a, e in zip(te, pa, pe): g[o.decision_date].append((a - o.y) ** 2 - (e - o.y) ** 2)
    v = np.array([np.mean(x) for x in g.values()]); r = np.random.default_rng(3)
    bs = sorted(v[r.integers(0, len(v), len(v))].mean() for _ in range(3000))
    # placebo: fundamentals shuffled across companies within each date
    by = collections.defaultdict(list)
    for o in tr + te: by[o.decision_date].append(o)
    pg = []
    for seed in range(10):
        rr = np.random.default_rng(seed); sh = {}
        for d, os_ in by.items():
            p = rr.permutation(len(os_))
            for o, k in zip(os_, p): sh[id(o)] = os_[k].fund
        mp = MD.fit(mat(tr, E, sh), ytr, E); pp = MD.predict(mp, mat(te, E, sh))
        pg.append(float(((pa - yte) ** 2).mean() - ((pp - yte) ** 2).mean()))
    w = dict(zip(me.feature_names, me.weights))
    print(f"{label}: train {len(tr)} rows/{len({o.decision_date for o in tr})} dates, test {len(te)} rows/{len(g)} dates")
    print(f"   Brier base {((base-yte)**2).mean():.5f}  A {((pa-yte)**2).mean():.5f}  A+fundamentals {((pe-yte)**2).mean():.5f}")
    print(f"   gain (A - E), + = fundamentals help: {v.mean():+.5f}  95% CI [{bs[75]:+.5f}, {bs[2925]:+.5f}]")
    print(f"   placebo (shuffled across companies) gain mean {np.mean(pg):+.5f} range [{min(pg):+.5f}, {max(pg):+.5f}]")
    print("   standardized weights:", {k: round(w[k], 3) for k in F_E})
    return v.mean(), (bs[75], bs[2925])
dev = [o for o in M if o.exit_date < "2015-01-01"]
val = [o for o in M if "2015-01-01" <= o.decision_date < "2021-01-01"]
hold = [o for o in M if o.decision_date >= "2021-01-01"]
run(dev, val, "VALIDATION 2015-2020 (fit on <2015)")
print("\n--- HOLDOUT, run once; fit on everything that exited before 2021 ---")
run([o for o in M if o.exit_date < "2021-01-01"], hold, "HOLDOUT 2021-2026")
