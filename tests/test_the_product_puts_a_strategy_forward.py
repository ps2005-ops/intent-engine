"""The v5 pre-freeze invariants: a bounded read, a walled history, one story.

Every test here corresponds to a defect that was live on `377ea63` and was
read off the deployed page rather than found by the suite. The suite was green
throughout, which is the reason this file exists.
"""
from __future__ import annotations

import datetime as _dt

import pytest

from intent_engine.executive import history_rewind as HR
from intent_engine.executive import strategic_read as SR
from intent_engine.executive.analysis_selection import select
from intent_engine.founder_brief import flow
from intent_engine.product_eval import defect_taxonomy as DT
from intent_engine.product_eval import self_correction as SC
from intent_engine.strategic_intelligence.patterns import (PATTERN_LIBRARY,
                                                           patterns_for)

# Companies in the validation manifest, spanning materially different models.
GOLDEN = (
    ("Cloudflare, Inc.", "cloudflare.com"),
    ("Caterpillar Inc.", "caterpillar.com"),
    ("Shopify Inc.", "shopify.com"),
    ("Johnson & Johnson", "jnj.com"),
    ("Bank of America Corporation", "bankofamerica.com"),
    ("Stripe, Inc.", "stripe.com"),
)


# ===========================================================================
# §4 — the product almost always puts a bounded strategy forward
# ===========================================================================
@pytest.mark.parametrize("company,domain", GOLDEN)
def test_an_identifiable_company_always_gets_a_strategic_read(company, domain):
    """THE DEFECT THAT REOPENED THE GATE.

    Live on 377ea63 the first customer-facing sentence for Cloudflare was
    "No strategic reading of Cloudflare, Inc. cleared the evidence bar, so
    none is asserted here." -- with no third-party source being the reason.
    A missing corroborating source may cost confidence, causal strength and
    measured magnitude. It may not cost the synthesis.
    """
    read = SR.compose(company=company, domain=domain)
    assert read.puts_a_strategy_forward, company
    assert read.standing in (SR.READ_SUPPORTED, SR.READ_BOUNDED)
    assert read.identity and read.central_question
    assert read.level6_action is not None


@pytest.mark.parametrize("company,domain", GOLDEN)
def test_the_bridge_is_complete_or_it_is_not_a_bridge(company, domain):
    """§7. Every field, every time. A recommendation with no stopping
    condition is worse than no recommendation."""
    action = SR.compose(company=company, domain=domain).level6_action
    for field in ("causal_confidence", "what_is_known",
                  "what_remains_unknown", "why_it_matters", "action_now",
                  "minimum_viable_experiment", "kill_switch", "falsifier",
                  "voi_band"):
        assert getattr(action, field), (company, field)


@pytest.mark.parametrize("company,domain", GOLDEN)
def test_no_customer_facing_field_carries_a_refusal(company, domain):
    """A refusal may not reach the read by being copied out of the run.

    Measured: with the pattern library correctly gated, the run's own
    reasoning matched nothing -- and its "not enough to read a strategy from"
    sentence was carried into the bounded read's own headings, so slide 1
    read "Confidence: BOUNDED ... What is still open: what X has published is
    not enough to read a strategy from."
    """
    class _Refusing:
        headline = ("This run puts no decision forward: what it retrieved "
                    "did not carry enough to read one from.")
        mechanism = ""
        unsafe_because = (f"What {company} has published is not enough to "
                          f"read a strategy from.")
        limitation = ""
        options = ()
        recommended_next_move = ""

    read = SR.compose(company=company, domain=domain,
                      run_decision=_Refusing())
    surface = " ".join([
        read.identity, read.central_question, read.level5_decision.text,
        read.level6_action.what_is_known,
        read.level6_action.what_remains_unknown,
        read.level6_action.action_now])
    assert "not enough to read a strategy" not in surface.lower()
    assert "puts no decision forward" not in surface.lower()


