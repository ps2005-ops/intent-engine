"""Batch 13: independence reaches the founder's dossier, and says what it means.

Batch 12 left this seam open and described it as an allowlist gap. It was not:
`evidence_independence_state` was already allowed, and the PRODUCER hardcoded
`INDEPENDENCE_UNAVAILABLE`. The field existed, crossed the contract, and
carried a constant — so every dossier reported independence as unmeasured no
matter what retrieval found.

These pin both halves: the block crosses without being silently dropped into
`unknown_fields`, and the sentence it carries cannot overstate what is behind
it.
"""
from intent_engine.company_ingestion.independence import assess, describe
from intent_engine.demo_dossier import vocabulary as V
from intent_engine.demo_dossier.contracts import read_founder_snapshot
from intent_engine.external_intel.founder_demo_snapshot import build_payload


def _doc(source_id, url, source_class, filing=False, body=None):
    return {"source_id": source_id, "final_url": url,
            "source_class": source_class, "filing": filing,
            "content_hash": source_id,
            "text_content": body or f"{source_id} wording " * 30}


def _snapshot(documents, **kwargs):
    independence = assess(documents) if documents is not None else None
    payload = build_payload(run_id="r1", company_id="acme",
                            canonical_name="Acme, Inc.",
                            independence=independence, **kwargs)
    return read_founder_snapshot(payload, expected_company="acme"), payload


# --- the block crosses (§23) -----------------------------------------------
def test_independence_block_is_not_dropped_into_unknown_fields():
    """THE BRIDGE-NEVER-OPENED FAILURE, checked directly rather than assumed."""
    snap, _ = _snapshot([_doc("a", "https://acme.example/x", "company_owned")])
    assert snap.unknown_fields == ()
    assert snap.contract_state != V.CONTRACT_INCOMPATIBLE
    assert snap.evidence_independence is not None


def test_measured_independence_reaches_the_dossier_as_available():
    snap, _ = _snapshot([
        _doc("own", "https://www.sec.gov/Archives/edgar/data/1/a.htm",
             "investor_material", filing=True),
        _doc("ual", "https://www.sec.gov/Archives/edgar/data/2/b.htm",
             "competitor", filing=True),
    ])
    assert snap.evidence_independence_state == V.INDEPENDENCE_AVAILABLE
    block = snap.evidence_independence
    assert block["documents"] == 2
    assert block["independent_origin_count"] == 2
    assert len(block["independent_origins"]) == 2


def test_an_unmeasured_analysis_reports_unavailable_not_zero():
    """MISSING IS NOT ZERO, at the seam where a founder would read it."""
    snap, _ = _snapshot(None)
    assert snap.evidence_independence_state == V.INDEPENDENCE_UNAVAILABLE
    block = snap.evidence_independence
    assert block["documents"] == V.FIELD_UNAVAILABLE
    assert block["independent_origin_count"] == V.FIELD_UNAVAILABLE
    assert block["plain_statement"] == ""


def test_a_producer_that_omits_the_block_is_older_not_incompatible():
    """FOUNDER_ADDITIVE. An older producer must still join."""
    payload = build_payload(run_id="r1", company_id="acme")
    payload.pop("evidence_independence", None)
    snap = read_founder_snapshot(payload, expected_company="acme")
    assert snap.contract_state != V.CONTRACT_INCOMPATIBLE
    assert snap.evidence_independence is None


# --- the wording wall (§25) -------------------------------------------------
def test_ten_copies_of_one_release_are_never_rendered_as_ten_sources():
    """THE SENTENCE THIS EXISTS TO MAKE UNSAYABLE."""
    release = "acme opens a plant in ohio " * 40
    documents = [_doc("r0", "https://acme.example/press", "company_owned",
                      body=release)]
    documents += [_doc(f"m{i}", f"https://mirror{i}.example/a",
                       "independent_reporting", body=release)
                  for i in range(9)]
    snap, _ = _snapshot(documents)
    statement = snap.evidence_independence["plain_statement"]
    assert "Ten document(s)" in statement
    assert "none of them from a vantage point outside the company" in statement


def test_two_independent_origins_are_named_as_origins_not_documents():
    statement = describe({"evidence_count": 9,
                          "independent_evidence_count": 2,
                          "unknown_lineage_count": 0})
    assert "Nine document(s)" in statement
    assert "two independent origin(s)" in statement


def test_unknown_lineage_is_said_to_be_unknown_not_independent():
    statement = describe({"evidence_count": 3,
                          "independent_evidence_count": 0,
                          "unknown_lineage_count": 3})
    assert "could not be established" in statement
    assert "independent" not in statement.replace("independent origin", "")


def test_no_evidence_reads_as_no_assessment():
    assert "No evidence" in describe({"evidence_count": 0})


# --- learning summary (§21, §24) -------------------------------------------
def test_blocked_learning_reaches_the_dossier_as_a_state_not_a_number():
    from intent_engine.company_ingestion.learning_attribution import conversion

    learning = conversion(evidence_rows=[{"source_id": "a"}],
                          knowledge_layer_ran=False)
    payload = build_payload(run_id="r1", company_id="acme", learning=learning)
    snap = read_founder_snapshot(payload, expected_company="acme")
    summary = snap.learning_summary
    assert summary["state"] == V.UNAVAILABLE
    assert summary["value"] == "BLOCKED_EXTERNAL_CREDITS"
    assert snap.unknown_fields == ()


def test_measured_learning_reports_its_populations():
    from intent_engine.company_ingestion.learning_attribution import (
        SUPPORTED, THESIS, KnowledgeEffect, conversion,
    )

    effect = KnowledgeEffect(
        evidence_id="a", target_type=THESIS, target_id="t1",
        effect_type=SUPPORTED, before_state="weak", after_state="strong",
        reason="a competitor's filing confirms the capacity claim")
    learning = conversion(evidence_rows=[{"source_id": "a"},
                                         {"source_id": "b"}],
                          effects=[effect])
    payload = build_payload(run_id="r1", company_id="acme", learning=learning)
    snap = read_founder_snapshot(payload, expected_company="acme")
    assert snap.learning_summary["state"] == V.AVAILABLE
    assert snap.learning_summary["value"] == 0.5
    assert "1 of 2 evidence row(s)" in snap.learning_summary["note"]
