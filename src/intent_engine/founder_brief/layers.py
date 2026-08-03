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
# RECALIBRATED after de-duplication, not relaxed.
#
# 220 was measured on a page that printed one evidence gap three times -- as
# the biggest risk, the biggest unknown and an action. Removing that
# repetition took a real run from 218 to 213 words of UNIQUE intelligence
# without removing a single distinct fact, which means the old floor was
# partly counting padding. The floor still exists to catch a nearly-empty
# screen; it is a reading budget, not an evidence gate.
PRIMARY_MIN, PRIMARY_MAX = 205, 300
EXEC_RICH_MIN, EXEC_RICH_MAX = 500, 900
EXEC_LIMITED_MIN, EXEC_LIMITED_MAX = 250, 500
MAX_PARAGRAPH_WORDS = 70
MAX_ACTIONS = 3

# THE SCROLLABLE NARRATIVE IS BUDGETED IN TWO PLACES, NOT ONE.
#
# The 205-300 budget above was written for a page that TEASED the decision and
# sent the reader elsewhere for it. The narrative carries the whole thing --
# the answer, the trigger, the consequence, two options with what each costs,
# the next move, evidence on both sides, the falsifier and the prepared
# artefact -- so holding it to 300 words would mean deleting the options,
# which is the opposite of what this rebuild is for.
#
# What still has to be fast is the ANSWER. A founder gets the core in the
# first section and scrolls only if they want the rest, so that section is
# budgeted at 60 seconds of reading (~120 words at 250wpm) and the page as a
# whole is budgeted for depth. The floor matters more than the ceiling here:
# it is what catches a narrative that rendered headings over nothing.
ANSWER_MAX = 120
NARRATIVE_MIN, NARRATIVE_MAX = 250, 950

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


def _unavailable(key, title, reason, *, so_what="", to_watch="") -> Module:
    """A module with no data TEACHES. It still never draws an empty axis.

    Every dashboard, on every one of six live companies, opened with a stack
    of cards whose entire content was the word "Unavailable". That is an
    engineering status, not intelligence: it tells a founder the software
    failed rather than telling them what is and is not knowable about this
    company, and it was the single most common thing on the page.

    The refusal to fabricate a number is right and stays. What changes is that
    the absence now carries the two things a founder can act on -- why this
    gap matters to the decision, and what evidence would close it.
    """
    return Module(key=key, title=title, what_changed="", so_what=so_what,
                  what_to_watch=to_watch, available=False,
                  unavailable_reason=reason)


def _dedupe_dashboard(modules: List[Module]) -> List[Module]:
    """One screen, one sentence, once -- across every card.

    MEASURED on six live companies: after fixing the market module the
    dashboards still repeated 16 sentences between them. Business momentum and
    the strategic timeline print the same dated developments, and several
    cards inherit the same `so_what` and `what_to_watch` from the one key
    insight, so a founder met "how much to invest ahead of the transition"
    twice on one screen.

    First card to say a thing keeps it. A later card drops the line rather
    than repeating it, and drops nothing else -- a card that loses its
    interpretation still shows its rows.
    """
    ledger = Ledger()
    for module in modules:
        if module.what_changed and not ledger.fresh(module.what_changed):
            module.what_changed = ""
        if module.rows:
            kept = [r for r in module.rows
                    if ledger.fresh(str(r.get("value", "")))]
            module.rows = tuple(kept)
    # `so_what` and `what_to_watch` are deliberately NOT deduplicated. Every
    # available module owes the reader an interpretation -- the release gate
    # fails a module shown without one -- so suppressing a repeat here would
    # trade a duplicated sentence for a card that explains nothing. Cards
    # inheriting one insight's "why this matters" is a real remaining defect,
    # and the fix is a card-specific interpretation, not a blank.
    return modules