def test_an_unclassified_company_keeps_the_decision_its_run_reached():
    """A missing manifest row costs the ECONOMICS, not the conclusion.

    An earlier version dropped a run's own decision -- options, mechanism and
    recommended move -- whenever the company was outside the validation
    manifest, and rendered "could not be classified" instead. That is the
    refusal wearing a different hat.
    """
    class _Decided:
        headline = "Invest ahead of demand, or wait for the signal."
        mechanism = ("the engagement teaches the workflow and the product "
                     "sells it without the engagement")
        unsafe_because = "the revenue split is not public"
        limitation = ""
        recommended_next_move = ("One check separates them: whether the "
                                 "attach rate rises with tenure.")
        options = ()

    read = SR.compose(company="Vantorix Systems", domain="vantorix.example",
                      run_decision=_Decided())
    assert read.puts_a_strategy_forward
    assert "attach rate rises with tenure" in read.level6_action.action_now


def test_nothing_at_all_is_the_only_state_with_no_strategy():
    """The ONE honest refusal: not classified AND the run concluded nothing."""
    read = SR.compose(company="Nonesuch Holdings", domain="nonesuch.example")
    assert read.standing == SR.READ_UNIDENTIFIED
    # ...and even that state is actionable rather than a dead end.
    assert read.level6_action is not None
    assert read.level6_action.minimum_viable_experiment


@pytest.mark.parametrize("company,domain", GOLDEN)
def test_the_read_never_invents_a_magnitude(company, domain):
    """§5. No market share, retention rate or revenue effect appears."""
    import re
    read = SR.compose(company=company, domain=domain)
    prose = " ".join(
        [read.identity, read.economic_role, read.strategic_position,
         read.level5_decision.text]
        + [s.text for s in read.what_matters_now]
        + [m.how_it_works for m in read.level3_mechanism])
    # A percentage or a currency figure would have to come from a source, and
    # nothing in this composer reads one.
    assert not re.search(r"\d+(?:\.\d+)?\s?%", prose), prose[:200]
    assert not re.search(r"[$€£]\s?\d", prose), prose[:200]


# ===========================================================================
# §10 — a reading that belongs to another kind of business may not fire
# ===========================================================================
def test_the_pattern_library_is_gated_by_business_model():
    """Cloudflare was told about take-or-pay terms and ageing lines."""
    software = {p.pattern_id for p in patterns_for("SUBSCRIPTION_SOFTWARE")}
    industrial = {p.pattern_id
                  for p in patterns_for("MANUFACTURE_AND_AFTERMARKET")}
    assert "capacity_ahead_of_demand" not in software
    assert "capacity_ahead_of_demand" in industrial
    # A miner does not have a system of record to sell.
    miner = {p.pattern_id for p in patterns_for("COMMODITY_PRODUCER")}
    assert "tool_to_system_of_record" not in miner
    assert software != industrial != miner


def test_an_unclassified_company_still_gets_the_whole_library():
    """Withholding readings from a company we could not classify trades a
    wrong answer for no answer -- the failure this cycle reopened."""
    assert len(patterns_for("")) == len(PATTERN_LIBRARY)
    assert len(patterns_for("UNKNOWN")) == len(PATTERN_LIBRARY)


def test_no_pattern_excludes_every_business_model():
    """A pattern that can never fire is a pattern that should be deleted."""
    for pattern in PATTERN_LIBRARY:
        assert len(set(pattern.excluded_model_classes)) < 9, pattern.pattern_id


# ===========================================================================
# §44 — the vintage wall
# ===========================================================================
def _timeline():
    filings = tuple(
        HR.Filing(form=form, date=_dt.date.fromisoformat(when),
                  url=f"https://sec.gov/{when}", title=f"SEC {form} ({when})")
        for form, when in (("10-K", "2022-02-01"), ("10-Q", "2022-05-01"),
                           ("10-K", "2023-02-01"), ("8-K", "2023-06-01"),
                           ("10-K", "2024-02-01")))
    selection = select(name="Cloudflare, Inc.", domain="cloudflare.com")
    return filings, HR.build(company="Cloudflare, Inc.", filings=filings,
                             profile=selection.profile, selection=selection)


def test_no_vintage_panel_mentions_a_date_after_its_own_cutoff():
    """§44. The one panel allowed past the wall is named, and it is one."""
    filings, timeline = _timeline()
    assert timeline.available
    for vintage in timeline.vintages:
        cutoff = _dt.date.fromisoformat(vintage.date)
        later = [f.iso for f in filings if f.date > cutoff]
        for panel in vintage.panels:
            if panel.after_the_wall:
                continue
            for iso in later:
                assert iso not in panel.body, (vintage.date, panel.key, iso)


