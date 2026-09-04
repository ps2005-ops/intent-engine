#!/usr/bin/env python3
"""Where does learning stop? Name the FIRST starved conversion, not the total.

    PYTHONPATH=src python3 scripts/v5_learning_funnel.py WAVE.json [--out F]

THE QUESTION
------------
Batch 13 raised independent evidence 9 → 22 and independently corroborated
companies 0 → 6. None of that says the system LEARNED anything. A funnel that
reports totals lets a healthy early stage hide a dead late one, so this walks
the chain in order and stops at the first transition that loses materially:

  DISCOVERED → FETCHED → CANONICALIZED → INDEPENDENT → ANALYZED
             → BELIEF_ELIGIBLE → BELIEF_CHANGED
             → THESIS_OR_EXPECTATION_CHANGED → EXECUTIVE_CONSUMED

WHY THE CAUSE MATTERS AS MUCH AS THE STAGE
-------------------------------------------
A stage can read zero for three completely different reasons, and they have
three different repairs:

  LOSS                 the stage ran and discarded most of its input
  BLOCKED_EXTERNAL     a dependency outside this system did not run
  NO_PRODUCER          nothing in this codebase can produce this stage's
                       output at all

Collapsing them is how "we are blocked on credits" survives as an explanation
for a stage that has no producer and would still read zero with the backend
fully paid. Every stage therefore carries its cause, and the verdict names it.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

CONTRACT = "learning_funnel.v1"

LOSS = "LOSS"
BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
NO_PRODUCER = "NO_PRODUCER"
HEALTHY = "HEALTHY"
UNAVAILABLE = "UNAVAILABLE"

#: Below this share surviving a transition, the transition is STARVED. Not a
#: quality bar on any company — a sparse private company legitimately loses
#: most candidates — which is why the verdict also carries the cause.
MATERIAL_SURVIVAL = 0.20


def _dig(payload, *path, default=None):
    node = payload
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


#: What each stage COUNTS. A ratio between two stages is only a survival rate
#: when both count the same kind of thing. `INDEPENDENT` counts documents and
#: `ANALYZED` counts companies, so "22 → 1 = 4.5% survived" is not a share of
#: anything — it is documents divided by companies. This programme has shipped
#: that error before under other names, so the populations are declared and
#: the ratio is only taken WITHIN one.
DOCUMENTS = "documents"
COMPANIES = "companies"
EVIDENCE_ROWS = "evidence_rows"


def stages(record: dict) -> list:
    """The chain for one company, in order, each with its cause."""
    evidence = record.get("evidence") or {}
    independence = evidence.get("independence") or {}
    health = record.get("source_health") or {}
    intel = record.get("intelligence") or {}
    learning = record.get("learning") or {}

    documents = int(evidence.get("documents_retrieved") or 0)
    independent = independence.get("independent_evidence_count")
    analysed = 1 if (intel.get("strategic_report") == "PRESENT"
                     and str(intel.get("result_state") or "")
                     not in ("FAILED", "")) else 0
    attribution = str(learning.get("attribution_state") or "")

    return [
        {"stage": "DISCOVERED", "n": int(health.get("attempted") or 0),
         "population": DOCUMENTS, "cause": HEALTHY},
        {"stage": "FETCHED", "n": int(health.get("ok") or 0),
         "population": DOCUMENTS, "cause": HEALTHY},
        {"stage": "CANONICALIZED", "n": documents, "population": DOCUMENTS,
         "cause": HEALTHY},
        {"stage": "INDEPENDENT",
         "n": independent if isinstance(independent, int) else None,
         "population": DOCUMENTS,
         "cause": HEALTHY if isinstance(independent, int) else UNAVAILABLE},
        # The denominator ANALYZED is actually a share of. Without it the next
        # transition divides companies by documents.
        {"stage": "ELIGIBLE_COMPANIES", "n": 1, "population": COMPANIES,
         "cause": HEALTHY},
        # The analyst either produced a usable report or it did not, and when
        # it did not for an external reason that is not a fact about the
        # evidence.
        {"stage": "ANALYZED", "n": analysed, "population": COMPANIES,
         "cause": (HEALTHY if analysed else
                   BLOCKED_EXTERNAL
                   if attribution == "BLOCKED_EXTERNAL_CREDITS" else LOSS)},
        # NO_PRODUCER, and this is the finding this instrument exists to make
        # unmissable: nothing in the founder codebase constructs a
        # KnowledgeEffect, so these stages would read zero with the backend
        # fully paid. `NOT_ATTEMPTED` from the attribution producer means
        # exactly that — a knowledge state existed and nothing was written
        # against it.
        {"stage": "BELIEF_ELIGIBLE", "n": 0, "population": EVIDENCE_ROWS,
         "cause": (BLOCKED_EXTERNAL
                   if attribution == "BLOCKED_EXTERNAL_CREDITS"
                   else NO_PRODUCER)},
        {"stage": "BELIEF_CHANGED",
         "n": int(learning.get("effect_producing_evidence_rows") or 0)
         if isinstance(learning.get("effect_producing_evidence_rows"), int)
         else 0,
         "population": EVIDENCE_ROWS, "cause": NO_PRODUCER},
        {"stage": "THESIS_OR_EXPECTATION_CHANGED", "n": 0,
         "population": EVIDENCE_ROWS, "cause": NO_PRODUCER},
        {"stage": "EXECUTIVE_CONSUMED",
         "n": 1 if record.get("dossier") else 0, "population": COMPANIES,
         "cause": HEALTHY},
    ]


def first_starved(chain: list) -> dict:
    """The first transition that loses materially, and WHY.

    Walked in order and returned on the first hit. A later stage reading zero
    is not news when an earlier one already emptied.

    TWO TESTS, BECAUSE THERE ARE TWO KINDS OF TRANSITION:

      * within one population, a survival RATIO below the floor is a loss;
      * across a population boundary a ratio is meaningless, so the only
        thing asserted is the zero crossing — upstream produced something and
        downstream produced nothing.

    The zero crossing applies in both cases and is the stronger signal: it is
    what separates "this stage discards most of its input" from "this stage
    has no producer at all".
    """
    for index in range(1, len(chain)):
        prior, current = chain[index - 1], chain[index]
        if current["n"] is None:
            return {"transition": f"{prior['stage']} → {current['stage']}",
                    "cause": UNAVAILABLE, "survived": UNAVAILABLE,
                    "from": prior["n"], "to": current["n"]}
        if prior["n"] in (None, 0):
            continue
        same_population = prior.get("population") == current.get("population")
        if current["n"] == 0:
            return {"transition": f"{prior['stage']} → {current['stage']}",
                    "cause": current["cause"],
                    "survived": 0.0 if same_population else UNAVAILABLE,
                    "from": prior["n"], "to": current["n"]}
        if not same_population:
            # Different units. Nothing is claimed about magnitude, and
            # claiming one is how "22 documents → 1 company" became "4.5%".
            continue
        survived = current["n"] / prior["n"]
        if survived < MATERIAL_SURVIVAL:
            return {"transition": f"{prior['stage']} → {current['stage']}",
                    "cause": current["cause"],
                    "survived": round(survived, 4),
                    "from": prior["n"], "to": current["n"]}
    return {"transition": "none", "cause": HEALTHY, "survived": 1.0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wave")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    wave = json.loads(pathlib.Path(args.wave).read_text())
    records = wave.get("results", [])

    per_company, causes = [], {}
    for record in records:
        chain = stages(record)
        verdict = first_starved(chain)
        per_company.append({"company_id": record.get("company_id"),
                            "chain": chain, "first_starved": verdict})
        key = f"{verdict['transition']} [{verdict['cause']}]"
        causes[key] = causes.get(key, 0) + 1

    cohort_chain = []
    for index, stage in enumerate(stages(records[0]) if records else []):
        total = 0
        unavailable = False
        for record in records:
            value = stages(record)[index]["n"]
            if value is None:
                unavailable = True
            else:
                total += value
        cohort_chain.append({"stage": stage["stage"],
                             "n": None if unavailable else total,
                             "population": stage.get("population"),
                             "cause": stage["cause"]})
    cohort_verdict = first_starved(cohort_chain) if cohort_chain else {}

    payload = {"contract": CONTRACT,
               "runtime_sha": _dig(wave, "frozen", "runtime_sha"),
               "cohort_chain": cohort_chain,
               "cohort_first_starved": cohort_verdict,
               "per_company": per_company,
               "first_starved_histogram": dict(sorted(causes.items()))}

    print(f"\n{'=' * 74}\nLEARNING FUNNEL — cohort\n{'=' * 74}")
    previous, previous_population = None, None
    for stage in cohort_chain:
        value = "UNAVAILABLE" if stage["n"] is None else stage["n"]
        share = ""
        if isinstance(stage["n"], int) and isinstance(previous, int) \
                and previous and stage.get("population") == previous_population:
            share = f"   ({stage['n'] / previous:.1%} of previous)"
        elif stage.get("population") != previous_population \
                and previous_population is not None:
            share = f"   [{stage.get('population')}, new population]"
        print(f"{stage['stage']:<32}{str(value):>8}{share}")
        previous, previous_population = stage["n"], stage.get("population")
    print(f"\nFIRST_STARVED_CONVERSION: {cohort_verdict.get('transition')}")
    print(f"CAUSE                   : {cohort_verdict.get('cause')}")
    print(f"survived                : {cohort_verdict.get('survived')}")
    print("\nper-company first starved transition:")
    for key, count in sorted(causes.items()):
        print(f"  {count:>2}  {key}")

    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True))
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
