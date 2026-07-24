"""Synthetic Worlds -> Learning Ledger bridge (Phase 2 connection).

Phase 1 (core/synthetic_worlds.py) is a reasoning DIAGNOSTIC — it changes
nothing. Phase 2, per the founder's architecture, is to let those
stress-tests *feed learning* — but the same way everything else does:
discover a weakness, PROPOSE a candidate, and stop. This bridge turns a
synthetic-world evaluation into read-only learning candidates
(source='synthetic_world'). It never modifies the frozen synthetic module,
never changes a model weight/prompt/enum, and never promotes. It is the
seam that makes Synthetic Worlds "the intelligence gym" without touching
production.

A weakness is a mechanism the engine *repeatedly fails to identify* across
the world set: for each ground-truth mechanism, count how often the worlds
that planted it were correctly identified. A low identification rate over
enough worlds is a blind spot worth a candidate.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Sequence, Tuple

from intent_engine.learning.records import SuccessCriterion

# A mechanism needs at least this many worlds before its identification
# rate is worth acting on — one miss is noise, same discipline as the
# learning ledger's MIN_SAMPLE ancestry in growth_studio.
_MIN_WORLDS = 3
# Below this identification rate, the mechanism is a blind spot.
_WEAK_RATE = 0.75


def _rows(results: Sequence[Any]) -> List[Tuple[Tuple[str, ...], bool, str]]:
    """Normalize WorldResult objects OR plain dicts to
    (ground_truth_mechanisms, identified, world_type)."""
    out = []
    for r in results:
        if isinstance(r, dict):
            gt = tuple(r.get("ground_truth", ()) or ())
            identified = bool(r.get("identified"))
            wtype = str(r.get("world_type", ""))
        else:
            gt = tuple(getattr(r, "ground_truth", ()) or ())
            identified = bool(getattr(r, "identified"))
            wtype = str(getattr(r, "world_type", ""))
        out.append((gt, identified, wtype))
    return out


def weaknesses(results: Sequence[Any]) -> List[Dict[str, Any]]:
    """Pure, read-only: per-mechanism identification rate over the worlds
    that planted it, filtered to the blind spots. Returns an auditable list
    (no side effects) — the report half of Phase 2."""
    seen: Dict[str, int] = defaultdict(int)
    hit: Dict[str, int] = defaultdict(int)
    for gt, identified, wtype in _rows(results):
        if wtype == "control":
            continue   # control worlds plant nothing to identify
        for mech in gt:
            seen[mech] += 1
            if identified:
                hit[mech] += 1
    out = []
    for mech, n in seen.items():
        if n < _MIN_WORLDS:
            continue
        rate = hit[mech] / n
        if rate <= _WEAK_RATE:
            out.append({"mechanism": mech, "worlds": n,
                        "identification_rate": rate, "hits": hit[mech]})
    return sorted(out, key=lambda w: w["identification_rate"])


def candidates_from_synthetic_eval(results: Sequence[Any], learning_ledger,
                                   *, eval_id: str = "synthetic_eval") -> List[str]:
    """Propose a learning candidate for each blind spot the eval revealed.
    Read-only w.r.t. production. Idempotent per (eval, mechanism) via a
    guard against still-open candidates for the same mechanism. Returns the
    proposed candidate ids."""
    open_mechs = {
        c.provenance.get("mechanism")
        for c in learning_ledger.list(source="synthetic_world")
        if c.status in ("proposed", "evaluated")}

    proposed: List[str] = []
    for w in weaknesses(results):
        mech = w["mechanism"]
        if mech in open_mechs:
            continue
        candidate = learning_ledger.propose(
            source="synthetic_world", target=f"mechanism:{mech}",
            statement=(f"The engine fails to identify mechanism {mech!r} in "
                       f"synthetic stress-tests ({w['identification_rate']:.0%} "
                       f"identification over {w['worlds']} worlds)"),
            hypothesis=("the trigger-condition mapping or extraction for this "
                        "mechanism is a reasoning blind spot"),
            baseline_ref="mechanism_library.current",
            success_criteria=[SuccessCriterion(
                metric="identification_rate", comparator=">=", threshold=0.8,
                direction="higher_better")],
            param_diff={"mechanism": mech, "review": "trigger_conditions"},
            provenance={"mechanism": mech, "eval_id": eval_id,
                        "worlds": w["worlds"],
                        "identification_rate": w["identification_rate"]},
            idempotency_key=f"synthetic:{eval_id}:{mech}")
        proposed.append(candidate.id)
    return proposed
