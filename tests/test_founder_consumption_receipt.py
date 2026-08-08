"""The founder half of the market→founder loop.

This side is the only one that knows what became of a dossier: it is read,
validated, accepted or refused, and turned into reasoning blocks here. Without
these receipts the producer's founder-utility metric is permanently
UNMEASURABLE.

The tests are mostly about NOT claiming consumption — a receipt that
overstates is worse than none, because the producer would then optimise
toward a number that means nothing.
"""
import json

import pytest

from intent_engine.external_intel import consumption_receipt as CR


class FakeIntel:
    """Stands in for a loaded StrategicIntel at a chosen point on the ladder."""

    def __init__(self, *, available=True, has_material=True, beliefs=(),
                 as_of="2026-08-07", reason=""):
        self.available = available
        self.has_material = has_material
        self.beliefs = beliefs
        self.as_of = as_of
        self.reason = reason


def _rows(root):
    path = root / CR.LEDGER_PATH
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _stages(root):
    return [r["stage"] for r in _rows(root)]


# ===========================================================================
# THE LADDER IS WALKED HONESTLY
# ===========================================================================
def test_a_used_dossier_reaches_used_in_reasoning(tmp_path):
    CR.acknowledge_context(
        tmp_path, company_id="acme", analysis_id="run1",
        strategic=FakeIntel(beliefs=({"x": 1},)), has_strategic=True)
    stages = _stages(tmp_path)
    assert CR.USED_IN_REASONING in stages
    assert stages.index(CR.RECEIVED) < stages.index(CR.USED_IN_REASONING)


def test_a_dossier_with_no_material_stops_at_validated(tmp_path):
    """Delivered empty and not delivered have different fixes.

    Recorded as a refusal at VALIDATED rather than silently absent, so the
    producer can tell "the founder never got it" from "the founder got it and
    it said nothing" — the second is an upstream content problem.
    """
    CR.acknowledge_context(
        tmp_path, company_id="acme", analysis_id="run1",
        strategic=FakeIntel(has_material=False), has_strategic=False)
    stages = _stages(tmp_path)
    assert CR.USED_IN_REASONING not in stages
    assert CR.ELIGIBLE not in stages
    assert CR.VALIDATED in stages
    assert any(r.get("refusal_code") == CR.NO_MATERIAL for r in _rows(tmp_path))


def test_an_unavailable_dossier_never_reaches_validated(tmp_path):
    CR.acknowledge_context(
        tmp_path, company_id="acme", analysis_id="run1",
        strategic=FakeIntel(available=False, reason="schema mismatch"),
        has_strategic=False)
    stages = _stages(tmp_path)
    assert CR.VALIDATED not in stages
    assert CR.USED_IN_REASONING not in stages
    assert any(r.get("refusal_code") == CR.SCHEMA_REJECTED
               for r in _rows(tmp_path))


def test_no_dossier_writes_no_receipt(tmp_path):
    """Silence about a company nobody published for is correct.

    Emitting a row here would make "the market never looked at this company"
    indistinguishable from "the founder refused it".
    """
    CR.acknowledge_context(tmp_path, company_id="acme", analysis_id="run1",
                           strategic=None, has_strategic=False)
    assert _rows(tmp_path) == []


# ===========================================================================
# IT MUST NOT OVERSTATE
# ===========================================================================
def test_reloading_an_analysis_does_not_add_a_second_consumption(tmp_path):
    for _ in range(3):
        CR.acknowledge_context(
            tmp_path, company_id="acme", analysis_id="run1",
            strategic=FakeIntel(), has_strategic=True)
    used = [r for r in _rows(tmp_path) if r["stage"] == CR.USED_IN_REASONING]
    assert len(used) == 1


def test_a_different_analysis_is_a_different_consumption(tmp_path):
    for run in ("run1", "run2"):
        CR.acknowledge_context(
            tmp_path, company_id="acme", analysis_id=run,
            strategic=FakeIntel(), has_strategic=True)
    used = [r for r in _rows(tmp_path) if r["stage"] == CR.USED_IN_REASONING]
    assert len(used) == 2


