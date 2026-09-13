"""Break proofs for E-DEM-002: figures that disagree without being adjacent.

Proof 1 is the one to read. It makes CANCELLATIONS point the same way as
everything else, which is the assumption the chain's direction rule already
makes and the reason backlog-up-with-cancellations-up was invisible.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

M = ROOT / "src/intent_engine/market"
T = "tests"
DT = f"{T}/test_market_demand_tension.py"
RP = f"{T}/test_market_report_projections.py"

PROOFS = [
    ("1. a rise in cancellations becomes good news",
     M / "demand_tension.py",
     "POLARITY[DC.CANCELLATIONS] = DEMAND_NEGATIVE",
     "POLARITY[DC.CANCELLATIONS] = DEMAND_POSITIVE",
     f"{DT}::test_a_rise_in_cancellations_points_down_for_demand"),

    ("2. polarity stops being applied at all",
     M / "demand_tension.py",
     "    if POLARITY.get(state, DEMAND_POSITIVE) == DEMAND_NEGATIVE:\n"
     "        return DOWN if direction == UP else UP",
     "    if False:\n"
     "        return DOWN if direction == UP else UP",
     f"{DT}::test_backlog_up_with_cancellations_up_is_a_tension"),

    ("3. a flat figure is given a direction",
     M / "demand_tension.py",
     "    if direction not in (UP, DOWN):\n        return None",
     "    if direction not in (UP, DOWN):\n        return UP",
     f"{DT}::test_a_flat_figure_points_nowhere"),

    # An earlier version of this proof mutated a `known` check inside
    # demand_tension and came back NOT_CAUGHT: `unknown()` always sets FLAT,
    # so the direction guard already dropped those readings and the check
    # could not be reached by any input. The guard was DELETED rather than
    # kept with a test naming it. What actually carries the property is the
    # direction an unmeasured reading is given, so that is what this mutates.
    ("4. an unmeasured figure is handed a direction and starts disagreeing",
     M / "demand_chain.py",
     'return DemandReading(company_id=company_id, state=state, direction="FLAT",\n'
     "                         standing=UNKNOWN)",
     'return DemandReading(company_id=company_id, state=state, direction="UP",\n'
     "                         standing=UNKNOWN)",
     f"{DT}::test_one_measured_figure_cannot_disagree_with_an_absent_one"),

    ("5. figures that agree are reported as disagreeing",
     M / "demand_tension.py",
     "        if left_sign == right_sign:\n            continue",
     "        if False:\n            continue",
     f"{DT}::test_two_figures_that_agree_are_not_a_tension"),

    ("6. a tension loses its innocent reading",
     M / "demand_tension.py",
     '        alternative="the cancellations are concentrated in one contract '
     'or "\n                    "one customer and say nothing about the rest '
     'of the pool",',
     '        alternative="",',
     f"{DT}::test_every_tension_carries_an_alternative_and_a_falsifier"),

    ("7. the summary flattens to a total",
     M / "demand_tension.py",
     '        "by_pair": by_pair,',
     '        "by_pair": {},',
     f"{DT}::test_the_summary_counts_by_pair_rather_than_in_total_only"),

    ("8. an overall demand verdict appears",
     M / "demand_tension.py",
     '        "note": ("two measured figures whose joint movement needs an "',
     '        "overall": "demand strong",\n'
     '        "note": ("two measured figures whose joint movement needs an "',
     f"{DT}::test_no_overall_demand_verdict_is_produced"),

    ("9. the block stops reaching the report",
     M / "report.py",
     '        "demand_tension": {\n'
     '            k: (knowledge.get("demand_tension") or {}).get(k)',
     '        "demand_tension_unprojected": {\n'
     '            k: (knowledge.get("demand_tension") or {}).get(k)',
     f"{RP}::test_every_required_key_survives_the_projection"),
]


if __name__ == "__main__":
    sys.exit(run_all(
        [Proof(*p) for p in PROOFS],
        title=(f"v4n — E-DEM-002, demand figures that disagree: "
               f"{len(PROOFS)} proofs")))
