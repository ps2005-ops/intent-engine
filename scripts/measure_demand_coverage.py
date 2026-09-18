"""Demand-chain coverage over the live ledger, before and after a change.

E-DEM-001 asks for coverage "measured before and after", and a number without
a method is not a measurement — the same corpus can be made to look twice as
covered by counting states per evidence row instead of per company.

So this is the method, fixed in one place:

    cells       = company x state pairs the corpus actually observes
    possible    = companies x states
    by_state    = how many companies observe each state

The denominator is every company with any evidence, not every company with
demand evidence. Restricting it to companies that already have demand would
report a coverage of 1.0 the moment one company had one state.

    python3 scripts/measure_demand_coverage.py [ledger.jsonl]
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from intent_engine.market import demand_chain as DC  # noqa: E402

DEFAULT = pathlib.Path("/Users/prathamsharma/intent-engine-market/reports/"
                       "market/learning_ledger.jsonl")


def measure(rows) -> dict:
    evidence = [r for r in rows if r.get("record") == "evidence"]
    companies = sorted({r.get("subject_company") for r in evidence
                        if r.get("subject_company")})
    by_state: collections.Counter = collections.Counter()
    cells = 0
    with_any = 0
    for company in companies:
        states = DC.read_states(rows, company_id=company,
                                aliases=(company, company.replace('-', ' ')))
        cells += len(states)
        with_any += 1 if states else 0
        for state in states:
            by_state[state] += 1
    possible = len(companies) * len(DC.STATES)
    return {
        "evidence_rows": len(evidence),
        "companies": len(companies),
        "states": len(DC.STATES),
        "cells_observed": cells,
        "cells_possible": possible,
        "coverage": round(cells / possible, 4) if possible else None,
        "companies_with_any_state": with_any,
        "by_state": {s: by_state.get(s, 0) for s in DC.STATES},
        # The states with nothing at all. Named rather than counted: which
        # ones are missing decides whether a transmission path can be built,
        # and a mediator missing from the middle breaks every link through it.
        "states_with_zero_companies": [s for s in DC.STATES
                                       if not by_state.get(s)],
    }


def main() -> int:
    path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    if not path.exists():
        print(f"no ledger at {path}")
        return 1
    rows = [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]
    got = measure(rows)
    print(f"ledger {path}")
    print(f"  evidence rows              {got['evidence_rows']}")
    print(f"  companies                  {got['companies']}")
    print(f"  cells observed / possible  {got['cells_observed']} / "
          f"{got['cells_possible']}   ({got['coverage']})")
    print(f"  companies with any state   {got['companies_with_any_state']}")
    print("  by state:")
    for state, count in got["by_state"].items():
        print(f"    {state:20s} {count:3d} companies")
    if got["states_with_zero_companies"]:
        print("  ZERO COMPANIES: "
              + ", ".join(got["states_with_zero_companies"]))
        print("  A state with no companies breaks every transmission link "
              "that runs through it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
