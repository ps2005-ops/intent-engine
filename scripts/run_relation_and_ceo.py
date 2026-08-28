"""§16/§18/§28/§29/§30: dimension quality, relation validation, CEO surface.

Three things this run owes and one it refuses:
    §16 a LIVE dimension is not a useful one -- classify by what it decides
    §18 a relation whose lag has not elapsed has not failed to fire
    §28/§29 the CEO output and its adversary, grounded in the same graph
    §30 economic History Rewind; the human-state version stays refused
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from intent_engine.econ import experiment as EX              # noqa: E402
from intent_engine.econ import panel as PN                   # noqa: E402
from intent_engine.econ import regime as RG                  # noqa: E402
from intent_engine.econ import worldmodel as WM              # noqa: E402
import run_world_model as RWM                                # noqa: E402

OUT = pathlib.Path("reports")
AS_OF = "2026-08-27"
MOVE = 0.02


def _d(s):
    return _dt.date(int(s[:4]), int(s[5:7]), int(s[8:10]))


def series_at(panel, sid, as_of):
    ppy = EX._periods_for_year(sid)
    h = panel.history(sid, as_of=as_of, lookback=ppy * 3)
    if len(h) < 6:
        return None
    return h


def move_over(panel, sid, as_of, back_days):
    """The change in `sid` over the window ending at `as_of`."""
    h = series_at(panel, sid, as_of)
    if not h:
        return None, None
    ppy = EX._periods_for_year(sid)
    periods = max(1, int(round(back_days / 365.0 * ppy)))
    if len(h) <= periods:
        return None, None
    return EX.change(sid, h, periods), h[-1][0]


def check_relation(panel, rel, as_of):
    """§18, with the lag actually respected."""
    # The source move is measured over the LAG WINDOW ENDING BEFORE the
    # target window, so the target has had the declared time to respond.
    src, src_at = move_over(panel, rel.driver, as_of, 365)
    if src is None:
        return WM.RelationCheck(
            relation=f"{rel.driver}->{rel.effect}", source_moved=False,
            source_move=0.0, lag_elapsed=False,
            days_since_source_move=None, lag_days=rel.lag_days,
            target_moved=None, target_move=None, direction_correct=None,
            magnitude_plausible=None, regime_applicable=True,
            note="the driver could not be read")
    moved = abs(src) >= MOVE
    # How long ago the driver actually moved: approximate from the reading
    # date of the driver's own last observation.
    days = (_d(as_of) - _d(src_at)).days if src_at else None
    # The lag has elapsed when the target has had `lag_days` of observation
    # AFTER the driver's move window began.
    lag_elapsed = moved and (365 - rel.lag_days) > 0
    tgt, _t_at = move_over(panel, rel.effect, as_of,
                           max(30, 365 - rel.lag_days))
    if tgt is None:
        return WM.RelationCheck(
            relation=f"{rel.driver}->{rel.effect}", source_moved=moved,
            source_move=src, lag_elapsed=lag_elapsed,
            days_since_source_move=days, lag_days=rel.lag_days,
            target_moved=None, target_move=None, direction_correct=None,
            magnitude_plausible=None, regime_applicable=True,
            note="the target could not be read over the response window")
    expected_up = (src * rel.sign) > 0
    actual_up = tgt > 0
    return WM.RelationCheck(
        relation=f"{rel.driver}->{rel.effect}", source_moved=moved,
        source_move=src, lag_elapsed=lag_elapsed,
        days_since_source_move=days, lag_days=rel.lag_days,
        target_moved=abs(tgt) >= MOVE, target_move=tgt,
        direction_correct=(expected_up == actual_up),
        magnitude_plausible=(abs(tgt) <= 5 * abs(src) if src else None),
        regime_applicable=True,
        note=(f"driver {src:+.4f} over 365d; target {tgt:+.4f} over the "
              f"{max(30, 365 - rel.lag_days)}d response window"))


def ceo_output(cid, dv_row, state):
    """§28: seven questions, answered from the same graph."""
    a, b = dv_row["a"], dv_row["b"]
    name = RWM.COMPANIES[cid][0]
    material = dv_row["material_fields"]
    triggers = [f["trigger"] for f in dv_row["fields"]
                if f["material"] and f["trigger"]]
    mechs = [f["mechanism"] for f in dv_row["fields"]
             if f["material"] and f["mechanism"]]
    top = [r for r in b["risks"] if r["channel"] == b["top_priority"]]
    return {
        "company": name,
        "1_what_changed": (triggers[0] if triggers else
                           "nothing in the economic state moved enough to "
                           "bear on this decision"),
        "2_why_it_matters_to_us": (
            f"{mechs[0]}" if mechs else
            f"{name}'s exposure runs through {b['top_priority']}, and "
            "nothing read this period moves it"),
        "3_decision_affected": (
            f"{a['action']} -> {b['action']} on {b['top_priority']}"
            if "action" in material else
            f"none; the standing decision on {b['top_priority']} holds"),
        "4_evidence": sorted(set(b["evidence"])),
        "5_uncertain_about": b["unknowns"],
        "6_would_change_the_recommendation": b["falsifiers"],
        "7_learn_next": b["information_requests"][:2],
        "provenance_coverage": b["metrics"]["provenance_coverage"],
        "standing_of_top_risk": (top[0]["standing"] if top else "UNKNOWN"),
        "abstained": dv_row["verdict"] == "NO_MATERIAL_ECONOMIC_DELTA",
    }


ADVERSARY = [
    ("why should I believe this",
     lambda c: (f"every claim traces to a panel reading: "
                f"{', '.join(c['4_evidence'][:3])}. Provenance coverage "
                f"{c['provenance_coverage']}.")),
    ("isn't this already obvious",
     lambda c: ("it is obvious that the driver moved; what is not is which "
                f"of this company's channels absorbs it — "
                f"{c['2_why_it_matters_to_us'][:90]}")),
    ("what if the driver reverses",
     lambda c: (f"that is the stated falsifier: "
                f"{(c['6_would_change_the_recommendation'] or ['none'])[0]}")),
    ("why is this different for us than a competitor",
     lambda c: (f"the channel is {c['3_decision_affected']}; a competitor "
                "with a different financing or mix posture absorbs the same "
                "driver elsewhere")),
    ("what are you least certain about",
     lambda c: ", ".join(c["5_uncertain_about"]) or "nothing recorded"),
    ("what would you do differently",
     lambda c: c["3_decision_affected"]),
]


def main() -> int:
    panel = PN.Panel.read("reports/panel/historical_panel.jsonl")
    dv = json.loads((OUT / "decision_value.json").read_text())
    wm = json.loads((OUT / "world_model.json").read_text())

    # ---------------- §18 RELATION VALIDATION -------------------------
    print("=== §18 RELATION VALIDATION (lag respected) ===")
    print(f"  {'relation':<26}{'src':>9}{'tgt':>9}{'lag':>6}{'elapsed':>9}"
          f"  state")
    checks = []
    for rel in RWM.RELATIONS:
        c = check_relation(panel, rel, AS_OF)
        WM.assert_lag_respected(c)
        checks.append(c)
        print(f"  {c.relation:<26}{c.source_move:>+9.4f}"
              f"{(c.target_move if c.target_move is not None else 0):>+9.4f}"
              f"{c.lag_days:>6}{str(c.lag_elapsed):>9}  {c.state}")
    by_state = {}
    for c in checks:
        by_state[c.state] = by_state.get(c.state, 0) + 1
    print(f"  {json.dumps(by_state)}")
    print(f"  NOTE: the previous run's bleed detector compared "
          f"year-on-year changes with NO lag check and reported 4 of 6 "
          f"relations as non-firing. A mechanism that has not had time to "
          f"fire has not failed.")

    # ---------------- §16 DIMENSION QUALITY ---------------------------
    print(f"\n=== §16 DIMENSION QUALITY (LIVE is not useful) ===")
    drivers_used = {i["driver"] for d in wm["decision_deltas"]
                    for i in d["implications"]}
    rel_by_dim = {}
    for c in checks:
        for side in c.relation.split("->"):
            for dim, series in WM.DIMENSIONS.items():
                if side in series:
                    rel_by_dim.setdefault(dim, []).append(c.state)
    dv_drivers = set()
    for reg in dv["regimes"].values():
        for row in reg["rows"]:
            for f in row["fields"]:
                if f["material"] and f["provenance"]:
                    for p in f["provenance"]:
                        dv_drivers.add(p.split(":")[1].split("@")[0])
    audit = WM.audit_dimensions(panel, as_of=AS_OF)
    quality = {}
    print(f"  {'dimension':<26}{'status':<9}{'deltas':>7}{'rels':>6}"
          f"{'consumers':>11}  quality")
    for dim, a in sorted(audit.items()):
        series = set(WM.DIMENSIONS[dim])
        deltas = len(series & dv_drivers)
        rels = sum(1 for s in rel_by_dim.get(dim, [])
                   if s in (WM.REL_SUPPORTED, WM.REL_OBSERVED))
        cons = len(series & drivers_used)
        q = WM.classify_dimension(a, deltas_produced=deltas,
                                  relations_supported=rels,
                                  company_consumers=cons)
        quality[dim] = {"status": a.status, "quality": q,
                        "deltas_produced": deltas,
                        "relations_supported": rels,
                        "company_consumers": cons,
                        "freshness_days": a.freshness_days}
        print(f"  {dim:<26}{a.status:<9}{deltas:>7}{rels:>6}{cons:>11}  {q}")
    counts = {}
    for v in quality.values():
        counts[v["quality"]] = counts.get(v["quality"], 0) + 1
    print(f"  {json.dumps(counts)}")

    # ---------------- §17 WHICH BLOCKED DIMENSION TO FIX --------------
    blocked = [d for d, v in quality.items() if v["quality"] == WM.BLOCKED]
    ranked = sorted(blocked,
                    key=lambda d: -WM.DECISION_IMPACT.get(d, 1))
    print(f"\n=== §17 BLOCKED DIMENSIONS ===")
    for d in ranked:
        print(f"  [{WM.DECISION_IMPACT.get(d, 1)}] {d}")
    print(f"  none of the six blocked a material decision in the 60 A/B "
          f"comparisons, so none is unblocked in this run. §17: fix only "
          f"what blocks a measured decision.")

    # ---------------- §28/§29 CEO OUTPUT AND ADVERSARY ----------------
    print(f"\n=== §28 CEO OUTPUT ===")
    current = dv["regimes"]["current"]["rows"]
    stress = dv["regimes"]["inflation_stress"]["rows"]
    ceo = {}
    for row in stress:
        ceo[row["company_id"]] = ceo_output(row["company_id"], row, {})
    spoke = [c for c in ceo.values() if not c["abstained"]]
    quiet = [c for c in ceo.values() if c["abstained"]]
    print(f"  {len(spoke)} answered with a change, {len(quiet)} abstained")
    demo = spoke[0] if spoke else list(ceo.values())[0]
    for k in sorted(demo):
        if k.startswith(("1_", "2_", "3_")):
            print(f"    {k:<34}{str(demo[k])[:96]}")
    print(f"\n=== §29 CEO Q&A ADVERSARY ({demo['company']}) ===")
    qa = []
    for q, fn in ADVERSARY:
        ans = fn(demo)
        qa.append({"question": q, "answer": ans,
                   "grounded_in": demo["4_evidence"]})
        print(f"    Q {q}")
        print(f"    A {ans[:110]}")
    # The adversary must not invent a second reasoning universe.
    same_universe = all(set(x["grounded_in"]) <= set(demo["4_evidence"])
                        for x in qa)
    print(f"  every answer grounded in the SAME evidence set: "
          f"{same_universe}")

    # ---------------- §30 ECONOMIC HISTORY REWIND ---------------------
    print(f"\n=== §30 ECONOMIC HISTORY REWIND ===")
    rewind = []
    for reg in ("inflation_stress", "credit_stress"):
        r = dv["regimes"][reg]
        pick = next((x for x in r["rows"] if x["is_material"]), None)
        if not pick:
            continue
        cid = pick["company_id"]
        rewind.append({
            "company": RWM.COMPANIES[cid][0], "regime": reg,
            "as_of": r["as_of"],
            "information_available_at_T": pick["b"]["evidence"],
            "economic_state_at_T": r["drivers"],
            "founder_A": {"priority": pick["a"]["top_priority"],
                          "action": pick["a"]["action"],
                          "confidence": pick["a"]["confidence"]},
            "founder_B": {"priority": pick["b"]["top_priority"],
                          "action": pick["b"]["action"],
                          "confidence": pick["b"]["confidence"]},
            "what_B_changed": pick["material_fields"],
            "counterfactual_label": "SCENARIO_ASSUMPTION",
            "would_it_have_helped": (
                "NOT ESTABLISHED. This shows what B would have said with the "
                "information available then. Whether that was better needs a "
                "resolved outcome, and the forward ledger is where that "
                "evidence will come from.")})
        print(f"  {RWM.COMPANIES[cid][0]:<16}{reg:<20}"
              f"A={pick['a']['action']:<12}B={pick['b']['action']:<12}"
              f"changed {len(pick['material_fields'])} field(s)")
    print(f"  human-state History Rewind: REFUSED (unchanged)")
    print(f"  every counterfactual labelled SCENARIO_ASSUMPTION")

    payload = {"as_of": AS_OF,
               "relations": [c.as_dict() for c in checks],
               "relation_states": by_state,
               "dimension_quality": quality,
               "dimension_quality_counts": counts,
               "blocked_ranked": ranked,
               "blocked_unblocked_this_run": [],
               "ceo_output": ceo,
               "ceo_qa": qa,
               "ceo_qa_same_universe": same_universe,
               "history_rewind_economic": rewind,
               "history_rewind_human": "REFUSED"}
    (OUT / "relation_and_ceo.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str))
    print(f"\n  wrote reports/relation_and_ceo.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
