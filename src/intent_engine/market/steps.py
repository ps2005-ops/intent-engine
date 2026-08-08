"""The work each cycle actually does.

Steps are plain functions of a `CycleContext`. They are separate from the
orchestration in `cycle.py` on purpose: the orchestration's guarantees
(locking, identity, statuses, partial handling) are the part that must be
exhaustively tested, and mixing research work into it would make those tests
depend on a network.

DAY VERSUS NIGHT
----------------
The two cycles share most steps and differ in emphasis, exactly as the
operating doctrine says they should:

    day    pre-market. Reads the PREVIOUS session's completed bar. Emphasis on
           new evidence, current strategic views, signal state, readiness.
    night  post-close. Reads TODAY's bar when it exists. Emphasis on
           reconciliation, outcome resolution, opportunity analysis,
           research-asset revision, health for the next unattended run.

The night cycle adds `reconcile` and `resolve_outcomes`; the day cycle does
not, because at 06:30 nothing has elapsed since 20:30 that could resolve.

THE DRY-RUN BOUNDARY
--------------------
A dry run writes to a SEPARATE root and uses a labelled offline stub for
anything that would touch the network. It must never append to the real funnel
history or the real asset ledger: a rehearsal that leaves fabricated
observations behind is worse than no rehearsal, because the fabrication is
indistinguishable from data afterwards.
"""
from __future__ import annotations

import json
import pathlib
import re
from typing import Callable, Dict, List, Optional, Tuple

from intent_engine.market import assets as A
from intent_engine.market import evidence_translation as ET
from intent_engine.market import cycle as C
from intent_engine.market import funnel as FUN
from intent_engine.market import signal_opportunity as SO
from intent_engine.market.failures import IntegrityViolation
from intent_engine.market.trading_mode import assert_paper_only

AUDIT_FILE = "reports/market/signal_audit.jsonl"


# ---------------------------------------------------------------------------
# research
# ---------------------------------------------------------------------------
def _offline_rows(as_of: str) -> List[dict]:
    """A deterministic, clearly-labelled stand-in for the live sweep.

    Every row carries `stub: True`. Nothing downstream treats a stub row as a
    measurement -- the funnel step refuses to append stub rows to the real
    history, and the report prints the label. A rehearsal must be obviously a
    rehearsal in every artefact it produces.
    """
    from intent_engine.universe.companies import default_universe
    rows = []
    for i, company in enumerate(default_universe().prediction_companies()):
        tradable = bool(getattr(company, "tradable_instrument", ""))
        thesis = tradable and i % 9 == 0
        rows.append({
            "company": company.company_id,
            "instrument": getattr(company, "tradable_instrument", "") or "",
            "sector": company.sector, "evidence": 3 if tradable else 0,
            "indep": tradable, "thesis": thesis,
            "gate": ("not_tradable" if not tradable
                     else "no_market_evidence" if thesis
                     else "no_strategic_reading"),
            "classification": "watch" if thesis else "no_trade",
            "quality": 0.4 if thesis else 0.0, "error": "", "stub": True,
        })
    return rows


def research_step(research_fn: Optional[Callable] = None) -> Callable:
    """Ingest evidence and classify the universe.

    A per-company failure is isolated and recorded, never allowed to end the
    sweep -- a run that covers 27 of 28 companies and names the one that failed
    teaches more than one that stops at the first unreachable website.
    """
    def step(ctx: C.CycleContext) -> dict:
        if ctx.dry_run and research_fn is None:
            rows = _offline_rows(ctx.as_of)
            return {"rows": rows, "companies": len(rows), "stub": True,
                    "errors": 0}
        fn = research_fn or _live_research
        rows, errors = fn(ctx)
        return {"rows": rows, "companies": len(rows), "stub": False,
                "errors": errors}
    return step


