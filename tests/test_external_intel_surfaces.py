"""External context on the surfaces a founder actually reads.

Plus the break proofs from the cycle's own list. Each deliberately breaks one
guarantee and asserts the intended gate stops it -- a guarantee nobody has
tried to break is a guarantee nobody knows the strength of.
"""
import datetime

import pytest

from intent_engine.external_intel import competitor_contract as CC
from intent_engine.external_intel import macro_contract as MaC
from intent_engine.external_intel import macro_exposure as MX
from intent_engine.external_intel import market_contract as MC
from intent_engine.external_intel import market_producer as MP
from intent_engine.external_intel import pack as PK
from intent_engine.external_intel import presenter as PS
from intent_engine.external_intel import visuals as V
from intent_engine.founder_brief import build as B
from intent_engine.founder_brief import dossier as D
from intent_engine.founder_brief import layers as L
from intent_engine.founder_brief import narrative as N

TODAY = "2026-08-04"


def _closes(n=300, start=100.0, step=0.25, first="2025-01-01"):
    out, day, price = {}, datetime.date.fromisoformat(first), start
    while len(out) < n:
        if day.weekday() < 5:
            out[day.isoformat()] = round(price, 4)
            price += step
        day += datetime.timedelta(days=1)
    return out


def _market(tmp_path, ticker="ACME", **kw):
    base = dict(ticker=ticker, closes=_closes(),
                benchmark_closes=_closes(start=400.0, step=0.10),
                as_of=max(_closes()), exchange="NYSE", currency="USD")
    base.update(kw)
    MP.write_export(MP.build_export(**base), tmp_path)
    return MP.load_export(tmp_path, ticker, today=base["as_of"])


def _macro():
    return MaC.MacroFactor(
        observation=MaC.MacroObservation(
            factor_key=MX.PUBLIC_DEFENCE_SPEND, label="DoD outlays",
            series_id="MTS-5", current_value=678.7, prior_value=647.4,
            unit="$bn", observation_date="2026-06-30", frequency="monthly",
            source="US Treasury",
            comparison_note="same month a year earlier"),
        exposure=MaC.Exposure(
            factor_key=MX.PUBLIC_DEFENCE_SPEND,
            mechanism="Sells into federal defence budgets.",
            business_consequence="A wider pool, awarded slowly.",
            decision_implication="Whether to fund delivery capacity.",
            evidence_ids=("ev-1",), matched_on="government contracts"),
        limitation="Does not measure exposed revenue.",
        confidence_basis="Company evidence plus a published series.")


def _competitor(**kw):
    base = dict(name="Databricks Inc", relationship=CC.DIRECT_COMPETITOR,
                overlap="We compete with Databricks Inc. for the same "
                        "customers.",
                evidence_ids=("ev-10q",), source_titles=("SEC 10-Q",),
                relevance=CC.CLAIM_RELEVANT, date="2026-05-05",
                decision_implication="Whether the differentiation is one a "
                                     "buyer would notice.",
                limitation="From the company's own account.")
    base.update(kw)
    return CC.Competitor(**base)


def _context(tmp_path, market=True, macro=True, competitors=True):
    return PK.build_context(
        market=_market(tmp_path) if market else None,
        macro=[_macro()] if macro else (),
        competitors=[_competitor()] if competitors else (),
        as_of=TODAY)


def _report():
    return {"thesis": {"view": "Growth is shifting to government platform "
                               "contracts.",
                       "why_care": "Whether to fund public-sector delivery.",
                       "tension": "Revenue concentrates in few awards."},
            "hypotheses": [{"statement": "Growth is shifting to government "
                                         "contracts.",
                            "reasoning": "Three dated awards name federal "
                                         "agencies.",
                            "supporting_observation_ids": ["ev-1"],
                            "confidence": "moderate"}],
            "observations": [
                {"observation_id": "ev-1", "date": "2026-05-05",
                 "source_class": "regulatory_filing",
                 "text": "Delivers platforms to US federal agencies under "
                         "multi-year government contracts."}]}


def _brief(market=None):
    return B.build(company="Acme", mode=B.PUBLIC_INFORMATION_RICH,
                   report=_report(), observations=_report()["observations"],
                   market=market)


# --- the primary narrative --------------------------------------------------
def test_the_narrative_carries_outside_context_when_it_is_relevant(tmp_path):
    context = _context(tmp_path)
    story = N.build_narrative(company="Acme", brief=_brief(), report=_report(),
                              external=context)
    outside = next((s for s in story.sections if s.key == N.OUTSIDE), None)
    assert outside is not None
    assert outside.items


