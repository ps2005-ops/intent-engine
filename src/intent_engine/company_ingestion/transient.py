"""Bounded, host-aware retry for TRANSIENT retrieval failures.

WHY THIS EXISTS. `safe_fetch` already classified a 429 as ``retryable=True``
and then returned it, so the only retry the product ever performed was asking
the customer to try again. Measured across the Batch-A programme: Walmart and
NVIDIA both dead-ended on repeated SEC 429s, and the surface told a Chief
Strategy Officer "no approved source could be retrieved" — a sentence about
the company, produced by a fact about our request rate.

THE RULES THIS ENCODES.

1. TRANSIENT ONLY. A 429 or a 503 means "not now". A 403, a 404, an SSRF
   refusal, a policy refusal, or a truncated index means "not this, ever" —
   and re-asking is both useless and rude. The two sets are explicit and
   disjoint here rather than inferred at each call site.

2. HOST-SCOPED. A 429 from sec.gov must not pause retrieval from the
   company's own website. Attempts, backoff and the total retry budget are
   accounted PER HOST, so exhausting SEC's budget leaves every other host
   with a full one.

3. BOUNDED IN BOTH DIMENSIONS. Attempts are capped per call and total sleep
   is capped per host per run. Without the second cap a run of many SEC
   documents multiplies a small per-call bound into minutes of wall clock,
   which the progress surface has no way to explain.

4. FAIR ACCESS IS PRESERVED, NOT WORKED AROUND. Retry never widens the
   request rate: it waits longer after being told to wait. The identifying
   User-Agent, the SSRF wall and the existing per-run host circuit breaker
   are all upstream of this module and unchanged.

5. DETERMINISTIC UNDER TEST. The sleeper and the jitter source are injected.
   Production adds a small jitter so concurrent runs do not re-converge on
   the same instant; the suite injects a zero jitter and a recording sleeper
   and asserts exact delays.
"""
from __future__ import annotations

import random
import time
import urllib.error
from dataclasses import dataclass, field
from urllib.parse import urlparse

#: "Not now." Asking again, later, is the correct response.
RETRYABLE_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})

#: Transport-level failures that are a property of the moment, not the target.
#:
#: EMPTY IN THE DEFAULT POLICY, AND THE REASON IS MEASURED. A host that
#: answers 429 has told us when to come back; a host that never answers has
#: told us nothing, and each attempt costs the full connect timeout. The run
#: already has the right instrument for silence — a per-run host circuit
#: breaker that stops dialling after two failures ACROSS candidates, built
#: because ten silent URLs once cost ten eight-second dials in one pass.
#: Retrying inside each candidate multiplies exactly that: two dials became
#: six, and the breaker could not see it because it counts candidates, not
#: attempts. So silence is left to the breaker, and retry is spent on hosts
#: that answered.
#:
#: The mechanism is kept and tested — a caller that owns its own pacing can
#: enable it by policy — but nothing on the ingestion path does.
RETRYABLE_TRANSPORT_FAILURES = frozenset()

#: The transport failures a policy MAY choose to retry, for a caller that is
#: not behind a host circuit breaker.
TRANSIENT_TRANSPORT_FAILURES = frozenset({"timeout", "connection"})

#: "Not this." Listed explicitly rather than left as "everything else",
#: because the difference is the whole point of the module and a reader
#: should be able to see the refusal set without deriving it.
NEVER_RETRY_HTTP_STATUSES = frozenset({400, 401, 402, 403, 404, 405, 406,
                                       409, 410, 414, 415, 451})


@dataclass(frozen=True)
class RetryPolicy:
    """The single canonical retry contract. One object, one place to read."""

    max_attempts: int = 3                 # the first try plus 2 retries
    base_backoff_s: float = 1.0
    max_backoff_s: float = 8.0
    total_retry_budget_s: float = 20.0    # PER HOST, per run
    #: PER RUN, across every host. A per-host budget alone still stacks: a
    #: run touching four throttled hosts would spend four times the bound
    #: before showing a failure page that was always coming, and the
    #: progress surface has no way to explain the wait. The run ceiling is
    #: what a customer actually experiences.
    run_retry_budget_s: float = 45.0
    jitter: float = 0.25                  # fraction of the delay, additive
    retryable_http_statuses: frozenset = field(
        default=RETRYABLE_HTTP_STATUSES)
    retryable_transport_failures: frozenset = field(
        default=RETRYABLE_TRANSPORT_FAILURES)


