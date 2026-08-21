"""Every surface reads ONE named outcome, and scarcity has to be earned.

WHY THIS FILE EXISTS. Meta Platforms rendered "Analysis could not be
completed" on two deployed builds and was scored a PASS, because the
acceptance instrument searched for the literal string "Limited analysis" and
that page says something else. The lesson is not "add the other string": it
is that a customer outcome was being inferred, separately, by every surface
and every instrument, from the words on a page. Words are a rendering of the
outcome. They are not the outcome.

So the outcome is produced once and travels on the response, and the two
things that used to look identical -- thin evidence and broken retrieval --
are now different names.
"""
import io

import pytest

from company_fixture_pages import BASE as FIXTURE_SITE, transport as fixture_transport

from intent_engine.webapp import outcome as O
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig


# --- the rule, in isolation ------------------------------------------------

def _ready(**kw):
    base = {"opens_result": False, "terminal": True, "in_flight": False,
            "degraded": False, "state": "READY_FAILED"}
    base.update(kw)
    return base


def test_a_composed_report_is_the_full_analysis():
    assert O.classify(readiness=_ready(opens_result=True)) == O.FULL_ANALYSIS


def test_a_composed_report_still_running_is_refreshing():
    got = O.classify(readiness=_ready(opens_result=True, in_flight=True))
    assert got == O.FULL_ANALYSIS_REFRESHING


def test_a_bounded_page_is_never_the_full_analysis():
    """THE FALSE PASS. A bounded page opens a result, so anything keyed on
    `opens_result` alone calls it a success -- which is exactly how Meta's
    "could not be completed" was scored green."""
    got = O.classify(readiness=_ready(opens_result=True, degraded=True),
                     exhaustion={"attempted": True,
                                 "subject_retrieval_ok": True})
    assert got == O.TRUE_EVIDENCE_SCARCITY
    assert got not in O.SUCCESSFUL


def test_scarcity_may_not_be_claimed_when_the_subject_never_arrived():
    """Meta's exact live shape: seven documents, four of them filed by Oklo,
    Enbridge, Network-1 and RingCentral. That is not a statement about Meta."""
    got = O.classify(readiness=_ready(opens_result=True, degraded=True),
                     exhaustion={"attempted": True, "retrieved": 7,
                                 "subject_documents": 0,
                                 "foreign_documents": 4,
                                 "subject_retrieval_ok": False,
                                 "displaced_by_foreign": True})
    assert got == O.RETRIEVAL_TEMPORARILY_UNAVAILABLE


def test_scarcity_is_refused_on_no_information_at_all():
    """An unexplained stop is OUR fault until something proves otherwise.
    The other default -- assume the company is thin -- is the one that told a
    customer their company could not be analysed."""
    assert O.classify(readiness=_ready()) == O.RETRIEVAL_TEMPORARILY_UNAVAILABLE


def test_rate_limiting_is_its_own_name():
    got = O.classify(readiness=_ready(),
                     exhaustion={"attempted": True, "rate_limited": True,
                                 "subject_retrieval_ok": True})
    assert got == O.RATE_LIMITED


def test_a_lost_instance_is_not_a_failed_analysis():
    got = O.classify(readiness=_ready(), run_state="INTERRUPTED")
    assert got == O.RUN_RESTART_LOST
    assert got in O.OPERATIONAL_FAILURE


def test_still_working_is_not_terminal():
    got = O.classify(readiness=_ready(terminal=False, in_flight=True),
                     run_state="RETRIEVING")
    assert got == O.WORKING
    assert got not in O.TERMINAL


def test_every_returned_state_is_a_named_one():
    """No unnamed strings escape. A consumer switching on these must be able
    to enumerate them."""
    seen = set()
    for opens in (True, False):
        for degraded in (True, False):
            for terminal in (True, False):
                for state in ("", "FAILED", "INTERRUPTED", "COMPLETE"):
                    for rep in ({}, {"attempted": True,
                                     "subject_retrieval_ok": True},
                                {"attempted": True,
                                 "displaced_by_foreign": True},
                                {"rate_limited": True}):
                        seen.add(O.classify(
                            readiness=_ready(opens_result=opens,
                                             degraded=degraded,
                                             terminal=terminal),
                            run_state=state, exhaustion=rep))
    assert seen <= set(O.OUTCOMES), seen - set(O.OUTCOMES)


# --- the producer, on a real app -------------------------------------------

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

    def get(self, path):
        env = {"REQUEST_METHOD": "GET", "PATH_INFO": path,
               "CONTENT_LENGTH": "0", "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": "; ".join(f"{k}={v}"
                                        for k, v in self.cookies.items()),
               "wsgi.input": io.BytesIO(b"")}
        out = {}
        body = b"".join(self.app(env, lambda s, h: out.update(
            status=s, headers=h))).decode()
        return out["status"], dict(out["headers"]), body

    def post(self, path, body=""):
        env = {"REQUEST_METHOD": "POST", "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": "; ".join(f"{k}={v}"
                                        for k, v in self.cookies.items()),
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}
        payload = b"".join(self.app(env, lambda s, h: out.update(
            status=s, headers=h))).decode()
        for key, value in out["headers"]:
            if key == "Set-Cookie":
                name, _, rest = value.partition("=")
                self.cookies[name] = rest.split(";")[0]
        return out["status"], dict(out["headers"]), payload


