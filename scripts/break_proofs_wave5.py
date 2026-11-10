"""Break proofs for wave 5: rivalry, game-theoretic state, planning, and
the self-test repair.

A PROOF ONLY COUNTS IF IT GOES RED. Each entry mutates the source so a
self-flattering behaviour becomes true, runs the ONE test paired with it, and
requires a FAILURE. Restore bumps mtime — a same-length restore leaves
CPython running cached bytecode whose size and hash still match.
"""
from __future__ import annotations
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

S = ROOT / "src/intent_engine/market"
T = "tests"
CR = f"{T}/test_market_competitive_relationships.py"
GT = f"{T}/test_market_game_theoretic_state.py"
RP = f"{T}/test_market_research_planning.py"
ST = f"{T}/test_market_self_test_contamination.py"
CK = f"{T}/test_market_calibration_consistency.py"
CM = f"{T}/test_market_counterfactual_memory.py"

PROOFS = [
    # --- rivalry: the seven ways to fabricate a competitor ---------------
    # `_NOT_RIVALRY` is defence in depth for most negative cases — they
    # match no rivalry pattern either. The one case where it is the ONLY
    # guard is a sentence that DOES match a pattern and is about
    # securities rather than products.
    ("1. a securities shortlist becomes COMPETES_WITH",
     S / "competitive_relationships.py",
     "    if _NOT_RIVALRY.search(clause):",
     "    if False:",
     f"{CR}::test_the_negative_corpus_produces_no_rivalry"
     f"[securities shortlist]"),

    ("1b. a whole-sentence veto kills a valid rivalry clause",
     S / "competitive_relationships.py",
     "    clause = _clause_around(sentence, start, end)\n"
     "    if _NOT_RIVALRY.search(clause):",
     "    if _NOT_RIVALRY.search(sentence):",
     f"{CR}::test_the_filter_runs_at_the_scope_of_the_claim"
     f"[rivalry then complementarity]"),

    ("1c. a local explicit non-compete is ignored",
     S / "competitive_relationships.py",
     "    if _NEGATED.search(sentence[:start]):",
     "    if False:",
     f"{CR}::test_an_explicit_negation_before_the_verb_governs_it"),

    ("2. a claim with no competitive object is admitted",
     S / "competitive_relationships.py",
     "    if len(obj) < MIN_OBJECT_CHARS or _VACUOUS_OBJECT.match(obj):",
     "    if False:",
     f"{CR}::test_a_claim_without_a_competitive_object_is_refused"),

    ("3. a vacuous object counts as an object",
     S / "competitive_relationships.py",
     "_VACUOUS_OBJECT = re.compile(",
     "_VACUOUS_OBJECT = re.compile(\n    r'^(?!x)x$'  # matches nothing\n    or ",
     f"{CR}::test_a_vacuous_object_is_not_an_object"),

    ("4. a rivalry needs no buyer",
     S / "competitive_relationships.py",
     '    if not (buyer_or_market or "").strip():',
     "    if False:",
     f"{CR}::test_a_claim_without_a_buyer_is_refused"),

    ("5. an unnamed end becomes a competitor",
     S / "competitive_relationships.py",
     "        if not AR.is_named_actor(value):",
     "        if False:",
     f"{CR}::test_an_unnamed_end_is_refused"),

    ("6. a fiscal period becomes a competitor",
     S / "competitive_relationships.py",
     "            if _NOT_AN_ACTOR_TOKEN.match(left) or \\",
     "            if False and (_NOT_AN_ACTOR_TOKEN.match(left) or \\",
     f"{CR}::test_a_fiscal_period_is_not_a_competitor"),

    ("7. an unbuilt evidence type is silently accepted",
     S / "competitive_relationships.py",
     "    if evidence_type not in BUILT:",
     "    if False:",
     f"{CR}::test_an_unbuilt_evidence_type_is_refused_with_what_it_would_need"),

    ("8. the edge drops the terms it was admitted under",
     S / "competitive_relationships.py",
     '                f"{self.evidence_span} [competitive object: "',
     '                f"{self.evidence_span} [" + "" if False else f"{self.evidence_span} ["  # noqa\n                f"" or f"{self.evidence_span} [x: "',
     f"{CR}::test_the_edge_carries_its_terms_into_the_graph"),

    # --- game-theoretic state --------------------------------------------
    ("9. motive rendered as fact — one alternative is enough",
     S / "strategic_objectives.py",
     "    if len(alternatives) < MIN_ALTERNATIVES:",
     "    if False:",
     f"{GT}::test_one_alternative_is_not_enough"),

    ("10. an objective that predicts nothing is stored",
     S / "strategic_objectives.py",
     "    if not expected_next_action.strip():",
     "    if False:",
     f"{GT}::test_an_objective_that_predicts_nothing_is_refused"),

    ("11. an objective is born above WEAK",
     S / "strategic_objectives.py",
     "        standing=WEAK, falsifier=falsifier,",
     "        standing=SUPPORTED, falsifier=falsifier,",
     f"{GT}::test_every_hypothesis_is_born_weak"),

    ("12. one response creates a stable actor behaviour",
     S / "actor_response_memory.py",
     "        repeat_count=1, standing=CANDIDATE, contexts=(context,))",
     "        repeat_count=1, standing=PATTERN, contexts=(context,))",
     f"{GT}::test_one_episode_is_a_candidate_and_says_its_count"),

    ("13. a pattern needs neither repetition nor a second context",
     S / "actor_response_memory.py",
     "    if count >= MIN_EPISODES_PATTERN and len(contexts) >= 2:",
     "    if True:",
     f"{GT}::test_three_episodes_in_one_context_do_not_make_a_pattern"),

    ("14. a contradicting response accumulates instead of contradicting",
     S / "actor_response_memory.py",
     "    if held.response_type != episode.response_type:",
     "    if False:",
     f"{GT}::test_a_different_response_contradicts_rather_than_accumulates"),

    ("15. a response with no delay is admitted",
     S / "actor_response_memory.py",
     "    if response_type != NO_OBSERVED_RESPONSE and delay_days is None:",
     "    if False:",
     f"{GT}::test_a_response_with_no_delay_is_unfalsifiable_and_refused"),

    # --- planning ---------------------------------------------------------
    ("16. a source-yield planner overfits one tiny observation",
     S / "research_planning.py",
     "        immature = got.maturity == PROVISIONAL",
     "        immature = False",
     f"{RP}::test_a_provisional_family_is_kept_ahead_of_its_measured_rank"),

    ("17. degraded learning health has no operational response",
     S / "research_planning.py",
     "    if learning_status == LA.DEGRADING and \\",
     "    if False and learning_status == LA.DEGRADING and \\",
     f"{RP}::test_degrading_on_re_reads_reorders_the_same_question"),

    ("18. a family answers a predicate it cannot answer",
     S / "research_planning.py",
     "    eligible = CAN_ANSWER.get(question_type, ())",
     "    eligible = tuple(by_family := {}) or tuple(\n"
     "        p.source_family for p in performance)",
     f"{RP}::test_a_family_that_cannot_answer_is_excluded_however_good_it_is"),

    ("19. the degradation response fires on the alarm, not the diagnosis",
     S / "research_planning.py",
     "            dominant_self_test_class == OB.SAME_SOURCE_REPACKAGING:",
     "            True:",
     f"{RP}::test_degrading_for_another_reason_does_not_reorder"),

    # --- the self-test repair --------------------------------------------
    ("20. the sweep date returns to a fact's identity",
     S / "micro_evidence.py",
     "    del observed_at                       # see `occurrence_key`\n"
     "    raw = occurrence_key(",
     "    raw = (observed_at or '')[:10] + occurrence_key(",
     f"{ST}::test_the_sweep_date_is_not_part_of_a_facts_identity"),

    ("21. a re-read becomes a second observation",
     S / "learning_store.py",
     "        if key not in held:",
     "        if True:",
     f"{ST}::test_a_re_read_is_recorded_but_is_not_a_second_observation"),

    ("22. a legacy row is not recognised, so history duplicates once more",
     S / "learning_store.py",
     "        held = self._occurrence_first_seen()",
     "        held = {}",
     f"{ST}::test_legacy_rows_written_under_the_old_id_are_still_recognised"),

    ("23. same-day re-reads grow the ledger, breaking replay",
     S / "learning_store.py",
     "        if seen_at <= held[key]:\n            return False",
     "        if False:\n            return False",
     f"{T}/test_evidence_pipeline_break_proofs.py::"
     f"test_break_append_only_by_replaying_a_session"),

    # `PRODUCER_OF = {} or {...}` evaluates to the second dict — the
    # mutation was a no-op, which is exactly the kind of proof that passes
    # while proving nothing. Emptying one entry is what the test can see.
    ("24. a self-test class loses its named producer",
     S / "observation_binding.py",
     '    LEGITIMATE_LATER_OBSERVATION: "not a self-test; admitted",',
     '    LEGITIMATE_LATER_OBSERVATION: "",',
     f"{ST}::test_every_class_carries_a_producer"),

    # --- cross-layer + analogy -------------------------------------------
    ("25. mechanism / belief maturity semantic inconsistency",
     S / "calibration_consistency.py",
     "        if _MATURITY_RANK.get(state, 0) > _MATURITY_RANK.get(cap, 3):",
     "        if False:",
     f"{CK}::test_a_contested_mechanism_caps_its_beliefs_at_supported"),

    ("26. a causal family stops capping its own predictor",
     S / "calibration_consistency.py",
     "        if _MECHANISM_RANK.get(mech, 0) > _MECHANISM_RANK.get(cap, 3):",
     "        if False:",
     f"{CK}::test_a_contested_causal_family_caps_its_own_predictor"),

    ("27. the consistency checker rewrites stored state",
     S / "calibration_consistency.py",
     "    for maturity in maturities:\n        belief_id = getattr(",
     "    for maturity in maturities:\n"
     "        try:\n            maturity.state = 'CANDIDATE'\n"
     "        except Exception:\n            pass\n"
     "        belief_id = getattr(",
     f"{CK}::test_nothing_is_rewritten"),

    ("28. a historical analogy becomes current evidence",
     S / "counterfactual_memory.py",
     "    is_evidence: bool = False",
     "    is_evidence: bool = True",
     f"{CM}::test_an_analogy_carries_no_evidence_and_says_so"),

    ("29. an analogy is offered for the case it came from",
     S / "counterfactual_memory.py",
     "        if episode_.subject == subject:",
     "        if False:",
     f"{CM}::test_an_episode_is_never_an_analogy_for_its_own_subject"),

    # --- standing invariants ----------------------------------------------
    ("30. production is targeted",
     S / "trading_mode.py",
     "def assert_paper_only(",
     "def assert_paper_only(\n    *_a, **_k):\n    return\ndef _unused(",
     f"{T}/test_trading_mode.py"),
]



def main() -> int:
    return run_all([Proof(*row) for row in PROOFS],
                   title="wave-5 break proofs, hardened harness")


if __name__ == "__main__":
    sys.exit(main())
