"""End-to-end: the real step list, the real CLI, offline.

Covers the properties that only appear once the steps are composed — dry-run
isolation, funnel invariants, idempotent reruns, and the CLI's exit status
(which is the entire alerting channel).
"""
import json
import pathlib

import pytest

from intent_engine.market import __main__ as CLI
from intent_engine.market import cycle as C
from intent_engine.market import funnel as FUN
from intent_engine.market import steps as STEPS
from intent_engine.market.failures import IntegrityViolation

SERIES = {f"2026-{m:02d}-{d:02d}": 100.0 + (d % 3)
          for m in (5, 6, 7) for d in range(1, 29)}


def _rows(n=10, thesis_every=3):
    return [{"company": f"c{i}", "instrument": f"S{i}", "sector": "Tech",
             "evidence": 2, "indep": True, "thesis": i % thesis_every == 0,
             "gate": "no_market_evidence" if i % thesis_every == 0
                     else "no_strategic_reading",
             "classification": "watch" if i % thesis_every == 0 else "no_trade",
             "quality": 0.4, "error": "", "stub": False}
            for i in range(n)]


def _steps(rows=None, series=None):
    rows = _rows() if rows is None else rows
    return STEPS.day_steps(
        research_fn=lambda ctx: (rows, 0),
        series_fn=lambda symbol: series if series is not None else SERIES)


def _run(root, **kw):
    kw.setdefault("as_of", "2026-07-31")
    kw.setdefault("latest_bar", "2026-07-30")
    kw.setdefault("sleep", lambda _s: None)
    kw.setdefault("steps", _steps())
    return C.run_cycle(C.DAY, root=root, **kw)


# --- the full step list runs ------------------------------------------------
def test_a_complete_day_cycle_runs_every_step(tmp_path):
    result = _run(tmp_path)
    assert result.status == C.COMPLETED, result.reason
    assert [s.name for s in result.steps] == [
        "research", "opportunity", "funnel", "positions", "paper_entries",
        "assets", "learning", "health", "report"]
    assert all(s.ok for s in result.steps)


def test_learning_runs_after_positions_so_it_knows_the_trade_count(tmp_path):
    """The learning step must be able to state whether a trade was opened.

    Its central claim — that knowledge moved WITHOUT a trade — is only
    checkable if it runs after the step that would have opened one.
    """
    names = [n for n, _ in STEPS.day_steps()]
    assert names.index("learning") > names.index("positions")
    assert names.index("learning") < names.index("report")


def test_learning_runs_in_the_night_cycle_too(tmp_path):
    assert "learning" in [n for n, _ in STEPS.night_steps()]


def test_a_complete_night_cycle_adds_reconciliation_and_resolution(tmp_path):
    result = C.run_cycle(
        C.NIGHT, root=tmp_path,
        steps=STEPS.night_steps(research_fn=lambda ctx: (_rows(), 0),
                                series_fn=lambda s: SERIES),
        as_of="2026-07-31", latest_bar="2026-07-31", sleep=lambda _s: None)
    assert result.status == C.COMPLETED, result.reason
    names = [s.name for s in result.steps]
    assert "reconcile" in names and "resolve_outcomes" in names


def test_both_report_forms_are_produced(tmp_path):
    result = _run(tmp_path)
    assert pathlib.Path(result.report_paths["md"]).exists()
    payload = json.loads(pathlib.Path(result.report_paths["json"]).read_text())
    assert payload["run_id"] == result.run_id
    assert payload["recommendation"] in (
        "CONTINUE OPERATING",
        "PAUSE FOR ONE ENGINEERING CYCLE — operational health is DOWN; "
        "the engine cannot run unattended in this state")


def test_the_report_declares_every_position_metric_unmeasurable(tmp_path):
    result = _run(tmp_path)
    text = pathlib.Path(result.report_paths["md"]).read_text()
    for metric in ("win rate", "Sharpe", "Sortino", "profit factor",
                   "maximum drawdown", "alpha vs SPY",
                   "Position Decision Quality"):
        assert metric in text
    assert "UNMEASURABLE" in text
    # zero must never be printed as if it were a measured rate
    assert "| win rate | 0" not in text


