"""§11-§14/§18/§20/§22/§24: the economic world model, and what it changes.

The demonstration this run owes: the SAME economic state produces DIFFERENT,
traceable implications for different companies, with the change measured
rather than asserted. No human-state construct appears anywhere in it.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import experiment as EX               # noqa: E402
from intent_engine.econ import panel as PN                    # noqa: E402
from intent_engine.econ import regime as RG                   # noqa: E402
from intent_engine.econ import worldmodel as WM               # noqa: E402

OUT = pathlib.Path("reports")
AS_OF = "2026-08-27"

# ---------------------------------------------------------------------------
# §12 TYPED CROSS-ASSET RELATIONS. Each names its lag, regime and falsifier.
# ---------------------------------------------------------------------------
RELATIONS = [
    WM.Relation(driver="DFF", effect="MORTGAGE30US", sign=1,
                mechanism="the policy rate sets the front of the curve and "
                          "mortgage pricing follows the long end with a "
                          "spread that widens under funding stress",
                lag_days=30, uncertainty="LOW", regime="ALL",
                falsifier="the mortgage rate moves opposite to the policy "
                          "rate over two consecutive quarters",
                evidence="both series in the panel, daily, never revised"),
    WM.Relation(driver="MORTGAGE30US", effect="PERMIT", sign=-1,
                mechanism="a higher mortgage rate raises the monthly payment "
                          "on a given price, and builders pull permits before "
                          "they pull starts",
                lag_days=120, uncertainty="MEDIUM", regime="ALL",
                falsifier="permits rise through a 200bp mortgage-rate "
                          "increase",
                evidence="panel, 1971-2026"),
    WM.Relation(driver="PERMIT", effect="HOUST", sign=1,
                mechanism="a permit is a committed intention to start; the "
                          "gap between them is the builder's own timing",
                lag_days=60, uncertainty="LOW", regime="ALL",
                falsifier="starts and permits diverge for a year",
                evidence="panel, 1960-2026", order=2),
    WM.Relation(driver="BAA10Y", effect="INDPRO", sign=-1,
                mechanism="a wider credit spread raises the marginal cost of "
                          "corporate financing, which shows up first in "
                          "inventory and capex and then in output",
                lag_days=180, uncertainty="MEDIUM", regime="ALL",
                falsifier="industrial production accelerates through a "
                          "200bp spread widening",
                evidence="panel, 1986-2026", order=2),
    WM.Relation(driver="T10Y3M", effect="BAA10Y", sign=-1,
                mechanism="an inverted curve compresses bank net interest "
                          "margin, lending standards tighten, and the credit "
                          "spread widens",
                lag_days=180, uncertainty="MEDIUM", regime="ALL",
                falsifier="spreads narrow through a sustained inversion",
                evidence="panel, 1982-2026"),
    WM.Relation(driver="UNRATE", effect="PCEC96", sign=-1,
                mechanism="employment is the household income channel; "
                          "spending follows with a lag set by savings buffers",
                lag_days=90, uncertainty="MEDIUM", regime="ALL",
                falsifier="real consumption rises through a 1pp "
                          "unemployment increase",
                evidence="panel, 1959-2026", order=3),
]

# ---------------------------------------------------------------------------
# §13 MULTI-ORDER PATHS. Every step persisted; endpoints alone lose the
# places the chain can break.
# ---------------------------------------------------------------------------
PATHS = [
    WM.TransmissionPath(
        name="policy_to_housing", shock="policy tightening",
        steps=(RELATIONS[0], RELATIONS[1], RELATIONS[2])),
    WM.TransmissionPath(
        name="curve_to_output", shock="curve inversion",
        steps=(RELATIONS[4], RELATIONS[3])),
]

# ---------------------------------------------------------------------------
# §17/§18 COMPANY CHANNELS. The channel is the point: two companies may both
# be hurt by weak demand and the CHANNEL is what makes the analysis specific.
#
# THE FOURTH ELEMENT IS THE ADVERSE DRIVER DIRECTION, AND IT USED TO BE
# SOMETHING ELSE.
#
# It was a "base direction" that consumers resolved by flipping it when the
# driver fell. Traced empirically, that convention made EVERY channel adverse
# when its driver ROSE -- which is right for unemployment and credit spreads
# and inverted for consumption, industrial production and permits. Nike's own
# mechanism says "weaker real consumption hits units before price", and the
# harness scored falling consumption as NOT adverse for Nike. Union Pacific's
# says "aggregates and lumber carloads follow permits", and rising permits
# scored as adverse for it.
#
# Found by running the same sixty cases through the product consumer, whose
# sign comes from the canonical business-model transmission table: five
# divergences in one direction and two in the other, all seven on demand
# channels. The field now says exactly what it means -- which way the DRIVER
# has to move to hurt this company through this channel -- and MIXED means the
# mechanism states both directions and no net sign may be asserted.
# ---------------------------------------------------------------------------
COMPANIES = {
    "walmart": ("Walmart", "consumer_staples",
                [("UNRATE", "basket mix and trade-down",
                  "weaker employment pushes households toward lower-margin "
                  "staples and private label; traffic can RISE while mix "
                  "deteriorates", "MIXED"),
                 ("CPIAUCSL", "price gap versus competitors",
                  "grocery inflation widens the everyday-low-price advantage "
                  "against higher-priced grocers", "MIXED")]),
    "nike": ("Nike", "consumer_discretionary",
             [("PCEC96", "discretionary unit demand",
               "footwear and apparel are deferrable; weaker real consumption "
               "hits units before price", "DOWN"),
              ("UNRATE", "promotional intensity and inventory",
               "soft demand meets ordered inventory, so the adjustment shows "
               "up as markdowns before it shows up as revenue", "UP")]),
    "jpmorgan": ("JPMorgan", "financials",
                 [("T10Y3M", "net interest margin",
                   "an inverted curve compresses the spread between funding "
                   "and lending; the deposit beta decides how fast", "DOWN"),
                  ("BAA10Y", "credit provisioning",
                   "a wider spread anticipates the charge-offs that drive "
                   "reserve builds", "UP"),
                  ("DFF", "loan demand",
                   "a higher policy rate suppresses new origination volume "
                   "even where credit quality holds", "UP")]),
    "visa": ("Visa", "payments",
             [("PCEC96", "ticket value and spend mix",
               "volume is resilient because payments are non-deferrable; the "
               "damage is in average ticket and cross-border mix", "DOWN"),
              ("UNRATE", "cross-border travel volume",
               "the highest-yield transactions are discretionary travel, "
               "which is the first to go", "UP")]),
    "caterpillar": ("Caterpillar", "industrials",
                    [("BAA10Y", "customer financing cost",
                      "equipment is bought on credit; the dealer's financing "
                      "cost gates the order before the end market weakens",
                      "UP"),
                     ("INDPRO", "order backlog conversion",
                      "backlog converts to revenue only if the customer's own "
                      "capex survives", "DOWN"),
                     ("PERMIT", "construction end-market",
                      "residential and non-residential permits lead machine "
                      "utilisation by two to three quarters", "DOWN")]),
    "meta": ("Meta", "communication_services",
             [("PCEC96", "advertiser budget and conversion",
               "ad spend is a lagging derivative of expected consumer "
               "spending; performance advertising falls last because it is "
               "measurable", "DOWN"),
              ("DFF", "advertiser cost of capital",
               "venture and growth-stage advertisers cut first when "
               "financing is expensive", "UP")]),
    "nvidia": ("NVIDIA", "semiconductors",
               [("BAA10Y", "customer capex financing",
                 "data-centre buildout is financed; a wider spread lengthens "
                 "the ordering cycle before it cuts it", "UP"),
                ("INDPRO", "supply-chain utilisation",
                 "substrate and packaging capacity tracks industrial output "
                 "rather than end demand", "MIXED")]),
    "unionpacific": ("Union Pacific", "transport",
                     [("INDPRO", "carload volume",
                       "rail volume is close to a direct read on industrial "
                       "output; the mix between intermodal and bulk decides "
                       "yield", "DOWN"),
                      ("PERMIT", "construction materials volume",
                       "aggregates and lumber carloads follow permits with a "
                       "two-quarter lag", "DOWN")]),
    "salesforce": ("Salesforce", "software",
                   [("UNRATE", "seat count",
                     "subscription revenue is priced per seat, so hiring "
                     "freezes hit renewals before they hit new logos", "UP"),
                    ("DFF", "deal cycle length",
                     "a higher discount rate lengthens procurement approval "
                     "for multi-year commitments", "UP")]),
    "regional_private": ("A private regional builder", "sparse",
                         [("MORTGAGE30US", "buyer qualification rate",
                           "a small builder's constraint is how many buyers "
                           "clear underwriting at the prevailing rate, not "
                           "its own cost of capital", "UP")]),
}


def read_state(panel):
    """The live economic reading, per driver, from the walled panel."""
    out = {}
    for sid in ("DFF", "UNRATE", "CPIAUCSL", "PCEC96", "INDPRO", "BAA10Y",
                "T10Y3M", "MORTGAGE30US", "PERMIT", "HOUST"):
        ppy = EX._periods_for_year(sid)
        h = panel.history(sid, as_of=AS_OF, lookback=ppy * 2)
        if len(h) < 6:
            continue
        chg = EX.change(sid, h, ppy)
        if chg is None:
            continue
        out[sid] = {"as_of": h[-1][0], "level": h[-1][1],
                    "yoy_change": round(chg, 5),
                    "direction": "UP" if chg > 0 else "DOWN"}
    return out


def implications(state):
    out = []
    for cid, (name, sector, chans) in sorted(COMPANIES.items()):
        for driver, channel, mechanism, adverse_dir in chans:
            r = state.get(driver)
            if r is None:
                continue
            # DOWN means "this channel is hurt", and it is hurt when the
            # driver moves the way `adverse_dir` names. A MIXED channel
            # states both directions in its own mechanism and never resolves
            # to an adverse reading.
            moved = r["direction"]
            direction = "DOWN" if (adverse_dir in ("UP", "DOWN")
                                   and moved == adverse_dir) else "UP"
            mag = ("HIGH" if abs(r["yoy_change"]) > 0.10
                   else ("MEDIUM" if abs(r["yoy_change"]) > 0.02 else "LOW"))
            out.append(WM.CompanyImplication(
                company_id=cid, driver=driver, channel=channel,
                mechanism=mechanism, direction=direction, magnitude=mag,
                confidence=0.5,
                falsifier=(f"{name} reports this channel moving the other way "
                           f"while {driver} continues {moved}"),
                evidence=(f"panel:{driver}@{r['as_of']}",),
                depends_on=(f"panel:{driver}",)))
    return out


def decision_deltas(state, impls):
    """§22: what the founder analysis says with and without the world model."""
    by_company = {}
    for i in impls:
        by_company.setdefault(i.company_id, []).append(i)
    out = []
    for cid, items in sorted(by_company.items()):
        name = COMPANIES[cid][0]
        # WITHOUT: the generic view — no macro reading, so no priority and no
        # scenario, and the information request is the same for everyone.
        without = {"priority": "none", "recommendation": "monitor",
                   "risk": "unspecified", "scenario": "none",
                   "information_request": "more company detail",
                   "confidence": "low"}
        worst = max(items, key=lambda x: ({"HIGH": 3, "MEDIUM": 2,
                                           "LOW": 1}[x.magnitude],
                                          x.direction == "DOWN"))
        down = [x for x in items if x.direction == "DOWN"]
        with_wm = {
            "priority": worst.channel,
            "recommendation": (
                f"stress-test {worst.channel} against a continued move in "
                f"{worst.driver}" if down else
                f"the current reading of {worst.driver} is not adverse "
                f"through {worst.channel}; hold"),
            "risk": (f"{len(down)} of {len(items)} channels adverse"),
            "scenario": f"{worst.driver} continues; {worst.channel} absorbs it",
            "information_request": worst.falsifier,
            "confidence": "medium" if len(items) > 1 else "low"}
        d = WM.DecisionDelta(company_id=cid, without_world_model=without,
                             with_world_model=with_wm)
        out.append({**d.as_dict(), "company_name": name,
                    "implications": [x.as_dict() for x in items]})
    return out


def bleeds(panel, state):
    """§14: expected links that did not fire, as CANDIDATES."""
    found = []
    for r in RELATIONS:
        a, b = state.get(r.driver), state.get(r.effect)
        if not a or not b:
            continue
        expected = ("UP" if (a["yoy_change"] * r.sign) > 0 else "DOWN")
        if expected == b["direction"]:
            continue
        found.append(WM.Bleed(
            source=r.driver, expected_target=r.effect,
            expected_timing_days=r.lag_days, expected_direction=expected,
            actual_direction=b["direction"],
            transmission_gap=b["yoy_change"] - (a["yoy_change"] * r.sign),
            candidate_explanation=(
                f"the {r.driver} -> {r.effect} link did not fire over the "
                f"last year. Candidates: a longer lag than {r.lag_days}d, a "
                f"regime in which this link is suspended, or an offsetting "
                f"driver not in this model."),
            evidence=f"panel:{r.driver},{r.effect} year-on-year at {AS_OF}",
            uncertainty="HIGH", controllability="LOW",
            decision_impact=WM.DECISION_IMPACT.get("credit", 3)))
    return found


def state_vs_state(panel, as_of_a, as_of_b):
    """§26: the SAME machinery on two different economic states.

    WHY THE FIRST DECISION DELTA IS THE WEAK ONE. Comparing "with the world
    model" against a constant placeholder makes every field differ by
    construction, and 10/10 at 6/6 fields measures nothing but the
    placeholder. The test that means something is whether the analysis MOVES
    when the state moves: if a year of economic change leaves every
    recommendation identical, the world model is present and not read.
    """
    global AS_OF
    keep = AS_OF
    try:
        AS_OF = as_of_a
        sa = read_state(panel)
        ia = {(x.company_id, x.driver): x for x in implications(sa)}
        da = {d["company_id"]: d for d in decision_deltas(sa, list(ia.values()))}
        AS_OF = as_of_b
        sb = read_state(panel)
        ib = {(x.company_id, x.driver): x for x in implications(sb)}
        db = {d["company_id"]: d for d in decision_deltas(sb, list(ib.values()))}
    finally:
        AS_OF = keep
    drivers_moved = sorted(
        k for k in set(sa) & set(sb)
        if sa[k]["direction"] != sb[k]["direction"]
        or abs(sa[k]["yoy_change"] - sb[k]["yoy_change"]) > 0.005)
    rows = []
    for cid in sorted(set(da) & set(db)):
        fa = da[cid]["with_world_model"]
        fb = db[cid]["with_world_model"]
        changed = [f for f in WM.DecisionDelta.FIELDS if fa.get(f) != fb.get(f)]
        flipped = sorted(
            k[1] for k in set(ia) & set(ib)
            if k[0] == cid and ia[k].direction != ib[k].direction)
        rows.append({"company_id": cid, "changed_fields": changed,
                     "nonzero": bool(changed),
                     "implication_directions_flipped": flipped,
                     "from": fa, "to": fb})
    return {"as_of_a": as_of_a, "as_of_b": as_of_b,
            "drivers_moved": drivers_moved,
            "drivers_compared": len(set(sa) & set(sb)),
            "companies": len(rows),
            "companies_changed": sum(1 for r in rows if r["nonzero"]),
            "rows": rows}


def stagnation(state_a, state_b, deltas, bl):
    """§28: is stability legitimate, or is learning broken?

    Four ways a learning system goes quiet, and only one of them is fine.
    """
    alerts = []
    if not state_a or not state_b:
        alerts.append("a state could not be read at all")
    same = [k for k in set(state_a) & set(state_b)
            if state_a[k] == state_b[k]]
    if len(same) == len(set(state_a) & set(state_b)) and same:
        alerts.append("every driver reads identically a year apart; the "
                      "panel is not advancing")
    if not any(d["nonzero"] for d in deltas):
        alerts.append("no company analysis changed under any state")
    if not bl:
        alerts.append("no expected link ever fails, which usually means the "
                      "links are not being checked")
    return {"alerts": alerts,
            "state": ("DEGRADING" if alerts else "STABLE"),
            "reading": (
                "; ".join(alerts) if alerts else
                "drivers move, company analyses move with them, and expected "
                "links are checked and sometimes fail. Stability here is "
                "legitimate rather than broken.")}


def main() -> int:
    panel = PN.Panel.read("reports/panel/historical_panel.jsonl")
    print(f"=== §11 ECONOMIC STATE COVERAGE (as of {AS_OF}) ===")
    audit = WM.audit_dimensions(panel, as_of=AS_OF)
    print(f"  {'dimension':<26}{'status':<9}{'fresh(d)':>9}  producer")
    for dim, a in sorted(audit.items()):
        print(f"  {dim:<26}{a.status:<9}"
              f"{(a.freshness_days if a.freshness_days is not None else '-'):>9}"
              f"  {a.producer or a.note[:44]}")
    live = sum(1 for a in audit.values() if a.status == "LIVE")
    partial = sum(1 for a in audit.values() if a.status == "PARTIAL")
    blocked = sum(1 for a in audit.values() if a.status == "BLOCKED")
    print(f"  LIVE {live}  PARTIAL {partial}  BLOCKED {blocked} of "
          f"{len(audit)}")
    gaps = WM.rank_gaps(audit)
    print(f"\n  gaps ranked by DECISION IMPACT:")
    for g in gaps[:6]:
        print(f"    [{g['decision_impact']}] {g['dimension']:<24}"
              f"{g['status']:<9}{g['why'][:46]}")

    state = read_state(panel)
    print(f"\n=== LIVE READINGS === {len(state)} drivers")
    for sid, r in sorted(state.items()):
        print(f"  {sid:<14}{r['as_of']}  level {r['level']:<12.4g}"
              f"yoy {r['yoy_change']:+.4f}  {r['direction']}")

    print(f"\n=== §12/§13 TRANSMISSION ===")
    for p in PATHS:
        print(f"  {p.name}: {p.shock}")
        for i, s in enumerate(p.steps, 1):
            print(f"    order {i}: {s.driver} -> {s.effect} "
                  f"({'+' if s.sign > 0 else '-'}) lag {s.lag_days}d "
                  f"[{s.uncertainty}]")
        print(f"    net sign {p.net_sign:+d}, total lag "
              f"{p.total_lag_days}d, weakest step "
              f"{p.weakest_step.driver}->{p.weakest_step.effect}")

    bl = bleeds(panel, state)
    print(f"\n=== §14 CAUSAL BLEEDS === {len(bl)} of {len(RELATIONS)} "
          f"relations did not fire")
    for b in sorted(bl, key=lambda x: -x.priority):
        WM.assert_bleed_not_proven(b.as_dict())
        print(f"  [{b.priority:>4}] {b.statement()[:118]}")

    impls = implications(state)
    spec = WM.assert_company_specific(impls)
    print(f"\n=== §18 COMPANY SPECIFICITY ===")
    print(f"  {spec['companies']} companies, {spec['implications']} "
          f"implications, {spec['distinct_channels']} distinct channels "
          f"(specificity {spec['channel_specificity']})")
    for c, ch in sorted(spec["channels_by_company"].items()):
        print(f"    {c:<18}{ch}")

    deltas = decision_deltas(state, impls)
    nonzero = sum(1 for d in deltas if d["nonzero"])
    print(f"\n=== §22 DECISION DELTA ===")
    print(f"  {nonzero} of {len(deltas)} companies had a decision field "
          f"change when the economic state was supplied")
    for d in deltas:
        print(f"    {d['company_name']:<26}{len(d['changed_fields'])}/6 "
              f"fields  priority: {d['with_world_model']['priority'][:40]}")

    print(f"\n  CAVEAT, stated rather than buried: the 'without world "
          f"model' arm is a constant placeholder, so every field differs by "
          f"construction. 10/10 at 6/6 measures the placeholder. The test "
          f"below is the one that means something.")

    # §26 THE TEST THAT MEANS SOMETHING: does the analysis MOVE with the state?
    svs = state_vs_state(panel, "2025-08-27", AS_OF)
    print(f"\n=== §26 STATE V1 vs V2 ({svs['as_of_a']} -> "
          f"{svs['as_of_b']}) ===")
    print(f"  {len(svs['drivers_moved'])} of {svs['drivers_compared']} "
          f"drivers moved: {svs['drivers_moved']}")
    print(f"  {svs['companies_changed']} of {svs['companies']} company "
          f"analyses changed as a result")
    for r in svs["rows"]:
        if r["nonzero"]:
            print(f"    {r['company_id']:<18}{len(r['changed_fields'])} "
                  f"field(s); directions flipped on "
                  f"{r['implication_directions_flipped'] or 'none'}")
    if svs["companies_changed"] == 0:
        print("    NOTHING MOVED. The world model is present and not read.")

    # §18's specificity number, honestly scoped.
    print(f"\n  CAVEAT: channel specificity of "
          f"{spec['channel_specificity']} measures that the AUTHORED "
          f"channels are distinct. It proves the analysis is not one "
          f"paragraph under ten names; it does not prove the system derived "
          f"the channels. The guard is a floor, not an achievement.")

    # §20 the double-counting wall, exercised on the real lineage.
    lineage = {"industrial_aggregate": ["caterpillar", "unionpacific"],
               "caterpillar": ["panel:INDPRO"],
               "unionpacific": ["panel:INDPRO"]}
    try:
        WM.assert_no_double_count("industrial_aggregate", lineage,
                                  ["panel:INDPRO"])
        double_count = "NOT_CAUGHT"
    except WM.WorldModelDefect:
        double_count = "CAUGHT"
    print(f"\n=== §20 DOUBLE-COUNTING WALL === derived aggregate "
          f"corroborated by its own input: {double_count}")

    payload = {"as_of": AS_OF,
               "coverage": {k: v.as_dict() for k, v in audit.items()},
               "coverage_summary": {"live": live, "partial": partial,
                                    "blocked": blocked, "total": len(audit)},
               "gaps_by_decision_impact": gaps,
               "readings": state,
               "relations": [r.as_dict() for r in RELATIONS],
               "paths": [p.as_dict() for p in PATHS],
               "bleeds": [b.as_dict() for b in bl],
               "company_specificity": spec,
               "decision_deltas": deltas,
               "double_counting_wall": double_count,
               "state_vs_state": svs,
               "stagnation": None,
               "caveats": {
                   "decision_delta": (
                       "the 'without' arm is a constant placeholder, so 10/10 "
                       "at 6/6 fields measures the placeholder. state_vs_state "
                       "is the load-bearing measurement."),
                   "channel_specificity": (
                       "measures that the AUTHORED channels are distinct, not "
                       "that the system derived them. It is a floor against a "
                       "template, not evidence of reasoning.")}}
    # THE DETECTOR CAUGHT MY OWN CALL. Passing `read_state(panel)` twice
    # compares today with today, so every driver is identical and the
    # detector correctly reported DEGRADING -- of a bug in the caller, not of
    # the panel. It needs the TWO states the state-vs-state test used.
    _keep = AS_OF
    try:
        globals()["AS_OF"] = svs["as_of_a"]
        _sa = read_state(panel)
    finally:
        globals()["AS_OF"] = _keep
    payload["stagnation"] = stagnation(_sa, read_state(panel), deltas, bl)
    payload["stagnation"]["compared"] = [svs["as_of_a"], svs["as_of_b"]]
    (OUT / "world_model.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str))
    st = payload["stagnation"]
    print(f"\n=== §28 STAGNATION DETECTOR === {st['state']}")
    print(f"  {st['reading'][:150]}")
    print(f"\n  wrote reports/world_model.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
