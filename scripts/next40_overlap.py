#!/usr/bin/env python3
"""§16 — substantive similarity across surfaces, with the boilerplate removed.

TEXTUAL DIFFERENCE IS NOT DIFFERENTIATION, and textual similarity is not
collapse. Two companies of one business model SHOULD share a great deal: the
economics of a subscription business are the same economics. What must not be
shared is the part that is supposed to be about THIS company.

So every comparison is made after normalising away the things that differ
trivially (the company's own name, dates, numbers) and the things that are
shared by construction (navigation, the demo chrome). What is left is the
substance, and a high score there is only a collapse if the two companies do
not share the mechanism the page claims.
"""
from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
from public_journey_ten import visible                           # noqa: E402

UI = ROOT / "reports/next40_ui"
SURFACES = ("intro", "brief", "full", "xray", "history", "evidence")
#: Shared by construction on every page of a guest demo.
_CHROME = re.compile(
    r"home · your analyses|guest demo session|leave demo|strategic "
    r"intelligence|executive x-ray|history rewind|introduction", re.I)


def _slug(n):
    return re.sub(r"[^a-z0-9]+", "-", str(n or "").lower()).strip("-")


def _normalised(company, key):
    p = UI / f"{_slug(company)}-{key}.html"
    if not p.exists():
        return set()
    text = " ".join(visible(p.read_text()).split()).lower()
    text = _CHROME.sub(" ", text)
    # the company's own name, in every form it appears
    for part in re.split(r"[^a-z0-9]+", company.lower()):
        if len(part) > 2:
            text = text.replace(part, " ")
    text = re.sub(r"\b(inc|llc|ltd|corp|corporation|nv|lp|plc)\b", " ", text)
    text = re.sub(r"\d[\d,.%$-]*", " ", text)          # dates and numbers
    return {w for w in re.findall(r"[a-z]{4,}", text)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", default="ALL")
    args = ap.parse_args()
    analysis = json.loads((ROOT / "reports/next40_analysis.json").read_text())
    rows = {r["company"]: r for r in analysis["rows"]}
    cats = {c: r.get("category") for c, r in rows.items()}
    models = {c: r.get("model_class") for c, r in rows.items()}
    questions = {c: r.get("decision_question") for c, r in rows.items()}

    per_surface, pairs = {}, []
    for key in SURFACES:
        bags = {c: _normalised(c, key) for c in rows}
        bags = {c: b for c, b in bags.items() if len(b) > 40}
        scores = []
        for a, b in itertools.combinations(sorted(bags), 2):
            j = len(bags[a] & bags[b]) / max(1, len(bags[a] | bags[b]))
            scores.append((round(j, 3), a, b))
            pairs.append({"surface": key, "jaccard": round(j, 3),
                          "a": a, "b": b,
                          "same_category": cats.get(a) == cats.get(b),
                          "same_model": models.get(a) == models.get(b),
                          "same_question": questions.get(a) == questions.get(b)})
        scores.sort(reverse=True)
        per_surface[key] = {"companies": len(bags),
                            "max": scores[0][0] if scores else None,
                            "top": scores[:3]}
    within = [p for p in pairs if p["same_category"]]
    cross = [p for p in pairs if not p["same_category"]]
    near = [p for p in cross if p["jaccard"] >= 0.90]
    doc = {
        "contract": "next40_overlap.v1", "cohort": args.cohort,
        "normalisation": "company name, legal suffixes, dates, numbers and "
                         "demo chrome removed before comparison",
        "per_surface": {k: {"companies": v["companies"], "max": v["max"]}
                        for k, v in per_surface.items()},
        "max_within_category_overlap": max((p["jaccard"] for p in within),
                                           default=None),
        "max_cross_category_overlap": max((p["jaccard"] for p in cross),
                                          default=None),
        "near_identical_cross_category_pairs": len(near),
        "near_identical_examples": sorted(near, key=lambda p: -p["jaccard"])[:8],
    }
    (ROOT / "reports/next40_overlap.json").write_text(json.dumps(doc, indent=1))
    print(f"{'surface':10s} {'companies':>9s} {'max overlap':>12s}   top pair")
    for k, v in per_surface.items():
        top = v["top"][0] if v["top"] else None
        print(f"{k:10s} {v['companies']:9d} {str(v['max']):>12s}   "
              f"{(top[1] + ' <-> ' + top[2]) if top else '-'}")
    print(f"\nMAX_WITHIN_CATEGORY_OVERLAP        "
          f"{doc['max_within_category_overlap']}")
    print(f"MAX_CROSS_CATEGORY_OVERLAP         "
          f"{doc['max_cross_category_overlap']}")
    print(f"NEAR_IDENTICAL_CROSS_CATEGORY      "
          f"{doc['near_identical_cross_category_pairs']} pairs at >= 0.90")
    for p in doc["near_identical_examples"][:5]:
        print(f"   {p['jaccard']}  {p['surface']:9s} {p['a'][:12]:13s} <-> "
              f"{p['b'][:12]:13s} same_model={p['same_model']} "
              f"same_question={p['same_question']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
