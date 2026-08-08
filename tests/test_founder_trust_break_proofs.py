"""Every trust guard, proven load-bearing by breaking it.

A guard nobody has broken is a guard nobody has checked. Each proof mutates
the real source, requires the bytes to change, requires the named test to turn
RED for the stated reason, and requires an exact restore. A mutation that
changes bytes and nothing that runs is reported NOT_CAUGHT rather than passed —
that verdict is a finding about the guard, not a failure of the harness.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]
                       / "scripts"))

from break_proof_harness import HELD, INVALID, Proof, ROOT, verify  # noqa: E402

TRUST = ROOT / "src/intent_engine/external_intel/evidence_trust.py"
GRAPH = ROOT / "src/intent_engine/business_graph/projections.py"
PACK = ROOT / "src/intent_engine/external_intel/pack.py"
CONTRACT = ROOT / "src/intent_engine/external_intel/strategic_contract.py"
IMPACT = ROOT / "src/intent_engine/external_intel/decision_impact.py"
RECEIPT = ROOT / "src/intent_engine/external_intel/consumption_receipt.py"

QA = ROOT / "src/intent_engine/founder_brief/qa.py"

T = "tests/test_founder_evidence_trust.py"
S = "tests/test_founder_trust_surfaces.py"

PROOFS = [
    # 1. three SAME_ORIGIN articles act like three independent supports
    Proof(label="dependent cluster becomes three supports",
          path=GRAPH,
          find="        for event in _occurrences(belief, trust):",
          replace="        for event in _occurrences(belief, ET.UNRATED):",
          target=f"{T}::test_three_same_origin_reports_are_one_support_in_the_graph",
          expect_failure_contains="assert"),

    # 2. a dependent cluster matures the belief anyway
    Proof(label="dependent cluster still matures the belief",
          path=GRAPH,
          find="    if trust.known and trust.must_bound:\n        return _UNCORROBORATED",
          replace="    if False:\n        return _UNCORROBORATED",
          target=f"{T}::test_a_dependent_cluster_does_not_mature_the_belief",
          expect_failure_contains="assert"),

    # 3. independent corroboration flattened to one weak observation
    #
    # Mutated at the READ, not at a weight table: this side has no weight
    # table, because the weights are the market's judgement and arrive on the
    # wire. Discarding them here is exactly how the flattening would happen.
    Proof(label="independence flattened",
          path=TRUST,
          find='        weight=float(block.get("weight") or 0.0),',
          replace='        weight=1.0,',
          target=f"{T}::test_the_independent_case_keeps_the_stronger_standing",
          expect_failure_contains="assert"),

    # 4. a conflicted event is treated as confirmation
    Proof(label="conflicted reads as confirmed",
          path=GRAPH,
          find="    if trust.standing == ET.CONFLICTED:\n        return _DISPUTED",
          replace="    if False:\n        return _DISPUTED",
          target=f"{T}::test_conflicted_evidence_cannot_become_a_confident_conclusion",
          expect_failure_contains="assert"),

    # 5. the standing moves the wording but licenses the same claims
    Proof(label="dependent may still claim independence",
          path=TRUST,
          find="_MAY_CLAIM_INDEPENDENCE = frozenset({INDEPENDENTLY_CORROBORATED})",
          replace=("_MAY_CLAIM_INDEPENDENCE = frozenset("
                   "{INDEPENDENTLY_CORROBORATED, DEPENDENT_REREPORTING})"),
          target=f"{T}::test_the_independent_case_keeps_the_stronger_standing",
          expect_failure_contains="assert"),

    # 6. DecisionImpact counts only the citation, missing the bounding line
    Proof(label="bounding line invisible to the metric",
          path=IMPACT,
          find='        if block.get("evidence_standing"):\n            bounded.append(str(block["evidence_standing"]))',
          replace='        if False:\n            bounded.append("")',
          target=f"{T}::test_the_bounding_sentence_reaches_the_decision_comparison",
          expect_failure_contains="assert"),

    # 7/8. internal vocabulary reaches a rendered surface
    Proof(label="wire vocabulary reaches the page",
          path=GRAPH,
          find='                "trust_sentence": ET.sentence(trust),',
          replace='                "trust_sentence": "standing: " + trust.standing.lower(),',
          target=f"{T}::test_no_internal_standing_name_reaches_a_rendered_block",
          expect_failure_contains="assert"),

    # 9. trust provenance loses the event identity
    Proof(label="provenance loses the rows",
          path=GRAPH,
          find='                       "evidence_ids": list(event.evidence_ids),',
          replace='                       "evidence_ids": [],',
          target=f"{T}::test_grouping_never_deletes_a_row",
          expect_failure_contains="assert"),

    # 10. the raw ids stop reaching the rendered block
    Proof(label="rendered block loses provenance",
          path=PACK,
          find="                evidence_ids.extend(str(i) for i in ids)",
          replace="                pass",
          target=f"{T}::test_the_rendered_block_still_carries_every_raw_id",
          expect_failure_contains="assert"),

    # 11. an unnormalized dossier silently reads as a normalized one
    Proof(label="absent standing becomes single observation",
          path=TRUST,
          find="        return UNRATED\n    standing = str(block.get",
          replace="        return Trust(SINGLE_SOURCE, 1, 1, 1, 1.0, '')\n    standing = str(block.get",
          target=f"{T}::test_an_unnormalized_dossier_is_unknown_rather_than_confirmed",
          expect_failure_contains="assert"),

    # 12. the unknown case borrows the dependent sentence
    Proof(label="unknown borrows the dependent claim",
          path=TRUST,
          find='    UNKNOWN:\n        "How independent the sources behind this are was not established, so "\n        "it is not treated as confirmed.",',
          replace='    UNKNOWN:\n        "The reports behind this do not independently confirm each other, so "\n        "it is weaker than the number of articles suggests.",',
          target=f"{T}::test_an_unnormalized_dossier_does_not_borrow_the_dependent_sentence",
          expect_failure_contains="assert"),

    # 13. this side starts re-deriving trust from a row count
    Proof(label="consumer re-derives from source counts",
          path=TRUST,
          find="def weigh(trusts: Sequence[Trust]) -> float:",
          replace="def classify(rows):\n    return len(rows)\n\n\ndef weigh(trusts: Sequence[Trust]) -> float:",
          target=f"{T}::test_the_founder_side_never_classifies_from_a_source_count",
          expect_failure_contains="assert"),

    # 14. an undeclared field rides in on the trust block
    #
    # The fail-closed branch itself, not the schema entry: adding a key to
    # `_TRUST` proved nothing, because the validator refuses unknown keys
    # regardless of how many known ones sit beside them. Disabling the
    # refusal is the mutation that tests whether the walk reaches this depth.
    # Fails OPEN rather than crashing: replacing the raise with nothing left
    # the walk to KeyError on the undeclared key, which is red for an
    # unrelated reason and the harness rejected it as WRONG_REASON. Skipping
    # the key is what "the allowlist stopped guarding" actually looks like.
    Proof(label="allowlist stops failing closed",
          path=CONTRACT,
          find='            if key not in spec:\n                raise StrategicLeak(',
          replace=('            if key not in spec:\n'
                   '                continue\n'
                   '            if False:\n                raise StrategicLeak('),
          target="tests/test_founder_trust_contract.py::test_an_undeclared_field_in_the_trust_block_is_refused",
          expect_failure_contains="assert"),

    # 15. availability is counted as use
    Proof(label="availability counted as use",
          path=RECEIPT,
          find='    if trust["normalized_events_available"]:',
          replace="    if True:",
          target="tests/test_founder_trust_contract.py::test_an_unnormalized_dossier_emits_no_trust_stage",
          expect_failure_contains="assert"),

    # 16. the raw source count comes back to Q&A
    #
    # Restores the rule as it actually shipped: a verdict computed from how
    # many rows survived a publisher-class filter, reported to a founder as
    # independent support.
    Proof(label="row count decides the Q&A verdict again",
          path=QA,
          find="    if trust.known:\n        if trust.standing == _ET.CONFLICTED:",
          replace="    if n >= 2:\n        return ('Probably — ' + str(n) + "
                  "' independent source(s) support this.')\n"
                  "    if trust.known:\n        if trust.standing == _ET.CONFLICTED:",
          target=f"{S}::test_a_dependent_cluster_is_not_reported_as_independent_support",
          expect_failure_contains="assert"),

    # 17. Q&A stops discriminating: every standing gives one answer
    Proof(label="Q&A ignores the standing",
          path=QA,
          find="    if trust.known:\n        if trust.standing == _ET.CONFLICTED:",
          replace="    if False:\n        if trust.standing == _ET.CONFLICTED:",
          target=f"{S}::test_dependent_and_independent_differ_on_identical_rows",
          expect_failure_contains="assert"),

    # 18. an old analysis is re-rated by a dossier published after it
    Proof(label="newer dossier rewrites the old analysis",
          path=TRUST,
          find="    if ran and revision and revision > ran:\n        return UNRATED",
          replace="    if False:\n        return UNRATED",
          target=f"{S}::test_a_dossier_from_after_the_analysis_is_not_applied_to_it",
          expect_failure_contains="assert"),

    # 19. the pin over-fires and withholds every standing, which would look
    #     like historical stability while silently deleting the feature
    Proof(label="the pin withholds everything",
          path=TRUST,
          find="    ran = str(analysis_as_of or \"\")[:10]",
          replace="    return UNRATED\n    ran = str(analysis_as_of or \"\")[:10]",
          target=f"{S}::test_the_dossier_the_analysis_actually_read_still_applies",
          expect_failure_contains="assert"),

    # 21. the projection goes back to normalizing every belief twice
    Proof(label="belief normalized twice per dossier",
          path=GRAPH,
          find="            confidence=belief_standing(belief, trust),",
          replace="            confidence=belief_standing(belief),",
          target=f"{S}::test_the_projection_normalizes_each_belief_once",
          expect_failure_contains="normalizations for"),

    # 20. the Q&A limitation stops being carried, so a bounded standing is
    #     acted on but never disclosed
    Proof(label="standing bounds silently",
          path=QA,
          find="        _caveat = _ET.limitation(trust)",
          replace="        _caveat = \"\"",
          target=f"{S}::test_the_standing_earns_its_limitation_on_the_evidence_surface",
          expect_failure_contains="assert"),
]


@pytest.mark.parametrize("proof", PROOFS, ids=lambda p: p.label)
def test_the_guard_is_load_bearing(proof):
    got = verify(proof)
    assert got.verdict not in INVALID, f"{proof.label}: {got.detail}"
    assert got.verdict == HELD, f"{proof.label}: {got.verdict} — {got.detail}"
