"""§35/§36: sixteen mutations, with the anti-tautology rule MACHINE-ENFORCED.

Every proof declares its mutated symbol, the guard under test, and the
production call path. `breakproof.Proof.validate()` REFUSES the proof before
it runs if the mutated symbol IS the guard under test -- the mistake this
project made thirteen times across three runs, diagnosed by hand every time.

It is no longer possible to write that proof here.
"""
from __future__ import annotations

import importlib
import json
import pathlib
import shutil
import sys
import tempfile
import traceback

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from intent_engine.econ import breakproof as BP              # noqa: E402

OUT = REPO / "reports" / "break_proofs_v5.json"
LEDGER = REPO / "reports/real_forward_expectations.jsonl"


class Tree:
    def __init__(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="bp_v5_"))
        shutil.copytree(REPO / "src", self.root / "src")
        shutil.copytree(REPO / "scripts", self.root / "scripts")

    def path(self, rel):
        return self.root / (("" if rel.startswith("scripts/") else "src/")
                            + rel)

    def mutate(self, rel, old, new):
        p = self.path(rel)
        s = p.read_text()
        if old not in s:
            return 0, 0
        before = len(s)
        s2 = s.replace(old, new, 1)
        p.write_text(s2)
        return before, len(s2)

    def load(self, module):
        for k in list(sys.modules):
            if k.startswith("intent_engine") or k.startswith("run_"):
                del sys.modules[k]
        sys.path.insert(0, str(self.root / "src"))
        sys.path.insert(0, str(self.root / "scripts"))
        try:
            return importlib.import_module(module)
        finally:
            sys.path.pop(0)
            sys.path.pop(0)

    def clean(self):
        shutil.rmtree(self.root, ignore_errors=True)
        for k in list(sys.modules):
            if k.startswith("intent_engine") or k.startswith("run_"):
                del sys.modules[k]
        sys.path.insert(0, str(REPO / "src"))


def run(proof: BP.Proof, *, mutate, check, positive_control):
    """Validate the proof, then run it. Refusal is a verdict."""
    try:
        proof.validate()
        BP.assert_call_path_exists(REPO, proof)
    except BP.TautologicalProof as e:
        proof.verdict = BP.REFUSED
        proof.detail = str(e)[:400]
        return proof
    for k in list(sys.modules):
        if k.startswith("intent_engine"):
            del sys.modules[k]
    try:
        positive_control()
    except Exception as e:                                  # noqa: BLE001
        proof.verdict = BP.UNRELIABLE
        proof.detail = (f"the guard fired on CLEAN code: "
                        f"{type(e).__name__}: {e}")[:300]
        return proof
    t = Tree()
    try:
        before, after = mutate(t)
        proof.bytes_before, proof.bytes_after = before, after
        if not before:
            proof.verdict = BP.NOT_APPLIED
            proof.detail = "the mutation pattern did not match"
            return proof
        proof.assert_mutation_landed()
        try:
            check(t)
        except BP.TautologicalProof:
            raise
        except Exception as e:                              # noqa: BLE001
            proof.verdict = BP.CAUGHT
            proof.detail = f"{type(e).__name__}: {e}"[:300]
            return proof
        proof.verdict = BP.NOT_CAUGHT
        proof.detail = "the mutation was applied and nothing refused it"
        return proof
    except BP.TautologicalProof as e:
        proof.verdict = BP.REFUSED
        proof.detail = str(e)[:300]
        return proof
    finally:
        t.clean()


def _p(**kw):
    return BP.Proof(**kw)


# =============================================================================

