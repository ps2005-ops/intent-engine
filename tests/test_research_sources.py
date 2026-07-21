"""T019 bars: canonicalization, grading, independence, freshness,
retirement, anti-recency."""
import pytest

from intent_engine.research import (
    ResearchError, canonicalize_locator, count_independent, freshness_of,
    grade_source, independence_group, outranks,
)
from intent_engine.research.sources import content_hash

AS_OF = "2026-07-21T00:00:00+00:00"


def _src(**over):
    base = {"source_id": "S1", "source_class": "peer_reviewed",
            "author": "Ng", "publisher": "JMLR",
            "published_date": "2026-07-01T00:00:00+00:00",
            "retrieved_at": AS_OF, "content_hash": content_hash("text"),
            "domain": "ai_research"}
    base.update(over)
    return base


# --- canonicalization (improvement 12) ---------------------------------------

def test_url_variants_resolve_to_one_canonical_source():
    variants = [
        "https://example.com/paper?download=1",
        "https://www.example.com/paper/",
        "https://example.com/paper?utm_source=twitter&utm_medium=social",
        "https://example.com/paper.pdf",
        "https://EXAMPLE.com/paper/amp",
    ]
    canonical = {canonicalize_locator(v) for v in variants}
    assert len(canonical) == 1


def test_doi_is_the_canonical_identity_wherever_hosted():
    a = canonicalize_locator("https://doi.org/10.1234/abc.5678")
    b = canonicalize_locator("https://publisher.example/x?doi=10.1234/abc.5678")
    assert a == b == "doi:10.1234/abc.5678"


def test_non_url_locators_pass_through():
    assert canonicalize_locator("founder-supplied") == "founder-supplied"
    with pytest.raises(ResearchError):
        canonicalize_locator("")


# --- grading -----------------------------------------------------------------

def test_high_classes_grade_high_when_attributed_and_dated():
    for cls in ("peer_reviewed", "official_docs", "book", "primary_data"):
        assert grade_source(_src(source_class=cls))["source_quality"] == "HIGH"


def test_missing_hash_or_retrieval_cannot_be_graded_or_cited():
    with pytest.raises(ResearchError, match="content hash"):
        grade_source(_src(content_hash=None))
    with pytest.raises(ResearchError, match="retrieval timestamp"):
        grade_source(_src(retrieved_at=None))


def test_undated_high_class_downgrades_and_unattributed_is_unknown():
    assert grade_source(_src(published_date=None))["source_quality"] == "MEDIUM"
    assert grade_source(_src(author=None, publisher=None)
                        )["source_quality"] == "UNKNOWN"


def test_low_classes_and_llm_generated():
    for cls in ("company_blog", "personal_blog", "forum_post", "social_post"):
        assert grade_source(_src(source_class=cls))["source_quality"] == "LOW"
    llm = grade_source(_src(source_class="llm_generated"))
    assert llm["source_quality"] == "LOW" and llm["model_written"] is True
    assert "including our own" in llm["reasons"][0]


def test_grade_is_independent_of_whether_the_source_agrees():
    """The load-bearing property: grading never sees agreement."""
    agreeing = grade_source(_src(source_id="A", stance="supports"))
    disagreeing = grade_source(_src(source_id="B", stance="contradicts"))
    assert agreeing["source_quality"] == disagreeing["source_quality"]
    assert agreeing["reasons"] == disagreeing["reasons"]


def test_grade_carries_reasons_and_a_version():
    graded = grade_source(_src())
    assert graded["reasons"] and graded["quality_version"] == "source_quality.v1"


# --- independence (improvement 2) --------------------------------------------

def test_three_outlets_quoting_one_wire_are_one_independent_source():
    reuters = _src(source_id="reuters", canonical_locator="reuters")
    nyt = _src(source_id="nyt", derived_from_source="reuters")
    cnn = _src(source_id="cnn", derived_from_source="reuters")
    result = count_independent([reuters, nyt, cnn])
    assert result["independent_count"] == 1
    assert result["total_sources"] == 3
    assert result["collapsed"]


def test_source_family_groups_related_outlets():
    a = _src(source_id="a", source_family="vendor_x")
    b = _src(source_id="b", source_family="vendor_x")
    c = _src(source_id="c", canonical_locator="c")
    assert count_independent([a, b, c])["independent_count"] == 2


def test_unrelated_sources_count_separately():
    a = _src(source_id="a", canonical_locator="a")
    b = _src(source_id="b", canonical_locator="b")
    assert count_independent([a, b])["independent_count"] == 2
    assert independence_group(a) != independence_group(b)


# --- freshness and retirement (improvement 6) --------------------------------

def test_fresh_within_policy_and_stale_beyond_it():
    fresh = freshness_of(_src(published_date="2026-06-01T00:00:00+00:00"),
                         as_of=AS_OF)
    assert fresh["freshness"] == "FRESH"
    stale = freshness_of(_src(published_date="2025-01-01T00:00:00+00:00"),
                         as_of=AS_OF)
    assert stale["freshness"] == "STALE" and stale["age_days"] > 180


def test_unknown_domain_gets_the_conservative_policy():
    result = freshness_of(_src(domain="something_new",
                               published_date="2026-06-01T00:00:00+00:00"),
                          as_of=AS_OF)
    assert result["freshness"] == "STALE"        # 7-day conservative limit
    assert "most conservative" in result["reason"]


def test_never_expiring_domains():
    for domain in ("mathematics", "historical_event"):
        result = freshness_of(_src(domain=domain,
                                   published_date="1970-01-01T00:00:00+00:00"),
                              as_of=AS_OF)
        assert result["freshness"] == "FRESH"


def test_undated_is_stale_not_fresh():
    result = freshness_of(_src(published_date=None, retrieved_at=None),
                          as_of=AS_OF)
    assert result["freshness"] == "STALE"


def test_retired_is_distinct_from_stale_and_never_deletes():
    retired = freshness_of(_src(retired_reason="retracted_by_publisher"),
                           as_of=AS_OF)
    assert retired["freshness"] == "RETIRED"
    assert "regardless of age" in retired["note"]
    with pytest.raises(ResearchError, match="unknown retirement reason"):
        freshness_of(_src(retired_reason="i disagree"), as_of=AS_OF)


# --- anti-recency bias (improvement 14) --------------------------------------

def test_quality_outranks_recency():
    old_paper = grade_source(_src(source_class="peer_reviewed",
                                  published_date="2014-01-01T00:00:00+00:00"))
    new_blog = grade_source(_src(source_class="personal_blog",
                                 published_date="2026-07-01T00:00:00+00:00"))
    a = {**old_paper, "published_date": "2014-01-01T00:00:00+00:00"}
    b = {**new_blog, "published_date": "2026-07-01T00:00:00+00:00"}
    assert outranks(a, b) is True
    assert outranks(b, a) is False


def test_recency_only_breaks_ties_inside_a_quality_band():
    older = {"source_quality": "HIGH", "published_date": "2020-01-01"}
    newer = {"source_quality": "HIGH", "published_date": "2026-01-01"}
    assert outranks(newer, older) is True
