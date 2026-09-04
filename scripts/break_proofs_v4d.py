#!/usr/bin/env python3
"""Break proofs for the prospective-research and executor guards.

A guard that has never been shown to fail is a guard nobody has tested. Last
session four of twenty-one mutations came back NOT_CAUGHT, and each named a
real test that did not discriminate what it claimed to.

Each proof breaks ONE guard and names the test that must go RED for it. The
harness holds a mutation lock, verifies the file hash changed, requires the
named test to fail for the stated reason, restores the exact bytes, and clears
the bytecode — a same-length edit restored in place otherwise leaves CPython
running the mutated module.

    python3 scripts/break_proofs_v4d.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
S = ROOT / "src" / "intent_engine" / "market"

RD = S / "research_decision.py"
RP = S / "research_policy.py"
VG = S / "vintage.py"
EM = S / "economic_method.py"
TH = S / "thesis_history.py"
ST = S / "steps.py"
LS = S / "learning_store.py"

D = "tests/test_market_research_decision.py"
W = "tests/test_market_research_decision_wiring.py"
P = "tests/test_market_research_policy.py"
V = "tests/test_market_vintage.py"
M = "tests/test_market_economic_method.py"
H = "tests/test_market_thesis_history.py"

PROOFS = [
    # --- the prospective log's own invariants ---------------------------
    ("v4d-1. a chosen action need not be in its own candidate set",
     RD,
     "        if not chosen:",
     "        if False:",
     f"{D}::test_a_chosen_action_must_be_in_its_own_candidate_set"),

    ("v4d-2. an ineligible option may be recorded as the choice",
     RD,
     "        if not chosen[0].eligible:",
     "        if False:",
     f"{D}::test_a_chosen_action_recorded_as_ineligible_is_refused"),

    ("v4d-3. a deterministic policy may invent a propensity",
     RD,
     "        if status != KNOWN and self.selection_probability is not None:",
     "        if False:",
     f"{D}::test_a_deterministic_policy_may_not_claim_a_propensity"),

    ("v4d-4. an empty action may be recorded as a success",
     RD,
     "        if self.status == SUCCESS and not self.accepted_evidence:",
     "        if False:",
     f"{D}::test_success_with_no_accepted_evidence_is_refused"),

    ("v4d-5. an outcome may predate the decision that produced it",
     RD,
     "        if started and chosen and started < chosen:",
     "        if False:",
     f"{D}::test_an_outcome_may_not_start_before_its_decision_was_written"),

    ("v4d-6. a failure need not name its kind",
     RD,
     "        if self.status in (FAILED, TIMEOUT) and not self.failure_type:",
     "        if False:",
     f"{D}::test_a_failure_must_name_its_kind"),

    ("v4d-7. an excluded candidate need not say why",
     RD,
     "        if not self.eligible and not self.refusal_reason:",
     "        if False:",
     f"{D}::test_an_excluded_candidate_must_say_why"),

    ("v4d-8. a reconstructed row loses its mark crossing the bridge",
     RD,
     "        reconstructed=decision.provenance == RECONSTRUCTED,",
     "        reconstructed=False,",
     f"{D}::test_a_reconstructed_row_keeps_its_mark_through_the_bridge"),

    ("v4d-9. a deterministic prospective log is offline-evaluable",
     RD,
     '        standing, why = "REPLAY_ONLY", (',
     '        standing, why = "OFFLINE_EVALUABLE", (',
     f"{D}::test_a_deterministic_prospective_log_is_replay_only"),

    # --- the store refuses the rows that reintroduce the bias -----------
    ("v4d-10. an outcome may be written with no prior decision",
     LS,
     "        if did not in self.research_decision_ids():",
     "        if False:",
     f"{W}::test_an_outcome_without_a_prior_decision_is_refused"),

    # --- the choice set reaches policy evaluation -----------------------
    ("v4d-11. a policy is scored against every family regardless of the menu",
     RP,
     "        available = list(record.eligible_options or options)",
     "        available = list(options)",
     f"{P}::test_the_recorded_menu_can_make_a_preferred_family_unreachable"),

    ("v4d-12. an assumed menu counts as a real one",
     RP,
     "        return self.total > 0 and self.assumed_menu < self.total",
     "        return True",
     f"{P}::test_a_score_built_only_on_assumed_menus_has_no_real_menu"),

    # --- the vintage wall ------------------------------------------------
    ("v4d-13. a row observed after the wall is admitted",
     VG,
     "        if seen > self.as_of:",
     "        if False:",
     f"{V}::test_checking_a_future_row_raises_rather_than_filtering"),

    ("v4d-14. admission uses occurrence time instead of observation time",
     VG,
     "        seen = observation_time(row)\n        if not seen:\n            undated.append(row)",
     "        seen = occurrence_time(row)\n        if not seen:\n            undated.append(row)",
     f"{V}::test_a_row_that_happened_before_but_was_observed_after_is_withheld"),

    ("v4d-15. an undated row is admitted rather than excluded",
     VG,
     "        if not seen:\n            raise VintageViolation(",
     "        if False:\n            raise VintageViolation(",
     f"{V}::test_an_undated_row_cannot_be_placed_against_the_wall"),

    ("v4d-16. the wall may be moved forward",
     VG,
     "        if target > self.as_of:",
     "        if False:",
     f"{V}::test_moving_the_wall_forward_is_refused"),

    # --- the method registry ---------------------------------------------
    ("v4d-17. an unimplemented method silently falls back",
     EM,
     "    if not method.implemented:",
     "    if False:",
     f"{M}::test_a_declared_but_unimplemented_method_is_refused_not_downgraded"),

    ("v4d-18. methods are scored on their own training windows",
     EM,
     "    window = max(m.minimum_sample for m in usable)",
     "    window = min(m.minimum_sample for m in usable)",
     f"{M}::test_all_methods_are_scored_on_one_training_window"),

    ("v4d-19. a method below its minimum sample runs anyway",
     EM,
     "    if sample < method.minimum_sample:",
     "    if False:",
     f"{M}::test_a_method_below_its_minimum_sample_is_refused"),

    # --- the acquisition seam --------------------------------------------
    ("v4d-20. a family that retrieved nothing is not distinguished from one "
     "that failed",
     ST,
     "        return RD.FAILED if report.errors else RD.NO_RESULT",
     "        return RD.NO_RESULT",
     f"{W}::test_a_family_that_reached_nothing_and_errored_is_a_failure"),

    ("v4d-21. a company-published family is recorded as an independent one",
     RD,
     '    "customer_case_study": "company_owned",',
     '    "customer_case_study": "independent_reporting",',
     f"{W}::test_a_company_published_family_is_not_recorded_as_independent"),

    # --- thesis history --------------------------------------------------
    ("v4d-23. a transition may be explained by prose alone",
     TH,
     "        if self.transition != CREATED and not caused:",
     "        if False:",
     f"{H}::test_a_transition_explained_only_by_prose_is_refused"),

    ("v4d-24. a claim may be strengthened without an effect",
     TH,
     "        if self.transition in UPWARD and not self.knowledge_effect_ids:",
     "        if False:",
     f"{H}::test_strengthening_on_evidence_alone_is_refused"),

    ("v4d-25. an alternative may vanish without a named cause",
     TH,
     "        if dropped and not caused:",
     "        if False:",
     f"{H}::test_an_alternative_may_not_vanish_without_a_named_cause"),

    ("v4d-26. the revision chain may fork silently",
     TH,
     "        if revision.previous_revision != current:",
     "        if False:",
     f"{H}::test_a_revision_whose_parent_is_not_the_head_is_refused"),

    ("v4d-27. any effect on the same company evidences any thesis",
     TH,
     "        elif target_id and target_id in basis:",
     "        elif target_id:",
     f"{H}::test_an_effect_on_another_object_does_not_evidence_this_thesis"),

    # v4d-28 RETIRED, NOT DROPPED. It broke `thesis_history.identity` when
    # that function assembled `(subject, question)` itself. G-THE-004 moved
    # identity to its only correct home, `EconomicThesis.thesis_id`, and
    # `identity` now returns it rather than recomputing a coarser version.
    # The same guarantee — a reworded claim is the same thesis — is proved at
    # the new site by v4e-2 in break_proofs_v4e.py. Left as a comment because
    # a proof whose anchor has moved reports ANCHOR_MISSING, which is
    # indistinguishable from a proof somebody broke.

    ("v4d-29. a strengthening with no bearing effect is recorded as stronger",
     TH,
     "        if transition in UPWARD and not bearing:",
     "        if False:",
     f"{H}::test_a_strengthening_with_no_bearing_effect_is_not_recorded_as_stronger"),

    ("v4d-30. an unchanged thesis records a revision every cycle",
     TH,
     "        if not changed:",
     "        if False:",
     f"{H}::test_an_unchanged_thesis_records_no_revision"),

    ("v4d-31. an untraceable revision credits every action that night",
     RD,
     "        if not matched:",
     "        if False:",
     f"{D}::test_an_untraceable_revision_credits_nobody"),

    ("v4d-22. attribution is computed and not persisted",
     ST,
     "                if store.record_knowledge_effect(effect):",
     "                if False:",
     f"{W}::test_the_knowledge_step_persists_the_attributions_it_computes"),
]


if __name__ == "__main__":
    sys.exit(run_all([Proof(*p) for p in PROOFS], title="V4d"))
