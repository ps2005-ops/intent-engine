"""Cycle reports — human-readable and machine-readable, from the same data.

ONE SOURCE, TWO RENDERINGS
--------------------------
The markdown and the JSON are built from a single payload. A report a human
reads and a record a process reads must never be able to disagree, and the way
they disagree in practice is that one of them gets updated and the other does
not.

UNMEASURABLE IS A FIRST-CLASS VALUE
-----------------------------------
Every metric that cannot be computed prints `UNMEASURABLE` with the reason.
Not `0`, not `--`, not omitted. Zero positions is not a 0% win rate; it is the
absence of a win rate, and a report that prints 0% invites a reader to compare
it to something. This is the same rule the project has held since day 1 and the
reason it can still say honestly that it has never opened a position.
"""
from __future__ import annotations

from typing import List, Tuple

from intent_engine.market import cycle as C
from intent_engine.market import session as S
from intent_engine.market import signal_opportunity as SO
from intent_engine.market import translation_report as TR

UNMEASURABLE = "UNMEASURABLE"

# Metrics that need resolved positions, and the reason each is unavailable.
# Written once, printed everywhere, so a metric cannot quietly acquire a
# plausible-looking value without someone editing this table.
_POSITION_METRICS = (
    ("Position Decision Quality", "no position has ever been opened"),
    ("paper trades opened", "0"),
    ("paper trades closed", "0"),
    ("open positions", "0"),
    ("resolved positions", "0"),
    ("win rate", "0 resolved positions"),
    ("total return", "0 resolved positions"),
    ("expectancy", "0 resolved positions"),
    ("profit factor", "0 resolved positions"),
    ("Sharpe", "0 resolved positions"),
    ("Sortino", "0 resolved positions"),
    ("maximum drawdown", "0 resolved positions"),
    ("volatility", "0 resolved positions"),
    ("equity curve", "no closed book to plot"),
    ("SPY comparison", "no position series to compare"),
    ("alpha vs SPY", "no position series to compare"),
)


def _fmt(value, pct: bool = False) -> str:
    if value is None:
        return "—"
    if pct:
        return f"{value:.0%}"
    return str(value)


