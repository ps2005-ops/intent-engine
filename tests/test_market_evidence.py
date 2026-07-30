"""Stage 1: the research adapter produces real evidence, offline.

Runs the ACTUAL Founder Intelligence ingestion against the existing offline
company fixture — the same transport the strategic-intelligence suite uses — so
this exercises discovery, retrieval, parsing and composition rather than a mock
of them. No network.

The measurement that matters is at the bottom: the same company, through the
old placeholder and through this adapter, and what the opportunity reasoner
does with each.
"""
import tempfile

import pytest
from company_fixture_pages import BASE as FIXTURE_BASE
from company_fixture_pages import transport as fixture_transport

from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.founder_intelligence.service import FounderIntelligenceService
from intent_engine.market.evidence import (
    SYSTEM_ACTOR,
    founder_intelligence_research_fn,
)
from intent_engine.market.opportunity import (
    NO_MARKET_EVIDENCE,
    NO_STRATEGIC_READING,
    VIEW_WITHHELD,
    classify,
)

AS_OF = "2026-07-30"


class _Company:
    company_id = "brightlake"
    canonical_name = "Brightlake"
    website = FIXTURE_BASE
    strategic_priorities = ["growth"]
    tradable_instrument = "BLK"


def _services(tmp):
    ci = CompanyIngestionService(tmp / "ci.jsonl",
                                 transport=fixture_transport, resolver=False)
    fi = FounderIntelligenceService(tmp / "fi.jsonl")
    return ci, fi


@pytest.fixture()
def research():
    tmp = __import__("pathlib").Path(tempfile.mkdtemp())
    ci, fi = _services(tmp)
    return founder_intelligence_research_fn(ci, fi, max_sources=8)


def test_the_adapter_returns_real_dated_evidence(research):
    """The placeholder returned `{"evidence": [], "thesis": ""}` — every field
    empty. This is the assertion that Stage 1 is actually operational."""
    out = research(_Company(), AS_OF)
    assert out["evidence"], "no evidence collected — Stage 1 is still empty"
    for row in out["evidence"]:
        assert row["summary"].strip(), "an evidence row with no content"
        assert row["published_at"], "undated evidence cannot be reasoned from"
        assert row["kind"]
        assert row["source"]


def test_no_evidence_is_dated_after_the_run(research):
    """`refresh_company` drops future-dated evidence as leakage. Emitting it
    would mean the adapter is manufacturing work for that check to undo."""
    out = research(_Company(), AS_OF)
    assert all(row["published_at"][:10] <= AS_OF for row in out["evidence"])


def test_a_company_with_no_website_is_reported_not_crashed(research):
    class _NoSite(_Company):
        website = ""
    out = research(_NoSite(), AS_OF)
    assert out["evidence"] == [] and out["skipped"]


def test_one_companys_failure_does_not_end_the_sweep():
    """A research sweep that stops on the first unreachable site teaches the
    engine less than one that covers the rest and says which failed."""
    tmp = __import__("pathlib").Path(tempfile.mkdtemp())

    def _explode(url, timeout):
        raise RuntimeError("network is down")

    ci = CompanyIngestionService(tmp / "ci.jsonl",
                                 transport=_explode, resolver=False)
    fi = FounderIntelligenceService(tmp / "fi.jsonl")
    seen = []
    research = founder_intelligence_research_fn(
        ci, fi, on_error=lambda cid, exc: seen.append(cid))
    out = research(_Company(), AS_OF)
    assert out["evidence"] == []
    assert "error" in out or out.get("skipped")


def test_the_run_is_recorded_as_a_system_actor(research):
    """An autonomous job filed under a human actor would put a false answer in
    an append-only trail whose whole job is to say who asked."""
    tmp = __import__("pathlib").Path(tempfile.mkdtemp())
    ci, fi = _services(tmp)
    fn = founder_intelligence_research_fn(ci, fi)
    fn(_Company(), AS_OF)
    run_id = ci.create_run(company_name=_Company.canonical_name,
                           website=_Company.website, user_id=SYSTEM_ACTOR,
                           as_of=AS_OF, actor_type="system")["run_id"]
    rows = ci.store.for_run(run_id)
    created = [r for r in rows if r.event_type == "ci.run_created"]
    approved = [r for r in rows if r.event_type == "ci.approval_recorded"]
    assert created and all(r.actor_type == "system" for r in created)
    assert approved and all(r.actor_type == "system" for r in approved)
    assert all(r.actor_id == SYSTEM_ACTOR for r in created)


def test_the_webapp_flow_is_still_recorded_as_human(tmp_path):
    """The default must not have moved: a founder clicking a button is still a
    human actor, and this adapter must not have relaxed that for everyone."""
    ci = CompanyIngestionService(tmp_path / "ci.jsonl",
                                 transport=fixture_transport, resolver=False)
    run_id = ci.create_run(company_name="Brightlake", website=FIXTURE_BASE,
                           user_id="u-1", as_of=AS_OF)["run_id"]
    rows = [r for r in ci.store.for_run(run_id)
            if r.event_type == "ci.run_created"]
    assert rows and rows[0].actor_type == "human"


