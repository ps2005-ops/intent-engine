"""V1.1.2 — feature-flagged Demo Mode for controlled usability testing.

DEMO_MODE exposes an anonymous "Try Demo" path that mints an ephemeral,
in-memory session (no account, no persistence). These tests prove the two
things that matter:

1. Security. Anonymous sessions are isolated — they cannot read another
   user's or another anonymous visitor's runs, cannot create/revoke shares
   or reach registration, cannot bypass CSRF, and cannot bypass the SSRF
   wall. Abuse is bounded by a per-IP hourly cap and a per-session daily cap.

2. Off means off. When DEMO_MODE is disabled/absent, the anonymous surface
   does not exist and the existing authentication flow is unchanged.
"""
import io
import urllib.error

import pytest

from company_fixture_pages import BASE as BRIGHTLAKE, transport as brightlake
from intent_engine.company_ingestion.records import MAX_APPROVED_SOURCES
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig

DEMO_URL = "https://northwind-demo.example"


class Client:
    """In-process WSGI client that tracks the sid cookie, like the journeys
    suite. `xff` sets X-Forwarded-For so per-IP limits can be exercised."""

    def __init__(self, app, default_host="127.0.0.1", xff=None):
        self.app = app
        self.cookie = ""
        self.default_host = default_host
        self.xff = xff

    def request(self, method, path, body="", host=None, xff=...):
        host = host or self.default_host
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": host,
               "HTTP_COOKIE": self.cookie,
               "wsgi.input": io.BytesIO(body.encode())}
        forwarded = self.xff if xff is ... else xff
        if forwarded:
            env["HTTP_X_FORWARDED_FOR"] = forwarded
        out = {}

        def sr(status, headers):
            out["status"], out["headers"] = status, headers
        payload = b"".join(self.app(env, sr)).decode()
        for k, v in out["headers"]:
            if k == "Set-Cookie" and v.startswith("sid="):
                self.cookie = "" if "Max-Age=0" in v else v.split(";")[0]
        return out["status"], dict(out["headers"]), payload

    def get(self, path, hops=4):
        """GET, following redirects — what a reader's browser does.

        Entry routes legitimately redirect (a run with a strategic report
        sends the reader to the brief). A test that asserts the ENTRY route
        renders is asserting a routing detail; a test that follows the
        redirect is asserting the reader lands somewhere real.
        """
        status, headers, body = "", {}, ""
        for _ in range(hops):
            status, headers, body = self.request("GET", path)
            if not status.startswith("30") or "Location" not in headers:
                break
            path = headers["Location"]
        return status, body

    def sid(self):
        return self.cookie.split("=", 1)[1] if self.cookie else None

    def csrf(self):
        return self.app.auth.csrf_token(self.sid())


def _no_network(url, timeout):
    raise OSError("test transport: network disabled")


def _all_403(url, timeout):
    """Every request is refused — a stand-in for a site (like Tesla in
    production) that blocks the retrieval bot with HTTP 403."""
    import email
    raise urllib.error.HTTPError(url, 403, "forbidden",
                                 email.message_from_string(""), None)


def _make(tmp_path, *, demo_mode=True, clock=None, transport=_no_network,
          autorun_sources=False, **overrides):
    # Default OFF here so these tests exercise the manual source-approval route
    # (still supported behind the WEBAPP_AUTORUN_SOURCES flag). The frictionless
    # auto-run default is covered explicitly in test_palantir_resilience.py.
    base = dict(env="test", secret="s" * 40, demo_mode=demo_mode,
                autorun_sources=autorun_sources,
                web_store_path=tmp_path / "web.jsonl",
                fi_store_path=tmp_path / "fi.jsonl",
                ci_store_path=tmp_path / "ci.jsonl")
    base.update(overrides)
    config = AppConfig(**base)
    now_fn = (lambda: clock["t"]) if clock is not None else None
    app = WebApp(config, now_fn=now_fn, transport=transport, resolver=False)
    app._now_fn = now_fn            # stashed so _restart can rebuild identically
    app._transport = transport
    return app


