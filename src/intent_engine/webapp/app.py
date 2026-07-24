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
from intent_engine.company_ingestion.records import IngestionError
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
        form = self._form(environ) if method == "POST" else {}

        if method == "POST" and path not in ("/login", "/signup"):
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
        if path == "/logout" and method == "POST":
            self.auth.logout(sid)
            return self._redirect("/", clear_cookie=True)
        if path == "/analyze" and method == "POST":
            return self._analyze(session, form)
        if parts and parts[0] == "shared" and len(parts) == 2:
            return self._shared(parts[1])
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
                  500: "Something went wrong"}
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
        """The deterministic demo result for an owned run (idempotent rerun)."""
        if run_id not in self._results:
            result = self.fi.run(company_name=DEMO_COMPANY_NAME,
                                 website=f"https://{DEMO_DOMAIN}",
                                 claims_by_section=demo_claims(),
                                 as_of=DEMO_AS_OF)
            self._results[result["run_id"]] = result
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
        else:
            page = page.replace(
                '<form action="/analyze"',
                '<p><strong>Early access:</strong> <a href="/login">log in'
                '</a> to run an analysis.</p><form action="/analyze"', 1)
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

    def _analyze(self, session, form):
        if form.get("consent") is None:
            return self._error_page(400, "consent is required")
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
        if self._is_real_run(run_id):
            status = self.ci.store.run_state(run_id) or "VALIDATING_COMPANY"
        else:
            status = self.fi.run_status(run_id)
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<title>Analysis progress</title></head><body>'
                f'{self._nav(session, session["csrf"])}<main>'
                f'<h1>Analysis progress</h1>'
                f'<p>Run <code>{_e(run_id)}</code> status: '
                f'<strong>{_e(status)}</strong></p>'
                f'<p>These are real lifecycle stages, not decoration.</p>'
                f'<p><a href="/runs/{_e(run_id)}">Open the result</a></p>'
                f'</main></body></html>')
        return self._html(body)

    def _run_page(self, session, run_id):
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        if self._is_real_run(run_id):
            result = self._real_result(run_id)
            if result is None:
                return self._redirect(f"/runs/{run_id}/sources")
        else:
            result = self._result(run_id)
        if result is None:
            return self._error_page(404, "run result not found")
        csrf = session["csrf"]
        page = render_result_html(result)
        if result.get("overview"):
            overview_html = "".join(
                f'<p>{_e(s["text"])} <small>[{_e(", ".join(s["claim_ids"]))}]'
                f'</small></p>' for s in result["overview"])
            lib = result.get("evidence_library", {})
            lib_html = ""
            titles = {"company_website": "Company website",
                      "external_public": "External public evidence",
                      "user_provided": "User-provided evidence",
                      "unavailable_or_failed": "Unavailable or failed"}
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
                lib_html += (f'<h3>{titles.get(group, group)}</h3>'
                             f'<ul>{items}</ul>')
            page = page.replace(
                "<main>",
                f'<main><section aria-label="Executive overview">'
                f'<h2>Executive Overview</h2>{overview_html}</section>'
                f'<section aria-label="Evidence library">'
                f'<h2>Evidence Library</h2><p>This report is based only '
                f'on the approved sources listed below. It does not '
                f'represent internal company knowledge.</p>{lib_html}'
                f'</section>', 1)
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
                  f'<form action="/runs/{_e(run_id)}/share" method="post">'
                  f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
                  f'<button type="submit">Create share link</button></form>'
                  f'<form action="/runs/{_e(run_id)}/feedback" method="post">'
                  f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
                  f'<fieldset><legend>Was this useful?</legend>'
                  f'<label><input type="radio" name="useful" value="yes" '
                  f'required> Yes</label> '
                  f'<label><input type="radio" name="useful" value="partly">'
                  f' Partly</label> '
                  f'<label><input type="radio" name="useful" value="no">'
                  f' No</label></fieldset>'
                  f'<button type="submit">Send feedback</button></form>'
                  f'<p><a href="/runs/{_e(run_id)}/report">Executive report '
                  f'preview</a></p></section></main>')
        page = page.replace("</main>", extras, 1)
        return self._html(_chrome(page, self._nav(session, csrf)))

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
        flat_claims = self._run_claims(run_id)
        answer = self.fi.converse(run_id, form.get("question", ""),
                                  run_claims=flat_claims)
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

    # --- V1.1 real-company flow -------------------------------------------------
    def _is_real_run(self, run_id):
        return self.ci.run_meta(run_id) is not None

    def _sources_page(self, session, run_id):
        if not self._owned(session, run_id) or not self._is_real_run(run_id):
            return self._error_page(404, "no such run for this account")
        meta = self.ci.run_meta(run_id)
        candidates = self.ci.store.candidates(run_id)
        approval = self.ci.store.approval(run_id)
        if approval:
            return self._redirect(f"/runs/{run_id}/progress")
        csrf = session["csrf"]
        rows = "".join(
            f'<li><label><input type="checkbox" name="cand" '
            f'value="{_e(c["candidate_id"])}" '
            f'{"checked" if c["source_type"] in ("homepage", "product", "pricing", "about", "customers") else ""}> '
            f'<strong>{_e(c["source_type"])}</strong> — '
            f'<code>{_e(c["url"])}</code> '
            f'({_e(c["discovery_method"])}'
            f'{"" if c["same_domain"] else "; EXTERNAL"}'
            f'{"; unverified" if c.get("availability") == "UNVERIFIED" else ""})'
            f' · {_e(c["why_useful"])}</label></li>'
            for c in candidates)
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,'
                f'initial-scale=1"><title>Approve sources</title></head>'
                f'<body>{self._nav(session, csrf)}<main>'
                f'<h1>Choose the sources for this analysis</h1>'
                f'<p>We found these public pages on '
                f'<code>{_e(meta["domain"])}</code>. Founder Intelligence '
                f'analyzes only the pages and evidence you approve. '
                f'Public websites can be incomplete; a retrieved page may '
                f'be outdated; the report does not represent internal '
                f'company knowledge. The system does not automatically '
                f'contact, publish to, or modify any website.</p>'
                f'<form action="/runs/{_e(run_id)}/sources/approve" '
                f'method="post"><input type="hidden" name="csrf" '
                f'value="{_e(csrf)}"><ul>{rows}</ul>'
                f'<h2>Optional: paste external evidence</h2>'
                f'<p><label for="plabel">Source label</label> '
                f'<input id="plabel" name="pasted_label"></p>'
                f'<p><label for="porigin">Origin description</label> '
                f'<input id="porigin" name="pasted_origin"></p>'
                f'<p><label for="ptext">Pasted text</label> '
                f'<textarea id="ptext" name="pasted_text"></textarea></p>'
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
                self.ci.add_pasted(
                    run_id, user_id=session["user_id"],
                    label=form.get("pasted_label", "pasted evidence"),
                    origin=form.get("pasted_origin", "user"),
                    text=form["pasted_text"],
                    privacy="user_public_excerpt", authorized=True)
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
