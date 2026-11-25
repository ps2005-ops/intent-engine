"""PHASE 2 controlled diagnostics of the negative macro ablation. POST-HOC; nothing feeds a policy.
Split: train on outcomes known before 2015-01-01, test on decisions from 2015-01-01 (the replay's diagnostic split).
Uncertainty: block bootstrap over decision dates (rows on one date are one block)."""
import pickle, sys, json, collections
import numpy as np
from intent_engine.paper_validation import model as MD, policies as PL, macro as M, universe as U, features as F
D = pickle.load(open(sys.argv[1], "rb")); rows = D["rows"]; bars = D["bars"]
SPLIT = "2015-01-01"; MAC = list(M.MACRO_NAMES); rng0 = np.random.default_rng(0)
fams = sorted({(o.universe, o.family) for o in rows})
def A_of(u): return list(PL.A_ETF if u == U.ETF else PL.A_CO)
def brier(p, y): return float(((p - y) ** 2).mean())
def boot(diff_by_date, n=2000):
    k = list(diff_by_date); v = np.array([diff_by_date[x] for x in k]); w = np.array([1.0]*len(k))
    r = np.random.default_rng(1); s = []
    for _ in range(n):
        i = r.integers(0, len(k), len(k)); s.append(v[i].mean())
    s.sort(); return float(v.mean()), float(s[int(.025*n)]), float(s[int(.975*n)])
def fitpred(tr, te, names, featfn=None):
    f = featfn or (lambda o: o.feats)
    X = MD.matrix([f(o) for o in tr], names); y = np.array([o.y for o in tr], float)
    m = MD.fit(X, y, names); return MD.predict(m, MD.matrix([f(o) for o in te], names))
def split(u, fam):
    fr = [o for o in rows if o.universe == u and o.family == fam and not o.macro_missing]
    return [o for o in fr if o.exit_date < SPLIT], [o for o in fr if o.decision_date >= SPLIT]
def per_date_gain(te, pa, pb):
    """mean over dates of (Brier_A - Brier_B); positive = B better."""
    g = collections.defaultdict(list)
    for o, a, b in zip(te, pa, pb): g[o.decision_date].append((a - o.y) ** 2 - (b - o.y) ** 2)
    return {d: float(np.mean(v)) for d, v in g.items()}
out = {}
for u, fam in fams:
    tr, te = split(u, fam)
    if len(tr) < 40 or not te: continue
    A = A_of(u); B = A + MAC; yte = np.array([o.y for o in te], float)
    cell = {"n_train_rows": len(tr), "n_train_dates": len({o.decision_date for o in tr}),
            "n_test_rows": len(te), "n_test_dates": len({o.decision_date for o in te}),
            "instruments": len({o.symbol for o in tr})}
    # E1 effective sample + collinearity of the date-level macro block
    md = {}
    for o in tr: md[o.decision_date] = [o.feats[n] for n in MAC]
    Xm = np.array(list(md.values())); Z = (Xm - Xm.mean(0)) / np.where(Xm.std(0) == 0, 1, Xm.std(0))
    ev = np.linalg.eigvalsh(np.corrcoef(Z.T)); cell["macro_dates_per_param"] = round(len(md) / len(MAC), 1)
    cell["macro_condition_number"] = round(float(np.sqrt(ev.max() / max(ev.min(), 1e-12))), 1)
    pa = fitpred(tr, te, A); pb = fitpred(tr, te, B)
    cell["brier_A"] = round(brier(pa, yte), 5); cell["brier_B"] = round(brier(pb, yte), 5)
    cell["B_minus_A_gain"] = [round(x, 5) for x in boot(per_date_gain(te, pa, pb))]
    # E2 placebo: macro vectors reassigned across dates (same for all instruments on a date)
    alld = sorted({o.decision_date for o in tr + te}); gains = []
    for seed in range(10):
        r = np.random.default_rng(seed); perm = dict(zip(alld, r.permutation(alld)))
        mac_by_date = {}
        for o in tr + te: mac_by_date.setdefault(o.decision_date, {n: o.feats[n] for n in MAC})
        f = lambda o, pm=perm: {**o.feats, **mac_by_date[pm[o.decision_date]]}
        pp = fitpred(tr, te, B, f); gains.append(brier(pa, yte) - brier(pp, yte))
    cell["placebo_B_gain_mean_10seeds"] = round(float(np.mean(gains)), 5)
    cell["placebo_B_gain_range"] = [round(min(gains), 5), round(max(gains), 5)]
    # E3 univariate information of each macro feature (alone + intercept), out of sample
    base = float(np.array([o.y for o in tr]).mean()); bb = brier(np.full(len(te), base), yte)
    uni = {}
    for n in MAC:
        p1 = fitpred(tr, te, [n]); uni[n] = round(bb - brier(p1, yte), 5)
    cell["univariate_gain_vs_base_rate"] = uni
    cell["base_rate_brier"] = round(bb, 5)
    # E4 staleness: macro lagged one decision date (~21 sessions)
    prev = {d: alld[i - 1] for i, d in enumerate(alld) if i}
    mac_by_date = {}
    for o in tr + te: mac_by_date.setdefault(o.decision_date, {n: o.feats[n] for n in MAC})
    tr4 = [o for o in tr if o.decision_date in prev]; te4 = [o for o in te if o.decision_date in prev]
    f4 = lambda o: {**o.feats, **mac_by_date[prev[o.decision_date]]}
    p4 = fitpred(tr4, te4, B, f4); pa4 = fitpred(tr4, te4, A); y4 = np.array([o.y for o in te4], float)
    cell["stale_macro_B_gain"] = round(brier(pa4, y4) - brier(p4, y4), 5)
    # E5 exposure mapping (companies): macro x beta252 interactions instead of raw macro
    if u == U.COMPANY:
        IX = [f"{n}*beta" for n in MAC]
        f5 = lambda o: {**o.feats, **{f"{n}*beta": o.feats[n] * o.feats["beta252"] for n in MAC}}
        p5 = fitpred(tr, te, A + IX, f5)
        cell["exposure_macroXbeta_gain"] = [round(x, 5) for x in boot(per_date_gain(te, pa, p5))]
    out[f"{u}/{fam}"] = cell
json.dump(out, open(sys.argv[2], "w"), indent=1)
for k, c in out.items():
    print(f"\n{k}: train {c['n_train_rows']} rows / {c['n_train_dates']} dates / {c['instruments']} instruments; "
          f"macro dates per parameter {c['macro_dates_per_param']}, condition number {c['macro_condition_number']}")
    print(f"  Brier A {c['brier_A']}  B {c['brier_B']}  B-vs-A gain {c['B_minus_A_gain']} (mean, 95% CI; + = macro helps)")
    print(f"  placebo (macro from a random other date) gain {c['placebo_B_gain_mean_10seeds']} range {c['placebo_B_gain_range']}")
    print(f"  stale macro (one date late) gain {c['stale_macro_B_gain']}")
    best = sorted(c['univariate_gain_vs_base_rate'].items(), key=lambda x: -x[1])
    print(f"  univariate vs base rate {c['base_rate_brier']}: best {best[:3]} worst {best[-2:]}")
    if "exposure_macroXbeta_gain" in c: print(f"  exposure mapping macro x beta gain {c['exposure_macroXbeta_gain']}")
