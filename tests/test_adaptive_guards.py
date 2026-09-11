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

    # POSITIVE CONTROL FOR THE OTHER END. The fixture above is two short
    # sentences, so `[:max_chars]` -- the only place a span is cut at its
    # end -- never ran, and the half of this test's name after "or" asserted
    # nothing. A sentence LONGER than the budget is the case that reaches it.
    from intent_engine.adaptive.spans import MAX_CHARS
    long_one = (
        "Highspot is the sales enablement platform that increases the "
        "performance of sales teams by bridging the gap between strategy "
        "and execution across every customer conversation and every revenue "
        "motion a modern enterprise runs, and it does so with unified "
        "content management, guided selling, training and coaching, and "
        "engagement analytics in one system.")
    assert len(long_one) > MAX_CHARS, "fixture must exceed the budget"
    body = "Intro line here. " + long_one + " Trailing sentence follows."
    j = body.index("bridging")
    q2 = quote_around(body, j, j + 8)
    assert q2
    assert len(q2) <= MAX_CHARS
    # THE PROPERTY: the quote may be elided, but the cut must land on a word
    # boundary of the source sentence. Unpatched this ends "...training an"
    # and the next character in the source is "d".
    core = q2.rstrip(" \u2026")
    assert core and long_one.startswith(core), q2
    nxt = long_one[len(core):len(core) + 1]
    assert (not nxt) or (not nxt.isalnum()), q2


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

def test_a_company_is_never_its_own_critical_dependency():
    """MEASURED LIVE (Highspot, be5fde12). Its own page carries

        "Partner with Highspot's services team to move fast..."

    the `partners with` dependency pattern captured the subject, and the
    report told Highspot's chief executive "It names Highspot as something it
    depends on."
    """
    from intent_engine.adaptive.profile import build_profile, _is_the_subject
    body = ("Highspot is the sales enablement platform for revenue teams. "
            "Partner with Highspot's services team to move fast and scale. "
            "Highspot integrates with Salesforce for pipeline data.")
    p = build_profile(company="Highspot", domain="highspot.com",
                      evidence_text=body)
    named = [f.value for f in p.critical_dependencies]
    assert not any(_is_the_subject(v, "Highspot") for v in named), named
    # POSITIVE CONTROL: the real dependency in the same text still survives,
    # or this guard is just switching the extractor off.
    assert any("Salesforce" in v for v in named), named

def test_a_consultancy_is_read_as_services_from_its_own_words():
    """MEASURED LIVE (Slalom and Point B, be5fde12).

    Slalom's run retrieved four company-owned pages, all of them CLIENT
    INDUSTRY pages, whose text says "personalized consulting services". The
    library held "advisory services" and "consulting firm" and matched
    neither, so a consultancy scored 0.0 on the services class and the page
    told its chief executive the business model was not established.

    Point B scored 6.0 for services against 4.0 for branded consumer -- and
    the 4.0 was "Consumer Packaged Goods INDUSTRIES", a sector it SERVES.
    """
    from intent_engine.adaptive.classify import classify_from_evidence
    slalom = ("Media & communications | Slalom AU. Slalom’s deep experience "
              "and personalized consulting services help media and "
              "communications companies keep pace with the industry’s rapid "
              "evolution.")
    assert classify_from_evidence(slalom).model_class == (
        "PEOPLE_OR_ROUTE_BASED_SERVICES")

    point_b = ("Point B is a management consulting firm that specializes in "
               "leveraging technology to unlock human potential. We work "
               "across the Life Sciences, Retail, and Consumer Packaged "
               "Goods (CPG) industries.")
    c = classify_from_evidence(point_b)
    assert c.model_class == "PEOPLE_OR_ROUTE_BASED_SERVICES", c.reason

    # NEGATIVE CONTROL. A subscription business that also sells
    # implementation help is still a subscription business -- widening the
    # services vocabulary must not reach across the margin and take it.
    saas = ("Highspot is the sales enablement platform for revenue teams. "
            "Pricing is per user per month, billed annually as a "
            "subscription with annual recurring revenue. Our professional "
            "services team also offers consulting services for onboarding.")
    assert classify_from_evidence(saas).model_class == "SUBSCRIPTION_SOFTWARE"

