"""Per-company + cross-company learning state (sections 7 & 8).

The discipline the spec insists on: LEARN PER COMPANY FIRST, pool second. So we
compute a `CompanyLearningState` for each company from its OWN resolved outcomes
(Brier, directional accuracy, calibration, paper P&L, by-horizon error, sample
size), and only THEN look for cross-company patterns — and a cross-company
candidate needs multiple supporting companies and records which companies
contradict it. One company's result can never rewrite the rules for all.

These are learning CANDIDATES / STATE only. Nothing here promotes anything or
changes a production rule — that stays behind the human gate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

STATE_STREAM = "company_learning_state"
CROSS_STREAM = "cross_company_candidate"

_HAPPENED = "happened"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CalibrationBucket(BaseModel):
    lo: float
    hi: float
    n: int
    predicted_mean: float
    empirical_rate: float


class HorizonBucket(BaseModel):
    horizon_days: int
    n: int
    brier: Optional[float]
    directional_accuracy: Optional[float]


class CompanyLearningState(BaseModel):
    company_id: str
    peer_group: Optional[str] = None
    sample_size: int = 0
    resolved_count: int = 0
    directional_accuracy: Optional[float] = None
    brier: Optional[float] = None
    avg_confidence: Optional[float] = None
    calibration_error: Optional[float] = None       # |avg_conf - accuracy|
    calibration: List[CalibrationBucket] = Field(default_factory=list)
    by_horizon: List[HorizonBucket] = Field(default_factory=list)
    paper_pnl: float = 0.0
    avg_market_return: Optional[float] = None
    updated_at: str = Field(default_factory=_now)
    notes: List[str] = Field(default_factory=list)


def _brier(outs: List[dict]) -> Optional[float]:
    comps = [o["brier_component"] for o in outs
             if o.get("brier_component") is not None]
    return (sum(comps) / len(comps)) if comps else None


def _directional_accuracy(outs: List[dict]) -> Optional[float]:
    scored = [o for o in outs if o.get("outcome") in (_HAPPENED, "did_not_happen")]
    if not scored:
        return None
    return sum(1 for o in scored if o["outcome"] == _HAPPENED) / len(scored)


def _calibration(outs: List[dict], *, bins=(0.5, 0.6, 0.7, 0.8, 0.9, 1.01)
                 ) -> List[CalibrationBucket]:
    edges = [0.0] + list(bins)
    buckets: List[CalibrationBucket] = []
    for lo, hi in zip(edges, edges[1:]):
        grp = [o for o in outs if lo <= float(o.get("probability", 0)) < hi
               and o.get("outcome") in (_HAPPENED, "did_not_happen")]
        if not grp:
            continue
        pm = sum(float(o["probability"]) for o in grp) / len(grp)
        er = sum(1 for o in grp if o["outcome"] == _HAPPENED) / len(grp)
        buckets.append(CalibrationBucket(lo=lo, hi=hi, n=len(grp),
                                         predicted_mean=pm, empirical_rate=er))
    return buckets


def _by_horizon(outs: List[dict]) -> List[HorizonBucket]:
    groups: Dict[int, List[dict]] = {}
    for o in outs:
        h = int(o.get("horizon_days") or 0)
        groups.setdefault(h, []).append(o)
    out = []
    for h in sorted(groups):
        g = groups[h]
        out.append(HorizonBucket(horizon_days=h, n=len(g), brier=_brier(g),
                                 directional_accuracy=_directional_accuracy(g)))
    return out


def compute_company_state(company_id: str, outcomes: List[dict], *,
                          peer_group: Optional[str] = None
                          ) -> CompanyLearningState:
    """Compute a company's learning state from its OWN resolved outcomes."""
    scored = [o for o in outcomes
              if o.get("outcome") in (_HAPPENED, "did_not_happen")]
    acc = _directional_accuracy(scored)
    conf = ([float(o["probability"]) for o in scored if o.get("probability")
             is not None])
    avg_conf = (sum(conf) / len(conf)) if conf else None
    pnls = [o["trade_pnl"] for o in outcomes if o.get("trade_pnl") is not None]
    rets = [o["market_return"] for o in scored if o.get("market_return")
            is not None]
    cal_err = (abs(avg_conf - acc) if (avg_conf is not None and acc is not None)
               else None)
    notes = []
    if acc is not None and avg_conf is not None and avg_conf - acc > 0.15:
        notes.append("overconfident: stated confidence exceeds realised accuracy")
    return CompanyLearningState(
        company_id=company_id, peer_group=peer_group,
        sample_size=len(outcomes), resolved_count=len(scored),
        directional_accuracy=acc, brier=_brier(scored), avg_confidence=avg_conf,
        calibration_error=cal_err, calibration=_calibration(scored),
        by_horizon=_by_horizon(scored),
        paper_pnl=float(sum(pnls)) if pnls else 0.0,
        avg_market_return=(sum(rets) / len(rets)) if rets else None,
        notes=notes)


