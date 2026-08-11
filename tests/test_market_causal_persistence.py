"""A causal refusal must be as durable as an estimate would have been.

FOUND BY THE LIVE CYCLE, NOT BY A SUITE. A-WIRE-001's first real run formulated
25 questions from real dated events, refused all 25 for a named missing
prerequisite, and rendered that in the cycle report -- and
`causal_estimates_attempted` still folded to 0, because nothing reached the
ledger. Zero is what that metric reads when the capability has NEVER RUN, so
the planner could not tell a live refusal from a dead node.

That is the missing-versus-zero collapse one layer above the estimator, and it
is the layer the planner reads. These tests hold the write path shut.
"""
from __future__ import annotations

import json

import pytest

from intent_engine.market import learning_store as LS


class _Resolution:
    """The shape the step passes: anything with `as_dict`."""

    def __init__(self, rid, state="PANEL_UNAVAILABLE"):
        self._d = {"resolution_id": rid, "state": state,
                   "question_origin": "EVENT_DERIVED",
                   "missing_prerequisite": "NO_OUTCOME_SERIES_FOR_TREATED_UNIT"}

    def as_dict(self):
        return dict(self._d)


@pytest.fixture
def store(tmp_path):
    return LS.LearningStore(tmp_path / "learning_ledger.jsonl")


# =============================================================================
# 1. THE WRITE HAPPENS, AND A REFUSAL IS NOT SPECIAL-CASED AWAY
# =============================================================================
def test_a_refused_resolution_is_persisted(store):
    """The refusals ARE the finding right now. An engine that persisted only
    its successes would have a research history that is a success log."""
    assert store.record_causal_estimate(_Resolution("cres_a")) is True
    rows = [json.loads(l) for l in store.path.read_text().splitlines()]
    assert [r["record"] for r in rows] == [LS.CAUSAL_ESTIMATE]
    assert rows[0]["state"] == "PANEL_UNAVAILABLE"


def test_the_metric_can_see_a_refusal_that_was_persisted(store):
    """The whole point: the fold the planner reads counts these rows."""
    for i in range(25):
        store.record_causal_estimate(_Resolution(f"cres_{i}"))
    rows = [json.loads(l) for l in store.path.read_text().splitlines()]
    attempted = sum(1 for r in rows if r.get("record") == "causal_estimate")
    assert attempted == 25


def test_an_unwritten_ledger_reads_zero_which_is_why_the_write_matters(store):
    """The NEGATIVE CONTROL, and the actual bug: with no write, the fold reads
    0 -- indistinguishable from a capability that never ran."""
    assert store.causal_estimate_ids() == frozenset()


# =============================================================================
# 2. IDEMPOTENT, OR THE ROW GROWS BY 25 A NIGHT FOREVER
# =============================================================================
def test_the_same_resolution_is_not_appended_twice(store):
    assert store.record_causal_estimate(_Resolution("cres_a")) is True
    assert store.record_causal_estimate(_Resolution("cres_a")) is False
    assert len(store.path.read_text().strip().splitlines()) == 1


def test_a_nightly_rerun_of_unchanged_questions_appends_nothing(store):
    first = [_Resolution(f"cres_{i}") for i in range(25)]
    assert sum(store.record_causal_estimate(r) for r in first) == 25
    again = [_Resolution(f"cres_{i}") for i in range(25)]
    assert sum(store.record_causal_estimate(r) for r in again) == 0
    assert len(store.path.read_text().strip().splitlines()) == 25


def test_a_resolution_without_an_id_is_refused(store):
    """No id means no idempotence key, which means unbounded growth."""
    with pytest.raises(ValueError):
        store.record_causal_estimate(_Resolution(""))


# =============================================================================
# 3. IT SURVIVES A FRESH PROCESS -- "learned is not saved"
# =============================================================================
def test_a_persisted_estimate_reloads_in_a_new_store(tmp_path):
    """A write path proven only against the object that wrote it proves the
    object's memory, not the ledger's."""
    path = tmp_path / "learning_ledger.jsonl"
    LS.LearningStore(path).record_causal_estimate(_Resolution("cres_a"))
    reopened = LS.LearningStore(path)
    assert "cres_a" in reopened.causal_estimate_ids()
    assert reopened.record_causal_estimate(_Resolution("cres_a")) is False


