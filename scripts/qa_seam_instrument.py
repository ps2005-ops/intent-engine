"""Instrument the Q&A answer path end to end, per PRE-100 §4.

Two repairs to the standing seam shipped green and inert. The discipline the
programme asks for after a second inert fix is to MEASURE which producer
answers each board question, not to guess a third time.

This walks the production path exactly as `webapp.app` does -- the same
`build_payload` call with the same keyword arguments, the same `assemble`,
the same `decision_synthesis.compose`, the same `qa._route_answer` -- and
records, for each of the ten board questions:

    QUESTION / intent / decision field / branch / producer / final answer

together with the standing inputs the recommendation is a function of.

Run:  PYTHONPATH=src python scripts/qa_seam_instrument.py
"""
from __future__ import annotations

import json
import sys

from intent_engine.demo_dossier import (assemble, market_unavailable,
                                        read_founder_snapshot)
from intent_engine.external_intel import founder_demo_snapshot as FDS
from intent_engine.executive import decision_synthesis as DS
from intent_engine.founder_brief import qa as QA

BOARD_QUESTIONS = (
    "What should management do?",
    "Why now?",
    "What's the biggest risk?",
    "What proves this wrong?",
    "Who's the real competitor?",
    "What does the market believe?",
    "What's the weakest assumption?",
    "What's the impossible hypothesis?",
    "What should we measure next?",
    "What would you tell the board?",
)


def production_founder_payload(company_id: str, name: str, report=None,
                               context=None, **extra) -> dict:
    """EXACTLY the keyword set `webapp/app.py` passes at its one call site.

    If this drifts from the call site the instrument is measuring a path the
    product does not run, which is how a uniform defect gets invented.
    """
    kwargs = dict(run_id="instr", company_id=company_id, canonical_name=name,
                  domain="", report=report, context=context, scope=None,
                  independence=None, claim_provenance=None,
                  discovery=None, learning=None)
    kwargs.update(extra)
    return FDS.build_payload(**kwargs)


def trace(company_id: str, name: str, *, market=None, **extra) -> dict:
    founder = read_founder_snapshot(
        production_founder_payload(company_id, name, **extra))
    market = market or market_unavailable(
        "No market demo snapshot has been published for this company in "
        "this deployment.", company_id=company_id)
    dossier = assemble(market, founder, known_as=(company_id,),
                       now="2026-08-21")
    standing = DS._standing_of(dossier)
    decision = DS.compose(dossier).as_dict()

    fblocks = ((dossier.founder_block or {}).get("blocks") or {})
    mblocks = ((dossier.market_block or {}).get("blocks") or {})
    rows = []
    for question in BOARD_QUESTIONS:
        intent = QA.intent_of(question)
        field = next((f for n, _m, f, _a in QA.INTENT_ROUTES if n == intent),
                     "")
        answer, _ = QA._route_answer(question, decision, read=None)
        rows.append({
            "question": question,
            "intent": intent or "(NO ROUTE — strategic catch-all)",
            "decision_field": field,
            "field_present": bool(decision.get(field)) if field else False,
            "producer": ("decision.%s" % field if field
                         and decision.get(field) else "read-fallback/absent"),
            "answer": (answer or "")[:220],
        })
    return {
        "company": name,
        "standing": standing,
        "standing_inputs": {
            "market_availability": (dossier.market_block or {})
            .get("availability"),
            "market_evidence_count": (mblocks.get("evidence") or {})
            .get("count"),
            "market_beliefs_count": (mblocks.get("beliefs") or {})
            .get("count"),
            "founder_evidence_block": fblocks.get("evidence"),
        },
        "recommended_next_move": decision.get("recommended_next_move"),
        "questions": rows,
    }


def main() -> int:
    out = [trace(k, n) for k, n in (
        ("the-goldman-sachs-group-inc", "The Goldman Sachs Group, Inc."),
        ("nike-inc", "NIKE, Inc."),
        ("cloudflare-inc", "Cloudflare, Inc."),
        ("meta-platforms-inc", "Meta Platforms, Inc."),
    )]
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
