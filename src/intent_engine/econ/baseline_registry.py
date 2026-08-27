"""§2: frozen comparators. A negative result is a result, and it is kept.

WHY A NEGATIVE RESULT NEEDS A REGISTRY
--------------------------------------
`GLOBAL_COLLECTIVE_HUMAN_STATE_V1` did not improve held-out prediction:
delta -0.00565, CI [-0.02127, +0.00996], n=500. The temptation from here is
obvious and it has a name -- tune V1 until the number turns positive, then
report the number. That is not a variant beating a baseline; it is the same
hypothesis tested repeatedly with the failures discarded.

So V1 is FROZEN, with its feature set, its partitions, its preregistration
hash and its code SHA. Every later variant is compared against it, and
`assert_frozen` refuses to let a recorded baseline be edited in place.

WHAT A FROZEN BASELINE IS NOT
-----------------------------
It is not a claim that the collective layer is useless. The same run found
that 9 of 10 per-family comparisons were UNDERPOWERED, and that the pooled
interval still admits a small positive effect. V1 is the statement "this
feature set, on this panel, did not clear the bar" -- which is exactly the
thing a later variant has to beat to mean anything.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_baseline_registry.v1"

REGISTRY_PATH = pathlib.Path("reports/frozen_baselines.json")

NOT_PROMOTED = "NOT_PROMOTED"
PROMOTED_GLOBAL = "PROMOTED_GLOBAL"
PROMOTED_REGIME_CONDITIONAL = "PROMOTED_REGIME_CONDITIONAL"
PROMOTED_LEAD_TIME = "PROMOTED_LEAD_TIME"
OUTCOMES = (NOT_PROMOTED, PROMOTED_GLOBAL, PROMOTED_REGIME_CONDITIONAL,
            PROMOTED_LEAD_TIME)


@dataclass(frozen=True)
class FrozenBaseline:
    """One measured result, kept so a later variant has something to beat."""

    baseline_id: str
    outcome: str
    frozen_at: str
    base_score: float
    augmented_score: float
    delta: float
    ci_low: float
    ci_high: float
    n_paired: int
    mde: Optional[float]
    #: Everything needed to reproduce it. A baseline whose inputs are not
    #: recorded cannot be a comparator, because nobody can tell whether a
    #: later variant changed the model or changed the data.
    feature_set: Tuple[str, ...]
    base_feature_set: Tuple[str, ...]
    preregistration_hash: str
    panel_hash: str
    code_sha: str
    partitions: Dict[str, int] = field(default_factory=dict)
    underpowered_families: int = 0
    families_tested: int = 0
    note: str = ""

    def __post_init__(self) -> None:
        require(self.outcome in OUTCOMES,
                f"unknown baseline outcome {self.outcome!r}")
        require(bool(self.preregistration_hash),
                f"{self.baseline_id}: a baseline with no preregistration "
                "hash cannot show that its targets predated its results")
        require(bool(self.panel_hash),
                f"{self.baseline_id}: record which panel produced it, or a "
                "later variant on more data will look like a better model")

    @property
    def admits_positive_effect(self) -> bool:
        """Does the interval still allow the layer to be useful?

        The difference between "this failed" and "this was not measured".
        """
        return self.ci_high > 0

    @property
    def rules_out_above(self) -> float:
        """The largest improvement this result is consistent with."""
        return self.ci_high

    def as_dict(self) -> dict:
        return {"baseline_id": self.baseline_id, "outcome": self.outcome,
                "frozen_at": self.frozen_at, "base_score": self.base_score,
                "augmented_score": self.augmented_score, "delta": self.delta,
                "ci": [self.ci_low, self.ci_high], "n_paired": self.n_paired,
                "mde": self.mde, "feature_set": list(self.feature_set),
                "base_feature_set": list(self.base_feature_set),
                "preregistration_hash": self.preregistration_hash,
                "panel_hash": self.panel_hash, "code_sha": self.code_sha,
                "partitions": dict(self.partitions),
                "underpowered_families": self.underpowered_families,
                "families_tested": self.families_tested,
                "admits_positive_effect": self.admits_positive_effect,
                "rules_out_improvement_above": self.rules_out_above,
                "note": self.note}

    def statement(self) -> str:
        if self.outcome == NOT_PROMOTED:
            return (f"{self.baseline_id}: delta {self.delta:+.5f} "
                    f"[{self.ci_low:+.5f}, {self.ci_high:+.5f}] on n="
                    f"{self.n_paired}. NOT PROMOTED. The interval rules out "
                    f"any improvement above {self.ci_high:+.5f}"
                    + (f"; {self.underpowered_families} of "
                       f"{self.families_tested} per-family tests were "
                       "underpowered, so most of them measured nothing "
                       "either way." if self.underpowered_families else "."))
        return (f"{self.baseline_id}: {self.outcome}, delta "
                f"{self.delta:+.5f} [{self.ci_low:+.5f}, {self.ci_high:+.5f}] "
                f"on n={self.n_paired}.")


def load(path: pathlib.Path = None) -> Dict[str, FrozenBaseline]:
    p = path or REGISTRY_PATH
    if not p.exists():
        return {}
    out = {}
    for r in json.loads(p.read_text()):
        out[r["baseline_id"]] = FrozenBaseline(
            baseline_id=r["baseline_id"], outcome=r["outcome"],
            frozen_at=r["frozen_at"], base_score=r["base_score"],
            augmented_score=r["augmented_score"], delta=r["delta"],
            ci_low=r["ci"][0], ci_high=r["ci"][1], n_paired=r["n_paired"],
            mde=r.get("mde"), feature_set=tuple(r.get("feature_set", ())),
            base_feature_set=tuple(r.get("base_feature_set", ())),
            preregistration_hash=r["preregistration_hash"],
            panel_hash=r["panel_hash"], code_sha=r.get("code_sha", ""),
            partitions=r.get("partitions", {}),
            underpowered_families=r.get("underpowered_families", 0),
            families_tested=r.get("families_tested", 0),
            note=r.get("note", ""))
    return out


def freeze(b: FrozenBaseline, *, path: pathlib.Path = None,
           allow_replace: bool = False) -> pathlib.Path:
    """Record a baseline. Refuses to overwrite one that already exists.

    The refusal is the point. Editing a frozen baseline in place is how a
    comparator quietly becomes whatever the current variant needed it to be.
    """
    p = path or REGISTRY_PATH
    existing = load(p)
    if b.baseline_id in existing and not allow_replace:
        old = existing[b.baseline_id]
        if old.as_dict() != b.as_dict():
            raise EconError(
                f"{b.baseline_id} is already frozen with delta "
                f"{old.delta:+.5f} on n={old.n_paired}, and this call would "
                f"change it to {b.delta:+.5f} on n={b.n_paired}. A comparator "
                "that can be edited is not a comparator. Register a NEW "
                "baseline id for a variant.")
        return p
    existing[b.baseline_id] = b
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([v.as_dict() for v in
                             sorted(existing.values(),
                                    key=lambda x: x.baseline_id)],
                            indent=2, sort_keys=True))
    return p


def compare_to(baseline_id: str, *, delta: float, ci_low: float,
               ci_high: float, n_paired: int,
               path: pathlib.Path = None) -> dict:
    """Did a variant actually beat the frozen comparator?

    "Better point estimate" is not beating it. The variant's interval must
    exclude the baseline's delta, or the difference is inside the noise both
    were measured with.
    """
    base = load(path).get(baseline_id)
    if base is None:
        raise EconError(f"no frozen baseline {baseline_id!r} to compare to")
    beats = ci_low > base.delta
    return {"baseline_id": baseline_id, "baseline_delta": base.delta,
            "variant_delta": delta, "variant_ci": [ci_low, ci_high],
            "improvement": round(delta - base.delta, 5),
            "beats_baseline": beats,
            "reading": (
                f"variant delta {delta:+.5f} vs frozen {base.delta:+.5f}: "
                + ("the variant's interval excludes the baseline, so this is "
                   "a real improvement" if beats else
                   "the variant's interval contains the baseline's delta, so "
                   "the difference is inside the noise both were measured "
                   "with"))}
