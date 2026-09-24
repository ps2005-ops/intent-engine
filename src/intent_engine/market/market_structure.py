"""Industrial organisation: structure, pricing, procurement and entry.

WHY QUALITATIVE EVIDENCE IS THE DEFAULT
---------------------------------------
Market share and concentration are the two numbers everyone wants and almost
nobody can source. This engine has no licensed share data, so a computed HHI
here would be arithmetic over guesses — precise, citable, and wrong. The
structure model therefore records *qualitative* structural evidence with its
provenance, and `concentration` stays `UNMEASURED` unless real share figures
are supplied. That is a worse-looking output and a better one.

RELEVANCE IS GATED, NOT ASSUMED
-------------------------------
Auction theory is genuinely decisive for a defence contractor and completely
irrelevant to a self-serve SaaS product. §11 is explicit that these modules
must not be injected into unrelated companies, so each analysis carries a
`applies_because` that names the evidence establishing relevance. No
establishing evidence means no module — `pricing_analysis` and
`auction_analysis` return a stated absence rather than a generic essay.

This mirrors a defect already paid for on the founder side: a keyword
("procurement") on a commerce company's page fabricated a defence exposure,
complete with mechanism and citation. Every structural claim here needs the
mechanism, not the keyword.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT_VERSION = "market_structure.v1"

UNMEASURED = "UNMEASURED"
QUALITATIVE = "QUALITATIVE"
QUANTIFIED = "QUANTIFIED"

# --- pricing mechanisms ---------------------------------------------------
PENETRATION = "PENETRATION"
SKIMMING = "SKIMMING"
BUNDLING = "BUNDLING"
VERSIONING = "VERSIONING"
USAGE_PRICING = "USAGE_PRICING"
SUBSCRIPTION = "SUBSCRIPTION"
DISCRIMINATION = "DISCRIMINATION"
CROSS_SUBSIDY = "CROSS_SUBSIDY"
SWITCHING_COST_EXPLOITATION = "SWITCHING_COST_EXPLOITATION"
MARGIN_PROTECTION = "MARGIN_PROTECTION"

PRICING_STRATEGIES = frozenset({
    PENETRATION, SKIMMING, BUNDLING, VERSIONING, USAGE_PRICING, SUBSCRIPTION,
    DISCRIMINATION, CROSS_SUBSIDY, SWITCHING_COST_EXPLOITATION,
    MARGIN_PROTECTION})

# --- auction / procurement formats ---------------------------------------
FIRST_PRICE = "FIRST_PRICE"
SECOND_PRICE = "SECOND_PRICE"
SEALED_BID = "SEALED_BID"
REVERSE_AUCTION = "REVERSE_AUCTION"
MULTI_ROUND = "MULTI_ROUND"
NEGOTIATED = "NEGOTIATED"

AUCTION_FORMATS = frozenset({FIRST_PRICE, SECOND_PRICE, SEALED_BID,
                             REVERSE_AUCTION, MULTI_ROUND, NEGOTIATED})


class StructureError(ValueError):
    """A structural claim made without the evidence to support it."""


@dataclass(frozen=True)
class StructuralFact:
    """One structural observation, with its basis and its status."""
    dimension: str
    finding: str
    status: str
    evidence_ids: Tuple[str, ...] = ()
    limitation: str = ""

    def as_dict(self) -> dict:
        return {"dimension": self.dimension, "finding": self.finding,
                "status": self.status,
                "evidence_ids": list(self.evidence_ids),
                "limitation": self.limitation}


@dataclass(frozen=True)
class MarketStructure:
    """A bounded structural picture of one market."""
    market_definition: str
    strategic_job: str
    subject: str
    buyer_groups: Tuple[str, ...] = ()
    facts: Tuple[StructuralFact, ...] = ()
    concentration: str = UNMEASURED
    concentration_note: str = (
        "No licensed market-share source is wired, so concentration is "
        "reported as unmeasured rather than estimated.")
    limitations: Tuple[str, ...] = ()

    def dimension(self, name: str) -> Optional[StructuralFact]:
        for f in self.facts:
            if f.dimension == name:
                return f
        return None

    @property
    def assessed_dimensions(self) -> Tuple[str, ...]:
        return tuple(f.dimension for f in self.facts)

    @property
    def unassessed_dimensions(self) -> Tuple[str, ...]:
        return tuple(d for d in STRUCTURAL_DIMENSIONS
                     if d not in self.assessed_dimensions)

    def as_dict(self) -> dict:
        return {"market_definition": self.market_definition,
                "strategic_job": self.strategic_job, "subject": self.subject,
                "buyer_groups": list(self.buyer_groups),
                "facts": [f.as_dict() for f in self.facts],
                "concentration": self.concentration,
                "concentration_note": self.concentration_note,
                "assessed_dimensions": list(self.assessed_dimensions),
                "unassessed_dimensions": list(self.unassessed_dimensions),
                "limitations": list(self.limitations)}


STRUCTURAL_DIMENSIONS = (
    "entry_barriers", "switching_costs", "scale_economies",
    "network_effects", "capacity_constraints", "differentiation",
    "vertical_integration", "complements", "substitutes", "regulation",
    "procurement_structure", "pricing_mechanism", "bargaining_structure",
)


def structural_fact(*, dimension: str, finding: str,
                    evidence_ids: Sequence[str] = (),
                    quantified: bool = False,
                    limitation: str = "") -> StructuralFact:
    if dimension not in STRUCTURAL_DIMENSIONS:
        raise StructureError(f"unknown structural dimension {dimension!r}")
    if not evidence_ids:
        raise StructureError(
            f"{dimension}: a structural claim needs cited evidence; an "
            f"uncited one is a recollection about an industry")
    return StructuralFact(
        dimension=dimension, finding=finding.strip(),
        status=QUANTIFIED if quantified else QUALITATIVE,
        evidence_ids=tuple(evidence_ids), limitation=limitation.strip())


def build_structure(*, subject: str, market_definition: str,
                    strategic_job: str, facts: Sequence[StructuralFact] = (),
                    buyer_groups: Sequence[str] = (),
                    shares: Optional[Dict[str, float]] = None,
                    limitations: Sequence[str] = ()) -> MarketStructure:
    """Assemble a structural picture. Concentration only if shares are real.

    `shares` must be actual sourced share figures. When absent — which is the
    normal case — concentration stays UNMEASURED and says why, rather than
    being inferred from the number of competitors anyone happened to name.
    """
    limits = list(limitations)
    concentration = UNMEASURED
    note = MarketStructure.concentration_note
    if shares:
        total = sum(shares.values())
        if total > 1.5:  # percentages rather than fractions
            shares = {k: v / 100.0 for k, v in shares.items()}
            total = sum(shares.values())
        hhi = sum((v * 100) ** 2 for v in shares.values())
        concentration = QUANTIFIED
        note = (f"HHI {hhi:.0f} over supplied shares covering "
                f"{total:.0%} of the market")
        if total < 0.8:
            limits.append(
                f"Supplied shares cover only {total:.0%} of the market, so "
                f"the concentration figure understates it.")
    if not facts:
        limits.append("No structural dimension has been evidenced for this "
                      "market.")
    return MarketStructure(
        market_definition=market_definition.strip(),
        strategic_job=strategic_job.strip(), subject=subject.strip(),
        buyer_groups=tuple(buyer_groups), facts=tuple(facts),
        concentration=concentration, concentration_note=note,
        limitations=tuple(limits))


# --------------------------------------------------------------------------
# pricing / auction / entry — each gated on established relevance
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class GatedAnalysis:
    """An analysis that ran, or a stated reason it did not."""
    kind: str
    applies: bool
    applies_because: str
    findings: Tuple[str, ...] = ()
    mechanism: str = ""
    risks: Tuple[str, ...] = ()
    evidence_ids: Tuple[str, ...] = ()
    limitations: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"kind": self.kind, "applies": self.applies,
                "applies_because": self.applies_because,
                "findings": list(self.findings), "mechanism": self.mechanism,
                "risks": list(self.risks),
                "evidence_ids": list(self.evidence_ids),
                "limitations": list(self.limitations)}


def _absent(kind: str, reason: str) -> GatedAnalysis:
    return GatedAnalysis(kind=kind, applies=False, applies_because=reason)


def pricing_analysis(*, subject: str, strategy: str = "",
                     mechanism: str = "", evidence_ids: Sequence[str] = (),
                     findings: Sequence[str] = (),
                     risks: Sequence[str] = ()) -> GatedAnalysis:
    """Pricing analysis, or a stated absence.

    Requires a named strategy, a mechanism, and cited evidence. The mechanism
    is what makes it about THIS company: without it the output is a pricing
    textbook with a company name at the top.
    """
    if not strategy:
        return _absent("pricing", "no pricing strategy is evidenced for "
                                  f"{subject}")
    if strategy not in PRICING_STRATEGIES:
        raise StructureError(f"unknown pricing strategy {strategy!r}")
    if not evidence_ids:
        return _absent("pricing",
                       f"a {strategy} reading of {subject} was proposed but "
                       f"no evidence establishes it")
    if not mechanism:
        return _absent("pricing",
                       f"no mechanism connects {strategy} to {subject}'s "
                       f"buyers; a strategy label without a mechanism is a "
                       f"textbook entry, not a finding")
    return GatedAnalysis(
        kind="pricing", applies=True,
        applies_because=f"{strategy} evidenced for {subject}",
        findings=tuple(findings), mechanism=mechanism.strip(),
        risks=tuple(risks), evidence_ids=tuple(evidence_ids))


def auction_analysis(*, subject: str, fmt: str = "",
                     buyer_evidence: Sequence[str] = (),
                     mechanism: str = "", findings: Sequence[str] = (),
                     risks: Sequence[str] = ()) -> GatedAnalysis:
    """Auction/procurement analysis, or a stated absence.

    Gated hard. Auction theory injected into a company that does not sell
    through auctions is the exact failure §11 names, and the founder side has
    already paid for the equivalent mistake once.
    """
    if not fmt:
        return _absent("auction",
                       f"{subject} is not evidenced to sell through a "
                       f"competitive bidding process")
    if fmt not in AUCTION_FORMATS:
        raise StructureError(f"unknown auction format {fmt!r}")
    if not buyer_evidence:
        return _absent("auction",
                       f"a {fmt} process was proposed for {subject} but no "
                       f"evidence shows its buyers actually procure that way")
    if not mechanism:
        return _absent("auction",
                       f"no mechanism connects {fmt} bidding to {subject}'s "
                       f"revenue")
    return GatedAnalysis(
        kind="auction", applies=True,
        applies_because=f"{fmt} procurement evidenced for {subject}'s buyers",
        findings=tuple(findings), mechanism=mechanism.strip(),
        risks=tuple(risks), evidence_ids=tuple(buyer_evidence),
        limitations=("Bid-level data is not available; this describes the "
                     "mechanism, not any specific bid.",))


def entry_analysis(*, subject: str, market: str = "",
                   barriers: Sequence[StructuralFact] = (),
                   incumbent_response: str = "",
                   evidence_ids: Sequence[str] = ()) -> GatedAnalysis:
    """Entry analysis, or a stated absence.

    Requires evidenced barriers. "Entry is hard" with nothing behind it is
    true of every market and therefore informative about none.
    """
    if not market:
        return _absent("entry", f"no entry decision is evidenced for "
                                f"{subject}")
    if not barriers:
        return _absent("entry",
                       f"no entry barrier is evidenced for {market}; a "
                       f"generic 'entry is hard' is true everywhere and "
                       f"therefore says nothing about this market")
    findings = tuple(f"{b.dimension}: {b.finding}" for b in barriers)
    cited = tuple(evidence_ids) or tuple(
        e for b in barriers for e in b.evidence_ids)
    return GatedAnalysis(
        kind="entry", applies=True,
        applies_because=f"{len(barriers)} evidenced barrier(s) in {market}",
        findings=findings,
        mechanism=incumbent_response.strip(), evidence_ids=cited)