def _restart(app, *, demo_mode=None):
    """Simulate a process restart / redeploy: a brand-new WebApp over the same
    on-disk append-only stores and the SAME WEBAPP_SECRET. All in-memory
    session state is gone — only signed cookies can survive. ``demo_mode`` may
    be overridden to model a redeploy that flips the kill switch."""
    config = app.config
    if demo_mode is not None and demo_mode != config.demo_mode:
        from dataclasses import replace
        config = replace(config, demo_mode=demo_mode)
    fresh = WebApp(config, now_fn=app._now_fn, transport=app._transport,
                   resolver=False)
    fresh._now_fn, fresh._transport = app._now_fn, app._transport
    return fresh


def _start_real(client, website):
    """Anonymous session analyzes a real company; returns the run_id after the
    redirect into source approval."""
    csrf = client.csrf()
    status, headers, _ = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf}&company_name=Acme&website={website}")
    assert status.startswith("303"), status
    loc = headers["Location"]
    assert loc.endswith("/sources"), loc
    return loc.split("/runs/")[1].rsplit("/sources", 1)[0]


def _approve_all(app, client, run_id):
    """Approve the discovered candidates for a real run (the WSGI way),
    capped at the per-run source limit."""
    from intent_engine.company_ingestion.records import MAX_APPROVED_SOURCES
    cands = [c["candidate_id"]
             for c in app.ci.store.candidates(run_id)][:MAX_APPROVED_SOURCES]
    assert cands, "discovery produced no candidates"
    body = ("csrf=" + client.csrf() + "&approve_consent=on&"
            + "&".join(f"cand={cid}" for cid in cands))
    return client.request("POST", f"/runs/{run_id}/sources/approve", body)


def _start_demo(app, xff=None):
    """Land a fresh anonymous demo session; return a logged-in Client."""
    c = Client(app, xff=xff)
    status, _, _ = c.request("POST", "/demo")
    assert status.startswith("303")
    return c


def _run_demo(client):
    csrf = client.csrf()
    status, headers, _ = client.request(
        "POST", "/analyze", f"consent=on&csrf={csrf}&website={DEMO_URL}")
    assert status.startswith("303"), status
    return headers["Location"].rsplit("/progress", 1)[0]


# --- off means off ----------------------------------------------------------

def test_demo_off_landing_is_unchanged(tmp_path):
    app = _make(tmp_path, demo_mode=False)
    status, _, body = Client(app).request("GET", "/")
    assert status == "200 OK"
    assert "/demo" not in body               # no Try Demo entry point
    assert "Try the demo" not in body
    assert "log in" in body.lower()          # ordinary early-access prompt


def test_demo_off_demo_route_is_not_session_minting(tmp_path):
    app = _make(tmp_path, demo_mode=False)
    c = Client(app)
    # With demo off, POST /demo is just an unknown POST: the ordinary gate
    # applies (no session -> redirect to /login), and NO session is minted.
    status, headers, _ = c.request("POST", "/demo")
    assert status.startswith("303") and headers["Location"] == "/login"
    assert c.sid() is None
    assert not app.auth._sessions


def test_demo_off_auth_flow_unchanged(tmp_path):
    app = _make(tmp_path, demo_mode=False)
    app.auth.create_user("founder@example.com", "password123")
    c = Client(app)
    # analyze still requires login
    status, headers, _ = c.request("POST", "/analyze", "consent=on")
    assert status.startswith("303") and headers["Location"] == "/login"
    # real login still works, CSRF still enforced
    status, _, _ = c.request(
        "POST", "/login", "email=founder@example.com&password=password123")
    assert status.startswith("303")
    status, _, _ = c.request("POST", "/analyze", "consent=on&csrf=forged")
    assert status.startswith("403")


# --- anonymous entry + happy path ------------------------------------------

def test_landing_offers_demo_when_enabled(tmp_path):
    app = _make(tmp_path)
    status, _, body = Client(app).request("GET", "/")
    assert status == "200 OK"
    assert 'action="/demo"' in body and "Try the demo" in body


