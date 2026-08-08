"""Break proofs for wave 4: decay, chains, counterfactuals, calibration,
acceleration quality, source acquisition, and the LLM boundary.

A PROOF ONLY COUNTS IF IT GOES RED
----------------------------------
Every entry below mutates the source so a self-flattering behaviour becomes
true, then runs the ONE test paired with it and requires a FAILURE. "I
mutated something and the suite stayed green" is not a passing proof; it is
evidence that either the guard or the proof is not load-bearing. Wave 3 found
three bad pairings and one test that could not fail that way, so the harness
reports each outcome separately rather than as a single count.

Restore bumps mtime. A same-length restore leaves CPython running cached
bytecode whose size and hash still match, and the next proof then measures
the previous proof's mutation.
"""
from __future__ import annotations
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

S = ROOT / "src/intent_engine/market"
T = "tests"

PROOFS = [
    # --- knowledge decay --------------------------------------------------
    ("1. a belief never decays",
     S / "knowledge_decay.py",
     "    if since is None or since < cadence:",
     "    if True:",
     f"{T}/test_market_knowledge_decay.py::test_closed_window_past_cadence_is_stale"),

    ("2. stale becomes contradicted (a tested belief is called stale)",
     S / "knowledge_decay.py",
     "    if my_tests:",
     "    if False:",
     f"{T}/test_market_knowledge_decay.py::test_a_tested_belief_is_never_stale_however_old"),

    ("3. contradicted becomes stale (decay ignores the open window)",
     S / "knowledge_decay.py",
     "    if window and not window_closed:",
     "    if False:",
     f"{T}/test_market_knowledge_decay.py::test_open_expectation_window_blocks_decay_however_old"),

    ("4. one global threshold replaces the family's own cadence",
     S / "knowledge_decay.py",
     "def _cadence(belief: dict) -> int:\n    raw = belief.get(\"review_interval_days\")",
     "def _cadence(belief: dict) -> int:\n    return 90\n    raw = belief.get(\"review_interval_days\")",
     f"{T}/test_market_knowledge_decay.py::test_two_families_of_the_same_age_decay_differently"),

    ("5. retirement needs only one missed window",
     S / "knowledge_decay.py",
     "    if since >= cadence * RETIRE_AFTER_INTERVALS:",
     "    if True:",
     f"{T}/test_market_knowledge_decay.py::test_retirement_needs_two_full_refresh_windows"),

    ("6. a lifecycle event rewrites the belief row",
     S / "learning_store.py",
     "    def record_lifecycle(self, event) -> bool:",
     "    def record_lifecycle(self, event) -> bool:\n"
     "        self.path.write_text('')",
     f"{T}/test_market_knowledge_step.py::test_a_lifecycle_event_never_edits_the_belief_row"),

    # --- economic chain ----------------------------------------------------
    ("7. an UNKNOWN chain link becomes a fact",
     S / "economic_chain.py",
     "    if source.status == UNKNOWN or target.status == UNKNOWN:",
     "    if False:",
     f"{T}/test_market_economic_chain.py::test_an_unknown_end_makes_the_link_unknown"),

    ("8. a causal link claims to have been OBSERVED",
     S / "economic_chain.py",
     "        status = SUPPORTED\n        evidence = discriminating_test",
     "        status = OBSERVED\n        evidence = discriminating_test",
     f"{T}/test_market_economic_chain.py::test_no_link_constructor_can_produce_observed"),

    ("9. a node is asserted without evidence",
     S / "economic_chain.py",
     "        status=(KNOWN if ids else UNKNOWN), evidence_ids=ids,",
     "        status=KNOWN, evidence_ids=ids,",
     f"{T}/test_market_economic_chain.py::test_a_node_with_no_evidence_is_unknown"),

    # --- counterfactual memory --------------------------------------------
    ("10. the counterfactual alternative is deleted",
     S / "counterfactual_memory.py",
     "    if not alternative.strip():",
     "    if False:",
     f"{T}/test_market_counterfactual_memory.py::test_an_episode_with_no_alternative_is_refused"),

    ("11. an alternative that predicts the same thing is admitted",
     S / "counterfactual_memory.py",
     "    if left == right:",
     "    if False:",
     f"{T}/test_market_counterfactual_memory.py::test_an_alternative_that_expects_the_same_thing_is_refused"),

    ("12. a fabricated alternative fills in for a family with none",
     S / "counterfactual_memory.py",
     "        if not alternative:\n            # No stated alternative",
     "        if not alternative:\n"
     "            alternative = ('it was a one-off', 'x', 'y')\n"
     "        if False:\n            # No stated alternative",
     f"{T}/test_market_counterfactual_memory.py::test_a_family_with_no_stated_alternative_produces_no_episode"),

    # --- causal calibration -------------------------------------------------
    # The real ledger's five reconciliations are ALL informative, so `if
    # True` changes nothing when measured against it. The guard is only
    # load-bearing where a non-informative row exists, which is what this
    # test supplies.
    ("13. causal calibration counts an uninformative row as a test",
     S / "causal_calibration.py",
     "        if row.get(\"outcome\") in _INFORMATIVE:",
     "        if True:",
     f"{T}/test_market_causal_calibration.py::test_an_uninformative_reconciliation_is_not_a_test"),

    # EMERGING at 3 tests / 3 companies is held by TWO independent
    # thresholds, so mutating either one alone leaves it green. What is
    # actually load-bearing is that the thresholds are ORDERED, and this
    # mutation inverts that ordering.
    ("14. the ladder stops being monotone in sample size",
     S / "causal_calibration.py",
     "MIN_TESTS_FOR_REPEATED = 8",
     "MIN_TESTS_FOR_REPEATED = 4",
     f"{T}/test_market_causal_calibration.py::test_the_ladder_is_monotone_in_sample_size"),

    ("15. one company agreeing with itself earns SUPPORTED",
     S / "causal_calibration.py",
     "    if companies < MIN_COMPANIES_FOR_SUPPORTED or \\\n            tests < MIN_TESTS_FOR_SUPPORTED:",
     "    if False:",
     f"{T}/test_market_causal_calibration.py::test_one_company_agreeing_with_itself_never_reaches_supported"),

    ("16. a known exception is rounded up to 'mostly holds'",
     S / "causal_calibration.py",
     "    if contradicted and CONTESTED_ON_ANY_CONTRADICTION:",
     "    if False:",
     f"{T}/test_market_causal_calibration.py::test_any_contradiction_above_the_floor_makes_it_contested"),

    # --- acceleration quality ------------------------------------------------
    ("17. duplicate evidence counted as new knowledge",
     S / "learning_acceleration.py",
     "        \"unique_evidence\": accepted,",
     "        \"unique_evidence\": accepted + duplicates,",
     f"{T}/test_market_learning_acceleration.py::test_duplicate_evidence_does_not_raise_new_knowledge"),

    ("18. a self-test counted in acceleration",
     S / "learning_acceleration.py",
     "    self_tests = get(\"self_tests_refused\")",
     "    self_tests = 0.0",
     f"{T}/test_market_learning_acceleration.py::test_the_real_report_sees_the_twenty_self_tests"),

    ("19. backfill counted as fresh",
     S / "learning_acceleration.py",
     "    usable = [o for o in observations\n              if not getattr(o, \"backlog_drain\", False)]",
     "    usable = list(observations)",
     f"{T}/test_market_learning_acceleration.py::test_a_backlog_drain_is_excluded_from_every_rate"),

    ("20. volume growth overrides falling quality",
     S / "learning_acceleration.py",
     "    if degraded:\n        return DEGRADING, (",
     "    if False:\n        return DEGRADING, (",
     f"{T}/test_market_learning_acceleration.py::test_volume_up_with_quality_falling_is_degrading_not_accelerating"),

    ("21. a bad LEVEL passes because it has no trend",
     S / "learning_acceleration.py",
     "    degraded = (degradations(before, after)\n                + absolute_failures(now, reconciliations=reconciliations))",
     "    degraded = degradations(before, after)",
     f"{T}/test_market_learning_acceleration.py::test_a_rate_that_was_undefined_and_is_now_bad_still_degrades"),

    ("22. a share above one is produced instead of the denominator widening",
     S / "learning_acceleration.py",
     "    evaluated = max(totals[\"mechanisms_tested\"], unfalsifiable)",
     "    evaluated = totals[\"mechanisms_tested\"]",
     f"{T}/test_market_learning_acceleration.py::test_a_share_above_one_raises_rather_than_being_clamped"),

    # --- source acquisition --------------------------------------------------
    ("23. partnership co-mention becomes a relation",
     S / "partnership_releases.py",
     "        if not matched and _TOO_WEAK.search(sentence):",
     "        if False:",
     f"{T}/test_market_counterparty_sources.py::test_uses_and_works_with_state_no_holdable_relation"),

    ("24. 'supply chain' produces a partner called Chain",
     S / "partnership_releases.py",
     "            implausible = _plausible_counterparty(counterparty, document.text)",
     "            implausible = ''",
     f"{T}/test_market_counterparty_sources.py::test_a_place_is_refused_at_the_call_site_not_only_in_the_helper"),

    ("25. a customer case study becomes dependence",
     S / "customer_case_studies.py",
     "            subject_actor=vendor, predicate=AR.SELLS_TO,",
     "            subject_actor=vendor, predicate=AR.DEPENDS_ON,",
     f"{T}/test_market_counterparty_sources.py::test_a_case_study_admits_sells_to_from_vendor_to_customer"),

    ("26. a logo wall becomes a customer relationship",
     S / "customer_case_studies.py",
     "    if not _USE.search(document.text):",
     "    if False:",
     f"{T}/test_market_counterparty_sources.py::test_a_page_that_names_a_company_without_stating_use_is_refused"),

    ("27. a government award becomes permanent customer dependence",
     S / "gov_awards.py",
     "            subject_actor=recipient, predicate=AR.SELLS_TO,",
     "            subject_actor=recipient, predicate=AR.DEPENDS_ON,",
     f"{T}/test_market_counterparty_sources.py::test_an_award_admits_sells_to_and_nothing_stronger"),

    ("28. an award relationship outlives its own contract",
     S / "gov_awards.py",
     "    if end:\n        row = AR.ActorRelationship(**{**row.__dict__, \"valid_to\": end})",
     "    if False:\n        row = AR.ActorRelationship(**{**row.__dict__, \"valid_to\": end})",
     f"{T}/test_market_counterparty_sources.py::test_the_relationship_is_bounded_by_the_contracts_own_period"),

    ("29. a keyword hit becomes an identity",
     S / "counterparty_sources.py",
     "        if len(want_tokens) == 1 or len(got_tokens) == 1:",
     "        if False:",
     f"{T}/test_market_counterparty_sources.py::test_a_one_token_alias_may_not_claim_a_longer_name"),

    ("30. a bad source family with zero yield is permanently enabled",
     S / "counterparty_sources.py",
     "        if self.yield_per_document > INTEGRATE_ABOVE_YIELD:",
     "        if True:",
     f"{T}/test_market_counterparty_sources.py::test_a_family_is_integrated_on_yield_and_nothing_else"),

    ("31. a settled family is re-measured",
     S / "counterparty_sources.py",
     "    if family in CLOSED_FAMILIES:",
     "    if False:",
     f"{T}/test_market_counterparty_sources.py::test_a_closed_family_cannot_be_re_measured"),

    # --- the LLM boundary -----------------------------------------------------
    ("32. an LLM-proposed alternative becomes canonical without validation",
     S / "alternative_explanations.py",
     "            if not row.is_offerable:",
     "            if False:",
     f"{T}/test_market_alternative_explanations.py::test_an_unvalidated_llm_proposal_is_never_offered"),

    ("33. a retired alternative is offered again",
     S / "alternative_explanations.py",
     "        return (self.validation_status == VALIDATED\n                and self.standing != RETIRED)",
     "        return self.validation_status == VALIDATED",
     f"{T}/test_market_alternative_explanations.py::test_a_retired_alternative_is_not_offered_however_validated"),

    ("34. an alternative that predicts nothing is stored",
     S / "alternative_explanations.py",
     "    if not predictions:",
     "    if False:",
     f"{T}/test_market_alternative_explanations.py::test_an_alternative_that_predicts_nothing_is_refused"),

    # --- the standing invariants ----------------------------------------------
    ("35. production is targeted",
     S / "trading_mode.py",
     "def assert_paper_only(",
     "def assert_paper_only(\n    *_a, **_k):\n    return\ndef _unused(",
     f"{T}/test_trading_mode.py"),
]



def main() -> int:
    return run_all([Proof(*row) for row in PROOFS],
                   title="wave-4 break proofs, hardened harness")


if __name__ == "__main__":
    sys.exit(main())
