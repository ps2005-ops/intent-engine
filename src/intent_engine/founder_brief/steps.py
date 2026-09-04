"""The three steps the product did not have: Introduction, History, Connect.

Each renders from the canonical `StrategicRead` (steps 1 and 6) or the
canonical `Timeline` (step 5), so nothing here decides anything -- it is
presentation of one object, which is what §56 requires and what a page that
reaches its own conclusion violates.

WHY THE INTRODUCTION IS SYNTHESIZED (§22)
-----------------------------------------
The old opener was the best sentence off the company's own website, clipped
to 180 characters. For Cloudflare that produced

    "Cloudflare's mission is to help build a better Internet. We have built a
     global network that delivers a broad range of services to businesses of
     all sizes and in all…"

which is (a) marketing the reader has already seen, (b) about the mission
rather than the business, and (c) cut off mid-clause. The company's own words
are still on the page -- quoted, attributed, and complete -- because what a
company says about itself is real evidence. It is no longer the first thing a
customer reads, because the first thing a customer reads should be something
only this product could have written.

THE HISTORY SLIDER IS PURE CSS
------------------------------
Radio inputs plus `:checked ~` sibling selectors. No JavaScript, so it works
under the strictest CSP, in a printed page, and with a screen reader that
already understands a radio group. Each date is a real focusable control with
a real label, which a JS slider would have had to reimplement badly.
"""
from __future__ import annotations

from html import escape
from typing import Optional, Sequence

from intent_engine.executive import history_rewind as HR
from intent_engine.executive.strategic_read import (BOUNDED_INFERENCE,
                                                    OBSERVED,
                                                    READ_UNIDENTIFIED,
                                                    STANDING_PROSE,
                                                    STRONGLY_INFERRED,
                                                    UNMEASURED)
from intent_engine.founder_brief import flow
from intent_engine.founder_brief import history_chart as HC


def _e(text) -> str:
    return escape(str(text or ""), quote=True)