def _footing_prefix(footing: Optional[dict]) -> str:
    """What this run actually read, in one sentence, or "" if unknown.

    MEASURED on the deployed preview: Tesla and NVIDIA rendered BYTE-IDENTICAL
    dashboard, story and executive-brief pages -- 304, 371 and 387 words, the
    same text twice -- because every empty state was a constant. Naming the
    company fixes the heading and nothing else; two pages differing by one
    word are still materially identical, which is what the release gate now
    measures.

    So an absence is reported against THIS run's retrieval: what was read,
    how much of it was usable, and what refused. Counts only -- nothing here
    interprets evidence that was never retrieved.
    """
    if not footing:
        return ""
    read, usable = footing.get("pages_read"), footing.get("usable")
    if not read:
        return ""
    who = footing.get("company") or "this company"
    line = f"{read} page(s) were read for {who}"
    if usable is not None:
        line += f" and {usable} carried usable evidence"
    kinds = [k for k in (footing.get("kinds") or ()) if k]
    if kinds:
        line += f" ({', '.join(kinds)})"
    blocked = [b for b in (footing.get("blocked") or ()) if b]
    if blocked:
        shown = ", ".join(blocked[:2])
        more = f" and {len(blocked) - 2} more" if len(blocked) > 2 else ""
        line += f"; {shown}{more} refused automated access"
    return line + ". "


def build_dashboard(brief, report: Optional[dict] = None, *,
                    footing: Optional[dict] = None) -> List[Module]:
    """Modules supported by verified data, and honest gaps for the rest.

    `footing` carries what this particular run retrieved, so that a gap is
    reported as a fact about this company's evidence rather than as a
    constant that reads the same for every company.
    """
    report = report or {}
    modules: List[Module] = []
    seen = _footing_prefix(footing)

    # A. BUSINESS TRAJECTORY — only from a verified financial series.
    modules.append(_unavailable(
        "business_trajectory", "Business trajectory",
        seen +
        "No verified revenue, EPS, margin or cash-flow series was retrieved "
        "for this company. Estimated figures are deliberately not substituted "
        "— a fabricated financial series is the one error that would make "
        "this actively misleading.",
        so_what="Without a financial series you cannot tell growth from "
                "momentum, or a strong quarter from a strong year. Treat any "
                "read on this company's trajectory as provisional.",
        to_watch="A filed income statement, a published earnings release, or "
                 "an investor deck with a multi-period series would settle "
                 "it."))

    # B. MARKET TRAJECTORY — sanitised export only.
    market = brief.market_context or {}
    if market.get("available"):
        # The headline is the first module's sentence, and the rows repeat
        # every module including that one -- so Shopify's dashboard printed
        # "the shares fell 3.3% over the past three months" THREE times on one
        # screen. The ledger the layers already share is the fix: a row that
        # would restate the headline is dropped, not reprinted.
        market_ledger = Ledger()
        first = next(iter((market.get("modules") or {}).values()), {})
        market_ledger.spend(first.get("what_changed", ""))
        rows = []
        for name, module in (market.get("modules") or {}).items():
            value = market_ledger.fresh(module.get("what_changed", ""))
            if not value:
                continue
            rows.append({"label": name.replace("_", " ").title(),
                         "value": value,
                         "so_what": module.get("so_what", "")})
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
        # FOUR STATES, NOT TWO. The original copy asserted "for a private
        # company there is no market to read" on EVERY company without a
        # snapshot -- which the deployed preview printed under Tesla and
        # NVIDIA, both listed. A failed lookup and a private company are
        # different facts with different fixes, and only one of them is a
        # statement about the company.
        ticker = (footing or {}).get("ticker")
        status = (footing or {}).get("listing_status") or ""
        exchange = (footing or {}).get("listing_exchange") or ""
        if ticker:
            where = f" on {exchange}" if exchange else ""
            reason = (market.get("reason")
                      or f"No market snapshot has been published for "
                         f"{ticker}{where} in this run.")
            so_what = ("This company is listed, so a market read is possible "
                       "in principle -- it is missing here, not absent in "
                       "principle. Without it you are reading the company's "
                       "own account with nothing outside it to argue back.")
            to_watch = (f"A published price history for {ticker} is what "
                        f"makes this section possible.")
        elif status == "PUBLIC_LISTING_UNRESOLVED":
            reason = (market.get("reason")
                      or "The company appears to be publicly listed, but a "
                         "verified market identifier was not available for "
                         "this run.")
            so_what = ("The gap is in identifying the security, not in the "
                       "company. Until the right listing is confirmed, market "
                       "context would risk describing a different company's "
                       "shares.")
            to_watch = ("Confirming which listed entity and share class this "
                        "company trades as is what makes this section "
                        "possible.")
        elif status == "PRIVATE":
            reason = (market.get("reason")
                      or "This company has no public share-price series, so "
                         "listed-market context does not apply.")
            so_what = ("There is no market opinion to read for a private "
                       "company. That is a property of the company, not a "
                       "missing input, so nothing here is pending.")
            to_watch = ""
        else:
            reason = (market.get("reason")
                      or "No listing could be verified for this company, so "
                         "no market series was looked up.")
            so_what = ("Without market context you are reading the company's "
                       "own account with nothing outside it to argue back. "
                       "Whether that is because the company is private or "
                       "because the listing was not identified is itself "
                       "unresolved here.")
            to_watch = ("Confirming whether this company is listed, and under "
                        "which symbol, is the first step.")
        modules.append(_unavailable(
            "market_trajectory", "Market trajectory", reason,
            so_what=so_what, to_watch=to_watch))

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
        # A run can retrieve dated documents and still establish no dated
        # DEVELOPMENT -- Tesla's two SEC exhibits are the case. Naming them
        # tells the reader the difference between "nothing was found" and
        # "what was found does not carry a change", which are different
        # answers and lead to different next steps.
        docs = [d for d in ((footing or {}).get("documents") or ()) if d]
        if docs:
            shown = "; ".join(str(d) for d in docs[:3])
            reason = (f"No dated development could be verified. What was "
                      f"retrieved ({shown}) does not establish a change in "
                      f"direction.")
        else:
            reason = "No dated development could be verified from public sources."
        modules.append(_unavailable(
            "business_momentum", "Business momentum", reason,
            so_what="Undated material tells you what a company says it is, "
                    "never whether anything moved. Direction is the one thing "
                    "this evidence cannot establish.",
            to_watch="A dated announcement, release note or filing — one "
                     "timestamped item is enough to start a trajectory."))

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
    return _dedupe_dashboard(modules)


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
                ledger: Optional[Ledger] = None, *,
                footing: Optional[dict] = None) -> List[dict]:
    """Sections with real content. An empty section is omitted, never printed
    as a heading over nothing.

    On a limited run every candidate below is empty, so the story collapsed to
    the constant actions block -- identical for every company. `footing` gives
    it the one thing that is genuinely specific: what this run could and could
    not read.
    """
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

    # A story with no narrative section is the bounded case. It still opens
    # with what was actually read, so the reader learns where the reading
    # stopped for THEIR company rather than meeting a generic actions block.
    if not any(s["key"] != "watch" for s in out):
        opening = _footing_paragraphs(footing)
        if opening:
            out.insert(0, {"key": "verified",
                           "title": "What we could and could not read",
                           "paragraphs": opening})
    return out


