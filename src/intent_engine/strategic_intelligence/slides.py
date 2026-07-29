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
# Lowered from 5 when the presentation stopped padding itself. A
# deterministic run legitimately produces four or five strong
# screens, and the old floor would have bounced those readers to
# the full analysis -- undoing presentation-first to satisfy a
# count.
MIN_MEANINGFUL_SLIDES = 4

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


def _lead(prefix: str, body: str) -> str:
    """Prefix a fragment without producing "Customers are really buying Not a
    box". The model writes each field as a standalone sentence, so its capital
    has to give way when it becomes a clause."""
    body = (body or "").strip()
    if not body:
        return ""
    # only lower a leading capital when the word is not a proper noun
    first, rest = body.split(" ", 1) if " " in body else (body, "")
    if first[:1].isupper() and first[1:].islower() and not rest[:1].isupper():
        body = first[0].lower() + first[1:] + (" " + rest if rest else "")
    return f"{prefix}{body}"


def _bullet(text, *, evidence=None, date="", full=False):
    # `evidence` is a list of evidence ids. A bare string is not one id, it is
    # a sequence of characters, and `list("obs-1")` turns a citation into five
    # of them — which is how the "what changed" slide came to carry thirty
    # citations labelled "-", "n", "u", "p" and "g", each an invitation to
    # check a source that does not exist.
    if isinstance(evidence, str):
        evidence = [evidence] if evidence.startswith("obs-") else []
    return {"text": " ".join(str(text or "").split()),
            "evidence": [e for e in (evidence or []) if e], "date": date,
            "full": full}


def _shorten(text: str) -> str:
    """Trim to the budget, but end on a finished thought.

    Cutting at exactly N words leaves a slide reading "...waiting does not
    preserve optionality, it just delays finding out whether the current…",
    which is worse than saying less. Prefer the last complete sentence or
    clause that fits; fall back to a word cut only when the first clause is
    itself too long.
    """
    words = text.split()
    if len(words) <= MAX_WORDS_PER_BULLET:
        return text
    head = " ".join(words[:MAX_WORDS_PER_BULLET])
    for stop in (". ", "; ", " -- ", ", "):
        cut = head.rfind(stop)
        # only worth it if a useful amount of the bullet survives
        if cut > len(head) * 0.5:
            kept = head[:cut].rstrip(" ,;-")
            # never stop inside a bracket: "the network (multiplayer, cloud
            # streaming." reads as a typo, not as concision
            if kept.count("(") != kept.count(")"):
                continue
            return kept if kept.endswith(".") else kept + "."
    return head + "…"


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
        # `full` bullets are never trimmed. The insight is one sentence chosen
        # to be the thing the reader remembers, and trimming it to the budget
        # cut "...is not conservatism" off the end -- keeping the setup and
        # deleting the point.
        if len(words) > MAX_WORDS_PER_BULLET and not bullet.get("full"):
            bullet = dict(bullet, text=_shorten(bullet["text"]))
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


_URGENCY_WORDS = {"decide_now": "Decide now", "this_quarter": "This quarter",
                  "this_year": "This year", "watch_only": "Watch only"}


_CONFIDENCE_LEAD = {
    "high": "This reading is well supported",
    "moderate": "This reading is reasonably supported",
    "low": "Treat this as a lead rather than a finding",
}


def _confidence_in_plain_words(level: str, rationale: str) -> str:
    """State how far to trust the reading, in a sentence a person would say.

    "Confidence: low" is a label. The reasoning layer already knows WHY --
    how many vantage points, whether anything independent corroborates it --
    and that reason is the part worth showing.
    """
    lead = _CONFIDENCE_LEAD.get((level or "").lower())
    reason = (rationale or "").strip().rstrip(".")
    if not lead:
        return reason and f"{reason[0].upper()}{reason[1:]}."
    return f"{lead}: {reason}." if reason else f"{lead}."


def _lower_first(text: str) -> str:
    """Lower a leading capital so a sentence can become a clause -- unless the
    first word is a proper noun, which gives "that sentry appears to be"."""
    text = (text or "").strip()
    if not text:
        return ""
    first = text.split(" ", 1)[0].strip(".,:;")
    if len(first) > 1 and first[0].isupper() and any(c.isupper()
                                                     for c in first[1:]):
        return text
    return text[0].lower() + text[1:]


