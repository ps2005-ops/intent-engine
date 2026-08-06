"""A repeated reading needs repeated causal evidence, not repeated vocabulary.

HubSpot and Snowflake were handed the same dominant conclusion — "public
emphasis suggests meaningful dependence on regulated or public-sector buyers".
Measured on the live pages, they are not the same case at all:

    HubSpot   legal.hubspot.com/security
              "HubSpot uses a defense-in-depth approach to implement layers of
              security throughout our organization", plus SOC 2 / ISO 27001 /
              GDPR badges. `defense-in-depth` is a security ARCHITECTURE
              phrase. It matched `regulated_buyer` on the bare word "defense".

    Snowflake snowflake.com/en/solutions/industries/public-sector
              FedRAMP High, GovCloud, DoD IL5, CJIS, sovereign deployment.

One of these companies has a public-sector mechanism. The other has a security
page. The fix is therefore NOT to vary the wording so the two conclusions look
different: it is that a reading of this kind may only fire on evidence of a
CAUSAL mechanism — something the company had to build, win, be bought through,
or disclose.

Repeated conclusions remain allowed. Two companies with the same mechanism
should reach the same reading. What may not happen is two companies reaching it
on vocabulary neither of them earned.
"""
from __future__ import annotations

import pytest

from intent_engine.strategic_intelligence.observations import (
    _detect_neutral_signals, derive_observations,
)
from intent_engine.strategic_intelligence.patterns import (
    HYPOTHESIS_SCAFFOLDS, PATTERN_LIBRARY,
)
from intent_engine.strategic_intelligence.reasoning import _hypothesis_for

PATTERNS = {p.pattern_id: p for p in PATTERN_LIBRARY}
BUYER = PATTERNS["buyer_concentration_exposure"]
BUYER_SCAFFOLD = HYPOTHESIS_SCAFFOLDS["buyer_concentration_exposure"]
MECHANISMS = ("gov_dedicated_delivery", "accreditation_gate",
              "public_procurement_vehicle",
              "disclosed_public_sector_exposure")


def _doc(sid, url, title, text, source_type="product"):
    return {"source_id": sid, "source_type": source_type, "final_url": url,
            "title": title, "meta_description": "", "text_content": text,
            "retrieval_status": "OK", "freshness": "CURRENT",
            "content_hash": sid, "retrieved_at": "2026-08-06",
            "parser_version": "p1"}


def _fires(docs, company="Acme"):
    obs = derive_observations(docs, company=company)
    return _hypothesis_for(BUYER, BUYER_SCAFFOLD, obs, company)


# --- the two live cases, as measured ---------------------------------------

HUBSPOT = [
    _doc("h1", "https://legal.hubspot.com/security", "HubSpot Security Program",
         "HubSpot uses a defense-in-depth approach to implement layers of "
         "security across the organization and our infrastructure. We maintain "
         "SOC 2 Type II and ISO 27001 certification and support GDPR "
         "obligations for customers worldwide. Contact sales for details. Our "
         "customer stories and case studies describe deployments across many "
         "industries."),
    _doc("h2", "https://www.hubspot.com/products", "HubSpot Products",
         "HubSpot offers Marketing Hub, Sales Hub, Service Hub and Content Hub "
         "as separate products on one connected platform, priced per seat with "
         "a free plan available to any team."),
]

SNOWFLAKE = [
    _doc("s1", "https://www.snowflake.com/en/solutions/industries/public-sector/",
         "AI Data Cloud for Public Sector",
         "Snowflake for Public Sector is FedRAMP High authorized and available "
         "in GovCloud, supporting DoD IL5 workloads and CJIS requirements for "
         "law enforcement data. Sovereign deployment options let agencies keep "
         "regulated data in country. Read the customer story from the Superior "
         "Court of California, which reduced its caseload backlog."),
    _doc("s2", "https://www.snowflake.com/en/product/platform/", "Platform",
         "The AI Data Cloud spans data warehousing, data engineering and "
         "application development as distinct workloads. Pricing is "
         "consumption based; contact sales for an enterprise quote."),
]


def test_hubspots_security_page_no_longer_reads_as_a_regulated_buyer():
    """`defense-in-depth` is layered security, not a defence customer."""
    text = HUBSPOT[0]["text_content"].lower()
    assert "regulated_buyer" not in _detect_neutral_signals(text)
    assert not any(m in _detect_neutral_signals(text) for m in MECHANISMS)