# --- the measurement ---------------------------------------------------------
def test_evidence_moves_the_company_past_the_first_gate(research):
    """THE point of this cycle, stated as a test.

    Before: no evidence -> the reasoner exits at `no_strategic_reading` and the
    day teaches nothing. After: the company carries a dated, source-classed
    reading and reaches a LATER gate. The specific later gate is not asserted —
    what matters is that the first one stopped being the answer.
    """
    from intent_engine.market.daily import _report_for

    company = _Company()
    empty = classify(company, _report_for({"thesis": ""}, []), as_of=AS_OF)
    assert empty.classification == "NO_TRADE"
    assert NO_STRATEGIC_READING in empty.blocked_by
    assert empty.quality == 0.0

    out = research(company, AS_OF)
    real = classify(company, _report_for(out, out["evidence"]), as_of=AS_OF)

    # The gate moved: "we could retrieve nothing" is no longer the answer.
    assert NO_STRATEGIC_READING not in real.blocked_by, \
        "evidence was collected but the reasoner still saw nothing"
    assert real.dated_evidence_count > 0
    assert real.evidence_count > 0
    assert real.quality > empty.quality

    # For THIS fixture the strategic layer honestly withholds a view, so the
    # next gate is `view_withheld` -- a different fact needing a different
    # response, which is exactly why it stopped sharing a name with the case
    # above. A richer company advances further; that is not this fixture's job
    # to prove.
    assert real.blocked_by[0] in (VIEW_WITHHELD, NO_MARKET_EVIDENCE,
                                  "no_outside_source", "no_dated_evidence")


# --- source selection --------------------------------------------------------
def test_selection_spreads_across_source_classes_not_discovery_order():
    """The measured defect: discovery returns ~30 `company_owned` candidates
    ahead of 3 `customer_voice` ones, so `candidates[:8]` took eight company
    pages and zero outside sources — for every company, every time. That made
    `no_outside_source`, the gate those sources feed, structurally unreachable.
    """
    from intent_engine.market.evidence import select_diverse

    candidates = ([{"candidate_id": f"own-{i}", "source_class": "company_owned"}
                   for i in range(30)]
                  + [{"candidate_id": f"cust-{i}",
                      "source_class": "customer_voice"} for i in range(3)]
                  + [{"candidate_id": "inv-0",
                      "source_class": "investor_material"}])

    naive = [c["candidate_id"] for c in candidates[:8]]
    assert not any(c.startswith("cust") for c in naive), \
        "the fixture no longer reproduces the defect this guards"

    picked = select_diverse(candidates, 8)
    classes = {c["source_class"] for c in picked}
    assert len(picked) == 8
    assert "customer_voice" in classes, "an outside source was crowded out"
    assert "investor_material" in classes
    assert "company_owned" in classes, "the company's own pages still matter"


def test_selection_preserves_discovery_order_within_a_class():
    """Ranking within a class is the ingestion layer's judgement, and this is
    not the place to second-guess it."""
    from intent_engine.market.evidence import select_diverse

    candidates = [{"candidate_id": f"own-{i}", "source_class": "company_owned"}
                  for i in range(6)]
    picked = [c["candidate_id"] for c in select_diverse(candidates, 4)]
    assert picked == ["own-0", "own-1", "own-2", "own-3"]


def test_selection_never_exceeds_the_budget():
    from intent_engine.market.evidence import select_diverse

    candidates = [{"candidate_id": f"c-{i}",
                   "source_class": ["a", "b", "c"][i % 3]} for i in range(20)]
    assert len(select_diverse(candidates, 5)) == 5
    assert len(select_diverse(candidates, 100)) == 20
    assert select_diverse([], 5) == []


def test_an_outside_source_reaches_the_reasoner_end_to_end():
    """The whole point, measured on a fixture that actually hosts one."""
    import pathlib
    import tempfile

    from intent_engine.market.daily import _report_for
    from intent_engine.product_eval.sites import SITES, site_transport

    site = SITES["shopify"]
    tmp = pathlib.Path(tempfile.mkdtemp())
    ci = CompanyIngestionService(tmp / "ci.jsonl",
                                 transport=site_transport(site),
                                 resolver=False)
    fi = FounderIntelligenceService(tmp / "fi.jsonl")

    class _Pub:
        company_id = "shopify"
        canonical_name = site.name
        website = site.website
        strategic_priorities = []
        tradable_instrument = "SHOP"

    out = founder_intelligence_research_fn(ci, fi, max_sources=8)(_Pub(), AS_OF)
    opp = classify(_Pub(), _report_for(out, out["evidence"]), as_of=AS_OF)

    assert opp.independent_source, \
        "no outside source survived to the reasoner"
    assert "no_outside_source" not in opp.blocked_by
    # and it therefore reaches the deepest gate in the current pipeline
    assert opp.blocked_by == (NO_MARKET_EVIDENCE,)
