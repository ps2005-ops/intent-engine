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
import os
import re
from dataclasses import asdict
import contextlib
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
    render_company_entry_html, render_landing_html, render_report_preview,
    render_result_html,
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
from intent_engine.webapp import outcome as OUTCOME
from intent_engine.webapp import autocomplete as _AC
from intent_engine.webapp import failures as _failures
from intent_engine.webapp import run_recovery as _recovery
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


#: The progress page's own furniture: who is being analysed, what is being
#: assembled, and the preview note demoted to a footnote. Kept beside the
#: page it styles rather than in the shared sheet, because none of it appears
#: anywhere else and a shared rule nobody can find is how stylesheets rot.
_PROGRESS_CSS = """
<style>
.analysing{border:1px solid var(--line,#d1d5db);border-left:3px solid
var(--accent,#1d4ed8);border-radius:8px;padding:.6rem .8rem;margin:.8rem 0;
background:var(--panel,#f8fafc);font-size:.95rem}
.analysing b{font-size:1.02rem}
.analysing .idbits{color:var(--muted,#4b5563);font-size:.85rem;
margin-left:.5rem}
.stages{list-style:none;counter-reset:s;margin:1rem 0;padding:0;
display:grid;gap:.28rem;max-width:34rem}
.stages li{display:flex;justify-content:space-between;gap:1rem;
align-items:baseline;padding:.32rem .6rem;border-radius:7px;
border:1px solid transparent;font-size:.93rem}
.stages li.done{color:var(--muted,#4b5563)}
.stages li.now{border-color:var(--accent,#1d4ed8);font-weight:650;
background:var(--panel,#f8fafc)}
.stages li.wait{color:var(--muted,#4b5563);opacity:.62}
.stages .st{font-size:.68rem;text-transform:uppercase;letter-spacing:.07em;
color:var(--muted,#4b5563);white-space:nowrap}
.fineprint{font-size:.8rem;color:var(--muted,#4b5563);margin-top:1.6rem;
border-top:1px solid var(--line,#d1d5db);padding-top:.6rem;max-width:34rem}
</style>
"""

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
/* ...and a PRIMARY action is not a box either. The blanket fill above outranks
   the landing sheet's accent (both are one class + one element, and this sheet
   is injected second), so in dark every primary submit rendered #1b2230 — the
   same flat panel as a text input. Measured locally at 390px in dark: the
   first screen's dominant control and an inert field were the same colour,
   which is the whole hierarchy of that screen erased.
   Two selectors' worth of specificity, so it holds regardless of order, and it
   re-points to the same accent pair the dark palette already defines rather
   than inventing a third blue. */
