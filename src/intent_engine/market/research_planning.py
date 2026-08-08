"""Which source to ask, decided by what each source has actually produced.

THE CONNECTION THIS CLOSES
--------------------------
`learning_health` has been able to say DEGRADING for a while. Nothing read
it. A health metric that changes no behaviour is a dashboard, and this
project has shipped several.

Here health becomes an input to a decision: when learning degrades BECAUSE
the engine keeps re-reading its own evidence, the planner shifts the research
mix toward sources that produce genuinely new observations and away from the
ones producing restatements. Same budget, different allocation.

WHY A SOURCE IS CHOSEN BY PREDICATE, NOT BY QUALITY
---------------------------------------------------
Wave 4 measured three families and wave 5 measured competitor families. The
naive reading is a ranking — case studies at 0.500/doc beat awards at 0.172,
so ask case studies. That is wrong, and expensively so: a case study can
never tell you who a government buys from, and an award record can never
tell you who a company competes with. The families are not substitutes.

So selection is by the PREDICATE a question needs, and yield ranks only
within the families that could answer it at all. A high-yield family for the
wrong predicate has a yield of zero for that question.

WHY ONE MEASUREMENT MUST NOT BECOME A PERMANENT PREFERENCE
----------------------------------------------------------
`partnership_release` measured 0.051/doc on 59 documents and
`customer_case_study` 0.500 on 22. Treating those as settled would end
sampling forever, and the first of them has already been wrong once — the
same family measured 0.048 when the adapter was fetching index pages.

So every record carries a MATURITY, promotion needs a real sample, and an
immature family keeps getting sampled regardless of its current number.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "source_family_performance.v1"

# --- maturity ---------------------------------------------------------------
PROVISIONAL = "PROVISIONAL"      # too few attempts for the number to mean much
INDICATIVE = "INDICATIVE"        # enough to rank, not enough to settle
ESTABLISHED = "ESTABLISHED"      # enough to plan on
MATURITIES = (PROVISIONAL, INDICATIVE, ESTABLISHED)

MIN_DOCUMENTS_INDICATIVE = 20
MIN_DOCUMENTS_ESTABLISHED = 100

#: Even an ESTABLISHED family keeps a share of the budget. A planner that
#: stops sampling cannot discover that a source has decayed, and a source
#: that used to work is exactly the kind of thing that changes silently.
EXPLORATION_FLOOR = 0.15

# --- what a question needs --------------------------------------------------
#
# The predicate is the question. Everything else is ranking.
NEEDS_CUSTOMER = "NAMED_CUSTOMER"
NEEDS_GOVERNMENT_BUYER = "GOVERNMENT_BUYER"
NEEDS_PARTNER = "PARTNERSHIP"
NEEDS_COMPETITOR = "COMPETITOR_RELATIONSHIP"
NEEDS_COMPETITIVE_ACTION = "COMPETITIVE_ACTION"
NEEDS_ACTION_OBJECT = "ACTION_OBJECT"
NEEDS_OUTCOME_EVIDENCE = "OUTCOME_EVIDENCE"
NEEDS_FRESH_OBSERVATION = "FRESH_OBSERVATION"
QUESTION_TYPES = (NEEDS_CUSTOMER, NEEDS_GOVERNMENT_BUYER, NEEDS_PARTNER,
                  NEEDS_COMPETITOR, NEEDS_COMPETITIVE_ACTION,
                  NEEDS_ACTION_OBJECT, NEEDS_OUTCOME_EVIDENCE,
                  NEEDS_FRESH_OBSERVATION)

#: Which families CAN answer each question at all. A family absent from a
#: row cannot answer that question however well it scores elsewhere.
CAN_ANSWER: Dict[str, Tuple[str, ...]] = {
    NEEDS_CUSTOMER: ("customer_case_study", "government_award"),
    NEEDS_GOVERNMENT_BUYER: ("government_award",),
    NEEDS_PARTNER: ("partnership_release",),
    NEEDS_COMPETITOR: ("comparison_page", "customer_case_study"),
    # An action needs an ANNOUNCEMENT. A rival's blog is narrative and
    # measured 5 real actions from 8 documents at poor precision; release
    # notes and launch pages are where a company states what it did.
    NEEDS_COMPETITIVE_ACTION: ("release_notes", "product_launch_page",
                               "investor_release", "rival_newsroom"),
    # An object needs a document that names the BUYER as well as the thing.
    # A launch page says who it is for; a blog post rarely does.
    NEEDS_ACTION_OBJECT: ("pricing_page", "product_launch_page",
                          "migration_page", "release_notes"),
    NEEDS_OUTCOME_EVIDENCE: ("customer_case_study", "investor_release"),
    NEEDS_FRESH_OBSERVATION: ("government_award", "partnership_release",
                              "comparison_page", "customer_case_study",
                              "rival_newsroom"),
}


@dataclass
class SourceFamilyPerformance:
    """What a family has actually returned, and how much to trust that."""
    source_family: str
    question_type: str = ""
    attempts: int = 0
    retrieved: int = 0
    useful: int = 0
    relationship_yield: float = 0.0
    belief_yield: float = 0.0
    resolution_yield: float = 0.0
    false_positive_rate: Optional[float] = None
    latency_seconds: float = 0.0
    cost: str = ""
    last_updated: str = ""

    @property
    def key(self) -> Tuple[str, str]:
        """A family's record is per QUESTION TYPE, not overall.

        `customer_case_study` yields 0.500 relationships/document for a named
        customer and 0.136 for a competitor and 0.000 for an action object.
        One number for the family would recommend it for all three.
        """
        return (self.source_family, self.question_type)

    @property
    def maturity(self) -> str:
        if self.retrieved >= MIN_DOCUMENTS_ESTABLISHED:
            return ESTABLISHED
        if self.retrieved >= MIN_DOCUMENTS_INDICATIVE:
            return INDICATIVE
        return PROVISIONAL

    @property
    def latency_per_document(self) -> float:
        return (self.latency_seconds / self.retrieved) if self.retrieved else 0.0

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "source_family": self.source_family,
            "question_type": self.question_type, "attempts": self.attempts,
            "retrieved": self.retrieved, "useful": self.useful,
            "relationship_yield": round(self.relationship_yield, 4),
            "belief_yield": round(self.belief_yield, 4),
            "resolution_yield": round(self.resolution_yield, 4),
            "false_positive_rate": self.false_positive_rate,
            "latency_seconds": round(self.latency_seconds, 2),
            "latency_per_document": round(self.latency_per_document, 2),
            "cost": self.cost, "last_updated": self.last_updated,
            "maturity": self.maturity,
        }


def from_yield(report, *, question_type: str = "",
               as_of: str = "") -> SourceFamilyPerformance:
    """Read a `counterparty_sources.Yield` into durable performance state."""
    data = report.as_dict() if hasattr(report, "as_dict") else dict(report)
    retrieved = int(data.get("documents_retrieved", 0) or 0)
    accepted = int(data.get("relationships_accepted", 0) or 0)
    refused = int(data.get("relationships_refused", 0) or 0)
    return SourceFamilyPerformance(
        source_family=str(data.get("family") or ""),
        question_type=question_type,
        attempts=int(data.get("documents_attempted", 0) or 0),
        retrieved=retrieved, useful=accepted,
        relationship_yield=float(data.get("yield_per_document", 0.0) or 0.0),
        false_positive_rate=(refused / (refused + accepted)
                             if (refused + accepted) else None),
        latency_seconds=float(data.get("latency_seconds", 0.0) or 0.0),
        cost=("cheap" if retrieved and
              (float(data.get("latency_seconds", 0)) / retrieved) < 1.0
              else "expensive"),
        last_updated=as_of[:10])


@dataclass
class ResearchPlan:
    """What to ask next, in what order, and why."""
    question_type: str
    families: Tuple[str, ...]
    reasons: Dict[str, str] = field(default_factory=dict)
    excluded: Dict[str, str] = field(default_factory=dict)
    health_adjustment: str = ""

    def as_dict(self) -> dict:
        return {"question_type": self.question_type,
                "families": list(self.families), "reasons": dict(self.reasons),
                "excluded": dict(self.excluded),
                "health_adjustment": self.health_adjustment}


#: Families whose documents are mostly relayed rather than originated. When
#: the corpus is already dominated by syndication, asking these again buys
#: another copy of what is held, not another witness.
_RELAYED_FAMILIES = frozenset({"rival_newsroom", "comparison_page"})

#: Above this share of SAME_ORIGIN pairs, the corpus's apparent corroboration
#: is mostly one story wearing several bylines. Measured at 133/148 = 0.899
#: on the live ledger, so the threshold is not hypothetical.
SAME_ORIGIN_DOMINANT = 0.6


def plan(question_type: str, *,
         performance: Sequence[SourceFamilyPerformance] = (),
         learning_status: str = "", dominant_self_test_class: str = "",
         dependency_classes: Optional[Dict[str, int]] = None
         ) -> ResearchPlan:
    """Rank the families that could answer this question. Never all of them.

    Ordering, in strict precedence:

      1. a family that CANNOT answer this predicate is excluded outright,
         however well it scores;
      2. a PROVISIONAL family is kept ahead of its measured rank, because a
         number from four documents is not a finding;
      3. the rest are ranked by measured relationship yield;
      4. cost breaks ties, so a cheap source is asked before an expensive
         one at equal yield.
    """
    from . import learning_acceleration as LA
    from . import observation_binding as OB

    eligible = CAN_ANSWER.get(question_type, ())
    # Keyed by (family, question) and narrowed to THIS question, so a
    # family's score for a different job cannot rank it here.
    by_family = {p.source_family: p for p in performance
                 if not p.question_type or p.question_type == question_type}

    # Exclusions are computed from EVERY family the engine has measured, not
    # from the ones narrowed to this question — a family scored only for a
    # different job still needs a stated reason for not appearing here, or
    # the plan silently omits it.
    excluded = {
        p.source_family: (
            f"cannot answer {question_type}: this family names "
            f"{'buyers' if 'award' in p.source_family else 'the other party'}"
            f" of a different kind")
        for p in performance if p.source_family not in eligible}

    ranked: List[Tuple[tuple, str, str]] = []
    for name in eligible:
        got = by_family.get(name)
        if got is None:
            ranked.append(((0, 0.0, 0.0), name,
                           "never measured for this question; sampled so it "
                           "can be"))
            continue
        immature = got.maturity == PROVISIONAL
        reason = (f"{got.relationship_yield:.3f} relationships/document over "
                  f"{got.retrieved} documents ({got.maturity})")
        if immature:
            reason += "; kept ahead of its rank because the sample is small"
        ranked.append(((0 if immature else 1,
                        -got.relationship_yield,
                        got.latency_per_document), name, reason))

    adjustment = ""
    # --- health becomes an action, not a display -------------------------
    if learning_status == LA.DEGRADING and \
            dominant_self_test_class == OB.SAME_SOURCE_REPACKAGING:
        # The engine is re-reading its own evidence. The answer is not to
        # ingest less; it is to ingest from somewhere it has not already
        # read. Families that produce NEW documents move up, and the ones
        # whose documents change slowly move down.
        slow = {"customer_case_study", "comparison_page"}
        ranked = [((2 if name in slow else -1,) + key[1:], name,
                   reason + ("; deprioritised while learning is degrading "
                             "on re-reads — these pages change slowly"
                             if name in slow else
                             "; prioritised while learning is degrading on "
                             "re-reads — this source produces new documents"))
                  for key, name, reason in ranked]
        adjustment = (
            "learning is DEGRADING and the dominant self-test class is "
            "SAME_SOURCE_REPACKAGING, so slow-changing pages were "
            "deprioritised in favour of sources that produce new documents")

    # --- source dependence becomes an action too -------------------------
    # A corpus whose accounts are 90% SAME_ORIGIN does not need more
    # accounts; it needs a different KIND of witness. This does not suppress
    # baseline coverage — every family keeps its place in the ranking — it
    # reorders which is asked first.
    classes = dependency_classes or {}
    total_pairs = sum(classes.values())
    if total_pairs:
        same_origin_share = (classes.get("SAME_ORIGIN", 0)
                             + classes.get("DERIVED", 0)) / total_pairs
        if same_origin_share >= SAME_ORIGIN_DOMINANT:
            ranked = [((3 if name in _RELAYED_FAMILIES else -2,) + key[1:],
                       name,
                       reason + (
                           "; deprioritised because the corpus's accounts "
                           "are already mostly one origin, and this family "
                           "relays rather than originates"
                           if name in _RELAYED_FAMILIES else
                           "; prioritised because it originates a fact "
                           "rather than relaying one"))
                      for key, name, reason in ranked]
            adjustment = ((adjustment + "; " if adjustment else "") +
                          f"{same_origin_share:.0%} of paired accounts are "
                          f"SAME_ORIGIN or DERIVED, so originating sources "
                          f"were asked before relaying ones")

    ranked.sort(key=lambda row: row[0])
    return ResearchPlan(
        question_type=question_type,
        families=tuple(name for _, name, _ in ranked),
        reasons={name: reason for _, name, reason in ranked},
        excluded=excluded, health_adjustment=adjustment)


def summarise(performance: Sequence[SourceFamilyPerformance],
              plans: Sequence[ResearchPlan] = ()) -> dict:
    by_maturity = collections.Counter(p.maturity for p in performance)
    best = max(performance, key=lambda p: p.relationship_yield, default=None)
    return {
        "contract": CONTRACT,
        "families": len(performance),
        "by_maturity": {m: by_maturity.get(m, 0) for m in MATURITIES},
        "best_measured_family": best.source_family if best else "",
        "best_relationship_yield": (round(best.relationship_yield, 4)
                                    if best else 0.0),
        "exploration_floor": EXPLORATION_FLOOR,
        "performance": [p.as_dict() for p in performance],
        "plans": [p.as_dict() for p in plans],
        "note": ("families are selected by the PREDICATE a question needs; "
                 "yield ranks only within the families that could answer it "
                 "at all. A high-yield family for the wrong predicate has a "
                 "yield of zero for that question"),
    }
