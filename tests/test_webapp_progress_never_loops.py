"""The page a customer watches must resolve. It was a redirect loop.

MEASURED LIVE on 8397d67, four of four companies, with an instrumented
harness that recorded the status code rather than only the text:

    t=36.0  status=303  body empty  final_url .../runs/<id>/progress

A 303 whose final URL is the page it started from. `_progress` redirects to
the run page as soon as `result_readiness(...)["opens_result"]` is true;
`_run_page` redirected straight back while `_availability(...)["in_flight"]`
was true. Both are true together from the moment a readable result composes
until the worker clears -- which on these runs was:

    Alphabet    36s -> 152s   76% of the run
    Meta        37s -> 220s   83%
    JPMorgan    37s -> 157s   76%
    Cloudflare   9s ->  20s   50%

`result_readiness` already states the rule, and the run page was the one
caller not following it: "opens_result is True IF AND ONLY IF a
customer-readable result exists. When it is True the customer goes to the
analysis, whatever the worker's metadata says."

THE TEST FOLLOWS REDIRECTS WITH A BUDGET. A test that asserts on a single hop
cannot see a loop -- it sees a 303 and calls it a redirect, which is what a
loop looks like one step at a time.
"""
import io

import pytest

from company_fixture_pages import BASE as FIXTURE_SITE, transport as fixture_transport

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig

MAX_HOPS = 8


def _no_network(url, timeout):
    raise OSError("test transport: network disabled")


class Client:
    def __init__(self, app):
        self.app, self.cookies = app, {}

    def request(self, method, path, body=""):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": "; ".join(f"{k}={v}"
                                        for k, v in self.cookies.items()),
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}

        def sr(status, headers):
            out["status"], out["headers"] = status, headers
        payload = b"".join(self.app(env, sr)).decode()
        for key, value in out["headers"]:
            if key == "Set-Cookie":
                name, _, rest = value.partition("=")
                self.cookies[name] = rest.split(";")[0]
        return out["status"], dict(out["headers"]), payload

    def follow(self, path):
        """Walk redirects like a client, and RECORD THE TRAIL."""
        trail = [path]
        for _ in range(MAX_HOPS):
            status, headers, body = self.request("GET", path)
            if not status.startswith("30") or "Location" not in headers:
                return status, body, trail
            path = headers["Location"]
            trail.append(path)
        raise AssertionError(f"redirect loop: {' -> '.join(trail)}")


@pytest.fixture
def app(tmp_path):
    return WebApp(AppConfig(env="test", secret="s" * 40, demo_mode=True,
                            autorun_sources=True,
                            web_store_path=tmp_path / "w.jsonl",
                            fi_store_path=tmp_path / "f.jsonl",
                            ci_store_path=tmp_path / "c.jsonl"),
                  transport=fixture_transport, resolver=False)


def _start(client):
    """A REAL company run, not the synthetic demo.

    The loop lives on the real-run branch of `_run_page`, and a demo run
    dressed up as a real one crashes in the composer instead of reaching it --
    which is a fixture failing, not the product.
    """
    client.request("POST", "/demo", "")
    csrf = client.app.auth.csrf_token(client.cookies["sid"])
    _s, headers, _b = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf}&company_name=Brightlake"
        f"&website={FIXTURE_SITE}")
    loc = headers["Location"]
    assert "/runs/" in loc, loc
    return loc.split("/runs/")[1].split("/")[0]


def _in_flight_with_a_readable_result(app, run_id):
    """THE EXACT LIVE WINDOW: a result exists and the worker has not cleared.

    Forced rather than waited for, because it is a race in production and a
    test that waits for it is a test that passes when it misses it.
    """
    real = app._availability

    def in_flight(rid):
        # BOTH SIDES OF THE WINDOW, forced. `has_report` is what makes the
        # result openable; `in_flight` is what made the run page bounce. The
        # live defect needed exactly this pair and nothing else.
        avail = dict(real(rid))
        avail.update({"in_flight": True, "has_report": True,
                      "documents": max(1, avail.get("documents") or 1)})
        return avail
    app._availability = in_flight
    readiness = app.result_readiness(run_id)
    assert readiness["opens_result"], (
        "fixture is wrong: the window requires an openable result")
    assert readiness["in_flight"], "fixture is wrong: the worker must be live"


