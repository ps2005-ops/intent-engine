"""The presentation layer — the report as something you can walk someone through.

WHY SLIDES, AND WHY IN THE BROWSER
----------------------------------
The person this is for is standing up in a meeting in ten minutes. They do not
need a document; they need nine things they can say in order, each one small
enough to hold while talking. A scrolling report cannot do that — scroll
position is not a place, so there is nowhere to pause and nothing to advance.

NO SLIDE IS ALLOWED TO BE EMPTY
-------------------------------
Every slide is built from evidence or is not built. That is why the eligibility
rules live here next to the content rules rather than in the renderer: a
renderer handed an empty slide will faithfully render an empty slide, and a deck
padded to nine with three blanks is worse than an honest deck of six. The count
comes from `readiness.slide_units`, the same function the gate uses to decide
whether to synthesise at all, so the promise and the delivery cannot disagree.

NAVIGATION WITHOUT JAVASCRIPT
-----------------------------
Slide switching is CSS `:target`. It works with scripting disabled, in every
browser that has had `:target` for fifteen years, and it survives the print
stylesheet. Links are focusable, so Tab and Enter already navigate — that is the
accessible baseline, not a fallback. A small inline script adds arrow keys on
top; if it never runs, nothing is lost.
"""
from __future__ import annotations

import html as _html

from intent_engine.strategic_intelligence.editorial import (
    addresses_the_system, deduplicate, is_meaningful, meaningful_items,
)

_e = _html.escape

SLIDES_VERSION = "si_slides.v1"

# Below this a deck is not a presentation, it is a paragraph with arrows. The
# same floor the readiness gate applies to `slide_units`.
MIN_MEANINGFUL_SLIDES = 5

# How much text a slide may carry before it stops being a slide. A wall of text
# on a slide is strictly worse than the same text in a document, because the
# reader is also being talked at.
MAX_BULLETS_PER_SLIDE = 5
MAX_WORDS_PER_BULLET = 28
# The per-bullet cap alone permits 5 × 28 = 140 words on one slide, which is
# most of a page. A slide is bounded by what a reader can take in while someone
# is talking over it, so the WHOLE slide has a budget and bullets are dropped
# once it is spent — the last bullet is the one the room never reaches anyway.
MAX_WORDS_PER_SLIDE = 90


def _bullet(text, *, evidence=None, date=""):
    # `evidence` is a list of evidence ids. A bare string is not one id, it is
    # a sequence of characters, and `list("obs-1")` turns a citation into five
    # of them — which is how the "what changed" slide came to carry thirty
    # citations labelled "-", "n", "u", "p" and "g", each an invitation to
    # check a source that does not exist.
    if isinstance(evidence, str):
        evidence = [evidence] if evidence.startswith("obs-") else []
    return {"text": " ".join(str(text or "").split()),
            "evidence": [e for e in (evidence or []) if e], "date": date}


def _cap(bullets):
    """Bounded, deduplicated bullets — the no-wall-of-text rule, mechanically.

    Also the last place a page that talks to the system can be stopped: a
    bullet is the product speaking, and a quotation is indistinguishable from
    an assertion once it is on a slide in front of a room.
    """
    kept = deduplicate(meaningful_items(bullets, key="text"), key="text")
    kept = [b for b in kept if not addresses_the_system(b.get("text", ""))]
    out, spent = [], 0
    for bullet in kept[:MAX_BULLETS_PER_SLIDE]:
        words = bullet["text"].split()
        if len(words) > MAX_WORDS_PER_BULLET:
            bullet = dict(bullet,
                          text=" ".join(words[:MAX_WORDS_PER_BULLET]) + "…")
            words = bullet["text"].split()
        # Keep the first bullet whatever it costs — a slide with a title and
        # nothing under it is worse than a slightly long one — then stop when
        # the slide's budget is spent.
        if out and spent + len(words) > MAX_WORDS_PER_SLIDE:
            break
        out.append(bullet)
        spent += len(words)
    return out