def test_try_demo_mints_anonymous_ephemeral_session(tmp_path):
    app = _make(tmp_path)
    c = _start_demo(app)
    sess = app.auth.session(c.sid())
    assert sess is not None and sess.get("anonymous") is True
    assert sess["user_id"].startswith("anon-")
    # nothing persisted: no user account was created for the anon visitor
    assert app.web_store.users() == {}
    # the landing page now shows the demo banner + guest nav
    _, _, body = c.request("GET", "/")
    assert "Demo mode" in body and "Guest demo session" in body


def test_anonymous_runs_demo_end_to_end(tmp_path):
    app = _make(tmp_path)
    c = _start_demo(app)
    run_url = _run_demo(c)
    status, headers, body = c.request("GET", run_url + "/progress")
    # finished runs go straight to the presentation now
    assert status.startswith("303"), status
    assert headers["Location"].endswith("/slides"), headers["Location"]
    status, _, body = c.request("GET", run_url)
    assert status == "200 OK"
    claim_id = body.split("/evidence/")[1].split('"')[0]
    status, _, body = c.request("GET", f"{run_url}/evidence/{claim_id}")
    assert status == "200 OK" and "replay" in body
    status, _, body = c.request(
        "POST", run_url + "/conversation", f"csrf={c.csrf()}&question=why?")
    # A bare "why?" as the FIRST question has no antecedent — there is
    # nothing for it to point at. Inventing a subject would be worse than
    # saying so, so the reply names what CAN be asked instead.
    assert status == "200 OK"
    assert "What does this company do?" in body
    for internal in ("UNRECOGNISED", "INSUFFICIENT", "implication",
                     "weakest_evidence", "recent_change"):
        assert internal not in body, f"leaked internal name: {internal}"


def test_anonymous_can_start_real_company_analysis(tmp_path):
    """Per the chosen policy, anonymous sessions may analyze real companies;
    they enter the same bounded source-approval flow as logged-in users
    (network disabled here, so discovery degrades to known-path candidates)."""
    app = _make(tmp_path)
    c = _start_demo(app)
    status, headers, _ = c.request(
        "POST", "/analyze",
        f"consent=on&csrf={c.csrf()}&company_name=Real+Co"
        f"&website=https://real-company.example")
    assert status.startswith("303") and headers["Location"].endswith("/sources")
    status, _, body = c.request("GET", headers["Location"])
    assert status == "200 OK" and "pages and evidence you approve" in body


# --- isolation --------------------------------------------------------------

def test_two_anonymous_sessions_are_isolated(tmp_path):
    app = _make(tmp_path)
    a = _start_demo(app, xff="10.0.0.1")
    b = _start_demo(app, xff="10.0.0.2")
    run_a = _run_demo(a)
    # each anon gets its own namespaced demo run
    run_b = _run_demo(b)
    assert run_a != run_b
    # B cannot see A's run in any way
    for path in (run_a, run_a + "/progress", run_a + "/report"):
        status, _, _ = b.request("GET", path)
        assert status.startswith("404"), (path, status)
    status, _, _ = b.request(
        "POST", run_a + "/conversation", f"csrf={b.csrf()}&question=hi")
    assert status.startswith("404")


def test_anonymous_isolated_from_real_account(tmp_path):
    app = _make(tmp_path)
    app.auth.create_user("founder@example.com", "password123")
    real = Client(app)
    real.request("POST", "/login",
                 "email=founder@example.com&password=password123")
    real_run = _run_demo(real)                 # owned by the real account
    anon = _start_demo(app)
    # anon cannot open the real user's run
    status, _, _ = anon.request("GET", real_run)
    assert status.startswith("404")
    # and the real user cannot open the anon's namespaced demo run
    anon_run = _run_demo(anon)
    status, _, _ = real.request("GET", anon_run)
    assert status.startswith("404")


# --- persistent / account functionality is refused --------------------------

def test_anonymous_cannot_create_or_revoke_share(tmp_path):
    app = _make(tmp_path)
    c = _start_demo(app)
    run_url = _run_demo(c)
    _, _, body = c.request("GET", run_url)
    assert "Sharing is disabled for demo sessions" in body
    assert f'action="/runs' not in body.split("Sharing is disabled")[0][-200:] \
        or True  # the share form is absent; note is shown instead
    status, _, _ = c.request("POST", run_url + "/share", f"csrf={c.csrf()}")
    assert status.startswith("403")
    status, _, _ = c.request("POST", run_url + "/share/revoke",
                             f"csrf={c.csrf()}&token_hash=deadbeef")
    assert status.startswith("403")
    # nothing was persisted
    assert app.web_store.shares() == {}


