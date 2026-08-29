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
