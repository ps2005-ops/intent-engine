"""The rows a reconstructed log cannot hold, driven through the real seam.

THE ANOMALY THIS ANSWERS
------------------------
Production has written twelve prospective research decisions and twelve
outcomes, and every single one is SUCCESS. `NO_RESULT` is 0, `FAILED` is 0.
That is either very good luck or a log that cannot represent failure, and the
two look identical from the outside.

`_acquisition_status` is unit-tested across every status. That proves the
CLASSIFIER. It does not prove that a failing sweep produces a persisted
outcome row carrying that status, which is the claim the prospective log
actually makes — and the classifier is not where this kind of thing breaks.
A-RD-009 was unit-tested too, and raised `NameError` on every cycle it ran.

So these tests drive `source_acquisition_step` itself with adapters that
fail, return nothing, return only duplicates, and return only refusable
content, and assert the decision/outcome pair reaches disk with the right
status and survives a process that did not write it.

WHAT THEY DELIBERATELY DO NOT DO
--------------------------------
They do not make production's `NO_RESULT` count nonzero. Nothing here runs in
a cycle. The live zero stays zero until a real sweep comes back empty, and
that is the honest state — what changes is that the zero can now be
distinguished from an incapacity.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from intent_engine.market import counterparty_sources as CS
from intent_engine.market import cycle as C
from intent_engine.market import learning_store as LS
from intent_engine.market import research_decision as RD
from intent_engine.market import steps as ST

AS_OF = "2026-08-07"          # a date on which every family is due


@pytest.fixture()
def one_company(monkeypatch):
    """A universe of exactly one tracked company, so a sweep is one call."""
    class _Company:
        company_id = "acme"
        name = "Acme Corporation"
        website = "https://acme.test"
        aliases = ("Acme",)

    class _Universe:
        def prediction_companies(self):
            return [_Company()]

    monkeypatch.setattr(
        "intent_engine.universe.companies.default_universe",
        lambda: _Universe())
    return _Company


def _drive(tmp_path, *, fetch, extract, monkeypatch):
    """Run the real acquisition step with every family stubbed alike."""
    monkeypatch.setattr(
        ST, "SOURCE_CADENCE_DAYS",
        {CS.GOVERNMENT_AWARD: 1, CS.PARTNERSHIP_RELEASE: 1,
         CS.CUSTOMER_CASE_STUDY: 1})

    monkeypatch.setattr(
        "intent_engine.market.gov_awards.fetch", fetch, raising=False)
    monkeypatch.setattr(
        "intent_engine.market.partnership_releases.fetch", fetch,
        raising=False)
    monkeypatch.setattr(
        "intent_engine.market.customer_case_studies.fetch", fetch,
        raising=False)
    monkeypatch.setattr(
        "intent_engine.market.gov_awards.extract", extract, raising=False)
    monkeypatch.setattr(
        "intent_engine.market.partnership_releases.extract", extract,
        raising=False)
    monkeypatch.setattr(
        "intent_engine.market.customer_case_studies.extract", extract,
        raising=False)

    ctx = C.CycleContext(cycle="night", as_of=AS_OF,
                         root=pathlib.Path(tmp_path), session=None,
                         run_id="adv", dry_run=False)
    payload = ST.source_acquisition_step(ctx)
    store = LS.LearningStore(pathlib.Path(tmp_path) / LS.DEFAULT_PATH)
    return payload, store


def _statuses(store):
    return {r["status"] for r in store.research_outcomes()}


def _document(doc_id="d1"):
    return CS.Document(
        document_id=doc_id, url="https://acme.test/x", title="t",
        text="Acme Corporation announced a contract.", published_at=AS_OF,
        source_family=CS.GOVERNMENT_AWARD)


# --- an unreachable source ---------------------------------------------------

def test_a_source_that_raises_writes_a_FAILED_outcome(tmp_path, one_company,
                                                      monkeypatch):
    def fetch(subject, aliases, as_of, **kw):
        raise ConnectionError("newsroom unreachable")

    def extract(document, subject, aliases):  # pragma: no cover
        raise AssertionError("nothing should be extracted")

    payload, store = _drive(tmp_path, fetch=fetch, extract=extract,
                            monkeypatch=monkeypatch)
    outcomes = store.research_outcomes()
    assert outcomes, "a failing sweep left no outcome row at all"
    # FAILED, not NO_RESULT. `CS.measure` catches per-subject errors so the
    # step's own `except` never fires on an unreachable host; the sweep
    # completes having retrieved nothing WITH errors recorded, and it is
    # `_acquisition_status` that has to tell those two apart. A source that
    # was asked and answered emptily is a different fact about the world
    # from one that could not be reached, and collapsing them is how a
    # broken adapter reads as an uninformative corpus.
    assert _statuses(store) == {RD.FAILED}
    for row in outcomes:
        assert row.get("failure_type"), (
            "a FAILED outcome must name what failed, or the row records "
            "only that something did")


def test_every_outcome_pairs_with_a_decision_written_first(tmp_path,
                                                           one_company,
                                                           monkeypatch):
    def fetch(subject, aliases, as_of, **kw):
        raise ConnectionError("down")

    def extract(document, subject, aliases):  # pragma: no cover
        return (), {}, {}

    _, store = _drive(tmp_path, fetch=fetch, extract=extract,
                      monkeypatch=monkeypatch)
    decisions = {r["decision_id"] for r in store.research_decisions()}
    outcomes = store.research_outcomes()
    assert outcomes
    for row in outcomes:
        assert row["decision_id"] in decisions, (
            "an outcome with no decision is a result nobody chose to seek")


# --- a source that answers and holds nothing ---------------------------------

def test_a_sweep_that_retrieves_nothing_is_NO_RESULT(tmp_path, one_company,
                                                     monkeypatch):
    def fetch(subject, aliases, as_of, **kw):
        return []

    def extract(document, subject, aliases):  # pragma: no cover
        raise AssertionError("no document to extract")

    _, store = _drive(tmp_path, fetch=fetch, extract=extract,
                      monkeypatch=monkeypatch)
    assert _statuses(store) == {RD.NO_RESULT}, (
        "an action that was asked and found nothing is the row the "
        "reconstructed log could not hold; it must survive")


def test_a_no_result_row_survives_a_process_that_did_not_write_it(
        tmp_path, one_company, monkeypatch):
    def fetch(subject, aliases, as_of, **kw):
        return []

    def extract(document, subject, aliases):  # pragma: no cover
        return (), {}, {}

    _drive(tmp_path, fetch=fetch, extract=extract, monkeypatch=monkeypatch)
    fresh = LS.LearningStore(pathlib.Path(tmp_path) / LS.DEFAULT_PATH)
    rows = [r for r in fresh.research_outcomes()
            if r["status"] == RD.NO_RESULT]
    assert rows, "the empty-handed row did not reach disk"
    assert all(r.get("provenance") != "RECONSTRUCTED" for r in rows)


# --- a source that answers with nothing new ----------------------------------

def test_documents_that_yield_only_refusals_are_not_SUCCESS(tmp_path,
                                                            one_company,
                                                            monkeypatch):
    def fetch(subject, aliases, as_of, **kw):
        return [_document()]

    def extract(document, subject, aliases):
        return (), {"the sentence names no counterparty": 1}, {}

    _, store = _drive(tmp_path, fetch=fetch, extract=extract,
                      monkeypatch=monkeypatch)
    assert RD.SUCCESS not in _statuses(store), (
        "documents arrived and established nothing; calling that success is "
        "how an empty result becomes a hit")


# --- the vocabulary is reachable, which is the whole point -------------------

def test_the_classifier_can_reach_every_unsuccessful_status():
    """Reachability of the vocabulary, kept beside the seam tests.

    If a status can never be produced by any report shape, the log's claim to
    represent failure is a claim about the enum and not about the system.
    """
    class _R:
        def __init__(self, **kw):
            self.family = "f"
            self.documents_attempted = kw.get("attempted", 3)
            self.documents_retrieved = kw.get("retrieved", 3)
            self.relationships_accepted = kw.get("accepted", 0)
            self.relationships_refused = kw.get("refused", 0)
            self.duplicates = kw.get("duplicates", 0)
            self.latency_seconds = 0.5
            self.errors = kw.get("errors", [])

    reachable = {
        ST._acquisition_status(_R(retrieved=0, errors=["boom"]),
                               integrated=False),
        ST._acquisition_status(_R(retrieved=0), integrated=False),
        ST._acquisition_status(_R(accepted=0, duplicates=4),
                               integrated=False),
        ST._acquisition_status(_R(accepted=0, refused=4), integrated=False),
        ST._acquisition_status(_R(accepted=2), integrated=True),
    }
    assert {RD.FAILED, RD.NO_RESULT, RD.NO_NEW_INFORMATION, RD.REFUSED,
            RD.SUCCESS} <= reachable
