#!/usr/bin/env python3
"""Cross-company negative controls: unrelated evidence must not converge.

WHY PAIRS AND NOT A SCORE PER COMPANY. A template is invisible from inside a
single report -- every sentence looks reasonable. It is only when two
unrelated companies produce the same sentence that anybody can see it, which
is why the recorded failure is a constant decision question that survived to
the page for an entire cohort and looked fine on each one.

Generic INTRODUCTION text is allowed and expected: the "generic
interpretation" half of the differentiation section is supposed to be shared
by companies of a kind, and measuring it for collapse measures the design
rather than the output. What must differ is strategic SUBSTANCE.

Runs offline against each company's own published text. No demo quota, no
deployed service, no model call.
"""
from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from intent_engine.adaptive.differentiation import genericity   # noqa: E402
from intent_engine.adaptive.engine import build                 # noqa: E402

#: The pairs section 5 names, each chosen because the two are unrelated.
PAIRS = (
    ("Highspot", "BigID"),
    ("BigID", "Cyera"),
    ("Cyera", "Slalom"),
    ("Monte Carlo Data", "Point B"),
    ("ZoomInfo", "Veeam"),
    ("Sigma Computing", "Druva"),
)

SITES = {
    "Highspot": "https://www.highspot.com/",
    "BigID": "https://bigid.com/",
    "Cyera": "https://www.cyera.com/",
    "Monte Carlo Data": "https://www.montecarlodata.com/",
    "Veeam": "https://www.veeam.com/",
    "Druva": "https://www.druva.com/",
    "Slalom": "https://www.slalom.com/",
    "Sigma Computing": "https://www.sigmacomputing.com/",
    "ZoomInfo": "https://www.zoominfo.com/",
    "Point B": "https://pointb.com/",
}

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "replace")
    html = re.sub(r"<(script|style|noscript)\b[^>]*>.*?</\1>", " ", html,
                  flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


#: What must differ between two unrelated companies, and how it is read off.
#:
#: EACH ASPECT READS WHAT A READER SEES. An earlier version compared the bare
#: `decision_domain` STRING, which is the lens's own vocabulary and is
#: identical for any two companies sharing a lens by construction -- so it
#: reported a collapse for BigID and Cyera while the rendered cards said
#: visibly different things. A control that measures a field nobody reads
#: measures the schema, not the product.
ASPECTS = {
    "self description":
        lambda a: getattr(a.profile.self_description, "value", ""),
    "why this company":
        lambda a: a.differentiation.company_specific_difference,
    "decision domain":
        lambda a: " ".join(
            [f"{o.decision_description} {o.why_now}"
             for o in a.opportunity_map.opportunities]
            or [f"{d.domain} {d.why_it_could_matter}"
                for d in a.opportunity_map.domains]),
    "causal mechanism":
        lambda a: " ".join(l.text for l in a.causal_chain.links),
    "lens":
        lambda a: a.lens_selection.primary,
}

#: Compared only when BOTH sides are company-specific. A class prior is
#: shared by every company of a kind BY DESIGN -- that is what makes it a
#: prior -- and it reaches the page only inside the explicitly-labelled
#: "generic interpretation" half. Measuring it for collapse measures the
#: architecture rather than the output, and would push toward inventing
#: per-company economics we have not established.
PROVENANCE_GATED = {
    "business model explanation": lambda a: a.profile.business_model,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/adaptive_negative_controls.json")
    a = ap.parse_args()

    built, texts = {}, {}
    for name in sorted({n for pair in PAIRS for n in pair}):
        try:
            texts[name] = fetch(SITES[name])
        except Exception as exc:                             # noqa: BLE001
            print(f"{name:18s} FETCH FAILED {type(exc).__name__}")
            continue
        built[name] = build(company=name, domain=SITES[name],
                            evidence_text=texts[name])

    rows, failures = [], 0
    for left, right in PAIRS:
        if left not in built or right not in built:
            print(f"{left} vs {right}: SKIPPED (fetch)")
            continue
        row = {"left": left, "right": right, "aspects": {}}
        print(f"\n{left} vs {right}")
        for aspect, read in PROVENANCE_GATED.items():
            lf, rf = read(built[left]), read(built[right])
            if not (lf.company_specific and rf.company_specific):
                row["aspects"][aspect] = {
                    "verdict": "EXPECTED_SHARED",
                    "provenance": [lf.provenance, rf.provenance]}
                print(f"   {aspect:26s} shared    "
                      f"({lf.provenance.lower()}) — a class prior, shown "
                      f"only as the generic half")
                continue
            finding = genericity(left_text=lf.value, left_company=left,
                                 right_text=rf.value, right_company=right)
            row["aspects"][aspect] = {"ratio": finding.ratio,
                                      "collapsed": finding.collapsed}
            print(f"   {aspect:26s} "
                  f"{'COLLAPSED' if finding.collapsed else 'ok       '} "
                  f"{finding.ratio:.3f}")
            if finding.collapsed:
                failures += 1

        for aspect, read in ASPECTS.items():
            lv, rv = read(built[left]), read(built[right])
            if aspect == "lens":
                # A SHARED LENS IS NOT AUTOMATICALLY CONTAMINATION. Two data
                # security companies routing to Data Security & Governance is
                # the router being right, and section 20 names that family
                # for both. What would be a defect is two companies sharing a
                # lens AND saying the same things underneath it -- so this is
                # reported for inspection and counted only when the substance
                # collapsed too.
                same = bool(lv) and lv == rv
                substance = [k for k, v in row["aspects"].items()
                             if isinstance(v, dict) and v.get("collapsed")]
                verdict = ("SHARED_AND_DISTINCT" if same and not substance
                           else "SHARED_AND_COLLAPSED" if same
                           else "DIFFERENT")
                row["aspects"][aspect] = {"left": lv, "right": rv,
                                          "verdict": verdict}
                print(f"   {aspect:26s} "
                      f"{verdict:20s} {lv} / {rv}")
                if verdict == "SHARED_AND_COLLAPSED":
                    failures += 1
                continue
            finding = genericity(left_text=lv, left_company=left,
                                 right_text=rv, right_company=right)
            row["aspects"][aspect] = {"ratio": finding.ratio,
                                      "collapsed": finding.collapsed,
                                      "shared": list(
                                          finding.shared_sentences)[:2]}
            mark = "COLLAPSED" if finding.collapsed else "ok       "
            print(f"   {aspect:26s} {mark} {finding.ratio:.3f}")
            if finding.collapsed:
                failures += 1
        rows.append(row)

    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"pairs": rows, "failures": failures},
                              indent=2))
    print(f"\n{failures} collapse(s) across {len(rows)} pair(s) x "
          f"{len(ASPECTS)} aspect(s)")
    print(f"written {out}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
