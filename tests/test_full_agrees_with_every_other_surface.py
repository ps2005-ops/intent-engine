"""One run may not tell /full a different story than every other route.

MEASURED on 517e7ae, Meta Platforms, a single run:

    intro    6,008 chars   real analysis
    slides   5,863         real analysis
    story    4,558         real analysis
    history 29,692         real analysis
    step 6   4,110         real analysis
    brief   16,206         real analysis
    full       755         "did not produce a report: not enough of what it
                            needed could be retrieved"

Ten of ten board questions answered on the same run. A customer opened the
one route named "full analysis" and was told the company could not be
analysed, while six other routes analysed it.

CAUSE: the bounded surface was gated on `layer == "default"`, so `/full` fell
through to the failure page even with documents and a composed result present.

WHY IT MATTERED SO MUCH: for an information-rich public company, a failure
page is not honest degradation. It is a false statement about the company,
made by the surface most likely to be read.
"""
import io

import pytest

from company_fixture_pages import BASE as FIXTURE_SITE, transport as fixture_transport

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig

FAILURE_MARKERS = ("did not produce a report", "could not be completed",
                   "Limited analysis")


def _no_network(url, timeout):
    raise OSError("test transport: network disabled")


@pytest.fixture
def app(tmp_path):
    return WebApp(AppConfig(env="test", secret="s" * 40, demo_mode=True,
                            web_store_path=tmp_path / "w.jsonl",
                            fi_store_path=tmp_path / "f.jsonl",
                            ci_store_path=tmp_path / "c.jsonl"),
                  transport=fixture_transport, resolver=False)


class Client:
    def __init__(self, app):
        self.app, self.cookies = app, {}

    def request(self, method, path, body=""):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": "; ".join(f"{k}={v}"
                                        for k, v in self.cookies.items()),
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}

        def sr(status, headers):
            out["status"], out["headers"] = status, headers
        payload = b"".join(self.app(env, sr)).decode()
        for key, value in out["headers"]:
            if key == "Set-Cookie":
                name, _, rest = value.partition("=")
                self.cookies[name] = rest.split(";")[0]
        return out["status"], dict(out["headers"]), payload

    def follow(self, path, hops=6):
        for _ in range(hops):
            status, headers, body = self.request("GET", path)
            if not status.startswith("30") or "Location" not in headers:
                return status, body
            path = headers["Location"]
        raise AssertionError(f"redirect loop at {path}")


def _real_run(client):
    client.request("POST", "/demo", "")
    csrf = client.app.auth.csrf_token(client.cookies["sid"])
    _s, headers, _b = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf}&company_name=Brightlake&website={FIXTURE_SITE}")
    return headers["Location"].split("/runs/")[1].split("/")[0]


def _the_live_meta_shape(app, run_id):
    """THE EXACT STATE THE LIVE RUN WAS IN, and why this is not one line.

    Reconstructed from the capture rather than guessed, because two earlier
    guesses were both wrong and both left a green test over a live defect:

      * Shaping `_availability` alone (documents, a result, no report) never
        reached the branch at all -- it sits under `run_state == "FAILED"`
        and the fixture run is PARTIAL. The test stayed green with
        `layer == "default"` restored.
      * Clearing the strategic report as well DID reach it, but tripped
        `_step_guard`, which refuses every step page for a FAILED run with no
        report. That shape renders a failure page on intro, story, slides,
        history and connect -- the OPPOSITE of what Meta showed live.

    What the capture actually proves (517e7ae, run 01M0HEPPFB7X6GV1NDPRQ53G70):

        run      6,234 chars   "Meta Platforms, Inc. -- the decision"
        intro    5,965         real analysis
        slides   5,792         real analysis
        full       747         "This analysis could not be completed"
        story    4,530         real analysis
        history 29,234         real analysis
        connect  4,074         real analysis

    The steps rendered, so `_step_guard` let them through, so `has_report` was
    TRUE. The primary screen rendered the founder brief, which on that path is
    only reachable inside the `run_state == "FAILED"` branch. So: FAILED, with
    documents, with a composed result, AND with a report -- and `/full` was
    the one route the layer gate dropped.
    """
    real_state = app.ci.store.run_state
    app.ci.store.run_state = lambda rid: ("FAILED" if rid == run_id
                                          else real_state(rid))
    avail = app._availability(run_id)
    assert avail["state"] == "FAILED", avail
    assert avail["documents"], "fixture retrieved nothing"
    assert avail["has_result"], "fixture composed nothing"
    assert avail["has_report"], "fixture has no report: wrong shape"


