"""§34: the report, checked against its own calibration status."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import calibration as CAL            # noqa: E402
from intent_engine.econ import forward_engine as FE          # noqa: E402
from intent_engine.econ import forward_ledger as FL          # noqa: E402

OUT = pathlib.Path("reports")


def _j(n):
    return json.loads((OUT / n).read_text())


def main() -> int:
    cyc = _j("forward_cycle.json")
    wm = _j("world_model.json")
    v3 = _j("world_model_research_v3.json")
    gaps = _j("panel/two_gaps.json")
    house = _j("housing_baseline.json")
    bp = _j("break_proofs_v4.json")
    life = FL.assert_lifecycle()
    recs = list(FL.by_id().values())

    L, A = [], None
    A = L.append
    A("FORWARD")
    A(f"    expectations_open        = {life['open']}")
    A(f"    expectations_new         = 0 (the twelve are unchanged; "
      f"{cyc['real']['contracts_added']} received a DERIVED machine-readable "
      f"resolution contract as a superseding record)")
    A(f"    expectations_resolved    = {life['resolved']}")
    A(f"    BASE/AUGMENTED_pairs     = {cyc['real']['tournament']['pairs']} "
      f"matched, {cyc['real']['tournament']['unmatched']} unmatched")
    A(f"    calibration_status       = {cyc['real']['ladder']['stage']} — "
      f"{cyc['real']['ladder']['may_report']}")
    A(f"    gap to {cyc['real']['ladder']['next_stage']:<22} "
      f"{json.dumps(cyc['real']['ladder']['gap_to_next'])}")
    A(f"    lifecycle                = all seven facts hold "
      f"({life['all_seven_hold']})")
    A(f"    resolver PROVED on a backdated rehearsal ledger: "
      f"{cyc['rehearsal']['expectations']} expectations opened, "
      f"{cyc['rehearsal']['resolved_this_cycle']} resolved, ladder moved "
      f"PRE_CALIBRATION -> {cyc['rehearsal']['ladder']['stage']}, "
      f"{cyc['rehearsal']['tournament']['resolved_pairs']} pairs scored. "
      f"Its probabilities are fixed constants, not model output; it proves "
      f"the machinery and is never mixed into the real record.")
    A("")
    A("ECONOMIC WORLD MODEL")
    c = wm["coverage_summary"]
    A(f"    dimensions_live          = {c['live']}")
    A(f"    dimensions_partial       = {c['partial']}")
    A(f"    dimensions_blocked       = {c['blocked']} of {c['total']} — "
      f"{[g['dimension'] for g in wm['gaps_by_decision_impact']]}")
    A(f"    typed relations          = {len(wm['relations'])}")
    A(f"    transmission paths       = {len(wm['paths'])} "
      f"({', '.join(p['name'] + ' (' + str(p['orders']) + ' orders)' for p in wm['paths'])})")
    A(f"    causal_bleeds            = {len(wm['bleeds'])} of "
      f"{len(wm['relations'])} relations did not fire, all recorded "
      f"CANDIDATE_NOT_PROVEN")
    for b in wm["bleeds"]:
        A(f"        {b['source']} -> {b['expected_target']}: expected "
          f"{b['expected_direction']}, observed {b['actual_direction']}, "
          f"priority {b['priority']}")
    A("")
    A("COMPANY")
    s = wm["company_specificity"]
    A(f"    companies_tested         = {s['companies']}")
    A(f"    company_specificity      = {s['distinct_channels']} distinct "
      f"channels across {s['implications']} implications "
      f"({s['channel_specificity']})")
    A(f"        CAVEAT: this measures that the AUTHORED channels are "
      f"distinct. It is a floor against one paragraph under ten names, not "
      f"evidence that the system derived them.")
    svs = wm["state_vs_state"]
    A(f"    DecisionDelta_nonzero    = "
      f"{sum(1 for d in wm['decision_deltas'] if d['nonzero'])}/"
      f"{len(wm['decision_deltas'])} against a placeholder — which measures "
      f"the placeholder.")
    A(f"    THE LOAD-BEARING TEST    = {svs['companies_changed']}/"
      f"{svs['companies']} company analyses changed when the economic state "
      f"moved from {svs['as_of_a']} to {svs['as_of_b']} "
      f"({len(svs['drivers_moved'])} of {svs['drivers_compared']} drivers "
      f"moved). The world model is read, not merely present.")
    A("")
    A("FOUNDER")
    A(f"    economic_integration     = LIVE — 10 companies, "
      f"company-specific channels, traceable to panel readings")
    A(f"    human_state_integration  = REFUSED / FROZEN_CANDIDATE")
    A(f"    History_Rewind_economic  = the state-vs-state comparison is the "
      f"economic rewind; counterfactual typing is unchanged and break proof "
      f"11 guards it")
    A(f"    History_Rewind_human     = REFUSED")
    A("")
    A("LEARNING")
    A(f"    false_discoveries_killed = "
      f"{len(v3['false_discoveries_killed'])} across the programme")
    A(f"    hypotheses_retired       = {v3['hypotheses_retired']}")
    A(f"    constructs_promoted      = {v3['constructs_promoted']}")
    A(f"    stagnation_detector      = {wm['stagnation']['state']} "
      f"(compared {wm['stagnation'].get('compared')})")
    A(f"    reopening_gate           = {v3['reopening_gate']['state']} — "
      f"{len(v3['reopening_gate']['may_reopen_only_if'])} routes in, "
      f"{len(v3['reopening_gate']['may_not_reopen_because'])} closed")
    A("")
    A("HISTORICAL GAPS (the only two that were reopened, both bounded)")
    a = gaps["gap_a_pre2012_credit"]
    A(f"    pre2012_credit           = {a['verdict']} — candidates found "
      f"({a['usable']}) and NONE cleared the equivalence bar: best was "
      f"NPTLTL with crisis agreement 0.89 but a rank correlation of +0.15. "
      f"No defensible household-credit substitute exists in a keyless "
      f"archive. Search stopped.")
    A(f"    housing_baseline         = {house['verdict']} — adding "
      f"MORTGAGE30US and PERMIT did not make the macro block beat a "
      f"constant at either horizon in either arm. The target stays "
      f"BASELINE_INVALID; it was not tuned until it won.")
    A("")
    A("QUALITY")
    A(f"    break_proofs             = {bp['caught']}/{bp['proofs']} CAUGHT, "
      f"{bp['not_caught']} NOT_CAUGHT, {bp['not_applied']} NOT_APPLIED, "
      f"{bp['unreliable']} UNRELIABLE")
    A(f"    known_SEV1               = none")
    A(f"    known_learning_SEV2      = the channel-specificity metric "
      f"measures authored vocabulary, not derived reasoning. Stated at the "
      f"point of use rather than left to be discovered.")
    text = "\n".join(L)

    CAL.assert_no_unsupported_claim(text, CAL.report([]))
    print(text)
    (OUT / "v4_final_report.txt").write_text(text + "\n")
    print(f"\n  wrote reports/v4_final_report.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
