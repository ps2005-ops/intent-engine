"""The 100-company qualification table: one row per company, no averages.

Joins what was MEASURED, each from its own artifact, and grades ten
dimensions separately so a run can pass on honesty while failing on depth:

  1 identity      registry verified (Pass 1) and the run's surfaces name it
  2 search        every typed prefix puts it first (search_matrix.json)
  3 coverage      documents the run read and dated (history.dated_documents)
  4 independence  independent, relevant origins (discovery.independent_origins)
  5 economics     the decision is evidence-led, or only a class prior
  6 strategy      a decision-grade reading, or an honest abstention
  7 presentation  every surface renders, with no prose repeated on a page
  8 history       History Rewind level A/B/C
  9 visual        10 widths x 2 themes, from ui_matrix.json
 10 performance   analysis within its 120 s maximum, surfaces within budget

Each grade is PASS (1), BOUNDED (0.5: correct and honest, but limited by
evidence or by design) or FAIL / NOT_MEASURED (0). 10/10 requires ten PASSes.
A NOT_MEASURED dimension is never a pass.

Usage: PYTHONPATH=src python scripts/prospect100/qualify100.py
"""
from __future__ import annotations

import collections
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import yaml  # noqa: E402

DOCS = ROOT / "docs/engineering/prospect100"
P2 = ROOT / "reports/prospect100_pass2"
import os
#: Which local pass to qualify (default pass 3); pass 4 = the news channel.
P3 = ROOT / "reports" / os.environ.get("QUALIFY_PASS", "prospect100_pass3")

PASS, BOUNDED, FAIL, NM = "PASS", "BOUNDED", "FAIL", "NOT_MEASURED"
VALUE = {PASS: 1.0, BOUNDED: 0.5, FAIL: 0.0, NM: 0.0}
DIMS = ("identity", "search", "coverage", "independence", "economics",
        "strategy", "presentation", "history", "visual", "performance")

#: Table furniture that legitimately repeats once per row of a list; anything
#: else repeated on one page is prose said twice.
_FURNITURE = re.compile(
    r"^(Independent voice:|Another document from a source already counted|"
    r"No source of this kind was found to try|Would sit with:|"
    r"This is the first published reading|A regulatory filing written by|"
    r"public daily closes)", re.I)


def _load(path, default=None):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except Exception:                                        # noqa: BLE001
        return default


def _rows(*state_files):
    out = {}
    for f in state_files:
        s = _load(f, {}) or {}
        for r in (s.get("rows") or {}).values():
            if r.get("final_class"):
                out[r["entity_id"]] = r
    return out


def _documents_read() -> dict:
    """run_id -> documents retrieved, from the pass-3 store copy."""
    import collections as _c
    counts = _c.Counter()
    scratch = pathlib.Path(__import__("os").environ.get("PASS3_EXTRA_STORE", ""))
    for store in (P3 / "captures_final_store" / "ci.jsonl", scratch):
        if not store or not store.is_file():
            continue
        with open(store, encoding="utf-8") as fh:
            for line in fh:
                if '"ci.source_retrieved"' in line:
                    try:
                        counts[json.loads(line).get("run_id")] += 1
                    except ValueError:
                        continue
    return dict(counts)


def _slug(company):
    return re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")


def prose_repeats(captures: pathlib.Path) -> dict:
    """Per company slug: count of prose sentences said 2+ times on one page."""
    from repetition_audit import audit
    rep = audit(captures, strip_svg=True)
    per = collections.Counter()
    for page, dup in rep["repeats"].items():
        # History Rewind keeps every year's panel in the page and shows one at
        # a time (display:none on the rest), so a sentence shared by two
        # years is never on screen twice. Static text cannot see that.
        if page.endswith("-history.html"):
            continue
        slug = page.rpartition("-")[0]
        per[slug] += sum(1 for s in dup if not _FURNITURE.match(s)
                         and len(s) >= 60)
    return dict(per)


#: Timing gates only. AUTOCOMPLETE is a search result and is graded under
#: search; counting it here made Datarails a "performance failure".
_TIMING_GATES = ("CORE_WITHIN_120S", "SUBMIT_ACK_2S", "VISIBLE_PROGRESS_3S",
                 "NO_ENDLESS_SPINNER")