def test_an_abstention_does_not_contradict_the_recommendation_below_it():
    """MEASURED LIVE (Highspot, be5fde12). One page said both

        "What we cannot yet conclude -- What this management should actually
         do."

    and, one screen down, "What we recommend -- Move on pricing and
    packaging...". The founder layer's reading comes from the economics of the
    business-model class and is badged BOUNDED; the adaptive layer's refusal
    is about evidence on THIS company. The abstention has to say which it
    means, because the page does not stop at the abstention.
    """
    from intent_engine.adaptive import render as ar

    class _Map:
        has_reading = False
        evidence_limitation = "not enough independent material"
        what_would_unlock_a_decision = "a dated third-party account"
        state = "POTENTIAL_DOMAINS"

    class _Adaptive:
        opportunity_map = _Map()
        profile = None
        lens_selection = None

    html = ar.bounded_block("Highspot", _Adaptive())
    assert "What we cannot yet conclude" in html
    # It must scope the refusal to THIS RUN's evidence...
    assert "this run" in html, html
    # ...and must not make the unqualified claim that contradicts a
    # recommendation rendered further down the same page.
    assert "What this management should actually do." not in html, html

def test_a_newsletter_call_to_action_is_not_evidence():
    """MEASURED LIVE (Highspot, be5fde12). Under "The evidence this rests on",
    one of three quotations was "Stay informed on our sales enablement
    innovation." -- a complete, terminated sentence, which is why sentence
    snapping kept it and only a marker can refuse it."""
    from intent_engine.strategic_intelligence.evidence_text import (
        furniture_reason,
    )
    for cta in ("Stay informed on our sales enablement innovation.",
                "Stay up-to-date on all of the news in sales and marketing.",
                "Subscribe to our monthly revenue operations newsletter."):
        assert furniture_reason(cta), cta

    # POSITIVE CONTROL: a real first-party statement is still evidence, or
    # the marker list has simply been made to refuse prose.
    assert not furniture_reason(
        "Highspot is the sales enablement platform that increases the "
        "performance of revenue teams across every customer conversation.")

def test_one_run_resolves_one_business_model_on_every_surface():
    """MEASURED LIVE (Highspot, be5fde12). `/intro` said "It is a subscription
    software business, read from its own account of how it is paid" and
    `/xray` -- linked from that same page -- said "What kind of business this
    is has not been established", which is the defect this phase exists to
    remove, alive on a second surface.

    `profile_for` has three rungs and rung 3 only fires when the caller passes
    `published_text`. The adaptive call site passed it; the strategic-read
    call site did not.
    """
    import inspect

    from intent_engine.executive.company_profile import profile_for

    owned = ("Media & communications | Slalom AU. Slalom’s deep experience "
             "and personalized consulting services help media and "
             "communications companies keep pace with the industry’s rapid "
             "evolution.")

    # THE TWO RUNGS ARE REALLY DIFFERENT, or the rest of this proves nothing.
    without = profile_for(name="Slalom", domain="slalom.com",
                          registrant=None, evidence_text="")
    with_text = profile_for(name="Slalom", domain="slalom.com",
                            registrant=None, evidence_text="",
                            published_text=owned)
    assert not getattr(without, "known", False)
    assert getattr(with_text, "known", False)
    assert with_text.business_model_class == "PEOPLE_OR_ROUTE_BASED_SERVICES"

    # AND THE STRATEGIC-READ CALL SITE USES THE SECOND ONE. Read from the
    # running code rather than from a comment about it, because a grep over
    # prose matches the sentence explaining the rule.
    from intent_engine.webapp import app as webapp_app
    src = inspect.getsource(
        webapp_app.WebApp._compose_founder_economic_context)
    assert "published_text=" in src, (
        "the strategic read resolves a second profile for the same run")

