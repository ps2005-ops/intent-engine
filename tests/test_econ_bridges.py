"""The two crossings: market -> core -> founder, and company -> core.

These are the tests that would have caught the defect this whole programme is
about -- two products with excellent evidence each, and nothing crossing.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from intent_engine.econ import state as ES
from intent_engine.econ import store as EST
from intent_engine.econ import vocabulary as V
from intent_engine.external_intel import econ_context as EC
from intent_engine.external_intel import econ_evidence as EE
from intent_engine.market import econ_bridge as MB
from intent_engine.market import macro_state as MS


def an_observation(**kw):
    base = dict(state_kind=MS.POLICY_RATE, series_id="POLICY",
                label="policy rate", value=4.25, unit="percent",
                standing=MS.OBSERVED, area=MS.US,
                reference_period="2026-06-30", published_at="2026-07-15",
                retrieved_at="2026-08-08", source="central bank")
    base.update(kw)
    return MS.MacroObservation(**base)


# --- market -> core ---------------------------------------------------------
def test_availability_is_the_publication_date_not_the_period_or_the_read():
    node = MB.node_from_observation(an_observation())
    assert node.occurred_at == "2026-06-30", "the period it describes"
    assert node.available_at == "2026-07-15", (
        "a June figure published in July was knowable in July; using the "
        "period would invent two weeks of foresight and using the retrieval "
        "date would destroy a month of it")
    assert node.retrieved_at == "2026-08-08"


def test_the_ordering_invariant_is_enforced_upstream_not_duplicated_here():
    """The bridge relies on `macro_state`, and this asserts that it may.

    A defensive re-check in the bridge was written first and removed: it was
    unreachable, and dead code that reads as protection leaves the next
    reader unable to tell which guard is doing the work.
    """
    with pytest.raises(MS.MacroRejected, match="had not finished"):
        an_observation(reference_period="2026-07-30",
                       published_at="2026-06-15")


class _FutureKind:
    """A duck-typed observation carrying a state kind the map lacks.

    `MacroObservation` refuses an unknown kind outright, so this case can
    only arise the day `macro_state` gains a kind and `KIND_MAP` has not
    caught up -- which is exactly the case that must not silently drop data.
    """
    state_kind = "SOMETHING_NEW"
    series_id = "X"
    label = "a new condition"
    value = 1.0
    unit = "percent"
    standing = MS.OBSERVED
    area = MS.US
    reference_period = "2026-06-30"
    published_at = "2026-07-15"
    retrieved_at = "2026-08-08"
    source = "a publisher"
    publication_basis = MS.PUBLISHER


def test_an_unmapped_kind_does_not_cross_and_is_named():
    report = MB.publish_state(observations=[_FutureKind()],
                              as_of="2026-08-24")
    assert report["nodes_published"] == 0
    assert report["unmapped_kinds"] == {"SOMETHING_NEW": 1}, (
        "a state kind the bridge does not map was dropped without being "
        "reported; a new series would become a silent omission rather than "
        "a piece of work")


def _belief_row(belief_id="bel_1", **kw):
    base = dict(record="belief", belief_id=belief_id,
                proposition="asml is seeing demand strengthen rather than "
                            "plateau",
                subject="asml", posterior_probability=0.586,
                last_updated="2026-08-01", limitations=["one source"],
                supporting_evidence_ids=["ev_1"])
    base.update(kw)
    return base


def _expectation_row(hypothesis_id="bel_1", metric="demand_strengthening",
                     **kw):
    base = dict(record="expectation", expectation_id="exp_1",
                hypothesis_id=hypothesis_id, subject="asml", metric=metric,
                expected_event="the next reported revenue or guidance figure",
                falsifier="revenue or guidance falls in the next period",
                preregistered_at="2026-08-01",
                evaluation_window_ends="2027-08-01")
    base.update(kw)
    return base


def test_a_belief_is_joined_to_its_expectation_and_its_causal_family():
    """THE JOIN THE FIRST LIVE CYCLE EXPOSED.

    The bridge originally read `expected_observations`, `falsifier`,
    `mechanism` and `probability` off the belief record. `StrategicBelief`
    has none of those four -- its probability is `posterior_probability` and
    the rest live on the expectation joined by `hypothesis_id`, whose
    `metric` names the causal family that states the mechanism. Every one of
    151 real beliefs was refused, and the cycle report announced that the
    market engine's beliefs state no observable. They state one.
    """
    beliefs, report = MB.beliefs_from_ledger(
        [_belief_row(), _expectation_row()], at="2026-08-24")
    assert report["offered"] == 1
    assert len(beliefs) == 1
    got = beliefs[0]
    assert got.probability == 0.586, (
        "the probability came from `posterior_probability`, not a default")
    assert got.falsifier.startswith("revenue or guidance falls")
    assert got.expected_observations == (
        "the next reported revenue or guidance figure",)
    assert got.mechanism, "no mechanism was recovered from the causal family"
    assert "next reported period" in got.mechanism


def test_a_belief_whose_family_has_no_recorded_mechanism_is_refused_by_name():
    """Refused, and the FAMILY is named -- because that is a work list.

    Roughly twenty families receive evidence and four carry a recorded
    mechanism. A belief in one of the other sixteen has a proposition, a
    probability, an expectation and a falsifier, and no stated account of why
    the cause should produce the effect. Composing one here is exactly what
    the shared contract exists to prevent.
    """
    beliefs, report = MB.beliefs_from_ledger(
        [_belief_row(), _expectation_row(metric="procurement_momentum")],
        at="2026-08-24")
    assert beliefs == []
    assert report["refused_no_recorded_mechanism"] == {
        "procurement_momentum": 1}


def test_a_belief_with_no_expectation_at_all_is_refused_separately():
    beliefs, report = MB.beliefs_from_ledger([_belief_row()], at="2026-08-24")
    assert beliefs == []
    assert report["refused_no_expectation"] == 1
    assert report["refused_no_recorded_mechanism"] == {}


def test_the_two_refusal_reasons_are_never_merged():
    """They are different pieces of work and must stay countable apart."""
    rows = [_belief_row("bel_1"), _expectation_row("bel_1"),
            _belief_row("bel_2"), _expectation_row(
                "bel_2", expectation_id="exp_2",
                metric="consolidation_posture"),
            _belief_row("bel_3")]
    beliefs, report = MB.beliefs_from_ledger(rows, at="2026-08-24")
    assert len(beliefs) == 1
    assert report["offered"] == 3
    assert report["refused_no_expectation"] == 1
    assert report["refused_no_recorded_mechanism"] == {
        "consolidation_posture": 1}


def test_the_published_state_passes_the_shared_allowlist():
    """`publish_state` serialises through `EconomicState.as_dict`, which
    validates. A leak would raise here rather than reaching a founder."""
    report = MB.publish_state(observations=[an_observation()],
                              as_of="2026-08-24")
    assert report["conditions_measured"] == 1


def test_a_trading_internal_cannot_be_written_into_shared_state():
    payload = {"contract": ES.CONTRACT, "as_of": "2026-08-24", "area": "US",
               "conditions": {}, "sectors": [], "beliefs": [], "shocks": [],
               "positioning": [], "uncertainty": {}, "provenance": {},
               "portfolio_value": 101_235.0}
    with pytest.raises(ES.StateViolation, match="not in the shared"):
        ES.validate(payload)


def test_a_win_rate_inside_a_sentence_leaks_like_one_inside_a_key():
    payload = {"contract": ES.CONTRACT, "as_of": "2026-08-24", "area": "US",
               "conditions": {"growth": {
                   "kind": "growth", "standing": "UNKNOWN",
                   "direction": "FLAT", "value": None, "unit": "",
                   "as_of": "", "node_id": "", "publisher": "",
                   "reason": "not measured; our win rate on this was 61%",
                   "known": False}},
               "sectors": [], "beliefs": [], "shocks": [], "positioning": [],
               "uncertainty": {}, "provenance": {}}
    with pytest.raises(ES.StateViolation, match="trading internal"):
        ES.validate(payload)


# --- core -> founder --------------------------------------------------------
def test_the_founder_side_reads_what_the_market_side_published(tmp_path):
    MB.publish_state(observations=[an_observation()], as_of="2026-08-24",
                     runtime_root=tmp_path)
    context = EC.load(tmp_path)
    assert context.available
    assert context.as_of == "2026-08-24"
    assert context.reading("policy_rate")["value"] == 4.25
    assert context.reading("policy_rate")["publisher"] == "central bank"


def test_absence_is_a_reading_with_a_reason(tmp_path):
    context = EC.load(tmp_path)
    assert not context.available
    assert "never run" in context.reason
    assert context.changes_readiness is False


def test_economic_context_never_promotes_a_bounded_analysis(tmp_path):
    MB.publish_state(observations=[an_observation()], as_of="2026-08-24",
                     runtime_root=tmp_path)
    assert EC.load(tmp_path).changes_readiness is False


def test_a_state_that_fails_the_contract_on_the_way_in_is_refused(tmp_path):
    EST.append(tmp_path, "state_snapshot",
               {"contract": ES.CONTRACT, "as_of": "2026-08-24",
                "portfolio_value": 1.0}, written_at="2026-08-24")
    context = EC.load(tmp_path)
    assert not context.available
    assert "failed the shared contract" in context.reason


def test_an_exposure_the_economy_does_not_measure_is_named_not_dropped(tmp_path):
    MB.publish_state(observations=[an_observation()], as_of="2026-08-24",
                     runtime_root=tmp_path)
    rows = EC.relevant_to(EC.load(tmp_path),
                          exposures=["policy_rate", "real_yield"])
    assert len(rows) == 2
    measured = {r["quantity"]: r["measured"] for r in rows}
    assert measured == {"policy_rate": True, "real_yield": False}
    assert "does not measure" in [r for r in rows
                                  if r["quantity"] == "real_yield"][0]["reason"]


def test_the_transmission_note_is_empty_rather_than_a_placeholder(tmp_path):
    MB.publish_state(observations=[an_observation()], as_of="2026-08-24",
                     runtime_root=tmp_path)
    context = EC.load(tmp_path)
    assert EC.transmission_note(context, exposures=["real_yield"]) == ""
    note = EC.transmission_note(context, exposures=["policy_rate"])
    assert "policy rate" in note and "2026-08-24" in note


def test_the_founder_side_does_not_recompute_macro_when_the_state_is_absent():
    """There is no fallback that derives an economic condition from company
    documents. That fallback is what created two disagreeing pictures."""
    source = pathlib.Path(EC.__file__).read_text(encoding="utf-8")
    assert "macro_provider" not in source
    assert "build_factors" not in source


# --- company -> core --------------------------------------------------------
def a_doc_observation(**kw):
    base = dict(signals=("capital_intensity",),
                excerpt="Capital expenditures increased to $3.1 billion as "
                        "we expanded data centre capacity.",
                date="2026-02-14", origin="https://www.sec.gov/x",
                source_refs=[{"artifact_id": "d1"}],
                evidence_quality="strong")
    base.update(kw)
    return base


def test_a_public_company_statement_becomes_an_economic_node():
    out = EE.translate([a_doc_observation()], company_id="cloudflare",
                       company_name="Cloudflare, Inc.", as_of="2026-08-24")
    assert out["translated"] == 1
    node = out["nodes"][0]
    assert node.kind == "capex"
    assert node.subject == "cloudflare"
    assert node.visibility == V.PUBLIC
    assert node.statement.startswith("rising: ")


def test_the_publisher_is_the_author_not_the_venue():
    """The error that made every SEC filing one origin."""
    out = EE.translate([a_doc_observation()], company_id="cloudflare",
                       company_name="Cloudflare, Inc.", as_of="2026-08-24")
    node = out["nodes"][0]
    assert node.provenance.publisher == "Cloudflare, Inc."
    assert "sec.gov" in node.provenance.venue


def test_a_third_party_filing_is_attributed_to_its_filer():
    out = EE.translate(
        [a_doc_observation(source_class="competitor")],
        company_id="cloudflare", company_name="Cloudflare, Inc.",
        as_of="2026-08-24",
        documents=[{"source_id": "d1", "source_class": "competitor",
                    "filer": "Fastly, Inc.", "origin": "https://sec.gov/y"}])
    assert out["nodes"][0].provenance.publisher == "Fastly, Inc.", (
        "a rival's account of the market entered the graph as the subject's "
        "own statement about itself")


def test_a_statement_with_no_direction_is_not_a_reading():
    out = EE.translate(
        [a_doc_observation(excerpt="Revenue for the quarter was reported.",
                           signals=("revenue_trajectory",))],
        company_id="acme", company_name="Acme", as_of="2026-08-24")
    assert out["translated"] == 0
    assert out["declined"]["no_direction_stated"] == 1


def test_the_loss_accounting_is_complete():
    """Every offered observation is either translated or explained.

    A translator that reports only its output makes a 90% loss invisible.
    """
    observations = [
        a_doc_observation(),
        a_doc_observation(signals=("pricing_published",)),
        a_doc_observation(excerpt="Nothing directional here at all."),
        a_doc_observation(date=""),
        a_doc_observation(origin="", source_refs=[{"artifact_id": "zz"}]),
    ]
    out = EE.translate(observations, company_id="acme", company_name="Acme",
                       as_of="2026-08-24")
    declined = out["declined"]
    accounted = (declined["no_economic_signal"]
                 + declined["no_direction_stated"]
                 + declined["tenant_private"] + declined["undated"])
    # `translated` counts NODES and one observation can carry several
    # signals, so the identity is over observations that produced any node.
    produced = len({n.provenance.document_id for n in out["nodes"]})
    assert produced + accounted == out["offered"], (
        f"{out['offered']} offered, {produced} produced a node, {accounted} "
        "explained; the residue is where a silent loss hides")


def test_there_is_no_path_from_a_demo_query_into_an_economic_node():
    """Section 18's refusal, asserted structurally.

    No function in the bridge takes a query, a session, a visitor or a count
    of any of them.
    """
    source = pathlib.Path(EE.__file__).read_text(encoding="utf-8")
    import ast
    tree = ast.parse(source)
    params = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            params.update(a.arg for a in node.args.args)
            params.update(a.arg for a in node.args.kwonlyargs)
    forbidden = {"query", "queries", "search", "searches", "session",
                 "sessions", "visitor", "visitors", "views", "clicks",
                 "popularity", "demand_signal"}
    assert not (params & forbidden), sorted(params & forbidden)


# --- the round trip ---------------------------------------------------------
def test_a_company_observation_reaches_an_index_and_cannot_corroborate_itself(
        tmp_path):
    """The whole flywheel, end to end, including the wall at the end of it."""
    from intent_engine.econ import aggregates as AG
    from intent_engine.econ import evidence as EV
    from intent_engine.econ import lineage as LI

    nodes = []
    for i in range(6):
        out = EE.translate(
            [a_doc_observation(
                signals=("capital_intensity",),
                excerpt=f"Capital expenditures increased at company {i}.",
                source_refs=[{"artifact_id": f"d{i}"}])],
            company_id=f"co{i}", company_name=f"Company {i}",
            as_of="2026-08-24")
        nodes.extend(out["nodes"])
    assert len(nodes) == 6

    graph = EV.EvidenceGraph(nodes)
    agg = AG.build("capex_intention_index", nodes=nodes, as_of="2026-08-24")
    assert agg.sufficient and agg.direction == "UP"
    assert agg.tradable is False

    index = graph.add(AG.as_node(agg, as_of="2026-08-24"))
    EST.append(tmp_path, "aggregate", agg.as_dict(), written_at="2026-08-24")

    # It reaches the market side as a CANDIDATE and nothing more.
    candidates = MB.consume_aggregates(tmp_path, as_of="2026-08-24")
    assert len(candidates) == 1
    assert candidates[0]["status"] == "CANDIDATE"
    assert candidates[0]["tradable"] is False

    # And company 0's own analysis cannot count it as independent support.
    verdict = LI.independent(graph, index.node_id, nodes[0].node_id)
    assert not verdict.independent