STEP_CSS = """
<style>
.step{max-width:52rem;margin:0 auto;padding:0 1rem}
.step .kicker{font-size:.72rem;text-transform:uppercase;letter-spacing:.1em;
color:var(--muted);font-weight:700;margin:0 0 .3rem}
.step h1{font-size:clamp(1.6rem,4vw,2.3rem);line-height:1.15;margin:0 0 .6rem}
.step .lede{font-size:clamp(1.02rem,2.2vw,1.18rem);line-height:1.55;
margin:0 0 1rem}
.step .subject{font-size:.86rem;color:var(--muted);margin:-.3rem 0 .9rem;
letter-spacing:.01em}
.readbox{border:1px solid var(--line);border-left:4px solid var(--accent);
border-radius:12px;background:var(--card);padding:1.1rem 1.2rem;margin:1.4rem 0}
.readbox h2{margin:0 0 .5rem;font-size:.74rem;text-transform:uppercase;
letter-spacing:.09em;color:var(--muted)}
.readbox p{margin:.45rem 0}
.readbox .q{font-size:1.06rem;font-weight:600}
.readbox.rec{border-left-color:var(--ok,#1a6b47)}
.readbox.rec .n{font-size:.7rem;text-transform:uppercase;letter-spacing:.07em;
color:var(--muted);font-weight:700;margin-right:.35rem}
.stand{display:inline-block;font-size:.68rem;text-transform:uppercase;
letter-spacing:.06em;border:1px solid var(--line);border-radius:999px;
padding:.08rem .5rem;color:var(--muted);margin-left:.4rem;white-space:nowrap}
.stand.obs{border-color:var(--accent);color:var(--accent)}
.matters{list-style:none;margin:1.1rem 0;padding:0;display:grid;gap:.6rem}
.matters li{border:1px solid var(--line);border-radius:10px;
padding:.75rem .9rem;background:var(--card)}
.matters .n{font-size:.7rem;color:var(--muted);font-weight:700;
letter-spacing:.08em}
.quote{border-left:3px solid var(--line);padding:.3rem 0 .3rem .9rem;
margin:1.2rem 0;color:var(--muted);font-style:italic}
.quote cite{display:block;font-style:normal;font-size:.8rem;margin-top:.3rem}
.chapters section{padding:1.1rem 0;border-top:1px solid var(--line)}
.chapters h3{margin:0 0 .35rem;font-size:1.02rem}
.chapters p{margin:0}
/* --- step 6 feedback ---------------------------------------------------- */
.fbx{border:1px solid var(--line);border-radius:12px;padding:1.1rem 1.2rem;
margin:1.6rem 0;background:var(--card)}
.fbx h2{margin:0 0 .6rem;font-size:1.05rem;text-transform:none;
letter-spacing:0;color:var(--fg)}
.fbx fieldset{border:0;padding:0;margin:0 0 .9rem}
.fbx legend{font-size:.8rem;color:var(--muted);font-weight:700;padding:0;
margin-bottom:.35rem}
.fbx .scale{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;
margin:0;font-size:.8rem;color:var(--muted)}
.fbx .sc{display:inline-flex;align-items:center;gap:.25rem;
border:1px solid var(--line);border-radius:8px;padding:.3rem .6rem;
cursor:pointer;font-size:.95rem;color:var(--fg)}
.fbx .tags{display:flex;flex-wrap:wrap;gap:.4rem}
.fbx .tag{display:inline-flex;align-items:center;gap:.3rem;
border:1px solid var(--line);border-radius:999px;padding:.24rem .7rem;
font-size:.83rem;cursor:pointer}
.fbx label[for]{display:block;font-size:.83rem;color:var(--muted);
margin-bottom:.2rem}
.fbx input[type=text],.fbx input:not([type]){width:100%;box-sizing:border-box;
padding:.5rem .6rem;border:1px solid var(--line);border-radius:8px;
font:inherit;background:var(--bg,#fff);color:var(--fg)}
.fbx button{padding:.55rem 1.1rem;border-radius:9px;border:0;
background:var(--accent);color:#fff;font-weight:650;cursor:pointer;
font-size:.95rem}
.fbx .fb-priv{font-size:.78rem;color:var(--muted);margin:.7rem 0 0}
.fbx .fb-ok{border-left:3px solid var(--accent);padding-left:.7rem;
margin:0 0 .9rem}
/* --- history slider, JS-free ------------------------------------------- */
.rewind input[type=radio]{position:absolute;opacity:0;pointer-events:none}
.rail{display:flex;gap:.25rem;align-items:flex-end;margin:1.1rem 0 .3rem;
overflow-x:auto;padding-bottom:.4rem;-webkit-overflow-scrolling:touch}
.rail label{flex:1 1 0;min-width:5.2rem;cursor:pointer;text-align:center;
border:1px solid var(--line);border-bottom-width:3px;border-radius:8px 8px 0 0;
padding:.5rem .35rem;background:var(--card);font-size:.78rem;color:var(--muted)}
.rail label b{display:block;font-size:.86rem;color:var(--fg);font-weight:650}
.vint{display:none;border:1px solid var(--line);border-radius:0 12px 12px 12px;
padding:1.1rem 1.2rem;background:var(--card)}
.vint h2{margin:0 0 .2rem;font-size:1.15rem}
.vwall{font-size:.85rem;color:var(--muted);margin:.1rem 0 1rem}
.panels{display:grid;gap:.8rem;grid-template-columns:1fr 1fr;margin:0}
@media(max-width:720px){.panels{grid-template-columns:1fr}}
.panels div{border:1px solid var(--line);border-radius:10px;padding:.75rem .9rem}
.panels div.after{border-color:var(--accent);border-style:dashed;
grid-column:1/-1}
.panels h3{margin:0 0 .3rem;font-size:.72rem;text-transform:uppercase;
letter-spacing:.07em;color:var(--muted);font-weight:700}
.panels p{margin:0;font-size:.93rem}
.cfact{margin:1rem 0 0;border-top:1px solid var(--line);padding-top:.9rem}
.cfact dt{font-size:.7rem;text-transform:uppercase;letter-spacing:.07em;
color:var(--muted);font-weight:700;margin-top:.55rem}
.cfact dd{margin:.15rem 0 0}
/* --- connect ------------------------------------------------------------ */
.conn{display:grid;gap:.7rem;grid-template-columns:1fr 1fr;margin:1.1rem 0}
@media(max-width:720px){.conn{grid-template-columns:1fr}}
.conn div{border:1px solid var(--line);border-radius:10px;padding:.8rem .95rem;
background:var(--card)}
.conn h3{margin:0 0 .2rem;font-size:.95rem}
.conn p{margin:0;font-size:.9rem;color:var(--muted)}
.tag{display:inline-block;font-size:.66rem;text-transform:uppercase;
letter-spacing:.07em;border-radius:999px;padding:.1rem .5rem;font-weight:700;
border:1px solid var(--line);color:var(--muted);margin-bottom:.4rem}
.tag.on{border-color:var(--accent);color:var(--accent)}
.chain{list-style:none;margin:1rem 0;padding:0;display:grid;gap:.5rem}
.chain li{border:1px solid var(--line);border-radius:10px;padding:.7rem .9rem;
background:var(--card)}
.chain .st{font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;
color:var(--muted);font-weight:700}
.cta{display:inline-block;margin:1.2rem 0 0;border:1px solid var(--accent);
background:var(--soft);border-radius:10px;padding:.75rem 1.2rem;
font-weight:650;text-decoration:none;color:inherit}
</style>
"""

