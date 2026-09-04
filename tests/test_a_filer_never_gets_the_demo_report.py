"""A domainless filer takes the real path, never the synthetic demo.

FOUND ON THE DEPLOYED SERVICE. Typing "Toyota" and typing "Vale" both
returned a completed, confident report titled "Northwind Logistics Cloud
(synthetic demo)" -- under the SAME run id, because every company that fell
through shared the demo's deterministic id. A report about the wrong company
is the worst thing this product can emit.

The cause was a one-word guard. `if DEMO_DOMAIN not in website:` does not
merely open a block of entity resolution: everything under it, up to and
including `create_run`, IS the real-company path, and the method's trailing
`else` runs the synthetic demo. Narrowing it to `if website and ...` for the
benefit of a company that legitimately has no website dropped exactly those
companies into the demo.

The lesson is in the test name and worth keeping: a guard belongs where the
block RETURNS, not where it appears to begin.
"""
import io

import pytest

from intent_engine.company_ingestion import name_entry as NE
from intent_engine.founder_intelligence.fixtures import (DEMO_COMPANY_NAME,
                                                         DEMO_DOMAIN)
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from intent_engine.webapp.storage_state import record_boot


def _no_network(url, timeout):
    raise OSError("test transport: network disabled")


@pytest.fixture
def app(tmp_path):
    config = AppConfig(env="test", secret="s" * 40,
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl",
                       ci_store_path=tmp_path / "ci.jsonl",
                       demo_mode=True)
    record_boot(tmp_path, boot_id="previous-process-boot")
    return WebApp(config, transport=_no_network, resolver=False)


class _Client:
    def __init__(self, app):
        self.app, self.cookie = app, ""

    def post(self, path, body):
        env = {"REQUEST_METHOD": "POST", "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": self.cookie,
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}

        def sr(status, headers):
            out["status"], out["headers"] = status, headers

        payload = b"".join(self.app(env, sr)).decode()
        return out["status"], dict(out["headers"]), payload


@pytest.fixture
def filer(monkeypatch):
    """Toyota and Vale as the SEC returns them, without the network."""
    rows = {
        "toyota": {"cik": 1094517, "cik10": "0001094517",
                   "title": "TOYOTA MOTOR CORP/", "ticker": "TM"},
        "vale": {"cik": 917851, "cik10": "0000917851",
                 "title": "Vale S.A.", "ticker": "VALE"},
    }
    monkeypatch.setattr(NE, "_REGISTRANT_CACHE", {})
    monkeypatch.setattr(
        NE, "_registrant",
        lambda name, enabled=False, **kw: (
            rows.get(str(name or "").strip().lower()) if enabled else None))
    return rows


def _run_id(headers):
    """The run the response redirects to.

    ASSERTED INSTEAD OF THE BODY, deliberately. The first version of these
    tests checked that the demo company's NAME was absent from the response
    -- and a 303 has an empty body, so all four passed with the defect
    reintroduced. A test that cannot fail is worse than no test: it reports
    that the thing it never checked is fine.
    """
    location = headers.get("Location", "")
    assert location, "expected a redirect to a run"
    return location.split("/runs/", 1)[-1].split("/")[0]


def test_a_filer_is_not_sent_to_the_synthetic_demo(app, filer):
    """The defect exactly as it shipped.

    The synthetic demo namespaces its single deterministic run id with the
    session's user id, so a `--` in the run id IS the fall-through.
    """
    _, headers, _ = _Client(app).post(
        "/analyze", "company_name=Toyota&consent=on")
    assert "--" not in _run_id(headers)


def test_two_different_filers_are_two_runs(app, filer):
    """Two different companies never share one run.

    NOT asserted here: that two visitors asking about Toyota reach the SAME
    run. That was tried and is false by design -- the run key includes the
    user id so that runs are owned, which is what keeps one visitor's
    analysis out of another's account. Discovered by break-proofing: the
    assertion failed with the fix in place, which is the test telling the
    truth about a property the product never had.
    """
    toyota = _run_id(_Client(app).post(
        "/analyze", "company_name=Toyota&consent=on")[1])
    vale = _run_id(_Client(app).post(
        "/analyze", "company_name=Vale&consent=on")[1])
    assert toyota != vale


def test_the_demo_path_still_works(app):
    """The guard must not be widened into 'never run the demo'. A visitor
    who names no company still gets the demo, which is its purpose -- and
    its run id still carries the session namespacing."""
    _, headers, _ = _Client(app).post("/analyze", "consent=on")
    assert "--" in _run_id(headers)


def test_a_named_website_still_takes_the_real_path(app):
    """The ordinary path is unchanged: a website that is not the demo
    domain is a real company."""
    _, headers, _ = _Client(app).post(
        "/analyze", "company_name=Acme&website=https%3A%2F%2Facme.example"
                    "&consent=on")
    assert "--" not in _run_id(headers)


def test_the_demo_constants_are_what_this_guards(app):
    """Anchors the test to the real demo identity rather than to a `--`
    convention that could change meaning underneath it."""
    assert DEMO_COMPANY_NAME and DEMO_DOMAIN
    assert "synthetic" in DEMO_COMPANY_NAME.lower()