def _slide(slide_id, title, bullets, *, kind="content", note=""):
    """A slide, or None when there is nothing to put on it."""
    bullets = _cap(bullets)
    if not bullets:
        return None
    return {"id": slide_id, "title": title, "bullets": bullets,
            "kind": kind, "note": note}


def _document_bullets(documents, families, *, limit=3):
    """Bullets drawn from retrieved documents, classified exactly as the
    readiness gate classified them.

    The gate counts DOCUMENTS; the report's observations are a much smaller,
    analytically-selected subset that carries no `source_type` at all. Building
    the factual slides from observations therefore promised seven subjects and
    delivered three — the precise gate/renderer disagreement this module exists
    to prevent. Using `family_of` here means both sides classify the same
    evidence the same way, by construction.
    """
    from intent_engine.company_ingestion.coverage import family_of
    out = []
    for document in documents or ():
        if document.get("retrieval_status") != "OK":
            continue
        if family_of(document) not in families:
            continue
        text = " ".join((document.get("text_content") or "").split())
        if len(text) < 40:
            continue
        out.append(_bullet(text, date=document.get("date", "")))
        if len(out) >= limit:
            break
    return out


def build_slides(report, *, as_of: str = "", analysis_version: str = "",
                 brief=None, documents=()) -> list:
    """The deck, in narrative order, with every empty slide omitted.

    `documents` are the run's retrieved sources. When supplied, the factual
    slides are built from them — see `_document_bullets` for why.
    """
    from intent_engine.company_ingestion.coverage import (
        COMMERCIAL, CUSTOMERS, IDENTITY, INDEPENDENT, PRODUCT,
    )
    r = report.as_dict() if hasattr(report, "as_dict") else (report or {})
    company = r.get("company_name", "")
    thesis = r.get("thesis") or {}
    slides = []

    # 1. Company in one minute
    identity_bullets = _document_bullets(documents, {IDENTITY})
    for observation in meaningful_items(r.get("observations", []),
                                        key="excerpt"):
        if observation.get("source_class") == "company_owned":
            identity_bullets.append(_bullet(
                observation.get("excerpt", ""),
                evidence=[observation.get("observation_id")],
                date=observation.get("date", "")))
    slides.append(_slide("company", f"{company} in one minute",
                         identity_bullets[:3],
                         note="From the company's own public pages."))

    # 2. Central strategic view
    view_bullets = []
    if is_meaningful(thesis.get("view")):
        view_bullets.append(_bullet(thesis["view"]))
    if is_meaningful(thesis.get("transition")):
        view_bullets.append(_bullet(thesis["transition"]))
    if is_meaningful(thesis.get("why_care")):
        view_bullets.append(_bullet(f"Why it matters: {thesis['why_care']}"))
    slides.append(_slide("view", "The central strategic view", view_bullets,
                         kind="thesis"))

    # 3. What changed recently
    change_bullets = [
        # A shift's `evidence` is its EXCERPT — the words behind the change —
        # not a citation id. The id it cites is `observation_id`.
        _bullet(shift.get("title", ""), date=shift.get("date", ""),
                evidence=[shift.get("observation_id")])
        for shift in meaningful_items(r.get("shifts", []), key="title")]
    change_bullets += [
        _bullet(event.get("event", ""), date=event.get("date", ""))
        for event in meaningful_items(r.get("timeline", []), key="event")]
    slides.append(_slide("changed", "What changed recently", change_bullets,
                         note="Only dated evidence appears here."))

    # 4. Products, customers and market — the slide a reader most often wants
    #    first, and the one that must actually name the products.
    market_bullets = _document_bullets(
        documents, {PRODUCT, CUSTOMERS, COMMERCIAL, INDEPENDENT}, limit=4)
    for observation in meaningful_items(r.get("observations", []),
                                        key="excerpt"):
        if observation.get("source_class") in ("customer_voice",
                                               "independent_reporting"):
            market_bullets.append(_bullet(
                observation.get("excerpt", ""),
                evidence=[observation.get("observation_id")]))
    slides.append(_slide("market", "Products, customers and market",
                         market_bullets))

    # 5. Key strategic signals. Hypotheses first when synthesis produced any;
    #    otherwise the investor and strategy material the company published,
    #    which is a real signal slide rather than a substitute for one. A run
    #    with strong evidence but no hypotheses is common and should not lose
    #    a slide it can genuinely fill.
    from intent_engine.company_ingestion.coverage import INVESTOR, STRATEGY
    signal_bullets = [
        _bullet(h.get("title", "") or h.get("statement", ""),
                evidence=h.get("strongest_support_ids", []))
        for h in meaningful_items(r.get("hypotheses", []), key="title")]
    signal_bullets += [
        _bullet(s.get("finding", ""))
        for s in meaningful_items(r.get("surprises", []), key="finding")]
    if not signal_bullets:
        signal_bullets = _document_bullets(documents, {INVESTOR, STRATEGY})
    slides.append(_slide("signals", "Key strategic signals", signal_bullets))

    # 6. Main tension or risk
    tension_bullets = [
        _bullet(b.get("observed_tension", ""))
        for b in meaningful_items(r.get("blind_spots", []),
                                  key="observed_tension")]
    tension_bullets += [
        _bullet(f"Exposed: {v.get('exposed_layer', '')} — "
                f"{v.get('mechanism', '')}")
        for v in meaningful_items(r.get("vulnerabilities", []),
                                  key="exposed_layer")]
    slides.append(_slide("tension", "The main tension", tension_bullets))

    # 7. Opportunity to investigate
    opportunity_bullets = [
        _bullet(o.get("statement", ""))
        for o in meaningful_items(r.get("opportunities", []),
                                  key="statement")]
    slides.append(_slide("opportunity", "An opportunity worth investigating",
                         opportunity_bullets,
                         note="A question to test, not a recommendation."))

    # 8. Questions for leadership
    question_bullets = [
        _bullet(q.get("question", ""))
        for q in meaningful_items(r.get("questions", []), key="question")]
    slides.append(_slide("questions", "Questions for leadership",
                         question_bullets))

    # 9. Evidence and limitations. Not a content slide — it never counts
    #    toward the minimum, or a deck could reach five on disclaimers alone.
    from intent_engine.strategic_intelligence.editorial import (
        consolidate_limitations,
    )
    limitation_bullets = [
        _bullet(x) for x in consolidate_limitations(
            r.get("evidence_gaps", []),
            [f.get("message") for f in r.get("quality_findings", [])])]
    coverage = r.get("source_class_coverage", {}) or {}
    if coverage:
        limitation_bullets.insert(0, _bullet(
            "Built from " + ", ".join(f"{n} {c.replace('_', ' ')}"
                                      for c, n in sorted(coverage.items())
                                      if n) + " source(s)."))
    slides.append(_slide("evidence", "Evidence and limitations",
                         limitation_bullets, kind="evidence"))

    return [s for s in slides if s]