def test_a_new_dossier_revision_is_a_new_consumption(tmp_path):
    for revision in ("2026-08-06", "2026-08-07"):
        CR.acknowledge_context(
            tmp_path, company_id="acme", analysis_id="run1",
            strategic=FakeIntel(as_of=revision), has_strategic=True)
    used = [r for r in _rows(tmp_path) if r["stage"] == CR.USED_IN_REASONING]
    assert len(used) == 2


# ===========================================================================
# IT MUST NOT BE ABLE TO BREAK A RUN
# ===========================================================================
def test_an_unwritable_root_is_silent_rather_than_fatal(tmp_path):
    """A telemetry write that fails an analysis is worse than no telemetry."""
    blocked = tmp_path / "nope"
    blocked.write_text("not a directory", encoding="utf-8")
    assert CR.emit(blocked, company_id="acme", stage=CR.RECEIVED,
                   analysis_id="run1") is False


def test_a_broken_strategic_object_does_not_raise(tmp_path):
    class Hostile:
        @property
        def available(self):
            raise RuntimeError("boom")

    CR.acknowledge_context(tmp_path, company_id="acme", analysis_id="run1",
                           strategic=Hostile(), has_strategic=True)


# ===========================================================================
# THE CONTRACT BOTH SIDES SHARE
# ===========================================================================
def test_schema_string_matches_the_market_reader():
    """The one string the duplicated contract depends on.

    The market reader ignores rows whose schema it does not recognise, so a
    drift here is silent data loss rather than an error. Pinned literally.
    """
    assert CR.SCHEMA == "dossier_consumption.v1"
    assert CR.LEDGER_PATH == "reports/market/dossier_consumption.jsonl"


def test_every_emitted_row_carries_the_schema(tmp_path):
    CR.acknowledge_context(tmp_path, company_id="acme", analysis_id="run1",
                           strategic=FakeIntel(), has_strategic=True)
    assert all(r.get("schema") == CR.SCHEMA for r in _rows(tmp_path))
    assert _rows(tmp_path)


def test_no_market_internals_leak_into_the_receipt(tmp_path):
    """This travels to the producer; it must carry nothing private."""
    CR.acknowledge_context(tmp_path, company_id="acme", analysis_id="run1",
                           strategic=FakeIntel(), has_strategic=True)
    blob = json.dumps(_rows(tmp_path)).lower()
    for banned in ("password", "token", "secret", "api_key", "position",
                   "trade", "order", "pnl"):
        assert banned not in blob


# ===========================================================================
# RENDERED — the stage that must not be reachable with an empty section
# ===========================================================================
def test_rendered_requires_actual_blocks_not_an_open_section(tmp_path):
    """An empty strategic section was reachable until this cycle.

    Validated, eligible, "used", and nothing under the heading. Counting the
    heading as RENDERED would re-create exactly the overstatement this
    telemetry exists to prevent.
    """
    CR.acknowledge_context(tmp_path, company_id="acme", analysis_id="run1",
                           strategic=FakeIntel(), has_strategic=True,
                           rendered_blocks=0)
    assert CR.RENDERED_TO_FOUNDER not in _stages(tmp_path)
    assert CR.USED_IN_REASONING in _stages(tmp_path)


def test_rendered_fires_when_a_block_actually_exists(tmp_path):
    CR.acknowledge_context(tmp_path, company_id="acme", analysis_id="run1",
                           strategic=FakeIntel(), has_strategic=True,
                           rendered_blocks=2, surface="analysis")
    rows = [r for r in _rows(tmp_path)
            if r["stage"] == CR.RENDERED_TO_FOUNDER]
    assert len(rows) == 1
    assert rows[0]["strategic_content_used"] == 2
    assert rows[0]["founder_surface_rendered"] == "analysis"