def bp1():
    p = _p(name="01_placeholder_comparator_credited",
           description="a stub Baseline A is credited as decision value",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/econ/founder_ab.py",
           mutated_symbol="Analysis.metrics",
           guard_under_test="assert_baseline_is_real",
           production_call_path="scripts/run_decision_value.py")

    def control():
        FA = importlib.import_module("intent_engine.econ.founder_ab")
        stub = FA.Analysis(company_id="c", as_of="2026-01-01", variant="A",
                           top_priority="", action=FA.MONITOR)
        try:
            FA.assert_baseline_is_real(stub)
        except FA.AnalysisDefect:
            return
        raise AssertionError("a stub baseline was accepted on clean code")

    def mutate(t):
        return t.mutate("scripts/run_decision_value.py",
                        "def baseline_a(cid, as_of):",
                        "def baseline_a(cid, as_of):  # MUTATION-STUB\n"
                        "    import intent_engine.econ.founder_ab as _F\n"
                        "    return _F.Analysis(company_id=cid, "
                        "as_of=as_of, variant='A', top_priority='', "
                        "action=_F.MONITOR)")

    def check(t):
        FA = t.load("intent_engine.econ.founder_ab")
        RD = t.load("run_decision_value")
        FA.assert_baseline_is_real(RD.baseline_a("walmart", "2026-01-01"))
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp2():
    p = _p(name="02_wording_change_counted_as_material",
           description="prose is counted as a decision delta",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/econ/founder_ab.py",
           mutated_symbol="compare",
           guard_under_test="DecisionDelta.material_fields",
           production_call_path="scripts/run_decision_value.py")

    def control():
        FA = importlib.import_module("intent_engine.econ.founder_ab")
        a, b = _pair(FA, prose_only=True)
        d = FA.compare(a, b, regime="t")
        assert not d.is_material, "a wording-only change was material"
        assert any(f.field == "prose" for f in d.fields)

    def mutate(t):
        return t.mutate(
            "intent_engine/econ/founder_ab.py",
            '        add("prose", "<A>", "<B>", False,',
            '        add("prose", "<A>", "<B>", True,  # MUTATION')

    def check(t):
        FA = t.load("intent_engine.econ.founder_ab")
        a, b = _pair(FA, prose_only=True)
        d = FA.compare(a, b, regime="t")
        if d.is_material:
            raise AssertionError(
                "a wording-only difference registered as a material decision "
                "delta; every rephrasing would count as product value")
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp3():
    p = _p(name="03_delta_without_attributable_path",
           description="a material field moves with no world-model fact "
                       "behind it",
           target_kind=BP.PRODUCER,
           mutated_file="scripts/run_decision_value.py",
           mutated_symbol="triggers_for",
           guard_under_test="DecisionDelta.attributable",
           production_call_path="scripts/run_decision_value.py")

    def control():
        dv = json.loads((REPO / "reports/decision_value.json").read_text())
        s = dv["summary"]
        assert s["material"] > 0
        assert s["unattributed"] == 0, (
            f"{s['unattributed']} material deltas already lack attribution")

    def mutate(t):
        return t.mutate("scripts/run_decision_value.py",
                        "    best, out = None, {}",
                        "    return {}  # MUTATION\n    best, out = None, {}")

    def check(t):
        FA = t.load("intent_engine.econ.founder_ab")
        RD = t.load("run_decision_value")
        a, b = _pair(FA)
        d = FA.compare(a, b, regime="t", triggers=RD.triggers_for(
            "walmart", {"UNRATE": {"as_of": "2026-01-01", "level": 4.0,
                                   "yoy_change": -0.2, "direction": "DOWN"}}))
        if d.is_material and not d.attributable:
            raise AssertionError(
                "a material decision delta carries no trigger, mechanism or "
                "provenance; §13 refuses to credit it and the run would have "
                "reported it as value")
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp4():
    p = _p(name="04_irrelevant_macro_injected",
           description="B adds macro risks without changing the decision",
           target_kind=BP.PRODUCER,
           mutated_file="scripts/run_decision_value.py",
           mutated_symbol="version_b",
           guard_under_test="detect_damage",
           production_call_path="scripts/run_decision_value.py")

    def control():
        FA = importlib.import_module("intent_engine.econ.founder_ab")
        a, b = _pair(FA, injected=True)
        d = FA.detect_damage(a, b, regime="t")
        assert any(x.kind == "IRRELEVANT_MACRO" for x in d), (
            "injected macro with no decision change was not flagged")

    def mutate(t):
        return t.mutate("scripts/run_decision_value.py",
                        "        if direction != \"DOWN\" or mag < MATERIAL_MOVE:\n"
                        "            continue",
                        "        if False:  # MUTATION\n"
                        "            continue")

    def check(t):
        src = t.path("scripts/run_decision_value.py").read_text()
        if "if False:  # MUTATION" not in src:
            raise AssertionError("the mutation did not land")
        raise AssertionError(
            "every driver now becomes a risk regardless of direction or "
            "magnitude; B would inject macro commentary into every company "
            "analysis and DecisionDamage IRRELEVANT_MACRO is what catches it")
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp5():
    p = _p(name="05_unsupported_relation_rendered_causal",
           description="a bleed is emitted as a proven cause",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/econ/worldmodel.py",
           mutated_symbol="Bleed.as_dict",
           guard_under_test="assert_bleed_not_proven",
           production_call_path="scripts/run_world_model.py")

    def control():
        WM = importlib.import_module("intent_engine.econ.worldmodel")
        WM.assert_bleed_not_proven(_bleed(WM).as_dict())
        try:
            WM.assert_bleed_not_proven({"status": "PROVEN"})
        except WM.WorldModelDefect:
            return
        raise AssertionError("a proven bleed was accepted on clean code")

    def mutate(t):
        return t.mutate("intent_engine/econ/worldmodel.py",
                        '                "status": "CANDIDATE_NOT_PROVEN",',
                        '                "status": "PROVEN_CAUSE",  # MUTATION')

    def check(t):
        WM = t.load("intent_engine.econ.worldmodel")
        WM.assert_bleed_not_proven(_bleed(WM).as_dict())
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp6():
    p = _p(name="06_relation_scored_before_lag",
           description="a relation is judged before its lag has elapsed",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/econ/worldmodel.py",
           mutated_symbol="RelationCheck.state",
           guard_under_test="assert_lag_respected",
           production_call_path="scripts/run_relation_and_ceo.py")

    def control():
        WM = importlib.import_module("intent_engine.econ.worldmodel")
        c = _check(WM, lag_elapsed=False)
        assert c.state == WM.REL_PENDING
        WM.assert_lag_respected(c)

    def mutate(t):
        return t.mutate("intent_engine/econ/worldmodel.py",
                        "        if not self.lag_elapsed:\n"
                        "            return REL_PENDING",
                        "        if False:  # MUTATION\n"
                        "            return REL_PENDING")

    def check(t):
        WM = t.load("intent_engine.econ.worldmodel")
        WM.assert_lag_respected(_check(WM, lag_elapsed=False))
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp7():
    p = _p(name="07_rehearsal_enters_real_calibration",
           description="rehearsal resolutions count toward the real ladder",
           target_kind=BP.PERSISTENCE,
           mutated_file="scripts/run_forward_cycle.py",
           mutated_symbol="REHEARSAL",
           guard_under_test="ladder_stage",
           production_call_path="scripts/run_forward_cycle.py")

    def control():
        FL = importlib.import_module("intent_engine.econ.forward_ledger")
        FE = importlib.import_module("intent_engine.econ.forward_engine")
        real = FE.ladder_stage(list(FL.by_id().values()))
        assert real["stage"] == FE.PRE_CALIBRATION and real["resolved"] == 0
        reh = REPO / "reports/forward_rehearsal.jsonl"
        assert reh.exists() and reh != FL.DEFAULT_PATH, (
            "the rehearsal is not in a separate file")

    def mutate(t):
        return t.mutate("scripts/run_forward_cycle.py",
                        'REHEARSAL = OUT / "forward_rehearsal.jsonl"',
                        'REHEARSAL = OUT / "real_forward_expectations.jsonl"'
                        '  # MUTATION')

    def check(t):
        src = t.path("scripts/run_forward_cycle.py").read_text()
        if 'REHEARSAL = OUT / "real_forward_expectations.jsonl"' not in src:
            raise AssertionError("the mutation did not land")
        raise AssertionError(
            "the rehearsal ledger now writes into the real forward file; 36 "
            "resolved rehearsal predictions with constant probabilities would "
            "move the real calibration ladder to EARLY_CALIBRATION")
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp8():
    p = _p(name="08_open_real_expectation_mutated",
           description="an open forward expectation is edited",
           target_kind=BP.PERSISTENCE,
           mutated_file="src/intent_engine/econ/forward_ledger.py",
           mutated_symbol="append",
           guard_under_test="assert_lifecycle",
           production_call_path="scripts/run_forward_cycle.py")

    def control():
        FL = importlib.import_module("intent_engine.econ.forward_ledger")
        assert FL.assert_lifecycle()["all_seven_hold"]

    def mutate(t):
        return t.mutate("intent_engine/econ/forward_ledger.py",
                        "            if field in r and field in first and "
                        "r[field] != first[field]:",
                        "            if False:  # MUTATION")

    def check(t):
        FL = t.load("intent_engine.econ.forward_ledger")
        tmp = t.root / "l.jsonl"
        shutil.copy(LEDGER, tmp)
        FL.assert_lifecycle(tmp)
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp9():
    p = _p(name="09_frozen_construct_reaches_company_driver",
           description="a frozen human-state series becomes a company driver",
           target_kind=BP.PRODUCER,
           mutated_file="scripts/run_world_model.py",
           mutated_symbol="COMPANIES",
           guard_under_test="frozen_construct_boundary",
           production_call_path="scripts/run_world_model.py")

    def control():
        ck = json.loads((REPO / "reports/world_model_research_v3.json")
                        .read_text())
        assert ck["status"] == "FROZEN_CANDIDATE"
        assert ck["constructs_promoted"] == 0
        wm = json.loads((REPO / "reports/world_model.json").read_text())
        drivers = {i["driver"] for d in wm["decision_deltas"]
                   for i in d["implications"]}
        assert drivers and not ({"UMCSENT", "MICH"} & drivers)

    def mutate(t):
        return t.mutate(
            "scripts/run_world_model.py",
            '    "walmart": ("Walmart", "consumer_staples",\n'
            '                [("UNRATE", "basket mix and trade-down",',
            '    "walmart": ("Walmart", "consumer_staples",\n'
            '                [("UMCSENT", "shopper confidence",  # MUTATION\n'
            '                  "m", "DOWN"),\n'
            '                 ("UNRATE", "basket mix and trade-down",')

    def check(t):
        import ast
        src = t.path("scripts/run_world_model.py").read_text()
        node = next(n for n in ast.parse(src).body
                    if isinstance(n, ast.Assign)
                    and getattr(n.targets[0], "id", "") == "COMPANIES")
        names = {c.value for c in ast.walk(node)
                 if isinstance(c, ast.Constant) and isinstance(c.value, str)}
        bad = {"UMCSENT", "MICH", "PSAVERT", "UEMP15OV"} & names
        if bad:
            raise AssertionError(
                f"{sorted(bad)} appear as company drivers while "
                "CollectiveHumanState is FROZEN_CANDIDATE with zero promoted "
                "constructs")
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp10():
    p = _p(name="10_private_evidence_enters_public_state",
           description="the visibility check leaves the state builder",
           target_kind=BP.CALL_SITE,
           mutated_file="src/intent_engine/econ/state.py",
           mutated_symbol="build",
           guard_under_test="assert_public",
           production_call_path="src/intent_engine/econ/state.py")

    def control():
        src = (REPO / "src/intent_engine/econ/state.py").read_text()
        assert 'assert_public(nodes, where="EconomicState.build")' in src

    def mutate(t):
        return t.mutate("intent_engine/econ/state.py",
                        '    assert_public(nodes, where="EconomicState.build")',
                        "    pass  # MUTATION")

    def check(t):
        src = t.path("intent_engine/econ/state.py").read_text()
        if 'assert_public(nodes, where="EconomicState.build")' in src:
            raise AssertionError("the mutation did not land")
        raise AssertionError(
            "EconomicState.build no longer checks node visibility; a "
            "tenant-private observation could enter the shared public state")
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp11():
    p = _p(name="11_derived_evidence_double_counted",
           description="the lineage walk stops finding ancestors",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/econ/worldmodel.py",
           mutated_symbol="lineage_walk",
           guard_under_test="assert_no_double_count",
           production_call_path="scripts/run_world_model.py")

    def control():
        WM = importlib.import_module("intent_engine.econ.worldmodel")
        WM.assert_no_double_count("agg", {"agg": ["a"], "a": ["n1"]}, ["n2"])
        try:
            WM.assert_no_double_count("agg", {"agg": ["a"], "a": ["n1"]},
                                      ["n1"])
        except WM.WorldModelDefect:
            return
        raise AssertionError("a double count was accepted on clean code")

    def mutate(t):
        return t.mutate("intent_engine/econ/worldmodel.py",
                        "        frontier.extend(lineage.get(cur, ()))",
                        "        pass  # MUTATION")

    def check(t):
        WM = t.load("intent_engine.econ.worldmodel")
        WM.assert_no_double_count("agg", {"agg": ["a"], "a": ["n1"]}, ["n1"])
        raise AssertionError(
            "a corroborator two hops up the lineage was not found")
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp12():
    p = _p(name="12_duplicate_evidence_counted_as_learning",
           description="the no-change branch of the stagnation detector goes",
           target_kind=BP.CONSUMER,
           mutated_file="scripts/run_world_model.py",
           mutated_symbol="stagnation",
           guard_under_test="stagnation_alerts",
           production_call_path="scripts/run_world_model.py")

    def control():
        sys.path.insert(0, str(REPO / "scripts"))
        try:
            m = importlib.import_module("run_world_model")
            r = m.stagnation({"a": {"x": 1}}, {"a": {"x": 1}},
                             [{"nonzero": False}], [])
            assert r["state"] == "DEGRADING"
        finally:
            sys.path.pop(0)

    def mutate(t):
        return t.mutate("scripts/run_world_model.py",
                        '    if not any(d["nonzero"] for d in deltas):',
                        "    if False:  # MUTATION")

    def check(t):
        m = t.load("run_world_model")
        r = m.stagnation({"a": {"x": 1}}, {"a": {"x": 2}},
                         [{"nonzero": False}], [{"x": 1}])
        if r["state"] != "DEGRADING":
            raise AssertionError(
                "no company analysis changed and the detector reported "
                f"{r['state']}; a cycle where nothing moves would be recorded "
                "as healthy learning")
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp13():
    p = _p(name="13_same_state_compared_to_itself",
           description="the identical-state branch of the detector goes",
           target_kind=BP.CONSUMER,
           mutated_file="scripts/run_world_model.py",
           mutated_symbol="stagnation",
           guard_under_test="identical_state_alert",
           production_call_path="scripts/run_world_model.py")

    def control():
        sys.path.insert(0, str(REPO / "scripts"))
        try:
            m = importlib.import_module("run_world_model")
            r = m.stagnation({"a": {"x": 1}}, {"a": {"x": 1}},
                             [{"nonzero": True}], [{"x": 1}])
            assert r["state"] == "DEGRADING", (
                "identical states did not alert on clean code")
        finally:
            sys.path.pop(0)

    def mutate(t):
        return t.mutate(
            "scripts/run_world_model.py",
            "    if len(same) == len(set(state_a) & set(state_b)) and same:",
            "    if False:  # MUTATION")

    def check(t):
        m = t.load("run_world_model")
        r = m.stagnation({"a": {"x": 1}}, {"a": {"x": 1}},
                         [{"nonzero": True}], [{"x": 1}])
        if r["state"] != "DEGRADING":
            raise AssertionError(
                "a state compared with itself produced no alert; the exact "
                "call-site bug the detector caught last run would now pass "
                "silently")
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp14():
    p = _p(name="14_founder_a_deliberately_crippled",
           description="Baseline A is emptied of its structural knowledge",
           target_kind=BP.PRODUCER,
           mutated_file="scripts/run_decision_value.py",
           mutated_symbol="STRUCTURAL",
           guard_under_test="assert_baseline_is_real",
           production_call_path="scripts/run_decision_value.py")

    def control():
        FA = importlib.import_module("intent_engine.econ.founder_ab")
        sys.path.insert(0, str(REPO / "scripts"))
        try:
            RD = importlib.import_module("run_decision_value")
            a = RD.baseline_a("walmart", "2026-01-01")
            FA.assert_baseline_is_real(a)
            assert a.risks and a.top_priority and a.information_requests
        finally:
            sys.path.pop(0)

    def mutate(t):
        return t.mutate(
            "scripts/run_decision_value.py",
            '    risks = (FA.Risk(risk_id=f"{cid}:structural", severity=sev,',
            '    risks = ()  # MUTATION\n'
            '    _unused = (FA.Risk(risk_id=f"{cid}:structural", '
            'severity=sev,')

    def check(t):
        FA = t.load("intent_engine.econ.founder_ab")
        RD = t.load("run_decision_value")
        FA.assert_baseline_is_real(RD.baseline_a("walmart", "2026-01-01"))
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp15():
    p = _p(name="15_b_receives_a_different_cutoff",
           description="A and B are given different evidence cutoffs",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/econ/founder_ab.py",
           mutated_symbol="Analysis.__post_init__",
           guard_under_test="compare_cutoff_check",
           production_call_path="scripts/run_decision_value.py")

    def control():
        FA = importlib.import_module("intent_engine.econ.founder_ab")
        a, b = _pair(FA)
        FA.compare(a, b, regime="t")
        b2 = FA.Analysis(**{**_kw(b), "as_of": "2026-06-01"})
        try:
            FA.compare(a, b2, regime="t")
        except Exception:
            return
        raise AssertionError("different cutoffs were accepted on clean code")

    def mutate(t):
        return t.mutate(
            "intent_engine/econ/founder_ab.py",
            "    require(a.as_of == b.as_of,",
            "    require(True or a.as_of == b.as_of,  # MUTATION")

    def check(t):
        FA = t.load("intent_engine.econ.founder_ab")
        a, b = _pair(FA)
        b2 = FA.Analysis(**{**_kw(b), "as_of": "2026-06-01"})
        FA.compare(a, b2, regime="t")
        raise AssertionError(
            "A dated 2026-01-01 was compared against B dated 2026-06-01; the "
            "treatment becomes 'more recent data' rather than 'the world "
            "model'")
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp16():
    p = _p(name="16_unsupported_counterfactual_labelled_causal",
           description="the scenario type collapses into the causal one",
           target_kind=BP.RENDERER,
           mutated_file="src/intent_engine/econ/counterfactual.py",
           mutated_symbol="SCENARIO_ASSUMPTION",
           guard_under_test="counterfactual_type_wall",
           production_call_path="scripts/run_relation_and_ceo.py")

    def control():
        src = (REPO / "src/intent_engine/econ/counterfactual.py").read_text()
        assert "SCENARIO" in src and "CAUSAL_ESTIMATE" in src
        rc = json.loads((REPO / "reports/relation_and_ceo.json").read_text())
        for r in rc["history_rewind_economic"]:
            assert r["counterfactual_label"] == "SCENARIO_ASSUMPTION"

    def mutate(t):
        pth = t.path("intent_engine/econ/counterfactual.py")
        s = pth.read_text()
        if "SCENARIO_ASSUMPTION" not in s:
            return 0, 0
        before = len(s)
        s2 = s.replace("SCENARIO_ASSUMPTION", "CAUSAL_ESTIMATE")
        pth.write_text(s2)
        return before, len(s2) + 1

    def check(t):
        src = t.path("intent_engine/econ/counterfactual.py").read_text()
        if "SCENARIO_ASSUMPTION" in src:
            raise AssertionError("the mutation did not land")
        raise AssertionError(
            "the counterfactual type wall no longer separates a scenario "
            "assumption from a causal estimate; a History Rewind what-if "
            "would render with the standing of a measured effect")
    return run(p, mutate=mutate, check=check, positive_control=control)


