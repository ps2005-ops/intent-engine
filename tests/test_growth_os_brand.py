"""Brand Memory (§6) — human-approved lifecycle, active-fact fold, and the
'never contradict approved messaging' gate. Offline, deterministic."""
import pytest

from intent_engine.growth_os.foundation import Confidence, GrowthOSError, IntelStore, Provenance
from intent_engine.growth_os.brand import BrandMemoryService


def _svc(tmp_path):
    return BrandMemoryService(IntelStore(tmp_path / "brand.jsonl"))


def _p():
    return Provenance(source="founder", method="manual")


def _c():
    return Confidence(0.9, basis="founder-approved")


def test_agent_may_propose_but_not_approve(tmp_path):
    svc = _svc(tmp_path)
    svc.propose(kind="messaging", key="core", statement="Evidence over hype.",
                provenance=_p(), confidence=_c(), actor="agent")
    # an agent cannot approve
    with pytest.raises(GrowthOSError):
        svc.approve(kind="messaging", key="core", actor="agent",
                    provenance=_p(), confidence=_c())
    assert svc.active_facts() == []                   # nothing active yet
    # a human can
    svc.approve(kind="messaging", key="core", actor="human", provenance=_p(), confidence=_c())
    assert len(svc.active_facts(kind="messaging")) == 1


def test_retire_is_human_only_and_folds_out(tmp_path):
    svc = _svc(tmp_path)
    svc.propose(kind="claim", key="calib", statement="We report calibration.",
                provenance=_p(), confidence=_c())
    svc.approve(kind="claim", key="calib", actor="human", provenance=_p(), confidence=_c())
    assert len(svc.active_facts()) == 1
    with pytest.raises(GrowthOSError):
        svc.retire(kind="claim", key="calib", actor="agent", provenance=_p(), confidence=_c())
    svc.retire(kind="claim", key="calib", actor="human", provenance=_p(), confidence=_c())
    assert svc.active_facts() == []                   # retired folds out


def test_consistency_gate_flags_contradiction(tmp_path):
    svc = _svc(tmp_path)
    # approved messaging forbids over-claiming language
    svc.propose(kind="messaging", key="tone", statement="Never overpromise.",
                provenance=_p(), confidence=_c(),
                contradicts=["guaranteed returns", "get rich quick"])
    svc.approve(kind="messaging", key="tone", actor="human", provenance=_p(), confidence=_c())

    clean = svc.check_consistency("Evidence-driven forecasts you can audit.")
    assert clean == [] and svc.is_consistent("anything honest")

    bad = svc.check_consistency("Guaranteed returns with our tool!")
    assert len(bad) == 1
    assert bad[0].contradicting_phrase == "guaranteed returns"
    assert bad[0].kind == "messaging"                 # explainable: names the fact


def test_cannot_approve_messaging_that_contradicts_active(tmp_path):
    svc = _svc(tmp_path)
    svc.propose(kind="positioning", key="honest", statement="We never guarantee outcomes.",
                provenance=_p(), confidence=_c(), contradicts=["we guarantee outcomes"])
    svc.approve(kind="positioning", key="honest", actor="human", provenance=_p(), confidence=_c())
    # a new fact whose statement literally contradicts the active one is refused
    svc.propose(kind="messaging", key="bold", statement="We guarantee outcomes for everyone.",
                provenance=_p(), confidence=_c())
    with pytest.raises(GrowthOSError):
        svc.approve(kind="messaging", key="bold", actor="human", provenance=_p(), confidence=_c())
