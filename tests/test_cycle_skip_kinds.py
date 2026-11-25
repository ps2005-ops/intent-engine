"""A missed cycle must not look like a duplicate.

`SKIPPED_DUPLICATE` was returned for four different situations:

  1. the run id had already completed            -- a real duplicate
  2. it completed while waiting for the lock     -- a real duplicate
  3. the process fired outside its time window   -- NOT a duplicate
  4. another cycle held the lock                 -- NOT a duplicate

Cases 3 and 4 did no work and nothing retries them, so the work never happens.
Reporting them as "duplicate" made three permanently lost cycles
indistinguishable from three whose work was already done -- measured on
2026-10-11, when the host had slept through 2026-10-09 night, 2026-10-10 day
and 2026-10-10 night, launchd coalesced the missed firings and ran BOTH the
06:30 and the 20:30 job at 06:09, and every monitoring surface reported
success because each exited 0.
"""
from intent_engine.market import cycle as C


# ===========================================================================
# The four situations are four statuses
# ===========================================================================
def test_the_skip_kinds_are_all_distinct():
    kinds = {C.SKIPPED_DUPLICATE, C.SKIPPED_OUTSIDE_WINDOW,
             C.SKIPPED_LOCK_CONTENTION, C.SKIPPED_STALE_DATA,
             C.SKIPPED_NO_NEW_MARKET_SESSION}
    assert len(kinds) == 5


def test_every_skip_kind_is_a_declared_status():
    for kind in C.SKIPPED:
        assert kind in C.STATUSES


def test_outside_window_is_not_reported_as_a_duplicate():
    """The whole point: a lost cycle and a redundant one are different."""
    assert C.SKIPPED_OUTSIDE_WINDOW != C.SKIPPED_DUPLICATE


def test_lock_contention_is_not_reported_as_a_duplicate():
    assert C.SKIPPED_LOCK_CONTENTION != C.SKIPPED_DUPLICATE


# ===========================================================================
# The grouping must not swallow a cycle that actually ran
# ===========================================================================
def test_no_new_market_session_is_not_in_the_did_not_run_group():
    """It executed every step and found no new observation.

    Grouping it with the real skips made a completed cycle reporting an
    honest absence look like a process that did nothing -- and broke two
    `did it run?` assertions the moment the group was introduced.
    """
    assert C.SKIPPED_NO_NEW_MARKET_SESSION not in C.SKIPPED_WITHOUT_RUNNING
    assert C.SKIPPED_NO_NEW_MARKET_SESSION in C.SKIPPED


def test_the_did_not_run_group_is_exactly_the_pre_step_exits():
    assert set(C.SKIPPED_WITHOUT_RUNNING) == {
        C.SKIPPED_DUPLICATE, C.SKIPPED_OUTSIDE_WINDOW,
        C.SKIPPED_LOCK_CONTENTION, C.SKIPPED_STALE_DATA}


def test_skipped_is_the_did_not_run_group_plus_the_no_observation_case():
    assert set(C.SKIPPED) == set(C.SKIPPED_WITHOUT_RUNNING) | {
        C.SKIPPED_NO_NEW_MARKET_SESSION}


# ===========================================================================
# Exit codes: deliberate skips must not make launchd thrash, and must not
# be the channel that reports a missed cycle either.
# ===========================================================================
def _result(status):
    return C.CycleResult(
        run_id="2026-10-11:day:America/Toronto", cycle=C.DAY,
        as_of="2026-10-11", timezone="America/Toronto", status=status,
        reason="t")


def test_every_skip_exits_zero():
    for kind in C.SKIPPED:
        assert _result(kind).exit_code == 0, kind


def test_a_real_failure_still_exits_nonzero():
    assert _result(C.FAILED).exit_code == 1
    assert _result(C.PARTIAL).exit_code == 1


def test_exit_code_cannot_distinguish_a_missed_cycle():
    """Pins WHY the health report has to carry this signal.

    A missed cycle and a duplicate both exit 0, deliberately. Anything that
    needs to tell them apart must read the status, not the process result --
    which is exactly the mistake that let three lost cycles pass as healthy.
    """
    assert (_result(C.SKIPPED_OUTSIDE_WINDOW).exit_code
            == _result(C.SKIPPED_DUPLICATE).exit_code)


# ===========================================================================
# A new skip kind must not fall out of the mapping
# ===========================================================================
def test_adding_a_skip_kind_cannot_bypass_the_exit_code_mapping():
    """`exit_code` is built from the SKIPPED tuple, not a hand-written list.

    The previous mapping enumerated two of the five by hand, so a new skip
    kind would have exited 1 and made launchd treat a deliberate refusal as a
    crash.
    """
    import inspect
    import re
    source = inspect.getsource(C.CycleResult.exit_code.fget)
    # Comments and the docstring EXPLAIN the rule and name the statuses while
    # doing so. A guard that greps raw source matches its own rationale, so
    # strip prose and read only the code -- the first version of this test
    # failed on the comment directly above the line it was checking.
    code = re.sub(r'""".*?"""', "", source, flags=re.S)
    code = "\n".join(ln.split("#")[0] for ln in code.splitlines())
    assert "SKIPPED" in code, "exit_code no longer consults the skip group"
    for kind in ("SKIPPED_OUTSIDE_WINDOW", "SKIPPED_LOCK_CONTENTION",
                 "SKIPPED_STALE_DATA", "SKIPPED_NO_NEW_MARKET_SESSION"):
        assert kind not in code, (
            f"{kind} is enumerated by hand in exit_code; use the group")
