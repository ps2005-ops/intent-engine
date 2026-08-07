"""Market→Founder consumption — what counts as use, and what does not.

`founder_utility.strategic_dossiers_consumed` reported UNMEASURABLE from the
day learning health was built. Honest, and useless: an engine that cannot tell
whether its output is read is optimising in the dark.

The temptation with any telemetry like this is to make the number go up. Every
test below is about refusing to: a dossier that was received and ignored, an
analysis older than the dossier it claims to have used, a page reloaded twice,
a ledger that does not exist. Each of those has an obvious reading that
inflates utility, and each is rejected.
"""
import json

import pytest

from intent_engine.market import dossier_consumption as DC


def _emit(root, stage, *, analysis="an1", dossier="acme", **kw):
    return DC.record(root, dossier_id=dossier, company_id="acme",
                     founder_analysis_id=analysis, stage=stage, **kw)


# ===========================================================================
# ABSENCE IS NOT ZERO
# ===========================================================================
def test_an_absent_ledger_is_unmeasurable_not_zero(tmp_path):
    """"Nobody told us" and "nobody used it" are opposite findings."""
    summary = DC.summarise(tmp_path, published=22)
    assert summary["dossiers_used"] == DC.UNMEASURABLE
    assert summary["consumption_rate"] == DC.UNMEASURABLE
    assert summary["founder_utility_status"] == DC.UNMEASURABLE
    # and it explains itself, so the sentinel is not read as a bug
    assert "not sharing a root" in summary["because"]
    # what the market side knows on its own is still reported
    assert summary["dossiers_published"] == 22


def test_learning_health_no_longer_hardcodes_unmeasurable(tmp_path):
    """The stub it replaced always said UNMEASURABLE whatever happened."""
    for stage in (DC.RECEIVED, DC.VALIDATED, DC.ELIGIBLE, DC.SELECTED,
                  DC.PROJECTED, DC.USED_IN_REASONING):
        _emit(tmp_path, stage)
    for i in range(2):
        _emit(tmp_path, DC.USED_IN_REASONING, analysis=f"an{i+2}",
              dossier=f"co{i}")
    summary = DC.summarise(tmp_path, published=3)
    assert summary["dossiers_used"] == 3
    assert summary["consumption_rate"] == pytest.approx(1.0)


# ===========================================================================
# WHAT IS NOT CONSUMPTION
# ===========================================================================
def test_a_received_but_unused_dossier_is_not_consumption(tmp_path):
    """Handled is not used. This is the whole point of the stage ladder."""
    _emit(tmp_path, DC.RECEIVED)
    _emit(tmp_path, DC.VALIDATED)
    _emit(tmp_path, DC.ELIGIBLE, analysis="an2", dossier="b")
    _emit(tmp_path, DC.RECEIVED, analysis="an3", dossier="c")
    summary = DC.summarise(tmp_path, published=3)
    assert summary["dossiers_received"] == 3
    assert summary["dossiers_used"] == 0
    assert summary["founder_utility_status"] == DC.PUBLISHED_NOT_CONSUMED


def test_projection_without_reasoning_is_not_consumption(tmp_path):
    """A graph projection nothing reasoned over is a wasted projection."""
    for stage in (DC.RECEIVED, DC.VALIDATED, DC.ELIGIBLE, DC.SELECTED,
                  DC.PROJECTED):
        _emit(tmp_path, stage)
    _emit(tmp_path, DC.PROJECTED, analysis="an2", dossier="b")
    _emit(tmp_path, DC.PROJECTED, analysis="an3", dossier="c")
    summary = DC.summarise(tmp_path, published=3)
    assert summary["dossiers_projected"] == 3
    assert summary["dossiers_used"] == 0
    assert summary["founder_utility_status"] == DC.PUBLISHED_NOT_CONSUMED


def test_an_analysis_older_than_the_dossier_cannot_have_used_it(tmp_path):
    """Retrodiction, in the consumption ledger.

    An analysis that started before the dossier was published did not consume
    it, whatever stage the acknowledgement claims.
    """
    _emit(tmp_path, DC.USED_IN_REASONING,
          published_at="2026-08-07T12:00:00+00:00",
          analysis_started_at="2026-08-01T09:00:00+00:00")
    summary = DC.summarise(tmp_path, published=1)
    assert summary["analysis_predates_dossier"] == 1
    assert summary["founder_utility_status"] == DC.DEGRADED


