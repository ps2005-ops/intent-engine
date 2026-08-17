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
.readbox{border:1px solid var(--line);border-left:4px solid var(--accent);
border-radius:12px;background:var(--card);padding:1.1rem 1.2rem;margin:1.4rem 0}
.readbox h2{margin:0 0 .5rem;font-size:.74rem;text-transform:uppercase;
letter-spacing:.09em;color:var(--muted)}
.readbox p{margin:.45rem 0}
.readbox .q{font-size:1.06rem;font-weight:600}
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
.vint h3{margin:0 0 .2rem}
.vwall{font-size:.85rem;color:var(--muted);margin:.1rem 0 1rem}
.panels{display:grid;gap:.8rem;grid-template-columns:1fr 1fr;margin:0}
@media(max-width:720px){.panels{grid-template-columns:1fr}}
.panels div{border:1px solid var(--line);border-radius:10px;padding:.75rem .9rem}
.panels div.after{border-color:var(--accent);border-style:dashed;
grid-column:1/-1}
.panels h4{margin:0 0 .3rem;font-size:.72rem;text-transform:uppercase;
letter-spacing:.07em;color:var(--muted)}
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
.conn h4{margin:0 0 .2rem;font-size:.95rem}
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
                 learning: str = "") -> str:
    """§21–§25. Compelling immediately, synthesized, no truncated copy."""
    out = [STEP_CSS, '<main class="step">',
           '<p class="kicker">Introduction</p>',
           f'<h1>{_e(company)}</h1>']

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
def render_history(timeline, *, run_id: str, company: str) -> str:
    """§41–§48. A slider across dates, with the vintage wall visible."""
    out = [STEP_CSS, '<main class="step">',
           '<p class="kicker">History rewind</p>',
           f'<h1>{_e(company)} — rewind the record</h1>']
    out.append('<p class="lede">Move to a date and see only what the record '
               'showed then. What happened afterward is kept in one panel of '
               'its own, so nothing on this page reasons from an outcome it '
               'could not have known.</p>')

    if not timeline.available:
        out.append(f'<div class="readbox"><h2>No dated record</h2>'
                   f'<p>{_e(timeline.coverage_note)}</p></div>')
        out.append(flow.drawer(run_id, ("sources",),
                               title="What was retrieved"))
        out.append(flow.nav(run_id, "history"))
        out.append('</main>')
        return "".join(out)

    out.append(f'<p>{_e(timeline.coverage_note)}</p>')
    out.append('<div class="rewind">')
    # The radios come FIRST and the panels after, because `:checked ~` only
    # reaches later siblings.
    default = len(timeline.vintages) - 1
    for index, vintage in enumerate(timeline.vintages):
        checked = ' checked' if index == default else ''
        out.append(f'<input type="radio" name="rw" id="rw{index}"{checked}>')
    out.append(f'<style>{_rail_css(len(timeline.vintages))}</style>')
    out.append('<div class="rail" role="group" aria-label="Choose a date">')
    for index, vintage in enumerate(timeline.vintages):
        # THE MONTH IS NOT ALWAYS UNIQUE. Two 8-Ks three weeks apart both
        # read "2026-06", so the rail offered two identical-looking dates and
        # a reader could not tell which one they were on.
        label = (vintage.date if _ambiguous(timeline, vintage)
                 else vintage.date[:7])
        out.append(f'<label for="rw{index}"><b>{_e(label)}</b>'
                   f'{_e(_short_state(vintage.state))}</label>')
    out.append('</div>')
    for index, vintage in enumerate(timeline.vintages):
        out.append(f'<div class="vint" id="v{index}">')
        out.append(f'<h3>{_e(vintage.label)}</h3>')
        out.append(f'<p class="vwall">{_e(vintage.state_prose)}</p>')
        out.append('<div class="panels">')
        for panel in vintage.panels:
            cls = ' class="after"' if panel.after_the_wall else ''
            out.append(f'<div{cls}><h4>{_e(panel.title)}</h4>'
                       f'<p>{_e(panel.body)}</p></div>')
        out.append('</div>')
        if vintage.counterfactual is not None:
            out.append(_counterfactual(vintage.counterfactual))
        out.append('</div>')
    out.append('</div>')
    out.append(flow.drawer(run_id, ("evidence", "sources"),
                           title="The filings behind this timeline"))
    out.append(flow.nav(run_id, "history"))
    out.append('</main>')
    return "".join(out)


def _ambiguous(timeline, vintage) -> bool:
    months = [v.date[:7] for v in timeline.vintages]
    return months.count(vintage.date[:7]) > 1


def _short_state(state: str) -> str:
    return {HR.HISTORICAL_REPLAY: "testable",
            HR.DESCRIPTIVE_HISTORY: "not yet tested",
            HR.REPLAY_NOT_YET_VALID: "no record"}.get(state, "")


def _rail_css(count: int) -> str:
    """One rule per date: check radio N, show panel N and mark tab N.

    Generated rather than written because the number of dates is decided by
    the record, not by the design.
    """
    rules = []
    for index in range(count):
        rules.append(
            f'.rewind input#rw{index}:checked ~ .rail label[for="rw{index}"]'
            '{border-color:var(--accent);color:var(--fg);'
            'background:var(--soft)}')
        rules.append(
            f'.rewind input#rw{index}:checked ~ #v{index}{{display:block}}')
        rules.append(
            f'.rewind input#rw{index}:focus ~ .rail label[for="rw{index}"]'
            '{outline:2px solid var(--accent);outline-offset:2px}')
    return "".join(rules)


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


def render_connect(read, *, run_id: str, company: str) -> str:
    """§49–§52. What changes when the system knows the company's own numbers."""
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
                   f'<h4>{_e(title)}</h4><p>{_e(description)}</p></div>')
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
    # 1-3: what the business is and what it runs on, from the read's own
    # chapters -- the same four blocks the introduction showed, in the same
    # order, because a story a reader can retell is one they have heard once
    # already in outline.
    for chapter in read.story:
        out.append(f'<section><h3>{_e(chapter.title)}</h3>'
                   f'<p>{_e(chapter.body)}</p></section>')

    # 4: how it got here. Real dated material or nothing -- never invented.
    arc = _arc(timeline, company)
    if arc:
        out.append(f'<section><h3>How it got to here</h3><p>{_e(arc)}</p>'
                   f'</section>')

    # 5: what management appears to be doing, and where that is exposed.
    action = read.level6_action
    if action is not None:
        out.append(
            f'<section><h3>What the argument is actually about</h3>'
            f'<p>{_e(action.what_is_known)} '
            f'{_e(action.what_remains_unknown)} '
            f'{_e(action.why_it_matters)}</p></section>')

    # 6: the competitive turn.
    if read.level4_competition:
        rival = read.level4_competition[0]
        out.append(
            f'<section><h3>What the other side does</h3>'
            f'<p>{_e(rival.why_a_rival)} {_e(rival.likely_response)} '
            f'The counter available here is {_e(_lower(rival.counter_move))} '
            f'and the thing to watch for is {_e(_lower(rival.signal_to_watch))}'
            f'</p></section>')

    # 7: what should happen next.
    if action is not None:
        out.append(
            f'<section><h3>What should happen next</h3>'
            f'<p>{_e(action.action_now)} {_e(action.minimum_viable_experiment)}'
            f' {_e(action.kill_switch)}</p></section>')
        out.append(
            f'<section><h3>What would make this wrong</h3>'
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