def test_exactly_one_panel_is_allowed_past_the_wall():
    _filings, timeline = _timeline()
    for vintage in timeline.vintages:
        past = [p.key for p in vintage.panels if p.after_the_wall]
        assert past == ["after"], (vintage.date, past)


def test_a_descriptive_vintage_is_never_called_a_replay():
    """§45. The three states stay distinct."""
    _filings, timeline = _timeline()
    last = timeline.vintages[-1]
    assert last.state == HR.DESCRIPTIVE_HISTORY
    assert "Nothing here has been tested" in last.state_prose
    assert last.counterfactual.observed_outcome.startswith("Not testable")


def test_an_empty_timeline_explains_itself():
    timeline = HR.build(company="Acme", filings=())
    assert not timeline.available
    assert "not a statement about the company" in timeline.coverage_note


def test_ownership_reports_do_not_become_the_company_timeline():
    """Form 4 is about a person. Measured: 40 consecutive Cloudflare filings
    covered seven weeks and 23 were Forms 4 and 144."""
    payload = {"cik": "1", "filings": {"recent": {
        "form": ["4", "144", "10-K", "4", "SC 13G", "10-Q"],
        "filingDate": ["2026-01-01", "2026-01-02", "2026-02-01",
                       "2026-02-02", "2026-03-01", "2026-05-01"],
        "accessionNumber": ["a"] * 6, "primaryDocument": ["d.htm"] * 6}}}
    forms = [f.form for f in HR.filings_from_submissions(payload)]
    assert forms == ["10-K", "10-Q"]


# ===========================================================================
# §17/§18 — one story, in one order
# ===========================================================================
def test_the_flow_is_a_chain_and_reaches_every_step():
    reached, step = {flow.STEPS[0].key}, flow.STEPS[0]
    while flow.following(step.key) is not None:
        step = flow.following(step.key)
        reached.add(step.key)
    assert reached == {s.key for s in flow.STEPS}
    assert len(flow.STEPS) == 6


def test_a_primary_page_offers_one_way_forward_not_six():
    """§16/§18. The grid is the defect; a single Next is the fix."""
    for step in flow.STEPS:
        nav = flow.nav("r1", step.key)
        forward = flow.following(step.key)
        # Back and Next are the affordances. A jump to any OTHER step is the
        # grid coming back.
        back = flow.previous(step.key)
        allowed = {step.key,
                   forward.key if forward else "",
                   back.key if back else "",
                   # step 1's Back leaves the story, and the last step's
                   # forward link restarts it -- both point at step 1.
                   flow.STEPS[0].key}
        others = [s for s in flow.STEPS if s.key not in allowed]
        for other in others:
            assert f'href="/runs/r1{other.suffix}"' not in nav, (
                f"{step.key} offers a jump to {other.key}; the primary nav "
                f"is sequential")
        assert f"Step {step.number} of 6" in nav


def test_every_secondary_surface_is_still_reachable():
    """§19. Nothing was removed -- it moved."""
    drawer = flow.drawer("r1", tuple(flow.SECONDARY))
    for key in flow.SECONDARY:
        assert f"/runs/r1/{key}" in drawer, key


# ===========================================================================
# §59 — the taxonomy catches the defects that were live
# ===========================================================================
@pytest.mark.parametrize("text,code", [
    ("No strategic reading of Cloudflare, Inc. cleared the evidence bar, so "
     "none is asserted here.", "STRATEGIC_REFUSAL_COLLAPSE"),
    ("Cloudflare's mission is to help build a better Internet and serve "
     "every customer everywhere with the very best of what we do daily.",
     "WEBSITE_COPY_LEAK"),
    ("We have built a global network that delivers services to businesses "
     "of all sizes and in all…", "TRUNCATED_SENTENCE"),
    ("The bridge state is MARKET_BRIDGE_CURRENT for this company today.",
     "RAW_ENUM"),
    ("No competitor's own account was retrieved for this run at all.",
     "COMPETITOR_MISSING"),
    ("This carries zero risk for the company and its shareholders alike.",
     "FALSE_CONFIDENCE"),
])
def test_each_historical_defect_is_detected(text, code):
    found = {f.code for f in DT.scan(text, surface="intro",
                                     company="Cloudflare, Inc.",
                                     min_chars=0)}
    assert code in found, (code, sorted(found))


