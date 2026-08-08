"""A learning system that forgets on restart is not learning."""
from __future__ import annotations

from intent_engine.market import knowledge_retention as KR


def kind(**kw):
    base = dict(name="competes_with", is_original=True,
                write_path="record_relationship", produced=3, reloadable=3)
    base.update(kw)
    return KR.KnowledgeKind(**base)


def test_knowledge_produced_with_no_write_path_is_lost():
    """The wave-5 defect, stated mechanically: three rivalries discovered,
    reported, and measured as zero five waves later."""
    got = kind(write_path="", produced=3, reloadable=0)
    assert got.standing == KR.LOST
    assert got.lost_count == 3


def test_a_write_path_that_nothing_reloads_is_still_lost():
    """Having a method is not the same as the bytes being there."""
    assert kind(produced=3, reloadable=0).standing == KR.LOST


def test_a_derived_fold_is_not_lost():
    """Recomputing a near-miss corpus from the ledger is correct and cheap.
    Demanding that it persist would be cargo cult."""
    got = kind(name="near_miss", is_original=False, write_path="",
               produced=37, reloadable=0)
    assert got.standing == KR.DERIVED
    assert got.lost_count == 0


def test_an_unused_write_path_is_not_a_failure():
    assert kind(produced=0, reloadable=0).standing == KR.UNUSED


def test_the_audit_degrades_when_anything_is_lost():
    got = KR.audit([kind(), kind(name="cross_actor_expectation",
                         write_path="", produced=1, reloadable=0)])
    assert got["status"] == KR.DEGRADED
    assert got["objects_lost"] == 1
    assert "cross_actor_expectation" in got["reason"]


def test_the_audit_is_healthy_when_originals_reload():
    got = KR.audit([kind(), kind(name="near_miss", is_original=False,
                         produced=37, reloadable=0, write_path="")])
    assert got["status"] == KR.HEALTHY
    assert got["objects_lost"] == 0


def test_no_original_knowledge_is_unmeasurable_not_healthy():
    """Zero produced and zero lost is not a clean bill of health."""
    got = KR.audit([kind(produced=0, reloadable=0)])
    assert got["status"] == KR.UNMEASURABLE


def test_the_lost_entries_name_themselves():
    got = KR.audit([kind(name="strategic_objective", write_path="",
                         produced=2, reloadable=0)])
    assert got["lost"][0]["name"] == "strategic_objective"
    assert got["lost"][0]["lost"] == 2
