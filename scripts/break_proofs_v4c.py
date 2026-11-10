"""Are the attribution, demand, quantity and deck guards load-bearing?

Same harness, same discipline, and now with a mutation lock: these scripts
rewrite real source files, and two of them running at once against one
worktree corrupt each other's restores.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

S = ROOT / "src/intent_engine/market"
KE = S / "knowledge_effect.py"
CX = S / "company_exposure.py"
BF = S / "belief_formation.py"
RP = S / "research_policy.py"
EQ = S / "economic_quantity.py"
DC = S / "demand_chain.py"
PR = S / "presentation.py"

K = "tests/test_market_knowledge_effect.py"
D = "tests/test_market_demand_and_deck.py"

PROOFS = [
    ("v4c-1. an object the evidence was merely about counts as changed",
     KE,
     "            if self.before_state == self.after_state:",
     "            if False:",
     f"{K}::test_a_change_that_changed_nothing_is_refused"),

    ("v4c-2. an attribution needs no reason",
     KE,
     "        if not self.reason.strip():",
     "        if False:",
     f"{K}::test_an_unexplained_attribution_is_refused"),

    ("v4c-3. a reconstructed attribution prices a research action",
     KE,
     "PRICEABLE = frozenset({DIRECT})",
     "PRICEABLE = frozenset({DIRECT, RECONSTRUCTED, UNKNOWN})",
     f"{K}::test_a_reconstructed_attribution_cannot_price_an_action"),

    ("v4c-4. creating a belief counts as discriminating",
     KE,
     "DISCRIMINATING = frozenset({DISCRIMINATED, CONTRADICTED, RESOLVED,\n"
     "                            INVALIDATED})",
     "DISCRIMINATING = frozenset({DISCRIMINATED, CONTRADICTED, RESOLVED,\n"
     "                            INVALIDATED, CREATED})",
     f"{K}::test_creating_a_belief_does_not_discriminate"),

    ("v4c-5. an open window attributes nothing instead of NO_CHANGE",
     KE,
     "        if mapped == NO_CHANGE:\n            out.append(no_change(",
     "        if mapped == NO_CHANGE:\n            continue\n"
     "        if False:\n            out.append(no_change(",
     f"{K}::test_an_open_window_attributes_no_change_rather_than_nothing"),

    ("v4c-6. evidence that names no exposure records nothing",
     CX,
     "        if effects is not None and eid and not moved:",
     "        if False:",
     f"{K}::test_evidence_that_names_no_exposure_attributes_no_change"),

    ("v4c-7. unexamined evidence is given a result anyway",
     RP,
     "    for evidence_id, mine in sorted(by_evidence.items()):",
     "    for evidence_id, mine in sorted(\n"
     "            list(by_evidence.items())\n"
     "            + [(k, []) for k in meta if k not in by_evidence]):",
     f"{K}::test_evidence_with_no_effect_record_is_not_priced"),

    ("v4c-8. an attack that changes less still passes the audit",
     RP,
     "        if mine is None or theirs is None or mine < theirs:",
     "        if False:",
     f"{K}::test_an_attack_that_wins_while_changing_less_is_flagged"),

    ("v4c-9. a bare number becomes an economic quantity",
     EQ,
     '            if any(ch.isdigit() for ch in sentence):\n'
     '                refuse("no_subject")\n            continue',
     '            continue',
     f"{D}::test_a_bare_percentage_is_not_a_quantity"),

    ("v4c-10. a buyback is read as revenue again",
     EQ,
     "    claimed = bool(_OTHER_MONEY.search(between)\n"
     "                   or _OTHER_MONEY.search(trailing))",
     "    claimed = False",
     f"{D}::test_a_buyback_is_not_revenue"),

    ("v4c-11. a structural reference becomes a measurement",
     EQ,
     "        if any(p.search(sentence) for p in _NEVER):",
     "        if False:",
     f"{D}::test_a_structural_reference_is_never_a_measurement"),

    ("v4c-12. a quantity needs no words behind it",
     EQ,
     "        if not self.source_span.strip():",
     "        if False:",
     f"{D}::test_a_quantity_without_its_words_is_refused"),

    ("v4c-13. a backlog figure speaks for demand",
     DC,
     "    raise UnmediatedInference(",
     "    return 'demand is rising'\n    raise UnmediatedInference(",
     f"{D}::test_a_backlog_figure_refuses_to_speak_for_demand"),

    ("v4c-14. two measured states moving apart is called consistent",
     DC,
     '            standing, reason = CONTRADICTED, (',
     '            standing, reason = HYPOTHESIZED, (',
     f"{D}::test_two_measured_states_moving_apart_is_contradicted"),

    ("v4c-15. a third party establishes a company's own backlog",
     DC,
     "        standing = OBSERVED if role in _ESTABLISHING else INFERRED",
     "        standing = OBSERVED",
     f"{D}::test_a_companys_own_filing_observes_and_a_report_only_infers"),

    ("v4c-16. cancellations become a step along the chain",
     DC,
     "    (BACKLOG, SHIPMENTS),",
     "    (BACKLOG, CANCELLATIONS),\n    (BACKLOG, SHIPMENTS),",
     f"{D}::test_cancellations_are_a_leak_and_not_a_step"),

    ("v4c-17. a chain averages its links instead of taking the weakest",
     DC,
     "        return min((l.standing for l in self.links), "
     "key=lambda s: _RANK[s])",
     "        return max((l.standing for l in self.links), "
     "key=lambda s: _RANK[s])",
     f"{D}::test_a_chain_is_worth_its_weakest_link"),

    ("v4c-18. a slide need not name its source",
     PR,
     "        if not self.sourced_from.strip():",
     "        if False:",
     f"{D}::test_a_slide_that_cannot_name_its_source_is_refused"),

    ("v4c-19. certainty language survives into a slide",
     PR,
     "        for phrase in _BANNED:\n            if phrase in text:",
     "        for phrase in _BANNED:\n            if False:",
     f"{D}::test_certainty_language_is_refused_at_any_standing"),

    ("v4c-20. a proposed thesis produces a confident headline",
     PR,
     '    ET.PROPOSED: "may be",',
     '    ET.PROPOSED: "is, on the evidence we have tried to break",',
     f"{D}::test_the_headline_verb_is_bound_to_the_standing"),

    ("v4c-21. an edited deck is not re-checked against its thesis",
     PR,
     "            ET.consistent_with(thesis, rendered_standing=one.standing,\n"
     "                               surface=f\"slide {one.section}\")",
     "            pass",
     f"{D}::test_a_deck_edited_afterwards_is_caught_by_check"),
]

PROOFS = [Proof(label=p[0], path=p[1], find=p[2], replace=p[3], target=p[4])
          for p in PROOFS]

if __name__ == "__main__":
    raise SystemExit(run_all(PROOFS))
