"""Shared founder-facing CSS and the secondary layer renderers.

WHAT LIVES HERE, AND WHAT ROUTES TO IT
--------------------------------------
    BRIEF_CSS, LAYER_CSS   the shared stylesheet every founder page loads
    _deeper                the depth nav, used by every layer and by the
                           scrollable narrative
    render_dashboard       GET /runs/<id>/dashboard
    render_story           GET /runs/<id>/story
    render_actions         the prepared-artefact cards on the story layer
    confidence_sentence,   the "never a bare grade" contract, applied
    is_bare_grade          wherever a confidence word would otherwise stand
                           alone

EVERY PUBLIC RENDERER HERE IS ROUTED, AND A TEST KEEPS IT THAT WAY
------------------------------------------------------------------
`tests/test_no_dead_founder_renderers.py` fails if a `render_*` function in
this module, or a `_*_page` method on `WebApp`, has no caller in `src/`. The
exemption list is empty and is meant to stay empty.

`render_market` and `render_executive_brief` were deleted under that guard.
Both were unrouted, and both were kept alive by tests that asserted contracts
against HTML no founder could reach: the executive brief has been served from
the shared dossier since the deep-documents cycle, and market context reaches
the page through `layers.build_dashboard`, which reads `brief.market_context`.
The contracts were real -- no trading-engine performance on the page, and an
absent market series teaches instead of printing "Unavailable" -- so they moved
onto `build_dashboard`, which is the surface that actually serves them.

`_citations` is private and called from within this module, so it is not a
route of its own.

WHY THERE IS NO `render_brief` ANY MORE
---------------------------------------
It rendered the 60-second brief from `FounderBrief.key_insight`, and that field
is None whenever the thesis view is withheld -- while the composed
`FounderDecision` can be DECISION_READY at the same time, because it decides
across the whole hypothesis portfolio. So the page said "No strategic
conclusion is being asserted about this company" while the deck one click away
carried two options and a recommendation. Measured on the deployed preview,
commit a6866d6.

`founder_brief/narrative.py` replaced it: the default result renders the ONE
shared decision. Deleting this rather than leaving it unrouted is deliberate --
a second founder renderer built on a different source of truth is how that
contradiction happened, and leaving it here invites the next person to fix the
brief in the file nothing serves.
"""
from __future__ import annotations

from html import escape as _e
from typing import Optional

BRIEF_CSS = """
<style>
:root{--ink:#12161c;--muted:#5b6572;--line:#e3e7ec;--bg:#fff;--card:#fff;
--accent:#1c4ed8;--warn:#8a5300;--ok:#1a6b47;--soft:#f6f8fa}
@media (prefers-color-scheme:dark){:root{--ink:#e9edf2;--muted:#a8b2bf;
--line:#2b323c;--bg:#0f1319;--card:#151a21;--accent:#8fb0ff;--warn:#e0b070;
--ok:#7fd4ab;--soft:#171d25}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main.fb{max-width:56rem;margin:0 auto;padding:1.5rem 1.15rem 4rem}
.fb h1{font-size:1.55rem;line-height:1.25;margin:.2rem 0 .35rem;
letter-spacing:-.01em}
.fb .does{font-size:1.05rem;color:var(--muted);margin:0 0 1.4rem;max-width:44rem}
.fb h2{font-size:.76rem;text-transform:uppercase;letter-spacing:.08em;
color:var(--muted);margin:1.6rem 0 .5rem;font-weight:650}
.fb h3{font-size:1.02rem;margin:0 0 .35rem;line-height:1.35}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:1.05rem 1.15rem;margin:.55rem 0}
.headline{border-left:3px solid var(--accent);padding-left:1.05rem}
.headline p{margin:.45rem 0}
.sowhat{background:var(--soft);border-radius:10px;padding:.85rem 1rem;
margin:.7rem 0 0}
.sowhat .lbl,.decision .lbl{display:block;font-size:.7rem;font-weight:700;
text-transform:uppercase;letter-spacing:.07em;color:var(--muted);
margin-bottom:.2rem}
.decision{border-left:3px solid var(--warn);padding-left:.9rem;margin:.9rem 0 0}
ol.actions{margin:.4rem 0 0;padding-left:1.15rem}
ol.actions li{margin:.4rem 0}
.grid2{display:grid;gap:.55rem;grid-template-columns:1fr 1fr}
@media(max-width:640px){.grid2{grid-template-columns:1fr}}
.changed li{margin:.5rem 0;list-style:none}
.changed .when{font-variant-numeric:tabular-nums;color:var(--muted);
font-size:.82rem;display:block}
ul.changed{padding:0;margin:.3rem 0}
.conf{display:inline-block;font-weight:650}
.muted{color:var(--muted)}
.small{font-size:.88rem}
.chips{display:flex;flex-wrap:wrap;gap:.4rem;margin:.5rem 0 0;padding:0}
.chips li{list-style:none;border:1px solid var(--line);border-radius:999px;
padding:.2rem .6rem;font-size:.82rem}
.chips .yes{border-color:var(--ok);color:var(--ok)}
.chips .no{border-color:var(--warn);color:var(--warn)}
.deeper{display:flex;flex-wrap:wrap;gap:.5rem;margin:2rem 0 0;padding:1rem 0 0;
border-top:1px solid var(--line)}
.deeper a{color:var(--accent);text-decoration:none;border:1px solid var(--line);
border-radius:8px;padding:.45rem .8rem;font-size:.9rem}
.deeper a:hover{border-color:var(--accent)}
a:focus-visible,button:focus-visible,summary:focus-visible{outline:2px solid
var(--accent);outline-offset:2px}
details{margin:.5rem 0}
summary{cursor:pointer;color:var(--accent);font-size:.9rem}
@media print{.deeper{display:none}body{background:#fff;color:#000}
.card{break-inside:avoid;border-color:#bbb}}
</style>
"""


