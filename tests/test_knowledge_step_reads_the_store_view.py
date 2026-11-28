"""knowledge_step must fold the store's masked view, never the raw file."""
import ast
import inspect
import json

from intent_engine.market import belief_maturity as BM
from intent_engine.market import calibration_consistency as CK
from intent_engine.market import learning_store as LS
from intent_engine.market import steps


def test_knowledge_step_does_not_parse_the_ledger_itself():
    tree = ast.parse(inspect.getsource(steps.knowledge_step))
    calls = {n.func.attr for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "read_text" not in calls
    assert "rows" in calls
    # the cap must be APPLIED where belief maturity is published
    assert "cap_belief_maturities" in calls


def test_rows_applies_grade_invalidations(tmp_path):
    p = tmp_path / "l.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in [
        {"record": "reconciliation", "expectation_id": "e1", "outcome": "CONFIRMED",
         "evaluated_at": "2026-11-01"},
        {"record": "grade_invalidation", "expectation_id": "e1",
         "invalidates": {"evaluated_at": "2026-11-01"}}]))
    kinds = [r["record"] for r in LS.LearningStore(p).rows()]
    assert "reconciliation" not in kinds and "reconciliation_invalidated" in kinds


def test_a_belief_above_its_mechanism_ceiling_is_published_at_the_ceiling():
    import dataclasses
    m = dataclasses.replace(_any_maturity(), belief_id="b1", subject="vale",
                            state="SUPPORTED")
    inc = CK.Incoherence(kind="BELIEF_ABOVE_ITS_MECHANISM_CEILING",
                         family="demand_weakening", subject="vale",
                         upper_layer="mechanism_calibration", upper_state="FAILING",
                         lower_layer="belief_maturity", lower_state="SUPPORTED",
                         permitted="WEAKENING", why="")
    out, capped = CK.cap_belief_maturities([m], [inc],
                                           family_of={"b1": "demand_weakening"})
    assert out[0].state == "WEAKENING"
    assert capped == [{"belief_id": "b1", "subject": "vale", "family": "demand_weakening",
                       "uncapped": "SUPPORTED", "published": "WEAKENING"}]
    untouched, none = CK.cap_belief_maturities([m], [], family_of={"b1": "demand_weakening"})
    assert untouched[0].state == "SUPPORTED" and none == []


def _any_maturity():
    rows = [{"record": "belief", "belief_id": "b1", "subject": "vale",
             "proposition": "p", "declared_at": "2026-08-01", "created_at": "2026-08-01"}]
    got = BM.classify(rows, as_of="2026-08-07")
    assert got, "BM.classify produced nothing for a declared belief"
    return got[0]
