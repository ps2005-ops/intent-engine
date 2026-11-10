"""Batch 13: evidence → knowledge effect, and what may not be claimed from it.

Criterion 10 was UNAVAILABLE because no seam existed to attribute at. These
pin the seam, and most of them pin what it REFUSES:

  - evidence that merely mentions an object has not changed it;
  - a raw effect count is not a numerator over evidence rows;
  - a blocked backend is not a measured zero;
  - independent origins behind a change are not interchangeable with copies.
"""
import pytest

from intent_engine.company_ingestion.independence import assess
from intent_engine.company_ingestion.learning_attribution import (
    BLOCKED_EXTERNAL_CREDITS, CONTRADICTED, MEASURED, NOT_ATTEMPTED,
    NO_CHANGE, SUPPORTED, THESIS, UNAVAILABLE, EffectRejected, KnowledgeEffect,
    NotAChange, conversion, evidence_structure,
)


def _effect(evidence_id, target_id="t1", effect_type=SUPPORTED,
            before="weak", after="strong"):
    return KnowledgeEffect(
        evidence_id=evidence_id, target_type=THESIS, target_id=target_id,
        effect_type=effect_type, before_state=before, after_state=after,
        reason="a filing restated capacity", created_at="2026-08-13")


# --- about is not changed (§19) --------------------------------------------
def test_evidence_merely_about_a_thesis_is_not_a_change():
    with pytest.raises(NotAChange):
        _effect("e1", before="held", after="held")


def test_no_change_is_recordable_and_is_not_an_error():
    """An effect log that keeps only positives cannot price a retrieval."""
    effect = KnowledgeEffect(
        evidence_id="e1", target_type=THESIS, target_id="t1",
        effect_type=NO_CHANGE, before_state="held", after_state="held",
        reason="read and did not bear on the thesis")
    assert effect.effect_type == NO_CHANGE


def test_an_effect_without_its_evidence_is_refused():
    with pytest.raises(EffectRejected):
        KnowledgeEffect(evidence_id="", target_type=THESIS, target_id="t1",
                        effect_type=NO_CHANGE, reason="x")


def test_an_effect_without_a_reason_is_refused():
    with pytest.raises(EffectRejected):
        KnowledgeEffect(evidence_id="e1", target_type=THESIS, target_id="t1",
                        effect_type=NO_CHANGE, reason="   ")


def test_unknown_target_or_effect_type_is_refused():
    with pytest.raises(EffectRejected):
        KnowledgeEffect(evidence_id="e", target_type="VIBES", target_id="t",
                        effect_type=NO_CHANGE, reason="x")
    with pytest.raises(EffectRejected):
        KnowledgeEffect(evidence_id="e", target_type=THESIS, target_id="t",
                        effect_type="IMPROVED", reason="x")


# --- blocked is not zero (§21) ---------------------------------------------
def test_blocked_backend_is_not_a_measured_zero():
    """THE DEFECT THIS PROGRAMME KEEPS FINDING, in its newest location."""
    out = conversion(evidence_rows=[{"source_id": "a"}, {"source_id": "b"}],
                     knowledge_layer_ran=False)
    assert out["attribution_state"] == BLOCKED_EXTERNAL_CREDITS
    assert out["learning_conversion"] == UNAVAILABLE
    assert out["zero_effect_evidence_rows"] == UNAVAILABLE
    # the row count is still reported: it is a fact we DO have
    assert out["evidence_rows"] == 2


def test_a_ran_but_unwritten_ledger_is_not_the_same_as_blocked():
    """Three states, not two: the seam existing and being unused is its own
    finding, and is what this cohort would show if credits were restored."""
    out = conversion(evidence_rows=[{"source_id": "a"}],
                     knowledge_layer_ran=True)
    assert out["attribution_state"] == NOT_ATTEMPTED


# --- populations (§22) ------------------------------------------------------
def test_numerator_counts_rows_not_effects():
    """One row that moved four objects is ONE row that produced an effect.

    Counting effects here is how a rate exceeds 1, which this programme has
    already shipped once.
    """
    effects = [_effect("a", target_id=f"t{i}") for i in range(4)]
    out = conversion(evidence_rows=[{"source_id": "a"}, {"source_id": "b"}],
                     effects=effects)
    assert out["knowledge_effects"] == 4
    assert out["effect_producing_evidence_rows"] == 1
    assert out["learning_conversion"] == 0.5
    assert out["zero_effect_evidence_rows"] == 1


