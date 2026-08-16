"""Every capability the run workspace offers must be reachable FROM that run.

THIS IS THE CHECK THAT WAS MISSING FOR THREE BATCHES.

Batches 21, 22 and 23 each built a correct renderer -- the economic-history
projection, the second-iteration card, the Executive X-Ray -- proved it with
unit tests, deployed it, and then reported "UI live proof outstanding". The
proof was never going to arrive, because all three were wired to
`/demo-dossiers/<company>/xray`: a real route, with a real consumer, that no
live run links to and no customer can reach. `/runs/<id>/xray` answered 404.

A renderer with no link into it from the page a customer just created is not a
feature of the product. It is a feature of the codebase.

So this file does not test the X-Ray. It tests the WORKSPACE GRAPH: it starts a
real run, reads the navigation the run itself renders, follows every link, and
requires each one to answer for that same run. A capability added later and
linked from the nav is covered automatically; one that is built and never
linked fails `test_the_workspace_offers_the_executive_xray` by name.
"""
import io
import re

import pytest

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
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    autorun_sources=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    return WebApp(cfg, transport=_live_transport, resolver=False)


@pytest.fixture
def run(app):
    owner = _Client(app)
    owner.request("POST", "/demo")
    status, headers, _ = owner.request(
        "POST", "/analyze",
        f"consent=on&csrf={owner.csrf()}&company_name=Acme"
        f"&website=https://acme.example")
    assert status.startswith("303"), status
    return owner, headers["Location"].split("/runs/")[1].split("/")[0]


def _workspace_links(body, run_id):
    """Every distinct /runs/<this run>/... GET target the page offers."""
    found = re.findall(rf'href="(/runs/{re.escape(run_id)}[^"#?]*)"', body)
    return sorted(set(found))


def test_the_workspace_offers_the_executive_xray(run):
    """D9, named. The decision view must be reachable from the run itself."""
    owner, run_id = run
    _, _, body = owner.request("GET", f"/runs/{run_id}/brief")
    assert f"/runs/{run_id}/xray" in body, (
        "the run workspace does not link to its own Executive X-Ray; the "
        "X-Ray is reachable only at /demo-dossiers/<company>/xray, which no "
        "customer run ever opens")


def test_the_xray_route_answers_for_a_live_run(run):
    """The route existed for demo dossiers only. It must exist for runs."""
    owner, run_id = run
    status, _, body = owner.request("GET", f"/runs/{run_id}/xray")
    assert status.startswith("200"), (
        f"/runs/<id>/xray answered {status} for a live run")
    assert "Executive X-Ray" in body
    # It must be ABOUT this company, not a template.
    assert "Acme" in body, "the live X-Ray does not name the company"


def test_every_link_the_workspace_offers_resolves(run):
    """Follow the nav. No offered capability may 404 on its own run.

    Enumerating from the RENDERED PAGE rather than from a hardcoded list is
    the point: this is what turns "I added a renderer" into "a customer can
    reach it" without anyone remembering to update a constant.
    """
    owner, run_id = run
    _, _, body = owner.request("GET", f"/runs/{run_id}/brief")
    links = _workspace_links(body, run_id)
    assert len(links) >= 5, f"the workspace offers almost nothing: {links}"
    broken = []
    for href in links:
        status, _, _ = owner.request("GET", href)
        if status.startswith(("404", "405", "500")):
            broken.append(f"{href} -> {status}")
    assert not broken, "the workspace links to routes that do not answer: " \
                       + "; ".join(broken)


def test_the_live_xray_says_what_the_dossier_xray_says(run, app):
    """D13. Reaching the page is not the same as the page having anything on it.

    Live on 9a42372 the route answered 200 and rendered "this company is not
    classified here", "Nothing changed", "No action is put forward", 0 evidence
    rows and 0 channels -- while /demo-dossiers/<company>/xray, for the SAME
    company, rendered a pricing decision with six evidence rows and five
    beliefs. The renderer reads the fields `decision_synthesis.compose`
    populates, and the run's own reasoning decision does not have them, so an
    honest renderer reported emptiness about a run that had plenty.

    Comparing the two surfaces is what catches that. A test that only asserted
    HTTP 200, or only looked for the words "Executive X-Ray", passes on a page
    with nothing on it -- which is precisely how this shipped.
    """
    owner, run_id = run
    _, _, live = owner.request("GET", f"/runs/{run_id}/xray")
    from intent_engine.demo_dossier.store import DossierStore, company_key
    store = DossierStore(app._runtime_root)
    companies = store.companies()
    if not companies:
        pytest.skip("this run published no dossier, so there is nothing to "
                    "agree with")
    key = company_key("Acme") if company_key("Acme") in companies \
        else companies[0]
    _, _, demo = owner.request("GET", f"/demo-dossiers/{key}/xray")
    marker = "class=\"q\">"
    if marker not in demo:
        pytest.skip("the dossier X-Ray states no decision question here")
    question = demo.split(marker, 1)[1].split("<", 1)[0].strip()
    assert question, "the dossier X-Ray rendered an empty decision question"
    assert question in live, (
        "the live-run X-Ray and the dossier X-Ray disagree about the same "
        f"company: the dossier asks {question!r} and the live page does not")


def test_the_xray_carries_the_second_iteration_state(run):
    """A first run is a BASELINE, and must say so rather than fake a delta."""
    owner, run_id = run
    status, _, body = owner.request("GET", f"/runs/{run_id}/xray")
    # STATUS FIRST. Without this line the assertion below passed against the
    # 404 page from before the route existed -- a test that could not fail,
    # which is the same class of defect it was written to catch.
    assert status.startswith("200"), f"/xray answered {status}"
    lowered = body.lower()
    assert ("first reading" in lowered or "baseline" in lowered
            or "nothing yet to compare" in lowered), (
        "the X-Ray does not state the second-iteration state for a first run")