def _citations(evidence_ids, run_id: str, label: str = "Evidence",
               labels=None) -> str:
    """Expandable citations, visually secondary but keyboard-reachable.

    Behind a <details> on purpose: a founder reading a 60-second answer is not
    reading source ids, and a wall of them above the fold is the "source
    metadata wall" this rebuild removed. One click away, every one resolves
    through the real evidence route.

    NAMED BY THE PAGE THEY CITE, not by an internal identifier. The first
    grounded run on the deployed preview (Palantir, 2026-08-03) rendered
    "Sources behind this (8)" over a list reading `obs-src-eb15293b7148`,
    `obs-src-4856bb8a9f80` -- eight opaque strings where a reader expects to
    see what was read. The map that turns those into "About Palantir" already
    existed and served the evidence DETAIL page; this list simply never asked
    for it.

    Titles are never invented: an id with no readable source behind it still
    renders as the id, because a made-up document name is worse than an ugly
    one.
    """
    ids = [str(e) for e in (evidence_ids or ()) if e]
    if not ids or not run_id:
        return ""
    labels = labels or {}
    links = "".join(
        f'<li><a href="/runs/{_e(run_id)}/evidence/{_e(i)}">'
        f'{_e(labels.get(i) or i)}</a></li>'
        for i in dict.fromkeys(ids))
    return (f'<details class="cites"><summary>{_e(label)} '
            f'({len(set(ids))})</summary><ul>{links}</ul></details>')


def _p(text: str) -> str:
    return f"<p>{_e(text)}</p>" if text else ""


def _deeper(run_id: str) -> str:
    """Depth is offered, never required."""
    rid = _e(run_id)
    # `Presentation` stays reachable: /slides is a working layer and dropping
    # its only link orphaned it. Depth is offered, never required.
    return (
        '<nav class="deeper" aria-label="More depth">'
        f'<a href="/runs/{rid}/story">The full story</a>'
        f'<a href="/runs/{rid}/dashboard">Intelligence</a>'
        f'<a href="/runs/{rid}/brief">Executive brief</a>'
        f'<a href="/runs/{rid}/slides">Presentation</a>'
        f'<a href="/runs/{rid}/sources">Evidence and sources</a>'
        f'<a href="/runs/{rid}/full">Full analysis</a>'
        "</nav>")


