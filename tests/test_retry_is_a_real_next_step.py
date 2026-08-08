"""The retry path, which the matrix never opened.

`test_remaining_surfaces_are_release_grade` measured the dashboard, the Q&A
and both share states and said, in its own docstring, that the retry path had
never been measured once. It still had not.

What the measurement found is that retry is the one place this product is
*more* careful than the checklist asked for. The obvious contract — "offer a
retry button, disable it while retrying" — is the wrong contract here. The
composition path already spends its own targeted retry budget before a reader
ever sees the failure page, so a retry offered unconditionally is a button
that can only repeat itself. `app.py` calls that "the most corrosive kind of
dead end, because it looks like progress", and it is right.

So these tests lock in the contract the product actually implements: a retry
is offered when, and only when, a second look has somewhere new to go — and
when it is withheld, the page still hands the reader real next steps rather
than a shrug.
"""
from __future__ import annotations

import io
import pathlib
import re
import tempfile
import time

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig


class Client:
    def __init__(self, app):
        self.app, self.cookie = app, ""

    def request(self, method, path, body=""):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": self.cookie,
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}

        def sr(status, headers):
            out["status"], out["headers"] = status, headers
        payload = b"".join(self.app(env, sr)).decode()
        for k, v in out["headers"]:
            if k == "Set-Cookie" and v.startswith("sid="):
                self.cookie = "" if "Max-Age=0" in v else v.split(";")[0]
        return out["status"], dict(out["headers"]), payload

    def sid(self):
        return self.cookie.split("=", 1)[1] if self.cookie else None


def _no_network(url, timeout):
    raise OSError("test transport: network disabled")


def _app(tmp):
    config = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                       web_store_path=tmp / "w.jsonl",
                       fi_store_path=tmp / "f.jsonl",
                       ci_store_path=tmp / "c.jsonl")
    app = WebApp(config, transport=_no_network, resolver=False)
    app.auth.create_user("founder@example.com", "password123")
    return app


