"""Quota is spent on work delivered, not on requests attempted. §4.

MEASURED on the deployed preview: /analyze answered HTTP 500 in under a
second, six times, for six different companies -- and every one of those
still consumed one of the visitor's ten analyses for the hour, because the
rate limiter records the hit BEFORE the run is opened and the failure
happened afterwards. A visitor could spend a whole hour on requests that
produced nothing and were never explained.
"""
import pytest

from intent_engine.webapp.app import WebApp


class _Session(dict):
    pass


@pytest.fixture()
def app(tmp_path):
    from tests.test_strategic_intelligence import _strategic_webapp_run
    built, _client, _run = _strategic_webapp_run(tmp_path)
    return built


def _session():
    return _Session({"anonymous": True, "analyses": [], "user_id": "u1",
                     "csrf": "c"})


def _spent(app, session, remote="1.2.3.4"):
    return len([t for t in app._demo_ip_hits.get(remote, [])])


# Q1 -------------------------------------------------------------------------

def test_a_successful_reservation_consumes_exactly_one(app):
    s = _session()
    assert app._demo_rate_limited(s, "1.2.3.4") is None
    assert _spent(app, s) == 1
    assert len(s["analyses"]) == 1


# Q2 -------------------------------------------------------------------------

def test_a_429_consumes_no_new_quota(app):
    """Whichever window refuses first, the refusal must be free.

    DRIVEN TO THE BINDING LIMIT, not to the IP cap. One visitor is now held
    to a SHARE of their address's hourly ceiling -- so that the first person
    behind an office NAT cannot spend the whole network's allowance -- and
    that share binds before the ceiling does. Looping to the ceiling asserted
    `is None` for requests the product had already correctly refused, which
    tested the old limit rather than the property.
    """
    s = _session()
    cap = min(app.config.visitor_analyses_per_hour,
              app.config.demo_ip_analyses_per_hour)
    for _ in range(cap):
        assert app._demo_rate_limited(s, "1.2.3.4") is None
    before = _spent(app, s)
    blocked = app._demo_rate_limited(s, "1.2.3.4")
    assert blocked is not None                      # the 429 page
    assert _spent(app, s) == before, "a refusal charged the visitor"


# Q3 / Q4 --------------------------------------------------------------------

def test_a_failed_run_creation_refunds_the_reservation(app):
    s = _session()
    app._demo_rate_limited(s, "1.2.3.4")
    reserved = app._demo_quota_reservation(s, "1.2.3.4")
    assert _spent(app, s) == 1
    app._release_demo_quota(s, "1.2.3.4", reserved)
    assert _spent(app, s) == 0
    assert s["analyses"] == []


def test_a_scheduler_refusal_refunds_the_reservation(app):
    """Same mechanism, and it is the second of the two paths that could
    return without any work having been queued."""
    s = _session()
    app._demo_rate_limited(s, "1.2.3.4")
    app._release_demo_quota(s, "1.2.3.4",
                            app._demo_quota_reservation(s, "1.2.3.4"))
    assert _spent(app, s) == 0


# Q5 -------------------------------------------------------------------------

def test_a_retry_after_a_failed_creation_can_succeed(app):
    s = _session()
    cap = app.config.demo_ip_analyses_per_hour
    for _ in range(cap):
        app._demo_rate_limited(s, "1.2.3.4")
    app._release_demo_quota(s, "1.2.3.4",
                            app._demo_quota_reservation(s, "1.2.3.4"))
    assert app._demo_rate_limited(s, "1.2.3.4") is None, (
        "a refunded slot did not become available again")


# Q6 -------------------------------------------------------------------------

def test_a_double_release_cannot_refund_twice(app):
    s = _session()
    app._demo_rate_limited(s, "1.2.3.4")
    app._demo_rate_limited(s, "1.2.3.4")
    assert _spent(app, s) == 2
    stamp = app._demo_quota_reservation(s, "1.2.3.4")
    app._release_demo_quota(s, "1.2.3.4", stamp)
    app._release_demo_quota(s, "1.2.3.4", stamp)
    assert _spent(app, s) == 1, "a double release refunded twice"


def test_a_release_does_not_touch_another_requests_reservation(app):
    s = _session()
    app._demo_rate_limited(s, "1.2.3.4")
    first = app._demo_quota_reservation(s, "1.2.3.4")
    app._demo_rate_limited(s, "5.6.7.8")
    app._release_demo_quota(s, "1.2.3.4", first)
    assert _spent(app, s, "5.6.7.8") == 1


def test_a_logged_in_session_is_never_refunded_or_limited(app):
    s = _Session({"anonymous": False, "analyses": [], "user_id": "u2"})
    assert app._demo_rate_limited(s, "9.9.9.9") is None
    assert app._demo_quota_reservation(s, "9.9.9.9") is None
    app._release_demo_quota(s, "9.9.9.9", None)     # must not raise


# --- the structural guard: every failure path must release ----------------

def test_every_early_return_after_reservation_releases_it():
    """Every path that returns a PAGE instead of a run must refund.

    THE VERSION THIS REPLACES COULD NOT FAIL. It counted occurrences of
    `_release_demo_quota` in the source and required three or more. Three
    were present from the day it was written, so the assertion was satisfied
    for as long as the file existed -- while three other paths
    (`_company_not_found_page`, `_name_choice_page`, `_disambiguation_page`)
    returned without refunding anything. A visitor typing a company we could
    not name paid for the privilege, which is how "Too many analyses for now"
    was reached on the live preview without a single analysis running.

    So this reads the code rather than counting a substring: every `return`
    of a page-producing helper that sits after the reservation must have a
    release in the same block, ahead of it.
    """
    import ast
    import inspect
    import textwrap

    #: Helpers that build a PAGE. Reaching one means no run was opened.
    PAGE_RETURNS = {"_error_page", "_company_not_found_page",
                    "_name_choice_page", "_disambiguation_page"}
    source = textwrap.dedent(inspect.getsource(WebApp._analyze))
    tree = ast.parse(source)

    def call_name(node):
        func = getattr(node, "func", None)
        return getattr(func, "attr", "") if func is not None else ""

    def releases(stmt):
        return any(call_name(n) == "_release_demo_quota"
                   for n in ast.walk(stmt) if isinstance(n, ast.Call))

    # WHERE THE RESERVATION IS MADE. Returns ABOVE it (the consent check)
    # cannot leak anything, because nothing has been reserved yet.
    reserve_line = min(
        (n.lineno for n in ast.walk(tree)
         if isinstance(n, ast.Assign)
         and any(getattr(t, "id", "") == "_reserved" for t in n.targets)),
        default=0)
    offenders, reserved_seen = [], bool(reserve_line)
    for parent in ast.walk(tree):
        body = getattr(parent, "body", None)
        if not isinstance(body, list):
            continue
        freed = False
        for stmt in body:
            if stmt.lineno < reserve_line:
                continue
            # the reservation itself, and any refund, arm the block
            if isinstance(stmt, ast.Assign) and any(
                    getattr(t, "id", "") == "_reserved" for t in stmt.targets):
                reserved_seen = True
                freed = True
                continue
            if releases(stmt):
                freed = True
            if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call):
                if call_name(stmt.value) in PAGE_RETURNS and not freed:
                    offenders.append(
                        f"line {stmt.lineno}: {call_name(stmt.value)}")
    assert reserved_seen, "the reservation this guard keys on has moved"
    assert not offenders, (
        "these paths return a page without refunding the reservation: "
        + "; ".join(offenders))
