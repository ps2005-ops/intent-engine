"""The market engine's end of the canonical economic core.

WHICH DIRECTION EACH FUNCTION GOES
-----------------------------------
    publish_*   market -> core.   What this engine has measured about the
                economy, translated into the shared vocabulary.
    consume_*   core -> market.   Candidate indicators derived from public
                company evidence, arriving as HYPOTHESES.

WHY A TRANSLATION AND NOT A RE-EXPORT
--------------------------------------
`macro_state.MacroObservation` carries series selection rules, revision
chains, publication-basis flags and a `measure` axis that only this engine's
ingestion needs. The shared node is deliberately poorer. Handing the richer
object across would make every founder-side consumer depend on this package's
internal shape, and the whole point of the seam is that it does not.

THE NAME COLLISION, STATED ONCE
-------------------------------
`macro_state.EconomicState` is the state of ONE CONDITION -- "US policy rate,
OBSERVED, moved UP". `econ.state.EconomicState` is the whole economy at a
moment. This module maps the former into the latter's `ConditionReading`.
They were not merged; see `econ.state`'s docstring.

THREE DATES, AND WHICH ONE BECOMES `available_at`
--------------------------------------------------
`published_at`, always. Not `reference_period`, which is what the figure
DESCRIBES, and not `retrieved_at`, which is when we happened to look. A June
figure published in July and read in August was knowable in July, and using
either other date invents or destroys a month of foresight.

Where `publication_basis` is ASSUMED_LAG the date is this engine's own
assumption rather than a publisher's statement, and the node records that in
its provenance -- because a replay scored against an assumed availability
date is only as good as the assumption.

WHAT NEVER CROSSES
------------------
Positions, paper books, funnels, strategies, signal states, schedulers. Not
by filtering: `publish_state` builds from `MacroObservation` and belief
objects only, and `econ.state.validate` re-checks the result against an
allowlist that would refuse them at any depth.
"""
from __future__ import annotations

import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from intent_engine.econ import belief as EB
from intent_engine.econ import evidence as EV
from intent_engine.econ import state as ES
from intent_engine.econ import store as EST
from intent_engine.econ import vocabulary as V
from intent_engine.market import macro_state as MS

CONTRACT = "market_econ_bridge.v1"

PRODUCER = "market"

#: `macro_state` state kinds -> the shared vocabulary's macro kinds.
#:
#: A kind with no mapping is NOT published. Inventing a destination for it
#: would put a figure under a heading it does not measure, and the shared
#: vocabulary is closed precisely so that cannot happen quietly. Unmapped
#: kinds are reported by `publish_state` under `unmapped`, which is how a new
#: series becomes a piece of work rather than a silent omission.
KIND_MAP = {
    MS.GROWTH: "growth",
    MS.INFLATION: "inflation",
    MS.POLICY_RATE: "policy_rate",
    MS.MARKET_RATE: "treasury_10y",
    MS.CREDIT_CONDITIONS: "financial_conditions",
    MS.EMPLOYMENT: "labour",
    MS.WAGES: "wages",
    MS.CONSUMER_DEMAND: "consumer_demand",
    MS.BUSINESS_INVESTMENT: "business_investment",
    MS.INDUSTRIAL_PRODUCTION: "industrial_production",
    MS.INVENTORY: "industrial_production",
    MS.COMMODITY_PRICE: "commodity_copper",
    MS.ENERGY_PRICE: "commodity_oil",
    MS.CURRENCY: "fx_dxy",
    MS.HOUSING: "housing",
    MS.FISCAL: "fiscal",
    MS.TRADE: "trade",
}

#: `macro_state` standings -> the shared vocabulary's. Same four words by
#: design, so this is an identity map that exists to fail loudly if either
#: side adds a fifth.
STANDING_MAP = {MS.OBSERVED: V.OBSERVED, MS.INFERRED: V.INFERRED,
                MS.HYPOTHESIZED: V.HYPOTHESIZED, MS.UNKNOWN: V.UNKNOWN}