def meaningful_slide_count(slides) -> int:
    """Content slides only. The evidence slide is real and useful and is still
    not a finding, so it cannot help a thin deck reach the floor."""
    return sum(1 for s in slides if s["kind"] != "evidence")


def deck_is_presentable(slides) -> bool:
    return meaningful_slide_count(slides) >= MIN_MEANINGFUL_SLIDES


_CSS = """
<style>
.deck{--ink:#111827;--muted:#4b5563;--line:#d1d5db;--bg:#ffffff;
--panel:#f8fafc;--accent:#1d4ed8;--accent-ink:#ffffff;
font:16px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
color:var(--ink);background:var(--bg);max-width:900px;margin:0 auto;
padding:8px 16px 32px}
.deck *{box-sizing:border-box}
.deck .slide{display:none}
/* Order matters. The first slide is shown unconditionally, then hidden again
   only once some OTHER slide is targeted. Written the other way round — hiding
   everything and revealing the first via :has — a browser without :has drops
   the rule as invalid and the deck renders blank. This way the worst case is
   the first slide staying visible alongside the current one: degraded, still
   entirely readable. */
.deck .slide:first-of-type{display:block}
.deck .slide:target{display:block}
.deck:has(.slide:target) .slide:first-of-type:not(:target){display:none}
.deck .stage{border:1px solid var(--line);border-radius:14px;
background:var(--panel);padding:24px 26px;min-height:340px}
.deck h2{font-size:1.5rem;line-height:1.25;margin:0 0 14px;color:var(--ink)}
.deck ul{margin:0;padding-left:1.15rem}
.deck li{margin:0 0 12px;font-size:1.05rem}
.deck li .when{display:inline-block;font-size:.78rem;font-weight:700;
color:var(--muted);margin-right:8px}
.deck .note{color:var(--muted);font-size:.86rem;margin-top:16px}
.deck .bar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;
margin:16px 0 8px}
.deck .nav{display:inline-flex;gap:8px}
.deck .nav a,.deck .act a,.deck .act button{display:inline-block;
font-size:.9rem;font-weight:600;text-decoration:none;padding:9px 16px;
border-radius:9px;border:1px solid var(--line);background:#fff;
color:var(--ink);cursor:pointer}
.deck .nav a.primary{background:var(--accent);color:var(--accent-ink);
border-color:var(--accent)}
.deck .nav a:focus-visible,.deck .act a:focus-visible,
.deck .dots a:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.deck .count{color:var(--muted);font-size:.86rem;font-variant-numeric:tabular-nums}
.deck .dots{display:flex;gap:6px;flex-wrap:wrap;margin-left:auto}
.deck .dots a{width:26px;height:26px;display:grid;place-items:center;
border-radius:50%;border:1px solid var(--line);font-size:.72rem;
text-decoration:none;color:var(--muted);background:#fff}
.deck .act{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.deck .cites{margin-top:14px}
.deck .cites summary{cursor:pointer;color:var(--accent);font-size:.86rem;
font-weight:600}
.deck .cites li{font-size:.84rem;color:var(--muted);margin:.3rem 0}
.deck .meta{color:var(--muted);font-size:.8rem;margin-top:18px;
border-top:1px solid var(--line);padding-top:10px}
@media (max-width:600px){
.deck{padding:4px 10px 24px}.deck .stage{padding:18px 16px;min-height:280px}
.deck h2{font-size:1.25rem}.deck li{font-size:1rem}
.deck .dots{margin-left:0;width:100%}}
@media print{
.deck .slide{display:block!important;page-break-after:always;margin-bottom:20px}
.deck .bar,.deck .act,.deck .dots{display:none!important}
.deck .stage{border:none;background:none;min-height:0}
.deck .cites[open],.deck .cites{display:block}}
@media (prefers-color-scheme:dark){
.deck{--ink:#f3f4f6;--muted:#c3cad6;--line:#3a4454;--bg:#0f141c;
--panel:#161c26;--accent:#7aa2ff;--accent-ink:#0b1220}
.deck .nav a,.deck .act a,.deck .dots a{background:#1b222e;color:var(--ink)}}
</style>
"""

