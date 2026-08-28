"""Q&A answered from the SHARED founder intelligence object.

THE SPLIT THIS CLOSES
---------------------
Q&A independently re-interpreted the deterministic report. Two interpreters over
one report is two products: the brief could say the evidence is thin while the
assistant answered with confidence, and both were "correct" according to their
own path. A founder who reads one and asks the other gets contradictions and no
way to tell which to trust.

So this does NOT reason. It takes the answer text the existing conversation
engine produced and frames it with the shared object's implication, decision,
confidence and limitations. One interpretation, five surfaces.

    DIRECT ANSWER            from the existing conversation engine
    SO WHAT                  from the shared insight
    DECISION AFFECTED        from the shared insight
    EVIDENCE                 the shared insight's evidence ids
    WHAT COULD CHANGE IT     the shared insight's next check + limitations

THE REFUSAL THAT MATTERS
------------------------
When the primary experience WITHHELD a strategic reading -- sparse companies,
marketing-only sites -- the assistant must not supply one. That is the single
easiest way for this product to become dishonest: the report says "not enough
evidence", the user asks "but what do you think?", and a chatty model obliges.
`withheld` short-circuits every strategic intent to a refusal that still helps.
"""
from __future__ import annotations

import re
import dataclasses
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from intent_engine.external_intel import evidence_trust as _ET
from intent_engine.founder_brief.consistency import _looks_strategic
from intent_engine.founder_brief.contract import INTERNAL_VOCABULARY

# Questions that ask for a strategic conclusion rather than a fact.
_STRATEGIC_INTENT = ("what do you think", "what is the main point",
                     "main point", "so what", "what should", "why does it "
                     "matter", "what is the strategy", "what is going on",
                     "your view", "conclusion", "is it working")

# Questions asking which evidence carries the claim.
_EVIDENCE_INTENT = ("what evidence", "what is this based on", "strongest",
                    "weakest", "without that source", "how do you know",
                    "verified fact or", "fact or interpretation")


# ===========================================================================
# THE INTENT ROUTER — D28(b)
#
# Q&A had exactly TWO intents: _STRATEGIC_INTENT and _EVIDENCE_INTENT. Risk,
# uncertainty, falsifier, provenance, independence, search coverage, history,
# competitor response and monitoring had no intent at all, so every one of
# them fell to a single generic fallback. That is why, live on 5e2b625,
# "Biggest risk?", "What proves this wrong?" and "Show me the source. Is it
# independent?" returned the identical paragraph: not a branch to repair, a
# router that did not exist.
#
# Each row names ONE canonical field on the composed decision -- the same
# object the X-Ray renders -- and ONE sentence for when that field is empty.
# Q&A is a projection: it may explain at more length than the X-Ray, and it
# may not reach a different answer.
#
# THE ABSENCE COPY IS PER-INTENT ON PURPOSE. A universal "there is not enough
# public evidence" is what made three different questions indistinguishable;
# "no falsifier has been recorded" and "no source supports that" are different
# facts and a reader is entitled to know which one they hit.
# ===========================================================================
INTENT_ROUTES = (
    ("biggest_risk",
     ("biggest risk", "main risk", "what is the risk", "what's the risk",
      "greatest risk", "key risk"),
     "key_risk",
     "No company-specific risk cleared the evidence bar in this run."),
    ("biggest_uncertainty",
     ("biggest uncertainty", "most uncertain", "what is uncertain",
      "greatest uncertainty", "cannot measure", "can you not measure",
      "can't you measure"),
     "information_gaps",
     "No open uncertainty has been recorded for this company."),
    ("falsifier",
     # "prove this wrong" without the s: the board question is "What WOULD
     # prove this wrong?" and the marker required "proveS". One character,
     # and the question fell to the catch-all for every company.
     ("prove this wrong", "proves this wrong", "prove you wrong",
      "proves you wrong", "falsif", "what would change your mind",
      "kill switch"),
     "falsifier",
     "No falsifier has been established for this reading yet."),
    ("history",
     ("historically", "history", "past", "replay", "hindsight"),
     "economic_history",
     "No valid historical replay is available for this company yet."),
    ("what_changed",
     ("what changed", "changed your mind", "what held", "since last",
      "did you learn", "what did the system learn"),
     "second_iteration",
     "Nothing has been compared against an earlier reading yet."),
    ("competitor",
     ("competitor", "rival", "competition", "what could they do"),
     "competitors",
     "No competitor has been selected for this company from the evidence."),
    ("monitoring",
     ("monitor next", "measure next", "what should we monitor",
      "what should we measure", "watch next", "check next", "monday"),
     "monitoring",
     "Nothing is currently preregistered to watch for this company."),
    ("recommendation",
     ("what should we do", "what should i do", "what should management do",
      "what should they do", "what would you tell the board",
      "tell the board", "recommend", "next move"),
     "recommended_next_move",
     "No action is put forward for this company from this run."),
    # THE EIGHT THAT HAD NO ROUTE.
    #
    # MEASURED across all eight Batch-A companies on one SHA: of the ten
    # board questions this programme asks, only TWO reached the router.
    # "What's the biggest risk?" and "Who's the real competitor?" routed;
    # the other eight fell to the strategic catch-all — which answers from
    # the matched pattern's own text, so two companies on one pattern gave
    # the same answer to all eight, and a company whose run concluded
    # nothing gave a REFUSAL to all eight while its own introduction showed
    # a Bounded read with a real central question.
    #
    # One router gap, two collapse clusters and one contradiction. The
    # questions were being asked of a surface that had no idea what they
    # meant.
    ("why_now",
     ("why now", "why this now", "why is now", "timing"),
     "why_this_question",
     "Nothing in the record makes this urgent rather than important."),
    ("market_belief",
     ("market believe", "market expect", "consensus", "priced in",
      "what does the market"),
     "expectations",
     "No market expectation has been established for this company."),
    ("weakest_assumption",
     ("weakest assumption", "weakest link", "most fragile",
      "shakiest", "what is assumed"),
     "assumptions",
     "No assumption has been isolated as the weakest in this reading."),
    # THE ROUTE POINTED AT THE WRONG OBJECT. "What could not be true?" was
    # answered from `adversary`, which is the competitor's response ladder --
    # a different question with a different producer. There was no impossible
    # hypothesis to point at, so the route was aimed at the nearest field
    # that existed; §5 built the producer, and this now reads it.
    ("impossible_hypothesis",
     ("impossible hypothesis", "impossible", "what could not be true",
      "heretical", "what would surprise", "what are we not considering"),
     "impossible_hypotheses",
     "No heretical reading was put forward for this company: these are "
     "derived from its measured economics, and too little of that could be "
     "read from its own filings to support one."),
    # THE ADVERSARY HAD NO ROUTE OF ITS OWN once the heresy took this field.
    ("adversary",
     ("what would they do", "how would they respond", "competitor respond",
      "adversary", "if we move", "rival respond"),
     "adversary",
     "No adversarial reading was produced: it starts from a rival, and none "
     "was established for this company from the published record."),
)