def test_the_record_kind_is_registered(store):
    """`_append` refuses an unregistered kind, so this would fail loudly --
    but it would fail inside the step's `except Exception`, which turns a
    write failure into a rendered error nobody reads."""
    assert LS.CAUSAL_ESTIMATE in LS.RECORD_KINDS


# =============================================================================
# 4. THE PRODUCTION CALL SITE EXISTS -- a write path is not a write
# =============================================================================
def _event(company="acme", evidence_id="ev1", when="2026-03-02",
           kind="LAYOFF"):
    """The live ledger's evidence shape. Copied rather than imported so this
    file fails on its own terms if the shape changes."""
    return {"record": "evidence", "subject_company": company,
            "evidence_id": evidence_id, "observed_at": when,
            "available_at": when, "evidence_type": kind,
            "source": "a filing"}


def test_real_resolutions_reach_the_ledger_and_the_fold_counts_them(tmp_path):
    """End to end on the REAL producer: events in, refusals out, rows on disk,
    counted by the same fold the planner reads.

    This is the test that would have failed before the fix while every other
    causal test stayed green -- because all of them stopped at the report.
    """
    from intent_engine.market import causal_question as CQ

    ledger = tmp_path / LS.DEFAULT_PATH
    events = [_event(company=f"c{i}", evidence_id=f"e{i}") for i in range(3)]
    questions = CQ.questions_from_events(events, as_of="2026-08-10", limit=25)
    assert questions, "the fixture must produce real questions to be a proof"
    resolutions = [CQ.resolve(q, [], as_of="2026-08-10") for q in questions]

    store = LS.LearningStore(ledger)
    assert sum(store.record_causal_estimate(r) for r in resolutions) == \
        len(resolutions)

    # Re-read from a FRESH store, the way the metric does.
    rows = [json.loads(l) for l in ledger.read_text().splitlines()]
    attempted = sum(1 for r in rows if r.get("record") == "causal_estimate")
    assert attempted == len(resolutions) > 0
    # And the refusal survived the round trip intact, not just the row count.
    assert all(r.get("state") for r in rows)


def test_the_step_wires_the_write_into_its_payload():
    """`persisted` must reach the block, so a silent write failure is visible
    in the report instead of being swallowed by the step's `except Exception`.

    Read off the compiled function's constants rather than its source text: a
    source grep matches the comment explaining a removal.
    """
    from intent_engine.market import steps as STEPS

    # A dict display with constant keys compiles to BUILD_CONST_KEY_MAP, which
    # stores the keys as ONE TUPLE constant rather than as separate strings.
    # Reading only the bare strings finds nothing and passes for the wrong
    # reason -- which is what the first version of this test did.
    def _strings(code):
        for const in code.co_consts:
            if isinstance(const, str):
                yield const
            elif isinstance(const, tuple):
                for item in const:
                    if isinstance(item, str):
                        yield item

    flat = set(_strings(STEPS.knowledge_step.__code__))
    assert "causal_resolution" in flat, (
        "the anchor itself is missing; this test is reading the wrong function")
    assert "persisted" in flat, (
        "knowledge_step does not put `persisted` in the causal block; the "
        "write path exists but the surface cannot report whether it ran")

    # THE LOAD-BEARING ASSERTION. The key check above survives deletion of the
    # write itself -- `"persisted": 0` keeps the key and writes nothing -- and a
    # break proof caught exactly that, so it is not the guard. The CALL is.
    # Attribute lookups live in co_names, and a comprehension compiles to its
    # own code object, so both levels are searched.
    def _names(code):
        yield from code.co_names
        for const in code.co_consts:
            if hasattr(const, "co_names"):
                yield from _names(const)

    assert "record_causal_estimate" in set(_names(STEPS.knowledge_step.__code__)), (
        "knowledge_step never calls record_causal_estimate; the resolutions "
        "reach the report and the ledger stays empty, so the fold the planner "
        "reads cannot tell 25 refusals from a node that never ran")