def node_from_observation(obs: MS.MacroObservation) -> Optional[EV.EconomicNode]:
    """One `MacroObservation` as one shared evidence node, or None.

    Returns None rather than raising for an unmapped kind: a cycle that
    ingested a series this bridge does not know about should publish the rest
    and report the gap, not fail.
    """
    kind = KIND_MAP.get(obs.state_kind)
    if kind is None:
        return None
    occurred = (obs.reference_period or obs.published_at or "")[:10]
    available = (obs.published_at or obs.retrieved_at or occurred)[:10]
    if not occurred or not available:
        return None
    # NO ORDERING GUARD HERE, DELIBERATELY. The first version of this swapped
    # in the period end when publication preceded it, "conservatively". That
    # branch was unreachable: `MacroObservation.__post_init__` already refuses
    # a figure whose reference period ends after its publication date, with a
    # better message than this could give. A defensive branch duplicating an
    # upstream guard is dead code that reads as protection, and the next
    # reader has no way to tell which of the two is actually doing the work.
    # The invariant lives in `macro_state`; this bridge relies on it.
    basis_note = ("availability date is this engine's assumed publication "
                  "lag, not a date the publisher stated"
                  if obs.publication_basis == MS.ASSUMED_LAG else "")
    return EV.node(
        node_class=V.MACRO, kind=kind, subject=obs.area,
        standing=STANDING_MAP.get(obs.standing, V.HYPOTHESIZED),
        occurred_at=occurred, available_at=available,
        publisher=obs.source or obs.series_id or "unnamed publisher",
        value=obs.value, unit=obs.unit,
        statement=f"{obs.label}: {obs.value} {obs.unit}".strip(),
        confidence=0.8 if obs.standing == MS.OBSERVED else 0.5,
        visibility=V.PUBLIC, venue=obs.source, document_id=obs.series_id,
        producer=PRODUCER, retrieved_at=(obs.retrieved_at or "")[:10])


def _family_mechanisms() -> Dict[str, Tuple[str, str, str]]:
    """family -> (cause, effect, mechanism). The engine's own recorded table.

    Read from `causal_episodes`, which is where this engine states what it
    thinks connects a cause to an effect. Nothing is composed here: a family
    absent from that table has no recorded mechanism, and the belief it
    produced is refused rather than given a sentence that reads like one.
    """
    try:
        from intent_engine.market import causal_episodes as CE
        return {k: (v[0], v[1], v[2] if len(v) > 2 else "")
                for k, v in (CE._LINKS or {}).items()}
    except Exception:  # noqa: BLE001
        return {}


def beliefs_from_ledger(rows: Sequence[dict], *, at: str
                        ) -> Tuple[List[EB.EconomicBelief], Dict[str, Any]]:
    """Market beliefs as shared beliefs, by JOINING three records.

    THE DEFECT THIS REPLACED, FOUND ON THE FIRST LIVE CYCLE. The first
    version read `expected_observations`, `falsifier`, `mechanism` and
    `probability` off the belief object. `StrategicBelief` has none of those
    four fields -- its probability is `posterior_probability` and the rest
    live on other records -- so every one of 151 real beliefs was refused,
    and the cycle report announced that the market engine's beliefs "state no
    observable". They state one. The bridge was reading fields production
    does not write, which is where this class of defect always lives: in the
    seam, not in either side.

    THE JOIN, WHICH IS REAL AND WAS ALREADY THERE:

        belief.belief_id  ==  expectation.hypothesis_id      (151 of 151)
        expectation.metric ==  the causal family
        causal_episodes._LINKS[family]  ==  cause, effect, mechanism

    WHAT IS STILL REFUSED, AND WHY THAT NUMBER IS THE INTERESTING ONE. Only
    four families carry a recorded mechanism; `belief_formation` routes
    evidence into roughly twenty. A belief in one of the other sixteen has a
    proposition, a probability, an expectation and a falsifier -- and no
    stated account of WHY the cause should produce the effect. The shared
    contract requires one, so those are refused BY FAMILY, and the family
    names are reported. That is a work list for the market engine, not a
    flaw in its data.
    """
    expectations: Dict[str, dict] = {}
    for row in rows:
        if row.get("record") == "expectation":
            key = str(row.get("hypothesis_id") or "")
            if key:
                # Latest preregistration wins; earlier ones stay in the
                # ledger and are what a replay reads.
                prior = expectations.get(key)
                if (prior is None
                        or str(row.get("preregistered_at") or "")
                        >= str(prior.get("preregistered_at") or "")):
                    expectations[key] = row
    mechanisms = _family_mechanisms()

    out: List[EB.EconomicBelief] = []
    no_expectation, no_mechanism = 0, {}
    seen = set()
    for row in rows:
        if row.get("record") != "belief":
            continue
        belief_id = str(row.get("belief_id") or "")
        if not belief_id or belief_id in seen:
            continue
        seen.add(belief_id)
        expectation = expectations.get(belief_id)
        if not expectation:
            no_expectation += 1
            continue
        family = str(expectation.get("metric") or "")
        link = mechanisms.get(family)
        if not link:
            no_mechanism[family] = no_mechanism.get(family, 0) + 1
            continue
        cause, effect, mechanism = link
        falsifier = str(expectation.get("falsifier") or "").strip()
        expected = str(expectation.get("expected_event") or "").strip()
        proposition = str(row.get("proposition") or "").strip()
        if not (falsifier and expected and proposition):
            no_expectation += 1
            continue
        out.append(EB.declare(
            proposition=proposition,
            probability=float(row.get("posterior_probability") or 0.5),
            mechanism=(mechanism or f"{cause} -> {effect}"),
            falsifier=falsifier,
            expected_observations=(expected,),
            assumptions=tuple(str(x) for x in (row.get("limitations") or ())),
            at=str(row.get("last_updated") or at)[:10],
            subject=str(row.get("subject") or "US"),
            evidence_for=tuple(str(x) for x in
                               (row.get("supporting_evidence_ids") or ())),
            visibility=V.PUBLIC))
    return out, {"offered": len(seen),
                 "refused_no_expectation": no_expectation,
                 "refused_no_recorded_mechanism": no_mechanism}