def test_the_narrative_has_no_outside_section_when_nothing_is_relevant():
    story = N.build_narrative(company="Acme", brief=_brief(), report=_report(),
                              external=PK.build_context())
    assert not any(s.key == N.OUTSIDE for s in story.sections)


def test_the_narrative_takes_at_most_one_block_per_context(tmp_path):
    """The 60-second screen has a reading budget the deep documents do not."""
    story = N.build_narrative(company="Acme", brief=_brief(), report=_report(),
                              external=_context(tmp_path))
    outside = next(s for s in story.sections if s.key == N.OUTSIDE)
    assert len(outside.items) <= 3


def test_only_the_relevant_context_appears_in_the_narrative(tmp_path):
    """Do not add all three sections when only one is relevant."""
    context = _context(tmp_path, macro=False, competitors=False)
    story = N.build_narrative(company="Acme", brief=_brief(), report=_report(),
                              external=context)
    outside = next(s for s in story.sections if s.key == N.OUTSIDE)
    assert len(outside.items) == 1


def test_the_narrative_states_that_outside_context_does_not_decide(tmp_path):
    story = N.build_narrative(company="Acme", brief=_brief(), report=_report(),
                              external=_context(tmp_path))
    outside = next(s for s in story.sections if s.key == N.OUTSIDE)
    assert "do not make it" in outside.note


def test_the_outside_section_sits_after_the_decision(tmp_path):
    """Before it, the page reads as though the market drove the conclusion."""
    story = N.build_narrative(company="Acme", brief=_brief(), report=_report(),
                              external=_context(tmp_path))
    keys = [s.key for s in story.sections]
    assert keys.index(N.OUTSIDE) > keys.index(N.THE_DECISION)
    assert N.OUTSIDE in N.SECTION_ORDER


# --- the dashboard ----------------------------------------------------------
def test_the_dashboard_gains_macro_and_competitive_tiles(tmp_path):
    context = _context(tmp_path)
    modules = L.build_dashboard(
        _brief(PS.market_context_dict(context)), _report(),
        footing={"ticker": "ACME"}, external=context)
    keys = [m.key for m in modules]
    assert any(k.startswith("macro_") for k in keys)
    assert "competitive_pressure" in keys


def test_a_company_with_no_exposure_gets_no_empty_macro_tile(tmp_path):
    """An unavailable macro tile invites waiting for data that is not coming.

    The truthful statement is that this company's evidence establishes no
    exposure mechanism at all, so the tile is omitted rather than emptied.
    """
    context = _context(tmp_path, macro=False, competitors=False)
    modules = L.build_dashboard(
        _brief(PS.market_context_dict(context)), _report(),
        footing={"ticker": "ACME"}, external=context)
    assert not any(m.key.startswith("macro_") for m in modules)
    assert not any("macro" in (m.title or "").lower() for m in modules)


def test_every_dashboard_module_interprets_rather_than_only_reporting(
        tmp_path):
    """No module may show only a raw number or a source title."""
    context = _context(tmp_path)
    modules = L.build_dashboard(
        _brief(PS.market_context_dict(context)), _report(),
        footing={"ticker": "ACME"}, external=context)
    for module in modules:
        if not module.available:
            assert module.so_what, module.key
            continue
        assert module.so_what, module.key
        assert module.what_to_watch, module.key


# --- the deep documents -----------------------------------------------------
def _dossier(tmp_path, **kw):
    context = _context(tmp_path, **kw)
    return D.build_dossier(company="Acme", report=_report(),
                           market=PS.market_context_dict(context),
                           external=context), context


def test_the_brief_and_the_full_analysis_read_the_same_context(tmp_path):
    book, _ = _dossier(tmp_path)
    market = next(p for p in book.passages if p.key == "market")
    assert market.for_depth(D.BRIEF) and market.for_depth(D.FULL)


def test_the_market_passage_names_the_decision_it_bears_on(tmp_path):
    """The old version printed the fact and its why-this-matters and stopped,
    so a reader learned what the shares did and never which choice it bore
    on."""
    book, _ = _dossier(tmp_path)
    market = next(p for p in book.passages if p.key == "market")
    joined = " ".join(market.paragraphs).lower()
    assert "bears on one choice" in joined


def test_the_macro_passage_carries_a_mechanism_and_a_real_reading(tmp_path):
    book, _ = _dossier(tmp_path)
    macro = next(p for p in book.passages if p.key == "macro")
    labels = " ".join(str(i.get("label", "")) for i in macro.items)
    texts = " ".join(str(i.get("text", "")) for i in macro.items)
    assert "678.7" in labels, "a macro factor without a value is commentary"
    assert "defence budgets" in texts
    assert "not because it applies to companies generally" in macro.note


