"""The Full Analysis and the Presentation: two depths of one decision.

WHY THESE ARE NOT TWO REPORTS
-----------------------------
The X-Ray, this full analysis, the presentation, the CEO answers and the
personal assistant are five VIEWS of one `FounderDecision`. None of them
reasons. If any of them derived a conclusion of its own, two surfaces could
answer "what do you recommend" differently for the same company on the same
day, and a customer who noticed would be right to stop trusting all five.

So the rule here, from §34:

    the presentation may SIMPLIFY the analysis
    it may never STRENGTHEN it

Concretely: both read `standing`, and the verb each is allowed to use comes
from the same table. A deck cannot say "the evidence shows" about a reading
the full analysis calls bounded, because neither of them chooses the verb.

THE INFORMATION-QUALITY GATE (§15)
----------------------------------
A section earns its place by changing the decision or by being the evidence
under something that does. Sections that would do neither are not rendered
as empty headings -- an empty heading is worse than an absent one, because
it reads as a subsystem that failed rather than as a thing that does not
apply here. `_maybe` is that gate: a section with nothing to say does not
appear, and its absence is accounted for in the closing note.
"""
from __future__ import annotations

from intent_engine.founder_brief import plain as P
from intent_engine.founder_brief import xray as X

#: Escapes AND fixes source punctuation. Bound once so no string can
#: reach a page through this module without passing both rules.
_e = P.escape

FULL_CONTRACT = "full_analysis.v1"
DECK_CONTRACT = "decision_presentation.v1"

_CSS = """
<style>
.fa{--ink:#111827;--muted:#4b5563;--line:#d1d5db;--bg:#ffffff;
--panel:#f8fafc;--accent:#1d4ed8;--warn:#9a3412;
font:17px/1.65 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
color:var(--ink);background:var(--bg);max-width:44rem;margin:0 auto;
padding:10px 18px 56px}
.fa .eyebrow{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;
color:var(--muted);font-weight:700;margin:0 0 .2rem}
.fa h1{font-size:1.5rem;line-height:1.25;margin:.1rem 0 .4rem;font-weight:650}
.fa h2{font-size:1.02rem;margin:1.9rem 0 .4rem;font-weight:650;
border-top:1px solid var(--line);padding-top:1rem}
.fa h3{font-size:.79rem;text-transform:uppercase;letter-spacing:.07em;
color:var(--muted);margin:1.1rem 0 .3rem;font-weight:700}
.fa p{margin:0 0 .6rem}
.fa ul{margin:.3rem 0 .7rem;padding-left:1.15rem}
.fa li{margin:0 0 .45rem}
.fa .lead{background:var(--panel);border:1px solid var(--line);
border-left:3px solid var(--accent);border-radius:8px;padding:1rem 1.1rem;
margin:0 0 1rem}
.fa .lead .q{font-size:1.1rem;font-weight:640;margin:0 0 .5rem}
.fa .none{color:var(--muted);font-size:.92rem}
.fa .stamp{color:var(--muted);font-size:.85rem;margin:0 0 1rem}
.fa .rowlist{list-style:none;padding:0}
.fa .rowlist li{border:1px solid var(--line);border-radius:7px;
padding:.6rem .75rem;margin:0 0 .5rem;background:var(--panel)}
.fa .rowlist .h{font-weight:640;margin:0 0 .25rem}
.fa .rowlist .m{color:var(--muted);font-size:.88rem;margin:0}
.fa .chain{font-size:.9rem;margin:.3rem 0 0}.fa .chain span{color:var(--muted)}
.fa a{color:var(--accent)}
.fa .acts{display:flex;gap:10px;flex-wrap:wrap;margin:1.6rem 0 .4rem}
.fa .acts a{display:inline-block;padding:9px 16px;border-radius:9px;
border:1px solid var(--line);text-decoration:none;color:var(--ink);
font-weight:600;font-size:.94rem}
.fa :focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.fa .slide{border:1px solid var(--line);border-radius:10px;
padding:1.1rem 1.2rem;margin:0 0 .9rem;background:var(--bg)}
.fa .slide .n{font-size:.74rem;text-transform:uppercase;letter-spacing:.08em;
color:var(--muted);font-weight:700;margin:0 0 .3rem}
.fa .slide h2{border:0;padding:0;margin:0 0 .5rem;font-size:1.14rem}
.fa .slide p{margin:0 0 .45rem}
@media (max-width:640px){.fa{font-size:16px;padding:8px 14px 40px}
.fa h1{font-size:1.28rem}}
@media (prefers-color-scheme:dark){
.fa{--ink:#f3f4f6;--muted:#c3cad6;--line:#3a4454;--bg:#0f141c;
--panel:#161c26;--accent:#7aa2ff;--warn:#fca5a5}}
@media print{.fa .acts{display:none}.fa{max-width:none}
.fa .slide{page-break-inside:avoid}}
</style>
"""


