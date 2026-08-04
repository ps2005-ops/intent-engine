"""The bridge: pack, graph projection, presenter and charts.

MARKET LEARNING → SANITIZED EXPORT → GRAPH PROJECTION → REASONING → SURFACES

Most of these assert a REFUSAL: that a number nobody published cannot appear,
that a price fall cannot become a verdict on the strategy, that a chart with
too few points is not drawn, and that rich market data cannot make a bounded
company look answered.
"""
import datetime

import pytest

from intent_engine.business_graph.model import BusinessGraph
from intent_engine.external_intel import competitor_contract as CC
from intent_engine.external_intel import macro_contract as MaC
from intent_engine.external_intel import macro_exposure as MX
from intent_engine.external_intel import market_producer as MP
from intent_engine.external_intel import pack as PK
from intent_engine.external_intel import presenter as PS
from intent_engine.external_intel import projection as PJ
from intent_engine.external_intel import visuals as V

TODAY = "2026-08-04"


def _closes(n=300, start=100.0, step=0.25, first="2025-01-01"):
    out, day, price = {}, datetime.date.fromisoformat(first), start
    while len(out) < n:
        if day.weekday() < 5:
            out[day.isoformat()] = round(price, 4)
            price += step
        day += datetime.timedelta(days=1)
    return out


def _market(tmp_path, **kw):
    base = dict(ticker="ACME", closes=_closes(),
                benchmark_closes=_closes(start=400.0, step=0.10),
                as_of=max(_closes()), exchange="NYSE", currency="USD")
    base.update(kw)
    MP.write_export(MP.build_export(**base), tmp_path)
    return MP.load_export(tmp_path, base["ticker"], today=base["as_of"])


def _macro():
    observation = MaC.MacroObservation(
        factor_key=MX.PUBLIC_DEFENCE_SPEND, label="DoD outlays",
        series_id="MTS-5", current_value=678.7, prior_value=647.4,
        unit="$bn", observation_date="2026-06-30", frequency="monthly",
        source="US Treasury", comparison_note="same month a year earlier")
    exposure = MaC.Exposure(
        factor_key=MX.PUBLIC_DEFENCE_SPEND,
        mechanism="Sells into federal defence budgets.",
        business_consequence="A wider pool, awarded slowly.",
        decision_implication="Whether to fund delivery capacity.",
        evidence_ids=("ev-1",), matched_on="government contracts")
    return MaC.MacroFactor(observation=observation, exposure=exposure,
                           limitation="Does not measure exposed revenue.",
                           confidence_basis="Company evidence plus a series.")


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


def _full(tmp_path):
    return PK.build_context(market=_market(tmp_path), macro=[_macro()],
                            competitors=[_competitor()], as_of=TODAY)


# --- relevance gating -------------------------------------------------------
def test_all_three_sections_appear_when_all_three_have_something(tmp_path):
    assert _full(tmp_path).relevant_sections() == ["market", "macro",
                                                   "competitive"]


def test_a_context_with_nothing_renders_no_sections():
    empty = PK.build_context()
    assert empty.relevant_sections() == []
    assert PS.blocks(empty) == []


def test_only_the_contexts_with_data_appear(tmp_path):
    """Do not add all three sections when only one is relevant."""
    only_market = PK.build_context(market=_market(tmp_path), as_of=TODAY)
    assert only_market.relevant_sections() == ["market"]
    assert all(b.context == "market" for b in PS.blocks(only_market))


def test_a_competitor_that_only_frames_the_market_earns_no_section():
    framing = _competitor(relevance=CC.COMPETITIVE_CONTEXT)
    context = PK.build_context(competitors=[framing], as_of=TODAY)
    assert not context.has_competitors
    assert PS.competitor_blocks(context) == []


def test_the_narrative_budget_takes_at_most_one_block_per_context(tmp_path):
    leading = PS.leading_blocks(_full(tmp_path))
    assert len(leading) == len({b.context for b in leading})


# --- numeric grounding ------------------------------------------------------
def test_a_number_no_source_published_is_rejected(tmp_path):
    context = _full(tmp_path)
    assert context.ungrounded_numbers("Revenue will grow 47.3% next year") \
        == ["47.3"]


def test_a_published_number_passes(tmp_path):
    context = _full(tmp_path)
    value = context.market.payload["price_periods"]["1m"]["value"]
    assert context.ungrounded_numbers(f"The shares moved {value}%") == []


def test_years_and_small_counts_are_not_treated_as_market_claims(tmp_path):
    """Flagging "three of four announcements" would train a reader to ignore
    this gate."""
    context = _full(tmp_path)
    assert context.ungrounded_numbers(
        "Three of four dated announcements in the 2026 filing name "
        "enterprise buyers.") == []


def test_every_number_in_generated_blocks_is_grounded(tmp_path):
    """The gate applied to the product's own prose, not just to a fixture."""
    context = _full(tmp_path)
    for block in PS.blocks(context):
        text = " ".join([block.fact, block.so_what, block.decision,
                         block.limitation, block.text_alternative])
        assert context.ungrounded_numbers(text) == [], block.key


