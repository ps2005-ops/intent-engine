"""The measurement apparatus must read canonical state, not the rendered page.

WHY THIS FILE EXISTS
--------------------
Every deployed performance number this project has published was read off the
product's own HTML by a benchmark harness:

    CORE_READY    "the progress page stopped redirecting to /progress"
    evidence      `re.findall(r"https?://", body)`

The second could never return anything but zero. This product cites evidence
through INTERNAL routes -- `/runs/<id>/evidence/<claim_id>` -- and the
rendered report contains no absolute href at all, so the counter reported 0
for all six Tier-1 companies and for Apple. That was read as "the product
retrieves nothing", and a causal chain was built on it. Six identical zeros
across six very different companies were the tell: a real per-company
evidence problem scatters.

The first is not false but it is derived: it measures a redirect, at the
harness's poll granularity (4s, which is 13% of a 30s budget), over a
network, and it changes meaning if a template changes.

So the product now records WHEN each lifecycle boundary was crossed, where it
was crossed, in the append-only log -- and states where every published
number came from.
"""
import io

import pytest

from intent_engine.company_ingestion.records import (
    LIFECYCLE_MARKERS, IngestionError,
)
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from tests.test_strategic_intelligence import _live_transport


class _Client:
    def __init__(self, app):
        self.app, self.cookie = app, ""

    def request(self, method, path, body=""):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": self.cookie,
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}
        payload = b"".join(self.app(env, lambda s, h: out.update(
            status=s, headers=h))).decode()
        for key, value in out["headers"]:
            if key == "Set-Cookie" and value.startswith("sid="):
                self.cookie = ("" if "Max-Age=0" in value
                               else value.split(";")[0])
        return out["status"], dict(out["headers"]), payload

    def sid(self):
        return self.cookie.split("=", 1)[1] if self.cookie else None

    def csrf(self):
        return self.app.auth.csrf_token(self.sid())


@pytest.fixture
def app(tmp_path):
    return WebApp(AppConfig(env="test", secret="s" * 40, demo_mode=True,
                            autorun_sources=True,
                            web_store_path=tmp_path / "w.jsonl",
                            fi_store_path=tmp_path / "fi.jsonl",
                            ci_store_path=tmp_path / "ci.jsonl"),
                  transport=_live_transport, resolver=False)


@pytest.fixture
def finished(app):
    c = _Client(app)
    c.request("POST", "/demo")
    status, headers, _ = c.request(
        "POST", "/analyze",
        f"consent=on&csrf={c.csrf()}&company_name=Acme"
        f"&website=https://acme.example")
    assert status.startswith("303"), status
    return c, headers["Location"].split("/runs/")[1].split("/")[0]


# --- the markers themselves -------------------------------------------------

def test_the_lifecycle_is_recorded_where_it_happens(app, finished):
    """CORE_READY is a fact the product records, not one a harness infers."""
    _c, run_id = finished
    marks = app.ci.lifecycle(run_id)
    assert "accepted" in marks, marks
    assert "core_ready" in marks, (
        "the run produced a readable core and never recorded when")


def test_a_marker_is_idempotent(app, finished):
    """The FIRST crossing is the true one.

    A retry, or a second worker on one attempt, must not be able to move a
    timestamp the measurement already depends on -- that would let a slow run
    be relabelled as a fast one by doing more work.
    """
    _c, run_id = finished
    first = app.ci.lifecycle(run_id)["core_ready"]
    app.ci.mark_lifecycle(run_id, "core_ready")
    assert app.ci.lifecycle(run_id)["core_ready"] == first

    # ASSERTED ON THE ROW COUNT, not only on the returned value. `lifecycle`
    # reads with `setdefault`, so the first marker wins even when the log
    # holds duplicates -- which means removing the store's idempotency key
    # would leave the value assertion above green and the guarantee gone.
    # Two guards over one property, and only one of them is load-bearing.
    rows = [r for r in app.ci.store.for_run(run_id)
            if r.event_type == "ci.lifecycle_marked"
            and r.payload.get("marker") == "core_ready"]
    assert len(rows) == 1, f"core_ready was recorded twice ({len(rows)} rows)"


