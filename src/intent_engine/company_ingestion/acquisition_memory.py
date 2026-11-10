"""What this product has already LEARNED about retrieving a URL.

WHY THIS EXISTS, MEASURED
-------------------------
`FilingCache` remembers CONTENT and `SnapshotStore` remembers WHERE TO LOOK.
Nothing remembered the third thing, which is the one that costs the most:
WHAT HAPPENED LAST TIME WE ASKED.

A run gets `MAX_APPROVED_SOURCES` = 14 slots, and the selection comment in the
webapp is explicit that "the slot is the scarce resource, not the request".
Measured locally on 2026-09-03, one clean Johnson & Johnson run spent NINE of
its fourteen slots on guessed known paths -- `/api`, `/docs`, `/developers`,
`/plans`, `/business`, `/case-studies`, `/documentation` -- against a
PHARMACEUTICAL company. Every one returned 404. Five slots were left to carry
the analysis, and the run landed one document above the floor.

Those nine URLs return 404 on every future run too. So does
`https://www.g2.com/products/johnson-johnson/reviews`, which answered 403 on
every company in the probe cohort without a single exception. Re-learning that
costs a slot each time, and a slot is what independent evidence needs.

THE RULE
--------
A retrieval outcome that is a property of the TARGET rather than of the moment
is remembered, and the memory frees the slot instead of spending it. A 404 is
"there is nothing here"; asking again tomorrow asks the same question. A
timeout is "not now", which this module deliberately does NOT remember as a
verdict -- the per-run circuit breaker in `service` already owns silence, and
memorising it would let one bad afternoon suppress a host for a fortnight.

WHAT THIS IS NOT
----------------
It is NOT a lowering of the evidence bar. Nothing here admits a document,
weakens a check, or lets a report be published on less. It changes only WHICH
URLs a run spends its budget on, and every skip is recorded with the status and
the date that justified it, so a reader is told "not requested again: this
returned 404 on 2026-08-29" rather than being quietly shown less.

It is NOT a way to fetch MORE aggressively. The circuit half of this module
only ever reduces request rate: it holds a host OPEN after repeated host-level
failures and lets exactly one probe through when the window elapses.

TENANCY
-------
The key is a public URL and nothing else -- no run id, no tenant, no company
the caller was analysing. One tenant cannot learn from this memory what
another tenant asked about, exactly as `FilingCache` argues for content, and a
guard test holds the key surface to that.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

# --- verdicts ---------------------------------------------------------------
ALLOW = "ALLOW"
SKIP_KNOWN_FAILURE = "SKIP_KNOWN_FAILURE"
SKIP_HOST_OPEN = "SKIP_HOST_OPEN"

# --- circuit states ---------------------------------------------------------
CLOSED = "CLOSED"
HALF_OPEN = "HALF_OPEN"
OPEN = "OPEN"

#: "There is nothing at this address." The answer does not change by asking
#: again, and it is cheap to re-check occasionally in case a site is rebuilt.
GONE_STATUSES = frozenset({404, 410})
GONE_TTL_S = 14 * 24 * 3600

#: "You may not have this." Bot protection and licence walls DO get lifted,
#: and a 403 can also be the tail of a rate limit, so this expires sooner.
REFUSED_STATUSES = frozenset({401, 402, 403, 451})
REFUSED_TTL_S = 3 * 24 * 3600

#: Deterministic properties of the URL ITSELF, decided before or independently
#: of any per-call budget.
#:
#: `too_large` AND `bad_mime` ARE DELIBERATELY ABSENT, and the reason is
#: measured. Both depend on arguments the CALL SITE chooses, not on the
#: document: `safe_fetch` takes `max_bytes` and `accept_truncated` (the EDGAR
#: adapter raises the budget for statutory filings and accepts truncation),
#: and it takes `extra_mime_prefixes` (sitemap discovery accepts XML, the
#: default path does not). So the same URL legitimately returns `too_large`
#: to one caller and a document to another.
#:
#: Caching them cost exactly that: the first cold run of this memory recorded
#: THIRTEEN SEC filings as permanently `too_large`, including Netflix's own
#: 10-K -- a document the EDGAR path retrieves successfully by raising the
#: budget -- and would have refused to request it again for fourteen days.
#: A verdict may only be remembered when the question it answers is the same
#: question next time.
DETERMINISTIC_FAILURES = frozenset({"parse_error", "unsafe_redirect",
                                    "blocked"})
DETERMINISTIC_TTL_S = 14 * 24 * 3600

#: NOT REMEMBERED AS A VERDICT, on purpose. `service._DEAD_HOST_AFTER` already
#: stops a run dialling a silent host, and `transient.py` owns "not now".
#: Persisting these would let one degraded afternoon suppress a good host for
#: days -- the exact failure mode this module exists to avoid causing.
TRANSIENT_FAILURES = frozenset({"timeout", "connection", "host_unreachable",
                                "deadline_exceeded"})
TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})

# --- host circuit -----------------------------------------------------------
#: Host-level failures inside the window before a host is held OPEN.
HOST_OPEN_AFTER = 5
HOST_WINDOW_S = 900.0
#: How long a host stays OPEN before ONE probe is allowed through.
HOST_OPEN_S = 300.0
#: Minimum spacing between requests to one host, seconds. Politeness, and the
#: reason a cohort run stops looking like a burst to a rate limiter.
DEFAULT_MIN_INTERVAL_S = 0.0
HOST_MIN_INTERVAL_S = {
    "www.sec.gov": 0.12,          # SEC asks for <= 10 requests/second
    "sec.gov": 0.12,
    "efts.sec.gov": 0.12,
}

DEFAULT_MEMORY_DIR = Path("data/cache/acquisition")

#: How many URL verdicts to hold in memory. Disk is the system of record;
#: this is only a read cache, so evicting costs one small file read.
MAX_CACHED_VERDICTS = 20_000


def memory_dir() -> Path:
    return Path(os.environ.get("ACQUISITION_MEMORY_DIR")
                or DEFAULT_MEMORY_DIR)


def host_of(url: str) -> str:
    try:
        return (urlparse(url or "").hostname or "").lower()
    except Exception:                                       # noqa: BLE001
        return ""


def _url_key(url: str) -> str:
    """A stable, filesystem-safe key for one URL.

    Hashed rather than escaped because a URL can exceed any path component
    limit, and because a hash cannot smuggle a traversal segment into a path.
    """
    return hashlib.sha256((url or "").encode("utf-8")).hexdigest()[:24]


def classify_outcome(*, ok: bool, status=None, failure_type: str = ""):
    """(kind, ttl_seconds) for one retrieval outcome, or (None, 0).

    ``None`` means "do not remember this as a verdict" -- either it succeeded
    or it is a moment-in-time failure that belongs to the per-run breaker.
    """
    if ok:
        return None, 0
    code = None
    try:
        code = int(status) if status is not None else None
    except (TypeError, ValueError):
        code = None
    if failure_type in TRANSIENT_FAILURES:
        return None, 0
    if code in TRANSIENT_STATUSES:
        return None, 0
    if code in GONE_STATUSES:
        return "gone", GONE_TTL_S
    if code in REFUSED_STATUSES:
        return "refused", REFUSED_TTL_S
    if failure_type in DETERMINISTIC_FAILURES:
        return failure_type, DETERMINISTIC_TTL_S
    return None, 0


class AcquisitionMemory:
    """Disk-backed memory of retrieval outcomes and host health.

    Fully defensive: any storage failure degrades to "no memory", which is a
    request that would have been made anyway. A memory that can break a run
    is worse than no memory, exactly as `FilingCache` argues.
    """

    def __init__(self, root=None, *, enabled: bool = True, clock=None):
        # THE OPERATOR OVERRIDE WINS OVER THE CALLER'S ROOT. `ACQUISITION_MEMORY_DIR`
        # is how an operator points the memory at a different disk, and how a
        # cold-vs-warm measurement gets a clean starting state; a caller-supplied
        # root that silently outranked it would make both impossible.
        override = os.environ.get("ACQUISITION_MEMORY_DIR")
        self.root = (Path(override) if override
                     else (Path(root) if root is not None else memory_dir()))
        self.enabled = enabled
        self._clock = clock or time.time
        self._lock = threading.RLock()
        self._hosts: dict = {}          # host -> mutable host record
        self._urls: dict = {}           # url  -> cached verdict entry
        self._last_request: dict = {}   # host -> monotonic-ish last send
        self._probe_in_flight: set = set()
        self.counters = {"skipped_known_failure": 0, "skipped_host_open": 0,
                         "allowed": 0, "recorded": 0, "half_open_probes": 0,
                         "throttle_waits": 0, "throttle_seconds": 0.0}

    # --- paths ----------------------------------------------------------
    def _url_path(self, url: str) -> Path:
        host = host_of(url) or "_"
        return self.root / "urls" / host / f"{_url_key(url)}.json"

    def _host_path(self, host: str) -> Path:
        return self.root / "hosts" / f"{host or '_'}.json"

    # --- url verdicts ---------------------------------------------------
    def _load_url(self, url: str):
        if url in self._urls:
            return self._urls[url]
        path = self._url_path(url)
        entry = None
        try:
            if path.exists():
                entry = json.loads(path.read_text("utf-8"))
        except Exception:                                   # noqa: BLE001
            entry = None
        self._remember(url, entry)
        return entry

    def _remember(self, url: str, entry) -> None:
        """Hold a verdict in memory, under a bound.

        The preview is an ALWAYS-ON instance on a small plan: it analyses
        company after company without restarting, and every run reads
        50-100 URLs. An unbounded dict here would grow for the life of the
        process to hold answers that are already on disk, which is the wrong
        thing to spend a constrained instance's memory on. Eviction costs
        one file read the next time that URL comes up.
        """
        if len(self._urls) >= MAX_CACHED_VERDICTS:
            for key in list(self._urls)[:MAX_CACHED_VERDICTS // 4]:
                self._urls.pop(key, None)
        self._urls[url] = entry

    def verdict(self, url: str) -> dict:
        """Whether this URL is worth a request right now, and why.

        Returns {verdict, reason, status, failure_type, observed_at, kind}.
        The reason is written for a READER, not for an operator: it names the
        date and what happened, so a skipped source is a stated gap rather
        than a silent absence.
        """
        if not self.enabled:
            return {"verdict": ALLOW, "reason": "", "kind": ""}
        now = self._clock()
        with self._lock:
            entry = self._load_url(url)
            if entry:
                expires = float(entry.get("expires_at") or 0.0)
                if expires > now:
                    self.counters["skipped_known_failure"] += 1
                    return {
                        "verdict": SKIP_KNOWN_FAILURE,
                        "kind": entry.get("kind", ""),
                        "status": entry.get("status"),
                        "failure_type": entry.get("failure_type", ""),
                        "observed_at": entry.get("observed_at", ""),
                        "reason": _skip_reason(entry),
                    }
            host = host_of(url)
            state, detail = self._circuit(host, now)
            if state == OPEN:
                self.counters["skipped_host_open"] += 1
                return {"verdict": SKIP_HOST_OPEN, "kind": "host_open",
                        "reason": detail, "status": None,
                        "failure_type": "host_unreachable"}
            if state == HALF_OPEN:
                # EXACTLY ONE probe crosses an open circuit. Letting the whole
                # wave through on the first expiry would re-burst the host we
                # were protecting, which is how a breaker becomes a metronome.
                if host in self._probe_in_flight:
                    self.counters["skipped_host_open"] += 1
                    return {"verdict": SKIP_HOST_OPEN, "kind": "host_open",
                            "reason": detail, "status": None,
                            "failure_type": "host_unreachable"}
                self._probe_in_flight.add(host)
                self.counters["half_open_probes"] += 1
            self.counters["allowed"] += 1
            return {"verdict": ALLOW, "reason": "", "kind": "",
                    "circuit": state}

    # --- host circuit ---------------------------------------------------
    def _load_host(self, host: str) -> dict:
        if host in self._hosts:
            return self._hosts[host]
        record = {"failures": [], "opened_at": 0.0, "successes": 0,
                  "rate_limited": 0, "refused": 0, "server_error": 0,
                  "timeouts": 0}
        try:
            path = self._host_path(host)
            if path.exists():
                stored = json.loads(path.read_text("utf-8"))
                if isinstance(stored, dict):
                    record.update({k: stored.get(k, record[k])
                                   for k in record})
        except Exception:                                   # noqa: BLE001
            pass
        record["failures"] = [float(t) for t in record.get("failures") or ()]
        self._hosts[host] = record
        return record

    def _circuit(self, host: str, now: float):
        if not host:
            return CLOSED, ""
        record = self._load_host(host)
        opened = float(record.get("opened_at") or 0.0)
        if opened:
            if now - opened < HOST_OPEN_S:
                left = int(HOST_OPEN_S - (now - opened))
                return OPEN, (f"{host} refused or failed to answer "
                              f"{HOST_OPEN_AFTER} times; not dialled again "
                              f"for {left}s")
            return HALF_OPEN, f"{host} is being re-tested after a pause"
        return CLOSED, ""

    def circuit_state(self, host: str) -> str:
        with self._lock:
            return self._circuit(host, self._clock())[0]

    # --- rate awareness -------------------------------------------------
    def delay_before(self, url: str) -> float:
        """Seconds a polite caller should wait before dialling this host.

        Zero for almost everything. It exists so a cohort run spreads its SEC
        requests instead of arriving as a burst, which is what a rate limiter
        actually reacts to.
        """
        host = host_of(url)
        interval = HOST_MIN_INTERVAL_S.get(host, DEFAULT_MIN_INTERVAL_S)
        if interval <= 0:
            return 0.0
        with self._lock:
            last = self._last_request.get(host, 0.0)
            now = time.monotonic()
            wait = max(0.0, last + interval - now)
            # Reserve the slot NOW, so concurrent workers space out against
            # each other rather than all reading the same `last` and all
            # deciding they may go immediately.
            self._last_request[host] = max(now, last + interval)
            if wait > 0:
                self.counters["throttle_waits"] += 1
                self.counters["throttle_seconds"] = round(
                    self.counters["throttle_seconds"] + wait, 3)
            return wait

    # --- recording ------------------------------------------------------
    def record(self, url: str, *, ok: bool, status=None,
               failure_type: str = "") -> str:
        """Remember one retrieval outcome. Returns the kind remembered, or "".

        Never raises. A memory that cannot be written is a memory that is not
        consulted, which is the behaviour that existed before it.
        """
        if not self.enabled:
            return ""
        now = self._clock()
        host = host_of(url)
        kind, ttl = classify_outcome(ok=ok, status=status,
                                     failure_type=failure_type)
        with self._lock:
            record = self._load_host(host) if host else None
            self._probe_in_flight.discard(host)
            if record is not None:
                if ok:
                    # A SUCCESS CLOSES THE CIRCUIT AND CLEARS THE HISTORY.
                    # A host that just answered is not a host in trouble, and
                    # keeping stale failures would re-open it on the next
                    # unrelated 404.
                    record["successes"] += 1
                    record["failures"] = []
                    record["opened_at"] = 0.0
                else:
                    code = _int_or_none(status)
                    if code == 429:
                        record["rate_limited"] += 1
                    elif code in REFUSED_STATUSES:
                        record["refused"] += 1
                    elif code in (500, 502, 503, 504):
                        record["server_error"] += 1
                    if failure_type in TRANSIENT_FAILURES:
                        record["timeouts"] += 1
                    # ONLY SILENCE AND THROTTLING ARM THE BREAKER.
                    #
                    # A 404 is a fact about a path. So, it turns out, is a
                    # 403: `service._HOST_LEVEL_FAILURES` has always been
                    # ("connection", "timeout") for exactly this reason, and
                    # the first version of this module widened it to include
                    # refusals.
                    #
                    # MEASURED on the cold 20-company run: seven 403s on
                    # oracle.com opened its circuit, and Oracle's evidence
                    # collapsed from {identity, independent, investor,
                    # strategy, talent} to {investor, independent} -- the
                    # company's entire own account of itself, lost to a
                    # breaker protecting a host that serves most of its pages
                    # perfectly well. Alphabet and Applied Materials went the
                    # same way. A per-URL refusal memory keeps the part of
                    # that knowledge which is actually true.
                    host_level = (failure_type in TRANSIENT_FAILURES
                                  or code in TRANSIENT_STATUSES)
                    if host_level:
                        window = [t for t in record["failures"]
                                  if now - t < HOST_WINDOW_S]
                        window.append(now)
                        record["failures"] = window[-(HOST_OPEN_AFTER * 2):]
                        if len(window) >= HOST_OPEN_AFTER \
                                and not record.get("opened_at"):
                            record["opened_at"] = now
                self._write_host(host, record)
            if kind:
                entry = {"url": url, "kind": kind, "status":
                         _int_or_none(status), "failure_type": failure_type,
                         "observed_at": _iso(now), "expires_at": now + ttl}
                self._remember(url, entry)
                self._write_url(url, entry)
                self.counters["recorded"] += 1
                return kind
            if ok:
                # A URL THAT NOW WORKS MUST NOT STAY SKIPPED. Without this a
                # site that fixed a broken page would keep being skipped for
                # the whole TTL on the strength of one stale 404.
                self._forget(url)
        return ""

    def _forget(self, url: str) -> None:
        self._remember(url, None)
        try:
            path = self._url_path(url)
            if path.exists():
                path.unlink()
        except Exception:                                   # noqa: BLE001
            pass

    def _write_url(self, url: str, entry: dict) -> None:
        try:
            path = self._url_path(url)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            tmp.write_text(json.dumps(entry), "utf-8")
            tmp.replace(path)
        except Exception:                                   # noqa: BLE001
            pass

    def _write_host(self, host: str, record: dict) -> None:
        try:
            path = self._host_path(host)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            tmp.write_text(json.dumps(record), "utf-8")
            tmp.replace(path)
        except Exception:                                   # noqa: BLE001
            pass

    # --- telemetry ------------------------------------------------------
    def snapshot(self) -> dict:
        with self._lock:
            open_hosts = sorted(
                h for h, r in self._hosts.items()
                if r.get("opened_at") and
                self._clock() - float(r["opened_at"]) < HOST_OPEN_S)
            return dict(self.counters, open_hosts=open_hosts,
                        hosts_seen=len(self._hosts))


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _skip_reason(entry: dict) -> str:
    """What a READER is told about a source that was not requested again."""
    when = str(entry.get("observed_at") or "")[:10]
    status = entry.get("status")
    kind = entry.get("kind", "")
    if kind == "gone":
        return (f"not requested again: this address returned "
                f"HTTP {status} on {when} and no longer exists")
    if kind == "refused":
        return (f"not requested again: this site refused automated access "
                f"(HTTP {status}) on {when}")
    return (f"not requested again: this source could not be read on {when} "
            f"({kind or 'unreadable'})")


def _iso(epoch: float) -> str:
    import datetime
    return datetime.datetime.utcfromtimestamp(
        float(epoch)).replace(microsecond=0).isoformat() + "Z"
