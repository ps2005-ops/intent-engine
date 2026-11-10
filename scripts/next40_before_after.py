#!/usr/bin/env python3
"""BEFORE -> AFTER on the fields the six-repair batch was supposed to move.

Costs nothing. Reads a snapshot taken on the previous SHA and the live state
file, and reports the fields §5 names: decision archetype, decision question,
watch metrics, X-Ray overlap -- plus WHY each decision won, because a better
overlap number with no mechanism behind it is the same defect wearing
different clothes.
"""
from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
_CHROME = set(
    "the a an and or of to in for on with by is are was were be been this "
    "that it its as at from not no any all we our you your they their what "
    "which who when how why if then than so such more most less least "
    "company companies business evidence analysis reading decision strategic "
    "strategy management page pages document documents source sources date "
    "dated published retrieved record records level question".split())


def _words(text):
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower())
            if w not in _CHROME}


def _facts(row):
    x = (row.get("decision_text") or {}).get("xray", "")
    q = re.search(r"For [^:]{1,80}:\s*(.{15,200}?\?)", x)
    lab = re.search(r"\b([A-Z][a-z]+(?: [a-z]+)?) decision\b", x)
    w = re.findall(r"revenue at a business of this kind moves with "
                   r"([a-z ,]+?)(?:\.|revenue|$)", x)
    gen = row.get("generalization") or {}
    return {"company": row.get("company"), "n": row.get("n"),
            "archetype_label": lab.group(1) if lab else None,
            "decision_question": " ".join(q.group(1).split()) if q else None,
            "watch_metrics": sorted({t.strip() for t in w if t.strip()}),
            "contributions": gen.get("contributions") or {},
            "xray": x}


def _overlaps(xrays):
    out = []
    for a, b in itertools.combinations(sorted(xrays), 2):
        wa, wb = _words(xrays[a]), _words(xrays[b])
        out.append((round(len(wa & wb) / max(1, len(wa | wb)), 3), a, b))
    out.sort(reverse=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--state", default="reports/next40_state.json")
    args = ap.parse_args()
    before = json.loads(pathlib.Path(args.before).read_text())
    state = json.loads((ROOT / args.state).read_text())
    after = {r["company"]: _facts(r) for r in state.get("rows", {}).values()
             if (r.get("decision_text") or {}).get("xray")}
    bmap = {v["company"]: v for v in before["companies"].values()}
    shared = [c for c in after if c in bmap]
    if not shared:
        print("no company has both a BEFORE and an AFTER reading yet")
        return 0

    print(f"BEFORE sha {before['sha'][:12]}   AFTER sha "
          f"{state.get('live_sha','')[:12]}   companies {len(shared)}\n")
    print(f"{'company':18s} {'BEFORE decision':30s} -> {'AFTER decision':30s} "
          f"{'won by':12s}")
    moved = 0
    for c in sorted(shared, key=lambda x: after[x]["n"] or 0):
        b, a = bmap[c], after[c]
        cb = a.get("contributions") or {}
        won = ("CLASS_PRIOR" if cb.get("class_prior_only") else
               "EVIDENCE" if cb.get("evidence") else
               "ECON" if cb.get("econ") else
               "POSTURE" if cb.get("posture") else "?")
        same = (b.get("decision_question") == a.get("decision_question"))
        moved += 0 if same else 1
        mark = "  " if same else "->"
        print(f"{mark}{c[:16]:16s} {(b.get('decision_question') or '-')[:30]:30s} "
              f"-> {(a.get('decision_question') or '-')[:30]:30s} {won:12s}")
    bq = len({v.get("decision_question") for v in bmap.values()
              if v["company"] in shared})
    aq = len({after[c].get("decision_question") for c in shared})
    bo = before.get("xray_overlap_top") or []
    ao = _overlaps({c: after[c]["xray"] for c in shared})
    print(f"\nDISTINCT DECISION QUESTIONS   {bq}/{len(shared)} -> "
          f"{aq}/{len(shared)}")
    print(f"DECISIONS CHANGED             {moved}/{len(shared)}")
    print(f"MAX_XRAY_OVERLAP              "
          f"{bo[0][0] if bo else '-'} -> {ao[0][0] if ao else '-'}")
    print("\ntop overlaps AFTER:")
    for j, a, b in ao[:5]:
        print(f"   {j:.3f}  {a} <-> {b}")
    only = [c for c in shared
            if (after[c].get("contributions") or {}).get("class_prior_only")]
    print(f"\nCLASS_PRIOR_ONLY_DECISIONS    {len(only)}/{len(shared)}"
          + (f"  {only}" if only else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