def intent_of(question: str) -> str:
    """Which canonical category this question asks for, or "".

    Ordered, first match wins, because "what should we monitor next" contains
    both a monitoring marker and a recommendation marker and the specific one
    is listed first.
    """
    low = (question or "").lower()
    for name, markers, _field, _absent in INTENT_ROUTES:
        if any(m in low for m in markers):
            return name
    return ""


#: Where the canonical bounded read answers each intent. Consulted only when
#: the run's own decision has nothing in the field -- see `_route_answer`.
_READ_FALLBACK = {
    "falsifier": ("level6_action", "falsifier"),
    "market_belief": ("market_beliefs", ""),
    "weakest_assumption": ("assumption_chain", ""),
    "impossible_hypothesis": ("impossible_hypotheses", ""),
    "adversary": ("adversary", ""),
    "why_now": ("level5_decision", "text"),
    "recommendation": ("level6_action", "action_now"),
    "biggest_uncertainty": ("level6_action", "what_remains_unknown"),
    "biggest_risk": ("level6_action", "what_remains_unknown"),
    "monitoring": ("level7_monitoring", ""),
    "competitor": ("level4_competition", ""),
}


def _from_read(name: str, read) -> str:
    """This intent's answer, off the canonical read.

    D31. Measured live: the hostile executive question "What should we
    actually do, and what proves this wrong?" was answered "No falsifier has
    been established for this reading yet." on a run whose own step 1 carried
    a falsifier, an action, an experiment and a kill switch. Q&A was reading
    the RUN's decision, which had established nothing, while every other
    surface had moved to the read composed from the classification and the
    published record.

    That is the same seam that produced D13, D17, D22, D25 and D30, found for
    the sixth time. Q&A still does not decide anything: it projects, and this
    is the object it projects from when the run's own decision is silent.
    """
    if read is None:
        return ""
    # §22. WHO CONTESTS THIS COMPANY IS NOT A STRATEGY, SO IT IS NOT GATED
    # ON ONE.
    #
    # MEASURED LIVE on 0420fb0, 3 of 3 companies. Step 1 named the rivals —
    # "contested directly by banks and brokerage firms" — and one click later
    # this route answered "No competitor has been selected for this company
    # from the evidence." The product named the competitors and then denied
    # having identified any, which is the exact question a chief executive
    # asks first.
    #
    # Two causes, both here. The strategy gate below refused every intent
    # including this one, and a run may identify rivals while honestly
    # withholding a recommendation. And the fallback read only
    # `level4_competition`, which is EMPTY on exactly the runs where step 1
    # falls through to the class-level peers — so the two surfaces were
    # reading different objects. Both now project the ONE competitive state
    # the read carries, with its basis, so this route can no longer contradict
    # the page before it.
    if name == "competitor":
        return _competition_answer(read)
    if not getattr(read, "puts_a_strategy_forward", False):
        return ""
    where = _READ_FALLBACK.get(name)
    if where is None:
        return ""
    holder, field = where
    value = getattr(read, holder, None)
    if field:
        got = getattr(value, field, "") or ""
        return _printable(str(got)) or _render_row(got)
    if holder == "level7_monitoring":
        return "; ".join(s.text for s in (value or ())[:3])
    # THE SAME LEAK, THE OTHER PRODUCER.
    #
    # `or r` and `or weakest` are raw objects. MarketBelief has no
    # `.statement` and no `.text`; Link has no `.text`; BeliefChallenge has
    # neither. So each of these fell through to `str(<dataclass>)` and printed
    # a repr at a board:
    #
    #     MarketBelief(belief_id='mb_7939cefbda', subject_id='Cloudflare,
    #     Inc.', proposition="That Cloudflare, Inc.'s current weakness is a
    #     cyclical trough rather than a structural reset", ...)
    #
    # MEASURED ON THE DEPLOYED FIX. `_route_answer` was repaired and the leak
    # did not move: 3 of 3 answers on 49b6c3a, exactly as on 8397d67. The
    # repaired branch reads the RUN'S DECISION; these three questions are
    # answered from the CANONICAL READ, which is this function. The docstring
    # above already counts five previous appearances of this seam -- D13,
    # D17, D22, D25, D30 -- and this is the same one again.
    #
    # `_render_row` knows these shapes now (proposition, strongest_support,
    # frm/to/because), and `_printable` refuses anything still repr-shaped,
    # so a type nobody has taught it cannot leak here either.
    if holder in ("market_beliefs", "belief_challenges"):
        rows = tuple(value or ())[:2]
        rendered = [t for t in (_render_row(r) for r in rows) if t]
        return "; ".join(rendered)
    if holder == "assumption_chain":
        links = tuple(getattr(value, "links", ()) or ())
        if links:
            weakest = min(links, key=lambda l: getattr(l, "confidence", 1.0)) \
                if all(hasattr(l, "confidence") for l in links) else links[0]
            return _printable(str(getattr(weakest, "text", "") or "")) \
                or _render_row(weakest)
        return (_printable(str(getattr(value, "text", "") or ""))
                or _render_row(value)) if value else ""
    if holder == "level4_competition":
        return "; ".join(
            f"{c.name}: {c.likely_response} Watch {c.signal_to_watch}"
            for c in (value or ())[:2])
    return ""


