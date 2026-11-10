"""The ablation model: `econ.forecast`'s logistic, vectorised, per family.

WHY NOT CALL `econ.forecast.fit` DIRECTLY
-----------------------------------------
It is pure-Python gradient descent, ~75M multiply-adds per fit at this
panel's size, and the walk-forward makes ~300 fits. That is hours, and a
replay that takes hours is a replay that gets run once and believed. So this
is the SAME algorithm -- training-only standardisation, the same L2 penalty
scaled by n, the same 400 epochs at the same learning rate, full-batch -- in
numpy, and it returns an `econ.forecast.Model`, so prediction goes through
the existing contract. `tests/paper_validation` pins the two fitters to the
same weights on a fixture: if either drifts, the parity test fails.

PER FAMILY, NOT POOLED
----------------------
One logistic across Treasuries and equities has one macro coefficient for
both, which can express "credit widening is bad for everything" and cannot
express "bad for equities, good for Treasuries". That is the
misspecification [[misspecified-not-overfitted]] measured. Families are
fitted separately.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

import numpy as np

from intent_engine.econ import forecast as FC


def fit(X: np.ndarray, y: np.ndarray, names: Sequence[str], *,
        l2: float = FC.L2, epochs: int = FC.EPOCHS,
        lr: float = FC.LEARNING_RATE) -> FC.Model:
    n, d = X.shape
    if n < FC.MIN_TRAIN_ROWS:
        raise ValueError(f"{n} training rows < {FC.MIN_TRAIN_ROWS}")
    means = X.mean(axis=0)
    var = ((X - means) ** 2).sum(axis=0) / max(1, n - 1)
    scales = np.sqrt(var)
    scales[scales == 0] = 1.0
    Z = (X - means) / scales
    w = np.zeros(d)
    b = 0.0
    # numpy 2 on macOS Accelerate sets spurious floating-point flags inside
    # matmul (measured: `X.T @ ones`, which divides by nothing, raises
    # "divide by zero" under errstate(raise)). The flags are silenced and the
    # RESULT is checked instead, so a real numerical failure still stops here.
    with np.errstate(all="ignore"):
        for _ in range(epochs):
            z = np.clip(b + Z @ w, -40.0, 40.0)
            p = 1.0 / (1.0 + np.exp(-z))
            err = p - y
            gb = err.sum()
            gw = Z.T @ err
            b -= lr * gb / n
            w -= lr * (gw / n + l2 * w / n)
    if not (np.isfinite(w).all() and np.isfinite(b)):
        raise FloatingPointError("logistic fit diverged to a non-finite weight")
    return FC.Model(feature_names=tuple(names), weights=tuple(float(v) for v in w),
                    bias=float(b), means=tuple(float(v) for v in means),
                    scales=tuple(float(v) for v in scales), n_train=n)


def predict(model: FC.Model, X: np.ndarray) -> np.ndarray:
    w = np.array(model.weights)
    m = np.array(model.means)
    s = np.array(model.scales)
    with np.errstate(all="ignore"):
        z = np.clip(model.bias + ((X - m) / s) @ w, -40.0, 40.0)
        p = 1.0 / (1.0 + np.exp(-z))
    if not np.isfinite(p).all():
        raise FloatingPointError("non-finite prediction")
    return p


def matrix(rows: Sequence[dict], names: Sequence[str]) -> np.ndarray:
    return np.array([[float(r.get(n, 0.0)) for n in names] for r in rows],
                    dtype=float)


def l2_sweep(X: np.ndarray, y: np.ndarray, names: Sequence[str],
             Xo: np.ndarray, yo: np.ndarray,
             penalties: Sequence[float] = (0.1, 1.0, 10.0, 100.0, 1000.0)
             ) -> List[Tuple[float, float, float]]:
    """(l2, in-sample Brier, out-of-sample Brier). A flat in-sample curve
    across three orders of magnitude means nothing to fit, not overfitting."""
    out = []
    for l2 in penalties:
        m = fit(X, y, names, l2=l2)
        pin = predict(m, X)
        pout = predict(m, Xo)
        out.append((l2, float(((pin - y) ** 2).mean()),
                    float(((pout - yo) ** 2).mean())))
    return out
