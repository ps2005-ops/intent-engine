#!/usr/bin/env python3
"""The economic chain, per company, measured rather than assumed.

A GENERIC MACRO PARAGRAPH IS NOT ECONOMIC INTELLIGENCE. The question is
whether the page builds a chain a reader can follow and disagree with:

    economic or market change
      -> what of THIS company is exposed
        -> the effect on demand, cost, capital or operations
          -> the constraint or opportunity that creates
            -> the management decision it bears on
              -> the expected consequence
                -> what would falsify it
                  -> what to learn next

Each link is looked for on the company's own pages and quoted. A link that is
absent is reported absent; a page that says specifically WHY it cannot reach
a link is credited with the bound rather than the link, because "no economic
state had been published on or before this date" is information and a
fabricated transmission mechanism is not.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
from public_journey_ten import visible                           # noqa: E402

UI = ROOT / "reports/next40_ui"

LINKS = [
    ("economic_change", (
        r"The economic state published for [^.]{0,80}",
        r"measured [a-z ]+ conditions reach this business",
        r"economic layer did not run",
        r"no economic state had been published")),
    ("company_exposure", (
        r"Revenue moves with [^.]{0,90}",
        r"What it earns moves with [^.]{0,90}",
        r"Cost moves with [^.]{0,90}")),
    ("effect", (
        r"revenue at a business of this kind moves with [^.]{0,80}",
        r"so the installed base carries [^.]{0,80}",
        r"margin moves after volume does")),
    ("constraint_or_opportunity", (
        r"Key risk[^.]{0,160}",
        r"What most limits this[^.]{0,140}",
        r"What is open[^.]{0,120}")),
    ("management_decision", (
        r"For [^:]{1,70}: [^?]{10,190}\?",)),
    ("expected_consequence", (
        r"If we act, what follows",
        r"then [a-z ]{5,60} follows at the lag this business model imposes")),
    ("falsifier", (
        r"What would change the recommendation",
        r"stop if[^.]{0,140}",
        r"would falsify[^.]{0,120}",
        r"What could have invalidated it[^.]{0,120}")),
    ("next_priority", (
        r"Next test[^.]{0,180}",
        r"What would settle it[^.]{0,140}",
        r"should management investigate next")),
]


def _slug(n):
    return re.sub(r"[^a-z0-9]+", "-", str(n or "").lower()).strip("-")


def _blob(company):
    out = []
    for key in ("xray", "brief", "full", "result", "intro", "history",
                "story"):
        p = UI / f"{_slug(company)}-{key}.html"
        if p.exists():
            out.append(" ".join(visible(p.read_text()).split()))
    return " \n ".join(out)


def chain_for(company, no_decision=False, bounded_page=False) -> dict:
    text = _blob(company)
    found, quotes = {}, {}
    for name, patterns in LINKS:
        hit = None
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                hit = " ".join(m.group(0).split())[:170]
                break
        found[name] = bool(hit)
        quotes[name] = hit or ""
    # A BOUND IS NOT A GAP. A page that says why it cannot place the company
    # in its economic period has answered the question honestly.
    bounded = bool(re.search(
        r"no economic state had been published|economic layer did not run|"
        r"could not be answered from the public record", text))
    complete = sum(1 for v in found.values() if v)
    # A COMPANY WITH NO ESTABLISHED BUSINESS MODEL CANNOT HAVE THE MIDDLE OF
    # THE CHAIN, and inventing one is the failure this whole module guards.
    # Its exposure, its effect and its management decision all depend on
    # knowing how it is paid; the page says that is not established and names
    # what would settle it. A shorter chain there is the correct chain.
    # A RUN THAT PRODUCED NO REPORT HAS ALMOST NO CHAIN, AND THAT IS RIGHT.
    # 6sense's own site answers 401/403 on every path, so nothing was
    # retrieved; the page names the failure and refuses to invent a reading.
    # Expecting exposure, effect, a management decision or a falsifier from
    # a run with no evidence is expecting the thing this product exists not
    # to do.
    expected = (4 if bounded_page else
                len(LINKS) - 3 if no_decision else len(LINKS))
    return {"company": company, "links_present": complete,
            "links_total": len(LINKS), "links_expected": expected,
            "links": found, "quotes": quotes,
            "states_its_bound": bounded, "no_decision": no_decision,
            "bounded_page": bounded_page,
            "verdict": ("CHAIN_COMPLETE" if complete >= expected
                        and not no_decision and not bounded_page else
                        "CHAIN_BOUNDED" if complete >= expected else
                        "CHAIN_PARTIAL" if complete >= 5 else "CHAIN_THIN")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", default="ALL")
    args = ap.parse_args()
    analysis = json.loads((ROOT / "reports/next40_analysis.json").read_text())
    rng = {"A": range(1, 15), "B": range(15, 28), "C": range(28, 41),
           "ALL": range(1, 41)}[args.cohort]
    state = json.loads((ROOT / "reports/next40_state.json").read_text())
    bounded = {r["company"] for r in state["rows"].values()
               if r.get("bounded_page")}
    out = [chain_for(r["company"],
                     no_decision=(r.get("decision_force") == "NO_DECISION"),
                     bounded_page=(r["company"] in bounded))
           for r in analysis["rows"] if r["n"] in rng]
    names = [n for n, _p in LINKS]
    print(f"{'company':13s} " + " ".join(f"{n[:4]:>4s}" for n in names)
          + "   verdict")
    for c in out:
        cells = ["  ok" if c["links"][n] else "   -" for n in names]
        print(f"{c['company'][:12]:13s} " + " ".join(f"{x:>4s}" for x in cells)
              + f"   {c['verdict']}")
    tally = {}
    for c in out:
        tally[c["verdict"]] = tally.get(c["verdict"], 0) + 1
    print()
    for n in names:
        print(f"  {n:28s} {sum(1 for c in out if c['links'][n])}/{len(out)}")
    print(f"\n{tally}")
    (ROOT / "reports/next40_econ_chain.json").write_text(json.dumps(
        {"contract": "next40_econ_chain.v1", "companies": out}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