_BADGE = {
    OBSERVED: ("obs", "observed"),
    STRONGLY_INFERRED: ("", "strongly inferred"),
    BOUNDED_INFERENCE: ("", "bounded"),
    UNMEASURED: ("", "not established"),
}


def _badge(standing: str) -> str:
    cls, label = _BADGE.get(standing, ("", "bounded"))
    title = STANDING_PROSE.get(standing, "")
    return (f'<span class="stand {cls}" title="{_e(title)}">{_e(label)}</span>')


# ===========================================================================
# STEP 1 — INTRODUCTION
# ===========================================================================
def render_intro(read, *, run_id: str, company: str,
                 learning: str = "", identity: str = "") -> str:
    """§21–§25. Compelling immediately, synthesized, no truncated copy.

    `identity` is the canonical subject line — legal name, ticker, country,
    domain. It is passed in rather than derived because the renderer has no
    session and no registry, and it is REQUIRED reading rather than a nicety:
    the persona pass found a chief executive who could not confirm, from the
    first screen, which company this analysis was about. The page said
    "Cloudflare" six times and never "Cloudflare, Inc. · NET".
    """
    out = [STEP_CSS, '<main class="step">',
           '<p class="kicker">Introduction</p>',
           f'<h1>{_e(company)}</h1>']
    if identity:
        out.append(f'<p class="subject">{_e(identity)}</p>')

    # ONE opening line. `economic_role` and `strategic_position` say what the
    # story chapters below say, and printing both put the same two sentences
    # on the page twice before the reader reached anything new.
    if read.identity:
        out.append(f'<p class="lede">{_e(read.identity)}</p>')
    if read.strategic_position:
        out.append(f'<p>{_e(read.strategic_position)}</p>')

    # THE STRATEGIC READ, where "THE ANSWER — no strategic reading cleared the
    # evidence bar" used to be (§24).
    out.append('<div class="readbox"><h2>The strategic read</h2>')
    if read.standing == READ_UNIDENTIFIED:
        out.append(f'<p class="q">{_e(read.central_question)}</p>')
        out.append(f'<p>{_e(read.standing_reason)}</p>')
        for statement in read.level1_facts:
            out.append(f'<p>{_e(statement.text)}'
                       f'{_badge(statement.standing)}</p>')
    else:
        out.append(f'<p class="q">The question worth arguing about is '
                   f'{_e(_lower(read.central_question))}</p>')
        out.append(f'<p>{_e(read.level5_decision.text)}'
                   f'{_badge(read.level5_decision.standing)}</p>')
        out.append(f'<p><strong>Our read:</strong> '
                   f'{_e(_read_word(read.standing))} — '
                   f'{_e(read.standing_reason)}</p>')
    out.append('</div>')

    # THE RECOMMENDATION, ON THE FIRST SCREEN (§43, §70).
    #
    # The bridge always carried an action, a guardrail and a kill switch, and
    # the introduction never named any of them: the move appeared as an
    # unlabelled imperative in item 02 of "What matters now", and the
    # stopping rule appeared three pages later. A chief executive reading
    # only this screen could not have said what was being recommended or
    # when to stop — which is what the persona pass measured and what a
    # reader would have felt without being able to name.
    bridge = getattr(read, "level6_action", None)
    if bridge is not None and getattr(bridge, "action_now", ""):
        out.append('<div class="readbox rec"><h2>What we recommend</h2>')
        out.append(f'<p class="q">{_e(_capitalise(bridge.action_now))}</p>')
        # NOUN-PHRASE LABELS, NOT SENTENCE STEMS. "Stop if" + a kill switch
        # that already begins "if the direction is not visible" rendered
        # "Stop if if the direction is not visible" — a label that completes
        # into its value only works when every value has the same grammar,
        # and these come from four different producers.
        for label, value in (("Guardrail", bridge.guardrail),
                             ("Stopping rule", bridge.kill_switch),
                             ("How to test it",
                              bridge.minimum_viable_experiment),
                             ("What would change this view", bridge.falsifier)):
            if value:
                out.append(f'<p><span class="n">{_e(label)}</span> '
                           f'{_e(_capitalise(value))}</p>')
        out.append('</div>')

    if read.what_matters_now:
        out.append('<h2>What matters now</h2><ul class="matters">')
        for index, statement in enumerate(read.what_matters_now, start=1):
            out.append(f'<li><span class="n">{index:02d}</span> '
                       f'{_e(statement.text)}{_badge(statement.standing)}</li>')
        out.append('</ul>')

    # THE CHOICE THE RUN ACTUALLY WEIGHED (§56). Shown only when the run
    # reached one; nothing here composes a second pair of options.
    if read.options:
        out.append('<h2>The choice this bears on</h2><ul class="matters">')
        for index, option in enumerate(read.options, start=1):
            bits = [f'<strong>{_e(option.get("label"))}</strong>']
            for label, key in (("What it means", "what_it_means"),
                               ("Upside", "upside"), ("Cost", "cost"),
                               ("Assumes", "assumes")):
                if option.get(key):
                    bits.append(f'<br><span class="n">{_e(label)}</span> '
                                f'{_e(option[key])}')
            out.append(f'<li><span class="n">Option {index}</span> '
                       + "".join(bits) + '</li>')
        out.append('</ul>')

    if read.story:
        out.append('<div class="chapters">')
        for chapter in read.story:
            out.append(f'<section><h3>{_e(chapter.title)}</h3>'
                       f'<p>{_e(chapter.body)}</p></section>')
        out.append('</div>')

    # The company's own words: quoted, attributed, COMPLETE, and after the
    # analysis rather than in place of it.
    if read.own_words:
        out.append(f'<blockquote class="quote">{_e(read.own_words)}'
                   f'<cite>{_e(company)}, in its own words'
                   + (f' — {_e(read.own_words_source)}'
                      if read.own_words_source else '')
                   + '</cite></blockquote>')

    if learning:
        out.append(learning)
    out.append(flow.drawer(run_id, ("answer", "xray", "evidence"),
                           title="Where this comes from"))
    out.append(flow.nav(run_id, "intro"))
    out.append('</main>')
    return "".join(out)


