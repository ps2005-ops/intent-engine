"""The 60-second founder brief, rendered.

LAYOUT IS THE PRODUCT DECISION HERE
-----------------------------------
The order below is the answer to the customer's complaint. A founder reads
top-down and stops when they have enough, so the sequence is:

    what it does -> what changed -> the insight -> SO WHAT -> the decision
    -> what I would do -> risk / unknown -> confidence

"So what" and the decision appear ABOVE the fold on mobile, before evidence,
before charts and before navigation. If a reader stops after two cards they
still have the consequence.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
No run identifier, no pipeline state, no source enum, no hypothesis name, no
analysis version, no repeated dates, no citation metadata wall. Those belong in
the evidence layer, one click away, and every one of them on this screen costs
a founder attention they were going to spend on the answer.

ACCESSIBILITY IS NOT A PASS AT THE END
--------------------------------------
One `<main>`, one `<h1>`, headings in order, every colour meeting AA in both
schemes, focus visible, and each chart carrying a textual equivalent — because
a chart that only exists as a shape is a chart a screen reader user cannot read
and a print-out loses.
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


def _p(text: str) -> str:
    return f"<p>{_e(text)}</p>" if text else ""


def _clip(text: str, words: int) -> str:
    """Trim for the PRIMARY view only.

    The full sentence stays on the insight object, so the decision story and
    executive brief still show it complete. This is a reading-budget decision
    about one screen, not a truncation of the intelligence -- the 60-second
    brief has ~250 words to spend and a 60-word interpretation spends a
    quarter of them before the reader reaches the decision.
    """
    parts = (text or "").split()
    if len(parts) <= words:
        return text or ""
    return " ".join(parts[:words]).rstrip(",;:") + "…"


def render_brief(brief, *, run_id: str = "", links: bool = True) -> str:
    """The whole 60-second screen. One `<main>`, one `<h1>`."""
    b = brief
    out = [BRIEF_CSS, '<main class="fb">']

    out.append(f"<h1>{_e(b.company)}</h1>")
    if b.what_it_does:
        out.append(f'<p class="does">{_e(b.what_it_does)}</p>')
    else:
        out.append('<p class="does muted">The public material does not state '
                   'plainly what this company sells.</p>')

    # --- the answer, first ---------------------------------------------------
    if b.key_insight:
        k = b.key_insight
        out.append("<h2>The most important thing</h2>")
        out.append('<div class="card headline">')
        out.append(f"<h3>{_e(_clip(k.fact, 34))}</h3>")
        out.append(_p(_clip(k.interpretation, 38)))
        out.append('<div class="sowhat"><span class="lbl">Why this '
                   f'matters</span>{_e(_clip(k.so_what, 34))}</div>')
        if k.decision:
            out.append('<div class="decision"><span class="lbl">Decision '
                       f'affected</span>{_e(_clip(k.decision, 30))}</div>')
        out.append("</div>")
    elif b.verified or b.unclear:
        out.append("<h2>What a customer can actually verify</h2>")
        out.append('<div class="card headline">')
        out.append("<h3>There is not enough public evidence to read this "
                   "company&rsquo;s strategy — but that is itself the "
                   "finding.</h3>")
        out.append('<div class="sowhat"><span class="lbl">Why this matters'
                   '</span>A prospective customer, partner or investor sees '
                   'exactly what this analysis saw. What cannot be verified '
                   'here cannot be verified by them either.</div>')
        out.append("</div>")

    # --- what I would do next, BEFORE the history -----------------------------
    # Order is the product decision: a reader who stops after the decision must
    # already have the action. "What changed" is context for a reader who has
    # not stopped, so it comes after.
    if b.next_actions:
        out.append("<h2>What I would do next</h2>")
        out.append('<div class="card"><ol class="actions">')
        out.extend(f"<li>{_e(_clip(a, 26))}</li>"
                   for a in b.next_actions[:3])
        out.append("</ol></div>")

    # --- what changed --------------------------------------------------------
    if b.what_changed:
        out.append("<h2>What changed</h2><ul class=\"changed\">")
        for item in b.what_changed[:2]:
            when = f'<span class="when">{_e(item["when"])}</span>' if item.get(
                "when") else ""
            out.append(f'<li class="card">{when}'
                       f'{_e(_clip(item["what"], 22))}</li>')
        out.append("</ul>")

    # --- sparse-mode product -------------------------------------------------
    if b.customer_can_see:
        out.append("<h2>What a visitor can confirm</h2><ul class=\"chips\">")
        for item in b.customer_can_see:
            cls = "yes" if item["present"] else "no"
            mark = "visible" if item["present"] else "not visible"
            out.append(f'<li class="{cls}">{_e(item["item"])} — {mark}</li>')
        out.append("</ul>")
    if b.claimed:
        out.append('<h2>Claimed, not shown</h2>')
        out.append('<div class="card"><ul>')
        out.extend(f"<li>{_e(_clip(c, 20))}</li>" for c in b.claimed[:2])
        out.append("</ul></div>")
    if b.unclear:
        out.append("<h2>What is unclear</h2><div class=\"card\"><ul>")
        out.extend(f"<li>{_e(_clip(u, 16))}</li>" for u in b.unclear[:2])
        out.append("</ul></div>")

    if b.internal_questions:
        out.append("<h2>Three questions to answer internally</h2>")
        out.append('<div class="card"><ol class="actions">')
        out.extend(f"<li>{_e(_clip(q, 22))}</li>"
                   for q in b.internal_questions)
        out.append("</ol></div>")
    if b.public_proofs:
        # Secondary by design: these are what to publish LATER. The diagnosis
        # of what is true NOW is the primary product, and putting six more
        # bullets above the fold would push the reading budget past a
        # 60-second read.
        out.append('<details><summary>Three public proofs that would build '
                   'trust</summary><ol class="actions">')
        out.extend(f"<li>{_e(_clip(p, 20))}</li>" for p in b.public_proofs)
        out.append("</ol></details>")

    # --- risk / unknown ------------------------------------------------------
    if b.biggest_risk or b.biggest_unknown:
        out.append("<h2>Risk and unknown</h2><div class=\"grid2\">")
        if b.biggest_risk:
            out.append('<div class="card"><span class="lbl small muted">'
                       f'Biggest risk</span>'
                       f'{_e(_clip(b.biggest_risk, 26))}</div>')
        if b.biggest_unknown:
            out.append('<div class="card"><span class="lbl small muted">'
                       f'Biggest unknown</span>'
                       f'{_e(_clip(b.biggest_unknown, 26))}</div>')
        out.append("</div>")

    # Market context belongs on the dashboard, not the 60-second screen: it is
    # supporting detail, and it was costing ~60 words of the reading budget
    # before the reader reached confidence.

    # --- confidence, last because it qualifies everything above --------------
    if b.confidence:
        out.append("<h2>How confident is this</h2><div class=\"card\">")
        out.append(f'<p><span class="conf">{_e(b.confidence)}.</span> '
                   f'{_e(_clip(b.confidence_reason, 30))}</p>')
        if b.limitations:
            out.append('<details><summary>What this analysis could not see'
                       '</summary><ul>')
            out.extend(f"<li>{_e(l)}</li>" for l in b.limitations)
            out.append("</ul></details>")
        out.append("</div>")

    if links and run_id:
        out.append(_deeper(run_id))
    out.append("</main>")
    return "".join(out)


def render_market(context) -> str:
    """Market modules, each with what changed / so what / what to watch.

    An unavailable module says "Unavailable" and why. It never renders an empty
    axis, because a chart with no line reads as "flat" — a claim the missing
    data does not support.
    """
    if context is None:
        return ""
    ctx = context if isinstance(context, dict) else context.as_dict()
    out = ["<h2>Market context</h2>"]
    if not ctx.get("available"):
        return "".join(out + [
            '<div class="card muted small">Unavailable — '
            f'{_e(ctx.get("reason", "no market data"))}.</div>'])

    for name, module in (ctx.get("modules") or {}).items():
        out.append('<div class="card">')
        out.append(f'<h3>{_e(name.replace("_", " ").title())}</h3>')
        out.append(_p(module.get("what_changed", "")))
        out.append('<div class="sowhat"><span class="lbl">Why this matters'
                   f'</span>{_e(module.get("so_what", ""))}</div>')
        if module.get("what_to_watch"):
            out.append(f'<p class="small muted">What to watch: '
                       f'{_e(module["what_to_watch"])}</p>')
        out.append("</div>")

    for limitation in (ctx.get("limitations") or ()):
        out.append(f'<p class="small muted">{_e(limitation)}</p>')
    out.append(f'<p class="small muted">{_e(ctx.get("disclaimer", ""))} '
               f'As of {_e(ctx.get("as_of", "unknown"))}.</p>')
    return "".join(out)


def _deeper(run_id: str) -> str:
    """Depth is offered, never required."""
    rid = _e(run_id)
    return (
        '<nav class="deeper" aria-label="More depth">'
        f'<a href="/runs/{rid}/story">The full story</a>'
        f'<a href="/runs/{rid}/brief">Executive brief</a>'
        f'<a href="/runs/{rid}/sources">Evidence and sources</a>'
        f'<a href="/runs/{rid}/full">Full research</a>'
        "</nav>")


# ===========================================================================
# LAYER RENDERERS — dashboard, decision story, executive brief, actions
# ===========================================================================
LAYER_CSS = """
<style>
.dash{display:grid;gap:.7rem;grid-template-columns:1fr 1fr;margin:.5rem 0}
@media(max-width:760px){.dash{grid-template-columns:1fr}}
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


