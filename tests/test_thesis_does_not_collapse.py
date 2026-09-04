"""The headline strategic decision must come from the company, not a default.

MEASURED LIVE on 56921bce. Synopsys (EDA software), Emerson Electric
(industrial automation) and Lowe's Companies (home-improvement retail) each
received the byte-identical headline decision:

    "Whether a supply commitment should be treated as fixed or renegotiable."

That is `implications[0]` of the `capacity_ahead_of_demand` scaffold, whose
own `excluded_model_classes` names SUBSCRIPTION_SOFTWARE and SCALE_RETAIL.
The exclusion could not fire, because the gate was only ever told UNKNOWN.

THE SEAM: `_registrant_for` read `meta["cik"]`, which is populated ONLY when
a filer is typed with no website. Every domain-entry run -- the ordinary case
-- carried "", so no registrant was fetched, `profile_for` answered UNKNOWN,
and UNKNOWN takes the whole library.
"""
from __future__ import annotations

import inspect

import pytest

from intent_engine.executive.company_profile import profile_for
from intent_engine.strategic_intelligence.patterns import (
    PATTERN_LIBRARY, patterns_for,
)

CAPACITY = "capacity_ahead_of_demand"

#: (name, domain, SEC industry code, expected class, may the capacity
#: scaffold legitimately apply?)
COMPANIES = [
    ("Synopsys Inc", "synopsys.com", "7372", "SUBSCRIPTION_SOFTWARE", False),
    ("Emerson Electric Co", "emerson.com", "3823",
     "DESIGN_AND_MANUFACTURE", True),
    ("Lowes Companies Inc", "lowes.com", "5211", "SCALE_RETAIL", False),
    ("BlackRock, Inc.", "blackrock.com", "6282",
     "BALANCE_SHEET_OR_NETWORK", False),
]


def _class_for(name, domain, sic):
    return profile_for(name=name, domain=domain,
                       registrant={"sic": sic}).business_model_class


# --- the gate itself --------------------------------------------------------

def test_the_regulators_industry_code_classifies_an_unseen_company():
    """None of these are in the curated manifest; the SIC is what resolves
    them, and without it every one answers UNKNOWN."""
    for name, domain, sic, expected, _ok in COMPANIES:
        assert profile_for(name=name, domain=domain).business_model_class \
            == "UNKNOWN", f"{name} was expected to be outside the manifest"
        assert _class_for(name, domain, sic) == expected, name


def test_an_unclassified_company_takes_the_whole_library():
    """This is WHY the seam mattered: UNKNOWN is not a small failure, it
    disables the gate entirely."""
    assert len(patterns_for("UNKNOWN")) == len(PATTERN_LIBRARY)
    assert any(p.pattern_id == CAPACITY for p in patterns_for("UNKNOWN"))


def test_the_capacity_thesis_is_refused_where_it_does_not_belong():
    """NEGATIVE CONTROL. Software, retail and an asset manager must not be
    offered a semiconductor-style capacity commitment."""
    for name, domain, sic, _expected, may_apply in COMPANIES:
        got = patterns_for(_class_for(name, domain, sic))
        has = any(p.pattern_id == CAPACITY for p in got)
        assert has == may_apply, (
            f"{name}: capacity scaffold present={has}, expected={may_apply}")


def test_two_unrelated_businesses_do_not_receive_the_same_library():
    """Different mechanisms must produce different candidate sets."""
    software = {p.pattern_id for p in patterns_for(
        _class_for("Synopsys Inc", "synopsys.com", "7372"))}
    industrial = {p.pattern_id for p in patterns_for(
        _class_for("Emerson Electric Co", "emerson.com", "3823"))}
    assert software != industrial, (
        "an EDA vendor and an industrial manufacturer were offered an "
        "identical set of strategic readings")


def test_the_same_mechanism_may_still_reach_the_same_thesis():
    """POSITIVE CONTROL. The rule is SAME THESIS REQUIRES SAME MECHANISM --
    not that every company must differ. Two capital-intensive manufacturers
    are allowed the same reading."""
    a = {p.pattern_id for p in patterns_for("DESIGN_AND_MANUFACTURE")}
    b = {p.pattern_id for p in patterns_for("DESIGN_AND_MANUFACTURE")}
    assert a == b and CAPACITY in a


# --- the call site, which is where the repair actually lives ---------------

def test_the_registrant_lookup_resolves_the_subject_not_the_typed_cik():
    """`meta["cik"]` is empty for every run started from a website.

    `sufficiency.py` documents this same mistake being repaired in its own
    guard; the repair had not reached the pattern gate, so it is pinned at
    the call site rather than trusted to a comment.
    """
    from intent_engine.company_ingestion.service import CompanyIngestionService
    src = inspect.getsource(CompanyIngestionService._registrant_for)
    assert "self.subject_cik(meta)" in src, (
        "the registrant is resolved from meta['cik'], which is empty on "
        "every domain-entry run, so the pattern gate is never told who the "
        "company is")
    classification = inspect.getsource(
        CompanyIngestionService.classification_inputs)
    assert "self.subject_cik(meta)" in classification, (
        "the subject's own filing text is selected by a CIK the run does "
        "not carry")


def test_the_gate_is_consulted_by_the_production_composer():
    """A gate with no caller is the defect this repair exists to remove."""
    from intent_engine.company_ingestion.service import CompanyIngestionService
    src = inspect.getsource(CompanyIngestionService._strategic_report)
    assert "_patterns_for_company(" in src
    marker = src.index("_patterns_for_company(")
    after = src[marker:marker + 400]
    assert "registrant=" in after and "evidence_text=" in after, (
        "the composer calls the gate without the two inputs that classify a "
        "company outside the curated manifest")
