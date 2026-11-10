"""Weekly walk-forward evaluation + monthly promotion packet (sections 13, 15).

Both are HUMAN-GATED: the weekly job evaluates open candidates out-of-sample and
records the evaluation; the monthly job assembles a promotion packet. NEITHER
promotes anything — promotion is a human action (`CandidateStore.promote`, never
called here). A candidate is only ever a proposal until a human opens the gate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from intent_engine.hosted.candidates import CandidateStore
from intent_engine.predictions.resolution import outcomes_for_company

PACKET_STREAM = "promotion_packet"
WEEKLY_STREAM = "weekly_evaluation"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _directional_accuracy(outs: List[dict]) -> float:
    scored = [o for o in outs if o.get("outcome") in ("happened", "did_not_happen")]
    if not scored:
        return 0.0
    return sum(1 for o in scored if o["outcome"] == "happened") / len(scored)


def weekly_evaluate(ctx, as_of: str) -> Dict:
    """Split each candidate's company outcomes chronologically into an earlier
    (in-sample) and later (out-of-sample) half, and record whether the weakness
    the candidate names persists out-of-sample. A real (if simple) walk-forward
    that never uses future data for the in-sample half."""
    cstore = CandidateStore(ctx.store)
    evaluated = 0
    for cand in cstore.open():
        if not cand.company_id:
            continue
        outs = sorted(outcomes_for_company(ctx.store, cand.company_id),
                      key=lambda o: o.get("resolved_at", ""))
        if len(outs) < 4:
            continue
        mid = len(outs) // 2
        in_sample = _directional_accuracy(outs[:mid])
        out_sample = _directional_accuracy(outs[mid:])
        # the weakness "holds" out-of-sample if accuracy stays poor (< 0.55)
        holds = out_sample < 0.55
        evaluation = {"candidate_id": cand.id, "company_id": cand.company_id,
                      "in_sample_accuracy": round(in_sample, 3),
                      "out_of_sample_accuracy": round(out_sample, 3),
                      "weakness_holds_out_of_sample": holds,
                      "in_sample_n": mid, "out_sample_n": len(outs) - mid,
                      "at": _now(), "note": "walk-forward; no promotion (human "
                      "gate)"}
        cstore.record_evaluation(cand.id, evaluation)
        evaluated += 1
    summary = {"as_of": as_of[:10], "evaluated": evaluated,
               "open_candidates": len(cstore.open()), "at": _now()}
    ctx.store.append(WEEKLY_STREAM, as_of[:10], summary, status="evaluated",
                     idem_key=f"weekly:{as_of[:10]}:{evaluated}",
                     ts=summary["at"])
    return summary


def prepare_promotion_packet(ctx, as_of: str) -> Dict:
    """Assemble a human-review packet of EVALUATED candidates. Prepares only —
    it never flips a candidate to promoted."""
    cstore = CandidateStore(ctx.store)
    evaluated = [c for c in cstore.all_latest() if c.status == "evaluated"]
    packet = {
        "as_of": as_of[:10], "prepared_at": _now(),
        "candidates": [{"id": c.id, "company_id": c.company_id,
                        "statement": c.statement, "sample_size": c.sample_size,
                        "source": c.source} for c in evaluated],
        "note": "HUMAN-GATED — review required; nothing is promoted "
                "automatically. Promotion changes no production rule until a "
                "human approves.",
    }
    ctx.store.append(PACKET_STREAM, as_of[:10], packet, status="prepared",
                     idem_key=f"packet:{as_of[:10]}:{len(evaluated)}",
                     ts=packet["prepared_at"])
    return {"as_of": as_of[:10], "candidates_in_packet": len(evaluated),
            "promoted": 0, "human_gated": True}
