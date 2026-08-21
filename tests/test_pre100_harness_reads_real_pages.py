"""The capture harness must not manufacture the defect it is measuring.

FOUR INSTRUMENT DEFECTS PRECEDED THIS FILE, and each one produced a confident
number: chrome truncation reported two companies at 1.000 similarity by
comparing 454 characters of banner; a chrome marker matching the bare word
"next" truncated every answer to the question's own words and reported 28 of
28 identical; a canary window reported a catastrophic regression that was
forty copies of one error page.

The fifth was found by reading the app's route table beside the harness:
`capture.py` posted all ten board questions to `/runs/<id>/answer`, which the
product serves as GET only. The product's own Q&A form posts to
`/runs/<id>/conversation`. Ten "page not found" pages per company would have
been stored as that company's strategic answers and then compared for
collapse.

So this file asserts two properties, both positively controlled:

    the route the harness posts to is a route the app answers, and
    a response that is not an answer is NAMED rather than counted.
"""
import io

import pytest

from intent_engine.pre100 import capture
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig


def _no_network(url, timeout):
    raise OSError("test transport: network disabled")


@pytest.fixture
def app(tmp_path):
    return WebApp(AppConfig(env="test", secret="s" * 40, demo_mode=True,
                            web_store_path=tmp_path / "web.jsonl",
                            fi_store_path=tmp_path / "fi.jsonl",
                            ci_store_path=tmp_path / "ci.jsonl"),
                  transport=_no_network, resolver=False)


class _Client:
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


def _demo_run(client):
    client.request("POST", "/demo", "")
    csrf = client.app.auth.csrf_token(client.cookies["sid"])
    _s, headers, _b = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf}&website=https://northwind-demo.example")
    return headers["Location"].split("/runs/")[1].split("/")[0], csrf


# --- the route the harness uses ---------------------------------------------

def test_the_harness_asks_the_question_where_the_product_answers_it(app):
    """POST to the harness's Q&A route and require a real answer back.

    Deliberately behavioural rather than a grep for the string: a route table
    is what the app SERVES, and a structural test that read the harness's
    constant and the app's constant would agree with itself while both were
    wrong.
    """
    client = _Client(app)
    run_id, csrf = _demo_run(client)
    status, _h, body = client.request(
        "POST", f"/runs/{run_id}/conversation",
        f"csrf={csrf}&question=What+should+management+do%3F")
    text = capture.text_of(body)
    assert status.startswith("2") or status.startswith("30"), status
    assert not capture.not_an_answer(text), text[:300]
    assert not capture.run_is_gone(text)


def test_the_route_the_harness_used_to_post_to_is_not_an_answer(app):
    """THE POSITIVE CONTROL for the defect this file exists to stop.

    If `/answer` ever starts accepting POST, this test fails and the guard
    above stops being interesting -- which is the moment somebody should look
    at both again.
    """
    client = _Client(app)
    run_id, csrf = _demo_run(client)
    _s, _h, body = client.request(
        "POST", f"/runs/{run_id}/answer",
        f"csrf={csrf}&question=What+should+management+do%3F")
    assert capture.not_an_answer(capture.text_of(body)), \
        "the old harness route answered; re-check which one capture.py uses"


def test_capture_posts_questions_to_the_serving_route(app):
    """Read the harness's own source for the path it posts to, and require
    the app to serve THAT path as a POST route."""
    import inspect
    source = inspect.getsource(capture.capture_company)
    assert "/conversation" in source
    assert '/answer", {"csrf"' not in source


# --- what counts as an answer -----------------------------------------------

def test_a_failure_page_is_never_counted_as_an_answer():
    assert capture.not_an_answer("Page not found") == "FAILURE_PAGE"
    assert capture.not_an_answer("Something went wrong on our side.") \
        == "FAILURE_PAGE"
    assert capture.not_an_answer("Too many analyses for now") == "FAILURE_PAGE"
    assert capture.not_an_answer("", 200) == "EMPTY_RESPONSE"
    assert capture.not_an_answer("anything", 404) == "HTTP_404"


def test_a_real_answer_is_counted():
    real = ("Meta Platforms, Inc. What should management do? Yes - on balance "
            "the evidence supports running the reported segments as one "
            "portfolio (moderate confidence).")
    assert capture.not_an_answer(real) == ""


def test_the_recovery_page_is_a_lost_run_not_an_answer():
    """The new recovery screen is a better page and still not an answer.

    Without this the reliability repair would have quietly created a sixth
    instrument defect: fifty companies all 'answering' with the same
    recovery text scores as perfect cross-company collapse.
    """
    page = ("This analysis was lost when the service restarted. Run the same "
            "company again.")
    assert capture.run_is_gone(page)