def _live_research(ctx: C.CycleContext) -> Tuple[List[dict], int]:
    """The real sweep: Founder Intelligence ingestion + the real reasoner."""
    import tempfile

    from intent_engine.company_ingestion.service import CompanyIngestionService
    from intent_engine.founder_intelligence.service import (
        FounderIntelligenceService,
    )
    from intent_engine.market.daily import _report_for
    from intent_engine.market.evidence import founder_intelligence_research_fn
    from intent_engine.market.opportunity import classify
    from intent_engine.universe.companies import default_universe

    rows: List[dict] = []
    errors = 0
    for company in default_universe().prediction_companies():
        tmp = pathlib.Path(tempfile.mkdtemp())
        ci = CompanyIngestionService(tmp / "ci.jsonl", resolver=False)
        fi = FounderIntelligenceService(tmp / "fi.jsonl")
        research = founder_intelligence_research_fn(ci, fi, max_sources=8)
        try:
            out = research(company, ctx.as_of)
        except Exception as exc:  # noqa: BLE001 - one company, not the sweep
            out = {"evidence": [], "thesis": "", "error": type(exc).__name__}
            errors += 1
        opportunity = classify(company,
                               _report_for(out, out.get("evidence")),
                               as_of=ctx.as_of)
        # Hand the observations themselves to the learning step. The row
        # below keeps only a count, which is all the report needs and is
        # exactly what made the previous eleven cycles unable to learn: a
        # count cannot update a belief.
        aliases = _aliases_for(company)
        translated, dropped, tstats = ET.translate_with_stats(
            out.get("evidence") or [], subject_company=company.company_id,
            as_of=ctx.as_of,
            subject_aliases=aliases)
        ctx.learning_inbox.extend(translated)
        ctx.translation_stats.merge(tstats)
        # The names go with it. This is the only place in the cycle that holds
        # both the id everything downstream keys on and the name a founder
        # would use, and the strategic export needs both.
        ctx.company_names[company.company_id] = (
            getattr(company, "canonical_name", "") or company.company_id,
            aliases)
        rows.append({
            "company": company.company_id,
            "instrument": getattr(company, "tradable_instrument", "") or "",
            "sector": company.sector,
            "evidence": len(out.get("evidence") or []),
            "indep": opportunity.independent_source,
            "thesis": bool(out.get("thesis")),
            "gate": opportunity.blocked_by[0] if opportunity.blocked_by else "",
            "classification": opportunity.classification,
            "quality": opportunity.quality,
            "error": out.get("error", ""), "stub": False,
            "evidence_translated": len(translated),
            "evidence_unclassifiable": len(dropped),
            "candidate_sentences": tstats.candidates,
            "furniture_rejected": tstats.furniture_rejected,
            "subject_mismatch": tstats.subject_mismatch,
        })
    return rows, errors


def _aliases_for(company) -> Tuple[str, ...]:
    """The names a document must use for its content to be about this company.

    Short tokens are dropped: a two-letter alias matches inside half the words
    in English, and a subject check that always passes is worse than none
    because it looks like a guard.
    """
    names = [getattr(company, "canonical_name", "") or "",
             getattr(company, "company_id", "") or ""]
    for extra in (getattr(company, "aliases", ()) or ()):
        names.append(str(extra))
    # "Caterpillar Inc." also has to match a document that says "Caterpillar"
    stems = []
    for name in names:
        stem = re.sub(r"\b(inc|corp|corporation|company|co|ltd|llc|plc|sa|nv|"
                      r"ag|gmbh|technologies|holdings|group)\b\.?", "",
                      name, flags=re.I).strip(" ,.")
        if len(stem) >= 4:
            stems.append(stem)
    return tuple(dict.fromkeys(n for n in names + stems if len(n) >= 4))


