"""Three qualification views. The original is never altered.

  A  ORIGINAL       qualify100.py's grades, copied unchanged.
  B  INTELLIGENCE   the same ten metrics, each tightened to what the page
                    actually carries:
       strategy       decision-grade only when a strategic report EXISTS and
                      the original class was decision-grade (5 companies in
                      round 6 were classed decision-grade with no report)
       independence   >= 2 independent origins (original rule) AND >= 1
                      observation the analysis drew from an outside class --
                      an outside article read and never used is not evidence
       presentation   a deck exists (slides answered 200 on a composed
                      report) AND no prose repeated (original rule)
       history        original rule; the expanded private-company grade is
                      reported beside it and never substituted for it
       others         as the original
  C  COMMERCIAL     the product, not the reasoning: every surface answered
                    (200, or 303 to a page that exists), a deck or an explicit
                    evidence-limited page, the browser matrix clean for this
                    company, the performance gates passed.

A company is FULLY QUALIFIED only when every applicable metric in a view is
PASS -- never by an average. Status-only companies are reported separately.

  python scripts/prospect100/resume/strengthened_gate.py ROUND
      reads docs/engineering/prospect100/resume/{qualification,report_
      availability,ui_matrix,history_expanded}_rROUND.json and the round's
      re-render index; writes strengthened_rROUND.json
"""
from __future__ import annotations

import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs/engineering/prospect100/resume"
DIMS = ("search", "identity", "coverage", "independence", "economics",
        "strategy", "presentation", "history", "visual", "performance")
OUTSIDE = ("independent_reporting", "customer_voice", "competitor")


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _load(path, default=None):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except Exception:                                        # noqa: BLE001
        return default


def main() -> int:
    rnd = sys.argv[1]
    qual = _load(DOCS / f"qualification_r{rnd}.json")["companies"]
    avail = (_load(DOCS / f"report_availability_r{rnd}.json", {}) or {}
             ).get("companies", {})
    hist = {c["company"]: c for c in (_load(
        DOCS / f"history_expanded_r{rnd}.json", {}) or {}).get("companies", [])}
    index = _load(ROOT / f"reports/prospect100_resume/r{rnd}/captures_final/"
                  "index.json", {}) or {}
    ui = ((_load(DOCS / f"ui_matrix_r{rnd}.json", {}) or {}).get("summary")
          or {}).get("per_company") or {}
    rows, counts = [], {v: collections.Counter() for v in "ABC"}
    for c in qual:
        name, g = c["company"], dict(c.get("grades") or {})
        if c.get("verdict") == "STATUS_PAGE_BY_DESIGN":
            rows.append({"prospect_id": c["prospect_id"], "company": name,
                         "kind": "STATUS_PAGE", "A": g})
            continue
        a = avail.get(name) or {}
        obs = a.get("observation_classes") or {}
        has_report = bool(a.get("has_report"))
        surfaces = index.get(name) or {}
        deck = (surfaces.get("slides") or {}).get("status") == 200 \
            and has_report
        B = dict(g)
        B["strategy"] = ("PASS" if g.get("strategy") == "PASS" and has_report
                         else "BOUNDED" if has_report or g.get("strategy")
                         in ("PASS", "BOUNDED") else "FAIL")
        outside_used = sum(int(obs.get(k) or 0) for k in OUTSIDE)
        B["independence"] = ("PASS" if g.get("independence") == "PASS"
                             and outside_used else
                             "BOUNDED" if outside_used or g.get(
                                 "independence") == "PASS" else
                             g.get("independence"))
        B["presentation"] = ("PASS" if g.get("presentation") == "PASS"
                             and deck else
                             "BOUNDED" if g.get("presentation") != "FAIL"
                             else "FAIL")
        u = ui.get(_slug(name)) or {}
        all_served = bool(surfaces) and all(
            v.get("status") in (200, 303) for v in surfaces.values())
        C = {
            "surfaces": "PASS" if all_served else "FAIL",
            "deck_or_limited_page": "PASS" if deck else (
                "BOUNDED" if all_served else "FAIL"),
            "browser_matrix": ("PASS" if u.get("status") == "PASS" else
                               "BOUNDED" if u.get("status") ==
                               "PASS_WITH_A11Y_FINDINGS" else
                               "FAIL" if u else "NOT_MEASURED"),
            "performance": g.get("performance"),
            "identity": g.get("identity"),
        }
        h = hist.get(name) or {}
        row = {"prospect_id": c["prospect_id"], "company": name,
               "kind": "ANALYTICAL", "A": g, "B": B, "C": C,
               "history_expanded": h.get("expanded"),
               "outside_observations": outside_used,
               "has_report": has_report, "deck": deck}
        for view, grades in (("A", g), ("B", B), ("C", C)):
            row[f"{view}_fully_qualified"] = all(
                v == "PASS" for v in grades.values())
            counts[view]["fully_qualified"] += row[f"{view}_fully_qualified"]
            for d, v in grades.items():
                counts[view][f"{d}:{v}"] += 1
        row["false_decision_grade"] = (g.get("strategy") == "PASS"
                                       and not has_report)
        rows.append(row)
    analytical = [r for r in rows if r["kind"] == "ANALYTICAL"]
    summary = {
        "round": rnd, "analytical": len(analytical),
        "status_pages": len(rows) - len(analytical),
        "fully_qualified": {v: counts[v]["fully_qualified"] for v in "ABC"},
        "pass_by_metric": {v: {d: counts[v].get(f"{d}:PASS", 0)
                               for d in (DIMS if v != "C" else
                                         ("surfaces", "deck_or_limited_page",
                                          "browser_matrix", "performance",
                                          "identity"))} for v in "ABC"},
        "false_decision_grade": [r["company"] for r in analytical
                                 if r["false_decision_grade"]],
        "independent_read_but_unused": [
            r["company"] for r in analytical
            if r["A"].get("independence") in ("PASS", "BOUNDED")
            and not r["outside_observations"]],
    }
    (DOCS / f"strengthened_r{rnd}.json").write_text(json.dumps(
        {"summary": summary, "companies": rows}, indent=1, default=str) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