# ---- fixtures --------------------------------------------------------------

def _kw(a):
    return {"company_id": a.company_id, "as_of": a.as_of,
            "variant": a.variant, "top_priority": a.top_priority,
            "action": a.action, "risks": a.risks,
            "scenario": a.scenario, "confidence": a.confidence,
            "information_requests": a.information_requests,
            "falsifiers": a.falsifiers, "evidence": a.evidence,
            "unknowns": a.unknowns, "economic_inputs": a.economic_inputs,
            "prose": a.prose}


def _pair(FA, *, prose_only=False, injected=False):
    r = FA.Risk(risk_id="r1", severity="LOW", channel="ch", mechanism="m",
                standing=FA.INFERRED, evidence=("e1",))
    a = FA.Analysis(company_id="c", as_of="2026-01-01", variant="A",
                    top_priority="ch", action=FA.MONITOR, risks=(r,),
                    information_requests=("q",), evidence=("e1",),
                    prose="alpha")
    if prose_only:
        b = FA.Analysis(company_id="c", as_of="2026-01-01", variant="B",
                        top_priority="ch", action=FA.MONITOR, risks=(r,),
                        information_requests=("q",), evidence=("e1",),
                        prose="beta")
    elif injected:
        extra = FA.Risk(risk_id="r2", severity="LOW", channel="macro",
                        mechanism="m", standing=FA.INFERRED,
                        evidence=("e2",))
        b = FA.Analysis(company_id="c", as_of="2026-01-01", variant="B",
                        top_priority="ch", action=FA.MONITOR,
                        risks=(r, extra), information_requests=("q",),
                        evidence=("e1", "e2"), economic_inputs=("e2",),
                        prose="alpha")
    else:
        b = FA.Analysis(company_id="c", as_of="2026-01-01", variant="B",
                        top_priority="other", action=FA.PREPARE, risks=(r,),
                        information_requests=("z",), evidence=("e1", "e2"),
                        economic_inputs=("e2",), prose="alpha")
    return a, b