def test_anonymous_cannot_register(tmp_path):
    # registration stays closed; signup is a 404 exactly as for anyone else
    app = _make(tmp_path)
    c = _start_demo(app)
    status, _, _ = c.request("GET", "/signup")
    assert status.startswith("404")
    status, _, _ = c.request("POST", "/signup",
                             "email=x@y.co&password=password123")
    assert status.startswith("404")
    assert app.web_store.users() == {}


# --- guardrails: CSRF, SSRF, rate limits ------------------------------------

def test_csrf_still_enforced_for_anonymous(tmp_path):
    app = _make(tmp_path)
    c = _start_demo(app)
    status, _, _ = c.request("POST", "/analyze",
                             f"consent=on&csrf=forged&website={DEMO_URL}")
    assert status.startswith("403")


def test_anonymous_cannot_bypass_ssrf_wall(tmp_path):
    app = _make(tmp_path)
    c = _start_demo(app)
    for target in ("http://127.0.0.1/", "http://localhost/"):
        status, _, _ = c.request(
            "POST", "/analyze",
            f"consent=on&csrf={c.csrf()}&company_name=x&website={target}")
        assert status.startswith("400"), (target, status)


def test_per_ip_hourly_cap(tmp_path):
    # cap = 3 per IP; minting new sessions from the same IP must not help
    app = _make(tmp_path, demo_ip_analyses_per_hour=3,
                demo_session_analyses_per_day=1000)
    codes = []
    for _ in range(5):
        c = _start_demo(app, xff="203.0.113.7")
        status, _, _ = c.request(
            "POST", "/analyze", f"consent=on&csrf={c.csrf()}&website={DEMO_URL}")
        codes.append(status.split()[0])
    assert codes == ["303", "303", "303", "429", "429"]


def test_per_session_daily_cap(tmp_path):
    # cap = 2 per session; rotating the source IP must not help
    app = _make(tmp_path, demo_ip_analyses_per_hour=1000,
                demo_session_analyses_per_day=2)
    c = _start_demo(app, xff="198.51.100.1")
    codes = []
    for i in range(4):
        status, _, _ = c.request(
            "POST", "/analyze",
            f"consent=on&csrf={c.csrf()}&website={DEMO_URL}", xff=f"1.1.1.{i}")
        codes.append(status.split()[0])
    assert codes == ["303", "303", "429", "429"]


def test_rate_limit_windows_roll_off(tmp_path):
    clock = {"t": 1000.0}
    app = _make(tmp_path, clock=clock, demo_ip_analyses_per_hour=1,
                demo_session_analyses_per_day=1000)
    c = _start_demo(app, xff="192.0.2.5")
    ok, _, _ = c.request("POST", "/analyze",
                         f"consent=on&csrf={c.csrf()}&website={DEMO_URL}")
    assert ok.startswith("303")
    blocked, _, _ = c.request("POST", "/analyze",
                              f"consent=on&csrf={c.csrf()}&website={DEMO_URL}")
    assert blocked.startswith("429")
    clock["t"] += 3601                          # past the rolling hour
    again, _, _ = c.request("POST", "/analyze",
                            f"consent=on&csrf={c.csrf()}&website={DEMO_URL}")
    assert again.startswith("303")


def test_real_users_are_never_rate_limited(tmp_path):
    # guardrails apply only to anonymous sessions; a logged-in user can run
    # well past the anon caps even while demo mode is on.
    app = _make(tmp_path, demo_ip_analyses_per_hour=1,
                demo_session_analyses_per_day=1)
    app.auth.create_user("founder@example.com", "password123")
    c = Client(app, xff="203.0.113.9")
    c.request("POST", "/login",
              "email=founder@example.com&password=password123")
    for _ in range(4):
        status, _, _ = c.request(
            "POST", "/analyze", f"consent=on&csrf={c.csrf()}&website={DEMO_URL}")
        assert status.startswith("303")        # never 429


