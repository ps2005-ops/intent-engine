"""Failure taxonomy and bounded retry.

WHY CLASSIFY AT ALL
-------------------
An unattended system's failures are only useful if a human can tell, without
reading a stack trace, whether the answer is "wait" or "act". A news feed that
timed out and an evidence row dated after the decision that used it are both
"an exception" and they are nothing alike: the first resolves itself, the
second means a guarantee is broken and every measurement taken since is
suspect.

THE RULE ABOUT RETRIES
----------------------
Retry only what is plausibly transient. A deterministic failure retried three
times is the same failure three times, and the retries do real harm: they turn
one clear failure record into a burst that looks like instability, and they
delay the report that says what is actually wrong.

INTEGRITY VIOLATIONS ARE NEVER RETRIED
--------------------------------------
A lookahead detection, a future-dated observation, a funnel stage exceeding its
predecessor -- these are not flaky. Retrying one would be asking reality to
give a different answer, and the only outcome is that a broken run eventually
"succeeds". They fail immediately and loudly.

WHAT MUST NOT HAPPEN
--------------------
A failure must never be converted into zero observations. Zero is a
measurement; a failure is the absence of one. `evidence: 0` on a day the feed
was down would be recorded as a real reading of the world and would drag every
rolling mean down with it. That is why every step records its own status and
why PARTIAL exists as a cycle outcome.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, Optional, Tuple, Type

TRANSIENT_SOURCE_FAILURE = "TRANSIENT_SOURCE_FAILURE"
PERMANENT_SOURCE_FAILURE = "PERMANENT_SOURCE_FAILURE"
STALE_MARKET_DATA = "STALE_MARKET_DATA"
INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
INTEGRITY_VIOLATION = "INTEGRITY_VIOLATION"
LOCK_CONFLICT = "LOCK_CONFLICT"
STORAGE_FAILURE = "STORAGE_FAILURE"
CONFIGURATION_FAILURE = "CONFIGURATION_FAILURE"
TEST_FAILURE = "TEST_FAILURE"
PARTIAL_CYCLE = "PARTIAL_CYCLE"
UNEXPECTED_EXCEPTION = "UNEXPECTED_EXCEPTION"

# Only these are retried. The set is small on purpose -- every addition is a
# claim that a failure mode is genuinely non-deterministic, and that claim
# should be hard to make casually.
RETRYABLE = frozenset({TRANSIENT_SOURCE_FAILURE})


class IntegrityViolation(RuntimeError):
    """A guarantee this system exists to hold has been broken.

    Raised for lookahead, future-dated evidence, or a funnel stage exceeding
    its predecessor. Never retried, never downgraded to a warning.
    """


def classify(exc: BaseException) -> str:
    """Map an exception to a failure code.

    Checked most-specific first. Anything unrecognised is UNEXPECTED_EXCEPTION
    rather than being guessed into a friendlier bucket -- an unknown failure
    that gets filed as transient would be retried, and that is precisely the
    wrong default for something nobody has diagnosed.
    """
    from intent_engine.market.trading_mode import TradingModeError
    from intent_engine.runtime.locks import JobLockedError

    if isinstance(exc, IntegrityViolation):
        return INTEGRITY_VIOLATION
    if isinstance(exc, JobLockedError):
        return LOCK_CONFLICT
    if isinstance(exc, TradingModeError):
        return CONFIGURATION_FAILURE
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return TRANSIENT_SOURCE_FAILURE
    if isinstance(exc, (PermissionError, IsADirectoryError, NotADirectoryError)):
        return STORAGE_FAILURE
    if isinstance(exc, OSError):
        # An OSError from a socket is a source problem; from a path, storage.
        # errno is not reliable enough to split them, so the message is used
        # only as a hint and the safe (non-retryable) bucket wins ties.
        text = str(exc).lower()
        if any(w in text for w in ("urlopen", "resolve", "connection",
                                   "timed out", "temporary failure")):
            return TRANSIENT_SOURCE_FAILURE
        return STORAGE_FAILURE
    name = type(exc).__name__
    if name in ("URLError", "HTTPError", "IndustryUnavailable"):
        return TRANSIENT_SOURCE_FAILURE
    if name == "PriceUnavailable":
        return STALE_MARKET_DATA
    if isinstance(exc, ValueError) and "isoformat" in str(exc):
        return INVALID_TIMESTAMP
    return UNEXPECTED_EXCEPTION


def is_retryable(code: str) -> bool:
    return code in RETRYABLE


@dataclass(frozen=True)
class Attempt:
    attempts: int
    code: Optional[str]
    error: Optional[str]

    @property
    def ok(self) -> bool:
        return self.code is None


def retry(work: Callable[[], dict], *, attempts: int = 3,
          base_delay: float = 1.0, max_delay: float = 30.0,
          sleep: Callable[[float], None] = time.sleep,
          rng: Optional[Callable[[], float]] = None
          ) -> Tuple[Optional[dict], Attempt]:
    """Run `work`, retrying only plausibly-transient failures.

    Exponential backoff with full jitter. Jitter matters even for a single
    host: without it, a cycle that retries three feeds on the same schedule
    hits a rate-limited source in a synchronised burst, and the retry becomes
    the cause of the next failure.

    `sleep` and `rng` are injected so the tests exercise the real backoff
    arithmetic without spending real seconds on it.
    """
    rng = rng or random.random
    last_code: Optional[str] = None
    last_error: Optional[str] = None
    for attempt in range(1, max(attempts, 1) + 1):
        try:
            return work(), Attempt(attempt, None, None)
        except BaseException as exc:  # noqa: BLE001 - classify, then decide
            last_code = classify(exc)
            last_error = f"{type(exc).__name__}: {exc}"
            if not is_retryable(last_code) or attempt >= attempts:
                return None, Attempt(attempt, last_code, last_error)
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            sleep(delay * rng())
    # unreachable: the loop always returns
    return None, Attempt(attempts, last_code, last_error)  # pragma: no cover
