#!/usr/bin/env python3
"""Measure the data gates, from the ledger, with a date attached.

WHY THIS IS A SEPARATE FILE
---------------------------
`frontier.py` must not guess whether a node has enough evidence, and it must
not be handed a number somebody typed. It reads what was MEASURED, and every
measurement carries `measured_at` so a stale gate is visible as stale rather
than as fact.

    python3 docs/execution/v4/metrics.py            # measure and print
    python3 docs/execution/v4/metrics.py --write    # ... and update METRICS.json

A metric that cannot be measured is reported as None, never as 0. Those are
different claims: "we looked and there are none" and "we could not look". A
gate reading None blocks its node, because a node may not become runnable on
the strength of a measurement nobody took.
"""
from __future__ import annotations

import collections
import datetime as _dt
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
OUT = HERE / "METRICS.json"

#: The live PAPER runtime tree. Its ledger is the accumulating state, so the
#: gates are measured there rather than in whatever worktree this runs from.
RUNTIME_LEDGER = pathlib.Path(
    "/Users/prathamsharma/intent-engine-market/reports/market/"
    "learning_ledger.jsonl")


def _rows(path):
    if not path.exists():
        return None
    out = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def measure(ledger=RUNTIME_LEDGER) -> dict:
    rows = _rows(pathlib.Path(ledger))
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    if rows is None:
        # Unreadable ledger: every gate is UNKNOWN, not zero.
        return {"measured_at": now, "source": str(ledger),
                "readable": False, "metrics": {}}

    decisions = [r for r in rows if r.get("record") == "research_decision"]
    outcomes = [r for r in rows if r.get("record") == "research_outcome"]
    prospective = [d for d in decisions
                   if d.get("provenance") == "PROSPECTIVE"]
    by_status = collections.Counter(str(r.get("status") or "")
                                    for r in outcomes)
    relationships = [r for r in rows if r.get("record") == "relationship"]
    supplier = [r for r in relationships
                if str(r.get("predicate") or "").upper()
                in ("SUPPLIES", "SUPPLIED_BY", "SUPPLIER_OF")]

    metrics = {
        "prospective_decisions": len(prospective),
        "prospective_outcomes": len(outcomes),
        "prospective_with_forgone_option": sum(1 for d in prospective
                                               if d.get("forgone")),
        "prospective_empty_handed": (by_status.get("NO_RESULT", 0)
                                     + by_status.get("NO_NEW_INFORMATION", 0)),
        "prospective_failed": (by_status.get("FAILED", 0)
                               + by_status.get("TIMEOUT", 0)),
        # A propensity only exists where the policy randomised. The logging
        # policy is deterministic, so this is 0 and the bandit node stays
        # blocked on it rather than on a judgement call.
        "logged_exploration_events": sum(
            1 for d in prospective
            if d.get("selection_probability_status") == "KNOWN"),
        "named_supplier_edges": len(supplier),
        "macro_observations": sum(1 for r in rows
                                  if r.get("record") == "macro_observation"),
        # HOW MUCH OBSERVATION HISTORY EXISTS, which is a different quantity
        # from how much HISTORY exists. Every macro figure in the ledger was
        # retrieved inside one month while describing periods across three
        # years, so at any earlier instant the vintage admits nothing and a
        # historical replay has no T0 to stand on. Counting distinct
        # retrieval months makes that a gate the executor measures rather
        # than a judgement someone records — and it rises on its own as the
        # cycle keeps running.
        "macro_retrieval_months": len({
            str(r.get("retrieved_at") or "")[:7]
            for r in rows if r.get("record") == "macro_observation"
            and r.get("retrieved_at")}),
        "knowledge_effects": sum(1 for r in rows
                                 if r.get("record") == "knowledge_effect"),
        "evidence_rows": sum(1 for r in rows if r.get("record") == "evidence"),
    }
    return {"measured_at": now, "source": str(ledger), "readable": True,
            "metrics": metrics}


def load() -> dict:
    if OUT.exists():
        try:
            return json.loads(OUT.read_text(encoding="utf-8"))
        except ValueError:
            return {"metrics": {}, "readable": False}
    return {"metrics": {}, "readable": False}


def main(argv) -> int:
    got = measure()
    if "--write" in argv:
        OUT.write_text(json.dumps(got, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
    print(f"measured_at {got['measured_at']}  readable={got['readable']}")
    for key, value in sorted(got.get("metrics", {}).items()):
        print(f"  {key:36s} {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
