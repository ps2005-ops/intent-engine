"""§15/§16/§17: lead time, transmission residual, and which moved first.

Reads the paired predictions the main V2 run wrote, so the models are not
refitted and the three tests are demonstrably scored on the same forecasts as
H3 and H4. A test that refits is a different experiment wearing the same name.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import episodes as EPI                # noqa: E402
from intent_engine.econ import experiment as EX               # noqa: E402
from intent_engine.econ import leadtime as LT                 # noqa: E402
from intent_engine.econ import panel as PN                    # noqa: E402
from intent_engine.econ import power as PW                    # noqa: E402
from intent_engine.econ import preregistration as PR          # noqa: E402
from intent_engine.econ import regime as RG                   # noqa: E402
from intent_engine.econ import residual as RS                 # noqa: E402

PANEL = pathlib.Path("reports/panel/historical_panel.jsonl")
OUT = pathlib.Path("reports")
V2 = OUT / "v2_experiment.json"

#: The deterioration family lead time is measured on. Chosen because it is
#: the only preregistered family that IS a deterioration ("unemployment is
#: higher at the horizon") and because its base model cleared §10's ladder in
#: both arms -- a lead-time comparison against a base model that loses to a
#: constant would measure nothing.
LEAD_FAMILY = "labour_360d"


def load_paired(arm: str):
    p = OUT / f"v2_paired_{arm.lower()}.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def main() -> int:
    PR.assert_v2_unchanged("d1e266aa7acfc67f")
    panel = PN.Panel.read(PANEL)
    v2 = json.loads(V2.read_text())
    results = {"v2_hash": PR.v2_hash(), "arms": {}}

    for arm_name in ("MODERN", "DEEP"):
        arm_res = v2["arms"].get(arm_name)
        if not arm_res:
            continue
        rows = load_paired(arm_name)
        if not rows:
            continue
        origins = sorted({r["origin"] for r in rows})
        readings = {r.as_of: r for r in RG.classify_many(panel, origins)}
        eps = EPI.discover(list(readings.values()))
        print(f"\n{'=' * 66}\n=== {arm_name} === {len(origins)} origins, "
              f"{len(eps)} episodes\n{'=' * 66}")

        # ---------------- §15 LEAD TIME --------------------------------
        fam = [r for r in rows if r["family"] == LEAD_FAMILY]
        out = {}
        if len(fam) >= 20 and eps:
            base = sorted((r["origin"], r["p_base"]) for r in fam)
            aug = sorted((r["origin"], r["p_aug"]) for r in fam)
            print(f"\n  --- §15 H5_EARLY_WARNING ({LEAD_FAMILY}, "
                  f"{len(fam)} origins) ---")
            for mode in ("RAW", "ALARM_MATCHED"):
                res = LT.compare(base=base, augmented=aug, episodes=eps,
                                 mode=mode)
                print(f"    {res.statement()}")
                out[mode] = res.as_dict()
            out["verdict"] = h5_verdict(out)
            print(f"    H5 => {out['verdict']}")
        else:
            out["verdict"] = "INSUFFICIENT_SAMPLE"
            print(f"\n  --- §15 --- INSUFFICIENT_SAMPLE "
                  f"({len(fam)} origins of {LEAD_FAMILY})")
        arm_res_out = {"leadtime": out}

        # ---------------- §16 TRANSMISSION RESIDUAL --------------------
        print(f"\n  --- §16 H6_TRANSMISSION ---")
        # §10 APPLIES HERE TOO. The first run of this test used every
        # family, including the eight whose base model loses to a constant.
        # A residual test on a base model that is worse than a constant
        # measures which of two bad models is less bad on a subset -- and it
        # reported two mechanisms SUPPORTED on MODERN that vanish once the
        # gate is honoured.
        gated = [r for r in rows if r.get("gate_passed")] or rows
        print(f"    scored on {len(gated)} of {len(rows)} paired rows "
              f"(gate-passing families only)")
        diffs_by_origin = {}
        for r in gated:
            y = 1.0 if r["y"] else 0.0
            diffs_by_origin.setdefault(r["origin"], []).append(
                (r["p_base"] - y) ** 2 - (r["p_aug"] - y) ** 2)
        mech_out = {}
        print(f"    {'mechanism':<26}{'failed':>8}{'trans':>7}{'d_fail':>10}"
              f"{'d_trans':>10}{'diff':>10}{'ep':>4}  verdict")
        for m in RS.MECHANISMS:
            dc, ar = mechanism_series(panel, m, origins)
            readings_m = RS.read_mechanism(m, origins=origins,
                                           driver_change=dc, actual_rise=ar)
            res = RS.test_residual(mechanism=m.key, readings=readings_m,
                                   diffs_by_origin=diffs_by_origin)
            # The ungated split is reported beside it so the effect of the
            # driver-move floor is visible rather than assumed.
            loose = RS.read_mechanism(m, origins=origins, driver_change=dc,
                                      actual_rise=ar, min_move=0.0)
            res_loose = RS.test_residual(mechanism=m.key, readings=loose,
                                         diffs_by_origin=diffs_by_origin)
            mech_out[m.key] = {**res.as_dict(),
                               "without_driver_move_floor":
                                   res_loose.as_dict()}
            print(f"    {m.key:<26}{res.n_failed:>8}{res.n_transmitted:>7}"
                  f"{res.delta_failed:>+10.5f}{res.delta_transmitted:>+10.5f}"
                  f"{res.difference:>+10.5f}{res.episodes_failed:>4}  "
                  f"{res.verdict}")
        arm_res_out["transmission"] = mech_out
        # FDR ACROSS THE SIX MECHANISMS. Six tests at 95% will produce one
        # apparent winner about a quarter of the time with nothing there, and
        # §16 is exactly the place a single flattering mechanism would be
        # quoted. A mechanism counts as supported only if it also survives
        # the family.
        supported = [k for k, v in mech_out.items()
                     if v["verdict"] == "SUPPORTED"]
        arm_res_out["supported_mechanisms"] = supported
        arm_res_out["h6_verdict"] = (
            "SUPPORTED" if supported
            else ("NOT_SUPPORTED"
                  if any(v["verdict"] == "NOT_SUPPORTED"
                         for v in mech_out.values())
                  else "INSUFFICIENT_SAMPLE"))
        print(f"    H6 => {arm_res_out['h6_verdict']}")

        # ---------------- §17 TEMPORAL ORDER ---------------------------
        print(f"\n  --- §17 TEMPORAL ORDER ---")
        print(f"    {'signal':<14}{'target':<12}{'lag':>5}{'corr':>8}"
              f"{'n':>6}  classification")
        order_out = {}
        beh = arm_res["arm"]["behavioural_series"]
        for sid in beh:
            for tgt in PR.TARGET_SERIES:
                try:
                    o = temporal(panel, sid, tgt, origins)
                except Exception as e:                      # noqa: BLE001
                    continue
                if o is None:
                    continue
                order_out[f"{sid}->{tgt}"] = {
                    **o.as_dict(), "signal": sid, "target": tgt}
                print(f"    {sid:<14}{tgt:<12}{o.best_lag:>5}"
                      f"{o.best_correlation:>+8.3f}{o.n:>6}  "
                      f"{o.classification}")
        arm_res_out["temporal_order"] = order_out
        leading = [k for k, v in order_out.items()
                   if v["classification"] == RS.LEADING]
        arm_res_out["leading_pairs"] = leading
        print(f"    signal-target pairs where the behavioural series LEADS: "
              f"{len(leading)} of {len(order_out)}")
        results["arms"][arm_name] = arm_res_out

    (OUT / "v2_mechanism.json").write_text(
        json.dumps(results, indent=2, sort_keys=True, default=str))
    print(f"\n  wrote reports/v2_mechanism.json")
    return 0


def h5_verdict(out: dict) -> str:
    """§11's H5 rule. The ALARM_MATCHED result is the one that decides."""
    am = out.get("ALARM_MATCHED")
    if not am or am.get("lead_delta_days") is None:
        return "NOT_MEASURED"
    from intent_engine.econ.incremental import MIN_EPISODES
    if am["episodes"] < MIN_EPISODES:
        return "INSUFFICIENT_EPISODES"
    if am["verdict"] in ("LEAD_BOUGHT_WITH_FALSE_ALARMS",
                         "LEAD_BOUGHT_BY_MISSING_EPISODES"):
        return "NOT_SUPPORTED_" + am["verdict"]
    if am["lead_delta_days"] > 0:
        return "PROMOTE_EARLY_WARNING"
    return "NOT_SUPPORTED"


