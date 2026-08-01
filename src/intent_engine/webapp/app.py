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

import hmac
import html as _html
import json
import pathlib
import logging
import traceback
import uuid
from urllib.parse import parse_qs

# Unhandled-request errors go here. stderr is what the deployment platform
# captures, so this is the difference between a 500 that can be diagnosed and
# one that leaves only an access-log line.
_LOG = logging.getLogger("intent_engine.webapp")

from intent_engine.founder_intelligence.fixtures import (
    DEMO_AS_OF, DEMO_COMPANY_NAME, DEMO_DOMAIN, demo_claims,
)
from intent_engine.founder_intelligence.presentation import (
    _BASE_CSS as _APP_CSS,
    render_landing_html, render_report_preview, render_result_html,
)
from intent_engine.company_ingestion.entities import (
    AMBIGUOUS, name_from_domain, resolve_choice, resolve_entity,
)
from intent_engine.strategic_intelligence.editorial import is_meaningful
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

# The brief is the default landing surface, so its contrast is not a detail.
# Every foreground/background pair here is at or above WCAG AA for its size.
def central_view_after_headline(thesis: str, headline_view: str) -> str:
    """What "The central view" should say once the headline has spoken.

    OBSERVED LIVE on Sentry: the brief said "Sentry acquired Codecov." in the
    headline block and then again, ten words below, under "The central view".
    `headline.view` IS the thesis's first sentence -- see `_build_headline` --
    so a single-sentence thesis was printed twice in a 250-500 word brief
    whose stated design rule is that nothing gets a second slot.

    The headline keeps the claim, because that is the block written for a
    reader who will not scroll. This returns what the headline did NOT say,
    which is "" when the thesis was only that one sentence -- and an empty
    section renders as nothing at all.

    A thesis that does not open with the headline is returned untouched: the
    two are then saying different things, and both belong on the page.
    """
    thesis = " ".join((thesis or "").split())
    lead = " ".join((headline_view or "").split())
    if lead and thesis.startswith(lead):
        return thesis[len(lead):].strip()
    return thesis


_BRIEF_CSS = """
<style>
.brief{--ink:#111827;--muted:#4b5563;--line:#d1d5db;--bg:#ffffff;
--panel:#f8fafc;--accent:#1d4ed8;--accent-ink:#ffffff;
font:17px/1.65 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
color:var(--ink);background:var(--bg);
max-width:38rem;margin:0 auto;padding:8px 18px 40px}
.brief h1{font-size:1.75rem;line-height:1.2;margin:.4rem 0 .2rem}
.brief h2{font-size:.82rem;text-transform:uppercase;letter-spacing:.06em;
color:var(--muted);margin:1.6rem 0 .35rem;font-weight:700}
.brief p{margin:0 0 .5rem}
.brief .stamp{color:var(--muted);font-size:.86rem;margin-bottom:1.2rem}
.brief .b-part{border-top:1px solid var(--line);padding-top:.2rem}
.brief .b-headline{background:var(--panel);border:1px solid var(--line);
border-left:3px solid var(--accent);border-radius:6px;
padding:.9rem 1rem;margin:0 0 1.1rem}
.brief .b-headline .hl-does{font-size:1.02rem}
.brief .b-headline .hl-view{font-weight:600}
.brief .b-headline .hl-conf{color:var(--muted);font-size:.88rem;margin:0}
.brief ul,.brief ol{margin:.2rem 0;padding-left:1.2rem}
.brief li{margin:0 0 .5rem}
.brief .when{font-size:.78rem;font-weight:700;color:var(--muted);
margin-right:.5rem}
.brief a{color:var(--accent);text-decoration:underline}
.brief .layers{display:flex;gap:14px;flex-wrap:wrap;font-size:.9rem;
padding:10px 0;border-bottom:1px solid var(--line);margin-bottom:8px}
.brief .layers strong{color:var(--ink)}
.brief .b-act{display:flex;gap:10px;flex-wrap:wrap;margin:1.8rem 0 1rem}
.brief .b-act a{display:inline-block;padding:10px 18px;border-radius:9px;
border:1px solid var(--line);text-decoration:none;color:var(--ink);
font-weight:600;font-size:.95rem}
.brief .b-act a.primary{background:var(--accent);color:var(--accent-ink);
border-color:var(--accent)}
.brief a:focus-visible,.brief button:focus-visible,
.brief input:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.brief .b-ask{border-top:1px solid var(--line);padding-top:1rem}
.brief .b-ask label{display:block;font-size:.86rem;color:var(--muted);
margin-bottom:.35rem}
.brief .b-ask input{padding:9px 11px;border:1px solid var(--line);
border-radius:8px;font-size:1rem;min-width:60%;background:var(--bg);
color:var(--ink)}
.brief .b-ask button{padding:9px 16px;border-radius:8px;border:0;
background:var(--accent);color:var(--accent-ink);font-weight:600;
font-size:.95rem;cursor:pointer}
@media (max-width:600px){.brief{font-size:16px;padding:6px 14px 30px}
.brief h1{font-size:1.45rem}.brief .b-ask input{min-width:100%}}
@media (prefers-color-scheme:dark){
.brief{--ink:#f3f4f6;--muted:#c3cad6;--line:#3a4454;--bg:#0f141c;
--panel:#161c26;--accent:#7aa2ff;--accent-ink:#0b1220}}
@media print{.brief .layers,.brief .b-act,.brief .b-ask{display:none}
.brief{max-width:none}}
</style>
"""

# The floor every page meets, whatever else it brings. Deliberately small and
# additive — it grants visible focus, a readable dark scheme, a responsive
# minimum and print rules, and takes no design decisions that could fight a
# page's own stylesheet. Applied last so it wins on the properties it sets.
_A11Y_CSS = """
<style>
:where(a,button,input,select,textarea,summary,[tabindex]):focus-visible{
outline:3px solid #1d4ed8;outline-offset:2px}
img,svg,video,table{max-width:100%}
pre,code{overflow-x:auto;max-width:100%}
@media (max-width:600px){
body{font-size:16px}
main{padding-left:14px;padding-right:14px}
table{display:block;overflow-x:auto}}
@media (prefers-color-scheme:dark){
:root{color-scheme:dark}
body{background:#0f141c;color:#f3f4f6}
a{color:#7aa2ff}
:where(h1,h2,h3,h4,h5,h6){color:#f3f4f6}
/* NOT :where() — that zeroes specificity, so these lost to the very class
   rules they correct and the panels stayed light under a dark scheme. */
:root .card,:root .chip,:root .agenda,:root details,
:root fieldset{background:#161c26;border-color:#3a4454}
:root .muted,:root .state,:root .limitation,:root small{color:#c3cad6}
/* Components that define their own palette as custom properties (.brief and
   .deck) kept LIGHT values in dark mode: the body went near-black while
   var(--panel) stayed #f8fafc and var(--ink) stayed near-white, so the layer
   nav rendered near-white text on a near-white bar at 1.04:1 — the tab you
   were on was invisible. Re-point the variables rather than restyle
   everything that uses them.

   Two things here are load-bearing and easy to undo by accident:

   1. The :root prefix. .brief and .deck ship their CSS in the BODY, which
      lands after this stylesheet, so a bare `.deck` selector loses the
      cascade to the very rule it is correcting. :root outranks it.
   2. The absence of :where(). :where() zeroes specificity, so those rules
      would lose to any plain class selector — including all of these. */
:root .brief,:root .deck{--ink:#f3f4f6;--muted:#c3cad6;--line:#3a4454;
--bg:#0f141c;--panel:#161c26;--accent:#7aa2ff;--accent-ink:#0f141c}
:root nav,:root .trust-note,:root .panel{background:#161c26;
border-color:#3a4454;color:#c3cad6}
:root nav a,:root nav a:visited,:root nav button,
:root details summary{color:#7aa2ff}
:root code,:root pre{background:#1b2230;color:#e5e7eb}
/* Buttons keep a white background from the base sheet; inheriting the dark
   scheme's near-white text on it renders them at 1.1:1 — unreadable. */
:root button,:root input,:root select,:root textarea{background:#1b2230;
color:#f3f4f6;border-color:#3a4454}
:root .why,:root .alt,:root .q,:root .unavailable,:root .state,
:root .limitation,:root .muted,:root .when{color:#c3cad6}
/* Deck surfaces that hard-code a light literal rather than var(--panel), and
   so survived the variable re-pointing above: the citations drawer (#fafaff)
   and the slide action buttons (white). Both need a selector at least as
   specific as the deck's own. */
:root .deck .cites,:root details.cites{background:#161c26;
border-color:#3a4454}
:root .deck .act button,:root .deck .act a,:root .deck .nav a,
:root .deck button{background:#1b2230;color:#f3f4f6;border-color:#3a4454}
/* The full-analysis document (.si) carries its OWN dark palette, defined
   beside its own stylesheet in the strategic-intelligence renderer. Do not
   add .si rules here: overriding that palette from outside fights it instead
   of completing it, and measurably makes contrast worse. */}
@media print{
nav,form,.actions,.b-act,.layers{display:none!important}
body{background:#fff;color:#000}}
</style>
"""

