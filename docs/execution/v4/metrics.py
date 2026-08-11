#!/usr/bin/env python3
"""Measure the data gates, from the ledger, with a date attached.

WHY THIS IS A SEPARATE FILE
---------------------------
`frontier.py` must not guess whether a node has enough evidence, and it must
not be handed a number somebody typed. It reads what was MEASURED, and every
measurement carries `measured_at` so a stale gate is visible as stale rather
than as fact.

    python3 docs/execution/v4/metrics.py            # measure and print
    python3 docs/execution/v4/metrics.py --write    # ... and update METRICS.json

A metric that cannot be measured is reported as None, never as 0. Those are
different claims: "we looked and there are none" and "we could not look". A
gate reading None blocks its node, because a node may not become runnable on
the strength of a measurement nobody took.

EVERY `prospective_*` GATE FILTERS ON POPULATION
------------------------------------------------
B-HIST-002. The historical corpus exists so estimators and reward models can be
trained today rather than in a year, and it is worth nothing if a single row of
it can reach the counter that says how much the engine has actually been
tested. So the filter is POSITIVE — a row is counted because it declared
PROSPECTIVE, never because it failed to declare HISTORICAL — and a row that
declares nothing at all is refused and counted under
`population_untagged_rows` rather than defaulted into either side.

`prospective_outcomes` previously counted EVERY `research_outcome` row in the
ledger, with no population or provenance filter of any kind. That was not a
latent risk: 1,000 historical outcome rows appended to the ledger would have
moved it by 1,000, and `prospective_empty_handed` and `prospective_failed`
with it, because all three read the same unfiltered list. An outcome now
inherits the population of the decision it names, and an outcome naming no
decision on the ledger is an orphan that belongs to no population.

THE VOCABULARY IS DECLARED TWICE, ON PURPOSE
---------------------------------------------
`intent_engine.market.historical_corpus` owns it. This file restates it because
this file runs as `python3 docs/execution/v4/metrics.py` with no PYTHONPATH and
must stay stdlib-only — the same reason the founder branch keeps its own copy
of the export allowlist. Two copies drift, so
`tests/test_market_population_separation.py` runs both resolvers over the same
adversarial rows and fails if they ever disagree.
"""
from __future__ import annotations

import collections
import datetime as _dt
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
OUT = HERE / "METRICS.json"

#: The live PAPER runtime tree. Its ledger is the accumulating state, so the
#: gates are measured there rather than in whatever worktree this runs from.
RUNTIME_LEDGER = pathlib.Path(
    "/Users/prathamsharma/intent-engine-market/reports/market/"
    "learning_ledger.jsonl")

# --- population, restated from intent_engine.market.historical_corpus ---------
HISTORICAL = "HISTORICAL"
PROSPECTIVE = "PROSPECTIVE"
POPULATIONS = (HISTORICAL, PROSPECTIVE)

#: Declarations made under the field name that existed BEFORE `population`
#: did. Keyed on record kind, field and exact value so nothing generalises.
#:
#: WHY THIS IS A TRANSLATION AND NOT A DEFAULT. A `research_decision` row
#: carrying `provenance=PROSPECTIVE` was written by the live engine, before the
#: external call, with the answer unavailable — the definition of the
#: prospective population, asserted by the producer in the only field the
#: schema then had. Assuming a population for a row that declared NOTHING would
#: be a default, and `_population_of` returns "" for those.
#:
#: `provenance=RECONSTRUCTED` is deliberately absent. A reconstructed row is
#: not a historical episode either; it resolves to no population and is counted
#: on neither side.
LEGACY_POPULATION_DECLARATIONS = {
    ("research_decision", "provenance", PROSPECTIVE): PROSPECTIVE,
}


def _population_of(row):
    """The population a row DECLARES, or "" when it declares none.

    The explicit `population` field is read FIRST, so a row tagged HISTORICAL
    stays historical whatever else it carries. That order is the guard: the
    attack is a historical row wearing `provenance=PROSPECTIVE`, and it must
    lose to its own population tag.
    """
    declared = str(row.get("population") or "")
    if declared:
        return declared if declared in POPULATIONS else ""
    kind = str(row.get("record") or "")
    for (record, field, value), population in \
            LEGACY_POPULATION_DECLARATIONS.items():
        if kind == record and str(row.get(field) or "") == value:
            return population
    return ""


def _rows(path):
    if not path.exists():
        return None
    out = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _comparable_pairs(ledger) -> int:
    """DecisionImpact rows that graded a real prior-vs-current comparison.

    Sits beside the ledger rather than in it: the Founder surface writes
    `decision_impact.jsonl` next to the learning ledger. A row counts only if
    it graded an actual pair, so FIRST_OBSERVATION — a dossier with no prior
    revision — is excluded. It is neither an impact nor a failure to have
    one, and counting it would clear this gate with rows that cannot answer
    the question the gate is asking.
    """
    path = pathlib.Path(ledger).parent / "decision_impact.jsonl"
    rows = _rows(path)
    if not rows:
        return 0
    return sum(1 for r in rows
               if str(r.get("materiality") or r.get("impact") or "")
               not in ("", "FIRST_OBSERVATION"))