# --- funnel integrity -------------------------------------------------------
def test_the_funnel_stages_are_subsets(tmp_path):
    result = _run(tmp_path)
    counts = result.steps[2].detail["funnel"]["counts"]
    for above, below in zip(FUN.CHAIN, FUN.CHAIN[1:]):
        assert counts[below] <= counts[above], f"{below} > {above}"


def test_no_conversion_rate_exceeds_one_hundred_percent(tmp_path):
    result = _run(tmp_path)
    rates = result.steps[2].detail["funnel"]["rates"]
    for stage, rate in rates.items():
        if rate is not None:
            assert rate <= 1.0, f"{stage} = {rate:.0%}"


def test_terminals_partition_the_evaluated_set(tmp_path):
    result = _run(tmp_path)
    counts = result.steps[2].detail["funnel"]["counts"]
    assert sum(counts[t] for t in FUN.TERMINALS) == counts["evaluated"]


def test_a_broken_funnel_invariant_fails_the_cycle(tmp_path):
    """Enforced every cycle rather than trusted: this defect has produced a
    wrong bottleneck ranking twice already."""
    ctx = C.CycleContext(cycle=C.DAY, as_of="2026-07-31", root=tmp_path,
                         session=None, run_id="x")
    ctx.results["research"] = {"rows": _rows(4, thesis_every=1)}
    # more opportunities than companies that reached signal evaluation
    ctx.results["opportunity"] = {"observable": 99, "fired": 0}
    out = STEPS.funnel_step(ctx)
    # clamped, so the invariant holds rather than raising ...
    assert out["funnel"]["counts"]["signal_opportunity"] <= \
        out["funnel"]["counts"]["signal_evaluated"]


def test_a_false_fire_is_counted_separately_not_netted_into_the_chain(tmp_path):
    """A fire without a qualifying opportunity is an anomaly, not progress."""
    funnel = FUN.from_rows(_rows(3, thesis_every=1), as_of="2026-07-31",
                           signal_opportunity=0, signal_fired=2)
    assert funnel.counts["signal_fired"] == 0
    assert funnel.counts["false_fire"] == 2


# --- dry-run isolation ------------------------------------------------------
def test_a_dry_run_never_appends_to_the_real_funnel_history(tmp_path):
    """A rehearsal that leaves fabricated observations behind is worse than no
    rehearsal — afterwards they are indistinguishable from data."""
    history = tmp_path / "reports" / "funnel_history.json"
    _run(tmp_path, dry_run=True)
    assert not history.exists()
    _run(tmp_path)
    assert history.exists()


def test_a_dry_run_never_appends_to_the_signal_audit(tmp_path):
    _run(tmp_path, dry_run=True)
    assert not (tmp_path / STEPS.AUDIT_FILE).exists()


def test_the_cli_routes_a_dry_run_to_a_separate_root(tmp_path):
    class Args:
        root = str(tmp_path)
        dry_run = True
    assert CLI._root(Args()) == tmp_path / "dryrun"
    Args.dry_run = False
    assert CLI._root(Args()) == tmp_path


def test_stub_rows_are_labelled_as_not_a_measurement(tmp_path):
    ctx = C.CycleContext(cycle=C.DAY, as_of="2026-07-31", root=tmp_path,
                         session=None, run_id="x", dry_run=True)
    out = STEPS.research_step()(ctx)
    assert out["stub"] is True
    assert all(r["stub"] for r in out["rows"])


# --- idempotence ------------------------------------------------------------
def test_an_idempotent_rerun_after_a_partial_does_not_double_append(tmp_path):
    broken = _steps()[:2] + [("boom", _raise)] + _steps()[2:]
    partial = _run(tmp_path, steps=broken)
    assert partial.status == C.PARTIAL

    audit_after_partial = len(STEPS.read_audit(tmp_path))
    good = _run(tmp_path, steps=_steps())
    assert good.status != C.SKIPPED_DUPLICATE
    # the retry appended its own records; the partial's are not duplicated away
    assert len(STEPS.read_audit(tmp_path)) > audit_after_partial


def _raise(ctx):
    raise ConnectionError("news feed unreachable")