def _competition_answer(read) -> str:
    """The competitive state, in the words the rest of the product uses.

    Named rivals from the run's own ladder are described in full — who they
    are, how they are likely to respond, what to watch. A class-level basis
    is stated AS a class-level basis, in the same sentence step 1 renders,
    rather than being denied here and asserted there.
    """
    from intent_engine.executive.strategic_read import (
        COMPETITION_FROM_EVIDENCE, competitive_sentence,
    )
    rows = tuple(getattr(read, "level4_competition", ()) or ())
    basis = str(getattr(read, "competitive_basis", "") or "")
    rivals = tuple(getattr(read, "competitive_rivals", ()) or ())
    if rows and basis == COMPETITION_FROM_EVIDENCE:
        return "; ".join(
            f"{c.name}: {c.likely_response} Watch {c.signal_to_watch}"
            for c in rows[:2])
    if not rivals:
        return ""
    return competitive_sentence({"rivals": rivals, "basis": basis})


#: Keys a structured decision row may carry, in the order a reader needs
#: them. Ordered rather than guessed: the first present key is the row's
#: subject, and the rest qualify it.
#: THE VOCABULARY IS PART OF THE FIX, NOT A SEPARATE POLISH STEP.
#:
#: Normalising the dataclasses stopped the repr reaching the reader and then
#: rendered NOTHING, because none of these key names appear on MarketBelief,
#: BeliefChallenge or Link. That trades a leak for an absence on a question
#: whose answer is sitting right there -- which is the failure §24 exists to
#: forbid, arriving through the door that was just opened.
#:
#: So the names the newly-routed producers actually use are named here.
#: `proposition` is the belief itself; `strongest_support` is the case for
#: it; `frm`/`to` are the two ends of a link and read as a subject and its
#: consequence.
#: `hypothesis`/`mechanism` are the heresy's two ends and `action`/`impact`
#: are the adversary move's -- both newly routed here, and a producer whose
#: key names are absent from these tuples renders as NOTHING, which is how a
#: populated list came to answer "no competitor has been selected".
_ROW_SUBJECT_KEYS = ("name", "title", "statement", "text", "label",
                     "question", "summary", "hypothesis", "action",
                     "proposition", "strongest_support", "frm")
