#!/usr/bin/env python3
"""One immutable matrix over every capture we already hold. §3.

Development happens against THIS before any live quota is spent. A defect
already present in a capture does not need a live analysis to find.
"""
from __future__ import annotations

import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from intent_engine.pre100 import audit as A                 # noqa: E402
from intent_engine.pre100 import quality as Q               # noqa: E402
from intent_engine.pre100 import specificity as S           # noqa: E402

BASE = ROOT / "docs/execution/v5/pre100_50"
CAPTURES = BASE / "live_captures"


def newest_per_company() -> dict:
    """The newest capture each company has, by capture timestamp.

    Ordered by the manifest's own `captured_at` rather than by a hand-kept
    list of SHAs: a list has to be edited every wave and was wrong once.
    """
    latest = {}
    for manifest in CAPTURES.glob("*/*/manifest.json"):
        try:
            m = json.loads(manifest.read_text("utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        name, when = m.get("company"), str(m.get("captured_at") or "")
        if not name:
            continue
        # An empty capture has not measured this company.
        if not list(manifest.parent.glob("*.txt")):
            continue
        if name not in latest or when > latest[name][0]:
            latest[name] = (when, manifest.parent, m)
    return latest


def field_passages(company_dir: pathlib.Path) -> dict:
    out = {}
    for field, surface, cue in S.FIELDS:
        if surface == "qa":
            rows = A.load_qa(company_dir)
            text = " ".join(str(r.get("answer") or "") for r in rows)
        else:
            path = company_dir / f"{surface}.txt"
            text = path.read_text("utf-8", "replace") if path.exists() else ""
        out[field] = S.extract(cue, text)
    return out


def main() -> int:
    out_path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else \
        BASE / "final" / "DEVELOPMENT_MATRIX.json"
    latest = newest_per_company()
    rows, spec_rows = [], []
    for name, (when, company_dir, manifest) in sorted(latest.items()):
        quality = Q.score_company(company_dir)
        fields = field_passages(company_dir)
        spec_rows.append({"company": name, "fields": fields})
        rows.append({
            "company": name,
            "captured_at": when,
            "sha": manifest.get("deployed_sha", ""),
            "outcome": manifest.get("outcome", ""),
            "core_mean": quality["core_mean"],
            "core_min": quality["core_min"],
            "core_unmeasured": quality["core_unmeasured"],
            "dimensions": {d["dimension"]: d["score"]
                           for d in quality["dimensions"]},
        })
    spec = S.compare(spec_rows)
    by_dim = {}
    for key, _s, _c in Q.DIMENSIONS:
        vals = [r["dimensions"].get(key) for r in rows]
        vals = [v for v in vals if v is not None]
        by_dim[key] = round(statistics.mean(vals), 2) if vals else None
    means = [r["core_mean"] for r in rows if r["core_mean"] is not None]
    report = {
        "contract": "pre100_development_matrix.v1",
        "companies": len(rows),
        "core_mean": round(statistics.mean(means), 2) if means else None,
        "dimension_means": by_dim,
        "specificity": {k: v for k, v in spec.items() if k != "near_identical"
                        and k != "byte_identical"},
        "specificity_examples": {
            "byte_identical": spec["byte_identical"][:20],
            "near_identical": spec["near_identical"][:20],
        },
        "rows": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=1), "utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"
                      and k != "specificity_examples"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
