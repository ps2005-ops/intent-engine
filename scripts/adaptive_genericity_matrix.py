#!/usr/bin/env python3
"""Pairwise genericity across the final ten, on what the READER sees.

Telemetry fields can differ while the rendered paragraph is identical, so the
comparison holds the paragraph. Company names, their domains and their own
vocabulary are normalised out first -- otherwise every pair looks different
for the one reason that proves nothing.

SHARED FRAMEWORK LANGUAGE IS NOT A COLLAPSE. Two data-security companies
routing to the same lens is the router being correct, and the sentences that
state the lens will be similar by construction. What has to differ is the
SUBSTANCE inside the shared frame, so a high ratio is reported for inspection
and only a near-identical pair is called a collapse.
"""
from __future__ import annotations

import argparse
import difflib
import itertools
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The aspects §27 names, keyed to the sections the renderer labels.
ASPECTS = ("why_this_company", "decision_or_domains", "chain", "bounded",
           "lens", "value")

#: At or above this, two companies' prose is the same prose.
COLLAPSE = 0.92
#: At or above this it is worth a human look, but shared framing is expected.
INSPECT = 0.75


def normalise(text: str, company: str) -> str:
    """Strip what a pair CANNOT help sharing, and what only they can."""
    s = (text or "").lower()
    for token in sorted(re.split(r"[^a-z0-9]+", company.lower()),
                        key=len, reverse=True):
        if len(token) >= 3:
            s = s.replace(token, " ")
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"\d+(?:\.\d+)?", " ", s)          # scores and percentages
    return " ".join(s.split())


def ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", default="reports/adaptive_ten_matrix.json")
    ap.add_argument("--out", default="reports/adaptive_genericity_matrix.json")
    a = ap.parse_args()
    raw = json.loads((ROOT / a.matrix).read_text())
    rows = [r for r in raw.get("rows", []) if r.get("sections")]
    if len(rows) < 2:
        print(f"only {len(rows)} row(s) carry sections — nothing to compare")
        return 1

    pairs, collapses, inspects = [], 0, 0
    for left, right in itertools.combinations(rows, 2):
        ln, rn = left["company"], right["company"]
        aspects = {}
        for aspect in ASPECTS:
            lt = normalise((left.get("sections") or {}).get(aspect, ""), ln)
            rt = normalise((right.get("sections") or {}).get(aspect, ""), rn)
            if not lt or not rt:
                aspects[aspect] = {"ratio": None,
                                   "verdict": "ABSENT_ONE_SIDE"}
                continue
            r = round(ratio(lt, rt), 3)
            verdict = ("COLLAPSE" if r >= COLLAPSE else
                       "INSPECT" if r >= INSPECT else "DISTINCT")
            if verdict == "COLLAPSE":
                collapses += 1
            elif verdict == "INSPECT":
                inspects += 1
            aspects[aspect] = {"ratio": r, "verdict": verdict}
        same_lens = (left.get("primary_lens") and
                     left.get("primary_lens") == right.get("primary_lens"))
        pairs.append({"left": ln, "right": rn,
                      "same_lens": bool(same_lens),
                      "lens": [left.get("primary_lens"),
                               right.get("primary_lens")],
                      "aspects": aspects})

    out = {"live_commit": raw.get("live_commit"),
           "companies": [r["company"] for r in rows],
           "collapse_threshold": COLLAPSE, "inspect_threshold": INSPECT,
           "collapses": collapses, "inspect": inspects, "pairs": pairs}
    (ROOT / a.out).write_text(json.dumps(out, indent=2))
    print(f"{len(pairs)} pairs x {len(ASPECTS)} aspects")
    print(f"  collapses (>= {COLLAPSE}): {collapses}")
    print(f"  inspect   (>= {INSPECT}): {inspects}")
    for p in pairs:
        hot = [f"{k} {v['ratio']}" for k, v in p["aspects"].items()
               if v.get("verdict") in ("COLLAPSE", "INSPECT")]
        if hot:
            print(f"  {p['left']} vs {p['right']}"
                  f"{' [same lens]' if p['same_lens'] else ''}: "
                  + ", ".join(hot))
    print(f"written {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