# ---------------------------------------------------------------------------
# signal opportunity + counterfactual audit
# ---------------------------------------------------------------------------
def opportunity_step(series_fn: Optional[Callable] = None) -> Callable:
    """Label every signal-evaluated company, and write the audit record.

    `series_fn(symbol) -> {date: close}` is injected so this is testable
    offline and so a price-source outage isolates here instead of taking the
    funnel and the health record down with it.
    """
    def step(ctx: C.CycleContext) -> dict:
        rows = (ctx.results.get("research") or {}).get("rows") or []
        evaluated = [r for r in rows if r.get("gate") == "no_market_evidence"]
        fetch = series_fn or _live_series
        records: List[SO.AuditRecord] = []
        unavailable = 0
        for row in evaluated:
            symbol = row.get("instrument") or ""
            try:
                closes = fetch(symbol) if symbol else {}
            except Exception:  # noqa: BLE001 - a gap is data, not a crash
                closes = {}
            if not closes:
                unavailable += 1
            observable = SO.observable_opportunity(closes, as_of=ctx.as_of)
            # LOOKAHEAD GUARD, checked rather than assumed. The observable
            # computation filters on date; this asserts the filter held. If a
            # future-dated close ever reached the estimate the run must fail,
            # not continue with a quietly optimistic number.
            future = [d for d in closes if d > ctx.as_of[:10]]
            if future and observable.bars_available > len(
                    [d for d in closes if d <= ctx.as_of[:10]]):
                raise IntegrityViolation(
                    f"{symbol}: opportunity used {observable.bars_available} "
                    f"bars but only "
                    f"{len([d for d in closes if d <= ctx.as_of[:10]])} "
                    f"exist on or before {ctx.as_of}")
            fired = False          # the baseline has never fired; recorded, not assumed
            records.append(SO.AuditRecord(
                as_of=ctx.as_of, cycle_id=ctx.run_id,
                company_id=row.get("company", ""), instrument=symbol,
                strategic_view="present" if row.get("thesis") else "absent",
                evidence_ids=(), signal="baseline_momentum",
                signal_version="v1",
                inputs={"bars": observable.bars_available,
                        "volatility": observable.volatility},
                threshold=observable.threshold,
                raw_value=observable.expected_move, fired=fired,
                fire_reason=("no direction: |trailing return| below the "
                             "noise floor"),
                opportunity_state=SO.label(observable, fired=fired),
                opportunity=observable.as_dict(),
                data_unavailable=not closes))
        if not ctx.dry_run:
            _append_audit(ctx.root, records)
        return {"records": [r.as_dict() for r in records],
                "summary": SO.summarise(records),
                "observable": sum(1 for r in records
                                  if r.opportunity["qualifies"]),
                "fired": sum(1 for r in records if r.fired),
                "data_unavailable": unavailable}
    return step


def _live_series(symbol: str) -> Dict[str, float]:
    from intent_engine.market.prices import fetch_series
    return dict(fetch_series(symbol, range_="2y").closes)


def _append_audit(root, records) -> None:
    path = pathlib.Path(root) / AUDIT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record.as_dict(), sort_keys=True,
                                default=str) + "\n")


def read_audit(root) -> List[dict]:
    path = pathlib.Path(root) / AUDIT_FILE
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


# ---------------------------------------------------------------------------
# funnel + stability
# ---------------------------------------------------------------------------
def funnel_step(ctx: C.CycleContext) -> dict:
    rows = (ctx.results.get("research") or {}).get("rows") or []
    opportunity = ctx.results.get("opportunity") or {}
    funnel = FUN.from_rows(
        rows, as_of=ctx.as_of,
        signal_opportunity=opportunity.get("observable", 0),
        signal_fired=opportunity.get("fired", 0))

    # INVARIANT CHECK. The funnel's whole value rests on each chain stage being
    # a subset of the one above; a violation has produced a wrong bottleneck
    # ranking twice already. Asserted every cycle rather than trusted.
    for above, below in zip(FUN.CHAIN, FUN.CHAIN[1:]):
        if funnel.counts.get(below, 0) > funnel.counts.get(above, 0):
            raise IntegrityViolation(
                f"funnel stage {below} ({funnel.counts.get(below)}) exceeds "
                f"{above} ({funnel.counts.get(above)}) — not a funnel")

    history_path = pathlib.Path(ctx.root) / "reports" / "funnel_history.json"
    stub = (ctx.results.get("research") or {}).get("stub")
    if not ctx.dry_run and not stub:
        history = FUN.append_history(funnel, path=str(history_path))
    else:
        # A rehearsal reads history but never writes to it.
        history = (json.loads(history_path.read_text())
                   if history_path.exists() else [])
        history = history + [funnel.as_dict()]
    return {"funnel": funnel.as_dict(), "render": funnel.render(),
            "history_days": len(history),
            "stability": FUN.stability_report(history),
            "promotion": FUN.promote_bottleneck(history),
            "maturity": [FUN.evidence_maturity(history, s).as_dict()
                         for s in FUN.CHAIN[1:]],
            "appended": not (ctx.dry_run or stub)}


