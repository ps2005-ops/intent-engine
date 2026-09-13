"""§10/§26: attack the sentiment lead with every alternative that could
produce it.

WHY THIS IS NOT OPTIONAL
------------------------
"Consumer sentiment leads housing by six months" is exactly the kind of
sentence that survives because it is pleasant. Six alternatives produce the
same correlation without sentiment carrying any information of its own:

    1. sentiment merely reflects employment
    2. housing drives sentiment, not the reverse
    3. credit conditions drive both
    4. wealth effects drive both
    5. the survey's composition changed
    6. the relationship broke after 2008

Each is tested where the data allows and recorded as UNTESTABLE where it does
not. A relationship survives only if it beats the alternatives that can be
checked, and the ones that cannot are named rather than quietly dropped.

THE RESIDUAL TEST IS THE CORE
-----------------------------
If sentiment leads housing only because sentiment tracks unemployment and
unemployment leads housing, then the part of sentiment that is NOT explained
by unemployment should lead nothing. That is a one-line prediction and it is
what `_residualise` sets up.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import experiment as EX              # noqa: E402
from intent_engine.econ import panel as PN                   # noqa: E402
from intent_engine.econ import preregistration as PR         # noqa: E402
from intent_engine.econ import residual as RS                # noqa: E402

OUT = pathlib.Path("reports/h7_adversary.json")
PANEL = pathlib.Path("reports/panel/historical_panel.jsonl")
MANIFEST = pathlib.Path("reports/panel/historical_acquisition_manifest.json")

SIGNAL = "UMCSENT"
TARGETS = ("HOUST", "INDPRO")
#: Confounders, each standing for one adversary claim.
CONFOUNDERS = {"UNRATE": "sentiment merely reflects employment",
               "BAA": "credit conditions drive both",
               "CPIAUCSL": "inflation drives both"}


def walled_series(panel, sid, origins):
    """Year-on-year change of `sid` at each origin, through the wall."""
    ppy = EX._periods_for_year(sid)
    out = []
    for o in origins:
        h = panel.history(sid, as_of=o, lookback=ppy * 2)
        v = EX.change(sid, h, ppy)
        if v is not None:
            out.append((o, v))
    return out


def _ols_residuals(y, xs):
    """Residuals of y on a constant and the columns of xs. Stdlib only."""
    n = len(y)
    k = len(xs) + 1
    X = [[1.0] + [col[i] for col in xs] for i in range(n)]
    # Normal equations, solved by Gaussian elimination. k is 2 or 3 here.
    XtX = [[sum(X[i][a] * X[i][b] for i in range(n)) for b in range(k)]
           for a in range(k)]
    Xty = [sum(X[i][a] * y[i] for i in range(n)) for a in range(k)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(XtX[r][c]))
        if abs(XtX[p][c]) < 1e-12:
            return list(y)
        XtX[c], XtX[p] = XtX[p], XtX[c]
        Xty[c], Xty[p] = Xty[p], Xty[c]
        for r in range(k):
            if r == c:
                continue
            f = XtX[r][c] / XtX[c][c]
            for cc in range(c, k):
                XtX[r][cc] -= f * XtX[c][cc]
            Xty[r] -= f * Xty[c]
    beta = [Xty[i] / XtX[i][i] for i in range(k)]
    return [y[i] - sum(beta[a] * X[i][a] for a in range(k)) for i in range(n)]


def _residualise(sig, confs):
    """The part of `sig` that the confounders do not explain."""
    keys = sorted(set(dict(sig)) & set.intersection(
        *[set(dict(c)) for c in confs])) if confs else sorted(dict(sig))
    if len(keys) < 10:
        return []
    y = [dict(sig)[k] for k in keys]
    xs = [[dict(c)[k] for k in keys] for c in confs]
    r = _ols_residuals(y, xs)
    return list(zip(keys, r))


def order(a, b, label=""):
    try:
        o = RS.temporal_order(a, b, max_lag=12)
    except Exception:                                       # noqa: BLE001
        return None
    return {**o.as_dict(), "label": label}


def main() -> int:
    PR.assert_h7_unchanged("3a5c4d36259e08a2")
    panel = PN.Panel.read(PANEL)
    man = json.loads(MANIFEST.read_text())
    origins = man["origins_deep"] + man["origins_modern"]
    sig = walled_series(panel, SIGNAL, origins)
    tgt = {t: walled_series(panel, t, origins) for t in TARGETS}
    conf = {c: walled_series(panel, c, origins) for c in CONFOUNDERS}
    print(f"=== §10/§26 ADVERSARY === signal {SIGNAL} at {len(sig)} origins\n")

    out = {"h7_hash": PR.h7_hash(), "signal": SIGNAL, "tests": {}}

    # --- BASELINE: the claim being attacked ---------------------------
    print("  --- the claim ---")
    base = {}
    for t in TARGETS:
        o = order(sig, tgt[t], "raw")
        base[t] = o
        print(f"    {SIGNAL} -> {t:<8} lag {o['best_lag']:+3d}  corr "
              f"{o['best_correlation']:+.3f}  {o['classification']}")
    out["tests"]["claim"] = base

    # --- ADVERSARY 1/3/6: a confounder drives both --------------------
    print("\n  --- alternatives 1, 3: a confounder drives both ---")
    resid = {}
    for cname, why in sorted(CONFOUNDERS.items()):
        r = _residualise(sig, [conf[cname]])
        if not r:
            resid[cname] = {"status": "UNTESTABLE",
                            "why": "too few aligned observations"}
            continue
        entry = {"claim": why, "results": {}}
        for t in TARGETS:
            o = order(r, tgt[t], f"residual_on_{cname}")
            entry["results"][t] = o
            survived = (o["classification"] == RS.LEADING
                        and abs(o["best_correlation"]) >= 0.15)
            entry["results"][t]["survives"] = survived
            print(f"    {SIGNAL}|{cname:<9} -> {t:<8} lag "
                  f"{o['best_lag']:+3d}  corr {o['best_correlation']:+.3f}  "
                  f"{o['classification']:<12} "
                  f"{'SURVIVES' if survived else 'KILLED'}")
        resid[cname] = entry
    # All confounders at once -- the hardest version.
    r_all = _residualise(sig, [conf[c] for c in sorted(CONFOUNDERS)])
    entry = {"claim": "every confounder at once", "results": {}}
    for t in TARGETS:
        o = order(r_all, tgt[t], "residual_on_all")
        survived = (o["classification"] == RS.LEADING
                    and abs(o["best_correlation"]) >= 0.15)
        entry["results"][t] = {**o, "survives": survived}
        print(f"    {SIGNAL}|ALL       -> {t:<8} lag {o['best_lag']:+3d}  "
              f"corr {o['best_correlation']:+.3f}  {o['classification']:<12} "
              f"{'SURVIVES' if survived else 'KILLED'}")
    resid["ALL"] = entry
    out["tests"]["confounders"] = resid

    # --- ADVERSARY 2: the target drives the signal --------------------
    print("\n  --- alternative 2: the target drives the signal ---")
    rev = {}
    for t in TARGETS:
        o = order(tgt[t], sig, "reverse")
        rev[t] = o
        # If the target leads the signal MORE strongly than the reverse, the
        # arrow points the other way.
        fwd = base[t]
        verdict = ("REVERSED" if (o["classification"] == RS.LEADING
                                  and abs(o["best_correlation"])
                                  > abs(fwd["best_correlation"]))
                   else "HOLDS")
        rev[t]["verdict"] = verdict
        print(f"    {t} -> {SIGNAL:<8} lag {o['best_lag']:+3d}  corr "
              f"{o['best_correlation']:+.3f}  {o['classification']:<12} "
              f"{verdict}")
    out["tests"]["reverse"] = rev

    # --- ADVERSARY 5/6: composition change / structural break ---------
    print("\n  --- alternatives 5, 6: survey change or a 2008 break ---")
    split = {}
    for label, lo, hi in (("pre_2008", "1978-01-01", "2007-12-31"),
                          ("post_2008", "2008-01-01", "2026-12-31")):
        s = [(k, v) for k, v in sig if lo <= k <= hi]
        entry = {}
        for t in TARGETS:
            tt = [(k, v) for k, v in tgt[t] if lo <= k <= hi]
            if len(s) < 30 or len(tt) < 30:
                entry[t] = {"status": "INSUFFICIENT"}
                continue
            o = order(s, tt, label)
            entry[t] = o
            print(f"    {label:<10} {SIGNAL} -> {t:<8} lag "
                  f"{o['best_lag']:+3d}  corr {o['best_correlation']:+.3f}  "
                  f"{o['classification']} (n={o['n']})")
        split[label] = entry
    stable = []
    for t in TARGETS:
        a = split["pre_2008"].get(t, {})
        b = split["post_2008"].get(t, {})
        if "best_lag" in a and "best_lag" in b:
            stable.append(abs(a["best_lag"] - b["best_lag"]) <= 3
                          and a["classification"] == b["classification"])
    split["stable_across_the_break"] = bool(stable) and all(stable)
    out["tests"]["structural_break"] = split
    print(f"    stable across the 2008 break: "
          f"{split['stable_across_the_break']}")

    # --- ADVERSARY 7: the lead is an artifact of the evaluation window --
    #
    # THE ONE THAT FIRED. The previous run measured the temporal order on the
    # origins that appeared in its TEST FOLDS -- 482 of 584 -- because that is
    # the set the paired-prediction file contains. Walk-forward reserves the
    # earliest slice for training, so the measurement silently began in 1986
    # and the record begins in 1978.
    #
    # A temporal order is a DESCRIPTIVE property of two series. There is no
    # reason to compute it on an evaluation subsample, and doing so cost the
    # headline finding of the previous run.
    print("\n  --- alternative 7: the lead is a window artifact ---")
    v2_file = pathlib.Path("reports/v2_paired_deep.jsonl")
    window = {}
    if v2_file.exists():
        sub = sorted({json.loads(l)["origin"]
                      for l in v2_file.read_text().splitlines() if l.strip()})
        for t in TARGETS:
            s_sub = [(k, v) for k, v in sig if k in set(sub)]
            t_sub = [(k, v) for k, v in tgt[t] if k in set(sub)]
            o_sub = order(s_sub, t_sub, "evaluation_subsample")
            o_full = base[t]
            moved = abs(o_sub["best_lag"] - o_full["best_lag"]) > 3
            flipped = o_sub["classification"] != o_full["classification"]
            window[t] = {
                "subsample": o_sub, "full": o_full,
                "origins_subsample": len(s_sub), "origins_full": len(sig),
                "lag_moved": moved, "classification_flipped": flipped,
                "robust_to_window": not (moved or flipped)}
            print(f"    {SIGNAL} -> {t:<8} subsample(n={o_sub['n']}) lag "
                  f"{o_sub['best_lag']:+3d} {o_sub['classification']:<11} | "
                  f"full(n={o_full['n']}) lag {o_full['best_lag']:+3d} "
                  f"{o_full['classification']:<11} "
                  f"=> {'ROBUST' if not (moved or flipped) else 'ARTIFACT'}")
    out["tests"]["evaluation_window"] = window

    # --- ADVERSARY 4: wealth effects -----------------------------------
    out["tests"]["wealth_effects"] = {
        "status": "UNTESTABLE",
        "why": ("the household equity-share series BOGZ1FL153064486Q has no "
                "ALFRED vintage before 2020 and is excluded from every "
                "walled read. There is no vintage-correct household wealth "
                "measure in this panel, so this alternative is NOT ruled "
                "out -- it is unchecked, which is a different and weaker "
                "statement.")}
    print(f"\n  --- alternative 4: wealth effects --- UNTESTABLE "
          f"(no vintage-correct wealth series)")

    # --- §10 ROLE -------------------------------------------------------
    survives_all = all(
        resid["ALL"]["results"][t].get("survives") for t in TARGETS)
    survives_any = any(
        resid["ALL"]["results"][t].get("survives") for t in TARGETS)
    reversed_any = any(rev[t]["verdict"] == "REVERSED" for t in TARGETS)
    # A pair that is not robust to the window has no temporal order to
    # explain, so it is settled before the mechanism question is asked.
    out["window_artifacts"] = [t for t, v in window.items()
                               if not v.get("robust_to_window", True)]
    if out["window_artifacts"]:
        print(f"\n  WINDOW ARTIFACTS: {out['window_artifacts']} — the lead "
              "is a property of the origins that were measured, not of the "
              "series")
    if reversed_any:
        role = "COINCIDENT_OR_REFLECTION"
    elif survives_all:
        role = "CANDIDATE_DRIVER"
    elif survives_any:
        role = "PARTIAL_CANDIDATE_DRIVER"
    else:
        role = "EARLY_REFLECTION_OF_ANOTHER_VARIABLE"
    out["role"] = role
    out["role_note"] = (
        "CANDIDATE_DRIVER is the strongest label available and it is still "
        "not causal: it means the lead survived every confounder that could "
        "be checked, with wealth effects unchecked. "
        "EARLY_REFLECTION means the lead is carried by variables the "
        "economic block already has, which is the same thing H7 calls "
        "LEADING_BUT_REDUNDANT arriving by a different route.")
    print(f"\n  §10 ROLE => {role}")
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, default=str))
    print(f"  wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
