"""Competitor intelligence as a contract, not as whatever happened to be read.

THE FAILURE THIS REPLACES
-------------------------
Competitive position was substantive only when a page whose `source_class`
happened to be `competitor` was retrieved. Shopify had one and got a real
section; Palantir did not and got a stated absence. Same product, same
question, and the difference was retrieval luck rather than anything about the
two companies.

The material was there the whole time. A 10-K or 10-Q carries a Competition
section that names real rivals in the company's own words, with overlap
language attached -- and since the periodic report started arriving, it is in
the evidence of every listed company's run.

WHAT MAKES A NAME A COMPETITOR
-------------------------------
Not proximity. A name printed near the subject's name establishes nothing: the
same paragraph of a proxy statement lists the executive-compensation peer
group, which is chosen for revenue and headcount comparability and routinely
contains companies in unrelated businesses. Treating that list as competitive
evidence is how a founder gets told their rival is a company they have never
lost a deal to.

So every mention is classified, and only one class may support a conclusion:

    CLAIM_RELEVANT       the passage states an OVERLAP -- same buyer, same
                         job, a substitute product, a migration, a head-to-head
    COMPETITIVE_CONTEXT  named in a discussion of competition, but with no
                         specific overlap claim. Frames the market; corrobo-
                         rates nothing.
    BARE_MENTION         the name appears with no competitive framing at all
    STALE                a competitive claim old enough that the market has
                         probably moved
    IRRELEVANT           compensation peer groups, investor lists, board
                         memberships, customer lists

`supports_conclusion` is True for CLAIM_RELEVANT alone. COMPETITIVE_CONTEXT is
allowed to shape framing and is explicitly barred from corroborating.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Sequence, Tuple

SCHEMA_VERSION = "competitor_intel.v1"

# --- relationship types -----------------------------------------------------
DIRECT_COMPETITOR = "DIRECT_COMPETITOR"
PLATFORM_ALTERNATIVE = "PLATFORM_ALTERNATIVE"
INTERNAL_BUILD = "INTERNAL_BUILD"
CONSULTING_ALTERNATIVE = "CONSULTING_ALTERNATIVE"
PARTNER_AND_COMPETITOR = "PARTNER_AND_COMPETITOR"
ADJACENT_SUBSTITUTE = "ADJACENT_SUBSTITUTE"

RELATIONSHIPS = frozenset({
    DIRECT_COMPETITOR, PLATFORM_ALTERNATIVE, INTERNAL_BUILD,
    CONSULTING_ALTERNATIVE, PARTNER_AND_COMPETITOR, ADJACENT_SUBSTITUTE})

RELATIONSHIP_WORDS = {
    DIRECT_COMPETITOR: "competes for the same buyer with a comparable product",
    PLATFORM_ALTERNATIVE: "a platform a buyer could standardise on instead",
    INTERNAL_BUILD: "the buyer's own engineering team building it in-house",
    CONSULTING_ALTERNATIVE: "a services firm delivering the same outcome as a "
                            "project rather than a product",
    PARTNER_AND_COMPETITOR: "a partner in some deals and a rival in others",
    ADJACENT_SUBSTITUTE: "a different product that removes the same problem",
}

# --- relevance --------------------------------------------------------------
CLAIM_RELEVANT = "CLAIM_RELEVANT"
COMPETITIVE_CONTEXT = "COMPETITIVE_CONTEXT"
BARE_MENTION = "BARE_MENTION"
STALE = "STALE"
IRRELEVANT = "IRRELEVANT"

#: Only this class may corroborate a conclusion.
CONCLUSIVE = frozenset({CLAIM_RELEVANT})

#: A competitive claim older than this describes a market that has probably
#: moved. Three years is generous for software and deliberately so -- the
#: point is to catch a 2019 filing being read as current, not to expire
#: last year's 10-K.
STALE_AFTER_DAYS = 365 * 3

#: Contexts where a list of company names is NOT a competitor list. Checked
#: first, because these passages also contain the competitive-sounding words
#: below -- a compensation peer group is literally introduced as a list of
#: "comparable companies".
_DISQUALIFYING = (
    r"compensation\s+peer\s+group", r"peer\s+group\s+for\s+purposes\s+of",
    r"compensation\s+committee", r"say[- ]on[- ]pay",
    r"executive\s+compensation", r"benchmark(?:ing)?\s+compensation",
    r"named\s+executive\s+officers?", r"total\s+shareholder\s+return\s+peer",
    r"board\s+of\s+directors\s+of", r"serves?\s+on\s+the\s+board",
    r"our\s+customers\s+include", r"investors\s+include",
    r"underwriters?", r"index\s+includes",
)

#: An explicit overlap: same buyer, same job, a substitute, a switch. These are
#: what turn a name into a claim.
_OVERLAP = (
    r"compet(?:e|es|ing|itor)\s+(?:with|against)", r"\bversus\b", r"\bvs\.?\b",
    r"alternative\s+to", r"instead\s+of", r"rather\s+than\s+(?:using|buying)",
    r"switch(?:ed|ing)?\s+(?:from|to)", r"migrat(?:e|ed|ing|ion)\s+(?:from|to)",
    r"replac(?:e|ed|ing|ement)\s+(?:for|of)?", r"displac(?:e|ed|ing)",
    r"same\s+(?:customers?|buyers?|market|use\s+case)",
    r"head[- ]to[- ]head", r"win(?:s)?\s+(?:against|over)",
    r"lost?\s+(?:deals?\s+)?to", r"in\s+place\s+of",
    r"build\s+(?:it\s+)?(?:in[- ]house|internally|themselves)",
    r"in[- ]house\s+(?:team|solution|alternative|development)",
)

#: The market IS competitive language -- framing without a specific claim.
_CONTEXT = (
    r"competitive\s+(?:landscape|environment|market|pressures?)",
    r"highly\s+competitive", r"principal\s+competitors?",
    r"we\s+compete", r"our\s+competitors?", r"competition\s+from",
    r"market\s+participants", r"other\s+(?:providers|vendors|platforms)",
)


class CompetitorRejected(ValueError):
    """A competitor tried to appear without evidence of overlap."""


def _matches(patterns, text: str) -> Optional[str]:
    for pattern in patterns:
        found = re.search(pattern, text, re.I)
        if found:
            return found.group(0)
    return None


@dataclass(frozen=True)
class Mention:
    """One appearance of a name in one retrieved passage."""
    name: str
    passage: str
    source_title: str = ""
    source_class: str = ""
    evidence_id: str = ""
    date: str = ""


@dataclass(frozen=True)
class Assessment:
    relevance: str
    reason: str
    matched_on: str = ""

    @property
    def supports_conclusion(self) -> bool:
        return self.relevance in CONCLUSIVE


def assess(mention: Mention, *, today: str = "") -> Assessment:
    """Classify one mention. Order of checks is the whole design.

    Disqualifying context is tested BEFORE overlap language, because a
    compensation peer group passage contains both -- it introduces its list as
    comparable companies in a competitive industry, and reads as competitive
    evidence to anything matching on keywords alone.
    """
    text = mention.passage or ""
    if not mention.name or mention.name.lower() not in text.lower():
        return Assessment(IRRELEVANT, "the name does not appear in the passage")

    disqualified = _matches(_DISQUALIFYING, text)
    if disqualified:
        return Assessment(
            IRRELEVANT,
            f"the passage is a {disqualified.lower()} list, which is chosen "
            f"for size comparability rather than for competing in the same "
            f"market", disqualified)

    overlap = _matches(_OVERLAP, text)
    context = _matches(_CONTEXT, text)

    if not overlap and not context:
        return Assessment(
            BARE_MENTION,
            "the name appears with nothing said about overlapping customers, "
            "products or use cases, so it establishes only that the name was "
            "printed")

    if today and mention.date and _stale(mention.date, today):
        return Assessment(
            STALE,
            f"the claim is dated {mention.date}, old enough that the "
            f"competitive position it describes may have moved",
            overlap or context)

    if overlap:
        return Assessment(
            CLAIM_RELEVANT,
            "the passage states an overlap in customers, product or use case",
            overlap)
    return Assessment(
        COMPETITIVE_CONTEXT,
        "the passage discusses competition without claiming a specific "
        "overlap, so it frames the market without corroborating a position",
        context)


def _stale(when: str, today: str) -> bool:
    try:
        return (date.fromisoformat(today[:10])
                - date.fromisoformat(when[:10])).days > STALE_AFTER_DAYS
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class Competitor:
    """One alternative a buyer could choose instead, and what says so."""
    name: str
    relationship: str
    overlap: str
    evidence_ids: Tuple[str, ...] = ()
    source_titles: Tuple[str, ...] = ()
    relevance: str = CLAIM_RELEVANT
    reason: str = ""
    matched_on: str = ""
    date: str = ""
    stronger_where: str = ""
    subject_stronger_where: str = ""
    decision_implication: str = ""
    limitation: str = ""
    #: §3. WHAT THIS ENTITY IS, AND WHETHER A CUSTOMER COULD CHOOSE IT.
    #
    # `relationship` above says how the alternative takes the decision away
    # ASSUMING it is one. These say whether it is one at all, and they exist
    # because three live introductions named an index, a payer programme and
    # a captive lender's rivals as the companies contesting the subject's
    # market. Defaults keep every existing construction valid; the extractor
    # fills them from `executive.competitive_qualification`.
    qualification_state: str = ""
    entity_type: str = ""
    contest_owner: str = ""
    focal_need: str = ""
    substitution_mechanism: str = ""
    routed_section: str = ""

    def __post_init__(self):
        if self.relationship not in RELATIONSHIPS:
            raise CompetitorRejected(
                f"unknown relationship {self.relationship!r}")
        if not self.evidence_ids:
            raise CompetitorRejected(
                f"{self.name}: a competitor must name the evidence that "
                f"establishes it")
        if not self.overlap:
            raise CompetitorRejected(
                f"{self.name}: a competitor must state the overlapping buyer, "
                f"product or job — a name near the subject's name is not a "
                f"competitive claim")

    @property
    def supports_conclusion(self) -> bool:
        return self.relevance in CONCLUSIVE

    def as_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "name": self.name,
            "relationship": self.relationship,
            "relationship_meaning": RELATIONSHIP_WORDS.get(self.relationship,
                                                           ""),
            "overlap": self.overlap,
            "evidence_ids": list(self.evidence_ids),
            "source_titles": list(self.source_titles),
            "relevance": self.relevance,
            "reason": self.reason,
            "matched_on": self.matched_on,
            "date": self.date,
            "stronger_where": self.stronger_where,
            "subject_stronger_where": self.subject_stronger_where,
            "decision_implication": self.decision_implication,
            "limitation": self.limitation,
            "supports_conclusion": self.supports_conclusion,
            "qualification_state": self.qualification_state,
            "entity_type": self.entity_type,
            "contest_owner": self.contest_owner,
            "focal_need": self.focal_need,
            "substitution_mechanism": self.substitution_mechanism,
            "routed_section": self.routed_section,
        }

    @property
    def may_contest(self) -> bool:
        """§3. May this fill a competitive claim on a customer-facing page?

        An unqualified competitor — one built before this field existed, or
        by a caller that does not run the qualification — keeps the old
        behaviour, because the qualification is what narrows the claim and a
        missing qualification is not evidence of anything.
        """
        from intent_engine.executive.competitive_qualification import (
            MAY_CONTEST,
        )
        return (not self.qualification_state
                or self.qualification_state in MAY_CONTEST)


def corroborating(competitors: Sequence[Competitor]) -> List[Competitor]:
    """Only the competitors a conclusion may rest on."""
    return [c for c in competitors if c.supports_conclusion]


def framing_only(competitors: Sequence[Competitor]) -> List[Competitor]:
    """Named in a competition discussion, but corroborating nothing."""
    return [c for c in competitors
            if c.relevance == COMPETITIVE_CONTEXT]