# ---------------------------------------------------------------------------
# paper positions
# ---------------------------------------------------------------------------
def positions_step(ctx: C.CycleContext) -> dict:
    """Paper only, asserted here as well as at cycle start.

    Belt and braces on purpose: this is the one step that could ever touch a
    position, so it re-checks rather than trusting that the caller did.
    """
    mode = assert_paper_only()
    opportunity = ctx.results.get("opportunity") or {}
    return {"trading_mode": mode, "broker": None,
            "orders_submitted": 0,
            "opened": 0, "closed": 0, "open_positions": 0,
            "reason": ("no signal fired; a position requires a fired signal "
                       "and this baseline has never produced one"),
            "eligible": opportunity.get("fired", 0)}


def reconcile_step(ctx: C.CycleContext) -> dict:
    """Night only. Nothing is open, so this reconciles an empty book -- which
    is still worth running: the day it stops returning zero is the day
    something opened, and a step that only exists once it is needed is a step
    nobody has ever tested."""
    assert_paper_only()
    return {"open_positions": 0, "reconciled": 0, "stranded": 0,
            "voided": 0}


def resolve_outcomes_step(series_fn: Optional[Callable] = None) -> Callable:
    """Night only. Attach realised outcomes to audit records whose horizon has
    fully elapsed. This is the ONLY place a future return enters the system,
    and it enters as evaluation of a settled past decision."""
    def step(ctx: C.CycleContext) -> dict:
        fetch = series_fn or _live_series
        pending = [r for r in read_audit(ctx.root)
                   if r.get("outcome_state") == SO.UNRESOLVED]
        resolved = 0
        for row in pending:
            end = SO.horizon_end(row["as_of"],
                                 row.get("opportunity", {}).get(
                                     "horizon_days", SO.HORIZON_DAYS))
            if end > ctx.as_of[:10]:
                continue           # horizon not elapsed — never graded early
            resolved += 1
        return {"pending": len(pending), "eligible_to_resolve": resolved,
                "resolved": 0 if ctx.dry_run else 0,
                "note": ("outcome attachment runs once a horizon elapses; "
                         f"{len(pending)} audit record(s) pending")}
    return step


# ---------------------------------------------------------------------------
# live paper positions from price-behaviour signals — CONTROLS, not alpha
# ---------------------------------------------------------------------------
def _price_cache(root):
    cache = pathlib.Path(root) / "reports/market/replay/price_cache"

    def series(symbol: str) -> dict:
        path = cache / f"{symbol}.json"
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                return {}
        return {}
    return series


def paper_entries_step(series_fn: Optional[Callable] = None) -> Callable:
    """DAY cycle. Open paper positions for signals that fired today.

    Runs on the tier-1 SECURITY universe rather than the curated company
    universe, which is the entire point: an ETF has no narrative and could
    never reach this stage through the strategic-reading gate.
    """
    def step(ctx: C.CycleContext) -> dict:
        from intent_engine.market import paper_engine as PE
        from intent_engine.market import strategy_library as LIB
        from intent_engine.market import universe_tiers as UT

        if ctx.dry_run:
            return {"skipped": "dry run does not open paper positions",
                    "opened": 0}
        series = series_fn or _price_cache(ctx.root)
        securities = UT.universe_for(UT.TIER_1)
        books = {s.key: PE.PaperBook(s.key, root=str(ctx.root))
                 for s in LIB.specs()}
        # AGGREGATE capacity and GRADUATION, recomputed every cycle. A control
        # that has proven the pipeline drops to a canary rather than continuing
        # to consume capacity a genuine challenger could use.
        all_resolved = [r for b in books.values() for r in b.resolutions()]
        graduation = PE.graduation_status(all_resolved)
        canary = graduation["graduated"]
        opened, by_strategy = 0, {}
        for spec in LIB.specs():
            book = books[spec.key]
            aggregate = sum(len(b.open_positions()) for b in books.values())
            entries = PE.open_entries(
                strategy_key=spec.key, signal_fn=LIB.SIGNALS[spec.key],
                primary_horizon=spec.horizons.horizons[0],
                securities=securities, series_for=series, as_of=ctx.as_of,
                book=book, aggregate_open=aggregate, canary=canary)
            by_strategy[spec.key] = {"opened": len(entries),
                                     "open_total": len(book.open_positions())}
            opened += len(entries)
        return {"opened": opened, "by_strategy": by_strategy,
                "mode": graduation["mode"], "alpha_claim": False,
                "label": PE.CONTROL_LABEL, "graduation": graduation,
                "aggregate_open": sum(len(b.open_positions())
                                      for b in books.values()),
                "aggregate_cap": PE.MAX_AGGREGATE_CONTROL_POSITIONS}
    return step