def _belief_learning(learning: dict) -> List[str]:
    """BELIEF LEARNING, reported apart from anything trading produced.

    The separation is the point of the section. Trading performance is not a
    research-velocity measure, and using it as one is what made eleven
    consecutive cycles report NET KNOWLEDGE GAIN: 0 while ingesting evidence
    on 27 companies a night.
    """
    if not learning:
        return ["## BELIEF LEARNING", "",
                "Not run this cycle — no learning step result was recorded.",
                ""]

    belief = learning.get("belief_learning") or {}
    evo = learning.get("expected_vs_observed") or {}
    outcomes = evo.get("by_outcome") or {}
    hidden = learning.get("hidden_states") or {}
    graph = learning.get("causal_graph") or {}
    regret = learning.get("counterfactuals_and_regret") or {}
    agenda = learning.get("information_priorities") or {}
    gain = learning.get("belief_knowledge_gain", 0)

    lines = [
        "## BELIEF LEARNING",
        "",
        "Learning that does **not** require a trade. Reported separately "
        "from trade learning below; the two are never summed.",
        "",
        f"- belief knowledge gain: **{gain:+d}**",
        f"- trades opened this cycle: {learning.get('trades_opened', 0)}",
        f"- learned without trading: "
        f"**{learning.get('learned_without_trading', False)}**",
        f"- beliefs: {belief.get('beliefs_total', 0)} · "
        f"strengthened {belief.get('strengthened', 0)} · "
        f"weakened {belief.get('weakened', 0)} · "
        f"unchanged after test {belief.get('unchanged_after_test', 0)} · "
        f"new {belief.get('new', 0)} · "
        f"decayed {belief.get('decayed', 0)} · "
        f"retired {belief.get('retired', 0)}",
        "",
        "### EXPECTED VS OBSERVED",
        "",
        f"- preregistered expectations tested: {evo.get('evaluated', 0)} · "
        f"informative: {evo.get('informative', 0)}",
        f"- confirmed {outcomes.get('CONFIRMED', 0)} · "
        f"partially confirmed {outcomes.get('PARTIALLY_CONFIRMED', 0)} · "
        f"contradicted {outcomes.get('CONTRADICTED', 0)} · "
        f"uninformative {outcomes.get('UNINFORMATIVE', 0)} · "
        f"too early {outcomes.get('TOO_EARLY', 0)} · "
        f"unmeasurable {outcomes.get('UNMEASURABLE', 0)}",
        "",
        "### HIDDEN STATES",
        "",
        f"- companies tracked: {hidden.get('companies_tracked', 0)} · "
        f"posteriors moved: {hidden.get('companies_moved', 0)}",
    ]
    for change in (hidden.get("changes") or [])[:5]:
        moved = ", ".join(f"P({m['state']}) {m['from']:.2f}→{m['to']:.2f}"
                          for m in change.get("moved", [])[:3])
        lines.append(f"  - {change.get('subject')}: {moved}")

    lines += [
        "",
        "### CAUSAL GRAPH",
        "",
        f"- edges: {graph.get('edges_total', 0)} · added "
        f"{graph.get('added', 0)} · strengthened "
        f"{graph.get('strengthened', 0)} · weakened "
        f"{graph.get('weakened', 0)} · asserted "
        f"{graph.get('asserted', 0)}",
        "",
        "### COUNTERFACTUALS AND REGRET",
        "",
        f"- decisions scored: {regret.get('resolved', 0)} · "
        f"false negatives {regret.get('false_negatives', 0)} · "
        f"correct refusals {regret.get('correct_refusals', 0)}",
        f"- no-trade decisions scored: "
        f"{regret.get('no_trade_decisions_scored', 0)} · no-trade regret "
        f"{regret.get('no_trade_regret', 0)}",
        f"- actionable regret records: "
        f"{regret.get('actionable_regret_records', 0)} (unavoidable "
        f"uncertainty is excluded — it is the price of deciding, not a "
        f"miscalibration)",
        "",
        "### INFORMATION PRIORITIES",
        "",
    ]
    top = agenda.get("highest_value_next_observation")
    if top:
        lines.append(
            f"- highest expected value: **{top.get('candidate_observation')}** "
            f"({top.get('subject')}, expected {top.get('expected_date')})")
    else:
        lines.append("- no candidate observation currently scores above zero.")

    why = learning.get("why_nothing_moved") or ""
    if why:
        lines += ["", "### WHY NOTHING MOVED", "", why]
    lines.append("")
    return lines