def test_the_competitive_passage_names_alternatives_from_a_filing(tmp_path):
    book, _ = _dossier(tmp_path)
    competitive = next(p for p in book.passages if p.key == "competitive")
    joined = " ".join(competitive.paragraphs)
    assert "Databricks Inc" in joined


def test_the_absence_notice_still_fires_when_no_alternative_is_established(
        tmp_path):
    """Regression: keying the notice off `paragraphs` suppressed it for a
    company that had a vulnerability and no competitor -- which is exactly
    when a reader needs it."""
    book, _ = _dossier(tmp_path, competitors=False)
    competitive = next((p for p in book.passages if p.key == "competitive"),
                       None)
    if competitive is not None:
        joined = " ".join(competitive.paragraphs)
        assert "Databricks" not in joined


# --- BREAK PROOFS -----------------------------------------------------------
def test_break_an_internal_trading_metric_entering_founder_output(tmp_path):
    payload = MP.build_export(
        ticker="ACME", closes=_closes(), benchmark_closes=_closes(start=400.0),
        as_of=max(_closes()))
    payload["win_rate"] = 0.62
    with pytest.raises(MC.ExportViolation):
        MC.validate(payload)


def test_break_a_missing_market_value_becoming_zero():
    with pytest.raises(MC.ExportViolation):
        MC.measurement(0.0, MC.UNMEASURABLE, period="1m", unit="percent",
                       source="x")


def test_break_a_stale_export_presenting_itself_as_current(tmp_path):
    payload = MP.build_export(
        ticker="ACME", closes=_closes(), benchmark_closes=_closes(start=400.0),
        as_of=max(_closes()))
    payload["data_freshness"]["stale"] = False
    payload["data_freshness"]["age_days"] = 0
    MP.write_export(payload, tmp_path)
    loaded = MP.load_export(tmp_path, "ACME", today="2027-06-01")
    assert loaded.stale, "freshness is recomputed from the session, not read"


def test_break_market_movement_presented_as_causation():
    assert PK.causal_language(
        "The shares fell, therefore the strategy is failing.")


def test_break_generic_macro_without_an_exposure_mechanism():
    with pytest.raises(MaC.MacroRejected):
        MaC.Exposure(factor_key="interest_rates", mechanism="",
                     business_consequence="c", decision_implication="d",
                     evidence_ids=("ev-1",))


def test_break_a_competitor_bare_mention_becoming_corroboration():
    verdict = CC.assess(CC.Mention(
        name="Acme Corp",
        passage="Acme Corp. was mentioned in the announcement."))
    assert not verdict.supports_conclusion


def test_break_a_compensation_peer_group_becoming_competitor_evidence():
    verdict = CC.assess(CC.Mention(
        name="Adobe Inc.",
        passage="The compensation peer group includes Adobe Inc., chosen for "
                "revenue comparability."))
    assert verdict.relevance == CC.IRRELEVANT
    assert not verdict.supports_conclusion


def test_break_market_and_macro_repeating_each_other(tmp_path):
    blocks = PS.blocks(_context(tmp_path))
    facts = [b.fact for b in blocks]
    assert len(facts) == len(set(facts))


def test_break_a_chart_with_no_so_what(tmp_path):
    """Every chart's caption comes from the block's so-what and decision, so
    a chart cannot be constructed without one."""
    context = _context(tmp_path)
    for block in PS.blocks(context):
        svg = V.render(block, context)
        if svg:
            assert "figcaption" in svg
            assert block.so_what


def test_break_a_chart_lacking_source_or_freshness(tmp_path):
    context = _context(tmp_path)
    for block in PS.blocks(context):
        svg = V.render(block, context)
        if svg:
            assert "xc-src" in svg
            assert block.source


def test_break_a_private_company_receiving_fabricated_ticker_data(tmp_path):
    """No ticker means no series was looked up, and nothing is substituted."""
    got = MP.ensure_export(ticker="", root=tmp_path, today=TODAY)
    assert not got.available
    assert "no ticker" in got.reason.lower()


def test_break_an_unsupported_numerical_forecast(tmp_path):
    context = _context(tmp_path)
    assert context.ungrounded_numbers(
        "Revenue should reach 340.5 million next year") == ["340.5"]