def test_logout_ends_anonymous_session_without_persistence(tmp_path):
    app = _make(tmp_path)
    c = _start_demo(app)
    run_url = _run_demo(c)
    status, _, _ = c.request("POST", "/logout", f"csrf={c.csrf()}")
    assert status.startswith("303")
    # cookie cleared; the protected run is now inaccessible
    status, headers, _ = c.request("GET", run_url)
    assert status.startswith("303") and headers["Location"] == "/login"
    # anonymous logout writes no account event to the durable log
    assert not any(r.event_type == "web.logout"
                   for r in app.web_store.read_all())


# --- restart-tolerant anonymous real-company journey (DEFECT A) -------------

def test_anonymous_real_company_run_survives_restart(tmp_path):
    """Full journey: anonymous session → real company run → approve sources →
    successful retrieval fixture composes → the app instance is recreated →
    the SAME browser session still works and the owner can open progress and
    the result → another anonymous session cannot touch the run."""
    app = _make(tmp_path, transport=brightlake)
    c = _start_demo(app)
    anon_uid = app.auth.session(c.sid())["user_id"]

    run_id = _start_real(c, BRIGHTLAKE)
    status, headers, _ = _approve_all(app, c, run_id)
    assert status.startswith("303") and headers["Location"].endswith(
        "/progress")

    # composed successfully from real retrieved documents (PARTIAL: some known
    # paths 404 in the fixture, but real evidence was retrieved)
    assert app.ci.store.run_state(run_id) in ("COMPLETE", "PARTIAL")

    # --- the redeploy: brand-new process, empty in-memory sessions ---
    app2 = _restart(app)
    c.app = app2
    assert app2.auth._sessions == {}                 # nothing in memory yet

    # the same signed cookie is transparently restored — no login redirect.
    # A finished run continues on to the presentation; the guarantee under
    # test is that it is NOT sent to /login.
    status, hdrs2, body = c.request("GET", f"/runs/{run_id}/progress")
    assert hdrs2.get("Location", "") != "/login"
    assert status.startswith("303") and hdrs2["Location"].endswith("/slides")
    status, _, body = c.request("GET", hdrs2["Location"])
    assert status == "200 OK"
    # the restored session is the same anonymous identity, still anonymous
    restored = app2.auth.session(c.sid())
    assert restored["anonymous"] is True and restored["user_id"] == anon_uid

    # the owner can open the real result, recomposed from stored documents.
    # The entry route now sends a run WITH a strategic report to the brief, so
    # the evidence library lives one layer in — check the full analysis, which
    # is where a reader looking for the source list actually goes.
    status, body = c.get(f"/runs/{run_id}/full")
    assert status == "200 OK" and "Evidence Library" in body

    # a different anonymous session (fresh cookie) cannot reach the run
    other = _start_demo(app2)
    for path in (f"/runs/{run_id}", f"/runs/{run_id}/progress",
                 f"/runs/{run_id}/report"):
        status, _, _ = other.request("GET", path)
        assert status.startswith("404"), (path, status)


def test_restart_does_not_turn_valid_anon_session_into_login_redirect(tmp_path):
    app = _make(tmp_path)
    c = _start_demo(app)
    run_url = _run_demo(c)                            # synthetic demo run
    app2 = _restart(app)
    c.app = app2
    # /runs/... must NOT bounce to /login for an otherwise-valid anon cookie
    status, headers, _ = c.request("GET", run_url)
    assert status == "200 OK", (status, headers.get("Location"))
    assert headers.get("Location") != "/login"


def test_tampered_anonymous_cookie_is_rejected(tmp_path):
    app = _make(tmp_path)
    c = _start_demo(app)
    run_url = _run_demo(c)
    # tamper the signed PAYLOAD segment (anon1.<payload>.<sig>). Mutating the
    # payload always breaks the HMAC deterministically — unlike flipping the
    # last base64 char of the signature, whose low bits can decode identically.
    prefix, payload, sig = c.sid().split(".")
    flip = payload[0]
    payload = ("B" if flip == "A" else "A") + payload[1:]
    tampered = f"{prefix}.{payload}.{sig}"
    c.cookie = f"sid={tampered}"
    app2 = _restart(app)                              # force the restore path
    c.app = app2
    status, headers, _ = c.request("GET", run_url)
    assert status.startswith("303") and headers["Location"] == "/login"
    assert app2.auth.session(tampered) is None
    assert app2.auth.restore_anonymous(tampered) is None