def test_a_clean_page_is_clean():
    """A detector that fires on correct prose is noise."""
    good = (
        "Cloudflare, Inc. is a software platform business that runs on "
        "recurring software subscription: revenue is contracted and renews, "
        "so the installed base carries next period's revenue before any new "
        "sale. The decision in front of management is what to charge, and "
        "for what. Move on pricing and packaging at a size that can be "
        "reversed inside one planning cycle, and instrument it so the result "
        "is readable before the next commitment.")
    findings = DT.scan(good, surface="intro", company="Cloudflare, Inc.",
                       model_class="SUBSCRIPTION_SOFTWARE", min_chars=0)
    assert not findings, [f.code for f in findings]


def test_a_software_company_described_in_industrial_terms_is_caught():
    text = ("Utilisation, order books and take-or-pay terms are not public, "
            "so the commitment cannot be sized from outside the company.")
    found = {f.code for f in DT.scan(text, surface="full",
                                     company="Cloudflare, Inc.",
                                     model_class="SUBSCRIPTION_SOFTWARE",
                                     min_chars=0)}
    assert "TEMPLATE_COLLAPSE" in found


# ===========================================================================
# §65/§67 — the correction loop adds nothing and needs no model
# ===========================================================================
def test_the_critic_never_adds_a_claim():
    """§67. Every repair either supplies a MISSING structural element or
    REMOVES something unsupported. None makes the product assert more."""
    read = SR.compose(company="Cloudflare, Inc.", domain="cloudflare.com")
    before = len(" ".join(
        [read.identity, read.economic_role, read.strategic_position]
        + [m.how_it_works for m in read.level3_mechanism]
        + [c.likely_response for c in read.level4_competition]))
    corrected = SC.correct(read)
    after = len(" ".join(
        [corrected.read.identity, corrected.read.economic_role,
         corrected.read.strategic_position]
        + [m.how_it_works for m in corrected.read.level3_mechanism]
        + [c.likely_response for c in corrected.read.level4_competition]))
    assert after <= before


def test_the_correction_loop_makes_no_model_call(monkeypatch):
    """§65. REQUIRED_ANTHROPIC_CALLS = 0, proven by making one impossible."""
    import sys
    import types

    exploding = types.ModuleType("anthropic")

    def _boom(*_a, **_k):
        raise AssertionError("the correction loop called a hosted model")

    exploding.Anthropic = _boom
    exploding.Client = _boom
    monkeypatch.setitem(sys.modules, "anthropic", exploding)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    read = SR.compose(company="Caterpillar Inc.", domain="caterpillar.com")
    corrected = SC.correct(read)
    assert corrected.read.puts_a_strategy_forward


def test_a_macro_channel_with_no_transmission_is_removed():
    """§11. A factor attached because it exists is noise wearing a chart."""
    read = SR.compose(company="Cloudflare, Inc.", domain="cloudflare.com")
    read = read.__class__(**{**read.as_dict_fields()}) if False else read
    import dataclasses
    polluted = dataclasses.replace(read, macro=(
        {"factor": "rates", "mechanism": "", "business_variable": "",
         "consequence": ""},))
    corrected = SC.correct(polluted)
    assert corrected.read.macro == ()
    assert any("macro" in r for r in corrected.repairs)


# ===========================================================================
# §15 — a rival must be a company a buyer could choose instead
# ===========================================================================
def test_a_programme_or_a_standard_is_never_a_competitor():
    """MEASURED LIVE on the deployed introduction, one line under the company
    name: "Its position is contested most directly by Authorization Management
    Program, Cloudflare Workers and FedRAMP." Two of those are fragments of a
    US government certification scheme and the third is Cloudflare's own
    product."""
    from intent_engine.external_intel.competitor_finder import candidate_names
    passage = (
        "We compete with Akamai Technologies and other vendors. Cloudflare "
        "Workers competes with serverless offerings. The Federal Risk and "
        "Authorization Management Program (FedRAMP) authorizes our service, "
        "and the General Services Administration lists us.")
    names = candidate_names(passage, subject="Cloudflare, Inc.")
    lowered = " ".join(names).lower()
    assert "fedramp" not in lowered
    assert "authorization management program" not in lowered
    assert "cloudflare" not in lowered, names
    assert any("Akamai" in n for n in names), names


