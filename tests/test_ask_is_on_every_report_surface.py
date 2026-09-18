"""Ask-a-follow-up, on every surface that declares it should have one.

MEASURED LIVE on 517180e6 with Microsoft: Q&A appeared on 3 of 9 report
surfaces. `/answer`, `/full` and `/slides` had it; `/brief`, `/xray`,
`/dashboard`, `/intro` and `/evidence` did not. Nobody decided that `/brief`
should be mute -- it was simply never edited. That is what per-page mounting
produces, so the mount is declarative and this test reads the same tuple the
router does.
"""
from __future__ import annotations

import inspect
import re

from intent_engine.webapp.app import WebApp


def test_every_declared_surface_is_wired_at_the_route():
    """The router must mount the component on each declared surface.

    Structural rather than behavioural on purpose: a rendered-page assertion
    needs a completed analysis per surface, and that is a live run per test.
    This reads the routing table, which is where the omission actually lives.
    """
    src = inspect.getsource(WebApp._route) if hasattr(WebApp, "_route") else ""
    if not src:
        src = inspect.getsource(WebApp)
    missing = []
    for surface in WebApp.ASK_SURFACES:
        pattern = (r'parts\[2\] == "%s":\s*\n\s*return self\._with_ask\('
                   % re.escape(surface))
        if not re.search(pattern, src):
            missing.append(surface)
    assert not missing, (
        f"declared report surfaces whose route does not mount the follow-up "
        f"form: {missing} -- this is the /brief-shaped hole the declaration "
        f"exists to prevent")


def test_the_component_is_not_duplicated_per_page():
    """One canonical implementation (§29), not six controllers."""
    builders = [n for n in dir(WebApp)
                if "ask" in n.lower() and callable(getattr(WebApp, n, None))]
    form_builders = []
    for name in builders:
        try:
            body = inspect.getsource(getattr(WebApp, name))
        except (OSError, TypeError):
            continue
        if 'name="question"' in body:
            form_builders.append(name)
    assert form_builders == ["_ask_form"], (
        f"more than one place builds the question form: {form_builders}")


def test_the_mount_fails_open():
    """Losing the box costs a feature; raising would cost the report."""
    app = WebApp.__new__(WebApp)
    app._owned = lambda session, run_id: True

    def boom(_run_id):
        raise RuntimeError("layers unavailable")

    app._founder_layers = boom
    page = ("200 OK", [], "<main><h1>Report</h1></main>")
    assert app._with_ask({}, "r1", page) == page


def test_a_page_that_already_mounts_it_is_not_given_a_second_one():
    app = WebApp.__new__(WebApp)
    app._owned = lambda session, run_id: True
    app._founder_layers = lambda r: (None, {}, "")
    app._ask_form = lambda *a: "<section>SHOULD NOT APPEAR</section>"
    body = '<main><form action="/runs/r1/conversation"></form></main>'
    status, headers, out = app._with_ask({}, "r1", ("200 OK", [], body))
    assert "SHOULD NOT APPEAR" not in out
    assert out.count("/conversation") == 1


def test_the_mount_actually_injects_when_it_should():
    """POSITIVE CONTROL. Without this, a mount that never fires would pass
    every assertion above."""
    app = WebApp.__new__(WebApp)
    app._owned = lambda session, run_id: True
    app._founder_layers = lambda r: (None, {"observations": []}, "Acme")
    app._ask_form = lambda *a: "<section id='ask'>ASK</section>"
    status, headers, out = app._with_ask(
        {}, "r1", ("200 OK", [], "<main><h1>Report</h1></main>"))
    assert "ASK" in out
    assert out.index("ASK") < out.index("</main>")


def test_the_mount_does_not_read_a_run_the_reader_does_not_own():
    """The wrapper builds company-specific suggestions from run data, so it
    is a reader of the run in its own right -- and a wrapper is exactly where
    nobody thinks to look for a missing ownership check."""
    app = WebApp.__new__(WebApp)
    app._owned = lambda session, run_id: False
    reads = []
    app._founder_layers = lambda r: (reads.append(r), (None, {}, ""))[1]
    app._ask_form = lambda *a: "<section>LEAK</section>"
    page = ("200 OK", [], "<main><h1>Someone else's report</h1></main>")
    out = app._with_ask({"user_id": "intruder"}, "not-mine", page)
    assert out == page, "a foreign run was decorated with its own questions"
    assert not reads, "run data was read before ownership was established"
