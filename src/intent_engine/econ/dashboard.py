"""What /learning shows about the collective layer (Section 49).

WHY THE PAYLOAD IS BUILT HERE AND NOT IN THE WEBAPP
---------------------------------------------------
"Two definitions of novel evidence is how a dashboard starts disagreeing with
the engine it describes" -- the existing learning endpoint already says this
about itself. The same trap applies with more force here, because the
collective layer's headline numbers are exactly the ones a surface would be
tempted to recompute: how many constructs do we track, how many are promoted,
how sure are we. So the payload is computed once, in the core, from the store.

WHAT THE PAGE MUST SAY EVEN WHEN THERE IS NOTHING
--------------------------------------------------
Especially then. One construct of sixteen is measurable today, and the honest
reading of that is a research programme that has barely started -- not a blank
panel. `measurement_reality` is therefore always present, and it names the
specific reason each construct is unavailable: no proxy at all, a proxy whose
series needs a key, or a construct that was tested and retired.

THE THREE HEADLINE NUMBERS
--------------------------
    measured    a posterior exists
    usable      its uncertainty is narrow enough to support a reading
    promoted    it beat the base economic model, twice, in different regimes

They are always reported together, and they are almost never equal. A surface
that showed only the first would be describing effort as if it were result.
"""
from __future__ import annotations

from typing import Dict, List, Sequence

from . import collective as CO
from . import construct as CK
from . import proxies as PX
from . import series as SER
from . import store as ST
from .vocabulary import (
    CANDIDATE, COLLECTIVE_DIMENSIONS, OBSERVED_C, PROMOTED, REPLICATED,
    RETIRED, TESTED, WEAKENED,
)

CONTRACT = "econ_dashboard.v1"

#: What a reader should take from each promotion state, in one clause.
_MEANING = {
    CANDIDATE: "proposed; nothing has been measured for it yet",
    OBSERVED_C: "measured, but never tested against the base economic model",
    TESTED: "beat the base model once; one regime is not a replication",
    REPLICATED: "beat the base model in two regimes; awaiting promotion",
    PROMOTED: "earns its place — it may inform a decision",
    WEAKENED: "used to beat the base model and has stopped",
    RETIRED: "removed: it did not add incremental predictive value",
}


def _load_register(root, *, upto: str = "") -> List[CK.Construct]:
    by_dim: Dict[str, dict] = {}
    for r in ST.load(root, "construct", upto=upto):
        if isinstance(r, dict) and r.get("dimension"):
            by_dim[r["dimension"]] = r
    out = []
    for dim, r in sorted(by_dim.items()):
        try:
            out.append(CK.Construct(
                dimension=dim, state=r.get("state", CANDIDATE),
                proposed_by=r.get("proposed_by", ""),
                proxy=r.get("proxy", ""),
                retired_reason=r.get("retired_reason", "")))
        except Exception:                                   # noqa: BLE001
            continue
    return out


def _load_states(root, *, upto: str = "") -> Dict[str, dict]:
    """Latest estimate per population."""
    latest: Dict[str, dict] = {}
    for r in ST.load(root, "collective_state", upto=upto):
        if not isinstance(r, dict):
            continue
        key = (r.get("population") or {}).get("key")
        if not key:
            continue
        if key not in latest or str(r.get("as_of", "")) >= str(
                latest[key].get("as_of", "")):
            latest[key] = r
    return latest


def _load_comparisons(root, *, upto: str = "") -> List[dict]:
    return [r for r in ST.load(root, "comparison", upto=upto)
            if isinstance(r, dict)]


