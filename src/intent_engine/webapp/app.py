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

import hashlib
import hmac
import html as _html
import json
import pathlib
import logging
import re
from dataclasses import asdict
import time
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
from intent_engine.strategic_intelligence import evidence_classes as _EC
from intent_engine.webapp import acceptance as _acc
from intent_engine.webapp import failures as _failures
from intent_engine.webapp.auth import AuthService, PASSWORD_RESET_STATUS
from intent_engine.webapp.records import WebAppError, WebEvent
from intent_engine.webapp.sharing import SharingService
from intent_engine.webapp.store import WebStore

_e = _html.escape

# The brief is the default landing surface, so its contrast is not a detail.
# Every foreground/background pair here is at or above WCAG AA for its size.
def _external_charts(external) -> dict:
    """Rendered charts for one run's external context, keyed by module key.

    Empty when the data is too thin to draw honestly -- `visuals.render`
    returns "" below its observation floor, and the tile then carries its
    sentence and its text alternative alone. A chart is an addition to a
    module that already reads correctly without one, never the module's
    content.
    """
    if external is None:
        return {}
    from intent_engine.external_intel import presenter as _pres
    from intent_engine.external_intel import visuals as _charts
    out = {}
    for block in _pres.blocks(external):
        svg = _charts.render(block, external)
        if svg:
            out[block.key] = svg
    return out


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
.brief{--ink:#111827;--muted:#4b5563;--line:#d1d5db;--ctl:#888aa4;--bg:#ffffff;
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
border:1px solid var(--ctl);text-decoration:none;color:var(--ink);
font-weight:600;font-size:.95rem}
.brief .b-act a.primary{background:var(--accent);color:var(--accent-ink);
border-color:var(--accent)}
.brief a:focus-visible,.brief button:focus-visible,
.brief input:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.brief .b-ask{border-top:1px solid var(--line);padding-top:1rem}
.brief .b-ask label{display:block;font-size:.86rem;color:var(--muted);
margin-bottom:.35rem}
.brief .b-ask input{padding:9px 11px;border:1px solid var(--ctl);
border-radius:8px;font-size:1rem;min-width:60%;background:var(--bg);
color:var(--ink)}
.brief .b-ask button{padding:9px 16px;border-radius:8px;border:0;
background:var(--accent);color:var(--accent-ink);font-weight:600;
font-size:.95rem;cursor:pointer}
@media (max-width:600px){.brief{font-size:16px;padding:6px 14px 30px}
.brief h1{font-size:1.45rem}.brief .b-ask input{min-width:100%}}
@media (prefers-color-scheme:dark){
.brief{--ink:#f3f4f6;--muted:#c3cad6;--line:#3a4454;--ctl:#606e88;--bg:#0f141c;
--panel:#161c26;--accent:#7aa2ff;--accent-ink:#0b1220}}
@media print{.brief .layers,.brief .b-act,.brief .b-ask{display:none}
.brief{max-width:none}}
</style>
"""

#: A page's own stylesheet, wherever in the body it was emitted. Used by
#: `_stylize` to lift it into the head — see the reasoning there.
_STYLE_BLOCK = re.compile(r"<style\b[^>]*>.*?</style>", re.S | re.I)

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
/* The focus ring is set once above in the light accent (#1d4ed8), and that
   colour carried into dark mode unchanged: measured on the deployed /login at
   b66dbe3, 2.76:1 against #0f141c, under the 3:1 WCAG floor for a non-text UI
   indicator. A keyboard user in dark mode could not reliably see where they
   were. `.brief` and `.deck` were already correct because their ring reads
   var(--accent), which IS re-pointed below; only the global floor hard-coded
   the literal. Same specificity as the base rule, so it wins on order. */
:where(a,button,input,select,textarea,summary,[tabindex]):focus-visible{
outline-color:#7aa2ff}
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
--ctl:#606e88;--bg:#0f141c;--panel:#161c26;--accent:#7aa2ff;--accent-ink:#0f141c}
:root nav,:root .trust-note,:root .panel{background:#161c26;
border-color:#3a4454;color:#c3cad6}
:root nav a,:root nav a:visited,:root nav button,
:root details summary{color:#7aa2ff}
:root code,:root pre{background:#1b2230;color:#e5e7eb}
/* Buttons keep a white background from the base sheet; inheriting the dark
   scheme's near-white text on it renders them at 1.1:1 — unreadable. */
/* A CONTROL'S EDGE IS NOT DECORATION. WCAG 1.4.11 asks 3:1 for the boundary
   that tells a reader where a field IS, and #3a4454 renders at 1.88:1 on
   #0f141c and 1.74:1 on a panel — measured live on the deployed landing form
   at a5e1322, where the text and placeholders passed and the boxes around
   them did not. #606e88 is 3.59:1 on the page, 3.32:1 on a panel and 3.10:1
   inside the field. Panel and separator borders stay #3a4454: those are
   decorative, and this rule is only for things you click into. */
:root button,:root input,:root select,:root textarea{background:#1b2230;
color:#f3f4f6;border-color:#606e88}
/* A BORDER-COLOUR WITH NO WIDTH DRAWS NOTHING. The rule above names #606e88
   and stops there, but the base sheet ships a global `button{border:0}`
   (presentation._BASE_CSS) that zeroes the WIDTH, so on every <button> that
   colour had nothing to paint. Measured live on preview-v3 at 81ac65d, in
   dark mode: the landing page's anonymous-entry CTA rendered #1b2230 on
   #0f141c — 1.16:1 — a control a reader can read the label of and cannot see
   the edges of. The inputs passed only because the landing sheet happens to
   set its own 1px width.

   (Phrased without quoting that button's copy on purpose: this stylesheet is
   inlined into every page, comments included, so a label quoted here would
   appear on pages the control itself is switched off for.)

   Checkboxes and radios are excluded on purpose: `:root{color-scheme:dark}`
   above already hands them a native dark boundary, and giving them an author
   border makes the engine drop that native rendering — trading a boundary
   that works for one that also loses the tick. */
:root button,:root input:not([type=checkbox]):not([type=radio]),
:root select,:root textarea{border-style:solid;border-width:1px}
/* ...but a text-styled control is not a box. `nav button` (Log out, Leave
   demo) and `button.linkish` (the example runs) set a transparent background
   deliberately so they read as links beside their real <a> siblings. The
   blanket fill above outranks them, so in dark each one became a flat
   #1b2230 rectangle at 1.16:1 — no longer a link, not yet a visible button.
   Give the transparency back and keep the edge off. Both selectors outrank
   the two rules above, so this holds wherever it lands in the cascade. */
:root nav button,:root button.linkish{background:transparent;border-width:0}
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

#: The shared link is the one page a reader reaches with no session, no nav and
#: no way to ask for anything else, so it carries its own reading layout. It
#: names no colour: every value comes from the shared palette variables, so the
#: dark block in `_A11Y_CSS` can re-point them (see the rule about pages naming
#: colours — a colour a page names is a colour dark mode cannot correct).
_SHARED_CSS = """
<style>
main{max-width:46rem;margin:0 auto;padding:20px 18px 48px;line-height:1.55}
main h1{font-size:1.6rem;margin:0 0 .4rem}
main h2{font-size:1.1rem;margin:1.8rem 0 .6rem}
main section{margin-bottom:.6rem}
ul.cards,ul.limits{list-style:none;padding:0;margin:0}
ul.cards>li{border:1px solid var(--line,#e5e7eb);border-radius:10px;
padding:12px 14px;margin-bottom:10px;background:var(--panel,#f8fafc)}
ul.limits>li{margin:0 0 .35rem 1.1rem;list-style:disc}
p.headline{margin:0 0 .35rem;font-weight:600}
p.muted{margin:.2rem 0;font-size:.9rem;color:var(--muted,#4b5563)}
@media (max-width:600px){main{padding:14px 14px 36px}
main h1{font-size:1.35rem}}
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


class _Unset:
    """Distinguishes "caller passed None on purpose" from "caller said nothing"."""


_UNSET = _Unset()


def _analyst_cache_for(config):
    """Evidence-keyed analyst cache, co-located with the ingestion store.

    Re-opening a report must not pay for a second model call, and a repeated
    analysis of the same evidence is the single largest avoidable cost here.
    The cache key already includes the prompt version and model, so a changed
    prompt invalidates it rather than serving a stale reading.
    """
    try:
        from intent_engine.strategic_intelligence.analyst.runner import FileCache
        ci_path = pathlib.Path(getattr(config, "ci_store_path",
                                       "data/company_ingestion.jsonl"))
        return FileCache(ci_path.parent / "analyst_cache")
    except Exception:  # noqa: BLE001 - the cache is best-effort by contract
        return None


def _conf_para(grade, reason) -> str:
    """Reason first, grade only if it adds something. See render.py."""
    from intent_engine.founder_brief.render import confidence_sentence
    return confidence_sentence(grade, reason)


def _grade_note(grade) -> str:
    """A grade shown alone says nothing; shown after its reasons it is a
    summary. Returns '' for a value that would read as a bare label."""
    from intent_engine.founder_brief.render import is_bare_grade
    g = (grade or "").strip().strip(".")
    if not g:
        return ""
    return f"Overall confidence: {g.lower()}." if is_bare_grade(g) else g


def _retry_phrase(seconds: float) -> str:
    """"Try again later" is not an answer to "when?".

    A founder who has just been refused needs to know whether to wait or to
    give up on the demo, and the window is already known here -- the oldest
    recorded hit decides it. Rounded up, because promising a minute that has
    not elapsed reads as a broken promise.
    """
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return "You can try again in under a minute."
    minutes = int(seconds // 60) + 1
    if minutes < 60:
        return f"You can try again in about {minutes} minutes."
    hours = int(seconds // 3600) + 1
    return f"You can try again in about {hours} hours."


def _with_annual_filing_sections(documents: list) -> list:
    """Replace an annual report's body with its Competition section.

    Everything else passes through untouched. Fully defensive: a filing the
    extractor cannot parse keeps its original text, so this can only ever
    add competitive evidence, never remove a document from the run.

    The truncation note travels with it, so a downstream surface can say the
    filing was read only as far as the retrieval cap reached.
    """
    from intent_engine.external_intel import annual_filing as af

    out = []
    for document in documents:
        title = str(document.get("source_title")
                    or document.get("title") or "")
        if not any(form in title for form in ("10-K", "20-F", "40-F")):
            out.append(document)
            continue
        body = str(document.get("text_content") or document.get("text") or "")
        if not body:
            out.append(document)
            continue
        try:
            sections = af.extract(
                body, form="10-K",
                truncated=bool(document.get("truncated")),
                source_url=str(document.get("url") or ""))
        except Exception:  # noqa: BLE001 - never break a run over a filing
            out.append(document)
            continue
        competition = sections.competition
        if competition is None or not competition.usable:
            out.append(document)
            continue
        out.append(dict(document, text_content=competition.text,
                        text=competition.text,
                        filing_completeness=sections.completeness_note))
    return out


#: Source classes as a reader would name them, for the bounded fallback's
#: "What was found" list. Same vocabulary the readiness note already uses.
_SOURCE_FAMILY = {
    "company_owned": "the company's own pages",
    "investor_material": "investor or earnings material",
    "executive_statement": "an executive statement",
    "customer_voice": "customer accounts",
    "competitor": "a competitor's account",
    "independent_reporting": "independent reporting",
}


class WebApp:
    """The WSGI callable. All state-changing routes require login + CSRF."""

    def __init__(self, config, *, now_fn=None, transport=None,
                 resolver=None, analyst_client=_UNSET):
        config.validate()
        self.config = config
        self.web_store = WebStore(config.web_store_path)
        # THE TENANCY SEAM. Sited beside the other stores rather than built
        # per request: the directory must be reload-stable, because the private
        # graph partition is keyed on the tenant id and a re-minted id would
        # silently show a founder an empty business instead of an error.
        from intent_engine.core.tenant import ScopeAuditLog
        from intent_engine.business_graph.private_store import PrivateGraphStore
        from intent_engine.webapp.tenancy import TenantDirectory, TenantReceiptLog

        _state = config.web_store_path.parent
        self._tenant_directory = TenantDirectory(_state / "tenant_directory.jsonl")
        self._private_graph = PrivateGraphStore(_state)
        self._scope_audit = ScopeAuditLog(_state / "tenant_scope_audit.jsonl")
        self._tenant_receipts = TenantReceiptLog(_state / "tenant_receipts.jsonl")
        # Bounded counters for D-MDR-001. Deliberately in memory and
        # deliberately nameless: a stream recording WHICH private columns a
        # tenant was asked for is itself a private dataset, so this one counts
        # and never names.
        from intent_engine.external_intel.minimum_data_request import (
            MDRTelemetry as _MDRTelemetry,
        )
        self._mdr_telemetry = _MDRTelemetry()
        # The 100-company program's first telemetry substrate. Counts what the
        # Market/Founder join actually did, and keeps "the producer never
        # published" separate from "this side refused it" -- the two numbers
        # whose conflation hid 22 silently refused dossiers.
        from intent_engine.demo_dossier.telemetry import DossierTelemetry
        self._demo_telemetry = DossierTelemetry()
        #: The last per-company bridge reading, for the operator surface. Not
        #: a cache: the dossier build always re-assesses.
        self._market_bridge_last: dict = {}
        self.fi = FounderIntelligenceService(config.fi_store_path)
        # THE REASONING BACKEND WAS NEVER WIRED IN.
        #
        # `CompanyIngestionService` accepts `analyst_client`, and this call
        # never passed one -- so `analyse()` raised AnalystUnavailable on every
        # request no matter what the environment held, and every run took the
        # limited path. `/readyz` reported `strategic_reasoning` from the
        # presence of an env var, which is why the two disagreed: the variable
        # could be set while nothing could ever use it.
        #
        # `default_client()` returns None when no key is configured, so the
        # honest no-backend path is preserved exactly. Tests never reach it:
        # env="test" refuses to build a client, so a stray .env cannot turn a
        # test run into live model calls. Tests that want the analyst inject a
        # recorded client explicitly.
        ci_analyst = analyst_client
        if ci_analyst is _UNSET:
            ci_analyst = None
            if config.env != "test":
                from intent_engine.strategic_intelligence.analyst.runner import (
                    default_client,
                )
                try:
                    ci_analyst = default_client()
                except Exception:  # noqa: BLE001 - never fail to boot on this
                    _LOG.warning("analyst client unavailable; "
                                 "continuing without a reasoning backend")
                    ci_analyst = None
                    self._analyst_error = "key present but no client was built"
        # WHY the backend is off, not just THAT it is off.
        #
        # `/readyz` reports whether a client exists, which is the honest
        # capability signal -- but it cannot tell a MISSING key apart from a
        # key that is present and unusable, and those need opposite fixes:
        # add the variable, or fix the code. A whole cycle was spent guessing
        # between them. Both are booleans; the value is never read anywhere.
        import os as _os
        self._analyst_key_present = bool(_os.environ.get("ANTHROPIC_API_KEY"))
        if not getattr(self, "_analyst_error", ""):
            self._analyst_error = (
                "" if ci_analyst is not None
                else ("ANTHROPIC_API_KEY is not set in this environment"
                      if not self._analyst_key_present
                      else "key present but no client was built"))
        self._analyst_client = ci_analyst
        # Listing resolution needs the same outbound path as retrieval, and
        # the same discipline as the analyst client above: env="test" never
        # reaches the network, so the suite stays hermetic and a stray
        # environment cannot turn a test run into live SEC traffic. Both
        # caches are per-process; the SEC table changes daily at most, and
        # re-fetching it per page render would put a network round trip in
        # front of a dashboard.
        self._transport = transport
        self._resolver = resolver
        self._sec_map = None
        self._listing_cache: dict = {}
        # External context is assembled once per run and shared by every
        # founder surface, so the dashboard, the narrative, the brief and the
        # full analysis cannot disagree about what the market did.
        self._external_cache: dict = {}
        self.ci = CompanyIngestionService(
            getattr(config, "ci_store_path", "data/company_ingestion.jsonl"),
            transport=transport, resolver=resolver,
            analyst_client=ci_analyst,
            analyst_cache=_analyst_cache_for(config))
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
        # ASYNCHRONOUS ANALYSIS.
        #
        # `POST /analyze` used to run discovery, retrieval, reasoning and
        # rendering inside the request. A real browser on the deployed preview
        # was blocked for the WHOLE analysis -- minutes for Costco -- and the
        # progress page, which already records truthful stages, could not be
        # reached during the one window it exists to explain.
        #
        # In-process and bounded, not a second job framework: the run, its
        # ownership and every stage transition are already persisted by the
        # ingestion service, so the request only has to stop waiting for them.
        # One worker, because the preview is a free instance and two
        # concurrent analyses would contend for its memory.
        import threading as _threading
        from concurrent.futures import ThreadPoolExecutor as _Pool
        self._analysis_pool = _Pool(max_workers=1,
                                    thread_name_prefix="analysis")
        self._analysis_lock = _threading.Lock()
        self._analysis_inflight: dict = {}   # run_id -> started monotonic
        self._analysis_attempts: dict = {}   # run_id -> executions started
        # Instrumented so duplicate execution is measurable rather than
        # inferred from output: a second worker on one attempt can produce an
        # identical-looking result while doing the work twice.
        self._worker_starts: dict = {}      # run_id -> worker entries
        self._terminal_writes: dict = {}    # run_id -> terminal transitions
        # ASYNC EVERYWHERE, INCLUDING TESTS.
        #
        # This was briefly gated on env != "test" so the existing suite could
        # keep asserting on finished runs. That left 3000+ tests exercising a
        # code path real users no longer receive -- the route returned
        # immediately in production and blocked in every test. The divergence
        # is the bug: the harness waits now (see tests/conftest.py), the
        # product does not.
        self._analysis_async = True
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

        # MACHINE ROUTE, HANDLED BEFORE ANYTHING READS THE BODY.
        #
        # Deliberately above the session lookup and above `self._form`, which
        # consumes `wsgi.input` and would leave nothing to read. It carries no
        # cookie and cannot: the caller is the market publisher on another
        # machine, authenticated by a shared token rather than by a session,
        # so the CSRF gate below has nothing to protect here and no session to
        # protect it with.
        #
        # It does not exist unless configured, and never in production. See
        # `external_intel/dossier_ingest`.
        if path == "/internal/strategic-dossier" and method == "POST":
            return self._ingest_strategic_dossier(environ)

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
        post_exempt = ("/login", "/signup", "/internal/acceptance")
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
        if path == "/internal/acceptance" and method == "POST":
            return self._acceptance(environ)
        if path == "/internal-impact" and method == "GET":
            return self._internal_impact(session, environ)
        if path == "/decisions" and method == "GET":
            return self._decisions(session, environ)
        # The write path. POST-only and NOT in `post_exempt`, so it carries
        # the ordinary session + CSRF gate above: recording what a person
        # chose is the most forgeable thing in the product.
        if path == "/decisions/record" and method == "POST":
            return self._record_decision(session, form, environ)
        # NOT "/learning": that path is the operations dashboard and is
        # login-gated. Mounting an unauthenticated page there shadowed it and
        # let a demo guest read the operations view -- caught by
        # test_a_demo_guest_cannot_read_the_operations_dashboard.
        if path == "/learning-acceleration" and method == "GET":
            return self._learning_acceleration(environ)
        if path == "/demo-dossiers/telemetry" and method == "GET":
            return self._ok_json(self._demo_telemetry.as_dict())
        if path == "/demo-dossiers" and method == "GET":
            return self._demo_dossier_index()
        # THE RENDERED SCREENS, BEFORE THE JSON PREFIX MATCH.
        #
        # `/demo-dossiers/<c>` is a prefix match, so it would swallow
        # `/demo-dossiers/<c>/xray` and hand "cloudflare/xray" to the store
        # as a company id -- a 404 that reads like the company is missing.
        if route == ("GET", "demo-dossiers", 3) and parts[2] in (
                "xray", "full", "deck"):
            return self._decision_screen(parts[1], parts[2])
        if route == ("GET", "demo-dossiers", 3) and parts[2] == "memory":
            return self._memory_screen(parts[1])
        if route == ("GET", "demo-dossiers", 3) and parts[2] == "evidence":
            return self._evidence_screen(parts[1])
        if path.startswith("/demo-dossiers/") and method == "GET":
            return self._demo_dossier_detail(path[len("/demo-dossiers/"):])
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
        if route == ("GET", "runs", 3) and parts[2] == "story":
            return self._story_page(session, parts[1])
        if route == ("GET", "runs", 3) and parts[2] == "dashboard":
            return self._intelligence_page(session, parts[1])
        if route == ("GET", "runs", 3) and parts[2] == "brief":
            return self._executive_brief_page(session, parts[1])
        if route == ("GET", "runs", 3) and parts[2] == "xray":
            return self._run_xray(session, parts[1])
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
                429, "Demo analysis limit reached for your network. "
                     f"{_retry_phrase(min(ip_hits) + 3600 - now)} "
                     "Analyses already running are unaffected, and finished "
                     "ones stay under your analyses.")
        if len(session_hits) >= self.config.demo_session_analyses_per_day:
            session["analyses"] = session_hits
            self._demo_ip_hits[remote] = ip_hits
            return self._error_page(
                429, "This demo session has reached its analysis limit for "
                     "today. "
                     f"{_retry_phrase(min(session_hits) + 86400 - now)} "
                     "Analyses already running are unaffected, and finished "
                     "ones stay under your analyses.")
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
        # A <style> BLOCK IS NOT CONTENT, AND IT WAS SITTING IN <main>.
        #
        # `LAYER_CSS` is prepended to the fragment each layer renderer returns,
        # so the dashboard, the story and the actions list each carried a copy
        # INSIDE the element that holds the reading. Invisible to a reader, and
        # it is stylesheet text inside `main.innerText` -- so every text-based
        # gate, every accessibility tree and every extractor read CSS as part
        # of the analysis.
        #
        # Hoisted here rather than at the twenty call sites that build a body,
        # because this is the one function every HTML response passes through,
        # and a rule that has to be remembered at each call site is a rule that
        # will be missed at the twenty-first.
        #
        # Order is preserved deliberately: the shared sheet, then the
        # accessibility baseline, then the page's own rules -- exactly the
        # cascade that held when the page's rules lived below in the body.
        head, sep, rest = body.partition("</head>")
        hoisted: list = []

        def _take(match):
            hoisted.append(match.group(0))
            return ""

        rest = _STYLE_BLOCK.sub(_take, rest)
        return head + head_extra + "".join(hoisted) + sep + rest

    def _html(self, body, *, status="200 OK", extra_headers=()):
        return status, [("Content-Type", "text/html; charset=utf-8"),
                        *extra_headers], self._stylize(body)

    def _ok_json(self, obj):
        return "200 OK", [("Content-Type", "application/json")], json.dumps(obj)

    def _ingest_strategic_dossier(self, environ):
        """Accept one published dossier from the market publisher.

        Thin on purpose: read the body, hand it to the contract, translate the
        refusal into a status. Every decision about what is acceptable lives
        in `dossier_ingest`, which shares the allowlist with the local file
        path, so this route cannot become a second, weaker way in.
        """
        from intent_engine.external_intel import dossier_ingest as DI
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except (TypeError, ValueError):
            length = 0
        if length > DI.MAX_BYTES:
            return ("413 Payload Too Large",
                    [("Content-Type", "application/json")],
                    json.dumps({"error": "dossier too large"}))
        raw = environ["wsgi.input"].read(length) if length else b""
        try:
            result = DI.ingest(
                raw, runtime_root=self._runtime_root,
                provided_token=environ.get("HTTP_X_DOSSIER_TOKEN", ""),
                request_host=environ.get("HTTP_HOST", ""))
        except DI.IngestRefused as exc:
            _LOG.info("strategic dossier refused: %s", exc.reason)
            return (f"{exc.status} Refused",
                    [("Content-Type", "application/json")],
                    json.dumps({"error": exc.reason}))
        # The consumer caches external context per run; a newly-arrived
        # dossier must be visible to the NEXT analysis rather than to the
        # next process.
        self._external_cache.clear()
        _LOG.info("strategic dossier %s for %s (%s)", result["status"],
                  result["company_id"], result["revision"])
        return self._ok_json(result)

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
        """A reader-facing failure. Never a status line and an exception.

        Measured live: `GET /runs/{id}` on a run that had not yet been
        approved answered "Bad request / approve at least one source" — a
        framework status and an internal message, which tells a reader they
        did something wrong when the run had simply not reached its next step.

        The category decides what is said; `message` never reaches the page.
        It is hashed into a short reference an operator can correlate.
        """
        category = _failures.classify(message)
        # Decided from the message's OWN classification, before any
        # code-specific substitution below replaces it: substituting first and
        # then reading `explained["category"]` made every unrecognised 404
        # look understood, and silently dropped the one sentence it had.
        understood = category != _failures.INTERNAL_FAILURE
        if code in (403, 429) and category == _failures.INTERNAL_FAILURE:
            titles = {403: "That is not available to this session",
                      429: "Too many analyses for now"}
            explained = {
                "category": category, "title": titles[code],
                "what_worked": "Your session is active.",
                "what_failed": "This request was not carried out.",
                "why": ("This preview limits how much one visitor can run, so "
                        "it stays available to everyone."
                        if code == 429 else
                        "This session does not have access to that."),
                "next_step": ("Wait a little and try again."
                              if code == 429 else "Start a new analysis."),
                "retryable": code == 429,
            }
        elif code == 404 and category == _failures.INTERNAL_FAILURE:
            explained = _failures.explain(_failures.NOT_FOUND)
        else:
            explained = _failures.explain(category)
        # THE MESSAGE IS SUPPRESSED ONLY WHERE IT WAS UNDERSTOOD.
        #
        # When `classify` recognised the cause, this module has better words
        # for it than the exception did, and showing both would be showing the
        # internal one. When it did NOT recognise the cause, the message is the
        # only information there is — and it is carrying things a reader needs:
        # the 500 handler puts the log-correlation reference in it, debug mode
        # puts the traceback in it, and a revoked share link explains itself
        # there. Dropping it unrecognised would trade one silence for another.
        detail = "" if understood else (message or "")
        return self._failure_response(code, explained, detail)

    def _failure_response(self, code, explained, detail=""):
        retry = ('<p><a class="cta" href="/">Run a new analysis</a></p>'
                 if explained["retryable"] else
                 '<p><a href="/">Back to start</a></p>')
        body = (
            f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,'
            f'initial-scale=1">'
            f'<title>{_e(explained["title"])}</title></head><body>'
            f'<main class="brief"><h1>{_e(explained["title"])}</h1>'
            f'<p><strong>What did work.</strong> '
            f'{_e(explained["what_worked"])}</p>'
            f'<p><strong>What did not.</strong> '
            f'{_e(explained["what_failed"])}</p>'
            f'<p><strong>Why.</strong> {_e(explained["why"])}</p>'
            f'<p><strong>What to do next.</strong> '
            f'{_e(explained["next_step"])}</p>'
            f'{retry}'
            + (f'<p class="small muted">{_e(detail)}</p>' if detail else "")
            + '</main></body></html>')
        titles = {400: "Bad Request", 403: "Forbidden", 404: "Not Found",
                  429: "Too Many Requests", 500: "Internal Server Error"}
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

    def _analyze(self, session, form, remote="unknown", *, smoke=False,
                 fresh=False):
        if form.get("consent") is None:
            return self._error_page(400, "consent is required")
        limited = None if smoke else self._demo_rate_limited(session, remote)
        if limited is not None:
            return limited
        company_name = form.get("company_name", "")[:120].strip()
        website = (form.get("website") or "").strip()
        #: Set only when the company was identified as an SEC filer with no
        #: domain on record. It is what lets the run open at all, and it must
        #: never be filled in from anywhere else -- a CIK guessed from a name
        #: attributes one company's filings to another.
        filer_cik = ""

        # THE NAME IS ENOUGH.
        #
        # `website` used to default to the demo domain when absent, and the
        # branch below reads that default as "run the canned demo". So once
        # the form stopped requiring a URL, typing "Cloudflare" would have
        # analysed the sample company instead -- a confident report about
        # somebody else, which is the worst failure this product has.
        #
        # A typed name is resolved against the entity registry, which is the
        # component that exists for exactly this and was previously only
        # consulted when a website had already been supplied.
        if company_name and not website and not form.get("entity_id"):
            from intent_engine.company_ingestion import name_entry as _NE
            # The SEC registrant source is opted into PER CALL, not by a
            # module flag: a live request is exactly the context where the
            # one outbound lookup belongs, and no other caller in the
            # process should start making it as a side effect. Without it
            # the register is ~105 companies and every other real firm on
            # earth comes back "not found".
            # THE ONE OUTBOUND LOOKUP, and it is off under test.
            #
            # Threading the app's transport through is not sufficient on its
            # own: some tests construct WebApp with no transport at all, so
            # the lookup fell back to the real SEC and every such test paid
            # an 8-second timeout. The suite crawled at 7% twice before this
            # was pinned. `env` is the honest gate -- a test must never make
            # an outbound call, whatever transport it did or did not inject.
            entry = _NE.resolve(company_name=company_name,
                                allow_registrant=True,
                                transport=self._transport,
                                resolver=self._resolver)
            if entry.state == _NE.AMBIGUOUS_COMPANY:
                # Two real companies share this name. Asking is strictly
                # better than picking, and it is asked once, before any work.
                return self._name_choice_page(session, entry, form)
            if entry.resolved:
                company_name = entry.company_name
                website = entry.website
            elif entry.state == _NE.IDENTIFIED_NO_DOMAIN:
                # A FILER IS ANALYSABLE WITHOUT A WEBSITE. The regulator
                # records no domain, and guessing one would send retrieval at
                # whatever sits on it. What it does record is every filing
                # this company has made, which is more authoritative than the
                # marketing site would have been. The run is opened on the
                # CIK and the acquisition path is EDGAR-first.
                company_name = entry.company_name
                filer_cik = entry.company_id
            else:
                # NOT A BAD REQUEST. The user did nothing wrong: this is a
                # company the registry does not carry. Say so, and offer the
                # one input that would resolve it, rather than returning a
                # 400 the user cannot act on.
                return self._company_not_found_page(session, company_name,
                                                    entry)
        if not website and not filer_cik:
            website = f"https://{DEMO_DOMAIN}"
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
        # A domainless filer skips this block entirely: every branch inside
        # it resolves or names the company FROM its website, and there isn't
        # one. Its name came from the regulator, which is a better source
        # than a domain would have been.
        # THIS CONDITION SELECTS THE REAL-COMPANY PATH, not merely a block of
        # entity resolution -- everything below it up to and including
        # `create_run` is the real analysis, and the `else` at the end of the
        # method runs the SYNTHETIC DEMO.
        #
        # A first version guarded this with `website and ...`, reasoning that
        # a domainless filer has nothing to resolve from a website. True, and
        # it dropped Toyota and Vale straight through to the demo: both came
        # back as a confident report titled "Northwind Logistics Cloud
        # (synthetic demo)", under a run id shared by every company that took
        # the same fall. A report about the wrong company is the worst thing
        # this product can emit, and it shipped because the guard was placed
        # by what the block APPEARED to do at the top rather than by what it
        # returns at the bottom. Found on the deployed service.
        #
        # A resolved filer is a real company and takes the real path.
        if filer_cik or (website and DEMO_DOMAIN not in website):
            # The website-derived resolution below is skipped for a filer:
            # there is no website to resolve from, and its name came from the
            # regulator, which is a better source than a domain would be.
            if not chosen and website:
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
                    website=website, cik=filer_cik,
                    user_id=session["user_id"],
                    as_of=self._as_of(fresh=fresh))
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
            if self.config.autorun_sources:
                # Frictionless default: no separate source-review page. The
                # work is SCHEDULED and the response returns at once;
                # discovery is itself a network call and belongs off the
                # request thread with everything after it.
                if self._analysis_async:
                    self._schedule_analysis(session["user_id"], run_id)
                    return self._redirect(f"/runs/{run_id}/progress")
                self.ci.discover(run_id)
                return self._autorun(session, run_id)
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

    def _name_choice_page(self, session, entry, form):
        """One name, several real companies. Ask, once, before any work.

        The choices carry a NAME, not an entity id the user could not have
        meant anything by: a business reader tells companies apart by legal
        name, sector and country. Each card posts the resolved legal name so
        the next request resolves exactly, without this page having to know
        which registry the candidate came from.
        """
        csrf = session["csrf"] if session else ""
        cards = "".join(
            f'<form action="/analyze" method="post" class="choice">'
            f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
            f'<input type="hidden" name="consent" value="1">'
            f'<input type="hidden" name="company_name" '
            f'value="{_e(c["legal_name"])}">'
            f'<input type="hidden" name="business_question" '
            f'value="{_e(form.get("business_question", ""))}">'
            f'<h3>{_e(c["legal_name"])}</h3>'
            f'<p class="state">{_e(c.get("describe", ""))}</p>'
            f'<p class="why">{_e(c.get("note", ""))}</p>'
            f'<button type="submit">Analyse {_e(c["legal_name"])}</button>'
            f'</form>' for c in entry.choices)
        body = (
            f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,'
            f'initial-scale=1"><title>Which company do you mean?</title>'
            f'</head><body>{self._nav(session, csrf)}<main>'
            f'<h1>Which company do you mean?</h1>'
            f'<p>{_e(entry.reason)}. These are different companies with '
            f'different products, results and risks, so the answer depends '
            f'on which one you want.</p>{cards}'
            f'<p><a href="/">Start over with a different company</a></p>'
            f'</main></body></html>')
        return self._html(body)

    def _company_not_found_page(self, session, company_name, entry=None):
        """COMPANY_NOT_FOUND, as a state the user can act on.

        This replaces a 400. A name the registry does not carry is not a
        malformed request -- it is the ordinary case of a private company, a
        misspelling, or a firm nobody has analysed here yet, and all three
        are answered by the same thing: the website, which is the strongest
        identity signal a person can give.

        The form comes back with the name still in it. Making the user retype
        what they already typed is how a recoverable state becomes a dead end.

        TWO DIFFERENT STATES SHARE THIS FORM, and they must not share its
        words. When the SEC names the company as a registrant we know exactly
        who it is and lack only its domain, and telling that user "we could
        not identify Toyota Motor Corporation" is simply false. The form is
        the same because the next step is the same; the heading is not.
        """
        csrf = session["csrf"] if session else ""
        identified = entry is not None and getattr(entry, "state", "") == \
            "IDENTIFIED_NO_DOMAIN"
        if identified:
            ticker = getattr(entry, "ticker", "") or ""
            heading = (f'We found &ldquo;{_e(entry.company_name)}&rdquo;'
                       f'{f" ({_e(ticker)})" if ticker else ""}')
            explain = (
                f'<p>It is a filing registrant with the SEC, so its identity '
                f'is not in doubt. What the regulator does not record is a '
                f'web address, and we will not guess one — a guessed domain '
                f'sends the analysis at somebody else&rsquo;s company.</p>')
        else:
            heading = f'We could not identify &ldquo;{_e(company_name)}&rdquo;'
            explain = (
                '<p>No company by that name is in our register. That usually '
                'means one of three things: it is privately held, the name is '
                'spelled differently in its filings, or nobody has analysed '
                'it here yet. None of them is a problem with what you '
                'typed.</p>')
        title = "Company identified" if identified else "Company not found"
        body = (
            f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,'
            f'initial-scale=1"><title>{title}</title>'
            f'</head><body>{self._nav(session, csrf)}'
            f'<main class="notice"><h1>{heading}</h1>'
            f'{explain}'
            f'<p>Its website settles it — a domain names exactly one '
            f'company.</p>'
            f'<form action="/analyze" method="post" class="analyze">'
            f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
            f'<input type="hidden" name="consent" value="1">'
            f'<p><label for="company_name">Company name</label> '
            f'<input id="company_name" name="company_name" '
            f'value="{_e(company_name)}" required></p>'
            f'<p><label for="website">Website</label> '
            f'<input id="website" name="website" type="url" '
            f'placeholder="https://www.example.com" autofocus required></p>'
            f'<button type="submit">Analyse company</button></form>'
            f'<p><a href="/">Start over</a></p></main></body></html>')
        return self._html(body)

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

    #: Backend transitions the ingestion service ALREADY records, mapped to
    #: words a founder reads. Only states that genuinely occur are listed --
    #: claiming "checking outside context" for a stage that never runs is the
    #: dishonesty this mapping exists to avoid.
    STAGE_COPY = {
        "VALIDATING_COMPANY": "Checking which company this is",
        "DISCOVERING_SOURCES": "Finding the company's own, investor and "
                               "regulatory sources",
        "AWAITING_SOURCE_APPROVAL": "Choosing which sources to read",
        "FETCHING_APPROVED_SOURCES": "Reading the most relevant material",
        "PARSING_SOURCES": "Reading the most relevant material",
        "BUILDING_SOURCE_ARTIFACTS": "Organising what the sources actually say",
        "ASSEMBLING_COMPANY_UNDERSTANDING": "Testing whether the evidence "
                                            "supports a useful conclusion",
        "ASSEMBLING_REPORT": "Writing the founder briefing",
    }

    def _stage_line(self, state) -> str:
        """One truthful sentence, or an honest general fallback."""
        return self.STAGE_COPY.get(
            state or "", "Still working through the available evidence")

    def _elapsed_line(self, run_id: str) -> str:
        """Real elapsed time. Never a percentage, never a countdown."""
        import datetime as _dt
        first = None
        for row in self.ci.store.for_run(run_id):
            first = getattr(row, "recorded_at", None)
            if first:
                break
        if not first:
            return "Just started."
        try:
            began = _dt.datetime.fromisoformat(str(first).replace("Z", "+00:00"))
        except ValueError:
            return "Just started."
        seconds = int((_dt.datetime.now(_dt.timezone.utc) - began)
                      .total_seconds())
        if seconds < 60:
            return f"Running for {max(seconds, 1)}s."
        return f"Running for {seconds // 60}m {seconds % 60}s."

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
        # Read the one list. A local tuple here omitted INTERRUPTED, and
        # because the stale-marker refuses to re-mark a run it has already
        # marked, such a run polled itself every four seconds forever under
        # "Reading the public evidence..." -- a dead run wearing a live stage.
        terminal = status in self.TERMINAL_STATES
        # FOUNDER BRIEF FIRST.
        #
        # The original fix here was "do not stop on a status page" and it sent
        # the reader to the deck, which was right at the time -- the deck beat
        # an eleven-section report. It is no longer the shortest useful thing
        # in the product: the 60-second founder brief is, and a deck is still
        # a document someone has to work through before they learn anything.
        #
        # So completion lands on /runs/<id>. The deck keeps its own route and
        # its place in the layer nav; it is one click away, not compulsory.
        if status in ("COMPLETE", "PARTIAL"):
            return self._redirect(f"/runs/{run_id}")

        # A worker that vanished must not leave this page polling forever.
        if not terminal and self._interrupted_if_stale(run_id):
            status = self.ci.store.run_state(run_id) or status
            terminal = True
        refresh = ('' if terminal
                   else '<meta http-equiv="refresh" content="4">')
        # A run that failed must say so in the heading. Softening every state
        # into "Reading the public evidence…" would hide a failure behind a
        # progress message, which is worse than the jargon it replaced.
        heading = {
            "FAILED": "This analysis could not be completed",
            # Say what happened. "Reading the public evidence..." on a run
            # whose worker died is a progress message covering for a stop.
            "INTERRUPTED": "This analysis was interrupted",
            "REJECTED": "This analysis was not accepted",
        }.get(status, "Reading the public evidence…")
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
            # THE STAGE, THE ELAPSED TIME, AND WHERE TO FIND THIS LATER.
            # No percentage and no countdown: there is no honest denominator
            # for either, and a fake one is worse than none.
            # THE CANONICAL HYDRATION PROJECTION, not a generic stage line.
            # `hydration.assess` was built, unit-proven and called by nothing
            # on the customer path, so the page a reader actually watches
            # still showed one lifecycle-derived sentence. Its `current_step`
            # is the same sentence the tier table is derived from, so the
            # headline and the detail cannot disagree.
            hyd = self._hydration_state(run_id, terminal=terminal)
            step = (hyd.get("current_step") or "").strip() \
                or self._stage_line(status)
            tail = (f'<p role="status" aria-live="polite">'
                    f'<strong>{_e(step)}.</strong></p>'
                    f'{self._hydration_body(hyd)}'
                    f'<p>{_e(self._elapsed_line(run_id))}</p>'
                    f'<p>You can safely leave this page — the analysis keeps '
                    f'running, and it will be waiting under '
                    f'<a href="/analyses">your analyses</a>.</p>'
                    f'<p class="coverage">This preview stores runs in memory, '
                    f'so a restart can interrupt one. If that happens the page '
                    f'says so rather than waiting forever.</p>')
        return self._html(head + tail + '</main></body></html>')

    def _hydration_state(self, run_id, *, terminal=False):
        """What this run can already show, measured from its own outputs.

        Every argument is read from a PRODUCER, never from elapsed time. That
        is the whole contract: a tier is READY because something produced its
        output, so a slow run reports honestly instead of a fast one lying.
        A read that fails costs the reader the tier table, never the page.
        """
        try:
            from intent_engine.founder_brief import hydration
            meta = self.ci.run_meta(run_id) or {}
            avail = self._availability(run_id)
            result = self._results.get(run_id) or {}
            report = result.get("strategic_report") \
                if isinstance(result, dict) else None
            decision = {}
            if isinstance(report, dict):
                from intent_engine.strategic_intelligence.decision import \
                    decision_of
                composed = decision_of(report)
                decision = composed.as_dict() if composed is not None else {}
            try:
                discovery = self.ci.discovery_report(run_id)
            except Exception:                               # noqa: BLE001
                discovery = None
            return hydration.assess(
                identity=str(meta.get("company_name") or "") or None,
                previous_decision=None,
                market_snapshot=self._market_snapshot(run_id)
                if self._listing_for(run_id).ticker else None,
                source_coverage=(result.get("coverage")
                                 if isinstance(result, dict) else None),
                discovery_coverage=discovery,
                decision=decision,
                economic_history=decision.get("economic_history") or None,
                second_iteration=decision.get("second_iteration") or None,
                blocked=bool(avail.get("blocked")),
                finished=bool(terminal))
        except Exception:                                   # noqa: BLE001
            _LOG.warning("hydration not assessed for %s", run_id)
            return {}

    @staticmethod
    def _hydration_body(hyd) -> str:
        """The tier table, in the reader's words.

        Ordered by what a reader can ACT on rather than by pipeline order,
        which is what lets this page be worth reading before it finishes. The
        raw state never reaches the sentence: PENDING/RUNNING/READY are
        machine words, and a customer watching an analysis should be told what
        is known, not which enum a producer landed in.
        """
        if not hyd or not hyd.get("tiers"):
            return ""
        from intent_engine.founder_brief import hydration as H
        said = {H.READY: "done", H.BOUNDED: "partial",
                H.DEGRADED: "limited", H.RUNNING: "working",
                H.PENDING: "waiting"}
        rows = "".join(
            f'<li>{_e(H.TIER_COPY.get(tier, tier))} — '
            f'{_e(said.get(hyd["tiers"].get(tier), "unknown"))}</li>'
            for tier in H.TIERS)
        return f'<ul class="hydration">{rows}</ul>'

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
        # WHAT WAS READ, WHEN ANYTHING WAS. "no approved source could be
        # retrieved" is the reason a run has no report, and it was printed
        # unconditionally — including for runs where the store DID hold
        # documents. Measured live on preview-v3, twice (Alphabet,
        # https://abc.xyz): every guessed path 404'd, the run went FAILED, and
        # EDGAR then returned the 10-K and the 10-Q. This page told the reader
        # nothing had been retrieved while `/brief`, reading the same store,
        # listed both filings under "What could actually be read".
        #
        # The reader is owed the true sentence and the place the evidence is,
        # so say what was read and link to it. Re-routing the page was tried
        # twice and answered 500 both times: the deeper surfaces are built for
        # a run that composed something, and this one did not.
        read = self._retrieved_documents(run_id)
        if read:
            titles = [str(d.get("title") or d.get("final_url") or "").strip()
                      for d in read]
            titles = [t for t in titles if t][:5]
            listed = "".join(f'<li>{_e(t)}</li>' for t in titles)
            opening = (
                f'<p>Run <code>{_e(run_id)}</code> did not produce a report: '
                f'not enough of what it needed could be retrieved, so no '
                f'reading is asserted here — we do not invent one.</p>'
                f'<p><strong>{len(read)} source(s) were read</strong> before '
                f'it stopped, and the executive brief covers what they '
                f'support: <a href="/runs/{_e(run_id)}/brief">read the '
                f'brief</a>.</p>'
                + (f'<h2>What was read</h2><ul>{listed}</ul>' if listed else ''))
        else:
            opening = (
                f'<p>Run <code>{_e(run_id)}</code> did not produce a report '
                f'because no approved source could be retrieved. There is no '
                f'result to show — we do not invent one.</p>')
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,'
                f'initial-scale=1"><title>Analysis could not be completed'
                f'</title></head><body>{self._nav(session, session["csrf"])}'
                f'<main><h1>This analysis could not be completed</h1>'
                f'{opening}'
                f'<p>Public websites can refuse automated access, rate-limit '
                f'requests, or require JavaScript to render. A failed '
                f'retrieval is not evidence that anything is missing in the '
                f'real world.</p>{detail_block}'
                f'{self._targeted_retry_action(session, run_id)}'
                f'<p><a href="/">Start a new analysis</a></p>'
                f'</main></body></html>')
        return self._html(body)

    def _targeted_retry_action(self, session, run_id) -> str:
        """The second look, offered here only when it has somewhere to go.

        `_insufficient_evidence_page` has offered this since it was written.
        This page — the one a reader gets when the run produced no report at
        all — never did, so the only exit was "Start a new analysis", which
        re-runs everything from scratch and pays for the whole analysis again.
        Measured on a run whose sources were all unreachable: `retry_state`
        returned allowed (FAILED is retryable by design) and
        `_has_untried_sources` returned True — the machinery for a cheap,
        targeted second look was ready and nothing on the page reached it.

        The condition is deliberately the same one the other page uses rather
        than a new one. A retry with nowhere new to look is a button that can
        only repeat itself, and `_insufficient_evidence_page` is right that
        this is worse than no button: it looks like progress. So both gates
        apply — somewhere new to go, AND a retry the run is actually owed
        (ownership, not already running, budget not spent).
        """
        try:
            if not self._has_untried_sources(run_id):
                return ""
            if not self.retry_state(session, run_id).get("allowed"):
                return ""
        except Exception:                       # never break the failure page
            return ""
        csrf = _e(session.get("csrf", "")) if session else ""
        return (f'<form action="/runs/{_e(run_id)}/retry" method="post" '
                f'class="action">'
                f'<input type="hidden" name="csrf" value="{csrf}">'
                f'<button type="submit">Look again for the missing evidence'
                f'</button>'
                f'<p class="why">Runs one more targeted search for the kinds '
                f'of source that are missing, skipping everything that '
                f'already failed. Nothing already verified is discarded.</p>'
                f'</form>')

    # =====================================================================
    # PREVIEW-ONLY ACCEPTANCE RUNS
    # =====================================================================
    #
    # The public demo allows ten analyses per IP per rolling hour. That is an
    # abuse guardrail on a public URL and it does not move -- which is exactly
    # why a twenty-company matrix could not be driven through the guest flow,
    # and why every previous cycle generalised from one or five companies.
    #
    # This is NOT a second analysis path. It calls the same `_analyze` the
    # guest form calls, with `smoke=True`, and that flag buys exactly one
    # thing: the quota. If the runner could produce a result the product
    # cannot, the matrix would be measuring the runner.

    #: How long one company may take before the entry is recorded timed out.
    ACCEPTANCE_TIMEOUT_S = 420
    ACCEPTANCE_POLL_S = 5
    #: Bounded request body. An acceptance request is a short JSON list.
    ACCEPTANCE_MAX_BODY = 16_384

    def _acceptance(self, environ):
        """Run a bounded acceptance matrix. Preview-only, authenticated.

        Every refusal returns the SAME 404 with no body detail: an endpoint
        that answers "wrong token" differently from "not enabled here" tells
        an unauthenticated caller which of the two it is.
        """
        try:
            expected = (_acc.token_from_env() or "").strip()
            _acc.authorise(env=self.config.env, expected=expected,
                           presented=(environ.get(_acc.ACCEPTANCE_HEADER)
                                      or "").strip())
        except _acc.AcceptanceRefused:
            return self._error_page(404, "page not found")
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > self.ACCEPTANCE_MAX_BODY:
            return self._ok_json({"error": "invalid request size"})
        try:
            payload = json.loads(
                environ["wsgi.input"].read(length).decode("utf-8"))
            requested = _acc.plan(
                payload.get("companies"),
                max_companies=payload.get("max_companies"),
                concurrency=payload.get("concurrency"),
                budget=payload.get("budget"))
        except (ValueError, KeyError, TypeError, _acc.AcceptanceRefused) as exc:
            # The refusal reason is safe here: the caller is authenticated.
            return self._ok_json({"error": str(exc)[:200]})

        run_id = str(payload.get("acceptance_run_id") or "")[:64] or \
            f"acc-{uuid.uuid4().hex[:12]}"
        ledger = _acc.Ledger(
            pathlib.Path(self.config.web_store_path).parent
            / "acceptance.jsonl", run_id=run_id)
        if payload.get("cancel"):
            ledger.cancel()
            return self._ok_json({"acceptance_run_id": run_id,
                                  "cancelled": True,
                                  "summary": ledger.summary()})
        if ledger.cancelled:
            return self._ok_json({"acceptance_run_id": run_id,
                                  "cancelled": True,
                                  "summary": ledger.summary()})

        pending = ledger.pending(requested["companies"],
                                 force_fresh=bool(payload.get("force_fresh")))
        spent = sum(1 for e in ledger.entries.values()
                    if e.state in _acc.TERMINAL and e.state !=
                    _acc.BUDGET_EXHAUSTED)
        for company in pending:
            if spent >= requested["budget"]:
                ledger.record(_acc.Entry(
                    requested_company=company["name"],
                    website=company["website"],
                    state=_acc.BUDGET_EXHAUSTED,
                    reasons=["analysis budget exhausted before this entry"]))
                continue
            spent += 1
            ledger.record(self._acceptance_one(company, run_id=run_id))
        return self._ok_json({
            "acceptance_run_id": run_id,
            "deployed_commit": self._deployed_commit(),
            "summary": ledger.summary(),
            "entries": [asdict(e) for e in ledger.entries.values()],
        })

    def _deployed_commit(self) -> str:
        try:
            from intent_engine._version import version_info
            return str(version_info().get("commit", ""))[:12]
        except Exception:                                     # noqa: BLE001
            return ""

    def _acceptance_one(self, company, *, run_id):
        """One company, through the real pipeline, scored deterministically."""
        entry = _acc.Entry(requested_company=company["name"],
                           website=company["website"],
                           state=_acc.RUNNING, started_at=time.time())
        sid = self.auth.create_anonymous_session()
        session = self.auth.session(sid)
        try:
            response = self._analyze(
                session, {"consent": "1", "company_name": company["name"],
                          "website": company["website"]},
                remote="acceptance", smoke=True)
        except Exception as exc:                              # noqa: BLE001
            entry.state = _acc.FAILED
            entry.internal_failure_category = _failures.classify(str(exc))
            entry.reasons = ["the analysis raised before producing a page"]
            entry.completed_at = time.time()
            return entry
        location = dict(response[1]).get("Location", "")
        match = re.search(r"/runs/([A-Za-z0-9_-]+)", location)
        if not match:
            entry.state = _acc.FAILED
            entry.internal_failure_category = _failures.COMPANY_RESOLUTION_FAILED
            entry.reasons = ["no analysis was created for this company"]
            entry.completed_at = time.time()
            return entry
        analysis_id = match.group(1)
        entry.analysis_id = analysis_id
        entry.fresh_or_reused = ("reused" if analysis_id in self._results
                                 else "fresh")

        deadline = time.time() + self.ACCEPTANCE_TIMEOUT_S
        html = ""
        while time.time() < deadline:
            page = self._run_page(session, analysis_id)
            html = page[2] if isinstance(page, tuple) else ""
            if "Reading the public evidence" not in html and len(html) > 4000:
                break
            time.sleep(self.ACCEPTANCE_POLL_S)
        else:
            entry.state = _acc.TIMED_OUT
            entry.internal_failure_category = _failures.ANALYSIS_TIMEOUT
            entry.reasons = ["the analysis did not finish inside the budget"]
            entry.completed_at = time.time()
            entry.duration_seconds = round(entry.completed_at
                                           - entry.started_at, 1)
            return entry

        verdict = _acc.score(html, company=company["name"])
        entry.state = verdict["state"]
        entry.checks = verdict["checks"]
        entry.reasons = verdict["reasons"]
        entry.completed_at = time.time()
        entry.duration_seconds = round(entry.completed_at
                                       - entry.started_at, 1)
        try:
            records = self.ci.store.retrieved(analysis_id)
            entry.evidence_count = len(records)
            entry.source_classes = sorted(
                {r.get("source_class", "") for r in records})
            entry.filing_quality_states = sorted(
                {(r.get("filing") or {}).get("extraction_quality", "")
                 for r in records if r.get("filing")})
        except Exception:                                     # noqa: BLE001
            pass                    # diagnostics must never fail the entry
        entry.safe_diagnostic_id = analysis_id[:12]
        return entry

    def _run_page(self, session, run_id, *, layer="default"):
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        if self._is_real_run(run_id):
            # A FAILED real-company run has no report. Render an honest
            # failed-run page — never redirect back to source approval and
            # never present a nonexistent result.
            #
            # "FAILED" IS THE LAST TRANSITION, NOT THE WHOLE STORY. The state
            # is whatever `ci.run_transitioned` said last, and the evidence
            # loop can fail a pass, transition FAILED, and then retrieve on a
            # later one. `compose` decides on the documents themselves
            # (`if not documents`), and this page has to ask the same question
            # or it contradicts the run it is reporting.
            #
            # Measured live on preview-v3 (Alphabet, https://abc.xyz, runs
            # 01KZATHG9PX98WCVS5M0PG2XHD and 01KZAXYRE9CAX8MBX9EVV4QZDA, both
            # passes): every guessed abc.xyz path 404'd, the run went FAILED,
            # and EDGAR then returned the 10-K and 10-Q. `/runs/{id}` and
            # `/full` told the reader "did not produce a report because no
            # approved source could be retrieved. There is no result to show"
            # while `/brief` — reading the SAME store, through
            # `_retrieved_documents` — listed "SEC 10-K (2026-02-05)" and
            # "SEC 10-Q (2026-07-23)" under "What could actually be read".
            # The primary screen stated something the same store disproved,
            # and threw away a correct bounded result to do it.
            #
            # Falling through does not invent anything: with documents and a
            # composed result the readiness gate below still decides, and a
            # run that cannot support a view lands on the insufficient-evidence
            # page, which says so.
            # AND THE FIX IS TO THE PAGE'S WORDS, NOT ITS ROUTING. Two
            # attempts at re-routing this run both made it worse, measured
            # live on preview-v3 (Alphabet, https://abc.xyz): falling through
            # to the report renderer answered 500 on `/full` and `/slides`
            # (run 01KZB03PMHJV49G826M9NPACSV), and routing to
            # `_insufficient_evidence_page` answered 500 on the PRIMARY screen
            # (run 01KZB1MXQ5VPCZDSGFT92ZE144). Both pages are built for a run
            # that composed something; this one did not, which is why its
            # state is FAILED.
            #
            # A FAILED run therefore keeps the page written for it. What was
            # wrong was never the routing — it was the sentence, which claimed
            # nothing had been retrieved while the same store held the
            # filings. `_failed_run_page` now reads the store and says what is
            # true, so the reader is told what WAS read and where to read it.
            # WHILE THE WORKER IS WORKING, THIS PAGE ONLY WATCHES. Below, both
            # `_autorun` and `_real_result` mutate the run, and a reader who
            # refreshes during the analysis raced the worker doing the same
            # thing — that is the live 400 at t=0 and the live 500 that
            # followed it. The progress page is the honest transitional answer
            # and it already exists.
            avail = self._availability(run_id)
            if avail["in_flight"]:
                return self._redirect(f"/runs/{run_id}/progress")

            if self.ci.store.run_state(run_id) == "FAILED":
                # A FAILED run that nonetheless COMPOSED a reading is not a
                # failure to the reader — it is a bounded result, and the
                # canonical bounded surface is the founder brief the primary
                # screen already renders for every other run. Measured live
                # (Alphabet, https://abc.xyz): `/brief` served 820 words off
                # this same dossier while the primary screen served a failure
                # page. Rendering the dossier here is not relabelling the run:
                # the state stays FAILED, the failure detail stays one click
                # away, and nothing is invented — if no reading was composed
                # this still falls through to the failure page below.
                # THE TEST IS "COULD ANYTHING BE READ", NOT "IS THERE A
                # REPORT". Measured live at c9afbc7 (run
                # 01KZB7BBJ43ZKYXE5CG4VEHMCQ): FAILED, five sources read
                # including the 10-K and 10-Q, and no composed strategic
                # report — so a `has_report` test still sent the reader to a
                # 278-word failure page while `/brief`, off the same run,
                # served 1060 words. `_founder_brief_page` and
                # `_founder_layers` both tolerate a missing report and compose
                # from identity, listing and the documents; the primary screen
                # was the only surface that would not.
                stored = self._results.get(run_id)
                if avail["documents"] and avail["has_result"] \
                        and layer == "default":
                    # WHICH BOUNDED SURFACE. A run that composed a reading gets
                    # the founder brief. A run whose composition FAILED has
                    # evidence and no view, which is what
                    # `_insufficient_evidence_page` is written for — it names
                    # what was read, what is missing and what to do next.
                    #
                    # Measured on the deployed preview at 1446db6: the founder
                    # brief for that state told the reader "the public record
                    # did not carry enough" and never mentioned the SEC 10-K
                    # and 10-Q the run had just read. Naming five sources and
                    # then saying nothing could be read is the same untruth
                    # the failure page had.
                    if stored.get("composition_failure"):
                        return self._insufficient_evidence_page(
                            session, run_id, stored,
                            reason="The sources below were read, but the full "
                                   "synthesis did not complete, so no "
                                   "strategic reading is asserted here.")
                    return self._founder_brief_page(session, run_id, stored)
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
            # V3: on the DEFAULT route a company with little public material
            # gets a useful bounded product -- what a customer can verify,
            # what is only claimed, what is unclear, what to publish --
            # instead of a dead end. That was the customer's sharpest
            # complaint.
            #
            # LAYER-AWARE, deliberately. `/full` still returns the honest
            # limited-analysis page: a reader who explicitly asked for full
            # research is owed the full-research answer, including "there was
            # not enough here", and silently substituting a summary for it
            # would be a second, quieter dead end.
            if layer == "default":
                return self._founder_brief_page(session, run_id, result)
            return self._insufficient_evidence_page(
                session, run_id, result,
                reason="The pages that could be read describe what the "
                       "company offers, but none carried the dated, checkable "
                       "material a strategic reading has to rest on.")

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
        # A FAILED or INTERRUPTED run is retried as a NEW ATTEMPT on the
        # worker -- retry must not reintroduce the blocking request the async
        # change just removed. Bounded, and a no-op while an attempt is live,
        # so a repeatedly clicked button cannot stack executions.
        state = self.ci.store.run_state(run_id)
        if state in self.RETRYABLE_STATES:
            if self.retry_state(session, run_id)["allowed"]:
                self._schedule_analysis(session["user_id"], run_id,
                                        allow_retry=True)
            return self._redirect(f"/runs/{run_id}/progress")
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
            # Deduplicate the READABLE names, not the attempts. Several
            # candidates routinely resolve to the same readable string — a
            # homepage proposed by two discovery paths, or pages whose titles
            # are unknown so both fall back to the same host. Measured live on
            # Caterpillar, the list opened "www.caterpillar.com,
            # www.caterpillar.com, www.caterpillar.com/api", which reads as
            # carelessness and spends two of the three visible slots saying
            # one thing.
            #
            # The count follows the deduplicated list, so "and N more" counts
            # pages the reader would recognise as distinct rather than
            # internal retry attempts, which are not a fact about the company.
            distinct = list(dict.fromkeys(sources))
            shown = ", ".join(_e(s) for s in distinct[:3])
            if len(distinct) > 3:
                shown += f" and {len(distinct) - 3} more"
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
        # D22. THE LAST SITE THAT DECIDED THIS FOR ITSELF, and the one every
        # refusing ROUTE funnels into. D17 was fixed at the surfaces that
        # RENDER a verdict; Caterpillar then failed anyway, because /slides
        # redirects here when the deck is not ready and this page asserts
        # "There is not enough public evidence to build a briefing on this
        # company" while the X-Ray for the same run gives a supported capacity
        # decision.
        #
        # Fixed HERE rather than at /slides deliberately. Three routes reach
        # this page and patching the one that was caught would have produced
        # the fifth instance of this defect somewhere else -- the sweep that
        # found this site is the reason it is being fixed once.
        #
        # What was READ is unchanged: this page's whole job is to say what it
        # found and what is missing, and that is still true and still useful.
        # What it may no longer do is conclude, from this run alone, that the
        # system has nothing to say about the company.
        _contract = self._executive_contract(run_id)
        if _contract is not None and getattr(_contract, "reading_exists",
                                             False):
            # The CONTRACT's name, which is the canonical one resolved for the
            # dossier. `company` here is whatever the run metadata recorded,
            # which is what the founder typed -- "Caterpillar" rather than
            # "Caterpillar Inc.", and "this company" when the run has no
            # metadata at all.
            company = getattr(_contract, "company", "") or company
            reason = (
                f"A supported reading of {company} exists and is set out on "
                f"the Executive X-Ray. "
                + (getattr(_contract, "run_contribution", "") or
                   "This run did not add enough independent evidence to "
                   "strengthen it."))
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

    def _founder_questions(self, report):
        """Follow-ups a first-time reader actually asks, plus report-specific
        ones. The plain questions come first because "what does this company
        do?" is the most common real question and the report-derived ones
        assume the reader already has a thesis in mind.

        Never phrased so as to imply a withheld thesis is established.
        """
        plain = ["What does this company do?",
                 "Why does this matter?",
                 "What should I do next?"]
        return (plain + [q for q in self._suggested_questions(report)
                         if q not in plain])[:5]

    def _suggested_questions(self, report):
        """Company-specific follow-ups derived from the report, not generic."""
        from intent_engine.strategic_intelligence.concrete import (
            reads_as_taxonomy,
        )
        hyps = report.get("hypotheses", [])
        qs = []
        if hyps:
            top = hyps[0]
            # A hypothesis TITLE is the pattern library's label for a shape.
            # Quoting it back inside a suggested question put "absorbing
            # adjacent tools until the work lives inside it" on the deployed
            # Palantir page, in a question the reader was invited to click.
            title = top.get("title", "").split(" (")[0]
            if title and not reads_as_taxonomy(title):
                qs.append(f"What evidence most weakens the "
                          f"{title.lower()} thesis?")
            else:
                qs.append("What evidence most weakens the reading here?")
            comps = top.get("comparables", [])
            if comps:
                # The library names a comparable "Amazon → AWS". An arrow is
                # its own notation, and it reached a founder-facing suggested
                # question verbatim on the deployed /full page.
                comparable = str(comps[0]).replace("→", "to").replace(
                    "->", "to")
                comparable = " ".join(comparable.split())
                qs.append(f"How is this transition similar to {comparable}, "
                          f"and where does the comparison break down?")
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
        # THE DOSSIER LEADS; THE LEGACY REPORT BECOMES THE APPENDIX.
        #
        # Measured on the deployed preview 2026-08-04: `/full` was 789 words
        # against the primary screen's 816, so the "complete intelligence
        # dossier" was SHALLOWER than the 60-second summary. It also carried
        # the library talking to itself -- "leadership is likely weighing how
        # aggressively to act on: turning a people-delivered service into a
        # repeatable product" is a pattern name, and "Accenture -> industry
        # platforms" is the library's own notation.
        #
        # The dossier now leads with the shared decision and the full-depth
        # material (business model, chronology, evidence by provenance,
        # competitive position, analogs with their breaking points,
        # assumptions, scenarios, unknowns, monitoring, evidence appendix).
        # The legacy report follows as supporting detail rather than being
        # the page.
        from intent_engine.external_intel import visuals as _charts
        from intent_engine.founder_brief import dossier as fd
        from intent_engine.founder_brief import narrative as fn
        from intent_engine.founder_brief import render as fr
        from intent_engine.strategic_intelligence.decision import decision_of
        _brief, _report_obj, _name = self._founder_layers(run_id)
        _decision = decision_of(report)
        _external = self._external_context(run_id)
        _story = fn.build_narrative(company=_name, brief=_brief, report=report,
                                    decision=_decision, external=_external,
                                    contract=self._executive_contract(run_id))
        _book = fd.build_dossier(company=_name, report=report,
                                 decision=_decision, narrative=_story,
                                 documents=self._retrieved_documents(run_id),
                                 external=_external,
                                 market=self._market_snapshot(run_id)
                                 if self._listing_for(run_id).ticker else None)
        strat = (fr.BRIEF_CSS + fn.NARRATIVE_CSS + _charts.CHART_CSS
                 + fd.render_dossier(
                     _book, depth=fd.FULL, run_id=run_id, wrap=False,
                     citation_labels=self._citation_labels(run_id),
                     charts=_external_charts(_external),
                     lead=fd.render_decision_lead(
                         _decision, _name, depth=fd.FULL, run_id=run_id)))
        # The legacy report is NOT appended. It said the same things the
        # dossier above now says -- one decision, one evidence list, one set
        # of alternatives -- so keeping it made every sentence on the page
        # appear twice. Its one unique element, the source table, is the
        # dossier's evidence appendix.
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

    @staticmethod
    def _as_of(*, fresh: bool = False) -> str:
        """The run's as-of stamp, and therefore half of its identity.

        A run's id is `ci-run:{subject}:{user}:{as_of}`, and this was always
        truncated to `T00:00:00` -- so the SAME company analysed twice by the
        same person on the same day is one run, not two. That is the right
        default: it is what stops a double-submit or a refresh paying for the
        analysis twice.

        It also made a second iteration structurally unreachable. There is no
        way, within a day, for a reader to produce the earlier-and-later pair
        the whole learning surface is built on, which is why the live card
        reported a baseline for what looked like a second Cloudflare run.

        An EXPLICIT request for a fresh analysis is the one case where the
        reader has said they want another one, so it keeps full precision and
        gets its own run. Everything else still dedupes by day.
        """
        import datetime as _dt

        now = _dt.datetime.now(_dt.timezone.utc)
        return (now.strftime("%Y-%m-%dT%H:%M:%S+00:00") if fresh
                else now.strftime("%Y-%m-%dT00:00:00+00:00"))

    def _fresh_analysis(self, session, run_id):
        """Deliberately bypass the compatible-result cache.

        The point of the button is that the user does not have to trust our
        judgement about whether the cached run is still good. A stale
        low-quality report must never be able to trap someone with no way out
        of it.

        IT HAD TO BYPASS THE RUN ID TOO. Clearing `_results` and re-entering
        `_analyze` rebuilt the same `ci-run:{subject}:{user}:{date}` key, so
        this returned the SAME run every time -- a button whose whole purpose
        is "give me another one" that could not give you another one. Passing
        `fresh` keeps the full timestamp in the as-of, so the reader's
        explicit request gets its own run and becomes the second observation
        the learning surface can actually compare against.
        """
        if not self._owned(session, run_id) or not self._is_real_run(run_id):
            return self._error_page(404, "no such run for this account")
        meta = self.ci.run_meta(run_id) or {}
        # THE OLD RUN'S RESULT IS KEPT. This popped it, which was correct only
        # while a fresh analysis reused the same run id -- clearing the cache
        # was then the sole way to force recomputation. Now that the fresh run
        # gets its own id, popping the old one destroys the very reading the
        # new run is about to be compared against: the prior vanished at the
        # moment the second observation was created, so the second iteration
        # reported a baseline forever.
        form = {"consent": "1", "company_name": meta.get("company_name", ""),
                "website": meta.get("website", ""), "csrf": session["csrf"]}
        return self._analyze(session, form, fresh=True)

    def _founder_layers(self, run_id):
        """Everything the deeper layers need, built from ONE brief.

        Shared so the dashboard, story and executive brief cannot drift apart
        or repeat one another -- the dedup ledger is threaded through them in
        reading order.
        """
        from intent_engine.founder_brief import build as fb
        from intent_engine.founder_brief import layers as fl

        result = self._result(run_id) or {}
        report = result.get("strategic_report") or {}
        observations = [o for o in (report.get("observations") or ())
                        if isinstance(o, dict)]
        independent = sum(
            1 for o in observations
            if o.get("source_class") not in ("company_owned",
                                             "executive_statement", None, ""))
        thesis = report.get("thesis") or {}
        identity = self.ci.entity_identity(run_id) or {}
        listing = self._listing_for(run_id)
        ticker = listing.ticker
        # A company can be listed and still have no ticker resolved for this
        # run. `is_public` asks what the company IS, so it reads the status
        # rather than whether one lookup happened to return a symbol.
        mode = fb.classify_mode(
            is_public=listing.is_public, evidence_count=len(observations),
            independent_sources=independent,
            has_thesis=bool(thesis.get("view"))
            and not thesis.get("view_withheld"))
        market = self._market_snapshot(run_id) if ticker else None
        # `company_name` is what the presentation deck has always used, so a
        # run whose identity record is absent (every anonymous demo run) was
        # headed "Shopify — presentation" on one layer and "This company" on
        # the founder brief beside it. The name was in the report the whole
        # time; only this path declined to read it.
        # ...and the run's own metadata is the source that is ALWAYS set,
        # because it is what the founder typed. Leaving it out of the chain
        # is why three unrelated companies rendered byte-identical bounded
        # pages headed "This company": on a limited run the identity record
        # and the report are both empty, so every company collapsed onto the
        # same placeholder. Measured on the deployed preview -- Tesla, NVIDIA
        # and Costco produced identical dashboard, story and executive-brief
        # text down to the word count.
        name = (identity.get("canonical_name") or identity.get("name")
                or report.get("company_name")
                or result.get("company")
                or (self.ci.run_meta(run_id) or {}).get("company_name")
                or "This company")
        brief = fb.build(company=name, mode=mode, report=report,
                         observations=observations, market=market)
        return brief, report, name

    def _executive_contract(self, run_id):
        """The one answer to "does a supported reading of this company exist".

        D17. Every executive surface used to decide this for itself, from
        whichever decision object it happened to consume, and on a company
        with a published market reading they reached opposite answers on the
        same run. This is the single place that question is settled; the
        surfaces keep their own prose and their own depth.

        Returns None on any failure, and every consumer treats None as "ask
        the old way" -- a contract that could fail a page is worse than the
        contradiction it removes.
        """
        try:
            from intent_engine.demo_dossier.store import (DossierStore,
                                                          company_key)
            from intent_engine.executive import contract as ec
            from intent_engine.strategic_intelligence.decision import \
                decision_of

            result = self._result(run_id) or {}
            report = result.get("strategic_report") or {}
            meta = self.ci.run_meta(run_id) or {}
            name = str(meta.get("company_name") or "")
            key, _c, _m = self._manifest_placement(
                company_key(name or str(meta.get("domain") or "") or run_id),
                name=name, domain=str(meta.get("domain") or ""))
            dossier = DossierStore(self._runtime_root).latest(key)
            market = self._executive_read(dossier) if dossier is not None \
                else None
            # The bridge already decided whether this snapshot is for the
            # right company and recent enough. Asking again here would be a
            # second freshness contract, and two of those is how the first
            # one stops being believed.
            usable = dossier is not None
            return ec.decide(
                company=(getattr(dossier, "canonical_name", "") or name),
                run_decision=decision_of(report), market_decision=market,
                market_usable=usable)
        except Exception:                                   # noqa: BLE001
            _LOG.warning("executive contract not composed for %s", run_id)
            return None

    def _retrieved_documents(self, run_id):
        """The run's retrieved documents, or () when the store has no rows.

        The deep layers name what was readable, which is the only
        company-specific footing a bounded run has once source-count narration
        is removed.
        """
        try:
            return list(self.ci.store.retrieved(run_id))
        except Exception:                       # noqa: BLE001 - a run with no
            return ()                           # store rows yet still renders

    def _evidence_footing(self, run_id, name, ticker=""):
        """What this run actually retrieved, for the bounded layers.

        The limited landing page has always rendered these facts and is
        company-specific because of it -- "3 page(s) read; 1 carried usable
        evidence" under a heading naming Tesla. The dashboard, story and brief
        beside it were built from constants, which is why they came out
        byte-identical for Tesla and NVIDIA. Same facts, same run, so the
        deeper layers now read from the same place rather than from copy.

        Counts and identifiers only. Nothing here interprets evidence, and a
        missing piece yields a missing key rather than a guess.
        """
        from intent_engine.company_ingestion.readiness import is_english
        from urllib.parse import urlsplit
        try:
            fetched = [d for d in self.ci.store.retrieved(run_id)
                       if d.get("retrieval_status") == "OK"]
        except Exception:                       # a run with no store rows yet
            return {}
        used = [d for d in fetched if is_english(d)]
        result = self._result(run_id) or {}
        note = result.get("insufficient_evidence") or {}
        kinds = sorted({str(d.get("source_class") or "").replace("_", " ")
                        for d in used} - {""})
        blocked = []
        for readable, _label, _human, _detail in self._failure_rows(run_id):
            host = urlsplit(str(readable)).netloc or str(readable)
            if host and host not in blocked:
                blocked.append(host)
        # A retrieved record carries no publication date -- only the title the
        # page declared. Where the pipeline could date a filing it says so in
        # that title ("SEC 8-K exhibit (2026-07-22)"), so the title is the
        # honest thing to quote and an invented date is the thing to avoid.
        documents = [t for t in
                     ((d.get("title") or "").strip() for d in used) if t]
        listing = self._listing_for(run_id)
        return {"company": name, "pages_read": len(used),
                "usable": note.get("source_count"), "kinds": kinds,
                "blocked": blocked, "documents": documents,
                "ticker": ticker or "",
                "listing_status": listing.status,
                "listing_exchange": listing.exchange}

    @staticmethod
    def _ticker_of(identity: dict) -> str:
        """The listed ticker for this entity, or "".

        SECOND BREAK IN THE SAME CHAIN. Both call sites read
        `identity["ticker"]`; the identity record has no such key. It carries
        `listings: [{"exchange": "NASDAQ", "ticker": "PLTR"}]`. So the ticker
        was always "", the market lookup was never even attempted, and the
        dashboard printed "no market snapshot" for companies whose snapshot
        was sitting on disk.
        """
        for listing in (identity or {}).get("listings") or ():
            if isinstance(listing, dict) and listing.get("ticker"):
                return str(listing["ticker"]).strip().upper()
        return str((identity or {}).get("ticker") or "").strip().upper()

    def _sec_ticker_map(self):
        """The SEC registrant table, fetched once per process."""
        if self._sec_map is None:
            from intent_engine.company_ingestion.listings import (
                SecTickerMap, load_sec_ticker_map,
            )
            if self.config.env == "test" and self._transport is None:
                self._sec_map = SecTickerMap(())
            else:
                self._sec_map = load_sec_ticker_map(
                    transport=self._transport, resolver=self._resolver)
        return self._sec_map

    def _listing_for(self, run_id):
        """This run's listing resolution, computed once per run.

        THE THREE-COMPANY BOTTLENECK. `_ticker_of` reads `identity["listings"]`,
        which is populated only from the hand-written registry in entities.py
        -- and that registry lists exactly three companies. So Tesla, NVIDIA
        and Costco resolved no ticker, `_market_snapshot()` was never called,
        and the dashboard reported a missing market snapshot for companies
        whose shares trade every day. The registry still wins when it has an
        answer; the SEC registrant table now answers for everyone else.
        """
        cached = self._listing_cache.get(run_id)
        if cached is not None:
            return cached
        from intent_engine.company_ingestion.listings import resolve_listing
        identity = self.ci.entity_identity(run_id) or {}
        meta = self.ci.run_meta(run_id) or {}
        name = (identity.get("canonical_name") or identity.get("common_name")
                or identity.get("name") or meta.get("company_name") or "")
        resolution = resolve_listing(
            company_name=name, website=meta.get("website", ""),
            registry_listings=identity.get("listings") or (),
            sec_map=self._sec_ticker_map())
        self._listing_cache[run_id] = resolution
        return resolution

    def _external_context(self, run_id, *, allow_fetch=False):
        """Market, macro and competitive context for one run, assembled once.

        WHY ONE OBJECT RATHER THAN THREE LOOKUPS. The dashboard, the narrative,
        the Executive Brief and the Full Analysis all need the same outside
        facts. Three surfaces each computing their own version is how they
        drifted apart before; they read this.

        `allow_fetch` IS THE WHOLE REFRESH POLICY. A page render passes False
        and can never start a network download, however stale the data is. The
        analysis path passes True, so a run on a company nobody has looked at
        before still gets real data. A recent export is reused either way, so
        a founder never waits on a market download that already happened.

        Fails soft, deliberately. External context is context: if every source
        is down, the founder still gets their analysis and the sections say
        what is missing. A market outage must not be able to take a run away.
        """
        cached = self._external_cache.get(run_id)
        if cached is not None and not allow_fetch:
            return cached
        import datetime as _dt
        from intent_engine.external_intel import (
            competitor_finder as cf, macro_provider as mp, market_producer,
            pack as ep,
        )
        today = _dt.date.today().isoformat()
        listing = self._listing_for(run_id)
        result = self._result(run_id) or {}
        report = result.get("strategic_report") or {}
        observations = [o for o in (report.get("observations") or ())
                        if isinstance(o, dict)]
        identity = self.ci.entity_identity(run_id) or {}
        name = (identity.get("canonical_name") or identity.get("name")
                or report.get("company_name")
                or (self.ci.run_meta(run_id) or {}).get("company_name") or "")

        market = macro = competitors = None
        try:
            market = market_producer.ensure_export(
                ticker=listing.ticker, root=self._runtime_root, today=today,
                exchange=listing.exchange, company_id=run_id,
                allow_fetch=allow_fetch)
        except Exception:  # noqa: BLE001 - context must never break a run
            _LOG.warning("market context unavailable for %s", run_id)
        # Retrieved documents carry the Competition section a filing states in
        # the company's own words; observations carry the exposure phrases.
        documents = [dict(d, observation_id=d.get("source_id") or
                          d.get("document_id") or "")
                     for d in self._retrieved_documents(run_id)
                     if isinstance(d, dict)]
        # An annual report is handed over as its EXTRACTED Competition
        # section, not as 550,000 characters of raw filing. Passing the whole
        # document means the finder mines Item 1A as well, where competition
        # is discussed at length and no rival is named in the same passage —
        # so the real Competition section is outvoted by risk-factor prose
        # and the run reports that no competitor account was retrieved.
        documents = _with_annual_filing_sections(documents)
        try:
            macro = mp.build_factors(observations + documents,
                                     root=self._runtime_root, today=today)
        except Exception:  # noqa: BLE001
            _LOG.warning("macro context unavailable for %s", run_id)
        try:
            competitors = cf.find_competitors(
                observations + documents, subject=name, today=today)
        except Exception:  # noqa: BLE001
            _LOG.warning("competitor context unavailable for %s", run_id)

        # The sanitized strategic dossier, if the market-learning engine has
        # published one for this company. It is READ ONLY, from one versioned
        # file, and it is the only channel between the two systems — there is
        # no import path from here into the market package, and the package is
        # not even present on this branch. A missing dossier is the normal
        # case and stays silent; see `ExternalContext.has_strategic`.
        # It is resolved by NAME rather than by one derived filename. The
        # producer keys its files on an internal universe id it never shares,
        # and this side knows the company by whatever the founder typed, so a
        # single-key lookup missed every real dossier ever published without
        # reporting anything — see `strategic_contract.resolve`. Every name
        # this run holds for the company is offered, and the dossier has to
        # name itself back.
        strategic = None
        try:
            from intent_engine.external_intel import (
                strategic_contract as sc,
            )
            strategic = sc.resolve(
                pathlib.Path(self._runtime_root) / "reports" / "market"
                / "strategic",
                names=[name, identity.get("common_name") or "",
                       identity.get("canonical_legal_name") or "",
                       identity.get("fallback_subject") or "",
                       (self.ci.run_meta(run_id) or {}).get(
                           "company_name") or ""],
                today=today)
        except Exception:  # noqa: BLE001 - context must never break a run
            _LOG.warning("strategic context unavailable for %s", run_id)

        context = ep.build_context(market=market, macro=macro or (),
                                   competitors=competitors or (),
                                   strategic=strategic, as_of=today)

        # Tell the market engine what became of the dossier it published.
        # Only this side knows: the file is read, validated, accepted or
        # refused, and turned into reasoning blocks here. Without this the
        # producer's founder-utility metric is permanently UNMEASURABLE, which
        # is honest and leaves it optimising in the dark.
        #
        # This records CONSUMPTION, never truth — nothing written here flows
        # back into a belief, a mechanism or an expectation. It is also
        # deliberately unable to break a run: every failure inside is
        # swallowed, because a telemetry write that can fail an analysis is a
        # worse defect than the missing measurement it was added to fix.
        try:
            from intent_engine.external_intel import consumption_receipt as cr
            from intent_engine.external_intel import strategic_contract as _sc
            # Re-imported rather than reusing `sc`: that name is bound inside
            # the try above, so an import failure there would leave it unbound
            # and this would raise NameError on a path that is meant to be
            # incapable of affecting the run.
            # RENDERED counts actual strategic BLOCKS, not the fact that the
            # section opened. An empty strategic section was reachable until
            # this cycle -- validated, eligible, "used", and nothing under the
            # heading -- so counting the heading would have re-created exactly
            # the overstatement this telemetry exists to prevent.
            rendered = len([b for b in ep.reasoning_pack(context)["blocks"]
                            if b.get("context") == ep.STRATEGIC])
            # DECISION_RELEVANT is decided by a deterministic comparison of
            # the SAME analysis with and without the dossier, over semantic
            # fields rather than prose. Comparing two generations would
            # measure sampling noise: run the same analysis twice with no
            # dossier at all and the wording differs.
            from intent_engine.external_intel import decision_impact as _di
            without = ep.build_context(
                market=market, macro=macro or (),
                competitors=competitors or (), strategic=None, as_of=today)
            impact = _di.assess(
                analysis_id=run_id, company_id=_sc.company_key(name),
                dossier_revision=str(getattr(strategic, "as_of", "") or ""),
                before=_di.semantic_state(without),
                after=_di.semantic_state(context),
                provenance=_di.evidence_of(context))
            cr.acknowledge_context(
                self._runtime_root, company_id=_sc.company_key(name),
                analysis_id=run_id, strategic=strategic,
                has_strategic=context.has_strategic, analysis_as_of=today,
                rendered_blocks=rendered, surface="analysis",
                decision_impact=impact.as_dict() if impact.changed else None)
            # THE TEMPORAL COMPARISON, WHICH IS THE ONE LEARNING NEEDS.
            #
            # The grading above asks "was the market dossier decision-
            # relevant" by running the same analysis with and without it.
            # That is a real question and it stays. It cannot answer "did we
            # learn anything", and `decision_impact`'s own docstring says
            # why: the without-dossier side is empty on every field, so every
            # field reads empty -> populated, nothing can grade NONE, and the
            # number is 100% by construction.
            #
            # Learning needs the BEFORE to be what the founder saw LAST TIME.
            # `assess_against_prior`, `record_revision` and `record_impact`
            # were built for exactly this and had ZERO production call sites,
            # which is why no KnowledgeEffect could exist: the prior state was
            # never written, so no second run could ever compare against a
            # first.
            self._record_learning(
                run_id=run_id, company_id=_sc.company_key(name),
                context=context, dossier_revision=str(
                    getattr(strategic, "as_of", "") or ""))
        except Exception:  # noqa: BLE001 - see above
            _LOG.warning("consumption receipt not written for %s", run_id)

        self._external_cache[run_id] = context
        return context

    def _record_learning(self, *, run_id: str, company_id: str, context,
                         dossier_revision: str = "") -> dict:
        """Compare this analysis with the last one, and record what changed.

        ORDER MATTERS AND IS NOT OBVIOUS. The comparison must run against the
        prior revision BEFORE this one is recorded, or every run compares
        against itself and nothing ever changes.

        Every failure is swallowed and reported as a state. A learning ledger
        that can fail an analysis is a worse defect than the missing rows it
        was added to produce — the same judgement the consumption receipt
        beside it is built on.
        """
        from intent_engine.external_intel import decision_impact as _di
        from intent_engine.external_intel import effect_producer as _ep

        try:
            after = _di.semantic_state(context)
            prior = _di.load_revisions(self._runtime_root).get(company_id)
            impact = _di.assess_against_prior(
                self._runtime_root, analysis_id=run_id,
                company_id=company_id, after=after,
                provenance=_di.evidence_of(context),
                dossier_revision=dossier_revision)
            effects = _ep.effects_from_impact(
                impact, evidence_ids=_di.evidence_of(context),
                prior_company_id=str((prior or {}).get("company_id") or ""))
            written = _ep.record_effects(self._runtime_root, effects)
            # Recorded AFTER the comparison, and idempotent by content: an
            # unchanged dossier appends nothing, so the file does not grow by
            # a row per company per cycle.
            _di.record_revision(self._runtime_root, company_id=company_id,
                                state=after,
                                dossier_revision=dossier_revision)
            _di.record_impact(self._runtime_root, impact=impact)
            return {"state": "RECORDED", "effects": len(effects),
                    "new_effects": written,
                    "materiality": getattr(impact, "materiality", "")}
        except Exception as exc:  # noqa: BLE001 - never fail an analysis
            _LOG.warning("learning not recorded for %s: %s", run_id, exc)
            return {"state": "PRODUCER_FAILED",
                    "detail": f"{type(exc).__name__}: {str(exc)[:160]}"}

    def _market_snapshot(self, run_id: str):
        """The founder-facing market context, in the shape the layers read.

        THIS CHANNEL WAS DEAD TWICE OVER. Both original call sites read
        `self.config.data_dir`, and AppConfig has no such field, so every
        lookup raised AttributeError into a bare `except` and the dashboard
        reported "market context unavailable" on every run ever made. Fixing
        that revealed the second half: nothing was WRITING an export, so there
        was no file to read even once the path was right.

        `market_intel_export.v2` is the only sanctioned channel, and it is
        enforced by allowlist rather than by a list of banned names -- see
        external_intel/market_contract.py for why a blacklist could not hold.
        """
        from intent_engine.external_intel import presenter
        try:
            return presenter.market_context_dict(
                self._external_context(run_id))
        except Exception:  # noqa: BLE001 - a bad FILE degrades, a bug does not
            _LOG.warning("market context unreadable for run %s", run_id)
            return {"available": False, "modules": {}, "limitations": [],
                    "reason": "The market snapshot could not be read."}

    def _founder_answer_page(self, session, run_id, answer):
        """One answer, in the same shape as every other founder surface."""
        from intent_engine.founder_brief import render as fr
        a = answer
        parts = [f'{fr.BRIEF_CSS}<main class="fb">',
                 f'<h1>{_e(a.question[:120])}</h1>',
                 f'<div class="card headline"><p>{_e(a.direct_answer)}</p>']
        if a.so_what:
            parts.append('<div class="sowhat"><span class="lbl">Why this '
                         f'matters</span>{_e(a.so_what)}</div>')
        if a.decision_affected:
            parts.append('<div class="decision"><span class="lbl">Decision '
                         f'affected</span>{_e(a.decision_affected)}</div>')
        parts.append("</div>")
        if a.strongest_evidence or a.weakest_evidence:
            parts.append('<h2>Evidence</h2><div class="card">')
            if a.strongest_evidence:
                parts.append(f'<p><strong>Strongest.</strong> '
                             f'{_e(a.strongest_evidence)}</p>')
            if a.weakest_evidence:
                parts.append(f'<p><strong>Weakest.</strong> '
                             f'{_e(a.weakest_evidence)}</p>')
            if a.fact_or_interpretation:
                parts.append(f'<p class="small muted">'
                             f'{_e(a.fact_or_interpretation)}</p>')
            parts.append("</div>")
        if a.what_could_change:
            parts.append('<h2>What could change this answer</h2>'
                         f'<div class="card"><p>{_e(a.what_could_change)}</p>'
                         "</div>")
        # A trailing "Confidence: Low." qualifies nothing a reader can use.
        # It survives only when it carries its reason.
        _q_conf = _conf_para(a.confidence, getattr(a, "confidence_reason", ""))
        if _q_conf:
            parts.append(f'<p class="small muted">{_e(_q_conf)}</p>')
        # An answer that resolved nothing must still tell the reader what CAN
        # be asked. Dropping this turned "I could not find a subject for that"
        # into a dead end -- the same failure the sparse report page had.
        report = ((self._result(run_id) or {}).get("strategic_report") or {})
        parts.append(self._ask_form(run_id, report, session))
        parts.append(fr._deeper(run_id))
        parts.append("</main>")
        return self._html(self._page(f"{a.question[:60]}", "".join(parts),
                                     session, session.get("csrf", "")))

    @staticmethod
    def _observation_ids(report):
        """Evidence ids a founder-facing layer may cite. Only ids that exist
        on the report -- a citation that cannot resolve is worse than none."""
        return [o.get("observation_id") for o in (report or {}).get(
            "observations", []) if isinstance(o, dict)
            and o.get("observation_id")][:8]

    def _executive_brief_page(self, session, run_id):
        # OWNERSHIP, like every other run route. Measured on the deployed
        # preview 2026-08-03: `/runs/{id}` answered 404 "no such run for this
        # account" to a session that did not own the run, while `/brief`,
        # `/dashboard` and `/story` served the whole analysis to that same
        # session with HTTP 200. The guard existed on the primary page and on
        # /slides and /sources, and was simply missing on these three -- so
        # the protection looked present and was not.
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        # The same availability question the other run routes ask. This one
        # answered 200 with a full dossier while the primary screen answered
        # 400, which is how the two surfaces came to contradict each other.
        if self._is_real_run(run_id) and self._availability(run_id)["in_flight"]:
            return self._redirect(f"/runs/{run_id}/progress")
        """The executive brief — depth WITHOUT repetition.

        Built from the same `FounderBrief` as every other layer, with the
        dedup ledger pre-loaded with what the 60-second screen already said.
        That is what stops this becoming a longer copy of the summary above
        it, which is what the legacy renderer had become.
        """
        # ONE DECISION, RENDERED DEEPER -- NOT A SECOND CONCLUSION.
        #
        # Measured on the deployed preview 2026-08-04: this page said "none of
        # it supports a strategic view strongly enough to put one forward" and
        # then offered a DIFFERENT decision ("Whether to close the evidence gap
        # publicly...") while the primary screen carried a DECISION_READY
        # choice about services-to-product. It was 396 words against the
        # primary screen's 816, so the summary was also the deepest surface in
        # the product.
        #
        # It now renders the SHARED decision, then the dossier at brief depth:
        # how the business works, what changed and when, what the evidence
        # says, competitive position, market expectations, the opportunity and
        # the risk. The dossier is seeded with what the 60-second screen
        # already said, so this adds to that page instead of restating it.
        from intent_engine.external_intel import visuals as _charts
        from intent_engine.founder_brief import dossier as fd
        from intent_engine.founder_brief import narrative as fn
        from intent_engine.founder_brief import render as fr
        from intent_engine.strategic_intelligence.decision import decision_of
        brief, report, name = self._founder_layers(run_id)
        decision = decision_of(report)
        external = self._external_context(run_id)
        story = fn.build_narrative(company=name, brief=brief, report=report,
                                   decision=decision, external=external,
                                   contract=self._executive_contract(run_id))
        book = fd.build_dossier(company=name, report=report,
                                decision=decision, narrative=story,
                                documents=self._retrieved_documents(run_id),
                                external=external,
                                market=self._market_snapshot(run_id)
                                if self._listing_for(run_id).ticker else None)
        body = fr.BRIEF_CSS + fn.NARRATIVE_CSS + _charts.CHART_CSS + \
            fd.render_dossier(
                book, depth=fd.BRIEF, run_id=run_id,
                citation_labels=self._citation_labels(run_id),
                charts=_external_charts(external),
                lead=fd.render_decision_lead(
                    decision, name, depth=fd.BRIEF, run_id=run_id,
                    contract=self._executive_contract(run_id)))
        return self._html(self._page(f"{name} — executive brief", body,
                                     session, session.get("csrf", "")))

    def _prior_run(self, session, run_id):
        """The newest earlier run of the SAME company owned by this reader.

        §16 asks for a prior-run lookup and §17 for a comparability wall. Both
        are answered from the index that already exists -- `runs_owned_by`
        plus `run_meta` -- because a second history store would immediately
        disagree with the first about what has been analysed.

        THE WALL IS APPLIED HERE, not inside `compare`. Four conditions, and
        each one is a way this has actually gone wrong somewhere in this
        codebase: the canonical company must match (a name-shaped key matched
        a different registrant once), the prior must be strictly earlier in
        the owner's own ordering (a run compared against itself reports every
        field unchanged, which reads as stability), the prior must have
        produced a report (comparing against a failure is comparing against
        nothing), and the prior must belong to this reader (a cross-tenant
        prior is a leak wearing a delta).

        Returns (run_id, report) or (None, None). No exception escapes: a
        comparison is an enrichment, and a lookup that fails must cost the
        reader the delta, never the page.
        """
        try:
            owner = (session or {}).get("user_id")
            if not owner:
                return None, None
            from intent_engine.demo_dossier.store import company_key
            here = self.ci.run_meta(run_id) or {}
            mine = company_key(str(here.get("company_name") or ""))
            if not mine:
                return None, None
            ordered = list(self.web_store.runs_owned_by(owner))
            if run_id not in ordered:
                return None, None
            # Strictly EARLIER in the owner's ordering. Slicing at the current
            # run rather than filtering by timestamp keeps this correct when
            # two runs share an `as_of` date, which they routinely do.
            for rid in reversed(ordered[:ordered.index(run_id)]):
                meta = self.ci.run_meta(rid) or {}
                if company_key(str(meta.get("company_name") or "")) != mine:
                    continue
                _, report, _ = self._founder_layers(rid)
                if isinstance(report, dict) and report:
                    return rid, report
            return None, None
        except Exception:                                   # noqa: BLE001
            _LOG.warning("prior run not resolved for %s", run_id)
            return None, None

    def _second_iteration_delta_composed(self, session, run_id, *,
                                         current, previous):
        """The delta between two COMPOSED executive readings of one company.

        The first version compared the two runs' `decision_of(report)`
        objects, which is the same seam that made the X-Ray render empty: the
        reasoning path does not populate `decision_question`, and `compare`
        opens by requiring both sides to answer the same question. With the
        field blank on both, every second reading came back INCOMPARABLE --
        "these two readings cannot be compared" -- for a company analysed
        twice from the same evidence. Measured live on ad1de5f.

        So the comparison now reads the decisions the X-Ray actually renders,
        which are also the ones `what_changed` is computed from. Evidence
        identity still comes from the RUNS' retrieved documents, keyed by
        content hash: what a reader means by "new information" is a document
        we had not held, not a field that moved.
        """
        try:
            from intent_engine.strategic_intelligence import second_iteration \
                as si
            prior_id, _prior_report = self._prior_run(session, run_id)
            return si.compare(
                previous_decision=previous,
                current_decision=current,
                previous_documents=(self._retrieved_documents(prior_id)
                                    if prior_id else ()),
                current_documents=self._retrieved_documents(run_id),
                tested_claims=tuple((current or {}).get(
                    "supporting_evidence_ids") or ())[:12])
        except Exception:                                   # noqa: BLE001
            _LOG.warning("second iteration not composed for %s", run_id)
            return {}

    def _second_iteration_delta(self, session, run_id, decision):
        """What this run learned against the last reading of the same company.

        Composed on the LIVE run path. `second_iteration.compare` existed with
        no production caller at all, so `second_iteration` was never written
        onto any decision and every surface that reads it rendered the absent
        state -- on the demo dossier as well as here. A projection whose
        producer is never called is indistinguishable from a company that has
        only ever been read once.
        """
        try:
            from intent_engine.strategic_intelligence import second_iteration \
                as si
            from intent_engine.strategic_intelligence.decision import \
                decision_of
            prior_id, prior_report = self._prior_run(session, run_id)
            current = decision.as_dict() if hasattr(decision, "as_dict") \
                else dict(decision or {})
            if prior_id is None:
                # FIRST OBSERVATION IS A STATE, NOT A GAP. `compare` says so
                # itself when handed no prior, so it is still called rather
                # than short-circuited: the card must say "this is the
                # baseline" in the same words whichever way it got there.
                return si.compare(previous_decision=None,
                                  current_decision=current,
                                  current_documents=self._retrieved_documents(
                                      run_id))
            prior = decision_of(prior_report)
            return si.compare(
                previous_decision=prior.as_dict() if prior is not None
                else None,
                current_decision=current,
                previous_documents=self._retrieved_documents(prior_id),
                current_documents=self._retrieved_documents(run_id),
                tested_claims=tuple(current.get("supporting_evidence_ids")
                                    or ())[:12])
        except Exception:                                   # noqa: BLE001
            _LOG.warning("second iteration not composed for %s", run_id)
            return {}

    def _run_xray(self, session, run_id):
        """The Executive X-Ray for a LIVE run — the customer's decision home.

        THE ROUTE THAT DID NOT EXIST. The X-Ray, the economic-history state
        and the second-iteration card were all built, unit-proven and wired to
        `/demo-dossiers/<company>/xray`, which no live run ever links to and
        no customer ever reaches. Three consecutive batches shipped correct
        renderers onto that surface and reported "UI live proof outstanding"
        without noticing that the proof could not arrive from there.

        WHICH DECISION THIS PROJECTS, measured rather than reasoned about.
        The first version rendered the run's own `decision_of(report)` on the
        argument that `/brief`, `/full` and `/story` read it, so anything else
        would be a second state system. That argument was sound and the result
        was empty: live on 9a42372 this page said "this company is not
        classified here", "Nothing changed", "No action is put forward", 0
        evidence rows and 0 channels, while `/demo-dossiers/cloudflare/xray`
        rendered "Supported in direction, not in size", a pricing decision,
        six evidence rows and five beliefs FOR THE SAME COMPANY.

        `xray.render` reads the fields `executive.decision_synthesis.compose`
        populates -- archetype, selection, transmission, competitors,
        scenarios, standing. The reasoning path's decision simply does not
        have them, so the renderer found nothing and said so honestly about a
        run that had plenty.

        This is not a second reasoning. The dossier is a MATERIALIZED VIEW of
        this very run -- `_publish_demo_dossier` wrote it from this run's
        founder snapshot as the run completed -- so composing from it is the
        executive projection of the same evidence, which is exactly what the
        demo route does. The two things `compose` does not produce are carried
        across from the run's own decision below rather than left empty.
        """
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        avail = self._availability(run_id)
        if avail["in_flight"]:
            return self._redirect(f"/runs/{run_id}/progress")
        from intent_engine.demo_dossier.store import DossierStore, company_key
        from intent_engine.founder_brief import xray
        from intent_engine.strategic_intelligence.decision import decision_of
        _, report, name = self._founder_layers(run_id)
        meta = self.ci.run_meta(run_id) or {}
        # The SAME key derivation the publisher used, so this reads the record
        # that run wrote rather than a near-miss under a different key.
        key, _cohort, _mv = self._manifest_placement(
            company_key(name or str(meta.get("domain") or "") or run_id),
            name=name, domain=str(meta.get("domain") or ""))
        dossier = DossierStore(self._runtime_root).latest(key)
        decision = self._executive_read(dossier) if dossier is not None \
            else None
        if decision is None:
            # A RUN THAT RETRIEVED NOTHING IS NOT A FAULT IN THE PRODUCT.
            # This answered "Something went wrong on our side ... This is a
            # fault in the product" for Toyota, whose run simply could not
            # retrieve an approved source -- while `/sources`, on the same
            # run, said so plainly. Two surfaces describing one failure in
            # incompatible terms is the same defect class as D17, and the
            # honest page for this already exists.
            if self.ci.store.run_state(run_id) in self.TERMINAL_STATES:
                return self._failed_run_page(session, run_id)
            return self._error_page(
                500, "The executive read for this run could not be composed. "
                     "That is a fault on this side, not a finding about the "
                     "company.")
        # THE TWO FIELDS `compose` DOES NOT PRODUCE, carried from the run's
        # own decision. `economic_history` is measured by the archive during
        # the run and has never been on the dossier at all; the delta is
        # computed here. Both are attached to the decision rather than passed
        # beside it, so they reach the renderer through the same object and
        # survive being serialised on the way.
        own = decision_of(report)
        if own is not None and getattr(own, "economic_history", None):
            decision["economic_history"] = dict(own.economic_history)
        # The PREVIOUS composed reading of this company, from the dossier
        # version before this one -- the same prior `what_changed` uses, so
        # the two cannot describe one pair of runs differently.
        prior_dossier = DossierStore(self._runtime_root).previous(
            key, before=getattr(dossier, "dossier_version", 0))
        decision["second_iteration"] = self._second_iteration_delta_composed(
            session, run_id, current=decision,
            previous=(self._executive_read(prior_dossier)
                      if prior_dossier is not None else None))
        listing = self._listing_for(run_id)
        stamp = " · ".join(bit for bit in (
            f"Analysis {run_id[:8]}",
            f"Ticker {listing.ticker}" if listing.ticker else "",
            str(meta.get("as_of", ""))[:10]) if bit)
        body = xray.render(
            decision, company=name, stamp=stamp,
            labels=self._citation_labels(run_id),
            crossing=str(getattr(dossier, "crossing", "") or ""),
            links=[("Full analysis", f"/runs/{run_id}/full"),
                   ("Presentation", f"/runs/{run_id}/slides"),
                   ("Evidence and sources", f"/runs/{run_id}/sources"),
                   ("Executive brief", f"/runs/{run_id}/brief")])
        return self._html(self._page(f"{name} — executive X-Ray", body,
                                     session, session.get("csrf", "")))

    def _intelligence_page(self, session, run_id):
        """The executive INTELLIGENCE dashboard for one company.

        Named `_intelligence_page`, not `_dashboard_page`: the webapp already
        has a `_dashboard_page` for platform status, and Python would silently
        have kept whichever was defined last -- which is how a founder-facing
        route ends up serving an operator page.
        """
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        from intent_engine.founder_brief import layers as fl
        from intent_engine.founder_brief import render as fr
        brief, report, name = self._founder_layers(run_id)
        footing = self._evidence_footing(
            run_id, name, self._listing_for(run_id).ticker)
        from intent_engine.external_intel import visuals as _charts
        external = self._external_context(run_id)
        body = (f'{fr.BRIEF_CSS}{_charts.CHART_CSS}<main class="fb">'
                f'<h1>{_e(name)} — intelligence</h1>'
                + fr.render_dashboard(
                    fl.build_dashboard(brief, report, footing=footing,
                                       external=external),
                    charts=_external_charts(external))
                + fr._deeper(run_id) + "</main>")
        return self._html(self._page(f"{name} — intelligence", body, session,
                                     session.get("csrf", "")))

    def _story_page(self, session, run_id):
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        from intent_engine.founder_brief import layers as fl
        from intent_engine.founder_brief import render as fr
        brief, report, name = self._founder_layers(run_id)
        ledger = fl.Ledger()
        # The 60-second brief was read first, so its sentences are spent.
        if brief.key_insight:
            # The fact and the implication were on the first screen, so the
            # story must not restate them. The DECISION is deliberately NOT
            # spent: it is the section the whole narrative builds toward, and
            # deduplicating it away leaves the story without its climax.
            # Orientation repetition is permitted; a missing mandated section
            # is not.
            ledger.spend(brief.key_insight.fact, brief.key_insight.so_what)
        sections = fl.build_story(
            brief, report, ledger,
            footing=self._evidence_footing(
                run_id, name,
                self._listing_for(run_id).ticker))
        actions = fl.build_actions(brief)
        body = (f'{fr.BRIEF_CSS}<main class="fb"><h1>{_e(name)} — the '
                f'decision story</h1>'
                + fr.render_story(sections, run_id=run_id)
                + fr.render_actions(actions)
                + fr._deeper(run_id) + "</main>")
        return self._html(self._page(f"{name} — decision story", body,
                                     session, session.get("csrf", "")))

    def _founder_brief_page(self, session, run_id, result):
        """The 60-SECOND FOUNDER BRIEF — the default completed-result view.

        Serves every company mode from one route. A rich public company and a
        one-page marketing site both land here; what differs is which sections
        have material behind them, not which page the reader gets. That is the
        point of the mode system -- equally USEFUL, not equally detailed.
        """
        from intent_engine.founder_brief import build as fb
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
        listing = self._listing_for(run_id)
        ticker = listing.ticker

        mode = fb.classify_mode(
            is_public=listing.is_public, evidence_count=len(observations),
            independent_sources=independent, has_thesis=has_view,
            has_financials=False)

        # Market context comes ONLY from the versioned export, and only when
        # a snapshot has actually been published. Absent or unreadable, the
        # section renders "Unavailable" -- never a zero, and never a 500: a
        # founder-facing page must not die because an upstream research
        # artefact is missing.
        market = self._market_snapshot(run_id) if ticker else None

        # `company_name` is what the presentation deck has always used, so a
        # run whose identity record is absent (every anonymous demo run) was
        # headed "Shopify — presentation" on one layer and "This company" on
        # the founder brief beside it. The name was in the report the whole
        # time; only this path declined to read it.
        # ...and the run's own metadata is the source that is ALWAYS set,
        # because it is what the founder typed. Leaving it out of the chain
        # is why three unrelated companies rendered byte-identical bounded
        # pages headed "This company": on a limited run the identity record
        # and the report are both empty, so every company collapsed onto the
        # same placeholder. Measured on the deployed preview -- Tesla, NVIDIA
        # and Costco produced identical dashboard, story and executive-brief
        # text down to the word count.
        name = (identity.get("canonical_name") or identity.get("name")
                or report.get("company_name")
                or result.get("company")
                or (self.ci.run_meta(run_id) or {}).get("company_name")
                or "This company")
        brief = fb.build(company=name, mode=mode, report=report,
                         observations=observations, market=market)

        # THE DECISION IS THE DEFAULT SCREEN.
        #
        # `render_brief` reads `brief.key_insight`, which is None whenever the
        # thesis view is withheld -- and the composed decision can be
        # DECISION_READY while that is true, because it decides across the
        # portfolio rather than from the top-ranked reading alone. Measured on
        # the preview: Palantir's default page said "No strategic conclusion
        # is being asserted about this company" while the deck one click away
        # carried two options, a cost on each side and the check that
        # separates them. Same run, same decision object, three surfaces
        # disagreeing about whether an answer existed.
        #
        # So the default now renders the one decision, vertically, and the
        # brief object feeds it rather than gating it.
        from intent_engine.founder_brief import narrative as fn
        from intent_engine.founder_brief.layers import build_actions
        from intent_engine.strategic_intelligence.decision import decision_of

        story = fn.build_narrative(
            company=name, brief=brief, report=report,
            observations=observations, decision=decision_of(report),
            actions=build_actions(brief),
            external=self._external_context(run_id),
            contract=self._executive_contract(run_id))
        # The assistant belongs ON the default screen. Dropping it was a real
        # regression: a founder who has just read a 60-second answer is exactly
        # the person with a follow-up question, and making them navigate first
        # is how a conversation never starts.
        body = fr.BRIEF_CSS + fn.render_narrative(
            story, run_id=run_id,
            citation_labels=self._citation_labels(run_id),
            trailing=self._ask_form(run_id, report, session))
        return self._html(self._page(f"{name} — the decision", body,
                                     session, session.get("csrf", "")))

    def _ask_form(self, run_id, report, session):
        """The one-click assistant, with company-specific suggestions."""
        csrf = session.get("csrf", "")
        suggested = "".join(
            f'<form action="/runs/{_e(run_id)}/conversation" method="post" '
            f'style="display:inline-block;margin:3px">'
            f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
            f'<input type="hidden" name="question" value="{_e(q)}">'
            f'<button type="submit" class="ghost">{_e(q)}</button></form>'
            for q in self._founder_questions(report or {}))
        return (
            f'<section class="ui-controls" aria-label="Ask a follow-up">'
            f'<h2>Ask a follow-up</h2>'
            f'<form action="/runs/{_e(run_id)}/conversation" method="post">'
            f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
            f'<label for="q">Your question</label> '
            f'<input id="q" name="question" required style="min-width:60%">'
            f'<button type="submit">Ask</button></form>'
            f'<p class="muted small">Suggested:</p>{suggested}</section>')

    def _slides_page(self, session, run_id):
        if not self._owned(session, run_id):
            return self._error_page(404, "no such run for this account")
        # THE SAME GUARD `_run_page` HAS, WHICH THIS ROUTE NEVER GOT. A FAILED
        # run composed no report, and building a deck from one raised —
        # measured live on preview-v3 (Alphabet, https://abc.xyz, run
        # 01KZB2PCVR1A5SFVQTA2B9FYE5): `/runs/{id}` and `/full` answered 200
        # and `/slides` answered 500 for the same run, on a link the layer nav
        # offers the reader.
        if self._is_real_run(run_id):
            avail = self._availability(run_id)
            # Asking for the deck before the deck exists is the reader
            # following the layer nav, not an error. Send them to the page
            # that says what IS ready.
            if avail["in_flight"]:
                return self._redirect(f"/runs/{run_id}/progress")
            if not avail["slides_ready"]:
                if avail["state"] == "FAILED" and not avail["has_report"]:
                    return self._failed_run_page(session, run_id)
                return self._redirect(f"/runs/{run_id}")
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
                              contract=self._executive_contract(run_id),
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

    # -- INTERNAL IMPACT ---------------------------------------------------
    # D-IBG-001 / D-SYN-001 / F-TS-001 all had live proofs that required a
    # request to reach them, and no Founder request path established a
    # TenantScope, so all three sat at CAPABILITY_VERIFIED. This route is that
    # path. It parses the query and calls `internal_view.answer`, and does
    # NOTHING ELSE -- so a controlled local invocation of `answer()` executes
    # exactly the code an HTTP request executes, with no helper bypass.
    def _internal_impact(self, session, environ):
        from urllib.parse import parse_qs

        from intent_engine.webapp import internal_view

        query = {k: v[0] for k, v in
                 parse_qs(environ.get("QUERY_STRING", "")).items()}
        subject = (query.get("subject") or "").strip()
        if not subject:
            return self._error_page(
                400, "an internal-impact question needs a subject")
        from intent_engine.executive import living_decision as LDR
        from intent_engine.external_intel import minimum_data_request as MDRM

        root = self.config.web_store_path.parent
        ans = internal_view.answer(
            session=session, subject_id=subject,
            decision=(query.get("decision")
                      or "what this external subject changes internally"),
            directory=self._tenant_directory, store=self._private_graph,
            audit=self._scope_audit,
            requests=MDRM.DataRequestStore(root),
            decisions=LDR.LivingDecisionStore(root),
            decision_id=(query.get("decision_id") or "").strip(),
            runtime_sha=self._runtime_sha())
        # The receipt is written for a scopeless request too: the requests an
        # auditor came for are the refused ones.
        self._tenant_receipts.append(ans.receipt)
        # SYSTEM learning, kept apart from anything economic: these counters
        # describe this engine's restraint, never a market.
        self._mdr_telemetry = self._mdr_telemetry.merged(ans.telemetry)
        if query.get("format") == "json":
            payload = ans.as_dict()
            payload["telemetry_cumulative"] = self._mdr_telemetry.as_dict()
            return self._ok_json(payload)
        return self._html(self._page(
            "Internal impact", internal_view.render(ans), session,
            self.auth.csrf_token(self._cookie(environ, "sid") or "") or ""))

    # -- LIVING DECISION RECORDS (E-LDR-001) -------------------------------
    # A projection, never a generator. Every answer below is computed from
    # stored revisions, so "what changed your mind?" is auditable rather than
    # narrated -- which is the difference between a decision record and a chat
    # transcript.
    def _decisions(self, session, environ):
        import html as _html
        from urllib.parse import parse_qs

        from intent_engine.executive import living_decision as LDR
        from intent_engine.webapp.tenancy import receipt_for, scope_for_session

        query = {k: v[0] for k, v in
                 parse_qs(environ.get("QUERY_STRING", "")).items()}
        scope = scope_for_session(session, directory=self._tenant_directory,
                                  audit=self._scope_audit)
        request_id = "dreq_" + (self._runtime_sha() or "0")[:12]

        if scope is None:
            # A scopeless reader is not shown an empty decision list, because
            # an empty list reads as "you have no open decisions". It is told
            # that it holds no authority.
            payload = {"contract": "living_decisions_view.v1", "scoped": False,
                       "state": "DECISIONS_UNAVAILABLE",
                       "reason": "SCOPELESS_READ", "open": [], "awaiting": []}
            self._tenant_receipts.append(receipt_for(
                request_id=request_id, scope=None,
                company_id=query.get("company", ""), operation="decisions.read",
                denial_reason="SCOPELESS_READ",
                runtime_sha=self._runtime_sha()))
        else:
            root = self.config.web_store_path.parent
            store = LDR.LivingDecisionStore(root)
            open_rows = LDR.open_decisions(store, scope=scope)
            payload = {
                "contract": "living_decisions_view.v1", "scoped": True,
                "state": ("NO_OPEN_DECISIONS" if not open_rows
                          else "OPEN_DECISIONS"),
                "open": [dict(r, what_would_change_this=None) for r in open_rows],
                "awaiting_information": [
                    r["decision_id"]
                    for r in LDR.awaiting_information(store, scope=scope)],
                "awaiting_outcome": [
                    r["decision_id"]
                    for r in LDR.awaiting_outcome(store, scope=scope)],
            }
            # "What are we waiting for, and why?" answered from the canonical
            # request rows rather than from a copy inside the decision. The
            # decision holds IDS; dereferencing them here is what keeps one
            # decision history instead of two.
            from intent_engine.external_intel import minimum_data_request as MDRM

            _requests = MDRM.DataRequestStore(root)
            awaiting_ids = {
                rid for r in LDR.awaiting_information(store, scope=scope)
                for rid in (r.get("minimum_data_requests") or ())}
            awaiting_mves = {
                mid for r in LDR.awaiting_information(store, scope=scope)
                for mid in (r.get("mve_refs") or ())}
            payload["minimum_data_requests"] = [
                q.as_dict() for q in _requests.requests(scope=scope)
                if q.request_id in awaiting_ids]
            payload["minimum_viable_experiments"] = [
                x.as_dict() for x in _requests.experiments(scope=scope)
                if x.experiment_id in awaiting_mves]
            if query.get("decision"):
                payload["changed"] = list(LDR.what_changed(
                    store, query["decision"], scope=scope))
            self._tenant_receipts.append(receipt_for(
                request_id=request_id, scope=scope,
                company_id=query.get("company", ""), operation="decisions.read",
                requested=len(open_rows), allowed=len(open_rows),
                runtime_sha=self._runtime_sha()))

        if query.get("format") == "json":
            return self._ok_json(payload)
        rows = "".join(
            f"<li data-status=\"{_html.escape(r['status'])}\">"
            f"<strong>{_html.escape(r['decision_question'])}</strong>"
            f"<span class=\"status\">{_html.escape(r['status'])}</span>"
            + ("<span class=\"not-decided\">recommendation only — "
               "no human has chosen</span>"
               if r.get("is_recommendation_only") else
               f"<span class=\"decided-by\">decided by "
               f"{_html.escape(r.get('decided_by', ''))}</span>")
            + "</li>"
            for r in payload.get("open", []))
        body = (f"<section id=\"decisions\" data-state=\""
                f"{_html.escape(payload['state'])}\"><h2>Open decisions</h2>"
                + (f"<ul>{rows}</ul>" if rows else
                   "<p>No decision records are visible to this reader.</p>")
                + "</section>")
        return self._html(self._page(
            "Decisions", body, session,
            self.auth.csrf_token(self._cookie(environ, "sid") or "") or ""))

    def _record_decision(self, session, form, environ):
        """A named person records what they chose. The only write path.

        THE WRITE THIS EXISTS TO MAKE POSSIBLE, AND THE ONE IT REFUSES. The
        product could not previously record that a human decided anything --
        so every memory screen truthfully said nothing had been decided, and
        the five stages, while correctly modelled, had no way to be exercised
        past the first one.

        It refuses, in this order and for different reasons:

          no scope    a decision belongs to a named tenant; there is no such
                      thing as an unscoped decision, and a public visitor
                      recording one against a company would be writing into
                      somebody else's history;
          no actor    `record_human_decision` refuses it, because a decision
                      nobody made is a recommendation;
          no choice   likewise -- "somebody decided" is not a decision.

        The actor is taken from the SESSION, never from the form. A caller
        who could name the decider could attribute their own choice to
        somebody else, and the record's whole audit value is that it says who
        chose.
        """
        from intent_engine.core.tenant import ScopeRefused
        from intent_engine.executive import living_decision as LDR
        from intent_engine.webapp.tenancy import receipt_for, scope_for_session

        scope = scope_for_session(session, directory=self._tenant_directory,
                                  audit=self._scope_audit)
        request_id = "dwri_" + (self._runtime_sha() or "0")[:12]
        company = str(form.get("company", "") or "").strip()
        choice = str(form.get("choice", "") or "").strip()
        rationale = str(form.get("rationale", "") or "").strip()
        # WHO IS ASKING, not who the form says chose.
        actor = str((session or {}).get("email", "")
                    or (session or {}).get("user", "") or "").strip()

        if scope is None:
            self._tenant_receipts.append(receipt_for(
                request_id=request_id, scope=None, company_id=company,
                operation="decisions.write", denial_reason="SCOPELESS_WRITE",
                runtime_sha=self._runtime_sha()))
            return self._error_page(
                403, "Recording a decision requires an account. A decision "
                     "record says what a named person in a named organisation "
                     "chose, so there is nowhere to put an anonymous one.")
        if not actor:
            return self._error_page(
                403, "This session does not identify who is deciding, and a "
                     "decision that cannot name its decider cannot be audited.")

        root = self.config.web_store_path.parent
        store = LDR.LivingDecisionStore(root)
        record = self._living_record_for(company, scope=scope)
        try:
            if record is None:
                # No open decision for this company yet: open one, then
                # decide it. Opening is not deciding -- the record passes
                # through RECOMMENDATION_READY so the transition table sees
                # the same move it would see for an engine-opened decision.
                question = (str(form.get("question", "") or "").strip()
                            or f"What should we do about {company}?")
                record = LDR.open_decision(
                    scope=scope, company_id=company, question=question,
                    owner=actor, runtime_sha=self._runtime_sha())
                record = LDR.revise(
                    record, scope=scope, status=LDR.RECOMMENDATION_READY,
                    recommendation=str(form.get("recommendation", "") or ""),
                    reason="opened for a human decision")
                store.append(record, scope=scope)
            decided = LDR.record_human_decision(
                record, scope=scope, choice=choice, actor=actor,
                rationale=rationale)
            store.append(decided, scope=scope)
        except LDR.DecisionRefused as exc:
            # The refusal states are the product's discipline, so the reader
            # is told which one refused rather than shown a generic failure.
            return self._error_page(400, f"{exc.failure_state}: {exc}")
        except ScopeRefused as exc:
            return self._error_page(403, str(exc))

        self._tenant_receipts.append(receipt_for(
            request_id=request_id, scope=scope, company_id=company,
            operation="decisions.write", requested=1, allowed=1,
            runtime_sha=self._runtime_sha()))
        return self._redirect(f"/decisions?company={company}")

    def _manifest_placement(self, company_id: str, *, name: str = "",
                            domain: str = ""):
        """This company's manifest id, cohort, and the manifest version.

        Read-only, and read from the canonical manifest rather than from
        anything the analysis produced: nothing observed at runtime may place
        a company in a cohort.

        RESOLVES ON DOMAIN AND NAME, NOT ONLY ON A NORMALISED ID. The analysis
        resolves companies to their LEGAL name, so "Cloudflare, Inc." became
        the key `cloudflare-inc` and matched no manifest entry — every real
        company's dossier was stamped with no cohort and no manifest version,
        which reads exactly like a company outside the universe. Found by the
        first breaker run; it would have made the whole 100-company
        measurement read zero without anything raising.

        Returns the MANIFEST id when the company is in the universe, so the
        dossier is stored where the programme can find it again.
        """
        try:
            from intent_engine.validation import load
            manifest = load()
            company = manifest.resolve(domain=domain, name=name,
                                       company_id=company_id)
            return ((company.company_id, company.cohort, manifest.version)
                    if company else (company_id, "", ""))
        except Exception:  # noqa: BLE001 - the manifest must never fail a run
            _LOG.warning("validation manifest unavailable for %s", company_id)
            return company_id, "", ""

    def _demo_dossier_store(self):
        from intent_engine.demo_dossier.store import DossierStore
        return DossierStore(self._runtime_root)

    def _demo_dossier_index(self):
        """Every dossier this deployment has assembled, as an index.

        Deliberately unscoped and deliberately harmless: `views.index_row`
        emits states, availabilities and runtime SHAs, and no reference ids
        at all. There is nothing here to partition by tenant because there is
        nothing here that belongs to one.
        """
        from intent_engine.demo_dossier import views
        store = self._demo_dossier_store()
        rows = [d for d in (store.latest(c) for c in store.companies())
                if d is not None]
        return self._ok_json(views.index(rows))

    def _demo_dossier_detail(self, company_id: str):
        """One dossier, with tenant-partitioned reference ids withheld.

        The withholding is unconditional — see `views` for why that is
        stronger than a scope check here, and why a missing company is a
        stated reading rather than a bare 404.
        """
        from urllib.parse import unquote

        from intent_engine.demo_dossier import views
        from intent_engine.demo_dossier.store import company_key
        company_id = company_key(unquote(company_id or ""))
        dossier = self._demo_dossier_store().latest(company_id)
        if dossier is None:
            # 404 for the caller, but with a BODY that says which absence
            # this is. A bare status code cannot distinguish "never analysed
            # here" from "analysed and refused", and at 100 companies that
            # difference is the whole signal.
            return ("404 Not Found",
                    [("Content-Type", "application/json")],
                    json.dumps(views.not_found(company_id)))
        payload = views.with_executive_read(views.detail(dossier),
                                            self._executive_read(dossier))
        # THE CEO'S QUESTIONS, ON THE SAME PAYLOAD AS THE READ THEY PROJECT.
        # A separate endpoint would let a surface pair an answer with a
        # decision from a different assembly, which is the one thing the
        # single-decision design exists to prevent.
        payload["ceo_questions"] = self._ceo_questions(dossier)
        return self._ok_json(payload)

    def _decision_screen(self, company_id: str, which: str):
        """The X-Ray, the full analysis or the presentation, rendered.

        THREE ROUTES, ONE DECISION. All three compose the same
        `FounderDecision` from the same dossier and then project it; none of
        them reasons. That is what makes the cross-surface consistency check
        a property of the code rather than a thing to keep re-verifying: a
        difference between these pages could only come from a rendering bug,
        never from two answers.

        Open to anyone who can reach the dossier index, like the JSON detail
        beside it -- these carry no reference ids and nothing tenant-scoped,
        which is the same reason `views` withholds unconditionally.
        """
        from urllib.parse import unquote

        from intent_engine.demo_dossier.store import company_key
        from intent_engine.founder_brief import deep, xray

        company_id = company_key(unquote(company_id or ""))
        dossier = self._demo_dossier_store().latest(company_id)
        if dossier is None:
            # WHICH ABSENCE. A bare 404 cannot tell "never analysed here"
            # from "analysed and refused", and at 100 companies that is the
            # whole signal.
            return self._error_page(
                404, f"No analysis is stored here for {company_id!r}. That "
                     f"means this deployment has not run it — not that the "
                     f"company was analysed and found empty.")
        decision = self._executive_read(dossier)
        if decision is None:
            return self._error_page(
                500, "The decision for this company could not be composed. "
                     "That is a fault on this side, not a finding about the "
                     "company.")
        stamp = (f"Market snapshot {dossier.market_snapshot_id} · evidence "
                 f"cutoff {dossier.effective_evidence_cutoff}")
        base = f"/demo-dossiers/{company_id}"
        company = dossier.canonical_name or company_id
        if which == "full":
            body = deep.full_analysis(
                decision, company=company, stamp=stamp,
                links=[("Executive X-Ray", f"{base}/xray"),
                       ("Presentation", f"{base}/deck"),
                       ("Why this reading exists", f"{base}/evidence")])
        elif which == "deck":
            body = deep.presentation(
                decision, company=company, stamp=stamp,
                links=[("Executive X-Ray", f"{base}/xray"),
                       ("Full analysis", f"{base}/full"),
                       ("Why this reading exists", f"{base}/evidence")])
        else:
            body = xray.render(
                decision, company=company, stamp=stamp,
                crossing=str(getattr(dossier, "crossing", "") or ""),
                links=[("Full analysis", f"{base}/full"),
                       ("Presentation", f"{base}/deck"),
                       ("Why this reading exists", f"{base}/evidence")])
        return self._html(self._page(company, body, None, ""))

    @staticmethod
    def _discovery_detail(discovery: dict) -> str:
        """How hard we looked, in the buyer's words rather than ours.

        A hostile buyer's second question after "is it independent?" is "how
        hard did you try?", and a coverage enum alone does not answer it. This
        renders the WORK: channels tried, candidates considered, documents
        actually read. Absent when no producer ran -- inventing a number here
        would be worse than the silence it replaces.
        """
        if not discovery:
            return ('<p class="none">No discovery run is recorded for this '
                    'analysis, so how hard we searched is unknown.</p>')
        considered = int(discovery.get("candidates_considered") or 0)
        fetched = int(discovery.get("candidates_fetched") or 0)
        hits = int(discovery.get("hits_total") or 0)
        channels = discovery.get("channels_successful") or []
        bits = [f'<p class="none">We searched {len(channels) or 0} '
                f'independent channel(s), found {hits} filing(s) naming this '
                f'company, judged {considered} of them worth reading, and '
                f'read {fetched} in full.</p>']
        if discovery.get("budget_exhausted"):
            bits.append('<p class="none">We stopped at our reading budget, so '
                        'candidates remain that we have not assessed.</p>')
        reasons = discovery.get("rejection_reasons") or {}
        if isinstance(reasons, dict) and reasons:
            listed = " · ".join(
                f"{_e(str(k).replace('_', ' ').lower())}: {int(v)}"
                for k, v in sorted(reasons.items())[:8])
            bits.append(f'<p class="none">Set aside — {listed}</p>')
        return "".join(bits)

    def _evidence_screen(self, company_id: str):
        """Why this reading exists: every source, and what it is worth.

        THE FIFTH PROJECTION, beside the X-Ray, the full analysis, the
        presentation and the decision history. It renders the sanitized
        records that already cross the bridge -- it computes nothing, and
        deliberately does not re-decide independence or relevance, because
        two opinions about one document is how the drawer and the count
        start disagreeing.

        The sources are grouped by WHAT THEY ARE WORTH rather than listed
        flat, because the interesting fact about this company's evidence is
        not that there are eleven documents. It is that none of them is an
        outside voice with anything to say -- and a flat bibliography hides
        exactly that.
        """
        from urllib.parse import unquote

        from intent_engine.company_ingestion import relevance as REL
        from intent_engine.demo_dossier.store import company_key

        company_id = company_key(unquote(company_id or ""))
        dossier = self._demo_dossier_store().latest(company_id)
        if dossier is None:
            return self._error_page(
                404, f"No analysis is stored here for {company_id!r}, so "
                     f"there are no sources to show.")
        company = getattr(dossier, "canonical_name", "") or company_id
        founder = getattr(dossier, "founder_block", {}) or {}
        provenance = founder.get("claim_provenance") or {}
        base = f"/demo-dossiers/{company_id}"
        nav = (f'<p class="none"><a href="{base}/xray">X-Ray</a> · '
               f'<a href="{base}/full">Full analysis</a> · '
               f'<a href="{base}/deck">Presentation</a> · '
               f'<a href="{base}/memory">Decision history</a></p>')

        state = str(provenance.get("state") or "")
        records = provenance.get("records") or []
        if not records:
            # An absent projection is a fact about us. Saying "no sources"
            # would be a claim about the company.
            reason = str(provenance.get("reason") or
                         "This analysis carries no source projection.")
            return self._html(self._page(company, (
                f'<p class="eyebrow">Why this reading exists</p>'
                f'<h1>{_e(company)}</h1>{nav}'
                f'<section class="card"><h2>No sources are attached</h2>'
                f'<p>{_e(reason)}</p>'
                f'<p class="none">State: '
                f'{_e(state or "PROVENANCE_UNAVAILABLE")}'
                f'</p></section>'), None, ""))

        supporting = [r for r in records if r.get("independence_bearing")]
        set_aside = [r for r in records
                     if r.get("independent_voice")
                     and not r.get("independence_bearing")]
        own = [r for r in records if not r.get("independent_voice")]

        # WHAT A ZERO LICENCES US TO SAY. The coverage state is MEASURED by
        # the discovery run -- how many candidates it considered, how many
        # documents it actually read, whether it ran out of budget or ran out
        # of candidates. An absent block means no producer ran, which reads
        # DISCOVERY_NOT_RUN and never licenses "this company has no coverage".
        discovery = founder.get("discovery_coverage")
        discovery = discovery if isinstance(discovery, dict) else {}
        reading = REL.zero_reading(
            independent_relevant=len(supporting),
            coverage=str(discovery.get("coverage") or REL.DISCOVERY_NOT_RUN),
            channels_attempted=len(discovery.get("channels_attempted") or []),
            channels_successful=len(discovery.get("channels_successful") or []))
        headline = (
            f'<section class="card"><h2>Independent support</h2>'
            f'<p><strong>{len(supporting)}</strong> of {len(records)} '
            f'source(s) are both independent of {_e(company)} and say enough '
            f'about it to support the reading.</p>'
            + (f'<p>{_e(reading["statement"])}</p>' if reading["statement"]
               else "")
            + f'<p class="none">Search coverage: '
              f'{_e(reading["coverage"])} · reading: {_e(reading["reading"])}'
              f'</p>'
            + self._discovery_detail(discovery)
            + '</section>')

        def _card(rec):
            bits = []
            for label, key in (("Author", "author"), ("Host", "host"),
                               ("Subject", "subject"),
                               ("Published", "published_at"),
                               ("Retrieved", "retrieved_at"),
                               ("Freshness", "freshness")):
                value = str(rec.get(key) or "")
                if value:
                    bits.append(f"<dt>{label}</dt><dd>{_e(value)}</dd>")
            url = str(rec.get("url") or "")
            link = (f'<p><a href="{_e(url)}" rel="nofollow noopener" '
                    f'target="_blank">{_e(url[:90])}</a></p>' if url else
                    '<p class="none">This source is not publicly linkable.</p>')
            passage = str(rec.get("passage") or "")
            return (
                f'<section class="card">'
                f'<h3>{_e(rec.get("title") or "Untitled source")}</h3>'
                f'<p><strong>{_e(rec.get("plain_statement") or "")}</strong></p>'
                f'<p>{_e(rec.get("relevance_statement") or "")}</p>'
                + (f'<blockquote>{_e(passage)}</blockquote>' if passage else "")
                + link
                + f'<dl>{"".join(bits)}</dl>'
                + f'<p class="none">Independent voice: '
                  f'{"yes" if rec.get("independent_voice") else "no"} · '
                  f'Relevance: {_e(rec.get("relevance") or "")} · '
                  f'Counts as corroboration: '
                  f'{"yes" if rec.get("independence_bearing") else "no"}</p>'
                + (f'<p class="none">{_e(rec.get("relevance_reason") or "")}'
                   f'</p>' if rec.get("relevance_reason") else "")
                + '</section>')

        sections = [headline]
        for title, note, group in (
            ("Independent and relevant",
             "Outside voices that discuss this company. These are what the "
             "reading rests on.", supporting),
            ("Independent, but not relevant here",
             "Written by somebody else, and they do not say enough about "
             "this company to support the reading. Shown because a source "
             "set aside is more informative than a source hidden.", set_aside),
            ("Written by the company itself",
             "Useful evidence, and often the best there is — but the company "
             "speaking about itself cannot corroborate itself.", own),
        ):
            if not group:
                continue
            sections.append(f'<h2>{title} ({len(group)})</h2>'
                            f'<p class="none">{note}</p>'
                            + "".join(_card(r) for r in group))

        body = (f'<p class="eyebrow">Why this reading exists</p>'
                f'<h1>{_e(company)}</h1>{nav}' + "".join(sections))
        return self._html(self._page(company, body, None, ""))

    def _memory_screen(self, company_id: str):
        """What we decided, what we did, and what came of it.

        THE FOURTH PROJECTION of the same decision, beside the X-Ray, the
        full analysis and the presentation -- except that the questions here
        are about the PAST, and the past lives in `LivingDecisionRecord`
        rather than in the composed `FounderDecision`.

        Every stage that has not happened is shown as not having happened.
        The point of the screen is that a reader can see the difference
        between what the engine recommended, what a person chose, what the
        company did, and what followed -- because a product that blurs them
        will eventually tell somebody "we expanded and it worked" about a
        decision nobody executed.
        """
        from urllib.parse import unquote

        from intent_engine.demo_dossier.store import company_key
        from intent_engine.executive import personal_ai as PA

        company_id = company_key(unquote(company_id or ""))
        dossier = self._demo_dossier_store().latest(company_id)
        if dossier is None:
            return self._error_page(
                404, f"No analysis is stored here for {company_id!r}, so "
                     f"there is no decision history to show.")
        company = getattr(dossier, "canonical_name", "") or company_id
        # No scope on this public page, so no decision history is read.
        # The questions still render, each stating that nothing is recorded,
        # which is the truthful answer for a visitor who has decided nothing.
        record = self._living_record_for(company_id, scope=None)
        decision = self._executive_read(dossier)
        rows = []
        for question in PA.MEMORY_QUESTIONS:
            out = PA.answer(question, record=record, decision=decision)
            state = "" if out.supported else (
                f'<p class="none">Not established: '
                f'{_e(out.information_gap or "nothing on the record")}</p>')
            rows.append(
                f'<section class="card"><h2>{_e(question)}</h2>'
                f'<p>{_e(out.answer)}</p>{state}</section>')
        base = f"/demo-dossiers/{company_id}"
        body = (
            f'<p class="eyebrow">Decision history</p><h1>{_e(company)}</h1>'
            f'<p class="none">The engine&rsquo;s reading is on the '
            f'<a href="{base}/xray">X-Ray</a>. This page is the record of '
            f'what was decided and done, which is a different thing: a '
            f'recommendation is not a decision, and a decision is not an '
            f'act.</p>' + "".join(rows))
        return self._html(self._page(company, body, None, ""))

    def _living_record_for(self, company_id: str, scope=None):
        """This company's latest living decision, or None. Never raises.

        A DECISION HISTORY IS TENANT-SCOPED, always. Without a scope this
        returns None rather than reading the store unscoped -- the decisions
        JSON view beside it refuses the same read as SCOPELESS_READ, and a
        public page that showed one tenant's decisions to another visitor
        would be the worst kind of leak: it is not evidence about a company,
        it is what a named person chose to do.
        """
        if scope is None:
            return None
        try:
            from intent_engine.executive import living_decision as LDR
            store = LDR.LivingDecisionStore(self.config.web_store_path.parent)
            rows = [r for r in store.all(scope=scope)
                    if str(r.get("company_id") or "") == company_id]
            if not rows:
                return None
            latest = sorted(rows, key=lambda r: r.get("revision", 0))[-1]
            return LDR.LivingDecisionRecord(**{
                k: v for k, v in latest.items()
                if k in LDR.LivingDecisionRecord.__dataclass_fields__})
        except Exception:                                   # noqa: BLE001
            # A memory that cannot be read is not a memory that is empty,
            # but the screen degrades to "nothing recorded" either way and
            # says so per question rather than failing the page.
            return None

    def _learning_acceleration(self, environ):
        """What the engine learned, over three windows.

        RENDERS THE MARKET ENGINE'S OWN REPORT and computes no metric of its
        own. Two definitions of "novel evidence" is how a dashboard starts
        disagreeing with the engine it describes.

        The headline is deliberately NOT the arrival count. A cycle that
        re-reads eighty pages and changes nothing has been busy, not
        productive, and putting 86 at the top of the page teaches a reader to
        mistake the first for the second.
        """
        from intent_engine.demo_dossier import learning_bridge as LB
        windows = []
        for period, label in (("day", "Today"), ("week", "Last 7 days"),
                              ("month", "Last 30 days")):
            report = LB.load(period)
            reading = LB.activity_versus_learning(report)
            if not report.available:
                windows.append(
                    f'<section class="card"><h2>{_e(label)}</h2>'
                    f'<p class="none">{_e(report.reason)}</p></section>')
                continue
            payload = report.payload
            bottleneck = payload.get("bottleneck") or {}
            nxt = payload.get("next_research_priority") or {}
            summary = payload.get("executive_summary") or {}
            learned = "".join(
                f"<li>{_e(x)}</li>"
                for x in (summary.get("top_learnings") or ())[:5])
            windows.append(
                f'<section class="card"><h2>{_e(label)}</h2>'
                f'<p class="verdict"><strong>{_e(reading["verdict"])}</strong>'
                f' — {_e(reading["why"])}</p>'
                f'<ul class="counts">'
                f'<li>{_e(str(reading["arrivals"]))} observations arrived</li>'
                f'<li>{_e(str(reading["novel"]))} were new; '
                f'{_e(str(reading["re_observed"]))} had been seen before</li>'
                f'<li>{_e(str(reading["changed_the_model"]))} changed the model</li>'
                f'<li>{_e(str(reading["tested_and_unchanged"]))} were tested and '
                f'held — a result, not an idle period</li></ul>'
                + (f"<h3>What it learned</h3><ul>{learned}</ul>"
                   if learned else "")
                + (f'<h3>What is holding learning back</h3>'
                   f'<p>{_e(bottleneck.get("bottleneck", ""))}: '
                   f'{_e(bottleneck.get("reason", ""))}</p>'
                   if bottleneck else "")
                + (f'<h3>What it will look at next</h3>'
                   f'<p>{_e(nxt.get("suggested_action", ""))}</p>'
                   f'<p class="none">{_e(nxt.get("why_now", ""))}</p>'
                   if nxt else "")
                + '</section>')
        body = (
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,'
            'initial-scale=1"><title>What the engine learned</title>'
            '<style>body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;'
            'max-width:820px;margin:0 auto;padding:2rem;color:#1a1a2e;'
            'line-height:1.55}.card{border:1px solid #e6e6ef;border-radius:10px;'
            'padding:1rem 1.2rem;margin:1rem 0}.none{color:#666;'
            'font-style:italic}.verdict{font-size:1.05rem}'
            'h3{margin-top:1.2rem;font-size:.95rem}</style></head><body>'
            '<main><h1>What the engine learned</h1>'
            '<p class="none">Read from the market engine&rsquo;s own learning '
            'record. Activity and learning are shown separately: reading more '
            'is not the same as knowing more.</p>'
            + "".join(windows) + '</main></body></html>')
        return self._html(body)

    def _registrant(self, dossier) -> dict:
        """The SEC's classification of this filer, or {}.

        WHY IT IS RESOLVED HERE. `compose` is deterministic and makes no
        network call, so the one classification lookup a company outside the
        validation manifest needs has to happen at the request layer. It is
        skipped entirely for the 100 manifest companies, which are already
        classified by hand -- so the common path costs nothing.

        Cached per company for the process lifetime: the SIC code of a
        registrant does not change between two page loads, and the SEC
        rate-limits.
        """
        cid = getattr(dossier, "company_id", "") or ""
        name = getattr(dossier, "canonical_name", "") or cid
        if not cid and not name:
            return {}
        cache = getattr(self, "_registrant_cache", None)
        if cache is None:
            cache = self._registrant_cache = {}
        if cid in cache:
            return cache[cid]
        out = {}
        try:
            from intent_engine.executive.company_profile import profile_for
            from intent_engine.validation import load as _load_manifest
            if profile_for(cid, name=name,
                           manifest=_load_manifest()).known:
                cache[cid] = out          # in the manifest; no lookup needed
                return out
        except Exception:                                   # noqa: BLE001
            pass
        try:
            from intent_engine.company_ingestion.edgar import (
                registrant_classification, resolve_cik)
            resolved = resolve_cik(name)
            if resolved:
                out = registrant_classification(resolved) or {}
        except Exception:                                   # noqa: BLE001
            out = {}
        cache[cid] = out
        return out

    def _ceo_questions(self, dossier) -> dict:
        """Every required CEO question, answered by projecting the decision.

        A failure is a STATE. An empty list would read as "this company has
        no answers", which is a claim about the company rather than about
        the composer.
        """
        try:
            from intent_engine.executive import ceo_questions as _Q
            from intent_engine.executive.decision_synthesis import compose
            decision = compose(dossier, registrant=self._registrant(dossier))
            return {"contract": _Q.CONTRACT,
                    "answers": [_Q.answer(q, decision).as_dict()
                                for q in _Q.REQUIRED_QUESTIONS]}
        except Exception as exc:                            # noqa: BLE001
            return {"state": "CEO_QUESTIONS_UNAVAILABLE",
                    "reason": f"the answers could not be composed: {exc}"}

    def _executive_read(self, dossier):
        """Compose the FounderDecision for one dossier. No model call.

        Composed HERE rather than inside `demo_dossier.views` because the
        synthesis is founder-side reasoning and that package is the neutral
        seam — the structural guard tokenizes its imports and rejects one,
        which is how this ended up in the right place.

        The previous version is passed so `what_changed` compares against a
        real earlier reading rather than announcing a change on every page
        load. A composer failure returns None, which the view renders as a
        stated absence: "could not be composed" is about the composer, and
        must never read as "this company has no decision".
        """
        try:
            from intent_engine.executive.decision_synthesis import compose
            # CALLED, NOT PROBED. This read `if hasattr(store, "previous")`
            # against a store that had no such method, so the expression was
            # None on every request and "what changed" reported a first
            # reading for every company forever. A capability test that can
            # only ever answer False is not a guard, it is a switched-off
            # feature -- and it stayed green because None is a legal value.
            previous = self._demo_dossier_store().previous(
                dossier.company_id, before=dossier.dossier_version)
            return compose(dossier, previous=previous,
                           registrant=self._registrant(dossier)).as_dict()
        except Exception:                                   # noqa: BLE001
            _LOG.warning("executive read not composed for %s",
                         dossier.company_id)
            return None

    def _runtime_sha(self) -> str:
        from intent_engine._version import version_info

        info = version_info()
        return str(info.get("git_sha") or info.get("app_version") or "")

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
        """The evidence behind one cited observation, read from the GRAPH.

        THE FIRST GRAPH-DRIVEN FOUNDER SURFACE. Ingestion has been building the
        business graph since 37b9c92 and no founder surface read it, so reports
        remained the effective source of truth for everything a founder sees.
        This page now resolves the evidence node, and — the part a report
        cannot express — the ROLE that evidence plays: whether it supports a
        reading or contradicts one.

        FAILS CLOSED. If the projection cannot be built, this returns None
        rather than quietly serving the report copy underneath. A silent
        fallback is how two sources of truth survive a migration: the new path
        looks live while the old one is still answering.

        The report is still read for the excerpt text, which the projection
        deliberately truncates for labels. That is a compatibility export, not
        a second truth, and it is asserted against the graph below.
        """
        report = self._strategic_report_for(run_id)
        if not report:
            return None
        observation = next(
            (o for o in (report.get("observations") or [])
             if o.get("observation_id") == observation_id), None)
        if observation is None:
            return None

        from intent_engine.business_graph import CONTRADICTS, SUPPORTS
        graph = self.ci.business_graph(run_id, {"strategic_report": report})
        node = graph.node(observation_id)
        if node is None:
            # The citation resolves in the report and not in the graph. That
            # is a projection defect, and showing the report copy would hide
            # it for as long as the two disagree.
            _LOG.warning("evidence %s missing from graph for run %s",
                         observation_id, run_id)
            return None

        # WHAT THIS EVIDENCE IS DOING. A contradiction rendered identically to
        # a supporting citation is the one thing this page must not do.
        roles = []
        for edge in graph.out_edges(observation_id, SUPPORTS):
            target = graph.node(edge.dst)
            roles.append(("Supports", target.label if target else edge.dst))
        for edge in graph.out_edges(observation_id, CONTRADICTS):
            target = graph.node(edge.dst)
            roles.append(("Contradicts", target.label if target else edge.dst))
        role_html = "".join(
            f'<p class="stamp"><strong>{_e(kind)}</strong> — {_e(what)}</p>'
            for kind, what in roles)

        label = self._citation_labels(run_id).get(observation_id, "")
        url = observation.get("source_url") or node.source or ""
        link = (f'<p><a href="{_e(url)}" rel="noopener noreferrer nofollow" '
                f'target="_blank">Open the source page</a></p>') if url else ''
        body = (
            f'{_BRIEF_CSS}<main class="brief">'
            f'<h1>Evidence</h1>'
            f'<p class="lead">{_e(observation.get("excerpt") or observation.get("text") or node.label)}</p>'
            + role_html
            + (f'<p class="stamp">From {_e(label or observation.get("source_title") or "a retrieved page")}'
               + (f' · {_e(observation.get("date") or node.as_of)}'
                  if (observation.get("date") or node.as_of) else '')
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
        # V3: Q&A answers from the SHARED founder intelligence object.
        #
        # Before this, Q&A independently re-interpreted the report -- two
        # interpreters over one report, which is two products. The brief could
        # say the evidence was thin while the assistant answered with
        # confidence, and a founder had no way to tell which to trust.
        #
        # The conversation engine still produces the ANSWER TEXT. What it no
        # longer decides is the implication, the decision, the confidence or
        # whether a withheld thesis may be revived.
        from intent_engine.founder_brief import qa as fqa
        brief, _report, _name = self._founder_layers(run_id)
        strat = self._strategic_report_for(run_id)
        engine_text = ""
        if strat is not None:
            from intent_engine.strategic_intelligence.conversation import (
                answer_strategic,
            )
            sa = answer_strategic(question, strat)
            # COMPARISON keeps its own page: it renders a side-by-side the
            # founder-answer shape cannot express, and collapsing it into a
            # single "direct answer" loses the comparison itself. Only
            # EXPLAINED is reframed through the shared object.
            if sa["intent"] == "COMPARISON":
                return self._strategic_answer_page(session, run_id, sa)
            if sa["intent"] == "EXPLAINED":
                # On the EXPLAINED branch `answer` is a STRUCTURED dict and
                # there is no `paragraphs` key at all, so the old fallback
                # str()'d the dict itself onto the page: a founder who asked
                # "what does this company do?" was shown
                # "{'direct_answer': ..., 'reasoning': ...}".
                engine = sa.get("answer")
                if isinstance(engine, dict):
                    engine_text = str(engine.get("direct_answer") or "")
                else:
                    engine_text = " ".join(
                        str(p.get("text", ""))
                        for p in (sa.get("paragraphs") or ())
                    ) or str(engine or "")
        observations = [o for o in ((_report or {}).get("observations") or ())
                        if isinstance(o, dict)]
        # The SAME canonical standing the analysis reasoned from, read from the
        # same dossier by the same contract. Q&A must not re-derive how
        # independent the sources are — that is the market side's judgement,
        # and a second derivation here is a second product. Absent a dossier
        # this stays UNRATED and the answer says so rather than counting rows.
        #
        # PINNED TO THE REVISION THE ANALYSIS READ. The dossier on disk is
        # live: the market side republishes it as evidence arrives. Reading it
        # unconditionally would answer a question about a WEEK-OLD analysis
        # using a standing that analysis never saw — the page would say the
        # evidence was thin while the assistant beneath it said sources now
        # agree, which is the two-interpreters split this module exists to
        # close, re-opened along the time axis. A dossier newer than the run
        # is treated as absent rather than as an upgrade.
        _trust = None
        try:
            from intent_engine.external_intel import evidence_trust as _et
            from intent_engine.external_intel import strategic_contract as _sc
            _intel = _sc.load(
                pathlib.Path(self._runtime_root) / "reports" / "market"
                / "strategic" / f"{_sc.company_key(_name)}.json",
                expected_company=_sc.company_key(_name))
            _ran = ((self.ci.run_meta(run_id) or {}).get("as_of") or "")[:10]
            _trust = _et.as_read_by(_intel, _ran)
        except Exception:  # noqa: BLE001 - a question must still be answerable
            _LOG.warning("trust standing unavailable for %s", run_id)
        founder_answer = fqa.answer(question, brief,
                                    contract=self._executive_contract(run_id),
                                    engine_answer=engine_text,
                                    observations=observations,
                                    trust=_trust)
        return self._founder_answer_page(session, run_id, founder_answer)
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
                    f'<h2>What is missing</h2>'
                    f'<p>{_e(_conf_para(c["confidence"], c["missing_evidence"]))}</p>'
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
                f'<h2>What this rests on</h2><ul>{reasons}</ul>'
                + (f'<p class="small muted">{_e(_grade_note(a["confidence"]))}'
                   f'</p>' if _grade_note(a["confidence"]) else '')
                + f'<h2>What would change my view</h2><ul>{falsify}</ul>'
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
        # RENDER THE REPORT, NOT ITS TABLE OF INTERNAL NAMES.
        #
        # This page used to emit `<li>{s["kind"]}</li>` — so someone opening a
        # shared link was shown five snake_case enum values
        # ("company_understanding", "what_stood_out", …) and no analysis at
        # all. Every section already carries a reader-facing `title` and cards
        # with headlines; the renderer was reading the one field on the object
        # that is internal and discarding the rest.
        #
        # The subset contract is unchanged — `render_report_preview` still
        # decides what may leave — and nothing internal is printed here:
        # `kind`, `insight_id` and claim ids stay out of the markup.
        company = (preview.get("company") or {}).get("normalized_name") or ""
        blocks = []
        for section in preview.get("sections", []):
            cards = []
            for card in section.get("cards", []):
                headline = (card.get("headline") or "").strip()
                if not headline:
                    continue
                bits = [f'<p class="headline">{_e(headline)}</p>']
                confidence = (card.get("confidence") or "").strip()
                if confidence:
                    bits.append(f'<p class="muted">Confidence: '
                                f'{_e(confidence)}</p>')
                for field, label in (("why_it_matters", "Why it matters"),
                                     ("alternative_explanation",
                                      "Another reading"),
                                     ("what_would_change_the_view",
                                      "What would change this")):
                    value = (card.get(field) or "").strip()
                    if value:
                        bits.append(f'<p class="muted">{label}: '
                                    f'{_e(value)}</p>')
                cards.append(f'<li>{"".join(bits)}</li>')
            if not cards:
                continue
            title = (section.get("title") or "").strip()
            blocks.append(f'<section><h2>{_e(title)}</h2>'
                          f'<ul class="cards">{"".join(cards)}</ul></section>')
        limitations = "".join(f'<li>{_e(l)}</li>'
                              for l in preview.get("limitations", []) if l)
        if limitations:
            blocks.append(f'<section><h2>What this does not cover</h2>'
                          f'<ul class="limits">{limitations}</ul></section>')
        if not blocks:
            blocks.append('<p>This analysis produced no shareable sections.</p>')
        heading = (f'Shared analysis: {_e(company)}' if company
                   else 'Shared executive report')
        body = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'<meta name="robots" content="noindex,nofollow">'
                f'<title>{heading}</title>{_SHARED_CSS}</head><body><main>'
                f'<h1>{heading}</h1>'
                f'<p class="muted">A read-only, evidence-backed extract of an '
                f'executive report. No private notes; no internal metadata; '
                f'nothing here can be edited.</p>'
                f'{"".join(blocks)}</main></body></html>')
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
            # ATTESTED BEATS GUESSED — INSIDE THE INDEPENDENT FAMILY TOO.
            #
            # Batch 12 established this for the company's own domain (an
            # attested `homepage_link` over a guessed `known_path`) and the
            # same defect survived one bucket over, where it was costing far
            # more.
            #
            # A `third_party_filing` is a filing by a DIFFERENT registrant that
            # an EDGAR full-text query just returned: the accession exists, the
            # filer is named, the date is exact, and the regulator serves it as
            # plain HTML. An `external_proposed` review-site URL is built by
            # slugifying the company name into a template and is marked
            # UNVERIFIED by its own producer — a guess, and one that is only
            # ever plausible for consumer software.
            #
            # Both scored 4, and the `independent` family takes ONE candidate,
            # so insertion order decided it. Measured on the frozen ten
            # (b13_discovery_before, 6645a4f): 39 third-party filings were
            # discovered and 38 discarded, while 10 of 10 companies spent
            # their single independent slot on a guessed g2.com URL — for a
            # bank, a miner, an airframer and a pharmaceutical company alike.
            # That is the whole of "zero independent external sources".
            #
            # ORDER ONLY. Nothing here makes a candidate eligible that was not
            # already eligible, and no host, scheme or redirect rule moves.
            if method == "third_party_filing":
                return 1
            if _on_refusing_host(candidate):
                return 9
            if "sitemap" in why:
                return 2
            # ATTESTED beats GUESSED, and until Batch 12 these tied.
            #
            # A `homepage_link` is a URL the company itself rendered on its
            # own page, so the publisher has asserted it exists. A
            # `known_path` is one of ~44 paths this system GUESSES at every
            # company (/about, /pricing, /newsroom, ...). Both scored 3, so a
            # guess could take one of the 14 approved-source slots ahead of a
            # link the site actually published.
            #
            # Measured on the frozen ten (b12_before, 6c3370d): 38 of 62
            # http_status failures were 404 — the largest single failure class
            # in the wave, larger than 403 (24), and every 404 is a slot spent
            # discovering that a guessed path does not exist. The slot is the
            # scarce resource, not the request: a run gets 14 of them.
            #
            # This changes ORDER ONLY. No candidate becomes eligible that was
            # not eligible before, no host, scheme or redirect rule moves, and
            # guesses still fill the leftover budget below. It is also
            # company-agnostic: no rule here can name a company, and a site
            # with no usable homepage links (the Sony case, where the homepage
            # 403s) has no attested links to promote and is unaffected.
            if method in ("homepage_link", "entered"):
                # `entered` is the URL the founder typed. It is the most
                # strongly attested URL in the run and the company's own
                # homepage is the single densest identity document there is;
                # leaving it tied with the guesses let a diversity tie-break
                # promote a slug-built review URL over it (measured on the
                # `non_english` fixture: the homepage dropped out of the run).
                return 3
            # A TEMPLATE GUESS, AND ITS OWN PRODUCER MARKS IT UNVERIFIED.
            #
            # `external_proposed` builds review-site URLs by slugifying the
            # company name. It ranks below a guessed path on the company's own
            # domain because it is measured to be worse: across the frozen ten
            # every one of these that took a slot answered 403, for a bank, a
            # miner, an airframer and a pharmaceutical company alike — none of
            # which a software review site has ever covered.
            #
            # DEMOTED, NOT EXCLUDED. For a consumer-software company these are
            # exactly the right sources, so they still take leftover budget;
            # they simply no longer outrank evidence that exists.
            if method == "external_proposed":
                return 5
            return 4

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
        # AMONG EQUALLY USEFUL CANDIDATES, PREFER AN ORIGIN WE DO NOT HAVE.
        #
        # Information value stays primary and this can never override it: the
        # preference applies ONLY inside one relevance tier of one family, so
        # a more relevant candidate is never displaced by a fresher origin.
        # That restriction is the point — a diversity rule that outranked
        # relevance would trade real evidence for variety, and several of the
        # frozen ten genuinely publish everything useful on one host.
        #
        # It binds here rather than in the leftover fill below because this
        # loop is where most slots are spent: `product` alone takes five, and
        # taking five pages from one host is how a cohort reaches a mean
        # origin concentration of 0.82 (b13_before) while other origins sit
        # unapproved.
        from intent_engine.company_ingestion.independence import origin_family

        pools = {name: list(group) for name, group in buckets}
        used = {name: 0 for name, _group in buckets}
        picked, seen_origins = [], set()
        while len(picked) < MAX_APPROVED_SOURCES:
            progressed = False
            for name, _group in buckets:
                if len(picked) >= MAX_APPROVED_SOURCES:
                    break
                if used[name] >= _QUOTAS.get(name, 1):
                    continue
                pool = pools[name]
                if not pool:
                    continue
                # `pool` is already sorted by relevance, so its head defines
                # the best tier available in this family right now.
                best_tier = _relevance_first(pool[0])
                choice = next(
                    (c for c in pool
                     if _relevance_first(c) == best_tier
                     and origin_family(c.get("url", "")) not in seen_origins),
                    pool[0])
                pool.remove(choice)
                picked.append(choice["candidate_id"])
                seen_origins.add(origin_family(choice.get("url", "")))
                used[name] += 1
                progressed = True
            if not progressed:
                break
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
            # Same tie-break as above, over what the quotas left behind, and
            # carrying the SAME `seen_origins` — otherwise the leftover budget
            # would happily refill the origin the quota loop just avoided.
            tiers: dict = {}
            for candidate in remaining:
                tiers.setdefault(_relevance_first(candidate),
                                 []).append(candidate)
            for tier in sorted(tiers):
                pool = tiers[tier]
                while pool and len(picked) < MAX_APPROVED_SOURCES:
                    choice = next(
                        (c for c in pool
                         if origin_family(c.get("url", "")) not in seen_origins),
                        pool[0])
                    pool.remove(choice)
                    picked.append(choice["candidate_id"])
                    seen_origins.add(origin_family(choice.get("url", "")))
                if len(picked) >= MAX_APPROVED_SOURCES:
                    break
        return picked

    # --- asynchronous analysis ------------------------------------------
    #: A run whose last transition is older than this and is not terminal is
    #: treated as INTERRUPTED. The free instance restarts without warning, and
    #: a run left permanently "reading evidence" is the worst of both worlds:
    #: it never finishes and never admits it.
    STALE_ATTEMPT_SECONDS = 15 * 60

    TERMINAL_STATES = ("COMPLETE", "PARTIAL", "FAILED", "REJECTED",
                       "INTERRUPTED")

    # --- what exists for a run, asked once -------------------------------
    #
    # WHY THIS EXISTS. Five handlers each decided independently what a run had,
    # and they disagreed. Measured live on preview-v3 at a183f51, one Alphabet
    # run (01KZB5F4F58V176TSGPXHXWB7H), all six routes sampled together:
    #
    #   t=0.0s   /=400  /progress=200  /brief=200  /full=200  /slides=200
    #   t=11.2s  /=200  /progress=200  /brief=200  /full=200  /slides=303
    #
    # The primary screen answered 400 while every other surface answered 200.
    #
    # AND THE READS WERE WRITES. `_real_result` composes on demand and
    # `_autorun` approves and fetches — both from a GET, both while the async
    # worker was doing the same thing. The 400 is `_autorun` losing the race to
    # approve; the 500 seen in earlier cycles is a compose racing a compose.
    # A page a reader refreshes must never be the thing that mutates the run.
    #
    # So availability is DERIVED, never inferred per handler, and this function
    # touches nothing: no approve, no fetch, no compose.
    AVAIL_NO_CONTENT = "NO_CONTENT_YET"
    AVAIL_IN_PROGRESS = "PARTIAL_PROGRESS"
    AVAIL_BOUNDED = "BOUNDED_DOSSIER_AVAILABLE"
    AVAIL_FULL = "FULL_REPORT_AVAILABLE"
    AVAIL_FAILURE = "TERMINAL_FAILURE"

    def _analysis_in_flight(self, run_id) -> bool:
        with self._analysis_lock:
            return run_id in self._analysis_inflight

    def _bounded_result(self, run_id, exc):
        """What the product can still say when full synthesis failed.

        MEASURED, NOT HYPOTHETICAL. Five fresh Alphabet runs on 568f7ec all
        ended identically: five sources read including the 10-K and the 10-Q,
        and composition raising
        `PersonalError: claim text overclaims: ['always']` — the editorial
        language wall refusing a sentence. The wall is right to refuse it. It
        was wrong that refusing one sentence threw away the whole run, and the
        reader got a failure page for a company whose filings had been read.

        This invents nothing. It carries the identity the run resolved, the
        documents it actually retrieved and the honest limitation of that
        mixture, and it says plainly that the synthesis did not complete. No
        thesis, no options, no recommendation — `_founder_brief_page` composes
        the bounded view from these facts exactly as it does for any run whose
        evidence supports no reading.

        Returns None when nothing usable survived, so a run that genuinely
        retrieved nothing still gets the terminal failure page.
        """
        documents = self._retrieved_documents(run_id)
        if not documents:
            return None
        meta = self.ci.run_meta(run_id) or {}
        observations = []
        for doc in documents:
            title = str(doc.get("title") or doc.get("final_url") or "").strip()
            if not title:
                continue
            observations.append({
                "observation_id": f"obs-{doc.get('source_id', '')}",
                "source_class": doc.get("source_class") or "company_owned",
                "source_title": title,
                "origin": doc.get("final_url", ""),
                "excerpt": "",
            })
        if not observations:
            return None
        coverage = sorted({o["source_class"] for o in observations})
        return {
            "run_id": run_id,
            "status": "BOUNDED_AFTER_COMPOSITION_FAILURE",
            "company_domain": meta.get("domain", ""),
            "observations": observations,
            "sections": [],
            "strategic_report": None,
            "coverage": {"document_count": len(documents),
                         "families": coverage},
            # The gate did not decide this; the composer never got that far.
            # Saying `may_synthesize` false is the honest reading of a run
            # with evidence and no synthesis.
            "readiness": {"may_synthesize": False,
                          "research_mode": "composition_incomplete"},
            # WITHOUT THIS THE PAGE CONTRADICTED ITSELF. `found` drives the
            # "What was found" list, and its empty-state reads "No usable
            # public source could be read" — printed directly under
            # "5 page(s) read", measured live at 19a9c5d. Name the families
            # actually retrieved so the two sentences agree.
            "readiness_explanation": {
                "found": [_SOURCE_FAMILY.get(family, family)
                          for family in coverage],
            },
            "limitations": [_EC.standing_limitation(
                {c: 1 for c in coverage},
                has_filing=any(_EC.is_regulatory_filing(
                    str(d.get("final_url") or "")) for d in documents))],
            "composition_failure": {
                # Safe by construction: a class name and a short id. The
                # message stays in the log; a reader never sees exception text.
                "stage": "composition",
                "error_class": type(exc).__name__,
                "diagnostic_id": hashlib.sha256(
                    f"{run_id}:{type(exc).__name__}".encode()
                ).hexdigest()[:12],
            },
        }

    def _failure_stage(self, run_id) -> str:
        """How far the run got, named in pipeline terms. Durable facts only."""
        try:
            if self.ci.store.approval(run_id) is None:
                return "discovery"
            if not self._retrieved_documents(run_id):
                return "retrieval"
            return "composition"
        except Exception:                                     # noqa: BLE001
            return "unknown"

    def _availability(self, run_id) -> dict:
        """What this run currently has. READ-ONLY, and the single source every
        run route consults before deciding what it may render."""
        in_flight = self._analysis_in_flight(run_id)
        state = self.ci.store.run_state(run_id)
        documents = self._retrieved_documents(run_id)
        # `self._results.get` deliberately, NOT `_real_result`: composing here
        # would make a read a write again, which is the defect this exists for.
        result = self._results.get(run_id) or {}
        report = bool(result.get("strategic_report"))
        settled = (not in_flight) and state in self.TERMINAL_STATES

        if in_flight or (state not in self.TERMINAL_STATES and state):
            level = self.AVAIL_IN_PROGRESS
        elif report:
            level = self.AVAIL_FULL
        elif documents:
            level = self.AVAIL_BOUNDED
        elif state == "FAILED":
            level = self.AVAIL_FAILURE
        else:
            level = self.AVAIL_NO_CONTENT
        return {
            "level": level,
            "in_flight": in_flight,
            "settled": settled,
            "state": state,
            "documents": len(documents),
            "has_result": bool(result),
            "has_report": report,
            # Slides need a composed report. Asking for them earlier is the
            # reader following the layer nav, not an error.
            "slides_ready": report and settled,
        }

    def wait_for_analysis(self, run_id: str, timeout: float = 30.0) -> bool:
        """Block until this run reaches a terminal state. TESTS ONLY.

        Production never waits -- that is the entire point of the change. This
        exists so a test can assert on the finished state without sleeping on
        a guess.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._analysis_lock:
                running = run_id in self._analysis_inflight
            state = self.ci.store.run_state(run_id)
            if not running and state in self.TERMINAL_STATES:
                return True
            time.sleep(0.05)
        return False

    #: One analysis at a time on a free instance. Two concurrent runs contend
    #: for the memory of a 512MB container while each holds retrieved
    #: documents, and the second finishes slower than if it had waited.
    MAX_ACTIVE_ANALYSES = 1

    #: How many may WAIT. Bounded because the queue lives in this process:
    #: an unbounded one is a memory leak with a friendly name, and work it
    #: cannot promise to run should be refused rather than accepted quietly.
    MAX_PENDING_ANALYSES = 3

    #: A run may be retried this many times. Bounded because a retry costs a
    #: full retrieval pass, and an unbounded button is how a free instance is
    #: taken down by one impatient visitor.
    MAX_ANALYSIS_ATTEMPTS = 3

    #: Only these terminal states may be retried. A COMPLETE or LIMITED run is
    #: a RESULT -- re-running it is "analyse again", a separate deliberate
    #: action, not error recovery.
    RETRYABLE_STATES = ("FAILED", "INTERRUPTED")

    def attempt_count(self, run_id: str) -> int:
        """How many executions this run has had, this process.

        NOT derived from run transitions: `_transition` is idempotent per
        (run, state), so a second attempt through DISCOVERING_SOURCES writes
        nothing and a counter built on it always reads 1. Counting in memory
        is honest about its scope -- the bound survives as long as the process
        that would run the retry, which is exactly as long as it needs to.
        """
        return self._analysis_attempts.get(run_id, 0)

    def retry_state(self, session, run_id: str) -> dict:
        """Whether retry is offered, and the reason when it is not."""
        if not self._owned(session, run_id):
            return {"allowed": False, "reason": "not yours"}
        with self._analysis_lock:
            if run_id in self._analysis_inflight:
                return {"allowed": False,
                        "reason": "This analysis is still running."}
        state = self.ci.store.run_state(run_id)
        if state not in self.RETRYABLE_STATES:
            return {"allowed": False,
                    "reason": "This run finished; there is nothing to retry."}
        attempts = self.attempt_count(run_id)
        if attempts >= self.MAX_ANALYSIS_ATTEMPTS:
            return {"allowed": False,
                    "reason": (f"This analysis has been attempted "
                               f"{attempts} times without completing. "
                               f"Starting a fresh analysis is more likely to "
                               f"help than trying again.")}
        return {"allowed": True, "attempts": attempts,
                "reason": ("Runs the evidence pass again from the sources "
                           "already found. Nothing already verified is "
                           "discarded.")}

    def _schedule_analysis(self, user_id: str, run_id: str, *,
                           allow_retry: bool = False) -> bool:
        """Queue the analysis for this OWNED run exactly once.

        Returns True when this call scheduled work. A double-click, a browser
        retry or a duplicate POST returns False and changes nothing: the run
        id is deterministic per company+user+day, so the second submission
        resolves to the same run and must not start a second execution.
        """
        with self._analysis_lock:
            if run_id in self._analysis_inflight:
                return False
            state = self.ci.store.run_state(run_id)
            retrying = allow_retry and state in self.RETRYABLE_STATES
            if not retrying and (state in self.TERMINAL_STATES
                                 or run_id in self._results):
                return False                    # already done; reuse it
            if retrying and self.attempt_count(run_id) >= \
                    self.MAX_ANALYSIS_ATTEMPTS:
                return False                    # bounded, never a loop
            active = len(self._analysis_inflight)
            if active >= (self.MAX_ACTIVE_ANALYSES
                          + self.MAX_PENDING_ANALYSES):
                # Refused, not silently dropped: a run that can never execute
                # is worse than an honest no.
                return False
            self._analysis_inflight[run_id] = time.monotonic()
            self._analysis_attempts[run_id] = \
                self._analysis_attempts.get(run_id, 0) + 1
        try:
            self._analysis_pool.submit(self._run_analysis, user_id, run_id)
        except RuntimeError:                    # pool shut down
            with self._analysis_lock:
                self._analysis_inflight.pop(run_id, None)
            return False
        return True

    def _run_analysis(self, user_id: str, run_id: str) -> None:
        """The whole pipeline, off the request thread.

        Every exception becomes a TERMINAL state. A worker that dies silently
        would leave the progress page claiming work forever, which is the
        failure this whole change exists to remove.
        """
        with self._analysis_lock:
            self._worker_starts[run_id] = self._worker_starts.get(run_id, 0) + 1
        meta = self.ci.run_meta(run_id) or {}
        domain = meta.get("domain", "")
        try:
            self.ci.discover(run_id)
            candidates = self.ci.store.candidates(run_id)
            if self.ci.store.approval(run_id) is None:
                approved = self._recommended_candidate_ids(
                    candidates, refusing_hosts=self.ci.refusing_hosts(run_id))
                rejected = [c["candidate_id"] for c in candidates
                            if c["candidate_id"] not in approved]
                self.ci.approve(run_id, user_id=user_id,
                                approved_ids=approved, rejected_ids=rejected)
                self.ci.fetch_approved(run_id)
            self._results[run_id] = self._compose(run_id)
            with self._analysis_lock:
                self._terminal_writes[run_id] = \
                    self._terminal_writes.get(run_id, 0) + 1
        except Exception as exc:  # noqa: BLE001 - a worker may not escape
            # THE CLASS ALONE COULD NOT BE ACTED ON. Every composition failure
            # on this service logged "ValueError" and nothing else, and
            # `StrategicError` subclasses ValueError — so the one line that
            # exists to explain the failure named the base class of the thing
            # that actually failed and no stage. A bounded message and the
            # stage make it a diagnosis instead of a category.
            #
            # These are structural messages ("unknown source_class 'x'"),
            # never source text, and they stay in the log: the reader gets the
            # safe diagnostic id, never this.
            _LOG.warning("analysis failed run=%s stage=%s %s: %s", run_id,
                         self._failure_stage(run_id), type(exc).__name__,
                         str(exc)[:200])
            try:
                self.ci._transition(run_id, domain, "FAILED")
                with self._analysis_lock:
                    self._terminal_writes[run_id] = \
                        self._terminal_writes.get(run_id, 0) + 1
            except Exception:  # noqa: BLE001 - already failing
                pass
            # A COMPANY WITH USABLE EVIDENCE MAY NOT BECOME NON-USEFUL JUST
            # BECAUSE SYNTHESIS FAILED. The run stays FAILED — that is the
            # truth about the composer — but the reader gets what the run did
            # establish rather than a page saying it produced nothing.
            try:
                bounded = self._bounded_result(run_id, exc)
                if bounded is not None:
                    self._results.setdefault(run_id, bounded)
            except Exception:  # noqa: BLE001 - the fallback may not fail too
                pass
        finally:
            with self._analysis_lock:
                self._analysis_inflight.pop(run_id, None)

    def _interrupted_if_stale(self, run_id: str) -> bool:
        """Mark a run INTERRUPTED when its worker vanished.

        Ephemeral free-tier instances restart mid-run. Without this the
        progress page polls a state that will never advance.
        """
        state = self.ci.store.run_state(run_id)
        if state in self.TERMINAL_STATES:
            return False
        with self._analysis_lock:
            if run_id in self._analysis_inflight:
                return False                    # genuinely running here
        last = None
        for row in self.ci.store.for_run(run_id):
            last = getattr(row, "recorded_at", None) or last
        if not last:
            return False
        import datetime as _dt
        try:
            when = _dt.datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        except ValueError:
            return False
        now = _dt.datetime.now(_dt.timezone.utc)
        if (now - when).total_seconds() < self.STALE_ATTEMPT_SECONDS:
            return False
        meta = self.ci.run_meta(run_id) or {}
        self.ci._transition(run_id, meta.get("domain", ""), "INTERRUPTED")
        return True

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
                # LOSING A RACE IS NOT A BAD REQUEST. The async worker approves,
                # fetches and composes the same run; a reader who opened the
                # page at the same moment arrived here and was shown a 400
                # built from the ingestion exception. Measured live at a183f51:
                # `/runs/{id}` answered 400 at t=0 while every other route
                # answered 200. If the work is already in hand, say so.
                if self._analysis_in_flight(run_id) \
                        or self.ci.store.approval(run_id) is not None:
                    return self._redirect(f"/runs/{run_id}/progress")
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
            "competitor": "Another registrant's filing (independent)",
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
        stamped = stamp(result,
                        app_version=version_info().get("app_version", ""))
        # THE ONLY PLACE EXTERNAL CONTEXT MAY FETCH. Analysis has just
        # finished, the reader is already waiting on this request, and a
        # market series for a company nobody has looked at before has to be
        # downloaded once by somebody. Every page render afterwards is
        # read-only, so no founder loading a brief can trigger a download.
        #
        # `self._results` is written by the CALLER, so it is primed here
        # first -- the context reads the report to find exposure phrases and
        # competitor passages, and without this it would build against an
        # empty run and cache the emptiness.
        self._results[run_id] = stamped
        self._external_cache.pop(run_id, None)
        try:
            self._external_context(run_id, allow_fetch=True)
        except Exception:  # noqa: BLE001 - context must never lose a run
            _LOG.warning("external context refresh failed for %s", run_id)
        self._publish_demo_dossier(run_id, stamped)
        return stamped

    def _publish_demo_dossier(self, run_id, result):
        """Emit this run's founder snapshot and assemble its demo dossier.

        THE REAL PATH, not a demo-only one: every composed analysis passes
        through here, so the 100-company runner gets a comparable versioned
        record for free rather than another ad hoc report (§12).

        The market side may be absent — usually is, since it publishes from a
        different process on its own schedule — and that is a stated product
        state, not a failure. `FOUNDER_AVAILABLE_MARKET_UNAVAILABLE` is a
        valid dossier.

        Every failure inside is swallowed. A read-model write that can fail an
        analysis is a worse defect than the missing record it was added to
        produce; the same judgement the consumption receipt above is built on.
        """
        try:
            from intent_engine.demo_dossier import (assemble,
                                                    read_founder_snapshot,
                                                    read_market_snapshot)
            from intent_engine.demo_dossier import transport as dt
            from intent_engine.demo_dossier.store import (DossierStore,
                                                          company_key)
            from intent_engine.external_intel import founder_demo_snapshot \
                as fds

            meta = self.ci.run_meta(run_id) or {}
            report = (result or {}).get("strategic_report")
            name = str(meta.get("company_name") or "")
            domain = str(meta.get("domain") or "")
            # IDENTITY IS SETTLED BEFORE ANYTHING IS BUILT. Both snapshots,
            # the market lookup and the store key must agree on who this
            # company is; resolving afterwards would file the dossier under
            # one identity while its contents claimed another.
            key, cohort, manifest_version = self._manifest_placement(
                company_key(name or domain or run_id), name=name,
                domain=domain)
            context = self._external_cache.get(run_id)

            # EVIDENCE INDEPENDENCE AND LEARNING, MEASURED HERE RATHER THAN
            # DESCRIBED AS UNAVAILABLE.
            #
            # The producer for both already exists; until now the dossier
            # hardcoded `INDEPENDENCE_UNAVAILABLE` and emitted no learning
            # summary at all, so a founder reading a dossier could not tell
            # nine copies of one release from nine separate accounts.
            #
            # Both are computed defensively and their FAILURE IS A STATE, not
            # a zero: `assess` raising must not turn into "no independent
            # sources", which is a claim about the company.
            from intent_engine.company_ingestion import independence as _IND
            from intent_engine.company_ingestion import (
                learning_attribution as _LA,
            )
            try:
                # THE SUBJECT IS PASSED IN, or its own filings corroborate it.
                # A company's 10-K is hosted by the SEC, so without this the
                # venue check made the subject's own annual report an
                # "independent origin" -- Cloudflare's dossier published
                # INDEPENDENTLY_CORROBORATED off two origins, one of which was
                # Cloudflare.
                #
                # RESOLVED THROUGH `subject_cik`, NOT read off `meta`. Reading
                # `meta["cik"]` directly was the first repair and it shipped
                # doing nothing: a run started from a WEBSITE carries no CIK,
                # which is the ordinary case, so the filter received an empty
                # subject and the live claim never changed. Filing discovery
                # had the fallback all along; this is the same one.
                _assessed = _IND.assess(
                    self.ci.store.retrieved(run_id),
                    subject_filers=(self.ci.subject_cik(meta),),
                    subject_domain=str(meta.get("domain") or ""),
                    subject_name=name)
            except Exception:  # noqa: BLE001 - a read model may not fail a run
                _assessed = None
            # THE SAME SUBJECT, THE SAME DOCUMENTS, ONE MORE PROJECTION.
            # Built from `independence.classify` rather than beside it, so
            # the drawer and the independence count can never disagree about
            # whether a document is the company's own.
            try:
                from intent_engine.company_ingestion import provenance as _PRV
                _provenance = _PRV.project(
                    self.ci.store.retrieved(run_id),
                    subject_filers=(self.ci.subject_cik(meta),),
                    subject_domain=str(meta.get("domain") or ""),
                    subject_name=name)
            except Exception:  # noqa: BLE001 - a read model may not fail a run
                # A projection that could not be built is UNAVAILABLE, which
                # is a fact about us. An empty record list would read as "this
                # company has no sources", which is a claim about the company.
                _provenance = None
            # No strategic report means the reasoning layer produced no
            # knowledge state, so no evidence row could have moved one. That
            # is BLOCKED, never a measured zero (§21).
            # THE EFFECTS ARE READ FROM THE LEDGER, not passed as an empty
            # literal. `effects=()` was hard-coded here and in the wave, which
            # is why learning conversion could only ever report NOT_ATTEMPTED
            # however well retrieval performed.
            from intent_engine.external_intel import effect_producer as _EP
            try:
                _effects = _EP.load_effects(self._runtime_root,
                                            company_id=key)
            except Exception:  # noqa: BLE001 - a read model may not fail a run
                _effects = []
            _learning = _LA.conversion(
                evidence_rows=(_assessed or {}).get("rows", ()),
                effects=_effects,
                independence_rows=(_assessed or {}).get("rows", ()),
                knowledge_layer_ran=isinstance(report, dict),
                blocked_reason=(
                    "" if isinstance(report, dict) else
                    "no strategic report was produced for this run, so no "
                    "knowledge state existed for evidence to change"))

            # HOW HARD THE SEARCH WORKED. Read from the run that just ran,
            # never defaulted: an absent report crosses as None and the drawer
            # reads DISCOVERY_NOT_RUN, which is the only honest reading when
            # nothing searched.
            try:
                _discovery = self.ci.discovery_report(run_id)
            except Exception:  # noqa: BLE001 - a read model may not fail a run
                _discovery = {}

            founder = read_founder_snapshot(fds.build_payload(
                run_id=run_id, company_id=key, canonical_name=name,
                domain=str(meta.get("domain") or ""), report=report,
                context=context, scope=None,
                independence=_assessed, claim_provenance=_provenance,
                discovery=_discovery, learning=_learning))

            # The market snapshot, through the CONFIGURED bridge.
            #
            # This read used `self._runtime_root` -- the founder's own
            # persistent disk. The market engine publishes under its own root,
            # so the two never met: 26 real snapshots sat on disk while every
            # dossier reported "no market snapshot has been published", which
            # is a true sentence about the wrong directory and therefore
            # raised nothing for months.
            from intent_engine.demo_dossier import bridge as _bridge
            # THE OTHER KEYS THIS COMPANY IS KNOWN BY. `key` is the manifest
            # id (`cloudflare`); the market publishes under the key derived
            # from the legal name (`cloudflare-inc`). Live, that produced
            # FOUNDER_AVAILABLE_MARKET_UNAVAILABLE for a company whose
            # snapshot was on disk. Each candidate is still identity-checked
            # against the snapshot filed under it.
            _aliases = [k for k in (company_key(name), company_key(domain))
                        if k and k != key]
            assessment = _bridge.for_company(key, aliases=_aliases)
            self._market_bridge_last = assessment.as_dict()
            market = assessment.snapshot if assessment.usable else None
            if market is None:
                from intent_engine.demo_dossier import market_unavailable
                # The bridge's own reason, which names WHICH of the four
                # states this is. "Nothing was published" and "the root is
                # not configured" and "the bytes could not be read" are
                # different repairs, and the founder surface said the same
                # sentence for all three.
                market = market_unavailable(
                    assessment.reason or
                    "No market demo snapshot has been published for this "
                    "company in this deployment. The market blocks are "
                    "unavailable; nothing about the market was measured.",
                    company_id=key)

            # The validation universe reaches the dossier BY REFERENCE: only
            # the cohort and the manifest version cross, because copying the
            # rest would make every dossier version a snapshot of the
            # manifest and the two would drift. A company absent from the
            # manifest keeps its derived key and no cohort — it simply is not
            # part of the 100, which is a legitimate state, not an unknown.
            store = DossierStore(self._runtime_root)
            previous = store.latest(key)
            # The keys this company is legitimately known by, carried
            # into the join. Without them the assembler compares the
            # two sides' ids as strings and quarantines every real
            # company as WRONG_COMPANY_EVIDENCE -- found live.
            dossier = assemble(market, founder, cohort=cohort,
                               known_as=tuple([key, *_aliases]),
                               manifest_version=manifest_version,
                               now=__import__("datetime").date.today()
                               .isoformat(), previous=previous)
            stored = store.save(dossier)
            self._demo_telemetry.snapshot_read(founder)
            self._demo_telemetry.snapshot_read(market)
            self._demo_telemetry.assembled(stored)
            self._demo_telemetry.persisted(
                created=previous is None
                or previous.content_key() != stored.content_key())
            from intent_engine.demo_dossier.diff import compare
            self._demo_telemetry.differed(compare(previous, stored).state)
        except Exception:  # noqa: BLE001 - see docstring
            _LOG.warning("demo dossier not published for %s", run_id)

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
                       # THE MARKET BRIDGE, STATED AT STARTUP. Whether this
                       # deployment can read the market engine's output is
                       # not discoverable from a dossier that correctly
                       # reports "nothing published for this company" -- that
                       # sentence is identical whether the root is wrong,
                       # unset, or genuinely empty.
                       "market_bridge": self._market_bridge_state(),
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

    def _market_bridge_state(self) -> dict:
        """The configured market bridge, assessed now rather than at boot.

        Assessed per request because the market engine writes on its own
        schedule from another process: a value cached at boot would report
        MISSING for the whole life of a web service that started before the
        first market cycle of the day.

        A failure to assess is its own state. Returning MISSING here would
        claim the market engine published nothing, which is a statement about
        the market and not about this probe.
        """
        from intent_engine.demo_dossier import bridge as _bridge
        try:
            return _bridge.assess()
        except Exception as exc:                                # noqa: BLE001
            return {"state": "MARKET_BRIDGE_UNASSESSED",
                    "reason": f"the bridge could not be assessed: {exc}"}

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
        # Report the CLIENT THIS PROCESS HOLDS, not the presence of an
        # environment variable. The two disagreed: nothing passed an analyst
        # client to the ingestion service, so the variable could be set --
        # and this endpoint say "true" -- while every single run still took
        # the limited path. A capability probe that cannot be wrong in that
        # direction is the only kind worth publishing.
        # MARKET AND MACRO WERE UNVERIFIABLE FROM OUTSIDE.
        #
        # Three cycles reported "TIINGO_API_KEY / FRED_API_KEY availability
        # unknown" because this endpoint published neither, and nothing else
        # on the service does. That turned a one-second check into a blocked
        # objective. Presence only, exactly as with the reasoning key: these
        # are booleans and the values are never read into a response.
        #
        # Unlike `strategic_reasoning`, these deliberately report the KEY and
        # not a live client, because neither the price producer nor the macro
        # adapter is constructed inside the web process -- claiming a
        # capability here would repeat the mistake the reasoning probe fixed.
        import os as _os
        return {"pdf_extraction": pdf_available,
                "browser_rendering": rendering_enabled(),
                "strategic_reasoning": self._analyst_client is not None,
                # Presence only -- the value is never read into a response.
                "reasoning_key_present": getattr(
                    self, "_analyst_key_present", False),
                "reasoning_unavailable_because": getattr(
                    self, "_analyst_error", ""),
                "market_key_present": bool(_os.environ.get("TIINGO_API_KEY")),
                "macro_key_present": bool(_os.environ.get("FRED_API_KEY"))}

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
