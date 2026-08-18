#!/usr/bin/env python3
"""§10. Break the economic-actor qualification deliberately.

Three mutations, each restoring a shipped or a plausible defect:

  A  every named entity is allowed into the direct-rival list — the state
     before this repair, which put an index, a payer programme and a captive
     lender's competitors in "contested most directly by";

  B  every non-company alternative is demoted — the OPPOSITE overreach, and
     the reason this is a qualification and not a "must be a company" test:
     open-source AI, the in-house build, the manual workflow and doing
     nothing are legitimate competitive alternatives and the ladder depends
     on them;

  C  REGULATOR, FINANCIER and COMPLEMENT collapse into COMPETITOR — the
     shape of the defect §4 exists to prevent, where "what is this thing"
     and "how does it relate to us" become one question again.

Plus the two seams the last repair in this area died at: the qualification
must reach the object the renderer receives, and selection must not fall
back to the alphabet.

Run:  PYTHONPATH=src python3 scripts/break_proofs_economic_actor.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all       # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
Q = ROOT / "src/intent_engine/executive/competitive_qualification.py"
F = ROOT / "src/intent_engine/external_intel/competitor_finder.py"
T = "tests/test_a_name_in_a_contest_is_not_an_alternative.py"

PROOFS = [
    # --- MUTATION A: every named entity may contest ------------------------
    ("A1. an index is allowed into the competitive claim",
     Q,
     "    if entity == ENTITY_INDEX_PROVIDER:",
     "    if False:",
     f"{T}::test_the_qualification_matrix",
     "qualification_state"),

    ("A2. a payer programme is allowed into the competitive claim",
     Q,
     "    if entity == ENTITY_PROGRAM:",
     "    if False:",
     f"{T}::test_the_qualification_matrix",
     "qualification_state"),

    ("A3. a clause that says nothing about competing still qualifies",
     Q,
     "    if not (contests or substitutes):\n"
     "        return refuse(INCIDENTALLY_NAMED, UNKNOWN,\n"
     "                      \"the clause naming this entity does not say a "
     "contest \"",
     "    if False:\n"
     "        return refuse(INCIDENTALLY_NAMED, UNKNOWN,\n"
     "                      \"the clause naming this entity does not say a "
     "contest \"",
     f"{T}::test_the_qualification_matrix",
     "qualification_state"),

    ("A4. the whole passage is read instead of the name's own clause",
     Q,
     "    clause = governing_clause(evidence, name) or (evidence or \"\").strip()",
     "    clause = (evidence or \"\").strip()",
     f"{T}::test_the_quoted_evidence_is_the_clause_that_names_the_candidate",
     "evidence_basis"),

    ("A5. a lender contesting the financing is called a direct rival",
     Q,
     "    if entity == ENTITY_FINANCIER and \\\n"
     "            (business_model or \"\").upper() not in _FINANCING_MODELS:",
     "    if False:",
     f"{T}::test_the_qualification_matrix",
     "qualification_state"),

    ("A6. a segment's contest is published as the company's",
     Q,
     "    if owner:\n"
     "        if not (contests or substitutes):",
     "    if False:\n"
     "        if not (contests or substitutes):",
     f"{T}::test_the_qualification_matrix",
     "qualification_state"),

    # --- MUTATION B: the opposite overreach --------------------------------
    #
    # Demoting every non-company would delete the alternatives the ladder is
    # built on. This mutation makes the financier rule fire on EVERY subject,
    # including a bank — whose rivals are banks — and the matrix's negative
    # control is what refuses it.
    ("B1. a bank's rivals are demoted because they are financial",
     Q,
     "_FINANCING_MODELS = frozenset({\"BALANCE_SHEET_OR_NETWORK\", \"BANK\",\n"
     "                               \"INSURANCE\"})",
     "_FINANCING_MODELS = frozenset()",
     f"{T}::test_the_qualification_matrix",
     "qualification_state"),

    ("B2. an adjacent threat is promoted to the direct sentence",
     Q,
     "MAY_CONTEST_DIRECTLY = (DIRECT_COMPETITOR, SUBSTITUTE_STATE)",
     "MAY_CONTEST_DIRECTLY = (DIRECT_COMPETITOR, SUBSTITUTE_STATE,\n"
     "                        ADJACENT_THREAT_STATE)",
     f"{T}::test_only_three_states_may_reach_a_competitive_claim",
     "MAY_CONTEST_DIRECTLY"),

    # --- MUTATION C: the two questions collapse into one -------------------
    ("C1. REGULATOR, FINANCIER and PROGRAM collapse into the competitive set",
     Q,
     "MAY_CONTEST = (DIRECT_COMPETITOR, SUBSTITUTE_STATE, "
     "ADJACENT_THREAT_STATE)",
     "MAY_CONTEST = (DIRECT_COMPETITOR, SUBSTITUTE_STATE, "
     "ADJACENT_THREAT_STATE,\n"
     "               REGULATOR_STATE, FINANCIER_STATE, PROGRAM_OR_POLICY)",
     f"{T}::test_only_three_states_may_reach_a_competitive_claim",
     "MAY_CONTEST"),

    ("C2. a competitive claim may be made without a customer choice",
     Q,
     "            if not self.customer_choice_possible:\n"
     "                raise QualificationRefused(",
     "            if False:\n"
     "                raise QualificationRefused(",
     f"{T}::test_a_competitive_state_requires_a_customer_choice",
     "QualificationRefused"),

    ("C3. a competitive claim may be made without a mechanism",
     Q,
     "            if not (self.substitution_mechanism or \"\").strip():\n"
     "                raise QualificationRefused(",
     "            if False:\n"
     "                raise QualificationRefused(",
     f"{T}::test_a_competitive_state_requires_a_substitution_mechanism",
     "QualificationRefused"),

    # --- THE SEAMS ---------------------------------------------------------
    ("D1. the qualification stops at the extractor and never reaches the row",
     F,
     "                        qualification_state=qualification."
     "qualification_state,",
     "                        qualification_state=\"\",",
     f"{T}::test_the_extractor_carries_the_qualification_onto_the_competitor",
     "qualification_state"),

    ("D2. the refused candidates are dropped instead of routed",
     F,
     "    if refusals is not None:\n        refusals.extend(refused)",
     "    if False:\n        refusals.extend(refused)",
     f"{T}::"
     "test_the_extractor_hands_back_what_it_refused_and_where_it_belongs",
     "Regulation and payer economics"),

    ("D3. selection falls back to the alphabet",
     F,
     "                                order.get(c.name.lower(), 10_000),\n"
     "                                c.name.lower()))",
     "                                c.name.lower()))",
     f"{T}::test_selection_is_not_alphabetical",
     "Wabtec"),
]


if __name__ == "__main__":
    raise SystemExit(run_all(
        [Proof(*p) for p in PROOFS],
        title=f"economic-actor qualification: {len(PROOFS)} proofs"))
