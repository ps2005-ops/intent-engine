#!/usr/bin/env python3
"""Break proofs for thesis identity and one-to-one reconciliation.

G-THE-004. The defect this wave guards was live for two cycles and looked
green the whole time: `compared: 11` sat beside `loaded: 7` in a persisted
report, and every downstream number was internally consistent with it.

Each proof reintroduces one part of that defect and names the test that must
go RED for it. The harness holds a mutation lock, verifies the file hash
changed, requires the named test to fail for the stated reason, restores the
exact bytes and clears the bytecode.

    python3 scripts/break_proofs_v4e.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
S = ROOT / "src" / "intent_engine" / "market"

ET = S / "economic_thesis.py"
TH = S / "thesis_history.py"
ST = S / "steps.py"
PR = S / "presentation.py"

H = "tests/test_market_thesis_history.py"
W = "tests/test_market_thesis_history_wiring.py"
E = "tests/test_market_economic_thesis.py"
D = "tests/test_market_demand_and_deck.py"

PROOFS = [
    # --- identity carries what distinguishes two theses -------------------
    ("v4e-1. two economies moving one condition share an identity",
     ET,
     "            self.area,\n            self.question,",
     "            self.question,",
     f"{H}::test_two_economies_moving_one_condition_are_two_theses",
     "assert"),

    ("v4e-2. a reworded claim becomes a different thesis",
     ET,
     "            self.leading_mechanism.identity_key,\n        )",
     "            self.leading_mechanism.identity_key,\n            self.claim,\n        )",
     f"{H}::test_a_claim_that_moved_by_a_word_is_still_the_same_thesis",
     "assert"),

    ("v4e-3. a restatement tomorrow becomes a different thesis",
     ET,
     "            self.leading_mechanism.identity_key,\n        )",
     "            self.leading_mechanism.identity_key,\n            self.as_of,\n        )",
     f"{H}::test_a_restatement_on_a_later_date_is_the_same_thesis",
     "assert"),

    ("v4e-4. two mechanisms answering one question collapse into one thesis",
     ET,
     "            self.leading_mechanism.identity_key,\n        )",
     "        )",
     f"{H}::test_two_mechanisms_answering_one_question_are_two_theses",
     "assert"),

    ("v4e-5. a reworded mechanism restarts the thesis's history",
     ET,
     "        return self.key.strip() or self.description.strip()",
     "        return self.description.strip()",
     f"{H}::test_rewording_a_catalogue_mechanism_does_not_restart_its_history",
     "assert"),

    # --- the match is one-to-one -----------------------------------------
    ("v4e-6. one prior is compared against by several current theses",
     TH,
     "        if prior is not None and key in consumed:",
     "        if False:",
     f"{H}::test_a_prior_is_never_compared_against_twice",
     "compared"),

    ("v4e-7. two priors sharing an identity are silently folded to one",
     TH,
     "            counts[\"identity_collisions\"] += 1\n            continue\n        before[key] = prior_thesis",
     "            pass\n        before[key] = prior_thesis",
     f"{H}::test_two_priors_sharing_an_identity_are_refused_not_silently_dropped",
     "assert"),

    ("v4e-8. loaded reports distinct identities rather than priors held",
     TH,
     "    counts[\"loaded\"] = len(previous)",
     "    counts[\"loaded\"] = len(before)",
     f"{H}::test_two_priors_sharing_an_identity_are_refused_not_silently_dropped",
     "assert"),

    ("v4e-9. a prior nobody rebuilt is not reported as unmatched",
     TH,
     "    counts[\"unmatched_prior\"] = len(previous) - len(consumed)",
     "    counts[\"unmatched_prior\"] = 0",
     f"{H}::test_a_prior_with_no_current_thesis_is_counted_unmatched",
     "assert"),

    # --- attribution names an object the thesis rests on ------------------
    ("v4e-10. the exposure basis drops the company and matches every one",
     TH,
     "        out.add(text if text.startswith(prefix) else prefix + text)",
     "        out.add(text)",
     f"{H}::test_an_effect_on_this_companys_exposure_bears_on_its_thesis",
     "assert"),

    ("v4e-11. an unrelated effect evidences this thesis",
     TH,
     "        elif target_id and target_id in basis:",
     "        elif target_id:",
     f"{H}::test_an_effect_on_another_object_does_not_evidence_this_thesis",
     "assert"),

    ("v4e-12. a condition's economy is dropped from the basis",
     TH,
     "        out.add(f\"{area}:{kind}\" if area else kind)",
     "        out.add(kind)",
     f"{H}::test_an_effect_on_this_economys_condition_bears_on_its_thesis",
     "assert"),

    # --- the seam inside the cycle ---------------------------------------
    ("v4e-13. the chain is rebuilt empty every night",
     ST,
     "        history, unreadable = THI.ThesisHistory.load(stored_revisions)",
     "        history, unreadable = THI.ThesisHistory(), []",
     f"{W}::test_the_chain_is_reloaded_rather_than_rebuilt_empty",
     "assert"),

    ("v4e-14. a rehydrated thesis loses the economy it was about",
     ST,
     "            area=str(row.get(\"area\") or \"\"),",
     "            area=\"\",",
     f"{W}::test_a_second_cycle_compares_no_more_theses_than_it_loaded",
     "assert"),

    ("v4e-15. a rehydrated mechanism loses its catalogue key",
     ST,
     "            key=str(d.get(\"key\") or \"\"))",
     "            key=\"\")",
     f"{W}::test_a_second_cycle_compares_no_more_theses_than_it_loaded",
     "assert"),

    ("v4e-16. theses sharing an identity are not counted",
     ST,
     "                len(theses) - len({t.thesis_id for t in theses})),",
     "                0),",
     f"{W}::test_a_collision_the_step_cannot_prevent_is_still_counted",
     "assert"),

    ("v4e-17. a briefing inherits another economy's reason for moving",
     ST,
     "        reasons = {(s.area, s.state_kind): s.reason for s in states if s.known}",
     "        reasons = {(\"\", s.state_kind): s.reason for s in states if s.known}",
     f"{W}::test_each_briefing_carries_its_own_economys_reason",
     "assert"),

    # --- a surface may not outlive the claim it renders --------------------
    ("v4e-18. a deck keeps asserting a claim the thesis withdrew",
     PR,
     "    elif deck.claim and deck.claim != thesis.claim:",
     "    elif False:",
     f"{D}::test_a_deck_still_asserting_a_withdrawn_claim_is_caught",
     "assert"),

    ("v4e-19. a wording-only supersession puts two rows under one id",
     ET,
     "    if successor.thesis_id == previous.thesis_id:",
     "    if False:",
     f"{E}::test_a_supersession_that_only_rewords_the_claim_is_refused",
     "DID NOT RAISE"),
]


if __name__ == "__main__":
    sys.exit(run_all([Proof(*p) for p in PROOFS], title="V4e"))
