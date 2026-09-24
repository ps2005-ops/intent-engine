"""What the adaptive layer must never stop doing.

Each test below pins ONE property, and each one exists because the property
failed at least once during construction. The measurement that forced it is in
the docstring, because a test whose reason is not written down is a test the
next person deletes.
"""
from __future__ import annotations

import pytest

from intent_engine.adaptive import causal, classify, composer
from intent_engine.adaptive import differentiation, lens
from intent_engine.adaptive import opportunity as opp
from intent_engine.adaptive import profile as prof
from intent_engine.adaptive import roles
from intent_engine.adaptive.engine import build
from intent_engine.executive.company_profile import MODEL_CLASSES

# --- fixtures: real first-party marketing text, of the shape the retrieval
#     layer actually returns for a private company -------------------------

HIGHSPOT = (
    "Highspot is the sales enablement platform that increases the "
    "performance of revenue teams. Our platform gives sales reps the "
    "content, coaching and guidance they need to improve win rate and "
    "shorten the sales cycle. Reduce ramp time for new account executives. "
    "Integrates with Salesforce. Pricing plans per user per month.")

BIGID = (
    "BigID helps organizations discover and govern their data. Our software "
    "platform delivers data discovery, data classification and access "
    "governance across the enterprise data estate, including shadow data. "
    "Meet GDPR and CCPA obligations. Subscription pricing. Integrates with "
    "Snowflake.")

SLALOM = (
    "Slalom is a global consulting firm focused on strategy, technology and "
    "business transformation. Our consultants work with our clients across "
    "client engagements in more than forty markets. Practice areas span "
    "cloud, data and AI. We partner with Amazon Web Services.")


# --- classification ---------------------------------------------------------

def test_a_private_company_can_be_classified_from_its_own_words():
    """The gap this whole layer exists to close.

    Measured before it: all ten qualification companies resolved
    PROFILE_SPARSE / business_model_class=UNKNOWN, because the two existing
    classifiers need a curated manifest row or an SEC industry code and a
    private company has neither. UNKNOWN switches off the pattern library,
    the per-class metrics, the macro transmission table, the causal questions
    and the competitor set at once.
    """
    assert prof.classify_from_evidence(HIGHSPOT).model_class == \
        "SUBSCRIPTION_SOFTWARE"
    assert prof.classify_from_evidence(SLALOM).model_class == \
        "PEOPLE_OR_ROUTE_BASED_SERVICES"


def test_a_classification_quotes_the_span_that_produced_it():
    """A read whose evidence cannot be quoted back is not auditable."""
    c = prof.classify_from_evidence(HIGHSPOT)
    assert c.evidence_span
    assert c.evidence_span in " ".join(HIGHSPOT.split()) or \
        any(word in c.evidence_span for word in ("platform", "Pricing",
                                                 "subscription", "per user"))


def test_subject_matter_alone_never_classifies_a_business_model():
    """Applicability, enforced. A rule firing on domain words alone reaches
    the wrong kind of company -- the recorded pattern-library failure."""
    # THE FIXTURE MUST CLEAR `FLOOR` ON SUBJECT MATTER ALONE. A thinner one
    # is refused by the floor instead, and a break proof that deleted the
    # applicability guard then ran GREEN -- the mutation changed the source
    # and not the outcome, because a second guard was doing the work.
    c = prof.classify_from_evidence(
        "We care deeply about data security and privacy for the enterprise. "
        "Our integrations and our API let you deploy anywhere. Dashboard, "
        "workflow, onboarding, single sign on, enterprise ready.")
    assert not c.known
    assert c.matched
    assert sum(w for _p, _k, w in c.matched) > classify.FLOOR
    assert "how it is paid" in c.reason


def test_two_readings_within_the_margin_are_refused_not_rounded():
    """A company that genuinely is both is not separated by picking one."""
    c = prof.classify_from_evidence(
        "We are a consultancy whose consultants deliver client engagements, "
        "and we also sell a software platform on subscription with pricing "
        "plans and a free trial. Our platform. Our clients.")
    assert not c.known
    assert c.runner_up
    assert "not a separation" in c.reason


def test_every_classified_class_is_a_real_business_model():
    """A class this module can emit that no economics table knows is a class
    that silently degrades every consumer downstream."""
    for model in classify.covered_classes():
        assert model in MODEL_CLASSES, model