def test_an_unknown_marker_is_refused(app, finished):
    _c, run_id = finished
    with pytest.raises(IngestionError):
        app.ci.mark_lifecycle(run_id, "nearly_ready")


def test_markers_survive_a_process_restart(app, finished, tmp_path):
    """Read from the log, not from a process dictionary.

    The preview keeps analyses in memory and loses them on restart, so a
    timing held only in `self._core_ready_at` cannot answer a question asked
    after a deploy -- which is exactly when performance questions get asked.
    """
    _c, run_id = finished
    before = app.ci.lifecycle(run_id)
    # ASSERT THE CONTENT, NOT ONLY THE EQUALITY. Comparing the two calls
    # alone is a tautology: break proof m-6 emptied `lifecycle` at the source
    # and this test still passed, because {} == {}. A restart test that
    # cannot tell "survived" from "there was never anything there" is not a
    # restart test.
    assert "core_ready" in before, "nothing was recorded to survive anything"
    reloaded = WebApp(AppConfig(env="test", secret="s" * 40, demo_mode=True,
                                web_store_path=tmp_path / "w.jsonl",
                                fi_store_path=tmp_path / "fi.jsonl",
                                ci_store_path=tmp_path / "ci.jsonl"),
                      transport=_live_transport, resolver=False)
    after = reloaded.ci.lifecycle(run_id)
    assert "core_ready" in after, "a fresh process could not read the timing"
    assert after == before


# --- the surface a harness reads --------------------------------------------

def test_timing_reports_a_latency_and_says_where_it_came_from(app, finished):
    """§16. A metric that cannot name its source cannot decide a release."""
    import json
    c, run_id = finished
    status, _h, body = c.request("GET", f"/runs/{run_id}/timing")
    assert status.startswith("200"), status
    data = json.loads(body)
    assert data["core_latency_s"] is not None
    assert data["core_latency_s"] >= 0
    assert data["provenance"]["core_latency_s"] == "persisted_lifecycle_event"
    assert data["provenance"]["evidence_count"] == \
        "canonical_retrieved_documents"


def test_evidence_is_counted_from_documents_not_from_html(app, finished):
    """§12. The positive half of the pair below.

    Without this, deleting the counter entirely would satisfy the negative
    case and the suite would still be green.
    """
    import json
    c, run_id = finished
    _s, _h, body = c.request("GET", f"/runs/{run_id}/timing")
    stored = len(list(app.ci.store.retrieved(run_id)))
    assert stored > 0, "fixture retrieved nothing; the control is not a control"
    assert json.loads(body)["evidence_count"] == stored


def test_a_run_with_no_documents_reports_zero(app):
    """And the negative half: zero must still be reachable and truthful."""
    import json
    import datetime as _dt
    from intent_engine.webapp.records import WebEvent
    c = _Client(app)
    c.request("POST", "/demo")
    uid = app.auth.session(c.sid())["user_id"]
    run = app.ci.create_run(company_name="Empty", website="https://e.example",
                            user_id=uid, as_of=_dt.date.today().isoformat())
    rid = run["run_id"]
    # Ownership is recorded by the web layer, not by `create_run`, and
    # `/timing` is ownership-gated like every other run route. Recording it
    # the way the analyze path does keeps this a test of the COUNTER; without
    # it the route returns its "no such run" page and the assertion below
    # would pass or fail for a reason that has nothing to do with counting.
    app.web_store.append(WebEvent(
        event_type="web.run_owned", actor_type="human", actor_id=uid,
        subject_type="run", subject_id=rid,
        idempotency_key=f"own:{rid}",
        payload={"user_id": uid, "run_id": rid}))
    status, _h, body = c.request("GET", f"/runs/{rid}/timing")
    assert status.startswith("200"), f"{status}: {body[:160]}"
    assert json.loads(body)["evidence_count"] == 0


