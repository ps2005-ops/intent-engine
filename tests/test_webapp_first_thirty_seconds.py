"""The first thirty seconds of a first-time visit.

Every case here was observed on the deployed product at ec337f5 by using it as
a first-time user, not by reading code.
"""
from company_fixture_pages import transport as brightlake
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from test_webapp_demo_mode import DEMO_URL, Client, _make, _start_demo


# --- the login dead end ----------------------------------------------------

def test_anonymous_analyze_is_not_thrown_at_a_login_page(tmp_path):
    """OBSERVED LIVE: a first-time visitor filled the company form, ticked
    consent, pressed the primary button, and was redirected to /login -- a
    page offering no signup and stating "Password reset: NOT AVAILABLE".
    Their input was silently discarded, and the demo was reachable only by
    noticing a different button and pressing it BEFORE filling the form."""
    app = _make(tmp_path)
    status, headers, _ = Client(app).request(
        "POST", "/analyze", f"consent=on&website={DEMO_URL}")
    assert headers.get("Location") != "/login", \
        "a first-time analysis still dead-ends at the login page"
    assert status.startswith("303")


def test_anonymous_analyze_carries_a_session_forward(tmp_path):
    app = _make(tmp_path)
    _, headers, _ = Client(app).request(
        "POST", "/analyze", f"consent=on&website={DEMO_URL}")
    cookie = headers.get("Set-Cookie", "")
    assert cookie.startswith("sid="), "no session carried onto the analysis"
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_the_run_started_that_way_is_reachable(tmp_path):
    """Not a dead end either: the minted session must own the run it just
    created, or the user lands on someone else's 404."""
    app = _make(tmp_path)
    c = Client(app)
    _, headers, _ = c.request("POST", "/analyze",
                              f"consent=on&website={DEMO_URL}")
    where = headers["Location"]
    status, _, _ = c.request("GET", where)
    assert status.startswith(("200", "303")), status


# --- what the exemption must NOT weaken ------------------------------------

def test_consent_is_still_required(tmp_path):
    app = _make(tmp_path)
    status, _, _ = Client(app).request("POST", "/analyze",
                                       f"website={DEMO_URL}")
    assert status.startswith("400")


def test_analyze_still_requires_login_when_demo_mode_is_off(tmp_path):
    """The exemption is demo-mode only. Off means off, unchanged."""
    app = _make(tmp_path, demo_mode=False)
    _, headers, _ = Client(app).request("POST", "/analyze",
                                        f"consent=on&website={DEMO_URL}")
    assert headers.get("Location") == "/login"


def test_csrf_is_still_enforced_once_a_session_exists(tmp_path):
    """Minting skips CSRF because there is nothing yet to protect. An
    established session must still present a valid token."""
    app = _make(tmp_path)
    c = _start_demo(app)
    status, _, _ = c.request("POST", "/analyze",
                             f"consent=on&website={DEMO_URL}&csrf=wrong")
    assert status.startswith("403")


def test_an_anonymous_session_still_cannot_read_another_visitors_run(tmp_path):
    app = _make(tmp_path)
    owner = Client(app)
    _, headers, _ = owner.request("POST", "/analyze",
                                  f"consent=on&website={DEMO_URL}")
    run_path = headers["Location"].rsplit("/progress", 1)[0]
    intruder = _start_demo(app)
    status, _, _ = intruder.request("GET", run_path)
    assert status.startswith("404"), \
        f"another visitor could read the run: {status}"


# --- internal language ------------------------------------------------------

def test_presentation_is_named_first_in_the_layer_nav(tmp_path):
    app = _make(tmp_path)
    nav = app._layer_nav("RUNID", "slides")
    assert nav.index("Presentation") < nav.index("Executive brief") \
        < nav.index("Full analysis")


def test_progress_page_does_not_talk_about_itself(tmp_path):
    """OBSERVED LIVE: 'Analysis progress', a raw run id, an unexplained
    PARTIAL badge, and 'These are real lifecycle stages, not decoration.'"""
    app = _make(tmp_path, transport=brightlake)
    c = _start_demo(app)
    csrf = c.csrf()
    _, headers, _ = c.request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf}&website={DEMO_URL}")
    _, _, body = c.request("GET", headers["Location"])
    for phrase in ("Analysis progress", "lifecycle stages",
                   "Open the result"):
        assert phrase not in body, f"page still says {phrase!r} to the reader"


def test_brief_stamp_carries_no_internal_version(tmp_path):
    app = _make(tmp_path)
    stamp = app._analysis_provenance("RUNID", "2026-07-28", "9.9.9-internal",
                                     "tok")
    assert "9.9.9-internal" not in stamp
    assert "produced by the current version of the product" not in stamp
    assert "Analysis version" not in stamp
    assert "source(s)" in stamp          # what the reader actually needs


# --- operator surfaces are not a guest surface -----------------------------

def test_a_demo_guest_cannot_read_the_operations_dashboard(tmp_path):
    """Seen on production: an anonymous guest who typed /dashboard was shown
    missing-credential names, the full deployed commit, scheduler state and
    status.json. The gate only asked whether a session existed, and a demo
    session is a session."""
    app = _make(tmp_path)
    c = _start_demo(app)
    for path in ("/dashboard", "/learning", "/assistant"):
        status, _, body = c.request("GET", path)
        assert status.startswith("404"), f"{path} reachable by a guest"
        for leak in ("TIINGO_API_KEY", "FRED_API_KEY", "status.json",
                     "scheduler"):
            assert leak not in body


def test_a_guest_can_find_their_own_analyses_again(tmp_path):
    """Closing the tab used to lose the result: no index, no history, and the
    only way back was a URL the reader no longer had."""
    app = _make(tmp_path, transport=brightlake)
    c = _start_demo(app)
    csrf = c.csrf()
    _, headers, _ = c.request(
        "POST", "/analyze", f"consent=on&csrf={csrf}&website={DEMO_URL}")
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    status, _, page = c.request("GET", "/analyses")
    assert status.startswith("200")
    assert run_id in page, "the analysis this session just ran is not listed"
    _, _, home = c.request("GET", "/")
    assert 'href="/analyses"' in home, "no route back to your own analyses"


def test_one_guest_cannot_see_another_guests_analyses(tmp_path):
    app = _make(tmp_path, transport=brightlake)
    owner = _start_demo(app)
    csrf = owner.csrf()
    _, headers, _ = owner.request(
        "POST", "/analyze", f"consent=on&csrf={csrf}&website={DEMO_URL}")
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    other = _start_demo(app)
    _, _, page = other.request("GET", "/analyses")
    assert run_id not in page


def test_a_limited_result_does_not_blame_the_company(tmp_path):
    """OBSERVED LIVE on Figma: the heading read "Not enough public evidence
    for Figma" -- directly above a body explaining that SOME kinds of evidence
    were missing and there were places left to look. The heading blamed the
    company for publishing too little; the body said the search was
    incomplete. Both cannot be true, and the heading is what a reader keeps."""
    app = _make(tmp_path)
    _, _, page = app._insufficient_evidence_page(
        None, "RUNID",
        {"insufficient_evidence": {
            "headline": "Some kinds of evidence are missing, and there are "
                        "places left to look.",
            "source_count": 4, "found": [], "missing": [], "unreadable": [],
            "actions": []}})
    assert "Limited analysis" in page
    assert "Not enough public evidence" not in page
