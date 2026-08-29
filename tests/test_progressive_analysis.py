"""§2–§13/§25/§48: CORE_READY before DEEP_READY, and DEEP may not destroy it.

WHAT THIS PINS, AND WHY IT IS NOT A LATENCY TEST
------------------------------------------------
The deployed measurement was 240s to a readable result, of which ~200s was a
single synchronous model call inside composition. No timeout fixes that:
bounding it harder truncates the analysis, which the quality wall forbids.
The repair is architectural — publish the evidence-grounded core, then merge
the strategic reading into it.

So these tests do not assert seconds. They assert the ORDER and the
SURVIVAL: that a reader can open a result before the model has run, that the
model failing costs only the model's half, and that a deep reading which
changes what the executive first saw records the change rather than
overwriting it silently.
"""
import datetime as _dt
import threading
import time

import pytest

from company_fixture_pages import BASE
from company_fixture_pages import transport as fixture_transport
from intent_engine.company_ingestion import service as SVC
from intent_engine.company_ingestion.transient import RetryLedger
from intent_engine.founder_brief.build import PUBLIC_INFORMATION_RICH, build
from intent_engine.strategic_intelligence.analyst.contract import ResultState
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig

AS_OF = _dt.date.today().isoformat()
DEEP_DELAY = 1.5


@pytest.fixture
def app(tmp_path):
    a = WebApp(AppConfig(env="development", secret="x" * 40,
                         web_store_path=tmp_path / "w.jsonl",
                         fi_store_path=tmp_path / "f.jsonl",
                         ci_store_path=tmp_path / "ci.jsonl"))
    a.ci.transport = fixture_transport
    a.ci.resolver = False
    return a


def _run(app):
    run = app.ci.create_run(company_name="Brightlake", website=BASE,
                            user_id="u", as_of=AS_OF)
    return run["run_id"]


def _slow_deep(delay=DEEP_DELAY, fail=False, mutate=None):
    """Replace the deep half with something slow and observable."""
    original = SVC.CompanyIngestionService._strategic_report
    seen = {"deep_calls": 0}

    def patched(self, company_name, documents, extra, previous_model=None,
                run_id="", deep=True):
        if not deep:
            return original(self, company_name, documents, extra,
                            previous_model=previous_model, run_id=run_id,
                            deep=False)
        seen["deep_calls"] += 1
        time.sleep(delay)
        if fail:
            raise RuntimeError("the model is unavailable")
        payload = original(self, company_name, documents, extra,
                           previous_model=previous_model, run_id=run_id,
                           deep=False)
        payload["result_state"] = ResultState.COMPLETE
        payload["reasoning_provenance"] = "grounded_analyst"
        payload["strategic_analysis"] = {"decisions": []}
        # THE DEEP PAYLOAD DOES NOT CARRY THE CORE'S EVIDENCE, on purpose.
        # A merge that copies whole objects instead of the reasoning fields
        # would drop what the reader is already looking at, and a fake deep
        # that happened to carry identical evidence could never show it.
        payload.pop("observations", None)
        payload.pop("source_library", None)
        if mutate:
            payload.update(mutate)
        return payload
    return patched, seen, original


# --- §7/§10: the core does not wait ---------------------------------------

def test_the_core_is_readable_before_the_model_has_run(app, monkeypatch):
    """The central claim. A reader may open the analysis while the deep
    strategic review is still running."""
    patched, seen, _orig = _slow_deep()
    monkeypatch.setattr(SVC.CompanyIngestionService, "_strategic_report",
                        patched)
    run_id = _run(app)
    core_at = {}
    began = time.monotonic()

    def watch():
        while time.monotonic() - began < 60:
            if app.result_readiness(run_id)["opens_result"]:
                core_at["t"] = time.monotonic() - began
                return
            time.sleep(0.02)

    w = threading.Thread(target=watch, daemon=True)
    w.start()
    app._run_analysis("u", run_id)
    total = time.monotonic() - began
    w.join(timeout=2)

    assert "t" in core_at, "no result ever became openable"
    # THE COMPARISON IS AGAINST THE WORKER, NOT THE DELAY. Acquisition has to
    # finish before any core can exist, so "core before DEEP_DELAY seconds"
    # was never possible and would measure nothing. What the architecture
    # claims is that the worker keeps working after the page is openable.
    assert total - core_at["t"] >= DEEP_DELAY * 0.7, (
        f"core became readable at {core_at['t']:.2f}s and the worker "
        f"finished at {total:.2f}s — the reader waited for the model")
    assert seen["deep_calls"] == 1, "the deep half must run exactly once"


