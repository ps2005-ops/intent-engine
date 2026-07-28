#!/usr/bin/env python3
"""Run the live pipeline N times per company and measure variance.

    python scripts/live_stability.py --runs 3

A single good live run proves the fix worked once. It says nothing about
whether a stranger opening the product tomorrow sees the same thing, which is
the only question that matters before handing out the link. Each run is fully
independent — a fresh store, fresh discovery, fresh retrieval — so anything
that varies here would vary for a real reader.

Reports, per company: how many sources were admitted, how much text was
extracted, which evidence families appeared, the quality outcome, and whether
the named acceptance vocabulary survived into the report — with the spread
across runs for each.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from intent_engine.company_ingestion.records import (              # noqa: E402
    MAX_APPROVED_SOURCES,
)
sys.path.insert(0, os.path.dirname(__file__))
from retrieval_trace import run as trace_run                      # noqa: E402

COMPANIES = (
    ("Palantir", "https://www.palantir.com",
     ("foundry", "gotham", "aip", "government", "commercial", "customer",
      "platform")),
    ("Shopify", "https://www.shopify.com",
     ("commerce", "merchant", "customer", "platform")),
    ("Sony", "https://www.sony.com", ()),
)


def _spread(values):
    numbers = [v for v in values if isinstance(v, (int, float))]
    if not numbers:
        return {"values": list(values)}
    return {"values": numbers, "min": min(numbers), "max": max(numbers),
            "mean": round(statistics.mean(numbers), 1),
            "spread_pct": (round(100 * (max(numbers) - min(numbers))
                                 / max(1, statistics.mean(numbers)), 1))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out", default="reports/live_stability.json")
    args = parser.parse_args()

    summary = {}
    for name, website, vocabulary in COMPANIES:
        passes = []
        for index in range(args.runs):
            payload = trace_run(name, website, out_path="",
                                max_sources=MAX_APPROVED_SOURCES)
            report = payload["report"]
            passes.append({
                "admitted": payload["totals"]["admitted"],
                "chars": payload["totals"]["chars_extracted"],
                "metadata_only": payload["totals"][
                    "metadata_only_admissions"],
                "quality": report["quality_outcome"],
                "coverage": report["coverage_state"],
                "families": sorted(report["families"] or []),
                "vocabulary": {term: report["vocabulary"].get(term, 0)
                               for term in vocabulary},
            })
            print(f"  {name} run {index + 1}/{args.runs}: "
                  f"{passes[-1]['admitted']} sources, "
                  f"{passes[-1]['chars']:,} chars, "
                  f"{passes[-1]['quality']}")

        families = [tuple(p["families"]) for p in passes]
        vocab_stable = {}
        for term in vocabulary:
            counts = [p["vocabulary"][term] for p in passes]
            vocab_stable[term] = {
                "present_in_all_runs": all(c > 0 for c in counts),
                "counts": counts,
            }
        summary[name] = {
            "runs": args.runs,
            "admitted": _spread([p["admitted"] for p in passes]),
            "chars": _spread([p["chars"] for p in passes]),
            "metadata_only": _spread([p["metadata_only"] for p in passes]),
            "quality_outcomes": sorted({p["quality"] for p in passes}),
            "coverage_states": sorted({p["coverage"] for p in passes}),
            "families_identical_across_runs": len(set(families)) == 1,
            "families": sorted(set(families))[0] if families else [],
            "vocabulary": vocab_stable,
        }
        print(f"{name}: quality={summary[name]['quality_outcomes']} "
              f"families_stable={summary[name]['families_identical_across_runs']}")
        print()

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as handle:
            json.dump(summary, handle, indent=2, sort_keys=True)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
