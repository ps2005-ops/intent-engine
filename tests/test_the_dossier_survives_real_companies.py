"""The read model against real analyses, on the production path.

WHY THE MARKET FIXTURES ARE GENERATED, NOT HAND-WRITTEN
--------------------------------------------------------
`tests/fixtures/market_demo_snapshot_*.json` were produced by the REAL market
producer (`intent_engine.market.demo_snapshot_export`) running on the market
branch, and are read here by the real founder consumer. Two hand-written
fixtures would only prove that the person who wrote them was self-consistent.

That matters more here than usual. The two allowlists are declared twice on
purpose, because the founder branch cannot import the market package — and
this program has already spent 22 silently refused dossiers on the two sides
disagreeing about one field name. A producer-generated fixture is the closest
thing to a live crossing that a single-repository test can be.

WHAT THIS FILE DOES NOT CLAIM
------------------------------
It is not the breaker cohort, and it does not prove a live bridge. Three
shapes, on the real pipeline, end to end: analyse → produce → assemble →
persist → reload → inspect.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from intent_engine.demo_dossier import vocabulary as V
from intent_engine.demo_dossier.assembler import (CROSSING_BOTH,
                                                  CROSSING_FOUNDER_ONLY,
                                                  assemble)
from intent_engine.demo_dossier.contracts import (read_founder_snapshot,
                                                  read_market_snapshot)
from intent_engine.demo_dossier.diff import compare
from intent_engine.demo_dossier.store import DossierStore, company_key
from intent_engine.demo_dossier.transport import payload_from_file
from intent_engine.external_intel import founder_demo_snapshot as fds
from intent_engine.product_eval.harness import _compose

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

#: THE FIXTURE'S DATES MOVE WITH THE CLOCK; ITS CONTENT DOES NOT.
#:
#: `market_demo_snapshot_rich.json` was written with every date at
#: 2026-08-11, and `read_market_snapshot` declares a snapshot STALE past
#: BOUNDED_WINDOW_DAYS. So these assertions passed for a few weeks and then
#: failed for everyone -- the guard blocked a commit on 2026-09-03 over a
#: fixture written on 2026-08-11, with a diff that says nothing about the
#: contract under test.
#:
#: Pinning the READER's clock instead is not the repair: the founder half is
#: composed live and carries today's dates, so a past `now` makes the
#: assembled dossier quarantine itself with TEMPORAL_LEAK. Both sides have to
#: share one clock, and the only one that can move is the fixture's.
_DATED_FIELDS = ("evidence_cutoff", "generated_at", "known_at", "as_of")


def _as_of_today(payload, today):
    """The same snapshot, re-dated to `today`. Content is untouched."""
    if isinstance(payload, dict):
        return {k: (today if k in _DATED_FIELDS and isinstance(v, str)
                    else _as_of_today(v, today)) for k, v in payload.items()}
    if isinstance(payload, list):
        return [_as_of_today(v, today) for v in payload]
    return payload


def _rich_snapshot_payload():
    import datetime as _dt
    today = _dt.date.today().isoformat()
    return _as_of_today(
        payload_from_file(FIXTURES / "market_demo_snapshot_rich.json"),
        today), today

#: Three analysis SHAPES, not three companies from one template.
#: A — a high-coverage public company with filings behind it.
#: B — a private company with a different business and economic structure.
#: C — a company the pipeline can barely see.
SHAPES = {"rich": "palantir", "different_shape": "linear", "sparse": "ghost_co"}


@pytest.fixture(scope="module")
def analyses():
    out = {}
    for shape, key in SHAPES.items():
        ci, run_id, result = _compose(key)
        out[shape] = (run_id, result)
    return out


def _founder_snapshot(run_id, result, company_id):
    report = result.get("strategic_report")
    return read_founder_snapshot(fds.build_payload(
        run_id=run_id, company_id=company_id, canonical_name=company_id,
        report=report, data_population=V.REAL_ENTERPRISE))


def test_a_bounded_run_is_degraded_and_an_absent_run_is_unavailable(analyses):
    """FOUND BY THE SPARSE SHAPE, in the producer this batch wrote.

    `ghost_co` completes an analysis and reaches no strategic report. That was
    being emitted as UNAVAILABLE — the same value as a company nobody ever
    analysed. A completed run that concluded little is a measured outcome
    about the COMPANY; an absent run is a fact about US, and a 100-company
    sweep that cannot separate them cannot find its own coverage holes.
    """
    run_id, result = analyses["sparse"]
    assert result.get("strategic_report") is None, \
        "ghost_co is the sparse fixture; it now produces a report"
    bounded = _founder_snapshot(run_id, result, "ghost-co")
    assert bounded.availability == V.DEGRADED
    assert bounded.has_content
    assert "bounded result" in bounded.reason

    absent = read_founder_snapshot(fds.build_payload(
        run_id="", company_id="never-analysed", report=None))
    assert absent.availability == V.UNAVAILABLE
    assert not absent.has_content
    assert bounded.availability != absent.availability


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_real_shape_produces_a_readable_founder_snapshot(shape,
                                                               analyses):
    run_id, result = analyses[shape]
    snap = _founder_snapshot(run_id, result, company_key(SHAPES[shape]))
    assert snap.contract_state in (V.SUPPORTED, V.OLDER_SUPPORTED)
    assert snap.availability in V.AVAILABILITY_STATES
    assert snap.snapshot_id
    # A producer that emitted a measured zero for an unmeasured subsystem
    # would be manufacturing findings on every run.
    assert snap.evidence_independence_state == V.INDEPENDENCE_UNAVAILABLE
    assert snap.decision_impact_state in V.IMPACT_STATES


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_real_shape_survives_assemble_persist_reload(shape, analyses,
                                                           tmp_path):
    run_id, result = analyses[shape]
    company = company_key(SHAPES[shape])
    founder = _founder_snapshot(run_id, result, company)
    payload, today = _rich_snapshot_payload()
    market = read_market_snapshot(payload)

    # The market fixture is for another company, so this is the join the
    # 100-company runner will make constantly: a founder analysis with no
    # market snapshot of its own.
    from intent_engine.demo_dossier import market_unavailable
    if market.company_id != company:
        market = market_unavailable(
            "no market snapshot has been published for this company",
            company_id=company)

    dossier = assemble(market, founder, now=today)
    store = DossierStore(tmp_path)
    saved = store.save(dossier)
    assert saved.dossier_version == 1

    reloaded = DossierStore(tmp_path).latest(company)
    assert reloaded is not None
    assert reloaded.as_dict() == saved.as_dict()
    assert reloaded.crossing_state == CROSSING_FOUNDER_ONLY
    assert reloaded.market_block["availability"] == V.UNAVAILABLE
    assert reloaded.market_block["reason"]
    assert reloaded.decision_impact_state == \
        V.IMPACT_UNMEASURABLE_FIRST_OBSERVATION
    for name, block in reloaded.market_block["blocks"].items():
        assert block["is_measured_zero"] is False, name


def test_the_real_market_producers_output_is_accepted_by_this_side():
    """THE CROSS-CONTRACT TEST. Bytes from the real market producer, read by
    the real founder consumer, with neither able to import the other."""
    payload, _today = _rich_snapshot_payload()
    assert payload is not None
    snap = read_market_snapshot(payload)
    assert snap.availability == V.AVAILABLE, snap.reason
    assert snap.contract_state == V.SUPPORTED, snap.missing_fields
    assert snap.unknown_fields == (), (
        "the market producer emitted a field this side has never seen; that "
        "is exactly how the bridge stayed silently closed for 22 dossiers")
    assert snap.block("belief_refs").ids == ("blf-1", "blf-2", "blf-3")
    # Blocks the market cycle genuinely did not compute.
    assert snap.block("causal_result_refs").state == "UNAVAILABLE"
    assert snap.block("causal_result_refs").is_zero is False


def test_a_market_stated_absence_is_read_as_an_absence_not_a_refusal():
    payload = payload_from_file(
        FIXTURES / "market_demo_snapshot_unavailable.json")
    snap = read_market_snapshot(payload)
    assert snap.availability == V.UNAVAILABLE
    assert snap.availability != V.REFUSED
    assert "never analysed" in snap.reason


def test_a_real_crossing_assembles_when_both_sides_are_present(analyses,
                                                               tmp_path):
    """The combined path, on the one company the market fixture is for."""
    run_id, result = analyses["rich"]
    company = "palantir-technologies-inc"
    founder = _founder_snapshot(run_id, result, company)
    payload, today = _rich_snapshot_payload()
    market = read_market_snapshot(payload, expected_company=company)
    assert market.availability == V.AVAILABLE

    dossier = assemble(market, founder, now=today)
    assert dossier.crossing_state == CROSSING_BOTH
    assert dossier.market_block["blocks"]["beliefs"]["count"] == 3
    assert dossier.market_block["blocks"]["theses"]["ids"] == ["thx-1"]
    assert dossier.population_compatibility == V.POPULATION_COHERENT_REAL
    assert not dossier.quarantined, dossier.quarantine_reasons

    store = DossierStore(tmp_path)
    saved = store.save(dossier)
    assert compare(None, saved).state == V.FIRST_OBSERVATION
    # Second pass, unchanged: no duplicate record, and NO_CHANGE not
    # "everything moved".
    again = store.save(assemble(market, founder, now="2026-08-12"))
    assert again.dossier_version == 1
    assert compare(saved, again).state == V.NO_CHANGE


def test_two_real_companies_do_not_flatten_into_one_state(analyses):
    """§25. Different canonical inputs must not collapse to a template."""
    rich_run, rich_result = analyses["rich"]
    sparse_run, sparse_result = analyses["sparse"]
    a = assemble(*_pair(rich_run, rich_result, "palantir"), now="2026-08-11")
    b = assemble(*_pair(sparse_run, sparse_result, "ghost-co"),
                 now="2026-08-11")
    assert a.content_key() != b.content_key()
    assert a.company_id != b.company_id
    # the sparse company must not acquire the rich one's coverage
    assert (a.coverage_class, a.founder_block["ceo_answer_coverage"]) != \
           (b.coverage_class, b.founder_block["ceo_answer_coverage"])


def _pair(run_id, result, company):
    from intent_engine.demo_dossier import market_unavailable
    return (market_unavailable("no market snapshot published", company),
            _founder_snapshot(run_id, result, company))


# --- §12: the producer is CALLED, not merely present ----------------------

def test_a_real_web_analysis_publishes_a_dossier_by_itself(tmp_path):
    """A CALLER IS NOT A CALL.

    `_publish_demo_dossier` is wrapped in a bare `except` so a read-model
    write can never fail an analysis. That is the right trade and it is also
    how a call site can raise `NameError` on every run while the node reports
    COMPLETE — recorded in this program, with a missing projection kept alive
    by exactly this pattern.

    So this drives the real `_compose` and asserts the ARTIFACT exists. It
    would fail if the wiring never executed, whatever the source says.
    """
    from company_fixture_pages import BASE, transport
    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig

    app = WebApp(AppConfig(
        env="test", secret="s" * 40, demo_mode=True,
        web_store_path=tmp_path / "web.jsonl",
        fi_store_path=tmp_path / "fi.jsonl",
        ci_store_path=tmp_path / "ci.jsonl"),
        transport=transport, resolver=False)

    run = app.ci.create_run(company_name="Brightlake", website=BASE,
                            user_id="u-1", as_of="2026-08-11T00:00:00+00:00")
    run_id = run["run_id"]
    candidates = app.ci.discover(run_id)
    picked = [c["candidate_id"] for c in candidates[:3]]
    app.ci.approve(run_id, user_id="u-1", approved_ids=picked,
                   rejected_ids=[c["candidate_id"] for c in candidates
                                 if c["candidate_id"] not in picked])
    app.ci.fetch_approved(run_id)

    app._compose(run_id)

    written = sorted((tmp_path / "demo_dossiers").glob("*.jsonl"))
    assert written, (
        "the real analysis path produced no dossier; the producer is wired "
        "but was never called, and the bare except hid the reason")

    store = DossierStore(tmp_path)
    companies = store.companies()
    assert companies
    dossier = store.latest(companies[0])
    assert dossier is not None
    assert dossier.dossier_version == 1
    assert dossier.founder_block["availability"] in V.HAS_CONTENT_STATES
    # No market engine publishes into this deployment, so the honest state is
    # the partial one — not a crash and not an empty dossier (§23).
    assert dossier.crossing_state == CROSSING_FOUNDER_ONLY
    assert dossier.market_block["reason"]

    # and the telemetry substrate actually counted it
    counts = app._demo_telemetry.counts
    assert counts["dossiers_assembled"] == 1
    assert counts["market_snapshots_unavailable"] == 1
    assert counts["diff_FIRST_OBSERVATION"] == 1


def test_the_fixtures_are_the_producers_own_bytes():
    """A guard on the fixture itself: if somebody hand-edits it into a shape
    the producer would never emit, this file stops proving anything."""
    payload = json.loads(
        (FIXTURES / "market_demo_snapshot_rich.json").read_text())
    assert payload["contract_version"] == "market_demo_snapshot.v1"
    assert set(payload["belief_refs"]) == {"state", "ids", "count", "note"}
    assert payload["causal_result_refs"]["state"] == "UNAVAILABLE"
    assert "tenant_id" not in json.dumps(payload)
