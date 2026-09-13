#!/usr/bin/env python3
"""Freeze one cohort (§13): its final rows, checkpoint and findings.

A frozen cohort is not "finished analysing" -- it is a cohort whose rows may
no longer be re-run to improve them. Recording that explicitly is what stops
a qualification quietly re-running its way to a nicer distribution.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/qualification"
RANGES = {"A": range(1, 15), "B": range(15, 28), "C": range(28, 41)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", required=True, choices=sorted(RANGES))
    args = ap.parse_args()
    c = args.cohort
    analysis = json.loads((ROOT / "reports/next40_analysis.json").read_text())
    rows = [r for r in analysis["rows"] if r["n"] in RANGES[c]]
    findings = [f for f in json.loads(
        (ROOT / "reports/next40_findings.json").read_text())["findings"]
        if f.get("cohort") == c]
    inv = None
    p = ROOT / f"reports/next40_invariants_{c}.json"
    if p.exists():
        inv = json.loads(p.read_text())
    controls = None
    p = ROOT / "reports/next40_controls.json"
    if p.exists() and c == "A":
        controls = json.loads(p.read_text())

    OUT.mkdir(parents=True, exist_ok=True)
    doc = {
        "contract": f"cohort_{c.lower()}_final.v1",
        "cohort": c,
        "frozen_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "sha": analysis.get("sha"),
        "companies": len(rows),
        "summary": analysis.get("summary") if c == "A" else None,
        "rows": rows,
        "invariants": inv,
        "controls": controls,
        "frozen": True,
        "what_frozen_means":
            "these rows may not be re-run to improve them. A row is only "
            "reopened by an unresolved P0, or by a later cohort proving a "
            "repair made here did not generalize.",
    }
    (OUT / f"COHORT_{c}_FINAL.json").write_text(json.dumps(doc, indent=1))
    (OUT / f"COHORT_{c}_FINDINGS.json").write_text(json.dumps(
        {"contract": f"cohort_{c.lower()}_findings.v1", "findings": findings},
        indent=1))
    print(f"froze cohort {c}: {len(rows)} rows, {len(findings)} findings")
    print(f"  {OUT}/COHORT_{c}_FINAL.json")
    print(f"  {OUT}/COHORT_{c}_FINDINGS.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
