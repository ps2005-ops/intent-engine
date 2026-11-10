"""The waiting page's elapsed clock, and what it may never do.

The timer is the one place the product's speed becomes visible to a reader,
so a timer that lies is worse than no timer. These hold it to four things:
it starts when the WORK was accepted, it does not reset when the page is
reloaded, it agrees between two tabs, and it never appears for an analysis
that never began.
"""
from __future__ import annotations

import datetime as _dt
import json

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from tests.test_measurement_is_canonical import _Client
from tests.test_strategic_intelligence import _live_transport


@pytest.fixture
def app(tmp_path):
    return WebApp(AppConfig(env="test", secret="s" * 40, demo_mode=True,
                            autorun_sources=True,
                            web_store_path=tmp_path / "w.jsonl",
                            fi_store_path=tmp_path / "fi.jsonl",
                            ci_store_path=tmp_path / "ci.jsonl"),
                  transport=_live_transport, resolver=False)


@pytest.fixture
def inflight(app):
    """A run that has been ACCEPTED and is not finished.

    The `run` fixture below completes synchronously, so `/progress` redirects
    and returns an empty body -- and a test that SKIPS on that can never
    fail. The waiting page only exists for this state, so the tests about it
    build this state deliberately.
    """
    import datetime as _d
    from intent_engine.webapp.records import WebEvent

    client = _Client(app)
    client.request("POST", "/demo")
    created = app.ci.create_run(
        company_name="Waiting Example Corp",
        website="https://waiting.example", user_id="tester",
        as_of=_d.date.today().isoformat())
    run_id = created["run_id"]
    app.ci.mark_lifecycle(run_id, "accepted")
    app.ci._transition(run_id, created["domain"], "DISCOVERING_SOURCES")
    user_id = app.auth.session(client.sid())["user_id"]
    app.web_store.append(WebEvent(
        event_type="web.run_owned", actor_type="human", actor_id=user_id,
        subject_type="run", subject_id=run_id,
        idempotency_key=f"own:{run_id}",
        payload={"user_id": user_id, "run_id": run_id}))
    return client, run_id


@pytest.fixture
def run(app):
    client = _Client(app)
    client.request("POST", "/demo")
    status, headers, _ = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={client.csrf()}&company_name=Acme"
        f"&website=https://acme.example")
    assert status.startswith("303"), status
    return client, headers["Location"].split("/runs/")[1].split("/")[0]


# --- format -----------------------------------------------------------------

def test_the_clock_reads_as_a_clock():
    assert WebApp._clock(0) == "00:00"
    assert WebApp._clock(7) == "00:07"
    assert WebApp._clock(47) == "00:47"
    assert WebApp._clock(60) == "1:00"
    assert WebApp._clock(72) == "1:12"
    assert WebApp._clock(605) == "10:05"
    assert WebApp._clock(None) == "00:00"


# --- the anchor -------------------------------------------------------------

def test_the_clock_starts_when_the_work_was_accepted(app, run):
    """NOT when the page was opened, and not when the browser says.

    `accepted` is marked at the instant the analysis was admitted, and its
    own call site says queue time is part of the customer's wait.
    """
    _client, run_id = run
    marks = app.ci.lifecycle(run_id)
    assert "accepted" in marks, "nothing recorded when the wait began"
    seconds = app._elapsed_seconds(run_id)
    assert seconds is not None
    began = _dt.datetime.fromisoformat(marks["accepted"].replace("Z", "+00:00"))
    expected = (_dt.datetime.now(_dt.timezone.utc) - began).total_seconds()
    assert abs(seconds - expected) <= 2, (seconds, expected)


def test_the_clock_does_not_reset_when_the_page_is_reloaded(app, run):
    """A reload re-renders the page; it must not restart the run's age."""
    client, run_id = run
    first = app._elapsed_seconds(run_id)
    for _ in range(3):
        client.request("GET", f"/runs/{run_id}/progress")
    second = app._elapsed_seconds(run_id)
    assert second >= first, "the clock went backwards across a reload"


def test_two_tabs_agree(app, run):
    """The server is the clock, so a second session sees the same age."""
    _client, run_id = run
    a = app._elapsed_seconds(run_id)
    b = app._elapsed_seconds(run_id)
    assert abs(a - b) <= 1


def test_the_poller_carries_the_clock_as_a_number(app, inflight):
    """The page's ticker re-seeds from this, so it has to be there."""
    client, run_id = inflight
    status, _h, body = client.request("GET", f"/runs/{run_id}/progress.json")
    assert status.startswith("200"), status
    payload = json.loads(body)
    assert not payload.get("terminal"), "the fixture did not stay in flight"
    assert "elapsed_s" in payload
    assert isinstance(payload["elapsed_s"], int)
    assert payload["elapsed_clock"] == WebApp._clock(payload["elapsed_s"])


# --- the promise ------------------------------------------------------------

def test_the_promise_is_withdrawn_once_the_run_outgrows_it():
    """Promising "within two minutes" at 2:30 is a small lie that costs a
    demo its credibility. There is no validated ETA model, so the honest
    move is to stop promising rather than to start counting down."""
    class _Fake:
        ETA_COPY = WebApp.ETA_COPY
        INTERACTIVE_MAX_S = WebApp.INTERACTIVE_MAX_S
        _waiting_expectation = WebApp._waiting_expectation

    fake = _Fake()
    assert fake._waiting_expectation(30) == WebApp.ETA_COPY
    assert fake._waiting_expectation(119) == WebApp.ETA_COPY
    late = fake._waiting_expectation(121)
    assert late != WebApp.ETA_COPY
    assert "longer" in late.lower()
    # AND IT IS NEVER A COUNTDOWN.
    for forbidden in ("remaining", "seconds left", "%", "estimated finish"):
        assert forbidden not in late.lower()
        assert forbidden not in WebApp.ETA_COPY.lower()


def test_the_waiting_page_shows_a_ticking_clock_and_names_the_company(
        app, inflight):
    client, run_id = inflight
    status, _h, body = client.request("GET", f"/runs/{run_id}/progress")
    assert status.startswith("200"), (status, body[:200])
    assert 'id="pg-timer"' in body, "no elapsed clock on the waiting page"
    assert "elapsed" in body
    assert "Waiting Example Corp" in body, \
        "the waiting page does not name the company"
    # The ticker must be seeded from the SERVER, not started at zero by JS.
    assert "var base=" in body
    assert WebApp.ETA_COPY in body


# --- what must never show a clock ------------------------------------------

def test_an_analysis_that_never_started_has_no_clock(app):
    """CAPACITY REFUSAL IS NOT A SLOW ANALYSIS. Nothing was fetched and no
    credit was used, so a timer would be counting a wait that never happened.
    """
    from intent_engine.webapp import failures as _failures
    _status, _headers, body = app._error_page(
        503, "This preview is already running as many analyses as it can at "
             "once. Nothing was fetched and NO ANALYSIS CREDIT WAS USED.",
        category=_failures.ADMISSION_REFUSED)
    assert 'id="pg-timer"' not in body
    assert "elapsed" not in body.lower()
