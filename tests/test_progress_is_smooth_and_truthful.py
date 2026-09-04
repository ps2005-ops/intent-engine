"""The waiting experience: no document reload, a stated maximum, one truth.

MEASURED, on the deployed preview at 517180e6 with Microsoft:

    meta http-equiv="refresh" content="4"
    16,976 bytes of server-rendered HTML per poll
    ~15 full document reloads per minute
    scripts: 0

The reader saw flicker, scroll reset and focus loss, and the server spent CPU
re-rendering a whole page to say that one word had changed -- on an instance
the analysis was already starved on (7-12% of a local core). The "laggy"
complaint was never the analysis being slow.
"""
from __future__ import annotations

import inspect
import re

from intent_engine.webapp.app import WebApp


def _code_only(fn) -> str:
    """Source with comment lines removed.

    A structural guard must read the CODE, not the prose explaining it. The
    first version of this test failed on the comment that documents the very
    string it forbids -- the comment quotes the old meta refresh in order to
    explain why it went away.
    """
    return "\n".join(l for l in inspect.getsource(fn).splitlines()
                      if not l.lstrip().startswith("#"))


def test_the_progress_page_does_not_reload_the_document():
    """A full-page refresh may survive only as the no-JS fallback."""
    src = _code_only(WebApp._progress)
    assert 'http-equiv="refresh"' in src, (
        "positive control: the fallback must still exist for clients without "
        "scripting, or this test would pass on a page that never updates")
    for m in re.finditer(r'http-equiv="refresh"', src):
        window = src[max(0, m.start() - 200):m.start()]
        assert "noscript" in window, (
            "a meta refresh outside <noscript> reloads the whole document "
            "every few seconds for every reader")


def test_the_progress_page_polls_a_small_document():
    src = _code_only(WebApp._progress)
    assert "progress.json" in src, "the page must poll JSON, not itself"
    assert hasattr(WebApp, "_progress_json"), "no JSON progress handler"


def test_the_maximum_shown_is_the_maximum_enforced():
    """A stated maximum is a contract, not reassurance.

    "up to two minutes" while a run continues to 2:30 is a false statement to
    the reader, which is worse than saying nothing at all. The copy and the
    interactive budget therefore come from numbers that must agree.
    """
    assert WebApp.INTERACTIVE_MAX_S == 120
    assert "two minutes" in WebApp.ETA_COPY
    from intent_engine.company_ingestion.deadline import TIER2_HARD_S
    assert WebApp.INTERACTIVE_MAX_S == TIER2_HARD_S, (
        f"the page promises {WebApp.INTERACTIVE_MAX_S}s but the deadline "
        f"enforces {TIER2_HARD_S}s; one of them is lying to the reader")


def test_the_expectation_is_stated_before_the_wait_and_during_it():
    """Both surfaces, from ONE constant, so they cannot drift apart."""
    landing = inspect.getsource(WebApp._demo_page) \
        if hasattr(WebApp, "_demo_page") else ""
    if not landing:
        for name in dir(WebApp):
            fn = getattr(WebApp, name, None)
            try:
                s = inspect.getsource(fn)
            except (OSError, TypeError):
                continue
            if "Not sure where to start" in s:
                landing = s
                break
    assert landing, "could not locate the landing form -- the search broke"
    assert "ETA_COPY" in landing, "no time expectation before the reader commits"
    # THE WAITING PAGE MAY REACH THE CONSTANT THROUGH ITS ACCESSOR.
    #
    # `_progress` now renders `_waiting_expectation(elapsed)`, which returns
    # ETA_COPY under the promise and a truthful "taking longer than usual"
    # sentence once a run passes INTERACTIVE_MAX_S. A page that kept
    # promising "within two minutes" at 2:30 would be lying, so the
    # indirection is the point rather than a way around this guard.
    #
    # So the assertion follows the indirection instead of forbidding it, and
    # then PROVES it: the accessor must actually yield the one constant, or
    # the two surfaces could still drift apart -- which is the only thing
    # this test has ever cared about.
    progress_src = inspect.getsource(WebApp._progress)
    assert ("ETA_COPY" in progress_src
            or "_waiting_expectation" in progress_src), \
        "no time expectation while the reader waits"
    if "_waiting_expectation" in progress_src:
        accessor = inspect.getsource(WebApp._waiting_expectation)
        assert "ETA_COPY" in accessor, (
            "the waiting page's expectation no longer comes from the one "
            "constant the landing page uses; they can now drift apart")

        class _Fake:
            ETA_COPY = WebApp.ETA_COPY
            INTERACTIVE_MAX_S = WebApp.INTERACTIVE_MAX_S
            _waiting_expectation = WebApp._waiting_expectation

        fake = _Fake()
        assert fake._waiting_expectation(0) == WebApp.ETA_COPY
        assert fake._waiting_expectation(None) == WebApp.ETA_COPY
        late = fake._waiting_expectation(WebApp.INTERACTIVE_MAX_S + 1)
        assert late != WebApp.ETA_COPY, (
            "a run past the stated maximum still promises the maximum")
        assert "longer" in late.lower(), late


def test_the_disabled_feedback_notice_is_truthful_and_not_an_infra_report():
    src = inspect.getsource(WebApp._feedback_form)
    assert "temporarily unavailable" in src
    # The gate itself must be untouched: this deployment may not promise to
    # keep what it is sent, so it does not ask.
    assert "feedback_available" in src
    for leak in ("filesystem", "redeploy", "application image", "disk"):
        assert leak not in src.split("return (")[1].split(")")[0], (
            f"the disabled notice exposes {leak!r} to a normal reader")


def test_the_poller_enforces_the_same_ownership_as_the_page():
    """A cheap polling route is still a route.

    `_progress_json` shipped in review with no ownership check: any session
    could watch the progress of somebody else's run, with the run id as the
    only thing protecting it. A new route is the easiest place in a codebase
    to forget a guard, which is why the gate that caught this enumerates the
    route table rather than trusting review.
    """
    src = _code_only(WebApp._progress_json)
    assert "_owned(session" in src, (
        "the JSON poller does not check ownership; the HTML page it mirrors "
        "does, so this route is a way around it")
    owned_at = src.index("_owned(session")
    for leak in ("run_state(", "_hydration_state(", "result_readiness("):
        if leak in src:
            assert src.index(leak) > owned_at, (
                f"{leak} reads run data before ownership is established")
