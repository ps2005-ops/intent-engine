"""§10: the ladder a model must climb before its extras get any credit.

WHY THIS EXISTS
---------------
The first run of this experiment compared a base economic model against
base-plus-collective and found the collective block did not help. What it did
NOT check first was whether the base model beat a CONSTANT. In ten families
out of ten it did not. "Sophisticated model A beats broken model B" is not a
finding about the world, and neither is "sophisticated model A LOSES to
broken model B by less than model C does".

So there is a ladder, and the augmented model is only scored once the base
model has climbed it:

    BASE_RATE      always predict the training base rate. No skill at all.
    PERSISTENCE    predict the target keeps doing what it just did.
    AR             the target's own recent history, and nothing else.
    MACRO          the conventional economic block. This is "the base model".
    REGIME_MACRO   the economic block plus contemporaneously-classified
                   regime indicators.

WHY PERSISTENCE IS COMPUTED FROM THE PANEL AND NOT FROM THE PREVIOUS ROW
------------------------------------------------------------------------
The previous implementation used the PREVIOUS ROW'S OUTCOME as the
persistence prediction. Rows are ordered by (origin, target), so the previous
row is a different target at the same origin -- the "persistence" baseline
was predicting housing from industrial production. It has to come from the
target's own last observed move, which is a feature of the row.

WHY REGIME_MACRO IS HERE
------------------------
Because the regime-conditional hypothesis (H4) claims the collective block
helps MORE in stress. If simply TELLING the model which regime it is in
captures that, the collective block has to beat that, not beat a model that
does not know.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import forecast as FC
from .vocabulary import EconError, require

CONTRACT = "econ_baselines.v1"

BASE_RATE = "BASE_RATE"
PERSISTENCE = "PERSISTENCE"
AR = "AR"
MACRO = "MACRO"
REGIME_MACRO = "REGIME_MACRO"
LADDER = (BASE_RATE, PERSISTENCE, AR, MACRO, REGIME_MACRO)

#: The row feature persistence reads. Set by the row builder from the
#: target's own history as known at the origin: +1 rose, -1 fell, 0 flat.
PERSISTENCE_FEATURE = "self_last_move"


@dataclass(frozen=True)
class BaselineScore:
    name: str
    brier: float
    n: int
    directional_accuracy: float
    features: int = 0
    note: str = ""

    def as_dict(self) -> dict:
        return {"name": self.name, "brier": round(self.brier, 5), "n": self.n,
                "directional_accuracy": round(self.directional_accuracy, 4),
                "features": self.features, "note": self.note}


def _brier(preds: Sequence[Tuple[float, bool]]) -> float:
    if not preds:
        return 0.0
    return sum((p - (1.0 if y else 0.0)) ** 2 for p, y in preds) / len(preds)


def _acc(preds: Sequence[Tuple[float, bool]]) -> float:
    if not preds:
        return 0.0
    return sum(1 for p, y in preds if (p >= 0.5) == y) / len(preds)


def _names(rows, prefixes) -> List[str]:
    seen = set()
    for r in rows:
        seen |= set(r.features)
    return sorted(n for n in seen
                  if any(n.startswith(p + "_") for p in prefixes))


def _fit_predict(folds, prefixes) -> List[Tuple[str, float, bool]]:
    """Fit one feature subset across blocked folds, return test predictions."""
    out = []
    for f in folds:
        names = _names(f.train, prefixes)
        if not names or len(f.train) < FC.MIN_TRAIN_ROWS:
            continue
        model = FC.fit(f.train, names)
        for r in f.test:
            out.append((r.key, model.predict(r), r.outcome))
    return out


def _persistence_predict(folds) -> List[Tuple[str, float, bool]]:
    """Predict the target repeats its own last observed move.

    Deliberately CONFIDENT (0.75 / 0.25) rather than 1/0: a persistence rule
    that is certain scores catastrophically on any turning point, and a
    baseline that is easy to beat because it was set up to fail is not a
    baseline. The probability is fixed, not fitted.
    """
    out = []
    for f in folds:
        for r in f.test:
            mv = r.features.get(PERSISTENCE_FEATURE, 0.0)
            p = 0.75 if mv > 0 else (0.25 if mv < 0 else 0.5)
            out.append((r.key, p, r.outcome))
    return out


def _base_rate_predict(folds) -> List[Tuple[str, float, bool]]:
    out = []
    for f in folds:
        if not f.train:
            continue
        p = FC.base_rate(f.train)
        for r in f.test:
            out.append((r.key, p, r.outcome))
    return out


def score_ladder(folds, *, macro_prefixes: Sequence[str],
                 ar_prefixes: Sequence[str],
                 regime_prefixes: Sequence[str] = ()) -> Dict[str, BaselineScore]:
    """Every rung, on the SAME folds and the same test rows."""
    got: Dict[str, List[Tuple[str, float, bool]]] = {
        BASE_RATE: _base_rate_predict(folds),
        PERSISTENCE: _persistence_predict(folds),
        AR: _fit_predict(folds, ar_prefixes),
        MACRO: _fit_predict(folds, macro_prefixes),
    }
    if regime_prefixes:
        got[REGIME_MACRO] = _fit_predict(
            folds, tuple(macro_prefixes) + tuple(regime_prefixes))
    # Score every rung on the INTERSECTION of test keys, so a rung that
    # skipped a fold is not flattered by having been scored on fewer rows.
    keysets = [set(k for k, _p, _y in v) for v in got.values() if v]
    shared = set.intersection(*keysets) if keysets else set()
    out: Dict[str, BaselineScore] = {}
    for name, preds in got.items():
        sel = [(p, y) for k, p, y in preds if k in shared]
        out[name] = BaselineScore(
            name=name, brier=_brier(sel), n=len(sel),
            directional_accuracy=_acc(sel),
            features=(len(_names([r for f in folds for r in f.train],
                                 macro_prefixes))
                      if name == MACRO else 0))
    return out


@dataclass(frozen=True)
class LadderVerdict:
    """Did the base model earn the right to have extras scored against it?"""

    passed: bool
    reason: str
    scores: Dict[str, float]
    beaten: Tuple[str, ...] = ()
    lost_to: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"passed": self.passed, "reason": self.reason,
                "scores": {k: round(v, 5) for k, v in self.scores.items()},
                "beaten": list(self.beaten), "lost_to": list(self.lost_to)}


def gate(scores: Dict[str, BaselineScore]) -> LadderVerdict:
    """MACRO must beat every trivial rung below it. §10, mechanically.

    A FAILED gate is not a reason to score the augmented model anyway with a
    caveat. It means the comparison being run measures which of two
    inadequate models is less inadequate, and the correct next action is to
    fix the base model.
    """
    macro = scores.get(MACRO)
    if macro is None or macro.n == 0:
        return LadderVerdict(False, "the macro baseline produced no "
                                    "predictions", {})
    trivial = [n for n in (BASE_RATE, PERSISTENCE, AR)
               if n in scores and scores[n].n > 0]
    beaten = tuple(n for n in trivial if macro.brier < scores[n].brier)
    lost = tuple(n for n in trivial if macro.brier >= scores[n].brier)
    vals = {k: v.brier for k, v in scores.items()}
    if lost:
        return LadderVerdict(
            False,
            (f"the macro baseline (Brier {macro.brier:.5f}) does not beat "
             f"{', '.join(lost)}. Section 10: fix the baseline, do not score "
             "the augmentation. A delta measured between two models that "
             "both lose to a constant is not evidence about the feature "
             "block."),
            vals, beaten, lost)
    return LadderVerdict(
        True,
        (f"the macro baseline (Brier {macro.brier:.5f}) beats every trivial "
         f"rung ({', '.join(beaten)}), so a delta measured against it means "
         "something"),
        vals, beaten, lost)
