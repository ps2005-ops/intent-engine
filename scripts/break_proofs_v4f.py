#!/usr/bin/env python3
"""Break proofs for the method assumption ledger and its wiring.

C-MET-002 and C-MET-004. The failure this wave guards is the quiet one: a
method runs, produces a number, and the number is read as an effect because
nothing recorded that the assumptions behind it were never tested. Listed
assumptions cannot fail, so a registry full of them looks exactly like a
registry that checks them.

    python3 scripts/break_proofs_v4f.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
S = ROOT / "src" / "intent_engine" / "market"

EM = S / "economic_method.py"
ST = S / "steps.py"
LS = S / "learning_store.py"

A = "tests/test_market_method_assumptions.py"

PROOFS = [
    # --- an assumption is tested, or it says it was not -------------------
    ("v4f-1. a critical assumption failure no longer blocks the causal read",
     EM,
     "        return self.result == FAILED and self.severity == CRITICAL",
     "        return False",
     f"{A}::test_a_failed_critical_assumption_refuses_the_causal_reading",
     "assert"),

    ("v4f-2. a design assumption no data can answer is counted as passing",
     EM,
     "                \"this is a statement about how the study was conducted, not \"\n                \"about the series; no test of the data can establish it\"))",
     "                \"assumed\"))",
     f"{A}::test_a_design_assumption_no_series_can_answer_is_untested_not_passed",
     "assert"),

    ("v4f-3. an assumption may be recorded as passing with no evidence",
     EM,
     "        if not self.evidence.strip():",
     "        if False:",
     f"{A}::test_an_assumption_check_must_state_its_evidence",
     "DID NOT RAISE"),

    ("v4f-4. only the testable assumptions are returned",
     EM,
     "        else:\n            # DESIGN ASSUMPTIONS, NOT DATA ASSUMPTIONS.",
     "        elif False:\n            # DESIGN ASSUMPTIONS, NOT DATA ASSUMPTIONS.",
     f"{A}::test_every_declared_assumption_comes_back_with_a_result",
     "assert"),

    # --- the statistic is the one the assumption is about ------------------
    ("v4f-5. stationarity is screened on a statistic the method does not fit",
     EM,
     "                beta = fit[1]",
     "                beta = _lag1_autocorrelation(values) or 0.0",
     f"{A}::test_stationarity_is_judged_on_the_coefficient_the_method_fits",
     "assert"),

    ("v4f-6. a unit root passes the stationarity screen",
     EM,
     "                    FAILED if beta >= _UNIT_ROOT_RHO else PASSED,",
     "                    PASSED,",
     f"{A}::test_a_random_walk_fails_the_stationarity_assumption",
     "assert"),

    ("v4f-7. residual autocorrelation is measured on walk-forward errors",
     EM,
     "                residuals = [values[i + 1] - (alpha + beta * values[i])\n                             for i in range(len(values) - 1)]",
     "                residuals = [values[i] - _ar1(values[:i])\n                             for i in range(3, len(values))]",
     f"{A}::test_one_lag_is_judged_on_in_sample_residuals_not_forecast_errors",
     "assert"),

    ("v4f-8. persistence is never told it is leaving a drift on the table",
     EM,
     "                    FAILED if share >= _DRIFT_IMBALANCE else PASSED,\n                    f\"{share:.2%} of {len(steps)} steps share one sign; at or \"",
     "                    PASSED,\n                    f\"{share:.2%} of {len(steps)} steps share one sign; at or \"",
     f"{A}::test_persistence_is_told_when_it_is_leaving_a_drift_on_the_table",
     "assert"),

    # --- what may be said afterwards ---------------------------------------
    ("v4f-9. a sixteen-prediction win is promoted to a result",
     EM,
     "    elif predictions is not None and predictions < _MINIMUM_OUT_OF_SAMPLE:",
     "    elif False:",
     f"{A}::test_a_win_on_too_few_predictions_is_bounded_not_useful",
     "assert"),

    ("v4f-10. an untestable critical assumption is treated as holding",
     EM,
     "    elif untested_critical:",
     "    elif False:",
     f"{A}::test_an_untestable_critical_assumption_bounds_rather_than_passes",
     "assert"),

    ("v4f-11. a refused causal reading discards the descriptive estimate",
     EM,
     "        \"descriptive_result_retained\": True,",
     "        \"descriptive_result_retained\": False,",
     f"{A}::test_a_refused_reading_still_keeps_the_descriptive_result",
     "assert"),

    ("v4f-12. not beating the baseline is reported as success",
     EM,
     "    elif beat_baseline is False:",
     "    elif False:",
     f"{A}::test_a_method_that_did_not_beat_the_baseline_is_a_result_not_a_failure",
     "assert"),

    # --- the cycle measures it, and the ledger keeps it --------------------
    ("v4f-13. the cycle computes method scores and never persists them",
     ST,
     "            if store.record_method_performance(",
     "            if False and store.record_method_performance(",
     f"{A}::test_a_fresh_process_reads_back_what_the_cycle_scored",
     "assert"),

    ("v4f-14. assumption checks are computed and never persisted",
     ST,
     "            if store.record_method_assumption_check(check):",
     "            if False:",
     f"{A}::test_the_cycle_scores_the_series_it_holds",
     "assert"),

    ("v4f-15. the cycle rescores the same date and appends again",
     LS,
     "        if key in held:\n            return False\n        self._append(METHOD_PERFORMANCE, payload)",
     "        if False:\n            return False\n        self._append(METHOD_PERFORMANCE, payload)",
     f"{A}::test_running_the_same_date_twice_appends_no_second_measurement",
     "assert"),

    ("v4f-16. a score is stored without the date it was measured on",
     LS,
     "        payload[\"measured_as_of\"] = as_of",
     "        payload[\"measured_as_of\"] = \"\"",
     f"{A}::test_a_fresh_process_reads_back_what_the_cycle_scored",
     "assert"),

    ("v4f-17. scoring reads figures published after the cycle date",
     ST,
     "    known = MS.as_known_at(observations, as_of)",
     "    known = list(observations)",
     f"{A}::test_the_scoring_never_reads_a_figure_published_after_the_cycle_date",
     "assert"),

    ("v4f-18. a series too short to score is scored anyway",
     ST,
     "        if len(ordered) < _METHOD_MIN_SERIES:",
     "        if False:",
     f"{A}::test_a_series_too_short_to_score_is_counted_not_scored",
     "assert"),

    # v4f-19 REMOVED, and the code it broke with it. The proof came back
    # NOT_CAUGHT: it broke a second dedupe of (series_id, reference_period)
    # inside `_evaluate_methods`, and `macro_state.as_known_at` already keeps
    # the latest publication per period, so the fold could not fire on any
    # input the function can receive. The honest response to an unreachable
    # guard is to delete it, not to find a test that appears to cover it.
    # --- the block that never ran ------------------------------------------
    ("v4f-20. the delayed-reward block loses its import again",
     ST,
     "            from . import research_decision as RD\n",
     "",
     "tests/test_market_thesis_history_wiring.py"
     "::test_the_delayed_reward_block_actually_runs",
     "assert"),

    ("v4f-21. a knowledge block fails silently into an error string",
     ST,
     "            delayed, delayed_summary = RD.credit_revisions(",
     "            delayed, delayed_summary = RD.credit_revisions_typo(",
     "tests/test_market_thesis_history_wiring.py"
     "::test_no_knowledge_block_reports_an_error_on_ordinary_data",
     "failed silently"),
    # --- the rows a reconstructed log cannot hold --------------------------
    #
    # Production has written twelve outcomes and every one is SUCCESS. These
    # break the seam that would have to work for a thirteenth to be anything
    # else, because the classifier being unit-tested proves the classifier and
    # not the write.
    ("v4f-22. a sweep that found nothing is recorded as a success",
     ST,
     "            status=_acquisition_status(report, integrated=integrated),",
     "            status=RD.SUCCESS,",
     "tests/test_market_unsuccessful_research_outcomes.py"
     "::test_a_sweep_that_retrieves_nothing_is_NO_RESULT",
     # Caught by DecisionOutcome's own invariant rather than by the test's
     # assert, which is the stronger place for it to be caught: the record
     # refuses to exist rather than the test noticing afterwards.
     "calling it success"),

    ("v4f-23. an empty-handed outcome never reaches disk",
     ST,
     "        store.record_research_outcome(RD.DecisionOutcome(\n            decision_id=decision.decision_id,\n            status=_acquisition_status(report, integrated=integrated),",
     "        _unused = (RD.DecisionOutcome(\n            decision_id=decision.decision_id,\n            status=_acquisition_status(report, integrated=integrated),",
     "tests/test_market_unsuccessful_research_outcomes.py"
     "::test_a_no_result_row_survives_a_process_that_did_not_write_it",
     "assert"),

    ("v4f-24. an unreachable source is recorded as having found nothing",
     ST,
     "        return RD.FAILED if report.errors else RD.NO_RESULT",
     "        return RD.NO_RESULT",
     "tests/test_market_unsuccessful_research_outcomes.py"
     "::test_a_source_that_raises_writes_a_FAILED_outcome",
     "assert"),

    # v4f-25 REMOVED. It broke `integrated = report.verdict()[0] ==
    # INTEGRATE`, and came back NOT_CAUGHT because the paired fixture accepts
    # zero relationships: `accepted_evidence` is 0 whether or not `integrated`
    # is forced true, so the mutation cannot change the recorded status.
    # Catching it needs a fixture where relationships ARE accepted while the
    # measured verdict withholds integration. Recorded rather than repointed
    # at a test that would pass for the wrong reason.
]


if __name__ == "__main__":
    sys.exit(run_all([Proof(*p) for p in PROOFS], title="V4f"))