class CompanyLearningStore:
    def __init__(self, store):
        self.store = store

    def save(self, state: CompanyLearningState) -> CompanyLearningState:
        # append-only history per company; latest wins
        self.store.append(
            STATE_STREAM, state.company_id, state.model_dump(mode="json"),
            status="updated", company_id=state.company_id, ts=state.updated_at,
            idem_key=f"clstate:{state.company_id}:{state.updated_at}:"
                     f"{state.sample_size}")
        return state

    def get(self, company_id: str) -> Optional[CompanyLearningState]:
        rec = self.store.get(STATE_STREAM, company_id)
        return CompanyLearningState(**rec.payload) if rec else None

    def all_latest(self) -> List[CompanyLearningState]:
        return [CompanyLearningState(**r.payload)
                for r in self.store.latest(STATE_STREAM)]


# --- cross-company (section 8) ----------------------------------------------
class CrossCompanyCandidate(BaseModel):
    id: str
    peer_group: str
    pattern: str
    supporting_companies: List[str]
    contradicting_companies: List[str]
    business_model_scope: str
    sample_size: int
    possible_confounders: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)


def cross_company_candidates(
    states: List[CompanyLearningState], *, min_supporting: int = 2,
    min_sample_per_company: int = 3,
) -> List[CrossCompanyCandidate]:
    """Find reusable patterns ACROSS companies in a peer group, preserving each
    company's own evidence. Requires >= min_supporting companies to support a
    pattern (never one company rewriting the rules), and records contradictors.
    """
    by_group: Dict[str, List[CompanyLearningState]] = {}
    for s in states:
        if s.peer_group and s.resolved_count >= min_sample_per_company:
            by_group.setdefault(s.peer_group, []).append(s)

    out: List[CrossCompanyCandidate] = []
    for group, members in by_group.items():
        # pattern: systematic overconfidence within the peer group
        supporting = [m.company_id for m in members
                      if m.calibration_error is not None
                      and m.avg_confidence is not None
                      and m.directional_accuracy is not None
                      and m.avg_confidence - m.directional_accuracy > 0.10]
        contradicting = [m.company_id for m in members
                         if m.company_id not in supporting]
        if len(supporting) >= min_supporting:
            sample = sum(m.resolved_count for m in members
                         if m.company_id in supporting)
            out.append(CrossCompanyCandidate(
                id=f"xcc:{group}:overconfidence",
                peer_group=group,
                pattern="stated confidence systematically exceeds realised "
                        "directional accuracy across peers",
                supporting_companies=sorted(supporting),
                contradicting_companies=sorted(contradicting),
                business_model_scope=group, sample_size=sample,
                possible_confounders=["shared market regime",
                                      "correlated horizon", "small sample"]))
    return out


def persist_cross_company(store, candidates: List[CrossCompanyCandidate]) -> None:
    for c in candidates:
        store.append(CROSS_STREAM, c.id, c.model_dump(mode="json"),
                     status="open", idem_key=f"xcc:{c.id}:{c.sample_size}",
                     ts=c.created_at)