def test_one_run_resolves_one_profile_for_every_surface():
    """MEASURED LIVE (807a4143): seven of ten companies said

        /intro  "It is a subscription software business, read from its own
                 account of how it is paid"
        /xray   "What kind of business this is has not been established"

    and the correlation with the model's SOURCE was exact -- every company
    classified at rung 3 carried it, the one public company at rung 2 did
    not. Six call sites resolved a profile and four never passed
    `published_text`, so rung 3 was unreachable from four of them.

    The repair is a canonical run-scoped selection every surface reads. This
    asserts the PRODUCERS agree, and that the consumers take the canonical
    answer when one is offered.
    """
    import inspect

    from intent_engine.webapp import app as webapp_app

    # 1. THE PRODUCER EXISTS AND GATHERS ALL THREE RUNGS' INPUTS.
    src = inspect.getsource(webapp_app.WebApp._canonical_profile_inputs)
    for rung in ("registrant", "evidence_text", "published_text"):
        assert rung in src, rung

    # 2. EVERY CONSUMER READS IT. Read from the running code rather than by
    # grepping prose: a grep over comments matches the sentence explaining
    # the rule instead of the call that obeys it.
    for method, what in (
            (webapp_app.WebApp._run_xray, "the X-Ray"),
            (webapp_app.WebApp._compose_strategic_read, "the strategic read"),
            (webapp_app.WebApp._adaptive, "the adaptive block"),
            (webapp_app.WebApp._compose_founder_economic_context,
             "the economic context")):
        body = inspect.getsource(method)
        assert "_canonical_selection" in body, what

    # 3. THE DECISION COMPOSER ACCEPTS IT, so the X-Ray panel stops building
    # its own profile from the manifest alone.
    from intent_engine.executive import decision_synthesis as DS
    # THE PROFILE, NOT THE WHOLE SELECTION. Passing the selection made the
    # live X-Ray and the dossier X-Ray ask two different questions, because
    # the archetype and the decision question are scored from the DOSSIER's
    # RecordFacts. The profile was the inconsistent thing; the facts belong
    # to the dossier.
    assert "profile" in inspect.signature(DS.compose).parameters
    assert "_select(dossier, hidden, registrant, profile=profile)" in (
        inspect.getsource(DS.compose))


def test_the_canonical_selection_reaches_rung_three():
    """The producer must actually classify a private company.

    A canonical answer that is canonically UNKNOWN would make every surface
    agree and would fix nothing.
    """
    from intent_engine.executive.analysis_selection import select
    owned = ("Point B is a management consulting firm that specializes in "
             "leveraging technology to unlock human potential.")
    without = select(name="Point B", domain="pointb.com")
    with_text = select(name="Point B", domain="pointb.com",
                       published_text=owned)
    assert not without.profile.known
    assert with_text.profile.known
    assert with_text.profile.business_model_class == (
        "PEOPLE_OR_ROUTE_BASED_SERVICES")

def test_the_subject_corpus_leads_with_the_company_own_description():
    """MEASURED LIVE (Point B, 807a4143): UNKNOWN after retrieving EIGHT of
    its own pages including /About, because the corpus was built from
    observation EXCERPTS and none happened to carry the sentence its About
    page leads with. A retrieved document carries `meta_description` -- the
    company's own one-sentence account of itself, structured rather than
    sampled -- and the corpus ignored it.
    """
    import inspect

    from intent_engine.webapp import app as webapp_app
    src = inspect.getsource(webapp_app.WebApp._subject_published_text)
    assert "meta_description" in src
    assert "_retrieved_documents" in src
    # the lead must be joined BEFORE the bodies, or the first self-description
    # match is still whichever excerpt happened to come first
    assert "[filings] + lead + owned" in src


def test_a_company_describing_itself_through_its_product_is_a_self_description():
    """Druva writes "Druva's AI-powered, cloud-native SaaS platform delivers
    data security..." -- a possessive, so the "X is a Y" form never matched
    and Druva was one of two companies with no self-description at all."""
    from intent_engine.adaptive.profile import _self_description
    got = _self_description(
        "Druva\u2019s AI-powered, cloud-native SaaS platform delivers data "
        "security, identity resilience and cyber recovery.", "Druva")
    assert got and "delivers data security" in got[0]

    # NEGATIVE CONTROLS: a possessive about the company is not the company's
    # account of what it is.
    assert not _self_description(
        "Acme\u2019s customers say the product transformed their business.",
        "Acme")
    assert not _self_description(
        "Acme\u2019s press releases are available in the newsroom.", "Acme")


