"""Keep-alive HTTP connections, shared across the requests of a deployment.

WHY THIS EXISTS
---------------
`fetch._default_transport` and `edgar._sec_transport` both called
`urllib.request.build_opener(...)` once per request. urllib pools nothing, so
every retrieval paid a fresh DNS lookup, TCP handshake and TLS handshake to a
host the process had already talked to seconds earlier.

MEASURED locally on one cold NVIDIA analysis (`scripts/perf_acquisition_ledger.py`):
36 outbound requests across 4 hosts — 20 to `www.nvidia.com`, 9 to
`www.sec.gov`/`data.sec.gov`. Thirty-two of those handshakes were avoidable.

THIS DOES NOT CHANGE REQUEST COUNT. It changes how many connections carry the
same requests, which is the one acquisition saving available that does not
touch the SEC request-budget discipline recorded in
`docs/INTERACTIVE_PERFORMANCE.md`. Nothing here makes a request that would not
have been made, and nothing here makes a request earlier than it was made.

STDLIB ONLY, DELIBERATELY. `requests`/`urllib3` would give pooling for free and
are in `requirements.txt` — but deployment builds with `pip install -e .` and
never reads that file, so a production import of either is a
`ModuleNotFoundError` waiting for the next clean build. `http.client` is what
urllib is built on anyway.

WHAT IS PRESERVED, EXACTLY
--------------------------
- **No redirects are followed.** `http.client` does not follow them at all;
  every non-2xx is raised as `urllib.error.HTTPError` with `.code` and
  `.headers`, which is precisely the contract `safe_fetch` already handles.
- **The SSRF wall is untouched.** Callers still resolve and validate the host
  before calling in. This module does not resolve, cache DNS, or decide what
  may be dialled — widening the resolve/connect window is a security change
  and does not belong in a latency repair.
- **Byte caps, timeouts, headers** are the caller's, passed through unchanged.
- **A pooled connection is used only when it is provably reusable**: a fully
  drained body, an HTTP/1.1 response, and no `Connection: close`.

STALE SOCKETS. A pooled socket the peer closed while idle fails on the NEXT
request, not when it was closed. Every request here is a GET — idempotent by
definition — so a failure on a REUSED connection is retried exactly once on a
fresh one. A failure on a fresh connection is raised: retrying it would hide a
real outage behind a doubled timeout.
"""
from __future__ import annotations

import http.client
import os
import threading
import time
import urllib.error
from collections import deque
from urllib.parse import urlparse

#: Idle connections kept per (scheme, host, port). Small on purpose: the point
#: is to reuse the connection the previous request just finished with, not to
#: hold sockets open against a free instance's file-descriptor budget.
MAX_IDLE_PER_HOST = 4

#: An idle connection older than this is closed rather than reused. Peers close
#: idle keep-alives unannounced, and a socket that has been sitting for a whole
#: analysis is more likely to fail than to help.
IDLE_TTL_S = 30.0

#: Total idle connections held across all hosts.
MAX_IDLE_TOTAL = 24


