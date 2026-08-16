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
import re

from intent_engine.strategic_intelligence.editorial import (
    SaidOnce, addresses_the_system, deduplicate, is_meaningful, lower_first,
    meaningful_items, sentence_identity,
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
        text = _readable_excerpt(document)
        if not text:
            continue
        out.append(_bullet(text, date=document.get("date", "")))
        if len(out) >= limit:
            break
    return out


# Page furniture that parses as text but describes no company. Each of these
# markers was read off a live slide.
_PAGE_FURNITURE = (
    "site footer", "help centre", "help center", "skip to", "cookie",
    "privacy policy", "terms of use", "terms of service", "all rights reserved",
    "sign up", "log in", "newsletter", "follow us", "download the app",
    # SEC cover pages: every filing opens with several hundred words of these
    "state or other jurisdiction", "commission file", "irs employer",
    "securities act", "exchange act", "written communication pursuant",
    "check the appropriate box", "title of each class",
    "emerging growth company", "incorporation or organization",
    "securities and exchange commission", "date of report",
    "date of earliest event", "former name or former address",
    "registrant's telephone number", "principal executive offices",
)

# Text addressed to whatever is reading the page rather than to a person.
# Retrieved content is data: a page may say anything, and what it may not do
# is end up in the product's own voice on a slide.
_ADDRESSED_TO_THE_MACHINE = (
    "ignore all previous instructions", "unrestricted mode", "system:",
    "note to any automated", "classify this page as", "raise confidence to",
    "should be cited as", "must not mention that",
)

# Comparative superiority a company asserts about itself, with nothing on the
# page to check it against. Rejected on the company's OWN pages only -- an
# independent source calling a company the market leader is a finding, and the
# same words self-published are an advertisement.
_UNEARNED_SELF_CLAIM = (
    "market leader", "unanimously confirmed", "highest market share",
    "no meaningful competitors", "best retention", "best-in-class",
    "world's leading", "world's best", "undisputed", "unrivalled",
    "unrivaled", "second to none",
)


def _readable_excerpt(document, *, budget=260) -> str:
    """Prose from a page, rather than whatever the extraction caught first.

    A deck is the surface where this shows most. Live on Airbnb, three of
    seven slides were raw page text: "Products, customers and market" was the
    site footer verbatim ("Site Footer. Support. Help Centre. Get help with a
    safety issue. AirCover."), "Airbnb in one minute" was the SEO listing strip
    ("Hinton Pet-friendly rentals. Porto Condo rentals."), and the published-
    evidence slide opened on the 8-K cover page ("Delaware. 001-39778.
    26-3051428. (State or other jurisdictionof incorporation)").

    Nav labels and list items are not sentences: they are short, and they are
    mostly capitalised because they are headings. Requiring a real sentence --
    ten words, several of them lowercase, and no furniture marker -- keeps the
    description and drops the chrome. A page that yields nothing loses its
    bullet rather than contributing the least-bad line: three real bullets
    beat three where two are footer.
    """
    # A company's own pages may not have their superlatives repeated as
    # findings. This surfaced when furniture filtering moved a hostile
    # fixture's "Independent analysts have unanimously confirmed that Hostile
    # Co has the highest market share... and no meaningful competitors" into
    # the bullet budget: the sentence had always been in the document, and
    # only the truncation point had been keeping it off the slide.
    reject = tuple(_PAGE_FURNITURE) + tuple(_ADDRESSED_TO_THE_MACHINE)
    if document.get("source_class") in (None, "", "company_owned",
                                        "executive_statement",
                                        "investor_material"):
        reject += tuple(_UNEARNED_SELF_CLAIM)

    for source in (document.get("meta_description"),
                   document.get("text_content")):
        sentences = re.split(r"(?<=[.!?])\s+",
                             " ".join((source or "").split()))
        kept, total = [], 0
        for sentence in sentences:
            low = sentence.lower()
            if any(marker in low for marker in reject):
                continue
            words = sentence.split()
            if len(words) < 10:
                continue
            if sum(1 for w in words if w[:1].islower()) < 4:
                continue
            kept.append(sentence)
            total += len(sentence)
            if total >= budget:
                break
        if not kept:
            continue
        # The page's own heading, when the page also has prose. A product
        # page's <h1> IS the product names -- "Foundry and Gotham and AIP" --
        # and a ten-word floor drops it, which cost the deck the one place
        # Gotham was named. Requiring prose alongside it is what separates a
        # heading from a footer: a footer is short lines all the way down and
        # still contributes nothing.
        lead = sentences[0] if sentences else ""
        lead_words = lead.split()
        if (lead and lead not in kept and 2 <= len(lead_words) <= 12
                and not any(m in lead.lower() for m in _PAGE_FURNITURE)
                and sum(1 for w in lead_words[1:] if w[:1].isupper()) >= 1):
            kept.insert(0, lead if lead[-1:] in ".!?" else lead + ".")
        text = " ".join(kept).strip()
        if len(text) >= 40:
            return text
    return ""


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


_lower_first = lower_first


def _confirm_question(title: str) -> str:
    """Turn one of the run's dated findings back into something to go and check.

    ONE PHRASING, TWO DECKS. Both founder-facing decks reach the same dead end
    — a reader with nothing to investigate because every question the run
    produced came from the pattern library and was filtered — and both answer
    it the same way, from the run's own findings. Written twice, the two
    copies would drift and only one of them would be the sentence anyone
    reviewed.

    Not `_lower_first`: these titles OPEN with the company name, and
    lowercasing turned "Linear pricing publishes its prices" into "linear
    pricing publishes its prices" in the reader's own deck.
    """
    return (f"Confirm with an independent or customer source: "
            f"{title.rstrip('.')}.")


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
    # THE READING MAY NOT ARRIVE WITHOUT WHAT CAUSED IT.
    #
    # "A plausible reading is that {company} appears to be broadening from a
    # focused tool toward being the place a team's work is stored, which
    # raises switching cost" was shown to HubSpot and Datadog with nothing
    # behind it a reader could check. The claim was correct and the evidence
    # existed — it just never reached this screen. The mechanism sentence now
    # travels WITH the interpretation, from `mechanism.because_line`, and a
    # reading that cannot produce one does not get to assert itself here.
    # Same three states as the narrative, in the same order, from the same
    # module — see `narrative.py`. The deck and the brief must not disagree
    # about why a company got a reading, and the only way to guarantee that is
    # for both to ask `mechanism` rather than each deciding for itself.
    from intent_engine.strategic_intelligence import mechanism as MECH
    interpretation = ""
    if claim and not reads_as_taxonomy(claim):
        because = MECH.because_line(top)
        if because:
            interpretation = (f"A plausible reading is that "
                              f"{_lower_first(claim)} The company's own words: "
                              f"{because}")
        elif MECH.needs_mechanism(top):
            interpretation = (f"A plausible reading is that "
                              f"{_lower_first(claim)} No retrieved source "
                              f"states this in its own words.")
        else:
            # A pattern that declares no mechanism gate is recorded debt, not
            # a hidden claim; it keeps the reading it always had.
            interpretation = f"A plausible reading is that {_lower_first(claim)}"
    elif top.get("reasoning") and not reads_as_taxonomy(top["reasoning"]):
        interpretation = top["reasoning"]
    paragraph = " ".join(x for x in [
        (f"Alongside: {' '.join(supporting)}" if supporting else ""),
        interpretation,
    ] if x).strip()

    # THE DECISION, NOT THE TOPIC.
    #
    # This was `thesis["why_care"]`, which is `implications[0]` -- "Whether to
    # keep investing in depth or in adjacency". The deck printed the question
    # under the heading "The decision" and the founder was left exactly where
    # they started. The composed object states which options exist, what each
    # wins and costs, and what would settle it, and when the evidence cannot
    # support two options it says so instead of choosing one.
    from intent_engine.strategic_intelligence.decision import decision_of
    composed = decision_of(r)
    # WITHHELD IS A POSITION, NOT AN ABSENCE.
    #
    # `composed` already states it: "No decision is put forward: the public
    # record did not carry enough to read one from", with `unsafe_because`
    # naming what is missing. That was computed and then dropped here, so a
    # run with real findings but no hypothesis answered "so what do I do
    # about it" with silence — and silence reads as the analysis having
    # forgotten to finish rather than having declined on purpose.
    #
    # It is carried only when the run found something. A company with no
    # findings AND no decision has nothing to present, and
    # `test_a_deck_with_nothing_concrete_is_not_presentable` is the contract
    # that says so — this must not become the slide that pads that deck to
    # the floor.
    decision = composed.headline if composed.readiness != "WITHHELD" else ""
    if not decision and (r.get("shifts") or ()):
        decision = composed.headline
    best = composed.options[0] if composed.options else None
    # WATCH ITEMS ARE FOUNDER-FACING, so taxonomy is filtered HERE -- at the
    # point where the visible item is selected, not by sanitising every string
    # in the system.
    #
    # The live Sentry deck told a reader to watch for "customers describing it
    # as a companion to a system of record rather than the record itself".
    # That is the pattern's own falsification question. A reader cannot observe
    # it, cannot check it, and has never heard the phrase.
    #
    # A rejected item is dropped, not replaced: there is no company-specific
    # observable to substitute, and generic filler would be worse than a
    # shorter screen.
    def _watchable(text):
        text = (text or "").strip()
        return text if text and not reads_as_taxonomy(text) else ""

    falsifier = _watchable(_first(top.get("falsification_questions")))
    questions = [q for q in
                 (_watchable(q.get("question", "") if isinstance(q, dict)
                             else str(q))
                  for q in (r.get("questions") or [])) if q]
    # Every question this layer produces is built FROM a hypothesis, so a run
    # that reached no hypothesis leaves the reader nothing to investigate —
    # the same dead end the fallback deck already answers, and the same
    # answer. See `_confirm_question`.
    if not questions:
        questions = [_confirm_question(t) for t in
                     (s.get("title", "") for s in (r.get("shifts") or ()))
                     if t and not reads_as_taxonomy(t)][:2]

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
            "readiness": composed.readiness,
            "options": [o.as_dict() for o in composed.options],
            "recommended_next_move": composed.recommended_next_move,
            "limitation": composed.limitation,
            "unsafe_because": composed.unsafe_because,
            "evidence_required": list(composed.evidence_required),
            "what_each_result_would_favour":
                composed.what_each_result_would_favour,
            "undecided_question": composed.undecided_question,
            "why_it_matters": best.business_consequence if best else "",
            "cost_of_waiting": "",
            "what_a_competitor_may_do_first": "",
            "upside": best.upside if best else "",
            "downside": best.downside if best else "",
            "what_would_invalidate_it": composed.falsifier or falsifier,
            "what_to_watch": falsifier,
            "confidence": top.get("confidence", ""),
            "confidence_rationale": _readable_confidence_reason(
                top.get("confidence_reasons")),
            "citations": list(top.get("strongest_support_ids") or []),
        }] if decision else []),
        # Both of these reached a live slide carrying "source of truth": the
        # case against is an alternative explanation and the gaps are the
        # scaffold's own, so they are library prose like everything else here
        # and get the same filter at the point of selection.
        "strongest_case_we_are_wrong": next(
            (a for a in (top.get("alternative_explanations") or ())
             if a and not reads_as_taxonomy(a)), ""),
        "questions": questions[:3],
        # The run's dated findings, carried rather than dropped. Only this
        # adapter sets the key: a grounded analysis writes its own screens and
        # must not have one appended from a different layer. Same taxonomy
        # filter as everything else chosen for display, and the same rule —
        # a rejected finding is dropped, never reworded.
        "dated_findings": [
            {"title": s.get("title", ""), "date": s.get("date", ""),
             "observation_id": s.get("observation_id", "")}
            for s in (r.get("shifts") or ())
            if s.get("title") and not reads_as_taxonomy(s.get("title", ""))],
        "evidence_gaps": [g for g in (r.get("evidence_gaps") or ())
                          if g and not reads_as_taxonomy(g)][:2],
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
    """"Why now" is a reason, and provenance is not one.

    The reasoning layer says "Recent public signal (2026-07-20, Pricing) keeps
    this timely", which is the system describing its own inputs. An earlier fix
    rewrote that as "The most recent evidence is Pricing (2026-07-20)" -- which
    reads better and still answers nothing. A founder shown that under "why
    now" learns when a page was published, not why the situation is urgent, and
    it was one of the three strings the deployed Palantir deck was criticised
    for.

    So a value whose entire content is a date and a page name is WITHHELD. A
    slide with no reason omits the line instead of printing a citation stamp
    where an argument belongs -- the same rule the founder brief applies to
    "why this matters".
    """
    import re
    text = (why_now or "").strip()
    if not text:
        return ""
    match = re.search(r"\(([^,]+),\s*(.+?)\)", text)
    if not match:
        # Prose that never mentioned the pipeline's own vocabulary is a real
        # reason and passes through untouched.
        return "" if "signal" in text.lower() else text
    # Everything outside the parenthetical is the pipeline's own phrasing
    # ("Recent public signal ... keeps this timely"), so what remains is
    # provenance only. That is a citation, and citations belong on evidence.
    return ""


