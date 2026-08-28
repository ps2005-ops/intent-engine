"""§20: does the PRODUCT consumer preserve the research semantics?

THE QUESTION THIS ANSWERS
-------------------------
The offline result -- 24 material of 60, 100% attributable, 36 deliberate
abstentions -- was produced by a research harness calling `founder_ab.compare`
directly. The product calls it through `econ_decision.build`, which adds four
things the harness did not have: the §8 admission wall, a company profile that
supplies the mechanism, a freshness gate, and a contract that refuses several
classes of material outright.

Any of those could silently change the verdict. A wall that refuses everything
turns 24 material deltas into 0 and the product looks calm; a wall that refuses
nothing makes the wall decorative. So the same 60 cases are run through the
product path and the two verdicts are compared CASE BY CASE.

WHAT PARITY MEANS HERE
----------------------
Not byte-identical prose -- §20 says so explicitly, and the two paths compose
different sentences by design. Parity is on the STRUCTURED verdict:

    material stays material
    abstention stays abstention
    no unsupported new delta appears

A divergence is not automatically a defect: the product knows things the
harness does not (a company whose business model has no mechanism for a
condition SHOULD abstain where the harness spoke). So every divergence is
CLASSIFIED rather than counted, and only the unexplainable ones are failures.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from intent_engine.econ import founder_ab as FA               # noqa: E402
from intent_engine.econ import founder_contract as FC         # noqa: E402
from intent_engine.econ import panel as PN                    # noqa: E402
from intent_engine.external_intel import econ_context as EC   # noqa: E402
from intent_engine.external_intel import econ_decision as ED  # noqa: E402
from intent_engine.executive import company_profile as CPF    # noqa: E402
from run_decision_value import (REGIMES, STRUCTURAL,          # noqa: E402
                                baseline_a, triggers_for, version_b)
from run_world_model import COMPANIES, read_state             # noqa: E402

OUT = pathlib.Path("reports")

#: The name each research company resolves by, so the PRODUCT'S OWN profile
#: resolver answers rather than this harness asserting a class.
#:
#: THE FIRST VERSION OF THIS FILE HAND-ASSIGNED THE MODEL CLASSES, and it was
#: measurably wrong: it called Walmart BRANDED_CONSUMER where the validation
#: manifest calls it SCALE_RETAIL, and the resulting five divergences were a
#: disagreement between this fixture and the manifest rather than between the
#: research arm and the product. A parity harness that supplies the product
#: with an input the product would never have is measuring the fixture.
COMPANY_NAME = {
    "walmart": "Walmart",
    "nike": "Nike Inc",
    "jpmorgan": "JPMorgan Chase & Co",
    "visa": "Visa Inc",
    "caterpillar": "Caterpillar Inc",
    "meta": "Meta Platforms",
    "nvidia": "NVIDIA Corporation",
    "unionpacific": "Union Pacific",
    "salesforce": "Salesforce Inc",
    # Not in the manifest and deliberately so -- a private regional builder is
    # the sparse case, and the product answers PROFILE_SPARSE for it. What
    # that produces is part of what this harness measures.
    "regional_private": "A private regional builder",
}

#: The panel driver each shared-state condition is measured by, so the same
#: numbers reach both arms. The research harness reads drivers by FRED id; the
#: product reads conditions by econ kind, and this is the join.
#: ONE DRIVER PER CONDITION, and this used to carry two.
#:
#: `PERMIT` and `HOUST` both mapped to `housing`, so whichever the state built
#: last decided what "housing" read -- and Union Pacific fired on a falling
#: HOUST in a regime where its own channel, PERMIT, was rising. That is a
#: defect in this fixture, not in the product: the shared state holds ONE
#: reading per condition and a harness that feeds it two is not modelling the
#: product's input. PERMIT is kept because it is the driver the companies'
#: own channels name.
DRIVER_KIND = {
    "DFF": "policy_rate", "UNRATE": "labour", "CPIAUCSL": "inflation",
    "PCEC96": "consumer_demand", "INDPRO": "industrial_production",
    "BAA10Y": "credit_spread_ig", "T10Y3M": "curve_slope",
    "PERMIT": "housing",
    "MORTGAGE30US": "treasury_10y",
}


class _Decision:
    """The run's own recommendation, in the shape the product reads.

    A stand-in for `FounderDecision` carrying only the fields
    `baseline_from_decision` consults. Using the real class would drag the
    whole strategic report in; using a stub that carried MORE than the product
    reads would be measuring something the product cannot see.
    """

    def __init__(self, readiness, archetype, requests, falsifier):
        self.readiness = readiness
        self.decision_archetype = archetype
        self.topic = archetype
        self.evidence_required = requests
        self.watch_items = ()
        self.falsifier = falsifier


def _state_for(cid, state):
    """The shared economic state as the PRODUCT would read it, from the same
    panel readings the research arm used."""
    conditions = {}
    for driver, reading in state.items():
        kind = DRIVER_KIND.get(driver)
        if not kind:
            continue
        conditions[kind] = {
            "kind": kind, "standing": "OBSERVED",
            "direction": reading["direction"], "value": reading["level"],
            "unit": "", "as_of": reading["as_of"],
            "node_id": f"panel:{driver}:{reading['as_of']}",
            "publisher": "FRED", "known": True,
            "moved": reading["direction"] in ("UP", "DOWN"),
            "prior_value": reading["level"] / (1 + reading["yoy_change"]
                                               or 1),
            "prior_as_of": reading["as_of"]}
    return EC.EconContext(available=True, as_of=max(
        (c["as_of"] for c in conditions.values()), default=""),
        area="US", conditions=conditions)


def main() -> int:
    panel = PN.Panel.read("reports/panel/historical_panel.jsonl")
    import run_world_model as RWM

    rows = []
    print(f"{'regime':<22}{'harness':>9}{'product':>9}{'agree':>7}"
          f"{'explained':>11}{'UNEXPLAINED':>13}")
    for reg_name, as_of in REGIMES.items():
        RWM.AS_OF = as_of
        state = read_state(panel)
        econ = _state_for(None, state)
        agree = explained = unexplained = 0
        h_mat = p_mat = 0
        for cid in sorted(STRUCTURAL):
            # --- the research arm, unchanged --------------------------------
            a = baseline_a(cid, as_of)
            b = version_b(cid, as_of, state)
            harness = FA.compare(a, b, regime=reg_name,
                                 triggers=triggers_for(cid, state))
            # --- the product arm --------------------------------------------
            priority, action, sev, why = STRUCTURAL[cid]
            decision = _Decision(
                "INVESTIGATION_REQUIRED", priority,
                (f"current reading of {priority}",),
                f"{COMPANIES[cid][0]} reports {priority} moving against "
                f"the structural expectation")
            profile = CPF.profile_for(cid, name=COMPANY_NAME[cid])
            exposures = sorted({DRIVER_KIND[d] for d, _c, _m, _bd
                                in COMPANIES[cid][2] if d in DRIVER_KIND})
            ctx = ED.build(
                company_id=cid, company_name=COMPANIES[cid][0], as_of=as_of,
                economy=econ, exposures=exposures, profile=profile,
                decision=decision,
                risks=[{"risk_id": f"{cid}:structural", "severity": sev,
                        "channel": priority, "mechanism": why,
                        "standing": "INFERRED",
                        "evidence": (f"company_profile:{cid}",)}])
            h_material = harness.is_material
            p_material = bool(ctx.material_decision_delta)
            h_mat += h_material
            p_mat += p_material
            verdict = "AGREE"
            why_diff = ""
            if h_material == p_material:
                agree += 1
            elif h_material and not p_material:
                # The product abstained where the harness spoke. Legitimate
                # exactly when the product knows something the harness does
                # not: no mechanism from this condition into this business
                # model, or the §8 wall refused the change.
                codes = {r.get("code") for r in ctx.refused}
                no_mech = [e.quantity for e in ctx.company_exposures
                           if not e.measured]
                if codes or no_mech:
                    verdict, explained = "EXPLAINED_ABSTENTION", explained + 1
                    why_diff = (f"refused={sorted(c for c in codes if c)} "
                                f"no_mechanism={no_mech}")
                else:
                    verdict, unexplained = "UNEXPLAINED_SILENCE", \
                        unexplained + 1
            else:
                # §20's hard requirement: no unsupported NEW delta.
                #
                # There is exactly one legitimate reason for the product to
                # speak where the research arm did not: the two arms hold
                # DIFFERENT EXPOSURE CLAIMS for the company, and the
                # product's comes from the canonical business-model
                # transmission table while the research arm's is a
                # hand-written per-company note. NVIDIA is the live example --
                # the note calls its industrial-production exposure MIXED
                # (substrate capacity), the canonical table for
                # DESIGN_AND_MANUFACTURE calls it order rates and signs it.
                # §9 says the reasoning must come from canonical exposure
                # state, so the product's source is the sanctioned one.
                #
                # It is only accepted when the product's change is
                # ATTRIBUTABLE and the canonical sign is actually established
                # for this company's model class -- a change with neither is
                # the unsupported delta this check exists to catch.
                canonical = [e for e in ctx.company_exposures
                             if e.measured and e.mechanism]
                hand = {d: bd for d, _c, _m, bd in COMPANIES[cid][2]}
                mixed = [d for d, bd in hand.items() if bd == "MIXED"]
                if ctx.attributable and canonical and mixed:
                    verdict = "EXPLAINED_CANONICAL_SIGN"
                    explained += 1
                    why_diff = (f"the research arm calls {mixed} MIXED for "
                                f"this company; the canonical "
                                f"{profile.business_model_class} transmission "
                                f"table signs it")
                else:
                    verdict, unexplained = "UNSUPPORTED_NEW_DELTA", \
                        unexplained + 1
            rows.append({
                "regime": reg_name, "company": cid, "verdict": verdict,
                "harness_material": h_material,
                "harness_fields": list(harness.material_fields),
                "product_material": p_material,
                "product_fields": [c.field for c
                                   in ctx.material_decision_delta],
                "product_status": ctx.status,
                "product_attributable": ctx.attributable,
                "refused": list(ctx.refused), "why": why_diff,
                "headline": ctx.headline()})
        print(f"{reg_name:<22}{h_mat:>9}{p_mat:>9}{agree:>7}"
              f"{explained:>11}{unexplained:>13}")

    total = len(rows)
    agree = sum(1 for r in rows if r["verdict"] == "AGREE")
    expl = sum(1 for r in rows if r["verdict"].startswith("EXPLAINED"))
    unex = total - agree - expl
    p_mat = sum(1 for r in rows if r["product_material"])
    h_mat = sum(1 for r in rows if r["harness_material"])
    p_abs = sum(1 for r in rows
                if r["product_status"] == FC.NO_MATERIAL_ECONOMIC_DELTA)
    new_delta = sum(1 for r in rows if r["verdict"] == "UNSUPPORTED_NEW_DELTA")
    unattributed = sum(1 for r in rows
                       if r["product_material"] and not r["product_attributable"])
    print(f"\n=== §20 PRODUCT SEMANTIC PARITY ===")
    print(f"  cases                       {total}")
    print(f"  harness material            {h_mat}")
    print(f"  product material            {p_mat}")
    print(f"  product abstained           {p_abs}")
    print(f"  identical verdict           {agree}")
    print(f"  explained divergence        {expl}")
    print(f"  UNEXPLAINED divergence      {unex}")
    print(f"  unsupported new delta       {new_delta}   (§20 requires 0)")
    print(f"  material but unattributed   {unattributed}   (§13 requires 0)")
    verdict = ("PASS" if new_delta == 0 and unattributed == 0 and unex == 0
               else "FAIL")
    print(f"\n=== VERDICT === {verdict}")
    payload = {
        "contract": "product_parity.v1",
        "code_sha": subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                   capture_output=True,
                                   text=True).stdout.strip(),
        "summary": {"cases": total, "harness_material": h_mat,
                    "product_material": p_mat, "product_abstained": p_abs,
                    "identical": agree, "explained_divergence": expl,
                    "unexplained_divergence": unex,
                    "unsupported_new_delta": new_delta,
                    "material_but_unattributed": unattributed,
                    "verdict": verdict},
        "rows": rows}
    (OUT / "product_parity.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str))
    print(f"  wrote reports/product_parity.json")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