def test_the_run_page_does_not_bounce_back_to_progress(app):
    client = Client(app)
    run_id = _start(client)
    _in_flight_with_a_readable_result(app, run_id)
    status, body, trail = client.follow(f"/runs/{run_id}")
    assert status == "200 OK", (status, trail)
    assert body.strip(), "the page a customer lands on may not be empty"


def test_the_progress_page_resolves_to_the_result(app):
    """What the customer actually does: watch, and be taken somewhere."""
    client = Client(app)
    run_id = _start(client)
    _in_flight_with_a_readable_result(app, run_id)
    status, body, trail = client.follow(f"/runs/{run_id}/progress")
    assert status == "200 OK", (status, trail)
    assert trail[-1] != trail[0], "progress never left itself"
    assert body.strip()


def test_a_run_with_nothing_to_show_still_goes_to_progress(app):
    """THE POSITIVE CONTROL, and the behaviour the bounce was written for.

    While the worker is working and there is nothing readable, the run page
    must still send the reader to progress rather than racing the worker.
    Deleting the guard entirely would pass the two tests above and reintroduce
    the 400s and 500s that guard exists to prevent.
    """
    client = Client(app)
    run_id = _start(client)
    real = app._availability

    def nothing_yet(rid):
        avail = dict(real(rid))
        avail.update({"in_flight": True, "has_report": False,
                      "has_result": False, "documents": 0})
        return avail
    app._availability = nothing_yet
    assert not app.result_readiness(run_id)["opens_result"]

    status, headers, _ = client.request("GET", f"/runs/{run_id}")
    assert status.startswith("303"), status
    assert headers["Location"].endswith("/progress"), headers["Location"]


def test_every_customer_route_resolves_in_the_open_window(app):
    """The loop was reachable from the entry route; check the others too.

    ASSERTS WHERE THE READER LANDS, not merely that something rendered. With
    the other nodes repaired, a single surface that still bounces no longer
    loops -- it quietly sends the reader to the progress page instead of the
    deck they asked for, and a test checking only "200 and non-empty" calls
    that a pass. A break proof that reintroduced the bounce on /slides ran
    GREEN against the weaker assertion.
    """
    client = Client(app)
    run_id = _start(client)
    _in_flight_with_a_readable_result(app, run_id)
    for route in ("", "/intro", "/slides", "/full", "/story", "/history",
                  "/connect", "/progress"):
        status, body, trail = client.follow(f"/runs/{run_id}{route}")
        assert status == "200 OK", (route, status, trail)
        assert body.strip(), route
        assert not trail[-1].endswith("/progress"), (
            f"{route or '/'} sent the reader back to the progress page while "
            f"a result was openable: {' -> '.join(trail)}")
        # AND THE READER ARRIVES WHERE THEY ASKED. Forbidding only /progress
        # is too weak: with the other nodes repaired, a surface that still
        # bounces lands the reader on the run page instead of the deck they
        # clicked, and "not /progress" calls that a pass. A break proof that
        # reintroduced the bounce on /slides ran GREEN against that.
        # Two routes are exempt because forwarding is their JOB: `/runs/<id>`
        # opens the first of the six steps, and `/progress` auto-advances to
        # the result -- which is the behaviour the terminal-state invariant
        # requires, not a bounce.
        if route and route != "/progress":
            assert trail[-1].endswith(route), (
                f"asked for {route}, landed on {trail[-1]}: "
                f"{' -> '.join(trail)}")
