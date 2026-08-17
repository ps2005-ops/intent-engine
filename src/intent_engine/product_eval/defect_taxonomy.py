"""Every defect Pre-100 found, as a detector that runs against a rendered page.

WHY A TAXONOMY AND NOT A CHECKLIST
----------------------------------
Five of the last six defects in this product were found by READING the
deployed page, not by running the suite. That is not an argument for more
reading; it is an argument that the suite was asking the wrong question. A
unit test asks "did this function return the right object". Every one of those
defects was a correct object rendered into a sentence a customer could not
use: a strategic refusal, an industrial mechanism on a software company, a
website tagline clipped mid-clause, a raw enum, a provenance drawer no route
opened.

So the detectors here take the CUSTOMER-FACING TEXT of a page and ask the
question a reader would. They are deliberately crude regular expressions over
visible prose rather than assertions about internal state, because the visible
prose is the product and the internal state has been correct throughout.

HOW TO ADD ONE
--------------
A detector earns its place by having been a real, observed defect. Each row
carries the severity, the surfaces it applies to, and the repair CLASS -- what
kind of change fixes it -- because a defect whose repair is unknown produces a
backlog entry rather than a fix.

WHAT A DETECTOR MAY NOT DO
--------------------------
Fail on a sentence that is correct. Several of these patterns describe
language that is right in one place and wrong in another: "no independent
source corroborated this" is honest inside a confidence statement and a
product failure as a hero. Where that is true the detector is scoped to the
surface or to the position, and where it cannot be scoped safely it is a
WARNING rather than a defect.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

CONTRACT = "defect_taxonomy.v1"

# --- severity ---------------------------------------------------------------
SEV1 = "SEV1"       #: the product is wrong, or claims something it cannot
SEV2 = "SEV2"       #: a customer would not buy this; demo-blocking
SEV3 = "SEV3"       #: visible blemish, not demo-blocking
WARNING = "WARNING"  #: possible defect, needs a human read

SEVERITIES = (SEV1, SEV2, SEV3, WARNING)

# --- repair classes ---------------------------------------------------------
REPAIR_SELECTION = "SELECTION"      #: the wrong thing was chosen; gate it
REPAIR_COMPOSITION = "COMPOSITION"  #: the right thing, said badly
REPAIR_ROUTING = "ROUTING"          #: it exists and nothing links to it
REPAIR_EVIDENCE = "EVIDENCE"        #: the claim needs a source it lacks
REPAIR_PRESENTATION = "PRESENTATION"  #: layout, contrast, responsiveness


@dataclasses.dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    surface: str
    evidence: str          #: the offending text, quoted
    repair_class: str
    detail: str = ""

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class Detector:
    code: str
    severity: str
    repair_class: str
    what: str
    #: Surfaces this applies to. Empty means every surface.
    surfaces: Tuple[str, ...] = ()
    #: Surfaces this NEVER applies to, checked before `surfaces`.
    except_surfaces: Tuple[str, ...] = ()


# ===========================================================================
# the patterns
# ===========================================================================
#: A product-level strategic dead end. The defect that reopened the gate.
_REFUSAL = re.compile(
    # NOT `[^.]{0,80}` between the two halves. The company name sits in that
    # gap and company names contain full stops -- "No strategic reading of
    # Cloudflare, Inc. cleared the evidence bar" is the exact sentence this
    # detector exists for, and the first draft could not see it.
    r"no strategic reading\b.{0,80}?cleared the evidence bar"
    r"|no reading cleared the evidence bar"
    r"|no single conclusion cleared the evidence bar"
    r"|no conclusion cleared the evidence bar"
    r"|not enough to read a strategy from"
    r"|the strategic analyst has no strategy", re.I | re.S)

#: A competitor section that reports its own retrieval instead of a read.
_NO_COMPETITOR = re.compile(
    r"no competitor'?s own account was retrieved"
    r"|no competitor (?:was|could be) (?:found|identified|retrieved)", re.I)

#: Prose that stops because a buffer did. A quotation inside a blockquote is
#: allowed to elide; product prose is not, which is why this is scoped to
#: text outside quotation marks by the caller.
_TRUNCATED = re.compile(r"[a-z,]\s*(?:…|\.\.\.)(?:\s|$)")

#: Website marketing that has been pasted in as product prose.
_MARKETING = re.compile(
    r"\bour mission is to\b|\bmission is to help build\b"
    r"|\bwe are on a mission\b|\bthe world'?s leading\b"
    r"|\bbest-in-class\b|\bcutting[- ]edge\b|\bindustry[- ]leading\b"
    r"|\bpowering the next generation\b|\bunlock(?:ing)? the power of\b", re.I)

#: An internal enum that reached a page.
_RAW_ENUM = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?:[A-Z][A-Z0-9]{2,}_[A-Z0-9_]{2,})"
    r"(?![A-Za-z0-9_])")

#: An internal identifier that reached a page.
_RAW_ID = re.compile(
    r"\b(?:obs|ev|claim|src|doc)[-_][0-9a-f]{6,}\b"
    r"|\b[0-9A-HJKMNP-TV-Z]{26}\b", re.I)

#: A number with more precision than public evidence can carry.
_UNSUPPORTED_PRECISION = re.compile(
    r"\b\d+\.\d{2,}\s?(?:%|percent)\b"
    r"|\bexactly \d")

#: Implementation vocabulary in customer-facing prose.
# CASE MATTERS HERE. `None` is a Python literal and `none` is an English
# word; matching case-insensitively flagged "so none is asserted here" as
# implementation vocabulary, which made the detector's own output noise.
_IMPLEMENTATION = re.compile(
    r"\bdataclass\b|\btraceback\b|\bstacktrace\b"
    r"|\bJSON\b|\bNoneType\b|\bNone\b|\bnull\b"
    r"|\bcontract v\d|\bpipeline stage\b|\brenderer\b|\bendpoint\b")

#: A caveat repeated so often it stops meaning anything.
_HEDGE = re.compile(
    r"not established|cannot be established|is not disclosed|not measured"
    r"|no independent source|not corroborated|bounded rather than measured",
    re.I)

#: A claim of certainty the evidence walls forbid.
_FALSE_CONFIDENCE = re.compile(
    r"\bzero risk\b|\bno risk\b|\bguarantee[ds]?\b|\bcertain(?:ly)? to\b"
    r"|\bwill definitely\b|\bproven to\b", re.I)

#: The model talking about itself.
_AI_VOICE = re.compile(
    r"\bAI says\b|\bas an AI\b|\bthe model (?:thinks|believes)\b"
    r"|\bour algorithm\b|\bmachine learning model\b", re.I)

#: Hindsight in a vintage panel.
_HINDSIGHT = re.compile(
    r"\bas we now know\b|\bin hindsight\b|\bit turned out\b"
    r"|\bwith the benefit of hindsight\b|\bwe now know\b", re.I)

#: A descriptive history calling itself a replay.
_FAKE_REPLAY = re.compile(r"\breplay(?:ed|ing)?\b.{0,40}\bhistor", re.I)

#: Language that presents activity as learning.
_ACTIVITY_AS_LEARNING = re.compile(
    r"\b\d+\s+(?:sources?|documents?|pages?)\s+learned\b"
    r"|\blearned\s+\d+\s+(?:sources?|documents?|pages?)\b", re.I)

#: The tab grid the six-step flow replaced.
_TAB_GRID = re.compile(
    r"Executive X-Ray\s*The full story\s*Intelligence\s*Executive brief", re.I)


DETECTORS: Tuple[Detector, ...] = (
    Detector("STRATEGIC_REFUSAL_COLLAPSE", SEV1, REPAIR_SELECTION,
             "the product declines to put any strategy forward"),

    # --- §21. The belief layer's own defects ------------------------------
    #
    # These are checked STRUCTURALLY, against the read, rather than by
    # pattern over prose. A regular expression cannot tell manufactured
    # contrarianism from the real thing; the objects can, because the engine
    # records what moved a belief and what it was bound to.
    Detector("MARKET_BELIEF_UNSUPPORTED", SEV1, REPAIR_EVIDENCE,
             "a belief is asserted without naming what it was derived from"),
    Detector("CONTRARIANISM_WITHOUT_EVIDENCE", SEV1, REPAIR_EVIDENCE,
             "a belief is called weakened with no evidence that weakened it"),
    Detector("BELIEF_CONFIRMATION_BIAS", SEV2, REPAIR_SELECTION,
             "every belief survived and none was attacked with an alternative"),
    Detector("MANAGEMENT_BELIEF_MISATTRIBUTED", SEV1, REPAIR_EVIDENCE,
             "a claim is attributed to management that management did not make"),
    Detector("ALTERNATIVE_EXPLANATION_MISSING", SEV2, REPAIR_SELECTION,
             "an observation is explained one way and no rival cause is put"),
    Detector("IMPOSSIBLE_HYPOTHESIS_GENERIC", SEV2, REPAIR_COMPOSITION,
             "an unconventional hypothesis names no part of this company"),
    Detector("IMPOSSIBLE_HYPOTHESIS_UNBOUNDED", SEV1, REPAIR_EVIDENCE,
             "a hypothesis is put with nothing that would settle it"),
    Detector("COMPETITOR_TOO_GENERIC", SEV2, REPAIR_SELECTION,
             "the competitive set is structural peers and nothing else"),
    Detector("SUBSTITUTE_MISSING", SEV2, REPAIR_SELECTION,
             "every alternative is a vendor; no substitute was considered"),
    Detector("INTERNAL_BUILD_IGNORED", SEV3, REPAIR_SELECTION,
             "buy-versus-build is never put as an alternative"),
    Detector("AI_DISPLACEMENT_UNTESTED", SEV3, REPAIR_SELECTION,
             "automation is not tested as a threat or as an expansion"),
    Detector("ASSUMPTION_GRAPH_BROKEN", SEV1, REPAIR_COMPOSITION,
             "the argument chain has a step with no reason under it"),
    Detector("WEAKEST_ASSUMPTION_MISSING", SEV2, REPAIR_COMPOSITION,
             "a recommendation is given without naming its weakest support"),
    Detector("FALSIFIER_MISSING", SEV1, REPAIR_EVIDENCE,
             "a recommendation is made that nothing could prove wrong"),
    Detector("MVE_MISSING", SEV2, REPAIR_COMPOSITION,
             "uncertainty is stated with no experiment that would resolve it"),
    Detector("LEVEL_K_REACTION_MISSING", SEV2, REPAIR_COMPOSITION,
             "a move is recommended without asking what the other side does"),
    Detector("CROSS_COMPANY_STRATEGY_COLLAPSE", SEV1, REPAIR_SELECTION,
             "two companies were given the same strategic sentence"),
    Detector("WRONG_COMPANY", SEV1, REPAIR_SELECTION,
             "the page names a company other than the subject"),
    Detector("COMPETITOR_MISSING", SEV2, REPAIR_SELECTION,
             "the competitive section reports retrieval instead of a read"),
    Detector("WEBSITE_COPY_LEAK", SEV2, REPAIR_COMPOSITION,
             "marketing copy is presented as product prose"),
    Detector("TRUNCATED_SENTENCE", SEV2, REPAIR_COMPOSITION,
             "prose ends because a buffer did"),
    Detector("RAW_ENUM", SEV3, REPAIR_COMPOSITION,
             "an internal enum reached the page"),
    Detector("RAW_EVIDENCE_ID", SEV3, REPAIR_COMPOSITION,
             "an internal identifier reached the page"),
    Detector("UNSUPPORTED_PRECISION", SEV1, REPAIR_EVIDENCE,
             "a figure carries more precision than its source"),
    Detector("IMPLEMENTATION_VOCABULARY", SEV3, REPAIR_COMPOSITION,
             "internal vocabulary in customer prose"),
    Detector("EXCESSIVE_HEDGING", SEV2, REPAIR_COMPOSITION,
             "so many caveats that no reading survives them"),
    Detector("FALSE_CONFIDENCE", SEV1, REPAIR_EVIDENCE,
             "certainty the evidence does not support"),
    Detector("AI_VOICE", SEV3, REPAIR_COMPOSITION,
             "the system talking about itself instead of the company"),
    Detector("HINDSIGHT_LEAK", SEV1, REPAIR_SELECTION,
             "a vintage panel reasons from a later outcome",
             surfaces=("history",)),
    Detector("FAKE_REPLAY", SEV1, REPAIR_COMPOSITION,
             "descriptive history described as a replay",
             surfaces=("history",)),
    Detector("LEARNING_ACTIVITY_CONFUSION", SEV2, REPAIR_COMPOSITION,
             "reading is reported as knowing"),
    Detector("NAVIGATION_GRID", SEV2, REPAIR_ROUTING,
             "the primary page ends in a menu of competing destinations"),
    Detector("GENERIC_STRATEGY", SEV2, REPAIR_SELECTION,
             "the page never names the company in its own analysis"),
    Detector("TEMPLATE_COLLAPSE", SEV1, REPAIR_SELECTION,
             "the reading belongs to a different business model"),
    Detector("EMPTY_SURFACE", SEV2, REPAIR_ROUTING,
             "a step in the flow renders almost nothing"),
    Detector("PROVENANCE_UNREACHABLE", SEV2, REPAIR_ROUTING,
             "the evidence drawer exists and no page links to it"),
    # --- §88. The classes this convergence run added -----------------------
    #
    # Each is a defect that was OBSERVED on the deployed product or is the
    # direct failure mode of something this run built. A detector for a
    # defect nobody has seen is a guess with a test attached.
    Detector("CUSTOMER_ABSENCE_COPY", SEV2, REPAIR_COMPOSITION,
             "an absence is stated to a customer with nothing to do about it"),
    Detector("HISTORY_TEXT_ONLY", SEV2, REPAIR_COMPOSITION,
             "the history step carries no chart, only prose",
             surfaces=("history",)),
    Detector("MISSING_MARKET_EXPECTATION", SEV2, REPAIR_COMPOSITION,
             "the history chart has no expectation series",
             surfaces=("history",)),
    Detector("UNLABELED_MODELED_EXPECTATION", SEV1, REPAIR_COMPOSITION,
             "a modelled expectation is shown without saying it is modelled",
             surfaces=("history",)),
    Detector("COUNTERFACTUAL_PRESENTED_AS_FACT", SEV1, REPAIR_COMPOSITION,
             "an alternative path is stated as what would have happened"),
    Detector("HISTORY_TEMPLATE_COLLAPSE", SEV1, REPAIR_SELECTION,
             "the historical explanation would fit a different company",
             surfaces=("history",)),
    Detector("PROGRESS_DEAD_END", SEV2, REPAIR_ROUTING,
             "the progress page tells the reader to navigate away"),
    Detector("FEEDBACK_MISSING", SEV2, REPAIR_ROUTING,
             "the last step collects no feedback", surfaces=("connect",)),
    Detector("ENTITY_AMBIGUITY_UNRESOLVED", SEV1, REPAIR_SELECTION,
             "two companies could answer to the identity that was analysed"),
)

BY_CODE = {d.code: d for d in DETECTORS}


# ===========================================================================
# §10 — the mechanism vocabulary that belongs to each business model
# ===========================================================================
#: Words that only make sense for a business of a particular kind. A software
#: company described in take-or-pay and cost-curve language is the
#: TEMPLATE_COLLAPSE defect, and it is detectable without knowing anything
#: about the company beyond its model class.
_MODEL_FOREIGN = {
    "SUBSCRIPTION_SOFTWARE": (
        "take-or-pay", "ageing lines", "ore body", "reserve life",
        "cost curve", "smelter", "refinery", "drilling", "net interest margin",
        "deposit repricing", "loan losses", "underwriting standard",
        "channel inventory", "dealer inventory", "capacity utilisation",
        "capacity utilization", "fab", "wafer", "installed-base annuity"),
    "BALANCE_SHEET_OR_NETWORK": (
        "take-or-pay", "ore body", "reserve life", "smelter", "wafer",
        "channel inventory", "dealer inventory", "seats per customer",
        "aftermarket parts"),
    "COMMODITY_PRODUCER": (
        "net revenue retention", "seats per customer", "renewal rate",
        "net interest margin", "deposit repricing", "annual recurring revenue"),
    "MANUFACTURE_AND_AFTERMARKET": (
        "net revenue retention", "seats per customer", "annual recurring "
        "revenue", "net interest margin", "deposit repricing", "ore body"),
    "DESIGN_AND_MANUFACTURE": (
        "net revenue retention", "seats per customer", "net interest margin",
        "deposit repricing", "ore body", "reserve life"),
    "BRANDED_CONSUMER": (
        "net revenue retention", "seats per customer", "net interest margin",
        "reserve life", "wafer"),
    "REGULATED_PRODUCT_OR_PROVIDER": (
        "net revenue retention", "seats per customer", "net interest margin",
        "ore body", "take-or-pay"),
    "CONTRACTED_OR_RATE_BASE_ASSETS": (
        "net revenue retention", "seats per customer", "wafer", "ore body"),
    "PEOPLE_OR_ROUTE_BASED_SERVICES": (
        "net revenue retention", "wafer", "ore body", "net interest margin"),
}


#: §19. A counterfactual asserted as history. "Would have grown 20%" is a
#: claim about a world that did not happen, stated in the grammar of one that
#: did — the single most dangerous sentence this page can produce.
_CF_AS_FACT = re.compile(
    r"\bwould have (?:grown|reached|earned|delivered|produced|been worth|"
    r"outperformed|avoided|prevented)\b"
    r"|\bthe company would have\b(?!.{0,40}\bplausibl)"
    r"|\bwas always going to\b"
    r"|\bwould definitely have\b", re.I)

#: A modelled figure presented as a retrieved one.
_FAKE_CONSENSUS = re.compile(
    r"\b(?:wall street|analysts?|the street|consensus) (?:expected|"
    r"forecast|predicted|estimated)\b", re.I)


def _quote(text: str, match: re.Match, width: int = 90) -> str:
    start = max(0, match.start() - width // 3)
    end = min(len(text), match.end() + width)
    return " ".join(text[start:end].split())


def _outside_quotes(text: str) -> str:
    """Text with quoted passages removed.

    An excerpt shown as evidence is allowed to elide and to contain the
    company's marketing; it is displayed as somebody else's words. This strips
    the straight- and curly-quoted spans so those detectors see only prose the
    product is speaking in its own voice.
    """
    without = re.sub(r"[“”\"][^“”\"]{20,}"
                     r"[“”\"]", " ", text)
    return without


def scan(text: str, *, surface: str = "", company: str = "",
         model_class: str = "", other_companies: Sequence[str] = (),
         min_chars: int = 400) -> List[Finding]:
    """Every defect visible in one page's customer-facing text.

    `text` is VISIBLE TEXT -- tags and style blocks already stripped. Passing
    HTML produces false positives on class names, which is itself a defect
    this module had in its first draft.
    """
    text = " ".join(str(text or "").split())
    out: List[Finding] = []

    def add(code, evidence, detail=""):
        detector = BY_CODE.get(code)
        if detector is None:
            return
        if detector.surfaces and surface not in detector.surfaces:
            return
        if surface in detector.except_surfaces:
            return
        out.append(Finding(code=code, severity=detector.severity,
                           surface=surface, evidence=evidence,
                           repair_class=detector.repair_class,
                           detail=detail or detector.what))

    prose = _outside_quotes(text)

    for pattern, code in ((_REFUSAL, "STRATEGIC_REFUSAL_COLLAPSE"),
                          (_NO_COMPETITOR, "COMPETITOR_MISSING"),
                          (_MARKETING, "WEBSITE_COPY_LEAK"),
                          (_FALSE_CONFIDENCE, "FALSE_CONFIDENCE"),
                          (_AI_VOICE, "AI_VOICE"),
                          (_HINDSIGHT, "HINDSIGHT_LEAK"),
                          (_ACTIVITY_AS_LEARNING,
                           "LEARNING_ACTIVITY_CONFUSION"),
                          (_UNSUPPORTED_PRECISION, "UNSUPPORTED_PRECISION"),
                          (_IMPLEMENTATION, "IMPLEMENTATION_VOCABULARY")):
        found = pattern.search(prose)
        if found:
            add(code, _quote(prose, found))

    found = _TRUNCATED.search(prose)
    if found:
        add("TRUNCATED_SENTENCE", _quote(prose, found))

    found = _RAW_ENUM.search(text)
    if found:
        add("RAW_ENUM", _quote(text, found))

    found = _RAW_ID.search(text)
    if found:
        add("RAW_EVIDENCE_ID", _quote(text, found))

    found = _TAB_GRID.search(text)
    if found:
        add("NAVIGATION_GRID", _quote(text, found))

    # EXCESSIVE_HEDGING is a density judgement, not a phrase match. Four or
    # more distinct caveats on one page is where a reading stops surviving
    # them; below that the caveats are doing their job.
    hedges = {m.group(0).lower() for m in _HEDGE.finditer(prose)}
    if len(hedges) >= 4:
        add("EXCESSIVE_HEDGING",
            "; ".join(sorted(hedges)[:5]),
            f"{len(hedges)} distinct caveats on one page")

    if company:
        head = company.split(",")[0].split(" Inc")[0].strip()
        if head and len(head) > 2 and head.lower() not in text.lower():
            add("GENERIC_STRATEGY", text[:120],
                f"the subject {company!r} is never named")
    for other in other_companies or ():
        if other and other.lower() in text.lower() \
                and other.lower() != (company or "").lower():
            add("WRONG_COMPANY", other,
                f"another subject, {other!r}, appears on this page")

    for word in _MODEL_FOREIGN.get(model_class, ()):
        found = re.search(re.escape(word), prose, re.I)
        if found:
            add("TEMPLATE_COLLAPSE", _quote(prose, found),
                f"{word!r} belongs to a different business model than "
                f"{model_class}")
            break

    # --- §19/§24. The two ways a bounded claim becomes an unbounded one ----
    found = _CF_AS_FACT.search(prose)
    if found:
        add("COUNTERFACTUAL_PRESENTED_AS_FACT", _quote(prose, found),
            "an alternative path is stated in the grammar of history")
    found = _FAKE_CONSENSUS.search(prose)
    if found:
        add("UNLABELED_MODELED_EXPECTATION", _quote(prose, found),
            "a modelled expectation is attributed to analysts who were never "
            "retrieved")

    # --- §14/§42. Absence that terminates ----------------------------------
    #
    # Delegated rather than reimplemented: `founder_brief.absence` owns the
    # adjudication and is what the customer-copy sweep runs, and two copies
    # of a phrase list drift apart within a cycle.
    try:
        from intent_engine.founder_brief import absence as _AB
        for dead in _AB.adjudicate(text)[:3]:
            add("CUSTOMER_ABSENCE_COPY", dead.sentence[:180],
                f"{dead.phrase!r} with nothing the reader can do about it")
    except Exception:                                       # noqa: BLE001
        pass

    if len(text) < min_chars:
        add("EMPTY_SURFACE", text[:120],
            f"{len(text)} characters of visible text")
    return out


# ===========================================================================
# §76, §89 — the history chart's own gate
# ===========================================================================
#: Each series must be identifiable in the RENDERED page by the name the
#: simulator gives it AND by the badge that says what kind of claim it is.
#: Checking the SVG alone would pass a chart whose legend lies; checking the
#: legend alone would pass a legend with no chart under it.
_SERIES_MARKERS = {
    "MISSING_ACTUAL": ("Actual path", "ln-actual"),
    "MISSING_MARKET_EXPECTATION": ("Market expectation", "ln-expect"),
    "MISSING_COUNTERFACTUAL": ("Better strategy", "ln-counter"),
}


def scan_history_chart(html: str, *, surface: str = "history"
                       ) -> List[Finding]:
    """Whether the history page actually carries a three-line simulator.

    Runs on HTML rather than on visible text, deliberately and unusually: the
    thing being asserted is that a CHART exists, and a chart is markup. Every
    other detector in this module reads prose because every other defect was
    a sentence; this one is checking for a drawing.
    """
    html = str(html or "")
    out: List[Finding] = []

    def add(code, evidence, detail=""):
        detector = BY_CODE.get(code)
        if detector is None:
            return
        out.append(Finding(code=code, severity=detector.severity,
                           surface=surface, evidence=evidence[:200],
                           repair_class=detector.repair_class, detail=detail))

    if "<svg" not in html or "ln-actual" not in html:
        # A page with no chart is only a defect when a chart was possible.
        # The bounded fallback names what it would take to draw one, which is
        # the correct behaviour for a company with no filed series — so it is
        # recognised here rather than punished.
        if "What would draw this chart" in html:
            return out
        add("HISTORY_TEXT_ONLY", html[:160],
            "no chart markup and no bounded explanation of its absence")
        return out
    for code, (title, css_class) in _SERIES_MARKERS.items():
        if css_class in html and title in html:
            continue
        if code == "MISSING_MARKET_EXPECTATION":
            add(code, title, f"{title!r} is not drawn or not labelled")
    if "Modelled" not in html:
        add("UNLABELED_MODELED_EXPECTATION", "legend",
            "the expectation series carries no MODELLED badge")
    if "ln-counter" in html and "Counterfactual" not in html:
        add("COUNTERFACTUAL_PRESENTED_AS_FACT", "legend",
            "the alternative series carries no COUNTERFACTUAL badge")
    return out


def history_is_templated(pages: Dict[str, str], *, threshold: float = 0.6
                         ) -> List[Tuple[str, str, float]]:
    """§78. Pairs of companies whose history reads the same. Empty is a pass.

    TWO THINGS HAD TO BE MEASURED CORRECTLY BEFORE THIS SAID ANYTHING.

    WHAT is compared: the DATE PANELS, not the page. Most of a history page
    is the legend, the axis definition and the explanation of what a
    counterfactual is — text that MUST be identical on every company. Whole-
    page comparison scored every pair high and told us nothing.

    HOW it is compared: the share of IDENTICAL SENTENCES, not character
    similarity. Two panels built from one template with different numbers in
    it score 0.94 on characters and are not templated — they say different
    things about different companies in a shared voice, which is what a
    product voice IS. What a template looks like is whole sentences repeated
    verbatim, and counting those says exactly how much of the argument was
    reused rather than reasoned.
    """
    keys = sorted(pages)
    panels = {k: _panel_sentences(pages[k]) for k in keys}
    out = []
    for i, left in enumerate(keys):
        for right in keys[i + 1:]:
            a, b = panels[left], panels[right]
            if not a or not b:
                continue
            shared = len(a & b) / max(len(a | b), 1)
            if shared >= threshold:
                out.append((left, right, round(shared, 3)))
    return out


def _panel_sentences(page: str) -> set:
    """The date-panel sentences of a history page, as a set."""
    panel = _date_panels(page)
    return {s.strip() for s in re.split(r"(?<=[.!?])\s+", panel)
            if len(s.strip()) > 40}


#: The date panel starts here and ends here. Everything outside is the
#: product's own voice — legend, axis definition, method note — and is
#: SUPPOSED to be identical on every company's page.
_PANEL_START = "What was true then"
_PANEL_END = "The same figures as a table"


def _date_panels(page: str) -> str:
    """The part of a history page that is about THIS company.

    Comparing whole pages scored Cloudflare and Shopify at 0.92 and would
    have scored any two companies that high, because most of a history page
    is the legend, the axis definition and the explanation of what a
    counterfactual is — text that must be identical everywhere. What has to
    differ is the six cards, and they are what is compared.
    """
    text = " ".join(str(page or "").split())
    start = text.find(_PANEL_START)
    if start < 0:
        return ""
    end = text.find(_PANEL_END, start)
    return text[start:end if end > start else len(text)]


def worst(findings: Sequence[Finding]) -> str:
    """The most severe severity present, or "" for a clean page."""
    for level in (SEV1, SEV2, SEV3, WARNING):
        if any(f.severity == level for f in findings):
            return level
    return ""


def summarise(findings: Sequence[Finding]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts


# ===========================================================================
# §21 — the belief layer, checked against the OBJECTS
# ===========================================================================
def scan_belief_layer(read, *, surface: str = "read",
                      other_reads: Sequence = ()) -> List[Finding]:
    """Defects in the belief layer that no regular expression could find.

    WHY THIS READS OBJECTS AND NOT PROSE. Every other detector here works on
    the visible text, because every other defect was a sentence. These are
    not. "Manufactured contrarianism" and "a hypothesis nothing could settle"
    are properties of how a claim was ARRIVED AT, and the page shows only the
    claim. The engine records the derivation, so that is what is inspected.

    `other_reads` enables the cross-company check: a strategic sentence is a
    defect only when a SECOND company produced the same one, which is why it
    cannot be found by looking at one report (§28's rule about clusters, in
    miniature).

    THE SURFACE IS "read", NOT "full". These findings are about the object,
    not about a page's prose, and `_surface_score` charges every finding on a
    surface against that surface's writing quality. Reporting them as "full"
    dropped `full_analysis_quality` from 10.0 to 6.0 on two companies whose
    full analysis was not the thing at fault -- a defect in the competitive
    ladder being charged to the paragraph that rendered it.
    """
    out: List[Finding] = []

    def add(code, evidence, detail=""):
        detector = BY_CODE.get(code)
        if detector is None:
            return
        out.append(Finding(code=code, severity=detector.severity,
                           surface=surface, evidence=str(evidence)[:200],
                           repair_class=detector.repair_class,
                           detail=detail or detector.what))

    beliefs = tuple(getattr(read, "market_beliefs", ()) or ())
    challenges = tuple(getattr(read, "belief_challenges", ()) or ())
    ground = getattr(read, "competitive_ground", None)
    graph = getattr(read, "assumption_chain", None)
    action = getattr(read, "level6_action", None)
    company = str(getattr(read, "company", "") or "")

    for belief in beliefs:
        if getattr(belief, "source_basis", "") != "OBSERVED" \
                and not str(getattr(belief, "basis_detail", "") or "").strip():
            add("MARKET_BELIEF_UNSUPPORTED", belief.proposition)
        if getattr(belief, "belief_type", "") == "MANAGEMENT" \
                and getattr(belief, "source_basis", "") != "OBSERVED":
            # A claim about what management believes must be quoted. Inferring
            # it and presenting it as theirs is putting words in their mouth.
            add("MANAGEMENT_BELIEF_MISATTRIBUTED", belief.proposition)

    moved = {"WEAKENED", "REVISED", "RETIRED"}
    attacked = 0
    for row in challenges:
        if getattr(row, "disposition", "") in moved \
                and not str(getattr(row, "strongest_contradiction", "")
                            or "").strip():
            add("CONTRARIANISM_WITHOUT_EVIDENCE", row.belief_id)
        if getattr(row, "alternative_explanations", ()) or \
                getattr(row, "unconventional_hypotheses", ()):
            attacked += 1
        for hypothesis in getattr(row, "unconventional_hypotheses", ()) or ():
            if not str(getattr(hypothesis, "falsifier", "") or "").strip() \
                    or not str(getattr(hypothesis, "test", "") or "").strip():
                add("IMPOSSIBLE_HYPOTHESIS_UNBOUNDED", hypothesis.hypothesis)
            # A hypothesis that never names this company, or anything this run
            # found about it, is the generic provocation §5 forbids.
            text = f"{hypothesis.hypothesis} {hypothesis.why_plausible}"
            if company and company.split()[0].lower() not in text.lower():
                add("IMPOSSIBLE_HYPOTHESIS_GENERIC", hypothesis.hypothesis)
    if challenges and not attacked:
        add("BELIEF_CONFIRMATION_BIAS",
            f"{len(challenges)} belief(s), none attacked with an alternative")

    field = getattr(read, "explanation_field", None)
    if field is None or len(getattr(field, "explanations", ()) or ()) < 2:
        add("ALTERNATIVE_EXPLANATION_MISSING",
            getattr(field, "question", "") or "no competing explanations")

    if ground is not None:
        rivals = tuple(getattr(ground, "rivals", ()) or ())
        kinds = set(getattr(r, "kind", "") for r in rivals)
        grounded = tuple(getattr(ground, "subject_grounded", ()) or ())
        attributed = tuple(r for r in rivals
                           if getattr(r, "is_attributed", False))
        if rivals and not (grounded or attributed):
            add("COMPETITOR_TOO_GENERIC",
                ", ".join(r.identity for r in rivals[:3]))
        if rivals and not (kinds - {"DIRECT", "PEER"}):
            add("SUBSTITUTE_MISSING",
                ", ".join(sorted(kinds)) or "no kinds recorded")
        if rivals and "BUILD_IN_HOUSE" not in kinds:
            add("INTERNAL_BUILD_IGNORED", ", ".join(sorted(kinds)))
        if rivals and not ({"AI_REPLACEMENT", "AI_ENTRANT"} & kinds):
            add("AI_DISPLACEMENT_UNTESTED", ", ".join(sorted(kinds)))
        if rivals and not any(getattr(r, "likely_response", "")
                              for r in rivals):
            add("LEVEL_K_REACTION_MISSING",
                "no rival carries a likely response")

    if graph is not None:
        for link in getattr(graph, "links", ()) or ():
            if not str(getattr(link, "because", "") or "").strip():
                add("ASSUMPTION_GRAPH_BROKEN", f"{link.frm} -> {link.to}")
        if graph.links and graph.weakest_critical is None \
                and any(getattr(l, "standing", "") in ("ASSUMED", "UNTESTED",
                                                       "CONTRADICTED")
                        for l in graph.links):
            add("WEAKEST_ASSUMPTION_MISSING", graph.conclusion)

    if action is not None:
        if not str(getattr(action, "falsifier", "") or "").strip():
            add("FALSIFIER_MISSING", getattr(action, "action_now", ""))
        if not str(getattr(action, "minimum_viable_experiment", "")
                   or "").strip():
            add("MVE_MISSING", getattr(action, "action_now", ""))

    # --- cross-company: a cluster needs two members ------------------------
    mine = _strategy_signature(read)
    for other in other_reads or ():
        if other is read:
            continue
        if str(getattr(other, "company", "")) == company:
            continue
        theirs = _strategy_signature(other)
        shared = mine & theirs
        if len(shared) >= 2:
            add("CROSS_COMPANY_STRATEGY_COLLAPSE",
                f"{company} and {getattr(other, 'company', '?')} share "
                f"{len(shared)} strategic sentence(s)",
                detail=sorted(shared)[0][:160])
            break
    return out


def _strategy_signature(read) -> set:
    """The sentences that are supposed to be about ONE company.

    Compared as whole sentences rather than by character overlap: two reports
    share a great deal of scaffolding by design, and a similarity ratio over
    the whole page is dominated by it. What matters is whether the same
    STRATEGIC CLAIM appears twice.
    """
    out = set()
    for belief in getattr(read, "market_beliefs", ()) or ():
        out.add(str(getattr(belief, "proposition", "")).strip())
    for row in getattr(read, "belief_challenges", ()) or ():
        for hypothesis in getattr(row, "unconventional_hypotheses", ()) or ():
            out.add(str(getattr(hypothesis, "hypothesis", "")).strip())
    action = getattr(read, "level6_action", None)
    if action is not None:
        out.add(str(getattr(action, "action_now", "")).strip())
    experiment = getattr(read, "belief_experiment", None)
    if experiment is not None:
        out.add(str(getattr(experiment, "test", "")).strip())
    return {s for s in out if len(s) > 40}