# ===========================================================================
# LAYER RENDERERS — dashboard, decision story, executive brief, actions
# ===========================================================================
LAYER_CSS = """
<style>
.dash{display:grid;gap:.7rem;grid-template-columns:1fr 1fr;margin:.5rem 0}
@media(max-width:760px){.dash{grid-template-columns:1fr}}
/* A TILE WITH A CHART SPANS BOTH COLUMNS. Measured at 1440px: a chart in a
   half-width tile rendered 317px wide against a 640-unit viewBox, scaling its
   11px axis labels to under 5px -- present, and unreadable. A chart nobody
   can read is decoration, and decoration is what stops a reader trusting the
   charts that do mean something. */
.dash .tile.haschart{grid-column:1/-1}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:1rem 1.1rem}
.tile h3{margin:0 0 .4rem;font-size:1rem}
.tile .rows{margin:.5rem 0 0;padding:0;list-style:none;font-size:.92rem}
.tile .rows li{display:flex;gap:.6rem;padding:.3rem 0;
border-top:1px solid var(--line)}
.tile .rows .k{color:var(--muted);min-width:7.5rem;flex:0 0 auto}
.tile.off{opacity:.85}
.story section{scroll-margin-top:4.2rem;padding:1.3rem 0;
border-top:1px solid var(--line)}
.story section:first-of-type{border-top:0}
.storynav{position:sticky;top:0;z-index:5;background:var(--bg);
border-bottom:1px solid var(--line);padding:.5rem 0;margin:0 0 .5rem;
display:flex;gap:.4rem;overflow-x:auto;flex-wrap:nowrap;
-webkit-overflow-scrolling:touch;scrollbar-width:thin}
.storynav a{white-space:nowrap;font-size:.84rem;color:var(--muted);
text-decoration:none;padding:.25rem .55rem;border-radius:999px}
.storynav a[aria-current="true"]{color:var(--accent);
border:1px solid var(--accent)}
.prog{height:3px;background:var(--accent);width:0;position:sticky;top:0;z-index:6}
.act{border:1px solid var(--line);border-radius:12px;padding:1rem 1.1rem;
margin:.55rem 0;background:var(--card)}
.act dt{font-size:.7rem;text-transform:uppercase;letter-spacing:.07em;
color:var(--muted);font-weight:700;margin-top:.5rem}
.act dd{margin:.15rem 0 0}
.approve{background:var(--soft);border-radius:8px;padding:.6rem .8rem;
margin:.7rem 0 0;font-size:.9rem}
@media print{.storynav,.prog{display:none}}
</style>
"""


def render_dashboard(modules, *, charts=None) -> str:
    """Tiles that each answer what changed / so what / what to watch.

    An unavailable module is rendered as a stated gap. It is not hidden,
    because a missing section a reader cannot see is a missing section they
    assume was checked.

    `charts` maps a module key to rendered SVG. A chart sits INSIDE its tile,
    under the sentence it illustrates and above the "why this matters" block,
    so the conclusion is read before the picture rather than inferred from it.
    Every tile keeps its text alternative whether or not a chart appears --
    the tile has to survive being printed, screen-read, or rendered where the
    data was too thin to draw.
    """
    charts = charts or {}
    out = [LAYER_CSS, '<h2>Executive intelligence</h2>', '<div class="dash">']
    for m in modules:
        d = m if isinstance(m, dict) else m.as_dict()
        if not d.get("available"):
            # AN EMPTY STATE STILL HAS TO TEACH.
            #
            # On six live companies every dashboard opened with a stack of
            # cards whose whole content was the word "Unavailable". That is an
            # engineering status: it tells a founder the software failed,
            # rather than what is and is not knowable about this company.
            # The refusal to invent a number stays; the card now carries why
            # the gap matters and what would close it.
            tile = [f'<div class="tile off"><h3>{_e(d["title"])}</h3>',
                    f'<p class="small muted">Not established — '
                    f'{_e(d.get("unavailable_reason", ""))}</p>']
            if d.get("so_what"):
                tile.append('<div class="sowhat"><span class="lbl">Why this '
                            f'matters</span>{_e(d["so_what"])}</div>')
            if d.get("what_to_watch"):
                tile.append(f'<p class="small muted">What would settle it: '
                            f'{_e(d["what_to_watch"])}</p>')
            out.append("".join(tile) + "</div>")
            continue
        chart = charts.get(d.get("key"))
        out.append(f'<div class="tile{" haschart" if chart else ""}">'
                   f'<h3>{_e(d["title"])}</h3>')
        # THE SAME SENTENCE, THREE TIMES. Measured on the deployed dashboard:
        # the tile printed `what_changed`, then a chart whose headline IS
        # `what_changed`, then `text_alternative`, which restates it again. A
        # reader met "the shares rose 5.4% over the past year" three times in
        # one tile.
        #
        # The chart's headline is the conclusion, and its <desc> is the text
        # alternative a screen reader gets -- so when a chart renders, the
        # tile contributes the interpretation and lets the figure carry the
        # fact.
        if d.get("what_changed") and not chart:
            out.append(f'<p>{_e(d["what_changed"])}</p>')
        if chart:
            out.append(chart)
        if d.get("rows"):
            out.append('<ul class="rows">')
            for row in d["rows"]:
                out.append(f'<li><span class="k">{_e(str(row.get("label","")))}'
                           f'</span><span>{_e(str(row.get("value","")))}</span>'
                           f'</li>')
            out.append("</ul>")
        if d.get("so_what"):
            out.append('<div class="sowhat"><span class="lbl">Why this '
                       f'matters</span>{_e(d["so_what"])}</div>')
        if d.get("what_to_watch"):
            out.append(f'<p class="small muted">What to watch: '
                       f'{_e(d["what_to_watch"])}</p>')
        if d.get("text_alternative") and not chart:
            # Textual equivalent for screen readers and print, where a visual
            # tile conveys nothing on its own. A rendered chart carries its
            # own <desc>, so repeating it here is duplication rather than
            # accessibility.
            out.append(f'<p class="small muted visually-alt">'
                       f'{_e(d["text_alternative"])}</p>')
        out.append("</div>")
    out.append("</div>")
    from intent_engine.founder_brief.layers import MARKET_DISCLAIMER
    out.append(f'<p class="small muted">{_e(MARKET_DISCLAIMER)}</p>')
    return "".join(out)