_ONBOARDING_CSS = """
<style>
.onboarding{border:1px solid var(--line);border-radius:14px;
background:var(--panel);padding:20px 22px;margin:12px 0 22px}
.onboarding h1{font-size:1.4rem;margin:0 0 .2rem}
.onboarding h2{font-size:.82rem;text-transform:uppercase;letter-spacing:.06em;
color:var(--muted);margin:1.2rem 0 .3rem;font-weight:700}
.onboarding .ob-part{border-top:0}
.onboarding ul{margin:.2rem 0;padding-left:1.15rem}
.onboarding li{margin:0 0 .35rem}
.onboarding dl.glossary{margin:.3rem 0}
.onboarding dl.glossary dt{font-weight:700;margin-top:.6rem}
.onboarding dl.glossary dd{margin:.1rem 0 0;color:var(--muted)}
.onboarding .ob-dismiss{margin-top:1.4rem}
.onboarding .ob-dismiss a,.onboarding .ob-dismiss button{display:inline-block;
padding:10px 18px;border-radius:9px;background:var(--accent);
color:var(--accent-ink);text-decoration:none;font-weight:600;border:0;
font-size:.95rem;cursor:pointer}
@media print{.onboarding{display:none}}
</style>
"""

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
        from pathlib import Path as _Path
        from intent_engine.strategic_intelligence.store import StrategicMemory
        ci_path = _Path(getattr(config, "ci_store_path",
                                "data/company_ingestion.jsonl"))
        # co-locate strategic state with the ingestion store (tmp in tests,
        # data/ in production) so tests never write into the repo.
        self.strategic_memory = StrategicMemory(
            ci_path.parent / "strategic_state.jsonl")
        # Runtime root — the ONE location the runtime jobs (scheduler) read and
        # write. In production this is the persistent disk (RUNTIME_ROOT); in
        # tests/dev it co-locates with the other stores. The web layer's
        # learning/paper/personal reads MUST use this same root, or the
        # dashboard would show a different (empty) location than where the
        # scheduler actually writes — a real production config-drift bug.
        import os as _os
        self._runtime_root = _Path(
            _os.environ.get("RUNTIME_ROOT") or ci_path.parent)
        # Read-only observation surface over the learning platform (Learning
        # Ledger + Paper book), exposed to the founder through Personal AI.
        # No bus here: the web layer only READS — it never proposes, evaluates,
        # promotes, or trades.
        from intent_engine.learning import LearningLedger
        from intent_engine.learning.inspection import PlatformLearningReader
        from intent_engine.paper import PaperTradingLoop
        from intent_engine.personal.service import PersonalService
        self._learning_reader = PlatformLearningReader(
            LearningLedger(self._runtime_root / "learning_ledger.db"),
            PaperTradingLoop(self._runtime_root / "paper_book.db"))
        self._personal = PersonalService(
            self._runtime_root / "personal.jsonl",
            learning_reader=self._learning_reader)
        # In-process scheduler (the deployable scheduling path — Render disks
        # are single-service, so scheduled jobs run inside the web service to
        # share the append-only stores). Disabled unless SCHEDULER_ENABLED, so
        # tests and dev never spawn the thread.
        self._scheduler = None
        from intent_engine.runtime.scheduler import Scheduler
        if Scheduler.enabled():
            self._scheduler = Scheduler(self._runtime_root).start()
        self._results: dict = {}   # run_id -> composed result cache
        self._demo_ip_hits: dict = {}   # client_ip -> [analysis timestamps]
        # run_id -> the last answered topics, so a bare "Why?" has a subject.
        self._conversation_context: dict = {}
        # Storage durability is MEASURED, once, at startup. Recording this
        # boot is what makes the next boot able to prove survival: finding an
        # earlier boot id in the ledger means a previous process wrote a file,
        # ended, and the file is still here. Until that has been observed the
        # honest answer is "unproven", and the feedback form says so rather
        # than promising a persistence nobody has checked.
        from intent_engine.webapp.feedback import FeedbackLog
        from intent_engine.webapp.storage_state import EPHEMERAL_LIKELY, probe_storage, record_boot
        record_boot(self._runtime_root)
        self._storage = probe_storage(self._runtime_root)
        self.feedback_log = FeedbackLog(self._runtime_root)

    # --- plumbing -------------------------------------------------------------
    def __call__(self, environ, start_response):
        try:
            status, headers, body = self._route(environ)
        except WebAppError as exc:
            status, headers, body = self._error_page(400, str(exc))
        except Exception:                                   # noqa: BLE001
            # The message used to promise "It has been logged" while the
            # traceback was only ever computed when debug was on — in
            # production it was formatted nowhere, written nowhere, and
            # discarded. A 500 left nothing behind but an access-log line, so
            # the one artefact needed to diagnose it never existed. Log it
            # unconditionally, to stderr, which the platform captures.
            #
            # The error id is the bridge: the user can quote it, and an
            # operator can grep for it, without any internal detail crossing
            # the boundary.
            error_id = uuid.uuid4().hex[:12]
            _LOG.exception("unhandled error %s handling %s %s", error_id,
                           environ.get("REQUEST_METHOD", "?"),
                           environ.get("PATH_INFO", "?"))
            detail = (traceback.format_exc() if self.config.debug
                      else (f"An internal error occurred and has been "
                            f"recorded (reference {error_id}). Quote this "
                            f"reference if you report it."))
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

        # THE FIRST-THIRTY-SECONDS FIX.
        #
        # A first-time visitor filled in the company form on the landing page,
        # ticked the consent box, pressed the primary button -- and was thrown
        # to a login page that offers no signup and says "Password reset: NOT
        # AVAILABLE". Their input was discarded. The demo was reachable only by
        # noticing a DIFFERENT button and pressing it BEFORE filling the form.
        #
        # In demo mode an anonymous /analyze is not an attack, it is the
        # product's entire purpose. There is no session to forge a request
        # against and no user data to reach, which is exactly why /demo is
        # already exempt above. So mint the session and carry the form through.
        minted_sid = None
        if (method == "POST" and path == "/analyze" and session is None
                and self.config.demo_mode):
            minted_sid = self.auth.create_anonymous_session()
            session = self.auth.session(minted_sid)
            sid = minted_sid

        if method == "POST" and path not in post_exempt:
            if session is None:
                return self._redirect("/login")
            # A session minted one line ago cannot have issued the token in
            # this form, and there is nothing yet to protect.
            if minted_sid is None and not self.auth.check_csrf(
                    sid, form.get("csrf", "")):
                return self._error_page(403, "invalid CSRF token")

        parts = [p for p in path.split("/") if p]
        route = (method, parts[0] if parts else "", len(parts))

        if path == "/" and method == "GET":
            return self._landing(session)
        if path == "/healthz":
            return self._ok_json({"status": "ok"})
        if path == "/readyz":
            return self._ready()
        if path == "/version":
            from intent_engine._version import version_info
            return self._ok_json(version_info())
        if path == "/onboarding" and method == "GET":
            return self._onboarding(session)
        if path == "/onboarding/dismiss" and method == "POST":
            if session is not None:
                session["onboarding_dismissed"] = True
            return self._redirect("/")
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
            result = self._analyze(session, form, remote,
                                   smoke=self._is_smoke_test(environ))
            if minted_sid:
                # carry the new demo session onto whatever the analysis
                # returned, so the user stays signed into it
                secure = "; Secure" if self.config.cookie_secure else ""
                status, headers, body = result
                headers = list(headers) + [
                    ("Set-Cookie", f"sid={minted_sid}; HttpOnly; "
                                   f"SameSite=Lax; Path=/{secure}")]
                return status, headers, body
            return result
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
        if route == ("GET", "runs", 3) and parts[2] == "brief":
            return self._brief_page(session, parts[1])
        if route == ("GET", "runs", 3) and parts[2] == "slides":
            return self._slides_page(session, parts[1])
        if route == ("GET", "runs", 3) and parts[2] == "full":
            return self._run_page(session, parts[1], layer="full")
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
        if route == ("POST", "runs", 3) and parts[2] == "retry":
            return self._retry_evidence(session, parts[1])
        if route == ("POST", "runs", 3) and parts[2] == "fresh":
            return self._fresh_analysis(session, parts[1])
        # The operator surfaces are for operators. The gate only asked whether
        # a session existed, and an anonymous demo session is a session -- so
        # any guest who typed /dashboard was shown the operations console:
        # missing-credential names (TIINGO_API_KEY, FRED_API_KEY), the full
        # deployed commit, scheduler job state and status.json. None of that is
        # a product surface, and a visitor evaluating the product should never
        # be looking at its plumbing.
        if parts and parts[0] in ("learning", "dashboard", "assistant"):
            if session is None:
                return self._redirect("/login")
            if session.get("anonymous"):
                # A demo session is a session, which is all the old gate
                # asked, so any guest who typed /dashboard was shown the
                # operations console. 404 rather than a redirect: a guest has
                # no account to log into, and pointing them at a login page
                # they cannot pass is the dead end this programme keeps
                # removing.
                return self._error_page(404, "no such page")
        if route == ("GET", "learning", 1):
            return self._learning_page(session)
        if route == ("GET", "learning", 2):
            return self._learning_explain_page(session, parts[1])
        if route == ("GET", "analyses", 1) and session is not None:
            return self._my_analyses(session)
        if route == ("GET", "dashboard", 1):
            return self._dashboard_page(session)
        if path in ("/feedback", "/feedback.jsonl") and method == "GET":
            if session is None:
                return self._redirect("/login")
            return self._operator_feedback(session, export=path.endswith(
                ".jsonl"))
        if path == "/status.json" and method == "GET":
            if session is None:
                return self._redirect("/login")
            return self._ok_json(self._platform_status())
        if route == ("GET", "assistant", 1):
            return self._assistant_page(session)
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

    #: request header carrying the smoke-test token (server-side only)
    SMOKE_TEST_HEADER = "HTTP_X_FOUNDER_INTELLIGENCE_SMOKE_TEST"

    def _is_smoke_test(self, environ) -> bool:
        """True when this request presents the configured smoke-test token.

        Exists because engineering smoke traffic was consuming the same
        allowance as real visitors, so repeated production checks returned 429
        and live validation stalled twice.

        Deliberately narrow. It is consulted in exactly one place -- the demo
        rate limiter -- so a valid token buys nothing except the quota. Consent,
        CSRF, run ownership, session isolation and every other boundary are
        untouched by it.

        With no token configured the mechanism does not exist: the header is
        not read and behaviour is unchanged. An absent, empty or wrong token is
        indistinguishable from an ordinary public request.
        """
        expected = (self.config.smoke_test_token or "").strip()
        if not expected:
            return False
        presented = (environ.get(self.SMOKE_TEST_HEADER) or "").strip()
        if not presented:
            return False
        # constant-time: a length-or-prefix leak here would let the token be
        # recovered a character at a time
        if not hmac.compare_digest(presented, expected):
            return False
        # Audited, because a bypass that leaves no trace is a bypass nobody can
        # review. The event names what happened and nothing else -- no token,
        # no prefix, no length.
        _LOG.info("internal_smoke_test_rate_limit_bypass_used path=%s",
                  environ.get("PATH_INFO", "?"))
        return True

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

    def _stylize(self, body: str) -> str:
        """Ensure every page carries the shared stylesheet and the
        accessibility baseline.

        The baseline is applied even to pages that embed their own <style>.
        Skipping those was how the least-styled page in the product stayed
        that way: the synthetic demo result renders its own CSS, so it was
        exempted from the shared one — and it is the first result a guest ever
        sees. The baseline only adds visible focus, a readable dark scheme, a
        responsive floor and print rules, so it cannot fight a page's own
        design; the full stylesheet is still applied only where absent.
        """
        if "</head>" not in body:
            return body
        head_extra = ""
        if 'name="viewport"' not in body:
            head_extra += ('<meta name="viewport" content="width=device-width,'
                           'initial-scale=1">')
        # The shared stylesheet goes in the HEAD of EVERY page, including pages
        # that bring their own. Skipping it left the brief — the page every
        # analysis lands on — with a completely unstyled header: `<nav>` sits
        # outside `main.brief`, so the brief's own scoped CSS never reached it
        # and the reader got browser-default Times above a designed document.
        #
        # It goes in FIRST, so a page's own <style> comes later in the cascade
        # and still wins; and the brief's rules are class-scoped, which beats
        # these element selectors on specificity regardless of order.
        head_extra += f"<style>{_APP_CSS}</style>"
        head_extra += _A11Y_CSS
        return body.replace("</head>", head_extra + "</head>", 1)

    def _html(self, body, *, status="200 OK", extra_headers=()):
        return status, [("Content-Type", "text/html; charset=utf-8"),
                        *extra_headers], self._stylize(body)

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
            [("Content-Type", "text/html; charset=utf-8")], self._stylize(body)

    def _nav(self, session, csrf=""):
        if session is None:
            return ('<nav aria-label="Session"><a href="/">Home</a> · '
                    '<a href="/login">Log in</a></nav>')
        if session.get("anonymous"):
            # A link back to your own analyses. Without it, navigating away
            # from a result loses it: there was no index, no history and no
            # way to reach a run again except the URL you no longer have.
            mine = ('<a href="/analyses">Your analyses</a> · '
                    if self.web_store.runs_owned_by(session["user_id"])
                    else '')
            return (f'<nav aria-label="Session"><a href="/">Home</a> · '
                    f'{mine}'
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
                # METHODOLOGY DOES NOT GO BEFORE VALUE.
                #
                # This used to inject the whole "Before you start" explainer
                # above the form: how retrieval works, what a hypothesis is,
                # what confidence means, a glossary -- everything except a
                # reason to care. A first-time visitor met a methodology
                # document and had to scroll past it to reach the one box that
                # does something.
                #
                # It also rendered SIX identical "Got it - start an analysis"
                # buttons, because the injection did
                #   .replace('</section>', form + '</section>')
                # and str.replace with no count replaces EVERY occurrence --
                # one per explainer section.
                #
                # The explainer still exists, in full, at /onboarding. It is
                # now a link for people who want it rather than a wall for
                # people who do not.
                from intent_engine.company_ingestion.demo_tiers import (
                    GOLDEN_COMPANIES,
                )
                examples = " · ".join(
                    f'<button type="submit" form="ex{i}" class="linkish">'
                    f'{_e(c["name"])}</button>'
                    for i, c in enumerate(GOLDEN_COMPANIES))
                forms = "".join(
                    f'<form id="ex{i}" action="/analyze" method="post" '
                    f'class="golden">'
                    f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
                    f'<input type="hidden" name="consent" value="1">'
                    f'<input type="hidden" name="company_name" '
                    f'value="{_e(c["name"])}">'
                    f'<input type="hidden" name="website" '
                    f'value="{_e(c["website"])}"></form>'
                    for i, c in enumerate(GOLDEN_COMPANIES))
                intro = (
                    f'<p class="try-line">Not sure where to start? '
                    f'Try {examples}.</p>{forms}')
                # After the form, not before the headline. Injected at
                # '<main>' it rendered above the h1, so the first thing a
                # visitor read was a footnote about examples.
                page = page.replace('</form>', '</form>' + intro, 1)
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

    # One screen, written for a business owner who has never seen this and is
    # not going to read a manual. No internal terminology, nothing about
    # pipelines or evidence families — what it does, how, what it does not do,
    # and how to use it. The old version described the product's early-access
    # limitations to someone who had not yet learned what the product was.
    _ONBOARDING = (
        ("What this does",
         "It builds a briefing on a company from public evidence — the kind "
         "of preparation you would do before a meeting, done for you and "
         "linked back to its sources.",
         []),
        ("How it works",
         "",
         ["It finds official and permitted public sources for the company.",
          "It checks whether the evidence is broad enough to be worth a "
          "briefing.",
          "It organises what it found into products, customers, strategy, "
          "risks and market signals.",
          "It writes a short executive briefing you can read in two minutes.",
          "It links every important finding back to the source it came from.",
          "It marks clearly where it is reasoning rather than reporting."]),
        ("What it does not do",
         "",
         ["It has no access to anything inside the company.",
          "It knows nothing about private meetings or internal plans.",
          "Not every company publishes enough for a useful briefing, and it "
          "will say so rather than guess.",
          "Where it reasons beyond the evidence, that is a hypothesis, not a "
          "fact."]),
        ("How to use it",
         "",
         ["Start with the brief — one page, the central view and what "
          "supports it.",
          "Move through the slides if you are presenting or want it in "
          "order.",
          "Open the evidence behind anything you would repeat out loud.",
          "Ask follow-up questions in plain English."]),
    )

    # The five words that would otherwise be jargon on first contact.
    _GLOSSARY = (
        ("Outside-in", "Built only from what the company and others have "
                       "published publicly — never from inside knowledge."),
        ("Confidence", "How much the evidence actually supports a statement. "
                       "Low confidence is not a hedge; it means treat this as "
                       "a lead, not a fact."),
        ("Hypothesis", "A possible explanation that fits the evidence but is "
                       "not established. Worth testing, not worth repeating "
                       "as fact."),
        ("Contradiction", "Two credible sources that disagree. Shown rather "
                          "than resolved, because which one is right is often "
                          "the interesting question."),
        ("Limited analysis", "The company publishes too little for a full "
                             "briefing. What was found is still shown, with "
                             "what was missing."),
    )

    def _onboarding_html(self, *, dismissible=True, run_id=""):
        blocks = ""
        for heading, lead, items in self._ONBOARDING:
            bullets = ("<ul>" + "".join(f"<li>{_e(i)}</li>" for i in items)
                       + "</ul>") if items else ""
            blocks += (f'<section class="ob-part"><h2>{_e(heading)}</h2>'
                       + (f'<p>{_e(lead)}</p>' if lead else '')
                       + bullets + '</section>')
        glossary = "".join(f'<dt>{_e(term)}</dt><dd>{_e(meaning)}</dd>'
                           for term, meaning in self._GLOSSARY)
        dismiss = ('<p class="ob-dismiss"><a href="/">Got it — start an '
                   'analysis</a></p>') if dismissible else ''
        return (f'<section class="onboarding" aria-label="How this works">'
                f'<h1>Before you start</h1>{blocks}'
                f'<section class="ob-part"><h2>A few words used here</h2>'
                f'<dl class="glossary">{glossary}</dl></section>'
                f'{dismiss}</section>')

    def _onboarding(self, session):
        csrf = session["csrf"] if session else ""
        body = (f'{_BRIEF_CSS}{_ONBOARDING_CSS}<main class="brief">'
                f'{self._onboarding_html()}</main>')
        return self._html(self._page("Before you start", body, session, csrf))

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
        return self._redirect("/", set_sid=sid)

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
        return self._redirect("/", set_sid=sid)

    def _analyze(self, session, form, remote="unknown", *, smoke=False):
        if form.get("consent") is None:
            return self._error_page(400, "consent is required")
        limited = None if smoke else self._demo_rate_limited(session, remote)
        if limited is not None:
            return limited
        website = form.get("website", f"https://{DEMO_DOMAIN}")
        company_name = form.get("company_name", "")[:120]
        # WHICH company? A name like "Sony" denotes a parent, a games
        # subsidiary, an electronics subsidiary and more. Picking one for the
        # user produces a confident report about the wrong company — strictly
        # worse than asking. Asked once, before any work, and answered by an
        # explicit choice that carries its own website (the choice form posts
        # no website field, so this must settle both).
        chosen = form.get("entity_id", "")
        if chosen:
            picked = resolve_choice(chosen)
            if picked.resolved:
                company_name = picked.profile.legal_name
                website = f"https://{picked.profile.primary_domain}"
        if DEMO_DOMAIN not in website:
            if not chosen:
                resolution = resolve_entity(company_name=company_name,
                                            website=website)
                if resolution.status == AMBIGUOUS:
                    return self._disambiguation_page(
                        session, resolution, form)
                # The landing form asks for a website, not a name, so almost
                # every real visit arrives with company_name empty -- and the
                # report was then headed "(unnamed company)" while citing
                # "About Sentry | Sentry" three lines below it. The name was
                # available twice over and used neither time: the registry had
                # already resolved the domain and its legal_name was thrown
                # away, and failing that the domain itself carries the name.
                if not company_name and resolution.resolved:
                    company_name = resolution.profile.legal_name
                if not company_name:
                    company_name = name_from_domain(website)
            # REAL company path: validate → discover → source approval.
            try:
                run = self.ci.create_run(
                    company_name=company_name or "(unnamed company)",
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
            if self.config.autorun_sources:
                # Frictionless default: no separate source-review page. Approve
                # the recommended sources (consent was given on this form) and
                # run straight through to the result.
                return self._autorun(session, run_id)
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

    def _disambiguation_page(self, session, resolution, form):
        """Ask which company was meant, once, before any analysis runs.

        Presented as plain business facts — legal name, country, listing —
        because a business reader distinguishes companies by those, not by an
        entity id. The parent is listed first (the likeliest reading) but every
        option is an equal, explicit choice.
        """
        csrf = session["csrf"] if session else ""
        payload = resolution.as_dict()
        cards = "".join(
            f'<form action="/analyze" method="post" class="choice">'
            f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
            f'<input type="hidden" name="consent" value="1">'
            f'<input type="hidden" name="entity_id" '
            f'value="{_e(c["entity_id"])}">'
            f'<input type="hidden" name="business_question" '
            f'value="{_e(form.get("business_question", ""))}">'
            f'<h3>{_e(c["legal_name"])}</h3>'
            f'<p class="state">{_e(c["describe"])}</p>'
            f'<p class="why">{_e(c["note"])}</p>'
            f'<button type="submit">Analyse {_e(c["legal_name"])}</button>'
            f'</form>' for c in payload["choices"])
        body = (
            f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,'
            f'initial-scale=1"><title>Which company do you mean?</title>'
            f'</head><body>{self._nav(session, csrf)}<main>'
            f'<h1>Which company do you mean?</h1>'
            f'<p>{_e(payload["reason"])}. These are different companies with '
            f'different products, results and risks, so the answer depends on '
            f'which one you want.</p>{cards}'
            f'<p><a href="/">Start over with a different company</a></p>'
            f'</main></body></html>')
        return self._html(body)

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
        # Auto-update without a manual refresh: while the run is still in a
        # non-terminal state, the page reloads itself; in any terminal state the
        # refresh is omitted so it stops (safe, JS-free, CSP-proof).
        terminal = status in ("COMPLETE", "PARTIAL", "FAILED", "REJECTED")
        # PRESENTATION FIRST. A finished analysis used to stop here and offer
        # a link called "Open the result", behind a heading that said "Analysis
        # progress" next to a raw run id and an unexplained PARTIAL badge. The
        # user had already waited; making them read a status page and then
        # click again is asking them to do the product's job.
        if status in ("COMPLETE", "PARTIAL"):
            return self._redirect(f"/runs/{run_id}/slides")

        refresh = ('' if terminal
                   else '<meta http-equiv="refresh" content="4">')
        # A run that failed must say so in the heading. Softening every state
        # into "Reading the public evidence…" would hide a failure behind a
        # progress message, which is worse than the jargon it replaced.
        heading = ("This analysis could not be completed"
                   if status == "FAILED" else "Reading the public evidence…")
        head = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'{refresh}<title>{_e(heading)}</title></head>'
                f'<body>'
                f'{self._nav(session, session["csrf"])}<main>'
                f'<h1>{_e(heading)}</h1>')
        if status == "FAILED":
            # Honest terminal failure: NO "Open the result" — there is no
            # result. Explain why and offer a safe start-over.
            tail = (f'<p>This analysis could not be completed, so there is no '
                    f'result to open. {self._failure_explanation(run_id, real)}'
                    f'</p><p><a href="/runs/{_e(run_id)}">See the failure '
                    f'details</a> · <a href="/">Start a new analysis</a></p>')
        else:
            # Still in flight. Say what is happening in words a person uses,
            # not lifecycle names, and never claim a result already exists.
            tail = ('<p>Finding the company\'s own pages, its investor and '
                    'financial material where it exists, and independent '
                    'coverage — then reading them. This usually takes under a '
                    'minute and the page moves on by itself.</p>'
                    '<p class="coverage">If nothing has happened after a '
                    'couple of minutes the run may have been interrupted. You '
                    'can <a href="/">start again</a>.</p>')
        return self._html(head + tail + '</main></body></html>')

    def _coverage_note(self, run_id, real):
        """A specific, non-technical statement of WHICH kinds of evidence the
        report rests on and what is missing — shown instead of leaving the
        reader to infer meaning from empty sections."""
        if not real:
            return ''
        result = self._results.get(run_id) or {}
        coverage = result.get("coverage")
        if not coverage:
            return ''
        families = ", ".join(_e(f) for f in coverage["families"])
        note = (f'<p class="coverage">Evidence coverage: '
                f'{coverage["document_count"]} usable source(s) across '
                f'{len(coverage["families"])} source '
                f'{"family" if len(coverage["families"]) == 1 else "families"}'
                f'{f" ({families})" if families else ""}.')
        steps = coverage.get("next_evidence_steps") or []
        if steps:
            note += (' To strengthen this analysis, add '
                     + _e("; ".join(steps[:3])) + '.')
        return note + '</p>'

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
        "content_rejected": ("not stored",
                             "the page was read, but its text looked like it "
                             "contained a credential or personal identifier, "
                             "so it was not kept"),
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
        """Per-source (readable-source, short-label, human-explanation, detail).

        The first element is what the READER should see — a page title or URL,
        never an internal candidate id. `cand-c89e584c34f7` tells a person
        nothing about which page failed, and a list of them reads as a system
        malfunction rather than as a site declining to be read.

        The raw ``safe_message`` (which can contain raw exception text) is
        included only in development — never in production.
        """
        from urllib.parse import urlparse
        by_id = {c["candidate_id"]: c
                 for c in self.ci.store.candidates(run_id)}
        meta = self.ci.run_meta(run_id) or {}
        rows = []
        for f in self.ci.store.failures(run_id):
            cat = self._failure_category(f)
            label, human = self._FAILURE_LABELS.get(
                cat, ("unavailable", "the source could not be retrieved"))
            detail = (f' — {_e(str(f.get("safe_message", ""))[:200])}'
                      if self.config.debug else '')
            candidate_id = str(f.get("candidate_id", ""))
            if candidate_id == "homepage":
                readable = meta.get("website") or "the company homepage"
            else:
                candidate = by_id.get(candidate_id) or {}
                readable = (candidate.get("title") or candidate.get("url")
                            or urlparse(candidate.get("url") or "").hostname
                            or "a requested page")
            rows.append((str(readable), label, human, detail))
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

    def _run_page(self, session, run_id, *, layer="default"):
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
                # Auto-run mode never routes guests through manual source
                # selection: (re)approve the recommended sources and run.
                if self.config.autorun_sources:
                    return self._autorun(session, run_id)
                return self._redirect(f"/runs/{run_id}/sources")
            if result.get("status") == "FAILED" and not result.get("sections"):
                return self._failed_run_page(session, run_id)
            # The gate said no. There is no strategic report to render, and a
            # report-shaped page with the findings removed is exactly the
            # "empty but finished-looking" artefact this must never produce.
            # Show what was found, what was missing, and what to do next.
            readiness = result.get("readiness") or {}
            if readiness and not readiness.get("may_synthesize", True):
                return self._insufficient_evidence_page(session, run_id,
                                                        result)
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
        feedback_form = self._feedback_form(run_id, csrf)

        # V1.2: when the run has a Strategic Intelligence Report it IS the
        # executive report. The legacy claim/evidence sections are quarantined
        # into a collapsed technical appendix so they never weaken the exec view.
        if result.get("strategic_report"):
            # The full report is not wrong; it is unreadable at the moment it
            # matters. Fifteen minutes before a meeting, eleven sections and a
            # technical appendix get skimmed, and a skimmed report is where a
            # reader picks up the first confident sentence they see. Depth was
            # never the problem — the default was. So the default is now the
            # brief, and the depth is one click away and still complete.
            if layer == "default":
                # V3: the default is the 60-SECOND FOUNDER BRIEF, not the
                # executive brief. The customer's message was that founders
                # should not have to read everything -- and the executive
                # brief, at 500-900 words, is still "everything" to someone
                # with fifteen minutes. Depth is one click away and unchanged.
                return self._founder_brief_page(session, run_id, result)
            return self._strategic_run_page(session, run_id, result,
                                            share_form, feedback_form)

        # A real run can retrieve pages, match no strategic signal, and so
        # produce no report while the pipeline still reports success — the
        # KNOWN LIMITATION named in `derive_observations`, which says outright
        # that the fix belongs one level up. This is that level.
        #
        # What it fell through to was the legacy claim/evidence dump: an
        # "Executive Overview" of field labels, internal claim ids printed
        # beside each line ("[u.offering]", "[mv.company_language]"), and a
        # "Strongest supported observation" that was a list of the five words
        # the company's pages use most. Every route into it is a reader who
        # asked for an analysis of a real company, so it is the likeliest
        # first impression the product makes, not an edge case.
        #
        # The honest page already exists and answers the three questions this
        # reader has — what was found, what was missing, what to do now.
        if self._is_real_run(run_id):
            # V3: a company with little public material gets a USEFUL bounded
            # product -- what a customer can verify, what is only claimed,
            # what is unclear, and what to publish -- instead of a dead end.
            # The old refusal was accurate and useless, and it was the
            # customer's sharpest complaint.
            return self._founder_brief_page(session, run_id, result)

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

    def _has_untried_sources(self, run_id) -> bool:
        """Whether any discovered source has neither been retrieved nor
        failed — i.e. whether a second look has anywhere to go."""
        candidates = self.ci.store.candidates(run_id)
        if not candidates:
            return False
        retrieved = {d.get("original_url") for d in
                     self.ci.store.retrieved(run_id)}
        retrieved |= {d.get("final_url") for d in
                      self.ci.store.retrieved(run_id)}
        failed_ids = {f.get("candidate_id")
                      for f in self.ci.store.failures(run_id)}
        return any(c["candidate_id"] not in failed_ids
                   and c["url"] not in retrieved for c in candidates)

    def _retry_evidence(self, session, run_id):
        """One more targeted pass at the specific missing evidence.

        Recomposition is what does the work: `compose_with_quality` gathers
        evidence to sufficiency, approving only candidates already discovered
        for this run and never re-requesting a URL that failed. So this is a
        genuine second look, not a page refresh dressed up as one — and the
        budget inside it is finite, so it cannot become a loop.
        """
        if not self._owned(session, run_id) or not self._is_real_run(run_id):
            return self._error_page(404, "no such run for this account")
        try:
            self._results[run_id] = self._compose(run_id)
        except IngestionError as exc:
            return self._error_page(400, str(exc))
        return self._redirect(f"/runs/{run_id}")

    def _insufficient_evidence_page(self, session, run_id, result, *,
                                    reason=""):
        """The honest alternative to an empty report.

        A reader who gets this must be able to answer three questions without
        asking anyone: what DID it find, what was it missing, and what can I do
        now. The last one matters most — a dead end with no next step reads as
        a broken product, which is why every route out is offered explicitly.

        `reason` replaces the readiness headline for callers whose situation
        the readiness note does not describe. A run that passed the gate and
        then matched no strategic signal is not short of evidence — it is
        short of the KIND of evidence a reading rests on — and telling that
        reader "some kinds of evidence are missing, and there are places left
        to look" would be answering a question they did not ask.
        """
        csrf = session["csrf"] if session else ""
        readiness = result.get("readiness") or {}
        note = result.get("readiness_explanation") or {}
        meta = self.ci.run_meta(run_id) or {}
        company = meta.get("company_name", "this company")

        def _ul(items, empty=""):
            rows = "".join(f"<li>{_e(str(i))}</li>" for i in items if i)
            return f"<ul>{rows}</ul>" if rows else empty

        found = _ul(note.get("found", []),
                    "<p class='unavailable'>No usable public source could be "
                    "read.</p>")
        # Evidence that WAS retrieved is never discarded just because there is
        # too little of it to support a briefing. It is the reader's, it cost a
        # real fetch, and seeing it is how they judge whether to add more.
        # "Read" meant retrieval_status == OK, which only says the fetch
        # succeeded. Figma's German blog pages were fetched fine, could not be
        # read by the analysis, were correctly excluded from the evidence --
        # and were still listed to the user under "Sources that were read".
        # The page asserted something false about its own work.
        from intent_engine.company_ingestion.readiness import is_english
        fetched = [d for d in self.ci.store.retrieved(run_id)
                   if d.get("retrieval_status") == "OK"]
        used = [d for d in fetched if is_english(d)]
        set_aside = [d for d in fetched if not is_english(d)]

        def _links(docs):
            # Ten links all reading "Duolingo" identify nothing, and that is
            # the normal case: a page's <title> is usually the site's name, so
            # the list of what was read became ten identical words. The path is
            # what tells a reader WHICH page — and for a filing whose title is
            # its accession filename ("duol-20260603") it is the readable part.
            from urllib.parse import urlsplit
            rows = []
            for d in docs:
                url = d["final_url"]
                bits = urlsplit(url)
                where = (bits.netloc + bits.path).rstrip("/")
                title = (d.get("title") or "").strip()
                label = _e(title) if title else _e(where)
                trail = (f' <span class="muted">{_e(where)}</span>'
                         if title and title.lower() != where.lower() else "")
                rows.append(f'<li><a href="{_e(url)}" rel="nofollow noopener">'
                            f'{label}</a>{trail}</li>')
            return "".join(rows)

        if used:
            # "Sources used" over the full fetched list overclaimed: a page can
            # be read and still not be usable evidence, which is exactly the
            # gap between the two numbers this page shows.
            found += f'<h3>Pages read</h3><ul>{_links(used)}</ul>'

        # Two numbers that disagree read as a broken page. "6 usable source(s)"
        # sat directly above a list of ten, because one counts evidence and the
        # other counts fetches. Both are true and the reader needs both, so the
        # sentence relates them rather than printing one and listing the other.
        usable = note.get("source_count") or 0
        read_line = f"{len(used)} page(s) read"
        if usable and usable != len(used):
            read_line += f"; {usable} carried usable evidence"
        read_line += "."
        if set_aside:
            found += (f'<h3>Sources found but not used</h3>'
                      f'<p class="why">Not available in a language this '
                      f'analysis can read.</p><ul>{_links(set_aside)}</ul>')
        missing = _ul(note.get("missing", []))
        blockers = _ul(note.get("blockers", [])[:5])
        # Render the rows — never interpolate the list itself, which prints
        # Python tuple syntax and internal candidate ids straight onto the
        # page. Sony produces twenty-one of these, so the defect was invisible
        # until the one company that most needed this page reached it.
        #
        # Identical failures are collapsed: "eleven pages, access refused" is
        # the fact, and eleven near-identical lines bury it.
        failure_rows = self._failure_rows(run_id)
        grouped: dict = {}
        for readable, label, human, detail in failure_rows:
            grouped.setdefault((label, human, detail), []).append(readable)
        items = []
        for (label, human, detail), sources in grouped.items():
            shown = ", ".join(_e(s) for s in sources[:3])
            if len(sources) > 3:
                shown += f" and {len(sources) - 3} more"
            items.append(f"<li><strong>{_e(label)}</strong>: {_e(human)}"
                         f"{detail}<br><span class='muted'>{shown}</span></li>")
        failed_html = (f"<h3>Sources that could not be read</h3>"
                       f"<ul>{''.join(items)}</ul>" if items else "")

        # Every one of these is a real, working next step — not a consolation.
        # The retry button is offered only when there is genuinely somewhere
        # new to look. The composition path already spends its own targeted
        # retry budget before it ever gets here, so offering "try again"
        # unconditionally would hand the reader a button that can only repeat
        # itself — the most corrosive kind of dead end, because it looks like
        # progress. It becomes live again once a source has been added.
        actions = []
        if self._has_untried_sources(run_id):
            actions.append(
                (f'/runs/{run_id}/retry', 'post',
                 'Look again for the missing evidence',
                 'Runs one more targeted search for the specific kinds of '
                 'source that are missing, skipping everything that already '
                 'failed.'))
        actions += [
            ('/', 'get', 'Run a fresh analysis',
             'Start again from scratch, ignoring anything cached.'),
            (f'/runs/{run_id}/sources', 'get', 'Add an official source',
             'If you know an official page, report or filing, add it and the '
             'analysis will use it.'),
            ('/', 'get', 'Correct the company',
             'If this is the wrong entity — a subsidiary rather than the '
             'group, or a similarly named company — enter it again.'),
            ('/', 'get', 'See a worked example',
             'Palantir and Shopify publish enough in public to show what a '
             'complete analysis looks like.'),
        ]
        action_html = "".join(
            (f'<form action="{_e(url)}" method="post" class="action">'
             f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
             f'<button type="submit">{_e(label)}</button>'
             f'<p class="why">{_e(why)}</p></form>')
            if method == 'post' else
            (f'<p class="action"><a href="{_e(url)}">{_e(label)}</a>'
             f'<br><span class="why">{_e(why)}</span></p>')
            for url, method, label, why in actions)

        # "Not enough public evidence for Figma" sat directly above a body
        # explaining that SOME kinds of evidence were missing and there were
        # places left to look. The heading blamed the company for publishing
        # too little; the body said the search was incomplete. They cannot both
        # be true, and the heading is the part a reader remembers.
        #
        # "Limited analysis" states the situation without accusing anyone, and
        # the body then says exactly what is missing and what to do about it.
        heading = f'Limited analysis of {_e(company)}'
        body = (
            f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,'
            f'initial-scale=1"><title>{heading}</title></head><body>'
            f'{self._nav(session, csrf)}<main>'
            f'<h1>{heading}</h1>'
            f'<p class="lead">{_e(reason or note.get("headline", ""))} '
            f'Rather than show a briefing that looks complete and is not, '
            f'here is exactly where it stands.</p>'
            f'<h2>What was found</h2>'
            f'<p class="state">{read_line}</p>{found}'
            f'<h2>What was missing</h2>{missing}{blockers}'
            f'{failed_html}'
            f'<h2>What you can do</h2>{action_html}'
            f'<p class="limitation">A company can be perfectly healthy and '
            f'still publish little in public. Missing evidence is a statement '
            f'about what could be read, not about the company.</p>'
            f'</main></body></html>')
        return self._html(body)

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
        # There is no technical appendix. It was a <details> headed "Technical
        # appendix — legacy source extraction" holding the claim/evidence dump:
        # internal claim ids beside every line, and a vocabulary ("legacy
        # source extraction") that describes the system's own build history to
        # someone who came to read about a company. Quarantining it was not
        # enough — a founder opens a collapsed section on a report they are
        # about to rely on, and what they found there said "prototype".
        #
        # Nothing is lost that the reader had a use for: the Sources section
        # lists every source with its link, which is the auditability the
        # appendix was standing in for.
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,'
                f'initial-scale=1"><title>Strategic Intelligence — '
                f'{_e(report.get("company_name", ""))}</title></head><body>'
                f'{self._nav(session, csrf)}'
                # One <main> per page. The layer nav used to sit in a <main>
                # of its own, so a screen reader met two main landmarks and
                # "skip to main content" could land on either — on the longest
                # page in the product, where getting out matters most.
                f'<main>'
                # Bare, as every other layer renders it. Wrapping it in
                # `.brief` gave the nav that class's white background,
                # 38rem cap and 40px bottom padding, so on a phone the layer
                # links sat in a stray white panel with a band of dead space
                # under them -- the first thing below the site nav.
                f'{self._layer_nav(run_id, "full")}'
                f'{strat}{actions}'
                f'</main></body></html>')
        return self._html(_BRIEF_CSS + body)

    # --- the three layers ---------------------------------------------------
    def _analysis_stamp(self, run_id):
        """When this analysis ran and against which pipeline version — shown
        on every layer, because a briefing with no date is a briefing whose
        staleness the reader cannot judge."""
        from intent_engine._version import version_info
        meta = self.ci.run_meta(run_id) or {}
        as_of = (meta.get("as_of") or "")[:10]
        return as_of, version_info().get("app_version", "")

    def _layer_nav(self, run_id, current):
        """One consistent way between the three layers, on all three."""
        # Presentation first, everywhere. It is the layer that opens by
        # default, so it is also the one the reader should see named first.
        links = (("slides", "Presentation", f"/runs/{run_id}/slides"),
                 ("brief", "Executive brief", f"/runs/{run_id}/brief"),
                 ("full", "Full analysis", f"/runs/{run_id}/full"))
        return ('<nav class="layers" aria-label="Report depth">' + " ".join(
            (f'<strong aria-current="page">{_e(label)}</strong>'
             if key == current else f'<a href="{_e(href)}">{_e(label)}</a>')
            for key, label, href in links) + '</nav>')

    def _analysis_provenance(self, run_id, as_of, version, csrf):
        """When this ran, on what, in which mode, and how to get a fresh one.

        A briefing with no date is a briefing whose staleness the reader cannot
        judge, and one that silently reused a cached run is a briefing whose
        freshness they have been misled about. Both are shown.
        """
        from intent_engine.company_ingestion.demo_tiers import (
            classify, presentation,
        )
        identity = self.ci.entity_identity(run_id) or {}
        result = self._results.get(run_id) or {}
        readiness = (result.get("readiness") or {}).get("state", "")
        tier = classify(entity_id=identity.get("entity_id", ""),
                        website=(self.ci.run_meta(run_id) or {}).get(
                            "website", ""),
                        readiness_state=readiness)
        mode = presentation(tier)
        documents = self.ci.store.retrieved(run_id)
        fresh = sum(1 for d in documents if d.get("retrieval_status") == "OK")
        # "Compatible" used to be a word with nothing behind it: any stored
        # result was served again whatever had changed underneath it. It now
        # reports an answer that was actually checked.
        # What the reader needs from a stamp is how much evidence this rests on
        # and when it was read. "produced by the current version of the
        # product" and an internal version string answer a question nobody
        # asked and quietly suggest the reader should be worried about which
        # version they got.
        return (
            f'<p class="stamp">Read {fresh} public source(s) on '
            f'{_e(as_of)}.</p>'
            f'<p class="stamp"><strong>{_e(mode["label"])}.</strong> '
            f'{_e(mode["summary"])}</p>'
            f'<form action="/runs/{_e(run_id)}/fresh" method="post" '
            f'class="freshen"><input type="hidden" name="csrf" '
            f'value="{_e(csrf)}">'
            f'<button type="submit">Look again</button>'
            f'<span class="why"> — fetches the sources again rather than '
            f'reusing what was already read.</span>'
            f'</form>')

    def _fresh_analysis(self, session, run_id):
        """Deliberately bypass the compatible-result cache.

        The point of the button is that the user does not have to trust our
        judgement about whether the cached run is still good. A stale
        low-quality report must never be able to trap someone with no way out
        of it.
        """
        if not self._owned(session, run_id) or not self._is_real_run(run_id):
            return self._error_page(404, "no such run for this account")
        meta = self.ci.run_meta(run_id) or {}
        self._results.pop(run_id, None)
        form = {"consent": "1", "company_name": meta.get("company_name", ""),
                "website": meta.get("website", ""), "csrf": session["csrf"]}
        return self._analyze(session, form)

    def _founder_brief_page(self, session, run_id, result):
        """The 60-SECOND FOUNDER BRIEF — the default completed-result view.

        Serves every company mode from one route. A rich public company and a
        one-page marketing site both land here; what differs is which sections
        have material behind them, not which page the reader gets. That is the
        point of the mode system -- equally USEFUL, not equally detailed.
        """
        from intent_engine.founder_brief import build as fb
        from intent_engine.founder_brief import market as fm
        from intent_engine.founder_brief import render as fr

        report = result.get("strategic_report") or {}
        observations = [o for o in (report.get("observations") or ())
                        if isinstance(o, dict)]
        if not observations:
            observations = [o for o in (result.get("observations") or ())
                            if isinstance(o, dict)]

        independent = sum(
            1 for o in observations
            if o.get("source_class") not in ("company_owned",
                                             "executive_statement", None, ""))
        thesis = report.get("thesis") or {}
        has_view = bool(thesis.get("view")) and not thesis.get("view_withheld")
        identity = self.ci.entity_identity(run_id) or {}
        ticker = identity.get("ticker") or ""

        mode = fb.classify_mode(
            is_public=bool(ticker), evidence_count=len(observations),
            independent_sources=independent, has_thesis=has_view,
            has_financials=False)

        # Market context comes ONLY from the versioned export, and only when
        # a snapshot has actually been published. Absent or unreadable, the
        # section renders "Unavailable" -- never a zero, and never a 500: a
        # founder-facing page must not die because an upstream research
        # artefact is missing.
        market = None
        if ticker:
            try:
                snapshot = (pathlib.Path(self.config.data_dir) / "reports"
                            / "market" / "export" / f"{ticker}.json")
                market = fm.load(snapshot, expected_ticker=ticker).as_dict()
            except Exception:  # noqa: BLE001 - degrade, never fail the page
                market = fm.unavailable(
                    "market snapshot could not be read").as_dict()

        name = (identity.get("canonical_name") or identity.get("name")
                or result.get("company") or "This company")
        brief = fb.build(company=name, mode=mode, report=report,
                         observations=observations, market=market)
        body = fr.render_brief(brief, run_id=run_id)
        return self._html(self._page(f"{name} — founder brief", body,
                                     session, session.get("csrf", "")))

    def _brief_page(self, session, run_id):
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        report = self._strategic_report_for(run_id)
        if report is None:
            return self._redirect(f"/runs/{run_id}/full")
        from intent_engine.strategic_intelligence.brief import build_brief
        as_of, version = self._analysis_stamp(run_id)
        brief = build_brief(report, as_of=as_of, analysis_version=version,
                            documents=self.ci.store.retrieved(run_id))
        csrf = session["csrf"] if session else ""

        def _p(label, value):
            return (f'<section class="b-part"><h2>{_e(label)}</h2>'
                    f'<p>{_e(value)}</p></section>') if is_meaningful(value) \
                else ''

        central = central_view_after_headline(
            brief.thesis,
            brief.headline.view if is_meaningful(brief.headline.does) else "")

        # A date earns its place only when it distinguishes one item from
        # another. Every line here carried the SAME retrieval date -- the day
        # the run happened -- which told the reader nothing and read as
        # chronology that was not there.
        _dates = {s.get("date") for s in brief.signals
                  if is_meaningful(s.get("date"))}
        _dates_differ = len(_dates) > 1
        signals = "".join(
            f'<li>' + (f'<span class="when">{_e(s["date"])}</span>'
                       if _dates_differ and is_meaningful(s.get("date"))
                       else '')
            + f'{_e(s["text"])}</li>' for s in brief.signals)
        questions = "".join(f'<li>{_e(q)}</li>' for q in brief.questions)
        body = (
            f'{_BRIEF_CSS}<main class="brief">'
            f'{self._layer_nav(run_id, "brief")}'
            f'<h1>{_e(brief.company)}</h1>'
            f'{self._analysis_provenance(run_id, as_of, version, csrf)}'
            # The whole answer for a reader who will not scroll: what this
            # company is, what we think is happening, and how much to trust
            # it. Everything below is for the reader who continues.
            + (f'<section class="b-headline">'
               f'<p class="hl-does">{_e(brief.headline.does)}</p>'
               f'<p class="hl-view">{_e(brief.headline.view)}</p>'
               f'<p class="hl-conf">{_e(brief.headline.confidence)}</p>'
               f'</section>' if is_meaningful(brief.headline.does) else '')
            + _p("The central view", central)
            + (f'<section class="b-part"><h2>What supports it</h2>'
               f'<ul class="signals">{signals}</ul></section>'
               if signals else '')
            + _p("What argues the other way", brief.counterpoint)
            + _p("The tension to watch", brief.tension)
            + _p("The decision this affects", brief.decision)
            + (f'<section class="b-part"><h2>Questions for leadership</h2>'
               f'<ol>{questions}</ol></section>' if questions else '')
            + _p("What this cannot tell you", brief.limitation)
            + f'<div class="b-act">'
            f'<a class="primary" href="/runs/{_e(run_id)}/slides">'
            f'Present this</a>'
            f'<a href="/runs/{_e(run_id)}/full">Read the full analysis</a>'
            f'</div>'
            f'<form action="/runs/{_e(run_id)}/conversation" method="post" '
            f'class="b-ask"><input type="hidden" name="csrf" '
            f'value="{_e(csrf)}"><label for="q">Ask a question about '
            f'{_e(brief.company)}</label> '
            f'<input id="q" name="question" required>'
            f'<button type="submit">Ask</button></form>'
            f'</main>')
        return self._html(self._page(f"{brief.company} — executive brief",
                                     body, session, csrf))

    def _slides_page(self, session, run_id):
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        report = self._strategic_report_for(run_id)
        if report is None:
            return self._redirect(f"/runs/{run_id}/full")
        from intent_engine.strategic_intelligence.slides import (
            build_slides, deck_is_presentable, meaningful_slide_count,
            render_deck,
        )
        as_of, version = self._analysis_stamp(run_id)
        csrf = session["csrf"] if session else ""
        slides = build_slides(report, as_of=as_of, analysis_version=version,
                              documents=self.ci.store.retrieved(run_id))
        if not deck_is_presentable(slides):
            # Better to say so than to hand someone a three-slide deck in a
            # meeting after promising a presentation.
            body = (
                f'<main>{self._layer_nav(run_id, "slides")}'
                f'<h1>Not enough for a presentation</h1>'
                f'<p>This analysis supports '
                f'{meaningful_slide_count(slides)} substantive slide(s), and a '
                f'presentation needs at least 5. The brief and the full '
                f'analysis contain everything that was found.</p>'
                f'<p><a href="/runs/{_e(run_id)}/brief">Read the executive '
                f'brief</a> · <a href="/runs/{_e(run_id)}/full">Full '
                f'analysis</a></p></main>')
            return self._html(self._page("Presentation unavailable", body,
                                         session, csrf))
        deck = render_deck(slides, company=report.get("company_name", ""),
                           as_of=as_of, analysis_version=version,
                           run_id=run_id, csrf=csrf,
                           full_analysis_url=f"/runs/{run_id}/full",
                           cite_labels=self._citation_labels(run_id))
        body = (f'<main>{self._layer_nav(run_id, "slides")}{deck}</main>')
        return self._html(self._page(
            f'{report.get("company_name", "")} — presentation', body, session,
            csrf))

    def _page(self, title, body, session, csrf):
        return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,'
                f'initial-scale=1"><title>{_e(title)}</title></head><body>'
                f'{self._nav(session, csrf)}{body}</body></html>')

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
        # Observation ids, which is what the presentation and the brief
        # actually cite. This route only ever searched legacy claim ids, so
        # every "Evidence behind this slide" link answered 404 — the product
        # invited a reader to check a source and then failed them at the
        # moment they decided to trust it.
        page = self._observation_evidence_page(session, run_id, claim_id)
        if page is not None:
            return page
        return self._error_page(404, "no such claim in this run")

    def _observation_evidence_page(self, session, run_id, observation_id):
        """The evidence behind one cited observation, or None if unknown."""
        report = self._strategic_report_for(run_id)
        if not report:
            return None
        observation = next(
            (o for o in (report.get("observations") or [])
             if o.get("observation_id") == observation_id), None)
        if observation is None:
            return None
        label = self._citation_labels(run_id).get(observation_id, "")
        url = observation.get("source_url") or ""
        link = (f'<p><a href="{_e(url)}" rel="noopener noreferrer nofollow" '
                f'target="_blank">Open the source page</a></p>') if url else ''
        body = (
            f'{_BRIEF_CSS}<main class="brief">'
            f'<h1>Evidence</h1>'
            f'<p class="lead">{_e(observation.get("excerpt") or observation.get("text") or "")}</p>'
            + (f'<p class="stamp">From {_e(label or observation.get("source_title") or "a retrieved page")}'
               + (f' · {_e(observation.get("date"))}' if observation.get("date") else '')
               + '</p>')
            + link
            + f'<p><a href="/runs/{_e(run_id)}/slides">Back to the '
              f'presentation</a> · <a href="/runs/{_e(run_id)}/brief">Back to '
              f'the brief</a></p></main>')
        return self._html(self._page("Evidence", body, session,
                                     session.get("csrf", "")))

    def _citation_labels(self, run_id):
        """Evidence id -> the readable name of the source behind it.

        Observation ids embed the source id they came from
        (`obs-src-4856bb8a9f80` -> `src-4856bb8a9f80`), so a citation can be
        named with the page it cites instead of an internal identifier.
        """
        from urllib.parse import urlparse
        labels = {}
        for record in self.ci.store.retrieved(run_id):
            title = (record.get("title") or "").strip()
            if not title:
                title = urlparse(record.get("final_url") or "").hostname or ""
            if not title:
                continue
            source_id = record["source_id"]
            labels[source_id] = title
            labels[f"obs-{source_id}"] = title
        return labels

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
        # The previous turn's subject, so "Why?" and "Explain that" resolve
        # against the conversation. Without this every turn starts from nothing
        # and the assistant behaves like a search box that forgets you.
        previous = self._conversation_context.get(run_id, ())
        answer = self.fi.converse(run_id, question, run_claims=flat_claims,
                                  previous_topics=previous)
        self._conversation_context[run_id] = answer.get("topics", ())

        paragraphs, citations = [], []
        for p in (answer.get("answer") or {}).get("paragraphs", []):
            paragraphs.append(p.get("text", ""))
            citations.extend(str(c) for c in p.get("citations", []))
        # Concise first: the direct answer, then the rest behind a disclosure.
        # A reader who asked a short question is not asking to read the report
        # again, and burying the answer in paragraph four is how they end up
        # taking the first confident sentence they see.
        lead = paragraphs[0] if paragraphs else ""
        rest = paragraphs[1:]
        more = (f'<details class="more"><summary>Explain more</summary>'
                + "".join(f'<p>{_e(p)}</p>' for p in rest) + '</details>') \
            if rest else ''
        cited = ("".join(f'<li>{_e(c)}</li>' for c in dict.fromkeys(citations))
                 if citations else '')
        body = (
            f'{_BRIEF_CSS}<main class="brief">'
            f'{self._layer_nav(run_id, "")}'
            f'<h1>{_e(question[:120])}</h1>'
            # The classifier's enum was rendered here verbatim, so a tester
            # asking a normal question was told "Intent: UNSUPPORTED".
            # Internal classification names are not part of the product's
            # vocabulary and never reach a reader.
            f'<p class="lead">{_e(lead)}</p>{more}'
            + (f'<section class="b-part"><h2>Evidence</h2><ul>{cited}</ul>'
               f'</section>' if cited else '')
            + f'<p class="stamp">Answers use only this run\'s approved '
            f'evidence. A source outside that set must be added and approved '
            f'before it can be used.</p>'
            f'<form action="/runs/{_e(run_id)}/conversation" method="post" '
            f'class="b-ask"><input type="hidden" name="csrf" '
            f'value="{_e(session["csrf"])}">'
            f'<label for="q">Ask something else</label> '
            f'<input id="q" name="question" required>'
            f'<button type="submit">Ask</button></form>'
            f'<p><a href="/runs/{_e(run_id)}/brief">Back to the brief</a></p>'
            f'</main>')
        return self._html(self._page("Answer", body, session,
                                     session["csrf"]))

    def _strategic_report_for(self, run_id):
        """The run's strategic report dict, if it has one (real runs only)."""
        if not self._is_real_run(run_id):
            return None
        result = self._real_result(run_id)
        return result.get("strategic_report") if result else None

    def _strategic_answer_page(self, session, run_id, sa):
        routing = sa.get("routing", {})
        # This line used to read "Discussing hypothesis H2 · operation:
        # EXPLAIN_HYPOTHESIS". A hypothesis id and an operation name are how
        # the code talks to itself; to a reader they are noise that looks like
        # a malfunction. Only the comparison subject is a real-world thing a
        # reader recognises, so only it survives.
        comparable = routing.get("selected_comparable")
        label = (f'<p class="muted"><small>Comparison with '
                 f'<strong>{_e(str(comparable))}</strong>.</small></p>'
                 if comparable else '')
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

    def feedback_available(self) -> bool:
        """Whether this deployment may accept feedback at all.

        Gated on demonstrated durability, not on the write appearing to work.
        Collecting feedback under a false promise is worse than not collecting
        it: a tester who believes their comment was received does not send it
        again, so the loss is silent and permanent.
        """
        from intent_engine.webapp.storage_state import may_promise_persistence
        return may_promise_persistence(self._storage)

    def _feedback_form(self, run_id, csrf, page="result"):
        if not self.feedback_available():
            # The honesty stays: the form is off because a comment would not
            # be kept, and saying so is the whole point. What went with it was
            # the reason in the operator's terms -- "Storage is writable but
            # sits on the same filesystem as the application image, which is
            # usually replaced on redeploy. Survival has not been
            # demonstrated." That is a paragraph about our hosting at the foot
            # of someone's report on their competitor. It is still reported in
            # full at /readyz, where the person who can act on it looks.
            return (
                f'<section class="fb" aria-label="Feedback"><h2>Feedback</h2>'
                f'<p>Feedback is switched off here for now — we could not '
                f'promise to keep what you sent, and asking anyway would be '
                f'worse than not asking.</p></section>')
        return (
            f'<form action="/runs/{_e(run_id)}/feedback" method="post" '
            f'class="fb"><input type="hidden" name="csrf" value="{_e(csrf)}">'
            f'<input type="hidden" name="page" value="{_e(page)}">'
            f'<fieldset><legend>Was this useful?</legend>'
            f'<label><input type="radio" name="useful" value="yes" required> '
            f'Yes</label> <label><input type="radio" name="useful" '
            f'value="partly"> Partly</label> <label><input type="radio" '
            f'name="useful" value="no"> No</label></fieldset>'
            f'<label for="fbnote">Anything else? (optional)</label>'
            f'<input id="fbnote" name="note" maxlength="4000">'
            f'<button type="submit">Send feedback</button></form>')

    def _feedback(self, session, run_id, form):
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        csrf = session["csrf"]
        if not self.feedback_available():
            return self._error_page(
                503, "Feedback is temporarily unavailable on this deployment. "
                     "Rather than accept a comment that would not be kept, "
                     "the form is switched off until durable storage is "
                     "attached.")
        meta = self.ci.run_meta(run_id) or {}
        from intent_engine._version import version_info
        from intent_engine.webapp.feedback import FeedbackNotDurable
        info = version_info()
        try:
            record = self.feedback_log.record(
                run_id=run_id,
                company=meta.get("company_name", DEMO_COMPANY_NAME),
                page=form.get("page", "result")[:40],
                rating=form.get("useful", "partly"),
                comment=form.get("note", ""),
                deployed_commit=info.get("commit", ""),
                analysis_version=info.get("app_version", ""),
                category=form.get("category", ""),
                user_id=session["user_id"])
        except (FeedbackNotDurable, ValueError) as exc:
            # No success page. The whole defect being fixed is a page that said
            # "recorded" because the code reached the next line.
            return self._error_page(
                503, f"Your feedback could not be saved, so it has not been "
                     f"recorded: {exc}. Nothing was kept — please try again "
                     f"later rather than assuming it was received.")
        # Keep the existing founder-input trail as well, so nothing that read
        # it before starts reading less.
        try:
            self.fi.record_feedback(run_id, meta.get("domain", DEMO_DOMAIN),
                                    useful=form.get("useful", "partly"),
                                    note=form.get("note", ""),
                                    actor_id=session["user_id"])
        except Exception:                                   # noqa: BLE001
            pass                    # the durable record is the one that counts
        body = (f'<main><h1>Thank you</h1>'
                f'<p>Your feedback was saved and read back to confirm it. '
                f'Reference <code>{_e(record.feedback_id)}</code>.</p>'
                f'<p>It is recorded as founder input — it never silently '
                f'changes the intelligence.</p>'
                f'<p><a href="/runs/{_e(run_id)}">Back to result</a></p>'
                f'</main>')
        return self._html(self._page("Thank you", body, session, csrf))

    def _operator_feedback(self, session, *, export=False):
        """Everything that was collected, and the storage state behind it.

        Both halves matter: a list of records without the durability state
        invites the same mistake the success page made, so an operator reading
        this sees what was kept AND whether keeping is proven.
        """
        from intent_engine.webapp.storage_state import explain_storage
        rows = self.feedback_log.all()
        if export:
            return ("200 OK",
                    [("Content-Type", "application/x-ndjson"),
                     ("Content-Disposition",
                      'attachment; filename="feedback.jsonl"')],
                    self.feedback_log.export_jsonl())
        summary = self.feedback_log.summary()
        table = "".join(
            f'<tr><td>{_e(r.get("submitted_at", "")[:19])}</td>'
            f'<td>{_e(r.get("company", ""))}</td>'
            f'<td>{_e(r.get("page", ""))}</td>'
            f'<td>{_e(r.get("rating", ""))}</td>'
            f'<td>{_e((r.get("comment") or "")[:160])}</td>'
            f'<td><code>{_e(r.get("run_id", "")[:12])}</code></td>'
            f'<td><code>{_e((r.get("deployed_commit") or "")[:8])}</code></td>'
            f'</tr>' for r in reversed(rows))
        body = (
            f'{_BRIEF_CSS}<main class="brief"><h1>Feedback</h1>'
            f'<p class="stamp">{summary["total"]} record(s) · '
            f'{summary["with_comment"]} with a comment</p>'
            f'<h2>Storage</h2>'
            f'<p>{_e(explain_storage(self._storage))}</p>'
            f'<p class="stamp">Runtime root <code>'
            f'{_e(self._storage["runtime_root"])}</code> · '
            f'{"writable" if self._storage["writable"] else "NOT writable"} · '
            f'{self._storage["boot_count"]} boot(s) recorded · accepting '
            f'feedback: {"yes" if self.feedback_available() else "no"}</p>'
            + (f'<h2>Records</h2><table><tr><th>When</th><th>Company</th>'
               f'<th>Page</th><th>Rating</th><th>Comment</th><th>Run</th>'
               f'<th>Commit</th></tr>{table}</table>'
               f'<p><a href="/feedback.jsonl">Export as JSONL</a></p>'
               if rows else '<p>No feedback has been recorded on this '
                            'deployment.</p>')
            + '</main>')
        return self._html(self._page("Feedback", body, session,
                                     session["csrf"]))

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

    # Evidence families an executive report needs. Selection takes a
    # round-robin across these rather than the first N candidates, so a run
    # cannot spend its whole source budget on one family (e.g. three SEC
    # filings and nothing describing the product) — the 2026-07 report-quality
    # incident. Order = priority when the budget cannot cover everything.
    _EVIDENCE_FAMILIES = (
        # NOTE: identity must NOT swallow executive-class pages. A /leadership
        # page is typed "about" but speaks for leadership; letting it take the
        # identity slot starves the strategy family of its only candidate.
        ("identity", lambda c: c["source_type"] in ("homepage", "about")
         and c.get("source_class") != "executive_statement"),
        ("investor", lambda c: c.get("source_class") == "investor_material"),
        ("product", lambda c: c["source_type"] == "product"),
        ("customers", lambda c: c["source_type"] == "customers"),
        ("strategy", lambda c: c.get("source_class") == "executive_statement"
         or c["source_type"] == "blog"),
        ("independent", lambda c: c.get("source_class") in
         ("customer_voice", "independent_reporting", "competitor")),
        ("commercial", lambda c: c["source_type"] == "pricing"),
        ("talent", lambda c: c["source_type"] == "careers"),
    )

    @classmethod
    def _recommended_candidate_ids(cls, candidates, *, refusing_hosts=()):
        """The default source set, chosen for EVIDENCE-FAMILY COVERAGE.

        Takes one candidate from each family in priority order, then a second
        pass, and so on, until the per-run budget is spent. This guarantees a
        report is grounded in several independent kinds of evidence (identity,
        product, investor, customers, strategy, ...) instead of many documents
        from a single family. Shared by the source-review page (pre-checked
        set) and auto-run (approved set), so both always agree."""
        # Within a family, order by RELEVANCE first and reachability second.
        # These are different questions and were previously conflated:
        #
        #   0. curated official URL from the entity registry — a human asserted
        #      "this is the page that explains this company", which is a claim
        #      about relevance that no automatic signal can make;
        #   1. SEC EDGAR filing — the URL was just resolved from the live
        #      submissions index, is served as plain HTML by the regulator, and
        #      is authoritative about the business;
        #   2. sitemap — the publisher lists it live today, so it resolves; but
        #      a sitemap says nothing about whether the page is worth reading;
        #   3. guessed known path — frequently a 404/403.
        #
        # Ranking sitemap above curated cost Palantir exactly the evidence the
        # acceptance criteria name: /docs/ is in the sitemap and took the single
        # product slot, while the registry's Foundry, Gotham and AIP pages —
        # which carry the platform story — sat below it and were never fetched.
        # It cost Sony everything: sony.com answers 403 to every request
        # including robots.txt, so its only retrievable evidence is its EDGAR
        # filings, which ranked level with guesses that could not succeed.
        # ...and a GUESS aimed at a host we have already watched refuse us
        # ranks below everything, because it cannot succeed and it is spending
        # a slot that authoritative evidence needs. sony.com answers 403 to
        # every request including its own robots.txt, so its guessed known
        # paths are certain failures — and while they held the budget, Sony's
        # SEC filings, retrievable and already discovered, went unselected and
        # the run admitted nothing at all.
        #
        # The demotion deliberately does NOT touch curated or regulatory
        # sources. One 403 on a homepage is a fact about that request, not a
        # proof about every path on the domain: plenty of sites refuse a bare
        # homepage or an unknown path and serve their investor pages perfectly
        # well. A hand-verified URL is worth trying on a host that has turned
        # us away; a guess is not.
        refused = {h for h in refusing_hosts if h}

        def _on_refusing_host(candidate):
            from urllib.parse import urlparse
            host = urlparse(candidate.get("url") or "").hostname or ""
            return any(host == bad or host.endswith("." + bad)
                       for bad in refused)

        def _relevance_first(candidate):
            method = candidate.get("discovery_method")
            why = candidate.get("why_relevant", "")
            if method == "official_fallback":
                return 0
            if "SEC EDGAR" in why:
                return 1
            if _on_refusing_host(candidate):
                return 9
            return 2 if "sitemap" in why else 3

        # Per-family quotas. Coverage across families is what stops a report
        # resting on three filings and nothing else, but one page per family is
        # too thin for the families that carry the most meaning: a company with
        # three platforms cannot be described by whichever product page sorted
        # first. Priority order still decides who gets scarce slots.
        # product carries both halves of "what does this company sell": the
        # platforms AND the market segments it sells them into. For Palantir
        # that is five pages (Foundry, Gotham, AIP, government, commercial) and
        # dropping any one of them loses a named part of the business.
        _QUOTAS = {"product": 5, "customers": 2, "investor": 2}

        buckets = []
        claimed = set()
        for name, matches in cls._EVIDENCE_FAMILIES:
            group = [c for c in candidates
                     if c["candidate_id"] not in claimed and matches(c)]
            group.sort(key=_relevance_first)
            claimed.update(c["candidate_id"] for c in group)
            buckets.append((name, group))
        picked, depth = [], 0
        while len(picked) < MAX_APPROVED_SOURCES:
            progressed = False
            for name, group in buckets:
                if depth >= _QUOTAS.get(name, 1):
                    continue
                if depth < len(group) and len(picked) < MAX_APPROVED_SOURCES:
                    picked.append(group[depth]["candidate_id"])
                    progressed = True
            if not progressed:
                break
            depth += 1
        # Budget left over because some families had no candidates at all (the
        # Sony case: nothing on the company's own domain can be retrieved). Fill
        # it from the best remaining evidence rather than returning a short list
        # — an unused slot is evidence thrown away.
        if len(picked) < MAX_APPROVED_SOURCES:
            taken = set(picked)
            # A refused host is DEMOTED, never excluded. One 403 on a homepage
            # is evidence about that request, not a proof about every path on
            # the domain — plenty of sites refuse a bare homepage or a guessed
            # path and serve their investor pages perfectly well. Ranking them
            # last is enough: real evidence takes the slots first, and if the
            # budget is still unspent we would rather try and record an honest
            # failure than decide in advance that a door is shut.
            remaining = [c for _name, group in buckets for c in group
                         if c["candidate_id"] not in taken]
            remaining.sort(key=_relevance_first)
            for candidate in remaining:
                if len(picked) >= MAX_APPROVED_SOURCES:
                    break
                picked.append(candidate["candidate_id"])
        return picked

    def _autorun(self, session, run_id):
        """Approve the recommended sources, retrieve, and compose in one shot,
        then land on the styled progress page — the manual source-review page
        is skipped. Idempotent: approval/retrieval/compose are each idempotent,
        so a double-clicked or duplicate submit never creates a second run.
        Consent was already given on the analyze form."""
        if self.ci.store.approval(run_id) is None:
            candidates = self.ci.store.candidates(run_id)
            approved_ids = self._recommended_candidate_ids(
                candidates,
                refusing_hosts=self.ci.refusing_hosts(run_id))
            rejected = [c["candidate_id"] for c in candidates
                        if c["candidate_id"] not in approved_ids]
            try:
                self.ci.approve(run_id, user_id=session["user_id"],
                                approved_ids=approved_ids, rejected_ids=rejected)
                self.ci.fetch_approved(run_id)
                self._results[run_id] = self._compose(run_id)
            except IngestionError as exc:
                return self._error_page(400, str(exc))
        elif run_id not in self._results:
            # Approval already exists (e.g. a duplicate submit after a restart):
            # recompose from the persisted, already-retrieved sources rather
            # than starting anything new.
            self._results[run_id] = self._compose(run_id)
        return self._redirect(f"/runs/{run_id}/progress")

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

        if selected_ids is not None:
            selected = set(selected_ids)
        else:
            # Same reachability knowledge as auto-run, so the pre-checked set
            # on the review page and the set auto-run approves never disagree.
            selected = set(self._recommended_candidate_ids(
                candidates, refusing_hosts=self.ci.refusing_hosts(run_id)))

        def _tag(c):
            if c.get("source_class") == "investor_material":
                return ('<span class="tag tag-authoritative">official filing'
                        '</span>')
            if not c["same_domain"]:
                extra = ('<span class="tag tag-unverified">unverified</span>'
                         if c.get("availability") == "UNVERIFIED" else '')
                return ('<span class="tag tag-external">external</span>'
                        + extra)
            return ''

        def _row(c):
            note = c.get("why_relevant") or c.get("why_useful", "")
            checked = "checked" if c["candidate_id"] in selected else ""
            return (
                f'<li><label><input type="checkbox" name="cand" '
                f'value="{_e(c["candidate_id"])}" {checked}> '
                f'<strong>{_e(c["source_type"])}</strong>{_tag(c)}<br>'
                f'<code>{_e(c["url"])}</code><br>'
                f'<span class="count-note">{_e(note)}</span></label></li>')

        # Group candidates by strategic source class — authoritative official
        # filings first — so the founder sees WHAT kind of evidence they are
        # approving, not a flat list of URLs.
        class_titles = {
            "investor_material": "Official filings & investor material",
            "company_owned": "Company-owned pages",
            "executive_statement": "Executive statements (company-published)",
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
            rows += (f'<h3>{_e(title)}</h3><ul class="source-list">'
                     + "".join(_row(c) for c in group) + '</ul>')
        alert = (f'<p role="alert"><strong>{_e(message)}</strong></p>'
                 if message else '')
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,'
                f'initial-scale=1"><title>Review sources — '
                f'{_e(meta["company_name"])}</title></head>'
                f'<body>{self._nav(session, csrf)}<main>'
                f'<p class="step-badge">Step 2 of 2 · Review sources</p>'
                f'<h1>Review the sources for this analysis</h1>{alert}'
                f'<p>We found candidate evidence for '
                f'<code>{_e(meta["domain"])}</code>. Recommended sources are '
                f'already selected — you can approve them as they are, or '
                f'adjust the selection. Founder Intelligence analyzes only the '
                f'pages and evidence you approve, and never contacts, '
                f'publishes to, or modifies any website. You may approve at '
                f'most {MAX_APPROVED_SOURCES} sources per analysis.</p>'
                f'<form action="/runs/{_e(run_id)}/sources/approve" '
                f'method="post"><input type="hidden" name="csrf" '
                f'value="{_e(csrf)}">{rows}'
                f'<p class="count-note">Selected: '
                f'<strong id="cand-count">{len(selected)}</strong> of '
                f'{MAX_APPROVED_SOURCES} maximum.</p>'
                f'<details><summary>Advanced: add your own evidence '
                f'(optional)</summary>'
                f'<p>Paste a short excerpt from an independent source — '
                f'reporting, an executive interview, or a competitor page — '
                f'and classify it. This is the safe, no-crawl way to add a '
                f'cross-source vantage point. Leave it blank to skip.</p>'
                f'<p><label for="plabel">Source label</label>'
                f'<input id="plabel" name="pasted_label" '
                f'value="{_e(pasted.get("pasted_label", ""))}"></p>'
                f'<p><label for="porigin">Origin description</label>'
                f'<input id="porigin" name="pasted_origin" '
                f'value="{_e(pasted.get("pasted_origin", ""))}"></p>'
                f'<p><label for="pclass">Source class</label>'
                f'<select id="pclass" name="pasted_class">'
                f'<option value="independent_reporting">Independent reporting'
                f'</option><option value="customer_voice">Customer voice'
                f'</option><option value="competitor">Competitor</option>'
                f'<option value="executive_statement">Executive statement'
                f'</option><option value="investor_material">Investor material'
                f'</option></select></p>'
                f'<p><label for="ptext">Pasted text</label>'
                f'<textarea id="ptext" name="pasted_text">'
                f'{_e(pasted.get("pasted_text", ""))}</textarea></p>'
                f'<p><label><input type="checkbox" name="pasted_authorized">'
                f' I am authorized to provide this text; it is included '
                f'only because I approve it.</label></p></details>'
                f'<p><label><input type="checkbox" name="approve_consent" '
                f'required> I approve retrieval and analysis of the '
                f'selected public pages.</label></p>'
                f'<div class="btn-row">'
                f'<button type="submit">Approve and analyze</button>'
                f'<a href="/">Cancel</a></div></form>'
                f'<script>(function(){{var max={MAX_APPROVED_SOURCES};'
                f'var boxes=[].slice.call(document.querySelectorAll('
                f'\'input[name="cand"]\'));'
                f'var out=document.getElementById("cand-count");'
                f'function sync(){{var n=boxes.filter(function(b){{'
                f'return b.checked;}}).length;if(out){{out.textContent=n;}}'
                f'boxes.forEach(function(b){{b.disabled=(!b.checked&&n>=max);'
                f'}});}}boxes.forEach(function(b){{'
                f'b.addEventListener("change",sync);}});sync();}})();</script>'
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
            self._results[run_id] = self._compose(run_id)
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
            self._results[run_id] = self._compose(run_id)
        elif not self._cache_compatibility(run_id)["reusable"]:
            # A stored analysis is served again only while it still agrees with
            # the product that would produce it. Otherwise the fixes that
            # stopped every company being described as a commerce company, or
            # that capped confidence without an outside source, never reach
            # anyone whose analysis predates them — they see the old answer
            # under today's date and cannot tell.
            self._results[run_id] = self._compose(run_id)
        return self._results.get(run_id)

    def _cache_compatibility(self, run_id) -> dict:
        """Whether the stored analysis for this run is still this product's
        answer, and what to tell a reader if it is not."""
        from intent_engine._version import version_info
        from intent_engine.company_ingestion.run_compatibility import assess
        stored = self._results.get(run_id)
        if stored is None:
            return {"reusable": False, "changed": [], "reason": ""}
        return assess(stored,
                      app_version=version_info().get("app_version", ""))

    def _compose(self, run_id):
        """Compose the run, threading the persisted mental model so the report
        is a VIEW over the company's evolving state, then persist the new
        snapshot and publish strategic events durably (idempotent).

        Uses the quality-gated path: evidence is gathered to sufficiency —
        with bounded, targeted rediscovery when a family is missing — before
        the report is synthesised exactly once."""
        meta = self.ci.run_meta(run_id)
        domain = meta["domain"] if meta else ""
        previous_model = self.strategic_memory.latest_model(domain) \
            if domain else None
        result = self.ci.compose_with_quality(run_id, fi_service=self.fi,
                                              previous_model=previous_model)
        report = result.get("strategic_report")
        if report and domain:
            self.strategic_memory.save_snapshot(domain, report["mental_model"])
            self.strategic_memory.publish(
                domain, report.get("analytics_events", []), run_id=run_id)
        # The last read before a stranger sees it. Attached rather than
        # applied: a critic that edits is a second author with less context
        # than the first, and its corrections would reach the reader
        # unreviewed. What it finds becomes a stated limitation, which is
        # worth more than a silent fix.
        if report is not None:
            from intent_engine.strategic_intelligence.critic import critique
            result["critique"] = critique(
                report, documents=self.ci.store.retrieved(run_id))
        # Record what produced this, so a later reuse can be checked rather
        # than assumed.
        from intent_engine._version import version_info
        from intent_engine.company_ingestion.run_compatibility import stamp
        return stamp(result,
                     app_version=version_info().get("app_version", ""))

    def _ready(self):
        try:
            self.config.validate()
            self.web_store.read_all()
            self.fi.store.read_all()
            # The runtime root (persistent disk in production) must be mounted
            # and WRITABLE — otherwise the scheduler's jobs would silently fail
            # to persist while /readyz still said "ready". Probe it explicitly.
            self._probe_runtime_root_writable()
            # Storage durability is reported as MEASURED, so an operator can
            # tell "proven to survive a restart here" from "writable, never
            # tested" without reading a path name and guessing.
            # PERSISTENCE FAILS LOUDLY.
            #
            # render.yaml declares a persistent disk at /var/data and sets
            # RUNTIME_ROOT to it, but the running service reported
            # runtime_root="data" with durability EPHEMERAL_LIKELY -- writing
            # inside the container, wiped on every deploy. Completed analyses
            # vanished, /analyses went empty and issued result URLs stopped
            # working, while /readyz cheerfully said "ready".
            #
            # "ready" now means ready. A production service whose storage
            # cannot survive a restart is degraded, and says which one-line
            # change fixes it. Still 200, because the demo does work -- it
            # just forgets.
            from intent_engine.webapp.storage_state import (
                EPHEMERAL_LIKELY as _EPHEMERAL,
            )
            ephemeral = (self._storage["durability"] == _EPHEMERAL)
            degraded = ephemeral and self.config.env == "production"
            payload = {"status": "degraded" if degraded else "ready",
                       "env": self.config.env,
                       "runtime_root": str(self._runtime_root),
                       "storage": {
                                      "durability": self._storage["durability"],
                                      "writable": self._storage["writable"],
                                      "separate_filesystem":
                                          self._storage["separate_filesystem"],
                                      "boot_count": self._storage["boot_count"],
                                      "accepting_feedback":
                                          self.feedback_available()},
                       "capabilities": self._capability_state()}
            if degraded:
                payload["degraded_reason"] = (
                    "storage is not durable: completed analyses are lost on "
                    "every deploy. Attach the persistent disk and set "
                    "RUNTIME_ROOT to its mount path (render.yaml declares "
                    "/var/data).")
            return self._ok_json(payload)
        except Exception as exc:                            # noqa: BLE001
            return ("503 Service Unavailable",
                    [("Content-Type", "application/json")],
                    json.dumps({"status": "not ready", "reason": str(exc)}))

    def _capability_state(self) -> dict:
        """Sanitized, OBSERVED runtime capability state — never a restatement
        of intent.

        pypdf was declared in requirements.txt but absent from pyproject, so
        the deployment (which builds with `pip install -e .`) silently had no
        PDF support at all while every test and config file said it did. There
        was no way to tell from outside the process. These values are probed
        live, so "PDF works in production" becomes checkable rather than
        assumed.

        Contains no secrets, no paths, no versions of anything private — only
        whether an optional capability is actually available in THIS process.
        """
        try:
            import pypdf                                   # noqa: F401
            pdf_available = True
        except ImportError:
            pdf_available = False
        from intent_engine.company_ingestion.rendering import rendering_enabled
        # Whether the grounded analyst can run in THIS process. Without it the
        # product still works but never asserts a strategic conclusion, so
        # "is the reasoning layer live?" must be checkable from outside rather
        # than inferred from render.yaml -- which does not govern the running
        # service and declares this variable only in a comment.
        import os
        return {"pdf_extraction": pdf_available,
                "browser_rendering": rendering_enabled(),
                "strategic_reasoning": bool(
                    os.environ.get("ANTHROPIC_API_KEY"))}

    def _probe_runtime_root_writable(self) -> None:
        import os as _os
        self._runtime_root.mkdir(parents=True, exist_ok=True)
        probe = self._runtime_root / ".readyz_probe"
        probe.write_text("ok")
        _os.remove(probe)

    # --- unified operational dashboard (Part 5) -----------------------------
    def _platform_status(self) -> dict:
        """One read-only status object for the whole platform — assembled from
        persisted runtime state. Every value is real (from the stores/status
        files) or an honest null. No secret value is ever included."""
        from intent_engine._version import version_info
        from intent_engine.runtime.config_health import check_config
        from intent_engine.runtime.jobs import latest_status
        as_of = __import__("datetime").date.today().isoformat()
        root = self._runtime_root
        jobs = latest_status(root)
        try:
            pipeline = self._personal.inspect_learning(as_of=as_of)["pipeline"]
        except Exception:                                   # noqa: BLE001
            pipeline = {}
        pm = self._learning_reader.paper_metrics() or {}

        # prediction ledger counts (real reads; honest zero if absent)
        pred_total = pred_resolved = 0
        mean_brier = None
        try:
            from intent_engine.core import prediction_ledger as pl
            lp = root / "prediction_ledger.db"
            preds = pl.list_predictions(path=lp)
            pred_total = len(preds)
            pred_resolved = sum(1 for p in preds
                                if p.outcome in ("happened", "did_not_happen"))
            mean_brier = pl.brier_summary(path=lp).mean_brier
        except Exception:                                   # noqa: BLE001
            pass

        open_positions = 0
        try:
            from intent_engine.paper.ledger import PaperStore
            open_positions = len(PaperStore(root / "paper_book.db").open_positions())
        except Exception:                                   # noqa: BLE001
            pass

        # pending human promotions (evaluated + ready)
        pending_promotions = 0
        for c in self._learning_reader.candidates(status="evaluated"):
            try:
                r = self._learning_reader.explain_candidate(
                    c["id"]).get("promotion_readiness")
                if r and r.get("ready"):
                    pending_promotions += 1
            except Exception:                               # noqa: BLE001
                continue

        failed_jobs = sorted(k for k, v in jobs.items()
                             if v.get("status") == "failed")
        cfg = {k: v["status"] for k, v in check_config().items()}
        missing_required = [k for k, v in check_config().items()
                            if v["required"] and v["status"] in
                            ("missing", "invalid_format")]

        # Read the CACHED integrity result (written by the scheduled
        # integrity-scan) so the user-facing dashboard never runs a full store
        # scan per view. Falls back to a live scan only if no cache exists yet.
        try:
            from intent_engine.runtime.integrity import (
                read_cached_integrity, run_integrity,
            )
            integ = read_cached_integrity(root)
            if integ is None:
                integ = run_integrity(root)
            integrity = {"clean": integ["clean"],
                         "issue_count": integ["issue_count"],
                         "checked_at": integ.get("checked_at")}
        except Exception as exc:                            # noqa: BLE001
            integrity = {"clean": None, "error": type(exc).__name__}

        def _last(status):
            hits = [(v.get("at"), k) for k, v in jobs.items()
                    if v.get("status") == status and v.get("at")]
            return max(hits)[0] if hits else None

        # the most recent failure, with why + since-when (observability:
        # answer "what failed / why / since when" without reading source)
        fails = [(v.get("at"), k, v.get("error")) for k, v in jobs.items()
                 if v.get("status") == "failed" and v.get("at")]
        last_failure_detail = None
        if fails:
            from intent_engine.runtime.redaction import redact_secrets
            at, job, err = max(fails)
            # defense in depth: redact at render too, in case a status file
            # predates the write-time redaction fix.
            last_failure_detail = {"job": job, "at": at,
                                   "error": redact_secrets(err)}

        return {
            "as_of": as_of,
            "version": version_info(),
            "market": {
                "candidate_pipeline": pipeline,
                "predictions": pred_total,
                "resolved": pred_resolved,
                "mean_brier": mean_brier,
                "open_positions": open_positions,
                "paper_closed": pm.get("closed_count", 0),
                "portfolio_value": pm.get("ending_equity"),
                "paper_total_pnl": pm.get("total_pnl"),
                "paper_win_rate": pm.get("win_rate"),
                "jobs": {k: jobs.get(k, {}).get("status") for k in
                         ("preflight", "market-open", "resolve",
                          "daily-candidates", "weekly-eval", "monthly-packet")},
            },
            "synthetic": {"last_run": jobs.get("synthetic-daily", {}).get("at"),
                          "status": jobs.get("synthetic-daily", {}).get("status")},
            "scheduler": {"last_success": _last("succeeded"),
                          "last_failure": _last("failed"),
                          "last_failure_detail": last_failure_detail,
                          "failed_jobs": failed_jobs},
            "pending": {"promotions": pending_promotions,
                        "failures": len(failed_jobs)},
            "integrity": integrity,
            "config_health": cfg,
            "attention": self._attention(missing_required, failed_jobs,
                                         pending_promotions, integrity),
        }

    @staticmethod
    def _attention(missing_required, failed_jobs, pending_promotions, integrity):
        """What needs a human — the 'what needs attention' the cards surface."""
        items = []
        if missing_required:
            items.append(f"missing required credentials: {missing_required}")
        if failed_jobs:
            items.append(f"failed jobs: {failed_jobs}")
        if integrity.get("clean") is False:
            items.append(f"data integrity: {integrity.get('issue_count')} issue(s)")
        if pending_promotions:
            items.append(f"{pending_promotions} candidate(s) awaiting your promotion")
        return items or ["nothing needs attention"]

    def _my_analyses(self, session):
        """Every analysis this session has started, newest first.

        Closing the tab used to lose the result permanently: there was no
        index, no history, and the only route back was a URL the reader no
        longer had.
        """
        run_ids = list(reversed(
            self.web_store.runs_owned_by(session["user_id"])))
        rows = ""
        for rid in run_ids:
            meta = self.ci.run_meta(rid) or {}
            name = meta.get("company_name") or "Analysis"
            when = (meta.get("as_of") or "")[:10]
            rows += (f'<li><a href="/runs/{_e(rid)}/slides">{_e(name)}</a>'
                     + (f' <span class="when">{_e(when)}</span>' if when
                        else '') + '</li>')
        # Do not promise history the storage cannot keep. When the runtime
        # root is not durable, every analysis here disappears on the next
        # deploy -- so say that on the page that lists them, rather than
        # letting someone come back to an empty list and conclude the product
        # lost their work silently.
        from intent_engine.webapp.storage_state import may_promise_persistence
        caveat = ('' if may_promise_persistence(self._storage) else
                  '<p class="caveat">These are kept only until the service '
                  'next restarts. Open anything you want to keep now.</p>')
        body = (f'<main><h1>Your analyses</h1>{caveat}'
                + (f'<ul class="analyses">{rows}</ul>' if rows else
                   '<p>Nothing yet. <a href="/">Read a company</a> to start.'
                   '</p>')
                + '</main>')
        return self._html(self._page("Your analyses", body, session,
                                     session.get("csrf", "")))

    def _dashboard_page(self, session):
        st = self._platform_status()
        m = st["market"]
        def _kv(d):
            return ", ".join(f"{_e(str(k))}: {_e(str(v))}" for k, v in d.items()) \
                or "none"
        def _card(title, what, why, attention):
            att = (f'<p><strong>Needs attention:</strong> {_e(attention)}</p>'
                   if attention else "")
            return (f'<section style="border:1px solid #8884;border-radius:8px;'
                    f'padding:12px;margin:10px 0"><h2>{_e(title)}</h2>'
                    f'<p><strong>What:</strong> {what}</p>'
                    f'<p><strong>Why it matters:</strong> {_e(why)}</p>{att}</section>')
        ver = st["version"]
        attn = st["attention"]
        market_attention = None
        if m["predictions"] and not m["resolved"]:
            market_attention = ("predictions exist but none have resolved yet — "
                                "calibration and paper P&L stay provisional")
        body = (
            f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>Operations dashboard</title></head><body><main>'
            f'<h1>Operations dashboard</h1>'
            f'<p><em>Read-only. As of {_e(st["as_of"])}. '
            f'Version {_e(ver["app_version"])} · commit {_e(ver["commit"])} · '
            f'<a href="/status.json">status.json</a></em></p>'
            + _card("Needs attention", "<ul>" + "".join(
                f"<li>{_e(a)}</li>" for a in attn) + "</ul>",
                "the single place to look before anything else", None)
            + _card("System health & scheduler",
                    f'last success {_e(str(st["scheduler"]["last_success"]))}; '
                    f'last failure {_e(str(st["scheduler"]["last_failure"]))}; '
                    f'jobs {_kv(m["jobs"])}',
                    "a scheduled job that silently stops is the top production "
                    "risk; failures here are persistent, not swallowed",
                    ((lambda d: f'{_e(d["job"])} failed at {_e(str(d["at"]))}: '
                      f'{_e(str(d["error"]))} — re-run the job (idempotent) or '
                      'see docs/RUNTIME_DEPLOYMENT.md recovery runbook')(
                        st["scheduler"]["last_failure_detail"])
                     if st["scheduler"]["last_failure_detail"] else None))
            + _card("Market learning",
                    f'{m["predictions"]} predictions, {m["resolved"]} resolved; '
                    f'mean Brier {_e(str(m["mean_brier"]))}; '
                    f'{m["open_positions"]} open / {m["paper_closed"]} closed paper '
                    f'positions; portfolio {_e(str(m["portfolio_value"]))}; '
                    f'P&L {_e(str(m["paper_total_pnl"]))}; '
                    f'pipeline {_kv(m["candidate_pipeline"])}',
                    "this is the loop the platform exists to run and grade",
                    market_attention)
            + _card("Pending your decision",
                    f'{st["pending"]["promotions"]} promotion(s) ready for review',
                    "promotion is human-gated by design; nothing is applied "
                    "to production without you",
                    (f'{st["pending"]["promotions"]} awaiting review — '
                     '<a href="/assistant">review</a>'
                     if st["pending"]["promotions"] else None))
            + _card("Data integrity",
                    ("clean" if st["integrity"].get("clean")
                     else f'{st["integrity"].get("issue_count", "?")} issue(s)'),
                    "append-only stores must stay consistent for replay and "
                    "provenance to be trustworthy",
                    (None if st["integrity"].get("clean") else "run integrity job"))
            + _card("Synthetic worlds",
                    f'last run {_e(str(st["synthetic"]["last_run"]))} '
                    f'({_e(str(st["synthetic"]["status"]))})',
                    "the stress-test gym that feeds candidate improvements", None)
            + _card("Configuration",
                    _kv(st["config_health"]),
                    "a missing credential fails jobs loudly rather than "
                    "producing an empty day; values are never shown",
                    None)
            + f'<p><a href="/assistant">Personal AI</a> · '
            f'<a href="/learning">Learning platform</a> · '
            f'<a href="/">Home</a></p>'
            f'</main></body></html>')
        return self._html(_chrome(body, self._nav(session)))

    def _assistant_page(self, session):
        """Personal AI operator surface — distinct from the report chat.
        Read-only observation + the pending-approval queue. Consequential
        actions (promotion, publish) are NOT on this surface: they are
        human-gated elsewhere, by design."""
        as_of = __import__("datetime").date.today().isoformat()
        insp = self._personal.inspect_learning(as_of=as_of)
        ready = [c for c in self._learning_reader.candidates(status="evaluated")]
        pending = []
        for c in ready:
            try:
                r = self._learning_reader.explain_candidate(
                    c["id"])["promotion_readiness"]
                if r and r.get("ready"):
                    pending.append(c)
            except Exception:                               # noqa: BLE001
                continue
        pend_html = ("<ul>" + "".join(
            f'<li>{_e(c["statement"])} '
            f'<a href="/learning/{_e(c["id"])}">review</a></li>'
            for c in pending) + "</ul>") if pending else \
            "<p>No candidate is promotion-ready.</p>"
        body = (
            f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>Personal AI</title></head><body><main>'
            f'<h1>Personal AI — operator</h1>'
            f'<p><em>I observe, explain, and prepare work for your approval. '
            f'I do not promote, trade, or publish — those stay human-gated.</em></p>'
            f'<h2>Pending your approval (promotion-ready)</h2>{pend_html}'
            f'<h2>Learning pipeline</h2><p>{_e(str(insp["pipeline"]))}</p>'
            f'<p><a href="/dashboard">Operations dashboard</a> · '
            f'<a href="/learning">Learning platform</a> · '
            f'<a href="/">Home</a></p>'
            f'</main></body></html>')
        return self._html(_chrome(body, self._nav(session)))

    # --- learning platform (read-only observation via Personal AI) ----------
    def _learning_page(self, session):
        """Personal AI's read-only view of the learning brain: the candidate
        pipeline by status and the paper book's scored metrics. This page
        can observe and explain; it exposes no promote/trade control (those
        are human, gated, and off the web surface entirely)."""
        as_of = __import__("datetime").date.today().isoformat()
        insp = self._personal.inspect_learning(as_of=as_of)
        pipeline = insp["pipeline"]
        pipe_html = (", ".join(f"{_e(k)}: {v}" for k, v in sorted(pipeline.items()))
                     or "no candidates recorded yet")
        rows = []
        for c in insp["candidates"]:
            ref = c["source_refs"][0] if c["source_refs"] else None
            cid = ref["artifact_id"] if ref else ""
            link = (f'<a href="/learning/{_e(cid)}">explain</a>' if cid else "")
            rows.append(f"<li>{_e(c['text'])} {link}</li>")
        cand_html = ("<ul>" + "".join(rows) + "</ul>" if rows
                     else "<p>No candidate is recorded yet.</p>")
        pb = insp["paper_book"]
        body = (
            f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<title>Learning platform</title></head><body><main>'
            f'<h1>Learning platform</h1>'
            f'<p><em>Personal AI, read-only. Candidates are proposed by the '
            f'engine, paper loop, and synthetic worlds; only a human promotes '
            f'one, and never from here.</em></p>'
            f'<h2>Candidate pipeline</h2><p>{pipe_html}</p>'
            f'<h2>Candidates</h2>{cand_html}'
            f'<h2>Paper-trading book (shadow — no real money)</h2>'
            f'<p>{_e(pb["text"])}</p>'
            f'<p><a href="/">Back to start</a></p>'
            f'</main></body></html>')
        return self._html(_chrome(body, self._nav(session)))

    def _learning_explain_page(self, session, candidate_id):
        as_of = __import__("datetime").date.today().isoformat()
        ex = self._personal.explain_candidate(candidate_id, as_of=as_of)
        if not ex.get("available"):
            return self._error_page(404, ex.get("reason", "candidate not found"))
        ev_rows = "".join(
            f"<li>{_e(e['kind'])}: {_e(e['verdict'])} "
            f"(candidate {_e(str(e['candidate_metrics']))} vs baseline "
            f"{_e(str(e['baseline_metrics']))}, n={e['sample_size']})</li>"
            for e in ex["evidence"]) or "<li>no evaluations yet</li>"
        body = (
            f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<title>Explain candidate</title></head><body><main>'
            f'<h1>Explain: learning candidate</h1>'
            f'<p><strong>Finding.</strong> {_e(ex["finding"])}</p>'
            f'<p><strong>Evidence.</strong></p><ul>{ev_rows}</ul>'
            f'<p><strong>Promotable on evidence.</strong> {_e(str(ex["confidence"]))}</p>'
            f'<p><strong>Reasoning.</strong> {_e(ex["reasoning"])}</p>'
            f'<p><strong>Source agent.</strong> {_e(str(ex["source_agent"]))}</p>'
            f'<p><strong>Replay.</strong> {_e(ex["replay_id"])}</p>'
            f'<p><a href="/learning">Back to learning platform</a></p>'
            f'</main></body></html>')
        return self._html(_chrome(body, self._nav(session)))


def make_server(app, host="127.0.0.1", port=0):
    """A threading WSGI server for local/production-smoke use."""
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import WSGIServer, make_server as _make

    class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    return _make(host, port, app, server_class=ThreadingWSGIServer)