def _read_word(standing: str) -> str:
    return {"SUPPORTED": "Supported",
            "BOUNDED": "Bounded",
            READ_UNIDENTIFIED: "Not established"}.get(standing, "Bounded")


def _capitalise(text: str) -> str:
    flat = str(text or "").strip()
    return flat[:1].upper() + flat[1:] if flat else ""


def _lower(text: str) -> str:
    flat = str(text or "").strip()
    if not flat:
        return ""
    head = flat.split(" ", 1)[0]
    if head.isupper() or (len(head) > 1 and head[1:].lower() != head[1:]):
        return flat
    return flat[0].lower() + flat[1:]


# ===========================================================================
# STEP 5 — HISTORY REWIND
# ===========================================================================
def render_history(sim, timeline=None, *, run_id: str, company: str) -> str:
    """§17-§36. A strategy simulator, chart first.

    The old version of this surface changed BLOCKS OF PROSE when you moved the
    slider. It was correct about the vintage wall and it did not answer the
    question an executive asks about the past, which is comparative: where did
    this go, where was it expected to go, and where could it have gone. Those
    are three lines on one axis, so that is what opens the page now.

    `timeline` (the dated filing record) is optional and secondary: it is the
    provenance of the dates, shown under the chart rather than instead of it.
    """
    out = [STEP_CSS, HC.CHART_CSS, '<main class="step">',
           '<p class="kicker">History rewind</p>',
           f'<h1>{_e(company)} — the strategy simulator</h1>']
    out.append('<p class="lede">Pick a year. The chart holds the path the '
               'company actually took, what the record published by then '
               'implied about where it was going, and where a named '
               'alternative available on the same information could have led. '
               'Nothing modelled at a date can see a filing made after it.</p>')

    if sim is None or not sim.available:
        out.append(_history_fallback(sim, timeline, company))
        out.append(flow.drawer(run_id, ("sources",),
                               title="What was retrieved"))
        out.append(flow.nav(run_id, "history"))
        out.append('</main>')
        return "".join(out)

    out.append('<div class="hrewind">')
    # Radios first: `:checked ~` reaches later siblings only.
    #
    # THE DEFAULT IS NOT THE LATEST DATE. The most recent vintage has almost
    # no hindsight after it, so it opens on a chart where the expectation and
    # the outcome are the same point and the page teaches nothing. The
    # default is the vintage about two-thirds along: late enough to have a
    # real trailing record, early enough that what followed is visible.
    default = max(0, min(len(sim.vintages) - 1,
                         int(len(sim.vintages) * 0.62)))
    for index in range(len(sim.vintages)):
        checked = ' checked' if index == default else ''
        out.append(f'<input type="radio" name="hv" id="hv{index}"{checked} '
                   f'aria-label="Rewind to {sim.vintages[index].year}">')
    out.append(f'<style>{HC.rail_css(len(sim.vintages))}</style>')
    out.append('<div class="hrail" role="group" '
               'aria-label="Choose the year to rewind to">')
    for index, vintage in enumerate(sim.vintages):
        out.append(f'<label for="hv{index}"><b>{vintage.year}</b>'
                   f'{_e(_knowable_note(vintage))}</label>')
    out.append('</div>')
    for index, vintage in enumerate(sim.vintages):
        out.append(f'<div class="hpanel hpanel{index}">')
        out.append('<div class="hsim">')
        out.append(HC.chart_svg(sim, vintage))
        out.append(HC.legend(sim, vintage))
        out.append(f'<p class="hsim-axis-note">{_e(sim.index.definition)}</p>')
        out.append('</div>')
        out.append(f'<h2>{_e(vintage.label)}</h2>')
        out.append(HC.cards(vintage))
        out.append(HC.drivers(vintage))
        out.append(HC.data_table(sim, vintage))
        out.append('</div>')
    out.append('</div>')
    out.append(f'<p class="hsim-axis-note">{_e(sim.coverage)}</p>')
    if timeline is not None and timeline.available:
        out.append(_filing_provenance(timeline))
    out.append(flow.drawer(run_id, ("evidence", "sources"),
                           title="The filings behind this timeline"))
    out.append(flow.nav(run_id, "history"))
    out.append('</main>')
    return "".join(out)


