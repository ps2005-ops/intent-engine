"""§12/§13: the same requests, over fewer connections.

Nothing here may change WHAT is requested. The saving is a connection count,
which is the one acquisition saving available that does not touch the SEC
request-budget discipline recorded in docs/INTERACTIVE_PERFORMANCE.md.
"""
from __future__ import annotations

import urllib.error

import pytest

from intent_engine.company_ingestion import httppool


class _FakeResponse:
    def __init__(self, status=200, body=b"hello", version=11, headers=None,
                 closed=True):
        self.status = status
        self.reason = "OK"
        self.version = version
        self._body = body
        self._headers = headers or {"Content-Type": "text/html"}
        self._closed = closed
        self.reads = 0

    def read(self, n=None):
        self.reads += 1
        if self.reads == 1:
            return self._body if n is None else self._body[:n]
        return b""

    def isclosed(self):
        return self._closed

    def getheaders(self):
        return list(self._headers.items())


class _FakeConn:
    instances = []

    def __init__(self, host, port, timeout=None, fail=False, response=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.requests = []
        self.closed = False
        self.sock = None
        self._fail = fail
        # A FRESH RESPONSE PER REQUEST, as a real connection produces. Sharing
        # one response object across a reused connection made the second read
        # return b"" and would have tested the fixture rather than the pool.
        self._make_response = response if callable(response) else (
            (lambda: response) if response is not None else _FakeResponse)
        _FakeConn.instances.append(self)

    def request(self, method, target, headers=None):
        if self._fail:
            raise OSError("connection reset by peer")
        self.requests.append((method, target))

    def getresponse(self):
        return self._make_response()

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _fresh_pool(monkeypatch):
    pool = httppool._Pool()
    monkeypatch.setattr(httppool, "POOL", pool)
    _FakeConn.instances = []
    yield pool


def _install(monkeypatch, pool, factory):
    monkeypatch.setattr(pool, "_connect",
                        lambda key, timeout: factory(key, timeout))


def test_two_requests_to_one_host_open_one_connection(monkeypatch,
                                                      _fresh_pool):
    pool = _fresh_pool
    made = []

    def factory(key, timeout):
        made.append(key)
        return _FakeConn(key[1], key[2], timeout)

    _install(monkeypatch, pool, factory)
    for path in ("/a", "/b", "/c"):
        status, head, body, exceeded = pool.request(
            f"https://x.example{path}", 5.0, 1000, headers={"User-Agent": "t"})
        assert status == 200 and body == b"hello"
    assert len(made) == 1, f"opened {len(made)} connections for three requests"
    assert pool.stats["reused"] == 2


def test_a_connection_with_bytes_left_on_it_is_not_reused(monkeypatch,
                                                          _fresh_pool):
    """A connection handed back undrained gives the NEXT request the tail of
    this one's response."""
    pool = _fresh_pool
    made = []

    def factory(key, timeout):
        made.append(key)
        # Over-cap body: bytes remain unread on the socket by construction.
        return _FakeConn(key[1], key[2], timeout,
                         response=lambda: _FakeResponse(body=b"x" * 50,
                                                        closed=False))

    _install(monkeypatch, pool, factory)
    pool.request("https://x.example/a", 5.0, 10, headers={"User-Agent": "t"})
    pool.request("https://x.example/b", 5.0, 10, headers={"User-Agent": "t"})
    assert len(made) == 2, "a connection with unread bytes was pooled"


def test_a_close_header_ends_the_connection(monkeypatch, _fresh_pool):
    pool = _fresh_pool
    made = []

    def factory(key, timeout):
        made.append(key)
        return _FakeConn(key[1], key[2], timeout, response=lambda: _FakeResponse(
            headers={"Content-Type": "text/html", "Connection": "close"}))

    _install(monkeypatch, pool, factory)
    pool.request("https://x.example/a", 5.0, 1000, headers={"User-Agent": "t"})
    pool.request("https://x.example/b", 5.0, 1000, headers={"User-Agent": "t"})
    assert len(made) == 2


def test_a_stale_pooled_connection_is_retried_once(monkeypatch, _fresh_pool):
    """A GET is idempotent, so one retry separates 'the pooled socket died'
    from 'the host is down'."""
    pool = _fresh_pool
    calls = {"n": 0}

    def factory(key, timeout):
        calls["n"] += 1
        # The first connection succeeds, is pooled, then "dies": the third
        # connection object is the fresh retry and answers normally.
        return _FakeConn(key[1], key[2], timeout)

    _install(monkeypatch, pool, factory)
    pool.request("https://x.example/a", 5.0, 1000, headers={"User-Agent": "t"})
    # Poison the pooled connection so the reused attempt raises.
    key = ("https", "x.example", 443)
    pooled, _at = pool._idle[key][0]
    pooled._fail = True
    status, _h, body, _e = pool.request("https://x.example/b", 5.0, 1000,
                                        headers={"User-Agent": "t"})
    assert status == 200 and body == b"hello"
    assert pool.stats["retried_stale"] == 1


def test_a_failure_on_a_fresh_connection_is_not_dialled_twice(monkeypatch,
                                                              _fresh_pool):
    """Retrying a fresh connection hides a real outage behind a doubled
    timeout, and doubles the load on a host that is already struggling."""
    pool = _fresh_pool
    made = []

    def factory(key, timeout):
        made.append(key)
        return _FakeConn(key[1], key[2], timeout, fail=True)

    _install(monkeypatch, pool, factory)
    with pytest.raises(OSError):
        pool.request("https://x.example/a", 5.0, 1000,
                     headers={"User-Agent": "t"})
    assert len(made) == 1, f"a dead host was dialled {len(made)} times"


def test_a_non_2xx_is_raised_as_urllib_would_raise_it(monkeypatch,
                                                      _fresh_pool):
    """`safe_fetch` reads `.code` and `.headers` off HTTPError to follow
    redirects and classify failures. The pooled transport must speak the same
    language as the opener it replaces."""
    pool = _fresh_pool
    _install(monkeypatch, pool, lambda key, timeout: _FakeConn(
        key[1], key[2], timeout, response=lambda: _FakeResponse(
            status=301, headers={"Location": "https://x.example/moved",
                                 "Content-Type": "text/html"})))
    with pytest.raises(urllib.error.HTTPError) as caught:
        pool.request("https://x.example/a", 5.0, 1000,
                     headers={"User-Agent": "t"})
    assert caught.value.code == 301
    assert caught.value.headers.get("Location") == "https://x.example/moved"
    assert caught.value.headers.get("location") == "https://x.example/moved"


def test_an_over_cap_response_reports_exceeded(monkeypatch, _fresh_pool):
    pool = _fresh_pool
    _install(monkeypatch, pool, lambda key, timeout: _FakeConn(
        key[1], key[2], timeout,
        response=lambda: _FakeResponse(body=b"y" * 100)))
    status, _h, body, exceeded = pool.request(
        "https://x.example/a", 5.0, 10, headers={"User-Agent": "t"})
    assert exceeded is True and len(body) == 10