def test_the_chain_heading_states_the_epistemic_state():
    """MEASURED LIVE (Point B, 807a4143): the body said "No chain is shown, of
    either kind" under the heading "From the change to the decision". The
    heading is the part a scanning reader actually reads."""
    import html
    import re

    from intent_engine.adaptive import causal as C
    from intent_engine.adaptive import render as ar

    class _Chain:
        def __init__(self, kind):
            self.kind, self.links, self.reason = kind, (), "nothing to follow"

    class _Adaptive:
        def __init__(self, kind):
            self.causal_chain = _Chain(kind)

    def heading_for(kind):
        out = ar.causal_chain(_Adaptive(kind))
        return html.unescape(re.search(r"<h2[^>]*>(.*?)</h2>", out).group(1))

    assert heading_for(C.DECISION_CHAIN) == "From the change to the decision"
    assert heading_for(C.INVESTIGATION_CHAIN) == (
        "What would be worth investigating")
    no_chain = heading_for(C.NO_CHAIN)
    assert no_chain != "From the change to the decision"
    assert "no supported chain" in no_chain.lower()


def test_a_bullet_fragment_is_never_quoted_as_a_sentence():
    """MEASURED LIVE (ZoomInfo, 807a4143). The page carried a risk-factor list
    item quoted as evidence: a bullet glyph at the front, a comma at the back,
    the middle of one item of a list."""
    from intent_engine.adaptive.spans import is_quotable, quote_around
    # THE FIXTURE MUST ISOLATE THE BULLET RULE. An earlier version used the
    # live string, which ALSO ends on a comma -- so the terminal-punctuation
    # rule refused it whether or not the bullet rule existed, and the break
    # proof ran NOT_CAUGHT. This one is well-formed at every other point, so
    # only the leading glyph can decide it.
    assert not is_quotable(
        "\u2022ZoomInfo is a global leader in modern go-to-market software, "
        "data, and intelligence for revenue teams.")
    # and the live string, which is refused at BOTH ends
    assert not is_quotable(
        "\u2022We experience competition from other companies and "
        "technologies that allow businesses to gather data,")
    assert not is_quotable(
        "and we may in the future face competition from LLM providers,")
    # A PASSAGE THAT BEGINS MID-SENTENCE is the same fault at the other end.
    assert not is_quotable(
        "etherlands New Zealand United Kingdom United States Careers.")
    # ...but a lowercase BRAND is how the company writes its own name, and
    # refusing it would delete real first-party evidence.
    assert is_quotable(
        "iPhone integrations let teams move data between systems quickly.")
    assert is_quotable(
        "eBay is a global commerce leader connecting millions of buyers.")

    # POSITIVE CONTROL: a list item that IS a whole statement stays quotable
    # once its marker is dropped, or this guard just deletes real evidence.
    assert is_quotable(
        "ZoomInfo is a global leader in modern go-to-market software, data, "
        "and intelligence for sales and marketing teams.")
    text = ("Our platform matters. \u2022 ZoomInfo is a global leader in "
            "modern go-to-market software and intelligence for revenue "
            "teams everywhere. Another line follows here.")
    i = text.index("global leader")
    got = quote_around(text, i, i + 13)
    assert got and got[0] not in "\u2022-*"


def test_the_same_passage_is_never_quoted_twice():
    """MEASURED LIVE (ZoomInfo, 807a4143): one sentence rendered twice. The
    guard was `dict.fromkeys` -- exact-string dedup -- and three producers
    quote with three different budgets (240, 280, 300), so one passage
    arrives as two strings."""
    from intent_engine.adaptive.spans import dedupe_passages
    short = ("Many of our customers use our integrations to access our data "
             "from within, or send data to, CRM, marketing automation")
    long_ = short + ", applicant tracking and other systems."
    got = dedupe_passages([short, long_, "A different sentence entirely."])
    assert len(got) == 2, got
    # the MORE COMPLETE form survives
    assert long_ in got


