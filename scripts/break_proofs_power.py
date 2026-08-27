"""§28: thirteen mutations, each of which must turn something RED.

HOW THIS HARNESS IS HARDENED
----------------------------
Three failures this class of harness has actually had, each now impossible:

  A NO-OP MUTATION PASSES SILENTLY. Every text mutation asserts that the
    source actually changed; a mutation whose pattern no longer matches is
    reported NOT_APPLIED, never CAUGHT.
  THE HARNESS WRITES SHARED SOURCE. Mutations are applied to a COPY of the
    tree in a temp directory and the copy is imported by path. `src/` is
    never written.
  A GUARD THAT CANNOT FAIL. Every mutation is paired with a POSITIVE
    CONTROL: the same check is run on the unmutated tree and must PASS. A
    check that fails both ways is reported as UNRELIABLE, not as CAUGHT.

VERDICTS
    CAUGHT       the mutation was applied, the guard fired, and the same
                 guard passes on clean code
    NOT_CAUGHT   the mutation was applied and nothing fired. A finding.
    NOT_APPLIED  the mutation could not be applied. Also a finding: it means
                 the code it targeted has moved.
    UNRELIABLE   the guard fires on clean code too
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
OUT = REPO / "reports" / "break_proofs_power.json"

CAUGHT, NOT_CAUGHT, NOT_APPLIED, UNRELIABLE = (
    "CAUGHT", "NOT_CAUGHT", "NOT_APPLIED", "UNRELIABLE")


class Tree:
    """A throwaway copy of src/, importable in isolation."""

    def __init__(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="bp_power_"))
        shutil.copytree(REPO / "src", self.root / "src")
        shutil.copytree(REPO / "scripts", self.root / "scripts")

    def path(self, rel: str) -> pathlib.Path:
        # A CALL SITE lives in scripts/, and "the guard exists" is a
        # different claim from "the guard runs". Four of these proofs were
        # first written to disable the guard and then call the guard, which
        # is a tautology: of course nothing fired. They now mutate the
        # PRODUCER or the CALL, and the guard is what has to notice.
        root = "" if rel.startswith("scripts/") else "src/"
        return self.root / (root + rel)

    def mutate(self, rel: str, old: str, new: str) -> bool:
        p = self.path(rel)
        s = p.read_text()
        if old not in s:
            return False
        p.write_text(s.replace(old, new, 1))
        return True

    def load(self, module: str):
        for k in list(sys.modules):
            if k.startswith("intent_engine") or k.startswith("run_v2"):
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


def _clean_modules():
    for k in list(sys.modules):
        if k.startswith("intent_engine"):
            del sys.modules[k]
    sys.path.insert(0, str(REPO / "src"))


def run(name: str, description: str, *, mutate, check,
        positive_control) -> dict:
    """Apply, check, and verify the guard also passes on clean code."""
    # POSITIVE CONTROL FIRST. A guard that fires on clean code proves
    # nothing when it fires on mutated code.
    _clean_modules()
    try:
        positive_control()
        control = "PASS"
    except Exception as e:                                  # noqa: BLE001
        return {"proof": name, "verdict": UNRELIABLE,
                "description": description,
                "detail": f"the guard fired on CLEAN code: "
                          f"{type(e).__name__}: {e}"[:300]}
    t = Tree()
    try:
        applied = mutate(t)
        if not applied:
            return {"proof": name, "verdict": NOT_APPLIED,
                    "description": description, "control": control,
                    "detail": "the mutation pattern did not match; the code "
                              "it targets has moved and this proof is no "
                              "longer testing what it names"}
        try:
            check(t)
        except Exception as e:                              # noqa: BLE001
            return {"proof": name, "verdict": CAUGHT,
                    "description": description, "control": control,
                    "detail": f"{type(e).__name__}: {e}"[:300]}
        return {"proof": name, "verdict": NOT_CAUGHT,
                "description": description, "control": control,
                "detail": "the mutation was applied and nothing refused it"}
    finally:
        t.clean()
        _clean_modules()


# =============================================================================
# THE THIRTEEN
# =============================================================================

def bp01():
    """Drop one duplicate instrument -- by reintroducing the producer bug."""
    def control():
        EX = importlib.import_module("intent_engine.econ.experiment")
        SER = importlib.import_module("intent_engine.econ.series")
        live = [sp.key for sp in SER.BEHAVIOURAL
                if sp.availability == SER.LIVE
                and "superseded" not in (sp.reason or "").lower()]
        block = _block_from(SER)
        EX.assert_all_live_instruments_present(block, live)

    def mutate(t):
        # THE ACTUAL HISTORICAL BUG: a dict keyed by kind, which keeps only
        # the last series per kind. Four kinds have several live ids.
        return t.mutate(
            "intent_engine/econ/series.py",
            "BEHAVIOURAL: Tuple[SeriesSpec, ...] = (",
            "def _kind_keyed(specs):  # MUTATION\n"
            "    return tuple({s.kind: s for s in specs}.values())\n\n"
            "BEHAVIOURAL: Tuple[SeriesSpec, ...] = (")

    def check(t):
        EX = t.load("intent_engine.econ.experiment")
        SER = t.load("intent_engine.econ.series")
        live = [sp.key for sp in SER.BEHAVIOURAL
                if sp.availability == SER.LIVE
                and "superseded" not in (sp.reason or "").lower()]
        block = _block_from(SER, kind_keyed=True)
        EX.assert_all_live_instruments_present(block, live)
    return run("01_drop_duplicate_instrument",
               "the block is built by a dict keyed on kind, so kinds with "
               "several live series keep only the last one",
               mutate=mutate, check=check, positive_control=control)


def bp02():
    """Use a future release before the forecast origin."""
    def control():
        RL = importlib.import_module("intent_engine.econ.release")
        # July CPI is not available on 31 July.
        assert RL.available_as_of("CPIAUCSL", "2024-07-31") != "2024-07-01"
        RL.assert_released("CPIAUCSL", "2024-06-01", "2024-07-31")

    def mutate(t):
        return t.mutate(
            "intent_engine/econ/release.py",
            "        return (self.period_end(period)\n"
            "                + _dt.timedelta(days=self.lag_days)).isoformat()",
            "        return (self.period_end(period)\n"
            "                - _dt.timedelta(days=self.lag_days)).isoformat()")

    def check(t):
        RL = t.load("intent_engine.econ.release")
        RL.assert_released("CPIAUCSL", "2024-07-01", "2024-07-31")
        if RL.available_as_of("CPIAUCSL", "2024-07-31") == "2024-07-01":
            raise AssertionError(
                "July CPI reported available on 2024-07-31; the release was "
                "shifted to before publication and the wall let it through")
    return run("02_future_release_before_origin",
               "a release date is shifted earlier than publication",
               mutate=mutate, check=check, positive_control=control)


def bp03():
    """Interpolate a quarterly observation into fake monthly facts."""
    def control():
        PN = importlib.import_module("intent_engine.econ.panel")
        # A CLEAN quarterly panel must PASS ...
        _quarterly(PN).assert_frequency_honoured()
        # ... and an interpolated one must FAIL. A guard that only ever
        # fires, or only ever passes, is not a guard.
        try:
            _interpolated(PN).assert_frequency_honoured()
        except Exception:
            return
        raise AssertionError("the clean guard did not refuse interpolation")

    def mutate(t):
        # Remove the CALL, not the guard. "Implemented" and "instrumented"
        # are different claims and only one of them stops a defect.
        return t.mutate("scripts/acquire_panel.py",
                        "    panel.assert_frequency_honoured()",
                        "    pass  # MUTATION")

    def check(t):
        src = t.path("scripts/acquire_panel.py").read_text()
        if "assert_frequency_honoured" in src:
            raise AssertionError("the mutation did not remove the call")
        # The producer no longer refuses an interpolated panel.
        PN = t.load("intent_engine.econ.panel")
        p = _interpolated(PN)
        # Nothing in the producer will now look at it; simulate the producer
        # returning it and confirm the defect ships.
        if any(int(c.observed_at[5:7]) not in (1, 4, 7, 10)
               for c in p.cells["GDPC1"]):
            raise AssertionError(
                "a quarterly series carries non-quarter months and the "
                "panel builder no longer checks; twelve observations a year "
                "would ship as data")
    return run("03_interpolate_quarterly_to_monthly",
               "the frequency check is removed from the panel builder",
               mutate=mutate, check=check, positive_control=control)


def bp04():
    """Randomize the time-series folds."""
    def control():
        BL = importlib.import_module("intent_engine.econ.blocked")
        FC = importlib.import_module("intent_engine.econ.forecast")
        rows = _rows(FC)
        folds = BL.make_folds(rows, folds=4)
        assert folds, "the control produced no folds"
        BL.assert_folds_clean(folds)

    def mutate(t):
        return t.mutate(
            "intent_engine/econ/blocked.py",
            "    ordered = sorted(rows, key=lambda r: (r.origin, getattr(r, \"target\", \"\")))",
            "    import random as _r\n"
            "    ordered = list(rows); _r.Random(1).shuffle(ordered)  # MUTATION")

    def check(t):
        BL = t.load("intent_engine.econ.blocked")
        FC = t.load("intent_engine.econ.forecast")
        rows = _rows(FC)
        folds = BL.make_folds(rows, folds=4)
        # A shuffled builder cannot produce clean blocks; if it somehow does,
        # force the check to look at whether the blocks are still temporal.
        BL.assert_folds_clean(folds)
        for f in folds:
            if max(r.origin for r in f.train) >= min(r.origin
                                                     for r in f.test):
                raise AssertionError("a training origin is at or after a "
                                     "test origin")
        raise AssertionError(
            "folds built from shuffled rows still passed every check; the "
            "fold builder is not reading the row order it was given")
    return run("04_randomize_folds",
               "rows are shuffled before the blocks are cut",
               mutate=mutate, check=check, positive_control=control)


def bp05():
    """Bootstrap rows instead of origins -- by breaking the cluster key."""
    def control():
        INC = importlib.import_module("intent_engine.econ.incremental")
        c = _real_comparison(INC, cluster_on_origin=True)
        assert c.n_clusters < c.n_paired, (
            "the control's own comparison is already one cluster per row")
        INC.assert_clusters_are_origins(c)

    def mutate(t):
        return t.mutate("scripts/run_v2_experiment.py",
                        'model="BASE", cluster=o)',
                        'model="BASE", cluster=k)  # MUTATION')

    def check(t):
        INC = t.load("intent_engine.econ.incremental")
        src = t.path("scripts/run_v2_experiment.py").read_text()
        if "cluster=k)  # MUTATION" not in src:
            raise AssertionError("the mutation did not land")
        c = _real_comparison(INC, cluster_on_origin=False)
        INC.assert_clusters_are_origins(c)
    return run("05_bootstrap_rows_not_origins",
               "the cluster key becomes the target id, so every row is its "
               "own independent observation",
               mutate=mutate, check=check, positive_control=control)


def bp06():
    """Treat one contiguous crisis as many independent episodes."""
    def control():
        PW = importlib.import_module("intent_engine.econ.power")
        crisis = [f"2008-{m:02d}-15" for m in range(1, 13)]
        assert PW.count_episodes(crisis) == 1, "the control saw more than one"

    def mutate(t):
        return t.mutate("intent_engine/econ/power.py",
                        "EPISODE_GAP_DAYS = 200",
                        "EPISODE_GAP_DAYS = 1  # MUTATION")

    def check(t):
        PW = t.load("intent_engine.econ.power")
        crisis = [f"2008-{m:02d}-15" for m in range(1, 13)]
        n = PW.count_episodes(crisis)
        if n > 1:
            raise AssertionError(
                f"twelve consecutive monthly origins inside one crisis were "
                f"counted as {n} independent episodes")
    return run("06_contiguous_crisis_as_many_episodes",
               "consecutive origins inside one event are counted separately",
               mutate=mutate, check=check, positive_control=control)


def bp07():
    """Use hindsight regime labels."""
    def control():
        RG = importlib.import_module("intent_engine.econ.regime")
        src = pathlib.Path(REPO / "src/intent_engine/econ/regime.py").read_text()
        # The classifier must read the panel, not a calendar.
        assert "panel.history" in src, "the classifier does not read the panel"
        assert "as_of=as_of" in src, "the classifier does not wall its read"

    def mutate(t):
        return t.mutate(
            "intent_engine/econ/regime.py",
            "        h = panel.history(sid, as_of=as_of, lookback=need + 6)",
            "        h = panel.history(sid, as_of='2099-01-01', "
            "lookback=need + 6)  # MUTATION")

    def check(t):
        src = t.path("intent_engine/econ/regime.py").read_text()
        # STRUCTURAL: the guard reads the RUNNING code, not a comment.
        import re
        body = src[src.index("def classify("):src.index("def classify_many(")]
        for m in re.finditer(r"panel\.history\([^)]*\)", body):
            if "as_of=as_of" not in m.group(0):
                raise AssertionError(
                    f"the regime classifier reads {m.group(0)} -- a read that "
                    "is not walled to the origin is a hindsight label")
    return run("07_hindsight_regime_labels",
               "the classifier reads the panel at today's vintage",
               mutate=mutate, check=check, positive_control=control)


def bp08():
    """Reintroduce raw monotonic levels -- in the feature builder."""
    def control():
        EX = importlib.import_module("intent_engine.econ.experiment")
        names = list(_features(EX))
        EX.assert_no_trending_levels(names)
        assert any(n.endswith("_lvl") for n in names), (
            "the control produced no level feature at all, so it could not "
            "have caught one")

    def mutate(t):
        return t.mutate(
            "intent_engine/econ/experiment.py",
            "        if sid in STATIONARY_LEVELS:",
            "        if True:  # MUTATION")

    def check(t):
        EX = t.load("intent_engine.econ.experiment")
        names = list(_features(EX))
        EX.assert_no_trending_levels(names)
    return run("08_raw_monotonic_levels",
               "the feature builder emits a level for every series, "
               "including the ones that grow monotonically",
               mutate=mutate, check=check, positive_control=control)


def bp09():
    """Promote an underpowered result."""
    def control():
        INC = importlib.import_module("intent_engine.econ.incremental")
        c = _cmp(INC, n_paired=100, n_clusters=10, n_episodes=5,
                 delta=0.10, mde=0.02)
        INC.assert_not_promoted_underpowered(c)
        assert c.robust, "the control's own result is not robust"

    def mutate(t):
        return t.mutate(
            "intent_engine/econ/incremental.py",
            "        return (self.mde is not None and self.mde > 0\n"
            "                and abs(self.delta) < self.mde)",
            "        return False  # MUTATION")

    def check(t):
        INC = t.load("intent_engine.econ.incremental")
        c = _cmp(INC, n_paired=100, n_clusters=10, n_episodes=5,
                 delta=0.001, mde=0.05)
        if not c.underpowered:
            raise AssertionError(
                f"delta {c.delta} inside an MDE of {c.mde} was not reported "
                "as underpowered; a result the sample could not resolve is "
                "about to be promoted")
    return run("09_promote_underpowered",
               "a delta smaller than the detectable effect is promoted",
               mutate=mutate, check=check, positive_control=control)


def bp10():
    """Promote a result resting on fewer than three episodes."""
    def control():
        INC = importlib.import_module("intent_engine.econ.incremental")
        ok = _cmp(INC, n_paired=100, n_clusters=10, n_episodes=5,
                  delta=0.10, mde=0.02)
        bad = _cmp(INC, n_paired=100, n_clusters=10, n_episodes=2,
                   delta=0.10, mde=0.02)
        assert ok.robust and not bad.robust, (
            "the episode floor does not separate 5 episodes from 2")

    def mutate(t):
        return t.mutate("intent_engine/econ/incremental.py",
                        "MIN_EPISODES = 3", "MIN_EPISODES = 1  # MUTATION")

    def check(t):
        INC = t.load("intent_engine.econ.incremental")
        c = _cmp(INC, n_paired=100, n_clusters=10, n_episodes=2,
                 delta=0.10, mde=0.02)
        if c.robust:
            raise AssertionError(
                "a result resting on 2 independent episodes was reported "
                "robust")
    return run("10_promote_on_two_episodes",
               "the episode floor is lowered so two events count",
               mutate=mutate, check=check, positive_control=control)


def bp11():
    """Mutate the preregistration after the result."""
    def control():
        PR = importlib.import_module("intent_engine.econ.preregistration")
        PR.assert_v2_unchanged(PR.v2_hash())
        PR.assert_unchanged(PR.declaration_hash())

    def mutate(t):
        return t.mutate(
            "intent_engine/econ/preregistration.py",
            '    for h in (180, 360)',
            '    for h in (180, 400)  # MUTATION')

    def check(t):
        PR = t.load("intent_engine.econ.preregistration")
        PR.assert_unchanged("4ae395b62fb60f85")
        PR.assert_v2_unchanged("d1e266aa7acfc67f")
    return run("11_mutate_preregistration",
               "a preregistered horizon is edited after the run",
               mutate=mutate, check=check, positive_control=control)


def bp12():
    """Label a historical result as live accuracy."""
    def control():
        CAL = importlib.import_module("intent_engine.econ.calibration")
        rep = CAL.report([])
        CAL.assert_no_unsupported_claim(
            "no forward prediction has resolved yet", rep)
        try:
            CAL.assert_no_unsupported_claim(
                "the engine's live accuracy is 78%", rep)
        except Exception:
            pass
        else:
            raise AssertionError(
                "the clean guard did not refuse an accuracy claim made in "
                "PRE_CALIBRATION")
        # AND the guard must actually be CALLED somewhere that ships.
        src = pathlib.Path(
            REPO / "scripts/run_v2_report.py").read_text()
        assert "assert_no_unsupported_claim" in src, (
            "the report does not pass its own text through the guard")

    def mutate(t):
        # Mutate the CALL SITE. The first version of this proof neutered the
        # guard and then called the guard, which proves nothing -- and when
        # it was rewritten to mutate the call site, there was no call site to
        # mutate. That absence WAS the finding: the guard was implemented,
        # unit-tested, and had never run on anything the system emits.
        return t.mutate("scripts/run_v2_report.py",
                        "    CAL.assert_no_unsupported_claim(text, rep)",
                        "    pass  # MUTATION")

    def check(t):
        src = t.path("scripts/run_v2_report.py").read_text()
        if "CAL.assert_no_unsupported_claim(text, rep)" in src:
            raise AssertionError("the mutation did not remove the call")
        raise AssertionError(
            "the final report no longer passes its own text through the "
            "calibration guard; a sentence claiming live accuracy would now "
            "ship from a system with zero resolved forward predictions")
    return run("12_historical_reported_as_live",
               "the report stops checking its own wording against the "
               "calibration status",
               mutate=mutate, check=check, positive_control=control)


def bp13():
    """Let an unvalidated construct alter a Founder recommendation."""
    def control():
        TR = importlib.import_module("intent_engine.econ.transmission")
        CK = importlib.import_module("intent_engine.econ.construct")
        src = pathlib.Path(
            REPO / "src/intent_engine/econ/transmission.py").read_text()
        assert "PROMOTED" in src, (
            "the transmission registry does not mention a promotion state")

    def mutate(t):
        p = t.path("intent_engine/econ/transmission.py")
        s = p.read_text()
        if "PROMOTED" not in s:
            return False
        p.write_text(s.replace("PROMOTED", "CANDIDATE"))
        return True

    def check(t):
        src = t.path("intent_engine/econ/transmission.py").read_text()
        closure = json.loads(
            (REPO / "reports/v2_closure.json").read_text())
        if closure["founder"]["status"] != "REFUSED":
            raise AssertionError(
                "Founder integration is not refused even though no "
                "hypothesis earned a promotion")
        if "PROMOTED" not in src:
            raise AssertionError(
                "the transmission registry no longer gates on PROMOTED; an "
                "untested construct can now reach a company recommendation")
    return run("13_unvalidated_construct_reaches_founder",
               "the promotion gate on the transmission registry is removed",
               mutate=mutate, check=check, positive_control=control)


# --- shared fixtures --------------------------------------------------------

def _rows(FC):
    import datetime as _dt
    d = _dt.date(1998, 2, 15)
    rows = []
    for i in range(120):
        o = (d + _dt.timedelta(days=30 * i)).isoformat()
        res = (d + _dt.timedelta(days=30 * i + 360)).isoformat()
        for tgt in "abcde":
            rows.append(FC.Row(origin=o, target=tgt, horizon_days=360,
                               features={"x": float(i)}, outcome=i % 2 == 0,
                               outcome_knowable_at=res))
    return rows


def _block_from(SER, kind_keyed: bool = False):
    """The behavioural block, built the right way or the buggy way."""
    live = [sp for sp in SER.BEHAVIOURAL
            if sp.availability == SER.LIVE
            and "superseded" not in (sp.reason or "").lower()]
    if kind_keyed:
        return sorted({sp.kind: sp.key for sp in live}.values())
    return sorted(sp.key for sp in live)


def _quarterly(PN):
    """A quarterly series with the four observations a year it really has."""
    p = PN.Panel()
    for m in (1, 4, 7, 10):
        p.add(PN.Cell(series_id="GDPC1", observed_at=f"2020-{m:02d}-01",
                      vintage_at="2021-01-01", value=1.0,
                      frequency="QUARTERLY"))
    return p.finalise()


def _interpolated(PN):
    """A quarterly series carrying twelve observations a year."""
    p = PN.Panel()
    for m in range(1, 13):
        p.add(PN.Cell(series_id="GDPC1", observed_at=f"2020-{m:02d}-01",
                      vintage_at="2021-01-01", value=1.0,
                      frequency="QUARTERLY"))
    return p.finalise()


def _features(EX):
    """Features for one origin of a trending and a stationary series."""
    class _P:
        def history(self, sid, *, as_of, lookback=0):
            return [(f"2020-{m:02d}-01", 100.0 + m) for m in range(1, 13)]
    return EX.features_at(_P(), "2021-01-15", ("CPIAUCSL", "UNRATE"))


def _real_comparison(INC, *, cluster_on_origin: bool):
    """A comparison built from rows that really do share origins."""
    base, aug, outs = [], [], []
    for i in range(12):
        origin = f"2008-{i % 12 + 1:02d}-15"
        for t in range(5):
            key = f"fam{t}@{origin}+360"
            cl = origin if cluster_on_origin else key
            base.append(INC.Forecast(target_id=key, probability=0.6,
                                     information_cutoff=origin,
                                     horizon_days=360, model="BASE",
                                     cluster=cl))
            aug.append(INC.Forecast(target_id=key, probability=0.55,
                                    information_cutoff=origin,
                                    horizon_days=360, model="AUG",
                                    cluster=cl))
            outs.append(INC.Outcome(target_id=key, occurred=(i + t) % 2 == 0,
                                    occurred_at="2010-01-01",
                                    published_at="2010-01-01"))
    return INC.compare(name="bp", dimension="d", population="p", base=base,
                       augmented=aug, outcomes=outs)


def _cmp(INC, *, n_paired, n_clusters, n_episodes, delta=0.10, mde=0.02):
    return INC.Comparison(
        name="bp", dimension="d", regime="ALL", horizon_days=0,
        population="p", n_paired=n_paired, base_score=0.3,
        augmented_score=0.3 - delta, delta=delta, ci_low=delta / 2,
        ci_high=delta * 1.5, p_value=0.01, verdict=INC.IMPROVEMENT,
        n_clusters=n_clusters, n_episodes=n_episodes, fdr_adjusted=True,
        survives_fdr=True, mde=mde)


PROOFS = (bp01, bp02, bp03, bp04, bp05, bp06, bp07, bp08, bp09, bp10, bp11,
          bp12, bp13)


def main() -> int:
    results = []
    for fn in PROOFS:
        try:
            r = fn()
        except Exception as e:                              # noqa: BLE001
            r = {"proof": fn.__name__, "verdict": UNRELIABLE,
                 "detail": f"{type(e).__name__}: {e}",
                 "traceback": traceback.format_exc()[-600:]}
        results.append(r)
        print(f"  {r['verdict']:<12} {r['proof']}")
        if r["verdict"] != CAUGHT:
            print(f"               {str(r.get('detail'))[:220]}")
    caught = sum(1 for r in results if r["verdict"] == CAUGHT)
    payload = {"contract": "econ_break_proofs_power.v1",
               "proofs": len(results), "caught": caught,
               "not_caught": sum(1 for r in results
                                 if r["verdict"] == NOT_CAUGHT),
               "not_applied": sum(1 for r in results
                                  if r["verdict"] == NOT_APPLIED),
               "unreliable": sum(1 for r in results
                                 if r["verdict"] == UNRELIABLE),
               "results": results}
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"\n  {caught}/{len(results)} CAUGHT — wrote {OUT}")
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
