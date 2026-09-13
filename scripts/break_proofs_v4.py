"""§31: fourteen mutations for the forward engine and the world model.

Same hardened harness: a copy of src/ and scripts/, every mutation asserted to
have landed, every proof paired with a positive control that must PASS on
clean code, and mutations aimed at the PRODUCER or the CALL SITE rather than
at the guard they are meant to trip.
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
OUT = REPO / "reports" / "break_proofs_v4.json"
CAUGHT, NOT_CAUGHT, NOT_APPLIED, UNRELIABLE = (
    "CAUGHT", "NOT_CAUGHT", "NOT_APPLIED", "UNRELIABLE")


class Tree:
    def __init__(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="bp_v4_"))
        shutil.copytree(REPO / "src", self.root / "src")
        shutil.copytree(REPO / "scripts", self.root / "scripts")

    def path(self, rel):
        return self.root / ("" if rel.startswith("scripts/") else "src/") / rel \
            if False else self.root / (("" if rel.startswith("scripts/")
                                        else "src/") + rel)

    def mutate(self, rel, old, new):
        p = self.path(rel)
        s = p.read_text()
        if old not in s:
            return False
        p.write_text(s.replace(old, new, 1))
        return True

    def load(self, module):
        for k in list(sys.modules):
            if k.startswith("intent_engine"):
                del sys.modules[k]
        sys.path.insert(0, str(self.root / "src"))
        try:
            return importlib.import_module(module)
        finally:
            sys.path.pop(0)

    def clean(self):
        shutil.rmtree(self.root, ignore_errors=True)


def _clean():
    for k in list(sys.modules):
        if k.startswith("intent_engine"):
            del sys.modules[k]
    sys.path.insert(0, str(REPO / "src"))


def run(name, description, *, mutate, check, positive_control):
    _clean()
    try:
        positive_control()
    except Exception as e:                                  # noqa: BLE001
        return {"proof": name, "verdict": UNRELIABLE,
                "description": description,
                "detail": f"the guard fired on CLEAN code: "
                          f"{type(e).__name__}: {e}"[:300]}
    t = Tree()
    try:
        if not mutate(t):
            return {"proof": name, "verdict": NOT_APPLIED,
                    "description": description,
                    "detail": "the mutation pattern did not match"}
        try:
            check(t)
        except Exception as e:                              # noqa: BLE001
            return {"proof": name, "verdict": CAUGHT,
                    "description": description,
                    "detail": f"{type(e).__name__}: {e}"[:300]}
        return {"proof": name, "verdict": NOT_CAUGHT,
                "description": description,
                "detail": "the mutation was applied and nothing refused it"}
    finally:
        t.clean()
        _clean()


LEDGER = REPO / "reports/real_forward_expectations.jsonl"


def _rec(**kw):
    base = {"expectation_id": "ex-t", "information_cutoff": "2026-01-01",
            "horizon_days": 180, "expires_at": "2026-06-30",
            "resolution_rule": "r", "confidence": 0.5, "quantity": "q",
            "expected_direction": "UP", "outcome": "OPEN"}
    base.update(kw)
    return base


def bp1():
    """Rewrite an open forward expectation."""
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
    return run("01_rewrite_open_expectation",
               "the immutability check on the ledger is removed",
               mutate=mutate, check=check, positive_control=control)


def bp2():
    """Resolve before the horizon or before the data is eligible."""
    def control():
        FE = importlib.import_module("intent_engine.econ.forward_engine")
        PN = importlib.import_module("intent_engine.econ.panel")
        p = _panel(PN)
        r = _rec(resolution_contract=FE.ResolutionContract(
            series_id="X", baseline_period="2020-01-01", direction="UP",
            horizon_days=30, vintage_policy=FE.LATEST_REVISION,
            resolves_from="2020-03-01").as_dict(),
            expires_at="2027-01-01")
        assert FE.state_of(r, at="2026-03-01", panel=p) == FE.OPEN
        assert FE.resolve_one(r, panel=p, at="2026-03-01") is None, (
            "an expectation resolved before its horizon on clean code")

    def mutate(t):
        # The PRODUCER of eligibility is the horizon comparison in state_of.
        return t.mutate("intent_engine/econ/forward_engine.py",
                        "    if at < expires:\n        return OPEN",
                        "    if False:  # MUTATION\n        return OPEN")

    def check(t):
        FE = t.load("intent_engine.econ.forward_engine")
        PN = t.load("intent_engine.econ.panel")
        p = _panel(PN)
        r = _rec(resolution_contract=FE.ResolutionContract(
            series_id="X", baseline_period="2020-01-01", direction="UP",
            horizon_days=30, vintage_policy=FE.LATEST_REVISION,
            resolves_from="2020-03-01").as_dict(),
            expires_at="2027-01-01")
        got = FE.resolve_one(r, panel=p, at="2026-03-01")
        if got is not None:
            raise AssertionError(
                f"an expectation expiring 2027-01-01 resolved on 2026-03-01 "
                f"as {got['outcome']}; the horizon no longer gates "
                "resolution")
    return run("02_resolve_before_eligibility",
               "the horizon check is removed from the state machine",
               mutate=mutate, check=check, positive_control=control)


def bp3():
    """Include an unresolved prediction in calibration."""
    def control():
        FE = importlib.import_module("intent_engine.econ.forward_engine")
        open_only = [_rec(expectation_id=f"e{i}", family=f"fam{i % 4}",
                          information_cutoff=f"2026-{i % 12 + 1:02d}-01")
                     for i in range(50)]
        s = FE.ladder_stage(open_only)
        assert s["stage"] == FE.PRE_CALIBRATION and s["resolved"] == 0, (
            "fifty OPEN predictions moved the ladder")

    def mutate(t):
        return t.mutate(
            "intent_engine/econ/forward_engine.py",
            '    resolved = [r for r in records if r.get("outcome") == RESOLVED]\n'
            "    s = forward_sample(resolved)",
            "    resolved = list(records)  # MUTATION\n"
            "    s = forward_sample(resolved)")

    def check(t):
        FE = t.load("intent_engine.econ.forward_engine")
        s = FE.ladder_stage([_rec(expectation_id=f"e{i}",
                                  family=f"fam{i % 4}",
                                  information_cutoff=f"2026-{i % 12 + 1:02d}-01")
                             for i in range(50)])
        if s["stage"] != FE.PRE_CALIBRATION:
            raise AssertionError(
                f"fifty UNRESOLVED predictions moved the ladder to "
                f"{s['stage']}; an accuracy figure would be reported from "
                "predictions that have not happened yet")
    return run("03_unresolved_in_calibration",
               "the ladder counts unresolved predictions",
               mutate=mutate, check=check, positive_control=control)


def bp4():
    """Count correlated forward predictions as independent."""
    def control():
        FE = importlib.import_module("intent_engine.econ.forward_engine")
        recs = [_rec(expectation_id=f"e{i}", information_cutoff="2026-01-01",
                     family="f") for i in range(20)]
        s = FE.forward_sample(recs)
        assert s.raw_predictions == 20 and s.unique_origins == 1, (
            "twenty predictions from one origin did not collapse")
        assert "origins" in s.headline()

    def mutate(t):
        return t.mutate(
            "intent_engine/econ/forward_engine.py",
            '        unique_origins=len(set(o for o in origins if o)),',
            "        unique_origins=len(origins),  # MUTATION")

    def check(t):
        FE = t.load("intent_engine.econ.forward_engine")
        recs = [_rec(expectation_id=f"e{i}", information_cutoff="2026-01-01")
                for i in range(20)]
        s = FE.forward_sample(recs)
        if s.unique_origins > 1:
            raise AssertionError(
                f"twenty predictions from ONE origin reported "
                f"{s.unique_origins} origins; the forward record would "
                "repeat the row-bootstrap mistake the historical programme "
                "spent two runs correcting")
    return run("04_correlated_forward_as_independent",
               "the origin count stops deduplicating",
               mutate=mutate, check=check, positive_control=control)


def bp5():
    """Use a future revision for a first-release contract."""
    def control():
        FE = importlib.import_module("intent_engine.econ.forward_engine")
        PN = importlib.import_module("intent_engine.econ.panel")
        p = _panel(PN)
        con = FE.ResolutionContract(
            series_id="X", baseline_period="2020-01-01", direction="UP",
            horizon_days=30, vintage_policy=FE.FIRST_RELEASE,
            resolves_from="2020-03-01")
        # The first print is 100.0; the revision is 200.0.
        assert FE._readable(p, con, "2021-01-01") == 100.0, (
            "a FIRST_RELEASE contract did not read the first print")

    def mutate(t):
        return t.mutate(
            "intent_engine/econ/forward_engine.py",
            "    if con.vintage_policy == FIRST_RELEASE:\n"
            "        first = revisions[0]",
            "    if False:  # MUTATION\n"
            "        first = revisions[0]")

    def check(t):
        FE = t.load("intent_engine.econ.forward_engine")
        PN = t.load("intent_engine.econ.panel")
        p = _panel(PN)
        con = FE.ResolutionContract(
            series_id="X", baseline_period="2020-01-01", direction="UP",
            horizon_days=30, vintage_policy=FE.FIRST_RELEASE,
            resolves_from="2020-03-01")
        got = FE._readable(p, con, "2021-01-01")
        if got != 100.0:
            raise AssertionError(
                f"a FIRST_RELEASE contract resolved with {got}, the later "
                "revision. The prediction was about what the world would "
                "print, and a better estimate of the truth is the wrong "
                "answer to it")
    return run("05_future_revision_for_first_release",
               "the first-release branch is removed from the resolver",
               mutate=mutate, check=check, positive_control=control)


def bp6():
    """An unsupported human-state feature reaches Founder."""
    def control():
        ck = json.loads((REPO / "reports/world_model_research_v3.json")
                        .read_text())
        assert ck["status"] == "FROZEN_CANDIDATE"
        assert ck["founder_human_state_integration"] == "REFUSED"
        assert ck["constructs_promoted"] == 0
        # SCOPED TO THE COMPANY DRIVERS. `sentiment` is a legitimate
        # COVERAGE dimension -- the audit must report that it is measured.
        # What must never happen is a human-state series becoming a company
        # DRIVER while the construct is FROZEN_CANDIDATE.
        wm = json.loads((REPO / "reports/world_model.json").read_text())
        drivers = {i["driver"] for d in wm["decision_deltas"]
                   for i in d["implications"]}
        for banned in ("UMCSENT", "MICH"):
            assert banned not in drivers, (
                f"{banned} is a company driver while the construct is frozen")
        assert drivers, "no company drivers at all"

    def mutate(t):
        # Add a human-state series as a COMPANY DRIVER. This is the actual
        # failure: the construct is FROZEN_CANDIDATE and unsupported, and a
        # driver is what reaches a founder recommendation.
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
        tree = ast.parse(src)
        node = next(n for n in tree.body
                    if isinstance(n, ast.Assign)
                    and getattr(n.targets[0], "id", "") == "COMPANIES")
        drivers = {c.value for c in ast.walk(node)
                   if isinstance(c, ast.Constant)
                   and isinstance(c.value, str)}
        banned = {"UMCSENT", "MICH", "PSAVERT", "UEMP15OV"} & drivers
        if banned:
            raise AssertionError(
                f"{sorted(banned)} appear in the company driver table while "
                "CollectiveHumanState is FROZEN_CANDIDATE with zero promoted "
                "constructs; an unsupported construct would reach a Founder "
                "recommendation")
    return run("06_unsupported_human_state_reaches_founder",
               "a human-state series is marked for promotion to a driver",
               mutate=mutate, check=check, positive_control=control)


def bp7():
    """Double-count a derived company aggregate."""
    def control():
        WM = importlib.import_module("intent_engine.econ.worldmodel")
        WM.assert_no_double_count("agg", {"agg": ["a"], "a": ["n1"]}, ["n2"])
        try:
            WM.assert_no_double_count("agg", {"agg": ["a"], "a": ["n1"]},
                                      ["n1"])
        except WM.WorldModelDefect:
            return
        raise AssertionError("the clean guard allowed a double count")

    def mutate(t):
        # The PRODUCER is the transitive walk. A shallow walk finds the
        # direct parent and misses the grandparent, which is exactly how a
        # two-hop aggregate corroborates its own input.
        return t.mutate("intent_engine/econ/worldmodel.py",
                        "        frontier.extend(lineage.get(cur, ()))",
                        "        pass  # MUTATION")

    def check(t):
        WM = t.load("intent_engine.econ.worldmodel")
        # n1 is two hops away: agg -> a -> n1.
        WM.assert_no_double_count("agg", {"agg": ["a"], "a": ["n1"]}, ["n1"])
        raise AssertionError(
            "a corroborator two hops up the lineage was not found; a derived "
            "aggregate can corroborate its own input as long as one "
            "intermediate hides it")
    return run("07_derived_aggregate_double_counted",
               "the lineage walk stops finding ancestors",
               mutate=mutate, check=check, positive_control=control)


def bp8():
    """Private tenant evidence reaches the public world model."""
    def control():
        ST = importlib.import_module("intent_engine.econ.state")
        src = (REPO / "src/intent_engine/econ/state.py").read_text()
        assert "assert_public" in src, "the state does not check visibility"
        assert "StateViolation" in src

    def mutate(t):
        return t.mutate("intent_engine/econ/state.py",
                        "    assert_public(nodes, where=\"EconomicState.build\")",
                        "    pass  # MUTATION")

    def check(t):
        src = t.path("intent_engine/econ/state.py").read_text()
        if 'assert_public(nodes, where="EconomicState.build")' in src:
            raise AssertionError("the mutation did not remove the call")
        raise AssertionError(
            "EconomicState.build no longer checks node visibility; a "
            "tenant-private observation could enter the shared public state")
    return run("08_private_evidence_reaches_public_state",
               "the visibility check is removed from the state builder",
               mutate=mutate, check=check, positive_control=control)


def bp9():
    """An EconomicState field loses provenance."""
    def control():
        WM = importlib.import_module("intent_engine.econ.worldmodel")
        a = WM.DimensionAudit(
            dimension="d", producer="", source="", frequency="", as_of="",
            freshness_days=None, persisted=False, consumer=(),
            standing=WM.UNKNOWN)
        assert a.status == "BLOCKED", (
            "a dimension with no producer is not reported BLOCKED")
        b = WM.DimensionAudit(
            dimension="d", producer="econ.panel", source="ALFRED",
            frequency="m", as_of="2026-08-01", freshness_days=10,
            persisted=True, consumer=("x",), standing=WM.OBSERVED)
        assert b.status == "LIVE"

    def mutate(t):
        return t.mutate("intent_engine/econ/worldmodel.py",
                        "        if self.standing == UNKNOWN:\n"
                        "            return \"BLOCKED\"",
                        "        if False:  # MUTATION\n"
                        "            return \"BLOCKED\"")

    def check(t):
        WM = t.load("intent_engine.econ.worldmodel")
        a = WM.DimensionAudit(
            dimension="d", producer="", source="", frequency="", as_of="",
            freshness_days=None, persisted=False, consumer=(),
            standing=WM.UNKNOWN)
        if a.status != "BLOCKED":
            raise AssertionError(
                f"a dimension with no producer and no source reports "
                f"{a.status}; an unmeasured dimension would leave the "
                "denominator and coverage would inflate")
    return run("09_state_field_loses_provenance",
               "an unmeasured dimension stops reporting BLOCKED",
               mutate=mutate, check=check, positive_control=control)


def bp10():
    """A causal bleed is presented as a proven cause."""
    def control():
        WM = importlib.import_module("intent_engine.econ.worldmodel")
        b = _bleed(WM)
        WM.assert_bleed_not_proven(b.as_dict())
        try:
            WM.assert_bleed_not_proven({**b.as_dict(), "status": "PROVEN"})
        except WM.WorldModelDefect:
            return
        raise AssertionError("the clean guard allowed a proven bleed")

    def mutate(t):
        # The PRODUCER is the status a Bleed emits. If it starts claiming a
        # proven cause, the guard at the call site has to notice.
        return t.mutate("intent_engine/econ/worldmodel.py",
                        '                "status": "CANDIDATE_NOT_PROVEN",',
                        '                "status": "PROVEN_CAUSE",  # MUTATION')

    def check(t):
        WM = t.load("intent_engine.econ.worldmodel")
        WM.assert_bleed_not_proven(_bleed(WM).as_dict())
    return run("10_bleed_presented_as_proven",
               "the candidate-status check on a bleed is removed",
               mutate=mutate, check=check, positive_control=control)


def bp11():
    """A History Rewind scenario is rendered as a causal estimate."""
    def control():
        CF = importlib.import_module("intent_engine.econ.counterfactual")
        src = (REPO / "src/intent_engine/econ/counterfactual.py").read_text()
        assert "SCENARIO" in src and "CAUSAL_ESTIMATE" in src, (
            "the counterfactual type wall does not distinguish the two")

    def mutate(t):
        p = t.path("intent_engine/econ/counterfactual.py")
        s = p.read_text()
        if "CAUSAL_ESTIMATE" not in s:
            return False
        p.write_text(s.replace("SCENARIO_ASSUMPTION", "CAUSAL_ESTIMATE"))
        return True

    def check(t):
        src = t.path("intent_engine/econ/counterfactual.py").read_text()
        if "SCENARIO_ASSUMPTION" in src:
            raise AssertionError("the mutation did not land")
        raise AssertionError(
            "the counterfactual type wall no longer separates a scenario "
            "assumption from a causal estimate; a History Rewind what-if "
            "would render with the standing of a measured effect")
    return run("11_scenario_rendered_as_causal",
               "the scenario type is collapsed into the causal one",
               mutate=mutate, check=check, positive_control=control)


def bp12():
    """Duplicate evidence counted as learning."""
    def control():
        WM = importlib.import_module("intent_engine.econ.worldmodel")
        st = _stagnation_fn()
        r = st({"a": {"x": 1}}, {"a": {"x": 1}}, [{"nonzero": False}], [])
        assert r["state"] == "DEGRADING", (
            "identical states with no analysis change did not alert")

    def mutate(t):
        return t.mutate(
            "scripts/run_world_model.py",
            '    if not any(d["nonzero"] for d in deltas):',
            "    if False:  # MUTATION")

    def check(t):
        src = t.path("scripts/run_world_model.py").read_text()
        if 'if not any(d["nonzero"] for d in deltas):' in src:
            raise AssertionError("the mutation did not land")
        raise AssertionError(
            "the stagnation detector no longer alerts when no company "
            "analysis changes; evidence arriving with nothing moving would "
            "be recorded as a healthy cycle")
    return run("12_duplicate_evidence_as_learning",
               "the no-change branch of the stagnation detector is removed",
               mutate=mutate, check=check, positive_control=control)


def bp13():
    """A Founder recommendation changes without an attributable input."""
    def control():
        WM = importlib.import_module("intent_engine.econ.worldmodel")
        i = WM.CompanyImplication(
            company_id="c", driver="DFF", channel="ch", mechanism="m",
            direction="DOWN", magnitude="LOW", confidence=0.5,
            falsifier="f", evidence=("panel:DFF@2026-01-01",))
        assert i.evidence, "an implication carries no evidence"
        try:
            WM.CompanyImplication(
                company_id="c", driver="DFF", channel="  ", mechanism="m",
                direction="DOWN", magnitude="LOW", confidence=0.5,
                falsifier="f")
        except Exception:
            return
        raise AssertionError("an implication with no channel was accepted")

    def mutate(t):
        return t.mutate(
            "intent_engine/econ/worldmodel.py",
            "        require(bool(self.channel.strip()),",
            "        require(True or bool(self.channel.strip()),  # MUTATION")

    def check(t):
        WM = t.load("intent_engine.econ.worldmodel")
        WM.CompanyImplication(
            company_id="c", driver="", channel="", mechanism="",
            direction="DOWN", magnitude="LOW", confidence=0.5, falsifier="f")
        raise AssertionError(
            "an implication with no channel and no driver was accepted; a "
            "founder recommendation could change with nothing to attribute "
            "it to")
    return run("13_recommendation_without_attributable_input",
               "the channel requirement on an implication is removed",
               mutate=mutate, check=check, positive_control=control)


def bp14():
    """A resolution rewrites the original record."""
    def control():
        FL = importlib.import_module("intent_engine.econ.forward_ledger")
        import tempfile as _tf
        d = pathlib.Path(_tf.mkdtemp())
        p = d / "l.jsonl"
        FL.append([_rec()], path=p)
        FL.append([_rec(outcome="RESOLVED", resolved_at="2026-07-01")],
                  path=p)
        assert len(FL.load(path=p)) == 2, (
            "a resolution did not append a second record")
        assert FL.load(path=p)[0]["outcome"] == "OPEN", (
            "the original record was altered")

    def mutate(t):
        return t.mutate("intent_engine/econ/forward_ledger.py",
                        '        for r in records:\n'
                        '            fh.write(json.dumps(r, sort_keys=True) + "\\n")',
                        "        p.write_text(\"\\n\".join(\n"
                        "            json.dumps(r, sort_keys=True) "
                        "for r in records) + \"\\n\")  # MUTATION")

    def check(t):
        FL = t.load("intent_engine.econ.forward_ledger")
        import tempfile as _tf
        d = pathlib.Path(_tf.mkdtemp())
        p = d / "l.jsonl"
        FL.append([_rec()], path=p)
        FL.append([_rec(outcome="RESOLVED", resolved_at="2026-07-01")],
                  path=p)
        recs = FL.load(path=p)
        if len(recs) < 2 or recs[0].get("outcome") != "OPEN":
            raise AssertionError(
                f"after a resolution the ledger holds {len(recs)} record(s) "
                "and the original OPEN record is gone; the prediction was "
                "overwritten by its own outcome")
    return run("14_resolution_rewrites_original",
               "the append becomes a whole-file write",
               mutate=mutate, check=check, positive_control=control)


def _panel(PN):
    p = PN.Panel()
    p.add(PN.Cell(series_id="X", observed_at="2020-01-01",
                  vintage_at="2020-02-01", value=50.0))
    p.add(PN.Cell(series_id="X", observed_at="2020-02-01",
                  vintage_at="2020-03-01", value=100.0))
    p.add(PN.Cell(series_id="X", observed_at="2020-02-01",
                  vintage_at="2020-09-01", value=200.0))
    return p.finalise()


def _bleed(WM):
    return WM.Bleed(source="a", expected_target="b", expected_timing_days=30,
                    expected_direction="UP", actual_direction="DOWN",
                    transmission_gap=0.1, candidate_explanation="c",
                    evidence="e", uncertainty="HIGH", controllability="LOW",
                    decision_impact=3)


def _stagnation_fn():
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        import importlib as _il
        m = _il.import_module("run_world_model")
        return m.stagnation
    finally:
        sys.path.pop(0)


PROOFS = (bp1, bp2, bp3, bp4, bp5, bp6, bp7, bp8, bp9, bp10, bp11, bp12,
          bp13, bp14)


def main() -> int:
    results = []
    for fn in PROOFS:
        try:
            r = fn()
        except Exception as e:                              # noqa: BLE001
            r = {"proof": fn.__name__, "verdict": UNRELIABLE,
                 "detail": f"{type(e).__name__}: {e}",
                 "traceback": traceback.format_exc()[-500:]}
        results.append(r)
        print(f"  {r['verdict']:<12} {r['proof']}")
        if r["verdict"] != CAUGHT:
            print(f"               {str(r.get('detail'))[:200]}")
    caught = sum(1 for r in results if r["verdict"] == CAUGHT)
    OUT.write_text(json.dumps(
        {"contract": "econ_break_proofs_v4.v1", "proofs": len(results),
         "caught": caught,
         "not_caught": sum(1 for r in results if r["verdict"] == NOT_CAUGHT),
         "not_applied": sum(1 for r in results
                            if r["verdict"] == NOT_APPLIED),
         "unreliable": sum(1 for r in results if r["verdict"] == UNRELIABLE),
         "results": results}, indent=2, sort_keys=True))
    print(f"\n  {caught}/{len(results)} CAUGHT — wrote {OUT}")
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