def _p(text: str) -> str:
    return f"<p>{_e(str(text))}</p>" if str(text or "").strip() else ""


def _maybe(title: str, body: str, *, absent: str = "") -> str:
    """A section, or nothing at all. §15's gate, executable.

    An empty section rendered as a heading with no content reads as a broken
    subsystem. Where the absence itself is informative the caller passes
    `absent` and it is stated; where it is not, the section does not appear.
    """
    if body.strip():
        return f"<h2>{_e(title)}</h2>{body}"
    if absent:
        return f'<h2>{_e(title)}</h2><p class="none">{_e(absent)}</p>'
    return ""


def _list(rows, *, empty: str = "") -> str:
    rows = [str(r) for r in (rows or ()) if str(r).strip()]
    if not rows:
        return f'<p class="none">{_e(empty)}</p>' if empty else ""
    return "<ul>" + "".join(f"<li>{_e(r)}</li>" for r in rows) + "</ul>"


# --- the full analysis ------------------------------------------------------

def full_analysis(decision: dict, *, company: str = "", stamp: str = "",
                  links=None) -> str:
    """Every section that changes the decision, in the order it is read."""
    d = decision or {}
    company = company or str(d.get("company") or "")
    standing = str(d.get("standing") or "")
    profile = d.get("company_profile") or {}

    head = (
        f'<p class="eyebrow">Full analysis</p><h1>{_e(company)}</h1>'
        f'<div class="lead">'
        f'<p class="q">{_e(d.get("decision_question", ""))}</p>'
        f'{_p(d.get("current_read", ""))}'
        f'<p class="none">{_e(P.say(standing, P.STANDING))}</p></div>')

    body = []

    body.append(_maybe(
        "The decision",
        _p(d.get("recommended_next_move", "")) +
        _p(d.get("recommendation_reason", "")) +
        (f'<h3>Why this question</h3>{_p(d.get("why_this_question", ""))}'
         if d.get("why_this_question") else "")))

    if profile.get("known"):
        body.append(_maybe(
            "The business, and why that decides the analysis",
            _p(profile.get("business_model")) +
            _p(profile.get("industry_structure")) +
            _p(profile.get("demand_model")) +
            "<h3>Revenue moves with</h3>" +
            _list(profile.get("primary_revenue_drivers")) +
            "<h3>Cost moves with</h3>" +
            _list(profile.get("primary_cost_drivers")) +
            "<h3>How it prices</h3>" + _p(profile.get("pricing_model")) +
            "<h3>Operating leverage</h3>" +
            _p(profile.get("operating_leverage")) +
            "<h3>Regulatory exposure</h3>" +
            _p(profile.get("regulatory_exposure")) +
            "<h3>Exposure to the cycle</h3>" +
            _p(profile.get("cyclical_exposure")) +
            f'<p class="none">{_e(profile.get("basis", ""))}</p>'))
    else:
        body.append(_maybe(
            "The business, and why that decides the analysis", "",
            absent=str(profile.get("basis") or
                       "This company is not classified in the validation "
                       "universe, so the analysis below was selected from the "
                       "published record alone.")))

    body.append(_maybe("What changed", _list(d.get("what_changed"),
                                             empty="Nothing changed.")))

    body.append(_maybe(
        "The evidence", X._evidence_body(d)))

    body.append(_maybe(
        "The economy, where it reaches this business",
        X._economics_body(d)))

    body.append(_maybe(
        "What history would say",
        X._history_body(d)))

    body.append(_maybe(
        "What we believe, and what is open",
        X._beliefs_body(d)))

    body.append(_maybe(
        "The causal question", X._causal_body(d)))

    body.append(_maybe(
        "Competitors, and how they would respond",
        X._competitor_body(d)))

    body.append(_maybe(
        "If we act, what follows", X._scenario_body(d)))

    body.append(_maybe(
        "What would prove this wrong",
        _p(d.get("falsifier", "")) +
        _list(d.get("guardrails"),
              empty="No guardrail is recorded for this reading.") +
        ("<h3>Where we stop</h3>" + _list(d.get("kill_switches"))
         if d.get("kill_switches") else "")))

    body.append(_maybe(
        "What we would need to know",
        _list(d.get("information_gaps")) +
        ("<h3>The smallest test</h3>" +
         _list(d.get("minimum_viable_experiments"))
         if d.get("minimum_viable_experiments") else "") +
        ("<h3>What data would settle it</h3>" +
         _list(d.get("minimum_data_requests"))
         if d.get("minimum_data_requests") else "") +
        ("<h3>What that is worth</h3>" +
         _list(d.get("value_of_information"))
         if d.get("value_of_information") else "")))

    body.append(_maybe("What we are watching",
                       _list(d.get("monitoring"),
                             empty="Nothing is currently preregistered.")))

    body.append(_maybe("Where this came from", X._provenance_body(d)))

    acts = ""
    if links:
        acts = ('<div class="acts">' + "".join(
            f'<a href="{_e(u)}">{_e(t)}</a>' for t, u in links) + "</div>")
    foot = f'<p class="stamp">{_e(stamp)}</p>' if stamp else ""
    return (f'{_CSS}<main class="fa">{head}{"".join(body)}{acts}{foot}'
            f'</main>')