def _upper_first(text: str) -> str:
    """`unsafe_because` is written as a clause because the headline embeds it.
    Standing alone as a bullet it is a sentence and needs a capital."""
    text = (text or "").strip()
    return text[:1].upper() + text[1:] if text else ""


def _identity(text: str, limit: int = 120) -> str:
    """A sentence's identity, so a deck can tell whether it already said it.

    The rule now lives in `editorial`, because the scrollable narrative needs
    exactly the same one and two implementations of "have I said this" is how
    one surface deduplicates what the other repeats. Kept as a name here so
    the call sites below read the same as they did.
    """
    return sentence_identity(text, limit)


def _decision_detail_slides(decision: dict, *, index: int = 0,
                            already_shown=()) -> list:
    """The options, or the honest reason there are none.

    Two screens at most, and only the one the readiness earns. A decision
    slide that names a choice and then shows nothing a reader can weigh is the
    same failure as printing the topic: it looks like an answer and carries
    none. Where the evidence supports two courses of action they appear side
    by side with what each wins, costs and assumes; where it does not, the
    screen says what cannot be concluded, which evidence is missing and the
    one bounded thing worth going to find out.
    """
    slides, options = [], (decision.get("options") or [])
    readiness = decision.get("readiness", "")
    shown = {_identity(t) for t in (already_shown or ())}

    def _fresh(text):
        """Drop a bullet this deck has already said, or already contains.

        Two collapses, both measured on the deployed decks. The next move and
        the missing evidence become the same sentence whenever no
        falsification question survives filtering. And the mechanism is the
        act option's key assumption, its upside, and -- on the
        alternative-derived path -- part of the headline too, so it appeared
        four times across two screens.

        Containment, not equality: "value and lock-in migrate from the visible
        product" and "If this reading holds, value and lock-in migrate from
        the visible product" are one sentence to a reader, and the second is
        not a prefix of the first.
        """
        key = _identity(text)
        if not text or not key:
            return ""
        if any(key in seen or seen in key for seen in shown):
            return ""
        shown.add(key)
        return text

    if readiness == "DECISION_READY" and len(options) >= 2:
        # ONE SCREEN PER OPTION, not both on one.
        #
        # Two options with an upside and a cost each is four bullets, and the
        # slide budget drops the fourth -- which is option two's cost, the one
        # thing a reader weighing them cannot do without. A deck compares
        # across consecutive screens; it does not need them side by side to be
        # a comparison, and at 375px they would not be side by side anyway.
        for n, option in enumerate(options[:2]):
            label = (option.get("label") or "").rstrip(":")
            # DEDUPED WITHIN THE SCREEN, not against the deck.
            #
            # The upside IS this screen -- it is what the option wins, and
            # dropping it because the decision screen already named the
            # mechanism left "Option 1" with nothing but its cost. What has to
            # go is the assumption when it restates what is already on the
            # same screen, which is the common case: the act option's key
            # assumption is the mechanism, and so is its upside.
            upside = option.get("upside", "")
            downside = option.get("downside", "")
            assumption = option.get("key_assumption", "")
            # Compared in full, not on the 120-character prefix the
            # cross-slide check uses: the assumption sits INSIDE the upside
            # here ("If <assumption>, nothing has been committed against it"),
            # and a truncated needle stops matching a truncated haystack.
            here = f"{_identity(upside, 0)} {_identity(downside, 0)}"
            if _identity(assumption, 0) and _identity(assumption, 0) in here:
                assumption = ""
            slides.append(_slide(
                f"option-{index + 1}-{n + 1}", f"Option {n + 1}: {label}", [
                    _bullet(upside,
                            evidence=option.get("supporting_evidence_ids")
                            or []),
                    _bullet(_lead("The cost: ", downside)),
                    _bullet(_lead("This assumes ", assumption)),
                ], kind="options",
                note="Cited against the evidence behind it."))
        slides.append(_slide(f"next-{index + 1}", "What to do next", [
            _bullet(_fresh(decision.get("recommended_next_move", ""))),
            _bullet(_lead("What this cannot settle: ",
                          _fresh(decision.get("limitation", "")))),
        ], kind="next_move"))
        return [s for s in slides if s]

    # WITHHELD belongs on this screen too. It is the same state one degree
    # further along — INVESTIGATION_REQUIRED says no option can be committed
    # to yet, WITHHELD says the record did not carry enough to name options at
    # all — and "What cannot be concluded yet" is the heading for both. Routed
    # anywhere else it becomes a one-line decision screen asserting that there
    # is no decision, with the reason left off.
    if readiness in ("INVESTIGATION_REQUIRED", "WITHHELD"):
        verified = [v for v in (decision.get("verified") or []) if v]
        slides.append(_slide(f"investigate-{index + 1}",
                             "What cannot be concluded yet", [
            _bullet(_lead("What was verified: ",
                          _fresh(verified[0] if verified else ""))),
            _bullet(_upper_first(_fresh(decision.get("unsafe_because", "")))),
            _bullet(_fresh(decision.get("recommended_next_move", ""))),
            _bullet(_lead("The evidence that would settle it: ",
                          _fresh((decision.get("evidence_required")
                                  or [""])[0]))),
            _bullet(_fresh(decision.get("what_each_result_would_favour", ""))),
        ], kind="investigation",
            note="Stated as an open question because the public record does "
                 "not close it."))
    return [s for s in slides if s]


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

    # What the run actually found, dated.
    #
    # THE DEFECT THIS FIXES: having MORE evidence produced a WORSE deck.
    # A concrete development is what hands a company to this deck rather than
    # the fallback one — and the fallback builds a "What changed recently"
    # screen from the run's dated findings while this one had nowhere to put
    # them, so they were computed and then dropped. Invisible while a pattern
    # was firing (its slides filled the deck), visible the moment one stopped:
    # Brightledger, which publishes four dated findings, fell to two screens
    # when `tool_to_system_of_record` was correctly gated off it.
    #
    # These are not filler. Each is an observation this run retrieved, with a
    # date and a citation, phrased as the consequence the reader should draw.
    # `_slide` returns None when nothing survives, so a company with no dated
    # findings gets no screen rather than an empty heading.
    slides.append(_slide("found", "What the analysis found", [
        _bullet(f.get("title", ""), date=f.get("date", ""),
                evidence=[f["observation_id"]] if f.get("observation_id")
                else [])
        for f in (a.get("dated_findings") or [])[:4]
    ], kind="findings"))

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
        # A BOUNDED DECISION GETS ONE SCREEN, NOT TWO.
        #
        # Its headline is "no option is safe to commit to yet, because X", and
        # the investigation screen below opens with that same X. Rendering
        # both put the identical sentence on two consecutive screens under two
        # headings, which reads as a broken deck and pads the count with a
        # repeat. WITHHELD is the same shape — "no decision is put forward"
        # followed by a screen whose first line is why — so it is skipped here
        # for the same reason.
        if d.get("readiness") not in ("INVESTIGATION_REQUIRED", "WITHHELD"):
            slides.append(_slide(f"decision-{i + 1}",
                                 f"The decision: {when}" if when
                                 else "The decision", [
                _bullet(d.get("decision", ""),
                        evidence=d.get("citations") or [], full=True),
                _bullet(_lead("Waiting costs: ", d.get("cost_of_waiting", ""))),
                _bullet(_lead("A rival may move first: ",
                              d.get("what_a_competitor_may_do_first", ""))),
            ], kind="decision"))
        slides.extend(_decision_detail_slides(
            d, index=i,
            already_shown=[b["text"] for s in slides if s
                           for b in s["bullets"]]))

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
                 brief=None, documents=(), contract=None) -> list:
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
        return meeting_quality(
            build_founder_slides(analysis, company=company))
    adapted = founder_view_from_report(r)
    if adapted:
        return meeting_quality(
            build_founder_slides(adapted, company=company))

    # The deck below is the fallback for a company with real evidence but no
    # concrete development to lead with. It was the LAST founder-facing surface
    # still printing the pattern library verbatim.
    #
    # Measured on production across five companies: every one that produced a
    # deck at all leaked here -- Hugging Face and Stripe carried "system of
    # record", "broadening from a focused tool" and "strategic signal";
    # CrowdStrike two of the three. The brief and the full analysis were clean
    # for all five, because those were filtered and this was not. Three of
    # three analysable companies is the norm, not an edge case.
    #
    # Same discipline as everywhere else: filter where the visible item is
    # chosen. A rejected bullet is DROPPED, never reworded -- and `_slide`
    # returns None once nothing is left, so an empty slide removes itself
    # rather than standing there as a heading over silence.
    from intent_engine.strategic_intelligence.concrete import reads_as_taxonomy

    def _concrete(text):
        """A founder-facing claim, or "".

        This was a non-emptiness check with a taxonomy filter, which is why
        "Palantir Partnership Vanguard" -- a retrieved PAGE TITLE -- reached a
        deployed slide as strategic intelligence. A title is not taxonomy, so
        nothing stopped it; the same hole passed internal pattern names
        ("product→platform") arriving via `hypothesis.title`.

        The contract is shared with the founder brief rather than restated
        here: a claim needs a finite assertion, not merely words. Grammar
        alone is insufficient, so metadata openings are excluded explicitly --
        `_is_consequence` already rejects those, which is precisely why it is
        reused instead of a second rule being written beside it.
        """
        from intent_engine.founder_brief.build import _is_consequence
        text = (text or "").strip()
        if not text or reads_as_taxonomy(text):
            return ""
        return text if _is_consequence(text) else ""

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
    # BUILT FIRST, SHOWN AFTER THE DECISION.
    #
    # This slide is the company's own copy, honestly labelled -- on the live
    # Palantir deck it opened with "At Palantir, we believe that with good
    # data and the right software, institutions can solve hard problems and
    # change the world for the better." Someone walking a room through this
    # deck should not spend their first slide on a values statement, so the
    # deck opens on the reading and the decision, and this becomes context a
    # reader reaches once they know why it matters. It is still built here
    # because it must claim its bullets before the market slide does.
    identity_slide = _slide("company", f"{company} in one minute",
                            identity_bullets[:3],
                            note="From the company's own public pages.")

    # 2. Central strategic view. `thesis["view"]` and `thesis["transition"]`
    #    are the pattern library's own sentences with the company name
    #    substituted in -- the exact source removed from the full analysis's
    #    _central_claim. "Huggingface appears to be absorbing adjacent tools
    #    until the work lives inside it" is a slide a reader cannot check, and
    #    it reads identically for Notion, Linear or Atlassian.
    view_bullets = []
    if _concrete(thesis.get("view")):
        view_bullets.append(_bullet(thesis["view"]))
    if _concrete(thesis.get("transition")):
        view_bullets.append(_bullet(thesis["transition"]))
    # `why_care` is the decision TOPIC, and "Why it matters: whether to keep
    # investing in depth or in adjacency" was the product restating the
    # question as though it were the point. The composed decision goes on its
    # own screens below, where it has room to say what the options are.
    # D17. THE DECK MAY NOT REACH ITS OWN VERDICT ON WHETHER A READING EXISTS.
    #
    # Live on 929a4b9, after the brief and the primary screen had been wired
    # to the contract, this slide still headed itself "The central strategic
    # view" over "What Cloudflare, Inc. has published is not enough to read a
    # strategy from" -- for a run whose X-Ray was, on the next click, giving a
    # supported pricing decision. The deck was the last surface still
    # deciding this for itself.
    #
    # The bullets are NOT rewritten: what this run could establish is a real
    # fact and the deck is entitled to say it. What changes is that the
    # sentence is scoped to this run rather than presented as the state of
    # the world.
    # GATED ON THE REFUSAL FLAG, NOT ON EMPTINESS. The first version of this
    # asked whether the thesis had no concrete view -- and the refusal
    # sentence IS the view ("What Cloudflare, Inc. has published is not enough
    # to read a strategy from"), so `_concrete` was true, the guard never
    # fired, and the deck kept denying a reading the X-Ray asserted. The
    # producer already flags this case; asking it is what the fix should have
    # done in the first place.
    if (contract is not None and getattr(contract, "reading_exists", False)
            and thesis.get("view_withheld")):
        view_bullets = [_bullet(
            f"A supported reading of {company} exists and is set out on the "
            f"Executive X-Ray."),
            _bullet(getattr(contract, "run_contribution", "") or
                    "This run did not add enough independent evidence to "
                    "strengthen it.")]
    slides.append(_slide("view", "The central strategic view", view_bullets,
                         kind="thesis"))

    # THE DECISION, AND THE SPARSE CASE THIS DECK EXISTS FOR.
    #
    # Measured on the Sentry-shaped fallback: with the library's sentences
    # filtered out, the whole deck came to "We are helping the community work
    # together." and "Built from 5 company owned source(s)." -- a marketing
    # quote and a source count. Neither is intelligence, and a reader given
    # those two lines has been told nothing at all.
    #
    # What the run DOES have, even then, is the honest bounded state: what it
    # verified, what it cannot conclude from that, and the one check that
    # would move it. That is a smaller claim than a strategy and it is a real
    # one, so it is what the screens below carry.
    from intent_engine.strategic_intelligence.decision import decision_of
    composed_decision = decision_of(r)
    shown_here = [b["text"] for s in slides if s for b in s["bullets"]]
    if composed_decision.is_ready:
        # The headline names the mechanism when the option labels are generic,
        # so the mechanism line below it would be the same sentence twice.
        # Compared in FULL. The headline appends the mechanism to labels that
        # are already a sentence long, so its 120-character identity is
        # truncated well before the part being looked for -- and the deployed
        # decision screen printed the mechanism twice, the second time under
        # the label "The mechanism:".
        mechanism = ("" if _identity(composed_decision.mechanism, 0) in
                     _identity(composed_decision.headline, 0)
                     else composed_decision.mechanism)
        slides.append(_slide("decision", "The decision this bears on", [
            _bullet(composed_decision.headline, full=True),
            _bullet(_lead("The mechanism: ", mechanism)),
        ], kind="decision"))
        shown_here = [b["text"] for s in slides if s for b in s["bullets"]]
    if composed_decision.readiness != "WITHHELD":
        # No separate headline screen for the bounded state: the headline IS
        # "no option is safe to commit to yet, because...", and the screen
        # below opens with that same sentence. Printed on both, the deck said
        # one thing twice and called it two screens.
        slides.extend(_decision_detail_slides(
            composed_decision.as_dict(), already_shown=shown_here))

    # Context, now that the reader knows what it is context FOR.
    if identity_slide:
        slides.append(identity_slide)

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
    # A hypothesis "title" IS a pattern name -- the library's label for the
    # shape, not a finding about this company. Dropped rather than reworded;
    # the surprises and the published investor material below are real.
    signal_bullets = [
        _bullet(h.get("title", "") or h.get("statement", ""),
                evidence=h.get("strongest_support_ids", []))
        for h in meaningful_items(r.get("hypotheses", []), key="title")
        if _concrete(h.get("title", "") or h.get("statement", ""))]
    signal_bullets += [
        _bullet(s.get("finding", ""))
        for s in meaningful_items(r.get("surprises", []), key="finding")
        if _concrete(s.get("finding", ""))]
    if not signal_bullets:
        signal_bullets = _document_bullets(documents, {INVESTOR, STRATEGY})
    # "Key strategic signals" is analyst vocabulary for a reader who never
    # asked for a signal. What they are looking at is published evidence.
    slides.append(_slide("signals", "What the company has published",
                         signal_bullets))

    # 6. Main tension or risk. A blind spot's "observed tension" is often the
    #    scaffold statement again, and a vulnerability's exposed layer and
    #    mechanism are the library's own vocabulary for the shape.
    tension_bullets = [
        _bullet(b.get("observed_tension", ""))
        for b in meaningful_items(r.get("blind_spots", []),
                                  key="observed_tension")
        if _concrete(b.get("observed_tension", ""))]
    tension_bullets += [
        _bullet(line) for line in (
            f"Exposed: {v.get('exposed_layer', '')} — {v.get('mechanism', '')}"
            for v in meaningful_items(r.get("vulnerabilities", []),
                                      key="exposed_layer"))
        if _concrete(line)]
    slides.append(_slide("tension", "The main tension", tension_bullets))

    # 7. Opportunity to investigate
    opportunity_bullets = [
        _bullet(o.get("statement", ""))
        for o in meaningful_items(r.get("opportunities", []),
                                  key="statement")
        if _concrete(o.get("statement", ""))]
    slides.append(_slide("opportunity", "An opportunity worth investigating",
                         opportunity_bullets,
                         note="A question to test, not a recommendation."))

    # 8. Questions for leadership. The same filter the brief and the full
    #    analysis apply: "How far toward a system of record do we go?" is the
    #    library asking its own falsification question in a founder's voice.
    # The decision's OWN next check does not belong here. Live on the deployed
    # deck, "Questions for leadership" was one bullet -- "Published pricing
    # that assumes no implementation engagement." -- which slide five had
    # already given as what to do next. A reader paged twice for one sentence.
    # This slide is for what the decision screens did NOT already ask.
    _already_asked = SaidOnce([composed_decision.falsifier,
                               composed_decision.recommended_next_move])
    question_bullets = [
        _bullet(q.get("question", ""))
        for q in meaningful_items(r.get("questions", []), key="question")
        if _concrete(q.get("question", ""))
        and not _already_asked.has(q.get("question", ""))]
    if not question_bullets:
        # Linear's ONLY leadership question was "Customers describing it as a
        # companion to a system of record rather than the record itself" --
        # the pattern's own falsification question. Filtering it left a reader
        # preparing for a meeting with nothing to investigate, and the persona
        # harness said so. It had been passing on that sentence, which means
        # the answer was never really there.
        #
        # The honest replacement is not the library's question reworded, and
        # it is not the limitations list moved up a slide -- that is a
        # disclaimer wearing an action's clothes, and the evidence slide
        # already carries it. It is the run's OWN dated findings, turned back
        # into the thing a founder would go and check. Every one of these
        # names something actually retrieved from this company.
        # Not _lower_first here: these titles OPEN with the company name, and
        # lowercasing turned "Linear pricing publishes its prices" into
        # "linear pricing publishes its prices" in the reader's own deck.
        question_bullets = [
            _bullet(_confirm_question(title))
            for title in (s.get("title", "") for s in
                          meaningful_items(r.get("shifts", []), key="title"))
            if _concrete(title)][:2]
    slides.append(_slide("questions", "Questions for leadership",
                         question_bullets, kind="questions"))

    # 9. Evidence and limitations. Not a content slide — it never counts
    #    toward the minimum, or a deck could reach five on disclaimers alone.
    from intent_engine.strategic_intelligence.editorial import (
        consolidate_limitations, reader_limitations,
    )
    limitation_bullets = [
        _bullet(x) for x in consolidate_limitations(
            r.get("evidence_gaps", []),
            reader_limitations(r.get("quality_findings", [])))]
    # NO SOURCE-COUNT NARRATION. "Built from 9 company owned, 1 executive
    # statement source(s)." is the taxonomy with its underscores rubbed out
    # and a plural the template never resolved, and counting sources tells a
    # reader nothing about whether to trust the reading -- the limitation
    # bullets below say what is actually missing, in English. The counts stay
    # available on the evidence-and-sources page, where a reader who wants
    # provenance goes to look.
    slides.append(_slide("evidence", "Evidence and limitations",
                         limitation_bullets, kind="evidence"))

    return meeting_quality(slides)


