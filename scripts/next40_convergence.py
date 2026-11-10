#!/usr/bin/env python3
"""§24 convergence, computed from the findings ledger rather than asserted.

THE CURVE IS THE RESULT. A qualification that keeps finding the same class of
defect in cohort C has not converged, however green each company looks; one
that finds many systemic defects in A, fewer in B and mostly confirmation in
C has. Both outcomes are reportable and neither may be manufactured.

A finding is SYSTEMIC when its repair changes behaviour for every company of
some kind, and LOCAL when it is about one company or one run. A finding is
REPEATED when an earlier cohort already found a defect of the same CLASS --
the class is what an invariant is written against, so rediscovering one means
the invariant was incomplete.
"""
from __future__ import annotations

import argparse
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The defect CLASSES this qualification has invariants for. Rediscovering
#: one in a later cohort is the signal that matters, so the classes are named
#: rather than inferred from wording.
CLASSES = {
    "IDENTITY_COLLISION": ("wrong company", "fuzzy-resolve", "registrant",
                           "cik", "collision", "cannabis"),
    "FOREIGN_EVIDENCE": ("foreign evidence", "another company's",
                         "cross-company evidence"),
    "EVIDENCE_MISATTRIBUTION": ("rejected candidate", "attributed",
                                "winner", "inherit"),
    "SUBSTRING_FABRICATION": ("substring", "manufactured", "port",
                              "boundary"),
    "CATEGORY_VOCABULARY_COLLAPSE": ("category vocabulary", "generic",
                                     "class prior", "collapse",
                                     "template"),
    "COMPOSER_BYPASS": ("composer", "inert", "call site", "seam"),
    "DISCOVERY_UNTRUTHFUL_STATE": ("no search was run", "never_started",
                                   "abandoned", "discovery state"),
    "INTERNAL_LEAK": ("dict repr", "python dict", "exception class",
                      "internal token", "raw enum", "httperror",
                      "no english mapping", "english mapping",
                      "engineering token"),
    "MECHANICAL_REPETITION": ("repeats", "repeated", "mechanically",
                              "duplicate"),
    "PEER_OVERCLAIM": ("competitor", "peer", "rival", "tautology"),
    "INSTRUMENT_DEFECT": ("harness", "instrument", "scraper", "fixture",
                          "reader", "artifact", "timed out and captured"),
    "ENVIRONMENT": ("cold start", "cold-start", "quota", "free-tier"),
    "MODEL_MISCLASSIFICATION": ("classified as", "business-model "
                                                 "classification",
                                "people/route", "people-or-route"),
}


def classify(finding) -> str:
    # AN EXPLICIT CLASSIFICATION WINS. A harness defect and a product defect
    # are different results, and the convergence curve is about the PRODUCT:
    # counting my own measurement bugs as systemic product findings would
    # make the curve say something it has no right to say.
    stated = str(finding.get("classification") or "").strip().upper()
    if stated == "HARNESS_DEFECT":
        return "INSTRUMENT_DEFECT"
    named = str(finding.get("defect_class_stated") or "").strip().upper()
    if named in CLASSES:
        return named
    if stated == "ENVIRONMENT_LIMITATION":
        return "ENVIRONMENT"
    blob = " ".join(str(finding.get(k, "")) for k in
                    ("title", "root_cause", "evidence")).lower()
    best, score = "UNCLASSIFIED", 0
    for name, words in CLASSES.items():
        hits = sum(1 for w in words if w in blob)
        if hits > score:
            best, score = name, hits
    return best


#: A finding whose repair is about ONE company or ONE run rather than a kind
#: of company. Named explicitly: guessing systemic-vs-local from wording is
#: how a convergence curve gets manufactured.
_LOCAL = {"ENVIRONMENT", "INSTRUMENT_DEFECT"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/next40_convergence.json")
    args = ap.parse_args()
    ledger = json.loads(
        (ROOT / "reports/next40_findings.json").read_text())["findings"]
    for f in ledger:
        f["defect_class"] = classify(f)

    seen, out = {}, {}
    for cohort in ("A", "B", "C"):
        rows = [f for f in ledger if f.get("cohort") == cohort]
        new, repeated = [], []
        for f in rows:
            cls = f["defect_class"]
            if cls in _LOCAL:
                continue
            if cls in seen and seen[cls] != cohort:
                repeated.append(f["id"])
            else:
                new.append(f["id"])
                seen.setdefault(cls, cohort)
        out[cohort] = {
            "companies": {"A": 14, "B": 13, "C": 13}[cohort],
            "findings": len(rows),
            "new_systemic": len(new), "new_ids": new,
            "repeated_systemic": len(repeated), "repeated_ids": repeated,
            "p0": sum(1 for f in rows if f["severity"] == "P0"),
            "p1": sum(1 for f in rows if f["severity"] == "P1"),
            "p2": sum(1 for f in rows if f["severity"] == "P2"),
            "classes": sorted({f["defect_class"] for f in rows
                               if f["defect_class"] not in _LOCAL}),
        }

    ran = [c for c in "ABC" if out[c]["findings"]]
    if len(ran) < 2:
        verdict, reason = "NOT_ENOUGH_EVIDENCE", (
            f"only cohort {', '.join(ran) or 'none'} has findings recorded; a "
            f"curve needs at least two points.")
    else:
        series = [out[c]["new_systemic"] for c in ran]
        rep = [out[c]["repeated_systemic"] for c in ran]
        if all(b <= a for a, b in zip(series, series[1:])) and \
                series[0] > series[-1]:
            verdict = "CONVERGING"
            reason = (
                f"new systemic findings fall {' -> '.join(map(str, series))} "
                f"across {' -> '.join(ran)}, and repeated ones are "
                f"{' -> '.join(map(str, rep))}. The later cohorts are "
                f"confirming invariants rather than discovering classes.")
        elif series[-1] > series[0]:
            verdict = "REGRESSING"
            reason = (
                f"new systemic findings RISE {' -> '.join(map(str, series))}; "
                f"a later cohort is finding more classes than the discovery "
                f"cohort did, which means the universe was not representative "
                f"or a repair introduced defects.")
        elif max(series) - min(series) <= 1:
            verdict = "PLATEAUED"
            reason = (
                f"new systemic findings are flat "
                f"{' -> '.join(map(str, series))}; each cohort is still "
                f"finding roughly as many new classes as the last, so the "
                f"defect supply is not exhausted.")
        else:
            verdict = "NOT_ENOUGH_EVIDENCE"
            reason = (f"the series {' -> '.join(map(str, series))} has no "
                      f"clear direction.")
        if any(out[c]["repeated_systemic"] for c in ran[1:]):
            reason += (" Repeated classes are listed per cohort: each one is "
                       "an invariant that was written too narrowly.")

    doc = {"contract": "next40_convergence.v1", "classification": verdict,
           "reason": reason, "cohorts_with_findings": ran,
           "class_first_seen": seen, **out}
    (ROOT / args.out).write_text(json.dumps(doc, indent=1))
    print(f"CONVERGENCE: {verdict}\n{reason}\n")
    for c in "ABC":
        r = out[c]
        print(f"COHORT {c}  findings {r['findings']:2d}  new systemic "
              f"{r['new_systemic']:2d}  repeated {r['repeated_systemic']:2d}  "
              f"P0 {r['p0']}  P1 {r['p1']}  P2 {r['p2']}")
        if r["classes"]:
            print(f"           classes: {', '.join(r['classes'])}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