def _knowable_note(vintage) -> str:
    """The rail's second line: where the index stood at that date.

    "Tested against what followed" was the first version and it was identical
    on every tab — a label that cannot vary is not a label, it is decoration
    on a control the reader is trying to choose with. The index at the date
    differs on every tab and is the number the tab is about.
    """
    point = next((p for p in vintage.actual.points if p.year == vintage.year),
                 None)
    return f"index {point.value:.0f}" if point is not None else "as filed"


def _history_fallback(sim, timeline, company: str) -> str:
    """No chart — and still not an empty page (§16 rung D, §38).

    Reached by a company with no multi-year filed series: a private company,
    a foreign issuer filing in another taxonomy, or one too young to have
    three years. The page states what that means for a decision and what
    single input would produce the chart, because "no history exists" is a
    sentence about our retrieval that reads to a customer as a sentence about
    their company.
    """
    fallback = getattr(sim, "fallback", None) if sim is not None else None
    out = ['<div class="readbox"><h2>What can be said about the path so far'
           '</h2>']
    if fallback is not None:
        out.append(f'<p class="q">{_e(fallback.statement)}</p>')
        if fallback.next_measurement:
            out.append(f'<p><strong>What would draw this chart:</strong> '
                       f'{_e(fallback.next_measurement)}.</p>')
        if fallback.decision_relevance:
            out.append(f'<p><strong>Why it matters:</strong> this bears on '
                       f'{_e(fallback.decision_relevance)}.</p>')
    else:
        out.append(f'<p class="q">No multi-year financial series has been '
                   f'retrieved for {_e(company)}, so the three-line '
                   f'comparison cannot be drawn from measured points.</p>')
        out.append('<p><strong>What would draw this chart:</strong> three or '
                   'more years of reported revenue and operating result.</p>')
    out.append('</div>')
    bounded = tuple(getattr(sim, "bounded_cards", ()) or ())
    if bounded:
        out.append('<p>The chart needs a filed series and this company has '
                   'none. The strategic question it would have framed does '
                   'not need one, so it is argued here directly — as an '
                   'argument, with no path drawn under it.</p>')
        out.append('<div class="hcards">')
        for card in bounded:
            style = {"OBSERVED": "obs", "MODELED": "mod",
                     "COUNTERFACTUAL": "cf"}.get(card.basis, "obs")
            out.append(f'<article class="{style}"><h3>{_e(card.title)}'
                       f'<span class="basis">{_e(card.label)}</span></h3>'
                       f'<p>{_e(card.body)}</p></article>')
        out.append('</div>')
    if timeline is not None and timeline.available:
        out.append('<p>The dated record that <em>was</em> retrieved is below: '
                   'it establishes when this company said what, which is the '
                   'sequence a strategy has to be judged in even without the '
                   'figures.</p>')
        out.append(_filing_provenance(timeline))
        latest = timeline.vintages[-1]
        out.append('<div class="hcards">')
        for panel in latest.panels:
            out.append(f'<article class="obs"><h3>{_e(panel.title)}</h3>'
                       f'<p>{_e(panel.body)}</p></article>')
        out.append('</div>')
    return "".join(out)


def _filing_provenance(timeline) -> str:
    """The dated filings the vintages are anchored on."""
    rows = "".join(
        f'<tr><th scope="row">{_e(f.get("date"))}</th>'
        f'<td>{_e(f.get("form"))}</td></tr>'
        for f in list(timeline.filings)[-14:])
    if not rows:
        return ""
    return (f'<details class="hsim-alt"><summary>The dated filings behind '
            f'these vintages ({len(timeline.filings)} retrieved)</summary>'
            f'<div class="scroll"><table><thead><tr>'
            f'<th scope="col">Filed</th><th scope="col">Form</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>'
            f'<p class="hsim-axis-note">{_e(timeline.coverage_note)}</p>'
            f'</details>')