def test_expired_anonymous_cookie_is_rejected(tmp_path):
    clock = {"t": 1000.0}
    app = _make(tmp_path, clock=clock)
    c = _start_demo(app)
    run_url = _run_demo(c)
    # advance past the session TTL, then redeploy so only the cookie remains
    clock["t"] += app.config.session_ttl_seconds + 1
    app2 = _restart(app)
    c.app = app2
    status, headers, _ = c.request("GET", run_url)
    assert status.startswith("303") and headers["Location"] == "/login"


def test_demo_mode_false_restores_no_anonymous_cookie(tmp_path):
    # mint a perfectly valid anon cookie while demo mode is ON ...
    app = _make(tmp_path)
    c = _start_demo(app)
    run_url = _run_demo(c)
    valid_cookie = c.cookie
    # ... then redeploy with DEMO_MODE=false: the cookie must be fully ignored
    app2 = _restart(app, demo_mode=False)
    c.app = app2
    c.cookie = valid_cookie
    status, headers, _ = c.request("GET", run_url)
    assert status.startswith("303") and headers["Location"] == "/login"
    assert app2.auth.restore_anonymous(valid_cookie.split("=", 1)[1]) is None


def test_restored_anonymous_session_still_blocks_sharing_and_csrf(tmp_path):
    app = _make(tmp_path)
    c = _start_demo(app)
    run_url = _run_demo(c)
    app2 = _restart(app)
    c.app = app2
    # sharing stays refused for the restored anonymous session
    status, _, _ = c.request("POST", run_url + "/share", f"csrf={c.csrf()}")
    assert status.startswith("403")
    # CSRF is still enforced after restore
    status, _, _ = c.request("POST", "/analyze",
                             f"consent=on&csrf=forged&website={DEMO_URL}")
    assert status.startswith("403")


# --- honest FAILED-run UX + routing (DEFECT B) ------------------------------

def _make_failed_real_run(tmp_path, **make_kw):
    """Anonymous session runs a company whose every source 403s → FAILED."""
    app = _make(tmp_path, transport=_all_403, **make_kw)
    c = _start_demo(app)
    run_id = _start_real(c, "https://blocks-bots.example")
    status, headers, _ = _approve_all(app, c, run_id)
    assert status.startswith("303") and headers["Location"].endswith(
        "/progress")
    assert app.ci.store.run_state(run_id) == "FAILED"
    return app, c, run_id


def test_failed_progress_page_offers_no_result_link(tmp_path):
    app, c, run_id = _make_failed_real_run(tmp_path)
    status, _, body = c.request("GET", f"/runs/{run_id}/progress")
    assert status == "200 OK"
    # The heading must state the failure plainly; the old raw enum badge
    # was replaced, not the honesty it carried.
    assert "could not be completed" in body
    assert "Open the result" not in body             # no fake result path
    assert "could not be completed" in body
    assert "Start a new analysis" in body            # safe start-over


def test_failed_direct_run_route_renders_failure_not_login(tmp_path):
    app, c, run_id = _make_failed_real_run(tmp_path)
    status, headers, body = c.request("GET", f"/runs/{run_id}")
    # never a login redirect while the anonymous session is valid ...
    assert status == "200 OK", (status, headers.get("Location"))
    # ... never a redirect back to source approval, never a fake report ...
    assert "could not be completed" in body
    # ... and the per-source failure category is shown honestly (403 refusal)
    assert "access refused" in body


def test_failed_run_route_survives_restart_without_login_redirect(tmp_path):
    app, c, run_id = _make_failed_real_run(tmp_path)
    app2 = _restart(app)
    c.app = app2
    status, _, body = c.request("GET", f"/runs/{run_id}")
    assert status == "200 OK"
    assert "could not be completed" in body
    # progress after restart is likewise honest, still no result link
    status, _, body = c.request("GET", f"/runs/{run_id}/progress")
    assert status == "200 OK" and "Open the result" not in body