def render_story(sections, *, run_id: str = "") -> str:
    """Scrollable narrative. Every section is reachable by scrolling alone —
    no Next button stands between the reader and the answer."""
    out = [LAYER_CSS, '<div class="prog" id="prog" aria-hidden="true"></div>',
           '<nav class="storynav" aria-label="Sections">']
    for i, s in enumerate(sections):
        current = ' aria-current="true"' if i == 0 else ""
        out.append(f'<a href="#{_e(s["key"])}"{current}>{_e(s["title"])}</a>')
    out.append("</nav><div class=\"story\">")
    for s in sections:
        out.append(f'<section id="{_e(s["key"])}" tabindex="-1">'
                   f'<h2>{_e(s["title"])}</h2>')
        for p in s["paragraphs"]:
            out.append(f"<p>{_e(p)}</p>")
        out.append("</section>")
    out.append("</div>")
    out.append(
        '<script>(function(){var p=document.getElementById("prog");'
        'var ls=[].slice.call(document.querySelectorAll(".storynav a"));'
        'function u(){var h=document.documentElement;'
        'p.style.width=(h.scrollTop/(h.scrollHeight-h.clientHeight||1)*100)+"%";'
        'var best=null;[].slice.call(document.querySelectorAll(".story section"))'
        '.forEach(function(s){if(s.getBoundingClientRect().top<120)best=s.id;});'
        'ls.forEach(function(a){a.setAttribute("aria-current",'
        'a.getAttribute("href")==="#"+best?"true":"false");});}'
        'addEventListener("scroll",u,{passive:true});u();})();</script>')
    return "".join(out)


def render_actions(actions) -> str:
    """Prepared artefacts. Every card states what will NOT happen."""
    if not actions:
        return ""
    out = [LAYER_CSS, "<h2>What this can prepare for you</h2>",
           '<p class="small muted">Intelligence is above. These are artefacts '
           'the product can draft from it — nothing leaves this page.</p>']
    for a in actions:
        d = a if isinstance(a, dict) else a.as_dict()
        out.append(f'<div class="act"><h3>{_e(d["title"])}</h3><dl>')
        for label, key in (("Intelligence", "intelligence"),
                           ("Recommended action", "recommended_action"),
                           ("Why", "why"),
                           ("Expected result", "expected_result")):
            if d.get(key):
                out.append(f'<dt>{label}</dt><dd>{_e(d[key])}</dd>')
        out.append("</dl>")
        out.append(f'<p class="approve"><strong>Approval required.</strong> '
                   f'{_e(d["approval_required"])}</p></div>')
    return "".join(out)


#: Grades that mean nothing on their own. "Low" is not a finding; the reason
#: is. A founder cannot act on a word, only on what is missing.
BARE_GRADES = {"low", "medium", "high", "moderate", "limited", "partial",
               "strong", "weak", "uncertain", "unknown", "none"}


def is_bare_grade(text) -> bool:
    """True when a string is only a confidence word (with trimming)."""
    t = (text or "").strip().strip(".,;:—-").lower()
    if not t:
        return False
    t = t.replace(" confidence", "").replace("confidence ", "").strip()
    return t in BARE_GRADES


def confidence_sentence(grade, reason) -> str:
    """Never show a grade without the reason that earns it.

    A bare "Low" tells a founder to distrust the reading but not what would
    fix it. The reason is the actionable half, so the reason leads and the
    grade -- when it adds anything at all -- trails it.
    """
    grade = (grade or "").strip().strip(".")
    reason = (reason or "").strip()
    if not reason:
        # Nothing to explain it with: a naked grade is worse than silence,
        # because it looks like a finding.
        return "" if is_bare_grade(grade) else grade
    if not grade or is_bare_grade(grade):
        return reason
    return f"{reason} ({grade})" if grade.lower() not in reason.lower() \
        else reason