# --- causation --------------------------------------------------------------
@pytest.mark.parametrize("sentence", [
    "The shares fell, therefore the strategy is failing.",
    "Because the shares fell, the plan is not working.",
    "The strategy is failing as shown by the share price.",
])
def test_market_movement_presented_as_causation_is_caught(sentence):
    assert PK.causal_language(sentence)


def test_the_products_own_market_prose_is_not_causal(tmp_path):
    for block in PS.market_blocks(_full(tmp_path)):
        text = " ".join([block.fact, block.so_what, block.decision,
                         block.limitation])
        assert PK.causal_language(text) == [], block.key


def test_the_market_block_states_the_non_causal_frame(tmp_path):
    blocks = PS.market_blocks(_full(tmp_path))
    assert any(PK.NON_CAUSAL_FRAME in b.so_what for b in blocks)


# --- external context never overrides company evidence ----------------------
def test_rich_market_data_does_not_change_readiness(tmp_path):
    """A bounded company stays bounded however good the market data is.

    The failure guarded: a company whose evidence could not support a
    conclusion suddenly reading as answered because its ticker resolved.
    """
    context = _full(tmp_path)
    assert not hasattr(context, "readiness")
    assert not any("DECISION_READY" in str(b.as_dict())
                   for b in PS.blocks(context))


def test_the_reasoning_pack_labels_every_block_with_its_role(tmp_path):
    pack = PK.reasoning_pack(_full(tmp_path))
    assert pack["blocks"]
    for block in pack["blocks"]:
        assert block["role"], block["context"]
        assert block["facts"]
    assert "never overrides" in " ".join(pack["rules"])


def test_the_reasoning_pack_carries_freshness_and_limitations(tmp_path):
    for block in PK.reasoning_pack(_full(tmp_path))["blocks"]:
        assert block["limitations"], block["context"]
        assert block["source"], block["context"]


# --- graph projection -------------------------------------------------------
def test_the_projection_builds_a_valid_graph(tmp_path):
    nodes, edges = PJ.project(_full(tmp_path), company="Acme")
    graph = BusinessGraph(nodes, edges)
    assert len(list(graph.nodes)) == len(nodes)


def test_every_projected_node_carries_provenance_and_its_role(tmp_path):
    nodes, _ = PJ.project(_full(tmp_path), company="Acme")
    for node in nodes:
        assert node.source, node.label
        assert node.attrs.get("role"), node.label
    context_nodes = [n for n in nodes
                     if n.attrs["role"] != "SUBJECT_COMPANY"]
    assert all(n.attrs.get("non_predictive") for n in context_nodes)
    assert all(n.attrs.get("subject_company") == "Acme"
               for n in context_nodes)


def test_reprojecting_unchanged_context_creates_no_duplicates(tmp_path):
    """Ids are derived from content, so this is true by construction."""
    context = _full(tmp_path)
    a_nodes, a_edges = PJ.project(context, company="Acme")
    b_nodes, b_edges = PJ.project(context, company="Acme")
    assert [n.node_id for n in a_nodes] == [n.node_id for n in b_nodes]
    graph = BusinessGraph(a_nodes + b_nodes, a_edges + b_edges)
    assert len(list(graph.nodes)) == len(a_nodes)


def test_the_macro_chain_reaches_a_decision(tmp_path):
    """MACRO_FACTOR -> COMPANY, and EXPOSURE_MECHANISM -> DECISION."""
    nodes, edges = PJ.project(_full(tmp_path), company="Acme")
    roles = {n.node_id: n.attrs["role"] for n in nodes}
    assert PJ.MACRO_FACTOR in roles.values()
    assert PJ.EXPOSURE_MECHANISM in roles.values()
    mechanism = next(n for n in nodes
                     if n.attrs["role"] == PJ.EXPOSURE_MECHANISM)
    assert any(e.src == mechanism.node_id
               and roles.get(e.dst) == "DECISION" for e in edges)


def test_only_corroborating_competitors_are_projected(tmp_path):
    context = PK.build_context(
        competitors=[_competitor(),
                     _competitor(name="Framing Co",
                                 relevance=CC.COMPETITIVE_CONTEXT)],
        as_of=TODAY)
    nodes, _ = PJ.project(context, company="Acme")
    labels = [n.label for n in nodes]
    assert "Databricks Inc" in labels
    assert "Framing Co" not in labels


def test_the_projection_can_attach_to_an_existing_company_node(tmp_path):
    """It must not own a second copy of the company."""
    nodes, _ = PJ.project(_full(tmp_path), company="Acme",
                          company_node_id="co-1")
    assert all(n.attrs.get("role") != "SUBJECT_COMPANY" for n in nodes)


# --- presenter --------------------------------------------------------------
def test_every_block_answers_the_four_questions(tmp_path):
    """What is the fact, so what, which decision, what is the limitation."""
    for block in PS.blocks(_full(tmp_path)):
        assert block.fact, block.key
        assert block.so_what, block.key
        assert block.decision, block.key
        assert block.limitation, block.key
        assert block.source, block.key