#: Production default. Import this rather than constructing a policy inline,
#: so there is exactly one answer to "how hard does this product retry?".
DEFAULT_POLICY = RetryPolicy()

#: Test default: same shape, no jitter, so delays are exactly predictable.
DETERMINISTIC_POLICY = RetryPolicy(jitter=0.0)

#: For a caller that owns its own pacing and has no host circuit breaker
#: behind it. Not used on the ingestion path — see
#: RETRYABLE_TRANSPORT_FAILURES.
TRANSPORT_RETRY_POLICY = RetryPolicy(
    jitter=0.0, retryable_transport_failures=TRANSIENT_TRANSPORT_FAILURES)


def classify_failure(exc, policy: RetryPolicy = DEFAULT_POLICY):
    """(failure_kind, transient) for an exception raised by a transport.

    A 3xx carrying a Location is CONTROL FLOW, not a failure: `safe_fetch`
    walks redirects by catching exactly that. Retrying it would re-request
    the hop we were about to follow anyway, so it is never transient here.
    """
    if isinstance(exc, urllib.error.HTTPError):
        code = getattr(exc, "code", 0)
        location = None
        try:
            location = exc.headers.get("Location") if exc.headers else None
        except Exception:                                   # noqa: BLE001
            location = None
        if code in (301, 302, 303, 307, 308) and location:
            return "redirect", False
        if code in policy.retryable_http_statuses:
            return "http_status", True
        return "http_status", False
    if isinstance(exc, TimeoutError):
        return "timeout", "timeout" in policy.retryable_transport_failures
    if isinstance(exc, (urllib.error.URLError, OSError)):
        kind = "timeout" if "timed out" in str(exc).lower() else "connection"
        return kind, kind in policy.retryable_transport_failures
    # Anything else — an SSRF refusal, a truncated index, a policy refusal,
    # a programming error — is NOT a moment-in-time failure. Retrying it
    # would repeat a decision, and repeating a decision changes nothing.
    return type(exc).__name__, False


def backoff_delay(attempt: int, policy: RetryPolicy = DEFAULT_POLICY,
                  rng=None) -> float:
    """Exponential backoff for the wait AFTER ``attempt`` failed (1-based)."""
    base = policy.base_backoff_s * (2 ** max(0, attempt - 1))
    delay = min(base, policy.max_backoff_s)
    if policy.jitter:
        draw = (rng or random.random)()
        delay = delay * (1.0 + policy.jitter * draw)
    return delay


