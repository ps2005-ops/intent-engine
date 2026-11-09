"""Score the prospect-100 live pass with the program's own ten-dimension rubric.

Calls `next40_ten_dimensions.assess` -- the validated per-company judgement,
where 10/10 means complete, truthful handling and all four epistemic outcomes
can qualify -- on this pass's state and captures, and reports per tier.
Executive usefulness comes from `next40_analysis.executive_usefulness`, the
same measure, over the same captures. Nothing is re-implemented, so a score
here means exactly what it meant for the Next-40.

A dimension whose input was not measured stays NOT_MEASURED and is listed,
never counted as a pass (UI needs the separate width matrix).

Usage:
  PYTHONPATH=src python scripts/prospect100/score_pass.py
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))

import next40_analysis as NA  # noqa: E402
import next40_ten_dimensions as TD  # noqa: E402

OUT = ROOT / "reports/prospect100_pass2"
DOCS = ROOT / "docs/engineering/prospect100"
NAMES = ["IDENTITY", "EVIDENCE_PROVENANCE", "COMPANY_UNDERSTANDING",
         "ECONOMIC_INTELLIGENCE", "STRATEGIC_DECISION", "HISTORY",
         "DISCOVERY", "QA_ROLE", "UI", "EXECUTIVE_USEFULNESS"]


def _arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main() -> int:
    # --state may be given more than once (pass 3 ran as two shards);
    # --captures points at the pages to judge; --out names the scorecard.
    states = [ROOT / a for i, a in enumerate(sys.argv)
              if i and sys.argv[i - 1] == "--state"] or [OUT / "state.json"]
    ui = ROOT / _arg("--captures", str(OUT / "reports/next40_ui"))
    TD.UI = ui
    NA.UI = ui
    state = {"rows": {}, "live_sha": None}
    for f in states:
        part = json.loads(pathlib.Path(f).read_text())
        state["rows"].update(part.get("rows") or {})
        state["live_sha"] = state["live_sha"] or part.get("live_sha")
    try:
        priors = NA._prior_first()
    except Exception:                                        # noqa: BLE001
        priors = {}
    ui_index = {}
    if (ui / "index.json").exists():
        ui_index = json.loads((ui / "index.json").read_text())
    rows = sorted((r for r in state["rows"].values() if r.get("final_class")),
                  key=lambda r: r.get("n") or 0)
    out = []
    for r in rows:
        try:
            r["_usefulness"] = NA.executive_usefulness(NA.analyse(r, priors))
        except Exception:                                    # noqa: BLE001
            r["_usefulness"] = None
        a = TD.assess(r, ui_index)
        a["tier"] = r.get("category")
        a["final_class"] = r.get("final_class")
        a["core_s"] = r.get("core_s")
        out.append(a)

    tally = {n: collections.Counter() for n in NAMES}
    by_tier = collections.defaultdict(collections.Counter)
    classes = collections.Counter()
    for a in out:
        for n in NAMES:
            tally[n][a["dimensions"][n]] += 1
        by_tier[a["tier"]]["companies"] += 1
        by_tier[a["tier"]]["qualified"] += int(a["qualification_10_of_10"])
        classes[a["final_class"]] += 1
    cores = sorted(a["core_s"] for a in out if a.get("core_s"))
    summary = {
        "live_sha": state.get("live_sha"),
        "companies_scored": len(out),
        "qualification_10_of_10": sum(a["qualification_10_of_10"]
                                      for a in out),
        "epistemic_outcomes": dict(classes),
        "by_tier": {k: dict(v) for k, v in sorted(by_tier.items())},
        "dimensions": {n: dict(tally[n]) for n in NAMES},
        "core_s_p50": cores[len(cores) // 2] if cores else None,
        "core_s_p90": cores[max(0, int(len(cores) * 0.9) - 1)] if cores
        else None,
    }
    print(json.dumps(summary, indent=1))
    for a in out:
        if a["failed"]:
            print(f"  FAIL {a['n']:>3} {a['company'][:22]:22s} {a['failed']}")
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / _arg("--out", "pass2_scorecard.json")).write_text(json.dumps(
        {"summary": summary, "companies": out}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
