"""V1.0.1 web experience — a stdlib WSGI application composing the frozen
Founder Intelligence service. No framework; no domain computation here.

Honesty boundaries carried into the web layer:
- live ingestion for arbitrary companies does not exist — the intake says
  so and offers the synthetic demo instead of pretending;
- every run is owned; every run view checks ownership; shares are the
  only anonymous read, and only of the report subset;
- error pages never leak tracebacks outside development.
"""
from __future__ import annotations

import html as _html
import json
import traceback
from urllib.parse import parse_qs

from intent_engine.founder_intelligence.fixtures import (
    DEMO_AS_OF, DEMO_COMPANY_NAME, DEMO_DOMAIN, demo_claims,
)
from intent_engine.founder_intelligence.presentation import (
    render_landing_html, render_report_preview, render_result_html,
)
from intent_engine.company_ingestion.records import (
    IngestionError, MAX_APPROVED_SOURCES,
)
from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.founder_intelligence.service import FounderIntelligenceService
from intent_engine.webapp.auth import AuthService, PASSWORD_RESET_STATUS
from intent_engine.webapp.records import WebAppError, WebEvent
from intent_engine.webapp.sharing import SharingService
from intent_engine.webapp.store import WebStore

_e = _html.escape

_SECURITY_HEADERS = [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
]


def _chrome(page_html: str, nav: str) -> str:
    """Inject the session nav into a full presentation-rendered page."""
    return page_html.replace("<body>", f"<body>{nav}", 1)