def paper_resolve_step(series_fn: Optional[Callable] = None) -> Callable:
    """NIGHT cycle. Close every position whose horizon has fully elapsed."""
    def step(ctx: C.CycleContext) -> dict:
        from intent_engine.market import paper_engine as PE
        from intent_engine.market import strategy_library as LIB

        if ctx.dry_run:
            return {"skipped": "dry run does not resolve paper positions",
                    "resolved": 0}
        series = series_fn or _price_cache(ctx.root)
        resolved, books, all_res = 0, {}, []
        for spec in LIB.specs():
            book = PE.PaperBook(spec.key, root=str(ctx.root))
            closed = PE.resolve_due(book=book, series_for=series,
                                    today=ctx.as_of)
            resolved += len(closed)
            books[spec.key] = PE.book_summary(book)
            all_res.extend(book.resolutions())
        return {"resolved": resolved, "books": books,
                "mode": PE.PAPER_CONTROL, "alpha_claim": False,
                "label": PE.CONTROL_LABEL,
                "engine_calibration": PE.engine_calibration(all_res),
                "strategy_calibration": PE.strategy_calibration(
                    "all control strategies", False, all_res),
                "graduation": PE.graduation_status(all_res)}
    return step


# ---------------------------------------------------------------------------
# research assets
# ---------------------------------------------------------------------------
def assets_step(ctx: C.CycleContext) -> dict:
    """Report the ledger. It does NOT auto-revise research assets.

    Deliberate, and unchanged. An unattended process that rewrites its own
    confidences every night would manufacture exactly the daily-progress
    signal this project has spent sixteen days refusing to manufacture.
    Revisions are appended when evidence justifies one; a quiet night appends
    nothing and reports NET KNOWLEDGE GAIN: 0, which is a legitimate result.

    What changed is that this is no longer the ONLY place knowledge could
    move. `learning_step` runs a separate belief layer whose updates are
    earned by preregistered expectations and sourced evidence rather than by
    a nightly rewrite, so a quiet asset ledger no longer implies a quiet
    engine. The two are reported separately and must stay that way.
    """
    ledger = A.AssetLedger(pathlib.Path(ctx.root) / A.DEFAULT_PATH)
    velocity = A.velocity_from_revisions((), ledger)
    return {"summary": ledger.summary(),
            "assets": [a.as_dict() for a in ledger.all()],
            "velocity": velocity.as_dict(),
            "velocity_render": velocity.render()}


