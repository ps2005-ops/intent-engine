"""The executive brief — the thing a busy reader actually reads.

WHY THIS LAYER EXISTS
---------------------
The full report is not wrong; it is unreadable at the moment it matters. The
tester opened a result fifteen minutes before a meeting and met eleven sections,
four hypothesis cards, a source library and a technical appendix. Everything
needed to answer "what should I know before I walk in?" was in there somewhere,
which is not the same as being answerable.

Depth was never the problem. The default was. A report that must be mined is a
report that gets skimmed, and a skimmed report is where a reader picks up the
first confident sentence they see — which is exactly how a pricing paragraph
became somebody's answer to "what does this company do?".

THE BUDGET IS THE DESIGN
------------------------
250–500 words, and the ceiling is enforced rather than encouraged. An
unenforced word budget is a preference, and preferences lose to the pressure to
include one more caveat. Everything below the budget survives on merit: one
thesis, three signals, one counterpoint, one tension, one decision, three
questions, one limitation. Nothing gets a second slot.

Trimming happens at sentence boundaries and never mid-clause, because half a
qualification reads as a stronger claim than the whole one — the opposite of
what trimming is for.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from intent_engine.strategic_intelligence.editorial import (
    consolidate_limitations, deduplicate, is_meaningful, meaningful_items,
)

BRIEF_VERSION = "si_brief.v1"

MIN_WORDS = 250
MAX_WORDS = 500
SIGNAL_COUNT = 3
QUESTION_COUNT = 3

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _words(text: str) -> int:
    return len((text or "").split())


def fit_to_words(text: str, max_words: int) -> str:
    """Trim to a whole number of sentences within the budget.

    Never mid-clause: "revenue grew, although churn in the SMB tier" reads as a
    stronger claim than the complete sentence it came from, which is precisely
    backwards for a trim whose purpose is to avoid overstating.
    """
    text = (text or "").strip()
    if _words(text) <= max_words:
        return text
    kept, used = [], 0
    for sentence in _SENTENCE.split(text):
        cost = _words(sentence)
        if used + cost > max_words:
            break
        kept.append(sentence)
        used += cost
    if kept:
        return " ".join(kept).strip()
    # A single sentence longer than the whole budget: cut at a word boundary
    # and mark the cut, rather than silently presenting a fragment as complete.
    return " ".join(text.split()[:max_words]).rstrip(",;:") + "…"


MAX_HEADLINE_WORDS = 60


@dataclass
class Headline:
    """The whole answer for a reader who will not scroll.

    Not a truncation of the brief — a truncated brief is a brief the reader
    finished in the wrong place. This is the smallest complete unit: what the
    company does, what we think is happening, and how much to trust it. Sixty
    words, about fifteen seconds.

    It creates no claim of its own. Every line is drawn from something the
    brief already says, so a reader who stops here and a reader who reads on
    have not been told different things.
    """
    does: str = ""
    view: str = ""
    confidence: str = ""

    @property
    def word_count(self) -> int:
        return sum(_words(p) for p in (self.does, self.view, self.confidence))

    def as_dict(self) -> dict:
        return {"does": self.does, "view": self.view,
                "confidence": self.confidence,
                "word_count": self.word_count}


@dataclass
class ExecutiveBrief:
    company: str
    thesis: str = ""
    signals: list = field(default_factory=list)
    counterpoint: str = ""
    tension: str = ""
    decision: str = ""
    questions: list = field(default_factory=list)
    limitation: str = ""
    as_of: str = ""
    analysis_version: str = ""
    brief_version: str = BRIEF_VERSION
    # True when the evidence supported no hypothesis and the brief says so
    # rather than leaving the most prominent line on the page blank.
    view_withheld: bool = False
    headline: Headline = field(default_factory=Headline)

    @property
    def word_count(self) -> int:
        parts = [self.thesis, self.counterpoint, self.tension, self.decision,
                 self.limitation]
        parts += [s.get("text", "") for s in self.signals]
        parts += list(self.questions)
        return sum(_words(p) for p in parts)

    @property
    def within_budget(self) -> bool:
        return self.word_count <= MAX_WORDS

    def as_dict(self) -> dict:
        return {"company": self.company, "thesis": self.thesis,
                "signals": self.signals, "counterpoint": self.counterpoint,
                "tension": self.tension, "decision": self.decision,
                "questions": self.questions, "limitation": self.limitation,
                "as_of": self.as_of,
                "analysis_version": self.analysis_version,
                "brief_version": self.brief_version,
                "view_withheld": self.view_withheld,
                "headline": self.headline.as_dict(),
                "word_count": self.word_count}


def _first(items, *keys, default=""):
    """The first meaningful value under any of `keys`, across `items`."""
    for item in items or ():
        for key in keys:
            value = item.get(key) if isinstance(item, dict) else item
            if is_meaningful(value):
                return str(value).strip()
    return default


# Verbs a company uses when it is saying what it actually does.
_DOES_VERBS = (" is a ", " is the ", " provides ", " builds ", " makes ",
               " sells ", " offers ", " serves ", " helps ", " powers ",
               " delivers ", " runs ", " operates ", " supplies ",
               " reconciles ", " combines ", " specialises ", " specializes ",
               " lets ", " enables ",
               # first person, which is how a company writes its own homepage
               " we build ", " we make ", " we provide ", " we help ",
               " we operate ", " we sell ", " we serve ")

# Sentences about corporate STATUS. "Notion is a privately held software
# company" scores well on every structural signal and tells a reader nothing
# about what Notion is for.
_STATUS_ONLY = ("privately held", "publicly traded", "publicly listed",
                "do not publish", "does not publish", "no financial results",
                "wholly owned subsidiary", "limited company")

# Openings that are about the company's feelings or its founding, not its
# business. Both are true and neither answers the question a stranger asked.
_NOT_A_DESCRIPTION = ("our mission", "our vision", "our goal", "we believe",
                      "our values", "our story", "our purpose")
_HISTORY = ("was founded", "founded in", "opened in", "was started",
            "started in", "began in")


def _describes_the_business(sentence: str, company: str) -> int:
    """How well one sentence answers "what does this company do".

    Scored rather than taken in order, because the first sentence of an
    identity page is as often a mission statement or a founding date as it is
    a description. "Our mission is to make commerce better for everyone" and
    "the practice opened in 2014 and is owned by the two dentists who work in
    it" are both true, and a reader who has never heard of the company learns
    nothing from either.
    """
    text = " " + " ".join((sentence or "").split()).lower() + " "
    if _words(sentence) < 6:
        return 0
    score = 1
    has_verb = any(v in text for v in _DOES_VERBS)
    first_word = (company or "").split()[0].lower() if company else ""
    names_company = bool(first_word) and first_word in text
    if has_verb:
        score += 2
    if names_company and has_verb:
        score += 2
    if any(text.lstrip().startswith(" " + m) or f" {m}" in text[:24]
           for m in _NOT_A_DESCRIPTION):
        score -= 4
    if any(h in text for h in _HISTORY) and not has_verb:
        score -= 2
    if any(s in text for s in _STATUS_ONLY):
        score -= 3
    # "Shopify Plus serves enterprise merchants…" is a sentence about a
    # product line wearing the company's name. A capitalised word immediately
    # after the company name is the tell.
    if names_company and _is_sub_brand(sentence, company):
        score -= 2
    return score


def _is_sub_brand(sentence: str, company: str) -> bool:
    words = (sentence or "").split()
    first = (company or "").split()[0] if company else ""
    if not first or len(words) < 2:
        return False
    if words[0].strip(",.").lower() != first.lower():
        return False
    nxt = words[1].strip(",.:;")
    return bool(nxt) and nxt[:1].isupper() and nxt.lower() not in ("the", "is")


def _without_leading_title(document) -> str:
    """The page's prose, without the heading the extractor kept in front of it.

    Extraction concatenates the h1 with the body, so the first sentence of an
    identity page reads "About Shopify Our mission is to make commerce better
    for everyone." Two sentences welded together, and the first one is
    navigation.
    """
    text = " ".join((document.get("text_content") or "").split())
    title = " ".join((document.get("title") or "").split())
    if title and text.lower().startswith(title.lower()):
        text = text[len(title):].lstrip(" -—:·|")
    return text


def _what_it_does(company, report, documents) -> str:
    """One sentence a reader who has never heard of this company can use.

    The thesis answers "what is changing", which is a different question and
    useless to someone who does not yet know what the company is. A reader
    arriving at "Shopify appears to be expanding from a smaller-customer wedge
    toward enterprise buyers" with no prior knowledge learns nothing.

    Taken from the company's own description of itself, because for this one
    question the company IS the authority — what it sells is not a contested
    claim.
    """
    from intent_engine.company_ingestion.coverage import (
        IDENTITY, PRODUCT, family_of,
    )
    best, best_score = "", 0
    for document in documents or ():
        if document.get("retrieval_status") != "OK":
            continue
        family = family_of(document)
        if family not in (IDENTITY, PRODUCT):
            continue
        text = _without_leading_title(document)
        # Only the opening of a page — a description that has not appeared by
        # the fourth sentence is not the page's description.
        for sentence in _SENTENCE.split(text)[:4]:
            score = _describes_the_business(sentence, company)
            if family is PRODUCT:
                score -= 1          # what it sells, one step from what it is
            if score > best_score:
                best, best_score = sentence, score
    if best:
        return fit_to_words(best, 34)
    # No identity page. Say that rather than inventing a description; a reader
    # can tell the difference between "we did not find this" and silence.
    return (f"What {company or 'this company'} does is not described on any "
            f"page we could retrieve.")


def _build_headline(company, report, brief, documents) -> Headline:
    r = report.as_dict() if hasattr(report, "as_dict") else (report or {})
    hypotheses = r.get("hypotheses") or []
    confidence = str((hypotheses[0].get("confidence") if hypotheses else "")
                     or "").strip().lower()
    provenance = str((hypotheses[0].get("provenance") if hypotheses else "")
                     or "").strip()
    # How it is known belongs beside how much to trust it. "Moderate
    # confidence" alone leaves a reader guessing whether that came from the
    # company's own page or from someone outside it, and those call for
    # different decisions.
    _BASIS = {
        "independently corroborated": "corroborated outside the company",
        "customer-observed": "based on what customers said, not only the "
                             "company",
        "company-stated": "based on the company's own account of itself",
        "pattern-supported": "based on a historical pattern, not on this "
                             "company",
        "inferred": "inferred from the evidence rather than stated anywhere",
    }
    if brief.view_withheld:
        note = "No view is put forward: the evidence does not support one."
    elif confidence:
        basis = _BASIS.get(provenance, "")
        note = (f"Held as a {confidence}-confidence hypothesis"
                + (f", {basis}." if basis else ", not a settled fact."))
    else:
        note = "A hypothesis, not a settled fact."
    # The thesis's own second sentence states the confidence, and the note
    # below states it again. Two lines apart, that is the repetition the whole
    # editorial pass exists to remove — so the view keeps only its claim.
    claim = _SENTENCE.split(brief.thesis.strip())[0] if brief.thesis else ""
    headline = Headline(does=_what_it_does(company, r, documents),
                        view=fit_to_words(claim, 40),
                        confidence=note)
    if headline.word_count > MAX_HEADLINE_WORDS:
        over = headline.word_count - MAX_HEADLINE_WORDS
        headline.view = fit_to_words(headline.view,
                                     max(12, _words(headline.view) - over))
    return headline


def build_brief(report, *, as_of: str = "", analysis_version: str = "",
                documents=()) -> ExecutiveBrief:
    """Assemble the brief from a strategic report. Deterministic.

    Selection is by rank, not by scoring: the report's own ordering already
    encodes evidential strength, so re-ranking here would be a second opinion
    with less information than the first.
    """
    r = report.as_dict() if hasattr(report, "as_dict") else (report or {})
    company = r.get("company_name", "")
    thesis = (r.get("thesis") or {})

    # One thesis. The view if there is one; otherwise the leading hypothesis,
    # which is the same claim earlier in its life.
    central = thesis.get("view", "") or _first(r.get("hypotheses", []),
                                               "statement", "title")

    # A brief whose most prominent line is blank is not a shorter brief; it is
    # one where the reader supplies the missing claim themselves, usually from
    # the first confident sentence further down. Say the thing instead: the
    # evidence described the company and supported no view worth putting
    # forward. That is a finding, and it is the honest one.
    view_withheld = bool(thesis.get("view_withheld"))
    if not is_meaningful(central):
        view_withheld = True
        central = (f"The public evidence describes what "
                   f"{company or 'this company'} does, but none of it "
                   f"supports a strategic view strongly enough to put one "
                   f"forward.")

    # Three signals, deduplicated across the sections they can come from — a
    # shift and a surprise describing the same event is one signal.
    candidates = []
    for shift in meaningful_items(r.get("shifts", []), key="title"):
        candidates.append({"text": shift.get("title", ""),
                           "date": shift.get("date", ""),
                           "source": shift.get("source_class", "")})
    for surprise in meaningful_items(r.get("surprises", []), key="finding"):
        candidates.append({"text": surprise.get("finding", ""),
                           "date": "", "source": ""})
    for observation in meaningful_items(r.get("observations", []),
                                        key="excerpt"):
        candidates.append({"text": observation.get("excerpt", ""),
                           "date": observation.get("date", ""),
                           "source": observation.get("source_class", "")})
    signals = deduplicate(candidates, key="text")[:SIGNAL_COUNT]

    # One counterpoint — what argues the other way. A brief with no
    # counterpoint is advocacy.
    counterpoint = (_first(r.get("surprises", []), "alternative_explanation")
                    or _first(r.get("vulnerabilities", []), "counterpoint")
                    or _first(r.get("hypotheses", []), "counter_note"))

    tension = (_first(r.get("blind_spots", []), "observed_tension")
               or _first(r.get("vulnerabilities", []), "exposed_layer"))

    decision = (thesis.get("why_care", "")
                or _first(r.get("decision_implications", []), "decision")
                or _first(r.get("questions", []), "decision_affected"))

    questions = [q.get("question", "") for q in
                 deduplicate(meaningful_items(r.get("questions", []),
                                              key="question"),
                             key="question")][:QUESTION_COUNT]

    limitations = consolidate_limitations(
        r.get("evidence_gaps", []),
        [f.get("message") for f in r.get("quality_findings", [])])
    limitation = limitations[0] if limitations else ""

    brief = ExecutiveBrief(
        company=company, thesis=central, signals=signals,
        counterpoint=counterpoint, tension=tension, decision=decision,
        questions=questions, limitation=limitation, as_of=as_of,
        analysis_version=analysis_version, view_withheld=view_withheld)
    brief = _enforce_budget(brief)
    # Built last, from the finished brief, so the headline can never say
    # something the brief has since trimmed away.
    brief.headline = _build_headline(company, r, brief, documents)
    return brief


def _enforce_budget(brief: ExecutiveBrief) -> ExecutiveBrief:
    """Bring the brief under MAX_WORDS by trimming the longest parts first.

    Longest-first because the budget is a reading-time budget: cutting the one
    rambling paragraph preserves every distinct point, while cutting evenly
    would shorten the crisp ones too and lose points that were already tight.
    The thesis and the limitation have floors — a brief without its central
    claim is not shorter, it is empty, and a brief that trims away its own
    caveat has been made more confident by editing.
    """
    if brief.within_budget:
        return brief
    fields = ["counterpoint", "tension", "decision", "thesis", "limitation"]
    floors = {"thesis": 40, "limitation": 20}
    while not brief.within_budget:
        over = brief.word_count - MAX_WORDS
        longest = max(fields, key=lambda f: _words(getattr(brief, f)))
        current = _words(getattr(brief, longest))
        floor = floors.get(longest, 8)
        if current <= floor:
            break                       # nothing left that may be cut
        target = max(floor, current - over)
        setattr(brief, longest, fit_to_words(getattr(brief, longest), target))
        if _words(getattr(brief, longest)) == current:
            break                       # trim made no progress; stop
    # Signals and questions are capped by count, so they are trimmed last and
    # individually — losing a whole signal loses a distinct point.
    if not brief.within_budget:
        brief.signals = [dict(s, text=fit_to_words(s.get("text", ""), 30))
                         for s in brief.signals]
        brief.questions = [fit_to_words(q, 25) for q in brief.questions]
    return brief


def brief_completeness(brief: ExecutiveBrief) -> dict:
    """Which of the brief's promised parts are actually present."""
    present = {
        "thesis": is_meaningful(brief.thesis),
        "signals": len(brief.signals) >= 1,
        "counterpoint": is_meaningful(brief.counterpoint),
        "tension": is_meaningful(brief.tension),
        "decision": is_meaningful(brief.decision),
        "questions": len(brief.questions) >= 1,
        "limitation": is_meaningful(brief.limitation),
    }
    return {"present": present,
            "missing": [k for k, v in present.items() if not v],
            "complete": all(present.values()),
            "word_count": brief.word_count,
            "within_budget": brief.within_budget}