class WebApp:
    """The WSGI callable. All state-changing routes require login + CSRF."""

    def __init__(self, config, *, now_fn=None, transport=None,
                 resolver=None):
        config.validate()
        self.config = config
        self.web_store = WebStore(config.web_store_path)
        self.fi = FounderIntelligenceService(config.fi_store_path)
        self.ci = CompanyIngestionService(
            getattr(config, "ci_store_path", "data/company_ingestion.jsonl"),
            transport=transport, resolver=resolver)
        self.auth = AuthService(self.web_store, config, now_fn=now_fn)
        self.sharing = SharingService(self.web_store, now_fn=now_fn)
        self._results: dict = {}   # run_id -> composed result cache
        self._demo_ip_hits: dict = {}   # client_ip -> [analysis timestamps]

    # --- plumbing -------------------------------------------------------------
    def __call__(self, environ, start_response):
        try:
            status, headers, body = self._route(environ)
        except WebAppError as exc:
            status, headers, body = self._error_page(400, str(exc))
        except Exception:                                   # noqa: BLE001
            detail = (traceback.format_exc() if self.config.debug
                      else "An internal error occurred. It has been logged.")
            status, headers, body = self._error_page(500, detail)
        headers = headers + _SECURITY_HEADERS
        payload = body.encode()
        headers.append(("Content-Length", str(len(payload))))
        start_response(status, headers)
        return [payload]

    def _route(self, environ):
        if (self.config.env == "production"
                and environ.get("HTTP_HOST", "").split(":")[0]
                not in self.config.trusted_hosts):
            return self._error_page(400, "untrusted host")
        method = environ["REQUEST_METHOD"]
        path = environ.get("PATH_INFO", "/")
        sid = self._cookie(environ, "sid")
        session = self.auth.session(sid) if sid else None
        if session is None and sid and self.config.demo_mode:
            # Restart-tolerant anonymous demo sessions: the in-memory copy is
            # gone (e.g. after a redeploy), but a valid signed cookie can be
            # cryptographically verified and restored. Fully disabled — and so
            # the cookie fully ignored — whenever DEMO_MODE is off.
            session = self.auth.restore_anonymous(sid)
        form = self._form(environ) if method == "POST" else {}
        remote = self._client_ip(environ)

        # Every POST requires a live session + CSRF, EXCEPT the session-
        # minting routes (there is no prior session to protect). `/demo` is a
        # session-minting route ONLY while DEMO_MODE is on; when it is off,
        # `/demo` is just an unknown path and the ordinary gate applies, so
        # the authentication flow is byte-for-byte unchanged.
        post_exempt = ("/login", "/signup")
        if self.config.demo_mode:
            post_exempt = post_exempt + ("/demo",)
        if method == "POST" and path not in post_exempt:
            if session is None:
                return self._redirect("/login")
            if not self.auth.check_csrf(sid, form.get("csrf", "")):
                return self._error_page(403, "invalid CSRF token")

        parts = [p for p in path.split("/") if p]
        route = (method, parts[0] if parts else "", len(parts))

        if path == "/" and method == "GET":
            return self._landing(session)
        if path == "/healthz":
            return self._ok_json({"status": "ok"})
        if path == "/readyz":
            return self._ready()
        if path == "/onboarding" and method == "GET":
            return self._onboarding(session)
        if path == "/login":
            return (self._login_page(None) if method == "GET"
                    else self._login_post(form))
        if path == "/signup":
            return (self._signup_page() if method == "GET"
                    else self._signup_post(form))
        if (path == "/demo" and method == "POST"
                and self.config.demo_mode):
            new_sid = self.auth.create_anonymous_session()
            return self._redirect("/", set_sid=new_sid)
        if path == "/logout" and method == "POST":
            self.auth.logout(sid)
            return self._redirect("/", clear_cookie=True)
        if path == "/analyze" and method == "POST":
            return self._analyze(session, form, remote)
        if parts and parts[0] == "shared" and len(parts) == 2:
            return self._shared(parts[1])
        if parts and parts[0] == "bootstrap" and len(parts) == 2 \
                and method == "GET":
            return self._bootstrap(parts[1])
        if parts and parts[0] == "runs" and session is None:
            return self._redirect("/login")
        if route == ("GET", "runs", 2):
            return self._run_page(session, parts[1])
        if route == ("GET", "runs", 3) and parts[2] == "sources":
            return self._sources_page(session, parts[1])
        if route == ("POST", "runs", 4) and parts[2:] == ["sources",
                                                          "approve"]:
            return self._sources_approve(session, parts[1], form)
        if route == ("GET", "runs", 4) and parts[2] == "sources":
            return self._source_detail(session, parts[1], parts[3])
        if route == ("GET", "runs", 3) and parts[2] == "progress":
            return self._progress(session, parts[1])
        if route == ("GET", "runs", 3) and parts[2] == "report":
            return self._report(session, parts[1])
        if route == ("GET", "runs", 4) and parts[2] == "evidence":
            return self._evidence(session, parts[1], parts[3])
        if route == ("POST", "runs", 3) and parts[2] == "conversation":
            return self._converse(session, parts[1], form)
        if route == ("POST", "runs", 3) and parts[2] == "share":
            return self._share_create(session, parts[1])
        if route == ("POST", "runs", 4) and parts[2:] == ["share", "revoke"]:
            return self._share_revoke(session, parts[1], form)
        if route == ("POST", "runs", 3) and parts[2] == "feedback":
            return self._feedback(session, parts[1], form)
        return self._error_page(404, "page not found")

    # --- helpers --------------------------------------------------------------
    def _cookie(self, environ, name):
        raw = environ.get("HTTP_COOKIE", "")
        for part in raw.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                if k == name:
                    return v
        return None

    def _form(self, environ) -> dict:
        try:
            size = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            size = 0
        body = environ["wsgi.input"].read(min(size, 1_000_000)).decode()
        return {k: (",".join(v) if k == "cand" else v[0])
                for k, v in parse_qs(body).items()}

    def _client_ip(self, environ) -> str:
        """Best-effort client IP for demo rate-limiting. Prefers the left-most
        X-Forwarded-For hop (the original client as seen by an edge proxy such
        as Render), falling back to REMOTE_ADDR. X-Forwarded-For is client-
        spoofable, so this is a throttle, NOT a security boundary — the real
        boundaries are per-session isolation, the SSRF wall, and the refusal
        of persistent/account functionality to anonymous sessions."""
        xff = environ.get("HTTP_X_FORWARDED_FOR", "")
        if xff:
            first = xff.split(",")[0].strip()
            if first:
                return first
        return environ.get("REMOTE_ADDR", "") or "unknown"

    def _demo_rate_limited(self, session, remote):
        """Anonymous-session abuse guardrail. Enforces a per-IP rolling-hour
        cap and a per-session rolling-day cap on analyses. Returns a 429
        response to block, or None to allow (recording the hit against both
        windows). Real (logged-in) sessions are never limited here, so their
        behaviour is unchanged."""
        if not session.get("anonymous"):
            return None
        now = self.auth.now()
        hour_ago, day_ago = now - 3600, now - 86400
        ip_hits = [t for t in self._demo_ip_hits.get(remote, [])
                   if t > hour_ago]
        session_hits = [t for t in session.get("analyses", []) if t > day_ago]
        if len(ip_hits) >= self.config.demo_ip_analyses_per_hour:
            self._demo_ip_hits[remote] = ip_hits
            return self._error_page(
                429, "Demo analysis limit reached for your network; please "
                     "try again later.")
        if len(session_hits) >= self.config.demo_session_analyses_per_day:
            session["analyses"] = session_hits
            self._demo_ip_hits[remote] = ip_hits
            return self._error_page(
                429, "This demo session has reached its analysis limit for "
                     "today; please try again later.")
        ip_hits.append(now)
        session_hits.append(now)
        self._demo_ip_hits[remote] = ip_hits
        session["analyses"] = session_hits
        return None

    def _html(self, body, *, status="200 OK", extra_headers=()):
        return status, [("Content-Type", "text/html; charset=utf-8"),
                        *extra_headers], body

    def _ok_json(self, obj):
        return "200 OK", [("Content-Type", "application/json")], json.dumps(obj)

    def _redirect(self, where, *, set_sid=None, clear_cookie=False):
        headers = [("Location", where)]
        secure = "; Secure" if self.config.cookie_secure else ""
        if set_sid:
            headers.append(("Set-Cookie",
                            f"sid={set_sid}; HttpOnly; SameSite=Lax; "
                            f"Path=/{secure}"))
        if clear_cookie:
            headers.append(("Set-Cookie",
                            f"sid=deleted; Max-Age=0; Path=/{secure}"))
        return "303 See Other", headers, ""

    def _error_page(self, code, message):
        titles = {400: "Bad request", 403: "Forbidden", 404: "Not found",
                  429: "Too many requests", 500: "Something went wrong"}
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<title>{titles.get(code, "Error")}</title></head><body>'
                f'<main><h1>{titles.get(code, "Error")}</h1>'
                f'<p>{_e(message)}</p><p><a href="/">Back to start</a></p>'
                f'</main></body></html>')
        return f"{code} {titles.get(code, 'Error')}", \
            [("Content-Type", "text/html; charset=utf-8")], body

    def _nav(self, session, csrf=""):
        if session is None:
            return ('<nav aria-label="Session"><a href="/">Home</a> · '
                    '<a href="/login">Log in</a></nav>')
        if session.get("anonymous"):
            return (f'<nav aria-label="Session"><a href="/">Home</a> · '
                    f'<span>Guest demo session</span> '
                    f'<form action="/logout" method="post" '
                    f'style="display:inline">'
                    f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
                    f'<button type="submit">Leave demo</button></form></nav>')
        return (f'<nav aria-label="Session"><a href="/">Home</a> · '
                f'<a href="/onboarding">Getting started</a> · '
                f'signed in as {_e(session["email"])} '
                f'<form action="/logout" method="post" style="display:inline">'
                f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
                f'<button type="submit">Log out</button></form></nav>')

    def _owned(self, session, run_id):
        owner = self.web_store.owner_of(run_id)
        return owner is not None and owner == session["user_id"]

    def _result(self, run_id):
        """The deterministic demo result for an owned run (idempotent rerun).

        The synthetic demo is deterministic, so it can be recomputed rather
        than stored. Anonymous sessions namespace its run_id by user_id
        (``<base>--<user_id>``); we cache the recomputed result under the
        requested id too, so an owned demo run survives a process restart —
        the result is recomputed on demand while ownership persists durably in
        the web store."""
        if run_id not in self._results:
            result = self.fi.run(company_name=DEMO_COMPANY_NAME,
                                 website=f"https://{DEMO_DOMAIN}",
                                 claims_by_section=demo_claims(),
                                 as_of=DEMO_AS_OF)
            self._results[result["run_id"]] = result
            if run_id != result["run_id"]:
                self._results[run_id] = dict(result, run_id=run_id)
        return self._results.get(run_id)

    # --- pages ----------------------------------------------------------------
    def _landing(self, session):
        page = render_landing_html()
        csrf = session["csrf"] if session else ""
        if session:
            # the analyze form needs the CSRF token; inject it once
            page = page.replace('<form action="/analyze" method="post"',
                                f'<form action="/analyze" method="post" '
                                f'data-auth="1"', 1)
            page = page.replace('<button type="submit">',
                                f'<input type="hidden" name="csrf" '
                                f'value="{_e(csrf)}"><button type="submit">', 1)
            if session.get("anonymous"):
                page = page.replace(
                    '<main>',
                    '<main><p role="status"><strong>Demo mode.</strong> '
                    'You are in an anonymous, isolated demo session — no '
                    'sign-in, no access to anyone else\'s data, no share '
                    'links. Analyze a company below.</p>', 1)
        else:
            note = ('<p><strong>Early access:</strong> '
                    '<a href="/login">log in</a> to run an analysis.</p>')
            if self.config.demo_mode:
                # Feature-flagged anonymous entry point. Absent entirely when
                # DEMO_MODE is off, so the logged-out landing page is unchanged.
                note += ('<form action="/demo" method="post" '
                         'aria-label="Try the demo without logging in">'
                         '<button type="submit">Try the demo — no login '
                         'required</button></form>'
                         '<p class="trust-note">Demo sessions are anonymous '
                         'and isolated: they can analyze companies and read '
                         'reports, but cannot see anyone else\'s data or '
                         'create share links.</p>')
            page = page.replace('<form action="/analyze"',
                                note + '<form action="/analyze"', 1)
        return self._html(_chrome(page, self._nav(session, csrf)))

    def _onboarding(self, session):
        if session is None:
            return self._redirect("/login")
        csrf = session["csrf"]
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,'
                f'initial-scale=1"><title>Getting started</title></head><body>'
                f'{self._nav(session, csrf)}<main>'
                '<h1>Getting started</h1>'
                '<p>Founder Intelligence produces an evidence-backed, '
                'outside-in view of a company. In early access, live '
                'ingestion of arbitrary company websites is not yet '
                'available — start with the synthetic demo company to see '
                'the complete experience: proof of understanding first, '
                'then perspective, then a cited conversation.</p>'
                '<ol><li>Run the demo from the <a href="/">home page</a> '
                '(use any name and the demo website, or just submit the '
                'form).</li><li>Open each section and expand the evidence '
                'behind any claim.</li><li>Ask a follow-up question — every '
                'answer cites its sources.</li><li>Create a share link for '
                'your cofounder, and revoke it when done.</li></ol>'
                f'<p>Password reset: {_e(PASSWORD_RESET_STATUS)}.</p>'
                '</main></body></html>')
        return self._html(body)

    def _login_page(self, message):
        note = f'<p role="alert">{_e(message)}</p>' if message else ""
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,'
                f'initial-scale=1"><title>Log in</title></head><body>'
                f'{self._nav(None)}<main><h1>Log in</h1>{note}'
                '<form action="/login" method="post" aria-label="Log in">'
                '<p><label for="email">Email</label>'
                '<input id="email" name="email" type="email" required></p>'
                '<p><label for="password">Password</label>'
                '<input id="password" name="password" type="password" '
                'required></p><button type="submit">Log in</button></form>'
                + ('<p><a href="/signup">Create an account</a></p>'
                   if self.config.registration_open else
                   '<p>Early-access accounts are created by the '
                   'administrator.</p>')
                + f'<p>Password reset: {_e(PASSWORD_RESET_STATUS)}.</p>'
                '</main></body></html>')
        return self._html(body)

    def _login_post(self, form):
        try:
            sid = self.auth.login(form.get("email", ""),
                                  form.get("password", ""))
        except WebAppError as exc:
            status, headers, body = self._login_page(str(exc))
            return "401 Unauthorized", headers, body
        return self._redirect("/onboarding", set_sid=sid)

    def _signup_page(self):
        if not self.config.registration_open:
            return self._error_page(404, "registration is closed")
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<title>Sign up</title></head><body>{self._nav(None)}<main>'
                '<h1>Create your account</h1>'
                '<form action="/signup" method="post" aria-label="Sign up">'
                '<p><label for="email">Email</label>'
                '<input id="email" name="email" type="email" required></p>'
                '<p><label for="password">Password (8+ characters)</label>'
                '<input id="password" name="password" type="password" '
                'required minlength="8"></p>'
                '<button type="submit">Sign up</button></form>'
                '</main></body></html>')
        return self._html(body)

    def _signup_post(self, form):
        if not self.config.registration_open:
            return self._error_page(404, "registration is closed")
        self.auth.create_user(form.get("email", ""),
                              form.get("password", ""),
                              created_by=form.get("email", ""),
                              via_registration=True)
        sid = self.auth.login(form.get("email", ""), form.get("password", ""))
        return self._redirect("/onboarding", set_sid=sid)

    def _analyze(self, session, form, remote="unknown"):
        if form.get("consent") is None:
            return self._error_page(400, "consent is required")
        limited = self._demo_rate_limited(session, remote)
        if limited is not None:
            return limited
        website = form.get("website", f"https://{DEMO_DOMAIN}")
        if DEMO_DOMAIN not in website:
            # REAL company path: validate → discover → source approval.
            try:
                run = self.ci.create_run(
                    company_name=form.get("company_name", "")[:120]
                    or "(unnamed company)",
                    website=website, user_id=session["user_id"],
                    as_of=__import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc
                    ).strftime("%Y-%m-%dT00:00:00+00:00"))
            except (IngestionError, ValueError) as exc:
                return self._error_page(400, str(exc))
            run_id = run["run_id"]
            existing = self.web_store.owner_of(run_id)
            if existing is None:
                self.web_store.append(WebEvent(
                    event_type="web.run_owned", actor_type="human",
                    actor_id=session["user_id"], subject_type="run",
                    subject_id=run_id, idempotency_key=f"own:{run_id}",
                    payload={"user_id": session["user_id"],
                             "run_id": run_id}))
            elif existing != session["user_id"]:
                return self._error_page(403, "this run belongs to another "
                                             "account")
            self.ci.discover(run_id)
            return self._redirect(f"/runs/{run_id}/sources")
        result = self.fi.run(company_name=DEMO_COMPANY_NAME,
                             website=f"https://{DEMO_DOMAIN}",
                             claims_by_section=demo_claims(), as_of=DEMO_AS_OF)
        run_id = result["run_id"]
        if session.get("anonymous"):
            # The synthetic demo has one deterministic run id (no user_id in
            # its key), so without this every anonymous tester would collide
            # on it and all but the first would get a 403. Namespacing by the
            # session's unique user_id gives each anonymous visitor their own
            # isolated, owned demo run. Real (logged-in) runs are untouched.
            run_id = f'{run_id}--{session["user_id"]}'
        self._results[run_id] = result
        existing = self.web_store.owner_of(run_id)
        if existing is None:
            self.web_store.append(WebEvent(
                event_type="web.run_owned", actor_type="human",
                actor_id=session["user_id"], subject_type="run",
                subject_id=run_id,
                idempotency_key=f"own:{run_id}",
                payload={"user_id": session["user_id"], "run_id": run_id}))
        elif existing != session["user_id"]:
            # deterministic demo produces one run id; never reassign it
            return self._error_page(403, "this run belongs to another account")
        return self._redirect(f"/runs/{run_id}/progress")

    def _progress(self, session, run_id):
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        real = self._is_real_run(run_id)
        if real:
            status = self.ci.store.run_state(run_id) or "VALIDATING_COMPANY"
        else:
            status = self.fi.run_status(run_id)
            if status == "UNKNOWN":
                # A per-session (namespaced) anonymous demo run is not in the
                # FI store under its namespaced id; reconstruct the
                # deterministic result (restart-safe) and read its status.
                result = self._result(run_id)
                status = (result or {}).get("status") or status
        head = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<title>Analysis progress</title></head><body>'
                f'{self._nav(session, session["csrf"])}<main>'
                f'<h1>Analysis progress</h1>'
                f'<p>Run <code>{_e(run_id)}</code> status: '
                f'<strong>{_e(status)}</strong></p>')
        if status == "FAILED":
            # Honest terminal failure: NO "Open the result" — there is no
            # result. Explain why and offer a safe start-over.
            tail = (f'<p>This analysis could not be completed, so there is no '
                    f'result to open. {self._failure_explanation(run_id, real)}'
                    f'</p><p><a href="/runs/{_e(run_id)}">See the failure '
                    f'details</a> · <a href="/">Start a new analysis</a></p>')
        elif status in ("COMPLETE", "PARTIAL"):
            note = ('' if status == "COMPLETE" else
                    '<p>Some approved sources could not be retrieved; the '
                    'result is based only on the evidence that was.</p>')
            tail = (f'{note}<p>These are real lifecycle stages, not '
                    f'decoration.</p>'
                    f'<p><a href="/runs/{_e(run_id)}">Open the result</a></p>')
        else:
            # Still in flight: show the current lifecycle stage without ever
            # claiming a result already exists.
            tail = ('<p>These are real lifecycle stages, not decoration. This '
                    'analysis is still in progress — no result exists yet.</p>')
        return self._html(head + tail + '</main></body></html>')

    # --- honest failure surface (real-company runs) --------------------------
    _FAILURE_LABELS = {
        "http_403": ("access refused",
                     "the site refused automated access (HTTP 401/403)"),
        "http_429": ("rate limited",
                     "the site rate-limited automated requests (HTTP 429)"),
        "http_error": ("site error", "the site returned an HTTP error"),
        "blocked": ("blocked",
                    "the address was refused by the safety wall or a "
                    "DNS/policy check"),
        "timeout": ("timed out", "the site did not respond in time"),
        "connection": ("unreachable",
                       "the site could not be reached (DNS, TLS, or network)"),
        "too_large": ("too large", "the page exceeded the size budget"),
        "too_large_budget": ("skipped",
                             "the run's overall byte budget was reached"),
        "bad_mime": ("unsupported content",
                     "the page was not text or HTML"),
        "unsafe_redirect": ("unsafe redirect",
                            "the page redirected off the approved domain"),
        "parse_error": ("unreadable", "the page could not be decoded"),
        "javascript_only": ("javascript-only",
                            "the page required JavaScript and served no "
                            "readable text"),
    }

    def _failure_category(self, failure):
        """Map a stored failure record to a coarse, user-facing category —
        distinguishing HTTP rejection (403/429) from server errors, network
        failures, policy blocks, unsupported/JavaScript-only content, etc."""
        ftype = failure.get("failure_type", "")
        msg = str(failure.get("safe_message", ""))
        if ftype == "http_status":
            if "403" in msg or "401" in msg:
                return "http_403"
            if "429" in msg:
                return "http_429"
            return "http_error"
        if ftype == "too_large" and "budget" in msg:
            return "too_large_budget"
        return ftype

    def _failure_rows(self, run_id):
        """Per-source (candidate, short-label, human-explanation, detail).
        The raw ``safe_message`` (which can contain raw exception text) is
        included only in development — never in production."""
        rows = []
        for f in self.ci.store.failures(run_id):
            cat = self._failure_category(f)
            label, human = self._FAILURE_LABELS.get(
                cat, ("unavailable", "the source could not be retrieved"))
            detail = (f' — {_e(str(f.get("safe_message", ""))[:200])}'
                      if self.config.debug else '')
            rows.append((str(f.get("candidate_id", "")), label, human, detail))
        return rows

    def _failure_explanation(self, run_id, real):
        if not real:
            return "No evidence could be composed for this session."
        rows = self._failure_rows(run_id)
        if not rows:
            return ("No approved source could be retrieved, so there was not "
                    "enough evidence to produce a report.")
        cats = sorted({label for _, label, _, _ in rows})
        return ("Every approved source failed to retrieve (" +
                _e(", ".join(cats)) + "). Public sites can refuse automated "
                "access or require JavaScript; a failed retrieval is not "
                "evidence of real-world absence.")

    def _failed_run_page(self, session, run_id):
        """A clear, honest failed-run page for the run's owner. No fabricated
        report, no redirect to source approval, no login redirect (the caller
        has already confirmed ownership) and — in production — no stack traces,
        secrets, internal paths, or raw exception data."""
        rows = self._failure_rows(run_id) if self._is_real_run(run_id) else []
        items = "".join(
            f'<li><code>{_e(cid)}</code> — <strong>{_e(label)}</strong>: '
            f'{_e(human)}{detail}</li>'
            for cid, label, human, detail in rows)
        detail_block = (f'<h2>What happened to each source</h2><ul>{items}</ul>'
                        if items else '')
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,'
                f'initial-scale=1"><title>Analysis could not be completed'
                f'</title></head><body>{self._nav(session, session["csrf"])}'
                f'<main><h1>This analysis could not be completed</h1>'
                f'<p>Run <code>{_e(run_id)}</code> did not produce a report '
                f'because no approved source could be retrieved. There is no '
                f'result to show — we do not invent one.</p>'
                f'<p>Public websites can refuse automated access, rate-limit '
                f'requests, or require JavaScript to render. A failed '
                f'retrieval is not evidence that anything is missing in the '
                f'real world.</p>{detail_block}'
                f'<p><a href="/">Start a new analysis</a></p>'
                f'</main></body></html>')
        return self._html(body)

    def _run_page(self, session, run_id):
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        if self._is_real_run(run_id):
            # A FAILED real-company run has no report. Render an honest
            # failed-run page — never redirect back to source approval and
            # never present a nonexistent result.
            if self.ci.store.run_state(run_id) == "FAILED":
                return self._failed_run_page(session, run_id)
            result = self._real_result(run_id)
            if result is None:
                return self._redirect(f"/runs/{run_id}/sources")
            if result.get("status") == "FAILED" and not result.get("sections"):
                return self._failed_run_page(session, run_id)
        else:
            result = self._result(run_id)
        if result is None:
            return self._error_page(404, "run result not found")
        csrf = session["csrf"]
        share_form = (
            '<p><small>Sharing is disabled for demo sessions.</small></p>'
            if session.get("anonymous") else
            f'<form action="/runs/{_e(run_id)}/share" method="post">'
            f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
            f'<button type="submit">Create share link</button></form>')
        feedback_form = (
            f'<form action="/runs/{_e(run_id)}/feedback" method="post">'
            f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
            f'<fieldset><legend>Was this useful?</legend>'
            f'<label><input type="radio" name="useful" value="yes" required> '
            f'Yes</label> <label><input type="radio" name="useful" '
            f'value="partly"> Partly</label> <label><input type="radio" '
            f'name="useful" value="no"> No</label></fieldset>'
            f'<button type="submit">Send feedback</button></form>')

        # V1.2: when the run has a Strategic Intelligence Report it IS the
        # executive report. The legacy claim/evidence sections are quarantined
        # into a collapsed technical appendix so they never weaken the exec view.
        if result.get("strategic_report"):
            return self._strategic_run_page(session, run_id, result,
                                            share_form, feedback_form)

        page = render_result_html(result)
        if result.get("overview"):
            page = page.replace("<main>",
                                "<main>" + self._legacy_sections_html(
                                    run_id, result), 1)
        claim_links = "".join(
            f'<li><a href="/runs/{_e(run_id)}/evidence/'
            f'{_e(claim["claim_id"])}">{_e(claim["text"][:90])}</a></li>'
            for section in result.get("sections", [])
            for card in section.get("cards", [])
            for claim in card.get("claims", []))
        extras = (f'<section aria-label="Evidence index"><h2>Evidence '
                  f'index</h2><p>Every claim resolves to its exact source '
                  f'artifacts:</p><ul>{claim_links}</ul></section>'
                  f'<section aria-label="Actions"><h2>Actions</h2>'
                  f'<form action="/runs/{_e(run_id)}/conversation" '
                  f'method="post"><input type="hidden" name="csrf" '
                  f'value="{_e(csrf)}"><label for="q">Ask a follow-up '
                  f'question</label> <input id="q" name="question" required>'
                  f'<button type="submit">Ask</button></form>'
                  f'{share_form}{feedback_form}'
                  f'<p><a href="/runs/{_e(run_id)}/report">Executive report '
                  f'preview</a></p></section></main>')
        page = page.replace("</main>", extras, 1)
        return self._html(_chrome(page, self._nav(session, csrf)))

    def _legacy_sections_html(self, run_id, result):
        """The legacy executive-overview + evidence-library HTML (used inline
        for non-strategic runs, or inside the technical appendix otherwise)."""
        overview_html = "".join(
            f'<p>{_e(s["text"])} <small>[{_e(", ".join(s["claim_ids"]))}]'
            f'</small></p>' for s in result.get("overview", []))
        lib = result.get("evidence_library", {})
        titles = {"company_website": "Company website",
                  "external_public": "External public evidence",
                  "user_provided": "User-provided evidence",
                  "unavailable_or_failed": "Unavailable or failed"}
        lib_html = ""
        for group, entries in lib.items():
            if not entries:
                continue
            items = "".join(
                f'<li>{_e(str(e.get("title") or e.get("origin", "")))} '
                f'— <code>{_e(str(e.get("origin", "")))}</code>'
                + (f' · <a href="/runs/{_e(run_id)}/sources/'
                   f'{_e(self._source_id_for(run_id, e))}">detail</a>'
                   if group != "unavailable_or_failed" else
                   f' · {_e(str(e.get("failure_type", "")))}: '
                   f'{_e(str(e.get("message", ""))[:80])}')
                + '</li>' for e in entries)
            lib_html += f'<h3>{titles.get(group, group)}</h3><ul>{items}</ul>'
        return (f'<section aria-label="Executive overview">'
                f'<h2>Executive Overview</h2>{overview_html}</section>'
                f'<section aria-label="Evidence library">'
                f'<h2>Evidence Library</h2><p>This report is based only on the '
                f'approved sources listed below. It does not represent internal '
                f'company knowledge.</p>{lib_html}</section>')

    def _suggested_questions(self, report):
        """Company-specific follow-ups derived from the report, not generic."""
        hyps = report.get("hypotheses", [])
        qs = []
        if hyps:
            top = hyps[0]
            qs.append(f"What evidence most weakens the "
                      f"{top['title'].split(' (')[0].lower()} thesis?")
            comps = top.get("comparables", [])
            if comps:
                qs.append(f"How is this transition similar to {comps[0]}, and "
                          f"where does the comparison break down?")
        if report.get("agenda"):
            qs.append("What is likely being debated internally right now?")
        qs.append("Which recent event makes this timely?")
        qs.append("What changed in the last six months?")
        return qs[:5]

    def _strategic_run_page(self, session, run_id, result, share_form,
                            feedback_form):
        from intent_engine.strategic_intelligence.render import (
            render_strategic_report,
        )
        csrf = session["csrf"]
        report = result["strategic_report"]
        strat = render_strategic_report(report)
        # company-specific suggested questions, each a one-click ask
        suggested = "".join(
            f'<form action="/runs/{_e(run_id)}/conversation" method="post" '
            f'style="display:inline-block;margin:3px">'
            f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
            f'<input type="hidden" name="question" value="{_e(q)}">'
            f'<button type="submit" class="ghost">{_e(q)}</button></form>'
            for q in self._suggested_questions(report))
        actions = (
            f'<section aria-label="Intelligence assistant"><h2>Ask the '
            f'intelligence assistant</h2>'
            f'<form action="/runs/{_e(run_id)}/conversation" method="post">'
            f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
            f'<label for="q">Your question</label> '
            f'<input id="q" name="question" required style="min-width:60%">'
            f'<button type="submit">Ask</button></form>'
            f'<p class="muted">Suggested, company-specific:</p>{suggested}'
            f'{share_form}{feedback_form}</section>')
        # legacy content quarantined; never in the primary executive flow
        appendix = (
            f'<details><summary>Technical appendix — legacy source extraction'
            f'</summary>{self._legacy_sections_html(run_id, result)}</details>')
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,'
                f'initial-scale=1"><title>Strategic Intelligence — '
                f'{_e(report.get("company_name", ""))}</title></head><body>'
                f'{self._nav(session, csrf)}<main>{strat}{actions}{appendix}'
                f'</main></body></html>')
        return self._html(body)

    def _evidence(self, session, run_id, claim_id):
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        result = self._result(run_id)
        for section in result.get("sections", []):
            for card in section.get("cards", []):
                for claim in card.get("claims", []):
                    if claim.get("claim_id") == claim_id:
                        refs = "".join(
                            f'<li><code>{_e(r.get("artifact_type"))}:'
                            f'{_e(r.get("artifact_id"))}</code> · replay '
                            f'<code>{_e(r.get("replay_id"))}</code> · '
                            f'freshness {_e(r.get("freshness_status"))} · '
                            f'as-of {_e(r.get("as_of"))}</li>'
                            for r in claim.get("source_refs", []))
                        body = (f'<!doctype html><html lang="en"><head>'
                                f'<meta charset="utf-8"><title>Evidence'
                                f'</title></head><body>'
                                f'{self._nav(session, session["csrf"])}'
                                f'<main><h1>Evidence</h1>'
                                f'<p>{_e(claim.get("text"))}</p>'
                                f'<p>Availability: '
                                f'{_e(claim.get("availability"))} · '
                                f'Confidence: {_e(claim.get("confidence"))}'
                                f'</p><ul>{refs}</ul>'
                                f'<p><a href="/runs/{_e(run_id)}">Back to '
                                f'result</a></p></main></body></html>')
                        return self._html(body)
        return self._error_page(404, "no such claim in this run")

    def _source_id_for(self, run_id, entry):
        for record in self.ci.store.retrieved(run_id):
            if record["final_url"] == entry.get("origin"):
                return record["source_id"]
        return ""

    def _run_claims(self, run_id):
        """Current-run ClaimSet only: real claims for real runs, demo
        claims for the synthetic demo. Never mixed."""
        if self._is_real_run(run_id):
            from intent_engine.company_ingestion.claims import build_claims
            meta = self.ci.run_meta(run_id)
            claims = build_claims(documents=self.ci.store.retrieved(run_id),
                                  company_name=meta["company_name"],
                                  domain=meta["domain"])
            return [c for group in claims.values()
                    if isinstance(group, list) for c in group]
        return [c for group in demo_claims().values()
                if isinstance(group, list) for c in group]

    def _converse(self, session, run_id, form):
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        question = form.get("question", "")
        # Prefer a strategic answer when the run has a strategic report and the
        # question maps to one of its hypotheses: reasoning chain + citations +
        # counter-evidence + confidence + falsification, not a card echo.
        strat = self._strategic_report_for(run_id)
        if strat is not None:
            from intent_engine.strategic_intelligence.conversation import (
                answer_strategic,
            )
            sa = answer_strategic(question, strat)
            if sa["intent"] in ("EXPLAINED", "COMPARISON"):
                return self._strategic_answer_page(session, run_id, sa)
        flat_claims = self._run_claims(run_id)
        answer = self.fi.converse(run_id, question, run_claims=flat_claims)
        paragraphs, citations = [], []
        for p in (answer.get("answer") or {}).get("paragraphs", []):
            paragraphs.append(f'<p>{_e(p.get("text", ""))}</p>')
            citations.extend(str(c) for c in p.get("citations", []))
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<title>Answer</title></head><body>'
                f'{self._nav(session, session["csrf"])}<main>'
                f'<h1>Answer</h1>'
                f'<p>Intent: {_e(str(answer.get("intent", "")))}</p>'
                f'{"".join(paragraphs)}'
                f'<p>Cited artifacts: {_e(", ".join(citations) or "none")}</p>'
                f'<p><small>Answers use only this run\'s approved evidence. '
                f'A source that is not part of the approved evidence set '
                f'must be added and approved before analysis.</small></p>'
                f'<p><a href="/runs/{_e(run_id)}">Back to result</a></p>'
                f'</main></body></html>')
        return self._html(body)

    def _strategic_report_for(self, run_id):
        """The run's strategic report dict, if it has one (real runs only)."""
        if not self._is_real_run(run_id):
            return None
        result = self._real_result(run_id)
        return result.get("strategic_report") if result else None

    def _strategic_answer_page(self, session, run_id, sa):
        routing = sa.get("routing", {})
        label = (f'<p class="muted"><small>Discussing hypothesis '
                 f'<strong>{_e(str(routing.get("selected_hypothesis") or "—"))}'
                 f'</strong>'
                 + (f' · comparison: <strong>'
                    f'{_e(str(routing.get("selected_comparable")))}</strong>'
                    if routing.get("selected_comparable") else "")
                 + f' · operation: {_e(str(routing.get("operation", "")))}'
                 f'</small></p>')
        back = (f'<p><a href="/runs/{_e(run_id)}">Back to report</a></p>'
                f'<p><small>Outside-in only; grounded in this run\'s approved '
                f'observations and the curated pattern library.</small></p>')

        if sa["intent"] == "COMPARISON":
            c = sa["comparison"]
            def _ul(items):
                return "".join(f"<li>{_e(x)}</li>" for x in items if x)
            ev = "".join(
                f'<li>“{_e(x["excerpt"])}” — <strong>{_e(x["source_title"])}'
                f'</strong> <em>({_e(x["source_class"])})</em></li>'
                for x in c["supporting_evidence"])
            body = (f'<!doctype html><html lang="en"><head>'
                    f'<meta charset="utf-8"><title>Comparison</title></head>'
                    f'<body>{self._nav(session, session["csrf"])}<main>'
                    f'<h1>Comparison: {_e(c["comparable"])}</h1>{label}'
                    f'<p><strong>{_e(c["direct_answer"])}</strong></p>'
                    f'<h2>Shared mechanism</h2><p>{_e(c["shared_mechanism"])}</p>'
                    f'<h2>Key similarities</h2><ul>{_ul(c["key_similarities"])}</ul>'
                    f'<h2>Key differences</h2><ul>{_ul(c["key_differences"])}</ul>'
                    f'<h2>Where the analogy breaks</h2>'
                    f'<p>{_e(c["where_the_analogy_breaks"])}</p>'
                    f'<h2>Strategic implication</h2>'
                    f'<p>{_e(c["strategic_implication"])}</p>'
                    f'<h2>Confidence &amp; missing evidence</h2>'
                    f'<p>{_e(str(c["confidence"]))} — {_e(c["missing_evidence"])}</p>'
                    f'<h2>Supporting evidence</h2><ul>{ev}</ul>{back}'
                    f'</main></body></html>')
            return self._html(body)

        a = sa["answer"]
        ev = "".join(
            f'<li>“{_e(x["excerpt"])}” — <strong>{_e(x["source_title"])}</strong> '
            f'<em>({_e(x["source_class"])}'
            f'{", " + _e(x["date"]) if x.get("date") else ""})</em></li>'
            for x in a["evidence"])
        counter = ("".join(
            f'<li>“{_e(x["excerpt"])}” — {_e(x["source_title"])} '
            f'({_e(x["source_class"])})</li>' for x in a["counter_evidence"])
            or f'<li>{_e(a["counter_note"])}</li>')
        reasons = "".join(f'<li>{_e(x)}</li>' for x in a["confidence_reasons"])
        falsify = "".join(f'<li>{_e(x)}</li>' for x in a["falsification"])
        alts = "".join(f'<li>{_e(x)}</li>'
                       for x in a.get("alternative_explanations", []))
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<title>Strategic answer</title></head><body>'
                f'{self._nav(session, session["csrf"])}<main>'
                f'<h1>Strategic answer</h1>{label}'
                f'<p><strong>{_e(a["direct_answer"])}</strong></p>'
                f'<p>{_e(a["reasoning"])}</p>'
                f'<h2>Strongest supporting evidence</h2><ul>{ev}</ul>'
                f'<h2>Counter-evidence</h2><ul>{counter}</ul>'
                f'<h2>Alternative explanations</h2><ul>{alts}</ul>'
                f'<h2>Confidence: {_e(str(a["confidence"]))}</h2><ul>{reasons}</ul>'
                f'<h2>What would change my view</h2><ul>{falsify}</ul>'
                f'<p><strong>Decision this affects:</strong> '
                f'{_e(a["decision"])}</p>{back}</main></body></html>')
        return self._html(body)

    def _report(self, session, run_id):
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        preview = render_report_preview(self._result(run_id))
        sections = "".join(f'<li>{_e(s["kind"])}</li>'
                           for s in preview.get("sections", []))
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<title>Executive report preview</title></head><body>'
                f'{self._nav(session, session["csrf"])}<main>'
                f'<h1>Executive report preview</h1>'
                f'<p>This preview contains only the shareable subset — no '
                f'private notes, no internal metadata.</p>'
                f'<ul>{sections}</ul>'
                f'<p><a href="/runs/{_e(run_id)}">Back to result</a></p>'
                f'</main></body></html>')
        return self._html(body)

    def _share_create(self, session, run_id):
        if session.get("anonymous"):
            return self._error_page(403, "sharing is not available in demo "
                                         "mode")
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        token = self.sharing.create_share(run_id=run_id,
                                          owner_id=session["user_id"])
        share_hash = __import__("hashlib").sha256(token.encode()).hexdigest()
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<title>Share link created</title></head><body>'
                f'{self._nav(session, session["csrf"])}<main>'
                f'<h1>Share link created</h1>'
                f'<p>This link shows only the executive report subset. It '
                f'expires automatically and can be revoked below. The link '
                f'is shown once — we store only its hash.</p>'
                f'<p><code>/shared/{_e(token)}</code></p>'
                f'<form action="/runs/{_e(run_id)}/share/revoke" '
                f'method="post"><input type="hidden" name="csrf" '
                f'value="{_e(session["csrf"])}">'
                f'<input type="hidden" name="token_hash" '
                f'value="{_e(share_hash)}">'
                f'<button type="submit">Revoke this link</button></form>'
                f'<p><a href="/runs/{_e(run_id)}">Back to result</a></p>'
                f'</main></body></html>')
        return self._html(body)

    def _share_revoke(self, session, run_id, form):
        if session.get("anonymous"):
            return self._error_page(403, "sharing is not available in demo "
                                         "mode")
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        self.sharing.revoke_share(token_hash=form.get("token_hash", ""),
                                  owner_id=session["user_id"])
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<title>Share revoked</title></head><body>'
                f'{self._nav(session, session["csrf"])}<main>'
                f'<h1>Share link revoked</h1>'
                f'<p><a href="/runs/{_e(run_id)}">Back to result</a></p>'
                f'</main></body></html>')
        return self._html(body)

    def _feedback(self, session, run_id, form):
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        meta = self.ci.run_meta(run_id)
        self.fi.record_feedback(run_id,
                                meta["domain"] if meta else DEMO_DOMAIN,
                                useful=form.get("useful", "partly"),
                                note=form.get("note", ""),
                                actor_id=session["user_id"])
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<title>Thanks</title></head><body>'
                f'{self._nav(session, session["csrf"])}<main>'
                f'<h1>Thank you</h1><p>Feedback recorded as founder input — '
                f'it never silently changes the intelligence.</p>'
                f'<p><a href="/runs/{_e(run_id)}">Back to result</a></p>'
                f'</main></body></html>')
        return self._html(body)

    def _shared(self, token):
        run_id = self.sharing.resolve(token)
        if run_id is None:
            return self._error_page(404, "this share link is not available "
                                         "(missing, revoked, or expired)")
        preview = render_report_preview(self._result(run_id) or {})
        sections = "".join(f'<li>{_e(s["kind"])}</li>'
                           for s in preview.get("sections", []))
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<meta name="robots" content="noindex,nofollow">'
                f'<title>Shared executive report</title></head><body><main>'
                f'<h1>Shared executive report</h1>'
                f'<p>A read-only, evidence-backed executive report subset. '
                f'No private notes; no internal metadata.</p>'
                f'<ul>{sections}</ul></main></body></html>')
        return self._html(body, extra_headers=(
            ("X-Robots-Tag", "noindex, nofollow"),))

    # --- one-time staging-user bootstrap (V1.1.1) --------------------------------
    def _bootstrap(self, supplied_token):
        """GET /bootstrap/{token} — exists only while all three bootstrap
        env vars are set; single use; constant-time token comparison;
        never echoes any secret; generic 404 on every failure path so
        nothing is learnable from responses."""
        import hashlib as _hashlib
        import hmac as _hmac
        config = self.config
        if not (config.bootstrap_email and config.bootstrap_password_hash
                and config.bootstrap_token):
            return self._error_page(404, "page not found")
        token_hash = _hashlib.sha256(
            config.bootstrap_token.encode()).hexdigest()
        consumed = any(
            row.event_type == "web.bootstrap_consumed"
            and row.payload.get("token_hash") == token_hash
            for row in self.web_store.read_all())
        if consumed:
            return self._error_page(404, "page not found")
        if not _hmac.compare_digest(supplied_token or "",
                                    config.bootstrap_token):
            return self._error_page(404, "page not found")
        if self.auth.store.user_by_email(
                config.bootstrap_email.strip().lower()) is not None:
            return self._error_page(404, "page not found")
        # consume FIRST (persistent), then create — a failure after this
        # point burns the token, which is the safe direction.
        self.web_store.append(WebEvent(
            event_type="web.bootstrap_consumed", actor_type="system",
            actor_id="bootstrap", subject_type="bootstrap",
            subject_id=token_hash[:16],
            idempotency_key=f"bootstrap:{token_hash}",
            payload={"token_hash": token_hash}))
        self.auth.create_user_with_hash(config.bootstrap_email,
                                        config.bootstrap_password_hash)
        body = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<title>Account created</title></head><body><main>'
                '<h1>Early-access account created</h1>'
                '<p>Your account is ready. This link has been consumed and '
                'will not work again. Remove the bootstrap environment '
                'variables and redeploy.</p>'
                '<p><a href="/login">Log in</a></p></main></body></html>')
        return self._html(body)

    # --- V1.1 real-company flow -------------------------------------------------
    def _is_real_run(self, run_id):
        return self.ci.run_meta(run_id) is not None

    def _sources_page(self, session, run_id, *, selected_ids=None,
                      message=None, pasted=None):
        if not self._owned(session, run_id) or not self._is_real_run(run_id):
            return self._error_page(404, "no such run for this account")
        meta = self.ci.run_meta(run_id)
        candidates = self.ci.store.candidates(run_id)
        approval = self.ci.store.approval(run_id)
        if approval:
            return self._redirect(f"/runs/{run_id}/progress")
        csrf = session["csrf"]
        pasted = pasted or {}

        def _checked(c):
            # On a re-render (e.g. too many sources) honour exactly what the
            # user had selected; on first render fall back to the sensible
            # default set.
            if selected_ids is not None:
                return "checked" if c["candidate_id"] in selected_ids else ""
            return ("checked" if c["source_type"] in
                    ("homepage", "product", "pricing", "about", "customers")
                    else "")

        def _row(c):
            note = c.get("why_relevant") or c.get("why_useful", "")
            return (
                f'<li><label><input type="checkbox" name="cand" '
                f'value="{_e(c["candidate_id"])}" {_checked(c)}> '
                f'<strong>{_e(c["source_type"])}</strong> — '
                f'<code>{_e(c["url"])}</code> '
                f'({_e(c["discovery_method"])}'
                f'{"" if c["same_domain"] else "; EXTERNAL"}'
                f'{"; unverified" if c.get("availability") == "UNVERIFIED" else ""})'
                f' · {_e(note)}</label></li>')

        # Group candidates by strategic source class so the founder sees WHAT
        # kind of evidence they are approving, not a flat list of URLs.
        class_titles = {
            "company_owned": "Company-owned pages",
            "executive_statement": "Executive statements (company-published)",
            "investor_material": "Investor material (company-published)",
            "customer_voice": "Customer evidence (independent)",
            "competitor": "Competitor evidence (independent)",
            "independent_reporting": "Independent reporting",
        }
        rows = ""
        for cls, title in class_titles.items():
            group = [c for c in candidates
                     if c.get("source_class", "company_owned") == cls]
            if not group:
                continue
            rows += (f'<h3>{title}</h3><ul>'
                     + "".join(_row(c) for c in group) + '</ul>')
        alert = (f'<p role="alert"><strong>{_e(message)}</strong></p>'
                 if message else '')
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,'
                f'initial-scale=1"><title>Approve sources</title></head>'
                f'<body>{self._nav(session, csrf)}<main>'
                f'<h1>Choose the sources for this analysis</h1>{alert}'
                f'<p>We found candidate evidence for '
                f'<code>{_e(meta["domain"])}</code>, organized by source '
                f'class. Founder Intelligence analyzes only the pages and '
                f'evidence you approve. A strong strategic report needs more '
                f'than company-owned pages — approve executive, investor, '
                f'customer, competitor, or independent sources for a '
                f'cross-source view. You may approve at most '
                f'{MAX_APPROVED_SOURCES} sources per analysis. Public websites '
                f'can be incomplete or outdated; the report does not represent '
                f'internal company knowledge. The system does not '
                f'automatically contact, publish to, or modify any '
                f'website.</p>'
                f'<form action="/runs/{_e(run_id)}/sources/approve" '
                f'method="post"><input type="hidden" name="csrf" '
                f'value="{_e(csrf)}">{rows}'
                f'<h2>Add independent evidence (bounded, explicit)</h2>'
                f'<p>Paste a short excerpt from an independent source — '
                f'reporting, an executive interview, or a competitor page — '
                f'and classify it. This is the safe, no-crawl way to add a '
                f'cross-source vantage point.</p>'
                f'<p><label for="plabel">Source label</label> '
                f'<input id="plabel" name="pasted_label" '
                f'value="{_e(pasted.get("pasted_label", ""))}"></p>'
                f'<p><label for="porigin">Origin description</label> '
                f'<input id="porigin" name="pasted_origin" '
                f'value="{_e(pasted.get("pasted_origin", ""))}"></p>'
                f'<p><label for="pclass">Source class</label> '
                f'<select id="pclass" name="pasted_class">'
                f'<option value="independent_reporting">Independent reporting'
                f'</option><option value="customer_voice">Customer voice'
                f'</option><option value="competitor">Competitor</option>'
                f'<option value="executive_statement">Executive statement'
                f'</option><option value="investor_material">Investor material'
                f'</option></select></p>'
                f'<p><label for="ptext">Pasted text</label> '
                f'<textarea id="ptext" name="pasted_text">'
                f'{_e(pasted.get("pasted_text", ""))}</textarea></p>'
                f'<p><label><input type="checkbox" name="pasted_authorized">'
                f' I am authorized to provide this text; it is included '
                f'only because I approve it.</label></p>'
                f'<p><label><input type="checkbox" name="approve_consent" '
                f'required> I approve retrieval and analysis of the '
                f'selected public pages.</label></p>'
                f'<button type="submit">Approve and analyze</button></form>'
                f'</main></body></html>')
        return self._html(body)

    def _sources_approve(self, session, run_id, form):
        if not self._owned(session, run_id) or not self._is_real_run(run_id):
            return self._error_page(404, "no such run for this account")
        if form.get("approve_consent") is None:
            return self._error_page(400, "explicit approval is required")
        # parse_qs collapsed to first value in _form; re-read all checkboxes
        approved = form.get("cand_all") or form.get("cand", "")
        approved_ids = [x for x in approved.split(",") if x] \
            if approved else []
        candidates = self.ci.store.candidates(run_id)
        # Too many sources is a correctable user choice, not an error: re-render
        # the approval page with their selections intact and tell them exactly
        # how many to deselect, instead of a dead-end 400 page.
        if len(approved_ids) > MAX_APPROVED_SOURCES:
            excess = len(approved_ids) - MAX_APPROVED_SOURCES
            return self._sources_page(
                session, run_id, selected_ids=set(approved_ids),
                pasted={k: form.get(k, "") for k in
                        ("pasted_label", "pasted_origin", "pasted_text")},
                message=(f"You selected {len(approved_ids)} sources, but the "
                         f"maximum is {MAX_APPROVED_SOURCES} per analysis. "
                         f"Please deselect at least {excess} "
                         f"source{'s' if excess != 1 else ''} before "
                         f"continuing."))
        rejected = [c["candidate_id"] for c in candidates
                    if c["candidate_id"] not in approved_ids]
        try:
            self.ci.approve(run_id, user_id=session["user_id"],
                            approved_ids=approved_ids,
                            rejected_ids=rejected)
            if (form.get("pasted_text") or "").strip():
                if form.get("pasted_authorized") is None:
                    return self._error_page(400, "pasted evidence requires "
                                                 "authorization confirmation")
                pasted_class = form.get("pasted_class", "independent_reporting")
                if pasted_class not in (
                        "independent_reporting", "customer_voice", "competitor",
                        "executive_statement", "investor_material"):
                    pasted_class = "independent_reporting"
                self.ci.add_pasted(
                    run_id, user_id=session["user_id"],
                    label=form.get("pasted_label", "pasted evidence"),
                    origin=form.get("pasted_origin", "user"),
                    text=form["pasted_text"],
                    privacy="user_public_excerpt", authorized=True,
                    source_class=pasted_class)
            self.ci.fetch_approved(run_id)
            self._results[run_id] = self.ci.compose(run_id,
                                                    fi_service=self.fi)
        except IngestionError as exc:
            return self._error_page(400, str(exc))
        return self._redirect(f"/runs/{run_id}/progress")

    def _source_detail(self, session, run_id, source_id):
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        for record in self.ci.store.retrieved(run_id):
            if record["source_id"] == source_id:
                body = (f'<!doctype html><html lang="en"><head>'
                        f'<meta charset="utf-8"><title>Source detail</title>'
                        f'</head><body>'
                        f'{self._nav(session, session["csrf"])}<main>'
                        f'<h1>{_e(record.get("title") or source_id)}</h1>'
                        f'<p>Origin: <code>{_e(record["final_url"])}</code> '
                        f'· type {_e(record["source_type"])} · retrieved '
                        f'{_e(record["retrieved_at"][:19])} · hash '
                        f'<code>{_e(record["content_hash"][:12])}</code> · '
                        f'parser {_e(record["parser_version"])} · '
                        f'freshness {_e(record["freshness"])}</p>'
                        f'<p>{_e(record.get("origin_note", ""))}</p>'
                        f'<h2>Extracted text</h2>'
                        f'<pre style="white-space:pre-wrap">'
                        f'{_e(record["text_content"][:8000])}</pre>'
                        f'<p><a href="/runs/{_e(run_id)}">Back to report'
                        f'</a></p></main></body></html>')
                return self._html(body)
        return self._error_page(404, "no such source in this run")

    def _real_result(self, run_id):
        if run_id not in self._results:
            if self.ci.store.approval(run_id) is None:
                return None
            self._results[run_id] = self.ci.compose(run_id,
                                                    fi_service=self.fi)
        return self._results.get(run_id)

    def _ready(self):
        try:
            self.config.validate()
            self.web_store.read_all()
            self.fi.store.read_all()
            return self._ok_json({"status": "ready", "env": self.config.env})
        except Exception as exc:                            # noqa: BLE001
            return ("503 Service Unavailable",
                    [("Content-Type", "application/json")],
                    json.dumps({"status": "not ready", "reason": str(exc)}))


def make_server(app, host="127.0.0.1", port=0):
    """A threading WSGI server for local/production-smoke use."""
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import WSGIServer, make_server as _make

    class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    return _make(host, port, app, server_class=ThreadingWSGIServer)