def test_long_provenance_urls_wrap_rather_than_overflow():
    """MEASURED LIVE (Monte Carlo Data, 807a4143): the retrieval-failure page
    -- the one naming every source it tried and why each was refused -- pushed
    85px off a 375px screen. `max-width` and `overflow-x` do nothing to an
    INLINE <code>."""
    from intent_engine.webapp import app as webapp_app
    css = webapp_app.BASE_CSS if hasattr(webapp_app, "BASE_CSS") else ""
    if not css:
        import inspect
        css = inspect.getsource(webapp_app)
    assert "overflow-wrap:anywhere" in css
    # provenance is wrapped, never hidden
    assert "code,.src,.prov{overflow-wrap:anywhere" in css

def test_the_canonical_profile_fills_a_gap_and_never_overrides():
    """`profile_for` consults the company's own published account ONLY where
    the manifest and the industry code both refused. This seam has to obey
    the same order.

    Passing the canonical profile unconditionally made the live X-Ray and the
    dossier X-Ray ask two different decision questions for a company the
    manifest DOES classify -- overriding a better-sourced answer to remove a
    contradiction only moves it.
    """
    from intent_engine.executive import decision_synthesis as DS
    from intent_engine.executive.company_profile import (
        CompanyIntelligenceProfile,
    )

    class _Dossier:
        company_id = "acme"
        canonical_name = "Acme"
        market_block = {}
        blocks = ()

    rung3 = CompanyIntelligenceProfile(
        company_id="acme", company_name="Acme", known=True,
        business_model_class="PEOPLE_OR_ROUTE_BASED_SERVICES")

    own = DS._select(_Dossier(), "", None)
    got = DS._select(_Dossier(), "", None, profile=rung3)
    if getattr(getattr(own, "profile", None), "known", False):
        # a surface that already had an answer keeps its own
        assert got.profile.business_model_class == (
            own.profile.business_model_class)
    else:
        # and an unclassified one takes the run's canonical answer
        assert got.profile.business_model_class == (
            "PEOPLE_OR_ROUTE_BASED_SERVICES")


def test_every_per_request_memo_is_cleared_for_the_next_visitor():
    """Worker threads are reused, so a memo left on the thread-local is the
    PREVIOUS visitor's company.

    The canonical selection memo was added without a reset line, and three
    existing tests failed in batch while passing alone -- the signature of a
    memo outliving its request. This asserts every memo assigned on
    `self._request` anywhere in the module is also cleared in the per-request
    reset, so the next one cannot be forgotten silently.
    """
    import inspect
    import re

    from intent_engine.webapp import app as webapp_app
    src = inspect.getsource(webapp_app)
    assigned = set(re.findall(r"self\._request\.([a-z_]+)\s*=", src))
    # `claim` is assigned None rather than a container; both count as cleared.
    cleared = set(re.findall(
        r"self\._request\.([a-z_]+)\s*=\s*(?:\{\}|\[\]|None)\n", src))
    missing = sorted(assigned - cleared)
    assert not missing, (
        "these per-request memos are never reset, so they survive into the "
        f"next visitor's request: {missing}")

def test_one_quotation_per_passage_on_the_whole_page():
    """MEASURED LIVE (Highspot, 7e6f3c9c). "Highspot helps enablement teams
    scale their impact with AI..." rendered under the lens block AND under
    "the evidence this rests on".

    Neither producer rendered it twice -- the PAGE did -- so deduping inside
    each producer could not see it.
    """
    from intent_engine.adaptive.render import _one_quote_per_passage
    same = ("Highspot helps enablement teams scale their impact with AI "
            "that identifies skill gaps and personalizes training.")
    html = (f'<section><p class="ad-quote">{same}</p></section>'
            f'<section><p class="ad-quote">{same}</p></section>'
            f'<section><p class="ad-quote">A different sentence entirely, '
            f'long enough to count as its own passage.</p></section>')
    out = _one_quote_per_passage(html)
    assert out.count('class="ad-quote"') == 2, out
    assert "A different sentence entirely" in out

    # THE TWO COPIES ARE NOT BYTE-EQUAL in production: three producers quote
    # at three budgets, so one arrives truncated.
    short = same[:80]
    html2 = (f'<section><p class="ad-quote">{short}</p></section>'
             f'<section><p class="ad-quote">{same}</p></section>')
    assert _one_quote_per_passage(html2).count('class="ad-quote"') == 1


