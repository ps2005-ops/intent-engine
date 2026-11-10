"""Break proofs for H-CON-001: the standing consistency wall.

Each proof removes one rule and names the test that must go red. The set is
chosen so that the two failures this node was opened for are pinned by
mutation rather than by assertion:

  * a proof package outranking the thesis it proves (proof 1), which was live;
  * a fact about the record rendered as a finding about the world (proofs 3, 6).

Proof 2 is the one to read if only one is read. A cap that fires only for
REFUTED would have looked correct on the live corpus — every published thesis
is PROPOSED — and would have let a PROPOSED thesis report a VERIFIED proof for
as long as nothing was ever refuted.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

M = ROOT / "src/intent_engine/market"
T = "tests"
SW = f"{T}/test_market_standing_wall.py"

PROOFS = [
    # --- the proof may not outrank the thesis ---------------------------
    ("1. a refuted thesis proves itself verified",
     M / "economic_thesis.py",
     "        if not self.thesis_standing:\n            return raw",
     "        if True:\n            return raw",
     f"{SW}::test_a_refuted_thesis_cannot_produce_a_verified_proof"),

    ("2. the cap fires only for an abandoned reading",
     M / "economic_thesis.py",
     "        if SW.permits(self.thesis_standing, raw):\n            return raw",
     "        if SW.ceiling(self.thesis_standing) != SW.ASSERT_NEGATIVE:\n"
     "            return raw",
     f"{SW}::test_the_cap_is_graded_rather_than_binary"),

    ("3. the cap overwrites the evidential reading instead of capping it",
     M / "economic_thesis.py",
     "        raw = self.evidential_status\n",
     "        raw = OPEN\n",
     f"{SW}::test_the_evidential_status_survives_the_cap"),

    # The cap must only ever LOWER. It does so structurally: a permitted
    # evidential status returns before the search for a weaker one begins.
    # Removing that early return makes the search run every time, and the
    # search starts at VERIFIED — so a TESTED thesis whose evidence supports
    # only BOUNDED comes back VERIFIED. Standing would be substituting for
    # evidence, which is the inverse of what this cap is for.
    ("4. standing is allowed to raise a proof as well as lower it",
     M / "economic_thesis.py",
     "        if SW.permits(self.thesis_standing, raw):\n            return raw",
     "        if False:\n            return raw",
     f"{SW}::test_a_proof_is_never_raised_by_the_thesis"),

    ("4b. the cap gives up instead of finding the weaker status",
     M / "economic_thesis.py",
     "        for candidate in (VERIFIED, BOUNDED, OPEN):",
     "        for candidate in (VERIFIED,):",
     f"{SW}::test_the_cap_is_graded_rather_than_binary"),

    # --- record states are not weak world states ------------------------
    ("5. a record state is treated as a faint claim about the world",
     M / "standing_wall.py",
     "    if state in RECORD_STATES:\n"
     "        # A fact about the record licenses no assertion about the world.",
     "    if state in RECORD_STATES:\n"
     "        return ASSERT_LEADING\n"
     "    if False:",
     f"{SW}::test_a_record_state_licenses_no_assertion"),

    ("6. one record state may stand in for another",
     M / "standing_wall.py",
     "    if is_record_state(a) or is_record_state(b):\n        return False",
     "    if is_record_state(a) or is_record_state(b):\n        return True",
     f"{SW}::test_history_unavailable_and_no_movement_are_not_interchangeable"),

    ("7. an abandoned reading is ranked as a weak positive one",
     M / "standing_wall.py",
     "    if ceiling_ == ASSERT_NEGATIVE:\n"
     "        raise CategoryError(",
     "    if False:\n"
     "        raise CategoryError(",
     f"{SW}::test_ranking_a_negative_ceiling_is_a_category_error"),

    ("8. a causal-hop standing is silently accepted as a thesis standing",
     M / "standing_wall.py",
     "    if state in HOP_STANDINGS:\n"
     "        raise StandingViolation(",
     "    if state in HOP_STANDINGS:\n"
     "        return ASSERT_BOUNDED\n"
     "    if False:\n"
     "        raise StandingViolation(",
     f"{SW}::test_a_hop_standing_is_rejected_rather_than_mapped"),

    ("9. an unrecognised standing is mapped onto the nearest known one",
     M / "standing_wall.py",
     '    raise StandingViolation(f"unknown state {state!r}")',
     "    return ASSERT_LEADING",
     f"{SW}::test_an_unknown_state_raises_rather_than_defaulting"),

    # --- the certainty ceiling has to move ------------------------------
    ("10. the forbidden vocabulary stops moving with the standing",
     M / "standing_wall.py",
     "    out: list = []\n"
     "    for step in _NARROWING:\n"
     "        out.extend(_BANNED_AT[step])\n"
     "        if step == ceiling_:\n"
     "            break\n"
     "    return tuple(dict.fromkeys(out))",
     "    return tuple(_BANNED_AT[ASSERT_TESTED])",
     f"{SW}::test_the_forbidden_vocabulary_narrows_as_the_record_weakens"),

    ("11. the strongest standing licenses everything",
     M / "standing_wall.py",
     '    ASSERT_TESTED: ("guaranteed", "risk-free", "cannot fail", "no doubt",\n'
     '                    "will certainly", "certain to", "beyond doubt",\n'
     '                    "proves", "proven", "proof that", "definitely",\n'
     '                    "certainly", "always", "never fails", "must be"),',
     "    ASSERT_TESTED: (),",
     f"{SW}::test_the_strongest_standing_still_forbids_something"),

    ("11b. the middle rung of the ladder is dead",
     M / "standing_wall.py",
     '    ASSERT_BOUNDED: ("withstood", "held up under", "survived every",\n'
     '                     "stress-tested", "we tried to break", "ruled out",\n'
     '                     "verified", "confirms", "confirmed"),',
     "    ASSERT_BOUNDED: (),",
     f"{SW}::test_every_rung_of_the_ladder_forbids_something_new"),

    # --- the cross-surface adjudication ---------------------------------
    ("12. a slide may claim more than the thesis behind it",
     M / "standing_wall.py",
     "            if not permits(thesis_state, claim.state):",
     "            if False:",
     f"{SW}::test_a_proposed_thesis_cannot_become_a_confirmed_slide"),

    ("13. an abandoned reading may still be reported as holding",
     M / "standing_wall.py",
     "        return ren in (ASSERT_NEGATIVE, ASSERT_NONE)",
     "        return True",
     f"{SW}::test_an_abandoned_reading_may_not_be_reported_as_holding"),

    ("14. the wall stops at the first disagreement",
     M / "standing_wall.py",
     "    for claim in surfaces:\n"
     "        try:",
     "    for claim in surfaces[:1]:\n"
     "        try:",
     f"{SW}::test_every_disagreement_is_reported_not_just_the_first"),

    ("15. a dropped alternative is tolerated below the assertable line",
     M / "standing_wall.py",
     "        if has_alternatives and not claim.keeps_alternatives:",
     "        if False:",
     f"{SW}::test_a_dropped_alternative_is_caught_at_every_standing"),

    ("16. a dropped falsifier is tolerated",
     M / "standing_wall.py",
     "        if has_falsifiers and not claim.keeps_falsifiers:",
     "        if False:",
     f"{SW}::test_a_dropped_falsifier_is_caught"),

    ("17. certainty language is not adjudicated with the standing",
     M / "standing_wall.py",
     "        for word in words_beyond(claim.text, claim.state):",
     "        for word in ():",
     f"{SW}::test_certainty_language_is_adjudicated_with_the_rest"),

    # --- what crosses the bridge ----------------------------------------
    ("18. the bare standing crosses instead of the adjudicated ceiling",
     M / "strategic_export.py",
     '    return {"ceiling": exported["ceiling"],\n'
     '            "forbidden_words": exported["forbidden_words"]}',
     '    return {"ceiling": "", "forbidden_words": []}',
     f"{SW}::test_the_ceiling_survives_the_export_projection"),

    ("19. an overclaiming proof is exported rather than refused",
     M / "standing_wall.py",
     "        if not permits(thesis_state, proof_status):\n"
     "            raise StandingViolation(",
     "        if False:\n"
     "            raise StandingViolation(",
     f"{SW}::test_exporting_an_overclaiming_proof_is_refused_at_the_boundary"),

    ("20. an unknown standing crosses as a guess rather than as silence",
     M / "strategic_export.py",
     "    except SW.StandingViolation:\n"
     '        return {"ceiling": "", "forbidden_words": []}',
     "    except SW.StandingViolation:\n"
     '        return {"ceiling": SW.ASSERT_LEADING, "forbidden_words": []}',
     f"{SW}::test_an_unknown_standing_crosses_as_no_ceiling_rather_than_a_guess"),

    # --- the fourth history state ---------------------------------------
    ("21. an empty history reports that nothing moved",
     M / "strategic_export.py",
     '            "status": HISTORY_AVAILABLE_NO_THESIS, "revisions": 0,',
     '            "status": HISTORY_AVAILABLE_NO_MOVEMENT, "revisions": 0,',
     f"{SW}::test_zero_revisions_is_not_a_finding_about_movement"),

    ("22. the new state swallows the one it was distinguished from",
     M / "strategic_export.py",
     "    if not rows:\n",
     "    if True:\n",
     f"{SW}::test_an_opened_but_unmoved_thesis_still_reports_no_movement"),

    ("23. an unreadable history is folded into an empty one",
     M / "strategic_export.py",
     '            "status": HISTORY_UNAVAILABLE, "revisions": 0, "moved": 0,',
     '            "status": HISTORY_AVAILABLE_NO_THESIS, "revisions": 0,\n'
     '            "moved": 0,',
     f"{SW}::test_an_unreadable_history_is_still_unavailable"),

    ("24. the live corpus is no longer checked for movement claims from "
     "nothing",
     M / "strategic_export.py",
     "    rows = [_revision(r) for r in revisions]\n    if not rows:",
     "    rows = [_revision(r) for r in revisions] or [{}]\n    if not rows:",
     f"{SW}::test_live_revision_lists_never_produce_a_movement_claim_from_nothing"),
]


if __name__ == "__main__":
    sys.exit(run_all(
        [Proof(*p) for p in PROOFS],
        title=(f"v4l — H-CON-001, the standing consistency wall: "
               f"{len(PROOFS)} proofs")))