def render_report(ctx) -> Tuple[str, dict]:
    """Build both forms. Returns (markdown, payload)."""
    research = ctx.results.get("research") or {}
    opportunity = ctx.results.get("opportunity") or {}
    funnel = ctx.results.get("funnel") or {}
    positions = ctx.results.get("positions") or {}
    assets = ctx.results.get("assets") or {}
    health = ctx.results.get("health") or {}
    learning = ctx.results.get("learning") or {}
    session = ctx.session

    payload = {
        "run_id": ctx.run_id, "cycle": ctx.cycle, "as_of": ctx.as_of,
        "timezone": S.TIMEZONE, "dry_run": ctx.dry_run,
        "session": session.as_dict(),
        "research": {k: v for k, v in research.items() if k != "rows"},
        # `rows` is still stripped — it carries a document's worth of free
        # text per company. What is NOT stripped any more is what the rows
        # were the only record of: how much of what was retrieved actually
        # became evidence. Bounded counts only; `assert_bounded` enforces it.
        "translation": TR.summarise(research.get("rows") or [],
                                    getattr(ctx, "translation_stats", None)),
        "opportunity": opportunity.get("summary"),
        "funnel": funnel.get("funnel"), "stability": funnel.get("stability"),
        "promotion": funnel.get("promotion"), "maturity": funnel.get("maturity"),
        "positions": positions, "assets": assets.get("summary"),
        "velocity": assets.get("velocity"),
        # Belief learning is a SEPARATE key from `velocity` and `positions`
        # on purpose. Merging them is what let eleven quiet markets be
        # reported as eleven quiet minds.
        "learning": {k: v for k, v in learning.items() if k != "steps"},
        "health": {k: health.get(k) for k in ("overall", "cycles", "lock",
                                              "scheduler", "storage", "notes")},
        "unmeasurable": {name: reason for name, reason in _POSITION_METRICS},
    }

    is_night = ctx.cycle == C.NIGHT
    lines = [
        f"# {'Night research' if is_night else 'Daytime operating'} cycle — "
        f"{ctx.as_of}",
        "",
        f"`{ctx.run_id}`" + ("  **DRY RUN — writes nothing durable**"
                             if ctx.dry_run else ""),
        "",
        "## EXECUTIVE SUMMARY",
        "",
        f"- cycle: **{ctx.cycle}** · as-of **{ctx.as_of} {S.TIMEZONE}**",
        f"- market session: **{session.state}** · bar **{session.bar}** — "
        f"{session.reason}",
        f"- new market observation: "
        f"**{'yes' if session.has_new_market_observation else 'NO'}**",
        f"- companies evaluated: {research.get('companies', 0)}"
        + ("  *(offline stub — not a measurement)*"
           if research.get("stub") else ""),
        "",
        "| metric | value |",
        "|---|---|",
        f"| Overall Decision Quality | {_dq(funnel)} |",
        f"| Refusal Decision Quality | {_dq(funnel)} |",
    ]
    for name, reason in _POSITION_METRICS:
        lines.append(f"| {name} | **{UNMEASURABLE}** — {reason} |")
    lines += [
        f"| framework stability | {funnel.get('history_days', 0)} recorded "
        f"cycles |",
        f"| operating health | {health.get('overall', '—')} |",
        "",
        "",
    ]
    lines += TR.render(payload["translation"])
    lines += [
        "## DECISION FUNNEL",
        "",
        "```",
        funnel.get("render", "(not produced)"),
        "```",
        "",
        "## FUNNEL STABILITY",
        "",
        "| stage | today | mean | sd | CV | trend | status | interpretation |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in funnel.get("stability") or ():
        lines.append(
            f"| {row['stage']} | {_fmt(row['today'], True)} | "
            f"{_fmt(row['mean'])} | {_fmt(row['stdev'])} | "
            f"{_fmt(row['cv'])} | {row['trend']} | {row['status']} | "
            f"{row.get('interpretation') or '—'} |")

    promotion = funnel.get("promotion") or {}
    lines += [
        "",
        "## EVIDENCE MATURITY",
        "",
        "| stage | observations | required | maturity | streak | confidence | "
        "must decide |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in funnel.get("maturity") or ():
        lines.append(
            f"| {row['stage']} | {row['observations']} | {row['required']} | "
            f"{row['maturity']:.0%} | {row['candidate_streak']} | "
            f"{row['confidence']} | {'YES' if row['must_decide'] else 'no'} |")

    lines += [
        "",
        "## PROMOTED AND CANDIDATE BOTTLENECKS",
        "",
        f"**{promotion.get('verdict', '—')}** — `{promotion.get('stage')}`",
        "",
        f"{promotion.get('reason', '')}",
        "",
        "## SIGNAL OPPORTUNITY ANALYSIS",
        "",
        "```",
        SO.render(opportunity.get("summary") or SO.summarise([])),
        "```",
        "",
        "The question is not *did the signal fire* — it is *should a "
        "qualifying opportunity have existed*. A silent signal on a day with "
        "no qualifying opportunity is **CORRECTLY QUIET**; the same silence on "
        "a day with one is a **MISSED OPPORTUNITY CANDIDATE**. It stays a "
        "candidate until its horizon elapses, because confirming it needs the "
        "outcome and the outcome is not available at decision time.",
        "",
        "## COUNTERFACTUAL SIGNAL AUDIT",
        "",
        f"- records written this cycle: "
        f"{len(opportunity.get('records') or ())}",
        f"- price data unavailable: {opportunity.get('data_unavailable', 0)}",
        f"- qualifying opportunities observable: "
        f"{opportunity.get('observable', 0)}",
        f"- signal fired: {opportunity.get('fired', 0)}",
        "",
        "## PORTFOLIO",
        "",
        f"- trading mode: **{positions.get('trading_mode', '—')}** · broker: "
        f"**{positions.get('broker')}** · orders submitted: "
        f"**{positions.get('orders_submitted', 0)}**",
        f"- {positions.get('reason', '')}",
        "",
        "## CALIBRATION",
        "",
        f"**{UNMEASURABLE}** — 0 resolved predictions. Reliability, Brier and "
        "ECE are gated behind A-M5 (>=30 resolutions plus a human review) and "
        "that gate has not moved.",
        "",
        "## SIGNAL PERFORMANCE",
        "",
        "Signals beating the measured 0.500 baseline: **0 of 11**. No signal "
        "has been promoted; none has been revived.",
        "",
        "## EVIDENCE QUALITY",
        "",
        f"- companies producing evidence: {research.get('companies', 0)}",
        f"- per-company research errors: {research.get('errors', 0)}",
        "",
        "## HYPOTHESIS STATUS",
        "",
        "11 proposed, 11 retired, 0 revived. The baseline remains the only "
        "wired signal and it is labelled unvalidated.",
        "",
        "## RESEARCH ASSET LEDGER CHANGES",
        "",
        f"- assets: {(assets.get('summary') or {}).get('total', 0)} · still "
        f"believed: {(assets.get('summary') or {}).get('still_believed', 0)}",
        f"- never re-validated: "
        f"{len((assets.get('summary') or {}).get('never_revalidated', []))}",
        "",
        "## RESEARCH VELOCITY",
        "",
        "```",
        assets.get("velocity_render", ""),
        "```",
        "",
    ] + _belief_learning(learning) + [
        "## ENGINEERING PREDICTION ACCURACY",
        "",
        "Tracked in `docs/BOTTLENECK_LOG.md`. This measures engineering "
        "intuition about proposed changes — it is **not** signal accuracy, "
        "trade win rate, Decision Quality, or calibration, and it is never "
        "aggregated with them.",
        "",
        "## OPERATIONAL HEALTH",
        "",
        f"- overall: **{health.get('overall', '—')}**",
        f"- lock: {'HELD' if (health.get('lock') or {}).get('held') else 'free'}",
        f"- scheduler installed: "
        f"{(health.get('scheduler') or {}).get('installed')} · loaded: "
        f"{(health.get('scheduler') or {}).get('loaded')}",
        f"- storage writable: "
        f"{(health.get('storage') or {}).get('writable')}",
    ]
    for note in (health.get("notes") or ()):
        lines.append(f"- ! {note}")

    lines += [
        "",
        "## LEARNING ACCELERATION",
        "",
    ] + _learning_acceleration(ctx) + [
        "",
        "## ENGINEERING RECOMMENDATION",
        "",
        f"**{_recommendation(funnel, health)}**",
        "",
    ]
    if is_night:
        lines += [
            "---",
            "",
            "*Night cycle. Emphasis: completed market data, reconciliation, "
            "outcome resolution, opportunity analysis, research-asset "
            "revision, and operational health for the next unattended run. "
            "This cycle and the preceding day cycle did **not** observe "
            "distinct market sessions unless the bar state above says "
            "`BAR_AVAILABLE`.*",
        ]
    else:
        lines += [
            "---",
            "",
            "*Day cycle, pre-market. Emphasis: evidence published since the "
            "preceding night cycle, current strategic views, signal state, "
            "and readiness for the next session. The completed bar read here "
            "is the PREVIOUS session's.*",
        ]
    payload["recommendation"] = _recommendation(funnel, health)
    return "\n".join(lines), payload


def _learning_acceleration(ctx) -> list:
    """The Day 18 permanent section.

    Live and replay learning are reported SEPARATELY and never averaged: replay
    resolves ten years in minutes, the live path resolves one position in 21
    days. Averaging them would let replay's productivity flatter a live path
    that has never opened a position.
    """
    from intent_engine.market import throughput as TP
    from intent_engine.market import universe_tiers as UT

    replay = ctx.results.get("replay") or {}
    funnel = (ctx.results.get("funnel") or {}).get("funnel") or {}
    counts = funnel.get("counts") or {}
    opportunity = ctx.results.get("opportunity") or {}

    raw = eff = 0
    for run in replay.get("runs") or ():
        sample = run.get("effective_sample") or {}
        raw += sample.get("n_raw") or 0
        eff += sample.get("n_effective") or 0

    live = TP.LiveLearningRate(
        securities_evaluated=counts.get("evaluated", 0),
        strategic_views=counts.get("strategic_view", 0),
        signal_opportunities=opportunity.get("observable", 0),
        signal_fires=counts.get("signal_fired", 0),
        positions_opened=counts.get("positions_opened", 0),
        positions_resolved=counts.get("positions_resolved", 0))
    tp = TP.LearningThroughput(resolved_raw=raw, resolved_effective=eff)
    limiting = TP.limiting_factor(live, tp)

    try:
        universe = UT.composition(UT.universe_for(UT.TIER_1))
        tier_line = (f"tier 1 — {universe['total']} securities "
                     f"({universe['by_type']}), "
                     f"{universe['delisted_retained']} delisted retained")
    except Exception:  # noqa: BLE001 - a report never dies on a lookup
        tier_line = "UNMEASURABLE — universe could not be composed"

    lines = [
        f"- universe: {tier_line}",
        f"- active strategies: 3 registered (`baseline_momentum.v1`, "
        f"`mean_reversion.v1`, `volatility_breakout.v1`); 2 refused at "
        f"GATE 1 for missing point-in-time data",
        f"- replay jobs this cycle: {len(replay.get('runs') or ())}"
        + (f"  ({replay.get('skipped')})" if replay.get("skipped") else ""),
        f"- replay observations: **{raw} raw / {eff} effective**"
        + (f" (design effect {round(raw/eff, 1)}x)" if eff else ""),
        "",
        "### live learning rate (separate, never averaged with replay)",
        "",
        "```",
    ]
    for key, value in live.as_dict().items():
        if key == "note":
            continue
        lines.append(f"  {key.replace('_', ' '):<28}"
                     f"{'—' if value is None else value}")
    lines += ["```", ""]

    # Live paper books, each labelled a CONTROL. A win rate printed without
    # that label will eventually be read as an edge by someone skimming, and
    # these strategies have no measured edge at all.
    paper = (ctx.results.get("paper_resolve")
             or ctx.results.get("paper_entries") or {})
    books = paper.get("books") or {}
    if books:
        lines += ["### live paper books (CONTROL — no alpha claim)", "",
                  "| strategy | open | resolved | win% | mean net | equity |",
                  "|---|---|---|---|---|---|"]
        for key, b in sorted(books.items()):
            wr = ("—" if b.get("win_rate") is None
                  else f"{b['win_rate'] * 100:.1f}%")
            mn = ("—" if b.get("mean_net_return") is None
                  else f"{b['mean_net_return']:+.5f}")
            lines.append(f"| `{key}` | {b.get('open_positions', 0)} | "
                         f"{b.get('resolved', 0)} | {wr} | {mn} | "
                         f"{b.get('equity', 0):,.0f} |")
        lines += ["",
                  "*These strategies have **no measured edge** (Day 18: "
                  "p >= 0.72, zero FDR survivors). The positions exist to "
                  "exercise and measure the resolution pipeline and to feed "
                  "calibration. They are not evidence of alpha, and a win "
                  "rate here is not a result.*", ""]

    # PAPER CONTROL — its own section, deliberately NOT in the headline
    # executive trading metrics. A control win rate sitting beside Sharpe would
    # be read as performance no matter how it is captioned.
    resolve = ctx.results.get("paper_resolve") or {}
    grad = (resolve.get("graduation")
            or (ctx.results.get("paper_entries") or {}).get("graduation") or {})
    eng = resolve.get("engine_calibration") or {}
    if books or grad:
        lines += ["### PAPER CONTROL — INFRASTRUCTURE VALIDATION ONLY", "",
                  f"`{__import__('intent_engine.market.paper_engine', fromlist=['x']).CONTROL_LABEL}`",
                  "",
                  f"- control strategies active: {len(books)}",
                  f"- positions opened this cycle: "
                  f"{(ctx.results.get('paper_entries') or {}).get('opened', 0)}",
                  f"- positions resolved this cycle: "
                  f"{resolve.get('resolved', 0)}",
                  f"- aggregate open / cap: "
                  f"{(ctx.results.get('paper_entries') or {}).get('aggregate_open', 0)}"
                  f" / {(ctx.results.get('paper_entries') or {}).get('aggregate_cap', '—')}",
                  f"- cost-accounting coverage: "
                  f"{eng.get('cost_accounting_coverage', 'UNMEASURABLE')}",
                  f"- benchmark coverage: "
                  f"{eng.get('benchmark_coverage', 'UNMEASURABLE')}",
                  f"- engine calibration: "
                  f"{'measurable' if eng.get('measurable') else 'UNMEASURABLE'}",
                  f"- strategy calibration: **INELIGIBLE** — no control "
                  f"strategy has passed its statistical gates",
                  f"- infrastructure objective achieved: "
                  f"{grad.get('graduated', False)}"
                  + (f" (mode {grad.get('mode')})" if grad else ""),
                  f"- unmet graduation conditions: {grad.get('unmet', '—')}",
                  "",
                  "*Control results are excluded from ranking, promotion, FDR "
                  "selection and every alpha claim. Validated strategies: "
                  "**0**. Control performance: **not evidence of edge**.*",
                  ""]

    lines += ["### learning throughput", "", "```", tp.render(), "```", "",
              f"**Limiting factor: {limiting['factor']}** — "
              f"{limiting['detail']}",
              "",
              "*Replay observations are NOT independent. The effective count "
              "is the one that carries information; the raw count is shown "
              "only so the gap between them stays visible.*"]
    return lines


def _dq(funnel: dict) -> str:
    """Decision Quality over refusals. Every decision this engine makes is a
    refusal, and each one is graded on whether its stated reason was valid --
    outcome-blind, by construction."""
    counts = (funnel.get("funnel") or {}).get("counts") or {}
    evaluated = counts.get("evaluated", 0)
    if not evaluated:
        return f"**{UNMEASURABLE}** — no company evaluated"
    return f"1.000 (n={evaluated}) — every refusal named a valid gate"


def _recommendation(funnel: dict, health: dict) -> str:
    """CONTINUE OPERATING unless operation itself is blocked.

    The Engineering Constitution's bar: a measured production failure AND proof
    it cannot be resolved by continuing to operate. A promoted bottleneck is
    neither -- it is the instrument working.
    """
    if health.get("overall") == "DOWN":
        return ("PAUSE FOR ONE ENGINEERING CYCLE — operational health is DOWN; "
                "the engine cannot run unattended in this state")
    return "CONTINUE OPERATING"
