"""Scores, with sample sizes and intervals, computed in code.

THE UNIT OF INDEPENDENCE IS THE DECISION DATE
---------------------------------------------
Twenty-five ETFs on one date are not twenty-five observations: on a day the
market falls they mostly fall together. Every interval here resamples
DECISION DATES (a circular block bootstrap, blocks of six periods, so a
regime's autocorrelation stays inside a block), carrying the whole
cross-section of that date with it. A hit rate quoted with a Wilson interval
over forecasts would be several times too narrow, so the Wilson interval is
only used inside reliability bins, where it is labelled as per-forecast.

PAIRED DIFFERENCES USE THE SAME RESAMPLE
----------------------------------------
"Policy X beat buy-and-hold" is a statement about the difference on the
same dates, so both arms are resampled with the SAME indices. Bootstrapping
each arm separately and comparing intervals throws away the pairing and
makes every comparison look less certain than it is -- or, when one arm is
volatile, more.
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from intent_engine.paper.portfolio import max_drawdown
from intent_engine.paper_validation.protocol import PROTOCOL

_M = PROTOCOL["metrics"]
PPY = _M["periods_per_year"]
EPS = 1e-6


def brier(p: Sequence[float], y: Sequence[int]) -> Optional[float]:
    if not len(p):
        return None
    p, y = np.asarray(p, float), np.asarray(y, float)
    return float(((p - y) ** 2).mean())


def log_loss(p: Sequence[float], y: Sequence[int]) -> Optional[float]:
    if not len(p):
        return None
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    y = np.asarray(y, float)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[Optional[float],
                                                      Optional[float]]:
    if n == 0:
        return None, None
    ph = k / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return c - h, c + h


def reliability(p: Sequence[float], y: Sequence[int],
                bins: int = _M["reliability_bins"]) -> List[dict]:
    out = []
    p, y = np.asarray(p, float), np.asarray(y, int)
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        m = (p >= lo) & ((p < hi) if b < bins - 1 else (p <= hi))
        n = int(m.sum())
        if not n:
            continue
        k = int(y[m].sum())
        wl, wh = wilson(k, n)
        out.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": n,
                    "mean_p": round(float(p[m].mean()), 4),
                    "observed": round(k / n, 4),
                    "wilson_low": round(wl, 4), "wilson_high": round(wh, 4)})
    return out


def calibration_slope(p: Sequence[float], y: Sequence[int]) -> Optional[float]:
    """Slope b of y ~ sigmoid(a + b * logit(p)); 1 is ideal, < 1 overconfident.

    None when it is not estimable: every forecast states the same probability
    (a constant-probability rule has no slope to measure), or the fit does
    not converge. A diverged Newton step is reported as None, never as the
    number it diverged to -- an unstable estimate printed as -2e7 reads as a
    finding.
    """
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    if len(p) < 10 or np.std(p) < 1e-9:
        return None
    x = np.log(p / (1 - p))
    yv = np.asarray(y, float)

    def nll(a, b):
        z = np.clip(a + b * x, -40, 40)
        return float(np.sum(np.logaddexp(0, z) - yv * z))

    a, b = 0.0, 1.0
    cur = nll(a, b)
    for _ in range(100):
        z = np.clip(a + b * x, -40, 40)
        q = 1 / (1 + np.exp(-z))
        w = q * (1 - q) + 1e-12
        g = np.array([(yv - q).sum(), ((yv - q) * x).sum()])
        H = np.array([[w.sum(), (w * x).sum()],
                      [(w * x).sum(), (w * x * x).sum()]])
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            return None
        t = 1.0
        while t > 1e-6:                     # step-halving line search
            na, nb = a + t * step[0], b + t * step[1]
            new = nll(na, nb)
            if new <= cur + 1e-12:
                break
            t /= 2
        else:
            break
        a, b, cur = na, nb, new
        if np.abs(t * step).max() < 1e-9:
            return float(b) if abs(b) < 50 else None
    return None


# --- bootstrap ---------------------------------------------------------------

def block_indices(n: int, *, draws: int = _M["bootstrap_draws"],
                  block: int = _M["bootstrap_block"],
                  seed: int = _M["bootstrap_seed"]) -> np.ndarray:
    """(draws, n) circular-block resample indices over periods."""
    rng = np.random.default_rng(seed)
    nb = int(math.ceil(n / block))
    starts = rng.integers(0, n, size=(draws, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    return idx.reshape(draws, nb * block)[:, :n]


def ci(samples: np.ndarray, level: float = _M["ci"]) -> Tuple[float, float]:
    s = samples[np.isfinite(samples)]
    if not len(s):
        return (float("nan"), float("nan"))
    a = (1 - level) / 2
    return float(np.quantile(s, a)), float(np.quantile(s, 1 - a))


def sharpe(r: np.ndarray) -> float:
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    return float(r.mean() / sd * math.sqrt(PPY)) if sd > 0 else float("nan")


def _sharpe_rows(R: np.ndarray) -> np.ndarray:
    sd = R.std(axis=1, ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(sd > 0, R.mean(axis=1) / sd * math.sqrt(PPY), np.nan)


def book_stats(r: Sequence[float], idx: Optional[np.ndarray] = None) -> dict:
    """Annualised statistics of a per-period net excess return series."""
    r = np.asarray(r, float)
    n = len(r)
    if n < 2:
        return {"periods": n}
    if idx is None:
        idx = block_indices(n)
    R = r[idx]
    curve = [1.0]
    for x in r:
        curve.append(curve[-1] * (1 + x))
    sh_s = _sharpe_rows(R)
    mu_s = R.mean(axis=1) * PPY
    return {"periods": n,
            "ann_return": float(r.mean() * PPY),
            "ann_return_ci": ci(mu_s),
            "ann_vol": float(r.std(ddof=1) * math.sqrt(PPY)),
            "sharpe": sharpe(r), "sharpe_ci": ci(sh_s),
            "max_drawdown": float(max_drawdown(curve) or 0.0),
            "total_return": float(curve[-1] - 1)}


def paired_sharpe_diff(a: Sequence[float], b: Sequence[float],
                       idx: Optional[np.ndarray] = None) -> dict:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if idx is None:
        idx = block_indices(len(a))
    if np.std(b) == 0:
        # A riskless benchmark (cash) has no Sharpe. The comparison is then
        # the policy's own Sharpe against zero, stated as such.
        sa = _sharpe_rows(a[idx])
        sa = sa[np.isfinite(sa)]
        return {"diff": sharpe(a), "ci": ci(sa),
                "p_one_sided": float((sa <= 0).mean()) if len(sa) else
                float("nan"), "against": "zero (riskless benchmark)"}
    d = _sharpe_rows(a[idx]) - _sharpe_rows(b[idx])
    d = d[np.isfinite(d)]
    point = sharpe(a) - sharpe(b)
    return {"diff": point, "ci": ci(d),
            "p_one_sided": float((d <= 0).mean()) if len(d) else float("nan")}


def paired_mean_diff(a: Sequence[float], b: Sequence[float],
                     idx: Optional[np.ndarray] = None) -> dict:
    """Annualised mean-return difference on the same dates.

    The comparison to use between two LOSING books: a Sharpe difference
    there rewards volatility (a negative mean over a larger standard
    deviation is a Sharpe closer to zero), so it can rank the noisier loser
    as the better one.
    """
    a, b = np.asarray(a, float), np.asarray(b, float)
    if idx is None:
        idx = block_indices(len(a))
    d = (a - b)[idx].mean(axis=1) * PPY
    return {"ann_return_diff": float((a - b).mean() * PPY), "ci": ci(d),
            "p_one_sided": float((d <= 0).mean())}


def date_grouped_brier_skill(dates: Sequence[str], p: Sequence[float],
                             p_ref: Sequence[float], y: Sequence[int],
                             idx_fn: Callable[[int], np.ndarray] = None
                             ) -> dict:
    """Brier skill 1 - B/B_ref, resampling decision DATES with their
    cross-sections, and a one-sided p for skill <= 0."""
    dates = list(dates)
    uniq = sorted(set(dates))
    if not uniq:
        return {"n_dates": 0}
    pos = {d: i for i, d in enumerate(uniq)}
    g = np.array([pos[d] for d in dates])
    p, pr, y = (np.asarray(p, float), np.asarray(p_ref, float),
                np.asarray(y, float))
    se = (p - y) ** 2
    sr = (pr - y) ** 2
    k = len(uniq)
    se_d = np.bincount(g, weights=se, minlength=k)
    sr_d = np.bincount(g, weights=sr, minlength=k)
    n_d = np.bincount(g, minlength=k).astype(float)
    idx = (idx_fn or block_indices)(k)
    S = se_d[idx].sum(axis=1)
    Sr = sr_d[idx].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        skill_s = 1 - S / Sr
    point = 1 - se.sum() / sr.sum() if sr.sum() else float("nan")
    return {"n_dates": k, "n_forecasts": int(n_d.sum()),
            "brier": float(se.mean()), "brier_ref": float(sr.mean()),
            "skill": float(point), "skill_ci": ci(skill_s),
            "p_one_sided": float((skill_s <= 0).mean())}


def date_grouped_mean(dates: Sequence[str], x: Sequence[float]) -> dict:
    """Mean of a per-forecast quantity with a date-cluster bootstrap CI."""
    dates = list(dates)
    uniq = sorted(set(dates))
    if not uniq:
        return {"n_dates": 0, "n": 0}
    pos = {d: i for i, d in enumerate(uniq)}
    g = np.array([pos[d] for d in dates])
    x = np.asarray(x, float)
    k = len(uniq)
    s_d = np.bincount(g, weights=x, minlength=k)
    n_d = np.bincount(g, minlength=k).astype(float)
    idx = block_indices(k)
    with np.errstate(invalid="ignore", divide="ignore"):
        m_s = s_d[idx].sum(axis=1) / n_d[idx].sum(axis=1)
    return {"n_dates": k, "n": int(len(x)), "mean": float(x.mean()),
            "ci": ci(m_s), "p_le_zero": float((m_s <= 0).mean()),
            "p_ge_zero": float((m_s >= 0).mean())}


def holm(pvalues: Dict[str, float]) -> Dict[str, float]:
    items = sorted((v, k) for k, v in pvalues.items() if v == v)
    m = len(items)
    out, running = {}, 0.0
    for i, (p, k) in enumerate(items):
        adj = min(1.0, (m - i) * p)
        running = max(running, adj)
        out[k] = running
    return out
