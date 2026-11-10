"""Leakage guards that can fail, and the canary that proves they are live.

THREE WALLS
-----------
1. EVIDENCE DATES. Every decision lists its evidence ids. Each id names a
   date (a price window's last bar, a panel cell's vintage, an economic
   state's as-of, a news item's knowable_at). `check_evidence` parses each
   one and refuses the decision if any is after the decision date. An id it
   cannot parse is refused too: an undated input cannot be walled.
2. TRUNCATION. `truncation_invariant` recomputes features from bars cut at
   the decision date. A feature that changes when the future is deleted was
   reading the future.
3. LABEL PURGE. `assert_purged` refuses a training row whose outcome was not
   known (exit after the refit date).

THE CANARY
----------
`oracle_canary` builds a decision that peeks at the exit bar and records it
honestly in its evidence. The replay passes it through the SAME checker as
every policy, and the run is refused unless the checker refused the canary.
A checker that has been disabled, or that a refactor has quietly bypassed,
lets the canary through, and the replay then fails loudly instead of
producing results from an unguarded path ([[a-guard-that-cannot-fail]]).
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Sequence

_PX = re.compile(r"^px:([^:]+):(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})$")
_PANEL = re.compile(r"^panel:([^:]+):(\d{4}-\d{2}-\d{2})@(\d{4}-\d{2}-\d{2})$")
_STATE = re.compile(r"^econ_state:(\d{4}-\d{2}-\d{2}):panel:([^:]+):"
                    r"(\d{4}-\d{2}-\d{2})$")
_REGIME = re.compile(r"^econ_regime:(\d{4}-\d{2}-\d{2})$")
_NEWS = re.compile(r"^news:(.+)@(\d{4}-\d{2}-\d{2})(T[0-9:+.Z-]*)?$")
_OUTCOME = re.compile(r"^outcome:([^:]+):(\d{4}-\d{2}-\d{2})$")
_RESOLVED = re.compile(r"^resolved_through:(\d{4}-\d{2}-\d{2})$")


class LeakDetected(RuntimeError):
    """A decision used something that did not exist when it was made."""


def evidence_date(eid: str) -> str:
    """The date at which this piece of evidence became knowable."""
    m = _STATE.match(eid)
    if m:
        # The cutoff the state was built at AND the period of the node it
        # read. Reading only the cutoff would pass a state built later than
        # it says, whose nodes describe periods after the decision.
        return max(m.group(1), m.group(3))
    for rx, group in ((_PX, 3), (_PANEL, 3), (_STATE, 1), (_REGIME, 1),
                      (_NEWS, 2), (_OUTCOME, 2), (_RESOLVED, 1)):
        m = rx.match(eid)
        if m:
            return m.group(group)
    raise LeakDetected(f"evidence id {eid!r} carries no parseable date; an "
                       "undated input cannot be walled")


def check_evidence(evidence_ids: Iterable[str], decision_date: str) -> None:
    late = []
    for eid in evidence_ids:
        d = evidence_date(eid)
        if d > decision_date:
            late.append(f"{eid} (knowable {d})")
    if late:
        raise LeakDetected(
            f"decision dated {decision_date} used {len(late)} input(s) from "
            f"after it: {late[:3]}")


def assert_purged(train_exit_dates: Sequence[str], refit_date: str) -> None:
    late = [d for d in train_exit_dates if d > refit_date]
    if late:
        raise LeakDetected(
            f"{len(late)} training row(s) resolve after the refit date "
            f"{refit_date} (latest {max(late)}); their labels were not known")


def truncation_invariant(feature_fn, bars, t: int, *args) -> bool:
    """True when the features at t do not change if the future is deleted."""
    full = feature_fn(bars, t, *args)
    cut = feature_fn(bars.truncated(bars.dates[t]), t, *args)
    return full == cut


def truncation_invariant_relative(b, t: int, spy, decision_date: str) -> bool:
    """The company-pair version: both legs cut at the decision date."""
    from intent_engine.paper_validation import features as F
    ts = spy.index_of(decision_date)
    full = F.relative_features(b, t, spy, ts)
    cut = F.relative_features(b.truncated(decision_date), t,
                              spy.truncated(decision_date), ts)
    return full == cut


def oracle_canary(symbol: str, decision_date: str, exit_date: str,
                  excess: float) -> Dict:
    """A decision that knows its own outcome, and says so in its evidence."""
    return {"policy_id": "oracle_canary", "symbol": symbol,
            "direction": "LONG" if excess > 0 else "SHORT",
            "probability": 0.99 if excess > 0 else 0.01,
            "evidence_ids": [f"outcome:{symbol}:{exit_date}"],
            "decision_date": decision_date}


def canary_refused(decision: Dict) -> bool:
    try:
        check_evidence(decision["evidence_ids"], decision["decision_date"])
    except LeakDetected:
        return True
    return False