:root button.primary,:root form.analyze button[type=submit]{
background:#7aa2ff;color:#0f141c;border-width:0}
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


def _language_note(inputs: dict) -> str:
    """The language-rejected documents, compactly, for the gate header."""
    rows = inputs.get("language_rejected") or []
    if not rows:
        return "-"
    return ";".join(
        f"{(r.get('url') or '').split('/')[-1][:28] or r.get('source_id')}"
        f"@m{r.get('marker_density')}/a{r.get('accent_density')}"
        f"/{r.get('chars')}c" for r in rows[:6])


_CONSTANT_SHAPED = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")


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
        # Per-request state that must not leak between concurrent
        # requests. `claim` is this browser's signed last-run claim;
        # a plain attribute on `self` would let one visitor's cookie
        # decide what another visitor is told.
        self._request = _threading.local()
        self._analysis_inflight: dict = {}   # run_id -> started monotonic
        # §21. ONE BUDGET PER ANALYSIS, created when the work is queued and
        # read by every stage that spends it. Before this, each stage was
        # separately bounded and the SUM was bounded by nothing: fourteen
        # sources x an 8s timeout x three attempts is the 4m54s a real
        # customer waited on Apple while every individual component stayed
        # inside its own limit.
        self._analysis_deadlines: dict = {}  # run_id -> Deadline
        self._analysis_gaps: dict = {}       # run_id -> spent budget + gaps
        # §40. When the CORE became readable, which is the number the
        # interactive SLO is written against -- distinct from when the whole
        # analysis finished, which is what every previous measurement recorded.
        self._core_ready_at: dict = {}       # run_id -> monotonic
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
        _began = time.monotonic()
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
        # THE OUTCOME IS STATED, NOT INFERRED FROM PROSE.
        #
        # Meta Platforms rendered "Analysis could not be completed" on two
        # deployed builds and was scored a PASS, because the acceptance
        # instrument searched for the literal string "Limited analysis" and
        # that page says something else. Every surface, and every instrument,
        # was separately guessing a customer outcome from the words on a page.
        #
        # So the run's outcome travels with the response. A harness reads a
        # named state; it no longer has to know every sentence the product can
        # write. `_route` already ran, so this costs one read of state the
        # request just used.
        run_id = self._run_id_of(environ.get("PATH_INFO", ""))
        if run_id:
            try:
                stated = self.analysis_outcome(run_id)
                # A PAGE THAT FAILED MAY NOT REPORT THE RUN'S HAPPY OUTCOME.
                #
                # MEASURED on 743df06: Pfizer's `/runs/<id>` returned HTTP 500
                # -- "Something went wrong on our side", 513 characters --
                # while carrying `X-Analysis-Outcome: FULL_ANALYSIS`, because
                # this header was attached after the error page was built and
                # never looked at the status it was travelling on. Every other
                # route rendered (full=21,718 chars), so the ANALYSIS was
                # fine; the customer's landing screen was not, and the header
                # said otherwise to anything reading it.
                #
                # The run's own outcome is unchanged and still readable
                # elsewhere. What this states is what happened to THIS
                # response, which is what a header on this response means.
                if status[:1] == "5":
                    stated = OUTCOME.ANALYSIS_FAILED
                headers = headers + [("X-Analysis-Outcome", stated),
                                     ("X-Evidence-Gate",
                                      self.evidence_gate_summary(run_id))]
                timing = self.request_timing(
                    (time.monotonic() - _began) * 1000.0)
                if timing:
                    headers = headers + [("X-Request-Timing", timing)]
            except Exception:                               # noqa: BLE001
                # Reporting an outcome must never be able to break the page
                # whose outcome it reports.
                _LOG.exception("outcome header failed for %s", run_id)
        payload = body.encode()
        headers.append(("Content-Length", str(len(payload))))
        start_response(status, headers)
        return [payload]

    def _route(self, environ):
        # CLEARED FIRST, POPULATED LATER. Worker threads are reused, so a
        # claim left behind by the previous request is the previous BROWSER's
        # claim. Two routes below return before the cookie is read (the
        # untrusted-host refusal and the machine dossier route), and neither
        # reads it today.
        #
        # DEFENCE IN DEPTH, AND SAID SO PLAINLY. Deleting this line is a
        # mutation that runs GREEN, because every path that reads the claim
        # assigns it a few lines further down; it is not a guard and is not
        # counted as one in `break_proofs_run_durability.py`. It exists so
        # that a future early return which reads the claim inherits None
        # rather than another visitor's.
        self._request.claim = None
        # ONE READINESS READ PER REQUEST, NOT THREE.
        #
        # `_progress` asks `result_readiness` up to three times, and each
        # answer costs several reads of the ingestion log -- the same log the
        # running analysis is appending to, so nothing upstream can cache it
        # for us. `result_readiness` is documented READ-ONLY and composes,
        # approves and fetches nothing, so two calls inside one request can
        # only differ by a race the page has no way to act on.
        #
        # Per-REQUEST and on the thread-local, never on `self`: a memo shared
        # between requests would show one visitor a state belonging to
        # another, which is the defect the line above exists to prevent.
        self._request.readiness = {}
        self._request.spans = []
        self._request.reads = {}
        # THE ECONOMIC CONTEXT MEMO, CLEARED FOR THE SAME REASON THE OTHERS
        # ARE. Worker threads are reused; a memo left behind is the previous
        # visitor's company, and this one carries their run's economic
        # exposures and decision delta.
        self._request.econ = {}
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

        # THE CLAIM THIS BROWSER CARRIES ABOUT ITS OWN LAST RUN.
        #
        # Read once, here, and kept on a thread-local rather than on `self` or
        # on the shared session dict: two requests can be in flight at the
        # same time and they do not necessarily come from the same browser.
        # It is only ever consulted AFTER an ownership check has already
        # failed (`_no_such_run`), so it can widen what a reader is TOLD about
        # a run that is already gone and can never widen access to one that
        # still exists. See `webapp.run_recovery`.
        self._request.claim = _recovery.verify(
            self.config.secret, self._cookie(environ, _recovery.COOKIE_NAME))

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
            from intent_engine.webapp import storage_state as _ss
            # THE COMMIT AND THE PROCESS, in one cheap call. `/readyz` folds
            # every append-only store to answer, so it is the wrong place to
            # poll while an analysis is running; this route touches nothing.
            # A caller that sees `process.boot_id` change has watched a
            # restart, which is the difference between "the product lost my
            # run" and "the instance was replaced under me".
            return self._ok_json(dict(version_info(),
                                      process=_ss.process_identity()))
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
        # THE SUGGESTION ENDPOINT. Public registries only (§82) — it reaches
        # the curated entity registry, the validation manifest and the SEC's
        # public ticker table, and nothing that holds tenant state. Session-
        # free by design: a visitor typing a company name has not logged in
        # yet, and requiring a session to spell a company would put the login
        # wall back in front of the first useful thing the product does.
        if path == "/api/companies" and method == "GET":
            return self._company_suggestions(environ)
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
        # TRY THE DEMO -> THE COMPANY QUESTION. This used to mint a session and
        # send the visitor back to "/", which was the form; now that "/" is the
        # pitch, returning there would loop them past the button they just
        # pressed.
        if (path == "/demo" and method == "POST"
                and self.config.demo_mode):
            new_sid = self.auth.create_anonymous_session()
            return self._redirect("/demo", set_sid=new_sid)
        if path == "/demo" and method == "GET":
            # A visitor may arrive here directly (a shared link, a back
            # button, a bookmark). Mint the guest session rather than
            # bouncing them to a page whose only button lands right back
            # here.
            if session is None and self.config.demo_mode:
                new_sid = self.auth.create_anonymous_session()
                return self._redirect("/demo", set_sid=new_sid)
            if session is None:
                return self._redirect("/login")
            return self._demo_entry(session)
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
        if route == ("GET", "runs", 3) and parts[2] == "timing":
            return self._timing_json(session, parts[1])
        if route == ("GET", "runs", 3) and parts[2] == "progress.json":
            return self._progress_json(session, parts[1])
        if route == ("GET", "runs", 3) and parts[2] == "progress":
            return self._progress(session, parts[1])
        if route == ("GET", "runs", 3) and parts[2] == "report":
            return self._report(session, parts[1])
        # THE SIX-STEP STORY (§17). `founder_brief.flow` owns the order;
        # these three routes are the steps the product did not have.
        if route == ("GET", "runs", 3) and parts[2] == "intro":
            return self._with_ask(session, parts[1],
                                  self._intro_page(session, parts[1]))
        # THE SCROLLABLE DECISION NARRATIVE. It was the default route until
        # step 1 took that place, and a designed 900-word surface with no
        # route into it is exactly the defect the verdict register exists to
        # catch. It is now a secondary surface, reached from the step that
        # raises the question it answers.
        if route == ("GET", "runs", 3) and parts[2] == "answer":
            return self._with_ask(session, parts[1],
                                  self._answer_page(session, parts[1]))
        if route == ("GET", "runs", 3) and parts[2] == "history":
            return self._history_page(session, parts[1])
        if route == ("GET", "runs", 3) and parts[2] == "connect":
            return self._connect_page(session, parts[1])
        if route == ("GET", "runs", 3) and parts[2] == "story":
            return self._with_ask(session, parts[1],
                                  self._story_page(session, parts[1]))
        if route == ("GET", "runs", 3) and parts[2] == "dashboard":
            return self._with_ask(session, parts[1],
                                  self._intelligence_page(session, parts[1]))
        if route == ("GET", "runs", 3) and parts[2] == "brief":
            return self._with_ask(
                session, parts[1],
                self._executive_brief_page(session, parts[1]))
        if route == ("GET", "runs", 3) and parts[2] == "xray":
            return self._with_ask(session, parts[1],
                                  self._run_xray(session, parts[1]))
        if route == ("GET", "runs", 3) and parts[2] == "evidence":
            return self._with_ask(session, parts[1],
                                  self._run_evidence(session, parts[1]))
        if route == ("GET", "runs", 3) and parts[2] == "slides":
            return self._with_ask(session, parts[1],
                                  self._slides_page(session, parts[1]))
        if route == ("GET", "runs", 3) and parts[2] == "full":
            return self._with_ask(
                session, parts[1],
                self._run_page(session, parts[1], layer="full"))
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
        # D29. `/status.json` and `/feedback` were left out of this list.
        #
        # Measured live on 2cce6d9 as an anonymous demo guest: /dashboard,
        # /learning and /assistant all answered 404, and /status.json answered
        # 200 with the deployed commit, the market engine's portfolio value
        # and paper P&L, prediction counts and scheduler job state. The
        # comment below describes exactly this defect being closed for the
        # console; the JSON behind the console kept serving it.
        #
        # The gate is a list, so the fix is to the list -- guarding
        # /status.json alone would leave /feedback, which exports the same
        # operator material one route over.
        # SCOPED TO WHAT WAS PROVEN. The first version added /feedback and
        # /feedback.jsonl too, on the reasoning that they export the same
        # operator material. They do -- but the operator sessions that read
        # them are themselves anonymous-flagged in this build, so the wider
        # gate 404'd legitimate operator access and turned an information
        # leak into a lockout. /feedback's exposure is recorded as unverified
        # rather than guessed at; /status.json is what was measured leaking.
        # `hosted` joins the list from the market lineage: the hosted-runtime
        # console is the same class of surface as /dashboard.
        if parts and parts[0] in ("learning", "dashboard", "assistant",
                                  "status.json", "hosted"):
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
        if route == ("GET", "hosted", 1):
            return self._hosted_dashboard(session)
        if path == "/hosted.json" and method == "GET":
            return self._ok_json(self._hosted_data())
        if path in ("/feedback", "/feedback.jsonl") and method == "GET":
            if session is None:
                return self._redirect("/login")
            return self._operator_feedback(session, export=path.endswith(
                ".jsonl"))
        if path == "/status.json" and method == "GET":
            if session is None:
                return self._redirect("/login")
            return self._ok_json(self._platform_status())
        if route == ("GET", "runs", 3) and parts[2] == "provenance.json":
            if session is None:
                return self._redirect("/login")
            return self._ok_json(self._run_provenance(parts[1]))
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
        # A REPEATED FIELD IS A LIST, AND TWO FIELDS ARE REPEATED.
        #
        # `cand` (source approval) and `tag` (feedback) both post one value
        # per checked box. Taking `v[0]` kept the first and silently dropped
        # every other selection, so a reader who ticked four feedback tags had
        # three of them discarded with no error anywhere.
        multi = ("cand", "tag")
        return {k: (",".join(v) if k in multi else v[0])
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
        # RESERVED, NOT SPENT. §4: quota is committed only once a run has
        # actually been accepted and scheduled.
        #
        # MEASURED on the deployed preview, six times: /analyze answered 500
        # in under a second and each one still consumed one of the visitor's
        # ten analyses for the hour, because the hit was recorded here and
        # the failure happened afterwards. A visitor could spend their whole
        # hour on requests that produced nothing and were never explained.
        ip_hits.append(now)
        session_hits.append(now)
        self._demo_ip_hits[remote] = ip_hits
        session["analyses"] = session_hits
        return None

    def _release_demo_quota(self, session, remote, stamp) -> None:
        """Give back a reservation for a run that never started. §4.

        Idempotent by construction: it removes ONE occurrence of the exact
        timestamp it was given, so a double release cannot refund twice and
        a concurrent request's reservation is untouched.
        """
        if stamp is None or not session.get("anonymous"):
            return
        hits = self._demo_ip_hits.get(remote)
        if hits and stamp in hits:
            hits.remove(stamp)
            self._demo_ip_hits[remote] = hits
        analyses = list(session.get("analyses") or [])
        if stamp in analyses:
            analyses.remove(stamp)
            session["analyses"] = analyses

    def _demo_quota_reservation(self, session, remote):
        """The timestamp `_demo_rate_limited` just reserved, or None."""
        if not session.get("anonymous"):
            return None
        hits = self._demo_ip_hits.get(remote) or []
        return hits[-1] if hits else None

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

    def _timing_json(self, session, run_id):
        """CANONICAL measurement, so the harness stops inferring from prose.

        Every previous number came from watching the rendered product:
        CORE_READY was "the progress page stopped redirecting" and the
        evidence count was a regex for `https?://` over the HTML -- which
        could never match, because this product cites evidence through
        internal routes. Six identical zeros across six companies were the
        tell. A benchmark that reads the UI measures the UI.

        Each value therefore states WHERE IT CAME FROM. A metric that cannot
        name its source cannot be trusted at the point it decides a release.
        """
        if not self._owned(session, run_id) or not self._is_real_run(run_id):
            return self._no_such_run(session, run_id)
        marks = self.ci.lifecycle(run_id)
        import datetime as _dtm

        def _at(key):
            raw = marks.get(key)
            if not raw:
                return None
            try:
                return _dtm.datetime.fromisoformat(
                    raw.replace("Z", "+00:00"))
            except ValueError:
                return None

        def _delta(a, b):
            x, y = _at(a), _at(b)
            return round((y - x).total_seconds(), 2) if x and y else None

        documents = list(self.ci.store.retrieved(run_id))
        report = (self._results.get(run_id) or {}).get("strategic_report") or {}
        return self._ok_json({
            "run_id": run_id,
            "markers": marks,
            "core_latency_s": _delta("accepted", "core_ready"),
            "deep_latency_s": _delta("accepted", "deep_ready"),
            "evidence_count": len(documents),
            "deep_status": report.get("deep_status"),
            "result_state": report.get("result_state"),
            "run_state": self.ci.store.run_state(run_id),
            "trace": self.ci.trace(run_id),
            "provenance": {
                "markers": "persisted_lifecycle_event:ci.lifecycle_marked",
                "core_latency_s": "persisted_lifecycle_event",
                "deep_latency_s": "persisted_lifecycle_event",
                "evidence_count": "canonical_retrieved_documents",
                "deep_status": "composed_report_object",
                "result_state": "composed_report_object",
                "run_state": "persisted_run_transitions",
                "trace": "persisted_spans:ci.trace_recorded",
            },
        })

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

    # --- hosted runtime dashboard: read-only view over the durable DB -------
    # Behind the same operations-console gate as /learning and /dashboard: a
    # logged-in account only, never a guest demo session. It is plumbing, and a
    # visitor evaluating the product should not be looking at it.
    def _durable_store(self):
        """A FRESH durable store per request — so the view recovers cleanly
        after a free web service has slept. Reads DATABASE_URL from env."""
        from intent_engine.storage.durable import DurableStore
        return DurableStore()

    def _hosted_data(self) -> dict:
        import datetime

        from intent_engine.hosted.budget import Budget
        from intent_engine.hosted.dashboard import assemble
        store = self._durable_store()
        try:
            return assemble(store, budget=Budget.from_env(),
                            as_of=datetime.date.today().isoformat())
        finally:
            store.close()

    def _hosted_dashboard(self, session):
        from intent_engine.hosted.dashboard import render_html
        frag = render_html(self._hosted_data())
        body = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<title>Hosted runtime — paper trading (simulated)</title>'
                '<meta name="viewport" content="width=device-width,'
                ' initial-scale=1"></head><body>'
                f'{self._nav(session, session["csrf"] if session else "")}'
                f'<main>{frag}</main></body></html>')
        return self._html(self._stylize(body))

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

    def _with_run_claim(self, response, session, run_id, company=""):
        """Attach this session's signed claim on `run_id` to any response.

        Minted the moment a run is opened, because that is the only moment
        the company name, the run id and the owner are all in hand -- and the
        instance that knows them may not exist by the time the reader comes
        back. Nothing is attached for a session-less request; there would be
        no owner to bind the claim to.
        """
        if session is None or not session.get("user_id") or not run_id:
            return response
        status, headers, body = response
        token = _recovery.mint(self.config.secret,
                               user_id=session["user_id"], run_id=run_id,
                               company=company)
        return status, list(headers) + [
            ("Set-Cookie", _recovery.cookie_header(
                token, secure=self.config.cookie_secure))], body

    def _error_page(self, code, message, *, category=None):
        """A reader-facing failure. Never a status line and an exception.

        `category` is for a call site that KNOWS the cause rather than one
        catching an exception. Classifying by substring is right for the
        latter and wrong for the former: the admission refusal below says "NO
        ANALYSIS CREDIT WAS USED", and the bare needle "credit" read that as
        the credit balance being exhausted -- so a run that never started
        told the reader its evidence had been retrieved.

        Measured live: `GET /runs/{id}` on a run that had not yet been
        approved answered "Bad request / approve at least one source" — a
        framework status and an internal message, which tells a reader they
        did something wrong when the run had simply not reached its next step.

        The category decides what is said; `message` never reaches the page.
        It is hashed into a short reference an operator can correlate.
        """
        category = category or _failures.classify(message)
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

    def _run_claim(self, session, run_id):
        """This browser's signed proof that it started `run_id`, or None.

        Only ever meaningful once ownership has already failed. See
        `webapp.run_recovery` for why the proof is carried by the browser
        rather than looked up: the lookup is exactly what a restart destroys.
        """
        if session is None:
            return None
        claim = getattr(self._request, "claim", None)
        if _recovery.proves(claim, user_id=session.get("user_id") or "",
                            run_id=run_id):
            return claim
        return None

    def _missing_run_state(self, session, run_id):
        """Which of the missing-run states this is. Never "unavailable".

        The failure this replaces answered `RUN_NOT_FOUND` to three different
        situations -- a restart, a typo, and another person's run id -- and so
        told a guest whose analysis had just been destroyed the same thing it
        tells a stranger probing ids. They are not the same event and they do
        not have the same next step.
        """
        owner = self.web_store.owner_of(run_id)
        if owner is not None:
            if session is not None and owner == session.get("user_id"):
                return _recovery.RUN_READY          # owned; refused elsewhere
            return _recovery.RUN_NOT_OWNED
        if self._run_claim(session, run_id) is not None:
            return _recovery.RUN_RESTART_LOST
        return _recovery.RUN_NOT_FOUND

    def _no_such_run(self, session, run_id):
        """The response for a run this session cannot open.

        EVERY ANALYSIS TERMINATES VISIBLY. A run that the service no longer
        holds is a terminal state of the customer's journey, so it gets a
        page that names what happened and offers the one action that can
        still work -- running the same company again -- instead of a 404 that
        reads as "you are lost".

        Isolation is unchanged. `RUN_NOT_OWNED` and `RUN_NOT_FOUND` both get
        exactly the refusal they got before; only the case where THIS session
        can prove it started THIS run is treated differently, and by then the
        run is gone from the service either way.
        """
        state = self._missing_run_state(session, run_id)
        if state != _recovery.RUN_RESTART_LOST:
            return self._error_page(404, "no such run for this account")
        claim = self._run_claim(session, run_id) or {}
        return self._lost_run_page(session, claim.get("co") or "")

    def _lost_run_page(self, session, company):
        """The terminal recovery screen. One explanation, two ways forward."""
        explained = _failures.explain(_failures.RUN_RESTART_LOST)
        csrf = session["csrf"] if session else ""
        named = _e(company) if company else "that company"
        # RETRY IS A REAL RE-RUN, not a link back to an empty form. The
        # company name travelled on the signed claim, so the reader does not
        # retype it and cannot be silently switched to a different company.
        retry = (f'<form action="/analyze" method="post">'
                 f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
                 f'<input type="hidden" name="consent" value="on">'
                 f'<input type="hidden" name="company_name" '
                 f'value="{_e(company)}">'
                 f'<button type="submit" class="cta">Analyse {named} again'
                 f'</button></form>') if company else ''
        body = (
            f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,'
            f'initial-scale=1">'
            f'<title>{_e(explained["title"])}</title></head><body>'
            f'{self._nav(session, csrf)}'
            f'<main class="brief"><h1>{_e(explained["title"])}</h1>'
            f'<p><strong>What did work.</strong> '
            f'{_e(explained["what_worked"])}</p>'
            f'<p><strong>What did not.</strong> '
            f'{_e(explained["what_failed"])}</p>'
            f'<p><strong>Why.</strong> {_e(explained["why"])} '
            f'Nothing was invented.</p>'
            f'<p><strong>What to do.</strong> {_e(explained["next_step"])}</p>'
            f'{retry}'
            f'<p><a href="/demo">Analyse a different company</a></p>'
            f'</main></body></html>')
        return "200 OK", [("Content-Type", "text/html; charset=utf-8")], \
            self._stylize(body)

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
    def _company_suggestions(self, environ):
        """Companies matching what the customer has typed. Never raises.

        The SEC ticker table behind the third source is one ~1MB fetch per
        process; every later keystroke is served from memory. Under test the
        outbound call is off, and the two curated sources still answer — so
        the feature degrades to the hundred companies the suite knows about
        rather than to an error.
        """
        from urllib.parse import parse_qs

        from intent_engine.company_ingestion import suggest as CS
        query = parse_qs(environ.get("QUERY_STRING", "")).get("q", [""])[0]
        try:
            rows = CS.suggest(query[:120], limit=8,
                              allow_registrant=(self.config.env
                                                != "test"),
                              transport=self._transport,
                              resolver=self._resolver)
        except Exception:                                   # noqa: BLE001
            _LOG.warning("company suggestions failed")
            rows = ()
        return self._ok_json({"contract": CS.CONTRACT,
                              "query": query[:120],
                              "companies": [r.as_dict() for r in rows]})

    def _landing(self, session):
        """The first screen: what this is, log in, try the demo. Nothing else.

        The company form now lives at /demo. A visitor who already has a
        session is NOT shortcut past this page — the landing sells the
        product, and skipping it for returning guests would mean the one
        screen written to explain the product is the one screen most people
        never see.
        """
        csrf = session["csrf"] if session else ""
        return self._html(_chrome(
            render_landing_html(demo_mode=bool(self.config.demo_mode)),
            self._nav(session, csrf)))

    def _demo_entry(self, session):
        """Company entry — the demo's first working screen."""
        page = _AC.inject(render_company_entry_html())
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
                # THE EXPECTATION BEFORE THE COMMITMENT, not only after it.
                #
                # A reader who is told nothing decides for themselves at
                # about forty seconds that the thing has hung. The same wait
                # is unremarkable once the range has been stated. It sits
                # here, immediately under the button, because that is the
                # last thing read before the wait starts -- and it is the
                # same constant the progress page renders, so the promise
                # made here and the promise shown there cannot drift.
                intro = (
                    f'<p class="eta">{_e(self.ETA_COPY)}</p>'
                    f'<p class="try-line">Not sure where to start? '
                    f'Try {examples}.</p>{forms}')
                # After the form, not before the headline. Injected at
                # '<main>' it rendered above the h1, so the first thing a
                # visitor read was a footnote about examples.
                page = page.replace('</form>', '</form>' + intro, 1)
        else:
            # No session and demo mode is off: this screen cannot do its job,
            # so say what is needed rather than rendering a form that will be
            # refused on submit.
            note = ('<p><strong>Early access:</strong> '
                    '<a href="/login">log in</a> to run an analysis.</p>')
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
        # The reservation this request holds, so any path that fails to open
        # or schedule a run can hand it back (§4).
        _reserved = None if smoke else self._demo_quota_reservation(session,
                                                                    remote)
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
        # A CONFIRMED PICK IS AN ANSWER, NOT A HINT.
        #
        # The customer chose one row out of a list that showed its legal name,
        # ticker, country and domain. Re-resolving that name from scratch can
        # only do one of two things: agree, or disagree with the customer
        # about which company they meant — and the second is the wrong-company
        # failure arriving through the one door where the user had already
        # been explicit. So a confirmed pick sets identity directly.
        #
        # The confirmation is checked against the typed name rather than
        # trusted blind: the hidden fields are client-supplied, and a form
        # replayed with a mismatched pair must fall through to ordinary
        # server-side resolution rather than analyse whatever was posted.
        confirmed = (form.get("suggest_confirmed") or "").strip()
        if confirmed and confirmed == company_name:
            picked_domain = (form.get("suggest_domain") or "").strip()
            picked_cik = "".join(ch for ch in
                                 (form.get("suggest_cik") or "")
                                 if ch.isdigit())
            if picked_domain and "://" not in picked_domain:
                picked_domain = f"https://{picked_domain}"
            if picked_domain:
                website = website or picked_domain
            if picked_cik:
                # A CONFIRMED PICK CARRIES BOTH, AND THIS USED TO BE AN ELIF.
                #
                # MEASURED LIVE across three deploys. JPMorgan has a domain
                # AND a CIK, so `picked_domain` won and `filer_cik` stayed
                # empty — the run opened with cik="", `run_meta` carried no
                # CIK, and every downstream owner-of-this-document test had
                # nothing to compare against. That is why the claim-ownership
                # repair read green in tests, PASSED a real-EDGAR probe that
                # was handed the CIK directly, and did not move the page:
                # the producer was correct and was being asked "is this
                # document filed under ''?".
                #
                # The comment above about never filling this in from
                # elsewhere is about GUESSING — a CIK inferred from a name
                # attributes one company's filings to another. This is not a
                # guess. The customer picked a row showing the legal name,
                # ticker, country and domain, and the pick was already
                # validated against the typed name a few lines up. A
                # confirmed pick is an answer, as the block above says.
                filer_cik = picked_cik
        if company_name and not website and not filer_cik \
                and not form.get("entity_id"):
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
                self._release_demo_quota(session, remote, _reserved)
                return self._error_page(400, str(exc))
            except Exception:                               # noqa: BLE001
                # OPENING A RUN CAN FAIL FOR REASONS THAT ARE NOT THE INPUT.
                #
                # MEASURED on the deployed preview, six times at concurrency
                # 1 with one orchestrator: /analyze answered HTTP 500 in
                # under a second for six different companies, each with a
                # confirmed CIK, and the visitor got the generic "Something
                # went wrong on our side" page. Only these two exception
                # types were caught, so anything the store raised -- and the
                # runtime root here is EPHEMERAL, which is a documented
                # blocker -- became an unhandled 500.
                #
                # THE QUOTA IS ALREADY SPENT AT THIS POINT: the rate limiter
                # records the hit before this line, so each of those 500s
                # consumed one of the visitor's ten analyses for the hour and
                # told them nothing. That is the part that makes this worth
                # catching rather than letting the generic handler take it.
                _LOG.exception("create_run failed company=%r cik=%r",
                               company_name, filer_cik)
                self._release_demo_quota(session, remote, _reserved)
                return self._error_page(
                    503, "We could not start this analysis right now. This "
                         "is a fault on our side, not in what you entered. "
                         "Nothing was fetched and NO ANALYSIS CREDIT WAS "
                         "USED — try again in a moment.")
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
                    # A REFUSED SCHEDULE MUST NOT LOOK LIKE A STARTED ONE.
                    #
                    # `_schedule_analysis` returns False when the pool is
                    # saturated or the run is already terminal, and its
                    # docstring says "refused, not silently dropped: a run
                    # that can never execute is worse than an honest no".
                    # The return value was discarded here, so a refusal
                    # redirected the visitor to a progress page for work
                    # nobody had queued -- which is the silent drop the
                    # producer went out of its way to avoid.
                    #
                    # A run that is already finished still redirects: that is
                    # the double-click case and its result exists.
                    started = self._schedule_analysis(session["user_id"],
                                                      run_id)
                    if not started and not (
                            run_id in self._results
                            or self.ci.store.run_state(run_id)
                            in self.TERMINAL_STATES):
                        self._release_demo_quota(session, remote,
                                                 _reserved)
                        # THE CATEGORY IS DECIDED HERE, not inferred from
                        # the words. This branch knows exactly what happened:
                        # admission was refused, no run exists, nothing ran.
                        return self._error_page(
                            503, "This preview is already running as many "
                                 "analyses as it can at once. Nothing was "
                                 "fetched and NO ANALYSIS CREDIT WAS USED — "
                                 "try again in a few minutes.",
                            category=_failures.ADMISSION_REFUSED)
                    return self._with_run_claim(
                        self._redirect(f"/runs/{run_id}/progress"),
                        session, run_id, company_name)
                self.ci.discover(run_id)
                return self._with_run_claim(self._autorun(session, run_id),
                                            session, run_id, company_name)
            self.ci.discover(run_id)
            return self._with_run_claim(
                self._redirect(f"/runs/{run_id}/sources"),
                session, run_id, company_name)
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
        return self._with_run_claim(
            self._redirect(f"/runs/{run_id}/progress"), session, run_id,
            DEMO_COMPANY_NAME)

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

    @contextlib.contextmanager
    def _segment(self, name):
        """Time one named span of a request and keep it on the thread-local.

        WHY A TIMER AND NOT ANOTHER HYPOTHESIS. `/runs/<id>/progress` stops
        answering for 100+ consecutive seconds during analysis while
        `/version` answers in 0.15s, and the leading explanation -- the
        append-only store re-parsing on every read -- was FALSIFIED by
        removing it: the cost went 153ms -> 1ms per poll and the stall did
        not move. Guessing a second mechanism costs another deploy and
        another hour of quota, so the handler measures itself instead.

        Never customer-visible: the numbers travel on a response header, like
        `X-Evidence-Gate`, and nothing renders them.
        """
        start = time.monotonic()
        try:
            yield
        finally:
            spans = getattr(self._request, "spans", None)
            if spans is not None:
                spans.append((name, (time.monotonic() - start) * 1000.0))

    def request_timing(self, wall_ms: float = 0.0) -> str:
        """The spans this request recorded, longest first.

        `wall` is the whole request and `named` is what the spans account
        for. THE GAP IS THE POINT: a stall that is not inside any measured
        segment is not in this handler at all, and that is a different
        repair from a slow segment.
        """
        spans = getattr(self._request, "spans", None) or []
        if not spans and not wall_ms:
            return ""
        named = sum(ms for _, ms in spans)
        parts = " ".join(f"{n}={ms:.0f}"
                         for n, ms in sorted(spans, key=lambda s: -s[1])[:9])
        return (f"wall={wall_ms:.0f} named={named:.0f} "
                f"unaccounted={max(0.0, wall_ms - named):.0f} {parts}").strip()

    def _progress(self, session, run_id):
        with self._segment("owned"):
            owned = self._owned(session, run_id)
        if not owned:
            return self._no_such_run(session, run_id)
        with self._segment("is_real_run"):
            real = self._is_real_run(run_id)
        if real:
            with self._segment("run_state"):
                status = self.ci.store.run_state(run_id) \
                    or "VALIDATING_COMPANY"
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
        # A RESULT THAT EXISTS BEATS A STATE THAT SAYS OTHERWISE.
        #
        # This branch used to read `status in ("COMPLETE", "PARTIAL")`, which
        # is the worker's opinion about its own run rather than an answer to
        # the only question this page exists to ask. A run can compose a
        # readable result and still transition FAILED — `_run_analysis` does
        # exactly that on purpose, storing a bounded reading in `_results`
        # after marking the run FAILED — and every such customer was told
        # there was nothing to open while the analysis sat one route away.
        #
        # Measured live on eb18371 with "Meta": five sources retrieved, a
        # readable result present, and this page saying "no result to open".
        if real:
            with self._segment("readiness"):
                readiness = self.result_readiness(run_id)
            if readiness["opens_result"]:
                return self._redirect(f"/runs/{run_id}")

        # A worker that vanished must not leave this page polling forever.
        with self._segment("interrupted_if_stale"):
            stale = not terminal and self._interrupted_if_stale(run_id)
        if stale:
            status = self.ci.store.run_state(run_id) or status
            terminal = True
            # The worker dying does not destroy what it had already written.
            # Re-ask: a stale marker plus a readable result is a redirect,
            # not a dead end.
            if real:
                readiness = self.result_readiness(run_id)
                if readiness["opens_result"]:
                    return self._redirect(f"/runs/{run_id}")

        if status in ("COMPLETE", "PARTIAL"):
            return self._redirect(f"/runs/{run_id}")
        # NO FULL-PAGE RELOAD. This was
        #     <meta http-equiv="refresh" content="4">
        # which reloaded the whole document every 4 seconds: the server
        # re-rendered ~17KB of HTML each time and the browser threw away the
        # page and rebuilt it. Measured on the preview, that is ~15 full
        # renders a minute, on an instance the analysis is already starved
        # for -- so the poller was competing with the worker it was waiting
        # on, and the reader saw flicker, scroll reset and focus loss. That
        # is the whole of the "laggy" complaint; the analysis was not what
        # felt slow.
        #
        # The replacement fetches a small JSON document and patches the three
        # things that change. The meta refresh survives inside <noscript>, so
        # a client without scripting keeps exactly the old behaviour rather
        # than being stranded on a page that never updates.
        refresh = ('' if terminal else
                   f'<noscript><meta http-equiv="refresh" content="4">'
                   f'</noscript>')
        # A run that failed must say so in the heading. Softening every state
        # into "Reading the public evidence…" would hide a failure behind a
        # progress message, which is worse than the jargon it replaced.
        # A run that is still recoverable may not be mourned. `status` alone
        # said FAILED for runs that had another attempt available and for runs
        # that had a result; the heading now follows readiness, which knows
        # the difference.
        with self._segment("readiness_retryable"):
            recoverable = bool(
                real and self.result_readiness(run_id)["retryable"])
        heading = {
            "FAILED": "This analysis could not be completed",
            # Say what happened. "Reading the public evidence..." on a run
            # whose worker died is a progress message covering for a stop.
            "INTERRUPTED": "This analysis was interrupted",
            "REJECTED": "This analysis was not accepted",
        }.get(status, "Reading the public evidence…")
        if recoverable:
            heading = "This analysis stopped early"
        head = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
                f'{refresh}<title>{_e(heading)}</title>{_PROGRESS_CSS}</head>'
                f'<body>'
                f'{self._nav(session, session["csrf"])}<main>'
                f'<h1>{_e(heading)}</h1>')
        if recoverable:
            # BOUNDED RECOVERY, NOT A DEAD END. One clear action, offered once
            # — `result_readiness` has already checked an attempt remains, so
            # this can never become a loop.
            tail = (f'<p>We stopped before there was anything worth showing '
                    f'you. {self._failure_explanation(run_id, real)}</p>'
                    f'{self._targeted_retry_action(session, run_id)}'
                    f'<p><a href="/demo">Analyse a different company</a></p>')
        elif status in ("FAILED", "INTERRUPTED", "REJECTED"):
            # Honest terminal failure: NO "Open the result" — there is no
            # result. Explain why and offer a safe start-over.
            tail = (f'<p>This analysis could not be completed, so there is no '
                    f'result to open. {self._failure_explanation(run_id, real)}'
                    f'</p><p><a href="/runs/{_e(run_id)}">See the failure '
                    f'details</a> · <a href="/demo">Start a new analysis</a>'
                    f'</p>')
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
            # THIS PAGE CARRIES THE CUSTOMER; IT DOES NOT PARK THEM.
            #
            # The old copy led with "You can safely leave this page — it will
            # be waiting under your analyses", which is true and is advice for
            # the wrong journey: it told a first-time visitor that the normal
            # way to reach their result was to navigate somewhere else and
            # find it. The page already redirects into step 1 the moment the
            # run is readable, so what it should say is that.
            #
            # The preview's in-memory storage is still disclosed, because it
            # is a real limit a tester can hit. It is a footnote now rather
            # than a boxed warning above the fold — infrastructure limits are
            # not what a demo is about.
            # THE POLLER, AND THE ONLY THING ON THIS PAGE THAT RUNS JS.
            #
            # It fetches `progress.json` -- a few hundred bytes -- patches the
            # step line, the ladder and the elapsed line, and navigates ONCE
            # when the run becomes readable. Nothing else on the page is
            # touched, so scroll position, focus and any text selection
            # survive, which a document reload cannot offer.
            poll = (
                f'<script>(function(){{'
                f'var u="/runs/{_e(run_id)}/progress.json",n=0;'
                f'function set(id,v){{var e=document.getElementById(id);'
                f'if(e&&v!=null&&e.innerHTML!==v)e.innerHTML=v;}}'
                f'function tick(){{'
                f'fetch(u,{{cache:"no-store",credentials:"same-origin"}})'
                f'.then(function(r){{return r.ok?r.json():null;}})'
                f'.then(function(d){{'
                f'if(!d)return schedule();'
                f'if(d.open_at){{location.replace(d.open_at);return;}}'
                f'set("pg-step",d.step_html);set("pg-stages",d.stages_html);'
                f'set("pg-elapsed",d.elapsed);'
                f'if(d.terminal){{location.reload();return;}}'
                f'schedule();}})'
                f'.catch(schedule);}}'
                # BACK OFF, do not hammer a starved instance. 2s while the
                # reader is watching closely, easing to 6s on a long run.
                f'function schedule(){{n++;'
                f'setTimeout(tick,n<10?2000:6000);}}'
                f'schedule();}})();</script>')
            tail = (poll
                    + f'<p role="status" aria-live="polite" id="pg-step">'
                    f'<strong>{_e(step)}.</strong></p>'
                    f'{self._identity_confirmation(run_id)}'
                    # ONE LIST, NOT TWO. The tier table and the stage ladder
                    # are derived from the same producers and were rendered
                    # one above the other, so the deployed page said
                    # "Loading what we already know - partial" and "Loading
                    # prior intelligence - DONE" four lines apart. Two
                    # vocabularies for one state reads as a malfunction.
                    f'<div id="pg-stages">{self._stage_ladder(hyd, status)}'
                    f'</div>'
                    f'<p id="pg-elapsed">{_e(self._elapsed_line(run_id))}</p>'
                    # THE EXPECTATION, WHERE THE WAITING HAPPENS. A reader who
                    # is told nothing assumes the worst at 40 seconds; the
                    # same wait is unremarkable when the range was stated up
                    # front. This is the same string the landing page shows,
                    # from one constant, so the two can never disagree.
                    f'<p class="eta">{_e(self.ETA_COPY)}</p>'
                    f'<p>We\'re building the analysis now. This page opens it '
                    f'by itself the moment it is ready.</p>'
                    # "YOUR ANALYSES" IS NOT A RECOVERY INSTRUCTION.
                    #
                    # This footnote used to end by naming /analyses as where
                    # to find the result. That is how the first external
                    # tester eventually got to theirs — and being told where
                    # to go looking is precisely the journey this page exists
                    # to make unnecessary. The storage limit is real and still
                    # disclosed; the navigation advice is gone, because the
                    # page redirects.
                    # THE NOTE STAYS UNTIL THE STORAGE CHANGES. Removing it
                    # would be a promise this deployment cannot keep --
                    # `/readyz` measures the runtime root as ephemeral, so a
                    # replaced instance really does take completed analyses
                    # with it. What changed is the ENDING: losing a run is no
                    # longer a dead end, so the note now says what happens
                    # instead of only what goes wrong.
                    f'<p class="fineprint">Preview note: this service keeps '
                    f'analyses on the instance that produced them, so a '
                    f'restart can interrupt one. If that happens you are '
                    f'told, and offered the same company again in one '
                    f'click \u2014 never left waiting.</p>')
        return self._html(head + tail + '</main></body></html>')

    def _progress_json(self, session, run_id):
        """The few hundred bytes the progress page actually needs.

        WHY THIS EXISTS. The page used to reload itself every four seconds,
        which made the server render the whole document -- ~17KB -- to
        communicate that one word had changed from "to come" to "working".
        On an instance measured at 7-12% of a local core, ~15 of those a
        minute is CPU taken from the analysis the reader is waiting for.

        Deliberately NOT a second source of truth: every field here is
        produced by the same call the HTML page makes, so the two cannot
        drift into disagreeing about the same run.
        """
        # THE SAME OWNERSHIP GATE THE PAGE HAS. A cheap polling route is
        # still a route: without this, any session could watch the progress
        # of a run belonging to somebody else, and a run id is the only
        # secret protecting it. Caught by
        # `test_every_run_layer_route_calls_the_ownership_guard`, which is
        # exactly the class of gate that exists because a new route is the
        # easiest place to forget one.
        if not self._owned(session, run_id):
            return ("404 Not Found",
                    [("Content-Type", "application/json")],
                    json.dumps({"error": "not_found"}))
        real = self._is_real_run(run_id)
        status = self.ci.store.run_state(run_id) or "RUNNING"
        terminal = status in self.TERMINAL_STATES
        # `open_at` is the ONLY instruction the client acts on, and it is the
        # same readiness the HTML route redirects on -- so a reader with
        # scripting and one without arrive at the same place.
        open_at = None
        if real:
            try:
                if self.result_readiness(run_id)["opens_result"]:
                    open_at = f"/runs/{run_id}"
            except Exception:                             # noqa: BLE001
                open_at = None
        if open_at is None and status in ("COMPLETE", "PARTIAL"):
            open_at = f"/runs/{run_id}"
        payload = {"run_id": run_id, "status": status, "terminal": terminal,
                   "open_at": open_at}
        if open_at is None and not terminal:
            try:
                hyd = self._hydration_state(run_id, terminal=terminal)
                step = (hyd.get("current_step") or "").strip() \
                    or self._stage_line(status)
                payload["step_html"] = f"<strong>{_e(step)}.</strong>"
                payload["stages_html"] = self._stage_ladder(hyd, status)
                payload["elapsed"] = _e(self._elapsed_line(run_id))
            except Exception:                             # noqa: BLE001
                # A projection failure costs the DETAIL, never the poll: the
                # client keeps its current text and asks again, which is the
                # same thing the old reload did on a slow render.
                pass
        return self._ok_json(payload)

    #: THE MAXIMUM IS A CONTRACT, NOT REASSURANCE.
    #:
    #: A page that says "up to 2 minutes" and then keeps spinning at 2:30 has
    #: told the reader something false, which is worse than saying nothing.
    #: `INTERACTIVE_MAX_S` is therefore the same number the deadline enforces:
    #: at it, the reader gets a bounded CORE or an explicit terminal state.
    #:
    #: Measured on the preview at da9fe4da: Apple 72.2s and 84.5s, Microsoft
    #: 107.78s. So "under a minute" is NOT sayable yet and is deliberately not
    #: said -- the copy promises what the p90 can currently support, and gets
    #: tightened when the cohort earns it, never before.
    INTERACTIVE_MAX_S = 120
    ETA_COPY = ("Analysis usually takes about a minute. Deeper or "
                "less-covered companies can take up to two minutes.")

    #: §11. What is being assembled, in the order a person would build it.
    #: Named for the WORK rather than for the lifecycle, because "VALIDATING
    #: _COMPANY" tells a customer nothing and "Identifying the company" tells
    #: them exactly what is happening to their request.
    _STAGE_LADDER = (
        ("identity", "Identifying the company"),
        ("prior", "Loading prior intelligence"),
        ("evidence", "Reading current company evidence"),
        ("macro", "Connecting macro and industry conditions"),
        ("competitors", "Mapping competitors"),
        ("stress", "Stress-testing the strategic read"),
        ("story", "Building the executive story"),
        ("ready", "Preparing the analysis"),
    )

    #: Which hydration tier proves each rung is done.
    #:
    #: FOUR TIERS ARE MEASURED AND EIGHT RUNGS ARE NAMED, so several rungs
    #: share a tier and therefore flip together. That is deliberate: the
    #: alternative is eight independently-animating rows whose states are
    #: invented, which is a progress bar that lies. A rung is marked from a
    #: PRODUCER's output and never from elapsed time — the contract
    #: `_hydration_state` already keeps.
    _STAGE_TIER = {
        "identity": "T0", "prior": "T1", "evidence": "T2", "macro": "T2",
        "competitors": "T3", "stress": "T3", "story": "T3", "ready": "T3",
    }

    def _stage_ladder(self, hyd, status) -> str:
        """The assembly, as a list a customer can watch fill in."""
        tiers = (hyd or {}).get("tiers") or {}
        if not tiers:
            return ""
        from intent_engine.founder_brief import hydration as H
        done_states = (H.READY, H.BOUNDED, H.DEGRADED)
        rows, reached = [], True
        for key, label in self._STAGE_LADDER:
            state = tiers.get(self._STAGE_TIER.get(key, ""), H.PENDING)
            if state in done_states and key != "ready":
                mark, cls = "done", "done"
            elif reached:
                mark, cls, reached = "working", "now", False
            else:
                mark, cls = "to come", "wait"
            rows.append(f'<li class="{cls}">{_e(label)}'
                        f'<span class="st">{mark}</span></li>')
        return (f'<ol class="stages" aria-label="What is being assembled">'
                f'{"".join(rows)}</ol>')

    def _identity_confirmation(self, run_id) -> str:
        """§7. Who is being analysed, shown before the answer arrives.

        Not a confirmation STEP — an interstitial the customer has to
        acknowledge is a click between them and the thing they asked for.
        The identity is stated where they are already looking, with the
        correction available beside it, so a wrong company is caught in the
        first four seconds instead of on the report.
        """
        meta = self.ci.run_meta(run_id) or {}
        name = str(meta.get("company_name") or "").strip()
        if not name:
            return ""
        listing = self._listing_for(run_id)
        bits = [b for b in (getattr(listing, "ticker", ""),
                            str(meta.get("country") or ""),
                            str(meta.get("domain") or "")) if b]
        detail = (f'<span class="idbits">{_e(" · ".join(bits))}</span>'
                  if bits else "")
        return (f'<p class="analysing">Analysing <b>{_e(name)}</b>{detail}'
                f' — <a href="/">not this company?</a></p>')

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
        # "EVERY" WAS NEVER CHECKED. This sentence was printed whenever ANY
        # source failed, so a live Meta run that had read its own 10-K and
        # 10-Q told the customer that every approved source had failed. A
        # count is one attribute lookup away and the claim was made without
        # it; say what actually happened instead.
        read = len(self._retrieved_documents(run_id))
        if read:
            return (f"{len(rows)} source(s) could not be retrieved ("
                    + _e(", ".join(cats)) + f"), though {read} were read. "
                    "Public sites can refuse automated access or require "
                    "JavaScript; a failed retrieval is not evidence of "
                    "real-world absence.")
        return ("No approved source could be retrieved (" +
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
            return self._no_such_run(session, run_id)
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
            #
            # ...BUT ONLY WHILE THERE IS NOTHING TO WATCH INSTEAD.
            #
            # THE REDIRECT LOOP. `_progress` sends the reader HERE the moment
            # `result_readiness(...)["opens_result"]` is true, and this line
            # sent them straight back while the worker was still in flight.
            # Both conditions are true together for most of a normal run --
            # from the moment a readable result composes until the worker
            # clears -- so the two pages bounced off each other until the
            # client gave up.
            #
            # MEASURED LIVE on 8397d67, and it is not an edge case:
            #
            #     Alphabet    303 loop from t=36s to t=152s   76% of the run
            #     Meta        blank from t=37s to t=220s      83%
            #     JPMorgan    blank from t=37s to t=157s      76%
            #     Cloudflare  blank from t=9s  to t=20s       50%
            #
            # Four of four companies. The customer watching the analysis they
            # asked for saw a page that never resolved, which is exactly the
            # "ambiguous limbo" the terminal-state invariant forbids.
            #
            # `result_readiness` already states the rule and this line was the
            # one place not following it: "opens_result is True IF AND ONLY IF
            # a customer-readable result exists. When it is True the customer
            # goes to the analysis, WHATEVER THE WORKER'S METADATA SAYS." So
            # readiness decides, and in-flight only decides when readiness has
            # nothing to offer.
            avail = self._availability(run_id)
            if self.only_watchable(run_id):
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
                # EVERY LAYER, NOT ONLY THE DEFAULT ONE.
                #
                # `layer == "default"` meant `/full` never reached the bounded
                # surface and fell through to the failure page even when the
                # run had documents AND a composed result. The comment below
                # records the primary screen being repaired and calls it "the
                # only surface that would not" tolerate a missing report;
                # `/full` was the other one, and it kept the failure page.
                #
                # MEASURED on 517e7ae, Meta Platforms, ONE run:
                #
                #     intro    6,008 chars   real analysis
                #     slides   5,863         real analysis
                #     story    4,558         real analysis
                #     history 29,692         real analysis
                #     step 6   4,110         real analysis
                #     brief   16,206         real analysis
                #     full       755         "did not produce a report"
                #
                # Ten of ten board questions answered on the same run. The
                # evidence was never insufficient; one route disagreed with
                # the other six about the run it was rendering, and that route
                # is the one a reader opens to read the analysis.
                if avail["documents"] and avail["has_result"]:
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
                # THE DEMO IS A STORY, AND A STORY HAS A FIRST PAGE (§17).
                #
                # This used to land on the 60-second founder brief, which was
                # right when the alternative was an eleven-section report. It
                # is no longer the first thing a reader should meet: the brief
                # opens on the run's own epistemic verdict, and for a company
                # whose run retrieved little that verdict was "no strategic
                # reading cleared the evidence bar" -- a refusal, as the
                # product's first sentence.
                #
                # Step 1 is now the Introduction, which says what the company
                # is and what the argument is about. The brief is unchanged
                # and is still served at /brief.
                return self._redirect(f"/runs/{run_id}/intro")
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
                return self._redirect(f"/runs/{run_id}/intro")
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
            return self._no_such_run(session, run_id)
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
        # ONE DENOMINATOR PER PAGE.
        #
        # `used` is read from the store, NOW. `note["source_count"]` was
        # computed inside `compose`, THEN. On Meta's live run at 5d43053 the
        # page said "7 page(s) read; 1 carried usable evidence" and listed
        # seven, of which three are Meta's own filings. Amazon said the same
        # thing on the same wave. A reader cannot reconcile those numbers,
        # and neither could I: the gate, re-run offline on Meta's seven real
        # documents, answers 7.
        #
        # So the page states what it can verify from the evidence in front of
        # it, and a stale smaller count is not printed as if it described
        # this list. The gate's verdict still stands -- this changes what the
        # page SAYS, never what the run was allowed to do -- and the run now
        # records `readiness_inputs` so the discrepancy is measured on the
        # next wave rather than argued about.
        usable = note.get("source_count") or 0
        read_line = f"{len(used)} page(s) read"
        if usable and usable != len(used):
            if usable < len(used):
                # The gate saw FEWER documents than the store now holds. Say
                # what is true of this list; do not attribute the smaller
                # number to it.
                read_line += (f"; the evidence gate was applied to {usable} "
                              f"of them")
            else:
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
                                 if self._listing_for(run_id).ticker else None,
                                 modeled_market=self._modeled_expectation(
                                     run_id, _name),
                                 read=self._strategic_read(run_id, _name),
                                 econ=self._founder_economic_context(run_id))
        from intent_engine.founder_brief import challenge_block as _cb
        strat = (fr.BRIEF_CSS + fn.NARRATIVE_CSS + _charts.CHART_CSS + _cb.CSS
                 + fd.render_dossier(
                     _book, depth=fd.FULL, run_id=run_id, wrap=False,
                     citation_labels=self._citation_labels(run_id),
                     charts=_external_charts(_external),
                     lead=fd.render_decision_lead(
                         _decision, _name, depth=fd.FULL, run_id=run_id,
                         contract=self._executive_contract(run_id),
                         read=self._strategic_read(run_id, _name))))
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
                f''
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
            return self._no_such_run(session, run_id)
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

    def _run_evidence(self, session, run_id):
        """The provenance drawer for a LIVE run — D30.

        `/demo-dossiers/<company>/evidence` renders every source with its
        author, host, subject, independence, relevance and the reason it was
        or was not counted, plus the discovery coverage behind it. On a live
        run that drawer was unreachable: `/runs/<id>/sources` listed what was
        read and offered no way into any of it.

        This is D9's shape exactly -- a correct, complete surface wired only
        to the demo-dossier path -- and it is fixed the same way, by routing
        rather than by building a second drawer. The renderer is untouched.
        """
        if not self._owned(session, run_id):
            return self._no_such_run(session, run_id)
        from intent_engine.demo_dossier.store import company_key
        meta = self.ci.run_meta(run_id) or {}
        name = str(meta.get("company_name") or "")
        key, _c, _m = self._manifest_placement(
            company_key(name or str(meta.get("domain") or "") or run_id),
            name=name, domain=str(meta.get("domain") or ""))
        return self._evidence_screen(key)

    def _composed_decision(self, run_id):
        """The composed executive decision as a dict — what the X-Ray renders.

        Q&A routes its per-intent answers at THIS object rather than at the
        run's reasoning decision, for the same reason the X-Ray does: the
        reasoning path does not populate `key_risk`, `falsifier`,
        `economic_history` or `competitors`, and a router pointed at it would
        answer "no risk recorded" for a company whose X-Ray displays one.
        """
        try:
            from intent_engine.demo_dossier.store import (DossierStore,
                                                          company_key)
            meta = self.ci.run_meta(run_id) or {}
            name = str(meta.get("company_name") or "")
            key, _c, _m = self._manifest_placement(
                company_key(name or str(meta.get("domain") or "") or run_id),
                name=name, domain=str(meta.get("domain") or ""))
            dossier = DossierStore(self._runtime_root).latest(key)
            composed = (self._executive_read(dossier)
                        if dossier is not None else {})
        except Exception:                                   # noqa: BLE001
            _LOG.warning("composed decision not read for %s", run_id)
            return {}
        if not isinstance(composed, dict):
            return {}
        # TWO COMPOSERS, AND THE FIELD WAS ADDED TO THE OTHER ONE.
        #
        # MEASURED from the captures, not inferred: across all eight Batch-A
        # companies on fdbfe77, ZERO of eighty Q&A answers carried the
        # company's own qualifying sentence — on a build that contains
        # `grounded_in`. The renderer was fine and the field was empty,
        # because Q&A's decision comes from
        # `executive.decision_synthesis.compose`, which builds a
        # FounderDecision from the DOSSIER, while `grounded_in` was added to
        # `strategic_intelligence.decision.compose_decision`, which builds one
        # from the run's hypothesis. Same class, two producers, one repaired.
        #
        # This is the seam where BOTH objects exist, so the run's own
        # grounding is joined on here rather than either composer learning
        # about the other.
        if not composed.get("grounded_in"):
            composed["grounded_in"] = self._run_grounding(run_id)
        # TWO COMPOSERS, AND THE ADVERSARY WAS WIRED INTO THE OTHER ONE.
        #
        # Same seam, second field. `analysis_selection._adversary` was
        # ungated last wave so the L0/L1/L2 engine would run for companies
        # outside the curated manifest -- but that repair landed in
        # `strategic_read.compose`, and the X-Ray, the full analysis and the
        # presentation all render `decision_synthesis.compose`, whose
        # `selection` still comes from the manifest. MEASURED: `adversary`
        # scored 0.0 on all 44 companies both before and after.
        #
        # `competitors` has the identical shape: it is read off
        # `profile.strategic_competitors`, which is the manifest's list, so
        # every company outside the manifest showed no competitor set on the
        # X-Ray while its own step 1 named rivals from its filings.
        #
        # Joined here rather than taught to either composer, which is the
        # precedent `grounded_in` set directly above: this is the ONE place
        # both objects exist, and a composer that reached into the other
        # would be a second place for them to disagree.
        # `_strategic_read` returns the OBJECT, not its dict. Reading it with
        # `.get` would silently find nothing and this join would be one more
        # repair that ships green and inert -- which is the failure mode this
        # very session measured twice on the standing seam.
        read = self._strategic_read(run_id)
        for field in ("adversary", "impossible_hypotheses"):
            value = list(getattr(read, field, ()) or ())
            if value and not composed.get(field):
                composed[field] = value
        rivals = getattr(read, "level4_competition", ()) or ()
        if rivals and not composed.get("competitors"):
            composed["competitors"] = [
                {"name": str(getattr(row, "name", "")),
                 "why": str(getattr(row, "why_a_rival", "")
                            or getattr(row, "why", ""))}
                for row in rivals if getattr(row, "name", "")]
        if not composed.get("economic_architecture"):
            composed["economic_architecture"] = getattr(
                read, "economic_architecture", None)
        return composed

    def _run_grounding(self, run_id) -> str:
        """The sentence from THIS company's filing that qualified its reading.

        Read from the run's own report, which is where the hypothesis and its
        `mechanism_evidence` live. Never raises: a missing grounding is an
        absent sentence, not a broken page.
        """
        try:
            from intent_engine.strategic_intelligence import mechanism as MECH
            report = (self._result(run_id) or {}).get("strategic_report") or {}
            for hypothesis in (report.get("hypotheses") or ()):
                line = MECH.because_line(hypothesis, limit=1)
                if line:
                    return line
        except Exception:                                   # noqa: BLE001
            return ""
        return ""

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
            # A DOSSIER IS NOT A MARKET READING.
            #
            # This asked only whether a dossier EXISTS. One always does after
            # a run, including for the 24 gauntlet companies the market
            # bundle does not cover -- its market side is assembled as
            # UNAVAILABLE and every block in it is empty. The composed
            # decision over that dossier was then handed to the contract as
            # `market_decision` with `market_usable=True`, so whatever
            # standing it reached was attributed to the market engine.
            #
            # It did not matter while such a dossier could only reach
            # UNMEASURABLE. It matters now that a run's own evidence lifts it
            # to BOUNDED: a fixture run whose OWN decision is WITHHELD was
            # told "A supported reading of Acme exists and is set out on the
            # Executive X-Ray" -- two surfaces of one run disagreeing about
            # whether a reading exists, which is the single thing this
            # contract was built to prevent.
            #
            # So the market side has to have actually published something.
            # Absence routes to `market_decision=None`, which the contract
            # already handles as "no market reading is published for this
            # company, so the reading below rests on this run alone".
            if str((getattr(dossier, "market_block", None) or {})
                   .get("availability") or "") not in ("AVAILABLE", "STALE"):
                market, usable = None, False
            # THE THIRD PRODUCER OF A READING, which this contract used not
            # to be told about.
            #
            # MEASURED, Pfizer Inc. on 743df06 and cb9e6b7: twelve usable
            # documents across five families, `/full` saying "No strategic
            # reading of Pfizer Inc. cleared the evidence bar, so none is
            # asserted here", and `/intro`, `/story` and `/connect` on the
            # SAME run saying Pfizer runs on a product that may only be sold
            # once a regulator permits it and a payer agrees to pay for it,
            # naming generic competition to Xtandi and Xeljanz as the
            # substitution, and setting out rebate economics.
            #
            # The curated transition library matching nothing is a fact about
            # a twelve-entry library. It is not a fact about whether this
            # product has a reading of Pfizer, and the one place that answers
            # that question was deciding it from two of the three producers.
            return ec.decide(
                company=(getattr(dossier, "canonical_name", "") or name),
                run_decision=decision_of(report), market_decision=market,
                market_usable=usable,
                bounded_read=self._bounded_read_exists(run_id, name))
        except Exception:                                   # noqa: BLE001
            _LOG.warning("executive contract not composed for %s", run_id)
            return None

    def _bounded_read_exists(self, run_id, name="") -> bool:
        """Did this run compose an economic reading the pages are rendering?

        Deliberately asks the SAME object the surfaces project from, rather
        than re-deriving the question: a second opinion about whether a
        reading exists is exactly the disagreement the contract removes.

        ONE READER, NOT A SECOND OPINION. `StrategicRead` already answers
        this as `puts_a_strategy_forward`, and the deep dossier has been
        branching on it all along -- it is only the narrative, and the
        contract every surface consults, that were never told. Re-deriving
        the question here would make a third answer to a question that
        exists to have one.

        Never raises: a contract that can fail a page is worse than the
        contradiction it removes.
        """
        try:
            read = self._strategic_read(run_id, name)
        except Exception:                                   # noqa: BLE001
            return False
        return bool(read is not None
                    and getattr(read, "puts_a_strategy_forward", False))

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

        # THE SHARED ECONOMIC STATE, and this company's evidenced exposure
        # to it. Read from the canonical core, never recomputed here: the
        # defect this closes is two macro pictures in one product, with the
        # better one unreachable. The founder side may not import the market
        # engine and does not; `econ` is neutral and both consume it.
        #
        # Fails soft like every other context family. A deployment where no
        # market engine has ever run reads "unavailable" with a reason, and
        # the analysis proceeds on the company's own evidence.
        # THIS COMPANY'S OWN EVIDENCE CROSSES FIRST, AND THE ORDER IS THE
        # WHOLE POINT.
        #
        # `_filed_exposures` READS what this writes, from the same store,
        # a few lines below. Running the read first meant the analysis
        # pass always found zero exposures -- and that pass is the one
        # that CACHES the context, so every page render of a fresh run
        # got the empty answer and the economic section reported
        # INSUFFICIENT_EVIDENCE for a company whose filings had just
        # established its exposures. It corrected itself only after a
        # restart dropped the cache, which is the shape of a defect that
        # cannot be reproduced by looking at it twice.
        #
        # THE OTHER DIRECTION, and it runs even when the state is absent.
        # This company's public statements about hiring, pricing, capacity,
        # inventories, demand, financing and supply become evidence nodes in
        # the shared graph, where the market engine's aggregate step reads
        # them. Nothing about who USED the product crosses; there is no path
        # from a demo query to an economic node.
        try:
            self._publish_econ_evidence(
                run_id=run_id, company_name=name, observations=observations,
                documents=documents, today=today)
        except Exception:  # noqa: BLE001 - see above
            _LOG.warning("econ evidence not published for %s", run_id)

        economy, exposures = None, ()
        try:
            from intent_engine.external_intel import econ_context as ec
            # THE RUN'S OWN EVIDENCE CUTOFF, NOT TODAY'S DATE.
            #
            # §26.16. The company evidence was gathered at `run_meta.as_of`
            # and the baseline analysis rests on it. Reading the economy at a
            # later date makes the treatment "the world model PLUS more recent
            # information", and the difference between the two arms stops
            # being attributable to the world model at all. `store.load`'s
            # cutoff is a write-order cutoff, so this asks the store what it
            # had recorded by the run's date -- which is the question.
            _run_as_of = str((self.ci.run_meta(run_id) or {}).get("as_of")
                             or "") or today
            economy = ec.load(self._runtime_root, as_of=_run_as_of)
            exposures = self._econ_exposures(macro or (), observations)
            # Exposures read from this company's own FILINGS, joined to the
            # ones its macro factors established. The filing path is the one
            # that finds anything: measured across six companies, the macro
            # factors contributed a handful and the filings contributed 39.
            exposures = tuple(dict.fromkeys(
                tuple(exposures) + self._filed_exposures(run_id, today)))
        except Exception:  # noqa: BLE001 - context must never break a run
            _LOG.warning("economic context unavailable for %s", run_id)

        context = ep.build_context(market=market, macro=macro or (),
                                   competitors=competitors or (),
                                   strategic=strategic, economy=economy,
                                   economy_exposures=exposures, as_of=today)

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

    #: Founder-side macro factor keys -> shared economic-state condition
    #: kinds. An exposure only counts when the company's OWN evidence
    #: established it, which is what `macro_contract.validate_factor` already
    #: enforces -- so this maps factors that survived that gate, and never
    #: derives an exposure from a sector.
    _ECON_EXPOSURE_MAP = {
        "policy_rate": "policy_rate", "interest_rate": "policy_rate",
        "rates": "policy_rate", "inflation": "inflation",
        "cpi": "inflation", "unemployment": "labour",
        "employment": "labour", "labour": "labour", "labor": "labour",
        "wages": "wages", "gdp": "growth", "growth": "growth",
        "industrial_production": "industrial_production",
        "housing": "housing", "oil": "commodity_oil",
        "energy": "commodity_oil", "gas": "commodity_gas",
        "copper": "commodity_copper", "dollar": "fx_dxy",
        "currency": "fx_dxy", "fx": "fx_dxy",
        "credit": "financial_conditions",
        "financial_conditions": "financial_conditions",
        "treasury": "treasury_10y", "yield": "treasury_10y",
        "real_yield": "real_yield",
    }

    def _econ_exposures(self, macro_factors, observations) -> tuple:
        """Which shared economic quantities THIS company is exposed to.

        Derived from the macro factors that already passed
        `macro_contract.validate_factor`, which refuses a factor not bound to
        a retrieved observation. Nothing here widens that: a condition the
        company has no evidenced connection to does not become an exposure
        because its sector suggests one.
        """
        out = []
        for factor in macro_factors or ():
            for source in (getattr(factor, "factor", ""),
                           getattr(factor, "name", ""),
                           getattr(getattr(factor, "observation", None),
                                   "series_id", "")):
                key = str(source or "").strip().lower()
                if not key:
                    continue
                mapped = self._ECON_EXPOSURE_MAP.get(key)
                if mapped is None:
                    mapped = next((v for k, v in
                                   self._ECON_EXPOSURE_MAP.items()
                                   if k in key), None)
                if mapped and mapped not in out:
                    out.append(mapped)
                    break
        return tuple(out)

    def _filed_exposures(self, run_id: str, today: str) -> tuple:
        """Economic quantities this company's own documents state it depends on.

        Read from the shared core, where `_publish_econ_evidence` wrote them
        during this run's translation. Reading them back rather than keeping
        them in memory means a page rendered from a cached run gets the same
        answer as the analysis that produced it.
        """
        try:
            from intent_engine.econ import store as est
            from intent_engine.external_intel import strategic_contract as sc
            company_id = sc.company_key(
                (self.ci.entity_identity(run_id) or {}).get("canonical_name")
                or (self.ci.run_meta(run_id) or {}).get("company_name") or "")
            rows = est.load(self._runtime_root, "priority", upto=today)
            return tuple(
                str(r.get("quantity"))
                for r in rows
                if isinstance(r, dict)
                and r.get("record") == "company_exposure"
                and r.get("company_id") == company_id and r.get("quantity"))
        except Exception:  # noqa: BLE001 - context must never break a run
            return ()

    def _publish_econ_evidence(self, *, run_id: str, company_name: str,
                               observations, documents, today: str) -> dict:
        """This company's public statements, as shared economic evidence.

        Written to the canonical core so the market engine's aggregate step
        can build candidate indicators from a panel of companies. The
        translation refuses anything tenant-private and anything with no
        stated direction, and reports what it declined -- a translator that
        returned only its output would make a 90% loss invisible.
        """
        from intent_engine.econ import store as est
        from intent_engine.external_intel import econ_evidence as ee
        from intent_engine.external_intel import strategic_contract as sc

        company_id = sc.company_key(company_name) or run_id
        out = ee.translate(observations, company_id=company_id,
                           company_name=company_name, as_of=today,
                           documents=documents)
        if out["nodes"]:
            est.append_many(self._runtime_root, "node",
                            [n.as_dict() for n in out["nodes"]],
                            written_at=today)
        # The exposures travel with the evidence. Without them the shared
        # economic state reaches this company and stops: `relevant_to` needs
        # a quantity this company is evidenced to be exposed to, and an
        # analysis with no exposures reads every economic condition as
        # irrelevant to it.
        if out.get("exposures"):
            est.append_many(
                self._runtime_root, "priority",
                [dict(r, record="company_exposure", as_of=today,
                      company_id=company_id) for r in out["exposures"]],
                written_at=today)
        _LOG.info("econ evidence for %s: %d of %d offered crossed (%s)",
                  company_id, out["translated"], out["offered"],
                  out["declined"])
        return out

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

    def _founder_economic_context(self, run_id: str):
        """§4/§6/§21: ONE economic decision context per run, for every surface.

        Memoised on the per-request thread-local for the same reason
        `_strategic_read` is: the brief, the full analysis, the Q&A and the
        API all render it, and four surfaces each building their own is
        exactly how brief and full came to say opposite things about the same
        company. §21 is a property of there being one object, not of four
        renderers agreeing.

        Never raises. §18 -- a missing or unreadable economic state leaves the
        founder analysis untouched and the section states what is missing.
        """
        memo = getattr(self._request, "econ", None)
        if memo is None:
            memo = self._request.econ = {}
        if run_id in memo:
            return memo[run_id]
        memo[run_id] = ctx = self._compose_founder_economic_context(run_id)
        return ctx

    def _compose_founder_economic_context(self, run_id: str):
        from intent_engine.econ import founder_contract as FC
        from intent_engine.external_intel import econ_decision as ED
        try:
            meta = self.ci.run_meta(run_id) or {}
            identity = self.ci.entity_identity(run_id) or {}
            name = (identity.get("canonical_name") or identity.get("name")
                    or str(meta.get("company_name") or ""))
            # THE RUN'S OWN CUTOFF, NOT TODAY'S DATE. §26.16: a product that
            # reads the economy at a different date from the one its evidence
            # was gathered at is comparing two vintages and calling the
            # difference an economic effect. `run_meta.as_of` is the date the
            # company evidence was gathered at, so it is the date the economic
            # state must be read at too.
            as_of = str(meta.get("as_of") or "") or self._as_of()
            external = self._external_context(run_id)
            economy = getattr(external, "economy", None)
            exposures = tuple(getattr(external, "economy_exposures", ()) or ())
            from intent_engine.external_intel import (
                strategic_contract as _sc,
            )
            company_id = _sc.company_key(name) or run_id
            if economy is None or not getattr(economy, "available", False):
                return FC.blocked(
                    company_id,
                    reason=(getattr(economy, "reason", "")
                            or "no shared economic state is available to this "
                               "deployment"),
                    as_of=as_of, status=FC.BLOCKED_DATA)
            ci_in = self.classification_inputs(run_id, name)
            from intent_engine.executive import company_profile as CPF
            profile = CPF.profile_for(
                company_id, name=name,
                domain=str(meta.get("domain") or ""),
                registrant=ci_in.get("registrant"),
                evidence_text=ci_in.get("evidence_text", ""))
            # THE RUN'S OWN DECISION. `StrategicRead` carries a `Statement`
            # for the level-5 answer, not a `FounderDecision`, and the object
            # the comparator projects is the decision -- so it is read from
            # the report, which is where every other surface reads it.
            decision = self._run_decision(run_id)
            return ED.build(
                company_id=company_id, company_name=name, as_of=as_of,
                economy=economy, exposures=exposures, profile=profile,
                decision=decision, risks=self._decision_risks(run_id),
                runtime_root=self._runtime_root,
                relations=self._econ_relations(run_id))
        except Exception as exc:                            # noqa: BLE001
            # A FAULT IS REPORTED AS A FAULT. Returning an abstention here
            # would tell a founder the economy does not bear on their
            # decision, which is a claim, when what happened is that we could
            # not work it out.
            _LOG.warning("economic context failed for %s: %s", run_id, exc)
            from intent_engine.external_intel import (
                strategic_contract as _sc,
            )
            return FC.blocked(
                _sc.company_key(str((self.ci.run_meta(run_id)
                                     or {}).get("company_name") or ""))
                or run_id,
                reason=(f"the economic reading could not be composed for this "
                        f"analysis ({type(exc).__name__}); it is reported as "
                        f"unavailable rather than omitted"),
                status=FC.BLOCKED_EXTERNAL)

    def _run_decision(self, run_id):
        """The run's own FounderDecision, or None."""
        from intent_engine.strategic_intelligence.decision import decision_of
        try:
            result = self._result(run_id) or {}
            report = result.get("strategic_report") or {}
            return decision_of(report) if report else None
        except Exception:                                   # noqa: BLE001
            return None

    def _decision_risks(self, run_id) -> list:
        """This run's own risks, in the structured comparison vocabulary.

        Baseline A's risks come from the company's OWN evidence -- the
        strategic report's vulnerabilities -- and each carries the observation
        that established it. §3: an A with no risks concedes two of the seven
        material fields before the comparison starts, so a run with no
        vulnerability produces no baseline and the delta is not claimed.
        """
        try:
            result = self._result(run_id) or {}
            report = result.get("strategic_report") or {}
        except Exception:                                   # noqa: BLE001
            return []
        # TWO SOURCES, IN ORDER, AND THE FALLBACK IS NOT A CONSOLATION PRIZE.
        #
        # MEASURED LIVE on 5f21b055 across ten companies: five produced no
        # Baseline A at all, so no economic delta could be measured for
        # half the matrix. The cause is upstream and specific --
        # `detect_vulnerabilities` only fires for a hypothesis whose
        # `pattern_id` is in the vulnerability playbook, so a company the
        # pattern library does not match has zero of them however much
        # evidence was read.
        #
        # A BLIND SPOT IS THE SAME SHAPE. It names an observed tension and
        # why it may matter -- a channel and a mechanism, resting on the
        # company's own observations -- which is exactly what a Baseline A
        # risk is. It is a genuinely weaker claim than a vulnerability, so it
        # carries LOW severity and the source is recorded on the risk rather
        # than being silently equivalent.
        out = []
        for i, row in enumerate(report.get("vulnerabilities") or ()):
            d = row.as_dict() if hasattr(row, "as_dict") else row
            if not isinstance(d, dict):
                continue
            layer = str(d.get("exposed_layer") or "")
            mechanism = str(d.get("mechanism") or "")
            if not layer.strip() or not mechanism.strip():
                continue
            out.append({
                "risk_id": f"company:{i}",
                # THE REPORT'S OWN CONFIDENCE, MAPPED. Stamping every
                # company risk MEDIUM would make `risk_severity` -- one of the
                # seven material fields -- a constant on the A side, and a
                # constant baseline field is a field B wins for free.
                #
                # The detector writes "moderate" and "low", lower case, and
                # the first version of this map looked for "MEDIUM" -- so
                # every company risk fell through to LOW and the field was a
                # constant anyway.
                "severity": {"HIGH": "HIGH", "MODERATE": "MEDIUM",
                             "MEDIUM": "MEDIUM", "LOW": "LOW"}.get(
                                 str(d.get("confidence", "")).upper(), "LOW"),
                "channel": layer,
                "mechanism": mechanism,
                "standing": "INFERRED",
                "source": "vulnerability",
                "evidence": tuple(str(e) for e in
                                  (d.get("evidence") or ()))[:3]})
        if not out:
            for i, row in enumerate(report.get("blind_spots") or ()):
                d = row.as_dict() if hasattr(row, "as_dict") else row
                if not isinstance(d, dict):
                    continue
                tension = str(d.get("observed_tension") or "")
                why = str(d.get("why_it_may_matter") or "")
                if not tension.strip() or not why.strip():
                    continue
                out.append({
                    "risk_id": f"company:blind:{i}",
                    "severity": "LOW",
                    "channel": tension,
                    "mechanism": why,
                    "standing": "INFERRED",
                    "source": "blind_spot",
                    "evidence": tuple(
                        str(e) for e in
                        (d.get("supporting_observation_ids") or ()))[:3]})
        if not out:
            out.extend(self._stated_exposure_risks(run_id))
        return out[:4]

    def _stated_exposure_risks(self, run_id) -> list:
        """What THIS company says it depends on, in its own filings.

        THE THIRD SOURCE, AND THE ONLY ONE THAT IS NEVER LIBRARY TEXT.
        Vulnerabilities need a matched pattern; blind spots need a tension the
        business model can have; both are written once and shared by every
        company that qualifies. This is a sentence out of the subject's own
        document -- "our results are sensitive to..." -- and it is the shape
        §3 asks Baseline A to have: the company's own structural economics.

        IT IS NOT THE TREATMENT. A is what the company says about itself; B
        adds what the economic state says those conditions are actually
        doing. The exposure is company evidence, the reading is not, and the
        two are separated by which side of the comparison they enter.
        """
        try:
            from intent_engine.econ import exposure as EXP
            documents = [d.get("text_content") or ""
                         for d in self._retrieved_documents(run_id)]
            rows = EXP.read(documents, company_id=run_id) if documents else []
        except Exception:                                   # noqa: BLE001
            return []
        out = []
        for i, row in enumerate(rows):
            basis = str(row.get("basis") or "").strip()
            dimension = str(row.get("dimension") or "")
            if not basis or not dimension:
                continue
            out.append({
                "risk_id": f"company:stated:{i}",
                "severity": "LOW",
                "channel": dimension.replace("_", " ").lower()
                                    .replace(" exposure", ""),
                "mechanism": basis[:240],
                "standing": "INFERRED",
                "source": "stated_exposure",
                "evidence": (f"filing:{run_id}",)})
        return out[:4]

    def _econ_relations(self, run_id) -> list:
        """Economic relations held about this economy, with their standing.

        Read from the shared state's beliefs. A belief that has not been
        supported out of sample arrives CANDIDATE and the contract keeps it in
        a separate list, so no surface can render it as a finding -- §26.4.
        """
        try:
            external = self._external_context(run_id)
            economy = getattr(external, "economy", None)
            rows = []
            for b in (getattr(economy, "beliefs", ()) or ()):
                if not isinstance(b, dict):
                    continue
                rows.append({
                    "statement": str(b.get("proposition", "")),
                    "state": str(b.get("status", "")),
                    "mechanism": str(b.get("mechanism", "")),
                    "falsifier": str(b.get("falsifier", "")),
                    "evidence": (str(b.get("belief_id", "")),)})
            return rows[:6]
        except Exception:                                   # noqa: BLE001
            return []

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

    def _run_company(self, run_id) -> str:
        """The company this run is about, for surfaces that show only an
        answer. Never raises and never returns a placeholder that could be
        mistaken for a name."""
        try:
            _brief, _report, name = self._founder_layers(run_id)
            if name:
                return name
        except Exception:                                   # noqa: BLE001
            pass
        meta = self.ci.run_meta(run_id) or {}
        return str(meta.get("company_name") or meta.get("domain") or "")

    def _founder_answer_page(self, session, run_id, answer):
        """One answer, in the same shape as every other founder surface."""
        from intent_engine.founder_brief import render as fr
        a = answer
        parts = [f'{fr.BRIEF_CSS}<main class="fb">',
                 # THE COMPANY IS NAMED ON THE PAGE THAT ANSWERS ABOUT IT.
                 # A reader who lands here from a shared link, or scrolls
                 # back to it later, was shown a question and an answer with
                 # no indication which company either concerned.
                 f'<p class="kicker">{_e(self._run_company(run_id))}</p>',
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
            return self._no_such_run(session, run_id)
        # The same availability question the other run routes ask. This one
        # answered 200 with a full dossier while the primary screen answered
        # 400, which is how the two surfaces came to contradict each other.
        if self._is_real_run(run_id) and self.only_watchable(run_id):
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
                                if self._listing_for(run_id).ticker else None,
                                modeled_market=self._modeled_expectation(
                                    run_id, name),
                                read=self._strategic_read(run_id, name),
                                econ=self._founder_economic_context(run_id))
        body = fr.BRIEF_CSS + fn.NARRATIVE_CSS + _charts.CHART_CSS + \
            fd.render_dossier(
                book, depth=fd.BRIEF, run_id=run_id,
                citation_labels=self._citation_labels(run_id),
                charts=_external_charts(external),
                lead=fd.render_decision_lead(
                    decision, name, depth=fd.BRIEF, run_id=run_id,
                    contract=self._executive_contract(run_id),
                    read=self._strategic_read(run_id, name)))
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
            return self._no_such_run(session, run_id)
        avail = self._availability(run_id)
        if self.only_watchable(run_id):
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
            return self._no_such_run(session, run_id)
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

    # =====================================================================
    # THE SIX-STEP STORY — steps 1, 5 and 6
    # =====================================================================
    def _strategic_read(self, run_id, name=""):
        """The canonical bounded read for this run (§56).

        ONE object, built once per request from everything the run holds, and
        projected by every step -- WHICH IS NOW TRUE. The docstring has said
        it since it was written and nothing enforced it: ten call sites, no
        memo, and a single executive page composing the whole read three or
        four times over. Each composition walks every retrieved document.

        WHY THAT MATTERS MORE THAN IT LOOKS. MEASURED live on 5e1218e:
        `/runs/<id>/progress` segments that cannot take 100ms -- a dict
        lookup for `owned`, a lock acquire for `avail.in_flight` -- all
        cluster at 88-106ms during analysis, which is the container's CPU
        quota period. The instance is throttled, so every avoidable
        recomposition is paid for in whole 100ms windows that some other
        request spends waiting. Composing this once instead of four times is
        the largest single CPU reduction available on the render path.

        Per REQUEST and on the thread-local, for the same reason the
        readiness memo is: one shared across requests would project one
        visitor's run into another's page. The alternative -- each page composing its
        own -- is what produced a primary screen asserting an industrial
        capacity mechanism about a software network while the X-Ray two
        clicks away read it correctly as subscription software.

        Never raises. A step that has to handle "no read" grows its own
        refusal, and a refusal on the first screen is the defect this whole
        change exists to remove.
        """
        memo = getattr(self._request, "reads", None)
        key = (run_id, name)
        if memo is not None and key in memo:
            return memo[key]
        read = self._compose_strategic_read(run_id, name)
        if memo is not None:
            memo[key] = read
        return read

    def _compose_strategic_read(self, run_id, name=""):
        """`_strategic_read` without the per-request memo."""
        from intent_engine.executive import strategic_read as SR
        from intent_engine.strategic_intelligence.decision import decision_of

        result = self._result(run_id) or {}
        report = result.get("strategic_report") or {}
        observations = [o for o in (report.get("observations") or ())
                        if isinstance(o, dict)]
        meta = self.ci.run_meta(run_id) or {}
        domain = str(meta.get("domain") or result.get("company_domain") or "")
        company = (name or str(meta.get("company_name") or "")
                   or str((self.ci.entity_identity(run_id) or {}).get("name")
                          or "") or domain)
        documents = list(self._retrieved_documents(run_id))
        try:
            run_decision = decision_of(report) if report else None
        except Exception:                                   # noqa: BLE001
            run_decision = None
        dossier = None
        try:
            from intent_engine.demo_dossier.store import (DossierStore,
                                                          company_key)
            key, _cohort, _mv = self._manifest_placement(
                company_key(company or domain or run_id),
                name=company, domain=domain)
            record = DossierStore(self._runtime_root).latest(key)
            dossier = record if isinstance(record, dict) else None
        except Exception:                                   # noqa: BLE001
            dossier = None
        own_words, own_source = self._own_words(observations, company)
        # WHAT KIND OF BUSINESS THIS IS, from the two facts the run already
        # holds. Omitting them is why a company whose 10-K had been read came
        # back "no regulator industry classification was found for it".
        ci_in = self.classification_inputs(run_id, company)
        try:
            read = SR.compose(
                company=company, domain=domain, dossier=dossier,
                run_decision=run_decision, observations=observations,
                documents=documents, own_words=own_words,
                own_words_source=own_source,
                registrant=ci_in["registrant"],
                evidence_text=ci_in["evidence_text"],
                # OWNERSHIP, so the economics are read out of THIS company's
                # filings. A sentence in a rival's 10-K describes the rival.
                subject_cik=self.ci.subject_cik(
                    self.ci.run_meta(run_id) or {}),
                # THE SIMULATION IS PASSED, NOT REBUILT. The belief layer
                # needs the observed trajectory and the trajectory comes from
                # the filed series; deriving it inside `compose` would put a
                # second set of regulator round trips on the critical path of
                # every run. This is the same cached object the history step
                # renders, behind the same outbound-call gate.
                simulation=self._history_simulation(run_id, company))
        except Exception:                                   # noqa: BLE001
            _LOG.exception("strategic_read_compose_failed run=%s", run_id)
            read = SR.compose(company=company, domain=domain)
        # STAGES 3-6 OF §64, BEFORE ANYTHING IS RENDERED. The audit is
        # structural and the repair is targeted; neither reads a model, and
        # neither may add a claim. A failure here returns the unrepaired read
        # rather than no read -- a self-correcting loop that can fail closed
        # is a loop that can delete the product.
        try:
            from intent_engine.product_eval import self_correction as SC
            corrected = SC.correct(read)
            if corrected.repairs:
                _LOG.info("strategic_read_repaired run=%s repairs=%s",
                          run_id, "; ".join(corrected.repairs))
            return corrected.read
        except Exception:                                   # noqa: BLE001
            _LOG.exception("strategic_read_correction_failed run=%s", run_id)
            return read

    def _own_words(self, observations, company):
        """The company's best complete sentence about itself, and its source.

        COMPLETE is the operative word (§23). The old opener took 180
        characters and appended an ellipsis, so the product's first sentence
        trailed off mid-clause. Here the text is cut at a SENTENCE boundary or
        not used at all -- a quotation that stops where the company stopped is
        a quotation; one that stops where the buffer stopped is a bug the
        reader can see.
        """
        import re as _re
        own = ("company_owned", "executive_statement", "investor_material")
        best, source = "", ""
        for obs in observations or ():
            if obs.get("weak") or obs.get("source_class") not in own:
                continue
            text = " ".join(str(obs.get("excerpt") or "").split())
            if len(text.split()) < 10:
                continue
            sentences = _re.split(r"(?<=[.!?])\s+", text)
            kept = []
            for sentence in sentences:
                if not sentence.strip().endswith((".", "!", "?")):
                    break
                kept.append(sentence.strip())
                if sum(len(k) for k in kept) > 240:
                    break
            joined = " ".join(kept).strip()
            # A MISSION STATEMENT IS NOT AN ACCOUNT OF A BUSINESS (§22).
            # "Cloudflare's mission is to help build a better Internet" is
            # correctly attributed, genuinely the company's words, and tells a
            # reader nothing. Quoting it under "in its own words" reintroduced
            # the marketing opener one section further down the same page.
            if _re.search(r"mission is to|our vision|we are on a mission"
                          r"|help build a better|the world'?s leading"
                          r"|welcome to ", joined, _re.I):
                continue
            if len(joined.split()) >= 10 and len(joined) > len(best):
                best = joined
                source = str(obs.get("source_title") or obs.get("origin") or "")
        return best, source

    def _step_guard(self, session, run_id):
        """Ownership and readiness, shared by every step page.

        Returns a response to send INSTEAD of the step, or None to proceed.
        """
        if not self._owned(session, run_id):
            return self._no_such_run(session, run_id)
        availability = self._availability(run_id)
        if self.only_watchable(run_id):
            return self._redirect(f"/runs/{run_id}/progress")
        # ONE RUN MAY NOT SAY TWO THINGS.
        #
        # MEASURED LIVE on 4952649, Meta, run 01M09XM6BQDZAM2XJGE9D0K2W6: SEC
        # EDGAR rate-limited the preview's egress, every source came back 429,
        # and the run FAILED with no report. `/full` and `/slides` said so —
        # they carry this check themselves — and `/intro`, `/story`,
        # `/history` and `/connect` rendered a confident analysis anyway,
        # including a business model ("recurring software subscription") read
        # off the SIC code alone because the filing that would have corrected
        # it was never retrieved.
        #
        # Six pages, one run, two irreconcilable answers, and the four that
        # spoke confidently were the four a customer opens first. The check
        # that `/slides` already had belongs to every step, which is what a
        # SHARED guard is for.
        if availability.get("state") == "FAILED" \
                and not availability.get("has_report"):
            return self._failed_run_page(session, run_id)
        return None

    def _answer_page(self, session, run_id):
        """The sixty-second scrollable decision narrative."""
        blocked = self._step_guard(session, run_id)
        if blocked is not None:
            return blocked
        result = self._result(run_id) or {}
        return self._founder_brief_page(session, run_id, result)

    def _learning_block(self) -> str:
        """The learning ledger, projected onto the story (§54).

        The ledger has always been served in full at /learning-acceleration,
        which is a page a customer reaches only if they already believe the
        system learns. Projecting it into step 1 is how they find out.

        Defensive: no report, no block. A learning panel that renders zeros
        teaches the opposite of what is true.
        """
        try:
            from intent_engine.demo_dossier import learning_bridge as LB
            from intent_engine.founder_brief import steps
            report = LB.load("week")
            return steps.render_learning(report,
                                         LB.activity_versus_learning(report))
        except Exception:                                   # noqa: BLE001
            return ""

    def _intro_page(self, session, run_id):
        """Step 1 (§21–§25). The first thing a customer reads."""
        blocked = self._step_guard(session, run_id)
        if blocked is not None:
            return blocked
        from intent_engine.founder_brief import steps
        _brief, _report, name = self._founder_layers(run_id)
        read = self._strategic_read(run_id, name)
        company = read.company or name
        body = steps.render_intro(read, run_id=run_id, company=company,
                                  learning=self._learning_block(),
                                  identity=self._subject_line(run_id, company))
        return self._html(self._page(f"{company} — introduction", body,
                                     session, session.get("csrf", "")))

    def _history_page(self, session, run_id):
        """Step 5 (§41–§48). The vintage-walled rewind."""
        blocked = self._step_guard(session, run_id)
        if blocked is not None:
            return blocked
        from intent_engine.founder_brief import steps
        _brief, _report, name = self._founder_layers(run_id)
        timeline = self._history_timeline(run_id, name)
        sim = self._history_simulation(run_id, name)
        body = steps.render_history(sim, timeline, run_id=run_id,
                                    company=timeline.company or name)
        return self._html(self._page(f"{name} — history rewind", body,
                                     session, session.get("csrf", "")))

    def _subject_line(self, run_id, company) -> str:
        """§7, §58. Which company this is, in one line a reader can check.

        Only fields a source carries. A country or a ticker that no source
        recorded is absent from the line rather than filled in — the whole
        value of a confirmation line is that everything on it was looked up.
        """
        meta = self.ci.run_meta(run_id) or {}
        listing = self._listing_for(run_id)
        legal = str(meta.get("company_name") or company or "").strip()
        ticker = getattr(listing, "ticker", "") or ""
        country = str(meta.get("country") or "")
        # THE REGISTRY KNOWS WHAT THE RUN DID NOT ASK.
        #
        # A run opened from a typed name carries a name and a domain; the
        # ticker and the country were never part of what it needed, so the
        # confirmation line read "Cloudflare · cloudflare.com" — which does
        # not let a reader confirm anything they did not already type. The
        # suggestion registry holds both and is the same source the entry
        # combobox showed them, so the line they confirm at the end matches
        # the row they chose at the start.
        if not (ticker and country):
            try:
                from intent_engine.company_ingestion import suggest as CS
                match = next(iter(CS.suggest(legal or company, limit=1,
                                             allow_registrant=False)), None)
                if match is not None:
                    ticker = ticker or match.ticker
                    country = country or match.country
                    legal = match.legal_name or legal
            except Exception:                               # noqa: BLE001
                pass
        bits = [b for b in (
            legal if legal and legal != company else "",
            ticker, country,
            str(meta.get("domain") or "").replace("https://", "").replace(
                "http://", "").strip("/"),
            (f"SEC CIK {meta['cik']}" if meta.get("cik") else ""),
        ) if b]
        return " · ".join(dict.fromkeys(bits))

    def _history_simulation(self, run_id, name):
        """The three-line simulation for this run, cached for the process.

        Deliberately built HERE rather than during the analysis: the XBRL
        concept calls are two to four round trips to the regulator, and
        putting them on the critical path of every run would slow the first
        useful screen for the sake of the fifth. Cached because a reader
        moving the date control must never re-dial the SEC, and defensive
        because a chart that raises is worse than one that says what it holds.
        """
        from intent_engine.executive import history_simulator as HS
        cached = getattr(self, "_simulations", None)
        if cached is None:
            cached = self._simulations = {}
        if run_id in cached:
            return cached[run_id]
        profile = selection = None
        try:
            from intent_engine.executive.analysis_selection import select
            meta = self.ci.run_meta(run_id) or {}
            ci_in = self.classification_inputs(run_id, name)
            selection = select(name=name, domain=str(meta.get("domain") or ""),
                               registrant=ci_in["registrant"],
                               evidence_text=ci_in["evidence_text"])
            profile = selection.profile
        except Exception:                                   # noqa: BLE001
            pass
        # THE OUTBOUND CALL IS OFF UNDER TEST, AND OPTED INTO EXPLICITLY.
        #
        # The financial series is two to four requests to the regulator. Left
        # ungated, every webapp test that renders a history page made them —
        # the suite went from ten minutes to over an hour, which is how the
        # omission announced itself. `env == "test"` is the honest gate: a
        # test must never make an outbound call whatever transport it was or
        # was not given.
        #
        # The local product harnesses are a real exception rather than a
        # loophole: they drive the whole customer journey against live
        # sources on purpose, and they set the variable to say so.
        cik = self._filer_cik(run_id, name) if self._xbrl_allowed() else ""
        try:
            sim = HS.build(company=name, cik=cik, profile=profile,
                           selection=selection, transport=self._transport,
                           resolver=self._resolver)
        except Exception:                                   # noqa: BLE001
            _LOG.warning("history simulation not built for %s", run_id)
            sim = HS.Simulation(company=name, coverage=(
                "The dated financial record could not be read on this "
                "request."))
        cached[run_id] = sim
        return sim

    def _modeled_expectation(self, run_id, name):
        """§15. The expectation the published record implies, or None.

        None is a real answer and reaches a passage that says so: a company
        with no multi-year filed series has nothing to model from, and
        producing a number anyway is the one thing the whole resolution
        ladder exists to forbid.
        """
        from intent_engine.executive import history_simulator as HS
        try:
            return HS.present_expectation(
                self._history_simulation(run_id, name), company=name)
        except Exception:                                   # noqa: BLE001
            _LOG.warning("modelled expectation not built for %s", run_id)
            return None

    #: Set by the product harnesses (`golden_cycle`, `golden_wave`,
    #: `surface_matrix`), which drive the real journey against real sources.
    XBRL_OPT_IN = "INTENT_ENGINE_ALLOW_XBRL"

    def _xbrl_allowed(self) -> bool:
        if self.config.env != "test":
            return True
        return os.environ.get(self.XBRL_OPT_IN, "").strip() == "1"

    def _filer_cik(self, run_id, name="") -> str:
        """The CIK OF THE SUBJECT, or nothing.

        THE DEFECT THIS REPLACES, WHICH WAS THE WORST ONE IN THE CYCLE.
        The first version took the CIK out of any SEC URL the run had
        fetched. That is safe only if every SEC document a run holds was
        filed BY the subject, and it is not: a third party's 10-K that
        mentions the subject once as a vendor is legitimate independent
        evidence and is retrieved on purpose. For Stripe — a private company
        that files no annual report — the run held exactly such a filing, and
        the history chart drew SOMEBODY ELSE'S nine-year revenue history
        under the heading "Stripe — the strategy simulator". Index 22, then
        2301, then 306. A chart of the wrong company is the worst thing this
        product can emit, and it arrived through a URL.

        So identity is now asserted from a source that is ABOUT the subject:

          1. the CIK the run was OPENED on, which the regulator gave us for
             this company by name;
          2. failing that, the registrant table, and only when the filer it
             returns carries the subject's name.

        There is no third rung. A company with no verified CIK gets no chart
        and the bounded fallback instead, which for a private company is the
        correct and honest answer rather than a degraded one.
        """
        meta = self.ci.run_meta(run_id) or {}
        recorded = "".join(ch for ch in str(meta.get("cik") or "")
                           if ch.isdigit())
        if recorded:
            return recorded
        subject = str(name or meta.get("company_name") or "").strip()
        # 2. A SEC URL from a document that is the SUBJECT'S OWN FILING.
        #
        # The discriminator the first version was missing, and it was already
        # in the data: `propose_edgar_candidates` resolves the CIK from the
        # company's NAME and marks what it retrieves `investor_material`,
        # while `third_party_filings` — the path that found the Aether 10-K
        # mentioning Stripe — marks its results `competitor`. Same host, same
        # URL shape, opposite meaning. Reading the class instead of the URL
        # is what separates "this company's own annual report" from "somebody
        # else's annual report that says this company's name once".
        own = {"investor_material", "company_owned", "executive_statement"}
        from intent_engine.executive import history_rewind as HR
        mine = [str(d.get("final_url") or d.get("original_url") or "")
                for d in self._retrieved_documents(run_id)
                if isinstance(d, dict)
                and str(d.get("source_class") or "") in own]
        harvested = HR.cik_from_urls(mine)
        if harvested:
            return harvested
        # THE SAME PREDICATE AS THE SERIES ITSELF, NOT A SECOND ONE.
        #
        # This rung was gated on `env == "test"` while the series it feeds
        # was gated on `_xbrl_allowed()`. The local product harness opts into
        # the outbound call and is still env="test", so it passed the second
        # gate and failed the first: Palantir, which has nine years of filed
        # results, drew no chart because this run happened to hold none of
        # its own SEC filings. Two gates for one decision is how a capability
        # ends up switched half on.
        if not subject or not self._xbrl_allowed():
            return ""
        try:
            from intent_engine.company_ingestion.edgar import resolve_cik
            found = resolve_cik(subject, transport=self._transport,
                                resolver=self._resolver)
        except Exception:                                   # noqa: BLE001
            return ""
        if not found:
            return ""
        # The registrant table matches on token containment, which is right
        # for finding a filer and not sufficient for trusting one. The filer
        # must carry the subject's leading word, or this is a different
        # company with an overlapping name.
        head = subject.split(",")[0].split(" Inc")[0].strip().lower()
        title = str(found.get("title") or "").lower()
        if head and head.split()[0] not in title:
            _LOG.warning("registrant %r does not match subject %r; no "
                         "financial series will be drawn", title, subject)
            return ""
        return str(found.get("cik") or "")

    def _history_timeline(self, run_id, name):
        """The dated record for this company, cached for the process.

        EDGAR's submissions document is one request and it is the only
        per-company dated series a first run can reach. It is cached because
        a reader moving the slider must not re-dial the SEC, and it is
        defensive because a history page that 500s is worse than a history
        page that says it holds nothing.
        """
        from intent_engine.executive import history_rewind as HR
        cached = getattr(self, "_timelines", None)
        if cached is None:
            cached = self._timelines = {}
        if run_id in cached:
            return cached[run_id]
        documents = list(self._retrieved_documents(run_id))
        filings = ()
        # THE SAME IDENTITY RULE AS THE CHART, FOR THE SAME REASON.
        #
        # `cik_from_urls` reads a CIK out of whatever SEC URL the run holds,
        # and a run legitimately holds third-party filings that merely
        # mention the subject. That put another filer's dated history under
        # this company's timeline exactly as it put another filer's revenue
        # under its chart — one bug, two surfaces, and only the chart made it
        # obvious because a wrong number looks wrong and a wrong date does
        # not.
        cik = self._filer_cik(run_id, name)
        if cik:
            try:
                from intent_engine.company_ingestion.edgar import submissions
                filings = HR.filings_from_submissions(submissions(cik),
                                                      limit=90)
            except Exception:                               # noqa: BLE001
                filings = ()
        if not filings:
            filings = HR.filings_from_documents(documents)
        read_selection = None
        profile = None
        try:
            from intent_engine.executive.analysis_selection import select
            meta = self.ci.run_meta(run_id) or {}
            ci_in = self.classification_inputs(run_id, name)
            read_selection = select(name=name,
                                    domain=str(meta.get("domain") or ""),
                                    registrant=ci_in["registrant"],
                                    evidence_text=ci_in["evidence_text"])
            profile = read_selection.profile
        except Exception:                                   # noqa: BLE001
            pass
        timeline = HR.build(company=name, filings=filings, profile=profile,
                            selection=read_selection)
        cached[run_id] = timeline
        return timeline

    def _connect_page(self, session, run_id):
        """Step 6 (§49–§52). Public demo becomes product."""
        blocked = self._step_guard(session, run_id)
        if blocked is not None:
            return blocked
        from intent_engine.founder_brief import steps
        _brief, _report, name = self._founder_layers(run_id)
        read = self._strategic_read(run_id, name)
        company = read.company or name
        csrf = session.get("csrf", "")
        sent = self._has_feedback(run_id)
        body = steps.render_connect(
            read, run_id=run_id, company=company,
            feedback=self._full_feedback_form(run_id, csrf, sent=sent))
        return self._html(self._page(f"{company} — connect your company",
                                     body, session, session.get("csrf", "")))

    def _story_page(self, session, run_id):
        # STEP 4 WAS THE ONE THAT KEPT ITS OWN OWNERSHIP CHECK and therefore
        # never got the readiness one. Measured live on c719979, Meta, run
        # 01M09Z896GA620CSBXEA5847Q3: five of six steps correctly showed the
        # failure page and `/story` rendered 5,241 characters of narrative
        # for a run that retrieved nothing. A guard six pages share is worth
        # nothing to the page that does not call it.
        blocked = self._step_guard(session, run_id)
        if blocked is not None:
            return blocked
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
        # THE NARRATIVE IS COMPOSED FROM THE CANONICAL READ (§39), and the
        # run's own sections are supporting material below it. The other way
        # round is what produced a step-4 page whose "business story" section
        # contained the single word "company".
        from intent_engine.founder_brief import steps
        read = self._strategic_read(run_id, name)
        substantive = [s for s in sections
                       if len(" ".join(getattr(s, "paragraphs", ()) or ())) > 80]
        extra = (fr.render_story(substantive, run_id=run_id)
                 + fr.render_actions(actions)) if substantive else \
            fr.render_actions(actions)
        body = (f'{fr.BRIEF_CSS}'
                + steps.render_story(
                    read, self._history_timeline(run_id, name),
                    run_id=run_id, company=read.company or name, extra=extra))
        return self._html(self._page(f"{name} — the full story", body,
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

    #: SURFACES THAT MUST CARRY "ASK A FOLLOW-UP", declared once.
    #:
    #: MEASURED LIVE on 517180e6 with Microsoft: Q&A appeared on 3 of 9
    #: surfaces -- `/answer`, `/full`, `/slides` had it; `/brief`, `/xray`,
    #: `/dashboard`, `/intro`, `/evidence`, `/sources` did not. That is what
    #: per-page mounting produces: nobody decided `/brief` should be mute, it
    #: was simply never edited.
    #:
    #: So the mount is DECLARATIVE and happens at the route, and this tuple is
    #: read by both the router and the test. A new report page cannot develop
    #: a `/brief`-shaped hole without failing the surface test, and the
    #: question of whether a surface should answer questions is settled here
    #: rather than in six separate render functions.
    #:
    #: `sources` and the per-item evidence pages are deliberately absent: they
    #: inspect one document's provenance, and a question asked there is a
    #: question about the analysis, which is one click away on every one of
    #: them.
    ASK_SURFACES = ("intro", "answer", "brief", "xray", "dashboard", "story",
                    "slides", "full", "evidence")

    def _with_ask(self, session, run_id, response):
        """Mount the ONE canonical Q&A component on a rendered report page.

        Injected rather than passed in, because the alternative is editing
        every page function and remembering to edit the next one. The form is
        identical on every surface -- same component, same route, same
        context -- so a reader who has learned it in one place has learned it
        everywhere.

        Fails open: a page that cannot build the form is still a page. Losing
        the follow-up box costs a feature; raising here would cost the report.
        """
        try:
            status, headers, body = response
        except (TypeError, ValueError):
            return response
        if not isinstance(body, str) or "</main>" not in body:
            return response
        if "/conversation" in body:
            return response          # a page that already mounts it
        # OWNERSHIP, BECAUSE THIS READS RUN DATA. The wrapped handler has
        # already checked -- but this function calls `_founder_layers(run_id)`
        # itself to build company-specific suggestions, so it is a reader of
        # the run in its own right. A future route that wraps a page which
        # forgot to check would otherwise leak one company's questions onto
        # another reader's screen, and the wrapper is exactly the place nobody
        # would think to look.
        if not self._owned(session, run_id):
            return response
        try:
            _b, report, _n = self._founder_layers(run_id)
            section = self._ask_form(run_id, report, session)
        except Exception:                                   # noqa: BLE001
            return response
        return status, headers, body.replace("</main>", section + "</main>", 1)

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
        # THE SHARED GUARD FIRST. This page had the failed-run check written
        # into it, which is how four other steps came to be missing it; the
        # check now lives in one place and this one calls it like the rest.
        blocked = self._step_guard(session, run_id)
        if blocked is not None:
            return blocked
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
            if self.only_watchable(run_id):
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
                              documents=self.ci.store.retrieved(run_id),
                              read=self._strategic_read(run_id))
        if not deck_is_presentable(slides):
            # Better to say so than to hand someone a three-slide deck in a
            # meeting after promising a presentation.
            from intent_engine.founder_brief import flow
            body = (
                f'<main>'
                f'<h1>Not enough for a presentation</h1>'
                f'<p>This analysis supports '
                f'{meaningful_slide_count(slides)} substantive slide(s), and a '
                f'presentation needs at least 5. The brief and the full '
                f'analysis contain everything that was found.</p>'
                f'<p><a href="/runs/{_e(run_id)}/brief">Read the executive '
                f'brief</a> · <a href="/runs/{_e(run_id)}/full">Full '
                f'analysis</a></p>{flow.nav(run_id, "slides")}</main>')
            return self._html(self._page("Presentation unavailable", body,
                                         session, csrf))
        deck = render_deck(slides, company=report.get("company_name", ""),
                           as_of=as_of, analysis_version=version,
                           run_id=run_id, csrf=csrf,
                           full_analysis_url=f"/runs/{run_id}/full",
                           cite_labels=self._citation_labels(run_id))
        from intent_engine.founder_brief import flow
        body = (f'<main>{deck}{flow.nav(run_id, "slides")}</main>')
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

    #: What a leaked constant looks like: SHOUTING words joined by
    #: underscores. Single all-caps words are NOT constants by shape -- USA,
    #: 10-K and META all are that -- so the ones that are states are mapped
    #: by name below instead.
    #: Internal state names, in the reader's words.
    #:
    #: MEASURED on Meta's live `/evidence` at b0ec8cb: "Search coverage:
    #: DISCOVERY_PARTIAL · reading: HAVE_INDEPENDENT" and "Relevance:
    #: DIRECTLY_RELEVANT · Counts as corroboration: yes". Those are internal
    #: enum constants printed as customer copy, on the one page whose whole
    #: job is to make a hostile reader trust the evidence.
    #:
    #: Mapped explicitly rather than transformed. A generic
    #: `.replace("_", " ").lower()` turns DISCOVERY_PARTIAL into "discovery
    #: partial", which is not English and still reads as a leaked constant;
    #: and it would quietly invent wording for states nobody has looked at.
    #: The fallback exists so an UNMAPPED state degrades to something
    #: readable instead of shouting, but the guard below is what stops one
    #: going unnoticed.
    _PLAIN_STATE = {
        "DISCOVERY_NOT_RUN": "no search was run",
        "DISCOVERY_PARTIAL": "partial — more sources remain unread",
        "DISCOVERY_ADEQUATE": "adequate for this reading",
        "DISCOVERY_EXHAUSTED": "exhausted — everything findable was read",
        "DISCOVERY_BLOCKED": "blocked — sources refused automated access",
        "HAVE_INDEPENDENT": "independent corroboration found",
        # THE DISTINCTION THIS PRODUCT EXISTS TO KEEP. A zero is either a
        # fact about the company or a limit of our search, and these two
        # states are how they are told apart. Mapped by hand rather than
        # left to the fallback: "failed to find" and "found none" happen to
        # be readable English, but a distinction this load-bearing must not
        # depend on a generic transform producing acceptable words.
        "FAILED_TO_FIND": "none retrieved — a limit of our search, "
                          "not a finding about the company",
        "FOUND_NONE": "searched thoroughly and none exists",
        "PARTIALLY_INDEPENDENT": "partly corroborated by independent sources",
        "NO_INDEPENDENT": "no independent corroboration yet",
        "DIRECTLY_RELEVANT": "directly about this company",
        "DECISION_RELEVANT": "bears on the decision",
        "CLAIM_RELEVANT": "supports a specific claim",
        "CONTEXTUALLY_RELEVANT": "background context",
        "WEAKLY_RELEVANT": "weakly related",
        "IRRELEVANT": "not relevant",
        "CURRENT": "current",
        "STALE": "out of date",
    }

    @classmethod
    def _plain_state(cls, value) -> str:
        """A state name a reader can act on, never the constant itself."""
        raw = str(value or "").strip()
        if not raw:
            return ""
        if raw in cls._PLAIN_STATE:
            return cls._PLAIN_STATE[raw]
        # ONLY UNDERSCORE-JOINED CONSTANTS. A first version also lowered any
        # all-caps word over three characters, and its own control caught it
        # rewriting "10-K" to "10-k" -- this runs over every record on the
        # page, so a form type, a country or a ticker would have been
        # quietly corrupted to hide a constant nobody had leaked.
        if _CONSTANT_SHAPED.match(raw):
            return raw.replace("_", " ").lower()
        return raw

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
              f'{_e(self._plain_state(reading["coverage"]))} · reading: '
              f'{_e(self._plain_state(reading["reading"]))}</p>'
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
                if key == "freshness":          # CURRENT / STALE are internal
                    value = self._plain_state(value)
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
                  f'Relevance: '
                  f'{_e(self._plain_state(rec.get("relevance")))} · '
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
            + "".join(windows)
            + self._econ_decision_block()
            + self._collective_block()
            + '</main></body></html>')
        return self._html(body)

    def _econ_decision_block(self) -> str:
        """§39: what the economic layer knows, and what it has not yet earned.

        OPERATOR-FACING, so the enums stay. §41's rule is about CUSTOMER
        surfaces; an operator debugging why a company abstained needs the
        refusal code, not a translation of it.

        THE CALIBRATION LINE IS THE POINT. It states PRE-CALIBRATION and the
        number of RESOLVED forward predictions, which is zero, and it may not
        contain a percentage -- an accuracy figure with an empty denominator
        is the claim this whole programme exists to not make. The rehearsal
        ledger is a different file and this reads the real store only.
        """
        import datetime as _dt
        from intent_engine.econ import founder_contract as FC
        from intent_engine.external_intel import econ_context as EC
        from intent_engine.external_intel import econ_decision as ED
        today = _dt.date.today().isoformat()
        try:
            context = EC.load(self._runtime_root, as_of=today)
        except Exception:                                   # noqa: BLE001
            context = None
        if context is None or not context.available:
            reason = getattr(context, "reason", "") or \
                "the shared economic state could not be read"
            return ('<section class="card"><h2>Economic decision layer</h2>'
                    f'<p class="none">{_e(reason)}</p></section>')
        fresh, age = FC.freshness_of(context.as_of, at=today)
        known = [v for v in context.conditions.values() if v.get("known")]
        moving = [v for v in known if v.get("direction") in ("UP", "DOWN")]
        try:
            exps, calibration, counts = ED.forward_status(self._runtime_root,
                                                          at=today)
        except Exception:                                   # noqa: BLE001
            exps, calibration, counts = [], FC.PRE_CALIBRATION, {}
        supported = [b for b in context.beliefs
                     if str(b.get("status", "")).upper().startswith(
                         "SUPPORTED")]
        candidate = [b for b in context.beliefs if b not in supported]
        def _row(v) -> str:
            value = v.get("value")
            shown = f"{value:g}" if isinstance(value, (int, float)) else ""
            prior = str(v.get("prior_as_of", "")) or "no earlier reading"
            return (f'<li>{_e(str(v.get("kind", "")))}: '
                    f'{_e(str(v.get("direction", "")))} to {_e(shown)} '
                    f'(as of {_e(str(v.get("as_of", "")))}, from {_e(prior)})'
                    f'</li>')

        rows = "".join(
            _row(v) for v in
            sorted(known, key=lambda x: str(x.get("kind", "")))[:14])
        forward = "".join(
            f'<li>{_e(x.quantity)} {_e(x.expected_direction)} by '
            f'{_e(x.expires_at)}</li>' for x in exps[:3])
        return (
            '<section class="card"><h2>Economic decision layer</h2>'
            f'<p class="verdict"><strong>{_e(fresh)}</strong> — the shared '
            f'state is dated {_e(context.as_of)} and is '
            f'{_e("1 day" if age == 1 else f"{age} days")} old.</p>'
            f'<ul class="counts">'
            f'<li>{len(known)} condition(s) measured of '
            f'{_e(str((context.uncertainty or {}).get("vocabulary", "?")))} '
            f'in the vocabulary</li>'
            f'<li>{len(moving)} moved; {len(known) - len(moving)} did '
            f'not</li>'
            f'<li>{len(supported)} supported relation(s), '
            f'{len(candidate)} candidate — a candidate is tracked and is '
            f'never stated as a finding</li>'
            f'<li>{_e(str(counts.get("open", 0)))} forward prediction(s) '
            f'open, {_e(str(counts.get("resolved", 0)))} resolved</li>'
            f'<li>CALIBRATION: {_e(calibration)} — no prediction has come '
            f'due, so there is no accuracy figure and none is shown</li>'
            f'<li>rehearsal results are held in a separate ledger this '
            f'surface does not read</li>'
            f'</ul>'
            + (f'<h3>What is being tracked</h3><ul>{forward}</ul>'
               if forward else "")
            + f'<h3>Conditions</h3><ul class="counts">{rows}</ul>'
            '</section>')

    def _collective_block(self) -> str:
        """Section 49: what the engine believes people are doing differently.

        THREE NUMBERS, ALWAYS TOGETHER. Measured, usable and promoted are
        almost never equal, and a panel showing only the first would present
        effort as if it were result -- the same mistake the window panel
        above refuses to make with arrival counts.

        THE EMPTY CASE IS THE INTERESTING ONE TODAY. One construct of sixteen
        is measurable, and rendering that as a blank section would read as
        "nothing to report" rather than "the layer is built and starved".
        So the block always renders, and always names the reason.
        """
        try:
            from intent_engine.econ import dashboard as CD
            # An ATTRIBUTE, set in __init__, not a method. Calling it would
            # raise TypeError, which the except below would swallow into a
            # permanently blank panel -- the silent-zero shape this codebase
            # has shipped before.
            payload = CD.build(self._runtime_root)
        except Exception:                                   # noqa: BLE001
            return ""
        if not payload.get("available"):
            return ""
        h = payload["headline"]
        inc = payload["incremental_value"]

        rows = []
        for pop in payload.get("populations", []):
            who = (pop.get("population") or {}).get("name", pop.get("key"))
            for r in pop.get("readings", []):
                moved = r.get("moved")
                move = ("" if moved is None
                        else f' <span class="none">({moved:+.3f} since the '
                             f'previous estimate)</span>')
                rows.append(
                    f'<li>{_e(r["sentence"])}{move}<br>'
                    f'<span class="none">{_e(r["promotion_state"])} — '
                    f'{_e(r["meaning"])}</span></li>')
        readings = ("<ul>" + "".join(rows) + "</ul>" if rows else
                    '<p class="none">No population has a usable reading in '
                    'this store yet.</p>')

        if inc.get("status") == "MEASURED":
            delta = inc.get("incremental_delta")
            value = (
                f'<h3>Base economic model vs base + collective state</h3>'
                f'<ul class="counts">'
                f'<li>base economic model: '
                f'{_e(str(inc.get("base_economic_model_score")))}</li>'
                f'<li>base + collective state: '
                f'{_e(str(inc.get("base_plus_collective_score")))}</li>'
                f'<li><strong>incremental delta: {_e(str(delta))}</strong> '
                f'({_e(str(inc.get("robust_improvements")))} robust of '
                f'{_e(str(inc.get("tested")))} tested)</li></ul>')
        else:
            value = (f'<h3>Base economic model vs base + collective state</h3>'
                     f'<p class="none">{_e(inc.get("reason", ""))}</p>')

        retired = "".join(
            f'<li>{_e(r["dimension"])} — {_e(r["reason"])}</li>'
            for r in payload.get("retired", []))
        reality = payload.get("measurement_reality", {})
        blocked = reality.get("dimensions_blocked_by_data", {})
        blocked_html = "".join(
            f'<li>{_e(d)}: {_e("; ".join(v)[:180])}</li>'
            for d, v in sorted(blocked.items()))

        return (
            '<section class="card"><h2>What people appear to be doing '
            'differently</h2>'
            f'<p class="verdict">{_e(payload.get("verdict", ""))}</p>'
            f'<ul class="counts">'
            f'<li>{_e(str(h["vocabulary"]))} constructs declared; '
            f'{_e(str(h["with_a_proxy"]))} have a proxy; '
            f'{_e(str(h["measurable_today"]))} can be measured with the data '
            f'this deployment can actually read</li>'
            f'<li>{_e(str(h["measured"]))} currently measured, '
            f'{_e(str(h["promoted"]))} promoted, '
            f'{_e(str(h["retired"]))} tested and removed</li></ul>'
            + readings + value
            + (f'<h3>Removed for adding no predictive value</h3>'
               f'<ul>{retired}</ul>' if retired else "")
            + (f'<h3>Cannot be measured here, and why</h3>'
               f'<ul>{blocked_html}</ul>' if blocked_html else "")
            + '</section>')

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
            return self._no_such_run(session, run_id)
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
            return self._no_such_run(session, run_id)
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
                                    decision=self._composed_decision(run_id),
                                    engine_answer=engine_text,
                                    observations=observations,
                                    trust=_trust,
                                    # D31: the canonical read, so Q&A cannot
                                    # deny a falsifier step 1 is showing.
                                    read=self._strategic_read(run_id),
                                    # §22: ONE economic object across brief,
                                    # full analysis and Q&A. Three surfaces
                                    # answering an economic question from
                                    # three derivations is three products.
                                    econ=self._founder_economic_context(
                                        run_id))
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
            return self._no_such_run(session, run_id)
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
            return self._no_such_run(session, run_id)
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
            return self._no_such_run(session, run_id)
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
            # TRUTHFUL, AND NOT AN INFRASTRUCTURE REPORT. The previous copy
            # was honest but explained OUR hosting at the foot of someone
            # else's report; the operator detail stays at /readyz, where the
            # person who can act on it looks. The gate itself is unchanged:
            # this deployment may not promise to keep what it is sent, so it
            # does not ask.
            return (
                f'<section class="fb" aria-label="Feedback"><h2>Feedback</h2>'
                f'<p>Feedback is temporarily unavailable in this preview '
                f'environment.</p></section>')
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

    def _has_feedback(self, run_id) -> bool:
        """Whether THIS run already carries feedback. Never raises.

        Scoped to the run, which is scoped to the session that owns it — the
        confirmation must not be derivable from anyone else's submission
        (§49, §82). A read that fails costs the confirmation line, never the
        page.
        """
        try:
            return bool(self.feedback_log.find(run_id=run_id))
        except Exception:                                   # noqa: BLE001
            return False

    def _full_feedback_form(self, run_id, csrf, *, sent=False) -> str:
        """§46-§49. The whole workflow, on the step that closes the demo.

        Deliberately more than a rating. A three-value "was this useful?" tells
        an operator that something was wrong and nothing about what, which is
        why the tags exist and why each one maps to a defect class the repair
        loop already clusters on — a customer saying "too generic" and the
        machine rubric finding TEMPLATE_COLLAPSE are the same defect from two
        sides.

        Every field except the score is optional. A form that demands five
        answers collects none.
        """
        from intent_engine.webapp.feedback import TAGS
        if not self.feedback_available():
            return (
                '<section class="fbx" aria-labelledby="fbh">'
                '<h2 id="fbh">Tell us what this was worth</h2>'
                '<p>Feedback is switched off on this deployment — we could '
                'not promise to keep what you sent, and asking anyway would '
                'be worse than not asking. Nothing you typed here would '
                'survive the next restart, so the form is not shown rather '
                'than shown and quietly discarded.</p></section>')
        thanks = ('<p class="fb-ok" role="status">Recorded — and read. '
                  'It is kept against this analysis so the next version of '
                  'it can be measured against what you said.</p>'
                  ) if sent else ''
        tags = "".join(
            f'<label class="tag"><input type="checkbox" name="tag" '
            f'value="{_e(key)}" aria-label="{_e(label)}"> {_e(label)}'
            f'</label>' for key, label in TAGS)
        # Each control announces its MEANING, not its number. "5" read aloud
        # on its own tells a screen-reader user nothing about which end of
        # the scale they are on.
        meaning = {1: "not useful at all", 2: "slightly useful",
                   3: "somewhat useful", 4: "useful",
                   5: "useful enough to act on"}
        scores = "".join(
            f'<label class="sc"><input type="radio" name="score" '
            f'value="{n}" required aria-label="{n} — {meaning[n]}"> {n}'
            f'</label>' for n in range(1, 6))
        return (
            f'<section class="fbx" aria-labelledby="fbh"><h2 id="fbh">'
            f'Tell us what this was worth</h2>{thanks}'
            f'<form action="/runs/{_e(run_id)}/feedback" method="post">'
            f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
            f'<input type="hidden" name="page" value="connect">'
            f'<fieldset><legend>How useful was this analysis?</legend>'
            f'<p class="scale"><span>Not useful</span>{scores}'
            f'<span>Would act on it</span></p>'
            f'<input type="hidden" name="useful" value="partly"></fieldset>'
            f'<fieldset><legend>What describes it? (optional)</legend>'
            f'<div class="tags">{tags}</div></fieldset>'
            f'<p><label for="fb_useful">What was most useful?</label>'
            f'<input id="fb_useful" name="most_useful" maxlength="2000"></p>'
            f'<p><label for="fb_missing">What was missing?</label>'
            f'<input id="fb_missing" name="what_was_missing" '
            f'maxlength="2000"></p>'
            f'<p><label for="fb_wrong">What looked wrong?</label>'
            f'<input id="fb_wrong" name="what_looked_wrong" '
            f'maxlength="2000"></p>'
            f'<p><label for="fb_decision">What decision would you use this '
            f'for?</label><input id="fb_decision" name="decision_use" '
            f'maxlength="2000"></p>'
            f'<fieldset><legend>Would you connect your own internal '
            f'context?</legend>'
            f'<label><input type="radio" name="would_connect" value="yes"> '
            f'Yes</label> <label><input type="radio" name="would_connect" '
            f'value="maybe"> Maybe</label> '
            f'<label><input type="radio" name="would_connect" value="no"> '
            f'No</label></fieldset>'
            f'<p><label for="fb_note">Anything else</label>'
            f'<input id="fb_note" name="note" maxlength="4000"></p>'
            f'<button type="submit">Send feedback</button>'
            f'<p class="fb-priv">Your feedback is tied to this session and '
            f'this analysis. It is not shown to other visitors, and sending '
            f'it is not permission to quote you.</p>'
            f'</form></section>')

    def _feedback(self, session, run_id, form):
        if not self._owned(session, run_id):
            return self._no_such_run(session, run_id)
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
                user_id=session["user_id"],
                # `cand` is the only key `_form` joins on commas, so a
                # multi-checkbox field arrives as its first value only. The
                # tag list is posted under a name the parser splits itself.
                score=(form.get("score") or "")[:1],
                tags=[t for t in (form.get("tag") or "").split(",") if t],
                most_useful=form.get("most_useful", ""),
                what_was_missing=form.get("what_was_missing", ""),
                what_looked_wrong=form.get("what_looked_wrong", ""),
                decision_use=form.get("decision_use", ""),
                would_connect=form.get("would_connect", ""))
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
    def _recommended_candidate_ids(cls, candidates, *, refusing_hosts=(),
                                   subject_cik=""):
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

        # A GUESS AT A CLOSED DOOR IS NOT WORTH A REQUEST, and ranking it last
        # was not enough to stop it being made.
        #
        # MEASURED on 743df06. The comment above already says a guess aimed at
        # a host we have watched refuse us "cannot succeed" -- but rank 9 is
        # still eligible, and the leftover fill spends the unused budget on
        # exactly these once the real candidates run out. Which is what
        # happened to every blocked company in the gauntlet:
        #
        #     Union Pacific  failed=27, 24 of them at up.com
        #     Goldman Sachs  failed=26, 24 of them at goldmansachs.com
        #     Mastercard     failed=24, 22 of them at mastercard.com
        #     Costco         failed=23, 21 of them at costco.com
        #
        # Twenty-odd requests per run to a host that had already refused the
        # homepage, each one waiting out a refusal or a timeout before the
        # customer sees anything. It is the largest single avoidable cost in
        # first-useful latency, and it buys nothing.
        #
        # THE EXEMPTIONS ARE THE ONES THE RANKING ALREADY ARGUES FOR: a
        # curated URL a human asserted, a regulatory filing, and a filing by
        # another registrant are worth trying on a host that turned us away.
        # Only the guesses are dropped.
        def _is_a_guess_at_a_closed_door(candidate) -> bool:
            if not _on_refusing_host(candidate):
                return False
            method = candidate.get("discovery_method")
            if method in ("official_fallback", "third_party_filing"):
                return False
            if "SEC EDGAR" in (candidate.get("why_relevant") or ""):
                return False
            return True

        candidates = [c for c in candidates
                      if not _is_a_guess_at_a_closed_door(c)]

        #: The subject's own CIK, as ten digits, or "". Ownership of an EDGAR
        #: document is stated by its URL -- `/edgar/data/<CIK>/...` names the
        #: FILER -- so it is decided here rather than inferred from a
        #: source_class, which says what KIND of document it is and never
        #: whose it is.
        subject_cik = "".join(ch for ch in str(subject_cik or "")
                              if ch.isdigit()).lstrip("0")

        def _filed_by_subject(candidate) -> bool:
            import re as _re
            match = _re.search(r"/edgar/data/(\d+)",
                               str(candidate.get("url") or ""))
            if not match or not subject_cik:
                return False
            return match.group(1).lstrip("0") == subject_cik

        def _relevance_first(candidate):
            method = candidate.get("discovery_method")
            why = candidate.get("why_relevant", "")
            if method == "official_fallback":
                return 0
            # A THIRD PARTY'S FILING MAY NOT TAKE THE SUBJECT'S SLOT.
            #
            # `third_party_filing` and the subject's own EDGAR filing both
            # returned 1, so they competed on equal footing. For a company
            # with a domain that is survivable -- homepage and sitemap
            # candidates fill the other families. For a company with NO domain
            # on record the entire pool is EDGAR, and the two ranks interleave.
            #
            # MEASURED LIVE on 49b6c3a and 517e7ae. Meta Platforms is the one
            # Wave-1 company with no domain, and its run read seven sources of
            # which four were other registrants:
            #
            #     1326801  Meta Platforms          the subject
            #     1849056  Oklo Inc.
            #      895728  Enbridge Inc
            #     1065078  Network-1 Technologies
            #     1384905  RingCentral, Inc.
            #
            # One usable source, below the floor, and the customer was shown
            # "this analysis could not be completed" for one of the most
            # heavily documented companies in the world. The filings were not
            # wrong to be found -- each does mention Meta -- they were wrong to
            # displace Meta's own 10-K and 10-Q.
            #
            # So ownership ranks ahead of relevance: the subject's own filing
            # first, a third party's mention of the subject well behind the
            # company's own web sources, never level with it.
            if "SEC EDGAR" in why and _filed_by_subject(candidate):
                return 1
            # ONLY WHERE OWNERSHIP CAN ACTUALLY BE DECIDED.
            #
            # The first version of this demoted every `third_party_filing`
            # unconditionally, and broke three guards that had nothing to do
            # with the subject: with NO subject CIK on the run, a filing an
            # index returned is still the best ATTESTED source in the
            # independent family, and "attested beats guessed" is a separate
            # invariant with its own measured defect behind it (10 of 10
            # slots to a guessed g2.com URL). Demoting it there did not make
            # the subject's filings win -- there were none in the pool -- it
            # just handed the slot back to the guess.
            #
            # So ownership only ranks where ownership is KNOWN. Without a
            # subject CIK this rule has no opinion.
            if subject_cik and not _filed_by_subject(candidate) and (
                    method == "third_party_filing" or "SEC EDGAR" in why):
                return 6
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
    #:
    #: FIFTEEN MINUTES WAS NOT A SAFETY MARGIN, IT WAS THE BUG. This check
    #: only ever fires for a run that is NOT in `_analysis_inflight` -- and
    #: the in-flight entry is written before the work is submitted, so a run
    #: missing from it has no worker in this process at all. Its worker is
    #: provably gone. Waiting another quarter of an hour to say so is how a
    #: restarted instance produced a page that polled itself forever.
    #:
    #: Three minutes is still generous against the 60s/120s hard budgets: it
    #: is longer than any run is allowed to take, so a live run can never be
    #: mistaken for a dead one.
    STALE_ATTEMPT_SECONDS = 180

    TERMINAL_STATES = ("COMPLETE", "PARTIAL", "FAILED", "REJECTED",
                       "INTERRUPTED")

    #: §22. Seconds held back from the interactive budget for composition.
    #: Letting acquisition spend the whole budget would push the ANSWER past
    #: the hard deadline -- the customer would have waited the full 60s and
    #: still be handed a spinner, which is the exact failure this exists to
    #: remove.
    #:
    #: THIS NUMBER IS CALIBRATED AGAINST LOCAL HARDWARE AND IS WRONG ON THE
    #: PREVIEW. It was set from "composition costs 7-11s locally and is pure
    #: CPU, so it is the one stage whose duration we can predict". The premise
    #: holds; the number does not travel. Measured on the preview at 14fc0a1a,
    #: Apple, with `/runs/<id>/timing`:
    #:
    #:     core_composition   50.29s wall / 7.31s cpu
    #:     cpu yardstick      196.63ms wall / 27.26ms cpu -> 7.2x stretch
    #:
    #: The instance grants roughly 7-12% of a local core, so composition needs
    #: ~26s there even after the discarded `analyst_evidence` scan (18.0s) and
    #: the enrichment moved off CORE (6.1s) are removed. A reserve is a
    #: PREDICTION about the machine, so it cannot be a constant shared by
    #: machines that differ 8-15x in scheduling. Raising it here would only
    #: starve acquisition; the honest fix is fewer seconds of work or more CPU,
    #: both of which are measured elsewhere. Left at its current value
    #: deliberately, with the discrepancy recorded rather than hidden.
    COMPOSE_RESERVE_S = 20.0

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

    # --- the canonical customer lifecycle ------------------------------------
    #
    # ONE ANSWER TO "IS THIS READY FOR THE CUSTOMER?", AND ONLY ONE.
    #
    # MEASURED LIVE, not hypothesised. A first-time visitor typed "Meta" on a
    # phone against eb18371 and was told:
    #
    #     "This analysis could not be completed, so there is no result to
    #      open. Every approved source failed to retrieve (too large)."
    #
    # Both halves were false. Five sources HAD been retrieved — including
    # Meta's own SEC 10-K and 10-Q — and a readable result existed the whole
    # time at /runs/<id>, which is where the visitor eventually found it by
    # clicking "Your analyses". The only true statement on that page was that
    # the run's last TRANSITION was FAILED.
    #
    # That is the defect in one line: `_progress` branched on the run's
    # lifecycle STATE, while the thing the customer wanted was the RESULT.
    # `_availability` — which already derives exactly this, and whose own
    # docstring calls it "the single source every run route consults" — was
    # never called by the progress page. A repair that lives in one function
    # and is read by another is this programme's oldest failure mode.
    #
    # So: readiness is derived HERE, every customer-facing route asks THIS,
    # and a state name may never again out-vote a result that exists.
    READY_CREATED = "CREATED"
    READY_RESOLVING = "RESOLVING_IDENTITY"
    READY_RETRIEVING = "RETRIEVING"
    READY_ANALYSING = "ANALYSING"
    READY_COMPOSING = "COMPOSING"
    READY_RESULT = "RESULT_READY"
    READY_DEGRADED = "DEGRADED_RESULT_READY"
    READY_BLOCKED = "BLOCKED_RECOVERABLE"
    READY_FAILED = "FAILED_FINAL"

    #: The ONLY two states that open the analysis, and the ONLY state that may
    #: show a customer a final failure. Anything else is still in motion.
    READY_OPENS_RESULT = (READY_RESULT, READY_DEGRADED)

    #: Internal pipeline state -> the phase a customer is in. Deliberately
    #: many-to-few: a reader does not need eight nouns for "we are working".
    _READY_PHASE = {
        "VALIDATING_COMPANY": READY_RESOLVING,
        "DISCOVERING_SOURCES": READY_RETRIEVING,
        "AWAITING_SOURCE_APPROVAL": READY_RETRIEVING,
        "FETCHING_APPROVED_SOURCES": READY_RETRIEVING,
        "PARSING_SOURCES": READY_RETRIEVING,
        "BUILDING_SOURCE_ARTIFACTS": READY_ANALYSING,
        "ASSEMBLING_COMPANY_UNDERSTANDING": READY_ANALYSING,
        "ASSEMBLING_REPORT": READY_COMPOSING,
    }

    def classification_inputs(self, run_id, name: str = "") -> dict:
        """What this run knows about WHAT KIND OF BUSINESS its subject is.

        DELEGATED, NOT DUPLICATED. This logic used to live here and only
        here, and the ingestion layer — which gates the pattern library —
        had no answer at all, so one run carried two classifications of the
        same company and only one of them reached the hypotheses. A second
        copy is how that happened, so there is now one implementation, on
        the service that owns the run, its meta and its documents.

        `allow_network` carries this layer's rule that a test environment
        makes no SEC call; the service passes its own injected transport, so
        an in-process test is unaffected either way.
        """
        cache = getattr(self, "_classification_cache", None)
        if cache is None:
            cache = self._classification_cache = {}
        if run_id in cache:
            return cache[run_id]
        try:
            out = self.ci.classification_inputs(
                run_id, name, documents=self._retrieved_documents(run_id),
                allow_network=(self.config.env != "test"))
        except Exception:                                     # noqa: BLE001
            out = {"registrant": {}, "evidence_text": ""}
        cache[run_id] = out
        return out

    def only_watchable(self, run_id) -> bool:
        """Is watching the run the ONLY thing this reader can do right now?

        True while the worker is live AND nothing readable exists yet. False
        the moment a result can be opened, whatever the worker is still doing.

        WHY THIS IS ONE PREDICATE AND NOT FIVE CONDITIONS. Five surfaces asked
        "is the worker in flight?" and sent the reader to the progress page if
        so -- and the progress page sends them back as soon as
        `result_readiness(...)["opens_result"]` is true. Both were true
        together for most of a normal run, so the pages bounced off each other
        until the client gave up.

        MEASURED LIVE on 8397d67, four of four companies, as a 303 whose final
        URL was the page it started from:

            Alphabet    36s -> 152s   76% of the run
            Meta        37s -> 220s   83%
            JPMorgan    37s -> 157s   76%
            Cloudflare   9s ->  20s   50%

        Reproduced offline as a three-node cycle -- /runs/<id> -> /intro ->
        /progress -> /runs/<id> -- which is why fixing the first site alone
        only moved the loop one hop along.

        The rule was already written down, in `result_readiness` below:
        "opens_result is True IF AND ONLY IF a customer-readable result
        exists. When it is True the customer goes to the analysis, whatever
        the worker's metadata says." This is that sentence, in one place, so
        the next surface to ask the question cannot answer it differently.
        """
        if not self._availability(run_id).get("in_flight"):
            return False
        return not self.result_readiness(run_id)["opens_result"]

    def result_readiness(self, run_id) -> dict:
        """Is there something this customer may be shown, and what is it?

        READ-ONLY. Composes nothing, approves nothing, fetches nothing — a
        page a reader refreshes must never be the thing that mutates the run.

        The contract every caller may rely on:

          * ``opens_result`` is True IF AND ONLY IF a customer-readable result
            exists. When it is True the customer goes to the analysis, whatever
            the worker's metadata says.
          * ``FAILED_FINAL`` is the only state that may show a final failure,
            and it requires that NO readable result exists.
        """
        memo = getattr(self._request, "readiness", None)
        if memo is not None and run_id in memo:
            return memo[run_id]
        verdict = self._result_readiness(run_id)
        if memo is not None:
            memo[run_id] = verdict
        return verdict

    def _result_readiness(self, run_id) -> dict:
        """`result_readiness` without the per-request memo."""
        avail = self._availability(run_id)
        state = avail["state"] or "VALIDATING_COMPANY"
        # A readable result is a composed report, or a bounded reading built
        # from documents that were actually retrieved. The second is not a
        # consolation prize: it is what the run established, and it is strictly
        # more than a page saying nothing was established.
        readable = bool(avail["has_report"]
                        or (avail["has_result"] and avail["documents"]))
        if readable:
            phase = (self.READY_RESULT if avail["has_report"]
                     else self.READY_DEGRADED)
            return {"state": phase, "opens_result": True,
                    "terminal": True, "in_flight": avail["in_flight"],
                    "documents": avail["documents"],
                    "degraded": phase == self.READY_DEGRADED,
                    "retryable": False, "availability": avail}
        if avail["in_flight"] or state not in self.TERMINAL_STATES:
            phase = self._READY_PHASE.get(state, self.READY_ANALYSING)
            return {"state": phase, "opens_result": False,
                    "terminal": False, "in_flight": avail["in_flight"],
                    "documents": avail["documents"], "degraded": False,
                    "retryable": False, "availability": avail}
        # Terminal, and nothing readable. A run whose worker vanished is NOT a
        # final failure — telling a customer their analysis is dead when one
        # more attempt would actually run is the same lie in a quieter voice.
        #
        # BUT "RETRYABLE" IS NOT "STATE == FAILED". Every FAILED run passing
        # this test would put a retry button in front of someone whose sources
        # all answered 403 — the button dials the same refusing hosts and
        # fails again, which is a manual-recovery loop wearing a helpful face.
        # The retrieval layer already grades each failure: 429 and 5xx are
        # marked retryable, 403/404/unsafe-redirect are not. Ask it.
        attempts_left = self.attempt_count(run_id) < self.MAX_ANALYSIS_ATTEMPTS
        try:
            transient = any(row.get("retryable")
                            for row in self.ci.store.failures(run_id))
        except Exception:                                     # noqa: BLE001
            transient = False
        retryable = attempts_left and (state == "INTERRUPTED" or transient)
        return {"state": (self.READY_BLOCKED if retryable
                          else self.READY_FAILED),
                "opens_result": False, "terminal": True,
                "in_flight": False, "documents": avail["documents"],
                "degraded": False, "retryable": retryable,
                "availability": avail}

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

    #: A run-scoped path names its run in the second segment. Kept as one
    #: pattern so the header cannot be attached to a different set of routes
    #: than the ones a customer reads.
    _RUN_PATH = re.compile(r"^/runs/([A-Za-z0-9_-]{6,64})(?:/|$)")

    @classmethod
    def _run_id_of(cls, path: str) -> str:
        match = cls._RUN_PATH.match(str(path or ""))
        return match.group(1) if match else ""

    def analysis_outcome(self, run_id) -> str:
        """WHAT HAPPENED TO THIS CUSTOMER'S ANALYSIS. The one producer.

        Every consumer -- the progress page, the run page, the six steps, the
        capture harness and the acceptance audit -- reads THIS, instead of
        each deciding for itself from rendered text. `outcome.classify` holds
        the rule; this supplies it with the two facts it needs and is the only
        place that knows how to get them.
        """
        return OUTCOME.classify(
            readiness=self.result_readiness(run_id),
            run_state=self.ci.store.run_state(run_id),
            exhaustion=self.evidence_report(run_id))

    def _readiness_on_current_evidence(self, run_id):
        """Re-run the gate over every document the store now holds.

        CHEAP ON PURPOSE. This reads stored text and fetches nothing, which
        is what makes it usable on a run that has already composed once --
        the expensive half is synthesis, not the gate.
        """
        try:
            from intent_engine.company_ingestion.readiness import (
                assess_readiness,
            )
            return assess_readiness(
                documents=self.ci.store.retrieved(run_id),
                identity=self.ci.entity_identity(run_id),
                failures=self.ci.store.failures(run_id), attempt=1)
        except Exception:                                   # noqa: BLE001
            _LOG.warning("re-gating failed for %s", run_id)
            return None

    def evidence_gate_summary(self, run_id) -> str:
        """What the readiness gate held, versus what the store holds now.

        A COMPACT HEADER BECAUSE THE ANSWER HAS TO SURVIVE A WAVE. `compose`
        records `readiness_inputs`, and a field nothing reads is a field that
        does not exist -- the whole reason Meta's discrepancy had to be
        chased through three falsified mechanisms is that no artifact on disk
        recorded which document set the gate was looking at.

        Never customer-visible, never allowed to raise, and deliberately not
        rendered on any page: this is measurement, not product copy.
        """
        inputs = (self._results.get(run_id) or {}).get("readiness_inputs") or {}
        try:
            stored = len([d for d in self.ci.store.retrieved(run_id)
                          if d.get("retrieval_status") == "OK"])
        except Exception:                                   # noqa: BLE001
            stored = -1
        dropped = "/".join(str(inputs.get(k, "?")) for k in (
            "dropped_not_ok", "dropped_empty", "dropped_duplicate",
            "dropped_language"))
        return (f"compose={inputs.get('documents_at_compose', '?')} "
                f"usable={inputs.get('usable_at_compose', '?')} "
                f"families={'|'.join(inputs.get('families_at_compose') or []) or '-'} "
                f"stored={stored} "
                f"attempt={inputs.get('attempt', '?')} "
                f"failed={len(self.ci.store.failures(run_id))}/"
                f"{self.evidence_report(run_id).get('subject_failures', '?')} "
                # status/empty/duplicate/language -- four different repairs,
                # and `usable` alone cannot tell them apart.
                f"dropped={dropped}"
                # Attrition no filter above accounts for. Non-zero means the
                # gate dropped documents for a reason nothing here names yet,
                # which is a finding rather than a rounding error.
                f" unexplained={inputs.get('dropped_unexplained', '?')}"
                # DID THE RE-GATE RUN AT ALL? `compose < stored` alone cannot
                # tell "the re-gate never fired" from "it fired and still saw
                # the smaller set", and those are different repairs. Meta on
                # 8fd6c82 read `compose=1 stored=9` and which of the two it
                # was could not be established from the header.
                f" regated={inputs.get('regated_from', 'no')}"
                # WHICH documents the language wall took, so `dropped=x/x/x/8`
                # can be adjudicated as false positives or as localised pages
                # discovery should not have proposed.
                f" lang_rejected={_language_note(inputs)}")

    def evidence_report(self, run_id) -> dict:
        """Was the SUBJECT's own evidence actually looked for and retrieved?

        THE DISTINCTION THIS EXISTS FOR. "We could not find enough about this
        company" and "our retrieval did not work" rendered the same apologetic
        page, so retrieval defects hid behind honest-sounding copy for as long
        as anyone cared to read it. Meta's run read seven sources of which
        four were filed by Oklo, Enbridge, Network-1 and RingCentral; calling
        that scarcity is a false statement about Meta.

        Ownership of an EDGAR document is stated by its URL --
        `/edgar/data/<CIK>/` names the FILER -- and ownership of a web page by
        its host. Neither is inferred from `source_class`, which says how a
        document was retrieved and never whose it is.
        """
        meta = (self.ci.run_meta(run_id) or {})
        cik = "".join(c for c in str(meta.get("cik") or "")
                      if c.isdigit()).lstrip("0")
        host = str(meta.get("domain") or meta.get("website") or "").lower()
        host = host.split("//")[-1].split("/")[0].removeprefix("www.")
        try:
            retrieved = self.ci.store.retrieved(run_id)
            failures = self.ci.store.failures(run_id)
            candidates = self.ci.store.candidates(run_id)
        except Exception:                                   # noqa: BLE001
            return {}

        own = foreign = 0
        for row in retrieved:
            url = str(row.get("final_url") or row.get("original_url") or "")
            filer = re.search(r"/edgar/data/(\d+)", url)
            if filer:
                if cik and filer.group(1).lstrip("0") == cik:
                    own += 1
                else:
                    foreign += 1
                continue
            page_host = url.split("//")[-1].split("/")[0].lower()
            page_host = page_host.removeprefix("www.")
            if host and (page_host == host or page_host.endswith("." + host)):
                own += 1
            elif page_host:
                foreign += 1

        # DID THE SUBJECT'S OWN SITE REFUSE US?
        #
        # MEASURED on dc17a9d. Seven of ten Wave-3 companies rendered
        # "Limited analysis", every one of them with `compose=3 usable=3
        # families=investor dropped=0/0/0/0` -- the gate discarding NOTHING
        # and only SEC filings ever arriving. Fetching their homepages with
        # this service's own user agent says why:
        #
        #     goldmansachs.com   HTTP 403
        #     mastercard.com     HTTP 403
        #     costco.com         timeout
        #     nike.com           HTTP 200   -> FULL_ANALYSIS
        #     walmart.com        HTTP 200   -> FULL_ANALYSIS
        #     coca-colacompany   HTTP 200   -> FULL_ANALYSIS
        #
        # The publishers refused the bot. That is an operational fact about
        # retrieval and it is emphatically NOT a finding about Goldman Sachs,
        # which the product's own page already says in the next paragraph:
        # "Public websites can refuse automated access."
        subject_failures = 0
        for row in failures:
            candidate = next((c for c in candidates
                              if c.get("candidate_id") == row.get(
                                  "candidate_id")), None)
            url = str((candidate or {}).get("url") or "")
            page_host = url.split("//")[-1].split("/")[0].lower()
            page_host = page_host.removeprefix("www.")
            if host and (page_host == host or page_host.endswith("." + host)):
                subject_failures += 1
        return {
            "attempted": bool(candidates),
            "retrieved": len(retrieved),
            "subject_failures": subject_failures,
            "subject_documents": own,
            "foreign_documents": foreign,
            # A run whose ONLY documents belong to other registrants did not
            # establish scarcity about this company; it established that this
            # company's own material never arrived.
            "subject_retrieval_ok": own > 0,
            "displaced_by_foreign": own == 0 and foreign > 0,
            "rate_limited": any(
                "429" in str(f.get("safe_message", "")) or
                f.get("failure_type") == "rate_limited" for f in failures),
            "retrieval_failures": len(failures),
        }

    def _availability(self, run_id) -> dict:
        """What this run currently has. READ-ONLY, and the single source every
        run route consults before deciding what it may render."""
        with self._segment("avail.in_flight"):
            in_flight = self._analysis_in_flight(run_id)
        with self._segment("avail.run_state"):
            state = self.ci.store.run_state(run_id)
        with self._segment("avail.documents"):
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
        from intent_engine.company_ingestion.deadline import Deadline
        self._analysis_deadlines[run_id] = Deadline.for_tier(
            self._tier_for(run_id))
        # THE CLOCK STARTS WHERE THE CUSTOMER'S WAIT STARTS -- when the work
        # is accepted, not when a worker happens to pick it up. Queue time is
        # part of the wait, and measuring from job start would hide it.
        try:
            self.ci.mark_lifecycle(run_id, "accepted")
        except Exception:                       # noqa: BLE001 - never block
            _LOG.warning("lifecycle accepted marker failed run=%s", run_id)
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
        deadline = self._analysis_deadlines.get(run_id)
        # Read ONCE, before composition, and reused by the deep pass — the
        # persisted model is what "what changed since last time" is computed
        # against, and re-reading it after the core has been published would
        # compare the deep reading against a model this run just wrote.
        previous_model_for_deep = (self.strategic_memory.latest_model(domain)
                                   if domain else None)
        from intent_engine.company_ingestion.latency import Trace
        trace = Trace(run_id)
        # CALIBRATE THE MACHINE BEFORE TRUSTING THE SPANS. Every stage on the
        # preview reads 14-15% CPU whether it fetches, computes, or writes
        # files, which is the signature of a CPU share rather than of I/O.
        # This measures it directly instead of arguing it from ratios.
        trace.calibrate("cpu_yardstick")
        try:
            # ONE BUDGET ACROSS BOTH ACQUISITION STAGES. Discovery and
            # retrieval are the two halves of the same wait; budgeting only
            # the second one leaves the customer exposed to the first.
            with trace.span("discovery", deadline=deadline) as sp:
                self.ci.discover(run_id, trace=trace, deadline=(
                    deadline.reserving(self.COMPOSE_RESERVE_S)
                    if deadline is not None else None))
                sp["item_count"] = len(self.ci.store.candidates(run_id))
            candidates = self.ci.store.candidates(run_id)
            # DEFINED ON EVERY PATH, not only the one that assigns it. A run
            # whose approval was already recorded skips the block below
            # entirely, and the continuation further down still reads this.
            deferred_ids: list = []
            if self.ci.store.approval(run_id) is None:
                with trace.span("source_selection", deadline=deadline) as sp:
                    approved = self._recommended_candidate_ids(
                        candidates,
                        refusing_hosts=self.ci.refusing_hosts(run_id),
                        subject_cik=(self.ci.run_meta(run_id) or {}).get("cik"))
                    rejected = [c["candidate_id"] for c in candidates
                                if c["candidate_id"] not in approved]
                    self.ci.approve(run_id, user_id=user_id,
                                    approved_ids=approved,
                                    rejected_ids=rejected)
                    sp["item_count"] = len(approved)
                    sp["candidates"] = len(candidates)
                # §22. The acquisition phase stops early ON PURPOSE, so the
                # step that turns evidence into an answer is still inside the
                # interactive budget when it runs.
                with trace.span("retrieval", deadline=deadline) as sp:
                    # §5/§7. CORE STOPS BLOCKING WHEN THE CONTRACT IS MET,
                    # not when the approved list runs out.
                    #
                    # MEASURED: `readiness.assess_readiness` reached
                    # READY_FOR_FULL_REPORT after 5 documents for NVIDIA and
                    # Microsoft and 8 for JPMorgan, against 13, 8 and 10
                    # fetched, and never changed state again. Everything
                    # after that index was evidence the reader waited for and
                    # the product's own contract did not require.
                    #
                    # The rest is DEFERRED, not dropped: it is acquired after
                    # `core_ready` below, on a fresh budget, and a source that
                    # never arrives is a recorded gap.
                    #
                    # THIS CALL SITE IS THE WHOLE CHANGE. An earlier edit
                    # added `_sufficiency_probe` and `_acquire_deferred` and
                    # failed to write this line: the helpers existed, sixteen
                    # break proofs held, thirty-one tests passed, and every
                    # production run called `fetch_approved` with no probe and
                    # then raised NameError on `deferred_ids`. A fix with no
                    # caller is not a fix, and no test that drives a helper
                    # directly can tell the difference.
                    fetched = self.ci.fetch_approved(
                        run_id,
                        deadline=(deadline.reserving(self.COMPOSE_RESERVE_S)
                                  if deadline is not None else None),
                        sufficiency_probe=self._sufficiency_probe(run_id))
                    deferred_ids = list(fetched.get("deferred") or ())
                    sp["item_count"] = len(list(self.ci.store.retrieved(run_id)))
                    sp["deferred"] = len(deferred_ids)
                    if fetched.get("sufficiency"):
                        sp["stopped_on"] = fetched["sufficiency"].get("reason")
            # §22. COMPOSITION IS NOT OPTIONAL AND IS NOT BUDGETED AWAY.
            #
            # The budget bounds ACQUISITION -- the part that talks to hosts we
            # do not control and that produced the 4m54s stall. Reasoning over
            # what already arrived is local, bounded, and is the only step
            # that turns evidence into something a reader can use. Skipping it
            # to save time would hit the latency target by deleting the
            # product, which §3 forbids: a run that spent its budget composes
            # what it has and SAYS which evidence is missing.
            # §7/§9/§10. THE CORE IS COMPOSED, PUBLISHED, AND OPENABLE
            # BEFORE THE MODEL RUNS.
            #
            # `_availability` reads `strategic_report` out of `self._results`,
            # and `result_readiness` opens the analysis the moment one exists
            # -- in flight or not. So publishing the core here is what turns a
            # four-minute wait into a readable page: the reader gets the
            # evidence, the exposure and the economic reading while the
            # strategic review is still being written.
            with trace.span("core_composition", deadline=deadline) as sp:
                core = self._compose(run_id, deep=False, trace=trace)
                sp["item_count"] = len(list(self.ci.store.retrieved(run_id)))
            self._results[run_id] = core
            self._core_ready_at[run_id] = time.monotonic()
            # Marked AFTER publication, so the recorded instant is one at
            # which the result could actually be opened. Marking before would
            # record an intention rather than an availability.
            try:
                self.ci.mark_lifecycle(run_id, "core_ready")
            except Exception:                   # noqa: BLE001
                _LOG.warning("lifecycle core_ready marker failed run=%s",
                             run_id)
            # ENRICHMENT RUNS HERE: AFTER the marker, not before it.
            #
            # The market refresh (3.2s deployed) and the dossier write (2.9s)
            # used to run inside `_compose`, ahead of `core_ready` -- 6.1s the
            # reader waited for work that adds nothing to what they are about
            # to read. Neither produces the answer, so neither may delay it.
            #
            # IT STILL RUNS. `_publish_demo_dossier` is the real path, not a
            # demo-only one: every composed analysis emits a versioned record
            # and the 100-company runner reads it. Moving the call and failing
            # to make it is how a latency repair quietly deletes a feature --
            # the guard caught exactly that, because the first version of this
            # change split the function out and wired only the batch caller.
            try:
                self._publish_enrichment(run_id, core, trace=trace)
            except Exception:                   # noqa: BLE001 - never a run
                _LOG.warning("enrichment failed after core_ready run=%s",
                             run_id)
            # §5. THE DEFERRED EVIDENCE IS ACQUIRED HERE, and the reader is
            # already reading. If it changes the answer they are TOLD, through
            # `analysis_updated`, rather than having the page rewritten under
            # them -- a recommendation that silently becomes a different
            # recommendation is worse than a slower one.
            trace.calibrate("cpu_yardstick_after")
            # RECORDED AT CORE_READY, not at the end of the run. A trace
            # written only after DEEP would be lost for exactly the runs
            # whose latency is worth reading -- the ones that never finish.
            self.ci.record_trace(run_id, "core", trace.waterfall())
            # THE CORE TRACE LANDS BEFORE THE CONTINUATION, NOT AFTER IT.
            #
            # `record_trace` already ran a few seconds behind the `core_ready`
            # marker, and two of ten cohort rows -- Caterpillar and Alphabet,
            # the two SLOWEST -- were read inside that window and came back
            # with no spans at all, quietly removing the most interesting rows
            # from every bucket ranking. Putting the deferred acquisition in
            # front of it would widen exactly that window, on exactly the runs
            # whose latency is worth reading.
            #
            # The continuation records its own phase below, so nothing is lost
            # -- the core trace simply stops waiting for work the core did not
            # do.
            if deferred_ids:
                try:
                    core = self._acquire_deferred(run_id, core, deferred_ids,
                                                  trace=trace)
                    self._results[run_id] = core
                    self.ci.record_trace(run_id, "core", trace.waterfall())
                except Exception as exc:            # noqa: BLE001
                    _LOG.warning("deferred acquisition failed run=%s %s: %s",
                                 run_id, type(exc).__name__, str(exc)[:200])
            # A SECOND READING, taken where the cost actually landed. The
            # first is at t=0 when the worker contends with nothing;
            # composition is where 48 of the 90 seconds went, so the CPU
            # share DURING it is the number that explains those seconds.
            # Two readings also test REPRODUCIBILITY: a constraint that shows
            # up once could be a noisy neighbour, one that shows up at both
            # ends of the run is the machine we were given.

            with self._analysis_lock:
                self._terminal_writes[run_id] = \
                    self._terminal_writes.get(run_id, 0) + 1
            # §25. The deep half may fail, time out, or be refused, and the
            # core the customer is already reading survives all three. It is
            # deliberately NOT inside the outer handler's failure path: a deep
            # failure is not an analysis failure and may not mark the run
            # FAILED, because the run produced a result the reader can use.
            try:
                self.ci.mark_lifecycle(run_id, "deep_started")
            except Exception:                   # noqa: BLE001
                pass
            try:
                self._results[run_id] = self.ci.enrich_deep(
                    run_id, core, previous_model=previous_model_for_deep,
                    deadline=self._analysis_deadlines.get(run_id))
                try:
                    self.ci.mark_lifecycle(run_id, "deep_ready")
                except Exception:               # noqa: BLE001
                    pass
            except Exception as exc:              # noqa: BLE001
                _LOG.warning("deep enrichment failed run=%s %s: %s", run_id,
                             type(exc).__name__, str(exc)[:200])
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
                spent = self._analysis_deadlines.pop(run_id, None)
            if spent is not None and spent.gaps:
                # The gaps outlive the budget object: they are what the reader
                # is told, so they are recorded where the page can read them
                # rather than discarded with the timer that produced them.
                self._analysis_gaps[run_id] = spent.as_dict()

    def _tier_for(self, run_id: str) -> str:
        """Which interactive contract this run is held to (§2).

        Tier 1 is the well-known public company an executive types in and
        expects an answer to inside half a minute. Everything else -- a filer
        with no domain, a sparse private company -- is a deeper read and is
        held to the tier-2 budget, because holding it to tier 1 would not make
        it faster, only earlier to give up.
        """
        from intent_engine.company_ingestion.deadline import TIER_1, TIER_2
        try:
            meta = self.ci.run_meta(run_id) or {}
            if not meta.get("website"):
                return TIER_2               # filer-only: filings are the path
            listing = self._listing_for(run_id)
            return TIER_1 if getattr(listing, "ticker", "") else TIER_2
        except Exception:                                   # noqa: BLE001
            return TIER_2

    def analysis_gaps(self, run_id: str) -> dict:
        """What this run could not finish inside its budget, if anything."""
        return self._analysis_gaps.get(run_id) or {}

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
                refusing_hosts=self.ci.refusing_hosts(run_id),
                subject_cik=(self.ci.run_meta(run_id) or {}).get("cik"))
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
            return self._no_such_run(session, run_id)
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
                candidates, refusing_hosts=self.ci.refusing_hosts(run_id),
                subject_cik=(self.ci.run_meta(run_id) or {}).get("cik")))

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
            return self._no_such_run(session, run_id)
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
            return self._no_such_run(session, run_id)
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

    #: What a READ may recompose. A reader asking for a page may not trigger
    #: a model call on the request thread, and may not have the answer they
    #: are already holding replaced by one that failed.
    #:
    #: MEASURED LIVE on 5a27b2a7: five of ten cohort runs answered
    #: `result_state: FAILED` with `deep_status: RUNNING` -- the exact shape
    #: of a `deep=True` payload whose analyst gave up, because
    #: `_strategic_report` sets RUNNING before the call and only
    #: `enrich_deep` ever finishes it. `_compose` defaults to `deep=True`,
    #: so a read that found the cache stale ran the whole deep pass
    #: SYNCHRONOUSLY and published its failure over a good core.
    #:
    #: The reader needs a CORE. The deep half belongs to the worker, which
    #: already has a guard stopping a failed model from overwriting the
    #: core's state; a read had no such guard because it was never supposed
    #: to be doing this work.
    def _recompose_for_reader(self, run_id, previous=None):
        """A bounded recompose for a READ, which may only improve the page.

        ALWAYS RETURNS WHAT IT COMPOSED WHEN THERE IS NOTHING TO PROTECT.
        The first version returned `previous` on an unusable recompose, and
        on a cache miss `previous` is None -- so the caller stored None and
        every later read recomposed again. That is unbounded recomposition on
        the request thread, measured at 98% CPU for 2h52m in one suite, and
        for a reader it is a poisoned run that never opens.
        """
        fresh = self._compose(run_id, deep=False)
        if not previous:
            # Nothing to protect: whatever compose produced IS the answer for
            # this run, and it is a dict, so it can be cached and not redone.
            return fresh
        if not (fresh or {}).get("strategic_report"):
            _LOG.warning("read-triggered recompose produced no report run=%s "
                         "— keeping the published result", run_id)
            return previous
        if (fresh["strategic_report"].get("result_state") == "FAILED"
                and (previous.get("strategic_report") or {}).get(
                    "result_state") not in (None, "FAILED")):
            # A recompose that failed is not a newer answer; it is no answer.
            _LOG.warning("read-triggered recompose failed run=%s — keeping "
                         "the published result", run_id)
            return previous
        return fresh

    def _real_result(self, run_id):
        if run_id not in self._results:
            if self.ci.store.approval(run_id) is None:
                return None
            self._results[run_id] = self._recompose_for_reader(run_id)
        elif not self._cache_compatibility(run_id)["reusable"]:
            # A stored analysis is served again only while it still agrees with
            # the product that would produce it. Otherwise the fixes that
            # stopped every company being described as a commerce company, or
            # that capped confidence without an outside source, never reach
            # anyone whose analysis predates them — they see the old answer
            # under today's date and cannot tell.
            self._results[run_id] = self._recompose_for_reader(
                run_id, previous=self._results.get(run_id))
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

    def _compose(self, run_id, *, deep: bool = True, trace=None):
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
        # The FULL budget, not the reserved view: the reserve exists to
        # protect composition, so composition is what spends it — including
        # the targeted retry passes the quality gate can order from inside.
        result = self.ci.compose_with_quality(
            run_id, fi_service=self.fi, previous_model=previous_model,
            deadline=self._analysis_deadlines.get(run_id), deep=deep,
            trace=trace)
        # THE GATE MUST JUDGE THE EVIDENCE THAT ARRIVED, NOT THE EVIDENCE
        # THAT HAD ARRIVED WHEN IT RAN.
        #
        # MEASURED LIVE on 10d1620, Meta Platforms, first run after the
        # evidence-gate header was deployed:
        #
        #     compose=1  usable=1  families=investor  stored=7  attempt=1
        #
        # The readiness gate was handed ONE document. The store holds SEVEN,
        # three of them Meta's own SEC filings. The customer was told the
        # public evidence about Meta Platforms was too thin to analyse, on a
        # run that had read Meta's 10-K and its 10-Q.
        #
        # This was chased through three offline reproductions first, and all
        # three were wrong: `usable_documents` keeps 7 of 7, `is_english` is
        # True for 7 of 7, and raw-HTML truncation swept from 16MB to 200KB
        # keeps 7 of 7. The gate itself, re-run on those seven documents,
        # answers 7. Nothing was miscounting. Composition simply happened
        # before the evidence finished arriving, and nothing looked again.
        #
        # ONE EXTRA PASS, AND ONLY WHEN DOCUMENTS ACTUALLY ARRIVED LATE.
        # This does not re-run retrieval, does not fetch, and cannot loop:
        # it recomposes at most once, and only when the store is strictly
        # larger than the set the gate judged. `compose` is already
        # idempotent and restart-safe -- rebuilding from stored documents is
        # what it is written to do.
        #
        # NOT A FIX TO THE RACE. Which caller composed early is not
        # established, and this deliberately does not guess: whatever the
        # ordering turns out to be, judging seven documents is right and
        # judging one of them is wrong.
        # A GATE THAT JUDGED NOTHING STILL JUDGED SOMETHING.
        #
        # `documents_at_compose` is absent exactly when `compose` took its
        # early return -- "no approved source could be retrieved" -- because
        # that path returns before `readiness_inputs` is recorded. This used
        # to read `isinstance(seen, int)` and skip the re-gate entirely in
        # that case, which is the ONE case where looking again matters most:
        # the gate saw nothing, and evidence arrived afterwards.
        #
        # MEASURED live on 5e1218e, Meta Platforms: `compose=? stored=9
        # regated=no`, outcome TRUE_EVIDENCE_SCARCITY. Nine documents in the
        # store, a gate that judged none of them, and a re-gate whose
        # precondition was the very field the failing path does not produce.
        # A guard keyed on the presence of an instrument is not a guard.
        seen = (result.get("readiness_inputs") or {}).get(
            "documents_at_compose")
        if seen is None:
            seen = 0
        if isinstance(seen, int):
            try:
                stored = len(self.ci.store.retrieved(run_id))
            except Exception:                               # noqa: BLE001
                stored = seen
            if stored > seen:
                # ASK THE GATE AGAIN BEFORE PAYING FOR A SECOND SYNTHESIS.
                #
                # The first version of this recomposed unconditionally, and
                # the cost was not theoretical. MEASURED on b37bee2, 0d02c0b
                # and e78c2a0: Meta's service stopped answering
                # `/runs/<id>/progress` from t=33 to t=349 -- over five
                # minutes of a single-worker deployment serving nobody -- and
                # four consecutive Meta runs were unobservable. On the two
                # SHAs before it, the same analysis finished in 48 and 52
                # seconds.
                #
                # Re-running `assess_readiness` on the full document set is
                # cheap: it reads text that is already in memory and fetches
                # nothing. Re-running SYNTHESIS is what costs the five
                # minutes. So the gate is asked first, and the expensive pass
                # happens only when the extra evidence actually changes the
                # verdict -- which is the only case where it could change
                # what the customer reads.
                verdict = self._readiness_on_current_evidence(run_id)
                if verdict is not None:
                    result["readiness"] = verdict
                    from intent_engine.company_ingestion.readiness import (
                        explain as _explain,
                    )
                    result["readiness_explanation"] = _explain(verdict)
                    # EVERY COUNTER, OVER THE SET THE GATE JUST JUDGED.
                    #
                    # This used to overwrite three keys and leave the four
                    # `dropped_*` counters describing the FIRST composition,
                    # so the header reported two document sets at once and
                    # its arithmetic did not close (UnitedHealth on 743df06:
                    # `compose=13 usable=9 dropped=0/0/2/0`). A breakdown
                    # that cannot be subtracted is worse than none: it looks
                    # like an answer.
                    from intent_engine.company_ingestion.readiness import (
                        readiness_inputs as _inputs,
                    )
                    prior = result.get("readiness_inputs") or {}
                    # READ HERE, NOT SMUGGLED THROUGH THE VERDICT. A first
                    # version attached the document list to the verdict dict
                    # and counted that, which silently became an empty list
                    # the moment anything supplied its own
                    # `_readiness_on_current_evidence` -- and the counters
                    # then described nothing at all while looking populated.
                    # The caller can see the store; it does not need the
                    # callee's cooperation to count what is in it.
                    fresh = _inputs(self.ci.store.retrieved(run_id), verdict,
                                    attempt=prior.get("attempt", 1))
                    fresh["regated_from"] = seen
                    result.setdefault("readiness_inputs", {}).update(fresh)
                changed = (verdict or {}).get("may_synthesize") and \
                    not result.get("strategic_report")
                if changed:
                    _LOG.info("recomposing %s: gate saw %d, store holds %d, "
                              "and the fuller set clears the bar",
                              run_id, seen, stored)
                    # `deep=deep`, NOT the default. This branch only fires
                    # when the first pass produced no report at all, so it
                    # cannot double a model call today -- but it defaults to
                    # deep=True, and a CORE pass that reached here would run
                    # the very call the core exists to not wait for. The flag
                    # travels or the split has a hole in it.
                    result = self.ci.compose_with_quality(
                        run_id, fi_service=self.fi,
                        previous_model=previous_model, deep=deep)
                    result.setdefault("readiness_inputs",
                                      {})["recomposed_from"] = seen
        report = result.get("strategic_report")
        if report and domain:
            # THE DISK IS NOT THE SAME DISK. Locally these are ~1.9s against a
            # local SSD; the preview writes append-only files to a NETWORK-
            # ATTACHED Render volume, and `core_composition` amplifies 12.5x
            # deployed while the network stages amplify 4x. Composition is
            # 14% CPU there, so it is waiting on something -- and after the
            # quality-retry hypothesis was measured and found not to fire,
            # this is the only I/O left inside it. Split so the next trace
            # says which of the two writes owns the time.
            if trace is not None:
                with trace.span("memory_snapshot"):
                    self.strategic_memory.save_snapshot(
                        domain, report["mental_model"])
                with trace.span("memory_publish") as _sp:
                    events = report.get("analytics_events", [])
                    _sp["item_count"] = len(events)
                    self.strategic_memory.publish(domain, events,
                                                  run_id=run_id)
            else:
                self.strategic_memory.save_snapshot(domain,
                                                    report["mental_model"])
                self.strategic_memory.publish(
                    domain, report.get("analytics_events", []), run_id=run_id)
        # The last read before a stranger sees it. Attached rather than
        # applied: a critic that edits is a second author with less context
        # than the first, and its corrections would reach the reader
        # unreviewed. What it finds becomes a stated limitation, which is
        # worth more than a silent fix.
        if report is not None:
            from intent_engine.strategic_intelligence.critic import critique
            if trace is not None:
                with trace.span("critic"):
                    result["critique"] = critique(
                        report, documents=self.ci.store.retrieved(run_id))
            else:
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
        # THE ONE NETWORK CALL LEFT INSIDE COMPOSITION, and it was the only
        # stage in the whole pipeline with no span on it. `core_composition`
        # measures 54.66s deployed at 14% CPU while every child span found so
        # far is 90-100% CPU and small; an external fetch is the only thing
        # in here that can wait. It is also wrapped in a bare `except`, so a
        # slow or hanging provider costs the customer the time and reports
        # nothing at all.
        # NEITHER OF THESE PRODUCES THE ANSWER, so neither may delay it.
        #
        # Measured on the preview: the market refresh is 3.9s and the dossier
        # write 2.6s, both AHEAD of the `core_ready` marker -- 6.5s the reader
        # waits for work that adds nothing to what they are about to read.
        # §26 classifies the refresh as enrichment and forbids it blocking
        # CORE_READY; the dossier is a read-model write with the same standing.
        #
        # GATED ON `deep`, NOT ON A NEW KEYWORD. Adding a keyword-only
        # parameter to a method that tests stub is a breaking change to every
        # stub of it, and the break surfaces as "composition failed" -- the
        # very condition those tests exercise. That has now happened three
        # times in this investigation (`deep`, then `trace`, then `trace` on
        # `_strategic_report`). `deep` already distinguishes the interactive
        # CORE pass from the batch callers, so it is the gate.
        #
        # The interactive worker calls `_publish_enrichment` itself, AFTER the
        # marker. Batch callers (deep=True) keep the old inline behaviour.
        if deep:
            self._publish_enrichment(run_id, stamped, trace=trace)
        return stamped

    # ------------------------------------------------------------------
    # §5/§7/§24. Minimum-evidence CORE, and what happens to the rest.
    # ------------------------------------------------------------------
    def _sufficiency_probe(self, run_id: str):
        """A callable acquisition consults after each wave.

        It asks `readiness.assess_readiness` -- the SAME contract that decides
        whether a report may be published. A second definition of "enough
        evidence" would let acquisition stop on one standard while composition
        refused on another, and the run would be fast because it had stopped
        producing a product. This project shipped that failure once already.
        """
        from intent_engine.company_ingestion import sufficiency

        meta = self.ci.run_meta(run_id) or {}
        # `ci.subject_cik`, NOT `meta["cik"]`. A run started from a website
        # carries no CIK -- which is the ORDINARY case -- so reading meta
        # directly made the "wait for the subject's own filing" condition
        # return True for every domain-entry run and never fire once.
        # Measured: meta["cik"] is "" for Apple and NVIDIA, while
        # `subject_cik` resolves 320193 and 1045810. A guard that cannot fail
        # is not a guard.
        subject_cik = str(self.ci.subject_cik(meta) or "")

        def probe(documents):
            try:
                return sufficiency.evaluate(
                    documents,
                    identity=self.ci.entity_identity(run_id),
                    failures=list(self.ci.store.failures(run_id)),
                    subject_cik=subject_cik)
            except Exception as exc:            # noqa: BLE001
                # A probe that cannot answer means "keep going", which is the
                # behaviour that existed before it. LOGGED, because a silent
                # fallback here looks exactly like a run that never had enough
                # evidence to stop -- the failure mode this session already
                # shipped once with the snapshot short-circuit.
                _LOG.warning("sufficiency probe failed run=%s %s: %s", run_id,
                             type(exc).__name__, str(exc)[:200])
                return {"sufficient": False, "reason": "probe unavailable"}

        return probe

    #: How much of the report may change before the reader is TOLD it changed,
    #: rather than the page being rewritten under them. Any change to the
    #: thesis, the decision implications or the result state is material by
    #: construction: those are the sentences a reader acts on.
    _MATERIAL_REPORT_FIELDS = ("thesis", "decision_implications",
                              "result_state", "status")

    @staticmethod
    def _decision_fingerprint(result) -> dict:
        """The part of a composed result a reader would notice changing."""
        report = (result or {}).get("strategic_report") or {}
        out = {}
        for field in WebApp._MATERIAL_REPORT_FIELDS:
            value = report.get(field)
            out[field] = json.dumps(value, sort_keys=True, default=str)                 if isinstance(value, (list, dict)) else str(value or "")
        return out

    def _acquire_deferred(self, run_id, core, deferred_ids, trace=None):
        """Acquire the evidence CORE did not wait for, then say what changed.

        THE READER IS ALREADY READING. `core_ready` has been marked and the
        result is openable, so this stage may not fail the run, may not block,
        and may not silently replace what is on the screen. Three rules:

        1. It composes AGAIN over the wider evidence.
        2. If the decision fingerprint is unchanged, the richer result
           replaces the core silently -- nothing a reader acts on moved.
        3. If it CHANGED, the run records `ci.analysis_updated` naming the
           fields that moved and how many new documents caused it, so the
           change is visible as a change rather than as a different page.

        A recommendation that quietly becomes a different recommendation is
        worse than a slower one, which is the whole reason deferral has to
        carry an update signal rather than just a recompose.
        """
        from contextlib import nullcontext
        span = (trace.span("deferred_acquisition") if trace is not None
                else nullcontext({}))
        before_documents = len(list(self.ci.store.retrieved(run_id)))
        with span as sp:
            # A FRESH BUDGET, NOT THE SPENT ONE. The interactive deadline
            # bounds the WAIT, and by here `core_ready` is marked and there is
            # no wait left to bound. Passing the spent deadline would make
            # `budget_for` return 0.0 for every deferred source, record each
            # one as `deadline_exceeded`, and turn deferral into deletion
            # wearing a retrieval failure -- against evidence nobody had asked
            # for yet.
            from intent_engine.company_ingestion.deadline import Deadline
            fetched = self.ci.fetch_approved(
                run_id, candidate_ids=list(deferred_ids),
                deadline=Deadline.for_continuation(self._tier_for(run_id)))
            after_documents = len(list(self.ci.store.retrieved(run_id)))
            if isinstance(sp, dict):
                sp["item_count"] = after_documents - before_documents
            if after_documents <= before_documents:
                # Nothing new arrived, so there is nothing to recompose and
                # nothing to tell the reader. The gaps the fetch recorded are
                # already on the run.
                return core
            widened = self._compose(run_id, deep=False, trace=trace)
        # A WIDER RECOMPOSE MAY ONLY REPLACE THE CORE IF IT IS STILL A REPORT.
        #
        # MEASURED LIVE on 5a27b2a7: five of ten cohort runs came back with
        # `result_state: FAILED`, and they were EXACTLY the five with
        # deferred evidence. `compose` returns `{"status": "FAILED", ...}`
        # with NO `strategic_report` key on its own failure paths, and this
        # function handed that object straight back to the worker, which
        # published it over a core the reader was already holding.
        #
        # The core is not improved by a recompose that produced nothing. It
        # is destroyed by it -- the same failure as the warm path that was
        # fast because it had stopped producing the product, one layer over.
        if not (widened or {}).get("strategic_report"):
            _LOG.warning("deferred recompose produced no report run=%s "
                         "status=%s — keeping the published core", run_id,
                         (widened or {}).get("status"))
            return core
        before = self._decision_fingerprint(core)
        after = self._decision_fingerprint(widened)
        changed = sorted(k for k in before if before[k] != after[k])
        if changed:
            try:
                self.ci.record_analysis_updated(
                    run_id, fields=changed,
                    new_documents=after_documents - before_documents,
                    reason="evidence acquired after the first answer was "
                           "published")
            except Exception:                   # noqa: BLE001
                _LOG.warning("analysis_updated marker failed run=%s", run_id)
        return widened

    def _publish_enrichment(self, run_id, stamped, trace=None):
        """Market refresh and dossier write -- everything CORE does not need.

        THE REFRESH CANNOT BE STARTED EARLIER, which is why it is here rather
        than at the top of the run: it reads the composed report to find
        exposure phrases and competitor passages, and building it against an
        empty run cached the emptiness. So it runs after composition -- but it
        no longer runs before the reader is told the answer is ready.

        Fails soft, and now says so. The bare `except` this replaces reported
        neither a duration nor a failure class, which is how an unbounded
        network call sat on the critical path through four wrong hypotheses.
        """
        if trace is not None:
            _ctx = trace.span("external_context")
        else:
            from contextlib import nullcontext
            _ctx = nullcontext({})
        try:
            with _ctx:
                self._external_context(run_id, allow_fetch=True)
        except Exception as exc:  # noqa: BLE001 - context must never lose a run
            _LOG.warning("external context refresh failed for %s %s: %s",
                         run_id, type(exc).__name__, str(exc)[:200])
        if trace is not None:
            with trace.span("demo_dossier"):
                self._publish_demo_dossier(run_id, stamped)
        else:
            self._publish_demo_dossier(run_id, stamped)

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

            # THE RUN'S OWN EVIDENCE REFERENCES, PASSED.
            #
            # `build_payload` has always accepted `evidence_ids`, and this --
            # its ONLY production call site -- has never supplied them. Every
            # dossier this deployment has ever written therefore carried
            # `evidence_reference_ids = {state: NOT_ATTEMPTED, count: 0}`,
            # for every company, however many documents the run composed.
            #
            # That is not a cosmetic gap. `decision_synthesis._standing_of`
            # asks this block whether the run has anything to stand on, so a
            # repair keyed on it could never fire: MEASURED by instrumenting
            # the production path (scripts/qa_seam_instrument.py), Goldman
            # Sachs reads NOT_ATTEMPTED/0 and lands on REFUSED, which is how
            # a live CEO answer came to read "Do not act on this reading" on
            # a company that composed eleven documents. Two repairs shipped
            # green and inert against this field before it was measured.
            #
            # OBSERVATIONS, NOT DOCUMENTS. A retrieved page is not evidence
            # until it yields a dated, checkable observation, and this
            # product has one denominator per page for exactly that reason.
            #
            # MEASURED: feeding retrieved documents here broke the two tests
            # that hold the honest page for a run which fetched ten sources
            # and derived no signal from any of them -- "the sources were
            # read and none carried dated, checkable material". That page is
            # TRUE and it is the one absence state worth keeping, so the
            # count that decides standing has to be the count of what was
            # actually derived. Goldman composed eleven observations and is
            # unaffected; the silent run keeps its page.
            _evidence_ids = []
            try:
                for _obs in ((report or {}).get("observations") or ()):
                    if not isinstance(_obs, dict):
                        continue
                    _oid = _obs.get("observation_id") or _obs.get("source_id")
                    if _oid:
                        _evidence_ids.append(str(_oid))
            except Exception:  # noqa: BLE001 - a read model may not fail a run
                _evidence_ids = []
            founder = read_founder_snapshot(fds.build_payload(
                run_id=run_id, company_id=key, canonical_name=name,
                domain=str(meta.get("domain") or ""), report=report,
                context=context, scope=None,
                evidence_ids=_evidence_ids,
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
            from intent_engine.webapp import storage_state as _ss
            payload = {"status": "degraded" if degraded else "ready",
                       "env": self.config.env,
                       "runtime_root": str(self._runtime_root),
                       # WHO THIS PROCESS IS. A client that sees `boot_id`
                       # change between two requests has WATCHED a restart --
                       # which `boot_count` structurally cannot report, since
                       # its ledger dies with the instance whose restart is in
                       # question. This is how a lost run gets attributed to a
                       # restart instead of guessed at.
                       "process": _ss.process_identity(),
                       # Is a persistent disk attached but unused? "No disk"
                       # and "disk attached, RUNTIME_ROOT never pointed at it"
                       # produce identical symptoms and have very different
                       # fixes. Looked at, never acted on.
                       "persistent_mounts": _ss.persistent_mount_candidates(),
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
    def _run_provenance(self, run_id) -> dict:
        """Whose document is behind each thing this run states. Operator only.

        WHY A SURFACE AND NOT ANOTHER HYPOTHESIS. The claim-ownership repair
        has now read green in unit tests, passed a probe against real EDGAR
        documents, and left the rendered page unchanged three times — and
        five separate hypotheses about why have all been wrong. Two of them
        were argued from a RENDERED LABEL rather than from the class it was
        computed from, which is the same error in both directions.

        This ends the guessing by making the run say what it used. For every
        observation: the id, the title a reader sees, the source_class the
        label is computed FROM, the origin URL (whose EDGAR path names the
        filer), and whether the ownership gate marked it the subject's own.
        A row where those disagree is the defect, and it takes one run.
        """
        meta = self.ci.run_meta(run_id) or {}
        subject_cik = "".join(ch for ch in str(meta.get("cik") or "")
                              if ch.isdigit())
        rows = []
        try:
            from intent_engine.founder_brief.narrative import provenance_label
            result = self._result(run_id) or {}
            report = result.get("strategic_report") or {}
            company = str(meta.get("company_name") or "")
            for raw in (report.get("observations") or ()):
                if not isinstance(raw, dict):
                    continue
                origin = str(raw.get("origin") or "")
                source_class = str(raw.get("source_class") or "")
                filed_by = ""
                if "/data/" in origin:
                    filed_by = origin.split("/data/", 1)[1].split("/", 1)[0]
                rows.append({
                    "observation_id": raw.get("observation_id", ""),
                    "source_title": raw.get("source_title", ""),
                    "source_class": source_class,
                    "rendered_label": provenance_label(
                        source_class, title=str(raw.get("source_title") or ""),
                        focal=company,
                        excerpt=str(raw.get("excerpt") or "")[:200],
                        origin=origin),
                    "origin": origin,
                    "filed_by_cik": filed_by,
                    "is_subject_filing": (bool(filed_by)
                                          and filed_by == subject_cik),
                    "subject_owned": raw.get("subject_owned"),
                    "strategic_signal": raw.get("strategic_signal", ""),
                })
        except Exception as exc:                            # noqa: BLE001
            return {"run_id": run_id, "error": type(exc).__name__}
        # The rows that ANSWER the question, called out rather than left to
        # be spotted: a document filed by someone else that the gate marked
        # the subject's own, or the reverse.
        disagreeing = [r for r in rows
                       if r["filed_by_cik"]
                       and r["is_subject_filing"] is not bool(
                           r["subject_owned"])]
        # AND THE ROWS AS THE PAGE COMPOSES THEM.
        #
        # If the defect is a JOIN, every observation above looks correct on
        # its own and the mismatch exists ONLY in the row — a clean
        # observation list would then read as a clean bill of health and
        # leave the join invisible. So each rendered row is resolved here the
        # way a surface resolves it: the component's own evidence ids, and
        # what each id actually points at.
        by_id = {r["observation_id"]: r for r in rows}
        rendered = []
        try:
            components = ((report.get("mental_model") or {}).get("components")
                          or {})
            for name, component in components.items():
                if not isinstance(component, dict):
                    continue
                ids = list(component.get("supporting_observation_ids") or ())
                cited = []
                for oid in ids[:3]:
                    hit = by_id.get(oid)
                    cited.append({
                        "observation_id": oid,
                        "resolves": bool(hit),
                        "source_title": (hit or {}).get("source_title", ""),
                        "source_class": (hit or {}).get("source_class", ""),
                        "rendered_label": (hit or {}).get("rendered_label", ""),
                        "filed_by_cik": (hit or {}).get("filed_by_cik", ""),
                        "is_subject_filing": (hit or {}).get(
                            "is_subject_filing"),
                    })
                rendered.append({
                    "row": name,
                    "states": str(component.get("current_state") or "")[:200],
                    "cited": cited,
                    "cites_a_document_filed_by_someone_else": any(
                        c["filed_by_cik"] and c["is_subject_filing"] is False
                        for c in cited),
                    "cites_an_id_that_does_not_resolve": any(
                        not c["resolves"] for c in cited),
                })
        except Exception as exc:                            # noqa: BLE001
            rendered = [{"error": type(exc).__name__}]

        return {"run_id": run_id, "subject_cik": subject_cik,
                "company_name": str(meta.get("company_name") or ""),
                "observations": rows,
                "rows_where_ownership_disagrees_with_the_filer": disagreeing,
                "rendered_rows": rendered,
                "rows_citing_another_filers_document": [
                    r for r in rendered
                    if r.get("cites_a_document_filed_by_someone_else")
                    or r.get("cites_an_id_that_does_not_resolve")]}

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

        # WHAT RETRIEVAL HAD TO DO. Operator-only on purpose: a chief
        # executive must never be asked to understand "429", and an operator
        # looking at a thin run must be able to tell "sec.gov asked us to
        # wait" from "this company has published nothing". Before this the
        # answer existed only inside a local variable.
        try:
            retrieval = self.ci.retrieval_telemetry_overview()
        except Exception as exc:                            # noqa: BLE001
            retrieval = {"error": type(exc).__name__}

        return {
            "as_of": as_of,
            "version": version_info(),
            "retrieval": retrieval,
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
    #: The eleven questions Section 28 requires `/learning` to answer. Kept
    #: as data so the page cannot quietly stop answering one: every question
    #: renders, and a question with no answer renders its absence and the
    #: reason, rather than being dropped from the list.
    _ECON_QUESTIONS = (
        ("what_changed", "What changed?"),
        ("why", "Why?"),
        ("market_belief", "What does the engine currently believe?"),
        ("most_fragile", "Which belief is most fragile?"),
        ("what_would_break_it", "What would break it?"),
        ("learning_faster", "What are we learning faster about?"),
        ("stuck", "Where is the system stuck?"),
        ("seek_next", "What should we find out next?"),
        ("open_expectations", "What forward expectations are open?"),
        ("resolved", "What resolved recently?"),
        ("wrong", "What did the system get wrong?"),
    )

    def _econ_intelligence(self, as_of: str) -> dict:
        """Answer Section 28's questions from the shared economic core.

        READS, NEVER COMPUTES. Every number here is already in the core; this
        assembles them. A surface that derived its own version of a belief
        count is how two pages of the same product came to disagree about how
        much the engine knew.

        An unanswerable question returns an ABSENCE with a reason. That is
        the difference between "the engine has resolved nothing yet" and
        "this page does not know how to ask", and only the first is a fact
        about the engine.
        """
        from intent_engine.econ import calibration as CAL
        from intent_engine.econ import store as EST
        from intent_engine.external_intel import econ_context as EC

        out = {"as_of": as_of, "answers": {}, "available": False}
        try:
            summary = EST.summary(self._runtime_root)
        except Exception as exc:  # noqa: BLE001
            summary = {"counts": {}, "error": str(exc)}
        out["store"] = summary
        context = EC.load(self._runtime_root, as_of=as_of)
        out["available"] = context.available
        if not context.available:
            for key, question in self._ECON_QUESTIONS:
                out["answers"][key] = {"answer": "", "absent": True,
                                       "reason": context.reason}
            return out

        beliefs = list(context.beliefs)
        conditions = {k: v for k, v in context.conditions.items()
                      if v.get("known")}
        moving = [v for v in conditions.values()
                  if v.get("direction") in ("UP", "DOWN")]
        fragile = max(beliefs, key=lambda b: float(b.get("fragility") or 0),
                      default=None)

        def answer(key, text, absent_reason=""):
            out["answers"][key] = {
                "answer": text, "absent": not text,
                "reason": absent_reason or (
                    "" if text else "the core holds nothing that answers "
                                    "this yet")}

        answer("what_changed",
               (f"{len(moving)} of {len(conditions)} measured conditions "
                f"moved: "
                + ", ".join(f"{v['kind'].replace('_', ' ')} "
                            f"{'up' if v['direction'] == 'UP' else 'down'}"
                            for v in moving[:5]))
               if moving else "")
        answer("why",
               ("each reading names the publisher and the evidence node it "
                "is; the causal graph states which mechanisms connect them, "
                "and only edges at evidence level 3 or above are permitted "
                "to say one causes another")
               if conditions else "")
        answer("market_belief",
               (f"{len(beliefs)} belief(s) published to the shared core. "
                + "; ".join(str(b.get("proposition", ""))[:110]
                            for b in beliefs[:3]))
               if beliefs else "",
               absent_reason=("the market engine has published no belief "
                              "that carries a mechanism, a falsifier and a "
                              "preregistered observation; beliefs missing "
                              "any of the three are refused at the bridge "
                              "and reported by causal family in the cycle "
                              "report"))
        answer("most_fragile",
               (f"{str(fragile.get('proposition', ''))[:140]} "
                f"(probability {fragile.get('probability')}, fragility "
                f"{fragile.get('fragility')})") if fragile else "")
        answer("what_would_break_it",
               str(fragile.get("falsifier", "")) if fragile else "")

        counts = summary.get("counts") or {}
        answer("learning_faster",
               (f"the core holds {counts.get('node', 0)} evidence node(s) "
                f"and {counts.get('aggregate', 0)} candidate indicator(s); "
                "learning acceleration is reported per rolling window in the "
                "cycle report")
               if counts else "")
        unmeasured = (context.uncertainty or {}).get("unmeasured") or []
        answer("stuck",
               (f"{len(unmeasured)} economic condition(s) in the vocabulary "
                f"are unmeasured: {', '.join(unmeasured[:6])}")
               if unmeasured else "")
        answer("seek_next",
               (f"the unmeasured conditions above, ranked by how far a "
                "belief could move on them; series this deployment cannot "
                "read at all are listed with the reason in `econ.series`")
               if unmeasured else "")

        try:
            expectations = EST.load(self._runtime_root, "expectation")
        except Exception:  # noqa: BLE001
            expectations = []
        open_count = sum(1 for e in expectations
                         if isinstance(e, dict) and e.get("outcome") == "OPEN")
        resolved = [e for e in expectations if isinstance(e, dict)
                    and e.get("outcome") in ("CORRECT", "INCORRECT",
                                             "NEAR_MISS")]
        answer("open_expectations",
               f"{open_count} open forward expectation(s)"
               if open_count else "")
        answer("resolved",
               f"{len(resolved)} resolved forward expectation(s)"
               if resolved else "",
               absent_reason=("no forward expectation has been written to "
                              "the shared core and reached its window yet"))
        wrong = [e for e in resolved if e.get("outcome") == "INCORRECT"]
        answer("wrong",
               "; ".join(str(e.get("reconciliation", ""))[:100]
                         for e in wrong[:3]) if wrong else "")

        # SECTION 37. The calibration line is rendered from the ledger, and
        # it is PRE-CALIBRATION until the declared minimum is met. There is
        # no branch here that prints a percentage before then.
        from intent_engine.econ import belief as EB
        rehydrated = []
        for row in expectations:
            if not isinstance(row, dict):
                continue
            try:
                rehydrated.append(EB.Expectation(**{
                    k: v for k, v in row.items()
                    if k in EB.Expectation.__dataclass_fields__}))
            except Exception:  # noqa: BLE001
                continue
        out["calibration"] = CAL.report(rehydrated).as_dict()
        return out

    def _econ_learning_block(self, as_of: str) -> str:
        """The shared-core section of `/learning`, as HTML."""
        data = self._econ_intelligence(as_of)
        rows = []
        for key, question in self._ECON_QUESTIONS:
            entry = data["answers"].get(key) or {}
            if entry.get("absent"):
                rows.append(
                    f"<li><strong>{_e(question)}</strong><br>"
                    f"<em>not answerable yet — {_e(entry.get('reason', ''))}"
                    f"</em></li>")
            else:
                rows.append(f"<li><strong>{_e(question)}</strong><br>"
                            f"{_e(entry.get('answer', ''))}</li>")
        counts = (data.get("store") or {}).get("counts") or {}
        counts_html = (", ".join(f"{_e(k)}: {v}"
                                 for k, v in sorted(counts.items()))
                       or "the shared core holds nothing yet")
        cal = data.get("calibration") or {}
        cal_html = _e(cal.get("headline", "")) if cal else (
            "no forward expectations have been recorded")
        return (
            f'<h2>Shared economic core</h2>'
            f'<p><em>One economic state, read by both the market engine and '
            f'every company analysis. This page shows what the core holds; '
            f'it exposes no position, no book and no scheduler.</em></p>'
            f'<p><strong>Calibration:</strong> {cal_html}</p>'
            f'<p><strong>Core contents:</strong> {counts_html}</p>'
            f'<ul>{"".join(rows)}</ul>')

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
            f'{self._econ_learning_block(as_of)}'
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