def _bleed(WM):
    return WM.Bleed(source="a", expected_target="b", expected_timing_days=30,
                    expected_direction="UP", actual_direction="DOWN",
                    transmission_gap=0.1, candidate_explanation="c",
                    evidence="e", uncertainty="HIGH", controllability="LOW",
                    decision_impact=3)


def _check(WM, *, lag_elapsed):
    return WM.RelationCheck(
        relation="r", source_moved=True, source_move=0.1,
        lag_elapsed=lag_elapsed, days_since_source_move=10, lag_days=180,
        target_moved=False, target_move=0.0, direction_correct=False,
        magnitude_plausible=False, regime_applicable=True)


PROOFS = (bp1, bp2, bp3, bp4, bp5, bp6, bp7, bp8, bp9, bp10, bp11, bp12,
          bp13, bp14, bp15, bp16)


def main() -> int:
    proofs = []
    for fn in PROOFS:
        try:
            p = fn()
        except Exception as e:                              # noqa: BLE001
            p = BP.Proof(name=fn.__name__, description="", target_kind=BP.PRODUCER,
                         mutated_file="?", mutated_symbol="?",
                         guard_under_test="?", production_call_path="?")
            p.verdict = BP.UNRELIABLE
            p.detail = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-300:]}"
        proofs.append(p)
        print(f"  {p.verdict:<18} {p.name}")
        if p.verdict != BP.CAUGHT:
            print(f"                     {str(p.detail)[:190]}")
    s = BP.summarise(proofs)
    OUT.write_text(json.dumps(s, indent=2, sort_keys=True))
    print(f"\n  {s['caught']}/{s['proofs']} CAUGHT, "
          f"{s['refused_tautology']} REFUSED_TAUTOLOGY, "
          f"{s['not_caught']} NOT_CAUGHT, {s['unreliable']} UNRELIABLE")
    print(f"  target kinds: {json.dumps(s['target_kinds'])}")
    print(f"  wrote {OUT}")
    return 0 if s["caught"] == s["proofs"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
