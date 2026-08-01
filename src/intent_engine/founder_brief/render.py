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
        out.append(f"<h3>{_e(k.fact)}</h3>")
        out.append(_p(k.interpretation))
        out.append('<div class="sowhat"><span class="lbl">Why this '
                   f'matters</span>{_e(k.so_what)}</div>')
        if k.decision:
            out.append('<div class="decision"><span class="lbl">Decision '
                       f'affected</span>{_e(k.decision)}</div>')
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

    # --- what changed --------------------------------------------------------
    if b.what_changed:
        out.append("<h2>What changed</h2><ul class=\"changed\">")
        for item in b.what_changed:
            when = f'<span class="when">{_e(item["when"])}</span>' if item.get(
                "when") else ""
            out.append(f'<li class="card">{when}{_e(item["what"])}</li>')
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
        out.append('<h2>Claimed, but not independently shown</h2>')
        out.append('<div class="card"><ul>')
        out.extend(f"<li>{_e(c)}</li>" for c in b.claimed)
        out.append("</ul></div>")
    if b.unclear:
        out.append("<h2>What is unclear</h2><div class=\"card\"><ul>")
        out.extend(f"<li>{_e(u)}</li>" for u in b.unclear)
        out.append("</ul></div>")

    # --- actions -------------------------------------------------------------
    if b.next_actions:
        out.append("<h2>What I would do next</h2>")
        out.append('<div class="card"><ol class="actions">')
        out.extend(f"<li>{_e(a)}</li>" for a in b.next_actions)
        out.append("</ol></div>")

    if b.internal_questions:
        out.append("<h2>Three questions to answer internally</h2>")
        out.append('<div class="card"><ol class="actions">')
        out.extend(f"<li>{_e(q)}</li>" for q in b.internal_questions)
        out.append("</ol></div>")
    if b.public_proofs:
        out.append("<h2>Three public proofs that would build trust</h2>")
        out.append('<div class="card"><ol class="actions">')
        out.extend(f"<li>{_e(p)}</li>" for p in b.public_proofs)
        out.append("</ol></div>")

    # --- risk / unknown ------------------------------------------------------
    if b.biggest_risk or b.biggest_unknown:
        out.append("<h2>Risk and unknown</h2><div class=\"grid2\">")
        if b.biggest_risk:
            out.append('<div class="card"><span class="lbl small muted">'
                       f'Biggest risk</span>{_e(b.biggest_risk)}</div>')
        if b.biggest_unknown:
            out.append('<div class="card"><span class="lbl small muted">'
                       f'Biggest unknown</span>{_e(b.biggest_unknown)}</div>')
        out.append("</div>")

    # --- market context ------------------------------------------------------
    out.append(render_market(b.market_context))

    # --- confidence, last because it qualifies everything above --------------
    if b.confidence:
        out.append("<h2>How confident is this</h2><div class=\"card\">")
        out.append(f'<p><span class="conf">{_e(b.confidence)}.</span> '
                   f'{_e(b.confidence_reason)}</p>')
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
