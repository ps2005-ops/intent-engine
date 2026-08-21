"""One progress poll that does not answer says nothing about the analysis.

MEASURED LIVE. Two companies, two SHAs, the same signature:

    Adobe Inc.            10d1620   status=0 at t=219.1s
    Meta Platforms, Inc.  b37bee2   status=0 at t=218.8s

Both were progressing normally -- "Stress-testing the reading" at t=33 -- and
Adobe had completed the same analysis in 229 seconds one SHA earlier. What
happened is that a single poll hung for the session's 180-second socket
timeout, and `wait_for_run` treated one transport error as a dead run.

The cost is not a wrong row in a table. Each of those was a live analysis out
of a quota of ten per hour, spent and then discarded by the instrument that
was supposed to measure it.
"""
import time

from intent_engine.pre100 import capture as C


class FakeSession:
    """A service that answers, then drops N polls, then answers again."""

    def __init__(self, script):
        self.script, self.calls, self.errors = list(script), 0, []
        self.last_status = 0
        self.last_headers = {}
        self.last_bytes = 0
        self.last_outcome = ""
        self.last_gate = ""

    def get(self, path, timeout=None):
        self.calls += 1
        status, url, body = self.script[min(self.calls - 1,
                                            len(self.script) - 1)]
        self.last_status, self.last_bytes = status, len(body)
        return status, url, body


WORKING = (200, "https://x/runs/r1/progress", "<p>Reading the evidence</p>")
DROPPED = (0, "https://x/runs/r1/progress", "")
LANDED = (200, "https://x/runs/r1", "<p>The decision</p>")


def test_one_dropped_poll_does_not_end_the_run(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    session = FakeSession([WORKING, DROPPED, WORKING, LANDED])
    state, _url, _secs, _samples = C.wait_for_run(session, "r1", poll=0)
    assert state == C.READY, f"one dropped poll killed the run: {state}"


def test_two_dropped_polls_do_not_end_the_run(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    session = FakeSession([WORKING, DROPPED, DROPPED, LANDED])
    state, _url, _secs, _samples = C.wait_for_run(session, "r1", poll=0)
    assert state == C.READY, state


def test_a_service_that_stops_answering_is_still_a_failure(monkeypatch):
    """THE NEGATIVE CONTROL. Tolerating a dropped poll must not become
    tolerating a dead service -- that would replace a false failure with a
    capture that never ends."""
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    session = FakeSession([WORKING, DROPPED, DROPPED, DROPPED, DROPPED])
    state, _url, _secs, _samples = C.wait_for_run(session, "r1", poll=0)
    assert state == C.FAILED, state


def test_the_poll_timeout_is_far_below_the_session_timeout():
    """A progress page that takes 45 seconds is already saying something.
    The session-wide 180s exists for ANALYSIS routes, which legitimately run
    for minutes; applying it to a poll is what burned three minutes and then
    discarded a live analysis."""
    assert C.POLL_TIMEOUT <= 60
    assert C.POLL_TIMEOUT < C.Session("https://x").timeout


def test_the_poll_is_actually_asked_to_use_it(monkeypatch):
    """A CONSTANT NOTHING PASSES IS A CONSTANT. The first version of this
    repair defined POLL_TIMEOUT and left `session.get` on its default."""
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    seen = []

    class Recording(FakeSession):
        def get(self, path, timeout=None):
            seen.append(timeout)
            return super().get(path, timeout)

    C.wait_for_run(Recording([WORKING, LANDED]), "r1", poll=0)
    assert seen and all(t == C.POLL_TIMEOUT for t in seen), seen


def test_errors_scattered_across_a_long_run_do_not_accumulate(monkeypatch):
    """THE COUNTER MUST RESET, and this test exists because a break proof
    said so.

    Removing the reset left every other test in this file green: they all use
    CONSECUTIVE drops. A run of four minutes that loses one poll early, one
    in the middle and one near the end has not failed -- it answered on every
    poll in between -- but without the reset those three add up and the
    company is discarded. That is the original defect with extra steps.
    """
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    session = FakeSession([WORKING, DROPPED, WORKING, WORKING,
                           DROPPED, WORKING, WORKING,
                           DROPPED, WORKING, LANDED])
    state, _url, _secs, _samples = C.wait_for_run(session, "r1", poll=0)
    assert state == C.READY, (
        "three errors spread across a healthy run were added together")
