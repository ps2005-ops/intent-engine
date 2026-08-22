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


# --- a write path is not a write -------------------------------------------

def test_an_unused_write_path_gets_no_credit_when_production_accepted_work():
    """The exact wave-11 gap: `record_relationship` existed, the nightly
    cycle never called it, and every check said "a write path exists" while
    production forgot four rivalries a night."""
    got = kind(produced=0, accepted=4, reloadable=0)
    assert got.standing == KR.DISCOVERED_NOT_PERSISTED
    assert got.persistence_gap == 4
    assert got.lost_count == 4


def test_accepting_and_persisting_everything_is_durable():
    got = kind(produced=4, accepted=4, reloadable=4)
    assert got.standing == KR.DURABLE
    assert got.persistence_gap == 0


def test_a_partial_write_is_still_a_gap():
    got = kind(produced=4, accepted=4, reloadable=3)
    assert got.standing == KR.DISCOVERED_NOT_PERSISTED
    assert got.persistence_gap == 1


def test_the_audit_degrades_on_a_persistence_gap():
    got = KR.audit([kind(produced=0, accepted=4, reloadable=0)])
    assert got["status"] == KR.DEGRADED
    assert got["persistence_gap"] == 4
    assert got["accepted_by_production"] == 4


def test_accepting_nothing_is_not_a_gap():
    """A quiet night is not a defect. Only accepted-but-unwritten is."""
    got = KR.audit([kind(produced=4, accepted=0, reloadable=4)])
    assert got["persistence_gap"] == 0
    assert got["status"] == KR.HEALTHY