def test_the_subject_is_never_its_own_rival_however_it_is_written():
    from intent_engine.external_intel.competitor_finder import candidate_names
    for subject, product in (("Cloudflare, Inc.", "Cloudflare Workers"),
                             ("Shopify Inc.", "Shopify Payments"),
                             ("Stripe, Inc.", "Stripe Terminal")):
        passage = f"We compete with Rivalcorp Holdings. {product} is ours."
        names = candidate_names(passage, subject=subject)
        assert product not in names, (subject, names)


def test_a_word_boundary_not_a_substring():
    """"alpha" inside "Alphabet Inc." must not refuse a real company."""
    from intent_engine.external_intel.competitor_finder import candidate_names
    names = candidate_names("We compete with Alphabet Inc. in search.",
                            subject="Alpha Industries")
    assert any("Alphabet" in n for n in names), names


@pytest.mark.parametrize("company,domain", GOLDEN)
def test_no_rival_on_the_read_is_the_company_itself(company, domain):
    read = SR.compose(company=company, domain=domain)
    head = company.split(",")[0].split(" Inc")[0].strip().lower()
    for rival in read.level4_competition:
        assert head not in rival.name.lower(), (company, rival.name)


def test_a_category_is_never_a_competitor():
    """Three consecutive live runs named something that is not a company.

    Run 1: "Authorization Management Program, Cloudflare Workers and
    FedRAMP".  Run 2, after the first repair: "Federal Risk, Intuitive User
    Experience and Online Platforms". Each was the first competitive
    statement a chief executive read.

    A multi-word span now needs POSITIVE evidence that it is an organisation:
    a legal form, or a trade word that is not preceded by ordinary English.
    That drops real single-word brands too, which is the trade this module
    documents and accepts -- a missed rival is a quiet omission and the read
    still shows classified peers, while a fabricated one sends someone to a
    board meeting worried about a company that does not exist.
    """
    from intent_engine.external_intel.competitor_finder import candidate_names
    passage = (
        "We compete with Akamai Technologies and Alphabet Inc. The Federal "
        "Risk and Authorization Management Program applies to us. Online "
        "Platforms and Intuitive User Experience are what buyers want. "
        "Cloudflare Workers is our own product.")
    names = candidate_names(passage, subject="Cloudflare, Inc.")
    assert "Akamai Technologies" in names, names
    for fabricated in ("Federal Risk", "Online Platforms",
                       "Intuitive User Experience", "Cloudflare Workers",
                       "Authorization Management Program"):
        assert fabricated not in names, (fabricated, names)


def test_a_real_firm_without_a_legal_form_survives():
    """The tightening must not cost a real company.

    "Booz Allen Hamilton" is three surnames and no corporate suffix, so a
    rule that demanded a legal form or a trade word dropped it. What
    separates it from "Intuitive User Experience" is that none of its tokens
    is ordinary English.
    """
    from intent_engine.external_intel.competitor_finder import candidate_names
    names = candidate_names(
        "Competitors include Databricks Inc, Snowflake Inc and consultancies "
        "such as Booz Allen Hamilton.", subject="Palantir Technologies")
    assert "Booz Allen Hamilton" in names, names


def test_a_name_never_spans_a_sentence_boundary():
    """`_NAME` allows "." inside a token so "Inc." survives; the cost was a
    span reaching across the full stop into the next sentence and producing a
    company called "Alphabet Inc. The Federal"."""
    from intent_engine.external_intel.competitor_finder import candidate_names
    names = candidate_names(
        "We compete with Alphabet Inc. The Federal Risk programme applies.",
        subject="Cloudflare, Inc.")
    assert "Alphabet Inc" in names, names
    assert not any("The Federal" in n for n in names), names