def test_a_restart_is_reported_as_measured_not_inferred():
    assert capture._restart_observed({"boot_id": "a"}, {"boot_id": "b"}) is True
    assert capture._restart_observed({"boot_id": "a"}, {"boot_id": "a"}) is False
    # An unknown is not a no.
    assert capture._restart_observed({}, {"boot_id": "b"}) is None
    assert capture._restart_observed({"boot_id": "a"}, {}) is None


# --- the audit must refuse the same pages the harness refuses ---------------

def test_the_audit_drops_failure_pages_not_only_lost_runs(tmp_path):
    """Two places refuse a non-answer, because they fail independently.

    The harness refuses at capture time and the audit refuses at read time.
    Captures written by an earlier harness -- including the ones already on
    disk that cost live analyses -- were never filtered at capture time, so
    the read-time refusal is the one that protects them.
    """
    import json
    from intent_engine.pre100 import audit as A
    company = tmp_path / "acme"
    company.mkdir()
    (company / "qa.json").write_text(json.dumps([
        {"question": "What should management do?", "answer": "Page not found",
         "status": 404},
        {"question": "Why now?", "answer": "A real strategic reading here.",
         "status": 200},
    ]), "utf-8")
    rows = A.load_qa(company)
    assert len(rows) == 1, rows
    assert rows[0]["question"] == "Why now?"


def test_the_audit_keeps_real_answers(tmp_path):
    """The positive control: the filter must not eat the data."""
    import json
    from intent_engine.pre100 import audit as A
    company = tmp_path / "acme"
    company.mkdir()
    (company / "qa.json").write_text(json.dumps([
        {"question": "Q1", "answer": "A real reading.", "status": 200},
        {"question": "Q2", "answer": "Another real reading.", "status": 200},
    ]), "utf-8")
    assert len(A.load_qa(company)) == 2


# --- the distinctness instrument -------------------------------------------

def test_within_company_distinctness_removes_the_echoed_question():
    """The measure that was wrong was the one with no control beside it.

    Raw answers give ten out of ten distinct however identical the readings
    are, because the page renders the question as the answer's heading.
    """
    from intent_engine.pre100 import audit as A
    rows = [
        {"question": "What should management do?",
         "answer": "What should management do? The same generic line."},
        {"question": "Why now?",
         "answer": "Why now? The same generic line."},
        {"question": "What's the biggest risk?",
         "answer": "What's the biggest risk? A genuinely different reading."},
    ]
    assert len({r["answer"] for r in rows}) == 3       # the false reading
    measured = A.within_company_distinctness(rows, "Acme")
    assert measured["answers"] == 3
    assert measured["distinct"] == 2, measured
    assert measured["ratio"] == round(2 / 3, 3)


def test_within_company_distinctness_does_not_flatten_real_variety():
    """THE POSITIVE CONTROL. A filter that reported collapse everywhere
    would be just as useless as one that reported none."""
    from intent_engine.pre100 import audit as A
    rows = [{"question": f"Q{i}?", "answer": f"Q{i}? Reading number {i}."}
            for i in range(5)]
    measured = A.within_company_distinctness(rows, "Acme")
    assert measured["distinct"] == 5, measured
    assert measured["ratio"] == 1.0


def test_distinctness_of_nothing_is_not_zero_distinct():
    from intent_engine.pre100 import audit as A
    assert A.within_company_distinctness([], "Acme")["ratio"] is None


# --- a wave may not run against a build it cannot name ---------------------

def test_a_wave_refuses_to_capture_when_the_build_is_unknown(monkeypatch):
    """MEASURED: a wave of eight opened with `sha=unknown`.

    One transient `/version` failure, on a service that answered in 145ms
    before and after, and every capture would have landed in a directory that
    is not comparable with the canaries it was extending, is invisible to
    `--resume`, and is only discovered after the live analyses are spent.

    Refusing costs one retry. Not refusing costs the wave.
    """
    monkeypatch.setattr(capture, "deployed_sha",
                        lambda base=None, **k: capture.UNKNOWN_SHA)
    with pytest.raises(capture.UnknownDeployment):
        capture.require_deployed_sha("https://example.invalid")


def test_a_known_build_is_returned_unchanged(monkeypatch):
    """THE POSITIVE CONTROL. A gate that refused everything would stop the
    programme rather than protect it."""
    monkeypatch.setattr(capture, "deployed_sha", lambda base=None, **k: "abc1234")
    assert capture.require_deployed_sha("https://example.invalid") == "abc1234"


def test_the_sha_lookup_retries_before_giving_up(monkeypatch):
    """One timeout is not an answer."""
    calls = {"n": 0}

    class _Resp:
        status = 200

        def read(self):
            return b'{"commit": "deadbee1234"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def flaky(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("transient")
        return _Resp()

    monkeypatch.setattr(capture.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(capture.time, "sleep", lambda s: None)
    assert capture.deployed_sha("https://example.invalid") == "deadbee"
    assert calls["n"] == 3, calls
