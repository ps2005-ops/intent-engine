"""What actually connects an economy to a company.

WHY THIS EXISTS
---------------
`macro_state` can say the cost of money rose. `economic_chain` can hold the
transmission from that to a company's orders. Neither can say whether THIS
company cares, and without that the chain is a template: the same story
applies equally to a capital-intensive manufacturer refinancing a debt stack
and to a profitable software company with no debt at all. A transmission that
applies to everyone explains nobody.

An exposure is the conditioning term. It is what makes "rates rose" mean
something different for Caterpillar than for Shopify.

THE RULE THAT MATTERS
---------------------
EVIDENCE MUST ESTABLISH COMPANY-SPECIFIC EXPOSURE.

The tempting shortcut is a sector table: airlines are exposed to fuel, banks
to rates, exporters to currency. Those statements are usually true and they
are not measurements — they are priors about a category, and applying one to a
company produces a confident claim about a specific firm that no document
supports. Worse, it produces the SAME claim for every company in the sector,
so the model's most specific-sounding output is the one carrying the least
information.

So `infer_from_sector` raises, and the only way to a rated exposure is a
document belonging to the company that names the dependency.

THREE STANDINGS, AND UNKNOWN IS THE COMMON ONE
----------------------------------------------
    OBSERVED   the company's own document names the exposure
    INFERRED   derived from observed company facts by a stated rule
    UNKNOWN    nothing in this company's evidence establishes it

UNKNOWN is expected to dominate, and that is the honest reading of a corpus
built from press releases and earnings summaries. An exposure model whose
every dimension is populated is a model that has been guessing.
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from . import macro_state as MS

CONTRACT = "company_exposure.v1"

# --- the dimensions --------------------------------------------------------
RATE = "RATE_EXPOSURE"
CREDIT = "CREDIT_EXPOSURE"
FX = "FX_EXPOSURE"
COMMODITY = "COMMODITY_EXPOSURE"
ENERGY = "ENERGY_EXPOSURE"
LABOR = "LABOR_EXPOSURE"
SUPPLY = "SUPPLY_EXPOSURE"
CUSTOMER_CONCENTRATION = "CUSTOMER_CONCENTRATION"
CAPITAL_INTENSITY = "CAPITAL_INTENSITY"
REGULATORY = "REGULATORY_EXPOSURE"

DIMENSIONS = (RATE, CREDIT, FX, COMMODITY, ENERGY, LABOR, SUPPLY,
              CUSTOMER_CONCENTRATION, CAPITAL_INTENSITY, REGULATORY)

# --- standings --------------------------------------------------------------
OBSERVED = "OBSERVED"
INFERRED = "INFERRED"
UNKNOWN = "UNKNOWN"
STANDINGS = (OBSERVED, INFERRED, UNKNOWN)

#: Only these condition a transmission. An UNKNOWN exposure does not mean the
#: company is unexposed — it means nobody established either way, and a chain
#: built on it is a chain built on an assumption.
CONDITIONING = frozenset({OBSERVED, INFERRED})

# --- who is entitled to establish a company's own exposure -----------------
#
# An exposure is a fact about a company's own economics, and the company — or
# a document it filed with a regulator — is the authority on it. A third party
# reporting the same thing is real evidence and is a weaker kind: it can be
# wrong about the internals in a way a filing cannot.
#
# THE CASE THAT FORCED THIS. The first run rated Linde CAPITAL_INTENSITY
# OBSERVED from "Linde plc (NASDAQ:LIN) Shares Fall 6% After Capex Boost
# Surpasses EPS Gain" — a headline about a share price move, promoted to a
# measured statement about the company's cost structure because the word
# "Capex" appeared in it. Honda's rating, by contrast, came from its own
# quarterly filing. Both were OBSERVED; only one should have been.
_SELF_PUBLISHED = frozenset({"regulatory_filing", "company_owned"})
_THIRD_PARTY = frozenset({"independent_reporting", "analyst_coverage"})


def standing_for(source_role: str) -> str:
    """What a publisher of this class is entitled to establish.

    An unrecognised role yields UNKNOWN rather than a default: a source class
    nobody has classified is not evidence that a company is exposed.
    """
    role = str(source_role or "").strip().lower()
    if role in _SELF_PUBLISHED:
        return OBSERVED
    if role in _THIRD_PARTY:
        return INFERRED
    return UNKNOWN

#: Which economic condition each dimension is sensitive to. This is the join
#: between the two halves of the model: a macro state whose kind appears here
#: can be conditioned by the matching exposure, and one whose kind does not
#: has no route into this company at all.
SENSITIVE_TO: Dict[str, Tuple[str, ...]] = {
    RATE: (MS.POLICY_RATE, MS.MARKET_RATE),
    CREDIT: (MS.CREDIT_CONDITIONS, MS.MARKET_RATE),
    FX: (MS.CURRENCY,),
    COMMODITY: (MS.COMMODITY_PRICE,),
    ENERGY: (MS.ENERGY_PRICE,),
    LABOR: (MS.EMPLOYMENT, MS.WAGES),
    SUPPLY: (MS.INDUSTRIAL_PRODUCTION, MS.TRADE),
    CUSTOMER_CONCENTRATION: (MS.CONSUMER_DEMAND, MS.BUSINESS_INVESTMENT),
    CAPITAL_INTENSITY: (MS.POLICY_RATE, MS.MARKET_RATE, MS.CREDIT_CONDITIONS),
    REGULATORY: (MS.FISCAL,),
}


class ExposureRejected(ValueError):
    """An exposure that would assert more than a document established."""


@dataclass(frozen=True)
class Exposure:
    """One company's sensitivity to one economic condition."""

    company_id: str
    dimension: str
    standing: str
    #: The sentence in the company's own material that establishes it. Empty
    #: only when UNKNOWN — a rated exposure without a quotation is exactly the
    #: sector prior this module refuses.
    basis: str = ""
    evidence_ids: Tuple[str, ...] = ()
    observed_at: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.dimension not in DIMENSIONS:
            raise ExposureRejected(f"unknown dimension {self.dimension!r}")
        if self.standing not in STANDINGS:
            raise ExposureRejected(f"unknown standing {self.standing!r}")
        if self.standing in CONDITIONING and not self.evidence_ids:
            raise ExposureRejected(
                f"a {self.standing} exposure needs the evidence that "
                "established it; without an id this is a claim about a "
                "category wearing a company's name")
        if self.standing in CONDITIONING and not self.basis.strip():
            raise ExposureRejected(
                "a rated exposure needs the wording that established it")

    @property
    def conditions(self) -> bool:
        return self.standing in CONDITIONING

    @property
    def state_kinds(self) -> Tuple[str, ...]:
        return SENSITIVE_TO.get(self.dimension, ())

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT, conditions=self.conditions,
                 state_kinds=list(self.state_kinds))
        return d


