"""Views A/B/C for prospect-98: the rules of scripts/prospect100/resume/
strengthened_gate.py (R12), unchanged, with the round's paths as arguments.

  A ORIGINAL      qualify98 grades (qualify100.grade, imported unchanged)
  B INTELLIGENCE  economics PASS for ECON_LED (a measured channel the original
                  classifier checks before evidence phrasing); strategy needs a
                  report; independence needs an outside observation the
                  analysis USED; presentation needs a deck
  C COMMERCIAL    every surface served, a deck or an evidence-limited page,
                  browser matrix clean, performance, identity
A company is fully qualified in a view only when EVERY metric there is PASS.

  python scripts/prospect98/strengthened98.py --qual Q.json --avail A.json \
      --history H.json --index CAPTURES/index.json --ui UI.json --out OUT.json
"""
from __future__ import annotations
import argparse, collections, json, pathlib, re

DIMS = ("search", "identity", "coverage", "independence", "economics",
        "strategy", "presentation", "history", "visual", "performance")
OUTSIDE = ("independent_reporting", "customer_voice", "competitor")
CDIMS = ("surfaces", "deck_or_limited_page", "browser_matrix", "performance", "identity")


def _slug(n):
    return re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")


def _load(p, d=None):
    try:
        return json.loads(pathlib.Path(p).read_text())
    except Exception:  # noqa: BLE001
        return d


def main():
    ap = argparse.ArgumentParser()
    for k in ("qual", "avail", "history", "index", "ui", "out"):
        ap.add_argument(f"--{k}", required=k in ("qual", "out"))
    a = ap.parse_args()
    qual = _load(a.qual)["companies"]
    avail = (_load(a.avail, {}) or {}).get("companies", {}) if a.avail else {}
    hist = {c["company"]: c for c in ((_load(a.history, {}) or {}).get("companies", []) if a.history else [])}
    index = (_load(a.index, {}) or {}) if a.index else {}
    ui = (((_load(a.ui, {}) or {}).get("summary") or {}).get("per_company") or {}) if a.ui else {}
    rows, counts = [], {v: collections.Counter() for v in "ABC"}
    for c in qual:
        name, g = c["company"], dict(c.get("grades") or {})
        av = avail.get(name) or {}
        obs = av.get("observation_classes") or {}
        has_report = bool(av.get("has_report"))
        surfaces = index.get(name) or {}
        deck = (surfaces.get("slides") or {}).get("status") == 200 and has_report
        B = dict(g)
        if c.get("decision_force") == "ECON_LED" and g.get("economics") != "FAIL":
            B["economics"] = "PASS"
        B["strategy"] = ("PASS" if g.get("strategy") == "PASS" and has_report else
                         "BOUNDED" if has_report or g.get("strategy") in ("PASS", "BOUNDED") else "FAIL")
        used = sum(int(obs.get(k) or 0) for k in OUTSIDE)
        B["independence"] = ("PASS" if g.get("independence") == "PASS" and used else
                             "BOUNDED" if used or g.get("independence") == "PASS" else g.get("independence"))
        B["presentation"] = ("PASS" if g.get("presentation") == "PASS" and deck else
                             "BOUNDED" if g.get("presentation") != "FAIL" else "FAIL")
        u = ui.get(_slug(name)) or {}
        served = bool(surfaces) and all(v.get("status") in (200, 303) for v in surfaces.values())
        C = {"surfaces": "PASS" if served else "FAIL",
             "deck_or_limited_page": "PASS" if deck else ("BOUNDED" if served else "FAIL"),
             "browser_matrix": ("PASS" if u.get("status") == "PASS" else "BOUNDED"
                                if u.get("status") == "PASS_WITH_A11Y_FINDINGS" else
                                "FAIL" if u else "NOT_MEASURED"),
             "performance": g.get("performance"), "identity": g.get("identity")}
        h = hist.get(name) or {}
        row = {"prospect_id": c["prospect_id"], "company": name, "split": c.get("split"),
               "A": g, "B": B, "C": C, "A_score": c.get("score"),
               "history_expanded": h.get("expanded"), "history_expanded_why": h.get("why"),
               "outside_observations_used": used, "has_report": has_report, "deck": deck,
               "blocker": c.get("blocker")}
        for view, grades in (("A", g), ("B", B), ("C", C)):
            row[f"{view}_fully_qualified"] = all(v == "PASS" for v in grades.values())
            counts[view]["fully_qualified"] += row[f"{view}_fully_qualified"]
            for d, v in grades.items():
                counts[view][f"{d}:{v}"] += 1
        row["false_decision_grade"] = g.get("strategy") == "PASS" and not has_report
        rows.append(row)
    summ = {"companies": len(rows),
            "fully_qualified": {v: counts[v]["fully_qualified"] for v in "ABC"},
            "pass_by_metric": {v: {d: counts[v].get(f"{d}:PASS", 0) for d in (DIMS if v != "C" else CDIMS)}
                               for v in "ABC"},
            "false_decision_grade": [r["company"] for r in rows if r["false_decision_grade"]],
            "independent_read_but_unused": [r["company"] for r in rows if r["A"].get("independence") in ("PASS", "BOUNDED")
                                            and not r["outside_observations_used"]],
            "history_expanded": dict(collections.Counter(r["history_expanded"] for r in rows))}
    pathlib.Path(a.out).write_text(json.dumps({"summary": summ, "companies": rows}, indent=1, default=str))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
