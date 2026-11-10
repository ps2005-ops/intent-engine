"""The learning loop, in SHADOW: resolve, compare, attribute, update, propose.

WHAT MAY LEARN FROM WHAT
------------------------
A belief is updated only from a RESOLVED record of the SAME ledger kind as
the belief file: forward beliefs from the forward ledger, rehearsal beliefs
from the rehearsal ledger. The replay never updates a forward belief -- it
is history the policies may have been shaped by, not forward evidence -- and
a rehearsal record never reaches a forward belief, because rehearsal
probabilities are constants. `update_beliefs` refuses both crossings.

WHAT IT MAY DO WITH WHAT IT LEARNS
----------------------------------
Propose. Candidates go to a `learning.LearningLedger` at a shadow path with
the preregistered success criteria attached; that ledger's `promote`
refuses any actor that is not a human, and nothing here calls it. No
policy reads a candidate. The only thing a belief changes is the next
shadow decision of the policy that owns it (`ie_econ_bayes`).

ERROR ATTRIBUTION
-----------------
Every resolved record gets one class:
    HIT          right direction, net of cost positive
    COST_LOSS    right direction, net negative: the edge was smaller than
                 the round trip
    NEAR_MISS    wrong direction inside the near-miss band
                 (protocol: 2x the round-trip cost)
    MISS         wrong direction beyond the band
    ABSTAIN_SPARED   abstained, and the move would have gone against the
                     policy's usual side (a short-only policy sparing an up
                     move counts; for others: |excess| within the band)
    ABSTAIN_MISSED   abstained through a move larger than the band
A policy whose losses are mostly NEAR_MISS and COST_LOSS is a different
problem from one whose losses are MISS, and they get different candidates.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
from typing import Dict, List, Optional, Sequence

from intent_engine.paper_validation import ledger as LG
from intent_engine.paper_validation import metrics as MT
from intent_engine.paper_validation.protocol import PROTOCOL, declaration_hash

ROOT = pathlib.Path("reports/paper_validation")
BELIEFS = {LG.FORWARD_SHADOW: ROOT / "shadow_beliefs_forward.jsonl",
           LG.REHEARSAL: ROOT / "shadow_beliefs_rehearsal.jsonl"}
SHADOW_LEARNING_DB = {
    LG.FORWARD_SHADOW: pathlib.Path("data/paper_validation_shadow_learning.db"),
    LG.REHEARSAL: pathlib.Path(
        "data/paper_validation_shadow_learning_rehearsal.db")}

_L = PROTOCOL["learning"]
_P = PROTOCOL["promotion"]


class LearningRefused(RuntimeError):
    """A belief tried to learn from evidence it may not learn from."""


def attribute(reg: dict, res: dict) -> str:
    band = _L["near_miss_band_multiple_of_cost"] * max(
        reg.get("expected_cost_bps") or 10.0, 10.0) * 1e-4
    x = float(res["excess_return"])
    d = reg["direction"]
    if d == "ABSTAIN":
        return "ABSTAIN_MISSED" if abs(x) > band else "ABSTAIN_SPARED"
    right = (d == "LONG") == (x > 0)
    if right:
        return "HIT" if res.get("net_position_return", 0) > 0 else "COST_LOSS"
    return "NEAR_MISS" if abs(x) <= band else "MISS"


def resolved_rows(ledger: LG.Ledger) -> List[dict]:
    out = []
    for st in ledger.states().values():
        if st.status != LG.RESOLVED:
            continue
        reg, res = st.registration, st.resolution
        out.append({"forecast_id": st.forecast_id,
                    "policy_id": reg["policy_id"], "family": reg["family"],
                    "universe": reg["universe"],
                    "decision_date": reg["decision_date"],
                    "direction": reg["direction"],
                    "probability": reg["probability"],
                    "y": res["outcome"], "excess": res["excess_return"],
                    "net": res.get("net_position_return", 0.0),
                    "class": attribute(reg, res),
                    "ledger_kind": reg["ledger_kind"]})
    return sorted(out, key=lambda r: (r["decision_date"], r["forecast_id"]))


def update_beliefs(ledger: LG.Ledger, rows: Sequence[dict], *,
                   path: Optional[pathlib.Path] = None,
                   now: Optional[_dt.datetime] = None) -> dict:
    """Beta(1,1) per (policy, family) on traded hits. Append-only events."""
    path = pathlib.Path(path or BELIEFS[ledger.kind])
    for r in rows:
        if r["ledger_kind"] != ledger.kind:
            raise LearningRefused(
                f"{r['forecast_id']} is {r['ledger_kind']}; a "
                f"{ledger.kind} belief may not learn from it")
    if ledger.kind == LG.REPLAY:
        raise LearningRefused("the replay is history, not forward evidence")
    seen = set()
    state: Dict[str, List[int]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            if e.get("ledger_kind") != ledger.kind:
                raise LearningRefused(f"{path} holds a {e.get('ledger_kind')}"
                                      f" event; refusing to mix kinds")
            seen.update(e["forecast_ids"])
            state[e["belief"]] = [e["posterior_alpha"], e["posterior_beta"]]
    now = now or _dt.datetime.now(_dt.timezone.utc)
    events = []
    groups: Dict[str, List[dict]] = {}
    for r in rows:
        if r["forecast_id"] in seen or r["direction"] == "ABSTAIN":
            continue
        groups.setdefault(f"{r['policy_id']}|{r['family']}", []).append(r)
    for belief, rs in sorted(groups.items()):
        a, b = state.get(belief, [1, 1])
        hits = sum(1 for r in rs if (r["direction"] == "LONG") == (r["y"] == 1))
        events.append({"ledger_kind": ledger.kind, "belief": belief,
                       "proposition": f"{belief.split('|')[0]} calls the "
                                      f"sign correctly on {belief.split('|')[1]}",
                       "prior_alpha": a, "prior_beta": b,
                       "posterior_alpha": a + hits,
                       "posterior_beta": b + len(rs) - hits,
                       "posterior_mean": (a + hits) / (a + b + len(rs)),
                       "forecast_ids": [r["forecast_id"] for r in rs],
                       "updated_at": now.isoformat(timespec="seconds"),
                       "protocol_hash": declaration_hash()})
    if events:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            for e in events:
                fh.write(json.dumps(e, sort_keys=True) + "\n")
    return {"events": len(events), "path": str(path)}


def calibration_drift(rows: Sequence[dict]) -> Dict[str, dict]:
    w = _L["calibration_drift_window"]
    out = {}
    by: Dict[str, List[dict]] = {}
    for r in rows:
        if r["probability"] is not None:
            by.setdefault(r["policy_id"], []).append(r)
    for pid, rs in by.items():
        dates = sorted({r["decision_date"] for r in rs})
        if len(dates) < 2 * w:
            out[pid] = {"status": "INSUFFICIENT", "dates": len(dates),
                        "needs": 2 * w}
            continue
        first, last = set(dates[:w]), set(dates[-w:])
        b0 = MT.brier([r["probability"] for r in rs if r["decision_date"]
                       in first], [r["y"] for r in rs
                                   if r["decision_date"] in first])
        b1 = MT.brier([r["probability"] for r in rs if r["decision_date"]
                       in last], [r["y"] for r in rs
                                  if r["decision_date"] in last])
        out[pid] = {"status": "DRIFT" if b1 - b0 >
                    _L["calibration_drift_alarm_brier_rise"] else "STABLE",
                    "brier_first": b0, "brier_last": b1, "dates": len(dates)}
    return out


def promotion_readiness(rows: Sequence[dict]) -> Dict[str, dict]:
    """The preregistered bar, applied. Never promotes; reports."""
    out = {}
    pols = sorted({r["policy_id"] for r in rows})
    for pid in pols:
        rs = [r for r in rows if r["policy_id"] == pid]
        dates = sorted({r["decision_date"] for r in rs})
        if len(dates) < _P["min_resolved_decision_dates"]:
            out[pid] = {"status": "NOT_ELIGIBLE", "resolved_dates": len(dates),
                        "needs": _P["min_resolved_decision_dates"]}
            continue
        out[pid] = {"status": "ELIGIBLE_FOR_EVALUATION",
                    "resolved_dates": len(dates),
                    "note": "apply the full promotion bar (Brier skill CI, "
                            "Sharpe vs benchmark CI, drawdown, calibration "
                            "slope, Holm) before any human review"}
    return out


def propose_candidates(ledger: LG.Ledger, rows: Sequence[dict],
                       drift: Dict[str, dict], *,
                       db_path: Optional[pathlib.Path] = None) -> List[str]:
    from intent_engine.learning.records import SuccessCriterion
    from intent_engine.learning.service import LearningLedger
    db = pathlib.Path(db_path or SHADOW_LEARNING_DB[ledger.kind])
    db.parent.mkdir(parents=True, exist_ok=True)
    ll = LearningLedger(db)
    ids = []
    classes: Dict[str, Dict[str, int]] = {}
    for r in rows:
        classes.setdefault(r["policy_id"], {}).setdefault(r["class"], 0)
        classes[r["policy_id"]][r["class"]] += 1
    crit = [SuccessCriterion(metric="brier_skill", comparator=">",
                             threshold=_P["brier_skill_ci_low_gt"],
                             direction="higher_better"),
            SuccessCriterion(metric="resolved_decision_dates",
                             comparator=">=",
                             threshold=_P["min_resolved_decision_dates"],
                             direction="higher_better")]
    for pid, d in sorted(drift.items()):
        if d.get("status") != "DRIFT":
            continue
        c = ll.propose(source="calibration", target=f"{pid}.probability_map",
                       statement=f"{pid}'s Brier rose from "
                                 f"{d['brier_first']:.4f} to "
                                 f"{d['brier_last']:.4f}",
                       hypothesis="recalibrating its probability map on "
                                  "resolved forward outcomes restores skill",
                       baseline_ref=f"{pid} as registered",
                       success_criteria=crit,
                       provenance={"ledger_kind": ledger.kind,
                                   "protocol_hash": declaration_hash()})
        ids.append(c.id)
    for pid, cl in sorted(classes.items()):
        losses = cl.get("NEAR_MISS", 0) + cl.get("COST_LOSS", 0)
        misses = cl.get("MISS", 0)
        if losses >= 10 and losses > misses:
            c = ll.propose(source="paper_trade", target=f"{pid}.trade_margin",
                           statement=f"{pid}: {losses} near-miss/cost losses "
                                     f"vs {misses} outright misses",
                           hypothesis="a wider no-trade margin would cut "
                                      "cost-dominated trades",
                           baseline_ref=f"{pid} as registered",
                           success_criteria=crit,
                           provenance={"ledger_kind": ledger.kind,
                                       "classes": cl,
                                       "protocol_hash": declaration_hash()})
            ids.append(c.id)
    return ids


def run(ledger: LG.Ledger, *, beliefs_path=None, db_path=None,
        now: Optional[_dt.datetime] = None) -> dict:
    n = ledger.verify()
    rows = resolved_rows(ledger)
    beliefs = update_beliefs(ledger, rows, path=beliefs_path, now=now)
    drift = calibration_drift(rows)
    ids = propose_candidates(ledger, rows, drift, db_path=db_path)
    classes: Dict[str, Dict[str, int]] = {}
    for r in rows:
        classes.setdefault(r["policy_id"], {}).setdefault(r["class"], 0)
        classes[r["policy_id"]][r["class"]] += 1
    return {"ledger": str(ledger.path), "kind": ledger.kind,
            "chain_entries": n, "resolved": len(rows),
            "attribution": classes, "calibration_drift": drift,
            "promotion": promotion_readiness(rows), "beliefs": beliefs,
            "candidates_proposed": ids,
            "promotion_authority": "human only (LearningLedger.promote)"}
