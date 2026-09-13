"""Break proofs for the consumer half of H-CON-001.

Two of these restore defects that were live at the start of this run and that
34 tests and 21 break proofs had not caught, because both were invisible to
any test written from the same mental model as the code:

  * proof B restores a certainty wall whose standing exemption tested for
    values the field can never hold, so the "ceiling" applied one fixed word
    list to every standing;
  * proof C restores `supported=True`, which read the mere presence of a
    thesis row as support for its claim, including for readings the producer
    had refused.

Proof F is the one to read if only one is read. It restores the reading that
put "nothing has changed this view yet" into 22 of the 25 published dossiers,
describing companies for which no view had ever been formed.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

E = ROOT / "src/intent_engine/external_intel"
T = "tests"
SC = f"{T}/test_founder_standing_ceiling.py"
CEO = f"{T}/test_ceo_answers.py"

PROOFS = [
    # --- A. the mirror ---------------------------------------------------
    ("A. an unknown standing falls to confidence rather than to silence",
     E / "standing_ceiling.py",
     "    if state in RECORD_STATES:\n"
     "        return ASSERT_NONE\n"
     "    return ASSERT_NONE",
     "    if state in RECORD_STATES:\n"
     "        return ASSERT_NONE\n"
     "    return ASSERT_BOUNDED",
     f"{SC}::test_an_unknown_standing_falls_to_silence_not_to_confidence"),

    ("B. the certainty wall stops moving with the standing",
     E / "standing_ceiling.py",
     "    out: list = []\n"
     "    for step in _NARROWING:\n"
     "        out.extend(_BANNED_AT[step])\n"
     "        if step == ceiling_:\n"
     "            break\n"
     "    return tuple(dict.fromkeys(out))",
     "    return tuple(_BANNED_AT[ASSERT_TESTED])",
     f"{SC}::test_the_wall_moves_with_the_standing"),

    ("C. an abandoned reading is a supported answer again",
     E / "ceo_answers.py",
     "        supported=SC.may_assert(ceiling_),",
     "        supported=True,",
     f"{SC}::test_an_abandoned_reading_is_not_a_supported_answer"),

    ("D. an abandoned reading is presented as the current one",
     E / "ceo_answers.py",
     "    if not SC.may_assert(ceiling_):\n"
     "        answer = _abandoned_reading(leading, answer, ceiling_)",
     "    if False:\n"
     "        answer = _abandoned_reading(leading, answer, ceiling_)",
     f"{SC}::test_an_abandoned_reading_is_reported_rather_than_hidden"),

    ("E. a live reading is refused along with the abandoned ones",
     E / "standing_ceiling.py",
     "    return ceiling_ in (ASSERT_LEADING, ASSERT_BOUNDED, ASSERT_TESTED)",
     "    return ceiling_ == ASSERT_TESTED",
     f"{SC}::test_a_live_reading_is_still_supported"),

    # --- the fourth history state ----------------------------------------
    ("F. zero revisions reads as a view that held still",
     E / "decision_impact.py",
     "    if status == HISTORY_AVAILABLE_NO_MOVEMENT and not _revisions(intel):\n"
     "        return HISTORY_AVAILABLE_NO_THESIS",
     "    if False:\n"
     "        return HISTORY_AVAILABLE_NO_THESIS",
     f"{SC}::test_zero_revisions_is_not_a_settled_view"),

    ("G. the new state swallows the one it was distinguished from",
     E / "decision_impact.py",
     "    if status == HISTORY_AVAILABLE_NO_MOVEMENT and not _revisions(intel):",
     "    if status == HISTORY_AVAILABLE_NO_MOVEMENT:",
     f"{SC}::test_a_real_no_movement_still_reads_as_no_movement"),

    ("H. the four history states share one answer",
     E / "decision_impact.py",
     "    if state == HISTORY_AVAILABLE_NO_THESIS:\n"
     "        return {\n"
     '            "state": state, "answer": (\n'
     '                "Nothing, because there is no view here yet. No economic "',
     "    if False:\n"
     "        return {\n"
     '            "state": state, "answer": (\n'
     '                "Nothing, because there is no view here yet. No economic "',
     f"{SC}::test_the_four_history_states_answer_differently"),

    ("I. one warning is reused for every history state",
     E / "ceo_answers.py",
     "    if state == di.HISTORY_AVAILABLE_NO_THESIS:\n"
     '        return ("an absence of analysis is not a finding about this '
     'company; "\n'
     '                "nothing here says the situation is quiet",)',
     "    if state == di.HISTORY_AVAILABLE_NO_THESIS:\n"
     '        return ("an absence of recorded change is not evidence the view '
     'is "\n'
     '                "settled; it may only mean nothing has tested it yet",)',
     f"{SC}::test_the_four_history_states_answer_differently"),

    ("J. a history state is rendered as a standing about the world",
     E / "ceo_answers.py",
     "        standing=got[\"state\"], ceiling=SC.from_standing(got[\"state\"]),",
     "        standing=got[\"state\"], ceiling=SC.ASSERT_BOUNDED,",
     f"{SC}::test_a_history_state_asserts_nothing_about_the_world"),

    ("K. an unknown producer status is read as a quiet thesis",
     E / "decision_impact.py",
     "    if status not in _KNOWN_HISTORY_STATES:\n"
     "        return HISTORY_UNAVAILABLE",
     "    if status not in _KNOWN_HISTORY_STATES:\n"
     "        return HISTORY_AVAILABLE_NO_MOVEMENT",
     f"{SC}::test_an_unknown_history_status_is_unavailable_not_settled"),

    # --- the bridge -------------------------------------------------------
    ("L. the ceiling is decided before the downgrade rather than after",
     E / "strategic_contract.py",
     '        row["ceiling"] = SC.ceiling_for(row)',
     '        row["ceiling"] = str(row.get("ceiling") or "") or '
     'SC.ceiling_for(row)',
     f"{SC}::test_the_consumer_re_decides_the_ceiling_after_it_downgrades"),

    ("M. a producer claiming more than this side is obeyed",
     E / "standing_ceiling.py",
     "    return stricter_of(transported, local)",
     "    return transported or local",
     f"{SC}::test_a_transported_ceiling_cannot_loosen_a_local_one"),

    ("N. an unrecognised ceiling is mapped onto the nearest one",
     E / "standing_ceiling.py",
     "    if transported and transported not in CEILINGS:\n"
     "        # An unrecognised ceiling is not mapped onto the nearest one.\n"
     "        transported = ASSERT_NONE",
     "    if transported and transported not in CEILINGS:\n"
     "        transported = ASSERT_TESTED",
     f"{SC}::test_an_unrecognised_transported_ceiling_is_not_mapped_to_the_nearest"),

    # --- the two vocabularies --------------------------------------------
    ("O. the thesis standing is copied into the hop slot again",
     E / "ceo_answers.py",
     "        Hop(\"THESIS\", _hop_standing(thesis),",
     "        Hop(\"THESIS\", str(thesis.get(\"standing\") or HYPOTHESIZED),",
     f"{SC}::test_the_thesis_hop_speaks_the_hop_vocabulary"),

    ("P. an abandoned thesis hop reads as nothing being known",
     E / "ceo_answers.py",
     '    "REFUTED": CONTRADICTED,',
     '    "REFUTED": MISSING,',
     f"{SC}::test_an_abandoned_thesis_hop_is_contradicted_not_missing"),
]


if __name__ == "__main__":
    sys.exit(run_all(
        [Proof(*p) for p in PROOFS],
        title=(f"standing — the consumer half of the standing wall: "
               f"{len(PROOFS)} proofs")))