def test_the_core_carries_evidence_and_provenance_not_scaffolds(app):
    """§4. CORE may not be a skeleton, and may not promote library
    scaffolds to findings in order to look complete."""
    run_id = _run(app)
    # Acquisition first: composing an empty run has nothing to compose, and a
    # KeyError here would be the test's fault, not the product's.
    app.ci.discover(run_id)
    candidates = app.ci.store.candidates(run_id)
    approved = app._recommended_candidate_ids(
        candidates, refusing_hosts=app.ci.refusing_hosts(run_id),
        subject_cik=(app.ci.run_meta(run_id) or {}).get("cik"))
    app.ci.approve(run_id, user_id="u", approved_ids=approved,
                   rejected_ids=[c["candidate_id"] for c in candidates
                                 if c["candidate_id"] not in approved])
    app.ci.fetch_approved(run_id)
    core = app._compose(run_id, deep=False)
    report = core["strategic_report"]
    assert report is not None, "acquisition produced nothing to compose"

    assert report["deep_status"] == SVC.DEEP_PENDING
    assert report["result_state"] == ResultState.DEEP_PENDING
    # It is grounded: real observations from real retrieved documents.
    assert report["observations"], "a core with no observations is a skeleton"
    # The evidence is counted where the product actually records it — the
    # first draft asserted a `documents` key that does not exist, which would
    # have been a test defect reported as a missing-evidence defect.
    assert (core.get("coverage") or {}).get("document_count", 0) > 0, (
        "core must rest on documents that were actually retrieved")
    assert report.get("source_library") or report.get("evidence_graph"), (
        "core must carry the provenance a reader can check")
    # And it does NOT claim a strategic reading it has not made.
    assert report["strategic_analysis"] is None
    assert report["reasoning_provenance"] == "pattern_library"
    # The reader is told WHY, and the reason is not a lie about the evidence.
    detail = report["result_state_detail"].lower()
    # THIS ONE FIRST. Ordered deliberately: the generic shape check below
    # fired ahead of it and the break proof went red for the wrong reason,
    # which is indistinguishable from a guard that does not work.
    assert "no reasoning backend" not in detail, (
        "a core that is waiting for the model must not tell the reader the "
        "model is unconfigured — that sends them to fix the wrong thing")
    assert "still" in detail or "review" in detail


# --- §25: deep failure may not destroy core -------------------------------

def test_a_failed_deep_pass_leaves_the_core_readable(app, monkeypatch):
    patched, _seen, _o = _slow_deep(delay=0.05, fail=True)
    monkeypatch.setattr(SVC.CompanyIngestionService, "_strategic_report",
                        patched)
    run_id = _run(app)
    app._run_analysis("u", run_id)

    assert app.result_readiness(run_id)["opens_result"], (
        "the model failed and took the customer's result with it")
    report = app._results[run_id]["strategic_report"]
    assert report["deep_status"] == SVC.DEEP_FAILED
    assert report["deep_failure"] == "RuntimeError"
    assert report["observations"], "the core evidence was lost"
    assert report["result_state"] == ResultState.DEEP_PENDING


def test_the_run_is_not_marked_failed_because_the_model_was(app, monkeypatch):
    """A deep failure is not an analysis failure."""
    patched, _s, _o = _slow_deep(delay=0.05, fail=True)
    monkeypatch.setattr(SVC.CompanyIngestionService, "_strategic_report",
                        patched)
    run_id = _run(app)
    app._run_analysis("u", run_id)
    assert app.ci.store.run_state(run_id) != "FAILED"


# --- §12/§13: one analysis, and changes are recorded ----------------------