def grade(reg, local, live, search, ui, repeats, core_budget=120.0,
          documents=None, rendered_final=None):
    eid = reg["entity_id"]
    row = local.get(eid)
    out = {"prospect_id": reg["prospect_id"], "tier": reg["tier"],
           "company": reg.get("common_name") or reg["name_as_listed"],
           "entity_id": eid, "listing": reg.get("listing"),
           "entry": reg.get("entry_readiness")}
    srow = search.get(reg["prospect_id"]) or {}
    s = srow.get("search_status")
    shared = [q["typed"] + " -> " + str(q["top"]) for q in srow.get("queries", [])
              if q.get("verdict") == "BOUNDED_SHARED_PREFIX"]
    out["search_bounded"] = shared
    stop = reg.get("entry_readiness") == "STOP_NO_LONGER_INDEPENDENT"
    g = {}
    g["search"] = (BOUNDED if s == "PASS" and shared else
                   PASS if s == "PASS" else (FAIL if s else NM))
    if stop:
        # Not analysable by design: the right answer is the status page.
        g["identity"] = PASS
        for d in DIMS[2:]:
            g[d] = "N/A"
        out.update(grades=g, score=None, verdict="STATUS_PAGE_BY_DESIGN",
                   blocker=("no longer independent -- the product shows the "
                            "status page and opens no run (verified live)"),
                   live_verified=True, local_verified=True)
        return out
    live_row = live.get(eid)
    out["live_verified"] = bool(live_row)
    out["live_class"] = live_row.get("final_class") if live_row else None
    if row is None:
        for d in DIMS:
            g.setdefault(d, NM)
        out.update(grades=g, score=0.0, verdict="NOT_RUN_LOCALLY",
                   blocker="no local Pass 3 result", local_verified=False)
        return out
    out["local_verified"] = True
    cls = row.get("final_class")
    out["class"] = cls
    names = " ".join(row.get("headline_names") or [])
    gates = row.get("gates") or {}
    g["identity"] = PASS if (gates.get("CANONICAL_IDENTITY", True)
                             and gates.get("PROFILE_CONSISTENCY", True)
                             and names) else FAIL
    hist = row.get("history") or {}
    # DOCUMENTS ACTUALLY READ for this run (ci.source_retrieved in the store),
    # not History Rewind's dated-document count.
    docs = (documents or {}).get(row.get("run_id"), 0)
    out["documents_read"] = docs
    g["coverage"] = PASS if docs >= 8 else (BOUNDED if docs >= 3 else FAIL)
    disc = row.get("discovery") or {}
    ind = disc.get("independent_origins") or 0
    g["independence"] = (PASS if ind >= 2 else BOUNDED if ind == 1 else FAIL)
    force = (row.get("generalization") or {}).get("decision_force")
    g["economics"] = (PASS if force in ("EVIDENCE_LED",
                                        "CLASS_PRIOR_REINFORCED_BY_EVIDENCE")
                      else BOUNDED if force == "CLASS_PRIOR_ONLY"
                      # No decision formed, but the page still names an
                      # economic mechanism and what would falsify it.
                      else BOUNDED if ((row.get("econ_intel") or {})
                                       .get("names_a_mechanism")
                                       and (row.get("econ_intel") or {})
                                       .get("names_a_falsifier"))
                      else FAIL)
    out["decision_force"] = force
    g["strategy"] = (PASS if cls == "DECISION_GRADE_READING" else
                     BOUNDED if cls in ("DEFENSIBLE_ABSTENTION",
                                        "INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY",
                                        "RETRIEVAL_LIMITATION_HANDLED_CORRECTLY")
                     else FAIL)
    # Rendering on the FINAL code (re-render index), redirects included.
    fin = (rendered_final or {}).get(row["company"]) or {}
    rendered = bool(fin) and all(v.get("status") in (200, 303)
                                 for v in fin.values())
    reps = repeats.get(_slug(row["company"]), repeats.get(_slug(out["company"])))
    g["presentation"] = (FAIL if not rendered else
                         NM if reps is None else
                         PASS if reps == 0 else BOUNDED)
    out["prose_repeats"] = reps
    lvl = hist.get("level") or row.get("history_level")
    g["history"] = {"A": PASS, "B": BOUNDED, "C": BOUNDED}.get(lvl, FAIL)
    u = (ui or {}).get(_slug(row["company"])) or (ui or {}).get(_slug(out["company"]))
    g["visual"] = (NM if not u else FAIL if u["status"] == "FAIL" else
                   BOUNDED if u["status"] == "PASS_WITH_A11Y_FINDINGS" else PASS)
    out["ui"] = u
    core = row.get("core_s")
    perf_ok = (core is not None and core <= core_budget
               and not [x for x in (row.get("failed_gates") or [])
                        if x in _TIMING_GATES])
    g["performance"] = PASS if perf_ok else FAIL
    out["core_s"] = core
    out["grades"] = g
    out["score"] = round(sum(VALUE.get(g[d], 0) for d in DIMS), 1)
    # The exact blocker: the first dimension that is not a PASS, in words.
    words = {
        "identity": "the run's surfaces do not name the company consistently",
        "search": "a typed prefix puts another company first",
        "coverage": f"only {docs} document(s) read",
        "independence": (f"{ind} independent relevant origin(s); the reading "
                         f"rests on company-published sources"),
        "economics": ("the decision question is the business-model default, "
                      "not derived from this company's evidence"
                      if force == "CLASS_PRIOR_ONLY" else
                      "no decision could be formed from the evidence"),
        "strategy": f"outcome {cls}: an honest reading, not a decision-grade one",
        "presentation": (f"{reps} prose sentence(s) repeated on a page"
                         if rendered else "a surface failed to render"),
        "history": f"History Rewind level {lvl} (no multi-year filed series)",
        "visual": ("layout overflow" if u and u["status"] == "FAIL" else
                   "accessibility findings (target size)" if u else
                   "not measured in the browser"),
        "performance": f"core analysis {core}s or a failed gate",
    }
    blockers = [words[d] for d in DIMS if g[d] != PASS]
    out["blocker"] = "; ".join(blockers[:3]) if blockers else ""
    functional = all(g[d] == PASS for d in ("identity", "search", "performance")) \
        and g["presentation"] != FAIL and g["visual"] != FAIL
    if all(g[d] == PASS for d in DIMS):
        out["verdict"] = "FULLY_DEMO_READY"
    elif cls in ("PRODUCT_DEFECT", "INFRASTRUCTURE", None) or not rendered:
        out["verdict"] = "INCOMPLETE_ANALYSIS"
    elif functional:
        out["verdict"] = "FUNCTIONAL_EVIDENCE_LIMITED"
    else:
        out["verdict"] = "FUNCTIONAL_WITH_DEFECTS"
    return out