# --- the presentation -------------------------------------------------------

def _slide(n: int, title: str, *paragraphs) -> str:
    text = "".join(_p(p) for p in paragraphs if str(p or "").strip())
    if not text:
        return ""
    return (f'<section class="slide"><p class="n">{n}</p>'
            f'<h2>{_e(title)}</h2>{text}</section>')


def presentation(decision: dict, *, company: str = "", stamp: str = "",
                 links=None) -> str:
    """The same decision as a narrative. Simplifies; never strengthens.

    Each slide is one claim and its support. A slide with nothing behind it
    is dropped rather than filled -- a deck that keeps a heading it cannot
    support is how a presentation ends up claiming more than the analysis.
    """
    d = decision or {}
    company = company or str(d.get("company") or "")
    standing = str(d.get("standing") or "")
    profile = d.get("company_profile") or {}
    scenarios = {str(s.get("name")): s for s in (d.get("scenarios") or ())}
    adversary = d.get("adversary") or ()
    transmission = d.get("economic_transmission") or ()

    slides = []
    n = 0

    def add(title, *paragraphs):
        nonlocal n
        html = _slide(n + 1, title, *paragraphs)
        if html:
            n += 1
            slides.append(html)

    add("The decision", d.get("decision_question", ""),
        d.get("why_this_question", ""))
    add("Where we stand", d.get("current_read", ""),
        P.say(standing, P.STANDING))
    add("What changed", *(d.get("what_changed") or ()))
    add("What the evidence is",
        (f'{len(d.get("supporting_evidence_ids") or ())} published evidence '
         f'row(s) sit under this reading.'
         if d.get("supporting_evidence_ids") else ""),
        ("Source independence is not measured by the published snapshot, so "
         "we do not claim how many of these are separate accounts."
         if d.get("supporting_evidence_ids")
         and not d.get("independent_origins") else ""))
    if transmission:
        first = transmission[0]
        add("The economic environment",
            first.get("mechanism", ""),
            f'That shows up in {first.get("business_variable", "")}.',
            first.get("decision_implication", ""))
    else:
        add("The economic environment",
            P.say(d.get("economic_state"), P.ECONOMIC))
    add("What history would say",
        ("No historical episode is replayed: replay needs this company's own "
         "observations as they stood at an earlier date, and the published "
         "snapshot carries only the current reading."
         if not d.get("historical_playback") else ""),
        *(d.get("historical_dimensions") or ())[:2])
    add("What we could establish, and what we could not",
        P.say(d.get("causal_status"), P.CAUSAL),
        d.get("causal_question", ""))
    if adversary:
        l1 = next((m for m in adversary if m.get("level") == "L1"), None)
        if l1:
            add("If we move, they respond",
                f'{l1.get("actor", "")} would {l1.get("action", "")}.',
                l1.get("impact", ""), l1.get("countermeasure", ""))
    down = scenarios.get("DOWNSIDE")
    adv = scenarios.get("ADVERSARIAL")
    if down or adv:
        worst = adv or down
        add("The branch to size against",
            worst.get("first_order", ""), worst.get("second_order", ""),
            worst.get("outcome_range", ""))
    add("What we recommend", d.get("recommended_next_move", ""),
        d.get("recommendation_reason", ""))
    add("What would stop us", d.get("falsifier", ""),
        *(d.get("kill_switches") or ())[:2])
    add("What we need to learn next",
        *(d.get("minimum_viable_experiments") or ()),
        *(d.get("minimum_data_requests") or ())[:1])
    add("What the system has learned since last time",
        *(d.get("what_changed_mind") or ()) or
        ("Nothing has changed our mind since the previous reading. That is "
         "not the same as nothing arriving: the record may have moved while "
         "our position on it held.",))

    appendix = (
        '<section class="slide"><p class="n">Appendix</p>'
        '<h2>Method, evidence and provenance</h2>'
        f'{X._provenance_body(d)}</section>')

    head = (f'<p class="eyebrow">Decision presentation</p>'
            f'<h1>{_e(company)}</h1>'
            f'<p class="stamp">{_e(P.label(standing))} &middot; '
            f'{n} slides</p>')
    acts = ""
    if links:
        acts = ('<div class="acts">' + "".join(
            f'<a href="{_e(u)}">{_e(t)}</a>' for t, u in links) + "</div>")
    foot = f'<p class="stamp">{_e(stamp)}</p>' if stamp else ""
    return (f'{_CSS}<main class="fa">{head}{"".join(slides)}{appendix}'
            f'{acts}{foot}</main>')
