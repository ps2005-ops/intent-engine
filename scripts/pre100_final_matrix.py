#!/usr/bin/env python3
"""Score, compare and cluster whatever the live batch has finished. §9/§13.

Safe to run at any time against a directory the batch is still writing: a
company is read only once it has both text surfaces and a run.json, which is
the same completeness test the batch's own resume check uses.
"""
from __future__ import annotations

import collections
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from intent_engine.pre100 import audit as A                 # noqa: E402
from intent_engine.pre100 import quality as Q               # noqa: E402
from intent_engine.pre100 import specificity as S           # noqa: E402


def complete(d: pathlib.Path) -> bool:
    return bool(list(d.glob("*.txt"))) and (d / "run.json").exists()


def passages(d: pathlib.Path) -> dict:
    out = {}
    for field, surface, cue in S.FIELDS:
        if surface == "qa":
            text = " ".join(str(r.get("answer") or "")
                            for r in A.load_qa(d))
        else:
            p = d / f"{surface}.txt"
            text = p.read_text("utf-8", "replace") if p.exists() else ""
        out[field] = S.extract(cue, text)
    return out


#: A defect cluster is a (dimension, score-band) the run keeps landing in.
def cluster(rows: list) -> list:
    buckets: dict = collections.defaultdict(list)
    for row in rows:
        for name, score in row["dimensions"].items():
            if score is None:
                buckets[(name, "NOT_MEASURED")].append(row["company"])
            elif score <= 3:
                buckets[(name, "ABSENT_OR_ADMITTED")].append(row["company"])
            elif score <= 6:
                buckets[(name, "GENERIC")].append(row["company"])
    out = []
    for (name, band), companies in buckets.items():
        core = name in Q.CORE
        out.append({
            "dimension": name, "band": band,
            "companies": len(companies), "core": core,
            "example_companies": sorted(companies)[:6],
            # prevalence x quality loss x executive importance (§13)
            "impact": round(len(companies)
                            * (10 if band != "GENERIC" else 4)
                            * (2 if core else 1), 1),
        })
    return sorted(out, key=lambda r: -r["impact"])


def main() -> int:
    outdir = pathlib.Path(sys.argv[1])
    report_path = outdir / "MATRIX.json"
    dirs = sorted(d for d in outdir.iterdir()
                  if d.is_dir() and complete(d))
    rows, spec_rows = [], []
    for d in dirs:
        try:
            manifest = json.loads((d / "manifest.json").read_text("utf-8"))
        except Exception:                                   # noqa: BLE001
            manifest = {}
        name = manifest.get("company") or d.name
        quality = Q.score_company(d)
        quality["company"] = name
        rows.append({
            "company": name,
            "sha": manifest.get("deployed_sha", ""),
            "outcome": manifest.get("outcome", ""),
            "seconds": manifest.get("seconds"),
            "core_mean": quality["core_mean"],
            "core_min": quality["core_min"],
            "core_unmeasured": quality["core_unmeasured"],
            "dimensions": {x["dimension"]: x["score"]
                           for x in quality["dimensions"]},
            "evidence": {x["dimension"]: {"surface": x["surface"],
                                          "why": x["why"],
                                          "passage": x["passage"][:180]}
                         for x in quality["dimensions"]},
        })
        spec_rows.append({"company": name, "fields": passages(d)})
    means = [r["core_mean"] for r in rows if r["core_mean"] is not None]
    mins = [r["core_min"] for r in rows if r["core_min"] is not None]
    by_dim = {}
    for key, _s, _c in Q.DIMENSIONS:
        vals = [r["dimensions"].get(key) for r in rows]
        vals = [v for v in vals if v is not None]
        by_dim[key] = round(statistics.mean(vals), 2) if vals else None
    spec = S.compare(spec_rows) if len(spec_rows) > 1 else {}
    report = {
        "contract": "pre100_final_matrix.v1",
        "companies_scored": len(rows),
        "core_mean": round(statistics.mean(means), 2) if means else None,
        "core_min": min(mins) if mins else None,
        "dimension_means": by_dim,
        "clusters": cluster(rows),
        "specificity": {k: v for k, v in spec.items()
                        if k not in ("byte_identical", "near_identical")},
        "specificity_examples": {
            "byte_identical": (spec.get("byte_identical") or [])[:25],
            "near_identical": (spec.get("near_identical") or [])[:25]},
        "rows": rows,
    }
    report_path.write_text(json.dumps(report, indent=1), "utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("rows", "specificity_examples")},
                     indent=1)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