_ROW_DETAIL_KEYS = ("likely_response", "signal_to_watch", "why", "reason",
                    "mechanism", "impact",
                    "basis", "detail", "so_what", "plain",
                    "basis_detail", "because", "to")


#: What a Python object looks like when it reaches a reader: a lowercase type
#: name, an open bracket, and a keyword argument. Matched so the product can
#: REFUSE to print one rather than relying on having thought of every type.
_LOOKS_LIKE_A_REPR = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*\((?:[a-z_]+=|\))")


def _as_row(row):
    """A decision row as a dict, whatever shape the producer used.

    MEASURED LIVE on 8397d67, Meta and Cloudflare, on the two questions a
    board cares most about:

        marketbelief(belief_id='mb_f3a52cac10', subject_id='Meta Platforms,
        Inc.', proposition="that ... resumes.", belief_type=...)

    The renderer below recognised dicts and strings. `MarketBelief`,
    `BeliefChallenge` and `Link` are DATACLASS INSTANCES, so every isinstance
    check missed them and `str()` fell through to `repr()`.

    The comment on the list branch in `_route_answer` records this same defect
    being closed once, for rows that were dicts. Nothing taught it about
    objects -- and it could not have been seen until the router repair made
    these eight intents reachable at all, because before that they fell to a
    catch-all that answered from the matched pattern's own text.
    """
    if isinstance(row, dict):
        return row
    if dataclasses.is_dataclass(row) and not isinstance(row, type):
        try:
            return dataclasses.asdict(row)
        except Exception:                                   # noqa: BLE001
            return {k: v for k, v in vars(row).items()
                    if not k.startswith("_")}
    if hasattr(row, "__dict__") and not isinstance(
            row, (str, bytes, int, float, bool)):
        return {k: v for k, v in vars(row).items()
                if not k.startswith("_")}
    return row


def _printable(text: str) -> str:
    """A sentence, or "" when what arrived is an object wearing one.

    A TYPE LIST WOULD HAVE TO BE KEPT UP TO DATE. `_as_row` handles the three
    shapes that exist today; this catches the fourth, whenever somebody adds
    it. Refusing is safe here because every caller falls back to the canonical
    read and then to the absent copy -- a bounded sentence rather than a
    repr.
    """
    body = (text or "").strip()
    return "" if _LOOKS_LIKE_A_REPR.match(body) else body


def _render_row(row) -> str:
    """One structured decision row, as a sentence. "" if it carries nothing."""
    row = _as_row(row)
    if not isinstance(row, dict):
        return _printable(str(row or ""))
    subject = ""
    for key in _ROW_SUBJECT_KEYS:
        subject = str(row.get(key) or "").strip()
        if subject:
            break
    details = []
    for key in _ROW_DETAIL_KEYS:
        value = str(row.get(key) or "").strip()
        if value and value not in details:
            details.append(value)
    if subject and details:
        return f"{subject}: {' '.join(details)}"
    return subject or (details[0] if details else "")


def _render_rows(value, limit: int = 3) -> str:
    """A list of structured rows, rendered. "" when nothing is renderable.

    PRESENT-BUT-UNFORMATTABLE IS NOT ABSENT, AND THIS IS WHERE THE PRODUCT
    SAID IT WAS.
    """
    out = []
    for row in list(value or ())[:limit]:
        text = _render_row(row)
        if text and text not in out:
            out.append(text)
    return "; ".join(out)


#: §22. Economic questions, answered from the canonical economic context and
#: from nothing else. Listed BEFORE the generic router runs, because
#: "what should we monitor next" is answerable from either object and the
#: economic one is the more specific answer when an economic delta exists.
#:
#: WHY THESE ROUTE SEPARATELY. The failure being prevented is a second
#: reasoning universe: Q&A composing an economic explanation out of the report
#: while the brief renders one out of the context object, and the two
#: disagreeing. Every string below is lifted from the context; none is
#: composed here.
ECONOMIC_INTENTS = (
    ("why_changed", ("why did this recommendation change",
                     "why did the recommendation change",
                     "why has this changed", "what changed economically",
                     "why did your recommendation change")),
    ("which_factor", ("which economic factor", "what economic factor",
                      "which factor matters most", "biggest economic",
                      "most important economic")),
    ("economic_evidence", ("what evidence supports it",
                           "what evidence supports that",
                           "evidence for the economic",
                           "where does that economic")),
    ("economic_wrong", ("what could make this wrong",
                        "what would make this wrong",
                        "how could the economic reading be wrong")),
    ("differently", ("differently than", "different from our competitor",
                     "why does this affect us differently",
                     "why us and not")),
    ("economic_monitor", ("what should i monitor next",
                          "what economic", "economic conditions")),
)


def economic_intent_of(question: str) -> str:
    low = (question or "").lower()
    for name, markers in ECONOMIC_INTENTS:
        if any(m in low for m in markers):
            return name
    return ""


