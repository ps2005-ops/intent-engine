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


def test_one_run_holds_one_business_model():
    """TWO PROFILE RESOLUTIONS, ONE RUN -- measured live and repaired.

    On df8830f0 the reading layer classified Highspot SUBSCRIPTION_SOFTWARE
    from its own pages while the run's own telemetry reported
    `business_model: UNKNOWN`, because the ingestion gates called
    `profile_for` with `evidence_text` and not with `published_text`. The
    pattern library therefore stayed wide open on a company the product had
    in fact classified -- twelve patterns offered where the classification
    allows eleven.

    Both gates read the SAME text, so they must return the same answer.
    """
    from intent_engine.company_ingestion.service import (
        _business_model_of, _patterns_for_company)
    from intent_engine.strategic_intelligence.patterns import PATTERN_LIBRARY

    reading = profile_for(name="Acme", published_text=SOFTWARE)
    ingestion = _business_model_of("Acme", evidence_text=SOFTWARE)
    assert reading.business_model_class == ingestion == "SUBSCRIPTION_SOFTWARE"

    # ...and the classification actually narrows the library, which is the
    # thing UNKNOWN was silently switching off.
    gated = _patterns_for_company("Acme", evidence_text=SOFTWARE)
    assert 0 < len(gated) < len(PATTERN_LIBRARY)


def test_the_classification_says_how_it_decided_not_only_what():
    """Telemetry went blank the moment `profile_for` started winning: the
    branch that computed the evidence read stopped running, so a matrix could
    report WHAT was decided and never HOW."""
    from intent_engine.adaptive.engine import build
    ai = build(company="Acme", evidence_text=SOFTWARE)
    t = ai.telemetry()
    assert t["business_model"] == "SUBSCRIPTION_SOFTWARE"
    assert t["business_model_confidence"]
    assert t["business_model_evidence"]


def test_no_customer_sentence_puts_a_bare_python_token_on_the_page():
    """The raw-internals detector reads a bare `None` as a rendered object,
    and it is right to. A sentence that opens "None has been measured" is
    correct English and indistinguishable from the defect, so the copy moves
    rather than the detector."""
    from intent_engine.adaptive import render as ar
    from intent_engine.adaptive.engine import build
    for text in (SOFTWARE, "Nothing much here."):
        ai = build(company="Acme", evidence_text=text)
        html = ar.block("Acme", "r1", ai, csrf="t", base="/runs/r1/intro")
        import re
        assert not re.search(r"\bNone\b", html), html[:400]
        assert not re.search(r"\bUNKNOWN\b", html)


# --- evidence spans: the defect measured on the deployed service ----------

def test_a_quoted_passage_never_begins_or_ends_mid_word():
    """MEASURED LIVE (Highspot, df8830f0): the primary screen carried

        "The evidence this rests on omers are transforming GTM performance."

    A window of "match minus 220 characters" has no idea where a word starts.
    """
    from intent_engine.adaptive.spans import quote_around
    text = ("See how customers are transforming performance. Pricing is per "
            "user per month and renews annually.")
    i = text.index("per user")
    q = quote_around(text, i, i + 8)
    assert q
    assert q[0].isupper() or q[0] in "“‘"
    assert not text[max(0, text.index(q) - 1):text.index(q)].isalnum()
    end = text.index(q) + len(q)
    assert end >= len(text) or not text[end].isalnum()


def test_page_furniture_never_wins_over_a_substantive_passage():
    """Two of three quotations on the first live page came from a
    press-release index. The furniture rule is owned by `evidence_text`; this
    asserts the span selector actually consults it."""
    from intent_engine.adaptive.spans import quote_around
    # THE MATCH MUST LAND INSIDE THE FURNITURE, or the guard is not the thing
    # being tested. An earlier fixture matched inside the substantive
    # sentence, where the "sentence containing the match" branch wins anyway
    # -- so deleting the furniture filter changed nothing and the break proof
    # ran NOT_CAUGHT.
    text = ("Get in touch for any press inquiries about sales enablement: "
            "press@highspot.com. Highspot is the sales enablement platform "
            "that increases the performance of revenue teams.")
    i = text.index("sales enablement")          # the FIRST one, in furniture
    q = quote_around(text, i, i + 16)
    assert "press inquiries" not in q, q
    assert "press@" not in q, q
    assert "increases the performance of revenue teams" in q, q


def test_everything_nearby_being_furniture_returns_nothing():
    """A refusal, not a fragment. A quotation that begins mid-word tells a
    reader the machine is not reading, which costs more than the quote."""
    from intent_engine.adaptive.spans import quote_around
    text = "Read article. Highspot in the news. Learn more. Contact us."
    assert quote_around(text, 20, 24) == ""


def test_a_quote_is_attributed_to_the_document_it_came_from():
    """A quotation with no source is not evidence."""
    from intent_engine.adaptive.corpus import Corpus, Source
    corpus = Corpus([
        Source(text="Globex is a consulting firm that serves many clients.",
               title="Globex", url="https://globex.example",
               source_class="competitor"),
        Source(text="Acme is the sales enablement platform for revenue "
                    "teams and is sold on subscription.",
               title="Acme home", url="https://acme.example",
               source_class="company_owned"),
    ])
    i = corpus.text.index("sales enablement")
    ref = corpus.evidence_at(i, i + 16, claim="what Acme sells")
    assert ref.is_quote
    assert "sales enablement" in ref.passage
    assert ref.source_title == "Acme home"
    assert ref.provenance == "SUBJECT_PUBLISHED"
    assert "Globex" not in ref.passage