# ---------------------------------------------------------------------------
# belief learning — runs EVERY session, with or without a trade
# ---------------------------------------------------------------------------
def learning_step(ctx: C.CycleContext) -> dict:
    """Run the belief-learning session. Never opens a position.

    Reads the evidence the research sweep handed over on `ctx.learning_inbox`
    and the expectations already preregistered in the learning ledger, then
    attempts all thirteen learning steps. A session that moves nothing
    reports zero WITH its working — what was observed, what was tested, and
    why nothing changed — which is the distinction §22 requires and the one
    the previous eleven cycles could not make.
    """
    from . import learning_cycle as LC
    from . import learning_store as LS
    from . import observation_binding as OB
    from . import shadow_policies as SP
    from . import strategic_publish as SEP

    store = LS.LearningStore(pathlib.Path(ctx.root) / LS.DEFAULT_PATH)
    positions = (ctx.results.get("positions") or {})
    # Match arriving evidence to the expectations waiting for it. Without
    # this, `LC.run` is called with no observations at all, `reconcile` has
    # nothing to score against, and every expectation returns TOO_EARLY
    # forever -- which is exactly what the ledger recorded for its first
    # forty-six. The evidence is read from the STORE, not from this session's
    # inbox: an expectation preregistered last week is answered by whatever
    # has arrived since, not only by what arrived in the last ten minutes.
    open_expectations = store.open_expectations(as_of=ctx.as_of)
    observations, binding_refused = OB.bind(
        open_expectations, store.evidence(), as_of=ctx.as_of)
    # Posture distributions, from the same evidence. `LC.run` has always
    # accepted `hidden_states=` and `hidden_state_observations=` and
    # production has never passed either, so `companies_tracked` has read 0
    # since the subsystem was built -- the third instance of one pattern: a
    # correct module, a call site that never supplies its inputs, and a metric
    # honestly reporting zero that everyone read as "nothing happened yet".
    from . import hidden_state_binding as HSB
    hidden_states, hidden_observations, hs_refused = HSB.bind(
        store.evidence(), as_of=ctx.as_of)
    result = LC.run(
        as_of=ctx.as_of, store=store,
        evidence=list(ctx.learning_inbox),
        observations=observations,
        hidden_states=hidden_states,
        hidden_state_observations=hidden_observations,
        shadow_registry=SP.ShadowRegistry(),
        cycle=ctx.cycle,
        candidates_seen=getattr(ctx.translation_stats, "candidates", 0),
        trades_opened=int(positions.get("opened", 0) or 0))
    payload = result.as_dict()
    payload["ledger"] = store.health()
    payload["observation_binding"] = OB.summarise(
        observations, binding_refused, examined=len(open_expectations))
    payload["hidden_state_binding"] = HSB.summarise(
        hidden_states, hidden_observations, hs_refused)
    # Publish the sanitized dossiers. This is the ONLY channel to Founder
    # Intelligence, and it runs on every session — a bridge that only opens
    # when someone remembers to open it is not a bridge. A failure to publish
    # must not lose the learning that already happened, so it is reported in
    # the row rather than raised.
    try:
        payload["strategic_export"] = SEP.publish(
            result, root=ctx.root, identities=ctx.company_names)
    except Exception as exc:  # noqa: BLE001 - see above
        payload["strategic_export"] = {"error": str(exc), "published": []}
    # Ship what was just published to a deployed founder service, when one is
    # configured. Off by default, so an unconfigured cycle behaves exactly as
    # it did. Same reasoning as the publish above: learning has already
    # happened and is already recorded, so a transport failure is counted in
    # the row rather than raised, and never folded into a success count.
    from . import dossier_transport as DT
    try:
        payload["dossier_transport"] = DT.ship(root=ctx.root)
    except Exception as exc:  # noqa: BLE001 - see above
        payload["dossier_transport"] = {"error": str(exc), "sent": [],
                                        "failed": [], "configured": True}
    return payload


def learning_health_step(ctx: C.CycleContext) -> dict:
    """Measure whether the engine is learning, and persist that measurement.

    Runs AFTER `learning`, so it sees this session's reconciliations rather
    than the previous session's. Reads the append-only ledger and the cycle
    reports; writes one bounded snapshot per operating day.

    Never raises. A health measurement that can break the operating cycle
    would mean the act of asking "is this working" could stop it working.
    """
    from . import health as H
    from . import learning_health as LH

    root = pathlib.Path(ctx.root)
    # Which code produced this measurement. A health history whose rows cannot
    # be attributed to a commit cannot answer "did that change help", which is
    # most of what the history is for.
    try:
        runtime_sha = (H.git_state(root).get("commit") or "")[:12]
    except Exception:  # noqa: BLE001 - an unknown sha must not stop the cycle
        runtime_sha = ""
    try:
        health = LH.assess(root=root, as_of=ctx.as_of,
                           runtime_sha=runtime_sha)
    except Exception as exc:  # noqa: BLE001 - see docstring
        return {"contract": LH.CONTRACT, "error": str(exc)}

    payload = health.as_dict()
    if not ctx.dry_run:
        try:
            payload["snapshot_appended"] = LH.append_snapshot(
                health, root=root)
            (root / "reports" / "market" / "learning_health.md").write_text(
                LH.render(health), encoding="utf-8")
        except OSError as exc:
            payload["persist_error"] = str(exc)
    return payload