def test_deep_merges_into_the_same_analysis(app, monkeypatch):
    patched, _s, _o = _slow_deep(delay=0.05)
    monkeypatch.setattr(SVC.CompanyIngestionService, "_strategic_report",
                        patched)
    run_id = _run(app)
    app._run_analysis("u", run_id)
    report = app._results[run_id]["strategic_report"]

    assert report["deep_status"] == SVC.DEEP_COMPLETE
    assert report["result_state"] == ResultState.COMPLETE
    assert report["reasoning_provenance"] == "grounded_analyst"
    # The evidence the reader already saw is still the evidence — and the
    # deep payload deliberately did not carry it, so this can only pass if
    # the merge took the reasoning fields rather than replacing the object.
    assert report["observations"], (
        "the deep pass replaced the analysis and dropped the core evidence")
    assert report.get("source_library") or report.get("evidence_graph")


def test_a_material_deep_change_is_recorded_not_silent(app, monkeypatch):
    """§13. If the deeper reading changes what the executive first saw, the
    change is stored — never a silent rewrite."""
    patched, _s, _o = _slow_deep(delay=0.05)
    monkeypatch.setattr(SVC.CompanyIngestionService, "_strategic_report",
                        patched)
    run_id = _run(app)
    app._run_analysis("u", run_id)
    changes = app._results[run_id]["strategic_report"]["deep_changes"]

    fields = {c["field"] for c in changes}
    assert "result_state" in fields and "reasoning_provenance" in fields
    for c in changes:
        assert c["core"] != c["deep"]
        assert c["core"] is not None


def test_enrichment_is_idempotent(app, monkeypatch):
    """A second enrichment of an already-deep report must not re-run it."""
    patched, seen, _o = _slow_deep(delay=0.05)
    monkeypatch.setattr(SVC.CompanyIngestionService, "_strategic_report",
                        patched)
    run_id = _run(app)
    app._run_analysis("u", run_id)
    assert seen["deep_calls"] == 1
    app.ci.enrich_deep(run_id, app._results[run_id])
    assert seen["deep_calls"] == 1, "enrichment ran twice on one analysis"


# --- §29: the poll route may not do the work ------------------------------

def test_readiness_composes_nothing(app):
    """A page a reader refreshes may not be the thing that builds the run."""
    run_id = _run(app)
    before = len(list(app.ci.store.for_run(run_id)))
    for _ in range(5):
        app.result_readiness(run_id)
        app._availability(run_id)
    assert len(list(app.ci.store.for_run(run_id))) == before, (
        "polling wrote to the run's ledger")
    assert run_id not in app._results, "polling composed the analysis"


# --- the concurrency defect that shipped ----------------------------------

