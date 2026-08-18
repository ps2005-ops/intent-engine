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
    # --- §8 THE SENTENCE CONTRACT ------------------------------------------
    ("E1. the kind dies at the projection and every row reads as direct",
     ROOT / "src/intent_engine/executive/strategic_read.py",
     "            kind=rival.kind,",
     "            kind=\"\",",
     f"{T}::test_the_kind_survives_the_projection_into_the_read",
     "kind"),

    ("E2. an in-house build is announced as a direct contest",
     ROOT / "src/intent_engine/executive/strategic_read.py",
     "_BUILD_KINDS = (\"BUILD_IN_HOUSE\",)",
     "_BUILD_KINDS = ()",
     f"{T}::test_an_in_house_build_is_not_described_as_a_direct_contest",
     "internalise the work"),

    ("E3. doing nothing is announced as a rival",
     ROOT / "src/intent_engine/executive/strategic_read.py",
     "_INERTIA_KINDS = (\"MANUAL_WORKFLOW\", \"DO_NOTHING\")",
     "_INERTIA_KINDS = ()",
     f"{T}::test_doing_nothing_is_described_as_delay_not_as_a_rival",
     "delaying the purchase"),

    ("E4. a phrase read off the model is capitalised like a company",
     ROOT / "src/intent_engine/executive/strategic_read.py",
     "    return _lower_first(name)",
     "    return name",
     f"{T}::"
     "test_a_retrieved_firm_keeps_its_capital_and_a_read_phrase_does_not",
     "another surface"),
    # --- §6 THE ROUTING REACHES A READER -----------------------------------
    ("F1. the run stops collecting the refusals",
     ROOT / "src/intent_engine/executive/strategic_read.py",
     "        named = _named_rivals(name, documents, profile=profile,\n"
     "                              refusals=refused)",
     "        named = _named_rivals(name, documents, profile=profile)",
     f"{T}::test_the_run_collects_the_refusals_rather_than_discarding_them",
     "refusals"),

    ("F2. the ground stops carrying what was routed",
     ROOT / "src/intent_engine/executive/strategic_read.py",
     "            other_relationships=_routed(refused))",
     "            other_relationships=())",
     f"{T}::test_the_run_collects_the_refusals_rather_than_discarding_them",
     "other_relationships"),

    ("F3. the full analysis stops rendering them",
     ROOT / "src/intent_engine/founder_brief/dossier.py",
     "    if not rows:\n        return []\n    by_section: dict = {}",
     "    if True:\n        return []\n    by_section: dict = {}",
     f"{T}::test_the_full_analysis_renders_the_routed_relationships",
     "Medicare Part D"),
    # --- ONE RUN MAY NOT SAY TWO THINGS ------------------------------------
    ("G1. a failed run keeps rendering analysis on four of six steps",
     ROOT / "src/intent_engine/webapp/app.py",
     "        if availability.get(\"state\") == \"FAILED\" \\\n"
     "                and not availability.get(\"has_report\"):",
     "        if False:",
     "tests/test_one_run_may_not_say_two_things.py::"
     "test_a_failed_run_with_no_report_is_refused_on_every_step",
     "failed"),

    ("G2. the guard over-refuses a run that did compose a report",
     ROOT / "src/intent_engine/webapp/app.py",
     "        if availability.get(\"state\") == \"FAILED\" \\\n"
     "                and not availability.get(\"has_report\"):",
     "        if availability.get(\"state\") == \"FAILED\":",
     "tests/test_one_run_may_not_say_two_things.py::"
     "test_a_failed_run_that_still_composed_a_report_is_not_refused",
     "is None"),
    ("G3. step 4 keeps its own ownership check and skips the shared guard",
     ROOT / "src/intent_engine/webapp/app.py",
     "        blocked = self._step_guard(session, run_id)\n"
     "        if blocked is not None:\n"
     "            return blocked\n"
     "        from intent_engine.founder_brief import layers as fl",
     "        if not self._owned(session, run_id):\n"
     "            return self._error_page(404, \"no such run\")\n"
     "        from intent_engine.founder_brief import layers as fl",
     "tests/test_one_run_may_not_say_two_things.py::"
     "test_every_step_page_goes_through_the_shared_guard",
     "_story_page"),
]


if __name__ == "__main__":
    raise SystemExit(run_all(
        [Proof(*p) for p in PROOFS],
        title=f"economic-actor qualification: {len(PROOFS)} proofs"))