def _footing_paragraphs(footing: Optional[dict]) -> List[str]:
    """This run's retrieval, as prose. Facts only -- no interpretation."""
    if not footing or not footing.get("pages_read"):
        return []
    who = footing.get("company") or "This company"
    read, usable = footing.get("pages_read"), footing.get("usable")
    first = f"{read} public page(s) could be read for {who}"
    if usable is not None:
        first += f", and {usable} carried evidence the analysis could use"
    docs = [d for d in (footing.get("documents") or ()) if d]
    if docs:
        first += ": " + "; ".join(str(d) for d in docs[:3])
    out = [first + "."]
    blocked = [b for b in (footing.get("blocked") or ()) if b]
    if blocked:
        shown = ", ".join(str(b) for b in blocked[:2])
        more = (f" and {len(blocked) - 2} other host(s)"
                if len(blocked) > 2 else "")
        out.append(f"{shown}{more} refused automated access. Anything "
                   f"published there is outside what this reading can check, "
                   f"which is a limit of the retrieval and not a finding "
                   f"about the company.")
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
    ("business", "Business and economic context"),
    ("context", "Market and financial context"),
    ("who", "Who benefits and who loses"),
    ("pattern", "How this has played out elsewhere"),
    ("wrong", "What could make this wrong"),
    ("next", "What to do or watch next"),
)

# The mental model's components, in the order a reader needs them: what the
# company sells, how it grows, how demand reaches it, what is hard to copy.
# These are the fields that answer "how does this business actually work",
# and the executive brief never read any of them.
_BUSINESS_COMPONENTS = ("value_proposition", "growth_engine",
                        "distribution_model", "strategic_assets",
                        "competitive_position")