def _economic_answer(question: str, econ) -> str:
    """One economic question, answered off the shared context.

    Returns "" when the question is not economic OR when the context has
    nothing that answers it. An empty return falls through to the ordinary
    router, which is right: an invented economic answer is worse than a
    company answer to an economic question.
    """
    if econ is None:
        return ""
    name = economic_intent_of(question)
    if not name:
        return ""
    if not econ.available:
        # §18/§26.12. The honest answer is that there is no economic reading,
        # not a reading composed here to fill the gap.
        return f"{econ.headline()} {econ.reason}".strip()
    if name == "why_changed":
        if not econ.material_decision_delta:
            return f"{econ.headline()} {econ.abstention_reason}".strip()
        c = econ.material_decision_delta[0]
        return (f"{econ.headline()} The change is to "
                f"{c.field.replace('_', ' ')}, and it is there because "
                f"{c.trigger}. The mechanism is: {c.mechanism}")
    if name == "which_factor":
        live = [e for e in econ.company_exposures if e.measured]
        if not live:
            return econ.headline()
        e = live[0]
        return (f"{e.quantity.replace('_', ' ').capitalize()}, through "
                f"{e.channel.replace('_', ' ').lower()}. {e.mechanism} "
                f"The variable it moves here is "
                f"{e.business_variable or e.channel.lower()}.")
    if name == "economic_evidence":
        if not econ.provenance:
            return econ.headline()
        rows = "; ".join(
            f"{p.claim} — {p.source}, {p.as_of}" for p in econ.provenance[:3])
        return (f"Every economic claim here rests on a published series read "
                f"from the shared economic state: {rows}.")
    if name == "economic_wrong":
        if econ.falsifiers:
            return (f"This economic reading would be wrong if "
                    f"{econ.falsifiers[0]}.")
        if econ.abstains:
            return ("The reading here is that the economy does not change "
                    "this recommendation. It would be wrong if a condition "
                    "this company is exposed to moved adversely through a "
                    "channel we have established — none currently does.")
        return econ.headline()
    if name == "differently":
        live = [e for e in econ.company_exposures if e.measured and e.mechanism]
        if not live:
            return ""
        e = live[0]
        return (f"The same condition reaches different businesses through "
                f"different mechanisms. Here it reaches "
                f"{econ.company_id} as: {e.mechanism} A business with a "
                f"different model would be reached through a different "
                f"variable, or not at all — a condition with no established "
                f"mechanism into a business is not reported as an exposure "
                f"for it.")
    if name == "economic_monitor":
        if econ.information_priorities:
            return (f"{econ.information_priorities[0]}. "
                    + (f"Also: {econ.information_priorities[1]}."
                       if len(econ.information_priorities) > 1 else "")).strip()
        return econ.headline()
    return ""


def _route_answer(question: str, decision, read=None) -> tuple:
    """(answer, matched_intent). Reads the composed decision, never invents.

    `decision` is the composed FounderDecision as a dict -- the object the
    X-Ray renders. `read` is the canonical bounded read, consulted ONLY where
    the decision is silent, so a run that concluded nothing of its own cannot
    make Q&A deny what the rest of the product asserts.
    """
    name = intent_of(question)
    if not name:
        return "", name
    if not isinstance(decision, dict):
        return _from_read(name, read), name
    for row_name, _markers, field, absent in INTENT_ROUTES:
        if row_name != name:
            continue
        value = decision.get(field)
        if not value or (isinstance(value, (list, tuple, dict))
                         and not any(value)):
            fallback = _from_read(row_name, read)
            if fallback:
                return fallback, name
        if isinstance(value, dict):
            # economic_history / second_iteration carry their own sentence.
            said = value.get("statement") or value.get("plain") or ""
            return (str(said) or absent), name
        if isinstance(value, (list, tuple)):
            # NORMALISE BEFORE ASKING WHAT SHAPE IT IS. The check below used
            # to decide "structured or not" from the raw members, so a list
            # of dataclasses answered "not structured" and went to the
            # str()-join that printed their reprs.
            value = [_as_row(v) for v in value]
            if value and any(isinstance(v, dict) for v in value):
                # A POPULATED, STRUCTURED LIST IS NOT AN ABSENCE.
                #
                # MEASURED LIVE on 0420fb0, 3 of 3 companies. The composed
                # decision carried competitor ROWS -- {"name": "Huawei
                # Technologies Co", ...} -- and this branch returned "No
                # competitor has been selected for this company from the
                # evidence." while step 1 of the same run named them. The
                # read fallback that would have answered correctly was
                # skipped PRECISELY BECAUSE the data was there: `value` is
                # truthy, so the emptiness check above never fired.
                #
                # The renderer could only join strings, so it treated rows it
                # could not format as nothing at all. That is why it
                # reproduced on three companies with three model classes,
                # three different ladders and three Bounded reads -- it
                # depends on the SHAPE of the decision, not on anything about
                # the company.
                rendered = _render_rows(value)
                if rendered:
                    return rendered, name
                # Still nothing renderable: ask the canonical read before
                # reaching for the absent copy. Refusing here is how a true
                # statement came to look like an honest gap.
                fallback = _from_read(row_name, read)
                return (fallback or absent), name
            items = [t for t in (_printable(str(v)) for v in value) if t]
            if not items:
                return absent, name
            return "; ".join(items[:3]), name
        # A SCALAR CAN BE AN OBJECT TOO. `key_risk` and `falsifier` are
        # strings today; nothing stops the next producer returning a row.
        if not isinstance(value, (str, bytes)):
            rendered = _render_row(value)
            if rendered:
                return rendered, name
        text = _printable(str(value or ""))
        return (text or _from_read(row_name, read) or absent), name
    return "", name


