#!/usr/bin/env python3
"""§60, §97. Crawl every primary page and count the dead ends.

    python scripts/customer_copy_sweep.py reports/wave/g

Reads the captured surfaces of a wave and adjudicates every absence phrase on
them. The required result is ZERO unresolved occurrences on a primary page —
bounded explanations are allowed and are the whole point, so this counts
absences that TERMINATE rather than absences that exist.

Kept separate from the rubric because it answers a different question. The
rubric asks whether each dimension is present and good; this asks whether any
sentence anywhere leaves a reader with nothing to do. A page can score ten on
every dimension and still contain one.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from intent_engine.founder_brief import absence, flow      # noqa: E402

PRIMARY = tuple(step.key for step in flow.STEPS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("wave")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    root = pathlib.Path(args.wave)
    report, total, headline = {}, 0, 0
    for company_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for key in PRIMARY:
            page = company_dir / f"{key}.html"
            if not page.exists():
                continue
            markup = page.read_text()
            dead = absence.adjudicate(markup)
            heads = absence.headline_dead_end(markup)
            if dead or heads:
                report.setdefault(company_dir.name, {})[key] = {
                    "unresolved": [d.as_dict() for d in dead],
                    "headline": [d.as_dict() for d in heads]}
                total += len(dead)
                headline += len(heads)

    for company, surfaces in report.items():
        for surface, found in surfaces.items():
            for row in found["headline"]:
                print(f"  HEADLINE {company}/{surface}: {row['sentence'][:110]}")
            for row in found["unresolved"]:
                print(f"  DEAD-END {company}/{surface}: "
                      f"{row['phrase']!r} — {row['sentence'][:110]}")
    print(f"\n  {total} unresolved absence(s), {headline} in a heading, "
          f"across {len(list(root.iterdir()))} companies")
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(
            {"unresolved": total, "headline": headline, "detail": report},
            indent=2))
    return 0 if total == 0 and headline == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