def test_the_html_regex_that_replaced_this_could_never_have_worked(app,
                                                                   finished):
    """The instrument defect, pinned so it cannot come back.

    `https?://` over the rendered report is what reported six zeros. The
    assertion is about the PRODUCT's rendering choice -- evidence is cited by
    internal route -- so if the product ever does start emitting absolute
    source links this test fails and the old counter becomes defensible
    again. Either way the harness is told the truth.
    """
    import re
    c, run_id = finished
    _s, _h, page = c.request("GET", f"/runs/{run_id}")
    assert not re.findall(r'href="https?://', page), (
        "the report now emits absolute hrefs; re-evaluate how evidence is "
        "counted, because the old absolute-URL counter is no longer "
        "structurally incapable of working")


def test_every_marker_name_is_one_the_service_will_accept(app, finished):
    """The vocabulary and the producer cannot drift apart silently."""
    _c, run_id = finished
    for marker in LIFECYCLE_MARKERS:
        app.ci.mark_lifecycle(run_id, marker)
    assert set(app.ci.lifecycle(run_id)) >= set(LIFECYCLE_MARKERS)


# --- the latency waterfall --------------------------------------------------

def test_the_trace_says_where_the_time_went(app, finished):
    """§17. Spans, not an end-to-end total.

    Two hypotheses about the deployed latency were argued from aggregates and
    both were wrong. A total cannot name the stage that owns the seconds, so
    the run records them where they are spent.
    """
    _c, run_id = finished
    phases = app.ci.trace(run_id)
    assert phases, "the run recorded no spans at all"
    core = [p for p in phases if p.get("phase") == "core"]
    assert core, f"no core waterfall; phases={[p.get('phase') for p in phases]}"
    names = {s["name"] for s in core[0]["spans"]}
    assert "core_composition" in names, names
    assert "retrieval" in names, names


def test_every_span_separates_waiting_from_computing(app, finished):
    """§18. Wall AND cpu, because they imply different repairs.

    20s wall / 0.2s cpu is a network wait and wants concurrency; 20s wall /
    19s cpu is computation and wants an algorithm. A span carrying only wall
    time cannot distinguish them, which is how "the model is the bottleneck"
    survived a whole cycle.
    """
    _c, run_id = finished
    for phase in app.ci.trace(run_id):
        for span in phase["spans"]:
            assert "wall_ms" in span, span
            assert "cpu_ms" in span, span
            assert span["wall_ms"] >= 0 and span["cpu_ms"] >= 0


def test_unaccounted_time_is_reported_not_hidden(app, finished):
    """A waterfall that omits what it did not measure misdirects the reader.

    If the spans cover 40s of a 135s wall clock, the interesting 95s is
    somewhere uninstrumented; reporting only the 40s would send the next
    person to optimise the wrong thing.
    """
    _c, run_id = finished
    core = [p for p in app.ci.trace(run_id) if p.get("phase") == "core"][0]
    assert "unaccounted_wall_ms" in core
    assert core["covered_wall_ms"] <= core["total_wall_ms"] + 1.0


def test_a_failing_stage_still_records_its_span(app):
    """The failures are the runs worth reading.

    A span recorded only on success makes every trace look healthy and hides
    exactly the stage that broke.
    """
    from intent_engine.company_ingestion.latency import Trace
    t = Trace("r")
    with pytest.raises(ValueError):
        with t.span("retrieval"):
            raise ValueError("host refused")
    assert len(t.spans) == 1
    assert t.spans[0]["status"] == "error"
    assert t.spans[0]["failure_class"] == "ValueError"