_KEYS = """
<script>
/* Progressive enhancement only: :target already switches slides, and Tab plus
   Enter already navigates. This adds arrow keys. If it never runs, the deck is
   unaffected. */
(function(){
  var deck=document.currentScript.parentNode;
  document.addEventListener('keydown',function(ev){
    if(ev.metaKey||ev.ctrlKey||ev.altKey)return;
    var t=(ev.target&&ev.target.tagName||'').toLowerCase();
    if(t==='input'||t==='textarea'||t==='select')return;
    var sel=ev.key==='ArrowRight'?'.js-next':ev.key==='ArrowLeft'?'.js-prev':'';
    if(!sel)return;
    var cur=deck.querySelector('.slide:target')||deck.querySelector('.slide');
    var link=cur&&cur.querySelector(sel);
    if(link){ev.preventDefault();link.click();}
  });
})();
</script>
"""


def render_deck(slides, *, company="", as_of="", analysis_version="",
                run_id="", csrf="", full_analysis_url="",
                cite_labels=None) -> str:
    """The whole deck as self-contained HTML.

    ``cite_labels`` maps an evidence id to the READABLE name of the source
    behind it. Without it the deck offered the reader forty-two links labelled
    `obs-src-4856bb8a9f80` — the tester pack asks them to open a citation and
    check it showed what they expected, and an opaque internal id cannot.
    """
    cite_labels = cite_labels or {}
    total = len(slides)
    dots = "".join(
        f'<a href="#slide-{_e(s["id"])}" aria-label="Go to slide {n + 1}: '
        f'{_e(s["title"])}">{n + 1}</a>' for n, s in enumerate(slides))

    out = []
    for n, slide in enumerate(slides):
        prev_id = slides[n - 1]["id"] if n > 0 else slides[-1]["id"]
        next_id = slides[(n + 1) % total]["id"]
        bullets = "".join(
            f'<li>' + (f'<span class="when">{_e(b["date"])}</span>'
                       if is_meaningful(b.get("date")) else '')
            + f'{_e(b["text"])}</li>' for b in slide["bullets"])
        citations = sorted({c for b in slide["bullets"]
                            for c in b.get("evidence", []) if c})
        # Citations are available on every slide and expanded on none: a reader
        # walking a deck needs to know the evidence is there and reachable, not
        # to read it now.
        cite_html = (
            f'<details class="cites"><summary>Evidence behind this slide '
            f'({len(citations)})</summary><ul>'
            + "".join(f'<li><a href="/runs/{_e(run_id)}/evidence/{_e(c)}">'
                      f'{_e(cite_labels.get(c) or c)}</a></li>'
                      for c in citations)
            + '</ul></details>') if citations and run_id else ''
        ask = (
            f'<form action="/runs/{_e(run_id)}/conversation" method="post" '
            f'style="display:inline">'
            f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
            f'<input type="hidden" name="slide" value="{_e(slide["id"])}">'
            f'<input type="hidden" name="question" '
            f'value="Explain this slide: {_e(slide["title"])}">'
            f'<button type="submit">Ask about this slide</button></form>'
        ) if run_id and csrf else ''
        out.append(
            f'<section class="slide" id="slide-{_e(slide["id"])}" '
            f'aria-label="{_e(slide["title"])}">'
            f'<div class="stage"><h2>{_e(slide["title"])}</h2>'
            f'<ul>{bullets}</ul>'
            + (f'<p class="note">{_e(slide["note"])}</p>'
               if is_meaningful(slide.get("note")) else '')
            + f'{cite_html}</div>'
            f'<div class="bar"><span class="nav">'
            f'<a class="js-prev" href="#slide-{_e(prev_id)}" '
            f'rel="prev">← Previous</a>'
            f'<a class="js-next primary" href="#slide-{_e(next_id)}" '
            f'rel="next">Next →</a></span>'
            f'<span class="count">Slide {n + 1} of {total}</span>'
            f'<span class="dots">{dots}</span></div>'
            f'<div class="act">{ask}'
            + (f'<a href="{_e(full_analysis_url)}">View full analysis</a>'
               if full_analysis_url else '')
            + f'</div>'
            f'<p class="meta">{_e(company)} · analysed {_e(as_of)} · '
            f'analysis version {_e(analysis_version)}</p>'
            f'</section>')
    return (_CSS + f'<div class="deck" role="region" '
            f'aria-roledescription="carousel" '
            f'aria-label="{_e(company)} presentation">'
            + "".join(out) + _KEYS + '</div>')