def founder_view_from_report(report) -> dict:
    """Adapt a deterministic report into the founder presentation contract.

    THE POINT OF THIS FUNCTION is that there is one founder-facing product,
    not two. Before it, a grounded run rendered the founder deck and every
    other run rendered a different deck that opened with "{company} in one
    minute" and closed on "Key strategic signals" -- a company description
    followed by internal vocabulary. Which product you saw depended on whether
    an API key happened to be configured.

    Both paths now populate the same contract and render through the same
    system. The deterministic path fills FEWER fields, deliberately: it cannot
    honestly reconstruct a business model, name what management is protecting,
    or say what a competitor will do, so it leaves those empty and the
    renderer omits those screens. A shorter honest presentation, not the same
    shape padded out.

    Nothing here invents language. Every string is one the reasoning layer
    already produced from this company's evidence, and that layer already
    hedges ("appears to be", "the evidence supports this as a low-confidence
    hypothesis"), which is the register this path should be speaking in.
    """
    r = report.as_dict() if hasattr(report, "as_dict") else (report or {})
    thesis = r.get("thesis") or {}
    hypotheses = r.get("hypotheses") or []
    top = hypotheses[0] if hypotheses else {}
    if hasattr(top, "as_dict"):
        top = top.as_dict()

    def _first(seq):
        seq = list(seq or ())
        return seq[0] if seq else ""

    # THE TAKEOVER GATE.
    #
    # Only replace the fallback when there is a real fact strong enough to
    # earn it. Sentry's run retrieved a page titled "Sentry Acquires Codecov"
    # -- a named acquisition -- and the deck opened instead with "broadening
    # from a focused tool toward being the place a team's work is stored",
    # which is the tool_to_system_of_record scaffold and reads identically for
    # Notion, Linear or Atlassian.
    #
    # The gate is deliberately narrow. An earlier attempt took the deck over
    # whenever page titles existed at all, which pushed a dental practice and
    # a hostile site into asserting a shape they could not fill. No concrete
    # development means this returns {} and every existing path is untouched.
    from intent_engine.strategic_intelligence.concrete import (
        reads_as_taxonomy, select_founder_claim_anchor,
    )
    anchor = select_founder_claim_anchor(r.get("observations") or [],
                                         company=r.get("company_name", ""))
    claim = thesis.get("transition") or top.get("statement") or ""
    if not anchor:
        # Nothing concrete to lead with. The caller falls back, and the
        # limited-analysis page (which explains what was and was not found)
        # is the right destination for these -- not a padded deck.
        return {}

    # FACT first, in the company's own words. The scaffold reading may follow
    # as an interpretation, and only if it is not built from ontology
    # vocabulary -- a reader can check "Sentry acquired Codecov" against the
    # world and cannot check "becoming the place a team's work is stored".
    fact = anchor["fact"]
    supporting = [t for t in anchor.get("supporting") or [] if t]
    interpretation = ""
    if claim and not reads_as_taxonomy(claim):
        interpretation = f"A plausible reading is that {_lower_first(claim)}"
    elif top.get("reasoning") and not reads_as_taxonomy(top["reasoning"]):
        interpretation = top["reasoning"]
    paragraph = " ".join(x for x in [
        (f"Alongside: {' '.join(supporting)}" if supporting else ""),
        interpretation,
    ] if x).strip()

    decision = thesis.get("why_care") or ""
    falsifier = _first(top.get("falsification_questions"))
    questions = [q.get("question", "") if isinstance(q, dict) else str(q)
                 for q in (r.get("questions") or [])]

    view = {
        # The one claim, stated first. Not a company description.
        "the_insight": {
            "sentence": fact,
            "paragraph": paragraph,
            "why_now": _why_now_in_plain_words(top.get("why_now", "")),
            "tension": {"side_a": thesis.get("tension", ""),
                        "side_b": "", "why_it_exists": ""},
            "economics": {"mechanism": "", "levers": []},
            "consequence_chain": [],
            "citations": [anchor["observation_id"]] if anchor.get(
                "observation_id") else list(
                top.get("strongest_support_ids") or []),
        },
        # Deterministically we can name the decision the evidence bears on,
        # but not its urgency or reversibility -- so those stay empty and the
        # ranking layer is told not to promote anything to "today".
        "decisions": ([{
            "decision": decision,
            "why_it_matters": "",
            "cost_of_waiting": "",
            "what_a_competitor_may_do_first": "",
            "upside": "", "downside": "",
            "what_would_invalidate_it": falsifier,
            "what_to_watch": falsifier,
            "confidence": top.get("confidence", ""),
            "confidence_rationale": _readable_confidence_reason(
                top.get("confidence_reasons")),
            "citations": list(top.get("strongest_support_ids") or []),
        }] if decision else []),
        "strongest_case_we_are_wrong": _first(
            top.get("alternative_explanations")),
        "questions": questions[:3],
        "evidence_gaps": list(r.get("evidence_gaps") or [])[:2],
        # Left empty on purpose -- see the docstring. The renderer drops the
        # screens these would have filled.
        "business_model": {}, "mental_model": {}, "competitive": {},
        "scenarios": {}, "assumptions": [],
        #: deterministic reasoning never claims something deserves today
        "supports_urgency": False,
    }
    return view