class _Pool:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._idle: dict = {}                 # key -> deque[(conn, put_at)]
        self._total = 0
        self.stats = {"reused": 0, "created": 0, "discarded": 0,
                      "retried_stale": 0}

    # -- internals ---------------------------------------------------------
    def _key(self, parsed):
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return (parsed.scheme, parsed.hostname or "", port)

    def _take(self, key):
        with self._lock:
            bucket = self._idle.get(key)
            while bucket:
                conn, put_at = bucket.popleft()
                self._total -= 1
                if time.monotonic() - put_at <= IDLE_TTL_S:
                    self.stats["reused"] += 1
                    return conn
                self.stats["discarded"] += 1
                try:
                    conn.close()
                except Exception:                          # noqa: BLE001
                    pass
        return None

    def _give_back(self, key, conn) -> None:
        with self._lock:
            bucket = self._idle.setdefault(key, deque())
            if (len(bucket) >= MAX_IDLE_PER_HOST
                    or self._total >= MAX_IDLE_TOTAL):
                self.stats["discarded"] += 1
                try:
                    conn.close()
                except Exception:                          # noqa: BLE001
                    pass
                return
            bucket.append((conn, time.monotonic()))
            self._total += 1

    def _connect(self, key, timeout):
        scheme, host, port = key
        self.stats["created"] += 1
        if scheme == "https":
            return http.client.HTTPSConnection(host, port, timeout=timeout)
        return http.client.HTTPConnection(host, port, timeout=timeout)

    # -- the transport -----------------------------------------------------
    def request(self, url: str, timeout: float, max_bytes: int, *,
                headers: dict) -> tuple:
        """GET `url`, returning (status, headers_lower, body, exceeded).

        Raises `urllib.error.HTTPError` for any non-2xx status, so callers
        that already handle urllib's opener see no difference. Raises
        `OSError`/`TimeoutError` for transport failures, as urllib does.
        """
        parsed = urlparse(url)
        key = self._key(parsed)
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        last_exc = None
        for attempt in (0, 1):
            reused = attempt == 0
            conn = self._take(key) if reused else None
            if conn is None:
                if attempt == 1 and last_exc is None:
                    # Nothing was reused, so there is no stale-socket theory
                    # to test; a second dial would just double the timeout.
                    break
                conn = self._connect(key, timeout)
                reused = False
            try:
                conn.timeout = timeout
                if getattr(conn, "sock", None) is not None:
                    try:
                        conn.sock.settimeout(timeout)
                    except OSError:
                        pass
                conn.request("GET", target, headers=dict(headers))
                response = conn.getresponse()
                body = response.read(max_bytes + 1)
                # The body MUST be drained before the connection goes back.
                # A connection returned with bytes still on it hands the next
                # request the tail of this one's response.
                exceeded = len(body) > max_bytes
                if exceeded:
                    remainder_pending = True
                else:
                    remainder_pending = not response.isclosed()
                    if remainder_pending:
                        try:
                            response.read()
                            remainder_pending = False
                        except Exception:                  # noqa: BLE001
                            remainder_pending = True
                head = {k.lower(): v for k, v in response.getheaders()}
                keep = (response.version == 11
                        and "close" not in head.get("connection", "").lower()
                        and not remainder_pending)
                if keep:
                    self._give_back(key, conn)
                else:
                    try:
                        conn.close()
                    except Exception:                      # noqa: BLE001
                        pass
                status = response.status
                if not 200 <= status < 300:
                    raise urllib.error.HTTPError(
                        url, status, response.reason,
                        _Headers(head), None)
                return (status, head, body[:max_bytes], exceeded)
            except urllib.error.HTTPError:
                raise
            except Exception as exc:                       # noqa: BLE001
                try:
                    conn.close()
                except Exception:                          # noqa: BLE001
                    pass
                last_exc = exc
                if reused and attempt == 0:
                    # A GET is idempotent, so exactly one retry on a fresh
                    # connection separates "the pooled socket had died" from
                    # "the host is down". Only a REUSED connection earns it.
                    self.stats["retried_stale"] += 1
                    continue
                raise
        if last_exc is not None:
            raise last_exc
        raise OSError(f"no connection could be made to {url}")


class _Headers(dict):
    """The two accessors `safe_fetch` uses on `HTTPError.headers`."""

    def get(self, key, default=None):                       # noqa: A003
        return dict.get(self, str(key).lower(), default)

    def items(self):
        return dict.items(self)


#: One pool per process. Connections are a property of the machine, not of a
#: run, and scoping this per analysis would reuse nothing.
POOL = _Pool()


def pooling_enabled() -> bool:
    """Off only if explicitly disabled, so a live incident has a switch that
    does not need a deploy to reason about."""
    return os.environ.get("CI_HTTP_POOLING", "1").strip().lower() not in (
        "0", "false", "no", "off")


def stats() -> dict:
    return dict(POOL.stats)
