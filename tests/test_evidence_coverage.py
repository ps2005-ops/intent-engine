"""Semantic evidence coverage quorum (2026-07 report-quality incident).

A source COUNT is not evidence sufficiency: three SEC filings satisfy "three
documents retrieved" while saying nothing about what the company does, who it
serves, or why it matters. These tests pin the semantic quorum.
"""
from intent_engine.company_ingestion.coverage import (
    EVIDENCE_INSUFFICIENT, EVIDENCE_PARTIAL, EVIDENCE_REPORT_READY,
    assess, family_of, missing_family_guidance,
)

AS_OF = "2026-07-27T00:00:00+00:00"


def _doc(source_id, source_type, source_class="company_owned", text="real "
         "readable business content about the product and its customers"):
    return {"source_id": source_id, "source_type": source_type,
            "source_class": source_class, "retrieval_status": "OK",
            "title": source_id, "meta_description": "",
            "content_hash": "a" * 64, "retrieved_at": AS_OF,
            "parser_version": "v1", "freshness": "CURRENT",
            "text_content": text}


# --- family mapping ---------------------------------------------------------

def test_family_mapping_covers_the_evidence_kinds():
    assert family_of(_doc("s1", "homepage")) == "identity"
    assert family_of(_doc("s2", "about")) == "identity"
    assert family_of(_doc("s3", "product")) == "product"
    assert family_of(_doc("s4", "customers")) == "customers"
    assert family_of(_doc("s5", "pricing")) == "commercial"
    assert family_of(_doc("s6", "careers")) == "talent"
    assert family_of(_doc("s7", "external_approved",
                          "investor_material")) == "investor"
    assert family_of(_doc("s8", "external_approved",
                          "customer_voice")) == "independent"
    assert family_of(_doc("s9", "blog", "executive_statement")) == "strategy"


# --- the incident case ------------------------------------------------------

def test_three_sec_filings_alone_are_not_report_ready():
    """THE regression: filings-only evidence must never read as sufficient."""
    filings = [_doc(f"src-sec-{i}", "external_approved", "investor_material")
               for i in range(3)]
    result = assess(filings)
    assert result["state"] != EVIDENCE_REPORT_READY
    assert result["dominant_family"] == "investor"
    assert result["dominant_share"] == 1.0
    assert result["reasons"], "an insufficient quorum must explain itself"
    # and it must say WHAT is missing, in business terms
    assert "identity" in result["missing_core"]
    assert "product" in result["missing_core"]
    guidance = missing_family_guidance(result["missing_core"])
    assert any("product" in g for g in guidance)


def test_single_family_domination_is_rejected_even_when_plentiful():
    """Ten blog posts are still one viewpoint."""
    posts = [_doc(f"src-b{i}", "blog", "executive_statement")
             for i in range(10)]
    result = assess(posts)
    assert result["state"] != EVIDENCE_REPORT_READY
    assert result["dominant_share"] > 0.75


# --- healthy coverage -------------------------------------------------------

def test_diverse_evidence_is_report_ready():
    documents = [
        _doc("src-home", "homepage"),
        _doc("src-prod", "product"),
        _doc("src-cust", "customers"),
        _doc("src-sec", "external_approved", "investor_material"),
    ]
    result = assess(documents)
    assert result["state"] == EVIDENCE_REPORT_READY
    assert not result["reasons"]
    assert set(result["families"]) >= {"identity", "product", "customers",
                                       "investor"}
    assert result["dominant_share"] <= 0.75


def test_partial_when_some_evidence_but_not_enough_families():
    result = assess([_doc("src-home", "homepage"),
                     _doc("src-about", "about")])
    assert result["state"] == EVIDENCE_PARTIAL
    assert result["reasons"]


def test_no_usable_evidence_is_insufficient():
    assert assess([])["state"] == EVIDENCE_INSUFFICIENT
    # a retrieved-but-empty document is not usable evidence
    empty = _doc("src-empty", "homepage", text="   ")
    assert assess([empty])["state"] == EVIDENCE_INSUFFICIENT


def test_failed_documents_never_count_as_coverage():
    failed = dict(_doc("src-x", "product"), retrieval_status="FAILED")
    result = assess([failed])
    assert result["document_count"] == 0
    assert result["state"] == EVIDENCE_INSUFFICIENT
