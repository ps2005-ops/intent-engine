#!/usr/bin/env python3
"""Does company #37 read like company #3? (§19, §21)

Runs on the state file, so it costs nothing and needs no analysis. Template
collapse is a property of a SET of companies -- one company cannot be compared
with itself -- which is why it is measured here rather than inside the journey.

WHAT COUNTS AS A COLLAPSE, AND WHAT DOES NOT. Two companies in one category
SHOULD share vocabulary: four data-protection vendors all talk about backup
and recovery, and demanding they not would be demanding noise. What may not
happen is two companies receiving the same SENTENCES with the name swapped.

So the measurement strips the company's own name and every number, then
compares what is left. A skeleton collision is a collapse. A high word overlap
with different skeletons is similarity, which is reported separately and is
allowed -- §19 says so explicitly.
"""
from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / "reports/next40_state.json"

#: Words that are the PRODUCT's vocabulary rather than a company's. Shared use
#: of these is the house style, not a collapse.
_CHROME = set("""
the a an and or of to in for on with by is are was were be been this that
it its as at from not no any all we our you your they their he she them
what which who when how why if then than so such more most less least
company companies business evidence analysis reading decision strategic
strategy management what-changed page pages document documents source
sources date dated published retrieved record records level question
""".split())


def _skeleton(text: str, names) -> str:
    out = " ".join(str(text or "").split())
    for name in sorted(names, key=len, reverse=True):
        if name:
            out = re.sub(re.escape(name), " CO ", out, flags=re.I)
    out = re.sub(r"\d[\d,.\-/]*", " N ", out)
    out = re.sub(r"[^A-Za-z ]+", " ", out)
    return " ".join(out.lower().split())


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower())
            if w not in _CHROME}


def _jaccard(a: set, b: set) -> float:
    return (len(a & b) / len(a | b)) if (a or b) else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=str(STATE))
    ap.add_argument("--field", default="brief",
                    choices=["brief", "full", "xray"])
    ap.add_argument("--out", default="reports/next40_differentiation.json")
    args = ap.parse_args()
    state = json.loads(pathlib.Path(args.state).read_text())
    rows = [r for r in state.get("rows", {}).values()
            if (r.get("decision_text") or {}).get(args.field)]
    if len(rows) < 2:
        print(f"need two companies with {args.field} text; have {len(rows)}")
        return 0

    prep = {}
    for r in rows:
        name = r["company"]
        names = {name, name.split()[0], name.replace(" ", "")}
        text = r["decision_text"][args.field]
        prep[name] = {"cat": r.get("category", "?"),
                      "skel": _skeleton(text, names),
                      "words": _words(text), "chars": len(text)}

    collapses, near, pairs = [], [], []
    for a, b in itertools.combinations(sorted(prep), 2):
        A, B = prep[a], prep[b]
        same = A["skel"] == B["skel"] and A["skel"]
        # A sentence-level collision is still a collapse even when the rest
        # of the page differs, so sentences are compared too.
        sa = {s.strip() for s in re.split(r"(?<=[.!?]) ", A["skel"])
              if len(s.strip()) > 80}
        sb = {s.strip() for s in re.split(r"(?<=[.!?]) ", B["skel"])
              if len(s.strip()) > 80}
        shared = sa & sb
        overlap = _jaccard(A["words"], B["words"])
        row = {"a": a, "b": b, "same_category": A["cat"] == B["cat"],
               "category_a": A["cat"], "category_b": B["cat"],
               "identical_skeleton": bool(same),
               "shared_long_sentences": len(shared),
               "word_overlap": round(overlap, 3)}
        pairs.append(row)
        if same:
            collapses.append(dict(row, why="identical page after removing the "
                                           "company name and every number"))
        elif shared:
            collapses.append(dict(
                row, why=f"{len(shared)} long sentence(s) identical after "
                         f"removing the name and numbers",
                example=sorted(shared)[0][:220]))
        elif overlap >= 0.82:
            near.append(row)

    pairs.sort(key=lambda r: -r["word_overlap"])
    print(f"companies compared      {len(prep)}  field={args.field}")
    print(f"pairs                   {len(pairs)}")
    print(f"TEMPLATE_COLLAPSES      {len(collapses)}")
    print(f"near-identical (>=0.82) {len(near)}  (similarity, not a collapse)")
    for c in collapses[:12]:
        print(f"  COLLAPSE {c['a']} <-> {c['b']} :: {c['why']}")
        if c.get("example"):
            print(f"           e.g. {c['example']}")
    print("\nhighest word overlap (expected WITHIN a category):")
    for r in pairs[:10]:
        mark = "same-cat" if r["same_category"] else "CROSS-CAT"
        print(f"  {r['word_overlap']:.3f} {mark:9s} {r['a']} <-> {r['b']}")
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        {"field": args.field, "companies": len(prep),
         "template_collapses": collapses, "near_identical": near,
         "pairs": pairs}, indent=1))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