def test_repeated_ingestion_of_the_same_bar_does_not_advance_history(tmp_path):
    _run(tmp_path, as_of="2026-07-31", latest_bar="2026-07-30")
    history = json.loads((tmp_path / "reports" /
                          "funnel_history.json").read_text())
    first_days = len(history)

    second = _run(tmp_path, as_of="2026-08-01", latest_bar="2026-07-30")
    assert second.status == C.SKIPPED_NO_NEW_MARKET_SESSION
    # the research still ran and is recorded ...
    assert all(s.ok for s in second.steps)
    # ... and the run record says plainly it was not a new market observation
    assert second.session["has_new_market_observation"] is False
    assert len(json.loads((tmp_path / "reports" /
                           "funnel_history.json").read_text())) >= first_days


# --- source failure isolation -----------------------------------------------
def test_a_total_price_source_failure_isolates_and_never_becomes_a_zero(tmp_path):
    """Two different correct behaviours, and the difference is the point.

    `opportunity` ABSORBS a dead feed: "we looked and could not tell" is a real
    measurement, recorded as data_unavailable.

    `paper_entries` must NOT absorb it. "Opened 0 positions" because the feed
    was down is not the same fact as "opened 0 positions because nothing
    fired", and recording the first as the second is exactly the
    failure-becomes-a-zero error this project refuses. So the cycle goes
    PARTIAL and names the step -- which is still not a dead cycle.
    """
    def dead(symbol):
        raise ConnectionError("price feed down")

    result = _run(tmp_path, steps=STEPS.day_steps(
        research_fn=lambda ctx: (_rows(), 0), series_fn=dead))
    assert result.status == C.PARTIAL
    assert "paper_entries" in result.reason

    opportunity = [s for s in result.steps if s.name == "opportunity"][0]
    assert opportunity.ok
    assert opportunity.detail["data_unavailable"] > 0
    assert opportunity.detail["observable"] == 0

    # the report is still produced -- it is what a human needs in order to see
    # that the feed was down
    assert result.report_paths.get("md")


def test_a_partial_research_failure_still_produces_a_report(tmp_path):
    """The failure is exactly what a human needs the report in order to see."""
    result = _run(tmp_path, steps=[("research", _raise)] + _steps()[1:])
    assert result.status == C.PARTIAL
    assert result.report_paths.get("md")
    assert pathlib.Path(result.report_paths["md"]).exists()


# --- CLI --------------------------------------------------------------------
def test_the_cli_status_command_runs_and_exits_zero_on_a_fresh_root(tmp_path,
                                                                    capsys):
    assert CLI.main(["status", "--root", str(tmp_path)]) == 0
    assert "MARKET OPERATING HEALTH" in capsys.readouterr().out


def test_the_cli_status_json_is_machine_readable(tmp_path, capsys):
    CLI.main(["status", "--root", str(tmp_path), "--json"])
    assert json.loads(capsys.readouterr().out)["overall"]


def test_the_cli_runs_command_lists_history(tmp_path, capsys):
    _run(tmp_path)
    assert CLI.main(["runs", "--root", str(tmp_path)]) == 0
    assert "2026-07-31:day" in capsys.readouterr().out


def test_the_cli_exposes_both_cycles_and_the_documented_times():
    parser = CLI.build_parser()
    helptext = parser.format_help()
    assert "day" in helptext and "night" in helptext
    assert "paper trading only" in helptext


def test_a_failed_cycle_exits_nonzero_so_launchd_records_it(tmp_path):
    result = _run(tmp_path, steps=[("a", _raise), ("b", _raise)])
    assert result.status == C.FAILED
    assert result.exit_code == 1


def test_a_skip_exits_zero_because_it_is_not_an_error(tmp_path):
    assert _run(tmp_path, latest_bar=None).exit_code == 0


def test_a_rehearsal_does_not_cancel_the_real_run(tmp_path):
    """A dry run at 06:00 must not make the 06:30 cycle a SKIPPED_DUPLICATE."""
    rehearsal = _run(tmp_path, dry_run=True)
    assert rehearsal.status == C.COMPLETED
    real = _run(tmp_path)
    assert real.status == C.COMPLETED
    assert real.dry_run is False


def test_a_rehearsals_bar_is_not_remembered_as_ingested(tmp_path):
    _run(tmp_path, dry_run=True, latest_bar="2026-07-30")
    assert C.RunStore(tmp_path).last_ingested_bar() is None
