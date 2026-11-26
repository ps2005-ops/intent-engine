"""The qualification loop must be able to tell when a round cannot help."""
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "stagnation", ROOT / "scripts/prospect100/stagnation.py")
ST = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ST)


def co(name, **fails):
    return {"company": name, **{m: fails.get(m, "PASS") for m in ST.METRICS}}


def test_disjoint_hard_metrics_are_a_structural_ceiling():
    r = [co("public", independence="FAIL"), co("private", history="BOUNDED")]
    out = ST.analyse({1: r, 2: r, 3: r})
    assert out["verdict"] == "STRUCTURAL_CEILING"
    assert ["independence", "history"] in [c["metrics"] for c in out["structural_ceiling"]] or \
        ["history", "independence"] in [c["metrics"] for c in out["structural_ceiling"]]


def test_flat_binding_metrics_are_stagnant_and_movement_is_productive():
    a = [co("x", independence="FAIL", history="FAIL"), co("y")]
    flat = ST.analyse({1: a, 2: a, 3: a})
    assert flat["verdict"] in ("STAGNANT", "PRODUCTIVE")
    assert flat["qualified_by_round"] == [1, 1, 1]
    b = [co("x"), co("y")]
    moving = ST.analyse({1: a, 2: a, 3: b})
    assert moving["qualified_by_round"][-1] == 2
    assert moving["verdict"] == "PRODUCTIVE"


def test_one_metric_from_qualifying_is_counted():
    out = ST.analyse({1: [co("x", economics="BOUNDED"), co("y", economics="FAIL",
                                                           history="FAIL")]})
    assert out["blocked_by_exactly_one_metric"] == {"economics": 1}


def test_rounds_4_to_12_hit_the_ceiling_that_was_measured():
    """Frozen fixture: the committed R4-R12 scorecard, not a live artifact."""
    out = ST.analyse(ST.load(ROOT / "docs/engineering/prospect100/resume/rounds_companies.csv"))
    assert out["rounds"] == [4, 5, 6, 7, 8, 9, 10, 12]
    assert out["qualified_by_round"] == [0] * 8
    assert out["verdict"] == "STRUCTURAL_CEILING"
    pairs = [set(c["metrics"]) for c in out["structural_ceiling"]]
    assert {"independence", "history"} in pairs