def _readable_confidence_reason(reasons) -> str:
    """The reasoning layer emits several reasons, the first of which is a
    signal-matching trace ("3 qualifying signal(s) matched: ..."). That is the
    system describing its own machinery. Prefer a reason about the EVIDENCE."""
    for reason in (reasons or ()):
        low = str(reason).lower()
        if "signal" in low or "qualifying" in low:
            continue
        return str(reason)
    return ""


def _why_now_in_plain_words(why_now: str) -> str:
    """The reasoning layer says "Recent public signal (2026-07-20, Pricing)
    keeps this timely", which is the system describing its own inputs. A
    reader wants the date and the page, not the word "signal"."""
    import re
    match = re.search(r"\(([^,]+),\s*(.+?)\)", why_now or "")
    if not match:
        return "" if "signal" in (why_now or "").lower() else (why_now or "")
    when, where = match.group(1).strip(), match.group(2).strip()
    return f"The most recent evidence is {where} ({when})."


def build_founder_slides(analysis, *, company="") -> list:
    """The deck a founder is shown. It answers five questions and stops.

    An audit of the previous deck measured the real problem, which was not
    repetition -- the highest similarity between any two fields was 0.32, and
    the median was 0.04. The problem was volume and invisibility: 2,361 words
    of reasoning produced 896 words on screen, and fifteen fields never
    reached the founder at all. Among the invisible ones were what leadership
    is protecting, where it might be blind, and the case for the whole reading
    being wrong -- the most valuable things in the analysis.

    So this deck is built backwards from the five questions a founder needs
    answered, and anything that does not serve one of them is not built:

        1  What business are they really in?
        2  What game are they playing, and why?
        3  What is leadership protecting, and what are they giving up?
        4  What assumption is carrying the weight?
        5  What should a competitor be afraid of?

    The decision slides sit between 3 and 4 because that is where a reader
    asks "so what do I do about it".
    """
    a = analysis or {}
    bm = a.get("business_model") or {}
    ins = a.get("the_insight") or {}
    mm = a.get("mental_model") or {}
    decisions = a.get("decisions") or []
    comp = a.get("competitive") or {}
    scen = a.get("scenarios") or {}
    blind = a.get("blind_spots") or {}
    assumptions = a.get("assumptions") or []
    cites = ins.get("citations") or []

    from intent_engine.strategic_intelligence.analyst.priority import (
        todays_decision, weakest_assumption,
    )
    slides = []

    # 0 - today, only when something has earned it
    today = todays_decision(decisions) if a.get("supports_urgency", True) \
        else None
    if today:
        slides.append(_slide("today", "What deserves today", [
            _bullet(today.get("decision", ""),
                    evidence=today.get("citations") or [], full=True),
            _bullet(_lead("Why now: ", today.get("cost_of_waiting", ""))),
        ], kind="today"))

    # 1 - what business are they really in
    slides.append(_slide("business", "What business they are really in", [
        _bullet(bm.get("one_line", ""), evidence=cites),
        _bullet(_lead("The money comes from ",
                      bm.get("where_profit_comes_from", ""))),
        _bullet(_lead("What customers are really buying: ",
                      bm.get("what_customers_actually_buy", ""))),
    ], kind="business_model"))

    # 2 - the game, and the one sentence worth remembering
    slides.append(_slide("game", "The game they are playing", [
        _bullet(bm.get("the_game_they_are_playing", ""), full=True),
        _bullet(_lead("It costs them ", bm.get("where_value_leaks", ""))),
    ], kind="game"))

    slides.append(_slide("insight", "The insight", [
        _bullet(ins.get("sentence", ""), evidence=cites, full=True),
        _bullet(ins.get("paragraph", "")),
    ], kind="insight"))

    # Why it matters now, and the trade-off underneath it. Restored after the
    # five-questions rebuild dropped it: the tension is one of the few things
    # the deterministic path can state honestly from its own reasoning, and
    # without this screen it had nowhere to appear at all.
    tension = ins.get("tension") or {}
    slides.append(_slide("why_now", "Why this matters now", [
        _bullet(ins.get("why_now", "")),
        _bullet(_lead("The trade-off: ", tension.get("side_a", ""))),
        _bullet(_lead("Against that: ", tension.get("side_b", ""))),
        _bullet((ins.get("economics") or {}).get("mechanism", "")),
    ], kind="tension"))

    # 3 - what leadership is protecting and giving up
    slides.append(_slide("mental_model", "What leadership is protecting", [
        _bullet(_lead("They believe ", mm.get("they_believe", ""))),
        _bullet(_lead("They are protecting ",
                      mm.get("they_are_protecting", ""))),
        _bullet(_lead("They have accepted losing ",
                      mm.get("they_are_sacrificing", ""))),
        _bullet(_lead("This could blind them to ",
                      mm.get("where_this_could_blind_them", ""))),
    ], kind="mental_model"))

    # the decisions
    for i, d in enumerate(decisions[:2]):
        when = _URGENCY_WORDS.get(d.get("urgency", ""), "")
        slides.append(_slide(f"decision-{i + 1}",
                             f"The decision: {when}" if when
                             else "The decision", [
            _bullet(d.get("decision", ""),
                    evidence=d.get("citations") or [], full=True),
            _bullet(_lead("Waiting costs: ", d.get("cost_of_waiting", ""))),
            _bullet(_lead("A rival may move first: ",
                          d.get("what_a_competitor_may_do_first", ""))),
        ], kind="decision"))

    # 4 - the assumption carrying the weight
    weakest = weakest_assumption(assumptions) or {}
    slides.append(_slide("assumption", "The assumption carrying the weight", [
        _bullet(weakest.get("assumption", ""), full=True),
        _bullet(_lead("It breaks if ", weakest.get("what_would_break_it", ""))),
        _bullet(_lead("Almost nobody is discussing ",
                      blind.get("almost_nobody_is_discussing", ""))),
    ], kind="assumption"))

    # 5 - what a competitor should be afraid of
    slides.append(_slide("threat", "What rivals should fear", [
        _bullet(comp.get("what_rivals_should_fear", ""), full=True),
        _bullet(_lead("Forcing the change: ",
                      comp.get("who_is_forcing_the_change", ""))),
        _bullet(_lead("If nobody responds: ",
                      comp.get("if_nobody_responds", ""))),
    ], kind="competitive"))

    # and the case against, argued rather than disclaimed
    slides.append(_slide("wrong", "Why this could be wrong", [
        _bullet(a.get("strongest_case_we_are_wrong", ""), full=True),
        _bullet(_lead("The wild card: ", scen.get("wild_card", ""))),
    ], kind="counterargument"))

    # what to watch
    watch = [_bullet(s) for s in (scen.get("leading_indicators") or [])[:2]]
    watch += [_bullet(q) for q in (a.get("questions") or [])[:2]]
    slides.append(_slide("watch", "What to watch, and what to ask",
                         watch, kind="monitor"))

    # What this could not establish. Not a disclaimer -- a reader deciding how
    # far to trust the reading needs to know which part of the picture is
    # missing, and it is the one screen the deterministic path can always fill
    # honestly from its own coverage.
    # How far to trust it, in a sentence, and what is missing.
    #
    # The persona evaluation caught this: rebuilding the deck dropped
    # confidence entirely and 17 cases failed on "unanswered: how confident to
    # be". A reader deciding what to do with a reading needs to know how well
    # supported it is, and "low" on its own is a label, not an answer.
    first = (decisions or [{}])[0]
    confidence_line = _confidence_in_plain_words(
        first.get("confidence", ""), first.get("confidence_rationale", ""))
    slides.append(_slide("gaps", "How far to trust this", (
        [_bullet(confidence_line, full=True)] if confidence_line else []
    ) + [_bullet(g) for g in (a.get("evidence_gaps") or [])[:3]],
        kind="gaps"))

    return [s for s in slides if s]


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

    # When a verified analysis exists, the founder deck replaces this one
    # outright rather than being appended to it. Showing both would mean
    # showing the same company twice: once as advice and once as method.
    # ONE founder-facing product. A grounded analysis fills the contract
    # richly; a deterministic report fills less of it. Both render here.
    analysis = r.get("strategic_analysis")
    if analysis and (analysis.get("decisions") or []):
        return build_founder_slides(analysis, company=company)
    adapted = founder_view_from_report(r)
    if adapted:
        return build_founder_slides(adapted, company=company)

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
/* Available to assistive technology, absent from the visual design. Not
   display:none, which would remove it from the accessibility tree too and
   leave the page with no heading again. */
