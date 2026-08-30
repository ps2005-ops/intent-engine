"""A usable report may not describe itself as FAILED.

MEASURED LIVE on 517180e6, Microsoft: a complete readable report rendered at
every surface, `deep_status: COMPLETE`, and `result_state: FAILED` on the same
run. Two false statements from one missing check.

`analyse` gives up by RETURNING `(None, ResultState.FAILED, [])` rather than
by raising, so `enrich_deep`'s `except` never fired: the merge loop copied
that FAILED over the core's own state and the next line announced the deep
pass as COMPLETE.
"""
from __future__ import annotations

from intent_engine.company_ingestion import service as SVC


class _Store:
    def __init__(self):
        self._docs = []

    def retrieved(self, run_id):
        return list(self._docs)


def _svc(deep_payload):
    """A service whose deep pass returns `deep_payload` without raising."""
    ci = SVC.CompanyIngestionService.__new__(SVC.CompanyIngestionService)
    ci.store = _Store()
    ci.run_meta = lambda run_id: {"company_name": "Microsoft Corporation"}
    ci._strategic_report = lambda *a, **k: deep_payload
    return ci


def _core_report():
    return {"result_state": "DEEP_PENDING",
            "result_state_detail": "the deeper reading has not finished",
            "deep_status": SVC.DEEP_PENDING,
            "observations": [{"id": "o1"}],
            "evidence_count": 9}


def test_a_deep_failure_does_not_overwrite_the_core_state():
    ci = _svc({"result_state": "FAILED", "strategic_analysis": None})
    report = _core_report()
    ci.enrich_deep("r1", {"strategic_report": report}, previous_model=None)
    assert report["deep_status"] == "FAILED", (
        "the deep pass returned FAILED and was recorded as COMPLETE")
    assert report["result_state"] != "FAILED", (
        "a readable core analysis was relabelled FAILED because a model call "
        "did not return")
    assert report["result_state"] == "DEEP_PENDING"
    assert report["evidence_count"] == 9, "the core's evidence was disturbed"


def test_a_deep_success_still_merges_its_own_fields():
    """POSITIVE CONTROL. Without this the test above passes on a merge that
    was broken outright, which would be a worse defect than the one fixed."""
    ci = _svc({"result_state": "COMPLETE",
               "result_state_detail": "done",
               "strategic_analysis": {"thesis": "x"},
               "reasoning_provenance": "grounded_analyst"})
    report = _core_report()
    ci.enrich_deep("r1", {"strategic_report": report}, previous_model=None)
    assert report["deep_status"] == "COMPLETE"
    assert report["result_state"] == "COMPLETE"
    assert report["strategic_analysis"] == {"thesis": "x"}
    assert report["reasoning_provenance"] == "grounded_analyst"


def test_the_states_come_from_the_existing_vocabulary():
    """No competing status system (§24)."""
    from intent_engine.strategic_intelligence.analyst.contract import (
        ResultState,
    )
    assert "FAILED" in ResultState.ALL
    assert "DEEP_PENDING" in ResultState.ALL
    assert SVC.DEEP_FAILED in SVC.DEEP_STATUSES
    assert SVC.DEEP_COMPLETE in SVC.DEEP_STATUSES