def unknown(company_id: str, dimension: str, reason: str = "") -> Exposure:
    """No document established this either way.

    NOT "the company is unexposed". A company with no debt and a company whose
    filings never mention debt look identical from outside, and collapsing
    them would let silence read as safety.
    """
    return Exposure(
        company_id=company_id, dimension=dimension, standing=UNKNOWN,
        note=reason or "no evidence for this company establishes this "
                       "exposure either way")


def infer_from_sector(*_args, **_kwargs):
    """Deliberately not implemented, and deliberately present.

    "Airlines are exposed to fuel" is usually true and is not a measurement.
    Applying it produces a confident, specific-sounding claim about a company
    that no document supports — and produces the IDENTICAL claim for every
    company in the sector, so the most authoritative-looking output in the
    model would carry the least information in it.
    """
    raise ExposureRejected(
        "an exposure may not be inferred from a company's sector; find the "
        "sentence in this company's own material, or record UNKNOWN")


# --- reading exposure out of a company's own words -------------------------
#
# Each pattern demands the company be the SUBJECT of the dependency, not
# merely nearby in the sentence. "Our results are sensitive to fuel prices"
# rates; "fuel prices rose this year" does not, because the second is a fact
# about the world that happens to appear in a company's document.
_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (RATE, r"\b(our|the compan\w+|its)\b[^.]{0,80}\b(interest rate|"
           r"floating rate|variable rate|rate)\s+(exposure|risk|sensitiv\w+)"),
    (RATE, r"\b(exposed|sensitive)\s+to\b[^.]{0,40}\binterest rates?\b"),
    (CREDIT, r"\b(our|its)\b[^.]{0,60}\b(refinanc\w+|debt maturit\w+|"
             r"credit facilit\w+|covenant\w*)\b"),
    (FX, r"\b(currency|exchange[- ]rate|foreign exchange|FX)\s+"
         r"(exposure|risk|translation|headwind|impact)\b"),
    (COMMODITY, r"\b(raw material|commodity|input)\s+(cost|price)\w*\b"
                r"[^.]{0,60}\b(our|its|impact\w*|pressur\w+)\b"),
    (ENERGY, r"\b(energy|fuel|electricity)\s+(cost|price)\w*\b"
             r"[^.]{0,60}\b(our|its|impact\w*|pressur\w+)\b"),
    (LABOR, r"\b(labou?r|wage|hiring|headcount)\s+"
            r"(cost|inflation|pressur\w+|shortage)\b"),
    (SUPPLY, r"\b(supply chain|supplier|component|semiconductor)\b"
             r"[^.]{0,60}\b(constraint|shortage|disrupt\w+|depend\w+)\b"),
    # TWO DEAD BRANCHES, FOUND BY RUNNING THE PATTERNS OVER REAL FILINGS.
    #
    # `\b(\d+\s*%|...)\b` could never match a percentage: the group ends on
    # "%", a non-word character, and the trailing \b then requires the NEXT
    # character to be a word character. In "22% of revenue" it is a space, so
    # the boundary fails. Only the "percent" and "majority" spellings ever
    # rated, and "22% of revenue" is the form filings actually use. The
    # boundary now belongs to the alternatives that are words.
    (CUSTOMER_CONCENTRATION,
     r"\b(largest|top|single)\s+(customer|client)s?\b[^.]{0,60}"
     r"(?:\b\d+\s*%|\bpercent\b|\bmajority\b)"),
    # `capital expenditure` did not match "capital expenditures", which is
    # the form nearly every filing uses -- the trailing \b fails against the
    # plural "s". Measured on six annual reports: the singular appears twice
    # and the plural forty-one times.
    (CAPITAL_INTENSITY, r"\b(capital expenditures?|capex|capital intensity|"
                        r"capital[- ]intensive)\b"),
    (REGULATORY, r"\b(regulat\w+|tariff|sanction)\w*\b[^.]{0,60}"
                 r"\b(our|its)\b[^.]{0,40}\b(business|operations|results)\b"),
)