def test_hubspot_does_not_reach_the_buyer_concentration_reading():
    assert _fires(HUBSPOT, "HubSpot") is None


def test_snowflake_still_reaches_it_and_says_which_mechanism():
    h = _fires(SNOWFLAKE, "Snowflake")
    assert h is not None, "a company running GovCloud at IL5 lost the reading"
    assert "government or sovereign estate" in h.statement
    assert "accreditations" in h.statement


def test_the_two_companies_no_longer_share_one_conclusion():
    hub, sno = _fires(HUBSPOT, "HubSpot"), _fires(SNOWFLAKE, "Snowflake")
    assert (hub, sno) != (None, None)
    assert hub is None and sno is not None


# --- what is and is not sufficient ------------------------------------------

INSUFFICIENT = {
    "compliance-only SaaS":
        "We are SOC 2 Type II certified, ISO 27001 certified and GDPR "
        "compliant. Our security programme is independently audited each year.",
    "generic security page":
        "Security at Acme. We use a defense-in-depth approach with encryption "
        "at rest and in transit across all of our infrastructure worldwide.",
    "one government case study":
        "Read our case study with the City of Springfield, which uses Acme to "
        "manage its internal scheduling across three municipal departments.",
    "serves-regulated-industries copy":
        "Acme serves regulated industries including healthcare, insurance and "
        "financial services, with the controls those industries expect.",
    "public-sector landing page with no mechanism":
        "Acme for the public sector. Government agencies choose Acme to work "
        "faster. Talk to our team about what your agency needs.",
}

SUFFICIENT = {
    "dedicated government region":
        "Acme GovCloud gives government agencies a dedicated government cloud "
        "region, operated separately from our commercial estate.",
    "accreditation that gates the purchase":
        "Acme is FedRAMP Moderate authorized and supports DoD Impact Level 5 "
        "workloads, with an authority to operate granted in 2025.",
    "procurement vehicle":
        "Acme is available on the GSA Schedule and through our contract "
        "vehicle, so agencies may buy without a separate competition.",
    "disclosed materiality":
        "Government customers accounted for 38% of revenue in fiscal 2025, "
        "reported separately from commercial revenue in our quarterly results.",
}


@pytest.mark.parametrize("label", sorted(INSUFFICIENT))
def test_weak_evidence_cannot_carry_the_reading(label):
    docs = [_doc("d1", "https://acme.example/x", "Acme", INSUFFICIENT[label]),
            _doc("d2", "https://acme.example/c", "Customers",
                 "Read our customer stories and case studies from teams "
                 "across many different industries and company sizes.",
                 source_type="customers")]
    assert _fires(docs) is None, f"{label!r} was enough to dominate"


@pytest.mark.parametrize("label", sorted(SUFFICIENT))
def test_a_real_mechanism_qualifies(label):
    docs = [_doc("d1", "https://acme.example/gov", "Government",
                 SUFFICIENT[label]),
            _doc("d2", "https://acme.example/p", "Products",
                 "Acme ships three separate products for commercial and "
                 "government agencies alike, each sold on its own.")]
    assert _fires(docs) is not None, f"{label!r} failed to qualify"


def test_two_qualifying_companies_differ_by_mechanism_not_by_wording():
    """Conclusion diversity comes from evidence, not from varied prose."""
    gov = [_doc("g1", "https://gov.example/x", "Gov", SUFFICIENT["procurement vehicle"]
                + " Government customers accounted for 41% of revenue."),
           _doc("g2", "https://gov.example/p", "Products",
                "Three separate products for commercial and government buyers.")]
    a = _fires(SNOWFLAKE, "Snowflake")
    b = _fires(gov, "GovVendor")
    assert a is not None and b is not None
    strip = lambda h, n: h.statement.replace(n, "{co}")  # noqa: E731
    assert strip(a, "Snowflake") != strip(b, "GovVendor"), \
        "two different mechanisms produced one identical sentence"
    assert "procurement machinery" in b.statement
    assert "procurement machinery" not in a.statement