def _run(client):
    client.post("/demo", "")
    csrf = client.app.auth.csrf_token(client.cookies["sid"])
    _s, headers, _b = client.post(
        "/analyze",
        f"consent=on&csrf={csrf}&company_name=Brightlake&website={FIXTURE_SITE}")
    return headers["Location"].split("/runs/")[1].split("/")[0]


SURFACES = ("", "/intro", "/full", "/story", "/history", "/slides",
            "/connect", "/brief")


def test_every_customer_surface_reports_the_same_outcome(app):
    """THE INVARIANT THE META RUN BROKE. One run said seven different things
    depending on which route was opened; /full alone rendered a failure page
    over 6,008 characters of real analysis on the same run."""
    client = Client(app)
    run_id = _run(client)
    app.wait_for_analysis(run_id, timeout=60)
    stated = {}
    for suffix in SURFACES:
        _s, headers, _b = client.get(f"/runs/{run_id}{suffix}")
        if "X-Analysis-Outcome" in headers:
            stated[suffix or "/"] = headers["X-Analysis-Outcome"]
    assert len(stated) == len(SURFACES), f"no outcome on {stated}"
    assert len(set(stated.values())) == 1, stated


def test_the_outcome_is_a_named_state_not_prose(app):
    client = Client(app)
    run_id = _run(client)
    app.wait_for_analysis(run_id, timeout=60)
    _s, headers, _b = client.get(f"/runs/{run_id}")
    assert headers["X-Analysis-Outcome"] in O.OUTCOMES


def test_a_route_that_is_not_a_run_carries_no_outcome(app):
    """The header may not become decoration on every page; a consumer must be
    able to read its ABSENCE as 'this was not an analysis'."""
    client = Client(app)
    _s, headers, _b = client.get("/")
    assert "X-Analysis-Outcome" not in headers


def test_the_evidence_report_names_whose_documents_arrived(app):
    client = Client(app)
    run_id = _run(client)
    app.wait_for_analysis(run_id, timeout=60)
    report = app.evidence_report(run_id)
    assert report["attempted"] is True
    assert report["retrieved"] >= 1
    assert report["subject_documents"] + report["foreign_documents"] \
        == report["retrieved"]
    assert report["subject_retrieval_ok"] is True
    assert report["displaced_by_foreign"] is False


def test_a_run_that_read_only_other_companies_is_not_scarcity(app, monkeypatch):
    """The Meta shape, driven through the real producer rather than asserted
    on a hand-made dict."""
    client = Client(app)
    run_id = _run(client)
    app.wait_for_analysis(run_id, timeout=60)
    real = app.ci.store.retrieved

    def foreign(rid):
        rows = list(real(rid))
        for row in rows:
            row["final_url"] = ("https://www.sec.gov/Archives/edgar/data/"
                                "1849056/000184905625000001/oklo-10k.htm")
            row["original_url"] = row["final_url"]
        return rows
    monkeypatch.setattr(app.ci.store, "retrieved", foreign)
    report = app.evidence_report(run_id)
    assert report["subject_documents"] == 0
    assert report["displaced_by_foreign"] is True
    assert app.analysis_outcome(run_id) != O.TRUE_EVIDENCE_SCARCITY


def test_the_evidence_gate_travels_on_the_response(app):
    """A FIELD NOTHING READS IS A FIELD THAT DOES NOT EXIST.

    `compose` records how many documents the readiness gate held. Meta's
    discrepancy -- "7 page(s) read; 1 carried usable evidence" over a list of
    seven -- had to be chased through three falsified mechanisms precisely
    because no artifact recorded which document set the gate looked at. The
    number is only worth recording if a harness can read it.
    """
    client = Client(app)
    run_id = _run(client)
    app.wait_for_analysis(run_id, timeout=60)
    _s, headers, _b = client.get(f"/runs/{run_id}")
    gate = headers.get("X-Evidence-Gate", "")
    assert "compose=" in gate and "stored=" in gate, gate
    assert "usable=" in gate and "families=" in gate, gate


def test_the_evidence_gate_never_reaches_a_reader(app):
    """Measurement, not product copy. It is a header precisely so it cannot
    become a diagnostic pasted onto a page a chief executive reads."""
    client = Client(app)
    run_id = _run(client)
    app.wait_for_analysis(run_id, timeout=60)
    for suffix in ("", "/intro", "/full"):
        _s, _h, body = client.get(f"/runs/{run_id}{suffix}")
        assert "compose=" not in body
        assert "X-Evidence-Gate" not in body
