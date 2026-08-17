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

    if len(text) < min_chars:
        add("EMPTY_SURFACE", text[:120],
            f"{len(text)} characters of visible text")
    return out


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