def test_reloading_the_same_analysis_is_not_a_second_consumption(tmp_path):
    """Otherwise a refresh button looks like founder utility."""
    assert _emit(tmp_path, DC.USED_IN_REASONING) is True
    assert _emit(tmp_path, DC.USED_IN_REASONING) is False
    assert len(DC.read(tmp_path)) == 1


def test_the_same_analysis_advancing_stages_counts_once(tmp_path):
    """A pairing emits many rows; it is still one consumption."""
    for stage in STAGES_UP_TO_USE:
        _emit(tmp_path, stage)
    summary = DC.summarise(tmp_path, published=1)
    assert len(DC.read(tmp_path)) == len(STAGES_UP_TO_USE)
    assert summary["analyses_seen"] == 1
    assert summary["dossiers_used"] == 1


STAGES_UP_TO_USE = (DC.RECEIVED, DC.VALIDATED, DC.ELIGIBLE, DC.SELECTED,
                    DC.PROJECTED, DC.USED_IN_REASONING)


# ===========================================================================
# RATES AND STATUS
# ===========================================================================
def test_a_rate_over_two_analyses_is_not_a_rate(tmp_path):
    _emit(tmp_path, DC.USED_IN_REASONING)
    _emit(tmp_path, DC.USED_IN_REASONING, analysis="an2", dossier="b")
    assert DC.summarise(tmp_path, published=2)["consumption_rate"] == \
        DC.UNMEASURABLE


def test_rendered_is_a_visible_effect_and_used_alone_is_not(tmp_path):
    for i in range(3):
        _emit(tmp_path, DC.USED_IN_REASONING, analysis=f"a{i}",
              dossier=f"c{i}")
    assert DC.summarise(tmp_path, published=3)["founder_utility_status"] == \
        DC.CONSUMED_NO_VISIBLE_EFFECT

    _emit(tmp_path, DC.RENDERED_TO_FOUNDER, analysis="a0", dossier="c0")
    assert DC.summarise(tmp_path, published=3)["founder_utility_status"] == \
        DC.CONSUMED_VISIBLE_EFFECT


def test_utility_status_vocabulary_is_closed(tmp_path):
    assert DC.summarise(tmp_path, published=0)["founder_utility_status"] \
        in DC.UTILITY_STATUSES
    _emit(tmp_path, DC.RECEIVED)
    assert DC.summarise(tmp_path, published=1)["founder_utility_status"] \
        in DC.UTILITY_STATUSES


def test_refusals_are_counted_by_cause(tmp_path):
    _emit(tmp_path, DC.RECEIVED, refusal_code=DC.STALE_DOSSIER,
          refusal_reason="dossier is 40 days old")
    _emit(tmp_path, DC.RECEIVED, analysis="a2", dossier="b",
          refusal_code=DC.IDENTITY_MISMATCH, refusal_reason="wrong company")
    summary = DC.summarise(tmp_path, published=2)
    assert summary["stale_dossier_refusals"] == 1
    assert summary["identity_refusals"] == 1


# ===========================================================================
# CONTRACT INTEGRITY
# ===========================================================================
def test_an_unknown_stage_is_refused(tmp_path):
    with pytest.raises(ValueError):
        _emit(tmp_path, "PROBABLY_FINE")


def test_an_unknown_refusal_code_is_refused(tmp_path):
    with pytest.raises(ValueError):
        _emit(tmp_path, DC.RECEIVED, refusal_code="MEH")


def test_utility_begins_at_used_in_reasoning():
    """Pinned, because moving it down is how this metric gets gamed."""
    assert DC.UTILITY_BEGINS_AT == DC.USED_IN_REASONING
    assert DC.STAGES.index(DC.USED_IN_REASONING) > DC.STAGES.index(
        DC.PROJECTED)


def test_a_corrupt_line_does_not_destroy_the_ledger(tmp_path):
    _emit(tmp_path, DC.USED_IN_REASONING)
    path = tmp_path / DC.LEDGER_PATH
    with path.open("a", encoding="utf-8") as fh:
        fh.write("not json\n")
    assert len(DC.read(tmp_path)) == 1


def test_rows_from_another_schema_are_ignored(tmp_path):
    path = tmp_path / DC.LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "something.else",
                                "stage": DC.USED_IN_REASONING}) + "\n",
                    encoding="utf-8")
    assert DC.read(tmp_path) == ()
    assert DC.summarise(tmp_path, published=1)["founder_utility_status"] == \
        DC.UNMEASURABLE