@dataclass
class FounderAnswer:
    """One answer, in the same shape as every other founder-facing surface."""
    question: str
    direct_answer: str
    so_what: str = ""
    decision_affected: str = ""
    evidence_ids: tuple = ()
    what_could_change: str = ""
    confidence: str = ""
    limitations: tuple = ()
    withheld: bool = False
    strongest_evidence: str = ""
    weakest_evidence: str = ""
    fact_or_interpretation: str = ""

    def as_dict(self) -> dict:
        return {"question": self.question, "direct_answer": self.direct_answer,
                "so_what": self.so_what,
                "decision_affected": self.decision_affected,
                "evidence_ids": list(self.evidence_ids),
                "what_could_change": self.what_could_change,
                "confidence": self.confidence,
                "limitations": list(self.limitations),
                "withheld": self.withheld,
                "strongest_evidence": self.strongest_evidence,
                "weakest_evidence": self.weakest_evidence,
                "fact_or_interpretation": self.fact_or_interpretation}


def _intent(question: str, markers) -> bool:
    low = (question or "").lower()
    return any(m in low for m in markers)


def _pattern_grounding(decision) -> str:
    """The sentence from THIS company's filing that qualified its reading.

    MEASURED LIVE on 31e6138. Caterpillar and Exxon Mobil are different
    business-model classes and answered EIGHT OF TEN board questions with the
    identical sentence, because every field of the composed decision is the
    pattern's static text with only the company name substituted —
    `compose_decision`'s own docstring says "nothing here is per-company".

    READ OFF THE DECISION, NOT THE BRIEF. The brief carries a projected
    `FounderInsight`, which has no hypothesis and no mechanism evidence on it
    at all — so this surface never had access to the quote, which is exactly
    why two different filers sounded identical here. The Full Analysis was
    already right: `narrative.py` prints it via `mechanism.because_line`.

    Not folded into the mechanism string either: that duplicated the sentence
    on the surface already showing it and reached this one not at all.
    """
    if not isinstance(decision, dict):
        return str(getattr(decision, "grounded_in", "") or "")
    return str(decision.get("grounded_in") or "")


