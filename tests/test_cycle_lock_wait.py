"""The day cycle waits for a finishing night run instead of skipping.

Five 06:30 day cycles (Nov 19-23) were SKIPPED_LOCK_CONTENTION behind night
runs that system sleep had stretched past morning.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from intent_engine.market import cycle as C
from intent_engine.runtime.locks import JobLock, JobLockedError

TZ = ZoneInfo("America/Toronto")


def test_day_waits_until_its_pre_market_deadline_and_night_does_not():
    at_0630 = datetime(2026, 11, 27, 6, 30, tzinfo=TZ)
    assert C.lock_wait_seconds("day", at_0630) == (2 * 60 + 55) * 60
    assert C.lock_wait_seconds("day", datetime(2026, 11, 27, 9, 40, tzinfo=TZ)) == 0
    assert C.lock_wait_seconds("night", at_0630) == 0


def test_a_waiter_acquires_once_the_holder_releases(tmp_path):
    holder = JobLock("market-cycle", root=tmp_path, owner={"run_id": "night"})
    holder.__enter__()
    t = [0.0]
    def fake_sleep(s):
        t[0] += s
        if t[0] >= 60:                       # the night run finishes
            holder.__exit__(None, None, None)
    waiter = JobLock("market-cycle", root=tmp_path, wait_seconds=600,
                     clock=lambda: t[0], sleep=fake_sleep)
    with waiter:
        assert waiter.waited >= 60


def test_a_wait_past_the_deadline_fails_and_names_the_holder(tmp_path):
    with JobLock("market-cycle", root=tmp_path, owner={"run_id": "2026-11-19:night"}):
        t = [0.0]
        waiter = JobLock("market-cycle", root=tmp_path, wait_seconds=90,
                         clock=lambda: t[0],
                         sleep=lambda s: t.__setitem__(0, t[0] + s))
        with pytest.raises(JobLockedError) as err:
            waiter.__enter__()
        assert "2026-11-19:night" in str(err.value)
        assert waiter.waited >= 90


def test_fail_fast_is_still_the_default(tmp_path):
    with JobLock("market-cycle", root=tmp_path):
        with pytest.raises(JobLockedError):
            JobLock("market-cycle", root=tmp_path,
                    sleep=lambda s: pytest.fail("must not wait")).__enter__()