def test_a_span_may_not_cross_from_one_document_into_another():
    """The window either side of a match can reach past the join, which is
    how a sentence gets attributed to a page it never appeared on."""
    from intent_engine.adaptive.corpus import Corpus, Source
    corpus = Corpus([
        Source(text="Acme sells software on subscription to revenue teams.",
               title="Acme", source_class="company_owned"),
        Source(text="Globex is a consulting firm with many consultants.",
               title="Globex", source_class="competitor"),
    ])
    i = corpus.text.index("subscription")
    ref = corpus.evidence_at(i, i + 12)
    assert "consulting firm" not in ref.passage
    assert ref.source_title == "Acme"


def test_a_third_party_passage_is_never_labelled_as_the_companys_own():
    from intent_engine.adaptive.corpus import Corpus, Source
    corpus = Corpus([Source(
        text="Analysts said the vendor had grown quickly last year.",
        title="Trade press", url="https://press.example",
        source_class="independent_reporting")])
    i = corpus.text.index("grown quickly")
    ref = corpus.evidence_at(i, i + 13)
    assert ref.provenance == "THIRD_PARTY"
    assert not corpus.sources[0].subject_owned


def test_a_paraphrase_is_never_dressed_as_a_quotation():
    """Inventing quotation marks is inventing a source's words."""
    from intent_engine.adaptive.corpus import Corpus, Source
    corpus = Corpus([Source(text="Read article. Learn more. Contact us.",
                            title="Index", source_class="company_owned")])
    ref = corpus.evidence_at(5, 12, paraphrase="the page is an index")
    assert not ref.is_quote
    assert ref.passage == ""
    assert ref.paraphrase


def test_the_subject_only_corpus_removes_third_parties_rather_than_reordering():
    """Ordering does not protect a subject: the scorer reads the whole
    string, so a rival with more signal simply wins. Measured 9.0 vs 13.0."""
    from intent_engine.adaptive.corpus import Corpus, Source
    corpus = Corpus([
        Source(text="Acme sells software on subscription.",
               source_class="company_owned"),
        Source(text="Globex is a consulting firm. Our consultants deliver "
                    "client engagements. Billable.",
               source_class="competitor"),
    ])
    assert "Globex" in corpus.text
    assert "Globex" not in corpus.subject_only.text
    assert "Acme" in corpus.subject_only.text


# --- the three reading states --------------------------------------------

def test_understanding_a_company_is_not_the_same_as_advising_it():
    """The distinction this whole pass exists to make visible."""
    from intent_engine.adaptive import opportunity as O
    from intent_engine.adaptive.engine import build
    ai = build(company="Acme", evidence_text=SOFTWARE)
    t = ai.telemetry()
    assert t["profile_available"] is True
    assert t["lens_available"] is True
    assert t["decision_reading_available"] is False
    assert ai.opportunity_map.state == O.POTENTIAL_DOMAINS
    assert ai.opportunity_map.domains
    assert ai.opportunity_map.what_would_unlock_a_decision


def test_a_potential_domain_cannot_be_ranked_beside_a_recommendation():
    """A KIND, not a low score. A type that cannot be sorted into the
    opportunity list is how that stays true whoever renders it."""
    from intent_engine.adaptive import opportunity as O
    assert not hasattr(O.PotentialDomain, "decision_priority")
    assert not issubclass(O.PotentialDomain, O.DecisionOpportunity)


def test_a_bounded_run_shows_no_empty_decision_or_chain_card():
    """Do not show an empty decision map. Do not show an empty causal chain.
    Do not fabricate one so the layout looks complete."""
    from intent_engine.adaptive import render as ar
    from intent_engine.adaptive.engine import build
    ai = build(company="Acme", evidence_text=SOFTWARE)
    html = ar.block("Acme", "r1", ai, csrf="t", base="/b")
    assert "Potential decision domains" in html
    assert "not current recommendations" in html
    assert "What would be worth investigating" in html
    assert "What we can and cannot say about Acme" in html
    assert "No decision opportunity cleared the bar" not in html


def test_an_investigation_chain_never_implies_settled_causality():
    from intent_engine.adaptive import causal as C
    from intent_engine.adaptive.engine import build
    ai = build(company="Acme", evidence_text=SOFTWARE)
    assert ai.causal_chain.kind == C.INVESTIGATION_CHAIN
    assert any(l.standing == C.OPEN_QUESTION for l in ai.causal_chain.links)


def test_the_classification_names_what_kind_of_source_established_it():
    from intent_engine.adaptive import profile as P
    assert P.model_source_of("VALIDATION_MANIFEST") == P.MODEL_SOURCE_CURATED
    assert P.model_source_of("SEC_SIC") == P.MODEL_SOURCE_REGULATOR
    assert P.model_source_of("SUBJECT_EVIDENCE") == P.MODEL_SOURCE_SUBJECT
    assert P.model_source_of("NONE") == P.MODEL_SOURCE_NONE
    for key, words in P.MODEL_SOURCE_WORDS.items():
        assert words and words[0].islower()
        assert "manifest" not in words
        assert "SIC" not in words
