"""One table of every scored round, built only from the committed round files.

  python scripts/prospect100/resume/rounds_summary.py
writes docs/engineering/prospect100/resume/rounds_summary.json and
rounds_companies.csv (one row per company per round, original + strengthened).
"""
from __future__ import annotations

import csv
import json
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[3]
P100 = ROOT / "docs/engineering/prospect100"
RES = P100 / "resume"
DIMS = ("search", "identity", "coverage", "independence", "economics",
        "strategy", "presentation", "history", "visual", "performance")


def _load(p):
    try:
        return json.loads(pathlib.Path(p).read_text())
    except Exception:                                        # noqa: BLE001
        return None


def main() -> int:
    rounds = {"4": P100 / "qualification_100_pass4.json"}
    for n in range(5, 30):
        if (RES / f"qualification_r{n}.json").exists():
            rounds[str(n)] = RES / f"qualification_r{n}.json"
    table, rows = [], []
    for n, path in rounds.items():
        q = _load(path)["companies"]
        scores = [c["score"] for c in q if c.get("score") is not None]
        meta = _load(RES / f"round{n}_meta.json") or {}
        strong = _load(RES / f"strengthened_r{n}.json") or {}
        hist = (_load(RES / f"history_expanded_r{n}.json") or {}).get(
            "summary", {})
        avail = (_load(RES / f"report_availability_r{n}.json") or {}).get(
            "companies", {})
        table.append({
            "round": int(n),
            "commit": meta.get("analysis_commit", "cc04b23a" if n == "4" else ""),
            "analytical": len(scores),
            "mean": round(statistics.mean(scores), 3),
            "median": statistics.median(scores),
            "ten_of_ten_original": sum(1 for s in scores if s == 10.0),
            "pass_original": {d: sum(1 for c in q if (c.get("grades") or {})
                                     .get(d) == "PASS") for d in DIMS},
            "pass_strengthened": (strong.get("summary") or {})
            .get("pass_by_metric", {}).get("B"),
            "pass_commercial": (strong.get("summary") or {})
            .get("pass_by_metric", {}).get("C"),
            "fully_qualified": (strong.get("summary") or {})
            .get("fully_qualified"),
            "false_decision_grade": (strong.get("summary") or {})
            .get("false_decision_grade"),
            "decks_missing": sorted(c for c, v in avail.items()
                                    if not (v.get("availability") or {})
                                    .get("slides_ready")) if avail else None,
            "history_expanded": hist.get("expanded"),
        })
        sb = {r["company"]: r for r in (strong.get("companies") or [])}
        for c in q:
            if c.get("score") is None:
                continue
            b = (sb.get(c["company"]) or {}).get("B") or {}
            rows.append({"round": n, "prospect_id": c["prospect_id"],
                         "company": c["company"], "score": c["score"],
                         **{f"A_{d}": (c.get("grades") or {}).get(d)
                            for d in DIMS},
                         **{f"B_{d}": b.get(d) for d in DIMS},
                         "C_fully_qualified": (sb.get(c["company"]) or {})
                         .get("C_fully_qualified")})
    (RES / "rounds_summary.json").write_text(json.dumps(table, indent=1) + "\n")
    with open(RES / "rounds_companies.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for t in table:
        print(t["round"], t["commit"], t["mean"], t["fully_qualified"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
