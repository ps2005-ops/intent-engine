"""Founder-side health — and the gap it refuses to fill with zeros."""
import pytest

from intent_engine.external_intel import consumption_receipt as CR
from intent_engine.external_intel import founder_learning_health as FH


class Intel:
    def __init__(self, available=True, as_of="2026-08-07", reason=""):
        self.available, self.as_of, self.reason = available, as_of, reason
        self.has_material, self.beliefs = True, ({"x": 1},)


def _ack(root, n, *, rendered=1, impact=None, available=True):
    for i in range(n):
        CR.acknowledge_context(
            root, company_id=f"c{i}", analysis_id=f"a{i}",
            strategic=Intel(available=available), has_strategic=available,
            rendered_blocks=rendered if available else 0,
            decision_impact=impact)


def test_no_run_store_is_unmeasurable_not_zero(tmp_path):
    """A health report whose inputs are invented is worse than one that says
    what it cannot see."""
    h = FH.assess(tmp_path)
    for field in ("analyses_full", "analyses_bounded", "analyses_withheld",
                  "acceptance_rate", "wrong_subject_defects"):
        assert h[field] == FH.UNMEASURABLE
    assert "run store" in h["unmeasurable_because"]


def test_no_dossier_at_all_is_a_coverage_bottleneck(tmp_path):
    assert FH.assess(tmp_path)["bottleneck"]["stage"] == FH.SOURCE_COVERAGE


def test_rendered_but_never_decisive_is_a_decision_impact_bottleneck(tmp_path):
    _ack(tmp_path, 4, rendered=1, impact=None)
    b = FH.assess(tmp_path)["bottleneck"]
    assert b["stage"] == FH.DECISION_IMPACT
    assert "not yet useful" in b["because"]


def test_used_but_never_rendered_is_a_presentation_bottleneck(tmp_path):
    _ack(tmp_path, 4, rendered=0)
    assert FH.assess(tmp_path)["bottleneck"]["stage"] == FH.PRESENTATION


def test_refused_dossiers_are_a_consumption_bottleneck(tmp_path):
    _ack(tmp_path, 4, available=False)
    assert FH.assess(tmp_path)["bottleneck"]["stage"] == FH.MARKET_CONSUMPTION


def test_a_rate_over_two_analyses_is_not_a_rate(tmp_path):
    _ack(tmp_path, 2, impact={"changed": True, "materiality": "MEANINGFUL",
                              "impact_types": ["ASSUMPTION"]})
    assert FH.assess(tmp_path)["decision_impact_rate"] == FH.UNMEASURABLE


def test_decision_impact_lifts_the_bottleneck_off_this_side(tmp_path):
    _ack(tmp_path, 4, impact={"changed": True, "materiality": "MEANINGFUL",
                              "impact_types": ["ASSUMPTION"]})
    h = FH.assess(tmp_path)
    assert h["market_learning_decision_relevant"] == 4
    assert h["bottleneck"]["stage"] == FH.NOT_LIMITED


def test_bottleneck_vocabulary_is_closed(tmp_path):
    assert FH.assess(tmp_path)["bottleneck"]["stage"] in FH.BOTTLENECKS
    _ack(tmp_path, 3)
    assert FH.assess(tmp_path)["bottleneck"]["stage"] in FH.BOTTLENECKS


def test_one_pairing_is_counted_once_not_once_per_stage(tmp_path):
    _ack(tmp_path, 1, impact={"changed": True, "materiality": "MINOR",
                              "impact_types": ["RISK"]})
    assert FH.assess(tmp_path)["market_dossiers_available"] == 1