def _counterfactual(cf) -> str:
    rows = (("What was actually chosen", cf.actual_choice),
            ("What was known at the time", cf.information_available),
            ("The alternative on the table", cf.alternative),
            ("What that would have been expected to do", cf.expected_outcome),
            ("What can be observed about it", cf.observed_outcome),
            ("The mechanism underneath", cf.mechanism),
            ("The lesson", cf.lesson))
    out = ['<dl class="cfact">']
    for label, value in rows:
        if not value:
            continue
        out.append(f'<dt>{_e(label)}</dt><dd>{_e(value)}</dd>')
    out.append('</dl>')
    return "".join(out)


# ===========================================================================
# STEP 6 — CONNECT YOUR COMPANY / PERSONAL AI
# ===========================================================================
#: §50. Only a connector that exists may read ACTIVE.
CONNECTORS = (
    ("Public filings and disclosures", "ACTIVE",
     "Regulatory filings, the company's own pages, and independent sources "
     "— everything the analysis you just read was built from."),
    ("Published market intelligence", "ACTIVE",
     "The economy, the competitive record and the learning ledger this "
     "system maintains between runs."),
    ("Your documents", "AVAILABLE_NEXT",
     "Board packs, strategy decks and plans. The system reads what management "
     "actually decided rather than inferring it from the outside."),
    ("Financial plan and internal metrics", "AVAILABLE_NEXT",
     "The numbers the public record does not contain — the ones that turn "
     "every bounded magnitude above into a measured one."),
    ("CRM and pipeline", "COMING",
     "Which deals moved, which stalled, and why. This is what separates a "
     "pricing hypothesis from a pricing answer."),
    ("Customer feedback", "COMING",
     "What buyers say when they are not filling in a renewal form."),
    ("Decision log", "COMING",
     "What leadership considered, chose, and rejected — with the reasons, so "
     "the next decision starts from the last one."),
)

_TAG_WORD = {"ACTIVE": "Connected now",
             "AVAILABLE_NEXT": "Available next",
             "COMING": "On the roadmap"}


def render_connect(read, *, run_id: str, company: str,
                   feedback: str = "") -> str:
    """§49–§52. What changes when the system knows the company's own numbers.

    `feedback` is the step-6 workflow, injected rather than built here: it
    needs a CSRF token and a durability check, and neither belongs in a
    renderer that has no session and no storage.
    """
    unmeasured = [m for m in (read.metrics or ()) if m.state == UNMEASURED]
    out = [STEP_CSS, '<main class="step">',
           '<p class="kicker">Connect your company</p>',
           f'<h1>What this becomes with your own context</h1>']
    out.append('<p class="lede">Everything you have just read was built from '
               'public evidence alone. That is deliberate — it is what makes '
               'it checkable. It is also what puts a boundary on it, and the '
               'boundary is visible in the analysis itself.</p>')

    out.append('<div class="readbox"><h2>Public intelligence — what it '
               'could establish</h2>')
    out.append(f'<p>{_e(read.identity)}</p>')
    out.append(f'<p>{_e(_capitalise(read.standing_reason))}</p>')
    if read.evidence_note:
        out.append(f'<p>{_e(read.evidence_note)}</p>')
    out.append('</div>')

    if unmeasured:
        out.append('<h2>Internal intelligence — what is still bounded</h2>')
        out.append('<p>These are the measures a business of this kind is '
                   'judged on that the public record did not supply. Each one '
                   'is a magnitude the analysis above had to leave in '
                   'direction only.</p>')
        out.append('<ul class="matters">')
        for metric in unmeasured[:6]:
            out.append(f'<li><strong>{_e(metric.metric)}</strong> — '
                       f'{_e(metric.why_it_matters)}</li>')
        out.append('</ul>')

    out.append('<h2>What can be connected</h2><div class="conn">')
    for title, state, description in CONNECTORS:
        cls = ' on' if state == "ACTIVE" else ''
        out.append(f'<div><span class="tag{cls}">'
                   f'{_e(_TAG_WORD.get(state, state))}</span>'
                   f'<h3>{_e(title)}</h3><p>{_e(description)}</p></div>')
    out.append('</div>')

    # §51. The stages, kept apart.
    out.append('<h2>What a private company intelligence keeps</h2>')
    out.append('<p>A recommendation is not a decision, and a decision is not '
               'an act. The system keeps them separate and remembers each one '
               'as its own kind of thing.</p>')
    out.append('<ul class="chain">')
    for label, text in (
            ("Recommendation",
             "What the analysis put forward, and the evidence standing behind "
             "it at the time."),
            ("Human decision",
             "What leadership actually chose — including choosing not to act, "
             "which is a decision and is usually recorded nowhere."),
            ("Action",
             "What was then done, by whom, and when. Nothing is ever done by "
             "this system on its own authority."),
            ("Outcome",
             "What followed, measured against what the recommendation said "
             "would follow."),
            ("Lesson",
             "Whether the reasoning held, separately from whether the result "
             "was good. Those come apart more often than anyone expects.")):
        out.append(f'<li><span class="st">{_e(label)}</span><br>'
                   f'{_e(text)}</li>')
    out.append('</ul>')

    # §52. FEEDBACK SITS BETWEEN THE DEMO AND THE ASK, NOT AFTER IT.
    #
    # Below the CTA it is a form nobody reaches, because a reader who has
    # decided either way has already left. Between them it is the natural
    # next thing: you have just been shown what was bounded and what would
    # unbound it, and the question "was this worth anything?" follows from
    # that rather than interrupting it.
    if feedback:
        out.append(feedback)

    out.append('<p><a class="cta" href="/signup">Start private company '
               'intelligence</a></p>')
    out.append('<p style="font-size:.85rem;color:var(--muted)">Nothing is '
               'sent, published, scheduled or shared without an explicit '
               'human approval — in this demo, and in the product.</p>')
    out.append(flow.nav(run_id, "connect"))
    out.append('</main>')
    return "".join(out)