def publish_state(*, observations: Sequence[MS.MacroObservation],
                  as_of: str, area: str = MS.US,
                  ledger_rows: Sequence[dict] = (),
                  graph_summary: Optional[dict] = None,
                  runtime_root=None) -> dict:
    """Translate what this engine measured, and write it to the shared core.

    Returns a REPORT, not a state: the caller is a cycle step and what it
    needs to record is how much crossed, how much did not, and why. The state
    itself is on disk and is what the founder side reads.
    """
    nodes: List[EV.EconomicNode] = []
    unmapped: Dict[str, int] = {}
    undated = 0
    for obs in observations:
        if obs.area != area:
            continue
        node = node_from_observation(obs)
        if node is None:
            if obs.state_kind not in KIND_MAP:
                unmapped[obs.state_kind] = unmapped.get(obs.state_kind, 0) + 1
            else:
                undated += 1
            continue
        nodes.append(node)

    beliefs, belief_report = beliefs_from_ledger(ledger_rows, at=as_of)
    state = ES.build(as_of=as_of, area=area, nodes=nodes, beliefs=beliefs,
                     producer=PRODUCER, graph_summary=graph_summary)
    payload = state.as_dict()          # validates against the allowlist

    written = 0
    if runtime_root is not None:
        EST.append_many(runtime_root, "node", [n.as_dict() for n in nodes],
                        written_at=as_of)
        EST.append_many(runtime_root, "belief", [b.as_dict() for b in beliefs],
                        written_at=as_of)
        EST.append(runtime_root, "state_snapshot", payload, written_at=as_of)
        written = len(nodes) + len(beliefs) + 1

    return {
        "contract": CONTRACT, "as_of": as_of, "area": area,
        "nodes_published": len(nodes),
        "beliefs_published": len(beliefs),
        "beliefs_offered": belief_report["offered"],
        # Named by family, not just counted. "Sixteen families have no
        # recorded mechanism" is a work list; "135 refused" is not.
        "beliefs_refused_no_expectation":
            belief_report["refused_no_expectation"],
        "beliefs_refused_no_recorded_mechanism":
            belief_report["refused_no_recorded_mechanism"],
        "unmapped_kinds": unmapped,
        "undated_observations": undated,
        "conditions_measured": state.known_conditions,
        "uncertainty": state.uncertainty,
        "rows_written": written,
    }


def read_state(runtime_root, *, as_of: str = "") -> Optional[dict]:
    """The most recent shared state at or before `as_of`. Read-only."""
    snapshots = EST.load(runtime_root, "state_snapshot", upto=as_of)
    return snapshots[-1] if snapshots else None


# --- core -> market ---------------------------------------------------------
def consume_aggregates(runtime_root, *, as_of: str) -> List[dict]:
    """Candidate indicators derived from public company evidence.

    They arrive as HYPOTHESES and this function says so in every row it
    returns: `tradable` is False, `standing` is INFERRED, and `status` is
    CANDIDATE. Nothing here opens a position, and there is deliberately no
    convenience function that turns one of these into a signal -- the path
    from candidate to anything actionable runs through `econ.promotion`,
    which requires forward validation in more than one regime.
    """
    rows = EST.load(runtime_root, "aggregate", upto=as_of)
    out = []
    for row in rows:
        if not row.get("sufficient"):
            continue
        out.append({
            "name": row.get("name"), "as_of": row.get("as_of"),
            "direction": row.get("direction"), "score": row.get("score"),
            "panel": row.get("panel"),
            "concentration": row.get("concentration"),
            "meaning": row.get("meaning"),
            "status": "CANDIDATE", "tradable": False,
            "note": ("derived from public company evidence; a candidate "
                     "macro indicator, not a signal, until forward "
                     "validated in more than one regime"),
        })
    return out