def test_a_nested_span_is_not_counted_twice(app):
    """A child's time is ALSO its parent's time.

    `quality_retry_fetch` runs inside `core_composition`, so summing every
    span counts those seconds twice and drives `unaccounted` negative. That
    would discredit the one number this module exists to make trustworthy --
    and it is exactly what happened the first time the sub-spans were added.
    """
    import time as _t
    from intent_engine.company_ingestion.latency import Trace
    t = Trace("r")
    with t.span("core_composition"):
        _t.sleep(0.05)
        with t.span("quality_retry_fetch"):
            _t.sleep(0.05)
    wf = t.waterfall()
    depths = {s["name"]: s["depth"] for s in wf["spans"]}
    assert depths["core_composition"] == 0
    assert depths["quality_retry_fetch"] == 1
    assert wf["covered_wall_ms"] <= wf["total_wall_ms"] + 1.0, (
        f"nested span double-counted: covered={wf['covered_wall_ms']} "
        f"total={wf['total_wall_ms']}")
    assert wf["unaccounted_wall_ms"] >= -1.0


def test_the_yardstick_measures_cpu_and_not_only_wall():
    """A wall-only probe cannot say WHY the machine is slow.

    Descheduling and a slower core both stretch wall time, and they are
    bought differently -- more CPU share fixes the first and does nothing for
    the second. Separating them needs the probe's own CPU time, which the
    first version of this recorded as a hardcoded 0.0.
    """
    from intent_engine.company_ingestion.latency import (
        _YARDSTICK_ROUNDS, cpu_yardstick,
    )
    r = cpu_yardstick()
    assert set(r) == {"wall_ms", "cpu_ms", "rounds"}
    assert r["rounds"] == _YARDSTICK_ROUNDS, (
        "the round count is reported so two readings can be PROVEN to have "
        "measured the same work; comparing across a changed constant is "
        "silently meaningless")
    assert r["wall_ms"] > 0 and r["cpu_ms"] > 0


def test_the_yardstick_is_free_of_io():
    """The control's whole value is that it CANNOT wait on anything.

    If the probe did any I/O its slowdown would confound the two causes it
    exists to separate. On an unloaded machine its CPU time must therefore
    account for essentially all of its wall time.
    """
    from intent_engine.company_ingestion.latency import cpu_yardstick
    best = max(cpu_yardstick()["cpu_ms"] / max(cpu_yardstick()["wall_ms"], 1e-9)
               for _ in range(5))
    assert best > 0.80, (
        f"probe spent {1 - best:.0%} of its wall time not computing; a "
        f"yardstick that waits cannot calibrate scheduling")


def test_calibration_is_excluded_from_the_product_accounting():
    """Instrument overhead is not time or CPU the product spent.

    Counting the probe would make the waterfall claim it explained work the
    analysis never did, and would inflate the run's CPU total -- the number
    used to decide whether a stage is starved or waiting.
    """
    import time as _t
    from intent_engine.company_ingestion.latency import Trace
    t = Trace("r")
    with t.span("core_composition"):
        _t.sleep(0.02)
    t.calibrate("cpu_yardstick")
    wf = t.waterfall()
    probe = [s for s in wf["spans"] if s["name"] == "cpu_yardstick"][0]

    # POSITIVE CONTROL. Without this the assertions below would also pass on
    # a probe that recorded nothing at all, which is the defect being fixed.
    assert probe["cpu_ms"] > 0 and probe["wall_ms"] > 0
    assert probe["calibration"] is True

    stage = [s for s in wf["spans"] if s["name"] == "core_composition"][0]
    assert wf["covered_wall_ms"] == pytest.approx(stage["wall_ms"], abs=1.0)
    assert wf["total_cpu_ms"] == pytest.approx(stage["cpu_ms"], abs=1.0)


def test_a_marked_span_sits_beside_its_siblings():
    """`mark` exists so a long block can be timed without re-indenting it.

    A marked span must therefore be indistinguishable from a `with` span at
    the same nesting level -- otherwise it would look like a top-level stage
    and be added to `covered` twice over.
    """
    import time as _t
    from intent_engine.company_ingestion.latency import Trace
    t = Trace("r")
    with t.span("parent"):
        w, c = _t.monotonic(), _t.thread_time()
        _t.sleep(0.01)
        t.mark("marked_child", w, c, note="x")
        with t.span("with_child"):
            _t.sleep(0.01)
    by = {s["name"]: s for s in t.waterfall()["spans"]}
    assert by["marked_child"]["depth"] == by["with_child"]["depth"] == 1
    assert by["marked_child"]["note"] == "x"
    assert by["marked_child"]["wall_ms"] >= 5.0