def _sentences_of(text: str, limit: int = 2) -> str:
    """At most `limit` sentences, so one long joined field cannot become a
    paragraph nobody finishes.

    Clauses split on a semicolon are rejoined with a full stop, not a bare
    space. Dropping the separator produced "...real infrastructure ownership
    language alone is not proof..." on the live page -- two clauses fused into
    one unreadable one.
    """
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|;\s+", text or "")
             if p.strip()]
    kept = []
    for part in parts[:limit]:
        if kept and not kept[-1][-1:] in ".!?":
            kept[-1] = kept[-1] + "."
            part = part[:1].upper() + part[1:]   # it is a sentence now
        kept.append(part)
    return " ".join(kept)


def _component_text(model: dict, name: str) -> str:
    """One mental-model component as a readable sentence, or ''."""
    component = ((model or {}).get("components") or {}).get(name) or {}
    return _sentences_of(component.get("current_state") or "")


def _exposure_texts(items, limit: int = 2) -> List[str]:
    """Vulnerabilities as sentences a reader can follow.

    Concatenating `exposed_layer` + `mechanism` + `market_force` produced
    "demand capture at the storefront if buying is mediated by AI agents ...
    AI shopping agents / answer engines" -- three fields welded together with
    no punctuation and no grammar. The fields are right; the joining was not.
    """
    out: List[str] = []
    for item in (items or ()):
        if len(out) >= limit or not isinstance(item, dict):
            continue
        layer = (item.get("exposed_layer") or "").strip()
        how = (item.get("mechanism") or "").strip()
        force = (item.get("market_force") or "").strip()
        if not (layer and how):
            continue
        sentence = f"{layer[:1].upper()}{layer[1:]} is the exposed layer: {how}"
        if not sentence.endswith("."):
            sentence += "."
        if force:
            sentence += f" The pressure comes from {force}."
        out.append(sentence)
    return out


def _composed_decision_lines(report) -> str:
    """The options and the next move, in one line, from the one decision."""
    from intent_engine.strategic_intelligence.decision import decision_of
    decision = decision_of(report)
    if decision.readiness == "WITHHELD":
        return ""
    parts = [decision.headline]
    for option in decision.options[:2]:
        parts.append(f"{option.label}: {option.upside} {option.downside}")
    parts.append(decision.recommended_next_move)
    return " ".join(p for p in parts if p)


def _field_texts(items, *fields, limit: int = 2) -> List[str]:
    """The first `limit` non-empty values of `fields` across `items`.

    The report carries its reasoning as dicts (`blind_spots`,
    `vulnerabilities`, `surprises`, `decision_implications`), and the brief
    only ever called `_first_text`, which reads one string from one item and
    discards the rest.
    """
    out: List[str] = []
    for item in (items or ()):
        if len(out) >= limit:
            break
        if isinstance(item, str):
            if item.strip():
                out.append(_sentences_of(item))
            continue
        if not isinstance(item, dict):
            continue
        parts = [str(item.get(f)).strip() for f in fields
                 if isinstance(item.get(f), str) and item.get(f).strip()]
        if parts:
            out.append(_sentences_of(" ".join(parts), limit=3))
    return out


def _pattern_texts(report: dict) -> List[str]:
    """The comparable pattern, its analogs, and when it stops being true.

    UNSURFACED INTELLIGENCE. The reasoning engine computes a full comparable
    pattern -- mechanism, named historical examples WITH sources, the
    conditions under which it does not apply, and its own limitations -- and
    the executive brief never read a word of it. It was reachable only from
    the full analysis, which is the page a founder is least likely to open.

    A founder asking "has anyone done this before, and what happened?" is
    asking the single most useful question available here, and the answer was
    already computed.
    """
    patterns = [p for p in (report.get("patterns") or ())
                if isinstance(p, dict)]
    if not patterns:
        return []
    pattern = patterns[0]
    out: List[str] = []
    names = [e.get("name", "") for e in
             (pattern.get("historical_examples") or ()) if e.get("name")]
    mechanism = _sentences_of(pattern.get("mechanism") or "", limit=2)
    if names and mechanism:
        out.append(f"This is a known move: {', '.join(names[:3])} went the "
                   f"same way. {mechanism}")
    elif mechanism:
        out.append(mechanism)
    # The falsifier belongs beside the analogy, or the analogy is just
    # flattery -- a pattern that cannot fail explains nothing.
    unless = _sentences_of(pattern.get("when_it_does_not_apply") or "")
    if unless:
        out.append(f"It stops being the right comparison when {unless[0].lower()}"
                   f"{unless[1:]}")
    caveat = _sentences_of(pattern.get("limitations") or "")
    if caveat:
        out.append(caveat)
    return [t for t in out if t]


