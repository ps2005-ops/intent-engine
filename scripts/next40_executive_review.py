#!/usr/bin/env python3
"""§18: would a chief executive understand this page in thirty seconds?

WHAT THIS DELIBERATELY IS NOT. It is not a score generator. A rubric that
returns eight numbers and no evidence cannot be checked, and this product has
already shipped one that read the wrong object and returned 10.0 for a surface
a customer saw as empty. So every dimension here returns the SPAN IT MATCHED
alongside its verdict, and a dimension that matched nothing says so rather than
scoring zero silently.

IT READS THE PAGE THE CUSTOMER READS. The captures are the served bytes, not an
internal object: a dimension satisfied by a field that never reaches the page
is a dimension that is not satisfied.

AND A UNIFORM RESULT IS AN INSTRUMENT FAULT, NOT A FINDING. If forty companies
score identically on a dimension, the dimension is measuring the house style
rather than the analysis -- so `--audit` reports exactly that, and it is the
first thing to read.
"""
from __future__ import annotations

import argparse
import collections
import html as _html
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _visible(raw: str) -> str:
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw or "",
                  flags=re.S | re.I)
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", body)).split())


def _span(text: str, pattern: str, width: int = 150):
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    lo = max(0, m.start() - 40)
    return text[lo:lo + width]


#: (dimension, what a page must SAY for it to be present, why it matters)
DIMENSIONS = (
    ("SPECIFICITY",
     r"\b(its own|this company|according to its|on its [a-z]+ page|"
     r"the filing|the company states|it says it)\b",
     "the page points at something only this company said"),
    ("STRATEGIC_RELEVANCE",
     r"\b(decision|posture|choose|trade-off|tradeoff|allocate|prioriti|"
     r"whether to|option)\b",
     "a decision is actually exposed"),
    ("ECONOMIC_RELEVANCE",
     r"\b(demand|budget|spend|pricing|cost|revenue|margin|capital|"
     r"interest rate|tariff|cycle|inflation|hiring|freight|volume)\b",
     "the reading touches the company's economic engine"),
    ("EVIDENCE_QUALITY",
     r"\b(evidence|source|retrieved|filing|published|cited|quote|"
     r"according to)\b",
     "the conclusion is traceable to something"),
    ("CONTRADICTION_HANDLING",
     r"\b(however|argues against|on the other hand|contradict|tension|"
     r"but the|counter|although|conflict)\b",
     "the page states what cuts the other way"),
    ("ACTIONABILITY",
     r"\b(should|next|investigate|watch|monitor|ask|establish|confirm|"
     r"recommend|do not act)\b",
     "the reader is told what to do or learn next"),
    ("UNCERTAINTY_HONESTY",
     r"\b(not known|unknown|uncertain|cannot|limit|assumption|assume|"
     r"would change|insufficient|not enough|bounded|we did not)\b",
     "the page names its own limits"),
    ("PRESENTATION",
     r"<h[12][^>]*>",
     "the page has a heading structure a reader can skim"),
)


def review(captures: dict) -> dict:
    """One company. `captures` maps surface -> raw html."""
    raw = " ".join(captures.values())
    text = _visible(raw)
    out = {"chars": len(text), "dimensions": {}}
    for name, pattern, why in DIMENSIONS:
        hay = raw if name == "PRESENTATION" else text
        hit = _span(hay, pattern)
        out["dimensions"][name] = {
            "present": hit is not None, "why": why,
            "evidence": (hit or "").strip()[:160],
        }
    # The thirty-second question is about the FIRST screen, so it is asked of
    # the intro alone rather than of everything concatenated.
    intro = _visible(captures.get("intro") or captures.get("result") or "")
    first = intro[:1800]
    out["first_screen"] = {
        "chars": len(intro),
        "what_changed": bool(re.search(
            r"what (has )?changed|new this|since|recently", first, re.I)),
        "why_it_matters": bool(re.search(
            r"matters|implication|means for|exposure|because", first, re.I)),
        "decision_exposed": bool(re.search(
            r"decision|posture|whether|choose|act", first, re.I)),
        "uncertainty_named": bool(re.search(
            r"limit|bounded|uncertain|cannot|not enough|assumption", first,
            re.I)),
    }
    present = sum(1 for d in out["dimensions"].values() if d["present"])
    fs = sum(1 for v in out["first_screen"].values() if v is True)
    out["dimensions_present"] = present
    out["first_screen_present"] = fs
    # "10/10 means no material defect, not fabricated perfection" (§18).
    out["material_defects"] = [
        name for name, d in out["dimensions"].items() if not d["present"]]
    out["verdict"] = "NO_MATERIAL_DEFECT" if present == len(DIMENSIONS) \
        else "MATERIAL_DEFECT"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="reports/next40_state.json")
    ap.add_argument("--captures", default="reports/next40_ui")
    ap.add_argument("--out", default="reports/next40_executive_review.json")
    ap.add_argument("--audit", action="store_true",
                    help="report dimensions that never vary -- an instrument "
                         "fault, not a finding about the companies")
    args = ap.parse_args()
    state = json.loads((ROOT / args.state).read_text())
    capdir = ROOT / args.captures
    results = {}
    for key, row in sorted(state.get("rows", {}).items(),
                           key=lambda k: int(k[0])):
        files = row.get("capture_files") or {}
        caps = {}
        for name, fname in files.items():
            try:
                caps[name] = (capdir / fname).read_text()
            except OSError:
                continue
        if not caps:
            continue
        results[row.get("company", key)] = dict(
            review(caps), n=row.get("n"), category=row.get("category"))

    if not results:
        print("no captures to review yet")
        return 0
    names = [n for n, _p, _w in DIMENSIONS]
    print(f"companies reviewed {len(results)}\n")
    print(f"{'company':22s} dims  first  verdict")
    for company, r in sorted(results.items(), key=lambda kv: kv[1]["n"] or 0):
        print(f"{company[:22]:22s} {r['dimensions_present']}/8   "
              f"{r['first_screen_present']}/4    {r['verdict']}"
              + (f"  missing={r['material_defects']}"
                 if r["material_defects"] else ""))
    if args.audit:
        print("\n--- INSTRUMENT AUDIT (read this first) ---")
        for name in names:
            vals = collections.Counter(
                r["dimensions"][name]["present"] for r in results.values())
            if len(vals) == 1 and len(results) > 3:
                print(f"  {name}: identical on all {len(results)} companies "
                      f"({list(vals)[0]}) -- this dimension is measuring the "
                      f"house style, not the analysis")
            else:
                print(f"  {name}: {vals[True]} present / {vals[False]} absent")
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=1))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