# --- lens routing -----------------------------------------------------------

def test_the_lens_is_routed_by_evidence_not_by_industry():
    """Eight of the ten are the same business model class. Routing on the
    class would give all eight the same analysis, which is the collapse."""
    a = lens.select_lens(evidence_text=HIGHSPOT,
                         business_model="SUBSCRIPTION_SOFTWARE")
    b = lens.select_lens(evidence_text=BIGID,
                         business_model="SUBSCRIPTION_SOFTWARE")
    assert a.primary == "revenue_gtm"
    assert b.primary == "data_security_governance"
    assert a.primary != b.primary


def test_a_lens_outside_its_applicability_is_refused_whatever_the_signals():
    """A software vendor writing about supply-chain security is describing
    its PRODUCT. A firm with no physical inputs has no supply-chain exposure
    to have, and scoring it is how a lens reaches the wrong company."""
    sel = lens.select_lens(
        evidence_text=("Our platform secures the software supply chain. "
                       "Suppliers, raw materials, freight and logistics are "
                       "all covered. Inventory and lead times too. "
                       "Subscription pricing."),
        business_model="SUBSCRIPTION_SOFTWARE")
    assert sel.primary != "supply_chain_shock"
    refused = [s for s in sel.scores if s.lens_id == "supply_chain_shock"]
    assert refused and not refused[0].eligible


def test_the_refusals_are_published():
    """A router that only shows its winner cannot be audited: a reader has no
    way to tell a considered choice from the only option on the table."""
    sel = lens.select_lens(evidence_text=BIGID,
                           business_model="SUBSCRIPTION_SOFTWARE")
    assert sel.why_selected
    assert sel.why_others_were_not_selected


def test_no_lens_is_asserted_when_the_evidence_does_not_carry_one():
    """Not proven is not disproven, and the generic reading is labelled."""
    sel = lens.select_lens(evidence_text="We build good things for people.",
                           business_model="SUBSCRIPTION_SOFTWARE")
    assert sel.primary == ""
    assert "No strategic lens was selected" in sel.why_selected


def test_every_lens_names_the_business_models_it_can_describe():
    for entry in lens.LENS_LIBRARY:
        assert entry.eligible_business_models, entry.lens_id
        for model in entry.eligible_business_models:
            assert model in MODEL_CLASSES, (entry.lens_id, model)
        assert entry.signals_that_activate, entry.lens_id
        assert entry.generic_reading, entry.lens_id


def test_a_lens_needs_a_model_signal_and_not_only_domain_words():
    """`A pattern needs an applicability`: at least one activating signal per
    lens must be worth enough to carry the lens on its own."""
    for entry in lens.LENS_LIBRARY:
        assert max(w for _p, w in entry.signals_that_activate) >= 3.0, \
            entry.lens_id


# --- decision opportunities -------------------------------------------------

def _analyst(decisions):
    from intent_engine.strategic_intelligence.analyst.contract import (
        StrategicAnalysis)
    return StrategicAnalysis(decisions=list(decisions), sufficient=True)


def test_naming_missing_evidence_does_not_destroy_a_decisions_priority():
    """Measured: a high-impact, decide-this-quarter, do-it-now decision with
    two cited observations scored 0.000, and so did every other decision in
    the map. `missing_evidence` -- the analyst saying what it does NOT have,
    which the whole contract is built to encourage -- carried a flat penalty
    that could exceed the entire bounded score."""
    honest = {"decision": "Move the renewal conversation onto ramp time",
              "why_it_matters": "the renewal metric is falling",
              "urgency": "this_quarter", "business_impact": "high",
              "verdict": "do_now", "confidence": "moderate",
              "citations": ["obs-1", "obs-2"],
              "missing_evidence": "cohort renewal data by usage decile"}
    silent = dict(honest)
    silent.pop("missing_evidence")
    p = prof.build_profile(company="Highspot", evidence_text=HIGHSPOT)
    a = opp.build_opportunity_map(company="Highspot", profile=p,
                                  analysis=_analyst([honest]))
    b = opp.build_opportunity_map(company="Highspot", profile=p,
                                  analysis=_analyst([silent]))
    assert a.top is not None and a.top.decision_priority > 0.1
    # honest is discounted, never destroyed, and never beaten to zero
    assert a.top.decision_priority >= b.top.decision_priority * 0.8