def test_own_time_partitions_the_run_instead_of_overlapping_it():
    """Nested spans must not have their seconds counted more than once.

    A parent's time INCLUDES its children's, so any quantity summed across
    every span counts the same seconds repeatedly. Summing "excess beyond CPU
    starvation" that way reported 68.8s unexplained in a 90.2s run -- 76% --
    where the true figure is 25.8s. A double-counted number does not look
    wrong; it looks precise and alarming, which is what makes it dangerous.

    The invariant that makes it safe: OWN times partition the wall clock, so
    they sum to the run and never past it.
    """
    import pathlib as _p
    import sys as _s
    _s.path.insert(0, str(_p.Path(__file__).resolve().parents[1] / "scripts"))
    import types as _t
    if "perf_progressive_matrix" not in _s.modules:      # network-free import
        _stub = _t.ModuleType("perf_progressive_matrix")
        _stub.BASE = ""
        _stub.POLL_S = 1
        _stub._opener = lambda: (None, None)
        _stub._req = lambda *a, **k: (200, "")
        _stub.visible = lambda *a: ""
        _s.modules["perf_progressive_matrix"] = _stub
    from perf_deployed_waterfall import own_time

    spans = [
        {"name": "child_a", "depth": 1, "offset_s": 0.0, "wall_ms": 3000.0,
         "cpu_ms": 1000.0},
        {"name": "child_b", "depth": 1, "offset_s": 3.0, "wall_ms": 2000.0,
         "cpu_ms": 500.0},
        {"name": "parent", "depth": 0, "offset_s": 0.0, "wall_ms": 6000.0,
         "cpu_ms": 2000.0},
        {"name": "probe", "depth": 0, "offset_s": 6.0, "wall_ms": 100.0,
         "cpu_ms": 100.0, "calibration": True},
    ]
    own = own_time(spans)
    assert own["child_a"]["own_wall_ms"] == 3000.0
    assert own["child_b"]["own_wall_ms"] == 2000.0
    # the parent owns only what its children do not account for
    assert own["parent"]["own_wall_ms"] == 1000.0
    assert sum(v["own_wall_ms"] for v in own.values()) == 6000.0, (
        "own times must sum to the parent's wall, not to 11000ms")
    assert "probe" not in own, "calibration is instrument overhead, not stage time"


def test_the_core_path_does_not_compute_what_only_deep_reads(app, finished):
    """Work whose result nothing reads may not sit on the interactive path.

    `derive_analyst_evidence` scanned every retrieved document a SECOND time
    and its result was discarded whenever `deep` was false: 587.5ms locally
    and 18.0s on the preview -- 20% of a 90.7s CORE. It was not slow work, it
    was work nothing read, and a faster machine only runs it faster.

    Pinned structurally rather than by timing, because a duration assertion
    on a shared CI machine is a flake and would be deleted rather than fixed.
    """
    import inspect
    from intent_engine.company_ingestion import service as SVC
    src = inspect.getsource(SVC.CompanyIngestionService._strategic_report)
    call = src.index("evidence = derive_analyst_evidence")
    early_return = src.index("if not deep:")
    assert call > early_return, (
        "derive_analyst_evidence runs BEFORE the `not deep` return, so every "
        "interactive CORE request pays for a full document scan it discards")