@pytest.fixture(scope="module")
def failed_run():
    """A run where every discovered source failed — nowhere new to look."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    app = _app(tmp)
    c = Client(app)
    c.request("POST", "/login",
              "email=founder@example.com&password=password123")
    csrf = app.auth.csrf_token(c.sid())
    _, headers, _ = c.request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf}&website=https://acme-not-real.example")
    run = headers["Location"].split("/runs/")[1].split("/")[0]
    # The analysis is asynchronous. Reading the page before it settles gets a
    # different, shorter failure rendering — which is why the earlier probe of
    # this surface and the first draft of these tests disagreed about what the
    # page says. Wait for a terminal state, then measure.
    for _ in range(200):
        if app.ci.store.run_state(run) in app.TERMINAL_STATES:
            break
        time.sleep(0.05)
    else:                                       # pragma: no cover
        pytest.fail(f"run never reached a terminal state: "
                    f"{app.ci.store.run_state(run)}")

    def get(path, hops=4):
        """A reader never sees the 303, they see the page it lands on — and
        an empty body from an unfollowed redirect silently passes any `not
        in` assertion, which is how the first draft of this file went green
        on nothing."""
        for _ in range(hops):
            status, headers, body = c.request("GET", path)
            if not status.startswith("30") or "Location" not in headers:
                return body
            path = headers["Location"]
        return body                             # pragma: no cover

    # `/runs/{id}` redirects to the progress page until the web store has
    # recorded the terminal state, and the progress page renders its OWN,
    # shorter FAILED summary that links onward with "See the failure details".
    # Landing there instead of on the detail page is what made the first
    # version of this file pass three times and fail the fourth. Poll until
    # the reader would actually be on the page under test.
    body = ""
    for _ in range(200):
        body = get(f"/runs/{run}")
        if "See the failure details" not in body:
            break
        time.sleep(0.05)
    else:                                       # pragma: no cover
        pytest.fail("never left the progress page")
    assert body.strip(), "fixture captured an empty page"
    assert "What happened to each source" in body, \
        "fixture did not land on the detailed failure page"
    return {"app": app, "client": c, "csrf": csrf, "run": run, "body": body,
            "get": get}


def _text(body):
    m = re.search(r"<main.*?</main>", body, re.S)
    inner = re.sub(r"<style.*?</style>", " ", m.group(0) if m else body, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()


# --- when a retry could only repeat itself -----------------------------------

def test_a_failed_run_offers_the_targeted_second_look(failed_run):
    """The defect this file found. `retry_state` calls FAILED retryable and
    `_has_untried_sources` was True — the machinery for a cheap second look
    was ready — and this page's only exit was "Start a new analysis", which
    re-runs everything and pays for the whole analysis again."""
    app, run = failed_run["app"], failed_run["run"]
    assert app._has_untried_sources(run) is True, \
        "fixture no longer reproduces the state the fix is about"
    assert f"/runs/{run}/retry" in failed_run["body"]


def test_the_failure_page_always_leaves_a_way_forward(failed_run):
    """Whether or not the second look is available, the page is never a dead
    end — and never an apology in place of an action."""
    text = _text(failed_run["body"]).lower()
    assert "start a new analysis" in text
    assert "sorry" not in text


def test_the_failure_page_keeps_what_the_run_learned(failed_run):
    """Partial work stays visible: the reader can see which sources were
    tried and what each one did, not just that "it failed"."""
    text = _text(failed_run["body"])
    assert "acme-not-real.example" in text
    assert "could not be read" in text.lower() or "what happened" in text.lower()


def test_the_failure_page_does_not_invent_a_result(failed_run):
    text = _text(failed_run["body"]).lower()
    assert "we do not invent" in text or "no result to show" in text


def test_the_failure_page_says_a_failed_retrieval_is_not_a_finding(failed_run):
    """The distinction the whole product rests on: we could not read it is
    not the same as there is nothing there."""
    text = _text(failed_run["body"]).lower()
    assert "not evidence that anything is missing" in text


# --- when there IS somewhere new to look -------------------------------------

def test_the_retry_says_what_it_will_do_not_just_try_again(failed_run):
    """"Try again" is not an action a reader can reason about. The label
    names the work and the description names what it will skip."""
    text = _text(failed_run["body"]).lower()
    assert "look again for the missing evidence" in text
    assert "skipping everything that already failed" in text
    assert re.search(r"\btry again\b", text) is None


def test_the_retry_disappears_when_it_would_only_repeat_itself(failed_run,
                                                               monkeypatch):
    """The gate that keeps this from becoming the dead end
    `_insufficient_evidence_page` warns about: a button that can only run the
    same failed requests again looks like progress and is not."""
    app, run = failed_run["app"], failed_run["run"]
    monkeypatch.setattr(app, "_has_untried_sources", lambda _r: False)
    body = failed_run["get"](f"/runs/{run}")
    assert body.strip()
    assert f"/runs/{run}/retry" not in body
    assert "Start a new analysis" in body       # still not a dead end


def test_the_retry_disappears_when_the_budget_is_spent(failed_run,
                                                       monkeypatch):
    """Somewhere to go is not sufficient: the run must also still be owed a
    retry (ownership, not already running, attempts remaining)."""
    app, run = failed_run["app"], failed_run["run"]
    monkeypatch.setattr(app, "retry_state",
                        lambda _s, _r: {"allowed": False, "reason": "spent."})
    body = failed_run["get"](f"/runs/{run}")
    assert body.strip()
    assert f"/runs/{run}/retry" not in body


def test_the_retry_form_carries_a_csrf_token(failed_run):
    """It is a state-changing POST that spends real budget."""
    body = failed_run["body"]
    form = re.search(r'<form[^>]*/retry"[^>]*>.*?</form>', body, re.S)
    assert form, "no retry form on the page"
    assert 'name="csrf"' in form.group(0)
    assert re.search(r'name="csrf" value="\S+"', form.group(0)), \
        "csrf token is present but empty"


# --- the guarantees underneath ------------------------------------------------

def test_retry_state_gives_a_reason_a_reader_could_act_on(failed_run):
    """Whatever the answer, it is expressed as a sentence, not a code."""
    app, run, c = failed_run["app"], failed_run["run"], failed_run["client"]
    session = app.auth.session(c.sid())
    assert session is not None, "fixture lost its login"
    state = app.retry_state(session, run)
    assert isinstance(state["reason"], str) and state["reason"].strip()
    # A sentence, not a state name leaking through.
    assert not re.fullmatch(r"[A-Z_]+", state["reason"].strip())
    assert state["reason"].strip().endswith(".")


def test_a_retry_is_bounded_and_cannot_become_a_loop(failed_run):
    """A retry costs a real analysis. The budget is finite and small."""
    app = failed_run["app"]
    assert app.MAX_ANALYSIS_ATTEMPTS >= 1
    assert app.MAX_ANALYSIS_ATTEMPTS <= 5, \
        "an unbounded-ish retry budget spends a founder's money on repeats"


def test_a_duplicate_submission_does_not_start_a_second_run(failed_run):
    """The run id is deterministic per company+user+day, so a double-click,
    a browser retry and a duplicate POST all resolve to the same run — and
    must not schedule the work twice."""
    app, run = failed_run["app"], failed_run["run"]
    user = "whoever"
    first = app._schedule_analysis(user, run, allow_retry=False)
    second = app._schedule_analysis(user, run, allow_retry=False)
    assert second is False, "a duplicate submission scheduled a second run"
    if first:                                   # tidy up if we started one
        with app._analysis_lock:
            app._analysis_inflight.pop(run, None)


def test_a_finished_run_reports_nothing_to_retry(failed_run):
    """Retry is not offered for states it cannot help."""
    app = failed_run["app"]
    assert "COMPLETE" not in app.RETRYABLE_STATES
    assert "FAILED" in app.RETRYABLE_STATES


def test_the_failure_page_never_says_the_company_does_not_exist(failed_run):
    """The other half of the distinction, and the one that can defame.

    "We could not read it" is a statement about a retrieval. "There is
    nothing there" is a statement about a company, and the product is never
    entitled to make it from a failed fetch. Verified live against
    brightledger.io, whose every path returned an HTTP error: the page named
    each failure and claimed nothing about the business.
    """
    text = _text(failed_run["body"]).lower()
    for forbidden in ("does not exist", "no such company", "is not a real",
                      "could not be found as a company",
                      "we found nothing about"):
        assert forbidden not in text, forbidden
    # And it must still say what DID happen, per source.
    assert "what happened to each source" in text


def test_the_failure_page_attributes_the_failure_to_the_retrieval(failed_run):
    text = _text(failed_run["body"]).lower()
    assert "no approved source could be retrieved" in text
    assert "we do not invent one" in text