def test_no_block_says_merely_monitor_this(tmp_path):
    for block in PS.blocks(_full(tmp_path)):
        assert not block.decision.lower().startswith(("monitor", "watch ",
                                                      "keep an eye"))


def test_market_and_macro_do_not_repeat_the_same_statement(tmp_path):
    """"Market and macro sections repeat each other" is its own break proof."""
    blocks = PS.blocks(_full(tmp_path))
    facts = [b.fact for b in blocks]
    assert len(facts) == len(set(facts))
    market = " ".join(b.fact for b in blocks if b.context == PK.MARKET)
    macro = " ".join(b.fact for b in blocks if b.context == PK.MACRO)
    overlap = set(market.lower().split()) & set(macro.lower().split())
    # Function words overlap; whole claims must not.
    assert not any(len(w) > 12 for w in overlap)


def test_an_absent_market_yields_no_market_block():
    context = PK.build_context(macro=[_macro()], as_of=TODAY)
    assert PS.market_blocks(context) == []
    assert PS.blocks(context)


def test_a_stale_market_says_so_in_words_a_reader_can_judge(tmp_path):
    payload = MP.build_export(
        ticker="ACME", closes=_closes(), benchmark_closes=_closes(start=400.0),
        as_of=max(_closes()))
    MP.write_export(payload, tmp_path)
    stale = MP.load_export(tmp_path, "ACME", today="2027-01-01")
    context = PK.build_context(market=stale, as_of="2027-01-01")
    block = PS.market_blocks(context)[0]
    assert "older than one trading week" in block.freshness


# --- charts -----------------------------------------------------------------
def test_a_chart_is_not_drawn_below_the_observation_floor(tmp_path):
    """Three points joined by a line read as a trend. They are not one."""
    context = PK.build_context(
        market=_market(tmp_path, closes=_closes(n=34),
                       benchmark_closes=_closes(n=34, start=400.0),
                       as_of=max(_closes(n=34))), as_of=TODAY)
    payload = context.market.payload
    assert V.market_trajectory(
        payload, headline="h", so_what="s", decision="d", source="src",
        freshness="f", alt="a") == "" or len(
            (payload.get("series") or {}).get("dates", [])) >= V.MIN_POINTS


def test_every_rendered_chart_carries_its_conclusion_and_source(tmp_path):
    context = _full(tmp_path)
    drawn = 0
    for block in PS.blocks(context):
        svg = V.render(block, context)
        if not svg:
            continue
        drawn += 1
        assert "<title" in svg and "<desc" in svg, block.key
        assert 'role="img"' in svg, block.key
        assert "xc-hd" in svg, f"{block.key} has no conclusion headline"
        assert "figcaption" in svg, f"{block.key} has no so-what"
        assert block.source.split(" (")[0][:20] in svg, \
            f"{block.key} has no source"
    assert drawn >= 2, "at least two decision-useful visuals must render"


def test_a_chart_never_ships_without_a_text_alternative(tmp_path):
    context = _full(tmp_path)
    for block in PS.blocks(context):
        if V.render(block, context):
            assert block.text_alternative or block.fact


def test_the_chart_headline_states_a_conclusion_not_a_topic(tmp_path):
    """"PLTR vs SPY" tells a reader what they are looking at, which they can
    already see."""
    block = PS.market_blocks(_full(tmp_path))[0]
    headline = V._headline(block)
    assert headline.startswith("The shares")
    assert block.title not in headline


def test_axis_ticks_come_from_the_data_not_from_a_default(tmp_path):
    payload = _full(tmp_path).market.payload
    svg = V.market_trajectory(payload, headline="h", so_what="s",
                              decision="d", source="src", freshness="f",
                              alt="a")
    series = payload["series"]
    lo = min(min(series["company_indexed"]), min(series["benchmark_indexed"]))
    hi = max(max(series["company_indexed"]), max(series["benchmark_indexed"]))
    # Every printed tick must lie within the padded range of real values.
    import re
    ticks = [float(t) for t in re.findall(
        r'text-anchor="end">(-?\d+)</text>', svg)]
    assert ticks
    pad = (hi - lo) * 0.09 + 1
    assert all(lo - pad <= t <= hi + pad for t in ticks)


def test_the_svg_scales_rather_than_forcing_a_horizontal_scroll(tmp_path):
    payload = _full(tmp_path).market.payload
    svg = V.market_trajectory(payload, headline="h", so_what="s",
                              decision="d", source="src", freshness="f",
                              alt="a")
    assert "viewBox" in svg
    assert "width=" not in svg.split("<svg")[1].split(">")[0]


def test_a_single_competitor_draws_no_positioning_chart():
    """One bar is not a comparison."""
    assert V.competitor_positioning(
        [{"name": "Solo", "relationship_meaning": "x"}], headline="h",
        so_what="s", decision="d", source="src", freshness="f", alt="a") == ""
