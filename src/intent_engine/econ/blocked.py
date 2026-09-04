"""§9: blocked time-series validation, with purging and an embargo.

WHAT WALK-FORWARD ALREADY DID, AND WHAT IT MISSED
-------------------------------------------------
`forecast.walk_forward` splits chronologically, which stops the obvious leak
(tomorrow in the training set). It does not stop the subtle one: a training
row whose OUTCOME resolves after the test period begins was scored against
information that overlaps the test window. With a 360-day horizon and a
monthly origin grid, that is not an edge case -- it is roughly a year of
training rows on every fold boundary, and every one of them shares an outcome
window with the rows being tested.

Two corrections, both standard and both checkable:

    PURGE     drop training rows whose outcome resolves at or after the test
              period starts.
    EMBARGO   drop test rows within `embargo_days` of the training end, so
              the fold boundary itself is not a place where features from the
              last training row and the first test row are near-identical.

THE TEST §9 ASKS FOR
--------------------
    train_end < test_information_cutoff   for every fold

`assert_folds_clean` checks it on the folds themselves rather than on the
intention, and reports what it dropped so a fold that purges away most of its
training set is visible rather than silently weak.

NEVER RANDOM
------------
There is no shuffle in this file and no seed. A random split over a time
series puts next year in the training set; it produces excellent numbers and
they mean nothing.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_blocked.v1"

EXPANDING, ROLLING = "EXPANDING", "ROLLING"


class FoldLeak(EconError):
    """A fold's training set reached into its own test window."""


def _d(s: str) -> _dt.date:
    return _dt.date(int(s[:4]), int(s[5:7]), int(s[8:10]))


def _days(a: str, b: str) -> int:
    return (_d(b) - _d(a)).days


@dataclass(frozen=True)
class Fold:
    """One train/test block, with what it had to throw away to be clean."""

    index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train: Tuple = ()
    test: Tuple = ()
    purged: int = 0
    embargoed: int = 0

    @property
    def n_train(self) -> int:
        return len(self.train)

    @property
    def n_test(self) -> int:
        return len(self.test)

    @property
    def test_information_cutoff(self) -> str:
        """The earliest origin in the test block. Nothing before it may know
        anything that resolves at or after it."""
        return self.test_start

    def as_dict(self) -> dict:
        return {"index": self.index, "train": [self.train_start,
                                              self.train_end],
                "test": [self.test_start, self.test_end],
                "n_train": self.n_train, "n_test": self.n_test,
                "purged": self.purged, "embargoed": self.embargoed}


def _resolution(row) -> str:
    """When this row's outcome became knowable."""
    k = getattr(row, "outcome_knowable_at", "") or ""
    if k:
        return k
    h = getattr(row, "horizon_days", 0) or 0
    return (_d(row.origin) + _dt.timedelta(days=h)).isoformat()


def make_folds(rows: Sequence, *, folds: int = 5, min_train: int = 40,
               embargo_days: int = 0, mode: str = EXPANDING,
               window_days: int = 0) -> List[Fold]:
    """Blocked folds over calendar time. `rows` need `.origin`.

    Blocks are cut on DATES, not on row indices. Cutting on indices makes a
    fold boundary fall in the middle of an origin whenever several rows share
    one, which silently puts the same forecast date on both sides.
    """
    require(mode in (EXPANDING, ROLLING), f"unknown fold mode {mode!r}")
    ordered = sorted(rows, key=lambda r: (r.origin, getattr(r, "target", "")))
    if not ordered:
        return []
    origins = sorted({r.origin for r in ordered})
    if len(origins) < folds + 2:
        return []
    # Reserve the first slice for training, then cut the rest into `folds`.
    start_idx = max(1, len(origins) // (folds + 1))
    step = max(1, (len(origins) - start_idx) // folds)
    out: List[Fold] = []
    for i in range(folds):
        cut = start_idx + i * step
        if cut >= len(origins):
            break
        test_origins = origins[cut:cut + step]
        if not test_origins:
            continue
        test_start, test_end = test_origins[0], test_origins[-1]
        train_lo = (origins[0] if mode == EXPANDING else
                    max(origins[0],
                        (_d(test_start) - _dt.timedelta(days=window_days))
                        .isoformat()))
        candidates = [r for r in ordered
                      if train_lo <= r.origin < test_start]
        # PURGE: a training row whose outcome resolves at or after the test
        # window opens shares information with the test rows.
        train = [r for r in candidates if _resolution(r) < test_start]
        purged = len(candidates) - len(train)
        # EMBARGO: drop test rows too close to the training end.
        test = list(r for r in ordered if test_start <= r.origin <= test_end)
        embargoed = 0
        if embargo_days > 0 and train:
            tr_end = max(r.origin for r in train)
            keep = [r for r in test
                    if _days(tr_end, r.origin) > embargo_days]
            embargoed = len(test) - len(keep)
            test = keep
        if len(train) < min_train or not test:
            continue
        out.append(Fold(index=i,
                        train_start=min(r.origin for r in train),
                        train_end=max(r.origin for r in train),
                        test_start=min(r.origin for r in test),
                        test_end=max(r.origin for r in test),
                        train=tuple(train), test=tuple(test),
                        purged=purged, embargoed=embargoed))
    return out


def assert_folds_clean(folds: Sequence[Fold]) -> None:
    """§9's own test, run on the folds rather than assumed of them."""
    bad = []
    for f in folds:
        if f.train_end >= f.test_information_cutoff:
            bad.append(f"fold {f.index}: train_end {f.train_end} is not "
                       f"before test cutoff {f.test_information_cutoff}")
        for r in f.train:
            if _resolution(r) >= f.test_start:
                bad.append(
                    f"fold {f.index}: a training row at {r.origin} resolves "
                    f"{_resolution(r)}, at or after the test window opens "
                    f"{f.test_start}")
                break
        overlap = {r.origin for r in f.train} & {r.origin for r in f.test}
        if overlap:
            bad.append(f"fold {f.index}: {len(overlap)} origin(s) appear in "
                       "both train and test")
    if bad:
        raise FoldLeak(
            f"{len(bad)} fold problem(s):\n  " + "\n  ".join(bad[:5]))


def summarise(folds: Sequence[Fold]) -> dict:
    return {"contract": CONTRACT, "folds": len(folds),
            "total_train": sum(f.n_train for f in folds),
            "total_test": sum(f.n_test for f in folds),
            "purged": sum(f.purged for f in folds),
            "embargoed": sum(f.embargoed for f in folds),
            "detail": [f.as_dict() for f in folds]}