def test_full_does_not_render_a_failure_page_when_evidence_exists(app):
    client = Client(app)
    run_id = _real_run(client)
    _the_live_meta_shape(app, run_id)
    status, body = client.follow(f"/runs/{run_id}/full")
    assert status.startswith("200"), status
    for marker in FAILURE_MARKERS:
        assert marker not in body, f"/full still says {marker!r}"


def test_full_and_the_default_layer_agree(app):
    """THE INVARIANT. Whatever the default screen is willing to show, /full
    may not contradict."""
    client = Client(app)
    run_id = _real_run(client)
    _the_live_meta_shape(app, run_id)
    _s, default_body = client.follow(f"/runs/{run_id}")
    _s2, full_body = client.follow(f"/runs/{run_id}/full")
    default_fails = any(m in default_body for m in FAILURE_MARKERS)
    full_fails = any(m in full_body for m in FAILURE_MARKERS)
    assert default_fails == full_fails, (
        f"default_fails={default_fails} full_fails={full_fails}: one run, "
        f"two stories")


def test_full_is_substantial_when_the_run_has_evidence(app):
    """755 characters is a failure page wearing the name of an analysis."""
    client = Client(app)
    run_id = _real_run(client)
    _the_live_meta_shape(app, run_id)
    _s, body = client.follow(f"/runs/{run_id}/full")
    assert len(body) > 2000, f"/full rendered only {len(body)} chars"


def test_the_failure_path_is_not_deleted(app):
    """THE NEGATIVE CONTROL, and an honest note about its limits.

    Removing `layer == "default"` widens which runs reach the bounded surface,
    so the risk is that no run can ever fail honestly again. Two attempts to
    control for that from `/full` did not work and are not shipped pretending
    to: with autorun on, a resultless run re-approves and recomposes before
    reaching the failure branch, so the branch is simply not reachable by that
    route in this fixture.

    What DOES cover it, and passes: `test_one_run_may_not_say_two_things.py`
    drives `_step_guard` directly across FAILED-with-no-report,
    FAILED-with-report, COMPLETE, documents-without-report and in-flight, and
    asserts the failed run is refused on every step. That suite is the
    guardian of the failure path; this file guards the agreement between
    surfaces.

    This test pins the one thing it can honestly pin from here: the failure
    renderer still exists and still refuses a run with nothing.
    """
    assert callable(getattr(app, "_failed_run_page", None))
    client = Client(app)
    run_id = _real_run(client)
    _s, _h, body = app._failed_run_page({"user_id": "u1", "csrf": "c",
                                         "anonymous": True}, run_id)
    assert any(m in body for m in FAILURE_MARKERS) or "could not" in body, \
        body[:200]


#: Every route a customer walks. The Meta capture visited all of these on one
#: run and six of them told one story.
CUSTOMER_SURFACES = ("", "/intro", "/slides", "/full", "/story", "/history",
                     "/connect", "/brief")


def test_no_customer_surface_contradicts_the_others(app):
    """THE GENERAL INVARIANT, not the one route that happened to break.

    `/full` was found by reading seven pages by eye. The next one will not be
    found that way, so the rule is stated over every surface at once: on a run
    with documents and a composed result, either they ALL give up or NONE of
    them does. A route is allowed to be short. It is not allowed to be the
    only one that says the company could not be analysed.
    """
    client = Client(app)
    run_id = _real_run(client)
    _the_live_meta_shape(app, run_id)
    gave_up = {}
    for suffix in CUSTOMER_SURFACES:
        status, body = client.follow(f"/runs/{run_id}{suffix}")
        assert status.startswith("200"), f"{suffix}: {status}"
        gave_up[suffix or "/"] = any(m in body for m in FAILURE_MARKERS)
    assert len(set(gave_up.values())) == 1, (
        "one run, two stories: " +
        ", ".join(f"{k}={'gave up' if v else 'analysed'}"
                  for k, v in gave_up.items()))