def render_dashboard(modules) -> str:
    """Tiles that each answer what changed / so what / what to watch.

    An unavailable module is rendered as a stated gap. It is not hidden,
    because a missing section a reader cannot see is a missing section they
    assume was checked.
    """
    out = [LAYER_CSS, '<h2>Executive intelligence</h2>', '<div class="dash">']
    for m in modules:
        d = m if isinstance(m, dict) else m.as_dict()
        if not d.get("available"):
            out.append(f'<div class="tile off"><h3>{_e(d["title"])}</h3>'
                       f'<p class="small muted">Unavailable — '
                       f'{_e(d.get("unavailable_reason", ""))}</p></div>')
            continue
        out.append(f'<div class="tile"><h3>{_e(d["title"])}</h3>')
        if d.get("what_changed"):
            out.append(f'<p>{_e(d["what_changed"])}</p>')
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
        if d.get("text_alternative"):
            # Textual equivalent for screen readers and print, where a visual
            # tile conveys nothing on its own.
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


def render_executive_brief(built) -> str:
    out = [LAYER_CSS, '<h2>Executive brief</h2>']
    for s in built.get("sections", []):
        out.append(f'<h3>{_e(s["title"])}</h3>')
        for p in s["paragraphs"]:
            out.append(f"<p>{_e(p)}</p>")
    budget = built.get("budget", {})
    out.append(f'<p class="small muted">{built.get("words", 0)} words '
               f'(target {budget.get("min")}–{budget.get("max")}). '
               f'{_e(built.get("note", ""))}</p>')
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