def test_the_same_mechanism_may_still_produce_the_same_reading():
    """Repetition is not the defect; unearned repetition is."""
    body = ("Acme ships three separate products for commercial and "
            "government agencies alike, each sold on its own.")
    one = [_doc("a1", "https://a.example/g", "Gov", SUFFICIENT["procurement vehicle"]),
           _doc("a2", "https://a.example/p", "P", body)]
    two = [_doc("b1", "https://b.example/g", "Gov", SUFFICIENT["procurement vehicle"]),
           _doc("b2", "https://b.example/p", "P", body)]
    ha, hb = _fires(one, "Acme"), _fires(two, "Acme")
    assert ha is not None and hb is not None
    assert ha.statement == hb.statement


# --- the contract itself -----------------------------------------------------

def test_the_pattern_declares_its_required_mechanisms():
    assert set(BUYER.required_any_signals) == set(MECHANISMS)
    for signal in BUYER.required_any_signals:
        assert signal in BUYER.qualifying_signals
    BUYER.validate()


def test_assurance_badges_are_deliberately_absent_from_the_gate():
    """SOC 2 / ISO / GDPR / HIPAA gate nothing — every B2B vendor has them."""
    from intent_engine.strategic_intelligence.observations import (
        _NEUTRAL_SIGNAL_KEYWORDS as K,
    )
    banned = ("soc 2", "iso 27001", "gdpr", "hipaa", "compliance")
    for signal in MECHANISMS + ("regulated_buyer",):
        for phrase in K[signal]:
            assert phrase not in banned, \
                f"{signal} accepts the assurance badge {phrase!r}"


def test_bare_defence_and_defense_are_not_regulated_buyer_markers():
    """The exact regression: it must stay removed."""
    from intent_engine.strategic_intelligence.observations import (
        _NEUTRAL_SIGNAL_KEYWORDS as K,
    )
    assert "defence" not in K["regulated_buyer"]
    assert "defense" not in K["regulated_buyer"]
    assert not _detect_neutral_signals(
        "we use a defense-in-depth approach to security across our stack")


def test_a_stronger_hypothesis_is_not_displaced_by_a_weak_regulated_reading():
    """A company whose real shape is consolidation keeps that reading, and
    does not additionally receive an unearned buyer-concentration one.

    MIGRATED. The point of this test is the buyer-concentration gate: a
    passing mention of regulated industries must not manufacture a reading,
    and the company's genuine reading must survive that. It needed a genuine
    reading to survive, and used the system-of-record one — which at the time
    fired on the products page alone, so the "stronger hypothesis" was itself
    ungated. That made half of this test a false control.

    The fixture now carries the mechanism instead of implying it. Note what
    was NOT enough on its own: "a single source of truth for the whole team"
    stays in the copy and is exactly the marketing language the pattern's own
    `limitations` field says it cannot read as proof.
    """
    docs = [
        _doc("c1", "https://acme.example/", "Acme",
             "Acme is one workspace that replaces several separate tools, a "
             "single source of truth for the whole team. We serve regulated "
             "industries too."),
        _doc("c2", "https://acme.example/p", "Products",
             "Marketing, Sales and Service are separate products on one "
             "connected workspace, with a developer API to build on. All "
             "three run on a shared data model, so the same underlying data "
             "is what each of them reads and writes."),
    ]
    obs = derive_observations(docs, company="Acme")
    assert _hypothesis_for(BUYER, BUYER_SCAFFOLD, obs, "Acme") is None
    tool = PATTERNS["tool_to_system_of_record"]
    assert _hypothesis_for(tool,
                           HYPOTHESIS_SCAFFOLDS["tool_to_system_of_record"],
                           obs, "Acme") is not None


def test_palantir_qualifies_on_disclosed_exposure_not_on_the_word_defence():
    """The genuine positive control, from the golden fixture."""
    from intent_engine.product_eval.harness import _compose
    _, _, result = _compose("palantir")
    report = result.get("strategic_report")
    report = report.as_dict() if hasattr(report, "as_dict") else report
    buyer = [h for h in (report.get("hypotheses") or [])
             if h.get("pattern_id") == "buyer_concentration_exposure"]
    assert buyer, "the government-revenue-disclosing control lost its reading"
    assert "written down what public-sector buyers contribute" \
        in buyer[0]["statement"]