def measure(ledger=RUNTIME_LEDGER) -> dict:
    rows = _rows(pathlib.Path(ledger))
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    if rows is None:
        # Unreadable ledger: every gate is UNKNOWN, not zero.
        return {"measured_at": now, "source": str(ledger),
                "readable": False, "metrics": {}}

    decisions = [r for r in rows if r.get("record") == "research_decision"]
    outcomes = [r for r in rows if r.get("record") == "research_outcome"]
    # TWO INDEPENDENT WALLS, AND A ROW MUST CLEAR BOTH. `population` separates
    # the engine running forward from a past assembled afterwards.
    # `provenance` separates a decision written before the call from one
    # inferred out of a document that survived. A reconstructed row is not
    # historical, and a historical row is not reconstructed; neither wall
    # implies the other and collapsing them would let a row through on the
    # strength of the test it happened to pass.
    prospective = [d for d in decisions
                   if _population_of(d) == PROSPECTIVE
                   and d.get("provenance") == PROSPECTIVE]
    # AN OUTCOME BELONGS TO THE POPULATION OF ITS DECISION. It carries no
    # population of its own — it is a result, and the choice that produced it
    # is what was or was not prospective. An outcome naming a decision that is
    # not on the ledger is an ORPHAN and belongs to no population: counting it
    # would let an outcome row with a made-up decision_id into the gate.
    prospective_ids = {d.get("decision_id") for d in prospective
                       if d.get("decision_id")}
    prospective_outcomes = [o for o in outcomes
                            if o.get("decision_id") in prospective_ids]
    by_status = collections.Counter(str(r.get("status") or "")
                                    for r in prospective_outcomes)
    census = collections.Counter(_population_of(r) or "UNTAGGED"
                                 for r in decisions)
    relationships = [r for r in rows if r.get("record") == "relationship"]
    supplier = [r for r in relationships
                if str(r.get("predicate") or "").upper()
                in ("SUPPLIES", "SUPPLIED_BY", "SUPPLIER_OF")]

    metrics = {
        "prospective_decisions": len(prospective),
        "prospective_outcomes": len(prospective_outcomes),
        "prospective_with_forgone_option": sum(1 for d in prospective
                                               if d.get("forgone")),
        "prospective_empty_handed": (by_status.get("NO_RESULT", 0)
                                     + by_status.get("NO_NEW_INFORMATION", 0)),
        "prospective_failed": (by_status.get("FAILED", 0)
                               + by_status.get("TIMEOUT", 0)),
        # A propensity only exists where the policy randomised. The logging
        # policy is deterministic, so this is 0 and the bandit node stays
        # blocked on it rather than on a judgement call.
        "logged_exploration_events": sum(
            1 for d in prospective
            if d.get("selection_probability_status") == "KNOWN"),
        "named_supplier_edges": len(supplier),
        # COMPARABLE FOUNDER REVISION PAIRS. The gate H-IMP-001's empirical
        # half waits on. A DecisionImpact row counts only if it graded an
        # actual comparison — FIRST_OBSERVATION is a dossier with no prior
        # revision, so it is neither an impact nor a failure to have one, and
        # counting it would clear the gate with rows that cannot answer the
        # question. Measured from the Founder's own persisted file so the
        # gate clears itself the first time a real second revision lands.
        "comparable_founder_revision_pairs": _comparable_pairs(ledger),
        "macro_observations": sum(1 for r in rows
                                  if r.get("record") == "macro_observation"),
        # HOW MUCH OBSERVATION HISTORY EXISTS, which is a different quantity
        # from how much HISTORY exists. Every macro figure in the ledger was
        # retrieved inside one month while describing periods across three
        # years, so at any earlier instant the vintage admits nothing and a
        # historical replay has no T0 to stand on. Counting distinct
        # retrieval months makes that a gate the executor measures rather
        # than a judgement someone records — and it rises on its own as the
        # cycle keeps running.
        "macro_retrieval_months": len({
            str(r.get("retrieved_at") or "")[:7]
            for r in rows if r.get("record") == "macro_observation"
            and r.get("retrieved_at")}),
        "knowledge_effects": sum(1 for r in rows
                                 if r.get("record") == "knowledge_effect"),
        "evidence_rows": sum(1 for r in rows if r.get("record") == "evidence"),
        # THE OTHER POPULATION, REPORTED AND NEVER ADDED. Named
        # `historical_*` so no gate can reach it by pattern, and present even
        # at zero so the separation is visibly being measured rather than
        # assumed. It is a count of ledger rows tagged HISTORICAL; the corpus
        # itself lives in reports/market/historical_corpus.jsonl and nothing
        # in this file reads it.
        "historical_decisions": census.get(HISTORICAL, 0),
        # ROWS THAT DECLARED NOTHING. Refused from both populations rather
        # than defaulted, and surfaced here so the refusal is a number an
        # operator can watch instead of a silent subtraction. It falls to
        # zero on its own as producers write the field.
        "population_untagged_rows": census.get("UNTAGGED", 0),
        # OUTCOMES NAMING NO DECISION ON THIS LEDGER. They belong to no
        # population, so they are in no gate; counting them here keeps the
        # difference between "there were none" and "they were dropped".
        "orphan_outcomes": sum(
            1 for o in outcomes
            if o.get("decision_id") not in {d.get("decision_id")
                                            for d in decisions}),
    }
    return {"measured_at": now, "source": str(ledger), "readable": True,
            "metrics": metrics}


def load() -> dict:
    if OUT.exists():
        try:
            return json.loads(OUT.read_text(encoding="utf-8"))
        except ValueError:
            return {"metrics": {}, "readable": False}
    return {"metrics": {}, "readable": False}


def main(argv) -> int:
    got = measure()
    if "--write" in argv:
        OUT.write_text(json.dumps(got, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
    print(f"measured_at {got['measured_at']}  readable={got['readable']}")
    for key, value in sorted(got.get("metrics", {}).items()):
        print(f"  {key:36s} {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