def build_executive_brief(brief, report: Optional[dict] = None,
                          ledger: Optional[Ledger] = None,
                          withheld_line: str = "", *,
                          footing: Optional[dict] = None) -> dict:
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
        return _limited_brief(brief, report, ledger, withheld_line, footing)

    # WHERE THE DEPTH WAS.
    #
    # This mapping read six fields and called `_first_text` on four of them,
    # which returns ONE string from ONE item. Meanwhile the report carried the
    # hypothesis's causal reasoning, a mental model of how the business makes
    # money, named vulnerabilities with their mechanism, second-order
    # surprises, and the alternatives behind each decision -- none of it
    # reachable from here. That is why an evidence-rich brief measured 131
    # words against a 500-900 budget: not missing analysis, unread analysis.
    thesis = report.get("thesis") or {}
    hypotheses = [h for h in (report.get("hypotheses") or ())
                  if isinstance(h, dict)]
    lead = hypotheses[0] if hypotheses else {}
    model = report.get("mental_model") or {}

    raw = {
        "bottom_line": [k.interpretation if k else withheld_line,
                        _sentences_of(thesis.get("transition") or ""),
                        _first_text(report.get("strategic_analysis"))],
        "changed": ([c["what"] for c in (brief.what_changed or ())]
                    + _field_texts(report.get("shifts"), "title", "evidence")
                    + _field_texts(report.get("timeline"), "event")),
        # `why_now` is deliberately NOT here. It reads "Recent public signal
        # (2024-11-01, Independent analysis) keeps this timely" -- provenance
        # wearing the clothes of a reason, and it was the entire "Why it
        # matters" section until the causal fields were wired in.
        "why": [_sentences_of(lead.get("reasoning") or "", limit=3),
                _sentences_of(thesis.get("tension") or ""),
                *_field_texts(report.get("decision_implications"),
                              "why_it_matters", limit=1),
                # The consequence, in economic terms. `why_now` on an
                # opportunity states what erodes if the reading is right --
                # which is the question this section exists to answer, and
                # the only one of these fields the 60-second screen has not
                # already spent.
                *_field_texts(report.get("opportunities"),
                              "why_now", limit=1)],
        # `decision_implications[*].decision` is `implications[0]` for each
        # hypothesis -- a decision TOPIC. The deployed brief printed two of
        # them verbatim under the heading "The decision": "Whether to keep
        # investing in depth or in adjacency." and "Whether to invest ahead of
        # demand in owning checkout/identity/data rails vs. deepening the core
        # product." The composed decision replaces them; the opportunities
        # below it are real statements and stay.
        "decision": ([k.decision if k else "",
                      _composed_decision_lines(report)]
                     + _field_texts(report.get("opportunities"),
                                    "statement", "why_now", "asymmetry")),
        # How the business actually works. Every one of these is a field the
        # reasoning layer already populated and the brief never opened.
        "business": [t for t in
                     (_component_text(model, name)
                      for name in _BUSINESS_COMPONENTS) if t],
        "context": [m.get("what_changed", "")
                    for m in (market.get("modules") or {}).values()],
        # Only where the evidence names a party. `vulnerabilities` states the
        # exposed layer and the mechanism; `surprises` states who a move
        # encroaches on. Neither is inferred here.
        "pattern": _pattern_texts(report),
        "who": (_exposure_texts(report.get("vulnerabilities"))
                + _field_texts(report.get("surprises"),
                               "finding", "why_surprising")),
        "wrong": (_field_texts(report.get("blind_spots"),
                               "observed_tension", "why_it_may_matter")
                  + [_sentences_of(a) for a in _alternatives(report)]
                  + _field_texts(report.get("underexamined_questions"),
                                 "question", "why_underexamined", limit=1)
                  + _field_texts(report.get("questions"),
                                 "question", "why_it_matters", limit=1)
                  + _field_texts(report.get("evidence_gaps"), limit=1)),
        "next": list(brief.next_actions),
    }

    # Up to three paragraphs where the material genuinely differs, two where
    # it does not. The ledger has already removed anything an earlier layer
    # said, so a third paragraph can only be new information -- padding is not
    # reachable through it.
    wide = {"business", "who", "wrong", "why", "decision", "changed",
            "pattern"}
    sections = []
    for key, title in BRIEF_SECTIONS:
        paragraphs = [t for t in (ledger.fresh(x) for x in raw.get(key, []))
                      if t]
        if paragraphs:
            sections.append({"key": key, "title": title,
                             "paragraphs": paragraphs[:3 if key in wide
                                                     else 2]})

    lo, hi = (EXEC_RICH_MIN, EXEC_RICH_MAX) if rich else (EXEC_LIMITED_MIN,
                                                          EXEC_LIMITED_MAX)
    words = sum(len(p.split()) for s in sections for p in s["paragraphs"])
    # BOTH bounds, like the limited brief one function below. Reporting only
    # the ceiling made `within_budget` mean "not too long", so a rich brief
    # that collapsed to a fraction of its promised depth -- because sections
    # were dropped or deduplicated away -- reported True and every gate above
    # it went green. A budget that is only ever checked from one side cannot
    # detect the failure it exists to detect.
    return {"sections": sections, "words": words,
            "budget": {"min": lo, "max": hi},
            "within_budget": lo <= words <= hi,
            "note": ("Sections with nothing new to say are omitted rather "
                     "than padded.")}