def test_no_change_effects_do_not_count_as_learning():
    out = conversion(
        evidence_rows=[{"source_id": "a"}],
        effects=[KnowledgeEffect(evidence_id="a", target_type=THESIS,
                                 target_id="t1", effect_type=NO_CHANGE,
                                 reason="read, changed nothing")])
    assert out["effect_producing_evidence_rows"] == 0
    assert out["learning_conversion"] == 0.0
    assert out["attribution_state"] == MEASURED


def test_conversion_over_an_empty_population_is_unavailable_not_zero():
    out = conversion(evidence_rows=[], effects=[])
    assert out["learning_conversion"] == UNAVAILABLE


# --- independence behind a change (§20) ------------------------------------
def _doc(source_id, url, source_class, filing=False):
    return {"source_id": source_id, "final_url": url,
            "source_class": source_class, "filing": filing,
            "content_hash": source_id,
            "text_content": f"{source_id} distinct wording here " * 30}


def test_one_release_and_its_copies_are_not_three_independent_origins():
    """§20's whole point, stated as a comparison the caller can see.

    The syndicated fixture must carry ONE body across three hosts. An earlier
    version gave each mirror its own wording, so they were genuinely separate
    accounts and the comparison proved nothing — the property held for a
    reason unrelated to the code.
    """
    release = "acme announces a new plant in ohio this quarter " * 30
    syndicated = assess([
        dict(_doc("r0", "https://acme.example/press", "company_owned"),
             text_content=release),
        dict(_doc("r1", "https://mirror1.example/a", "independent_reporting"),
             text_content=release),
        dict(_doc("r2", "https://mirror2.example/b", "independent_reporting"),
             text_content=release),
    ])["rows"]
    assert [r["lineage"] for r in syndicated].count(
        "DERIVED_REPUBLICATION") == 2
    diverse = assess([
        _doc("d0", "https://acme.example/press", "company_owned"),
        _doc("d1", "https://www.sec.gov/Archives/edgar/data/9/x.htm",
             "competitor", filing=True),
        _doc("d2", "https://www.sec.gov/Archives/edgar/data/8/y.htm",
             "competitor", filing=True),
    ])["rows"]
    thin = evidence_structure(["r0", "r1", "r2"], syndicated)
    thick = evidence_structure(["d0", "d1", "d2"], diverse)
    assert thin["document_count"] == thick["document_count"] == 3
    assert thick["independent_origin_count"] > thin["independent_origin_count"]


def test_evidence_ids_with_no_lineage_row_are_reported_not_dropped():
    structure = evidence_structure(["ghost"], [])
    assert structure["unmatched_evidence_ids"] == ["ghost"]
    assert structure["independent_origin_count"] == 0


def test_a_change_carries_the_structure_of_its_support():
    rows = assess([
        _doc("d1", "https://www.sec.gov/Archives/edgar/data/9/x.htm",
             "competitor", filing=True),
        _doc("d2", "https://www.sec.gov/Archives/edgar/data/8/y.htm",
             "competitor", filing=True),
    ])["rows"]
    out = conversion(
        evidence_rows=[{"source_id": "d1"}, {"source_id": "d2"}],
        effects=[_effect("d1"), _effect("d2")],
        independence_rows=rows)
    assert len(out["changes"]) == 1
    support = out["changes"][0]["support"]
    assert support["independent_origin_count"] == 2
    assert out["independent_effect_producing_evidence_rows"] == 2


def test_independent_conversion_denominator_is_independent_rows_only():
    """A share must divide by the population it is a share OF."""
    rows = assess([
        _doc("i1", "https://www.sec.gov/Archives/edgar/data/9/x.htm",
             "competitor", filing=True),
        _doc("c1", "https://acme.example/about", "company_owned"),
    ])["rows"]
    out = conversion(evidence_rows=[{"source_id": "i1"}, {"source_id": "c1"}],
                     effects=[_effect("i1")], independence_rows=rows)
    # one independent row, and it produced an effect -> 1.0, not 0.5
    assert out["independent_learning_conversion"] == 1.0


def test_contradiction_is_a_change_like_any_other():
    out = conversion(
        evidence_rows=[{"source_id": "a"}],
        effects=[_effect("a", effect_type=CONTRADICTED,
                         before="held", after="retired")])
    assert out["effects_by_type"] == {CONTRADICTED: 1}
    assert out["effect_producing_evidence_rows"] == 1