.deck-title{position:absolute;width:1px;height:1px;margin:-1px;padding:0;
overflow:hidden;clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap;
border:0}
.deck .slide{display:none}
/* Order matters. The first slide is shown unconditionally, then hidden again
   only once some OTHER slide is targeted. Written the other way round — hiding
   everything and revealing the first via :has — a browser without :has drops
   the rule as invalid and the deck renders blank. This way the worst case is
   the first slide staying visible alongside the current one: degraded, still
   entirely readable. */
.deck .slide:first-of-type{display:block}
.deck .slide:target{display:block}
/* Hiding the first slide once another is targeted used to need :has(), which
   is Safari 15.4+ — the one place in the product whose correctness depended on
   a browser version, and the reason a Safari pass was a release blocker rather
   than a formality. A class toggled on navigation does the same job in every
   browser, and when the script never runs the behaviour is what it always was:
   the first slide stays visible. */
.deck.is-navigated .slide:first-of-type:not(:target){display:none}
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
  /* Mark the deck as navigated whenever a slide is targeted, so the first
     slide can be hidden without :has(). Runs on load too, because a deck can
     be opened directly at #slide-3 from a link or a refresh. */
  function sync(){
    var t=deck.querySelector('.slide:target');
    deck.classList[t?'add':'remove']('is-navigated');
  }
  sync();
  window.addEventListener('hashchange',sync);
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
        # A date earns its place only when it distinguishes one bullet from
        # another. Every bullet carried the SAME retrieval date -- the day the
        # run happened -- which read as chronology that was not there.
        _dates = {b.get("date") for b in slide["bullets"]
                  if is_meaningful(b.get("date"))}
        _dated = len(_dates) > 1
        bullets = "".join(
            f'<li>' + (f'<span class="when">{_e(b["date"])}</span>'
                       if _dated and is_meaningful(b.get("date")) else '')
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
            # The build version was printed under every slide. It answers a
            # question no reader has, and reads as an internal artefact on a
            # page meant to be shown in a meeting.
            f'<p class="meta">{_e(company)} · {_e(as_of)}</p>'
            f'</section>')
    # A visually-hidden <h1>. The deck had no top-level heading at all: each
    # slide is an <h2>, so a screen-reader user met a page whose outline began
    # at the second level and never learned whose presentation they were in.
    # Hidden rather than shown because the deck's design puts the company name
    # in the status bar, and a duplicate title would push the first slide down
    # the screen for everyone else.
    return (_CSS + f'<h1 class="deck-title">{_e(company)} — presentation</h1>'
            f'<div class="deck" role="region" '
            f'aria-roledescription="carousel" '
            f'aria-label="{_e(company)} presentation">'
            + "".join(out) + _KEYS + '</div>')