# ===========================================================================
# STEP 4 — THE FULL STORY
# ===========================================================================
def render_story(read, timeline, *, run_id: str, company: str,
                 extra: str = "") -> str:
    """§39–§40. The same conclusion as a narrative somebody can retell.

    WHY THIS REPLACED THE OLD STORY PAGE. Live, after the pattern library was
    gated by business model, step 4 came to five sentences and two of them
    were broken:

        "The answer in one minute: Cloudflare's mission is to help build a
         better Internet."
        "The business story: company"

    A section heading followed by the single word "company" is what a
    template produces when the field behind it is empty, and the page had no
    way to notice. This composes from the canonical read instead, so the
    narrative cannot be emptier than the analysis it retells.

    It is a NARRATIVE, not a second report: continuous prose, no enums, no
    bullet dumps, and no methodology. Where the run produced substantive
    sections of its own they are appended below as supporting material.
    """
    out = [STEP_CSS, '<main class="step">',
           '<p class="kicker">The full story</p>',
           f'<h1>{_e(company)} — the whole picture, in order</h1>']

    if read.standing == READ_UNIDENTIFIED:
        # No economics, because none is established. What IS established is
        # what this run read, and that differs company by company -- which is
        # the whole difference between a bounded page and a template.
        out.append(f'<p class="lede">{_e(read.standing_reason)}</p>')
        if read.level1_facts:
            out.append('<h2>What this run could establish</h2>'
                       '<ul class="matters">')
            for statement in read.level1_facts:
                out.append(f'<li>{_e(statement.text)}'
                           f'{_badge(statement.standing)}</li>')
            out.append('</ul>')
        if read.run_contribution:
            out.append(f'<p>{_e(read.run_contribution)}</p>')
        if read.own_words:
            out.append(f'<blockquote class="quote">{_e(read.own_words)}'
                       f'<cite>{_e(company)}, in its own words'
                       + (f' — {_e(read.own_words_source)}'
                          if read.own_words_source else '')
                       + '</cite></blockquote>')
        action = read.level6_action
        if action is not None:
            out.append('<h2>What to do about that</h2>')
            out.append(f'<p>{_e(action.action_now)} '
                       f'{_e(action.minimum_viable_experiment)}</p>')
        out.append(flow.drawer(run_id, ("sources", "evidence"),
                               title="What was retrieved"))
        out.append(flow.nav(run_id, "story"))
        out.append('</main>')
        return "".join(out)

    out.append(f'<p class="lede">{_e(read.identity)}</p>')

    out.append('<div class="chapters">')
    # `<h2>`, not `<h3>`. On this page the chapters sit directly under the
    # `<h1>`, so an `<h3>` is a skipped level -- and the heading outline is
    # how a screen-reader user navigates, so a skipped level reads as a
    # section that is not there. (The introduction nests its chapters under
    # an `<h2>`, which is why the same renderer takes the level as an
    # argument rather than hard-coding one.)
    for chapter in read.story:
        out.append(f'<section><h2>{_e(chapter.title)}</h2>'
                   f'<p>{_e(chapter.body)}</p></section>')

    # 4: how it got here. Real dated material or nothing -- never invented.
    arc = _arc(timeline, company)
    if arc:
        out.append(f'<section><h2>How it got to here</h2><p>{_e(arc)}</p>'
                   f'</section>')

    # 5: what management appears to be doing, and where that is exposed.
    action = read.level6_action
    if action is not None:
        out.append(
            f'<section><h2>What the argument is actually about</h2>'
            f'<p>{_e(action.what_is_known)} '
            f'{_e(action.what_remains_unknown)} '
            f'{_e(action.why_it_matters)}</p></section>')

    # 6: the competitive turn.
    if read.level4_competition:
        rival = read.level4_competition[0]
        out.append(
            f'<section><h2>What the other side does</h2>'
            f'<p>{_e(rival.why_a_rival)} {_e(rival.likely_response)} '
            f'The counter available here is {_e(_lower(rival.counter_move))} '
            f'and the thing to watch for is {_e(_lower(rival.signal_to_watch))}'
            f'</p></section>')

    # 7: what should happen next.
    if action is not None:
        out.append(
            f'<section><h2>What should happen next</h2>'
            f'<p>{_e(action.action_now)} {_e(action.minimum_viable_experiment)}'
            f' {_e(action.kill_switch)}</p></section>')
        out.append(
            f'<section><h2>What would make this wrong</h2>'
            f'<p>{_e(action.falsifier)} '
            f'{_e(read.evidence_note)}</p></section>')
    out.append('</div>')

    if extra:
        out.append(extra)
    out.append(flow.drawer(run_id, ("brief", "evidence"),
                           title="If you want it shorter, or want the sources"))
    out.append(flow.nav(run_id, "story"))
    out.append('</main>')
    return "".join(out)