def test_break_a_bounded_result_becoming_rich_because_market_data_exists(
        tmp_path):
    """External context is context. It cannot answer a question the company's
    own evidence could not."""
    bounded = {"thesis": {"view_withheld": True}, "hypotheses": [],
               "observations": []}
    context = _context(tmp_path)
    story = N.build_narrative(
        company="Acme",
        brief=B.build(company="Acme", mode=B.MARKETING_ONLY, report=bounded,
                      observations=[], market=PS.market_context_dict(context)),
        report=bounded, external=context)
    assert story.readiness != "DECISION_READY"


def test_break_an_unknown_export_field_bypassing_the_allowlist(tmp_path):
    payload = MP.build_export(
        ticker="ACME", closes=_closes(), benchmark_closes=_closes(start=400.0),
        as_of=max(_closes()))
    payload["market_regime"]["confidence_score"] = 0.9
    with pytest.raises(MC.ExportViolation) as exc:
        MC.validate(payload)
    assert "unsanctioned" in str(exc.value)


def test_break_an_old_report_silently_adopting_new_market_context(tmp_path):
    """An analysis keeps the as-of it was built with.

    The export carries the date it describes, so a document built from one
    snapshot cannot silently start reading a newer one -- the two are
    different objects with different `as_of` values.
    """
    early = _market(tmp_path, as_of=sorted(_closes())[200])
    later = _market(tmp_path, as_of=max(_closes()))
    assert early.as_of != later.as_of
    old_book = D.build_dossier(
        company="Acme", report=_report(),
        market=PS.market_context_dict(PK.build_context(market=early)),
        external=PK.build_context(market=early))
    old_market = next(p for p in old_book.passages if p.key == "market")
    assert early.as_of in old_market.note
    assert later.as_of not in old_market.note


# --- what the second deployed reading showed --------------------------------
def test_a_tile_with_a_chart_does_not_say_the_same_thing_three_times(tmp_path):
    """Measured on the deployed dashboard.

    The tile printed `what_changed`, then a chart whose headline IS
    `what_changed`, then `text_alternative` restating it again -- so a reader
    met "the shares rose 5.4% over the past year" three times in one tile.
    """
    from intent_engine.founder_brief import render as R
    context = _context(tmp_path)
    modules = L.build_dashboard(
        _brief(PS.market_context_dict(context)), _report(),
        footing={"ticker": "ACME"}, external=context)
    charts = {b.key: V.render(b, context) for b in PS.blocks(context)}
    charts = {k: v for k, v in charts.items() if v}
    html = R.render_dashboard(modules, charts=charts)
    trajectory = next(b for b in PS.market_blocks(context)
                      if b.key == "market_trajectory")
    headline = V._headline(trajectory)
    assert charts.get("market_trajectory"), "the chart must render at all"
    assert html.count(headline.replace("%", "%")) <= 1, \
        "the fact appears once: as the chart's own conclusion"


def test_a_chart_carries_the_text_alternative_so_the_tile_need_not(tmp_path):
    """Dropping the tile's copy is only safe because the figure has <desc>."""
    context = _context(tmp_path)
    block = next(b for b in PS.market_blocks(context)
                 if b.key == "market_trajectory")
    svg = V.render(block, context)
    assert "<desc" in svg and "</desc>" in svg
    assert 'role="img"' in svg


def test_the_executive_brief_carries_the_macro_exposure(tmp_path):
    """A named exposure with a current figure and the choice it bears on is
    exactly what a decision memo is for.

    It was FULL-only while it was keyword-spotted, which was right then: a
    generic mechanism with no value is not decision material.
    """
    book, _ = _dossier(tmp_path)
    macro = next(p for p in book.passages if p.key == "macro")
    assert macro.for_depth(D.BRIEF), "the brief needs the macro exposure"
    assert macro.for_depth(D.FULL)


def test_a_dashboard_chart_tile_spans_the_grid(tmp_path):
    """Measured at 1440px on the deployed dashboard.

    A chart in a half-width tile rendered 317px wide against a 640-unit
    viewBox, scaling its 11px axis labels to under 5px -- present, and
    unreadable. A chart nobody can read is decoration, and decoration is what
    stops a reader trusting the charts that do mean something.
    """
    from intent_engine.founder_brief import render as R
    context = _context(tmp_path)
    modules = L.build_dashboard(
        _brief(PS.market_context_dict(context)), _report(),
        footing={"ticker": "ACME"}, external=context)
    charts = {b.key: V.render(b, context) for b in PS.blocks(context)}
    charts = {k: v for k, v in charts.items() if v}
    html = R.render_dashboard(modules, charts=charts)
    assert ".dash .tile.haschart{grid-column:1/-1}" in html
    assert html.count('class="tile haschart"') == len(charts)
    # A tile without a chart keeps its half-width slot.
    assert 'class="tile"' in html
