"""Break proofs for the decision-impact repair. The gap the last run left.

The defect these attack is not a wrong grade. It is a metric that could only
ever return a positive: with an EMPTY before-state, every field of every
attached dossier goes empty -> populated, and 25 of 25 live dossiers graded
MEANINGFUL or DECISION_CHANGING with no NONE available anywhere in the range.

A metric that cannot report the negative is not evidence, and it is worth
more mutation coverage than one that merely gets a threshold wrong.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

E = ROOT / "src/intent_engine/external_intel"
T = "tests"
DI = f"{T}/test_decision_impact_prior_revision.py"

PROOFS = [
    # --- A. the original defect, restored ------------------------------
    ("A. the BEFORE reverts to an empty state, so nothing can grade NONE",
     E / "decision_impact.py",
     "    before = {field: list(values)\n"
     "              for field, values in (prior.get(\"state\") or {}).items()}",
     "    before = {}",
     f"{DI}::test_an_identical_dossier_grades_none"),

    # --- B. FIRST_OBSERVATION becomes an impact ------------------------
    ("B. a first observation is graded as a real comparison",
     E / "decision_impact.py",
     "    if prior is None:\n"
     "        return DecisionImpact(",
     "    if False:\n"
     "        return DecisionImpact(",
     f"{DI}::test_no_prior_revision_is_not_an_impact"),

    # --- C. the identity wall ------------------------------------------
    ("C. any company's prior will do",
     E / "decision_impact.py",
     # Anchored on the line BELOW too: the same lookup appears verbatim in
     # `record_revision`, and the first version of this proof mutated that
     # one instead — the harness reported NOT_CAUGHT and it was the anchor
     # that was wrong, not the guard.
     "    prior = load_revisions(root, path=path).get(company_id)\n"
     "    if prior is None:",
     "    prior = (list(load_revisions(root, path=path).values()) or "
     "[None])[0]\n"
     "    if prior is None:",
     f"{DI}::test_another_companys_prior_is_not_a_prior"),

    # --- D. non-impacts stop being persisted ---------------------------
    ("D. only changed impacts are written, so the rate has no denominator",
     E / "decision_impact.py",
     "    target.parent.mkdir(parents=True, exist_ok=True)\n"
     "    payload[\"record\"] = \"decision_impact\"",
     "    if not impact.changed:\n"
     "        return False\n"
     "    target.parent.mkdir(parents=True, exist_ok=True)\n"
     "    payload[\"record\"] = \"decision_impact\"",
     f"{DI}::test_a_none_impact_is_recorded_too"),

    # --- E. the revision store stops discriminating --------------------
    ("E. an unchanged dossier appends a fresh revision every cycle",
     E / "decision_impact.py",
     "    if prior and str(prior.get(\"revision_key\")) == key:\n"
     "        return False",
     "    if False:\n"
     "        return False",
     f"{DI}::test_an_unchanged_revision_is_not_appended_twice"),

    # --- F. the content key stops being content ------------------------
    ("F. two different states hash to the same revision key",
     E / "decision_impact.py",
     "    payload = \"|\".join(\n"
     "        f\"{field}:{';'.join(sorted(_content(state.get(field, ()))))}\"\n"
     "        for field in IMPACT_TYPES)",
     "    payload = \"constant\"",
     f"{DI}::test_the_revision_key_is_content_addressed"),

    # --- G. unprovenanced change credited ------------------------------
    ("G. a field that moved with no evidence behind it credits the engine",
     E / "decision_impact.py",
     "    if grade != NONE and not provenance:",
     "    if False:",
     f"{DI}::test_an_unprovenanced_change_gets_no_credit"),

    # --- H. wording promoted to meaning --------------------------------
    ("H. whitespace and case count as a decision change",
     E / "decision_impact.py",
     "def _norm(text: object) -> str:",
     "def _norm(text: object) -> str:\n"
     "    return str(text)\n\n\n"
     "def _unused_norm(text: object) -> str:",
     f"{DI}::test_a_wording_only_change_is_not_meaningful"),

    # --- I. a real change stops registering ----------------------------
    ("I. the comparison refuses everything, which also passes 'no false "
     "positives'",
     E / "decision_impact.py",
     "    grade = materiality_of(deltas)",
     "    grade = NONE",
     f"{DI}::test_a_changed_dossier_still_grades_an_impact"),

    # --- J. the live-corpus guard ---------------------------------------
    ("J. the live corpus stops being checked for a second-pass NONE",
     E / "decision_impact.py",
     "    if prior is None:",
     "    if prior is None or True:",
     f"{DI}::test_the_live_corpus_grades_none_on_a_second_identical_pass"),
]

# --- NOT_BUILT ------------------------------------------------------------
#
# "a different evidence cutoff is refused as a paired comparison" has no guard
# to break. `assess_against_prior` compares two SEMANTIC STATES and neither
# carries an evidence cutoff — the dossier's `as_of` is recorded on the
# revision row for audit and nothing reads it back as a gate. Writing a proof
# against it would be demonstrating the absence of a code path, and the honest
# record is that this wall does not exist yet.
NOT_BUILT = 1



TRANSPORT_PROOFS = [
    # --- missing history impersonates a quiet thesis --------------------
    ("K. an absent history is read as 'nothing has changed this view'",
     E / "decision_impact.py",
     "    if not isinstance(stated, dict) or not stated.get(\"status\"):\n"
     "        return HISTORY_UNAVAILABLE",
     "    if not isinstance(stated, dict) or not stated.get(\"status\"):\n"
     "        return HISTORY_AVAILABLE_NO_MOVEMENT",
     f"{DI}::test_missing_history_is_not_no_movement"),

    # --- CREATED counted as a change of mind ---------------------------
    ("L. an opening revision counts as a transition",
     E / "decision_impact.py",
     "    moved = [r for r in (getattr(intel, \"thesis_revisions\", ()) or ())\n"
     "             if str(r.get(\"transition\") or \"\") != _OPENING_TRANSITION]",
     "    moved = list(getattr(intel, \"thesis_revisions\", ()) or ())",
     f"{DI}::test_created_only_says_nothing_has_changed_it"),

    # --- a causeless transition is presented as an answer --------------
    ("M. a transition with no effect or evidence is reported as supported",
     E / "decision_impact.py",
     "    if not effects and not evidence:",
     "    if False:",
     f"{DI}::test_a_transition_with_no_cause_is_not_a_supported_answer"),

    # --- an unknown status is trusted ----------------------------------
    ("N. an unrecognised history status is passed through",
     E / "decision_impact.py",
     "    return status if status in (",
     "    return status or HISTORY_AVAILABLE_NO_MOVEMENT if True else (",
     f"{DI}::test_an_unknown_status_is_treated_as_unavailable"),
]

PROOFS.extend(TRANSPORT_PROOFS)



CA_T = f"{T}/test_ceo_answers.py"

QA_PROOFS = [
    ("O. a leading question is answered instead of adjudicated",
     E / "ceo_answers.py",
     "    if leading_premise(text):\n        return CHALLENGE",
     "    if False:\n        return CHALLENGE",
     f"{CA_T}::test_a_leading_question_is_challenged"),

    ("P. an unrecognised question gets a default class",
     E / "ceo_answers.py",
     "    return UNKNOWN_QUESTION\n\n\ndef leading_premise",
     "    return CURRENT_STATE\n\n\ndef leading_premise",
     f"{CA_T}::test_an_unrecognised_question_is_not_guessed"),

    ("Q. a missing causal hop is bridged rather than named",
     E / "ceo_answers.py",
     "    if cls in (WHY, WHY_IT_MATTERS) and stopped is not None:",
     "    if False:",
     f"{CA_T}::test_a_missing_hop_stops_the_causal_statement"),

    ("R. an absent alternative reads as an uncontested view",
     E / "ceo_answers.py",
     '            "No competing explanation is recorded for this view. That is a "\n'
     '            "gap in the analysis rather than evidence the view is "\n'
     '            "uncontested.", source_constraints=constraints,',
     '            "No competing explanation applies here.",\n'
     '            source_constraints=constraints,',
     f"{CA_T}::test_an_absent_alternative_is_not_consensus"),

    ("S. the certainty wall stops reading the plan's standing",
     E / "ceo_answers.py",
     "    return tuple(word for word in FORBIDDEN_UPGRADES\n"
     "                 if f\" {word} \" in lowered)",
     "    return ()",
     f"{CA_T}::test_a_renderer_may_not_upgrade_the_standing"),

    ("T. a degraded source stops caveating the answer",
     E / "ceo_answers.py",
     "    if not impaired:\n        return ()",
     "    if True:\n        return ()",
     f"{CA_T}::test_a_degraded_source_reduces_visibility_not_activity"),

    ("U. 'what changed' is answered with the mind-change record",
     E / "ceo_answers.py",
     "    if cls == WHAT_CHANGED:\n"
     "        return _what_changed(question, intel, constraints)",
     "    if cls == WHAT_CHANGED:\n"
     "        return _changed_your_mind(question, intel, constraints)",
     f"{CA_T}::test_what_changed_is_not_what_changed_your_mind"),
]

PROOFS.extend(QA_PROOFS)


if __name__ == "__main__":
    raise SystemExit(run_all(
        [Proof(*p) for p in PROOFS],
        title=(f"ceo — decision impact + transport + CEO answers: {len(PROOFS)} proofs, "
               f"{NOT_BUILT} recorded NOT_BUILT")))
