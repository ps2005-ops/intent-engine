"""§30: twelve mutations for the V3 run, on the hardened harness.

Same discipline as `break_proofs_power.py`: mutations are applied to a COPY of
src/ and scripts/, every mutation must actually change the text, every proof
carries a POSITIVE CONTROL that must pass on clean code, and a mutation
targets the PRODUCER or the CALL SITE rather than the guard it is meant to
trip.
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
OUT = REPO / "reports" / "break_proofs_v3.json"
CAUGHT, NOT_CAUGHT, NOT_APPLIED, UNRELIABLE = (
    "CAUGHT", "NOT_CAUGHT", "NOT_APPLIED", "UNRELIABLE")


class Tree:
    def __init__(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="bp_v3_"))
        shutil.copytree(REPO / "src", self.root / "src")
        shutil.copytree(REPO / "scripts", self.root / "scripts")

    def path(self, rel):
        root = "" if rel.startswith("scripts/") else "src/"
        return self.root / (root + rel)

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
                    "detail": "the mutation pattern did not match; the code "
                              "it targets has moved"}
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


# =============================================================================

def bp1():
    """Derive origins from a '-15' string match, at the call site."""
    def control():
        # READ THE CODE, NOT THE PROSE. `declared_origins` documents the
        # defect it replaced, so the old pattern appears in its docstring.
        # A guard that greps the whole file matches the comment explaining
        # the bug and reports the bug as present.
        import ast
        src = (REPO / "scripts/run_experiment.py").read_text()
        tree = ast.parse(src)
        main = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        body = ast.dump(main)
        assert "declared_origins" in body, (
            "main() does not read the declared grid")
        assert "'-15'" not in body and '"-15"' not in body, (
            "main() still pattern-matches a date suffix")

    def mutate(t):
        return t.mutate(
            "scripts/run_experiment.py",
            "    origins = declared_origins()",
            "    origins = sorted({c.vintage_at for cs in "
            "panel.cells.values() for c in cs})\n"
            "    origins = [o for o in origins if o.endswith('-15')]  "
            "# MUTATION")

    def check(t):
        src = t.path("scripts/run_experiment.py").read_text()
        if "declared_origins()" in src.split("def main")[-1]:
            raise AssertionError("the mutation did not land in main()")
        raise AssertionError(
            "the runner derives its origin grid from a date suffix again; "
            "one quarterly series' release calendar would set the sampling "
            "grid, as it did when 344 origins appeared where 115 were "
            "planned")
    return run("01_origins_from_string_match",
               "the origin grid is inferred from a date suffix",
               mutate=mutate, check=check, positive_control=control)


def bp2():
    """Overwrite the vintage panel with latest-revised values."""
    def control():
        PN = importlib.import_module("intent_engine.econ.panel")
        p = PN.Panel()
        p.add(PN.Cell(series_id="PSAVERT", observed_at="2008-06-01",
                      vintage_at="2008-08-15", value=2.5,
                      revision_state=PN.PUBLISHER_VINTAGE))
        p.finalise()
        p.assert_no_assumed_lag(["PSAVERT"])

    def mutate(t):
        return t.mutate("scripts/acquire_panel.py",
                        "    panel.assert_no_assumed_lag(revising)",
                        "    pass  # MUTATION")

    def check(t):
        src = t.path("scripts/acquire_panel.py").read_text()
        if "assert_no_assumed_lag" in src:
            raise AssertionError("the mutation did not remove the call")
        raise AssertionError(
            "the panel builder no longer checks that a revising series "
            "carries only publisher vintages; today's value under a "
            "historical release date would ship again")
    return run("02_panel_overwritten_with_revised_values",
               "the assumed-lag check is removed from the panel builder",
               mutate=mutate, check=check, positive_control=control)


def bp3():
    """Drop one same-kind instrument silently."""
    def control():
        EX = importlib.import_module("intent_engine.econ.experiment")
        SER = importlib.import_module("intent_engine.econ.series")
        live = [s.key for s in SER.BEHAVIOURAL
                if s.availability == SER.LIVE
                and "superseded" not in (s.reason or "").lower()]
        EX.assert_all_live_instruments_present(live, live)
        # UEMP15OV and U6RATE share the kind `underemployment`: a kind-keyed
        # dict would keep exactly one of them.
        kinds = [s.kind for s in SER.BEHAVIOURAL
                 if s.availability == SER.LIVE]
        assert len(kinds) > len(set(kinds)), (
            "no kind has two live series, so this proof cannot fire")

    def mutate(t):
        return t.mutate("intent_engine/econ/series.py",
                        "BEHAVIOURAL: Tuple[SeriesSpec, ...] = (",
                        "def _collapse(x):  # MUTATION\n"
                        "    return tuple({s.kind: s for s in x}.values())\n\n"
                        "BEHAVIOURAL: Tuple[SeriesSpec, ...] = (")

    def check(t):
        EX = t.load("intent_engine.econ.experiment")
        SER = t.load("intent_engine.econ.series")
        live = [s for s in SER.BEHAVIOURAL if s.availability == SER.LIVE
                and "superseded" not in (s.reason or "").lower()]
        collapsed = sorted({s.kind: s.key for s in live}.values())
        EX.assert_all_live_instruments_present(
            collapsed, sorted(s.key for s in live))
    return run("03_drop_same_kind_instrument",
               "a kind-keyed dict keeps one series per kind",
               mutate=mutate, check=check, positive_control=control)


def bp4():
    """Pool heterogeneous target families into one baseline."""
    def control():
        src = (REPO / "scripts/run_v2_experiment.py").read_text()
        assert "def family_ladder" in src, "there is no per-family ladder"
        body = src[src.index("def family_ladder"):]
        assert "for fid, frows in sorted(by_family.items()):" in body, (
            "the ladder does not iterate families")

    def mutate(t):
        return t.mutate(
            "scripts/run_v2_experiment.py",
            "    for fid, frows in sorted(by_family.items()):\n"
            "        folds = BL.make_folds(frows, folds=FOLDS, "
            "embargo_days=EMBARGO_DAYS)\n"
            "        if not folds:\n"
            "            continue\n"
            "        target_series = PR.BY_ID[fid].target_series",
            "    for fid, frows in [(\"ALL\", rows)]:  # MUTATION\n"
            "        folds = BL.make_folds(frows, folds=FOLDS, "
            "embargo_days=EMBARGO_DAYS)\n"
            "        if not folds:\n"
            "            continue\n"
            "        target_series = \"\"")

    def check(t):
        src = t.path("scripts/run_v2_experiment.py").read_text()
        if '[("ALL", rows)]' not in src.replace("\\", ""):
            raise AssertionError("the mutation did not land")
        raise AssertionError(
            "the baseline ladder is scored once across every family; with "
            "base rates from 0.28 to 0.92 no single fit can represent them "
            "and the gate would measure the harness")
    return run("04_pooled_family_baseline",
               "the ladder is scored once across every family",
               mutate=mutate, check=check, positive_control=control)


def bp5():
    """Treat one episode as many."""
    def control():
        EPI = importlib.import_module("intent_engine.econ.episodes")
        e = _eps(EPI)
        EPI.assert_no_artificial_split([e[0], e[2]])
        try:
            EPI.assert_no_artificial_split([e[0], e[1]])
        except EPI.EpisodeSplitRefused:
            return
        raise AssertionError("the clean guard did not refuse a split")

    def mutate(t):
        return t.mutate("intent_engine/econ/episodes.py",
                        "NORMALISATION_ORIGINS = 6",
                        "NORMALISATION_ORIGINS = 0  # MUTATION")

    def check(t):
        EPI = t.load("intent_engine.econ.episodes")
        EPI.assert_no_artificial_split(_eps(EPI)[:2])
        raise AssertionError(
            "two episodes two months apart were accepted as separate events")
    return run("05_one_episode_as_many",
               "the normalisation window is set to zero",
               mutate=mutate, check=check, positive_control=control)


def bp6():
    """Relative change where the denominator crosses zero."""
    def control():
        EX = importlib.import_module("intent_engine.econ.experiment")
        hist = [("p", 0.0)] * 13 + [("q", -1.0)]
        assert EX.change("PSAVERT", hist, 12) == -1.0, (
            "a percentage-point series did not use a difference")

    def mutate(t):
        return t.mutate(
            "intent_engine/econ/release.py",
            "def is_percentage_point(series_id: str) -> bool:\n"
            "    return series_id in PERCENTAGE_POINT_SERIES",
            "def is_percentage_point(series_id: str) -> bool:\n"
            "    return False  # MUTATION")

    def check(t):
        EX = t.load("intent_engine.econ.experiment")
        hist = [("p", 0.0)] * 13 + [("q", -1.0)]
        if EX.change("PSAVERT", hist, 12) is None:
            raise AssertionError(
                "the saving rate's change became undefined at a zero base; "
                "the series would silently leave the block again")
    return run("06_relative_change_across_zero",
               "percentage-point series lose their arithmetic difference",
               mutate=mutate, check=check, positive_control=control)


def bp7():
    """Use the row interval for an episode-level verdict."""
    def control():
        INC = importlib.import_module("intent_engine.econ.incremental")
        diffs = [0.02] * 40 + [-0.01] * 40
        clusters = ([f"2008-{m:02d}-15" for m in range(1, 13)] * 4)[:80]
        rlo, rhi, _rp = INC._bootstrap_ci(diffs, seed=1)
        elo, ehi, _ep, k = INC._episode_bootstrap_ci(diffs, clusters, seed=1)
        assert k == 1 and elo is None, (
            "one contiguous block should yield no episode interval")
        assert rhi - rlo > 0, "the row interval is degenerate"

    def mutate(t):
        return t.mutate("intent_engine/econ/incremental.py",
                        "    if k < 2:\n"
                        "        # ONE BLOCK IS NOT A NARROW INTERVAL, "
                        "IT IS NO INTERVAL.",
                        "    if False:\n"
                        "        # MUTATION")

    def check(t):
        INC = t.load("intent_engine.econ.incremental")
        diffs = [0.02] * 40 + [-0.01] * 40
        clusters = ([f"2008-{m:02d}-15" for m in range(1, 13)] * 4)[:80]
        elo, ehi, _p, k = INC._episode_bootstrap_ci(diffs, clusters, seed=1)
        if k < 2 and elo is not None:
            raise AssertionError(
                f"a single-block sample returned an interval "
                f"[{elo:+.5f}, {ehi:+.5f}]; an episode-level verdict would "
                "be read off a row-level bootstrap")
    return run("07_row_interval_for_episode_verdict",
               "the single-block refusal is removed",
               mutate=mutate, check=check, positive_control=control)


def bp8():
    """Modify preregistered H7 after seeing the results."""
    def control():
        PR = importlib.import_module("intent_engine.econ.preregistration")
        PR.assert_h7_unchanged(PR.h7_hash())

    def mutate(t):
        return t.mutate("intent_engine/econ/preregistration.py",
                        '    "horizons": (180, 240),',
                        '    "horizons": (180, 300),  # MUTATION')

    def check(t):
        PR = t.load("intent_engine.econ.preregistration")
        PR.assert_h7_unchanged("3a5c4d36259e08a2")
    return run("08_mutate_h7_after_results",
               "a preregistered H7 horizon is edited",
               mutate=mutate, check=check, positive_control=control)


def bp9():
    """Promote a lead-only signal as causal, at the call site."""
    def control():
        RS = importlib.import_module("intent_engine.econ.residual")
        o = RS.TemporalOrder(signal="UMCSENT", target="HOUST", best_lag=6,
                             best_correlation=0.30, lag_profile=(), n=482)
        RS.assert_lead_is_not_causal(o, "OBSERVED")
        try:
            RS.assert_lead_is_not_causal(o, "PROMOTE_GLOBAL_FORECAST")
        except RS.CausalOverreach:
            pass
        else:
            raise AssertionError("the clean guard allowed a promotion")
        # AND the guard must be CALLED where verdicts are assigned.
        src = (REPO / "scripts/run_v3_closure.py").read_text()
        assert "assert_lead_is_not_causal" in src, (
            "the verdict path does not call the causal-overreach guard")

    def mutate(t):
        return t.mutate("scripts/run_v3_closure.py",
                        "        RS.assert_lead_is_not_causal(",
                        "        _skip = (  # MUTATION")

    def check(t):
        src = t.path("scripts/run_v3_closure.py").read_text()
        if "RS.assert_lead_is_not_causal(" in src:
            raise AssertionError("the mutation did not remove the call")
        raise AssertionError(
            "the verdict path no longer checks that a temporal order is not "
            "being promoted to a predictive state; a lag of +6 months could "
            "carry a PROMOTE verdict on its own")
    return run("09_lead_only_promoted_as_causal",
               "the causal-overreach check is removed from the verdict path",
               mutate=mutate, check=check, positive_control=control)


def bp10():
    """Let a historical metric satisfy forward calibration."""
    def control():
        CAL = importlib.import_module("intent_engine.econ.calibration")
        rep = CAL.report([])
        CAL.assert_no_unsupported_claim("no prediction has resolved", rep)
        try:
            CAL.assert_no_unsupported_claim("live accuracy is 78%", rep)
        except Exception:
            pass
        else:
            raise AssertionError("the clean guard allowed an accuracy claim")
        src = (REPO / "scripts/run_v3_report.py")
        assert src.exists() and "assert_no_unsupported_claim" in \
            src.read_text(), "the V3 report does not check its own wording"

    def mutate(t):
        return t.mutate("scripts/run_v3_report.py",
                        "    CAL.assert_no_unsupported_claim(text, rep)",
                        "    pass  # MUTATION")

    def check(t):
        src = t.path("scripts/run_v3_report.py").read_text()
        if "CAL.assert_no_unsupported_claim(text, rep)" in src:
            raise AssertionError("the mutation did not remove the call")
        raise AssertionError(
            "the V3 report no longer checks its own wording against the "
            "calibration status; a historical Brier could ship as accuracy")
    return run("10_historical_satisfies_forward_calibration",
               "the report stops validating its own text",
               mutate=mutate, check=check, positive_control=control)


def bp11():
    """Let an unsupported human signal enter Founder."""
    def control():
        closure = json.loads((REPO / "reports/v3_closure.json").read_text())
        assert closure["founder_integration"]["status"] == "REFUSED", (
            "Founder is not refused, so this proof cannot fire")
        verdicts = [v["verdict"] for v in
                    closure["construct_verdicts"]["sentiment"].values()]
        assert not any(v.startswith("PROMOTE") for v in verdicts), (
            "something was promoted, so the refusal is not the tested state")

    def mutate(t):
        return t.mutate("scripts/run_v3_closure.py",
                        '    promoted = [k for k, v in sentiment.items()\n'
                        '                if v["verdict"].startswith("PROMOTE")]',
                        '    promoted = ["forced"]  # MUTATION')

    def check(t):
        src = t.path("scripts/run_v3_closure.py").read_text()
        if 'promoted = ["forced"]' not in src:
            raise AssertionError("the mutation did not land")
        raise AssertionError(
            "Founder eligibility no longer derives from the construct "
            "verdicts; an unsupported signal would reach a company "
            "recommendation")
    return run("11_unsupported_signal_enters_founder",
               "the Founder gate stops reading the verdicts",
               mutate=mutate, check=check, positive_control=control)


def bp12():
    """Rewrite an existing REAL_FORWARD expectation."""
    def control():
        FL = importlib.import_module("intent_engine.econ.forward_ledger")
        r = FL.assert_lifecycle()
        assert r["all_seven_hold"], "the lifecycle does not hold on clean code"

    def mutate(t):
        return t.mutate("intent_engine/econ/forward_ledger.py",
                        "            if field in r and field in first and "
                        "r[field] != first[field]:",
                        "            if False:  # MUTATION")

    def check(t):
        FL = t.load("intent_engine.econ.forward_ledger")
        import shutil as _sh
        tmp = t.root / "ledger.jsonl"
        _sh.copy(REPO / "reports/real_forward_expectations.jsonl", tmp)
        FL.assert_lifecycle(tmp)
    return run("12_rewrite_forward_expectation",
               "the immutability check on the forward ledger is removed",
               mutate=mutate, check=check, positive_control=control)


def _eps(EPI):
    mk = EPI.EconomicEpisode
    return [
        mk("A", "2008-01-15", "2008-06-15", ("CREDIT_STRESS",), {}, 1, "",
           "2008-06-15", "p", ("2008-01-15",)),
        mk("B", "2008-08-15", "2008-12-15", ("CREDIT_STRESS",), {}, 1, "",
           "2008-12-15", "p", ("2008-08-15",)),
        mk("C", "2010-01-15", "2010-06-15", ("CREDIT_STRESS",), {}, 1, "",
           "2010-06-15", "p", ("2010-01-15",)),
    ]


PROOFS = (bp1, bp2, bp3, bp4, bp5, bp6, bp7, bp8, bp9, bp10, bp11, bp12)


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
        {"contract": "econ_break_proofs_v3.v1", "proofs": len(results),
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
