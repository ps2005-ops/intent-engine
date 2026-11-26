"""Is the qualification loop still producing information?

Reads docs/engineering/prospect100/resume/rounds_companies.csv (one row per
company per round, the ten original metrics as PASS/BOUNDED/FAIL) and answers
three questions a round should be able to answer BEFORE it is run:

1. BINDING: which metrics stand between companies and 10/10, and how many
   companies are blocked by exactly one metric?
2. CEILING: is there a pair of metrics that no company passes together? If
   so, no shared improvement to any OTHER metric can produce a qualifier,
   and a full-universe round cannot move the 10/10 count.
3. STAGNATION: over the last `window` rounds, did the pass counts of the
   binding metrics move? A round that moves only non-binding metrics is
   recorded as non-informative for qualification.

Measured 2026-11-26 on R4-R12: history passes exactly the 12 SEC filers,
independence passes 7 private companies, and the intersection is empty.
"""
from __future__ import annotations

import collections
import csv
import itertools
import json
import sys
from typing import Dict, List

METRICS = ("search", "identity", "coverage", "independence", "economics",
           "strategy", "presentation", "history", "visual", "performance")


def load(path) -> Dict[int, List[dict]]:
    by: Dict[int, List[dict]] = collections.defaultdict(list)
    for r in csv.DictReader(open(path)):
        flags = {m: r.get(f"A_{m}", "") for m in METRICS}
        if not any(flags.values()):
            continue
        by[int(r["round"])].append({"company": r["company"], **flags})
    return dict(sorted(by.items()))


def analyse(by_round: Dict[int, List[dict]], *, window: int = 3) -> dict:
    rounds = sorted(by_round)
    last = by_round[rounds[-1]]
    passers = {m: {c["company"] for c in last if c[m] == "PASS"} for m in METRICS}
    counts = {m: len(passers[m]) for m in METRICS}
    blocked_by_one = collections.Counter()
    for c in last:
        fails = [m for m in METRICS if c[m] != "PASS"]
        if len(fails) == 1:
            blocked_by_one[fails[0]] += 1
    hard = sorted(METRICS, key=lambda m: counts[m])[:4]
    empty_pairs = [(a, b) for a, b in itertools.combinations(hard, 2)
                   if not passers[a] & passers[b]]
    history = {m: [sum(1 for c in by_round[r] if c[m] == "PASS") for r in rounds]
               for m in METRICS}
    qualified = [sum(1 for c in by_round[r] if all(c[m] == "PASS" for m in METRICS))
                 for r in rounds]
    binding = hard[:2]
    recent = rounds[-window:]
    moved = {m: max(history[m][-window:]) - min(history[m][-window:]) for m in binding}
    stagnant = (len(rounds) >= window and len(set(qualified[-window:])) == 1
                and all(v <= 2 for v in moved.values()))
    return {
        "rounds": rounds, "qualified_by_round": qualified,
        "pass_counts_last_round": counts,
        "hardest_metrics": hard,
        "blocked_by_exactly_one_metric": dict(blocked_by_one),
        "structural_ceiling": [
            {"metrics": list(p), "passers": {p[0]: sorted(passers[p[0]]),
                                             p[1]: sorted(passers[p[1]])},
             "meaning": "no company passes both, so improving any other "
                        "metric cannot produce a 10/10 qualifier"}
            for p in empty_pairs],
        "binding_metric_history": {m: history[m] for m in binding},
        "stagnant": stagnant,
        "window_rounds": recent,
        "verdict": ("STRUCTURAL_CEILING" if empty_pairs else
                    "STAGNANT" if stagnant else "PRODUCTIVE"),
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "docs/engineering/prospect100/resume/rounds_companies.csv"
    print(json.dumps(analyse(load(path)), indent=1))