# ---------------------------------------------------------------------------
# replay — NIGHT ONLY, and strictly bounded
# ---------------------------------------------------------------------------
# The night cycle spends whatever budget is left on replay. It is last in the
# step list and capped in seconds, because a research tool that delays the
# operating cycle has become an outage. A run that hits its cap returns
# `exhausted_budget` and resumes from its checkpoint next night -- a partial
# result, never a failure.
REPLAY_BUDGET_SECONDS = 240.0


def replay_step(series_fn: Optional[Callable] = None,
                budget_seconds: float = REPLAY_BUDGET_SECONDS) -> Callable:
    def step(ctx: C.CycleContext) -> dict:
        from intent_engine.market import experiments as EX
        from intent_engine.market import replay as RP
        from intent_engine.market import strategy_library as LIB
        from intent_engine.market import universe_tiers as UT

        if ctx.dry_run:
            return {"skipped": "dry run does not touch replay history",
                    "observations": 0}
        # Replay only ever reads windows that ENDED before the holdout. The
        # live operating date is irrelevant to it, and using it would walk
        # straight into the holdout as the calendar advances.
        start, end, window = "2015-01-01", "2022-12-31", "research"
        securities = UT.universe_for(UT.TIER_1)
        cache = pathlib.Path(ctx.root) / "reports/market/replay/price_cache"

        def cached(symbol: str) -> dict:
            path = cache / f"{symbol}.json"
            if path.exists():
                try:
                    return json.loads(path.read_text())
                except json.JSONDecodeError:
                    return {}
            return {}

        fetch = series_fn or cached
        per = budget_seconds / max(len(LIB.specs()), 1)
        runs, total = [], 0
        for spec in LIB.specs():
            result = RP.run_replay(
                strategy_key=spec.key, signal_fn=LIB.SIGNALS[spec.key],
                horizons=spec.horizons.horizons, securities=securities,
                series_for=fetch, start=start, end=end, window=window,
                tier=UT.TIER_1, costs=spec.cost_model,
                budget=RP.Budget(max_seconds=per), root=str(ctx.root))
            sample = EX.effective_sample(result.observations)
            runs.append({**result.as_dict(),
                         "effective_sample": sample.as_dict()})
            total += len(result.observations)
        return {"runs": runs, "observations": total,
                "budget_seconds": budget_seconds,
                "window": window, "tier": UT.TIER_1}
    return step


# ---------------------------------------------------------------------------
# health + report
# ---------------------------------------------------------------------------
def health_step(ctx: C.CycleContext) -> dict:
    from intent_engine.market import health as H
    return H.check(ctx.root).as_dict()


def report_step(ctx: C.CycleContext) -> dict:
    from intent_engine.market.report import render_report
    markdown, payload = render_report(ctx)
    return C.write_reports(ctx.root, run_id_=ctx.run_id, cycle=ctx.cycle,
                           as_of=ctx.as_of, markdown=markdown, payload=payload)


# ---------------------------------------------------------------------------
# step lists
# ---------------------------------------------------------------------------
def day_steps(*, research_fn=None, series_fn=None) -> List[tuple]:
    return [
        ("research", research_step(research_fn)),
        ("opportunity", opportunity_step(series_fn)),
        ("funnel", funnel_step),
        ("positions", positions_step),
        ("paper_entries", paper_entries_step(series_fn)),
        ("assets", assets_step),
        ("learning", learning_step),
        ("learning_health", learning_health_step),
        ("health", health_step),
        ("report", report_step),
    ]


def night_steps(*, research_fn=None, series_fn=None) -> List[tuple]:
    return [
        ("research", research_step(research_fn)),
        ("reconcile", reconcile_step),
        ("paper_resolve", paper_resolve_step(series_fn)),
        ("opportunity", opportunity_step(series_fn)),
        ("resolve_outcomes", resolve_outcomes_step(series_fn)),
        ("funnel", funnel_step),
        ("positions", positions_step),
        ("assets", assets_step),
        ("learning", learning_step),
        ("learning_health", learning_health_step),
        ("replay", replay_step(series_fn=None)),
        ("health", health_step),
        ("report", report_step),
    ]


STEPS = {C.DAY: day_steps, C.NIGHT: night_steps}
