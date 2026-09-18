"""Break proofs for E-DEM-001: subject-, role- and standing-aware demand.

Every proof here removes one of the four questions the extractor asks and
checks that the corpus notices. Removing them all is what the phrase list
already did, and it scored precision 0.50.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

M = ROOT / "src/intent_engine/market"
T = "tests"
DX = f"{T}/test_market_demand_extraction.py"

PROOFS = [
    # --- 1. the role gate ----------------------------------------------
    ("1. company procurement is admitted as customer demand",
     M / "demand_extraction.py",
     "    role, evidence = _role_of(sentence, aliases)\n"
     "    if role != SELLER:",
     "    role, evidence = _role_of(sentence, aliases)\n"
     "    if False:",
     f"{DX}::test_the_company_buying_is_not_customer_demand"),

    # --- 2. the subject gate -------------------------------------------
    ("2. a rival's bookings are attributed to us",
     M / "demand_extraction.py",
     "    if owner in (COMPETITOR, MARKET) or state in _MARKET_STATES:",
     "    if False:",
     f"{DX}::test_a_rivals_demand_is_not_ours"),

    # --- 3. the standing gate ------------------------------------------
    ("3. an expectation is admitted as an observed demand fact",
     M / "demand_extraction.py",
     "    if standing != OBSERVATION and state not in _EXPECTATION_STATES:",
     "    if False:",
     f"{DX}::test_an_expectation_is_not_an_observation"),

    # --- 4. the domain guards ------------------------------------------
    ("4. a ticket backlog counts as committed demand",
     M / "demand_extraction.py",
     "        if any(d.search(text) for d in disqualifiers):",
     "        if False:",
     f"{DX}::test_the_same_word_in_another_domain"),

    # --- 5. guidance loses its exemption -------------------------------
    ("5. the speculation gate refuses every guidance sentence",
     M / "demand_extraction.py",
     '_EXPECTATION_STATES = frozenset({"GUIDANCE"})',
     "_EXPECTATION_STATES = frozenset()",
     f"{DX}::test_guidance_is_allowed_to_be_forward_looking"),

    # --- 6. direction invented -----------------------------------------
    ("6. a sentence with both directions picks one anyway",
     M / "demand_extraction.py",
     "    if up and down:",
     "    if False:",
     f"{DX}::test_two_directions_in_one_sentence_refuses_to_pick"),

    # --- 7. false numeric precision ------------------------------------
    ("7. a qualitative reading is marked quantitative",
     M / "demand_extraction.py",
     "standing=standing, quantitative=bool(quantity),",
     "standing=standing, quantitative=True,",
     f"{DX}::test_a_qualitative_reading_carries_no_false_precision"),

    # --- 8. refusal reasons collapse -----------------------------------
    ("8. every refusal reports the same reason",
     M / "demand_extraction.py",
     "        return Reading(None, role=role, reason=WRONG_ROLE,",
     "        return Reading(None, role=role, reason=NO_COMMERCIAL_OBJECT,",
     f"{DX}::test_each_refusal_reports_the_reason_that_applies"),

    # --- 9. the admission seam -----------------------------------------
    ("9. demand sentences never become canonical evidence",
     M / "evidence_translation.py",
     "                if demand.admitted:\n"
     "                    etype = ME.DEMAND_SIGNAL",
     "                if False:\n"
     "                    etype = ME.DEMAND_SIGNAL",
     f"{DX}::test_a_demand_sentence_becomes_evidence"),

    # --- 10. the wrong-role sentence gets in through the seam ----------
    ("10. the admission seam skips the role gate",
     M / "evidence_translation.py",
     "                demand = DX.read(candidate.text, aliases=aliases)",
     "                demand = DX.read(candidate.text, aliases=())",
     f"{DX}::test_a_wrong_role_sentence_does_not_become_evidence"),

    # --- 11. the two readers disagree ----------------------------------
    ("11. the chain reads demand with the old phrase list again",
     M / "demand_chain.py",
     "            reading = DX.read(sentence, aliases=aliases)\n"
     "            if not reading.admitted:\n"
     "                continue",
     "            reading = DX.read(sentence, aliases=())\n"
     "            if False:\n"
     "                continue",
     f"{DX}::test_demand_chain_refuses_the_procurement_sentence"),

    # --- 12. DEMAND_SIGNAL falls out of the vocabulary ------------------
    ("12. a type the seam produces is refused by the constructor",
     M / "micro_evidence.py",
     "    COMMITTED_DEMAND, COST_SHOCK, DEMAND_SIGNAL,",
     "    COMMITTED_DEMAND, COST_SHOCK,",
     f"{DX}::test_demand_signal_is_a_constructible_type"),
]

# --- NOT_BUILT ------------------------------------------------------------
#
# "a demand contradiction changes a thesis" has no guard to break. The live
# corpus has ONE demand state per company at most outside REVENUE and
# GUIDANCE, so no company has two demand states that could disagree, and the
# contradiction shapes in `demand_corpus.CONTRADICTIONS` are exercised as
# readings rather than as a fold. Building the fold to break would be a test
# about a code path no live data reaches.
NOT_BUILT = 1

if __name__ == "__main__":
    raise SystemExit(run_all(
        [Proof(*p) for p in PROOFS],
        title=(f"v4k — E-DEM-001 demand extraction: {len(PROOFS)} proofs, "
               f"{NOT_BUILT} recorded NOT_BUILT")))