def build(root, *, as_of: str = "") -> dict:
    """The Section 49 collective-state payload.

    Never raises on a missing store: an engine that has not run yet is a
    legitimate state, and it must be distinguishable from one that ran and
    found nothing. `has_run` is that distinction.
    """
    try:
        register = _load_register(root, upto=as_of)
        states = _load_states(root, upto=as_of)
        comparisons = _load_comparisons(root, upto=as_of)
    except Exception as exc:                                # noqa: BLE001
        return {"contract": CONTRACT, "available": False,
                "reason": f"{type(exc).__name__}: {exc}"}

    reality = SER.behavioural_coverage()
    by_state: Dict[str, List[str]] = {}
    for c in register:
        by_state.setdefault(c.state, []).append(c.dimension)

    populations = []
    for key, row in sorted(states.items()):
        dims = row.get("dimensions") or {}
        readings = []
        for name, d in sorted(dims.items()):
            if d.get("posterior_mean") is None or not d.get("usable"):
                continue
            readings.append({
                "dimension": name,
                "sentence": _sentence(row, name, d),
                "moved": d.get("moved"),
                "uncertainty": d.get("uncertainty"),
                "promotion_state": d.get("promotion_state", CANDIDATE),
                "meaning": _MEANING.get(d.get("promotion_state", CANDIDATE),
                                        ""),
                "contested": d.get("contested"),
                "evidence": len(d.get("evidence") or ()),
                "contradictory": len(d.get("contradictory_evidence") or ()),
                "lag_days": (d.get("lag_model") or {}).get("typical_days"),
            })
        populations.append({
            "key": key, "as_of": row.get("as_of"),
            "population": row.get("population"),
            "coverage": row.get("coverage"),
            "readings": readings,
            # An estimate with a posterior nobody may act on is reported as
            # such rather than dropped: a blank panel and a too-uncertain
            # reading are different states.
            "measured_but_unusable": sorted(
                n for n, d in dims.items()
                if d.get("posterior_mean") is not None
                and not d.get("usable")),
        })

    promoted = sorted(by_state.get(PROMOTED, []))
    retired = sorted(by_state.get(RETIRED, []))
    return {
        "contract": CONTRACT,
        "available": True,
        "has_run": bool(states or register),
        "as_of": as_of,
        "headline": {
            "vocabulary": len(COLLECTIVE_DIMENSIONS),
            "with_a_proxy": len(PX.covered_dimensions()),
            "measurable_today": len(reality["dimensions_measurable_now"]),
            "measured": sum(len(p["readings"]) for p in populations),
            "promoted": len(promoted),
            "retired": len(retired),
        },
        "by_state": {s: sorted(v) for s, v in sorted(by_state.items())},
        "state_meanings": _MEANING,
        "promoted": promoted,
        "retired": [{"dimension": c.dimension, "reason": c.retired_reason}
                    for c in register if c.state == RETIRED],
        "populations": populations,
        "measurement_reality": reality,
        "incremental_value": _incremental(comparisons),
        # The sentence a reader should leave with, computed rather than
        # written, so it cannot drift from the numbers above it.
        "verdict": _verdict(promoted, retired, populations, reality),
    }


def _sentence(row: dict, name: str, d: dict) -> str:
    """Re-narrate through `collective.narrate`, never through an f-string."""
    try:
        pop_row = row["population"]
        pop = CO.Population(name=pop_row["name"], scale=pop_row["scale"],
                            geography=pop_row.get("geography", "US"),
                            cohort=pop_row.get("cohort", ""))
        est = CO.DimensionEstimate(
            dimension=name, posterior_mean=d["posterior_mean"],
            uncertainty=d.get("uncertainty", 0.5),
            prior_mean=d.get("prior_mean"),
            evidence=tuple(d.get("evidence") or ("stored",)),
            promotion_state=d.get("promotion_state", CANDIDATE))
        return CO.narrate(est, pop)
    except Exception:                                       # noqa: BLE001
        return ""


def _incremental(comparisons: Sequence[dict]) -> dict:
    """Section 56's headline, or an explicit statement that there isn't one."""
    tested = [c for c in comparisons
              if c.get("verdict") != "INSUFFICIENT_SAMPLE"]
    if not tested:
        return {
            "status": "NOT_YET_MEASURED",
            "base_economic_model_score": None,
            "base_plus_collective_score": None,
            "incremental_delta": None,
            "reason": (
                "no base-vs-augmented comparison has completed. The delta is "
                "the ONLY thing that may promote a psychological construct "
                "(Section 18), so until one runs, every construct here is "
                "CANDIDATE or OBSERVED by definition and none of them may "
                "inform a decision."),
        }
    base = sum(c.get("base_score", 0.0) for c in tested) / len(tested)
    aug = sum(c.get("augmented_score", 0.0) for c in tested) / len(tested)
    robust = [c for c in tested if c.get("robust")]
    return {"status": "MEASURED",
            "comparisons": len(comparisons), "tested": len(tested),
            "robust_improvements": len(robust),
            "base_economic_model_score": round(base, 5),
            "base_plus_collective_score": round(aug, 5),
            "incremental_delta": round(base - aug, 5),
            "statements": [c.get("statement", "") for c in tested][:10]}


def _verdict(promoted, retired, populations, reality) -> str:
    measured = sum(len(p["readings"]) for p in populations)
    total = len(COLLECTIVE_DIMENSIONS)
    if promoted:
        return (f"{len(promoted)} of {total} collective constructs have beaten "
                f"the base economic model out of sample and may inform a "
                f"decision: {', '.join(promoted)}."
                + (f" {len(retired)} were tested and removed." if retired
                   else ""))
    if measured:
        return (f"{measured} construct(s) are being measured and NONE has yet "
                f"been tested against the base economic model. Nothing here "
                f"may inform a decision — a posterior is not evidence that "
                f"the construct predicts anything.")
    blocked = len(reality.get("dimensions_blocked_by_data", {}))
    noproxy = len(reality.get("dimensions_with_no_proxy_at_all", []))
    return (f"Nothing is being measured yet: {noproxy} of {total} constructs "
            f"have no proxy at all and {blocked} have proxies whose series "
            f"this deployment cannot read. The layer is built and starved, "
            f"which is a data problem rather than a modelling one.")