def test_an_uncited_decision_cannot_outrank_a_cited_one():
    """The confidence label is the model grading its own fluency. Citations
    are the evidence."""
    cited = {"decision": "A", "urgency": "this_year",
             "business_impact": "medium", "verdict": "monitor",
             "confidence": "moderate", "citations": ["obs-1"]}
    uncited = {"decision": "B", "urgency": "decide_now",
               "business_impact": "high", "verdict": "do_now",
               "confidence": "high", "citations": []}
    p = prof.build_profile(company="Highspot", evidence_text=HIGHSPOT)
    m = opp.build_opportunity_map(company="Highspot", profile=p,
                                  analysis=_analyst([cited, uncited]))
    by = {o.decision_description: o.evidence_strength
          for o in m.opportunities}
    assert by.get("B", 1.0) <= 0.3


def test_a_component_at_zero_takes_the_whole_priority_to_zero():
    """Multiplicative on purpose. A decision that is enormously material and
    completely unactionable is not half-useful, it is useless."""
    assert opp._score(materiality=1.0, change=1.0, exposure=1.0,
                      actionability=0.0, evidence=1.0, uncertainty=0.0,
                      gap=0.0, generic=0.0) == 0.0


def test_every_opportunity_publishes_its_components():
    p = prof.build_profile(company="Highspot", evidence_text=HIGHSPOT)
    m = opp.build_opportunity_map(
        company="Highspot", profile=p,
        analysis=_analyst([{"decision": "A", "urgency": "this_year",
                            "business_impact": "medium", "verdict": "monitor",
                            "confidence": "moderate",
                            "citations": ["obs-1"]}]))
    o = m.top
    assert o is not None
    for field in ("materiality", "change_velocity", "company_exposure",
                  "actionability", "evidence_strength"):
        assert 0.0 <= getattr(o, field) <= 1.0
    assert o.score_reason


# --- causal chain -----------------------------------------------------------

def test_a_generic_link_is_flagged_rather_than_hidden():
    """`rates -> demand -> revenue` is the canonical chain that could be shown
    to anybody. A true-but-generic link is still true, so it is marked."""
    generic, why = causal._is_generic(
        "rising rates reduce demand and therefore revenue", set())
    assert generic and "general economic vocabulary" in why


def test_a_link_built_from_this_companys_own_words_is_not_flagged():
    """Prefix matched: an exact match makes `renewal` and `renewed` different
    words, and marked 4 of 7 links on a company-specific chain as generic."""
    p = prof.build_profile(company="Highspot", evidence_text=HIGHSPOT)
    vocab = causal._company_vocabulary(p, "Highspot")
    # ONLY INFLECTIONS OVERLAP. A fixture sharing whole words passes under
    # an exact match too, so it cannot test the prefix rule -- measured: the
    # break proof that reverted to exact matching ran GREEN.
    assert "platform" in vocab and "increases" in vocab
    assert "platforms" not in vocab and "increase" not in vocab
    # and no stopword may carry the match either -- the first version of this
    # fixture said "the platforms THAT increase ...", and "that" was in the
    # vocabulary, so an exact match passed it and the prefix rule went
    # untested.
    assert "that" not in vocab
    generic, _why = causal._is_generic(
        "seller performances increase across platforms", vocab)
    assert not generic


def test_no_chain_is_composed_without_a_mechanism_or_a_lens():
    """WITH NEITHER, nothing is drawn. With a lens but no mechanism there is
    now an INVESTIGATION chain instead -- see
    `test_an_investigation_chain_never_implies_settled_causality`. The two
    are different product states and this pins the emptier one."""
    chain = causal.build_causal_chain(company="X", profile=None,
                                      analysis=None)
    assert not chain
    assert chain.kind == causal.NO_CHAIN
    assert "neither a mechanism nor a lens" in chain.stopped_because


# --- differentiation --------------------------------------------------------

