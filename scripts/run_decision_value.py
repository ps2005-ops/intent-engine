"""§2-§15: does the world model change a DECISION, on real companies?

RUBRIC FROZEN AT 15f463e9e671cb03 BEFORE ANY PAIR WAS SCORED.

Ten companies x five contemporaneously-classified regimes. Baseline A is a
legitimate analysis from the company's own structural economics; B adds the
economic state and nothing else. Only structured decision fields are compared,
so a wording change cannot register as value.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from intent_engine.econ import experiment as EX              # noqa: E402
from intent_engine.econ import founder_ab as FA              # noqa: E402
from intent_engine.econ import panel as PN                   # noqa: E402
from intent_engine.econ import regime as RG                  # noqa: E402
from run_world_model import COMPANIES, read_state            # noqa: E402

OUT = pathlib.Path("reports")
RUBRIC_HASH = "15f463e9e671cb03"

#: Chosen by asking the contemporaneous classifier which origins it reads
#: that way, not by remembering which years felt like what.
REGIMES = {
    "inflation_stress": "2022-07-15",
    "credit_stress": "2023-06-15",
    "recovery": "2016-01-15",
    "calm_expansion": "2016-05-15",
    "labour_deterioration": "2020-12-15",
    "current": "2026-08-27",
}

#: BASELINE A's knowledge: what a founder knows about their own company
#: WITHOUT any macro reading. Structural, durable, company-specific — this is
#: what makes A a real analysis rather than a stub.
STRUCTURAL = {
    "walmart": ("basket mix and trade-down", FA.MONITOR, "LOW",
                "grocery share is defensive but mix is the margin risk in any "
                "environment"),
    "nike": ("discretionary unit demand", FA.MONITOR, "MEDIUM",
             "inventory is ordered two to three quarters ahead of demand"),
    "jpmorgan": ("net interest margin", FA.MONITOR, "MEDIUM",
                 "the deposit franchise is the structural asset and its beta "
                 "is the recurring uncertainty"),
    "visa": ("ticket value and spend mix", FA.MONITOR, "LOW",
             "volume is non-deferrable; yield comes from mix"),
    "caterpillar": ("order backlog conversion", FA.MONITOR, "MEDIUM",
                    "backlog is the visible asset and its conversion is the "
                    "recurring question"),
    "meta": ("advertiser budget and conversion", FA.MONITOR, "MEDIUM",
             "performance advertising is defensible; brand budgets are not"),
    "nvidia": ("customer capex financing", FA.MONITOR, "MEDIUM",
               "demand is concentrated in a few financed buildouts"),
    "unionpacific": ("carload volume", FA.MONITOR, "MEDIUM",
                     "volume follows industrial output; mix decides yield"),
    "salesforce": ("seat count", FA.MONITOR, "LOW",
                   "revenue is priced per seat, so headcount is the exposure"),
    "regional_private": ("buyer qualification rate", FA.MONITOR, "MEDIUM",
                         "the constraint is how many buyers clear "
                         "underwriting, not the builder's own capital"),
}

#: How adverse a driver's move has to be before it changes a decision.
#: Declared here, before scoring.
MATERIAL_MOVE = 0.03


def baseline_a(cid, as_of):
    """§3: a legitimate analysis from company structure alone."""
    priority, action, sev, why = STRUCTURAL[cid]
    name = COMPANIES[cid][0]
    risks = (FA.Risk(risk_id=f"{cid}:structural", severity=sev,
                     channel=priority, mechanism=why,
                     standing=FA.INFERRED,
                     evidence=(f"company_profile:{cid}",)),)
    return FA.Analysis(
        company_id=cid, as_of=as_of, variant=FA.A, top_priority=priority,
        action=action, risks=risks, scenario="POSSIBLE", confidence="LOW",
        information_requests=(f"current reading of {priority}",),
        falsifiers=(f"{name} reports {priority} moving against the "
                    f"structural expectation",),
        evidence=(f"company_profile:{cid}",),
        unknowns=("the current economic environment",),
        prose=f"{name}: {why}.")


def version_b(cid, as_of, state):
    """§4: everything A has, plus the economic state and nothing else."""
    priority, action, sev, why = STRUCTURAL[cid]
    name, _sector, channels = COMPANIES[cid]
    risks = [FA.Risk(risk_id=f"{cid}:structural", severity=sev,
                     channel=priority, mechanism=why, standing=FA.INFERRED,
                     evidence=(f"company_profile:{cid}",))]
    inputs, adverse, requests, falsifiers = [], [], [], []
    for driver, channel, mechanism, base_dir in channels:
        r = state.get(driver)
        if r is None:
            continue
        inputs.append(f"panel:{driver}@{r['as_of']}")
        direction = base_dir
        if base_dir in ("UP", "DOWN") and r["direction"] == "DOWN":
            direction = "UP" if base_dir == "DOWN" else "DOWN"
        mag = abs(r["yoy_change"])
        if direction != "DOWN" or mag < MATERIAL_MOVE:
            continue
        sev_b = "HIGH" if mag > 0.10 else "MEDIUM"
        adverse.append((mag, channel, driver))
        risks.append(FA.Risk(
            risk_id=f"{cid}:{driver}", severity=sev_b, channel=channel,
            mechanism=mechanism, standing=FA.OBSERVED,
            evidence=(f"panel:{driver}@{r['as_of']}",)))
        requests.append(f"how much of {channel} is already contracted")
        falsifiers.append(f"{channel} holds while {driver} continues "
                          f"{r['direction']}")
    if adverse:
        adverse.sort(reverse=True)
        _m, top_channel, top_driver = adverse[0]
        action_b = FA.PREPARE if len(adverse) > 1 else FA.INVESTIGATE
        band = "LIKELY" if len(adverse) > 1 else "POSSIBLE"
        conf = "MEDIUM"
        priority_b = top_channel
    else:
        # §15 ABSTENTION. The state was read and does not bear on the
        # decision. This is a successful result, not a missing one.
        action_b, band, conf, priority_b = action, "POSSIBLE", "LOW", priority
        requests = [f"current reading of {priority}"]
    return FA.Analysis(
        company_id=cid, as_of=as_of, variant=FA.B, top_priority=priority_b,
        action=action_b, risks=tuple(risks), scenario=band, confidence=conf,
        information_requests=tuple(requests) or (f"current reading of "
                                                 f"{priority}",),
        falsifiers=tuple(falsifiers) or (f"{name} reports {priority} moving "
                                         f"against expectation",),
        evidence=tuple([f"company_profile:{cid}"] + inputs),
        unknowns=(("what is already contracted",) if adverse
                  else ("the current economic environment",)),
        economic_inputs=tuple(inputs),
        prose=f"{name}: {why}. Economic state read at {as_of}.")


def triggers_for(cid, state):
    """§13: the world-model fact behind every material field."""
    _p, _a, _s, _w = STRUCTURAL[cid]
    _name, _sector, channels = COMPANIES[cid]
    best, out = None, {}
    for driver, channel, mechanism, base_dir in channels:
        r = state.get(driver)
        if r is None:
            continue
        direction = base_dir
        if base_dir in ("UP", "DOWN") and r["direction"] == "DOWN":
            direction = "UP" if base_dir == "DOWN" else "DOWN"
        if direction != "DOWN" or abs(r["yoy_change"]) < MATERIAL_MOVE:
            continue
        if best is None or abs(r["yoy_change"]) > best[0]:
            best = (abs(r["yoy_change"]), driver, channel, mechanism, r)
    if best is None:
        return {}
    _m, driver, channel, mechanism, r = best
    t = (f"{driver} moved {r['yoy_change']:+.4f} year-on-year to "
         f"{r['level']:.4g} as of {r['as_of']}")
    prov = (f"panel:{driver}@{r['as_of']}",)
    for f in ("top_priority", "action", "top_risks", "scenario",
              "confidence", "information_priority", "risk_severity"):
        out[f] = (t, mechanism, prov)
    return out


def main() -> int:
    FA.assert_rubric_unchanged(RUBRIC_HASH)
    print(f"=== RUBRIC {FA.rubric_hash()} — frozen before any pair scored ===")
    panel = PN.Panel.read("reports/panel/historical_panel.jsonl")
    import run_world_model as RWM

    results, damages = [], []
    print(f"\n{'regime':<22}{'companies':>10}{'material':>10}"
          f"{'attributed':>12}{'abstained':>11}{'damage':>8}")
    per_regime = {}
    for reg_name, as_of in REGIMES.items():
        RWM.AS_OF = as_of
        state = read_state(panel)
        reading = RG.classify(panel, as_of)
        rows, dmg = [], []
        for cid in sorted(STRUCTURAL):
            a = baseline_a(cid, as_of)
            FA.assert_baseline_is_real(a)
            b = version_b(cid, as_of, state)
            d = FA.compare(a, b, regime=reg_name,
                           triggers=triggers_for(cid, state))
            rows.append({**d.as_dict(), "a": a.as_dict(), "b": b.as_dict()})
            dmg.extend(x.as_dict() for x in
                       FA.detect_damage(a, b, regime=reg_name))
        mat = sum(1 for r in rows if r["is_material"])
        att = sum(1 for r in rows if r["attributable"])
        abst = sum(1 for r in rows
                   if r["verdict"] == "NO_MATERIAL_ECONOMIC_DELTA")
        per_regime[reg_name] = {
            "as_of": as_of, "regimes_held": list(reading.regimes),
            "drivers": {k: v["direction"] for k, v in state.items()},
            "companies": len(rows), "material": mat, "attributed": att,
            "abstained": abst, "damage": len(dmg),
            "rows": rows, "damages": dmg}
        results.extend(rows)
        damages.extend(dmg)
        print(f"{reg_name:<22}{len(rows):>10}{mat:>10}{att:>12}"
              f"{abst:>11}{len(dmg):>8}")

    total = len(results)
    material = sum(1 for r in results if r["is_material"])
    attributed = sum(1 for r in results if r["attributable"])
    abstained = sum(1 for r in results
                    if r["verdict"] == "NO_MATERIAL_ECONOMIC_DELTA")
    unattributed = material - attributed
    print(f"\n=== §7/§13 DECISION VALUE ===")
    print(f"  A/B comparisons          {total}")
    print(f"  material DecisionDelta   {material} "
          f"({material / total:.0%})")
    print(f"  attributable             {attributed} "
          f"({attributed / material:.0%} of material)" if material else "")
    print(f"  MATERIAL_BUT_UNATTRIBUTED {unattributed}")
    print(f"  NO_MATERIAL_ECONOMIC_DELTA {abstained} "
          f"({abstained / total:.0%}) — §15 counts this as a success")
    print(f"  DecisionDamage           {len(damages)}")
    by_kind = {}
    for d in damages:
        by_kind[d["kind"]] = by_kind.get(d["kind"], 0) + 1
    for k, n in sorted(by_kind.items(), key=lambda x: -x[1]):
        print(f"    {k:<26}{n}")

    fields = {}
    for r in results:
        for f in r["material_fields"]:
            fields[f] = fields.get(f, 0) + 1
    print(f"\n  material field movements:")
    for f, n in sorted(fields.items(), key=lambda x: -x[1]):
        print(f"    {f:<24}{n}")

    # §12 NEGATIVE CONTROL: the world model must know when to stay quiet.
    quiet = {r["regime"] for r in results
             if r["verdict"] == "NO_MATERIAL_ECONOMIC_DELTA"}
    loud = {r["regime"] for r in results if r["is_material"]}
    control = ("PASS" if quiet and loud else
               ("FAIL_ALWAYS_LOUD" if not quiet else "FAIL_ALWAYS_QUIET"))
    print(f"\n=== §12 NEGATIVE CONTROL === {control}")
    print(f"  abstains in {sorted(quiet)}")
    print(f"  speaks in  {sorted(loud)}")
    if control != "PASS":
        print("  a system that changes every analysis in every regime is "
              "over-injecting, not informing")

    payload = {
        "rubric_hash": FA.rubric_hash(), "rubric": FA.RUBRIC,
        "code_sha": subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                   capture_output=True,
                                   text=True).stdout.strip(),
        "regimes": per_regime,
        "summary": {"comparisons": total, "material": material,
                    "attributed": attributed,
                    "unattributed": unattributed, "abstained": abstained,
                    "damage": len(damages), "damage_by_kind": by_kind,
                    "material_field_movements": fields,
                    "attributable_delta_rate": (round(attributed / material, 3)
                                                if material else None),
                    "negative_control": control},
        "superseded": {
            "metric": "DecisionDelta 10/10 against a constant placeholder",
            "status": "INVALID_COMPARATOR_FOR_PRODUCT_VALUE",
            "why": ("the 'without' arm was a hard-coded placeholder, so every "
                    "field differed by construction. Kept for the record; "
                    "never reported as product evidence again.")},
    }
    (OUT / "decision_value.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str))
    print(f"\n  wrote reports/decision_value.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