def _arc(timeline, company: str) -> str:
    """The company's own dated arc, or nothing.

    Composed ONLY from filing dates and forms, which are facts. No founding
    date, no product launches, no revenue path -- this system did not read
    those and will not narrate them.
    """
    vintages = tuple(getattr(timeline, "vintages", ()) or ())
    filings = tuple(getattr(timeline, "filings", ()) or ())
    if len(vintages) < 2 or not filings:
        return ""
    annual = [f for f in filings if str(f.get("form", "")).startswith(
        ("10-K", "20-F", "40-F"))]
    first, last = filings[0], filings[-1]
    out = (f"The public record this analysis holds for {company} runs from "
           f"{first.get('date')} to {last.get('date')}, across "
           f"{len(filings)} company filings")
    if annual:
        out += (f", including {len(annual)} full annual accounts — the "
                f"documents in which a company restates what it is. "
                f"Step 5 replays those dates one at a time, showing only "
                f"what the record held on each")
    return out + "."


def render_learning(report, reading) -> str:
    """§54. What was new, what was already known, and what to learn next.

    ACTIVITY IS NOT LEARNING, and the distinction is the headline: a cycle
    that re-read eighty pages and changed nothing has been busy. So the first
    number shown is what CHANGED THE MODEL, never what arrived.

    FIELD NAMES ARE READ OFF THE PRODUCER, NOT GUESSED. The first version of
    this asked for `beliefs_changed` and `novel_evidence`, which the learning
    report has never emitted -- so it rendered nothing at all, on every page,
    while a full report sat one call away. A consumer that names its
    producer's fields wrongly reports a uniform absence and looks exactly
    like a producer that is not running.

    Renders nothing when no report is available. An empty learning panel
    teaches a reader that the system does not learn, which is the opposite of
    true and worse than silence.
    """
    if report is None or not getattr(report, "available", False):
        return ""
    reading = reading or {}
    if str(reading.get("state") or "") != "LEARNING_AVAILABLE":
        return ""
    payload = getattr(report, "payload", None) or {}
    summary = payload.get("executive_summary") or {}
    bottleneck = payload.get("bottleneck") or {}
    nxt = payload.get("next_research_priority") or {}

    rows = []
    for label, key, gloss in (
            ("Changed the model", "changed_the_model",
             "beliefs this system revised because of what it read"),
            ("Genuinely new", "novel",
             "arrivals that were not already in the record"),
            ("Already known", "re_observed",
             "arrivals that confirmed what was already held"),
            ("Tested and held", "tested_and_unchanged",
             "beliefs checked against new evidence and left standing")):
        value = reading.get(key)
        if value in (None, ""):
            continue
        rows.append(f'<li><span class="st">{_e(label)} — {_e(value)}</span>'
                    f'<br>{_e(gloss)}</li>')
    if not rows:
        return ""

    out = ['<h2>What the system learned since last time</h2>']
    verdict = str(reading.get("verdict") or "").lower()
    why = str(reading.get("why") or "")
    if verdict:
        out.append(f'<p>Learning is <strong>{_e(verdict)}</strong>'
                   + (f' — {_e(why)}' if why else '') + '. Reading more is '
                   'not the same as knowing more, so this counts what '
                   'changed rather than what arrived.</p>')
    out.append(f'<ul class="chain">{"".join(rows)}</ul>')

    for item in (summary.get("top_learnings") or ())[:2]:
        out.append(f'<p>{_e(item)}</p>')
    reason = str(bottleneck.get("reason") or "")
    if reason:
        out.append(f'<p><strong>What is holding it back:</strong> '
                   f'{_e(reason)}</p>')
    action = str(nxt.get("suggested_action") or "")
    if action:
        out.append(f'<p><strong>What to learn next:</strong> {_e(action)}.</p>')
    return "".join(out)
