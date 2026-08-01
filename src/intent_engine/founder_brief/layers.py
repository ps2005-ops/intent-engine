"""The four layers below the 60-second brief — dashboard, story, brief, actions.

WHY ONE MODULE AND NOT FOUR
---------------------------
Deduplication is a stated product requirement, and it is only enforceable if
the layers are built together from one source. Four independent renderers each
reaching into the report would each pick the most quotable sentence -- which is
the same sentence -- and the reader would meet the thesis four times in four
places, which is exactly what "the executive brief repeats the presentation"
means.

So every layer here derives from ONE `FounderBrief`, and `Ledger` tracks which
excerpts have already been spent. A layer asks for a sentence; if it has been
used, it gets None and omits the line rather than repeating it.

THE READING BUDGET IS PART OF THE CONTRACT
------------------------------------------
    60-second brief    220-300 visible words
    executive brief    500-900 rich / 250-500 limited

A layer that cannot say something new within its budget should be shorter, not
padded. `omit_if_empty` exists so a section with nothing left to say disappears
instead of printing a heading over white space.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape as _e
from typing import Dict, List, Optional, Sequence

# --- reading budgets --------------------------------------------------------
PRIMARY_MIN, PRIMARY_MAX = 220, 300
EXEC_RICH_MIN, EXEC_RICH_MAX = 500, 900
EXEC_LIMITED_MIN, EXEC_LIMITED_MAX = 250, 500
MAX_PARAGRAPH_WORDS = 70
MAX_ACTIONS = 3

MARKET_DISCLAIMER = ("Descriptive market context, not an investment "
                     "recommendation.")


# Interface controls are not report prose. A follow-up form, its label and its
# suggested-question chips are how a founder ASKS for more -- counting them
# against the intelligence budget would force the product to choose between
# being answerable and being brief, which is a false trade.
UI_CONTROL_MARKER = "ui-controls"


def intelligence_words(html: str) -> int:
    """Words of FOUNDER INTELLIGENCE, excluding interface controls.

    This is the number the 220-300 budget governs. `visible_words` still
    reports total DOM text, so the split is visible rather than a way to hide
    prose inside a control -- a test asserts essential intelligence cannot be
    moved into the control block.
    """
    stripped = re.sub(
        r'<section[^>]*class="[^"]*' + UI_CONTROL_MARKER + r'[^"]*".*?</section>',
        " ", html or "", flags=re.S | re.I)
    return visible_words(stripped)


def visible_words(html: str) -> int:
    """Words a reader actually SEES on load.

    Excludes markup, style and script, and excludes the body of a closed
    `<details>` while keeping its `<summary>`. That is the honest measure for a
    progressive-disclosure design: text behind a disclosure the reader has not
    opened is not competing for the 60 seconds. Counting it would push the
    design toward hiding nothing and showing everything, which is the failure
    the budget exists to prevent.
    """
    text = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", html or "",
                  flags=re.S | re.I)
    # keep the summary, drop the collapsed body
    text = re.sub(r"<details[^>]*>(.*?)</details>",
                  lambda m: re.sub(r"<summary[^>]*>(.*?)</summary>.*",
                                   r"\1", m.group(1), flags=re.S) or "",
                  text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return len(re.sub(r"\s+", " ", text).strip().split())


class Ledger:
    """Which sentences have already been shown, so no layer repeats another."""

    def __init__(self):
        self._seen: set = set()

    @staticmethod
    def _key(text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))[:120]

    def fresh(self, text: str) -> Optional[str]:
        """The text, or None if a previous layer already used it."""
        if not text:
            return None
        key = self._key(text)
        if not key or key in self._seen:
            return None
        self._seen.add(key)
        return text

    def spend(self, *texts) -> None:
        for text in texts:
            if text:
                self._seen.add(self._key(text))


# ===========================================================================
# DASHBOARD
# ===========================================================================
@dataclass
class Module:
    """One dashboard tile. Every tile answers the same three questions."""
    key: str
    title: str
    what_changed: str
    so_what: str
    what_to_watch: str
    rows: tuple = ()
    text_alternative: str = ""
    available: bool = True
    unavailable_reason: str = ""

    def as_dict(self) -> dict:
        return {"key": self.key, "title": self.title,
                "what_changed": self.what_changed, "so_what": self.so_what,
                "what_to_watch": self.what_to_watch, "rows": list(self.rows),
                "text_alternative": self.text_alternative,
                "available": self.available,
                "unavailable_reason": self.unavailable_reason}


def _unavailable(key, title, reason) -> Module:
    """A module with no data says so. It never draws an empty axis, because a
    chart with no line is read as 'flat' -- a claim the absence cannot support."""
    return Module(key=key, title=title, what_changed="", so_what="",
                  what_to_watch="", available=False, unavailable_reason=reason)


def build_dashboard(brief, report: Optional[dict] = None) -> List[Module]:
    """Modules supported by verified data, and honest gaps for the rest."""
    report = report or {}
    modules: List[Module] = []

    # A. BUSINESS TRAJECTORY — only from a verified financial series.
    modules.append(_unavailable(
        "business_trajectory", "Business trajectory",
        "No verified revenue, EPS, margin or cash-flow series is available for "
        "this company. Estimated figures are deliberately not substituted — a "
        "fabricated financial series is the one error that would make this "
        "actively misleading."))

    # B. MARKET TRAJECTORY — sanitised export only.
    market = brief.market_context or {}
    if market.get("available"):
        rows = []
        for name, module in (market.get("modules") or {}).items():
            rows.append({"label": name.replace("_", " ").title(),
                         "value": module.get("what_changed", ""),
                         "so_what": module.get("so_what", "")})
        first = next(iter((market.get("modules") or {}).values()), {})
        modules.append(Module(
            key="market_trajectory", title="Market trajectory",
            what_changed=first.get("what_changed", ""),
            so_what=first.get("so_what", ""),
            what_to_watch=first.get("what_to_watch", ""),
            rows=tuple(rows),
            text_alternative="; ".join(
                f"{r['label']}: {r['value']}" for r in rows) or
            "no market series available"))
    else:
        modules.append(_unavailable(
            "market_trajectory", "Market trajectory",
            market.get("reason")
            or "No market snapshot is published for this company."))

    # C. BUSINESS MOMENTUM — dated, material developments only.
    momentum = [c for c in (brief.what_changed or ()) if c.get("what")]
    if momentum:
        modules.append(Module(
            key="business_momentum", title="Business momentum",
            what_changed=f"{len(momentum)} dated development(s) since the last "
                         f"material change.",
            so_what=(brief.key_insight.so_what if brief.key_insight else
                     "These are the changes a competitor or customer would "
                     "also notice."),
            what_to_watch=(brief.key_insight.watch if brief.key_insight
                           else "Whether the pattern continues."),
            rows=tuple({"label": c["when"], "value": c["what"]}
                       for c in momentum),
            text_alternative="; ".join(
                f"{c['when']}: {c['what']}" for c in momentum)))
    else:
        modules.append(_unavailable(
            "business_momentum", "Business momentum",
            "No dated developments could be verified from public sources."))

    # D. STRATEGIC TIMELINE — deduplicated, material only.
    timeline = _timeline(report, brief)
    if timeline:
        modules.append(Module(
            key="strategic_timeline", title="Strategic timeline",
            what_changed=f"{len(timeline)} material events, oldest first.",
            so_what="The sequence shows whether this is a direction or a "
                    "one-off.",
            what_to_watch="Whether the next event continues the sequence.",
            rows=tuple(timeline),
            text_alternative="; ".join(
                f"{t['label']}: {t['value']}" for t in timeline)))

    # E. DECISION MAP — the tension, both sides, and the no-regret move.
    if brief.key_insight:
        k = brief.key_insight
        modules.append(Module(
            key="decision_map", title="Decision map",
            what_changed=k.fact, so_what=k.so_what, what_to_watch=k.watch,
            rows=(
                {"label": "The tension", "value": k.so_what},
                {"label": "The decision", "value": k.decision},
                {"label": "No-regret move",
                 "value": (brief.next_actions[0] if brief.next_actions
                           else "Gather the evidence named below before "
                                "committing either way.")},
                {"label": "Evidence needed next", "value": k.watch},
            ),
            text_alternative=f"Tension: {k.so_what} Decision: {k.decision}"))
    return modules


def _timeline(report: dict, brief) -> List[dict]:
    """Material dated events, deduplicated.

    Retrieval timestamps and repeated wording are dropped: a timeline whose
    entries are 'we fetched this page' is a log, not a story.
    """
    seen, out = set(), []
    for item in (report.get("timeline") or []):
        if not isinstance(item, dict):
            continue
        when = str(item.get("date") or item.get("when") or "")[:10]
        what = " ".join(str(item.get("text") or item.get("event")
                            or item.get("what") or "").split())
        if not (when and what):
            continue
        key = Ledger._key(what)
        if key in seen:
            continue
        seen.add(key)
        out.append({"label": when, "value": what})
    if not out:
        for change in (brief.what_changed or ()):
            out.append({"label": change["when"], "value": change["what"]})
    return sorted(out, key=lambda r: r["label"])[:8]


# ===========================================================================
# SCROLLABLE DECISION STORY
# ===========================================================================
STORY_SECTIONS = (
    ("answer", "The answer in one minute"),
    ("changed", "What changed"),
    ("business", "The business story"),
    ("tension", "The important tension"),
    ("consequence", "The economic or market consequence"),
    ("decision", "The decision"),
    ("wrong", "What could make this wrong"),
    ("watch", "What to watch next"),
)


def build_story(brief, report: Optional[dict] = None,
                ledger: Optional[Ledger] = None) -> List[dict]:
    """Sections with real content. An empty section is omitted, never printed
    as a heading over nothing."""
    report = report or {}
    ledger = ledger or Ledger()
    k = brief.key_insight
    market = brief.market_context or {}

    candidates = {
        "answer": [brief.what_it_does, k.fact if k else "",
                   k.so_what if k else ""],
        "changed": [c["what"] for c in (brief.what_changed or ())],
        "business": [k.interpretation if k else "",
                     _first_text(report.get("mental_model"))],
        "tension": [(report.get("thesis") or {}).get("tension", ""),
                    k.so_what if k else ""],
        "consequence": [m.get("what_changed", "")
                        for m in (market.get("modules") or {}).values()],
        "decision": [k.decision if k else "",
                     _first_text(report.get("decision_implications"))],
        "wrong": [_first_text(report.get("blind_spots")),
                  _first_text(report.get("vulnerabilities")),
                  *[a for a in _alternatives(report)]],
        "watch": [k.watch if k else "", *list(brief.next_actions)],
    }

    out = []
    for key, title in STORY_SECTIONS:
        paragraphs = []
        for text in candidates.get(key, []):
            fresh = ledger.fresh(text)
            if fresh:
                paragraphs.append(fresh)
        if paragraphs:
            out.append({"key": key, "title": title,
                        "paragraphs": paragraphs[:3]})
    return out


def _first_text(items) -> str:
    for item in (items or ()):
        if isinstance(item, str) and item.strip():
            return item
        if isinstance(item, dict):
            for field_ in ("text", "statement", "summary", "title"):
                if item.get(field_):
                    return item[field_]
    return ""


def _alternatives(report: dict) -> List[str]:
    out = []
    for hypothesis in (report.get("hypotheses") or ())[:2]:
        if isinstance(hypothesis, dict):
            for alt in (hypothesis.get("alternative_explanations") or ())[:2]:
                text = alt if isinstance(alt, str) else alt.get("text", "")
                if text:
                    out.append(text)
    return out


# ===========================================================================
# EXECUTIVE BRIEF
# ===========================================================================
# When no reading was asserted, a brief built from thesis fields has almost
# nothing to draw on -- it measured 168 words. The answer is not filler: it is
# that a LIMITED brief has a different and genuinely useful structure, built
# from what WAS established rather than from a conclusion that was withheld.
LIMITED_SECTIONS = (
    ("bottom_line", "The bottom line"),
    ("verified", "What we verified"),
    ("why_limited", "Why the limitation matters"),
    ("customer_view", "What a customer or investor can currently see"),
    ("decision", "The decision"),
    ("could_change", "What could change this assessment"),
    ("next", "What to do next"),
)

BRIEF_SECTIONS = (
    ("bottom_line", "The bottom line"),
    ("changed", "What changed"),
    ("why", "Why it matters"),
    ("decision", "The decision"),
    ("context", "Economic and market context"),
    ("wrong", "What could make this wrong"),
    ("next", "What to do or watch next"),
)


def build_executive_brief(brief, report: Optional[dict] = None,
                          ledger: Optional[Ledger] = None,
                          withheld_line: str = "") -> dict:
    """Deepens the first screen without repeating it.

    The ledger is passed in ALREADY LOADED with the 60-second brief's
    sentences, so this layer physically cannot restate them -- which is the
    only reliable way to stop an executive brief becoming a longer copy of the
    summary above it.
    """
    report = report or {}
    ledger = ledger or Ledger()
    k = brief.key_insight
    market = brief.market_context or {}
    rich = brief.mode == "PUBLIC_INFORMATION_RICH"

    # THE WITHHELD CASE. When no reading cleared the evidence bar the brief
    # must SAY so and say what is established instead. Rendering an executive
    # brief with no bottom line leaves the reader to conclude the analysis
    # simply failed -- which is both wrong and the failure the sparse primary
    # view already fixed one layer up.
    if not k:
        withheld_line = (withheld_line
                         or report.get("result_state_detail")
                         or _first_text(report.get("strategic_analysis"))
                         or "The public evidence describes what this company "
                            "does, but none of it supports a strategic view "
                            "strongly enough to put one forward.")

    if not k:
        return _limited_brief(brief, report, ledger, withheld_line)

    raw = {
        "bottom_line": [k.interpretation if k else withheld_line,
                        _first_text(report.get("strategic_analysis"))],
        "changed": [c["what"] for c in (brief.what_changed or ())],
        "why": [(report.get("thesis") or {}).get("tension", ""),
                _first_text(report.get("decision_implications"))],
        "decision": [k.decision if k else "",
                     _first_text(report.get("opportunities"))],
        "context": [m.get("what_changed", "")
                    for m in (market.get("modules") or {}).values()],
        "wrong": [_first_text(report.get("blind_spots")),
                  *_alternatives(report),
                  _first_text(report.get("evidence_gaps"))],
        "next": list(brief.next_actions),
    }

    sections = []
    for key, title in BRIEF_SECTIONS:
        paragraphs = [t for t in (ledger.fresh(x) for x in raw.get(key, []))
                      if t]
        if paragraphs:
            sections.append({"key": key, "title": title,
                             "paragraphs": paragraphs[:2]})

    lo, hi = (EXEC_RICH_MIN, EXEC_RICH_MAX) if rich else (EXEC_LIMITED_MIN,
                                                          EXEC_LIMITED_MAX)
    words = sum(len(p.split()) for s in sections for p in s["paragraphs"])
    return {"sections": sections, "words": words,
            "budget": {"min": lo, "max": hi},
            "within_budget": words <= hi,
            "note": ("Sections with nothing new to say are omitted rather "
                     "than padded.")}


def _limited_brief(brief, report: dict, ledger: Ledger,
                   withheld_line: str) -> dict:
    """The executive brief for a company whose reading was withheld.

    Every section is built from material the run actually established. Nothing
    infers adoption, economics, leadership intent or defensibility -- those are
    precisely what the missing evidence would have been needed for, and
    supplying them here would undo the withholding one layer down.
    """
    observations = [o for o in (report.get("observations") or ())
                    if isinstance(o, dict)]
    dated = [o for o in observations if (o.get("date") or "")[:4].isdigit()]
    independent = [o for o in observations
                   if o.get("source_class") not in
                   ("company_owned", "executive_statement", None, "")]
    gaps = [g if isinstance(g, str) else g.get("text", "")
            for g in (report.get("evidence_gaps") or ())]
    questions = [q if isinstance(q, str) else q.get("text", "")
                 for q in (report.get("questions") or ())]

    bottom = withheld_line or (
        "The public material describes what this company does, but none of it "
        "carries the dated, independently-reported substance a strategic "
        "reading has to rest on. That is a finding about the evidence, not a "
        "verdict on the business.")

    verified = []
    for o in (dated or observations)[:3]:
        text = " ".join(str(o.get("text") or o.get("summary") or "").split())
        when = str(o.get("date") or "")[:10]
        if text:
            verified.append(f"{when + ' — ' if when else ''}{text}")

    why_limited = (
        f"Of {len(observations)} retrieved source(s), {len(independent)} come "
        f"from someone other than the company and {len(dated)} carry a date. "
        f"Without dated, independent material there is no way to tell a "
        f"direction from a snapshot, so any conclusion about where this "
        f"business is heading would be the analysis filling in the gap rather "
        f"than reading it. Decisions that depend on trajectory — hiring "
        f"ahead of demand, pricing changes, competitive positioning — cannot "
        f"be made confidently on this basis.")

    customer_view = (
        "A prospective customer, partner or investor researching this company "
        "sees exactly what this analysis saw. Where pricing, proof of use or "
        "independent coverage is absent here, it is absent for them too — and "
        "they will not ask; they will move on. That is the practical cost of "
        "the gap, and it is felt before any strategic question is settled.")

    decision = (
        "Whether to close the evidence gap publicly — pricing, a named "
        "customer outcome, a dated product record — or accept that every "
        "evaluation of this company starts from an unverified position. The "
        "first is cheap and controllable; the second compounds quietly.")

    could_change = []
    for gap in gaps[:2]:
        if gap:
            could_change.append(f"{gap} would materially change this.")
    for question in questions[:1]:
        if question:
            could_change.append(f"An answer to: {question}")
    if not could_change:
        could_change.append(
            "Independent reporting, a dated customer outcome, or published "
            "pricing would each move this assessment.")

    raw = {
        "bottom_line": [bottom],
        "verified": verified or ["No dated, checkable claim could be "
                                 "established from the public material."],
        "why_limited": [why_limited],
        "customer_view": [customer_view],
        "decision": [decision],
        "could_change": could_change,
        "next": list(brief.next_actions)[:3],
    }
    sections = []
    for key, title in LIMITED_SECTIONS:
        paragraphs = [x for x in (ledger.fresh(v) for v in raw.get(key, []))
                      if x]
        if paragraphs:
            sections.append({"key": key, "title": title,
                             "paragraphs": paragraphs})
    words = sum(len(p.split()) for s in sections for p in s["paragraphs"])
    return {"sections": sections, "words": words,
            "budget": {"min": EXEC_LIMITED_MIN, "max": EXEC_LIMITED_MAX},
            "within_budget": EXEC_LIMITED_MIN <= words <= EXEC_LIMITED_MAX,
            "limited": True,
            "note": ("Built from what was established. Nothing here infers "
                     "adoption, economics or strategy — those are what the "
                     "missing evidence would have been needed for.")}


# ===========================================================================
# ACTION LAYER — preparation only
# ===========================================================================
ACTION_KINDS = (
    ("decision_memo", "Founder decision memo"),
    ("board_briefing", "Board briefing"),
    ("competitor_watchlist", "Competitor watchlist"),
    ("diligence_questions", "Diligence questions"),
    ("monitoring_plan", "Weekly monitoring plan"),
    ("evidence_requests", "Evidence request checklist"),
    ("risk_register", "Risk register"),
    ("opportunity_brief", "Opportunity brief"),
    ("meeting_agenda", "Meeting agenda"),
    ("one_pager", "One-page summary"),
)

# Language that would claim an external action happened. This release prepares
# artefacts and nothing else, so these are forbidden outright rather than
# discouraged -- a founder who believes an email went out will not send it.
FORBIDDEN_EXECUTION_LANGUAGE = (
    "we contacted", "we have contacted", "this will be sent", "has been sent",
    "we emailed", "we notified", "published on your behalf",
    "the system has updated", "the campaign is live", "monitoring is active",
    "we scheduled", "we have reached out", "already sent",
)

APPROVAL_NOTICE = ("Prepared only. Nothing is sent, published, scheduled or "
                   "shared until you explicitly approve it.")


@dataclass
class Action:
    kind: str
    title: str
    intelligence: str
    recommended_action: str
    why: str
    expected_result: str
    evidence_ids: tuple = ()
    approval_required: str = APPROVAL_NOTICE

    def as_dict(self) -> dict:
        return {"kind": self.kind, "title": self.title,
                "intelligence": self.intelligence,
                "recommended_action": self.recommended_action,
                "why": self.why, "expected_result": self.expected_result,
                "evidence_ids": list(self.evidence_ids),
                "approval_required": self.approval_required,
                "prepared_only": True}


def build_actions(brief) -> List[Action]:
    """Artefacts this run has enough material to prepare.

    Only kinds the evidence supports are offered. Listing ten buttons where
    two have content is a menu, not a capability.
    """
    k = brief.key_insight
    out: List[Action] = []

    if k:
        out.append(Action(
            kind="decision_memo", title="Founder decision memo",
            intelligence=k.fact,
            recommended_action=f"Write up the choice: {k.decision}",
            why=k.so_what,
            expected_result="A one-page memo that forces the trade-off to be "
                            "made explicitly rather than by default.",
            evidence_ids=k.evidence_ids))
        out.append(Action(
            kind="monitoring_plan", title="Weekly monitoring plan",
            intelligence=k.watch,
            recommended_action="Check this one indicator weekly and record "
                               "what it shows.",
            why="It is the fastest signal that would confirm or contradict "
                "the reading above.",
            expected_result="Either the conclusion strengthens or it is "
                            "caught early while it is still cheap to change.",
            evidence_ids=k.evidence_ids))

    if brief.unclear or brief.public_proofs:
        out.append(Action(
            kind="evidence_requests", title="Evidence request checklist",
            intelligence="; ".join(brief.unclear[:2]) or
                         "Key facts could not be verified publicly.",
            recommended_action="Publish or obtain the specific proofs listed.",
            why="A buyer, partner or investor sees exactly what this analysis "
                "saw. What cannot be verified here cannot be verified by them.",
            expected_result="Fewer unanswered questions in a first "
                            "conversation."))

    if brief.biggest_risk:
        out.append(Action(
            kind="risk_register", title="Risk register",
            intelligence=brief.biggest_risk,
            recommended_action="Record this risk with an owner and a review "
                               "date rather than carrying it informally.",
            why="It is the single most consequential thing this analysis "
                "found that could go wrong.",
            expected_result="The risk is tracked instead of remembered."))
    return out[:MAX_ACTIONS + 1]


def check_execution_language(text: str) -> List[str]:
    low = (text or "").lower()
    return [p for p in FORBIDDEN_EXECUTION_LANGUAGE if p in low]