def test_the_peer_set_absence_does_not_contradict_an_established_model():
    """MEASURED LIVE (Highspot, 7e6f3c9c): the X-Ray printed "What this
    business is: SUBSCRIPTION_SOFTWARE" and, two blocks later, "this
    company's business model is not classified here".

    Both sentences were true -- the second is about the peer universe -- and
    the page contradicted itself, which is the only thing a reader sees.
    """
    from intent_engine.founder_brief.xray import _competitor_body
    known = _competitor_body({"competitors": (),
                              "company_profile": {"known": True}})
    assert "business model is not classified" not in known, known
    assert "validation universe" in known

    # ...and when the model genuinely is unknown, the honest reason stands.
    unknown = _competitor_body({"competitors": (),
                                "company_profile": {"known": False}})
    assert "business model is not classified" in unknown

def test_every_evidence_producer_quotes_through_the_selector():
    """MEASURED LIVE (ZoomInfo, 7e6f3c9c). After `quote_around` learned to
    refuse a passage opening with a bullet glyph, the page STILL carried

        "\u2022We experience competition from other companies ... and
         generative AI companies,"

    because two producers in `profile.py` never called it: they cut a span
    with `[^.]*KEYWORD[^.]*.` and truncated it at 280 characters -- a regex
    window and an arithmetic cut, which is the pair `spans.py` exists to
    replace. A selector three of five producers use is a convention, not a
    canon.
    """
    from intent_engine.adaptive.profile import build_profile
    from intent_engine.adaptive.spans import is_quotable

    body = ("ZoomInfo is a global leader in modern go-to-market software. "
            "\u2022We experience competition from other companies and "
            "technologies that allow businesses to gather and aggregate "
            "sales, marketing, recruiting, and other data, and we may in the "
            "future face competition from prominent large-language-model "
            "(LLM) providers and generative AI companies, "
            "Our platform uses AI and machine learning to enrich records. "
            "We maintain our proprietary data graph across many contacts.")
    p = build_profile(company="ZoomInfo", domain="zoominfo.com",
                      evidence_text=body)

    quoted = [getattr(getattr(p, "technology_exposure", None), "evidence", "")]
    quoted += [f.evidence for f in (getattr(p, "strategic_assets", ()) or ())]
    quoted = [q for q in quoted if q]
    assert quoted, "no producer emitted evidence at all"
    for q in quoted:
        assert q[0] not in "\u2022\u25cf\u25aa\u00b7*-", q
        assert is_quotable(q), q

def test_a_self_description_is_not_refused_for_being_slightly_long():
    """MEASURED LIVE (Cyera, 7e6f3c9c). Its own meta description reads

        "Cyera is an AI-native data security platform that helps enterprises
         discover, classify, govern, and protect sensitive data across cloud,
         SaaS, on-prem, and AI environments."

    which is 159 characters after "is an", against a capture capped at 150.
    It was refused for being NINE CHARACTERS too long -- and Cyera was then
    one of the two companies whose bounded block fell back to the class prior
    and scored 0.927 similarity with Druva.
    """
    from intent_engine.adaptive.profile import _SELF_MAX, _self_description

    cyera = ("Cyera is an AI-native data security platform that helps "
             "enterprises discover, classify, govern, and protect sensitive "
             "data across cloud, SaaS, on-prem, and AI environments.")
    got = _self_description(cyera, "Cyera")
    assert got, "a 159-character self-description was refused"
    assert "AI-native data security platform" in got[0]

    # THE CAP STILL EXISTS. An unbounded run of non-terminating text is a
    # paragraph, not a sentence, and quoting one back is how a page fills
    # with somebody's whole homepage.
    runaway = "Acme is a " + ("very " * 200) + "long thing."
    assert _SELF_MAX < 400
    assert not _self_description(runaway, "Acme")

    # AND A META DESCRIPTION THAT IS NOT A SELF-DESCRIPTION IS STILL REFUSED,
    # or the cap change would simply have made the matcher less careful.
    veeam = ("Discover cyber resilient solutions for AI and data. See risk "
             "reduced and recovery assured.")
    assert not _self_description(veeam, "Veeam")