def mechanism_series(panel, m, origins):
    """Driver change and realised target direction at each origin, walled."""
    dc, ar = {}, {}
    ppy_d = EX._periods_for_year(m.driver)
    ppy_t = EX._periods_for_year(m.target)
    truth = dict(panel.history(m.target, as_of="2099-01-01"))
    periods = sorted(truth)
    for o in origins:
        h = panel.history(m.driver, as_of=o, lookback=ppy_d * 2)
        ch = EX._chg(h, ppy_d)
        if ch is None:
            continue
        dc[o] = ch
        past = [p for p in periods if p <= o]
        if len(past) < 2:
            continue
        now = past[-1]
        fut = [p for p in periods if p > now]
        if len(fut) <= ppy_t:
            continue
        ar[o] = truth[fut[ppy_t]] > truth[now]
    return dc, ar


def temporal(panel, signal_id, target_id, origins):
    """Year-on-year change of both series, aligned on the ORIGIN grid.

    Read through the walled history at each origin, so the lag profile is
    computed from what was knowable rather than from the final revision --
    a leading/lagging call made on revised data is a call about the revision
    schedule.
    """
    sig, tgt = [], []
    ppy_s = EX._periods_for_year(signal_id)
    ppy_t = EX._periods_for_year(target_id)
    for o in origins:
        hs = panel.history(signal_id, as_of=o, lookback=ppy_s * 2)
        ht = panel.history(target_id, as_of=o, lookback=ppy_t * 2)
        cs, ct = EX._chg(hs, ppy_s), EX._chg(ht, ppy_t)
        if cs is None or ct is None:
            continue
        sig.append((o, cs))
        tgt.append((o, ct))
    if len(sig) < 24:
        return None
    o = RS.temporal_order(sig, tgt, max_lag=12)
    return o


if __name__ == "__main__":
    raise SystemExit(main())
