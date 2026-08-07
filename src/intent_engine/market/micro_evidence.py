"""The atom of strategic learning: one dated, sourced, attributable fact.

WHY THIS EXISTS
---------------
Measured on eleven consecutive operating cycles: 28 companies evaluated, 27
carrying independent evidence, and `net_knowledge_gain: 0` every single time.
The cause was not a shortage of observations. It was that an observation had
nowhere to go. `hypothesis.evaluate` can revise a belief from a predicted
observable, but nothing in the live engine ever produced one, so the only
reachable path ran through `decision_correct` — a resolved paper trade. No
trade therefore meant no learning, structurally.

`MicroEvidence` is the missing input. It is what an observation becomes once it
has a source, a time, and an actor: the unit a belief can actually be updated
against.

THE TWO TIMESTAMPS ARE NOT REDUNDANT
------------------------------------
`observed_at` is when the fact happened. `available_at` is when this engine
could first have known it. A 10-K describes a fiscal year that closed in
January and is filed in March; an engine that scores a February decision using
the March filing has given itself information it did not have. Counterfactual
and regret learning both read `available_at`, never `observed_at`, and
`visible_at` is the only supported way to ask "what did we know then".

INDEPENDENCE IS A PROPERTY OF THE SOURCE, NOT OF THE CLAIM
----------------------------------------------------------
A company press release announcing a price cut is excellent evidence that the
price was cut and near-worthless evidence about why. `independence` carries
that distinction into the update arithmetic, so corroboration by three outlets
that all rewrote the same press release cannot masquerade as three witnesses.

NO SOURCE MEANS NO EVIDENCE NODE
--------------------------------
`build` raises rather than defaulting. A fact whose provenance was lost is a
model recollection, and model recollection entering an evidence ledger is the
exact failure the citation work exists to prevent.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple

CONTRACT_VERSION = "micro_evidence.v1"

# --- evidence types -------------------------------------------------------
EARNINGS_SURPRISE = "EARNINGS_SURPRISE"
GUIDANCE_REVISION = "GUIDANCE_REVISION"
ESTIMATE_REVISION = "ESTIMATE_REVISION"
PRICE_CHANGE = "PRICE_CHANGE"
PRODUCT_LAUNCH = "PRODUCT_LAUNCH"
COMPETITOR_ACTION = "COMPETITOR_ACTION"
CUSTOMER_COMMENT = "CUSTOMER_COMMENT"
SUPPLIER_COMMENT = "SUPPLIER_COMMENT"
HIRING = "HIRING"
LAYOFF = "LAYOFF"
INSIDER_ACTIVITY = "INSIDER_ACTIVITY"
OPTIONS_SKEW = "OPTIONS_SKEW"
INVENTORY_CHANGE = "INVENTORY_CHANGE"
FREIGHT_CHANGE = "FREIGHT_CHANGE"
PATENT_ACTIVITY = "PATENT_ACTIVITY"
CONTRACT_AWARD = "CONTRACT_AWARD"
REGULATORY_ACTION = "REGULATORY_ACTION"
MACRO_RELEASE = "MACRO_RELEASE"
MARKET_REACTION = "MARKET_REACTION"
CAPEX_SIGNAL = "CAPEX_SIGNAL"
PRICING_SIGNAL = "PRICING_SIGNAL"
PROCUREMENT_SIGNAL = "PROCUREMENT_SIGNAL"

# Added when the sentence-level classifier was measured against a real corpus.
# Every one of these existed as an event in the corpus and had no honest home
# in the taxonomy, so it was being filed under a neighbouring type — and a
# type is a claim. "Microsoft announced results for the quarter" was reaching
# beliefs as EARNINGS_SURPRISE, which asserts a beat that the sentence does
# not state; a dividend increase was reaching them as CAPEX_SIGNAL, which
# asserts spending on capacity when the company was returning cash.
EARNINGS_RESULT = "EARNINGS_RESULT"        # results reported, no beat claimed
EXECUTIVE_CHANGE = "EXECUTIVE_CHANGE"      # appointment, departure, election
CAPITAL_RETURN = "CAPITAL_RETURN"          # dividend, buyback
PARTNERSHIP = "PARTNERSHIP"
MA_ACTIVITY = "MA_ACTIVITY"

# --- added 2026-08-07 from a measured corpus gap ---------------------------
#
# Five real 10-Q/10-K filings were run through the classifier and every
# rejected sentence carrying a quantity AND an economic concept was read. Two
# concepts appeared repeatedly that the vocabulary could not represent at all,
# and both are among the most economically load-bearing numbers a filing has.
#
#: Demand that is already contracted but not yet delivered. GAAP calls this
#: "unsatisfied/remaining performance obligations" and "contract liabilities";
#: neither phrase existed anywhere in the pattern library, so Caterpillar's
#: $44.1bn of unsatisfied performance obligations and its contract liabilities
#: going 2,745 -> 4,678 -> 7,280 ($M) were both discarded. `INVENTORY_CHANGE`
#: matches the word "backlog", which no filing uses. Deliberately separate
#: from inventory: inventory is goods the company holds and nobody has bought,
#: committed demand is revenue customers have already signed for -- opposite
#: economics, so they must not route to the same family in the same direction.
COMMITTED_DEMAND = "COMMITTED_DEMAND"
#: An externally imposed cost the company does not control -- tariffs, duties,
#: customs, sanctions. Caterpillar disclosed ~$1.0bn of IEEPA tariff costs and
#: $392m of expected recoveries; nothing in the vocabulary could hold either.
#: Distinct from PRICING_SIGNAL (a company choice) because the economics
#: differ: a company can pass a tariff through, absorb it, or relocate, and
#: which one it does is exactly the strategic question worth asking.
COST_SHOCK = "COST_SHOCK"

EVIDENCE_TYPES = frozenset({
    EARNINGS_SURPRISE, GUIDANCE_REVISION, ESTIMATE_REVISION, PRICE_CHANGE,
    PRODUCT_LAUNCH, COMPETITOR_ACTION, CUSTOMER_COMMENT, SUPPLIER_COMMENT,
    HIRING, LAYOFF, INSIDER_ACTIVITY, OPTIONS_SKEW, INVENTORY_CHANGE,
    FREIGHT_CHANGE, PATENT_ACTIVITY, CONTRACT_AWARD, REGULATORY_ACTION,
    MACRO_RELEASE, MARKET_REACTION, CAPEX_SIGNAL, PRICING_SIGNAL,
    PROCUREMENT_SIGNAL, EARNINGS_RESULT, EXECUTIVE_CHANGE, CAPITAL_RETURN,
    PARTNERSHIP, MA_ACTIVITY,
})

# --- contradiction role ---------------------------------------------------
SUPPORTING = "SUPPORTING"
CONTRADICTING = "CONTRADICTING"
NEUTRAL = "NEUTRAL"
CONTRADICTION_ROLES = frozenset({SUPPORTING, CONTRADICTING, NEUTRAL})

# --- source independence --------------------------------------------------
# The multiplier a single item of this provenance carries into a belief
# update. Company-authored material is capped low deliberately: it is the
# most abundant source class by an order of magnitude, and letting it update
# at full weight would mean a company could move this engine's beliefs about
# itself simply by publishing more.
INDEPENDENCE = {
    "regulatory_filing": 0.85,
    "independent_reporting": 0.90,
    "analyst_coverage": 0.70,
    "customer_voice": 0.75,
    "competitor_statement": 0.65,
    "supplier_statement": 0.65,
    "market_observation": 0.80,
    "government_statistic": 0.95,
    "executive_statement": 0.35,
    "company_owned": 0.25,
}

# Sources whose author is the subject of the claim. Never independent
# corroboration of that subject's own motives, however many outlets repeat it.
SELF_AUTHORED = frozenset({"executive_statement", "company_owned"})

_MAX_FACT = 600


class EvidenceRejected(ValueError):
    """The item could not become evidence, and says exactly why."""


@dataclass(frozen=True)
class MicroEvidence:
    """One dated fact with provenance, ready to update a belief."""
    evidence_id: str
    subject_company: str
    actor: str
    evidence_type: str
    observed_at: str
    available_at: str
    source: str
    fact: str
    source_author: str = ""
    source_role: str = "independent_reporting"
    numeric_values: Tuple[Tuple[str, float], ...] = ()
    affected_hypotheses: Tuple[str, ...] = ()
    affected_hidden_states: Tuple[str, ...] = ()
    affected_causal_nodes: Tuple[str, ...] = ()
    affected_interactions: Tuple[str, ...] = ()
    reliability: float = 0.5
    relevance: float = 0.5
    contradiction_role: str = NEUTRAL
    limitations: Tuple[str, ...] = ()

    @property
    def independence(self) -> float:
        return INDEPENDENCE.get(self.source_role, 0.5)

    @property
    def self_authored(self) -> bool:
        """Is the subject of the claim also its author?"""
        return self.source_role in SELF_AUTHORED

    def freshness(self, as_of: str) -> Optional[int]:
        """Age in days at `as_of`, or None when either date is unusable."""
        from datetime import date
        try:
            return (date.fromisoformat(as_of[:10])
                    - date.fromisoformat(self.available_at[:10])).days
        except (TypeError, ValueError):
            return None

    def visible_at(self, decision_time: str) -> bool:
        """Could a decision made at `decision_time` have used this?

        The single guard against hindsight leakage. Compares `available_at`,
        never `observed_at` — the gap between the two is exactly the window in
        which a backtest can quietly cheat.
        """
        if not decision_time or not self.available_at:
            return False
        return self.available_at[:10] <= decision_time[:10]

    def as_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "subject_company": self.subject_company,
            "actor": self.actor,
            "evidence_type": self.evidence_type,
            "observed_at": self.observed_at,
            "available_at": self.available_at,
            "source": self.source,
            "source_author": self.source_author,
            "source_role": self.source_role,
            "fact": self.fact,
            "numeric_values": {k: v for k, v in self.numeric_values},
            "affected_hypotheses": list(self.affected_hypotheses),
            "affected_hidden_states": list(self.affected_hidden_states),
            "affected_causal_nodes": list(self.affected_causal_nodes),
            "affected_interactions": list(self.affected_interactions),
            "reliability": self.reliability,
            "independence": self.independence,
            "relevance": self.relevance,
            "self_authored": self.self_authored,
            "contradiction_role": self.contradiction_role,
            "limitations": list(self.limitations),
        }


def evidence_id_for(*, subject_company: str, evidence_type: str,
                    observed_at: str, fact: str, source: str) -> str:
    """A content hash, so the SAME fact seen twice carries the same id.

    Deduplication has to survive re-ingestion: the daily cycle re-reads the
    same filings, and an incrementing counter would mint a fresh id each pass
    and let one fact update a belief every day forever. The id is derived from
    what the fact IS, so a repeat is recognisable as a repeat.

    `source` participates because two outlets reporting the same event really
    are two items — they are correlated, which the design-effect penalty in
    `beliefs` handles, but they are not literally the same row.
    """
    norm = _normalise(fact)
    raw = "|".join((subject_company.strip().lower(), evidence_type,
                    (observed_at or "")[:10], norm, source.strip().lower()))
    return "ev_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _normalise(text: str) -> str:
    """Collapse whitespace and case so trivial reformatting is not a new fact."""
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def build(*, subject_company: str, actor: str, evidence_type: str,
          observed_at: str, available_at: str = "", source: str = "",
          fact: str = "", source_author: str = "",
          source_role: str = "independent_reporting",
          numeric_values: Optional[Dict[str, float]] = None,
          affected_hypotheses: Sequence[str] = (),
          affected_hidden_states: Sequence[str] = (),
          affected_causal_nodes: Sequence[str] = (),
          affected_interactions: Sequence[str] = (),
          reliability: float = 0.5, relevance: float = 0.5,
          contradiction_role: str = NEUTRAL,
          limitations: Sequence[str] = ()) -> MicroEvidence:
    """Construct evidence, or refuse and say why.

    Every rejection here is a fabrication that did not reach the ledger.
    """
    if not (subject_company or "").strip():
        raise EvidenceRejected("evidence needs a subject company")
    if evidence_type not in EVIDENCE_TYPES:
        raise EvidenceRejected(f"unknown evidence_type {evidence_type!r}")
    if not (source or "").strip():
        raise EvidenceRejected(
            "evidence needs a source; a fact without provenance is model "
            "recollection, which never enters the ledger")
    if not (fact or "").strip():
        raise EvidenceRejected("evidence needs a stated fact")
    if not _is_date(observed_at):
        raise EvidenceRejected(f"observed_at {observed_at!r} is not a date")
    available = available_at or observed_at
    if not _is_date(available):
        raise EvidenceRejected(f"available_at {available!r} is not a date")
    if available[:10] < observed_at[:10]:
        raise EvidenceRejected(
            "available_at precedes observed_at: evidence cannot have been "
            "knowable before it happened")
    if contradiction_role not in CONTRADICTION_ROLES:
        raise EvidenceRejected(f"unknown role {contradiction_role!r}")
    if source_role not in INDEPENDENCE:
        raise EvidenceRejected(f"unknown source_role {source_role!r}")

    return MicroEvidence(
        evidence_id=evidence_id_for(subject_company=subject_company,
                                    evidence_type=evidence_type,
                                    observed_at=observed_at, fact=fact,
                                    source=source),
        subject_company=subject_company.strip(),
        actor=(actor or subject_company).strip(),
        evidence_type=evidence_type,
        observed_at=observed_at[:10],
        available_at=available[:10],
        source=source.strip(),
        source_author=source_author.strip(),
        source_role=source_role,
        fact=_clip(fact),
        numeric_values=tuple(sorted((numeric_values or {}).items())),
        affected_hypotheses=tuple(affected_hypotheses),
        affected_hidden_states=tuple(affected_hidden_states),
        affected_causal_nodes=tuple(affected_causal_nodes),
        affected_interactions=tuple(affected_interactions),
        reliability=_clamp(reliability),
        relevance=_clamp(relevance),
        contradiction_role=contradiction_role,
        limitations=tuple(limitations),
    )


def deduplicate(items: Sequence[MicroEvidence]) -> Tuple[MicroEvidence, ...]:
    """Collapse repeats, preserving first-seen order.

    Applied before any belief update. Without it the daily re-read of an
    unchanged filing would strengthen a belief once per cycle, which is
    manufactured confidence with a real citation attached — the most
    convincing kind of wrong.
    """
    seen, out = set(), []
    for item in items:
        if item.evidence_id in seen:
            continue
        seen.add(item.evidence_id)
        out.append(item)
    return tuple(out)


def visible_subset(items: Sequence[MicroEvidence],
                   decision_time: str) -> Tuple[MicroEvidence, ...]:
    """Only what a decision made at `decision_time` could have seen."""
    return tuple(i for i in items if i.visible_at(decision_time))


def _clip(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= _MAX_FACT else text[:_MAX_FACT - 1] + "…"


def _clamp(value: float) -> float:
    try:
        return round(min(max(float(value), 0.0), 1.0), 4)
    except (TypeError, ValueError):
        return 0.0


def _is_date(value: str) -> bool:
    from datetime import date
    try:
        date.fromisoformat((value or "")[:10])
        return True
    except (TypeError, ValueError):
        return False
