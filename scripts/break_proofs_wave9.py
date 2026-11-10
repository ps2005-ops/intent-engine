"""Break proofs for wave 9: action identity, attribution, near-miss counting.

Every proof runs through the hardened harness. A mutation that changes no
bytes, or changes bytes and not behaviour, or goes red for the wrong reason,
is INVALID and does not count.

Three of the nineteen the wave listed are recorded as NOT_BUILT rather than
faked. A break proof demonstrates that a guard is load-bearing; there is no
guard to break where the capability was not built, and writing a proof that
passes because the code path does not exist would be the exact
"test that cannot fail" this project has already found once.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

S = ROOT / "src/intent_engine/market"
T = "tests"
CO = f"{T}/test_market_competitive_objects.py"
CA = f"{T}/test_market_competitive_actions.py"
AQ = f"{T}/test_market_action_object_queries.py"
AC = f"{T}/test_market_action_object_acquisition.py"
EC = f"{T}/test_market_event_corroboration.py"
RP = f"{T}/test_market_research_planning.py"
NM = f"{T}/test_market_near_miss.py"
EI = f"{T}/test_market_event_identity.py"
GT = f"{T}/test_market_game_theoretic_state.py"
MF = f"{T}/test_market_multi_actor_founder.py"

PROOFS = [
    # --- 1. the object must come from the document ---------------------
    ("1. the relationship's object is trusted as the action's object",
     S / "competitive_actions.py",
     "    if not act.object_established or established_object is None:",
     "    if False:",
     f"{CA}::test_an_asserted_competitive_object_yields_unknown_not_relevant"),

    ("2. one axis is enough to establish an object",
     S / "competitive_objects.py",
     "        if all(dim in present for dim in required):",
     "        if any(dim in present for dim in required):",
     f"{CO}::test_a_product_with_no_buyer_is_partial_not_unknown"),

    # --- 3. NOT_BUILT: migration-page authority ranking ----------------
    # §5 asked that SEO comparison spam not create rivalry automatically.
    # No path in this wave turns a migration page into a COMPETES_WITH
    # edge — the family produced 0 actions and 0 rivalry claims — so there
    # is no guard to break. Recorded, not faked.

    # Nothing asserted the PRICE_CHANGE row of the dimension table: emptying
    # it left the whole suite green, which is how this proof found the gap.
    # The paired test was written for it.
    ("4. a price change with a tier and no buyer establishes an object",
     S / "competitive_objects.py",
     '    "PRICE_CHANGE": (WHAT, WHO),',
     '    "PRICE_CHANGE": (),',
     f"{CO}::test_a_price_change_with_a_tier_and_no_buyer_is_not_established"),

    ("5. a PARTIAL object is usable and can reach an interaction",
     S / "competitive_objects.py",
     "        return self.standing == ESTABLISHED",
     "        return self.standing in (ESTABLISHED, PARTIAL)",
     f"{CO}::test_a_required_dimension_is_never_filled_by_requiring_it"),

    # --- 6 & 7. expectations precede the evidence that resolves them ---
    # The expectation tests live beside the actions that trigger them, in
    # test_market_competitive_actions.py, not in the game-theoretic file.
    ("6. a response is scored against an expectation written after it",
     S / "cross_actor_expectations.py",
     "    if when and created and when < created:",
     "    if False:",
     f"{CA}::test_evidence_predating_the_prediction_cannot_test_it"),

    ("7. an expectation may be created after its own window closed",
     S / "cross_actor_expectations.py",
     "    if window <= created:",
     "    if False:",
     f"{CA}::test_a_window_that_closes_before_it_opens_is_refused"),

    # --- 8. one response never proves a motive -------------------------
    # Paired with the BROKEN prediction: forcing `if held` true is invisible
    # to a test that only ever passes held=True, which is how this proof
    # first came back NOT_CAUGHT.
    ("8. a broken prediction is recorded as though it held",
     S / "strategic_objectives.py",
     '    if held:',
     '    if True:',
     f"{GT}::test_a_broken_prediction_leaves_it_weak_and_records_the_evidence"),

    # --- 9. legacy rows are not unique events --------------------------
    ("9. two accounts of one occurrence are counted as two events",
     S / "event_identity.py",
     "        return \"|\".join(head + [\" \".join(numeric)])",
     "        return \"|\".join(head + [\" \".join(sorted(text.split()))])",
     f"{EI}::test_two_outlets_writing_one_event_differently_are_one_event"),

    ("9b. a dict row reads as empty and every row folds into one event",
     S / "event_identity.py",
     "    get = (item.get if isinstance(item, Mapping)",
     "    get = (item.get if False",
     f"{EI}::test_a_mapping_row_groups_the_same_as_an_object_row"),

    # `_field` is the reader event_corroboration borrows, and `group` no
    # longer uses it — so it needs its own proof or the two modules could
    # drift apart again with nothing red.
    ("9c. corroboration's borrowed reader goes blind to mappings",
     S / "event_identity.py",
     "    if isinstance(item, Mapping):\n"
     "        return str(item.get(name, \"\") or \"\")",
     "    if False:\n"
     "        return str(item.get(name, \"\") or \"\")",
     f"{EC}::test_corroboration_reads_a_mapping_row_the_same_as_an_object"),

    # --- 10. corroboration is never a later test -----------------------
    ("10. corroboration resolves the expectation its event opened",
     S / "event_corroboration.py",
     "    return False, (",
     "    return True, (",
     f"{EC}::test_corroboration_never_resolves_an_expectation"),

    # --- 11. syndication is not independence ---------------------------
    ("11. the same publisher twice counts as two witnesses",
     S / "event_corroboration.py",
     "    if pub_a and pub_a == pub_b:\n        return SAME_ORIGIN, "
     "f\"both published by {pub_a}\"",
     "    if pub_a and pub_a != pub_b:\n        return SAME_ORIGIN, "
     "f\"both published by {pub_a}\"",
     f"{EC}::test_the_same_publisher_twice_is_one_account"),

    ("11b. six copies of one wire story raise the effective count",
     S / "event_corroboration.py",
     "    SAME_ORIGIN: 0.0,",
     "    SAME_ORIGIN: 1.0,",
     f"{EC}::test_syndication_does_not_raise_the_effective_account_count"),

    # --- 12. dependent accounts do not mature a belief -----------------
    ("12. dependent accounts are enough for CORROBORATED",
     S / "event_corroboration.py",
     "    elif contribution >= 2.0 and independent >= 2:",
     "    elif len(rows) >= 2:",
     f"{EC}::test_syndication_does_not_raise_the_effective_account_count"),

    # --- 13. the planner reacts to per-question performance ------------
    ("13. a family measured at zero for THIS question is not demoted",
     S / "action_object_queries.py",
     "            score = covered * (rate if rate else -0.5)",
     "            score = covered * (rate if rate else 0.9)",
     f"{AQ}::test_a_measured_zero_sinks_below_an_untried_family"),

    ("13b. the object question is ranked by how much TEXT a family produced",
     S / "research_planning.py",
     "        relationship_yield=(established / retrieved) if retrieved else 0.0,",
     "        relationship_yield=(float(data.get('actions_found', 0) or 0)\n"
     "                            / retrieved) if retrieved else 0.0,",
     f"{RP}::test_the_object_question_is_scored_on_objects_not_on_actions"),

    # --- 14. high value never buys a generic page ----------------------
    # The first version of this proof mutated a GENERIC_FAMILIES score
    # penalty and came back NOT_CAUGHT, because the penalty sat BELOW the
    # coverage filter and could never execute. The dead line is deleted and
    # the proof now breaks the filter that actually excludes the homepage.
    ("14. a family that supplies no dimension is planned anyway",
     S / "action_object_queries.py",
     "        if not covered:\n            continue",
     "        if False:\n            continue",
     f"{AQ}::test_a_generic_family_is_never_planned_however_well_it_scored"),

    # --- 15 & 16. the founder view ------------------------------------
    ("15. an unestablished object still moves a founder risk field",
     S / "multi_actor_view.py",
     '    if object_standing != "ESTABLISHED":',
     "    if False:",
     f"{MF}::test_an_unestablished_object_moves_monitoring_and_nothing_else"),

    ("16. the multi-actor view renders a single motive as fact",
     S / "multi_actor_view.py",
     "    if len(hypotheses) < 2:",
     "    if False:",
     f"{MF}::test_a_single_objective_would_read_as_a_motive_and_is_refused"),

    # --- 17. the acquisition never supplies an object ------------------
    ("17. the fetching harness marks its own actions established",
     S / "competitive_actions.py",
     "                    competitive_object=competitive_object,\n"
     "                    event_time=event_time,",
     "                    competitive_object=competitive_object,\n"
     "                    object_established=True,\n"
     "                    event_time=event_time,",
     f"{AC}::test_an_action_is_never_marked_established_by_the_harness"),

    # Making only the verb optional left the month/day/year requirement in
    # place, so the undated corpus still failed to match and the proof came
    # back NOT_CAUGHT. The DATE is the guard; this removes it.
    ("17b. a static pricing page is admitted as a price change",
     S / "competitive_actions.py",
     "     r\"|\\b(?:starting|effective|beginning)\\s+\"\n"
     "     r\"(?:January|February|March|April|May|June|July|August|September|\"\n"
     "     r\"October|November|December)\\s+\\d{1,2},?\\s+\\d{4}[^.]{0,120}?\"",
     "     r\"|\\b(?:starting|effective|beginning)?\\s*\"\n"
     "     r\"(?:January|February|March|April|May|June|July|August|September|\"\n"
     "     r\"October|November|December)?\\s*\\d{0,2},?\\s*\\d{0,4}[^.]{0,120}?\"",
     f"{CA}::test_undated_pricing_prose_is_not_a_price_change"),

    # --- wave 9: one page, one document; one announcement, one action ---
    ("w9-1. an in-page anchor is fetched as a separate document",
     S / "action_object_acquisition.py",
     "    return urldefrag(url)[0].rstrip(\"/\")",
     "    return url.rstrip(\"/\")",
     f"{AC}::test_an_anchor_link_is_not_followed_as_a_new_page"),

    ("w9-2. the same announcement on five pages counts five times",
     S / "action_object_acquisition.py",
     "                    if act.action_id in counted:\n"
     "                        report.duplicate_action_sightings += 1\n"
     "                        continue",
     "                    if False:\n"
     "                        report.duplicate_action_sightings += 1\n"
     "                        continue",
     f"{AC}::test_one_announcement_on_five_pages_is_one_action"),

    # --- wave 9: an action belongs to whoever the sentence says ---------
    ("w9-3. a rival's launch on our page is recorded as ours",
     S / "competitive_actions.py",
     "        if subject and not _same_actor(subject, actor) and any(",
     "        if False and any(",
     f"{CA}::test_a_rivals_launch_on_our_page_is_not_our_launch"),

    ("w9-4. attribution is decided by capitalisation rather than by name",
     S / "competitive_actions.py",
     "                _same_actor(subject, other) for other in other_actors):",
     "                True for other in [1]):",
     f"{CA}::test_a_capitalised_sentence_opener_is_not_a_company"),

("w9-6. a page describing its release cadence is admitted as an action",
     S / "competitive_actions.py",
     "        shape = announces_nothing(sentence)\n        if shape:",
     "        shape = announces_nothing(sentence)\n        if False:",
     f"{CA}::test_the_refusal_names_which_shape_it_was"),

    ("w9-7. a non-action is counted as a missing buyer",
     S / "near_miss.py",
     "    real_actions = [m for m in adjudicated\n"
     "                    if m.adjudication != WRONG_DOCUMENT]",
     "    real_actions = list(adjudicated)",
     f"{NM}::test_a_non_action_is_not_counted_as_a_missing_buyer"),

    ("w9-8. an unadjudicated refusal is scored as a source failure",
     S / "near_miss.py",
     "    adjudicated = [m for m in misses if m.is_adjudicated]",
     "    adjudicated = list(misses)",
     f"{NM}::test_an_unadjudicated_refusal_is_not_a_source_failure"),

    ("w9-9. a curly quote silently loses a hand label",
     S / "near_miss.py",
     "    text = \" \".join((span or \"\").translate(_QUOTES).split()).lower()",
     "    text = \" \".join((span or \"\").split()).lower()",
     f"{NM}::test_a_curly_quote_does_not_lose_a_label"),

    # The first version mutated a `you\b` alternative that could never fire —
    # the head noun must name an economic agent and "you" is not one — so the
    # proof came back NOT_CAUGHT and the dead alternative was deleted. The
    # POSSESSIVE is the part that does the work.
    ("w9-10. the reader's own merchants are read as a named buyer",
     S / "competitive_objects.py",
     "    r\"\\bso\\s+((?!your\\b|our\\b|their\\b)(?:[a-z][\\w-]*\\s+){0,3}?\"",
     "    r\"\\bso\\s+((?:[a-z][\\w-]*\\s+){0,3}?\"",
     f"{CO}::test_a_possessive_after_so_addresses_the_reader_and_names_nobody"),
    ("w9-11. any capitalised word beside 'Bundled with' is a priced tier",
     S / "competitive_objects.py",
     "    r\"\\b([A-Z][A-Za-z0-9+]*\\s+(?:Edition|Plan|Tier|Package))\\b\")",
     "    r\"\\b([A-Z][A-Za-z0-9+]*\\s+[A-Z][A-Za-z0-9+]*)\\b\")",
     f"{CO}::test_a_bare_capitalised_word_is_not_a_tier"),

    ("w9-5. a sub-brand is treated as a different company",
     S / "competitive_actions.py",
     "    return a in b or b in a or bool(set(a.split()) & set(b.split()))",
     "    return a == b",
     f"{CA}::test_a_sub_brand_still_belongs_to_its_parent"),

    # --- 18 & 19: production target and PAPER --------------------------
    # Both are runtime guards asserted by the existing deployment tests
    # rather than by a mutation of market code; they are verified in the
    # wave report against the launchd plists and the production SHA.
]


def main() -> int:
    return run_all([Proof(*row) for row in PROOFS],
                   title="wave-9 break proofs, hardened harness")


if __name__ == "__main__":
    sys.exit(main())