_COMPILED = tuple((dim, re.compile(pat, re.I)) for dim, pat in _PATTERNS)


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "")
            if s.strip()]


def read_exposures(rows: Sequence[dict], *, company_id: str,
                   effects: Optional[list] = None) -> List[Exposure]:
    """Every exposure this company's OWN evidence establishes.

    Reads only rows filed under this company. A sentence in a competitor's
    filing that mentions this company does not establish this company's
    exposure — it establishes the competitor's view of it, which is a
    different and weaker fact.

    Pass a list as `effects` to have the attribution recorded: CREATED when a
    sentence first establishes a dimension, REVISED when a filing upgrades a
    reporting-derived rating, and NO_CHANGE for the great majority of rows
    that match nothing. The NO_CHANGE rows are the point — 257 of 260
    dimensions are unrated, and without a record of the evidence that failed
    to move them the research reward cannot tell a productive source from a
    prolific one.
    """
    from . import knowledge_effect as KE

    mine = [r for r in rows
            if r.get("record") == "evidence"
            and r.get("subject_company") == company_id]

    found: Dict[str, Exposure] = {}
    for row in mine:
        eid = str(row.get("evidence_id") or "")
        observed = str(row.get("observed_at") or "")[:10]
        standing = standing_for(row.get("source_role"))
        if standing == UNKNOWN:
            if effects is not None and eid:
                effects.append(KE.no_change(
                    eid, reason=("source role establishes no exposure "
                                 f"standing: {row.get('source_role')!r}"),
                    target_type=KE.COMPANY_EXPOSURE, occurred_at=observed,
                    created_at=observed))
            continue
        text = str(row.get("fact") or "")
        moved = False
        for sentence in _sentences(text):
            for dimension, pattern in _COMPILED:
                held = found.get(dimension)
                # The company's own word outranks a report of it, so a filing
                # arriving after a headline UPGRADES the standing rather than
                # being discarded as a duplicate.
                upgrade = (held is not None and held.standing == INFERRED
                           and standing == OBSERVED)
                if held is not None and not upgrade:
                    continue
                if pattern.search(sentence):
                    found[dimension] = Exposure(
                        company_id=company_id, dimension=dimension,
                        standing=standing, basis=sentence[:240],
                        evidence_ids=(eid,) if eid else (),
                        observed_at=observed,
                        note=f"established by {row.get('source_role')}")
                    moved = True
                    if effects is not None and eid:
                        effects.append(KE.KnowledgeEffect(
                            evidence_id=eid,
                            target_type=KE.COMPANY_EXPOSURE,
                            target_id=f"{company_id}:{dimension}",
                            effect_type=(KE.REVISED if upgrade
                                         else KE.CREATED),
                            before_state=(held.standing if held else UNKNOWN),
                            after_state=standing,
                            occurred_at=observed, created_at=observed,
                            reason=(f"{'upgraded' if upgrade else 'opened'} "
                                    f"{dimension} from a "
                                    f"{row.get('source_role')} source"),
                            standing=KE.DIRECT,
                            provenance="company_exposure.read_exposures"))
        if effects is not None and eid and not moved:
            effects.append(KE.no_change(
                eid, reason="no sentence in this evidence names an exposure",
                target_type=KE.COMPANY_EXPOSURE, occurred_at=observed,
                created_at=observed))
    return [found[d] for d in DIMENSIONS if d in found]