class RetryLedger:
    """Per-host retry accounting and telemetry for ONE run.

    A ledger is deliberately explicit rather than a module global: two runs
    in one process must not share a budget, and the diagnostics surface has
    to be able to say which host consumed it.
    """

    def __init__(self, policy: RetryPolicy = DEFAULT_POLICY):
        self.policy = policy
        self._spent: dict = {}        # host -> seconds slept
        self._attempts: dict = {}     # host -> total attempts made
        self._retries: dict = {}      # host -> retries actually performed
        self._exhausted: set = set()  # hosts whose budget ran out
        self.events: list = []        # one record per completed operation
        # ONE LEDGER, NOW SEVERAL THREADS.
        #
        # This class was written for a strictly sequential fetch loop, and
        # every counter here is a read-modify-write:
        #
        #     self._spent[key] = self._spent.get(key, 0.0) + seconds
        #
        # Concurrent retrieval (`service._prefetch`) hands ONE ledger to up to
        # six workers, so two threads charging the same host interleave
        # between the read and the write and one of the charges is lost. The
        # consequence is not a wrong number on a dashboard: `remaining()` is
        # what decides `mark_exhausted`, so an under-counted budget keeps
        # dialling a host that should have been dropped, and an over-counted
        # one retires a host that was answering.
        #
        # Reentrant because `record` reads `remaining` while holding it.
        import threading
        self._lock = threading.RLock()

    # --- budget ---------------------------------------------------------
    def spent(self, host: str) -> float:
        with self._lock:
            return self._spent.get(host or "", 0.0)

    def spent_total(self) -> float:
        with self._lock:
            return sum(self._spent.values())

    def remaining(self, host: str) -> float:
        """The smaller of what this host has left and what the RUN has left.

        Two ceilings, and the tighter one wins. Without the run ceiling a
        per-host budget multiplies by the number of hosts a run touches.
        """
        return max(0.0, min(
            self.policy.total_retry_budget_s - self.spent(host),
            self.policy.run_retry_budget_s - self.spent_total()))

    def charge(self, host: str, seconds: float) -> None:
        key = host or ""
        with self._lock:
            self._spent[key] = self._spent.get(key, 0.0) + seconds
            self._retries[key] = self._retries.get(key, 0) + 1

    def mark_exhausted(self, host: str) -> None:
        with self._lock:
            self._exhausted.add(host or "")

    def exhausted(self, host: str) -> bool:
        with self._lock:
            return (host or "") in self._exhausted

    # --- telemetry ------------------------------------------------------
    def record(self, *, host, url, attempt_count, final_status,
               retry_exhausted, elapsed_retry_time) -> None:
        key = host or ""
        with self._lock:
            self._attempts[key] = self._attempts.get(key, 0) + attempt_count
            self.events.append({
                "host": key,
                "url": url,
                "attempt_count": attempt_count,
                "final_status": final_status,
                "retry_exhausted": bool(retry_exhausted),
                "elapsed_retry_time": round(float(elapsed_retry_time), 3),
            })

    def snapshot(self) -> dict:
        """What diagnostics reads. Never shown to a customer: a Chief
        Strategy Officer must not have to understand the phrase '429'."""
        # A CONSISTENT PICTURE, not eight independent reads. Without the
        # lock this could report a host in `attempts_by_host` that is absent
        # from `retry_seconds_by_host` because a worker wrote between them.
        with self._lock:
            return self._snapshot()

    def _snapshot(self) -> dict:
        return {
            "hosts": sorted(set(self._spent) | set(self._attempts)),
            "attempts_by_host": dict(self._attempts),
            "retries_by_host": dict(self._retries),
            "retry_seconds_by_host": {h: round(s, 3)
                                      for h, s in self._spent.items()},
            "exhausted_hosts": sorted(self._exhausted),
            "total_retries": sum(self._retries.values()),
            "total_retry_seconds": round(self.spent_total(), 3),
            "run_retry_budget_s": self.policy.run_retry_budget_s,
            "run_budget_exhausted":
                self.spent_total() >= self.policy.run_retry_budget_s,
            "events": list(self.events),
        }


def call_with_retry(operation, *, url="", host=None,
                    policy: RetryPolicy = DEFAULT_POLICY,
                    ledger: RetryLedger = None, sleeper=None, rng=None,
                    clock=None):
    """Call ``operation()``, retrying only transient failures.

    Re-raises the LAST exception when the failure is permanent, when the
    attempt cap is reached, or when this host's retry budget cannot fund
    the next wait. The caller's existing error handling is therefore
    unchanged — this narrows the set of failures that reach it, and never
    widens it.
    """
    sleep = sleeper if sleeper is not None else time.sleep
    now = clock if clock is not None else time.monotonic
    if host is None:
        host = urlparse(url).hostname or ""
    ledger = ledger if ledger is not None else RetryLedger(policy)
    slept = 0.0
    attempt = 0
    while True:
        attempt += 1
        try:
            value = operation()
        except Exception as exc:                            # noqa: BLE001
            kind, transient = classify_failure(exc, policy)
            status = getattr(exc, "code", None) or kind
            budget_left = ledger.remaining(host)
            if not transient or attempt >= policy.max_attempts:
                ledger.record(host=host, url=url, attempt_count=attempt,
                              final_status=status,
                              retry_exhausted=transient,
                              elapsed_retry_time=slept)
                if transient:
                    ledger.mark_exhausted(host)
                raise
            delay = backoff_delay(attempt, policy, rng)
            if delay > budget_left:
                # The budget is a promise about wall clock, so a wait that
                # would break it is not taken at all. Truncating it to the
                # remainder would be a shorter wait after being asked to
                # wait longer, which is the opposite of fair access.
                ledger.mark_exhausted(host)
                ledger.record(host=host, url=url, attempt_count=attempt,
                              final_status=status, retry_exhausted=True,
                              elapsed_retry_time=slept)
                raise
            started = now()
            sleep(delay)
            # Charge the delay we committed to. Wall clock is used when the
            # sleeper is real; an injected sleeper reports zero elapsed and
            # would otherwise buy an unbounded number of free retries.
            actual = max(delay, now() - started)
            slept += actual
            ledger.charge(host, actual)
            continue
        ledger.record(host=host, url=url, attempt_count=attempt,
                      final_status="ok", retry_exhausted=False,
                      elapsed_retry_time=slept)
        return value