def answer(question: str, brief, *, engine_answer: str = "",
           observations: Optional[Sequence[dict]] = None,
           trust=None, contract=None, decision=None,
           read=None, econ=None) -> FounderAnswer:
    """Frame an answer using the shared object. Never invents a conclusion.

    `trust` is the CANONICAL standing produced by the market side, not a
    judgement made here. Absent it, this surface may still describe which
    accounts exist — it may not say they confirm each other.
    """
    observations = list(observations or ())
    trust = trust if trust is not None else _ET.UNRATED
    k = brief.key_insight
    # D25. WHETHER A READING EXISTS IS NOT DECIDED HERE.
    #
    # `brief.key_insight is None` measures what THIS RUN could establish, and
    # Q&A used it to refuse outright: live on 8f2ea0c it answered "I am not
    # going to give you a strategic read on this company, because the public
    # evidence does not support one -- the same reason the summary above
    # withheld it" while the X-Ray gave a supported pricing decision and the
    # summary above had stopped withholding. That trailing clause is the
    # tell: it cited a refusal no longer being made.
    #
    # Q&A was the FIFTH surface found deciding this for itself. It keeps
    # everything else it does -- the explanation, the citations, the
    # counter-evidence -- and gives up only the verdict.
    withheld = k is None
    if (contract is not None and getattr(contract, "reading_exists", False)
            and withheld):
        withheld = False
        out_contribution = getattr(contract, "run_contribution", "")
    else:
        out_contribution = ""

    out = FounderAnswer(question=question, direct_answer="",
                        confidence=brief.confidence,
                        limitations=tuple(brief.limitations),
                        withheld=withheld)

    # --- the refusal path ---------------------------------------------------
    # THE SPECIFIC CATEGORY WINS OVER THE CATCH-ALL.
    #
    # _STRATEGIC_INTENT matches on "what should", which catches "what should
    # we do" and "what should we monitor next" alike -- so running it first
    # collapsed a monitoring question onto the recommendation answer. Caught by
    # the distinctness test rather than live, which is the point of having it.
    # §22. THE ECONOMIC ROUTER FIRST, AND ONLY WHERE IT HAS AN ANSWER.
    #
    # Same evidence graph as every other surface: `_economic_answer` reads the
    # canonical `FounderEconomicContext` and composes nothing. It returns ""
    # when the context cannot answer, so an economic question about a company
    # with no economic reading still reaches the ordinary router rather than
    # being answered out of thin air -- §26.12.
    _econ_routed = _economic_answer(question, econ)
    if _econ_routed:
        out.direct_answer = _econ_routed
        if econ is not None and econ.material_decision_delta:
            out.decision_affected = (
                econ.material_decision_delta[0].why_material)
        if econ is not None and econ.provenance:
            out.strongest_evidence = (
                f"{econ.provenance[0].claim} ({econ.provenance[0].source}, "
                f"{econ.provenance[0].as_of})")
        return out

    _routed, _matched = _route_answer(question, decision, read)
    if _routed:
        out.direct_answer = _routed
        if contract is not None and getattr(contract, "run_contribution", ""):
            out.so_what = contract.run_contribution
        # A ROUTED ANSWER IS STILL THIS COMPANY'S ANSWER. This path returns
        # early, and when the router grew to cover all ten board questions
        # that early return started skipping the grounding — so the very
        # answers that had just stopped collapsing lost the sentence saying
        # whose filing made them true. Caught by the test that pins it.
        if not out.strongest_evidence:
            grounding = _pattern_grounding(decision)
            if grounding:
                out.strongest_evidence = grounding
        return out

    if out_contribution and _intent(question, _STRATEGIC_INTENT):
        # The contract holds a reading this run did not strengthen. Say both
        # facts; refusing would contradict the X-Ray, and claiming this run
        # established it would be the opposite lie.
        out.direct_answer = (
            f"A supported reading of "
            f"{getattr(contract, 'company', '') or 'this company'} exists and "
            f"is set out on the Executive X-Ray.")
        out.so_what = out_contribution
        return out
    if withheld and _intent(question, _STRATEGIC_INTENT):
        out.direct_answer = (
            "I am not going to give you a strategic read on this company, "
            "because the public evidence does not support one — the same "
            "reason the summary above withheld it.")
        out.so_what = (
            "What can be established is what a customer, partner or investor "
            "can verify from outside. That is a different and smaller "
            "question, and it is answerable.")
        out.decision_affected = (
            "Whether to publish more verifiable proof, or accept that every "
            "buyer conversation starts from zero.")
        out.what_could_change = (
            "Independent coverage, dated customer evidence, or public pricing "
            "would all move this.")
        return out

    # THE ENGINE STILL HOLDS THE READING THE BRIEF REFUSED.
    #
    # `answer_strategic` answers from the strategic report, which keeps its
    # hypothesis whether or not the brief judged the evidence strong enough to
    # assert it. So an ordinary, non-strategic question -- "what does this
    # company do?" -- was enough to carry that hypothesis onto the page under
    # a brief that had just said no conclusion was being asserted. The refusal
    # above only inspects the QUESTION; the reading arrives in the ANSWER.
    if withheld and _looks_strategic(engine_answer):
        engine_answer = ""

    # D28. THE FALLBACK WAS ONE SENTENCE FOR EVERY QUESTION.
    #
    # Measured live on a28549c: "Biggest risk?", "What proves this wrong?",
    # "Did you find none or fail to find it?" and "Show me the source. Is it
    # independent?" all returned "There is not enough public evidence to
    # answer that confidently." Four different questions, one canned answer,
    # on a run whose X-Ray asserted a supported pricing decision.
    #
    # D25 fixed only the branch gated on _STRATEGIC_INTENT -- the case that
    # was tested. Everything that did not match that pattern fell through to
    # here and still contradicted the contract. Same defect, one branch over.
    _fallback = "There is not enough public evidence to answer that confidently."
    if k is None and contract is not None and getattr(
            contract, "reading_exists", False):
        _fallback = (
            f"A supported reading of "
            f"{getattr(contract, 'company', '') or 'this company'} exists and "
            f"is set out on the Executive X-Ray. "
            + (getattr(contract, "run_contribution", "") or
               "This run did not add enough independent evidence to "
               "strengthen it.")
            + " This particular question is not answerable from what this run "
              "retrieved.")
    out.direct_answer = _plain(engine_answer) or (k.fact if k else _fallback)

    if k:
        out.so_what = k.so_what
        out.decision_affected = k.decision
        out.evidence_ids = tuple(k.evidence_ids)
        out.what_could_change = k.watch
        out.confidence = k.confidence or brief.confidence

    # --- evidence questions -------------------------------------------------
    if _intent(question, _EVIDENCE_INTENT):
        independent = [o for o in observations
                       if o.get("source_class") not in
                       ("company_owned", "executive_statement", None, "")]
        company = [o for o in observations
                   if o.get("source_class") in ("company_owned",
                                                "executive_statement")]
        out.strongest_evidence = _describe(
            independent[0] if independent else None,
            "No independent source was found; everything rests on the "
            "company's own material.")
        out.weakest_evidence = _describe(
            company[0] if company else None,
            "No company-stated material is being relied on.")
        # Source-ablation: would the reading survive without the best source?
        if "without" in (question or "").lower():
            out.direct_answer = _ablation(trust, independent)
        # The standing earns a limitation on the surface that asked about
        # evidence, whatever the question's exact wording. A reader who asks
        # how strong the evidence is has asked the one question the standing
        # answers, and answering it without the caveat is the omission.
        _caveat = _ET.limitation(trust)
        if _caveat and _caveat not in out.limitations:
            out.limitations = tuple(out.limitations) + (_caveat,)
        out.fact_or_interpretation = (
            "Interpretation. The dated events are verified facts; the reading "
            "of what they add up to is an inference, and it is labelled as "
            "one." if k else "Verified fact only — no interpretation is "
                             "offered because the evidence does not support "
                             "one.")
    # WHOSE FILING MADE THIS TRUE. Two companies matching one pattern receive
    # the same pattern text, so without this the answer is identical for both
    # — measured on Caterpillar and Exxon, 8 of 10 board questions. The quote
    # is only added where the answer does not already carry evidence of its
    # own, so an evidence question keeps the source it chose.
    if not out.strongest_evidence:
        grounding = _pattern_grounding(decision)
        if grounding:
            out.strongest_evidence = grounding
    return out