#: Slides that carry the decision. They are never dropped for thinness -- a
#: deck missing the choice is not a shorter deck, it is a different one.
# Two kinds of exemption, both learned from a gate failing.
#
# "questions" REFRAMES a finding as something to go and check ("Confirm with
# an independent source: <finding>"), so an identity match against the finding
# is a false positive -- the reader gains the instruction even though they
# have seen the fact.
#
# "wrong" and "watch" restate the falsifier and the checks on purpose. They
# are the only slides that answer "what weakens this", and dropping them for
# restating is how the persona suite lost that answer for a private company.
_LOAD_BEARING = frozenset({"decision", "options", "investigation",
                           "next_move", "today", "evidence", "questions"})
_LOAD_BEARING_IDS = frozenset({"wrong", "watch", "gaps"})


def _load_bearing(slide) -> bool:
    return (slide.get("kind") in _LOAD_BEARING
            or slide.get("id") in _LOAD_BEARING_IDS)

def meeting_quality(slides) -> list:
    """Drop the slides a meeting cannot use. Slides are OPTIONAL now.

    The scrollable narrative is the comprehension path, so this deck no longer
    has to reach a slide count -- it has to be worth paging through. Measured
    on the deployed Palantir deck, ten slides included:

        "Palantir Technologies in one minute"   three lines of the company's
                                                own marketing copy
        "What the company has published"        a blog index blurb and
                                                "Weighted-average shares of
                                                common stock outstanding used
                                                in computing earnings per
                                                share..."
        "Questions for leadership"              one bullet

    None of those changes a decision, and a reader who paged to them paid four
    clicks to learn nothing.

    ONE RULE, AND IT IS REPETITION. Two stronger rules were tried against the
    suite and both were wrong. Requiring a finite assertion on every slide
    dropped "Sentry acquired Codecov." -- a dated fact is not a weak slide, it
    is the shortest kind of strong one. A minimum word count dropped the
    Sentry deck's opening insight for the same reason. Terseness is not the
    defect; saying the same thing on a second screen is, and a bullet the deck
    has already shown costs a click and returns nothing.

    A slide left with no fresh bullets is dropped entirely. Load-bearing
    slides keep theirs whatever else has been said, because a deck missing the
    choice is not a shorter deck, it is a different one.
    """
    present = [s for s in slides if s]
    # WHICH SLIDE YIELDS MATTERS AS MUCH AS THE RULE.
    #
    # "<Company> in one minute" is built from whatever company-owned text was
    # retrieved first, so it claimed the product descriptions before the
    # products-and-market slide could -- and deduplicating in document order
    # then took Foundry, Gotham and AIP off the deck entirely, which a golden
    # gate caught. The weakest slide is the one that gives way, so it is
    # resolved LAST. Output order is unchanged; only claim order is.
    order = sorted(range(len(present)),
                   key=lambda i: present[i].get("id") == "company")
    said, dropped, edited = SaidOnce(), set(), {}
    for i in order:
        slide = present[i]
        texts = [b.get("text", "") for b in slide.get("bullets", ())]
        if _load_bearing(slide):
            for text in texts:
                said.remember(text)
            continue
        fresh = [t for t in texts if t and not said.has(t)]
        if not fresh:
            dropped.add(i)
            continue
        edited[i] = [b for b in slide.get("bullets", ())
                     if b.get("text") in fresh]
        for text in fresh:
            said.remember(text)
    return [dict(s, bullets=edited[i]) if i in edited else s
            for i, s in enumerate(present) if i not in dropped]