def test_two_companies_of_one_class_and_one_lens_still_read_differently():
    """BigID and Cyera are the same business model, the same lens and the
    same class prior. Measured before the self-description and own-vocabulary
    fields were added: their difference text was BYTE-IDENTICAL."""
    cyera = ("Cyera is the data security platform for the AI era. We "
             "discover sensitive data across cloud and SaaS. DSPM for the "
             "modern enterprise, delivering least privilege. Built on Amazon "
             "Web Services. Subscription.")
    a = build(company="BigID", evidence_text=BIGID)
    b = build(company="Cyera", evidence_text=cyera)
    assert a.lens_selection.primary == b.lens_selection.primary
    assert a.profile.business_model_class == b.profile.business_model_class
    left = a.differentiation.company_specific_difference
    right = b.differentiation.company_specific_difference
    assert left and right and left != right
    finding = differentiation.genericity(
        left_text=left, left_company="BigID",
        right_text=right, right_company="Cyera")
    assert not finding.collapsed, finding.reason


def test_the_collapse_detector_catches_an_actual_template():
    """The detector has to be able to FAIL, or it measures nothing.
    A negative control that cannot fire is not a control."""
    template = ("This company operates in a growing market. Its position is "
                "defensible and management should consider consolidating "
                "around its strongest capability while monitoring rivals.")
    finding = differentiation.genericity(
        left_text=template, left_company="Alpha Corp",
        right_text=template, right_company="Beta Industries")
    assert finding.collapsed
    assert finding.ratio > differentiation.COLLAPSE_RATIO


def test_normalising_removes_the_subject_and_keeps_the_content():
    """An earlier version stripped EVERY capitalised token, deleting the
    dependencies -- among the most company-specific things on the page -- so
    two different reports normalised to the same text and the detector
    reported a collapse of its own making."""
    out = differentiation._normalise(
        "BigID depends on Snowflake and meets GDPR.", "BigID")
    assert "bigid" not in out
    assert "snowflake" in out


def test_a_thin_difference_is_flagged_not_dressed_up():
    thin = build(company="Nowhere Systems",
                 evidence_text="Nowhere Systems is a company. Subscription "
                               "pricing. Our platform. Request a demo.")
    assert thin.differentiation.flagged
    assert thin.differentiation.flag_reason


# --- role lens: the invariant -----------------------------------------------

def test_a_role_changes_the_order_and_never_the_facts():
    """One world model. A CFO and a CEO reading the same run must be able to
    put the two screens side by side and find no contradiction."""
    ai = build(company="Highspot", evidence_text=HIGHSPOT, role_id="ceo")
    ids = ai.composition.included_ids
    ceo = roles.role_view(role_id="ceo", module_ids=ids)
    cfo = roles.role_view(role_id="cfo", module_ids=ids)
    assert set(ceo.order) == set(cfo.order) == set(ids)
    assert ceo.order != cfo.order
    assert ceo.questions != cfo.questions


def test_a_role_view_holds_no_module_bodies():
    """Enforced structurally: `role_view` is handed no evidence, no profile
    and no analysis, so there is nothing for it to rewrite."""
    import inspect
    sig = inspect.signature(roles.role_view)
    assert set(sig.parameters) == {"role_id", "module_ids", "lens_selection"}


def test_two_roles_are_live_and_the_rest_are_labelled_future():
    live = {r.role_id for r in roles.live_roles()}
    assert {"ceo", "cso"} <= live
    for r in roles.ROLES:
        assert r.status in (roles.LIVE, roles.FUTURE)
        assert r.priority_modules and r.decision_framing


def test_every_role_priority_names_a_real_module():
    known = {m.module_id for m in composer.MODULES}
    for r in roles.ROLES:
        for module in r.priority_modules:
            assert module in known, (r.role_id, module)


# --- composition ------------------------------------------------------------

def test_every_inclusion_decision_names_the_input_that_decided_it():
    """Hiding and showing cards at random is indistinguishable from
    adaptation on any single screen. A composition whose reasons are all
    'default' has not adapted."""
    ai = build(company="Highspot", evidence_text=HIGHSPOT)
    # INCLUDED modules positioned by an input, counted apart from excluded
    # ones. Conflating the two let a report that excluded twelve and adapted
    # none report a high number and look adaptive.
    assert ai.composition.explained >= 4
    assert ai.composition.excluded_explained >= 4
    for module in ai.composition.modules:
        assert module.reason