def _ablation(trust, accounts: Sequence[dict]) -> str:
    """Would the reading survive without its strongest source?

    THE DEFECT THIS CLOSES
    ----------------------
    This answered `len(independent) >= 2`, where `independent` was every row
    whose publisher was not the company, and reported the figure to a founder
    as "N independent source(s) support this". Publisher class is not source
    dependence: three outlets rewriting one press release are three non-company
    rows and one observation. So the surface that exists to say how strong the
    evidence is was the surface inflating it — and the answer it gave for a
    dependent cluster ("still leaves independent corroboration") also leaked a
    banned internal term straight onto the page, because it was written after
    `_plain` had already run.

    Trust is READ, never computed here. Where the market side established a
    standing, that standing answers. Where it did not, the honest answer names
    the accounts and refuses the independence claim rather than guessing it.
    """
    n = len(accounts)
    if not n:
        return ("No — removing the strongest one leaves it resting on the "
                "company describing itself.")

    if trust.known:
        if trust.standing == _ET.CONFLICTED:
            return ("No — public sources disagree on this point, so it "
                    "cannot carry a confident conclusion on its own.")
        if trust.standing == _ET.DEPENDENT_REREPORTING:
            return ("No — several reports repeat the same underlying "
                    "announcement, so removing the strongest one does not "
                    "leave a separate account behind it.")
        if trust.may_claim_independence and trust.independent_support >= 2:
            return ("Probably — separate sources support this on their own, "
                    "so removing the strongest one still leaves a second "
                    "account standing.")
        # SINGLE_SOURCE, PARTIALLY_INDEPENDENT, or independence that was
        # established but thin: one account carries it either way.
        return ("No — this rests on a single underlying account, so removing "
                "it removes the basis for the reading.")

    # UNRATED. The count is reportable; independence is not, because nobody
    # established it. Saying "N independent sources" here is the inflation.
    other = n - 1
    tail = (f"that leaves {other} other account(s), though whether they "
            "confirm each other on their own was not established."
            if other else "there is no second account behind it.")
    return f"Not established — {tail}"


def _describe(observation, fallback: str) -> str:
    if not observation:
        return fallback
    text = " ".join(str(observation.get("text")
                        or observation.get("summary") or "").split())
    when = str(observation.get("date") or "")[:10]
    return f"{when + ': ' if when else ''}{text[:180]}"


def _plain(text: str) -> str:
    """Strip internal vocabulary from an engine answer before a founder sees
    it. The conversation engine predates the founder-language rules."""
    out = " ".join((text or "").split())
    for term in INTERNAL_VOCABULARY:
        out = re.sub(re.escape(term), "", out, flags=re.I)
    return " ".join(out.split())


def leaked_terms(answer_obj) -> List[str]:
    fields = " ".join([answer_obj.direct_answer, answer_obj.so_what,
                       answer_obj.decision_affected,
                       answer_obj.what_could_change]).lower()
    return [t for t in INTERNAL_VOCABULARY if t in fields]
