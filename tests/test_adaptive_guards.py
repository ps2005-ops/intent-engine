"""The guards the break proofs mutate. One test per load-bearing invariant.

Kept in a file of its own so each proof's paired test is unambiguous: a proof
that names a whole module and hopes something goes red is a proof that can
pass on an unrelated failure.
"""
from __future__ import annotations

from intent_engine.adaptive import lens
from intent_engine.adaptive import profile as prof
from intent_engine.adaptive import roles
from intent_engine.adaptive.engine import build
from intent_engine.executive.company_profile import profile_for

SOFTWARE = ("Acme is the sales enablement platform for revenue teams. "
            "Subscription pricing per user per month. Our platform. "
            "Request a demo.")


def test_an_authored_classification_outranks_the_companys_own_marketing():
    """ORDER OF AUTHORITY. The manifest is authored, reviewed and
    version-controlled; a marketing page is neither. The evidence classifier
    is consulted ONLY where both the manifest and the industry code refused,
    and a build that consulted it first would let a landing page overwrite a
    reviewed classification for a hundred companies at once."""
    manifest_row = profile_for(name="Shopify", domain="shopify.com")
    if not manifest_row.known:                       # not in this manifest
        return
    with_marketing = profile_for(
        name="Shopify", domain="shopify.com",
        published_text="We are a consulting firm. Our consultants deliver "
                       "client engagements and advisory services. Billable.")
    assert with_marketing.business_model_class == \
        manifest_row.business_model_class
    assert with_marketing.profile_source == manifest_row.profile_source


def test_an_industry_code_outranks_the_companys_own_marketing():
    """Same ordering, one rung down: a regulator's classification of a filer
    is a third party's judgement about a statutory document."""
    registrant = {"sic": "7372", "sic_description": "Prepackaged Software"}
    coded = profile_for(name="Some Filer", registrant=registrant)
    hijacked = profile_for(
        name="Some Filer", registrant=registrant,
        published_text="We are a consultancy. Our consultants deliver client "
                       "engagements. Billable. Advisory services.")
    assert coded.known
    assert hijacked.business_model_class == coded.business_model_class
    assert hijacked.profile_source.startswith("SEC_SIC")


def test_the_evidence_classifier_fills_only_the_gap_the_others_leave():
    """The whole point: a private company, no manifest row, no industry code,
    and its own material states how it is paid."""
    sparse = profile_for(name="Nobody Ltd")
    filled = profile_for(name="Nobody Ltd", published_text=SOFTWARE)
    assert not sparse.known
    assert filled.known
    assert filled.profile_source == "SUBJECT_EVIDENCE"
    # and it unlocks the machinery that UNKNOWN switches off
    assert filled.decision_archetypes
    assert filled.relevant_macro_channels


def test_a_class_prior_is_never_counted_as_a_company_specific_finding():
    """`specificity` is the number the whole design turns on. Counting the
    class prior in it would make every company look fully understood, and
    the flag that says 'this difference is thin' would never fire."""
    p = prof.build_profile(company="Acme", evidence_text=SOFTWARE)
    assert p.pricing_model.provenance == prof.CLASS_PRIOR
    assert not p.pricing_model.company_specific
    assert p.specificity < 1.0
    assert "pricing_model" not in p.company_specific_fields


def test_a_role_may_not_drop_a_module_from_the_report():
    """A role that hid a module would be a role that changed what the reader
    is told, which is the line the role lens does not cross. Order changes;
    the set does not."""
    ids = ("strategic_thesis", "financial_sensitivity", "evidence",
           "regulatory_exposure", "provenance")
    for r in roles.ROLES:
        view = roles.role_view(role_id=r.role_id, module_ids=ids)
        assert set(view.order) == set(ids), r.role_id
        assert len(view.order) == len(ids), r.role_id


def test_the_lens_gate_refuses_by_business_model_before_it_scores():
    """Applicability is a HARD gate, not a weight. A weight can be
    outvoted by enough matching signals; a gate cannot."""
    sel = lens.select_lens(
        evidence_text=("raw materials suppliers freight logistics inventory "
                       "tariff lead times input costs " * 8),
        business_model="SUBSCRIPTION_SOFTWARE")
    entry = [s for s in sel.scores if s.lens_id == "supply_chain_shock"][0]
    assert not entry.eligible
    assert entry.score == 0.0
    assert sel.primary != "supply_chain_shock"


def test_the_subject_owns_the_text_that_classifies_it():
    """A rival's page must never classify this company.

    THE ASSERTION USED TO ACCEPT THE DEFECT. It allowed UNKNOWN as a pass and
    only checked the two classes it expected, so it stayed green while a
    competitor's page actually won: measured on a real two-observation
    fixture, the subject scored 9.0, the rival 13.0, and the subject was
    classified as the rival's business. Concatenating the two sets and
    trusting ORDER to protect the subject does not work, because the
    classifier scores the whole string.
    """
    rival_only = ("Globex is a consulting firm. Our consultants deliver "
                  "client engagements and advisory services worldwide. "
                  "Billable. Our clients. Practice areas.")
    subject_alone = build(company="Acme", evidence_text=SOFTWARE)
    assert subject_alone.profile.business_model_class == \
        "SUBSCRIPTION_SOFTWARE"
    # the rival's text, given ITS OWN WAY, would win on weight -- which is
    # exactly why it must never be in the string
    rival_alone = build(company="Acme", evidence_text=rival_only)
    assert rival_alone.profile.business_model_class == \
        "PEOPLE_OR_ROUTE_BASED_SERVICES"


def test_the_assembler_hands_over_subject_owned_text_alone():
    """The seam, exercised. A guard the caller does not honour is not a
    guard -- `_subject_published_text` is where the two sets meet."""
    import types

    from intent_engine.webapp.app import WebApp

    app = WebApp.__new__(WebApp)
    app._request = types.SimpleNamespace()
    app.classification_inputs = lambda rid, name="": {"evidence_text": "",
                                                      "registrant": {}}
    app._result = lambda rid: {"strategic_report": {"observations": [
        {"observation_id": "o1", "source_class": "company_owned",
         "source_title": "Acme",
         "excerpt": SOFTWARE},
        {"observation_id": "o2", "source_class": "competitor",
         "source_title": "Globex",
         "excerpt": "Globex is a consulting firm. Our consultants deliver "
                    "client engagements. Billable. Our clients."},
    ]}}
    text = WebApp._subject_published_text(app, "r1")
    assert "Acme" in text or "sales enablement" in text
    assert "Globex" not in text
    assert "consulting firm" not in text

    # ...and third-party text IS used when the company said nothing at all,
    # because a weaker reading beats no reading and it is labelled as one.
    app._request = types.SimpleNamespace()
    app._result = lambda rid: {"strategic_report": {"observations": [
        {"observation_id": "o2", "source_class": "competitor",
         "source_title": "Globex", "excerpt": "Globex is a consulting firm."},
    ]}}
    fallback = WebApp._subject_published_text(app, "r1")
    assert "Globex" in fallback