def main() -> int:
    reg = yaml.safe_load((DOCS / "PROSPECT_REGISTRY.yaml").read_text())["prospects"]
    search = {r["prospect_id"]: r for r in
              (_load(DOCS / "search_matrix.json", {}) or {}).get("rows", [])}
    # Shards first, then targeted re-runs, which supersede (later wins):
    # Barracuda was re-run after the gzip repair invalidated its documents.
    local = _rows(*sorted(P3.glob("s*/state.json")), P3 / "rerun/state.json")
    if not (P3 / "captures_final").exists():
        # A pass without a re-render: its own captures, merged.
        merged = P3 / "captures_final"
        merged.mkdir(exist_ok=True)
        for cap in P3.glob("s*/reports/next40_ui/*.html"):
            target = merged / cap.name
            if not target.exists():
                target.symlink_to(cap.resolve())
    live = _rows(P2 / "state.json")
    ui = ((_load(DOCS / os.environ.get("QUALIFY_UI", "ui_matrix_pass3.json"),
                 {}) or {}).get("summary") or {}).get("per_company")
    caps = P3 / "captures_final"
    repeats = prose_repeats(caps) if caps.exists() else {}
    documents = _documents_read()
    rendered_final = _load(caps / "index.json", {}) or {
        r["company"]: {k: {"status": v} for k, v in
                       (r.get("surface_status") or {}).items()}
        for r in local.values()}
    table = [grade(r, local, live, search, ui, repeats, documents=documents,
                   rendered_final=rendered_final) for r in
             sorted(reg, key=lambda r: r["prospect_id"])]
    verdicts = collections.Counter(t["verdict"] for t in table)
    dims = {d: dict(collections.Counter(t["grades"].get(d) for t in table))
            for d in DIMS}
    summary = {
        "companies": len(table),
        "verdicts": dict(verdicts),
        "ten_of_ten": sum(1 for t in table if t.get("score") == 10.0),
        "dimensions": dims,
        "live_verified": sum(1 for t in table if t.get("live_verified")),
        "local_verified": sum(1 for t in table if t.get("local_verified")),
        "local_only": sum(1 for t in table if t.get("local_verified")
                          and not t.get("live_verified")),
        "visual_fail": sum(1 for t in table if t["grades"].get("visual") == FAIL),
        "performance_fail": sum(1 for t in table
                                if t["grades"].get("performance") == FAIL),
    }
    (DOCS / os.environ.get("QUALIFY_OUT", "qualification_100.json")).write_text(json.dumps(
        {"summary": summary, "companies": table}, indent=1, default=str))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