def profile(rows: Sequence[dict], *, company_id: str,
            effects: Optional[list] = None) -> Dict[str, Exposure]:
    """The full profile — every dimension, rated or explicitly unknown.

    Total by construction. A caller that only receives the rated dimensions
    will forget the others exist, and the ones that are missing are precisely
    the ones a reader most needs to be told about.
    """
    rated = {e.dimension: e for e in read_exposures(rows,
                                                    company_id=company_id,
                                                    effects=effects)}
    return {d: rated.get(d) or unknown(company_id, d) for d in DIMENSIONS}


def conditions_transmission(exposure: Optional[Exposure],
                            state: Optional[MS.EconomicState]) -> bool:
    """Whether this exposure lets this economic condition reach this company.

    Both halves must be real. A measured economy with an unestablished
    exposure is a story, and an established exposure with an unmeasured
    economy is a sensitivity to nothing in particular.
    """
    if exposure is None or state is None:
        return False
    if not exposure.conditions or not state.anchors:
        return False
    return state.state_kind in exposure.state_kinds


def summarise(profiles: Dict[str, Dict[str, Exposure]]) -> dict:
    """Counted, never scored.

    There is no exposure "score". Summing dimensions would imply they are
    commensurable — that customer concentration and currency risk trade off
    against each other on one axis — and nothing in the evidence supports it.
    """
    by_standing: Dict[str, int] = {}
    by_dimension: Dict[str, int] = {}
    for company_profile in profiles.values():
        for dimension, exposure in company_profile.items():
            by_standing[exposure.standing] = \
                by_standing.get(exposure.standing, 0) + 1
            if exposure.conditions:
                by_dimension[dimension] = by_dimension.get(dimension, 0) + 1
    rated = sum(1 for p in profiles.values()
                for e in p.values() if e.conditions)
    return {
        "contract": CONTRACT,
        "companies": len(profiles),
        "dimensions": len(DIMENSIONS),
        "rated_exposures": rated,
        "by_standing": by_standing,
        "rated_by_dimension": by_dimension,
        "companies_with_any": sum(
            1 for p in profiles.values()
            if any(e.conditions for e in p.values())),
        "note": ("UNKNOWN dominating is the honest reading of a corpus of "
                 "press releases; a fully populated profile is a guessed one"),
    }
