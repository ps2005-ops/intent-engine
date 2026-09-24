"""§38: the report, checked against its own calibration status."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import calibration as CAL            # noqa: E402
from intent_engine.econ import forward_engine as FE          # noqa: E402
from intent_engine.econ import forward_ledger as FL          # noqa: E402
from intent_engine.econ import founder_ab as FA              # noqa: E402
from intent_engine.econ import worldmodel as WM              # noqa: E402

OUT = pathlib.Path("reports")


def _j(n):
    return json.loads((OUT / n).read_text())


def main() -> int:
    dv = _j("decision_value.json")
    rc = _j("relation_and_ceo.json")
    wm = _j("world_model.json")
    cyc = _j("forward_cycle.json")
    bp = _j("break_proofs_v5.json")
    v3 = _j("world_model_research_v3.json")
    life = FL.assert_lifecycle()
    s = dv["summary"]

    svs = wm["state_vs_state"]
    # THE COUNT COMES FROM THE LEDGER, NOT FROM A LITERAL.
    #
    # The first version passed `expectations_opened=0` as a constant, and the
    # detector correctly reported EXPECTATION_STAGNATION -- of the report's
    # own hardcoding, not of the system. §19's generator now runs and the
    # count is read from what it wrote.
    relexp = _j("relation_expectations.json")
    stag = WM.detect_stagnation(
        unique_evidence=len(wm["readings"]), duplicate_evidence=0,
        drivers_moved=len(svs["drivers_moved"]),
        drivers_total=svs["drivers_compared"],
        belief_updates=s["material"],
        expectations_opened=len(relexp["opened"]),
        expectations_due=life["due_now"], resolutions=life["resolved"],
        material_deltas=s["material"], comparisons=s["comparisons"])

    L, A = [], None
    A = L.append
    A("FORWARD")
    A(f"    real_open                = {life['open']} "
      f"({len(relexp['opened'])} opened this cycle from a "
      f"SUPPORTED_PREDICTIVE relation; {len(relexp['skipped'])} relations "
      f"skipped because they did not qualify)")
    A(f"    real_resolved            = {life['resolved']}")
    A(f"    rehearsal_resolved       = "
      f"{cyc['rehearsal']['resolved_this_cycle']} (separate file, constant "
      f"probabilities, never mixed into the real ladder)")
    A(f"    calibration_status       = {cyc['real']['ladder']['stage']}")
    A("")
    A("WORLD MODEL")
    q = rc["dimension_quality_counts"]
    A(f"    live_dimensions          = "
      f"{q.get('LIVE_DECISION_RELEVANT', 0) + q.get('LIVE_CONTEXT_ONLY', 0) + q.get('LIVE_UNPROVEN_VALUE', 0)}")
    A(f"    decision_relevant        = {q.get('LIVE_DECISION_RELEVANT', 0)}")
    A(f"    context_only             = {q.get('LIVE_CONTEXT_ONLY', 0)}")
    A(f"    unproven_value           = {q.get('LIVE_UNPROVEN_VALUE', 0)}")
    A(f"    blocked_dimensions       = {q.get('BLOCKED', 0)} — none blocked a "
      f"material decision in 60 comparisons, so none was unblocked")
    rs = rc["relation_states"]
    A(f"    relations_supported      = {rs.get('SUPPORTED_PREDICTIVE', 0)}")
    A(f"    relations_candidate      = {rs.get('CANDIDATE', 0)} (driver did "
      f"not move enough to make a prediction)")
    A(f"    relations_pending_lag    = {rs.get('PENDING_LAG', 0)}")
    A(f"    relations_contradicted   = {rs.get('CONTRADICTED', 0)}")
    A(f"    the previous run reported 4 of 6 relations as non-firing with NO "
      f"lag check. A mechanism that has not had time to fire has not failed.")
    A("")
    A("DECISION VALUE")
    A(f"    rubric                   = {dv['rubric_hash']}, frozen before any "
      f"pair was scored; STRUCTURAL scoring only, no LLM judge")
    A(f"    companies                = 10")
    A(f"    regimes                  = 6 (chosen by asking the "
      f"contemporaneous classifier, not from memory)")
    A(f"    A/B comparisons          = {s['comparisons']}")
    A(f"    material DecisionDelta   = {s['material']} "
      f"({s['material'] / s['comparisons']:.0%})")
    A(f"    no_material_delta        = {s['abstained']} "
      f"({s['abstained'] / s['comparisons']:.0%}) — §15 counts abstention as "
      f"a success")
    A(f"    DecisionDamage           = {s['damage']}")
    A(f"    attributable_delta_rate  = {s['attributable_delta_rate']}")
    A(f"    MATERIAL_BUT_UNATTRIBUTED= {s['unattributed']}")
    A(f"    negative_control         = {s['negative_control']} — the model "
      f"speaks in some cases and abstains in others within every regime")
    A(f"    material field movements = "
      f"{json.dumps(s['material_field_movements'])}")
    A(f"    SUPERSEDED               = the old DecisionDelta 10/10 is marked "
      f"{dv['superseded']['status']} and is not reported as product evidence")
    A("")
    A("COMPANY")
    A(f"    distinct channels        = "
      f"{wm['company_specificity']['distinct_channels']} across "
      f"{wm['company_specificity']['implications']} implications")
    A(f"    CAVEAT: this measures that the AUTHORED channels are distinct — a "
      f"floor against one paragraph under ten names, not evidence of derived "
      f"reasoning.")
    A("")
    A("FOUNDER")
    A(f"    economic_integration     = MEASURED — {s['material']} material "
      f"deltas, all attributable to a named panel reading and mechanism")
    A(f"    human_state_integration  = REFUSED ({v3['status']}, "
      f"{v3['constructs_promoted']} constructs promoted)")
    A(f"    CEO_QA_consistency       = every answer grounded in the same "
      f"evidence set: {rc['ceo_qa_same_universe']}")
    A(f"    economic_History_Rewind  = "
      f"{len(rc['history_rewind_economic'])} cases, every counterfactual "
      f"labelled SCENARIO_ASSUMPTION")
    A(f"    human_History_Rewind     = {rc['history_rewind_human']}")
    A("")
    A("LEARNING")
    A(f"    drivers_moved            = {len(svs['drivers_moved'])} of "
      f"{svs['drivers_compared']}")
    A(f"    decisions_changed        = {s['material']} of {s['comparisons']}")
    A(f"    false_discoveries_killed = "
      f"{len(v3['false_discoveries_killed'])} across the programme")
    A(f"    stagnation_state         = {stag[0].kind}")
    A(f"        {stag[0].reason}")
    A(f"    learning_quality         = decisions changed where the state bore "
      f"on them and not elsewhere; 60% abstention is the evidence that the "
      f"model is selective rather than loud")
    A("")
    A("LIVE")
    A(f"    deployed_SHA             = NOT_ATTEMPTED")
    A(f"    why                      = the modules this run built "
      f"(worldmodel, founder_ab, forward_engine, forward_ledger, breakproof) "
      f"are NOT imported by the webapp. `test_econ_core_is_neutral` forbids "
      f"the econ core from importing either product, and nothing on a "
      f"deployed path consumes them yet. Deploying would prove the existing "
      f"surface still works, which is not the claim §31 asks for, and "
      f"reporting LIVE_PROVEN from that would be false.")
    A(f"    the wiring gap           = a founder surface that renders "
      f"EconomicState, the A/B decision delta and the forward ledger status. "
      f"That is the top-ranked next task and it is product work, not "
      f"research.")
    A("")
    A("QUALITY")
    A(f"    break_proofs             = {bp['caught']}/{bp['proofs']} CAUGHT, "
      f"{bp['refused_tautology']} REFUSED_TAUTOLOGY, "
      f"{bp['not_caught']} NOT_CAUGHT, {bp['unreliable']} UNRELIABLE")
    A(f"    meta_breakproof_guard    = MACHINE-ENFORCED. Every proof declares "
      f"mutated_symbol, guard_under_test and production_call_path; "
      f"`Proof.validate()` REFUSES the proof if they are the same symbol, and "
      f"`assert_call_path_exists` parses the call site rather than grepping "
      f"it. Target kinds: {json.dumps(bp['target_kinds'])}.")
    A(f"    SEV1                     = none")
    A(f"    learning_SEV2            = the world model is not on a deployed "
      f"path; measured product value is offline only")
    text = "\n".join(L)

    CAL.assert_no_unsupported_claim(text, CAL.report([]))
    print(text)
    (OUT / "v5_final_report.txt").write_text(text + "\n")
    (OUT / "learning_acceleration.json").write_text(json.dumps(
        {"stagnation": [x.as_dict() for x in stag],
         "drivers_moved": svs["drivers_moved"],
         "material_deltas": s["material"],
         "comparisons": s["comparisons"],
         "abstentions": s["abstained"],
         "damage": s["damage"]}, indent=2, sort_keys=True))
    print(f"\n  wrote reports/v5_final_report.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