def test_enrichment_is_not_on_the_core_path(app, finished):
    """Market refresh and the dossier write may not delay CORE_READY.

    Measured on the preview: 3.2s and 2.9s respectively, both AHEAD of the
    `core_ready` marker -- 6.1s the reader waits for work that adds nothing
    to what they are about to read. §26 classifies the refresh as enrichment
    and forbids it blocking CORE_READY.
    """
    import inspect
    from intent_engine.webapp.app import WebApp
    src = inspect.getsource(WebApp._compose)
    assert "_publish_enrichment" in src, \
        "enrichment must be delegated, not inlined into composition"
    gate = src.index("if deep:")
    call = src.index("self._publish_enrichment")
    assert gate < call, "enrichment must be gated so the CORE pass skips it"
    # POSITIVE CONTROL: the work still exists for the callers that need it.
    assert "_external_context" in inspect.getsource(WebApp._publish_enrichment)
    assert "_publish_demo_dossier" in inspect.getsource(
        WebApp._publish_enrichment)


def test_moving_enrichment_off_core_did_not_delete_it(app, finished):
    """The interactive path must still DO the work, just not before the answer.

    Gating enrichment on `deep` removes it from the CORE pass, so the
    interactive worker has to call it itself after `core_ready`. The first
    version of this change split the function out and wired only the batch
    caller -- every interactive run then published no dossier and never
    refreshed market context. `_publish_demo_dossier` is the real path, not a
    demo-only one: the 100-company runner reads what it writes.

    Caught by the pre-commit guard, which is the point; pinned here so the
    next reader is told by a test instead of by a 30-minute suite.
    """
    import inspect
    from intent_engine.webapp.app import WebApp
    worker = inspect.getsource(WebApp._run_progressive_analysis) \
        if hasattr(WebApp, "_run_progressive_analysis") else ""
    if not worker:                       # find whichever worker composes core
        for name in dir(WebApp):
            fn = getattr(WebApp, name, None)
            if not callable(fn):
                continue
            try:
                src = inspect.getsource(fn)
            except (OSError, TypeError):
                continue
            # BOTH CONDITIONS. `dir()` is alphabetical, and composing a core
            # pass stopped being unique to the worker once the deferred
            # continuation recomposed over the widened evidence --
            # `_acquire_deferred` sorts first and was selected instead, so
            # this guard reported that the worker had lost enrichment when
            # what it had actually found was a different method.
            #
            # Marking `core_ready` IS what makes a method the interactive
            # worker, and it is the property the assertions below already
            # depend on.
            if ("self._compose(run_id, deep=False" in src
                    and 'mark_lifecycle(run_id, "core_ready")' in src):
                worker = src
                break
    assert worker, "no worker composes a CORE pass -- the search itself broke"
    assert "_publish_enrichment" in worker, (
        "enrichment was removed from _compose but the interactive worker "
        "never calls it: the dossier and market refresh are silently gone")
    ready = worker.index('mark_lifecycle(run_id, "core_ready")')
    call = worker.index("_publish_enrichment")
    assert call > ready, (
        "enrichment must run AFTER core_ready, or it still delays the reader")


def test_probe_time_is_excluded_from_both_sides_of_the_accounting():
    """`unaccounted` must describe the PRODUCT, not the instrument.

    Calibration spans were excluded from `covered` but left inside
    `total_wall_ms`, so `unaccounted` came out equal to the probe cost and
    nothing else: 1786.1ms unaccounted against 1782.7ms of probe on a real
    deployed run. That reads as a 1.9% instrumentation gap in the pipeline
    which does not exist, and the collector refuses to rank stages above 1%.
    Subtract the probe from both sides or from neither.
    """
    import time as _t
    from intent_engine.company_ingestion.latency import Trace
    t = Trace("r")
    with t.span("real_stage"):
        _t.sleep(0.05)
    t.calibrate("cpu_yardstick")
    wf = t.waterfall()
    probe = [s for s in wf["spans"] if s["name"] == "cpu_yardstick"][0]
    assert probe["wall_ms"] > 0, "positive control: the probe must cost time"
    assert abs(wf["unaccounted_wall_ms"]) < probe["wall_ms"], (
        f"unaccounted ({wf['unaccounted_wall_ms']}ms) is the probe's own "
        f"cost ({probe['wall_ms']}ms), not a gap in the pipeline")
    assert wf["unaccounted_wall_ms"] < 20.0
