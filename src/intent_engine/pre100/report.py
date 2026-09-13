"""The gauntlet report: what the fifty companies actually did.

Computed from the captures rather than narrated from them. The distinction is
the point -- a number a person reads off a page and retypes is a number that
drifts, and this programme has already lost one intelligence-quality score to
an instrument that had quietly stopped measuring.
"""
from __future__ import annotations

import json
import pathlib

from intent_engine.pre100 import verdict as V
from intent_engine.webapp import outcome as O


def _median(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    mid = len(values) // 2
    return (values[mid] if len(values) % 2
            else round((values[mid - 1] + values[mid]) / 2, 1))


def _percentile(values, pct):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    index = min(len(values) - 1, int(round((pct / 100.0) * (len(values) - 1))))
    return values[index]


def gather(capture_root, sha: str = "") -> dict:
    """Every company captured, scored, on one SHA (or all of them)."""
    root = pathlib.Path(capture_root)
    shas = [sha] if sha else [d.name for d in sorted(root.iterdir())
                              if d.is_dir()]
    rows = []
    for one in shas:
        base = root / one
        if not base.is_dir():
            continue
        for company in sorted(base.iterdir()):
            if company.is_dir() and (company / "manifest.json").exists():
                rows.append(V.verdict(company))
    return {"sha": sha, "companies": rows}


def summarise(gathered: dict) -> dict:
    # A capture in flight is not a result. Counting it either way -- as a
    # pass or as a failure -- reports a company that has not finished.
    rows = [r for r in gathered["companies"] if not r.get("capturing")]
    capturing = sum(1 for r in gathered["companies"] if r.get("capturing"))
    codes: dict = {}
    for row in rows:
        for failure in row["failures"]:
            codes[failure["code"]] = codes.get(failure["code"], 0) + 1
    outcomes: dict = {}
    for row in rows:
        key = row["outcome"] or "(not stated)"
        outcomes[key] = outcomes.get(key, 0) + 1
    firsts = [r.get("first_useful") for r in rows]
    return {
        "total": len(rows),
        "capturing": capturing,
        "passed": sum(1 for r in rows if r["passed"]),
        "full": outcomes.get(O.FULL_ANALYSIS, 0),
        "refreshing": outcomes.get(O.FULL_ANALYSIS_REFRESHING, 0),
        "true_scarcity": outcomes.get(O.TRUE_EVIDENCE_SCARCITY, 0),
        "operational_failure": sum(outcomes.get(s, 0)
                                   for s in O.OPERATIONAL_FAILURE),
        "not_stated": outcomes.get("(not stated)", 0),
        "by_outcome": dict(sorted(outcomes.items(), key=lambda kv: -kv[1])),
        "by_failure": dict(sorted(codes.items(), key=lambda kv: -kv[1])),
        "false_scarcity": codes.get("FALSE_SCARCITY", 0),
        "failure_page": codes.get("FAILURE_PAGE", 0),
        "wrong_identity": codes.get("WRONG_IDENTITY", 0),
        "lost_runs": codes.get("LOST_RUN", 0),
        "redirect_loops": codes.get("REDIRECT_LOOP", 0),
        "raw_repr": codes.get("RAW_REPR_IN_QA", 0),
        "outcome_disagreements": codes.get("OUTCOME_DISAGREEMENT", 0),
        "median_first_useful": _median(firsts),
        "p95_first_useful": _percentile(firsts, 95),
    }


def table(gathered: dict) -> str:
    lines = [f"{'company':30s} {'outcome':30s} {'1st':>5s} {'qa':>3s} "
             f"{'pass':>5s}  finding"]
    for row in sorted(gathered["companies"], key=lambda r: r["company"]):
        finding = (row["failures"][0]["code"] + ":" +
                   row["failures"][0]["detail"][:34]) if row["failures"] else ""
        state = ("....." if row.get("capturing")
                 else ("PASS" if row["passed"] else "FAIL"))
        lines.append(
            f"{row['company'][:30]:30s} {(row['outcome'] or '-')[:30]:30s} "
            f"{str(row.get('first_useful') or '-'):>5s} "
            f"{row['qa_answers']:>3d} "
            f"{state:>5s}  {finding}")
    return "\n".join(lines)


def main(argv=None) -> int:
    import sys
    argv = list(argv if argv is not None else sys.argv[1:])
    root = argv[0] if argv else "docs/execution/v5/pre100_50/live_captures"
    sha = argv[1] if len(argv) > 1 else ""
    gathered = gather(root, sha)
    print(table(gathered))
    print()
    print(json.dumps(summarise(gathered), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
