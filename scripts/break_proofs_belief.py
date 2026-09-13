#!/usr/bin/env python3
"""Break proofs for the competitive ladder and the belief layer (§24).

Each mutation re-creates a failure this cycle actually produced and measured,
or one the design is specifically bounded against. A proof counts only if the
source hash changes, the named test was green before, turns RED after, and the
failure text matches what the proof says it is about.

Run:  PYTHONPATH=src python scripts/break_proofs_belief.py
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from break_proof_harness import Proof, run_all           # noqa: E402

ROOT = HERE.parent
LADDER = ROOT / "src/intent_engine/executive/competitive_ladder.py"
GROUND = ROOT / "src/intent_engine/executive/competitive_ground.py"
BELIEFS = ROOT / "src/intent_engine/executive/beliefs.py"
GRAPH = ROOT / "src/intent_engine/executive/assumption_graph.py"

COMPETITOR_TESTS = "tests/test_a_competitor_need_not_be_a_company.py"
BELIEF_TESTS = "tests/test_a_belief_that_cannot_be_wrong_is_a_mood.py"

PROOFS = [
    # --- the competitive ladder -------------------------------------------
    Proof(
        label="1. a competitor may exist with no mechanism",
        path=LADDER,
        find='        if not (self.mechanism or "").strip():',
        replace='        if False:',
        target=f"{COMPETITOR_TESTS}::TestEveryRowIsAClaim::"
               f"test_a_rival_without_a_mechanism_is_refused",
        expect_failure_contains="RivalRefused"),

    Proof(
        label="2. a competitor may exist that nothing could disprove",
        path=LADDER,
        find='        if not (self.disproof or "").strip():',
        replace='        if False:',
        target=f"{COMPETITOR_TESTS}::TestEveryRowIsAClaim::"
               f"test_a_rival_that_cannot_be_wrong_is_refused",
        expect_failure_contains="RivalRefused"),

    Proof(
        label="3. an attributed rung may assert without quoting",
        path=LADDER,
        find="        if self.rung in ATTRIBUTED and not (self.evidence or \"\").strip():",
        replace="        if False:",
        target=f"{COMPETITOR_TESTS}::TestEveryRowIsAClaim::"
               f"test_an_attributed_rung_must_quote",
        expect_failure_contains="RivalRefused"),

    Proof(
        label="4. a third party's filing becomes this company's market",
        path=LADDER,
        find='        if source_class not in ("investor_material", "executive_statement",\n'
             '                                "company_owned"):',
        replace='        if False:',
        target=f"{COMPETITOR_TESTS}::TestOnlyTheSubjectsOwnWords::"
               f"test_a_third_partys_filing_is_not_this_companys_market",
        expect_failure_contains="assert"),

    Proof(
        label="5. marketing prose becomes a customer-named competitor",
        path=LADDER,
        find='                    if not re.match(r"^[A-Z][A-Za-z0-9&.\\-]*$", words[0] or ""):',
        replace="                    if False:",
        target=f"{COMPETITOR_TESTS}::TestMigrationSentences::"
               f"test_marketing_prose_is_not_a_competitor",
        expect_failure_contains="assert"),

    Proof(
        label="6. a migration away from us is filed as a win",
        path=LADDER,
        find="                if not (dest_words & subject_words):",
        replace="                if False:",
        target=f"{COMPETITOR_TESTS}::TestMigrationSentences::"
               f"test_a_migration_between_two_other_companies_is_not_ours",
        expect_failure_contains="assert"),

    Proof(
        label="7. competitive FACTORS are read as competitors",
        path=LADDER,
        find="    head = words[-1].lower().strip(\",.;:\")\n"
             "    if head not in _CATEGORY_HEAD:\n"
             "        return False",
        replace="    head = words[-1].lower().strip(\",.;:\")\n"
                "    if False:\n"
                "        return False",
        target=f"{COMPETITOR_TESTS}::TestTheCompanysOwnCategories::"
               f"test_a_price_is_not_a_competitor",
        expect_failure_contains="assert"),

    Proof(
        label="8. a list fragment is presented as a rival category",
        path=LADDER,
        find="    if words[0].lower() in _FRAGMENT_LEAD:\n        return False",
        replace="    if False:\n        return False",
        target=f"{COMPETITOR_TESTS}::TestTheCompanysOwnCategories::"
               f"test_a_fragment_is_not_a_category",
        expect_failure_contains="assert"),

    Proof(
        label="9. one kind of alternative takes the whole ladder",
        path=GROUND,
        find="        if taken_kinds.get(rival.kind, 0) >= _MAX_PER_KIND:\n            return",
        replace="        if False:\n            return",
        target=f"{COMPETITOR_TESTS}::"
               f"TestTheLadderCoversGroundRatherThanEnumerating::"
               f"test_one_kind_may_not_take_the_whole_table",
        expect_failure_contains="assert"),

    Proof(
        label="10. a run with no competitive statement names no measurement",
        path=GROUND,
        find="    if attributed or categories:\n        measurement = \"\"",
        replace="    if True:\n        measurement = \"\"",
        target=f"{COMPETITOR_TESTS}::"
               f"TestTheLadderCoversGroundRatherThanEnumerating::"
               f"test_a_run_with_no_competitive_statement_names_the_measurement",
        expect_failure_contains="assert"),

    Proof(
        label="11. a rival carries no reaction (level-k removed)",
        path=GROUND,
        find="            counter_move=counter,",
        replace="            counter_move=\"\",",
        target=f"{COMPETITOR_TESTS}::"
               f"TestTheLadderCoversGroundRatherThanEnumerating::"
               f"test_every_row_carries_a_reaction",
        expect_failure_contains="assert"),

    # --- the belief layer --------------------------------------------------
    Proof(
        label="12. a belief may move with no evidence that moved it",
        path=BELIEFS,
        find="        if self.disposition in MOVED and not \\\n"
             "                (self.strongest_contradiction or \"\").strip():",
        replace="        if False:",
        target=f"{BELIEF_TESTS}::TestManufacturedDoubtIsRefused::"
               f"test_a_belief_may_not_move_without_evidence",
        expect_failure_contains="BeliefRefused"),

    Proof(
        label="13. a belief may be asserted with no derivation",
        path=BELIEFS,
        find="        if self.source_basis != OBSERVED and not (self.basis_detail or \"\").strip():",
        replace="        if False:",
        target=f"{BELIEF_TESTS}::TestABeliefMustBeTestable::"
               f"test_an_inferred_belief_must_name_its_derivation",
        expect_failure_contains="BeliefRefused"),

    Proof(
        label="14. a belief may imply nothing observable",
        path=BELIEFS,
        find="        if not self.implied_expectations:",
        replace="        if False:",
        target=f"{BELIEF_TESTS}::TestABeliefMustBeTestable::"
               f"test_a_belief_with_no_implied_expectation_is_refused",
        expect_failure_contains="BeliefRefused"),

    Proof(
        label="15. a belief may carry no falsifier",
        path=BELIEFS,
        find="        if not self.falsifiers:",
        replace="        if False:",
        target=f"{BELIEF_TESTS}::TestABeliefMustBeTestable::"
               f"test_a_belief_with_no_falsifier_is_refused",
        expect_failure_contains="BeliefRefused"),

    Proof(
        label="16. an unconventional hypothesis needs no way to settle it",
        path=BELIEFS,
        find='            if not (getattr(self, field) or "").strip():',
        replace="            if False:",
        target=f"{BELIEF_TESTS}::TestAnUnconventionalHypothesisIsBounded::"
               f"test_provocation_without_a_way_to_settle_it_is_refused",
        expect_failure_contains="BeliefRefused"),

    Proof(
        label="17. an attack need not state the case FOR the belief",
        path=BELIEFS,
        find='        if not (self.strongest_support or "").strip():',
        replace="        if False:",
        target=f"{BELIEF_TESTS}::TestManufacturedDoubtIsRefused::"
               f"test_an_attack_that_cannot_state_the_case_for_has_not_attacked",
        expect_failure_contains="BeliefRefused"),

    Proof(
        label="18. uncertainty may be stated with no test",
        path=BELIEFS,
        find='        if not (self.cheapest_test or "").strip():',
        replace="        if False:",
        target=f"{BELIEF_TESTS}::TestManufacturedDoubtIsRefused::"
               f"test_uncertainty_without_a_test_is_refused",
        expect_failure_contains="BeliefRefused"),

    Proof(
        label="19. the most dangerous reading collapses onto the most likely",
        path=BELIEFS,
        find="        if likely is not None and len(ranked) > 1 \\\n"
             "                and ranked[0].hypothesis == likely.hypothesis:\n"
             "            return ranked[1]\n"
             "        return ranked[0]",
        replace="        return ranked[0]",
        target=f"{BELIEF_TESTS}::TestTheFourReadingsPointSomewhereUseful::"
               f"test_the_most_dangerous_is_not_the_most_likely",
        expect_failure_contains="assert"),

    # --- the assumption graph ---------------------------------------------
    Proof(
        label="20. a well-supported chain is warned about anyway",
        path=GRAPH,
        find="        if SUPPORT_RANK.get(link.standing, 9) <= SUPPORT_RANK[INFERRED]:",
        replace="        if False:",
        target=f"{BELIEF_TESTS}::TestTheWeakestLinkIsFoundNotAsserted::"
               f"test_a_fully_supported_chain_names_no_weakest_link",
        expect_failure_contains="assert"),

    Proof(
        label="21. a broken link is ranked instead of reported",
        path=GRAPH,
        find="        broken = self.contradicted\n        if broken:",
        replace="        broken = self.contradicted\n        if False:",
        target=f"{BELIEF_TESTS}::TestTheWeakestLinkIsFoundNotAsserted::"
               f"test_a_contradicted_link_is_reported_rather_than_ranked",
        expect_failure_contains="assert"),

    Proof(
        label="22. a step may be drawn with no reason under it",
        path=GRAPH,
        find='        if not (self.because or "").strip():',
        replace="        if False:",
        target=f"{BELIEF_TESTS}::TestTheWeakestLinkIsFoundNotAsserted::"
               f"test_a_step_with_no_reason_is_refused",
        expect_failure_contains="GraphRefused"),

    Proof(
        label="23. the settle sentence is composed from node labels again",
        path=GRAPH,
        find='    if (link.settled_by or "").strip():\n        return link.settled_by.strip()',
        replace="    if False:\n        return link.settled_by.strip()",
        target=f"{BELIEF_TESTS}::TestTheWeakestLinkIsFoundNotAsserted::"
               f"test_the_settle_sentence_comes_from_the_producer",
        expect_failure_contains="assert"),
]


if __name__ == "__main__":
    raise SystemExit(run_all(
        PROOFS, title="BREAK PROOFS — competitive ladder and belief layer"))
