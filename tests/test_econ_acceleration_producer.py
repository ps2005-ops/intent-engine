"""The producer that `econ.acceleration` did not have.

WHY THIS TEST EXISTS
--------------------
`acceleration` was complete, tested, and imported by nothing. That is this
repository's most repeated failure — a capability with no call site is a
document — and it is invisible from the module's own suite, which passes
perfectly against fixtures forever.

So this asserts the CALL SITE: that a cycle writes `cycle_counts`, that the
counts are of real things rather than of rows appended, and that the rolling
report reads its own history back.
"""
from __future__ import annotations

import pytest

from intent_engine.econ import acceleration as AC
from intent_engine.econ import store as EST
from intent_engine.market import steps as STEPS


class _Ctx:
    """The two attributes `_econ_acceleration` reads, and nothing else."""

    def __init__(self, root, as_of, run_id="r1", dry_run=False):
        self.root = root
        self.as_of = as_of
        self.run_id = run_id
        self.dry_run = dry_run
        self.results = {}


def _node(node_id, at):
    return {"node_id": node_id, "node_class": "MACRO", "kind": "inflation",
            "subject": "US", "standing": "OBSERVED", "occurred_at": at,
            "available_at": at, "value": 1.0}


def test_the_producer_is_wired_into_the_publish_step():
    """Structural: the step must actually call it.

    Asserted by reading the running code rather than by grepping the file,
    because a comment naming the function would satisfy a grep.
    """
    import inspect
    source = inspect.getsource(STEPS.econ_publish_step)
    assert "_econ_acceleration" in source, (
        "the publish step does not call the acceleration producer; the "
        "rolling windows would report INSUFFICIENT_HISTORY forever and "
        "nobody could tell that from a genuinely young engine")


def test_a_cycle_writes_its_counts_and_reads_the_history_back(tmp_path):
    EST.append(tmp_path, "node", _node("en-a", "2026-08-25"),
               written_at="2026-08-25")
    ctx = _Ctx(tmp_path, "2026-08-26")
    got = STEPS._econ_acceleration(ctx, {"beliefs_published": 2})
    assert "error" not in got, got
    assert got["cycles"] == 1
    assert EST.load(tmp_path, "cycle_counts")


def test_new_evidence_is_content_not_rows_appended(tmp_path):
    """`evidence_new` must answer a question about CONTENT.

    A cycle that re-reads yesterday's nodes has ingested them and learned
    nothing from them, and a counter that cannot tell those apart is gameable
    by running more often.
    """
    EST.append(tmp_path, "node", _node("en-old", "2026-08-25"),
               written_at="2026-08-25")
    EST.append(tmp_path, "node", _node("en-new", "2026-08-26"),
               written_at="2026-08-26")
    got = STEPS._econ_acceleration(_Ctx(tmp_path, "2026-08-26"), {})
    counts = got["recorded_this_cycle"]
    assert counts["evidence_ingested"] == 2
    assert counts["evidence_new"] == 1, (
        "a node written on a previous day was counted as new")
    assert counts["duplicate_evidence"] == 1


def test_belief_movement_is_the_size_of_the_change_not_the_count(tmp_path):
    """Ten revisions of 0.001 are not ten units of learning."""
    EST.append(tmp_path, "belief", {
        "belief_id": "b1", "revisions": [
            {"prior": 0.5, "posterior": 0.5001},
            {"prior": 0.5001, "posterior": 0.5002}]},
        written_at="2026-08-26")
    got = STEPS._econ_acceleration(_Ctx(tmp_path, "2026-08-26"), {})
    counts = got["recorded_this_cycle"]
    assert counts["beliefs_revised"] == 2
    assert counts["belief_movement"] == pytest.approx(0.0002, abs=1e-6)


def test_a_dry_run_writes_nothing_durable(tmp_path):
    STEPS._econ_acceleration(_Ctx(tmp_path, "2026-08-26", dry_run=True), {})
    assert EST.load(tmp_path, "cycle_counts") == []


def test_a_young_history_reports_insufficient_rather_than_stable(tmp_path):
    got = STEPS._econ_acceleration(_Ctx(tmp_path, "2026-08-26"), {})
    assert got["windows"]["30d"]["status"] == AC.INSUFFICIENT_HISTORY
    assert got["headline"] == AC.INSUFFICIENT_HISTORY
    assert "30" in got["windows"]["30d"]["reason"]


def test_the_producer_never_fails_a_cycle(tmp_path):
    """A metric that can fail a cycle is a worse defect than a missing metric."""
    got = STEPS._econ_acceleration(_Ctx("/nonexistent/\0bad", "2026-08-26"),
                                   {})
    assert "error" in got
