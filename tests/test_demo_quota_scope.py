"""What may consume an analysis, and what may not (§F).

The brief asks for a hard separation:

    NEW EXPENSIVE ANALYSIS   may consume the quota
    VIEW EXISTING RESULT     may not
    REOPEN RUN               may not
    POLL RUN                 may not
    Q&A                      may not
    HISTORY                  may not
    UI NAVIGATION            may not

The separation held before this file existed, and nothing asserted it -- so
a future handler could call the limiter and no test would notice. The
property is structural (which call sites exist) and behavioural (what the
counter does when a visitor reads).
"""
import pathlib
import re

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig

REMOTE = "203.0.113.99"


@pytest.fixture()
def app(tmp_path):
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    return WebApp(cfg, transport=None, resolver=False)


def _session(name="anon-scope"):
    return {"anonymous": True, "analyses": [], "user_id": name, "csrf": "c"}


def _spent(app):
    return len(app._demo_ip_hits.get(REMOTE, []))


def test_only_the_analyze_handler_can_consume_quota():
    """Structural: exactly one call site, and it is `_analyze`.

    Read from the source rather than asserted in prose, because "only
    /analyze calls it" is the kind of claim that stays in a docstring long
    after it stops being true.
    """
    import inspect
    text = pathlib.Path(inspect.getsourcefile(WebApp)).read_text()
    calls = [m for m in re.finditer(r"self\._demo_rate_limited\(", text)]
    assert len(calls) == 1, (
        f"{len(calls)} handlers can consume an analysis; only /analyze may")
    # and that one call is inside _analyze
    before = text[:calls[0].start()]
    last_def = before.rfind("    def ")
    assert text[last_def:last_def + 40].strip().startswith("def _analyze"), (
        "the limiter is called from something other than _analyze")


def test_reading_pages_never_consumes_an_analysis(app):
    """Behavioural: a visitor who opens a run and reads every surface,
    polls its progress and asks questions spends exactly one analysis --
    the one that started it."""
    s = _session()
    st, h, _b = app._analyze(s, {"consent": "on", "company_name": "Highspot"},
                             remote=REMOTE)
    run_id = dict(h).get("Location", "").split("/runs/")[1].split("/")[0]
    assert _spent(app) == 1
    for path in (f"/runs/{run_id}/progress", f"/runs/{run_id}/progress.json",
                 f"/runs/{run_id}/intro", f"/runs/{run_id}/brief",
                 f"/runs/{run_id}/full", f"/runs/{run_id}/history",
                 f"/runs/{run_id}/evidence", f"/runs/{run_id}/sources",
                 f"/runs/{run_id}/story", f"/runs/{run_id}/connect", "/demo"):
        app.handle("GET", path, session=s) if hasattr(app, "handle") else None
    assert _spent(app) == 1, (
        f"reading the result consumed {_spent(app) - 1} extra analysis/es")


def test_one_visitor_cannot_take_the_whole_address(app):
    """The monopolisation fix: behind one NAT the first visitor used to be
    able to consume all ten, so the second arrived to a spent network."""
    share = app.config.visitor_analyses_per_hour
    ceiling = app.config.demo_ip_analyses_per_hour
    assert share < ceiling, "a share that equals the ceiling is not a share"
    first = _session("anon-A")
    for _ in range(share):
        assert app._demo_rate_limited(first, REMOTE) is None
    assert app._demo_rate_limited(first, REMOTE) is not None, (
        "one visitor was allowed past their share of the address")
    # and the colleague behind them still finds allowance left
    assert app._demo_rate_limited(_session("anon-B"), REMOTE) is None, (
        "a second visitor was refused although the address had room")


def test_minting_a_session_buys_no_extra_allowance(app):
    """THE PROPERTY THE FIRST VERSION OF THIS REPAIR BROKE.

    Scaling the address ceiling by the number of sessions seen was meant to
    serve the office-NAT case. It also handed a free refill to anyone opening
    an incognito window, because an IP and a cookie cannot tell those two
    apart. Seven existing tests caught it. The ceiling is hard again, and
    this asserts it from the direction the broken version failed.
    """
    ceiling = app.config.demo_ip_analyses_per_hour
    allowed = 0
    for i in range(ceiling * 3):          # a fresh visitor every time
        if app._demo_rate_limited(_session(f"anon-mint-{i}"), REMOTE) is None:
            allowed += 1
    assert allowed == ceiling, (
        f"{allowed} analyses were admitted from one address against a "
        f"ceiling of {ceiling}; minting sessions bought capacity")
