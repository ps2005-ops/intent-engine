#!/usr/bin/env python3
"""Re-derive every measured field from the SAVED CAPTURES. Costs no quota.

WHY THIS EXISTS. A harness defect found on company three must not cost three
analyses to correct. Every surface the journey opened was written to
`reports/next40_ui/` as the bytes the server actually returned, so any field
that is a function of those bytes can be recomputed for free, for every
company already run -- and a measurement corrected this way is measured on
exactly what the customer was served, not on a re-run that might differ.

It rewrites ONLY derived measurements. Timings, run ids, gate outcomes and the
Q&A transcript are properties of the run itself and are left untouched: a
harness that could retroactively change whether a gate passed would not be an
instrument.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent

import next40_qualification as N                              # noqa: E402
from perf_progressive_matrix import visible                   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="reports/next40_state.json")
    ap.add_argument("--captures", default="reports/next40_ui")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    path = ROOT / args.state
    state = json.loads(path.read_text())
    capdir = ROOT / args.captures
    changed = []
    for key, row in sorted(state.get("rows", {}).items(),
                           key=lambda kv: int(kv[0])):
        files = row.get("capture_files") or {}
        if not files:
            continue
        surfaces = {}
        for name, fname in files.items():
            try:
                surfaces[name] = {"status": 200,
                                  "html": (capdir / fname).read_text()}
            except OSError:
                continue
        if not surfaces:
            continue
        before = {"history": row.get("history"),
                  "discovery": row.get("discovery")}
        # Recompute using the SAME functions the live journey uses, so the
        # corrected reading and the live one can never drift apart.
        hist_html = surfaces.get("history", {}).get("html", "") or ""
        hist = visible(hist_html)
        import re
        dates = sorted(set(re.findall(r"\b(20[0-2]\d-[01]\d-[0-3]\d)\b", hist)))
        # EACH LEVEL COUNTS ITS OWN RECORD IN ITS OWN WORDS, and all three must
        # yield §12's DATED_DOCUMENT_COUNT:
        #   A  "32 dated filing(s) span 2024-04-01 to 2026-09-01"
        #   B  "6 dated document(s) span 2026-07-10 to 2026-08-27"
        #   C  "One dated document was retrieved for Alation, Inc."
        # Matching only one of them read two of the three as null on pages that
        # state the number plainly.
        _WORDS = {"no": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                  "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
        spans = re.search(
            r"(\d+) dated (?:document|filing|record)\(s\) span", hist)
        if spans:
            dated_documents = int(spans.group(1))
        else:
            m2 = re.search(
                r"\b(\d+|no|one|two|three|four|five|six|seven|eight|nine|ten) "
                r"dated (?:document|filing|record)s?\b", hist, re.I)
            dated_documents = (
                (int(m2.group(1)) if m2.group(1).isdigit()
                 else _WORDS.get(m2.group(1).lower()))
                if m2 else None)
        econ_states = re.findall(r'data-econ-state="([^"]*)"', hist_html)
        ev = surfaces.get("evidence", {}).get("html", "") or ""
        evt = visible(ev)
        m = re.search(r'data-search-state="([^"]*)"', ev)
        origins = re.search(r'data-independent-origins="(\d+)"', ev)
        row["history"] = {
            "level": row.get("history_level"),
            "dated_documents": dated_documents,
            "earliest": dates[0] if dates else None,
            "latest": dates[-1] if dates else None,
            "financial_series": row.get("history_level") == "A",
            "econ_states": {s: econ_states.count(s) for s in set(econ_states)},
            "economic_links": sum(1 for s in econ_states
                                  if s == "ECONOMIC_CONTEXT_LINKED"),
            # A WALL GUARDS A WALK. LEVEL C walks no dates -- it states that the record is
            # too thin to rewind -- so there is no "then" for later evidence to leak into,
            # and reporting ABSENT there would read as a missing guard rather than an
            # inapplicable one.
            "hindsight_wall": ("NOT_APPLICABLE"
                               if row.get("history_level") == "C" else
                               "PRESENT" if any(
                p in hist.lower() for p in (
                    "not available then", "can see a filing made after it",
                    "had not happened yet", "after it, because that part"))
                else "ABSENT"),
            "stops": len(econ_states),
            "series_lines": sum(1 for x in ("ln-actual", "ln-expect",
                                            "ln-counter") if x in hist_html),
            "chart_years": sorted(set(re.findall(r">(20\d\d)<", hist_html))),
            "timeline_points": (lambda q: int(q.group(1)) if q else None)(
                re.search(r"timeline has (\d+) point", hist)),
        }
        row["discovery"] = {
            "search_state": m.group(1) if m else "ATTRIBUTE_ABSENT",
            "independent_origins": int(origins.group(1)) if origins else None,
            "says_no_search": "no discovery run is recorded" in evt.lower(),
            "reused": "reused the source list" in evt.lower(),
            "hits": (lambda q: int(q.group(1)) if q else None)(
                re.search(r"found (\d+) filing", evt)),
            "read_in_full": (lambda q: int(q.group(1)) if q else None)(
                re.search(r"read (\d+) in full", evt)),
            "company_owned_origins": evt.lower().count("host"),
            "counterevidence": bool(re.search(
                r"argues against|counter-evidence|counterevidence|set aside",
                evt, re.I)),
        }
        # §7 STRATEGIC GENERALIZATION, re-derived from the X-Ray's own reason.
        # The page states which force chose the decision and names the terms;
        # parsing the rendered page means the record can never claim more than
        # the product actually said.
        xr = (row.get("decision_text") or {}).get("xray") or visible(
            surfaces.get("xray", {}).get("html", "") or "")
        gen = dict(row.get("generalization") or {})
        terms = re.search(r"own record discusses (?:this decision )?in (\d+) "
                          r"distinct terms? \(([^)]*)\)", xr)
        if terms:
            gen["contributions"] = {
                "evidence": int(terms.group(1)),
                "evidence_terms": [t.strip() for t in
                                   terms.group(2).split(",") if t.strip()],
                "class_prior_only": False}
        elif "standing decision for this business model" in xr:
            gen["contributions"] = {"evidence": 0, "evidence_terms": [],
                                    "class_prior_only": True}
        q = re.search(r"For [^:]{1,80}:\s*(.{15,190}?\?)", xr)
        if q:
            gen["decision_question"] = " ".join(q.group(1).split())
        lab = re.search(r"\b([A-Z][a-z]+(?: [a-z]+)?) decision\b", xr)
        if lab:
            gen["archetype_label"] = lab.group(1)
        ranked = re.search(r"ranked above ([a-z ]+?) on the same evidence", xr)
        if ranked:
            gen["ranked_above"] = ranked.group(1).strip()
        if gen:
            row["generalization"] = gen
        if before != {"history": row["history"],
                      "discovery": row["discovery"]}:
            changed.append(row.get("company"))
            print(f"  {row.get('company','')[:20]:20s} "
                  f"docs {(before['history'] or {}).get('dated_documents')} -> "
                  f"{row['history']['dated_documents']}   wall "
                  f"{(before['history'] or {}).get('hindsight_wall')} -> "
                  f"{row['history']['hindsight_wall']}")
    print(f"\nrows re-derived: {len(changed)}")
    if not args.dry_run and changed:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
        tmp.replace(path)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