def meaningful_slide_count(slides) -> int:
    """Content slides only. The evidence slide is real and useful and is still
    not a finding, so it cannot help a thin deck reach the floor."""
    return sum(1 for s in slides if s["kind"] != "evidence")


def deck_is_presentable(slides) -> bool:
    return meaningful_slide_count(slides) >= MIN_MEANINGFUL_SLIDES


_CSS = """
<style>
/* TWO KINDS OF BORDER, TWO TOKENS. `--line` drew the slide frame, the meta
   rule AND the edge of every control — so the one value had to satisfy both a
   decorative divider (no WCAG floor) and an interactive boundary (1.4.11 asks
   3:1). It was tuned as a divider, and the controls inherited that: measured
   on the deployed Palantir deck at 485ec4b, in light mode, the slide nav, the
   follow-up question button and the numbered dots all rendered #d1d5db at
   1.47:1. (Labels are described rather than quoted here: this stylesheet is
   inlined into the page, comments and all.)
   Darkening `--line` would have fixed the controls by making every hairline
   divider heavy, which is a different design applied silently. So the
   interactive edge gets its own token; separators keep theirs. Dark mode
   already had two values for this and only needed the name. */
.deck{--ink:#111827;--muted:#4b5563;--line:#d1d5db;--ctl:#888aa4;--bg:#ffffff;
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
background:var(--panel);padding:24px 26px}
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
border-radius:9px;border:1px solid var(--ctl);background:#fff;
color:var(--ink);cursor:pointer}
.deck .nav a.primary{background:var(--accent);color:var(--accent-ink);
border-color:var(--accent)}
.deck .nav a:focus-visible,.deck .act a:focus-visible,
.deck .dots a:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.deck .count{color:var(--muted);font-size:.86rem;font-variant-numeric:tabular-nums}
.deck .dots{display:flex;gap:6px;flex-wrap:wrap;margin-left:auto}
.deck .dots a{width:26px;height:26px;display:grid;place-items:center;
border-radius:50%;border:1px solid var(--ctl);font-size:.72rem;
text-decoration:none;color:var(--muted);background:#fff}
.deck .act{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.deck .cites{margin-top:14px}
.deck .cites summary{cursor:pointer;color:var(--accent);font-size:.86rem;
font-weight:600}
.deck .cites li{font-size:.84rem;color:var(--muted);margin:.3rem 0}
.deck .meta{color:var(--muted);font-size:.8rem;margin-top:18px;
border-top:1px solid var(--line);padding-top:10px}
@media (max-width:600px){
.deck{padding:4px 10px 24px}.deck .stage{padding:18px 16px}
.deck h2{font-size:1.25rem}.deck li{font-size:1rem}
.deck .dots{margin-left:0;width:100%}}
@media print{
.deck .slide{display:block!important;page-break-after:always;margin-bottom:20px}
.deck .bar,.deck .act,.deck .dots{display:none!important}
.deck .stage{border:none;background:none}
.deck .cites[open],.deck .cites{display:block}}
@media (prefers-color-scheme:dark){
.deck{--ink:#f3f4f6;--muted:#c3cad6;--line:#3a4454;--ctl:#606e88;--bg:#0f141c;
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