def test_the_retry_ledger_guards_its_counters():
    """`_prefetch` hands ONE ledger to six threads; every counter on it is a
    read-modify-write. A lost charge is not a cosmetic miscount — `remaining`
    decides `mark_exhausted`, so it retires a host that was answering.

    STRUCTURAL, AND HONESTLY SO. The stress loop below does not reliably lose
    a charge under CPython: the GIL makes `d[k] = d.get(k) + x` almost always
    complete within one bytecode window, so a test that only stresses it
    passes with the lock removed — measured, as a break proof reporting
    NOT_CAUGHT. A guard that cannot fail is not a guard, so the property is
    asserted where it is decidable: the mutating methods hold the lock. The
    stress loop is kept beside it as a smoke check, not as the proof.
    """
    import inspect

    from intent_engine.company_ingestion.transient import RetryLedger

    for name in ("charge", "record", "mark_exhausted"):
        src = inspect.getsource(getattr(RetryLedger, name))
        assert "with self._lock" in src, (
            f"RetryLedger.{name} mutates shared counters without the lock, "
            f"and concurrent retrieval shares one ledger across threads")

    ledger = RetryLedger()
    workers, per_worker = 8, 200

    def charge():
        for _ in range(per_worker):
            ledger.charge("example.com", 0.001)

    threads = [threading.Thread(target=charge) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    expected = workers * per_worker
    assert ledger.snapshot()["retries_by_host"]["example.com"] == expected, (
        "charges were lost to a race between threads")  # smoke, not proof
    assert ledger.spent("example.com") == pytest.approx(expected * 0.001,
                                                        rel=1e-6)


# --- the core may not ship the library's reasoning as this company's --------

def _core_shaped_report(state, provenance="pattern_library"):
    """A CORE payload: the pattern library ran and the analyst did not.

    Shaped as `_strategic_report` leaves it before the model call -- a full
    `thesis` and `hypotheses` from the library, `strategic_analysis` still
    None, and the provenance saying where that reasoning came from.
    """
    return {
        "result_state": state,
        "reasoning_provenance": provenance,
        "strategic_analysis": None if provenance == "pattern_library" else {"x": 1},
        "thesis": {
            "view": "Recurring services are growing faster than hardware.",
            "why_care": "Whether to keep investing in depth or in adjacency",
            "tension": "Services growth is outpacing the hardware that carries it",
            "why_it_may_matter": "Pricing power may migrate away from the device",
            "transition": "The install base is being monetised after the sale",
        },
        "hypotheses": [{
            "statement": "Consolidating checkout and identity rails may "
                         "encroach on layers partners currently monetize.",
            "reasoning": "Platform owners capture the layer they standardise.",
            "supporting_observation_ids": ["obs-1", "obs-2"],
            "falsification_questions": ["Do partners report margin loss?"],
            "decision_implications": ["Decide whether to build or partner"],
            "confidence": "medium",
        }],
        "observations": [],
    }


_OBS = [{"source_class": "investor_material", "id": "obs-1"}]


@pytest.mark.parametrize("state", list(ResultState.ALL))
def test_a_core_never_ships_library_scaffolds_as_findings(state):
    """No result state may carry pattern-library reasoning onto the page.

    THE DENYLIST WAS THE BUG. `_WITHHELD_STATES` listed EVIDENCE_LIMITED, the
    CORE/DEEP split gave the pre-model payload DEEP_PENDING instead, and the
    scaffolds walked through: `key_insight` became `thesis.view`, and the next
    three became `hypotheses[:3]` -- on the screen a chief executive opens
    first, in seconds, which is exactly what made the split worth doing.
    Asserting it for every state in the contract is what stops the NEXT state
    from reopening it, since the mistake was never about one name.
    """
    brief = build(company="Apple Inc.", mode=PUBLIC_INFORMATION_RICH,
                  report=_core_shaped_report(state), observations=_OBS)
    assert brief.key_insight is None, (
        f"{state} let the pattern library reach the page as "
        f"{brief.key_insight.fact!r}")


def test_an_analyst_backed_report_still_produces_an_insight():
    """The positive control: the gate above withholds scaffolds, not everything.

    Without this, deleting the whole insight path would pass the test above,
    and a wall that refuses every report is not a wall -- it is an outage.
    """
    brief = build(company="Apple Inc.", mode=PUBLIC_INFORMATION_RICH,
                  report=_core_shaped_report(ResultState.COMPLETE,
                                             provenance="grounded_analyst"),
                  observations=_OBS)
    assert brief.key_insight is not None
    assert brief.key_insight.fact


# --- the retry budget is read as one number, not two ------------------------

def test_remaining_is_read_atomically():
    """`remaining` must report a budget the ledger actually held.

    IT IS THE COMPOSITE READ THAT DECIDES. Locking each accessor made every
    single field safe and left the one call that matters unsafe: `remaining`
    reads the per-host spend, releases, then reads the run total. A worker
    charging in that gap makes the two halves describe different moments, and
    `mark_exhausted` is decided from the answer.

    The interleaving is forced rather than raced, so this fails for its stated
    reason instead of when the scheduler happens to cooperate.
    """
    ledger = RetryLedger()
    ledger.charge("other.example", 20.0)      # run total 20 of 45
    before = ledger.remaining("h.example")    # min(20-0, 45-20) = 20.0
    after_if_charged = 1.0                    # min(20-19, 45-39) = 1.0

    reached, charged = threading.Event(), threading.Event()
    original_spent = ledger.spent

    def spent_then_yield(host):
        value = original_spent(host)
        reached.set()
        charged.wait(0.3)      # blocked by the lock when the lock is correct
        return value

    ledger.spent = spent_then_yield

    def charger():
        reached.wait(1.0)
        ledger.charge("h.example", 19.0)
        charged.set()

    worker = threading.Thread(target=charger)
    worker.start()
    got = ledger.remaining("h.example")
    charged.set()
    worker.join(2.0)

    assert got in (before, after_if_charged), (
        f"remaining() reported {got}, a budget the ledger never held: the "
        f"per-host half was read before the charge and the run half after it")
