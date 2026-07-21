"""Deterministic randomization and assignment (T018).

Stdlib only. The assignment of a unit to an arm is a pure function of
recorded metadata, so any historical assignment can be reproduced exactly
from the log — which is what makes an audit possible and what makes
silent re-randomization detectable.

There is deliberately no rebalancing, no reassignment, and no "fix the
skew" path. A skewed split is a fact to report, not a state to correct.
"""
from __future__ import annotations

import hashlib

from intent_engine.growth.records import GrowthError

RANDOMIZATION_METHOD = "deterministic_hash.v1"
RANDOMIZATION_UNITS = {"crm_entity", "session", "account"}

_BUCKETS = 10_000


def validate_randomization(spec: dict) -> dict:
    method = spec.get("method", RANDOMIZATION_METHOD)
    if method != RANDOMIZATION_METHOD:
        raise GrowthError(f"unsupported randomization method: {method!r} "
                          f"(this version implements {RANDOMIZATION_METHOD})")
    unit = spec.get("unit")
    if unit not in RANDOMIZATION_UNITS:
        raise GrowthError(f"unknown randomization unit: {unit!r}")
    seed = spec.get("seed")
    if not isinstance(seed, (int, str)) or seed == "":
        raise GrowthError("randomization requires an explicit recorded seed")
    hash_inputs = spec.get("hash_input_definition")
    if not hash_inputs or not isinstance(hash_inputs, list):
        raise GrowthError("randomization requires an explicit "
                          "hash_input_definition (which fields feed the hash)")
    return {"method": method, "unit": unit, "seed": seed,
            "hash_input_definition": list(hash_inputs)}


def validate_allocation(arms: list) -> dict:
    """arms: [{arm_id, is_control, allocation}]. Ratios must sum to 1."""
    if not arms:
        raise GrowthError("at least one arm is required")
    ids = [a.get("arm_id") for a in arms]
    if len(set(ids)) != len(ids) or not all(ids):
        raise GrowthError("arm ids must be present and unique")
    total = 0.0
    for arm in arms:
        ratio = arm.get("allocation")
        if not isinstance(ratio, (int, float)) or ratio <= 0:
            raise GrowthError(f"arm {arm.get('arm_id')!r} needs a positive "
                              "allocation ratio")
        total += float(ratio)
    if abs(total - 1.0) > 1e-9:
        raise GrowthError(f"allocation ratios must sum to 1.0, got {total}")
    return {a["arm_id"]: float(a["allocation"]) for a in arms}


def assign(experiment_id: str, seed, unit_id: str, allocation: dict) -> str:
    """Pure, reproducible arm assignment.

    The unit is hashed together with the experiment id and the recorded
    seed, mapped into 10,000 buckets, and allocated to arms in a stable
    (sorted) order. Same inputs always yield the same arm — forever.
    """
    if not allocation:
        raise GrowthError("allocation is empty")
    digest = hashlib.sha256(
        f"{experiment_id}|{seed}|{unit_id}".encode()).hexdigest()
    bucket = int(digest[:8], 16) % _BUCKETS
    cumulative = 0.0
    for arm_id in sorted(allocation):
        cumulative += allocation[arm_id]
        if bucket < cumulative * _BUCKETS:
            return arm_id
    return sorted(allocation)[-1]      # float-rounding tail