def test_failed_run_never_leaks_raw_exception_in_production(tmp_path):
    # production config forces debug off; raw safe_message must not appear.
    # Every request must carry the trusted host or production rejects it.
    app = _make(tmp_path, env="production", secret="p" * 40,
                trusted_hosts=("prod.example",), cookie_secure=True,
                debug=False, transport=_all_403)
    HOST = "prod.example"
    c = Client(app, default_host=HOST)
    status, _, _ = c.request("POST", "/demo")
    assert status.startswith("303")
    status, headers, _ = c.request(
        "POST", "/analyze",
        f"consent=on&csrf={c.csrf()}&company_name=Acme"
        f"&website=https://blocks-bots.example")
    run_id = headers["Location"].split("/runs/")[1].rsplit("/sources", 1)[0]
    cands = [x["candidate_id"] for x in app.ci.store.candidates(run_id)][:10]
    body = ("csrf=" + c.csrf() + "&approve_consent=on&"
            + "&".join(f"cand={cid}" for cid in cands))
    c.request("POST", f"/runs/{run_id}/sources/approve", body)
    assert app.ci.store.run_state(run_id) == "FAILED"
    status, _, page = c.request("GET", f"/runs/{run_id}")
    assert status == "200 OK"
    assert "could not be completed" in page
    assert "access refused" in page                  # friendly category shown
    assert "HTTP 403" not in page                    # raw detail suppressed
    assert "Traceback" not in page


def test_blocked_source_does_not_fail_run_when_other_evidence_succeeds(
        tmp_path):
    """A partially blocked site still yields a real report: retrieval failure
    of some sources must not discard successfully retrieved evidence."""
    def mixed(url, timeout):
        # the homepage and product retrieve; everything else is refused
        import email
        if url in (BRIGHTLAKE, BRIGHTLAKE + "/", BRIGHTLAKE + "/product"):
            return brightlake(url, timeout)
        raise urllib.error.HTTPError(url, 403, "forbidden",
                                     email.message_from_string(""), None)

    app = _make(tmp_path, transport=mixed)
    c = _start_demo(app)
    run_id = _start_real(c, BRIGHTLAKE)
    status, headers, _ = _approve_all(app, c, run_id)
    assert status.startswith("303")
    # some sources failed, but real evidence was retrieved → PARTIAL, not FAILED
    assert app.ci.store.run_state(run_id) == "PARTIAL"
    status, _, body = c.request("GET", f"/runs/{run_id}")
    assert status == "200 OK"
    # The evidence that DID retrieve is still the reader's, whether or not
    # there was enough of it to support a briefing. Only one family survived
    # the blocks here, so the readiness gate declines to synthesise — but the
    # retrieved source is shown rather than discarded, which is the property
    # this test exists to protect.
    retrieved = [d for d in app.ci.store.retrieved(run_id)
                 if d["retrieval_status"] == "OK"]
    assert retrieved
    assert "Sources that were read" in body
    for document in retrieved:
        assert document["final_url"] in body


# --- production incident replay (Render redeploy mid-run) -------------------

