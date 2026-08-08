"""Break proofs for wave 12: production persistence and retention truth.

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
AX = f"{T}/test_market_action_context.py"
ECH = f"{T}/test_market_economic_chain.py"
SE = f"{T}/test_market_strategic_episodes.py"
LC = f"{T}/test_market_learning_channels.py"
RPQ = f"{T}/test_market_relationship_persistence.py"
KRT = f"{T}/test_market_knowledge_retention.py"
CRL = f"{T}/test_market_competitive_relationships.py"
OTM = f"{T}/test_market_occurrence_time.py"
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

# --- wave 10 -------------------------------------------------------
    ("w10-1. an index page's neighbouring sentence supplies the buyer",
     S / "action_context.py",
     "    if sibling_actions > 0:",
     "    if False:",
     f"{AX}::test_an_index_page_supplies_no_context_at_all"),

    ("w10-2. a neighbouring announcement is treated as the same section",
     S / "action_context.py",
     "    if _OWN_ANNOUNCEMENT.search(text):\n"
     "        return False, \"announces its own action, so it is a section boundary\"",
     "    if False:\n"
     "        return False, \"announces its own action, so it is a section boundary\"",
     f"{AX}::test_a_neighbouring_announcement_is_a_section_boundary"),

    ("w10-3. the same document at two URLs is counted twice",
     S / "action_object_acquisition.py",
     "        if fingerprint in bodies:",
     "        if False:",
     f"{AC}::test_the_same_document_at_two_urls_is_retrieved_once"),

    ("w10-4. one vendor's changelog matures a whole source family",
     S / "research_planning.py",
     "        if (self.retrieved >= MIN_DOCUMENTS_ESTABLISHED\n"
     "                and actors >= MIN_ACTORS_ESTABLISHED):",
     "        if self.retrieved >= MIN_DOCUMENTS_ESTABLISHED:",
     f"{RP}::test_documents_alone_never_promote_a_family"),

    ("w10-5. macro states need a second graph",
     S / "economic_chain.py",
     "              ECONOMIC_FACTOR, CREDIT_STATE, CAPITAL_STATE, INDUSTRY_STATE)",
     "              )",
     f"{ECH}::test_the_graph_can_carry_macro_and_capital_states"),

("w10-6. a valid rivalry with a silent rival is ranked as learnable",
     S / "strategic_episodes.py",
     "    if obs != \"BOTH_SIDES_PUBLISH\":",
     "    if False:",
     f"{SE}::test_a_real_rivalry_with_a_silent_rival_is_not_observable"),

    ("w10-7. a high-value question promotes an unobservable pair",
     S / "strategic_episodes.py",
     "        candidates, key=lambda c: (_ORDER.get(c.standing, 9), -c.voi,",
     "        candidates, key=lambda c: (-c.voi, _ORDER.get(c.standing, 9),",
     f"{SE}::test_value_never_promotes_an_unobservable_pair"),

    ("w10-8. a pipeline repair is filed as economic knowledge",
     S / "learning_channels.py",
     "    if kind not in _ALLOWED[channel]:",
     "    if False:",
     f"{LC}::test_a_pipeline_repair_cannot_be_filed_as_economic_knowledge"),

    ("w10-9. an untested calibration track reports zero accuracy",
     S / "learning_channels.py",
     "        return (self.correct / self.tested) if self.tested else None",
     "        return (self.correct / self.tested) if self.tested else 0.0",
     f"{LC}::test_an_untested_track_is_unmeasurable_and_not_zero"),

# --- wave 11: what survives the process ----------------------------
    ("w11-1. a re-derived rivalry creates a second edge",
     S / "learning_store.py",
     "        held = self.relationship_scopes()\n        if key not in held:",
     "        held = {}\n        if key not in held:",
     f"{RPQ}::test_re_deriving_after_an_extractor_change_is_still_one_edge"),

    ("w11-2. rivalry identity is the id, so a pattern edit duplicates it",
     S / "learning_store.py",
     "    scope = str(row.get(\"competitive_object\")",
     "    scope = str(row.get(\"relationship_id\")",
     f"{RPQ}::test_a_different_contested_object_is_a_different_claim"),

    ("w11-3. a symmetric rivalry is stored twice, once per direction",
     S / "learning_store.py",
     "    pair = (\" & \".join(sorted((subject, obj)))\n"
     "            if predicate in SYMMETRIC_PREDICATES else f\"{subject} -> {obj}\")",
     "    pair = f\"{subject} -> {obj}\"",
     f"{RPQ}::test_a_symmetric_predicate_ignores_direction"),

    ("w11-4. retiring a relationship deletes the claim that asserted it",
     S / "learning_store.py",
     "        if not reason.strip():\n"
     "            raise ValueError(\"a retirement with no reason cannot be audited\")",
     "        if False:\n"
     "            raise ValueError(\"a retirement with no reason cannot be audited\")",
     f"{RPQ}::test_a_retirement_with_no_reason_is_refused"),

    ("w11-5. knowledge with no write path is reported as fine",
     S / "knowledge_retention.py",
     "        if not self.write_path:\n"
     "            return LOST if self.produced else UNUSED",
     "        if not self.write_path:\n            return UNUSED",
     f"{KRT}::test_knowledge_produced_with_no_write_path_is_lost"),

    ("w11-6. a recomputable fold is counted as lost knowledge",
     S / "knowledge_retention.py",
     "        if not self.is_original:\n            return DERIVED",
     "        if False:\n            return DERIVED",
     f"{KRT}::test_a_derived_fold_is_not_lost"),

    ("w11-7. producing nothing reads as a clean bill of health",
     S / "knowledge_retention.py",
     "    status = (DEGRADED if lost else\n"
     "              HEALTHY if durable else\n"
     "              UNMEASURABLE)",
     "    status = (DEGRADED if lost else HEALTHY)",
     f"{KRT}::test_no_original_knowledge_is_unmeasurable_not_healthy"),

    ("w11-8. an interrogative headline supplies the buyer",
     S / "competitive_relationships.py",
     "                    if AR.is_named_actor(candidate) and \\\n"
     "                            candidate.split()[0].lower() not in _NOT_A_BUYER_HEAD:",
     "                    if True:",
     f"{CRL}::test_a_question_headline_does_not_name_a_buyer"),

    ("w11-9. an outcome is recorded for an expectation nobody registered",
     S / "learning_store.py",
     "        if expectation_id not in self.cross_actor_expectation_ids():",
     "        if False:",
     f"{RPQ}::test_an_outcome_needs_a_preregistered_expectation"),

("w11-10. retrieval time is promoted to an occurrence",
     S / "occurrence_time.py",
     "    return ActionTime(occurred_at=\"\", published_at=\"\",\n"
     "                      retrieved_at=retrieved_at[:10], standing=UNKNOWN,\n"
     "                      evidence=\"neither the text nor the page states a date\")",
     "    return ActionTime(occurred_at=retrieved_at[:10], published_at=\"\",\n"
     "                      retrieved_at=retrieved_at[:10], standing=EXACT,\n"
     "                      evidence=\"neither the text nor the page states a date\")",
     f"{OTM}::test_retrieval_time_never_becomes_an_occurrence"),

    ("w11-11. a dated future commitment is recorded as something that happened",
     S / "occurrence_time.py",
     "        return self.standing in ORDERABLE and not self.is_future",
     "        return self.standing in ORDERABLE",
     f"{OTM}::test_a_dated_future_commitment_is_not_an_occurrence"),

    ("w11-12. an ambiguous changelog marker is guessed into last year",
     S / "occurrence_time.py",
     "    if got > published_at[:10]:\n        return \"\", \"\"",
     "    if got > published_at[:10]:\n"
     "        got = _iso(str(int(year) - 1), hit.group(\"month\"), hit.group(\"day\"))",
     f"{OTM}::test_a_marker_later_than_the_publication_is_refused_not_guessed"),

    ("w11-13. a dateless marker borrows the current year",
     S / "occurrence_time.py",
     "    if not hit or not published_at:\n        return \"\", \"\"",
     "    if not hit:\n        return \"\", \"\"\n"
     "    published_at = published_at or \"2026-12-31\"",
     f"{OTM}::test_a_marker_with_no_publication_year_is_no_date"),

    ("w11-14. vague recency is resolved to the publication date",
     S / "occurrence_time.py",
     "    if _VAGUE.search(text):",
     "    if False:",
     f"{OTM}::test_vague_recency_beats_a_publication_guess_by_refusing"),

# --- wave 12: the cycle must WRITE, not merely be able to ----------
    ("w12-1. the nightly cycle accepts a relationship and stores nothing",
     S / "steps.py",
     "            if store.record_relationship(row):\n"
     "                persisted += 1\n"
     "            else:\n"
     "                duplicates += 1",
     "            if False:\n"
     "                persisted += 1\n"
     "            else:\n"
     "                duplicates += 1",
     f"{RPQ}::test_the_acquisition_step_persists_what_it_accepts"),

    ("w12-2. a write path counts as healthy though the cycle never calls it",
     S / "knowledge_retention.py",
     "        if self.accepted and self.accepted > self.reloadable:\n"
     "            return DISCOVERED_NOT_PERSISTED",
     "        if False:\n            return DISCOVERED_NOT_PERSISTED",
     f"{KRT}::test_an_unused_write_path_gets_no_credit_when_production_accepted_work"),

    ("w12-3. a quiet night is reported as a persistence failure",
     S / "knowledge_retention.py",
     "        return max(0, self.accepted - self.reloadable)",
     "        return abs(self.accepted - self.reloadable)",
     f"{KRT}::test_accepting_nothing_is_not_a_gap"),

    ("w12-4. a rivalry with no contested object is stored anyway",
     S / "learning_store.py",
     "        if predicate == \"COMPETES_WITH\" and not scope_value:",
     "        if False:",
     f"{RPQ}::test_a_rivalry_with_no_contested_object_is_refused"),

    # --- 18 & 19: production target and PAPER --------------------------
    # Both are runtime guards asserted by the existing deployment tests
    # rather than by a mutation of market code; they are verified in the
    # wave report against the launchd plists and the production SHA.
]


def main() -> int:
    return run_all([Proof(*row) for row in PROOFS],
                   title="wave-12 break proofs, hardened harness")


if __name__ == "__main__":
    sys.exit(main())