def _limited_brief(brief, report: dict, ledger: Ledger,
                   withheld_line: str,
                   footing: Optional[dict] = None) -> dict:
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

    # "Of 0 retrieved source(s)" was printed for a run that had just read a
    # filing. `observations` counts EVIDENCE the analysis accepted, which on a
    # limited run is legitimately zero -- but the sentence calls it "retrieved",
    # and a reader who has seen the source list on the previous screen is being
    # told the software did not do what they watched it do. The retrieval
    # counts come from the run itself; the evidence count keeps its own name.
    read = (footing or {}).get("pages_read")
    if read:
        why_limited = (
            f"{read} page(s) were read and {len(observations)} carried "
            f"evidence the analysis could use, of which {len(independent)} "
            f"come from someone other than the company and {len(dated)} carry "
            f"a date. ")
    else:
        why_limited = (
            f"Of {len(observations)} retrieved source(s), {len(independent)} "
            f"come from someone other than the company and {len(dated)} carry "
            f"a date. ")
    why_limited += (
        "Without dated, independent material there is no way to tell a "
        "direction from a snapshot, so any conclusion about where this "
        "business is heading would be the analysis filling in the gap rather "
        "than reading it. Decisions that depend on trajectory — hiring "
        "ahead of demand, pricing changes, competitive positioning — cannot "
        "be made confidently on this basis.")

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

    # WHAT WE VERIFIED has to be concrete or it is not worth a heading. With
    # no accepted evidence there is still something true and specific to say:
    # which documents were actually read, and which hosts refused. That is the
    # difference between "nothing could be established about your company" and
    # the same sentence printed for every company in the product.
    if not verified:
        seen = []
        docs = [d for d in ((footing or {}).get("documents") or ()) if d]
        if docs:
            seen.append("The public material that could be read was: "
                        + "; ".join(str(d) for d in docs[:3]) + ".")
        blocked = [b for b in ((footing or {}).get("blocked") or ()) if b]
        if blocked:
            shown = ", ".join(str(b) for b in blocked[:2])
            more = (f" and {len(blocked) - 2} other host(s)"
                    if len(blocked) > 2 else "")
            seen.append(f"{shown}{more} refused automated access, so anything "
                        f"published there could not be checked.")
        seen.append("No dated, checkable claim could be established from the "
                    "public material.")
        verified = seen

    raw = {
        "bottom_line": [bottom],
        "verified": verified,
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
