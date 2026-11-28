"""Original ten-metric scorecard for prospect-98, using qualify100.grade UNCHANGED.

The rubric is imported, not copied, so it cannot drift: the only adaptation is
the join key. Prospect-98 companies enter unregistered (no catalog entity id),
so rows are keyed by position ("p98-<position>") on both sides of the join.

  PYTHONPATH=src python scripts/prospect98/qualify98.py --pass reports/prospect98/baseline \
     --store reports/prospect98/baseline_store/ci.jsonl --ui <ui_matrix.json> --search <search.json> \
     --out docs/engineering/prospect98/qualification_baseline.json
"""
from __future__ import annotations
import argparse, collections, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts/prospect100"))
import qualify100 as Q  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pass", dest="p", required=True)
    ap.add_argument("--store", required=True)
    ap.add_argument("--ui")
    ap.add_argument("--search")
    ap.add_argument("--out", required=True)
    ap.add_argument("--split", default="DEVELOPMENT")
    ap.add_argument("--captures", default="", help="a re-rendered capture set (with index.json); "
                    "default: the journey's own captures merged into captures_final")
    a = ap.parse_args()
    P = (ROOT / a.p) if not pathlib.Path(a.p).is_absolute() else pathlib.Path(a.p)
    reg = json.loads((ROOT / "docs/engineering/prospect98/IDENTITY_REGISTRY.json").read_text())["companies"]
    reg = [c for c in reg if c["split"] in a.split.split(",")]
    rows = {}
    for f in sorted(P.glob("s*/state.json")) + [P / "rerun/state.json"]:
        s = Q._load(f, {}) or {}
        for r in (s.get("rows") or {}).values():
            if r.get("final_class"):
                r["catalog_entity_id"] = r.get("entity_id")
                r["entity_id"] = f"p98-{r['n']}"
                rows[r["entity_id"]] = r
    # A RE-RENDERED SET IS COMPLETE AS IT IS. A surface that answers 303 has no
    # page of its own (it IS its target), and filling the gap with the
    # journey's capture graded a page rendered by OLDER code -- the defect
    # this replaces, found when presentation repeats on result/sources pages
    # survived a render-only fix. Exactly qualify100's rule: merge the
    # journey's captures only when there is no re-render.
    merged = pathlib.Path(a.captures) if a.captures else P / "captures_final"
    merged.mkdir(exist_ok=True)
    if not a.captures:
        for cap in P.glob("s*/reports/next40_ui/*.html"):
            t = merged / cap.name
            if not t.exists():
                t.symlink_to(cap.resolve())
    elif any(x.is_symlink() for x in merged.glob("*.html")):
        raise SystemExit(f"{merged} holds journey symlinks (contaminated by an older "
                         "qualify98); re-render into a fresh directory")
    import os
    os.environ["PASS3_EXTRA_STORE"] = str((ROOT / a.store) if not a.store.startswith("/") else a.store)
    Q.P3 = P
    documents = Q._documents_read()
    repeats = Q.prose_repeats(merged)
    ui = ((Q._load(a.ui, {}) or {}).get("summary") or {}).get("per_company") if a.ui else None
    search = {r["prospect_id"]: r for r in ((Q._load(a.search, {}) or {}).get("rows", []) if a.search else [])}
    rendered = Q._load(merged / "index.json", {}) or {
        r["company"]: {k: {"status": v} for k, v in (r.get("surface_status") or {}).items()} for r in rows.values()}
    table = []
    for c in reg:
        rr = {"entity_id": f"p98-{c['position']}", "prospect_id": c["position"], "tier": c["category"],
              "common_name": rows.get(f"p98-{c['position']}", {}).get("company") or c["analysis_target"],
              "name_as_listed": c["name_as_listed"], "entry_readiness": "READY_SITE"}
        t = Q.grade(rr, rows, {}, search, ui, repeats, documents=documents, rendered_final=rendered)
        t["split"] = c["split"]
        table.append(t)
    dims = {d: dict(collections.Counter(t["grades"].get(d) for t in table)) for d in Q.DIMS}
    scores = [t["score"] for t in table if t.get("score") is not None]
    summary = {"companies": len(table), "mean": round(sum(scores) / max(1, len(scores)), 3),
               "ten_of_ten": sum(1 for t in table if t.get("score") == 10.0),
               "verdicts": dict(collections.Counter(t["verdict"] for t in table)), "dimensions": dims,
               "rubric": "scripts/prospect100/qualify100.py::grade (imported unchanged)"}
    pathlib.Path(a.out).write_text(json.dumps({"summary": summary, "companies": table}, indent=1, default=str))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