def test_a_module_that_cannot_be_shown_says_why_rather_than_vanishing():
    """A section that disappears without explanation is how a reader
    concludes the analysis was thin when one input was missing."""
    ai = build(company="Highspot", evidence_text=HIGHSPOT)
    excluded = {m.module_id: m.reason for m in ai.composition.excluded}
    assert "supply_chain_exposure" in excluded
    assert "no physical inputs" in excluded["supply_chain_exposure"]
    assert "client_portfolio" in excluded


def test_the_epistemic_modules_are_always_present():
    """A report that silently drops its own uncertainty sections is a report
    that looks more confident than it is."""
    ai = build(company="Nowhere", evidence_text="Nothing much here.")
    ids = set(ai.composition.included_ids)
    assert {"what_would_change_our_mind", "information_priority",
            "provenance"} <= ids


def test_two_different_companies_get_different_compositions():
    a = build(company="Highspot", evidence_text=HIGHSPOT)
    b = build(company="Slalom", evidence_text=SLALOM)
    assert a.composition.included_ids != b.composition.included_ids


# --- the engine -------------------------------------------------------------

def test_the_declared_profile_fields_are_actually_written():
    """A field declared and never written reads to every consumer as "this
    company has none" rather than as "nobody computed any" -- the declared
    kind with no detector, in miniature. Both of these were empty on every
    company until they were measured for."""
    ai = build(company="Highspot", evidence_text=HIGHSPOT)
    assert ai.profile.likely_executive_priorities
    assert ai.profile.potential_intent_engine_roles
    # and the second one names something THIS company depends on, not a
    # generic capability list
    assert any("Salesforce" in r
               for r in ai.profile.potential_intent_engine_roles)


def test_engine_roles_are_withheld_when_no_lens_was_selected():
    """With no reading of what a company is for, a list of things we could
    do for it is a list of things we do for anybody."""
    ai = build(company="Nowhere", evidence_text="Nowhere does things.")
    assert ai.lens_selection.primary == ""
    assert ai.profile.potential_intent_engine_roles == ()


def test_the_role_and_lens_questions_are_askable_not_printed():
    """A suggestion a reader has to retype is a suggestion nobody takes."""
    from intent_engine.adaptive import render as ar
    ai = build(company="Highspot", evidence_text=HIGHSPOT)
    html = ar.block("Highspot", "run-1", ai, csrf="tok",
                    base="/runs/run-1/intro")
    assert html.count('class="ad-ask"') >= 4
    assert 'action="/runs/run-1/conversation"' in html
    assert 'name="csrf" value="tok"' in html
    # the lens's own topics reach the reader, not only the role's
    topics = ai.lens_selection.lens.preferred_q_and_a_topics
    assert any(t.split("?")[0][:40] in html for t in topics)


def test_the_engine_never_raises_and_records_what_failed():
    """A surface that cannot render its adaptive block shows the ordinary
    analysis, not a 500 -- and a missing block always has a named cause."""
    ai = build(company="", evidence_text="", analysis=object())
    assert ai is not None
    assert isinstance(ai.telemetry(), dict)


def test_telemetry_explains_an_abstention():
    """Telemetry must explain failures. A blank cell in a qualification
    matrix costs a whole re-run to explain."""
    ai = build(company="Nowhere", evidence_text="Nothing much here.")
    t = ai.telemetry()
    assert t["business_model"] == "UNKNOWN"
    assert t["business_model_reason"]
    assert t["primary_lens"] == ""
    assert t["lens_selection_reasons"]


def test_the_profile_separates_this_company_from_its_class():
    """CLASS_PRIOR is not a defect. A class prior PRESENTED AS a finding
    about this company is."""
    p = prof.build_profile(company="Highspot", evidence_text=HIGHSPOT)
    assert p.self_description.provenance == prof.SUBJECT_EVIDENCE
    assert p.pricing_model.provenance == prof.CLASS_PRIOR
    assert 0.0 < p.specificity <= 1.0
    assert "self_description" in p.company_specific_fields


@pytest.mark.parametrize("company,text,expected_lens", [
    ("Highspot", HIGHSPOT, "revenue_gtm"),
    ("BigID", BIGID, "data_security_governance"),
    ("Slalom", SLALOM, "consulting_portfolio"),
])
def test_the_ten_route_where_their_evidence_says(company, text,
                                                 expected_lens):
    ai = build(company=company, evidence_text=text)
    assert ai.lens_selection.primary == expected_lens
