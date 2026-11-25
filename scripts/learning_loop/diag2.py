import pickle, sys, json, collections
import numpy as np
from intent_engine.paper_validation import model as MD, policies as PL, macro as M, universe as U
D = pickle.load(open(sys.argv[1], "rb")); rows = D["rows"]; bars = D["bars"]; spy = bars[U.BENCHMARK]
MAC = list(M.MACRO_NAMES); SPLIT = "2015-01-01"
def fp(tr, te, names, yk):
    X = MD.matrix([o.feats for o in tr], names); y = np.array([yk(o) for o in tr], float)
    m = MD.fit(X, y, names); return MD.predict(m, MD.matrix([o.feats for o in te], names)), m
# E6 horizon: 63-session target from the same entry, exit = entry + 63 sessions
def y63(o):
    b = bars[o.symbol]; ie = b.index_of(o.entry_date)
    if ie is None or ie + 63 >= len(b.dates): return None
    r = b.open_adj[ie + 63] / b.open_adj[ie] - 1
    if o.universe == U.COMPANY:
        si = spy.index_of(o.entry_date)
        if si is None or si + 63 >= len(spy.dates): return None
        r -= spy.open_adj[si + 63] / spy.open_adj[si] - 1
    else:
        r -= 3 * (o.rf or 0.0)
    return 1 if r > 0 else 0
exit63 = {}
for o in rows:
    b = bars[o.symbol]; ie = b.index_of(o.entry_date)
    exit63[id(o)] = b.dates[ie + 63] if ie is not None and ie + 63 < len(b.dates) else "9999"
print("E6 horizon 63 sessions (purged: train exits63 < split)")
for u, fam in sorted({(o.universe, o.family) for o in rows}):
    fr = [o for o in rows if o.universe == u and o.family == fam and not o.macro_missing and y63(o) is not None]
    tr = [o for o in fr if exit63[id(o)] < SPLIT]; te = [o for o in fr if o.decision_date >= SPLIT]
    if len(tr) < 40: continue
    A = list(PL.A_ETF if u == U.ETF else PL.A_CO); yte = np.array([y63(o) for o in te], float)
    pa, _ = fp(tr, te, A, y63); pb, _ = fp(tr, te, A + MAC, y63)
    base = np.full(len(te), np.mean([y63(o) for o in tr]))
    print(f"  {u}/{fam}: base {((base-yte)**2).mean():.4f} A {((pa-yte)**2).mean():.4f} B {((pb-yte)**2).mean():.4f} gain B-A {((pa-yte)**2).mean()-((pb-yte)**2).mean():+.4f}")
# E7 regime instability: univariate coefficient sign before vs after split, per family
print("\nE7 univariate coefficient (standardised) before 2015 vs from 2015")
for u, fam in (("etf", "equity_broad"), ("etf", "sector"), ("etf", "bond"), ("etf", "commodity")):
    fr = [o for o in rows if o.universe == u and o.family == fam and not o.macro_missing]
    a = [o for o in fr if o.exit_date < SPLIT]; b = [o for o in fr if o.decision_date >= SPLIT]
    flips = []
    for n in MAC:
        _, ma = fp(a, a[:1], [n], lambda o: o.y); _, mb = fp(b, b[:1], [n], lambda o: o.y)
        if np.sign(ma.weights[0]) != np.sign(mb.weights[0]) and max(abs(ma.weights[0]), abs(mb.weights[0])) > 0.05:
            flips.append(f"{n}({ma.weights[0]:+.2f}->{mb.weights[0]:+.2f})")
    print(f"  {u}/{fam}: {len(flips)} of {len(MAC)} flip sign: {', '.join(flips)}")
# E8 trace one example end to end
o = next(x for x in rows if x.universe == "etf" and x.family == "equity_broad" and x.decision_date >= "2022-03-01")
print("\nE8 trace", o.symbol, o.decision_date, "entry", o.entry_date, "exit", o.exit_date)
print("  macro evidence ids:", o.ev_macro[:6], "...")
print("  macro features:", {n: round(o.feats[n], 4) for n in MAC})
tr = [x for x in rows if x.universe == "etf" and x.family == "equity_broad" and x.exit_date < o.decision_date[:4] + "-01-01" and not x.macro_missing]
pa, ma = fp(tr, [o], list(PL.A_ETF), lambda x: x.y); pb, mb = fp(tr, [o], list(PL.A_ETF) + MAC, lambda x: x.y)
print(f"  trained on {len(tr)} rows; p(A)={pa[0]:.3f} p(B)={pb[0]:.3f}; realised excess {o.excess:+.4f} y={o.y}")
print("  B macro weights:", {n: round(w, 3) for n, w in zip(mb.feature_names, mb.weights) if n in MAC})
