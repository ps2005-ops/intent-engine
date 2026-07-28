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
                "word_count": self.word_count}


def _first(items, *keys, default=""):
    """The first meaningful value under any of `keys`, across `items`."""
    for item in items or ():
        for key in keys:
            value = item.get(key) if isinstance(item, dict) else item
            if is_meaningful(value):
                return str(value).strip()
    return default


def build_brief(report, *, as_of: str = "", analysis_version: str = "") \
        -> ExecutiveBrief:
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
        analysis_version=analysis_version)
    return _enforce_budget(brief)


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
