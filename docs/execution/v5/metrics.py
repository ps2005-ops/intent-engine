#!/usr/bin/env python3
"""Measure the V5 data gates, from the live ledger, with a date attached.

Same contract as the V4 measurer: a metric that cannot be measured is None,
never 0, because "we looked and there are none" and "we could not look" are
different claims and only the first is evidence.

    python3 docs/execution/v5/metrics.py            # measure and print
    python3 docs/execution/v5/metrics.py --write    # ... and update METRICS.json

WHY A SECOND FILE RATHER THAN MORE GATES IN THE FIRST
-----------------------------------------------------
The V4 file measures the gates the V4 graph declares, and V4 is frozen. Adding
V5 gates to it would make a frozen program's planner depend on capabilities
built after the freeze. `frontier.py` loads whichever metrics module sits
beside the graph it was pointed at, by path rather than by name, so the two
never collide.

THE POPULATION WALL IS ENFORCED HERE TOO
----------------------------------------
`historical_decision_episodes` counts the HISTORICAL corpus and nothing else.
It is deliberately measured from a different file than the prospective gates,
so a historical row has no path by which it could reach them. B-HIST-002 adds
the guard that proves it; this is the arrangement that makes the guard cheap.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "METRICS.json"

#: The live PAPER runtime tree, as in V4. Gates are measured against the
#: accumulating state, not against whatever worktree this runs from.
RUNTIME = pathlib.Path("/Users/prathamsharma/intent-engine-market/reports/market")
RUNTIME_LEDGER = RUNTIME / "learning_ledger.jsonl"
HISTORICAL_CORPUS = RUNTIME / "historical_corpus.jsonl"


def _rows(path):
    """Rows, or None when the file is absent. None is not an empty list."""
    path = pathlib.Path(path)
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


def _historical_episodes(path=HISTORICAL_CORPUS):
    """Episodes in the HISTORICAL corpus that survived the T0 wall.

    A row counts only if it is tagged HISTORICAL and carries both a T0 and a
    resolved observable: an episode with no later observation cannot validate
    anything, and counting it would clear B-RM-001's gate with rows that
    cannot train a reward model.

    Returns None when the corpus does not exist yet — not 0. B-HIST-001 has
    not run, which is a different fact from having run and found nothing.
    """
    rows = _rows(path)
    if rows is None:
        return None
    return sum(1 for r in rows
               if str(r.get("population") or "") == "HISTORICAL"
               and r.get("t0")
               and r.get("actual_observable") is not None)


def _measured_utility_inputs(rows):
    """Internal graph nodes carrying a utility-relevant measured quantity.

    C-MECH-001 refuses to propose a mechanism without these. Measured rather
    than assumed because the failure this gate exists to prevent is optimising
    an invented utility function, and a gate somebody typed would not prevent
    it.
    """
    return sum(1 for r in rows
               if r.get("record") == "internal_node"
               and r.get("utility_dimension")
               and r.get("measured") is True)


def _resolved_expectations(rows):
    """Declared expectations whose observable has since resolved.

    The denominator of calibration. An expectation declared after its outcome
    was known is excluded here as well as in the estimator, because a gate that
    admits them would let H-CAL-001 become runnable on rows the node itself
    would then throw away.
    """
    out = 0
    for r in rows:
        if r.get("record") != "expectation":
            continue
        if not r.get("resolved_at") or not r.get("observable"):
            continue
        declared, resolved = r.get("declared_at"), r.get("resolved_at")
        if declared and resolved and str(declared) >= str(resolved):
            continue
        out += 1
    return out


def measure(ledger=RUNTIME_LEDGER) -> dict:
    rows = _rows(ledger)
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    if rows is None:
        return {"measured_at": now, "source": str(ledger),
                "readable": False, "metrics": {}}

    decisions = [r for r in rows if r.get("record") == "research_decision"]
    prospective = [d for d in decisions
                   if d.get("provenance") == "PROSPECTIVE"]

    metrics = {
        # --- B: historical and policy learning ---------------------------
        "historical_decision_episodes": _historical_episodes(),
        # Carried over from V4 deliberately. B-DR-001 waits on the same fact
        # the V4 bandit node waits on — a logger that randomised — and two
        # differently-named copies of one measurement is how gates drift.
        "logged_exploration_events": sum(
            1 for d in prospective
            if d.get("selection_probability_status") == "KNOWN"),
        # --- C: behavioral game engine -----------------------------------
        "measured_utility_inputs": _measured_utility_inputs(rows),
        # --- H: meta-learning --------------------------------------------
        "resolved_expectations": _resolved_expectations(rows),
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
        print(f"  {key:36s} {'UNMEASURED' if value is None else value}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
