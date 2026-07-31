"""Typed independent evidence — independence and relevance, kept apart.

WHY THE PREVIOUS GATE FAILED
----------------------------
`no_outside_source` checked membership in one hardcoded list of source classes.
That list conflated two conditions which are not the same thing:

  1. **Independence** — is the AUTHOR someone other than the subject?
  2. **Relevance** — does this evidence bear on THIS hypothesis's claim?

It got both wrong at the edges. An SC 13D filed by an activist about a company
is authored by the activist and is genuinely independent, and the old gate
rejected it because the class was not on the list. Meanwhile customer reviews
were accepted as corroboration for *any* claim, including governance claims
they say nothing about.

The measured symptom was `independent_source: 0/28` on every live run. The
diagnosis that mattered was not "G2 returns 403" — it was that the model could
not express *what kind* of corroboration a given claim actually needs.

WHAT THIS DOES NOT DO
---------------------
It does not make trading easier. Every category is still required to be
independent of the subject, and a hypothesis must still name what would
corroborate it. What changes is that the requirement is now *stated per
hypothesis* instead of being one global list that is wrong for most claims.

The Day 6 temptation — relabelling SC 13G as an outside source to unlock
trading — becomes structurally impossible rather than a matter of restraint.
A 13G is INSTITUTIONAL. A customer-adoption hypothesis requires CUSTOMER_VOICE.
No relabelling connects them, because the category a filing belongs to is a
fact about its author, not a knob.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set


class Category:
    """Evidence categories, kept distinct and never collapsed into a score.

    A single "corroboration score" would let strong evidence of the wrong kind
    substitute for weak evidence of the right kind, which is the failure this
    whole module exists to prevent.
    """
    COMPANY = "company"                 # the subject speaking about itself
    CUSTOMER_VOICE = "customer_voice"   # G2, Trustpilot, app-store reviews
    REGULATORY = "regulatory"           # SEC/EDGAR, SEDAR, FCA — by a regulator
    INSTITUTIONAL = "institutional"     # 13F, SC 13D/G, insider filings
    INDUSTRY = "industry"               # trade journals, industry bodies
    MACRO = "macro"                     # FRED, central banks, statistics offices
    ALTERNATIVE = "alternative"         # supply chain, hiring, traffic, shipping
    ANALYST = "analyst"                 # estimate revisions, consensus changes


# Independence is a fact about AUTHORSHIP, not a judgement about quality. A
# company's own 10-Q is legally binding and still not independent; a scrappy
# trade journal is independent and possibly wrong. The gate is about who is
# speaking, and quality is a separate axis this deliberately does not encode.
_INDEPENDENT: FrozenSet[str] = frozenset({
    Category.CUSTOMER_VOICE, Category.REGULATORY, Category.INSTITUTIONAL,
    Category.INDUSTRY, Category.MACRO, Category.ALTERNATIVE, Category.ANALYST,
})

# Where each ingestion source_class lands. `investor_material` is the important
# one: an SEC filing BY THE COMPANY is the company speaking, however official
# the venue. A filing by a THIRD PARTY about the company is institutional, and
# the ingestion layer distinguishes them by who filed.
_SOURCE_CLASS_TO_CATEGORY: Dict[str, str] = {
    "company_owned": Category.COMPANY,
    "executive_statement": Category.COMPANY,
    "investor_material": Category.COMPANY,      # the company's own filing
    "customer_voice": Category.CUSTOMER_VOICE,
    "independent_reporting": Category.INDUSTRY,
    "competitor_statement": Category.INDUSTRY,
    "analyst_coverage": Category.ANALYST,
    "regulator_filing": Category.REGULATORY,
    "third_party_filing": Category.INSTITUTIONAL,
    "macro_series": Category.MACRO,
    "alternative_data": Category.ALTERNATIVE,
}


def category_of(source_class: str) -> str:
    return _SOURCE_CLASS_TO_CATEGORY.get(str(source_class or ""),
                                         Category.COMPANY)


def is_independent(category: str) -> bool:
    return category in _INDEPENDENT


@dataclass(frozen=True)
class EvidenceRequirement:
    """What would corroborate a specific claim.

    `required` is a set of ALTERNATIVES, not a conjunction: any one of them
    satisfies the requirement. A customer-adoption claim is corroborated by
    customer voice OR by an industry body reporting the same adoption — but not
    by a macro series, which cannot speak to one company's customers.
    """
    required: FrozenSet[str]
    optional: FrozenSet[str] = field(default_factory=frozenset)

    def satisfied_by(self, present: Iterable[str]) -> bool:
        return bool(self.required & set(present))

    def missing_from(self, present: Iterable[str]) -> List[str]:
        return [] if self.satisfied_by(present) else sorted(self.required)


# Requirements per hypothesis kind. Each says what would actually check the
# claim — which is why they differ. Getting this list wrong is a reasoning
# error, not a configuration one, so each entry names why.
REQUIREMENTS: Dict[str, EvidenceRequirement] = {
    # Are customers actually adopting? Only customers or an industry observer
    # can say. A filing cannot.
    "customer_adoption": EvidenceRequirement(
        required=frozenset({Category.CUSTOMER_VOICE, Category.INDUSTRY}),
        optional=frozenset({Category.ALTERNATIVE, Category.MACRO})),
    # Who owns it and who is pressuring the board. Third-party filings ARE the
    # evidence here, and customer reviews are irrelevant however plentiful.
    "governance": EvidenceRequirement(
        required=frozenset({Category.REGULATORY, Category.INSTITUTIONAL}),
        optional=frozenset({Category.INDUSTRY})),
    # Sensitivity to rates, inflation, cycle. Macro series are the check.
    "macro_sensitivity": EvidenceRequirement(
        required=frozenset({Category.MACRO}),
        optional=frozenset({Category.INDUSTRY, Category.ANALYST})),
    # Is the market's expectation moving? Analyst revisions are that, directly.
    "expectation_shift": EvidenceRequirement(
        required=frozenset({Category.ANALYST, Category.INDUSTRY}),
        optional=frozenset({Category.INSTITUTIONAL})),
    # Competitive position: an outside observer or a competitor's own words.
    "competitive_position": EvidenceRequirement(
        required=frozenset({Category.INDUSTRY, Category.ALTERNATIVE}),
        optional=frozenset({Category.CUSTOMER_VOICE})),
    # A price/momentum claim asserts nothing about the business, so no company
    # evidence can corroborate it -- and none is required. It is gated
    # elsewhere, on dated evidence and on the market signal itself.
    "price_behaviour": EvidenceRequirement(required=frozenset()),
}

# What a claim needs when its kind is unknown. Deliberately the strictest
# non-empty option rather than an empty set: an unclassified hypothesis must
# not become the easy path to a position.
DEFAULT_KIND = "customer_adoption"


@dataclass(frozen=True)
class Corroboration:
    """The verdict, and enough detail to say precisely why."""
    hypothesis_kind: str
    present: tuple
    independent_present: tuple
    required: tuple
    missing: tuple
    satisfied: bool

    @property
    def reason(self) -> str:
        if self.satisfied:
            return (f"corroborated for a {self.hypothesis_kind} claim by "
                    f"{', '.join(self.independent_present)}")
        have = (", ".join(self.independent_present)
                if self.independent_present else "none")
        return (f"a {self.hypothesis_kind} claim needs "
                f"{' or '.join(self.missing)}; independent evidence present: "
                f"{have}")

    def as_dict(self) -> dict:
        return {"hypothesis_kind": self.hypothesis_kind,
                "present": list(self.present),
                "independent_present": list(self.independent_present),
                "required": list(self.required),
                "missing": list(self.missing),
                "satisfied": self.satisfied, "reason": self.reason}


def assess(source_classes: Sequence[str], *,
           hypothesis_kind: str = DEFAULT_KIND) -> Corroboration:
    """Is this claim corroborated by evidence of the right kind?

    Two conditions, checked separately and never traded off: the evidence must
    be authored by someone other than the subject, AND it must be of a category
    that can speak to this claim.
    """
    kind = hypothesis_kind if hypothesis_kind in REQUIREMENTS else DEFAULT_KIND
    requirement = REQUIREMENTS[kind]
    categories = {category_of(sc) for sc in source_classes or ()}
    independent = {c for c in categories if is_independent(c)}
    missing = requirement.missing_from(independent)
    return Corroboration(
        hypothesis_kind=kind,
        present=tuple(sorted(categories)),
        independent_present=tuple(sorted(independent)),
        required=tuple(sorted(requirement.required)),
        missing=tuple(missing),
        satisfied=not missing)


# ---------------------------------------------------------------------------
# TWO DIMENSIONS: who produced it, and what it is about.
#
# Measured on 175 real documents: 13 (7%) express a SOURCE that differs from
# their SUBJECT -- eight are journalists reporting an analyst action, four are
# analyst outlets writing about earnings or macro. A further 19% of classified
# documents carry MORE THAN ONE subject. One category cannot represent them.
#
# The Day 10 case that exposed this: Investing.com reporting "Scotiabank raises
# Duolingo price target". Authorship says INDUSTRY (a journalist wrote it);
# content says analyst opinion. Both are true, and collapsing them loses half
# the information.
#
# GATES ARE UNCHANGED. Corroboration continues to key on SOURCE alone, exactly
# as before. Subjects are recorded for future reasoning and grant nothing
# today: no gate is weakened, no hypothesis broadened, no evidence satisfies a
# requirement it previously could not. This is a semantics change, and the
# regression suite asserts that it changes no decision.
# ---------------------------------------------------------------------------

class Subject:
    """What a document is ABOUT. Independent of who wrote it."""
    CUSTOMER_ADOPTION = "customer_adoption"
    ANALYST_OPINION = "analyst_opinion"
    EARNINGS = "earnings"
    GOVERNANCE = "governance"
    REGULATION = "regulation"
    COMPETITION = "competition"
    MACRO = "macro"
    CAPITAL_ALLOCATION = "capital_allocation"
    PRODUCT = "product"
    PRICING = "pricing"


_SUBJECT_TERMS = {
    Subject.ANALYST_OPINION: ("analyst", "price target", "upgrade",
                              "downgrade", "rating", "initiates coverage",
                              "consensus", "estimate"),
    Subject.EARNINGS: ("earnings", "revenue", "eps", "quarterly results",
                       "guidance", "beat", "missed"),
    Subject.GOVERNANCE: ("board", "chief executive", "ceo ", "proxy",
                         "activist", "lawsuit", "probe", "resign"),
    Subject.REGULATION: ("regulator", "antitrust", "ruling", "fine",
                         "compliance", "investigation by"),
    Subject.COMPETITION: ("competitor", "rival", " vs ", "versus",
                          "market share"),
    Subject.CUSTOMER_ADOPTION: ("merchant", "customer", "adoption", "users",
                                "subscriber", "churn", "retention"),
    Subject.MACRO: ("tariff", "inflation", "interest rate", "recession",
                    "economy"),
    Subject.CAPITAL_ALLOCATION: ("buyback", "dividend", "acquisition",
                                 "capex", "divest", "raises capital"),
    Subject.PRODUCT: ("launch", "new feature", "platform", "release",
                      "partnership"),
    Subject.PRICING: ("price increase", "pricing", "discount", "fee change"),
}


def subjects_of(text: str) -> tuple:
    """Every subject a document speaks to. A SET, because 19% of real documents
    carry more than one and forcing a single value discards the rest."""
    low = (text or "").lower()
    return tuple(sorted(s for s, terms in _SUBJECT_TERMS.items()
                        if any(t in low for t in terms)))


@dataclass(frozen=True)
class EvidenceSemantics:
    """Source and subject, kept apart."""
    source: str
    subjects: tuple = ()

    @property
    def is_independent(self) -> bool:
        return is_independent(self.source)

    def as_dict(self) -> dict:
        return {"source": self.source, "subjects": list(self.subjects),
                "independent": self.is_independent}


def describe(source_class: str, text: str = "") -> EvidenceSemantics:
    """Two-dimensional description. `source` still decides every gate."""
    return EvidenceSemantics(source=category_of(source_class),
                             subjects=subjects_of(text))
