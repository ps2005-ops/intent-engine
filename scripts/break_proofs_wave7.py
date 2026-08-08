"""Break proofs for wave 7: competitive objects, event identity, founder view.

Every proof runs through the hardened harness. A mutation that changes no
bytes, or changes bytes and not behaviour, or goes red for the wrong reason,
is INVALID and does not count.
"""
from __future__ import annotations
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

S = ROOT / "src/intent_engine/market"
T = "tests"
CO = f"{T}/test_market_competitive_objects.py"
CA = f"{T}/test_market_competitive_actions.py"
EI = f"{T}/test_market_event_identity.py"
MF = f"{T}/test_market_multi_actor_founder.py"

PROOFS = [
    # --- the object must come from the document ------------------------
    ("1. a harness-supplied object is accepted as evidence",
     S / "competitive_actions.py",
     "    if not act.object_established or established_object is None:",
     "    if False:",
     f"{CA}::test_an_asserted_competitive_object_yields_unknown_not_relevant"),

    ("2. generic 'enterprise' establishes an object",
     S / "competitive_objects.py",
     "        if has_who and has_what:\n            standing = ESTABLISHED",
     "        if has_who or has_what:\n            standing = ESTABLISHED",
     f"{CO}::test_a_product_with_no_buyer_is_partial_not_unknown"),

    ("3. a vacuous word counts as the thing contested",
     S / "competitive_objects.py",
     "    if product and (_vacuous(product)",
     "    if product and (False",
     f"{CO}::test_a_vacuous_word_is_not_a_product"),

    ("4. an adjacent workflow is treated as exact overlap",
     S / "competitive_objects.py",
     "        if low in theirs or theirs in low:\n            return STRONG",
     "        if low or theirs:\n            return STRONG",
     f"{CO}::test_an_adjacent_workflow_never_reaches_strong"),

    ("5. shared vacuous words create overlap",
     S / "competitive_objects.py",
     "    shared = (set(theirs.split()) & {w for p in mine_parts\n"
     "                                     for w in p.lower().split()}) - _VACUOUS",
     "    shared = set(theirs.split()) & {w for p in mine_parts\n"
     "                                    for w in p.lower().split()}",
     f"{CO}::test_shared_vacuous_words_do_not_create_overlap"),

    ("6. a PARTIAL object reaches relevance",
     S / "competitive_objects.py",
     '        return self.standing == ESTABLISHED',
     '        return self.standing in (ESTABLISHED, PARTIAL)',
     f"{CO}::test_generic_language_never_establishes_an_object"),

    ("7. an object may be supplied through the extractor",
     S / "competitive_objects.py",
     "def extract(span: str, *, action_id: str, actor: str, source: str,\n"
     "            created_at: str, evidence_ids: Sequence[str] = ()",
     "def extract(span: str, *, action_id: str, actor: str, source: str,\n"
     "            created_at: str, competitive_object: str = '',\n"
     "            evidence_ids: Sequence[str] = ()",
     f"{CO}::test_no_parameter_supplies_an_object"),

    # --- event identity -------------------------------------------------
    ("8. two reports of one event become two events",
     S / "event_identity.py",
     "        return \"|\".join(head + [\" \".join(numeric)])",
     "        return \"|\".join(head + [\" \".join(numeric), fact[:40]])",
     f"{EI}::test_two_outlets_writing_one_event_differently_are_one_event"),

    ("9. a period marker splits accounts of one event",
     S / "event_identity.py",
     "and not _PERIOD.match(t))",
     "and True)",
     f"{EI}::test_a_period_marker_is_not_a_figure"),

    ("10. corroboration is discarded instead of counted",
     S / "observation_binding.py",
     "                refused[\"corroborates_the_opening_event\"] += 1\n"
     "                corroboration[exp.expectation_id] += 1",
     "                refused[\"corroborates_the_opening_event\"] += 1",
     f"{EI}::test_the_binder_counts_corroboration_rather_than_discarding_it"),

    ("11. an aggregator rewrite counts as a later test",
     S / "observation_binding.py",
     "            if EI.role_of(event_of.get(item.evidence_id),",
     "            if False and EI.role_of(event_of.get(item.evidence_id),",
     f"{EI}::test_the_binder_counts_corroboration_rather_than_discarding_it"),

    ("12. distinct outlets count as independent accounts",
     S / "event_identity.py",
     "        return len(set(self.source_roles))",
     "        return len(set(self.sources))",
     f"{EI}::test_independent_accounts_counts_roles_not_outlets"),

    ("13. different figures are merged into one event",
     S / "event_identity.py",
     "    numeric = sorted(t for t in (x.strip(\".\") for x in tokens)",
     "    numeric = sorted(t for t in ('' for x in tokens)",
     f"{EI}::test_different_figures_are_different_events"),

    # --- founder view ----------------------------------------------------
    ("14. the view renders a motive as fact",
     S / "multi_actor_view.py",
     "        if phrase in rendered:",
     "        if False:",
     f"{MF}::test_motive_language_is_refused_on_the_rendered_output"),

    ("15. one objective is presented as the objective",
     S / "multi_actor_view.py",
     "    if len(hypotheses) < 2:",
     "    if False:",
     f"{MF}::test_a_single_objective_would_read_as_a_motive_and_is_refused"),

    ("16. a competitor mention becomes a risk update",
     S / "multi_actor_view.py",
     '    if object_standing != "ESTABLISHED":',
     "    if False:",
     f"{MF}::test_an_unestablished_object_moves_monitoring_and_nothing_else"),

    ("17. an established object reaches the pricing field",
     S / "multi_actor_view.py",
     '        "changed": ["competitive_risk", "monitoring", "falsifier"],',
     '        "changed": ["competitive_risk", "monitoring", "falsifier",\n'
     '                    "pricing_watch"],',
     f"{MF}::test_an_established_object_moves_risk_but_never_pricing"),

    # --- planning and VOI -------------------------------------------------
    ("18. a family answers a question its record is not for",
     S / "research_planning.py",
     "    by_family = {p.source_family: p for p in performance\n"
     "                 if not p.question_type or p.question_type == question_type}",
     "    by_family = {p.source_family: p for p in performance}",
     f"{MF}::test_a_familys_score_for_another_question_cannot_rank_it_here"),

    ("19. competitor VOI is created without decision relevance",
     S / "competitor_voi.py",
     "    if decision_field not in DECISION_FIELDS:",
     "    if False:",
     f"{MF}::test_a_question_that_moves_no_decision_field_is_refused"),

    ("20. a lookup is stored as an uncertainty",
     S / "competitor_voi.py",
     "    if len(alternatives) < 2:",
     "    if False:",
     f"{MF}::test_a_question_with_one_answer_is_a_lookup"),

    ("21. an unanswerable question is queued as a priority",
     S / "competitor_voi.py",
     "    if not source_family:",
     "    if False:",
     f"{MF}::test_a_question_no_source_can_answer_is_unresolvable_not_queued"),

    # --- standing invariants ----------------------------------------------
    ("22. production is targeted",
     S / "trading_mode.py",
     "def assert_paper_only(",
     "def assert_paper_only(\n    *_a, **_k):\n    return\ndef _unused(",
     f"{T}/test_trading_mode.py"),
]


def main() -> int:
    return run_all([Proof(*row) for row in PROOFS],
                   title="wave-7 break proofs, hardened harness")


if __name__ == "__main__":
    sys.exit(main())