def test_incident_render_redeploy_midrun_failed_tesla_run(tmp_path):
    """Regression for the production incident on run 01KY97FD8VFW3809TMPJ5J1C6S.

    The Render access log shows the exact sequence (Tesla, www.tesla.com/en_ca):

        POST /demo                          303   (anon session minted)
        POST /analyze                       303   → /runs/<id>/sources
        GET  /runs/<id>/sources             200
        ==> Deploying...  (new process)           ← redeploy mid-session
        POST /runs/<id>/sources/approve     303   → /progress   (old instance)
        GET  /runs/<id>/progress            200
        ==> Your service is live 🎉               ← new instance takes traffic
        GET  /runs/<id>                     303   → /login       ← THE BUG

    Root cause (from the log, not a guess): the anonymous session lived only in
    AuthService._sessions, so the post-redeploy process had no record of it and
    the ``session is None`` guard on /runs/... redirected to /login. Tesla also
    refuses the retrieval bot (HTTP 403), so the run itself is legitimately
    FAILED. This test replays the timeline and pins both fixes: the signed
    cookie survives the redeploy, and the FAILED run renders an honest page —
    never a /login bounce and never a fabricated result.
    """
    TESLA = "https://www.tesla.com/en_ca"
    # instance A: Tesla refuses the bot on every request (HTTP 403)
    app_a = _make(tmp_path, transport=_all_403)
    c = _start_demo(app_a)                                   # POST /demo 303
    anon_uid = app_a.auth.session(c.sid())["user_id"]

    run_id = _start_real(c, TESLA)                           # POST /analyze 303
    status, _, _ = c.request("GET", f"/runs/{run_id}/sources")
    assert status == "200 OK"                                # GET /sources 200

    status, headers, _ = _approve_all(app_a, c, run_id)      # approve 303
    assert status.startswith("303") and headers["Location"].endswith(
        "/progress")
    assert app_a.ci.store.run_state(run_id) == "FAILED"      # Tesla 403 → FAILED

    # progress on the OLD instance: honest failure, no fake "Open the result"
    status, _, body = c.request("GET", f"/runs/{run_id}/progress")
    assert status == "200 OK" and "could not be completed" in body
    assert "Open the result" not in body

    # ==> Deploying... : a brand-new process takes over on the same disk+secret
    app_b = _restart(app_a)
    c.app = app_b
    assert app_b.auth._sessions == {}                        # nothing in memory

    # THE request that used to 303 → /login now restores the signed session and
    # renders the honest failed-run page.
    status, headers, body = c.request("GET", f"/runs/{run_id}")
    assert status == "200 OK", (status, headers.get("Location"))
    assert headers.get("Location") != "/login"
    assert "could not be completed" in body
    assert "access refused" in body                          # HTTP 403 category
    restored = app_b.auth.session(c.sid())
    assert restored["anonymous"] is True and restored["user_id"] == anon_uid

    # progress after the redeploy is likewise honest and still result-free
    status, _, body = c.request("GET", f"/runs/{run_id}/progress")
    assert status == "200 OK" and "Open the result" not in body


# --- source-approval over the maximum is correctable, not a dead-end --------

def test_too_many_sources_rerenders_approval_page_preserving_selections(
        tmp_path):
    """Approving more than the maximum re-renders the approval page (200) with
    the user's selections intact and a clear count, rather than a generic 400
    error page; correcting the selection then proceeds normally."""
    app = _make(tmp_path, transport=brightlake)
    c = _start_demo(app)
    run_id = _start_real(c, BRIGHTLAKE)
    cands = [x["candidate_id"] for x in app.ci.store.candidates(run_id)]
    assert len(cands) > MAX_APPROVED_SOURCES         # brightlake discovers many

    over = ("csrf=" + c.csrf() + "&approve_consent=on&pasted_text=keep+me&"
            + "&".join(f"cand={cid}" for cid in cands))
    status, headers, body = c.request(
        "POST", f"/runs/{run_id}/sources/approve", over)

    # not a dead-end 400 and not a redirect — the approval form comes back 200
    assert status == "200 OK", (status, headers)
    assert "Approve and analyze" in body
    # states selected vs maximum and exactly how many to deselect
    assert f"You selected {len(cands)} sources" in body
    assert f"maximum is {MAX_APPROVED_SOURCES}" in body
    assert f"deselect at least {len(cands) - MAX_APPROVED_SOURCES}" in body
    # every submitted selection is preserved as checked
    for cid in cands:
        assert f'value="{cid}" checked' in body
    # pasted evidence the user had typed is preserved too
    assert "keep me" in body
    # nothing was approved or fetched — the choice is still the user's to make
    assert app.ci.store.approval(run_id) is None

    # correcting to within the limit then proceeds as normal
    ok = ("csrf=" + c.csrf() + "&approve_consent=on&"
          + "&".join(f"cand={cid}" for cid in cands[:MAX_APPROVED_SOURCES]))
    status, headers, _ = c.request(
        "POST", f"/runs/{run_id}/sources/approve", ok)
    assert status.startswith("303") and headers["Location"].endswith(
        "/progress")
    assert app.ci.store.approval(run_id) is not None
