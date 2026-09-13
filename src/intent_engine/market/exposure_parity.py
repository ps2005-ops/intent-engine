"""§27: do the market and founder sides read exposures the same way?

THE ISSUE, RESTATED PRECISELY
-----------------------------
Both products infer "this company is exposed to rates / FX / labour cost" and
they have historically done it through different code over different corpora:

    founder   econ.exposure.read(full document text)
    market    market.company_exposure.read_exposures(ledger rows, row["fact"])

The founder side's own source comments record what that cost: a corpus of
news headlines -- 131 rows, 19,415 characters across six companies --
produced ONE exposure, while the same patterns over filings produced 39.

Two producers is the defect. A different corpus is not necessarily a defect,
but it must be a stated decision rather than an accident, and the two must
reconcile at the canonical layer.

WHAT THIS MODULE DOES
---------------------
It runs the CANONICAL producer (`econ.exposure`) over whatever text each side
actually has, and reports:

    agreed        the same (company, quantity) pair from both
    market_only   the market corpus found something the founder corpus did not
    founder_only  and the reverse
    producer      whether both sides used the canonical producer at all

`PRODUCER_DIVERGENCE` is the finding that matters. Two corpora disagreeing is
information about the corpora; two PRODUCERS disagreeing is a bug that will
drift further every time either is edited.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from intent_engine.econ import exposure as EXP

CONTRACT = "exposure_parity.v1"

CANONICAL_PRODUCER = "intent_engine.econ.exposure"

AGREED = "AGREED"
MARKET_ONLY = "MARKET_ONLY"
FOUNDER_ONLY = "FOUNDER_ONLY"
PRODUCER_DIVERGENCE = "PRODUCER_DIVERGENCE"


@dataclass(frozen=True)
class ParityRow:
    company_id: str
    quantity: str
    status: str
    market_evidence: int = 0
    founder_evidence: int = 0
    note: str = ""

    def as_dict(self) -> dict:
        return {"company_id": self.company_id, "quantity": self.quantity,
                "status": self.status,
                "market_evidence": self.market_evidence,
                "founder_evidence": self.founder_evidence, "note": self.note}


def _pairs(rows: Sequence[dict]) -> Set[Tuple[str, str]]:
    return {(str(r.get("company_id") or ""), str(r.get("quantity") or ""))
            for r in rows if r.get("quantity")}


def read_canonical(texts: Sequence[str], *, company_id: str) -> List[dict]:
    """The ONE producer. Both sides are measured through this, always.

    Passing each side's own corpus through the same function is what turns
    "the two sides disagree" from an unanswerable observation into a
    statement about the corpora specifically.
    """
    return EXP.read([t for t in texts if t], company_id=company_id)


def compare(*, company_id: str, market_texts: Sequence[str],
            founder_texts: Sequence[str],
            market_producer: str = "",
            founder_producer: str = "") -> Tuple[List[ParityRow], dict]:
    """Reconcile the two sides at the canonical layer."""
    m = read_canonical(market_texts, company_id=company_id)
    f = read_canonical(founder_texts, company_id=company_id)
    mp, fp = _pairs(m), _pairs(f)

    m_by = {}
    for r in m:
        m_by[(r.get("company_id"), r.get("quantity"))] = r
    f_by = {}
    for r in f:
        f_by[(r.get("company_id"), r.get("quantity"))] = r

    rows: List[ParityRow] = []
    for key in sorted(mp | fp):
        cid, q = key
        if key in mp and key in fp:
            status = AGREED
        elif key in mp:
            status = MARKET_ONLY
        else:
            status = FOUNDER_ONLY
        rows.append(ParityRow(company_id=cid, quantity=q, status=status,
                              market_evidence=1 if key in mp else 0,
                              founder_evidence=1 if key in fp else 0))

    producers_agree = (market_producer == founder_producer
                       == CANONICAL_PRODUCER)
    if not producers_agree:
        rows.append(ParityRow(
            company_id=company_id, quantity="*", status=PRODUCER_DIVERGENCE,
            note=(f"market uses {market_producer or 'unknown'}, founder uses "
                  f"{founder_producer or 'unknown'}; the canonical producer "
                  f"is {CANONICAL_PRODUCER}. Two corpora disagreeing is "
                  "information about the corpora; two PRODUCERS disagreeing "
                  "will drift further every time either is edited.")))

    summary = {
        "contract": CONTRACT, "company_id": company_id,
        "market_chars": sum(len(t or "") for t in market_texts),
        "founder_chars": sum(len(t or "") for t in founder_texts),
        "market_documents": len([t for t in market_texts if t]),
        "founder_documents": len([t for t in founder_texts if t]),
        "market_exposures": len(mp), "founder_exposures": len(fp),
        "agreed": sum(1 for r in rows if r.status == AGREED),
        "market_only": sum(1 for r in rows if r.status == MARKET_ONLY),
        "founder_only": sum(1 for r in rows if r.status == FOUNDER_ONLY),
        "producers_agree": producers_agree,
        "canonical_producer": CANONICAL_PRODUCER,
        "market_producer": market_producer or "unknown",
        "founder_producer": founder_producer or "unknown",
        "reconciles": producers_agree and not any(
            r.status in (MARKET_ONLY, FOUNDER_ONLY) for r in rows),
        "rows": [r.as_dict() for r in rows],
    }
    # The corpus asymmetry, named, because it is the thing a reader should
    # act on when the two sides disagree despite sharing a producer.
    if summary["founder_chars"] and summary["market_chars"]:
        summary["corpus_ratio"] = round(
            summary["founder_chars"] / max(1, summary["market_chars"]), 2)
    return rows, summary


def audit(cases: Dict[str, Tuple[Sequence[str], Sequence[str]]], *,
          market_producer: str = "", founder_producer: str = "") -> dict:
    """Run the reconciliation over several companies at once."""
    per_company, all_rows = {}, []
    for cid, (mtexts, ftexts) in sorted(cases.items()):
        rows, s = compare(company_id=cid, market_texts=mtexts,
                          founder_texts=ftexts,
                          market_producer=market_producer,
                          founder_producer=founder_producer)
        per_company[cid] = s
        all_rows.extend(rows)
    return {"contract": CONTRACT, "companies": len(cases),
            "producers_agree": all(s["producers_agree"]
                                   for s in per_company.values()),
            "companies_reconciling": sum(1 for s in per_company.values()
                                         if s["reconciles"]),
            "total_agreed": sum(1 for r in all_rows if r.status == AGREED),
            "total_market_only": sum(1 for r in all_rows
                                     if r.status == MARKET_ONLY),
            "total_founder_only": sum(1 for r in all_rows
                                      if r.status == FOUNDER_ONLY),
            "per_company": per_company}
