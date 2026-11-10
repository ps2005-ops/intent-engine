"""Batch 14: the funnel names the FIRST loss, and never mislabels its cause.

A funnel that reports totals lets a healthy early stage hide a dead late one.
A funnel that reports the wrong CAUSE is worse: "blocked on credits" is a
reason to wait, and "nothing produces this stage" is a reason to build — and
the founder path has one of each, one stage apart.
"""
import importlib.util
import pathlib

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "v5_learning_funnel",
    pathlib.Path(__file__).resolve().parent.parent
    / "scripts" / "v5_learning_funnel.py")
funnel = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(funnel)


def _record(*, attempted=14, ok=10, documents=10, independent=3,
            report="PRESENT", result_state="COMPLETE",
            attribution="NOT_ATTEMPTED", producing=0):
    return {
        "company_id": "acme",
        "source_health": {"attempted": attempted, "ok": ok},
        "evidence": {"documents_retrieved": documents,
                     "independence": {
                         "independent_evidence_count": independent}},
        "intelligence": {"strategic_report": report,
                         "result_state": result_state},
        "learning": {"attribution_state": attribution,
                     "effect_producing_evidence_rows": producing},
        "dossier": {"state": "PRESENT"},
    }


def test_the_first_starved_transition_is_the_earliest_one():
    """A later empty stage is not news once an earlier one has emptied."""
    chain = funnel.stages(_record(attempted=100, ok=5, documents=5,
                                  independent=1))
    verdict = funnel.first_starved(chain)
    assert verdict["transition"] == "DISCOVERED → FETCHED"


def test_a_stage_with_no_producer_is_not_reported_as_blocked():
    """THE DISTINCTION THIS INSTRUMENT EXISTS FOR.

    A company whose analysis COMPLETED and whose attribution is NOT_ATTEMPTED
    is not waiting on an external dependency — nothing in this codebase writes
    a KnowledgeEffect. Reporting that as BLOCKED_EXTERNAL would keep "we are
    blocked on credits" alive as an explanation for a stage that would read
    zero with the backend fully paid.
    """
    chain = funnel.stages(_record(attribution="NOT_ATTEMPTED"))
    belief = next(s for s in chain if s["stage"] == "BELIEF_ELIGIBLE")
    assert belief["cause"] == funnel.NO_PRODUCER
    assert belief["cause"] != funnel.BLOCKED_EXTERNAL


def test_a_credit_blocked_company_is_reported_as_blocked_not_as_loss():
    """The mirror image: an unpaid API bill is not an evidence finding."""
    chain = funnel.stages(_record(report="ABSENT", result_state="",
                                  attribution="BLOCKED_EXTERNAL_CREDITS"))
    analysed = next(s for s in chain if s["stage"] == "ANALYZED")
    assert analysed["cause"] == funnel.BLOCKED_EXTERNAL


def test_an_unmeasured_stage_is_unavailable_not_zero():
    record = _record()
    record["evidence"]["independence"] = {}
    chain = funnel.stages(record)
    independent = next(s for s in chain if s["stage"] == "INDEPENDENT")
    assert independent["n"] is None
    assert independent["cause"] == funnel.UNAVAILABLE


def test_a_healthy_chain_names_no_starved_transition():
    """NEGATIVE CONTROL. A detector that always fires measures nothing."""
    chain = funnel.stages(_record(attempted=10, ok=10, documents=10,
                                  independent=10, attribution="MEASURED",
                                  producing=10))
    # Sliced BY NAME, not by index: an earlier version cut at a fixed offset
    # and silently began including a different stage the moment one was
    # inserted, so the control stopped testing what it claimed to.
    upto = [s["stage"] for s in chain].index("BELIEF_ELIGIBLE")
    verdict = funnel.first_starved(chain[:upto])
    assert verdict["transition"] == "none"
    assert verdict["cause"] == funnel.HEALTHY


def test_the_verdict_carries_the_numbers_it_was_derived_from():
    chain = funnel.stages(_record(attempted=100, ok=5))
    verdict = funnel.first_starved(chain)
    assert verdict["from"] == 100 and verdict["to"] == 5
    assert verdict["survived"] == 0.05


@pytest.mark.parametrize("stage", [
    "DISCOVERED", "FETCHED", "CANONICALIZED", "INDEPENDENT", "ANALYZED",
    "BELIEF_ELIGIBLE", "BELIEF_CHANGED", "THESIS_OR_EXPECTATION_CHANGED",
    "EXECUTIVE_CONSUMED"])
def test_every_declared_stage_is_present(stage):
    """A funnel that silently drops a stage cannot report a loss in it."""
    assert stage in [s["stage"] for s in funnel.stages(_record())]
