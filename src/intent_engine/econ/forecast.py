"""§8/§9/§10: the base model, the augmented model, and the wall between them.

WHY A MODEL LIVES IN THIS PACKAGE AT ALL
----------------------------------------
Because the comparison has to be FAIR, and fairness is a property of the
harness rather than of either model. Model A and Model B must see the same
origins, the same targets, the same training window, the same regularisation
and the same fitting procedure -- differing in exactly one thing, the feature
block. Any of those handled separately is a place the comparison quietly
becomes a comparison of two harnesses.

So there is one `fit`, one `predict`, one walk-forward loop, and the only
argument that changes is which features go in.

WHY LOGISTIC REGRESSION AND NOTHING CLEVERER
--------------------------------------------
Section 37: complexity earns promotion only with out-of-sample value. The
question being asked is whether a BLOCK OF FEATURES adds information, not
whether a fancier learner can extract more from the same data. A stronger
model would raise both scores and could easily raise the augmented one more
for reasons that have nothing to do with the collective layer -- more
parameters, more chances to fit the noise in the extra columns.

L2-regularised logistic regression, same penalty both sides, is the smallest
thing that answers the actual question. It is also auditable: the whole
fitting procedure is forty lines of arithmetic anyone can read.

WHY STDLIB
----------
`test_econ_core_is_neutral` forbids this package importing either product,
and the dependency discipline that goes with it has kept this core free of a
numerical stack. A logistic fit on a few hundred rows does not need one.

THE PARTITION WALL
------------------
Section 10 requires a LOAD-BEARING guard that holdout data cannot influence
feature selection, construct selection, threshold tuning or hyperparameters.
`Partition.assert_untouched` is that guard: the holdout rows are hashed when
the partition is created and re-hashed when the experiment finishes, and any
read of a holdout row outside `evaluate` is recorded. A guard that merely
documented the rule would be a comment.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_forecast.v1"

TRAIN, VALIDATION, HOLDOUT = "TRAIN", "VALIDATION", "HOLDOUT"
PARTITIONS = (TRAIN, VALIDATION, HOLDOUT)

#: One penalty, applied identically to both models. Not tuned -- tuning it
#: would be a hyperparameter choice, and Section 10 forbids making one with
#: the holdout in view. It is set to a conventional weak value and left.
L2 = 1.0
EPOCHS = 400
LEARNING_RATE = 0.08

#: Below this many training rows a fold is skipped rather than fitted. A
#: logistic fit on eleven rows will converge to something and it will be
#: noise wearing coefficients.
MIN_TRAIN_ROWS = 40


class PartitionViolation(EconError):
    """Holdout data influenced something it must not have."""


# =============================================================================
# ROWS
# =============================================================================

@dataclass(frozen=True)
class Row:
    """One forecast origin: features known at `origin`, outcome at horizon."""

    origin: str
    target: str
    horizon_days: int
    #: name -> value, all knowable at `origin`.
    features: Dict[str, float]
    #: True when the target rose over the horizon. Known only in hindsight,
    #: which is correct: it is the thing being predicted.
    outcome: bool
    regime: str = "ALL"
    #: When the outcome became knowable. Used by the incremental-value gate's
    #: hindsight check, which is a separate wall from this module's.
    outcome_knowable_at: str = ""

    def vector(self, names: Sequence[str]) -> List[float]:
        return [self.features.get(n, 0.0) for n in names]

    @property
    def key(self) -> str:
        return f"{self.target}@{self.origin}+{self.horizon_days}"


# =============================================================================
# PARTITION
# =============================================================================

@dataclass
class Partition:
    """Train / validation / holdout, with the holdout sealed.

    The seal is a hash of the holdout rows taken at construction. Anything
    that changes those rows -- including re-deriving them from a different
    feature set, which is the subtle version of the violation -- changes the
    hash, and `assert_untouched` refuses.
    """

    train: Tuple[Row, ...]
    validation: Tuple[Row, ...]
    holdout: Tuple[Row, ...]
    _seal: str = ""
    _holdout_reads: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "_seal", self._hash(self.holdout))

    @staticmethod
    def _hash(rows: Sequence[Row]) -> str:
        h = hashlib.sha256()
        for r in sorted(rows, key=lambda x: x.key):
            h.update(r.key.encode())
            for k in sorted(r.features):
                h.update(f"{k}={r.features[k]:.9g}".encode())
            h.update(b"1" if r.outcome else b"0")
        return h.hexdigest()

    def seal(self) -> str:
        return self._seal

    def read_holdout(self) -> Tuple[Row, ...]:
        """The ONLY sanctioned way to touch the holdout, and it is counted."""
        self._holdout_reads += 1
        return self.holdout

    @property
    def holdout_reads(self) -> int:
        return self._holdout_reads

    def assert_untouched(self, *, expected_reads: int = 1) -> None:
        """The holdout was read exactly as often as evaluation requires.

        More reads than evaluations means something looked at it -- feature
        selection, a threshold sweep, an 'exploratory' peek. Fewer means the
        evaluation did not happen and a reported holdout score is fictional.
        """
        if self._hash(self.holdout) != self._seal:
            raise PartitionViolation(
                "the holdout rows changed after the partition was sealed. "
                "Re-deriving the holdout from a different feature set is the "
                "quiet version of tuning on it.")
        if self._holdout_reads != expected_reads:
            raise PartitionViolation(
                f"the holdout was read {self._holdout_reads} time(s); "
                f"{expected_reads} evaluation(s) were declared. Every extra "
                "read is a chance for the holdout to have influenced a "
                "choice, and Section 10 does not distinguish between doing "
                "that deliberately and doing it by accident.")

    def summarise(self) -> dict:
        return {"train": len(self.train), "validation": len(self.validation),
                "holdout": len(self.holdout), "seal": self._seal[:16],
                "holdout_reads": self._holdout_reads}


def split_by_date(rows: Sequence[Row], *, train_end: str,
                  validation_end: str) -> Partition:
    """Chronological split. Never random.

    A random split over a time series puts tomorrow in the training set and
    yesterday in the test set, which is a leak that shows up as excellent
    performance.
    """
    tr = tuple(r for r in rows if r.origin < train_end)
    va = tuple(r for r in rows if train_end <= r.origin < validation_end)
    ho = tuple(r for r in rows if r.origin >= validation_end)
    return Partition(train=tr, validation=va, holdout=ho)


# =============================================================================
# THE MODEL
# =============================================================================

@dataclass(frozen=True)
class Model:
    """A fitted logistic regression, and the standardisation it was fitted on."""

    feature_names: Tuple[str, ...]
    weights: Tuple[float, ...]
    bias: float
    means: Tuple[float, ...]
    scales: Tuple[float, ...]
    n_train: int

    def predict(self, row: Row) -> float:
        x = row.vector(self.feature_names)
        z = self.bias
        for xi, m, s, w in zip(x, self.means, self.scales, self.weights):
            z += w * ((xi - m) / s)
        return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, z))))


def _standardise(rows: Sequence[Row], names: Sequence[str]):
    n = len(rows)
    means, scales = [], []
    for j, name in enumerate(names):
        col = [r.features.get(name, 0.0) for r in rows]
        m = sum(col) / n
        var = sum((c - m) ** 2 for c in col) / max(1, n - 1)
        s = math.sqrt(var) or 1.0
        means.append(m)
        scales.append(s)
    return means, scales


def fit(rows: Sequence[Row], names: Sequence[str], *, l2: float = L2,
        epochs: int = EPOCHS, lr: float = LEARNING_RATE) -> Model:
    """L2 logistic regression by gradient descent.

    Standardisation statistics come from the TRAINING rows only. Computing
    them over the full sample is a leak that is almost invisible and is worth
    a real amount of apparent skill.
    """
    require(len(rows) >= MIN_TRAIN_ROWS,
            f"{len(rows)} training rows is below the floor of "
            f"{MIN_TRAIN_ROWS}; a logistic fit on fewer will converge to "
            "noise wearing coefficients")
    require(bool(names), "a model needs at least one feature")
    names = tuple(names)
    means, scales = _standardise(rows, names)
    X = [[(r.features.get(n, 0.0) - m) / s
          for n, m, s in zip(names, means, scales)] for r in rows]
    y = [1.0 if r.outcome else 0.0 for r in rows]
    n, d = len(X), len(names)
    w = [0.0] * d
    b = 0.0
    for _ in range(epochs):
        gw = [0.0] * d
        gb = 0.0
        for xi, yi in zip(X, y):
            z = b + sum(wj * xj for wj, xj in zip(w, xi))
            p = 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, z))))
            err = p - yi
            gb += err
            for j in range(d):
                gw[j] += err * xi[j]
        b -= lr * gb / n
        for j in range(d):
            w[j] -= lr * (gw[j] / n + l2 * w[j] / n)
    return Model(feature_names=names, weights=tuple(w), bias=b,
                 means=tuple(means), scales=tuple(scales), n_train=n)


def base_rate(rows: Sequence[Row]) -> float:
    """The no-skill benchmark. Every model must beat this to mean anything."""
    if not rows:
        return 0.5
    return sum(1 for r in rows if r.outcome) / len(rows)


# =============================================================================
# WALK-FORWARD
# =============================================================================

@dataclass(frozen=True)
class FoldResult:
    fold: int
    train_end: str
    n_train: int
    n_test: int
    predictions: Tuple[Tuple[str, float, bool, str], ...]  # key, p, y, regime


def walk_forward(rows: Sequence[Row], names: Sequence[str], *,
                 folds: int = 5, min_train: int = MIN_TRAIN_ROWS
                 ) -> List[FoldResult]:
    """Expanding-window walk-forward. Each fold trains only on its own past.

    Returns per-fold predictions rather than an aggregate score, because the
    incremental-value gate needs the individual paired forecasts and an
    aggregate cannot be un-aggregated.
    """
    ordered = sorted(rows, key=lambda r: (r.origin, r.target))
    if len(ordered) < min_train + folds:
        return []
    start = max(min_train, len(ordered) // (folds + 1))
    step = max(1, (len(ordered) - start) // folds)
    out = []
    for i in range(folds):
        cut = start + i * step
        if cut >= len(ordered):
            break
        train = ordered[:cut]
        test = ordered[cut:cut + step]
        if len(train) < min_train or not test:
            continue
        model = fit(train, names)
        preds = tuple((r.key, model.predict(r), r.outcome, r.regime)
                      for r in test)
        out.append(FoldResult(fold=i, train_end=train[-1].origin,
                              n_train=len(train), n_test=len(test),
                              predictions=preds))
    return out


def brier(predictions: Sequence[Tuple[str, float, bool, str]]) -> float:
    if not predictions:
        return 0.0
    return sum((p - (1.0 if y else 0.0)) ** 2
               for _k, p, y, _r in predictions) / len(predictions)


def directional_accuracy(predictions) -> float:
    if not predictions:
        return 0.0
    return sum(1 for _k, p, y, _r in predictions
               if (p >= 0.5) == y) / len(predictions)


def summarise_predictions(predictions) -> dict:
    if not predictions:
        return {"n": 0}
    ys = [y for _k, _p, y, _r in predictions]
    tp = sum(1 for _k, p, y, _r in predictions if p >= 0.5 and y)
    fp = sum(1 for _k, p, y, _r in predictions if p >= 0.5 and not y)
    fn = sum(1 for _k, p, y, _r in predictions if p < 0.5 and y)
    return {"n": len(predictions),
            "brier": round(brier(predictions), 5),
            "directional_accuracy": round(directional_accuracy(predictions), 4),
            "base_rate": round(sum(ys) / len(ys), 4),
            "false_positives": fp, "false_negatives": fn,
            "true_positives": tp}
