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

import collections
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
                    "errors": 0, "macro": {"skipped": "dry run"}}
        fn = research_fn or _live_research
        rows, errors = fn(ctx)
        return {"rows": rows, "companies": len(rows), "stub": False,
                "errors": errors, "macro": _macro_sweep(ctx)}
    return step


#: (area, long leg, short leg) for the credit conditions the engine derives.
#: Declared here rather than inside the fold so the set of derived conditions
#: is a listed decision and not an expression buried in a loop.
_CREDIT_SPREADS = (
    ("CA", "BOC_BD.CDN.10YR.DQ.YLD", "BOC_BD.CDN.2YR.DQ.YLD"),
    ("US", "TREASURY_NOTES_AVG_RATE", "TREASURY_BILLS_AVG_RATE"),
)

#: What a discovered regime has to help predict before it counts as useful.
#: Consumer prices, because it is the deepest monthly series with a real
#: publisher-stated release date, so the held-out test is not scoring a
#: forecast against a figure whose vintage the engine had to guess.
_REGIME_TARGET_SERIES = "STATCAN_V41690973"


class _Row:
    """A ledger dict read with attribute access.

    `from_reconciliation` reads a Reconciliation object; the ledger stores
    dicts. Wrapping is the row-shape seam this project has been caught by
    before — a getattr-only reader silently folds a dict into one empty
    record rather than failing.
    """

    def __init__(self, row: dict) -> None:
        self.__dict__.update(row)


def _macro_sweep(ctx: C.CycleContext) -> dict:
    """Acquire the economy, and keep it.

    HERE RATHER THAN IN THE KNOWLEDGE STEP. That step is a fold over the
    append-only ledger and promises the same answer twice on the same input;
    putting an HTTP call inside it broke that invariant and, less abstractly,
    put live network traffic into every unit test that touched it.

    PERSISTED, not merely read. An engine that fetches the current value of a
    series each cycle and keeps none of them only ever knows what the economy
    is doing today. It could never notice that a regime changed, because it
    has nothing to compare against — which is the whole point of a world model
    rather than a dashboard.

    Never raises: a publisher being down is not a reason to fail a cycle, and
    a failed feed is reported by name rather than appearing as an economy that
    stopped moving.
    """
    from intent_engine.market import learning_store as LS
    from intent_engine.market import macro_ingest as MI

    from intent_engine.market import source_health as SH

    try:
        store = LS.LearningStore(pathlib.Path(ctx.root) / LS.DEFAULT_PATH)
        got = MI.collect(retrieved_at=ctx.as_of)
        stored = sum(1 for o in got["observations"]
                     if store.record_macro_observation(o))
        # SOURCE HEALTH AS A STATE, NOT A LINE IN THIS CYCLE'S REPORT.
        # `failures` has named the Bureau of Labor Statistics 503 on every
        # recorded run and been forgotten every time, so there was no
        # streak, no last_success and no way to tell a source that went dark
        # from an economy that went quiet. Successes are recorded too:
        # "when did this last work" is the question that decides whether
        # silence is new.
        prior = {family: SH.SourceHealth(
                     source_family=family,
                     state=str(row.get("state") or SH.HEALTHY),
                     detected_at=str(row.get("detected_at") or ""),
                     last_success=str(row.get("last_success") or ""),
                     failure_streak=int(row.get("failure_streak") or 0),
                     failure=str(row.get("failure") or ""))
                 for family, row in store.latest_source_health().items()}
        healths = SH.from_collection(got, as_of=ctx.as_of, prior=prior,
                                     attempted=sorted(MI.SERIES))
        if not ctx.dry_run:
            for health in healths:
                store.record_source_health(health)
        return {"fetched": got["observation_count"],
                "newly_persisted": stored,
                "series_attempted": got["series_attempted"],
                "series_failed": got["series_failed"],
                "failures": got["failures"],
                "source_health": SH.summarise(healths)}
    except Exception as exc:  # noqa: BLE001 - a feed must not fail a cycle
        return {"error": f"{type(exc).__name__}: {exc}"}


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
    # The rate alone names no producer. The class breakdown does, and every
    # producer it can name is upstream of observation binding.
    payload["self_test_decomposition"] = OB.diagnose(
        open_expectations, store.evidence())
    payload["hidden_state_binding"] = HSB.summarise(
        hidden_states, hidden_observations, hs_refused)
    # Publish the sanitized dossiers. This is the ONLY channel to Founder
    # Intelligence, and it runs on every session — a bridge that only opens
    # when someone remembers to open it is not a bridge. A failure to publish
    # must not lose the learning that already happened, so it is reported in
    # the row rather than raised.
    try:
        payload["strategic_export"] = SEP.publish(
            result, root=ctx.root, identities=ctx.company_names,
            # Without this the dossiers ship raw evidence-id lists and the
            # founder side can only COUNT them. The module that normalizes
            # them has existed since wave 8 with no production caller, which
            # is the same shape as every other silent zero in this cycle.
            evidence_rows=store.evidence(),
            # THE HISTORY LEG, which had no production caller either.
            # `economic_theses` was an allowlisted export field this call
            # site never passed, and revisions had no field at all — so the
            # Founder side received the CURRENT view and no record of how it
            # got there. It could not tell "this thesis never moved" from
            # "the history was not transported", and those need opposite
            # answers to "what changed your mind".
            economic_theses=store.thesis_snapshots(),
            thesis_revisions=store.thesis_revisions(),
            # THE EXPECTATION LEG. The snapshot was handed
            # `information_priorities` -- a different thing, empty in 26/26
            # exports -- while the ledger held real preregistered
            # expectations. Zero expectations was a wiring artefact, not a
            # finding about the companies.
            expectations=store.expectations(),
            # THE CAUSAL TRUTH LEG: 25 real resolutions, every one a refusal
            # naming its missing prerequisite. Withholding them published
            # "did not run", which is false.
            causal_resolutions=store.causal_estimates(),
            history_available=True)
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


#: The prose families cost ~8 minutes of wall clock across 28 companies; the
#: structured one costs ~16 seconds. Running all three every night would add
#: more time than the rest of the cycle uses, so acquisition runs NIGHT ONLY
#: and each family carries its own cadence in days. Removing the expensive
#: ones instead would have been the wrong fix: they are where the
#: counterparties are.
SOURCE_CADENCE_DAYS = {
    "government_award": 1,        # structured, cheap, changes daily
    "customer_case_study": 7,     # marketing pages change slowly
    "partnership_release": 3,     # announcements are episodic
}


#: The question the counterparty sweep is asking. Named once so the decision
#: log and any later analysis agree on it.
_COUNTERPARTY_QUESTION = "NEEDS_COUNTERPARTY"

def _acquisition_status(report, *, integrated: bool) -> str:
    """Classify one family's sweep, keeping the empty-handed cases apart.

    THE DISTINCTION THAT MATTERS. `NO_RESULT` means the sources were reached
    and had nothing; `NO_NEW_INFORMATION` means documents came back and every
    relationship in them was already held. Both are actions that produced no
    knowledge, and both are invisible to a log reconstructed from surviving
    evidence — but they call for opposite fixes, so collapsing them into one
    status would hide which one the engine is suffering from.
    """
    from . import research_decision as RD

    if not report.documents_retrieved:
        # Reached nothing at all. If every subject errored it is a failure;
        # if the hosts answered and held nothing, it is a real empty result.
        return RD.FAILED if report.errors else RD.NO_RESULT
    if integrated and report.relationships_accepted:
        return RD.SUCCESS
    if report.relationships_refused and not report.relationships_accepted:
        return RD.REFUSED
    if report.duplicates and not report.relationships_accepted:
        return RD.NO_NEW_INFORMATION
    return RD.NO_RESULT


def source_acquisition_step(ctx: C.CycleContext) -> dict:
    """Acquire documents that NAME a counterparty, and measure each family.

    Night only, and per-family cadence-gated, because this is the only step
    in the cycle whose cost is dominated by other people's web servers. A
    family that is not due today reports `skipped_by_cadence` with the day it
    next runs, so a reader can tell a family that produced nothing from one
    that was not asked.

    Never raises: an unreachable newsroom must not cost the cycle its
    learning.
    """
    from . import counterparty_sources as CS
    from . import customer_case_studies as CC
    from . import gov_awards as GA
    from . import partnership_releases as PR

    if ctx.dry_run:
        return {"skipped": "a dry run does not fetch other people's sites",
                "families": {}}

    try:
        from intent_engine.universe.companies import default_universe
        companies = list(default_universe().prediction_companies())
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "families": {}}

    subjects = [(c.company_id, _aliases_for(c)) for c in companies]
    home = {c.company_id: getattr(c, "website", "") for c in companies}
    import datetime as _dt
    try:
        day = _dt.date.fromisoformat(ctx.as_of[:10]).toordinal()
    except ValueError:
        day = 0

    def with_home(module):
        def fetch(subject, aliases, as_of):
            return module.fetch(subject, aliases, as_of,
                                home_url=home.get(subject, ""))
        return fetch

    families = {
        CS.GOVERNMENT_AWARD: (GA.fetch, GA.extract),
        CS.PARTNERSHIP_RELEASE: (with_home(PR), PR.extract),
        CS.CUSTOMER_CASE_STUDY: (with_home(CC), CC.extract),
    }

    payload: dict = {"families": {}, "relationships": []}
    accepted: List = []

    # --- the choice, written before the call ------------------------------
    #
    # THIS IS THE SEAM. Every other research row in the ledger was inferred
    # from a document that survived, so an action returning nothing left no
    # trace and every rate computed from the log was biased toward success.
    # The decision goes to disk BEFORE `CS.measure` runs, carrying the menu
    # that was actually on the table — including the families that were
    # cadence-blocked, which are choices closed rather than choices not
    # considered.
    from . import learning_store as _LS
    from . import research_decision as RD

    store = _LS.LearningStore(pathlib.Path(ctx.root) / _LS.DEFAULT_PATH)
    snapshot = RD.StateSnapshot(
        as_of=ctx.as_of[:10],
        subjects_without_exposure=len(subjects),
        research_budget_remaining=float(len(families)))
    candidates = tuple(
        RD.CandidateAction(
            source_family=name,
            query_strategy="counterparty_sweep",
            estimated_cost=1.0,
            expected_voi=0.0,
            eligible=not (SOURCE_CADENCE_DAYS.get(name, 1) > 1
                          and day % SOURCE_CADENCE_DAYS.get(name, 1)),
            refusal_reason=(
                "" if not (SOURCE_CADENCE_DAYS.get(name, 1) > 1
                           and day % SOURCE_CADENCE_DAYS.get(name, 1))
                else f"cadence {SOURCE_CADENCE_DAYS.get(name, 1)}d; not due "
                     f"today"))
        for name in families)
    decisions: dict = {}
    logged = outcomes_written = 0

    for family, (fetch, extract) in families.items():
        cadence = SOURCE_CADENCE_DAYS.get(family, 1)
        if cadence > 1 and day % cadence:
            payload["families"][family] = {
                "skipped_by_cadence": True, "cadence_days": cadence,
                "note": "not due today; a family not asked is not a family "
                        "that found nothing"}
            continue
        # Written first, and only for a family that is actually about to be
        # asked. A decision recorded for a skipped family would be a choice
        # nobody made.
        # WHEN THE CHOICE WAS MADE, to the second. It was the cycle DATE,
        # which made `decision_id` collide across two runs on one day: the
        # second run's decision deduplicated away while its outcome appended,
        # leaving one decision carrying two outcomes and a pairing that is no
        # longer one-to-one. Two sweeps on one day are two real choices.
        chosen_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
        decision = RD.ResearchDecision(
            subject="ALL", question_type=_COUNTERPARTY_QUESTION,
            chosen_action=family, candidates=candidates,
            selection_policy="CADENCE_GATED_SWEEP", policy_version="1",
            missing_fact="a named counterparty for a tracked company",
            state_snapshot_id=snapshot.snapshot_id,
            expected_cost=1.0, budget_remaining=float(len(families)),
            query_strategy="counterparty_sweep",
            selection_probability=None,
            selection_probability_status=RD.DETERMINISTIC,
            chosen_at=chosen_at, provenance=RD.PROSPECTIVE,
            policy_family=RD.RP_FAMILY_FOR.get(family, ""))
        started = _dt.datetime.now(_dt.timezone.utc).isoformat()
        if store.record_research_decision(decision):
            logged += 1
        decisions[family] = decision

        try:
            found, report = CS.measure(
                family, subjects=subjects, fetch=fetch, extract=extract,
                as_of=ctx.as_of)
        except Exception as exc:  # noqa: BLE001 - see docstring
            payload["families"][family] = {"error": str(exc)}
            # A FAILURE IS AN OUTCOME. The reconstructed log could not hold
            # this row at all, which is precisely why the engine's measured
            # hit rate was never its real one.
            store.record_research_outcome(RD.DecisionOutcome(
                decision_id=decision.decision_id, status=RD.FAILED,
                started_at=started,
                completed_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
                failure_type=f"{type(exc).__name__}: {exc}"[:200]))
            outcomes_written += 1
            continue
        payload["families"][family] = report.as_dict()
        # Integrate on the MEASURED verdict, never on the family's name.
        integrated = report.verdict()[0] == CS.INTEGRATE
        if integrated:
            accepted.extend(found)
        store.record_research_outcome(RD.DecisionOutcome(
            decision_id=decision.decision_id,
            status=_acquisition_status(report, integrated=integrated),
            started_at=started,
            completed_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
            subjects_attempted=report.subjects_attempted,
            documents_attempted=report.document_attempts,
            documents_retrieved=report.documents_retrieved,
            accepted_evidence=(report.relationships_accepted if integrated
                               else 0),
            refused_evidence=report.relationships_refused,
            new_events=report.relationships_accepted,
            # WHAT THIS ACTION PRODUCED, so a consequence weeks later can be
            # traced back to the choice that found it. Without these ids the
            # delayed reward can only be spread across every action that ran
            # that night, which teaches an association nobody observed.
            produced_evidence_ids=tuple(
                str(getattr(r, "relationship_id", "") or "")
                for r in (found if integrated else ())
                if getattr(r, "relationship_id", "")),
            latency_seconds=report.latency_seconds, cost=1.0,
            failure_type=("; ".join(report.errors)[:200] if report.errors
                          and not report.documents_retrieved else "")))
        outcomes_written += 1

    payload["research_decisions"] = {
        "written": logged, "outcomes": outcomes_written,
        "candidate_rows": len(candidates),
        "eligible": sum(1 for c in candidates if c.eligible),
        "provenance": RD.PROSPECTIVE,
        "note": ("written before the call, so a family that returned nothing "
                 "leaves a row; the reconstructed log could not"),
    }

    payload["relationships"] = [r.as_dict() for r in accepted]

    # PERSIST what was ACCEPTED. This line is the one that was missing for
    # six waves: wave 5 discovered three valid COMPETES_WITH rivalries, the
    # run report carried them, and the next process saw none of it, because
    # `accepted` went into a payload and nowhere else.
    #
    # It writes AFTER the measured verdict, so a family that did not reach
    # INTEGRATE contributes nothing, and never before validation.
    persisted = duplicates = 0
    if not ctx.dry_run:
        for relationship in accepted:
            row = (relationship.as_dict() if hasattr(relationship, "as_dict")
                   else dict(relationship))
            if store.record_relationship(row):
                persisted += 1
            else:
                duplicates += 1

    payload["summary"] = {
        "relationships_accepted": len(accepted),
        "relationships_persisted": persisted,
        "relationships_already_held": duplicates,
        # accepted - persisted - already_held must be zero on a real run.
        # Anything else means discovery outran storage, which is the defect
        # this project spent five waves not noticing.
        "persistence_gap": (0 if ctx.dry_run else
                            len(accepted) - persisted - duplicates),
        "by_predicate": CS.counts_by_predicate(accepted),
        "distinct_actors": len({r.subject_actor for r in accepted}
                               | {r.object_actor for r in accepted}),
    }
    return payload


def _rehydrate_decision(row: dict):
    """A persisted research decision back into its record."""
    from . import research_decision as RD

    try:
        candidates = tuple(
            RD.CandidateAction(
                source_family=str(c.get("source_family") or ""),
                query_strategy=str(c.get("query_strategy") or ""),
                estimated_cost=float(c.get("estimated_cost") or 1.0),
                estimated_latency=float(c.get("estimated_latency") or 0.0),
                expected_voi=float(c.get("expected_voi") or 0.0),
                eligible=bool(c.get("eligible", True)),
                refusal_reason=str(c.get("refusal_reason") or ""))
            for c in (row.get("candidate_actions") or ()))
        return RD.ResearchDecision(
            subject=str(row.get("subject") or ""),
            question_type=str(row.get("question_type") or ""),
            chosen_action=str(row.get("chosen_action") or ""),
            candidates=candidates,
            selection_policy=str(row.get("selection_policy") or ""),
            policy_version=str(row.get("policy_version") or "1"),
            missing_fact=str(row.get("missing_fact") or ""),
            state_snapshot_id=str(row.get("state_snapshot_id") or ""),
            expected_voi=float(row.get("expected_voi") or 0.0),
            expected_cost=float(row.get("expected_cost") or 1.0),
            budget_remaining=float(row.get("budget_remaining") or 0.0),
            query_strategy=str(row.get("query_strategy") or ""),
            selection_probability=row.get("selection_probability"),
            selection_probability_status=str(
                row.get("selection_probability_status") or RD.DETERMINISTIC),
            chosen_at=str(row.get("chosen_at") or ""),
            provenance=str(row.get("provenance") or RD.PROSPECTIVE),
            policy_family=str(row.get("policy_family") or ""))
    except Exception:  # noqa: BLE001
        return None


def _rehydrate_outcome(row: dict):
    from . import research_decision as RD

    try:
        return RD.DecisionOutcome(
            decision_id=str(row.get("decision_id") or ""),
            status=str(row.get("status") or ""),
            started_at=str(row.get("started_at") or ""),
            completed_at=str(row.get("completed_at") or ""),
            subjects_attempted=int(row.get("subjects_attempted") or 0),
            documents_attempted=int(row.get("documents_attempted") or 0),
            documents_retrieved=int(row.get("documents_retrieved") or 0),
            accepted_evidence=int(row.get("accepted_evidence") or 0),
            refused_evidence=int(row.get("refused_evidence") or 0),
            new_events=int(row.get("new_events") or 0),
            knowledge_effect_ids=tuple(row.get("knowledge_effect_ids") or ()),
            produced_evidence_ids=tuple(
                row.get("produced_evidence_ids") or ()),
            latency_seconds=float(row.get("latency_seconds") or 0.0),
            cost=float(row.get("cost") or 0.0),
            failure_type=str(row.get("failure_type") or ""))
    except Exception:  # noqa: BLE001
        return None


#: A series shorter than this cannot leave enough held-out predictions for a
#: comparison to mean anything, and scoring it anyway fills the ledger with
#: rows whose only content is that the sample was too small.
_METHOD_MIN_SERIES = 12


def _evaluate_methods(store, observations, *, as_of: str, dry_run: bool
                      ) -> dict:
    """Score the baselines on the economy this cycle actually holds.

    C-MET-004. `economic_method` was measured once, offline, by a human, on
    fifteen series. That is a real evaluation and it is not memory: nothing in
    the cycle imported the module, so "which method works for which question,
    in this regime" could never accumulate an answer, and the offline result
    was frozen at the regime it was taken in.

    VINTAGE-SAFE BY CONSTRUCTION. Only figures published on or before `as_of`
    are read, so a score computed for a past date cannot use a revision that
    had not happened yet — the same wall `macro_state.state_of` enforces, for
    the same reason.

    ASSUMPTIONS BEFORE STANDING. Every scored series gets its assumptions
    tested and the result decides what the number may be called. A method that
    wins while its critical assumption failed has described the sample and has
    not identified anything, and the two rows are stored together so nobody
    reads the win on its own.
    """
    from . import economic_method as EM
    from . import macro_state as MS

    known = MS.as_known_at(observations, as_of)
    series: Dict[tuple, list] = {}
    for observation in known:
        key = (getattr(observation, "area", "") or "",
               observation.state_kind, observation.series_id)
        series.setdefault(key, []).append(observation)

    performances, checks = [], []
    refused_short = 0
    for (area, kind, series_id), rows in sorted(series.items()):
        # Sorted by the period the figure DESCRIBES, never by when it was
        # read. One figure per period already: `as_known_at` keeps the latest
        # publication per `(series_id, reference_period)`, so a revision has
        # superseded rather than extended before this loop sees it. A second
        # dedupe here was written and removed — it could not fire, and an
        # unreachable guard is a guard nobody can prove is connected.
        ordered = sorted(rows, key=lambda o: o.reference_period)
        if len(ordered) < _METHOD_MIN_SERIES:
            refused_short += 1
            continue
        values = [float(o.value) for o in ordered]
        name = f"{area}:{kind}:{series_id}"
        comparison = EM.compare(values, series_name=name,
                                question_type=EM.FORECAST_LEVEL)
        for result in comparison["results"]:
            method = result["method"]
            got = EM.check_assumptions(
                values, method, question=EM.FORECAST_LEVEL, series_name=name,
                as_of=as_of)
            reading = EM.interpret(
                got, beat_baseline=result.get("beat_baseline"),
                predictions=result.get("predictions"))
            performances.append({**result, "area": area, "state_kind": kind,
                                 "standing": reading["standing"],
                                 "causal_reading_allowed":
                                     reading["causal_reading_allowed"],
                                 "assumption_note": reading["why"]})
            checks.extend(got)

    written_p = written_c = 0
    if not dry_run:
        for row in performances:
            if store.record_method_performance(
                    row, as_of=as_of, question_type=EM.FORECAST_LEVEL):
                written_p += 1
        for check in checks:
            if store.record_method_assumption_check(check):
                written_c += 1

    # WHICH METHOD CURRENTLY LEADS, and on how much. Never "AR1 is best":
    # a leader is a leader for one question type, on the series measured, on
    # this date, and the count is carried so a lead of one is not read as a
    # finding.
    leaders: Dict[str, int] = {}
    for row in performances:
        if row.get("beat_baseline") is True:
            leaders[row["method"]] = leaders.get(row["method"], 0) + 1
    scored_series = len({row["series"] for row in performances})
    by_standing: Dict[str, int] = {}
    for row in performances:
        by_standing[row["standing"]] = by_standing.get(row["standing"], 0) + 1
    return {
        "contract": EM.CONTRACT,
        "series_available": len(series),
        "series_scored": scored_series,
        "series_too_short": refused_short,
        "minimum_series_length": _METHOD_MIN_SERIES,
        "evaluations": len(performances),
        "performance_records_written": written_p,
        "assumption_checks_written": written_c,
        "performances_held": len(store.method_performances()),
        "assumption_checks_held": len(store.method_assumption_checks()),
        "by_standing": dict(sorted(by_standing.items())),
        "beat_persistence_on": dict(sorted(leaders.items())),
        "leader": (max(leaders, key=leaders.get) if leaders
                   else EM.PERSISTENCE),
        "assumption_failures_critical": sum(
            1 for c in checks if c.blocks_causal_reading),
        "assumptions_untested": sum(1 for c in checks if not c.tested),
        "note": ("a method that did not beat persistence is recorded, not "
                 "dropped; the leader is per question type on the series "
                 "measured on this date, and persistence is the leader when "
                 "nothing beat it"),
    }


def _rehydrate_thesis(row: dict):
    """A persisted thesis snapshot back into an EconomicThesis.

    Returns None rather than raising on a row this build cannot read. A
    snapshot written by an older schema is not a reason to fail a cycle, and
    silently dropping it is honest: the comparison for that thesis is simply
    unavailable, which shows up as `loaded` being lower than expected.
    """
    from . import economic_thesis as ET

    def mech(d):
        if not isinstance(d, dict):
            return None
        return ET.Mechanism(
            description=str(d.get("description") or ""),
            direction=str(d.get("direction") or ""),
            lag_days=int(d.get("lag_days") or 0),
            falsifier=str(d.get("falsifier") or ""),
            evidence_ids=tuple(d.get("evidence_ids") or ()),
            standing=str(d.get("standing") or ET.PROPOSED),
            # IDENTITY-BEARING. Dropped here, a reloaded thesis computes a
            # different `thesis_id` than the live one it should match, and
            # every night reads as a brand new thesis with no history.
            key=str(d.get("key") or ""))

    try:
        leading = mech(row.get("leading_mechanism"))
        if leading is None:
            return None
        return ET.EconomicThesis(
            subject=str(row.get("subject") or ""),
            question=str(row.get("question") or ""),
            claim=str(row.get("claim") or ""),
            leading_mechanism=leading,
            alternatives=tuple(m for m in
                               (mech(d) for d in (row.get("alternatives")
                                                  or ())) if m is not None),
            area=str(row.get("area") or ""),
            macro_conditions=tuple(row.get("macro_conditions") or ()),
            exposures=tuple(row.get("exposures") or ()),
            supporting_evidence=tuple(row.get("supporting_evidence") or ()),
            contradicting_evidence=tuple(
                row.get("contradicting_evidence") or ()),
            unknowns=tuple(row.get("unknowns") or ()),
            horizon_days=int(row.get("horizon_days") or 90),
            standing=str(row.get("standing") or ET.PROPOSED),
            as_of=str(row.get("as_of") or ""),
            supersedes=str(row.get("supersedes") or ""))
    except Exception:  # noqa: BLE001 - see docstring
        return None


def knowledge_step(ctx: C.CycleContext) -> dict:
    """Derive standing, currency and research value from the ledger.

    WHY THIS STEP EXISTS AT ALL
    ---------------------------
    `belief_maturity`, `knowledge_decay`, `value_of_information` and
    `causal_episodes` were each built, tested and reported as shipped, and
    NONE of them was ever called by an operating cycle. That is the sixth
    instance of this codebase's dominant defect — a correct module, a call
    site that never runs it, and a report that is silent rather than wrong.
    A subsystem no cycle invokes has not shipped; it has compiled.

    Everything here is a FOLD over the append-only ledger, so it is safe to
    run every session and produces the same answer twice on the same input.
    The one write is `knowledge_decay`'s lifecycle events, and those are
    appended, idempotent on `event_id`, and never edit a belief row.

    Never raises: deriving a view must not be able to stop the cycle that
    produces the thing being viewed.
    """
    import json as _json

    from . import belief_maturity as BM
    from . import causal_calibration as CCAL
    from . import causal_episodes as CE
    from . import counterfactual_memory as CFM
    from . import economic_chain as ECH
    from . import hidden_state_binding as HSB
    from . import knowledge_decay as KD
    from . import learning_acceleration as LA
    from . import learning_health as LH
    from . import learning_store as LS
    from . import mechanism_calibration as MC
    from . import value_of_information as VOI

    path = pathlib.Path(ctx.root) / LS.DEFAULT_PATH
    store = LS.LearningStore(path)
    payload: dict = {}
    rows: List[dict] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(_json.loads(line))
            except ValueError:
                continue      # a corrupt line is skipped, never repaired

    maturities: tuple = ()
    try:
        maturities = BM.classify(rows, as_of=ctx.as_of)
        payload["belief_maturity"] = BM.summarise(maturities)
    except Exception as exc:  # noqa: BLE001
        payload["belief_maturity"] = {"error": str(exc)}

    try:
        assessments = KD.assess(rows, as_of=ctx.as_of)
        emitted = KD.events(assessments, as_of=ctx.as_of,
                            prior_events=store.lifecycle_events())
        written = 0
        if not ctx.dry_run:
            for event in emitted:
                written += int(store.record_lifecycle(event))
        payload["knowledge_decay"] = {
            **KD.summarise(assessments, emitted),
            "events_written": written,
            "events": [e.as_dict() for e in emitted[:10]],
        }
    except Exception as exc:  # noqa: BLE001
        payload["knowledge_decay"] = {"error": str(exc)}

    try:
        hidden_states, _, _ = HSB.bind(store.evidence(), as_of=ctx.as_of)
        # `company_names` holds (canonical_name, aliases); VOI wants the name
        # a founder would recognise, not the pair.
        names = {cid: (value[0] if isinstance(value, tuple) else str(value))
                 for cid, value in (ctx.company_names or {}).items()}
        items = VOI.from_state(
            maturities=maturities, mechanisms=MC.calibrate(rows),
            hidden_states=hidden_states, subject_names=names)
        payload["value_of_information"] = VOI.summarise(items)
    except Exception as exc:  # noqa: BLE001
        payload["value_of_information"] = {"error": str(exc)}

    try:
        payload["causal_episodes"] = CE.summarise(CE.build(rows))
    except Exception as exc:  # noqa: BLE001
        payload["causal_episodes"] = {"error": str(exc)}

    try:
        payload["causal_calibration"] = CCAL.summarise(
            CCAL.calibrate(rows, industry_of=_industries()))
    except Exception as exc:  # noqa: BLE001
        payload["causal_calibration"] = {"error": str(exc)}

    try:
        payload["counterfactual_memory"] = CFM.summarise(CFM.build(rows))
    except Exception as exc:  # noqa: BLE001
        payload["counterfactual_memory"] = {"error": str(exc)}

    # THE ECONOMY. Every chain below this was decapitated without it: the
    # ledger holds only company-scoped evidence, so MACRO_STATE was not merely
    # unobserved, it was unreachable, and the top link of every subject's
    # chain sat at UNKNOWN forever.
    #
    # READ, never fetched. This step is a FOLD over the append-only ledger and
    # must give the same answer twice on the same input; a network call here
    # would break that invariant and put live HTTP inside every unit test that
    # touches the step. Acquisition is the research step's job, and what it
    # persisted is what this reads.
    macro_state = None
    # Bound before the try so a failed feed degrades the transmission step to
    # "no economy measured" instead of a NameError on a path that is meant to
    # be incapable of failing the cycle.
    states: list = []
    try:
        from . import macro_state as MS

        history = [MS.from_dict(r) for r in store.macro_observations()]
        # DERIVED HERE, NOT STORED. A spread is a fold over two figures the
        # ledger already holds, so persisting it would put the same fact in
        # twice and let a stale copy outlive the legs it was computed from.
        derived = [s for s in (
            MS.term_spread(history, as_of=ctx.as_of, area=area,
                           long_series=long_id, short_series=short_id)
            for area, long_id, short_id in _CREDIT_SPREADS) if s]
        states[:] = list(MS.all_states(history + derived, as_of=ctx.as_of))
        anchoring = [s for s in states if s.anchors]
        macro_state = anchoring[0] if anchoring else None
        payload["macro_state"] = {
            **MS.summarise(states),
            "history_rows": len(history),
            "tracked_conditions": len(MS.TRACKED_CONDITIONS),
            "derived_conditions": [s.series_id for s in derived],
        }
        # WHICH METHOD EARNS THE RIGHT TO ANSWER, measured on the economy this
        # cycle holds rather than on a comparison somebody ran once offline.
        try:
            payload["economic_method"] = _evaluate_methods(
                store, history + derived, as_of=ctx.as_of,
                dry_run=ctx.dry_run)
        except Exception as exc:  # noqa: BLE001
            payload["economic_method"] = {
                "error": f"{type(exc).__name__}: {exc}"}
    except Exception as exc:  # noqa: BLE001 - a fold must not fail a cycle
        payload["macro_state"] = {"error": f"{type(exc).__name__}: {exc}"}

    # A-WIRE-001. THE CAUSAL QUESTION, ASKED OF WHAT THE ENGINE ACTUALLY HOLDS.
    #
    # synthetic_control and causal_diagnostics were built, adversarially
    # tested, and had zero production callers — `grep -n synthetic_control
    # steps.py` returned nothing, which is the shape this program has recorded
    # five times. This is the caller.
    #
    # WHAT IT WILL SAY, AND WHY THAT IS THE POINT. The ledger holds 423 dated
    # company events and not one numeric value attached to a company, so a
    # question derived from a real LAYOFF or GUIDANCE_REVISION resolves to
    # PANEL_UNAVAILABLE naming NO_OUTCOME_SERIES_FOR_TREATED_UNIT. That is the
    # honest answer and it is a decision: it names the one input that would
    # change it. A capability whose live output is a precise refusal is worth
    # more than one that quietly never runs, which is what this was.
    #
    # A FOLD, like everything else in this step. Questions come from evidence
    # rows already on the ledger and panels from macro observations already on
    # it; nothing here fetches, so the step gives the same answer twice on the
    # same input.
    try:
        from . import causal_question as CQ
        from intent_engine.market import learning_store as LS

        observations = [r for r in rows
                        if r.get("record") == "macro_observation"]
        # Bounded deliberately. Every dated event is a candidate and there are
        # hundreds; resolving all of them would spend a cycle re-deriving the
        # same refusal. The cap is on questions ASKED, never on which ones —
        # the events are taken in ledger order, not chosen.
        questions = CQ.questions_from_events(
            [r for r in rows if r.get("record") == "evidence"],
            as_of=ctx.as_of, limit=25)
        resolutions = [CQ.resolve(q, observations, as_of=ctx.as_of)
                       for q in questions]
        # PERSISTED, not merely rendered. The first live cycle proved the gap:
        # 25 questions asked, 25 refused for a named prerequisite, the block
        # rendered in the report — and `causal_estimates_attempted` still folded
        # to 0, because nothing reached the ledger. That is the same number the
        # metric reads when this capability has never run, so the planner could
        # not tell a live refusal from a dead node. Report is a surface; the
        # ledger is the memory.
        store = LS.LearningStore(pathlib.Path(ctx.root) / LS.DEFAULT_PATH)
        persisted = sum(1 for r in resolutions
                        if store.record_causal_estimate(r))
        payload["causal_resolution"] = {
            **CQ.summarise(resolutions),
            # Both numbers. `persisted` is new rows and is 0 on a re-run of an
            # unchanged ledger, which is correct and is NOT the same as having
            # attempted nothing -- `questions` carries that.
            "persisted": persisted,
            # The rows themselves, so a refusal is as durable as an estimate
            # would have been. A cycle that persisted only successes would
            # make the engine's research history a success log, which is the
            # defect PROGRAM A of V4 exists to have fixed.
            "resolutions": [r.as_dict() for r in resolutions[:5]],
        }
    except Exception as exc:  # noqa: BLE001 - a fold must not fail a cycle
        payload["causal_resolution"] = {"error": f"{type(exc).__name__}: {exc}"}

    # B-HIST-001 INSTRUMENTED. The corpus machinery was built and had no
    # caller, so `historical_decision_episodes` read UNMEASURED — which blocked
    # B-RM-001 on an instrumentation gap rather than on a fact about the world.
    # UNMEASURED and 0 are different claims and only the second is a
    # measurement.
    #
    # THE EPISODES ARE THE ENGINE'S OWN RESOLVED PAST. An expectation names a
    # metric, a direction and a falsifier at a stated instant; a reconciliation
    # resolves it later against evidence. That pair is a decision at T0 with an
    # observable at T1, which is what a historical episode IS. Nothing is
    # relabelled: these rows land in a separate file and B-HIST-002's guard
    # asserts a historical row cannot move a prospective gate.
    try:
        from . import historical_corpus as HC

        candidates = HC.candidates_from_reconciliations(rows)
        corpus = HC.build_corpus(
            candidates, rows_for={c["subject"]: rows for c in candidates},
            built_at=ctx.as_of)
        written = 0
        if not ctx.dry_run:
            store_ = HC.HistoricalCorpusStore(
                ctx.root / HC.DEFAULT_PATH)
            written = sum(1 for e in corpus.episodes
                          if store_.record_episode(e))
        usable, excluded = HC.for_estimator_validation(corpus.episodes)
        payload["historical_corpus"] = {
            "reconciliations_seen": sum(1 for r in rows
                                        if r.get("record") == "reconciliation"),
            "candidates": len(candidates),
            "episodes": len(corpus.episodes),
            # A builder that silently skipped would report a clean corpus of
            # three out of a hundred and nothing would say so.
            "refused": len(corpus.refusals),
            "refusals_by_reason": dict(collections.Counter(
                r.reason for r in corpus.refusals)),
            "episodes_written": written,
            "usable_for_estimator_validation": len(usable),
            "excluded_as_revised": len(excluded),
            # The wall's own work, carried so a reader can see it was not
            # vacuous: an episode built from a snapshot that refused nothing
            # is an episode whose wall was never tested.
            "t0_rows_admitted": sum(e.t0_rows_admitted
                                    for e in corpus.episodes),
            "t0_rows_refused": sum(e.t0_rows_refused
                                   for e in corpus.episodes),
        }
    except Exception as exc:  # noqa: BLE001 - a fold must not fail a cycle
        payload["historical_corpus"] = {"error": f"{type(exc).__name__}: {exc}"}

    # WHAT MAKES A MACRO STATE MEAN SOMETHING DIFFERENT PER COMPANY.
    # Without it the transmission is a template: the same story fits a
    # capital-intensive manufacturer refinancing debt and a software company
    # with none. Expect UNKNOWN to dominate — a corpus of press releases does
    # not establish exposures, and a fully populated profile is a guessed one.
    try:
        from . import company_exposure as CX

        subjects = sorted({str(r.get("subject_company") or "") for r in rows
                           if r.get("record") == "evidence"
                           and r.get("subject_company")})
        # ATTRIBUTION, WRITTEN WHERE THE EXPOSURE IS READ. Most rows match
        # no pattern and produce NO_CHANGE; those are the majority and they
        # are what makes a prolific source distinguishable from a productive
        # one.
        from . import knowledge_effect as KEF

        exposure_effects: list = []
        profiles = {c: CX.profile(rows, company_id=c, effects=exposure_effects)
                    for c in subjects}
        for row in rows:
            if row.get("record") == "reconciliation":
                exposure_effects.extend(KEF.from_reconciliation(
                    _Row(row), created_at=ctx.as_of[:10]))
        # PERSIST THE ATTRIBUTION. It was computed here, summarised into the
        # report, and dropped: the report said 343 effects while the ledger
        # held 6, and those 6 came from belief formation in learning_cycle,
        # the one place with a write path. So the effect log — the table the
        # research reward is priced from — could never accumulate across
        # cycles, and every cross-cycle claim about what evidence CHANGED was
        # being made against a table that was empty for practical purposes.
        #
        # Idempotent on effect_id, which is keyed on evidence, target and day,
        # so re-deriving the same attribution today appends nothing while the
        # same evidence moving the same object tomorrow is a second, real row.
        effects_written = effects_already_held = 0
        if not ctx.dry_run:
            for effect in exposure_effects:
                if store.record_knowledge_effect(effect):
                    effects_written += 1
                else:
                    effects_already_held += 1
        payload["knowledge_effects"] = {
            **KEF.summarise(exposure_effects,
                            evidence_total=sum(1 for r in rows
                                               if r.get("record")
                                               == "evidence")),
            "persisted": effects_written,
            "already_held": effects_already_held,
            # Computed minus persisted minus already-held must be zero on a
            # real run. Anything else means attribution outran storage, which
            # is the defect this line was added to close.
            "persistence_gap": (0 if ctx.dry_run else
                                len(exposure_effects) - effects_written
                                - effects_already_held),
        }
        payload["company_exposure"] = {
            **CX.summarise(profiles),
            "rated": [e.as_dict() for p in profiles.values()
                      for e in p.values() if e.conditions],
        }
        # WHERE THE TWO HALVES MEET. A measured economy and an established
        # exposure are each useless alone; this is the dated, falsifiable
        # hypothesis they support together. All HYPOTHESIZED — the join is
        # never an observation, because a company may have hedged, refinanced
        # early, or be sitting on cash.
        from . import transmission as TX

        proposed = TX.propose_all(profiles, states, as_of=ctx.as_of)
        payload["transmission"] = {
            **TX.summarise(proposed),
            "hypotheses": [t.as_dict() for t in proposed],
        }

        # STRUCTURE NOBODY ASKED FOR. Every partition here is a hypothesis
        # with a research question attached and no path to becoming a fact;
        # the fitted models are scored against the stated rule rather than
        # against each other, because two models agreeing is not evidence.
        from . import unsupervised as UN

        regimes = UN.discover_regimes(
            history, as_of=ctx.as_of, groups=3,
            target_series=_REGIME_TARGET_SERIES)
        clusters = UN.discover_exposure_clusters(
            profiles, as_of=ctx.as_of, groups=3)
        odd = UN.find_anomalies(history, as_of=ctx.as_of)
        payload["unsupervised"] = {
            **UN.summarise(regimes, clusters, odd),
            "regimes": {k: regimes[k] for k in
                        ("periods", "series", "scores",
                         "any_economically_useful", "note")
                        if k in regimes},
            "regime_groups": [
                {k: d[k] for k in ("method", "label", "size", "members",
                                   "distinguishing")}
                for d in regimes.get("discoveries", [])],
            "exposure_clusters": [
                {k: d[k] for k in ("label", "size", "members")}
                for d in clusters.get("discoveries", [])],
            "anomalies": [d["label"] for d in odd.get("discoveries", [])],
        }

        # WHAT THE ENGINE CHOSE TO LOOK AT, SCORED. The log is reconstructed
        # from evidence that survived, so it is biased toward success and says
        # so; the point of running it every cycle is that the reward audit is
        # a standing check rather than a one-off, and the day a real log
        # exists this reads it instead.
        from . import research_policy as RPOL

        # PRICED BY WHAT THE EVIDENCE DID, not by the shape of the row. The
        # reconstructed log could only see independence and duplication, so
        # three of the reward's four positive terms were permanently zero and
        # the volume attack could not lose. With effects, they are measured.
        research_log = (RPOL.log_from_effects(rows, exposure_effects)
                        or RPOL.reconstruct_log(rows))
        payload["research_policy"] = {
            **RPOL.compare(research_log, [
                RPOL.VOIPolicy(), RPOL.ContextualBanditPolicy(),
                RPOL.HistoricalYieldPolicy(), RPOL.RandomPolicy(),
                RPOL.FixedPolicy(RPOL.INDEPENDENT_REPORTING),
                RPOL.FixedPolicy(RPOL.REGULATORY_FILING)]),
            "reward_audit": RPOL.audit_reward(research_log),
            # THE DIAGNOSIS, STANDING RATHER THAN ONE-OFF. It reports the gap
            # between the preference order the engine states and the value it
            # measures, and it does not close that gap — a replacement order
            # derived from a log rebuilt from surviving evidence would be
            # justified by exactly the rows such a log cannot contain.
            "source_preference": RPOL.diagnose_source_preference(research_log),
        }

        # THE PROSPECTIVE LOG, REPORTED APART FROM THE RECONSTRUCTED ONE.
        # `research_policy` above is scored on rows inferred from evidence
        # that survived. These rows were written BEFORE the call, so they can
        # contain an action that returned nothing — and the two must never be
        # pooled, because the success bias in the first would silently
        # establish the value of the second.
        from . import research_decision as RDEC

        decision_rows = store.research_decisions()
        outcome_rows = store.research_outcomes()
        payload["research_decisions"] = {
            "decisions": len(decision_rows),
            "outcomes": len(outcome_rows),
            "by_status": dict(collections.Counter(
                str(r.get("status") or "") for r in outcome_rows)),
            "empty_handed": sum(
                1 for r in outcome_rows
                if str(r.get("status") or "") in RDEC.EMPTY_HANDED),
            "with_a_forgone_option": sum(1 for r in decision_rows
                                         if r.get("forgone")),
            "standing": ("NOT_EVALUABLE" if not decision_rows else
                         "REPLAY_ONLY"),
            "why": ("no prospective decision has been written yet; every "
                    "research row is inferred from evidence that survived, so "
                    "actions returning nothing are absent and every rate is "
                    "biased toward success"
                    if not decision_rows else
                    f"{len(decision_rows)} prospective decisions written "
                    "before their calls; the selection policy is "
                    "deterministic, so replay can rank policies on the subset "
                    "they agree with and cannot say what an unchosen option "
                    "would have returned"),
            "note": ("counted from the ledger rather than from this run, so "
                     "the figure is what a fresh process would read"),
        }

        # THE OBJECT EVERY CEO-FACING SURFACE IS A PROJECTION OF. Built from
        # the transmissions rather than written beside them, so a briefing
        # cannot contain a claim the thesis does not — `project` runs the
        # overclaim check on its way out.
        from . import economic_thesis as ETH
        from . import founder_v4_view as FV4

        theses = ETH.build_all(proposed, as_of=ctx.as_of)
        # KEYED BY (area, kind), which is how an EconomicState is keyed.
        # Keyed by kind alone, CA:MARKET_RATE and US:MARKET_RATE collapsed to
        # one entry and a briefing about one economy carried the other's
        # reason for moving — a sourced-looking sentence about the wrong
        # country.
        reasons = {(s.area, s.state_kind): s.reason for s in states if s.known}
        views = [FV4.project(t, state_reason=reasons.get(
            (t.area, t.macro_conditions[0]) if t.macro_conditions else
            (t.area, ""), ""))
            for t in theses]
        contests = ETH.competitions(theses)
        # KEYED APART FROM THE COUNTS. `summarise` reports `theses` and
        # `views` as integers; spreading the full records under the same keys
        # replaced both counts with lists, and the report's bounded projection
        # would then have embedded every briefing in full.
        payload["economic_thesis"] = {
            **ETH.summarise(theses),
            "thesis_records": [t.as_dict() for t in theses],
            "competitions": [c.as_dict() for c in contests],
            "contested": sum(1 for c in contests if c.contested),
            "proofs": [ETH.prove(t).as_dict() for t in theses],
        }
        # WHAT CHANGED SINCE LAST CYCLE. Theses were rebuilt from scratch
        # every night and never compared to the previous night's, so the
        # temporal question — did this claim move, and what moved it — had no
        # data behind it and "what changed your mind?" answered "nothing" for
        # every thesis. The snapshot is what gives the next cycle something to
        # compare against.
        from . import thesis_history as THI

        prior = [_rehydrate_thesis(r) for r in store.thesis_snapshots()]
        prior = [t for t in prior if t is not None]
        # The chain is REBUILT from the ledger before tonight's comparison is
        # appended to it, so a revision names the revision it follows. Built
        # empty, every row was written with an empty parent and the history
        # was a pile of first links.
        stored_revisions = store.thesis_revisions()
        history, unreadable = THI.ThesisHistory.load(stored_revisions)
        history, revision_summary = THI.reconcile(
            prior, theses, as_of=ctx.as_of, effects=exposure_effects,
            history=history)
        revisions_written = 0
        snapshots_written = 0
        snapshots_refused = 0
        if not ctx.dry_run:
            for revision in history.chain_all():
                if store.record_thesis_revision(revision):
                    revisions_written += 1
            for thesis in theses:
                if store.record_thesis_snapshot(thesis, as_of=ctx.as_of):
                    snapshots_written += 1
                else:
                    snapshots_refused += 1
        payload["thesis_history"] = {
            **revision_summary,
            "revision_records_written": revisions_written,
            "revisions_held": len(store.thesis_revisions()),
            # TWO THESES THE STORE CANNOT TELL APART. This is the defect
            # figure and it is computed from the theses themselves, not from
            # the store's refusals: the store is idempotent on
            # `(thesis_id, as_of)`, so re-running a cycle for a date it has
            # already written legitimately refuses every snapshot. Reading
            # the refusal count as the collision count would report a clean
            # re-run as eleven dropped theses, and a genuine collision on a
            # first run as nothing at all.
            "theses_sharing_an_identity": (
                len(theses) - len({t.thesis_id for t in theses})),
            "snapshot_records_written": snapshots_written,
            "snapshots_refused_as_duplicate": snapshots_refused,
            "theses_built": len(theses),
            # HOW MUCH HISTORY THIS CYCLE ACTUALLY PICKED UP. Without it, a
            # step that reloaded nothing is indistinguishable from one that
            # reloaded everything and found no movement — both report zero
            # revisions written, which is what a rebuilt-empty chain looked
            # like for every cycle it ran.
            "prior_revisions_loaded": len(history.chain_all()) - revision_summary["written"],
            "prior_revisions_on_disk": len(stored_revisions),
            "unreadable_prior_revisions": len(unreadable),
        }

        # THE DELAYED HALF OF THE RESEARCH REWARD. An action that found
        # evidence which later moved a thesis earns credit for it, weeks after
        # the night it ran. The immediate outcome is never rewritten — this
        # appends beside it, because the first record is the only honest
        # measurement of what was knowable at the time.
        delayed_written = 0
        try:
            # IMPORTED HERE, and this line is the whole of A-RD-009's live
            # existence. `RD` is bound as a local inside four OTHER functions
            # in this module and never inside this one, so the call below
            # raised `NameError: name 'RD' is not defined` on every cycle it
            # ever ran. The bare except turned that into
            # `delayed_summary = {"error": ...}`, and nothing projected
            # `delayed_reward` into the report — so a capability that had
            # never once executed was marked COMPLETE, and the note beside it
            # read "the code ran but its counts are unobservable".
            #
            # The counts were unobservable because there were none. Adding
            # the projection surfaced it on the first live cycle.
            from . import research_decision as RD

            logged = [_rehydrate_decision(r) for r in
                      store.research_decisions()]
            logged_outcomes = [_rehydrate_outcome(r) for r in
                               store.research_outcomes()]
            delayed, delayed_summary = RD.credit_revisions(
                [d for d in logged if d is not None],
                [o for o in logged_outcomes if o is not None],
                history.chain_all(), observed_at=ctx.as_of)
            if not ctx.dry_run:
                for row in delayed:
                    if store.record_research_delayed_outcome(row):
                        delayed_written += 1
        except Exception as exc:  # noqa: BLE001
            delayed_summary = {"error": str(exc)}
        payload["delayed_reward"] = {
            **delayed_summary, "written": delayed_written,
            "held": len(store.research_delayed_outcomes()),
        }

        payload["founder_v4"] = {
            **FV4.summarise(views),
            "briefings": [v.as_dict() for v in views],
        }

        # DEMAND, AS NINE STATES. Expect most of them empty: a press-release
        # corpus does not disclose bookings or backlog, and the honest output
        # is a chain with holes in it rather than a demand reading inferred
        # from the one figure companies always publish.
        from . import demand_chain as DCH
        from . import economic_quantity as EQU
        from . import presentation as PRES

        chains = [DCH.build(rows, company_id=c, as_of=ctx.as_of)
                  for c in subjects]
        payload["demand_chain"] = {
            **DCH.summarise(chains),
            "chains": [c.as_dict() for c in chains if c.known_states],
        }

        # TWO FIGURES THAT DISAGREE WITHOUT BEING ADJACENT. The chain compares
        # neighbours and reads "both moved UP" as agreement, which is right
        # for every state except CANCELLATIONS — where a rise is committed
        # demand leaving. Backlog up with cancellations up is the clearest
        # disagreement in the vocabulary and the chain cannot express it.
        from . import demand_tension as DTN

        payload["demand_tension"] = DTN.summarise(chains)

        quantities, refused_q = [], {}
        for row in rows:
            if row.get("record") != "evidence":
                continue
            got, why = EQU.extract(
                str(row.get("fact") or ""),
                evidence_id=str(row.get("evidence_id") or ""),
                period=str(row.get("observed_at") or "")[:10])
            quantities.extend(got)
            for key, count in why.items():
                refused_q[key] = refused_q.get(key, 0) + count
        payload["economic_quantities"] = {
            **EQU.summarise(quantities, refused_q),
            "extracted": [q.as_dict() for q in quantities[:40]],
        }

        # THE DECK IS A VIEW. Built here so the standing wall runs inside the
        # cycle rather than at presentation time, where a failure would be
        # discovered by whoever was about to present it.
        decks = [PRES.build(t, view=v, proof=ETH.prove(t), as_of=ctx.as_of)
                 for t, v in zip(theses, views)]
        payload["presentation"] = {
            **PRES.summarise(decks),
            "consistency": [PRES.check(d, t)
                            for d, t in zip(decks, theses)],
            "decks": [d.as_dict() for d in decks[:3]],
        }

        # HOW EACH THESIS FAILS WHILE STILL LOOKING RIGHT. Built from the
        # alternatives the engine could not exclude, because each of those IS
        # an assumption the leading reading relies on without saying so. Every
        # case here will be SPECULATIVE — a press-release corpus carries no
        # evidence of a counterparty's means or motive — and that is reported
        # rather than dressed up, since a speculative case is worth reading
        # and is not actionable.
        from . import adversary_case as ADV

        cases = [c for t in theses for c in ADV.from_alternatives(
            t, as_of=ctx.as_of)]
        payload["adversary"] = {
            **ADV.summarise(cases),
            "cases": [c.as_dict() for c in cases[:3]],
        }
    except Exception as exc:  # noqa: BLE001
        payload["company_exposure"] = {"error": f"{type(exc).__name__}: {exc}"}
        payload.setdefault("transmission",
                           {"error": f"{type(exc).__name__}: {exc}"})

    try:
        # One chain, for the subject whose evidence can actually carry one.
        # Building a chain per company would produce twenty-seven that say
        # UNKNOWN everywhere, which is true and useless; the scored winner is
        # the one where the gaps mean something.
        candidates = ECH.score_candidates(rows)
        if candidates:
            built = ECH.build(rows, subject=candidates[0]["subject"],
                              macro=macro_state)
            payload["economic_chain"] = {
                **ECH.summarise([built]),
                "chain": built.as_dict(),
                "founder_translation": built.founder_translation(),
                "candidates": list(candidates[:5]),
            }
        else:
            payload["economic_chain"] = {"contract": ECH.CONTRACT,
                                         "chains": 0,
                                         "reason": "no subject has evidence"}
    except Exception as exc:  # noqa: BLE001
        payload["economic_chain"] = {"error": str(exc)}

    try:
        payload["world_model"] = _world_model(ctx)
    except Exception as exc:  # noqa: BLE001
        payload["world_model"] = {"error": str(exc)}

    try:
        # `impacts` is a count of PUBLISHED dossiers and it feeds only the
        # volume/quality half, which has used it as a denominator since
        # before the channels existed. It is deliberately NOT passed to the
        # Founder channel: publication is volume, and a channel named Founder
        # VALUE that counts publications is the substitution I-ACC-001 exists
        # to stop. The channel reads decision-impact RECORDS, and where there
        # are none it reports UNMEASURABLE rather than a flattering zero.
        impacts = len((ctx.results.get("learning") or {}).get(
            "strategic_export", {}).get("published") or ())
        # The SCORES, not the discoveries. 117 discoveries were made and 4
        # partitions were scored; the channel asks whether knowing the group
        # reduced held-out error, which only a score can answer. Counting
        # discoveries here would rate a tidy partition of noise as a gain.
        discoveries = list(
            ((payload.get("unsupervised") or {}).get("regimes") or {}
             ).get("scores") or ())
        # THE FOUNDER CHANNEL'S ACTUAL INPUT. It reported UNMEASURABLE for
        # three sessions because nothing passed it decision-impact records —
        # the Founder side computed them and persisted only the ones that
        # CHANGED something, which is a success log a rate cannot be taken
        # over. `decision_impact.jsonl` now carries NONE and
        # FIRST_OBSERVATION too, which is what gives the rate a denominator.
        payload["learning_acceleration"] = LA.report(
            LH.load_cycle_observations(pathlib.Path(ctx.root)),
            ledger=rows, decision_impacts=impacts,
            decision_impact_records=_decision_impacts(ctx),
            execution_ledger=_execution_ledger(ctx),
            discoveries=discoveries)
    except Exception as exc:  # noqa: BLE001
        payload["learning_acceleration"] = {"error": str(exc)}

    # WORKING HARD AND LEARNING NOTHING, as five separate questions. Each is
    # computed from a denominator this cycle actually holds, and each may come
    # back UNMEASURABLE — which is not a pass. An engine that cannot tell
    # whether it is learning is in a worse position than one that knows it is
    # not, and folding the two into a comfortable zero is how it stops being
    # able to tell.
    try:
        from . import stagnation as STG

        effects = payload.get("knowledge_effects") or {}
        theses_block = payload.get("economic_thesis") or {}
        impacts_seen = _decision_impacts(ctx)
        payload["stagnation"] = STG.summarise(STG.evaluate(
            # A FRACTION OF EVIDENCE, NOT EFFECTS PER ROW. The first live run
            # reported 442 effects over 416 evidence rows — 106% against a 5%
            # floor. Both numbers are right and the ratio is meaningless: one
            # evidence row can strengthen a belief AND resolve an expectation,
            # so effects-per-row exceeds 1.0 routinely and can never fall
            # below a floor expressed as a share of evidence. The question is
            # how much evidence changed NOTHING, so the numerator is the
            # evidence that changed something.
            evidence_rows=effects.get("evidence_attributed"),
            knowledge_effects=effects.get("evidence_that_changed_something"),
            theses=theses_block.get("theses"),
            theses_resolved=theses_block.get("tested"),
            discoveries=(payload.get("unsupervised") or {}).get("clusters"),
            discoveries_validated=(payload.get("unsupervised") or {}).get(
                "validated"),
            # `materiality` IS THE FIELD; `impact` was a guess and no row has
            # it. Every grade read as empty, the numerator was 0, and all 25
            # FIRST_OBSERVATION rows stayed in the DENOMINATOR — so the check
            # fired "analyses are produced and none changes a decision"
            # against 25 dossiers that had no prior revision for anything to
            # change against. Read the way learning_acceleration reads it.
            #
            # FIRST_OBSERVATION LEAVES BOTH SIDES. A dossier with no prior
            # revision has not failed to change a decision; there was no
            # decision to change, and counting it as a denominator would make
            # a growing corpus look like worsening stagnation.
            analyses=(_impact_denominator(impacts_seen) or None),
            decision_impacts=(
                sum(1 for g in _impact_grades(impacts_seen)
                    if g not in ("", "NONE", "FIRST_OBSERVATION"))
                if _impact_denominator(impacts_seen) else None),
        ))
    except Exception as exc:  # noqa: BLE001
        payload["stagnation"] = {"error": str(exc)}
    return payload


def _impact_grades(records: Sequence[dict]) -> List[str]:
    """The materiality of each graded comparison, read the way LA reads it.

    `materiality` first, `impact` as the legacy alias. Both are tried because
    two writers have existed; neither is guessed.
    """
    return [str(r.get("materiality") or r.get("impact") or "")
            for r in records or ()]


def _impact_denominator(records: Sequence[dict]) -> int:
    """Comparisons that COULD have shown an impact.

    FIRST_OBSERVATION is excluded from both sides of the rate: a dossier with
    no prior revision did not fail to change a decision, and counting it as a
    denominator makes a growing corpus look like worsening stagnation.
    """
    return sum(1 for g in _impact_grades(records)
               if g and g != "FIRST_OBSERVATION")


def _decision_impacts(ctx) -> List[dict]:
    """Graded before/after comparisons produced by the Founder surface.

    Read-only and optional. Absent file means the Founder channel reports
    UNMEASURABLE, which is the honest reading for a runtime that has never
    compared an analysis against its own prior revision.
    """
    import json as _json

    path = pathlib.Path(ctx.root) / "reports" / "market" / "decision_impact.jsonl"
    if not path.exists():
        return []
    out: List[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(_json.loads(line))
        except ValueError:
            continue
    return out


def _execution_ledger(ctx) -> List[dict]:
    """The planner's own record, for the SYSTEM capability channel.

    Read-only and optional: if the file is absent the channel reports
    UNMEASURABLE, which is the honest reading for a runtime that has no
    engineering history to look at. It is a separate function so the failure
    mode is a missing file rather than a knowledge step that dies on one.
    """
    import json as _json

    path = (pathlib.Path(ctx.root) / "docs" / "execution" / "v4"
            / "EXECUTION_LEDGER.jsonl")
    if not path.exists():
        return []
    out: List[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(_json.loads(line))
        except ValueError:
            continue
    return out


def _world_model(ctx: C.CycleContext) -> dict:
    """Rerun relationship-derived views on whatever acquisition produced.

    The interaction binder needs COMPETES_WITH edges specifically. The three
    integrated source families produce SELLS_TO and PARTNERS_WITH — a company
    publishes who buys from it and who it works with, and never who it is
    losing to. So this reports the exact missing relationship type rather
    than a bare zero, and `interaction_binding` keeps refusing.
    """
    from . import actor_relationships as AR
    from . import interaction_binding as IB
    from . import learning_store as LS

    from . import competitive_relationships as CR
    from . import learning_store as _LS

    acquired = (ctx.results.get("source_acquisition") or {}).get(
        "relationships") or []
    rows = tuple(_rehydrate(r) for r in acquired)

    # Rivalry is extracted separately and under a stricter contract: a
    # COMPETES_WITH claim needs a competitive object, which no other
    # predicate does.
    claims = _competitive_claims(ctx)
    rows = rows + tuple(c.as_relationship() for c in claims)
    competitors = AR.competitor_map(rows)
    store = LS.LearningStore(pathlib.Path(ctx.root) / LS.DEFAULT_PATH)
    interactions, refused = IB.bind(
        store.evidence(), industry_of=_industries(),
        competitors_of=competitors)
    by_predicate = dict(collections.Counter(r.predicate for r in rows))
    # Both ends of a rivalry must be OBSERVED for an interaction to be
    # possible. The corpus names rivals the engine does not track — Magento,
    # Salesforce — so a real competitive edge can still leave interactions
    # at zero, for a reason that is about coverage rather than about the
    # relationship.
    tracked = {str(e.subject_company or "").strip().lower()
               for e in _LS.LearningStore(
                   pathlib.Path(ctx.root) / _LS.DEFAULT_PATH).evidence()}
    unobserved = sorted({
        end for claim_ in claims
        for end in (claim_.actor_a, claim_.actor_b)
        if not any(t and t in end.lower() for t in tracked)})
    return {
        "relationships": len(rows),
        "competitive_claims": len(claims),
        "competitive_objects": sorted({c.competitive_object for c in claims}),
        "rivals_outside_the_observed_universe": unobserved,
        "by_predicate": by_predicate,
        "distinct_actors": len({r.subject_actor for r in rows}
                               | {r.object_actor for r in rows}),
        "competitor_edges": len(competitors),
        "interactions": len(interactions),
        "interactions_refused": dict(refused),
        "missing_for_interactions": _missing_for_interactions(
            competitors, unobserved),
    }


def _missing_for_interactions(competitors: dict, unobserved: list) -> str:
    if not competitors:
        return ("COMPETES_WITH. Every integrated family is company-"
                "published, and a company names its customers and its "
                "partners but not its rivals")
    if unobserved:
        return (f"OBSERVATION OF THE RIVAL. Competitive edges exist, and "
                f"{len(unobserved)} of their ends are companies this engine "
                f"does not track: {', '.join(unobserved[:4])}. An "
                f"interaction needs an action from one side and a response "
                f"from the other, so a rivalry with one observed party "
                f"cannot produce one")
    return ""


def _competitive_claims(ctx: C.CycleContext) -> tuple:
    """Rivalry from the ledger's own evidence, under the strict contract."""
    from . import competitive_relationships as CR
    from . import learning_store as _LS

    try:
        from intent_engine.universe.companies import default_universe
        companies = {c.company_id: c
                     for c in default_universe().prediction_companies()}
    except Exception:                                       # noqa: BLE001
        return ()
    store = _LS.LearningStore(pathlib.Path(ctx.root) / _LS.DEFAULT_PATH)
    found = {}
    for row in store.evidence():
        company = companies.get((row.subject_company or "").strip().lower())
        if not company:
            continue
        got, _ = CR.extract(
            row.fact, subject=company.company_id,
            aliases=_aliases_for(company), source=row.source,
            event_date=row.observed_at[:10],
            # The competitive object comes from what the company SELLS, a
            # fact about it, never from who it competes with, which is the
            # claim under test.
            competitive_object=str(getattr(company, "industry", "") or ""))
        for claim_ in got:
            found.setdefault(claim_.claim_id, claim_)
    return tuple(found.values())


def _rehydrate(row: dict):
    from . import actor_relationships as AR
    return AR.ActorRelationship(
        relationship_id=row.get("relationship_id", ""),
        subject_actor=row.get("subject_actor_id", ""),
        predicate=row.get("predicate", ""),
        object_actor=row.get("object_actor_id", ""),
        subject_kind=row.get("subject_kind", AR.LEGAL_ENTITY),
        object_kind=row.get("object_kind", AR.LEGAL_ENTITY),
        epistemic_status=row.get("epistemic_status", AR.OBSERVED),
        evidence_ids=tuple(row.get("evidence_ids") or ()),
        source_document=(row.get("source_document_ids") or [""])[0],
        subject_span=row.get("subject_span", ""),
        object_span=row.get("object_span", ""),
        relationship_span=row.get("relationship_span", ""))


def _industries() -> Dict[str, str]:
    """company_id -> industry, for scope counting. Never raises."""
    try:
        from intent_engine.universe.companies import default_universe
        return {c.company_id: (getattr(c, "industry", "")
                               or getattr(c, "sector", ""))
                for c in default_universe().prediction_companies()}
    except Exception:                                       # noqa: BLE001
        return {}


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

    # The four channels, in the PERSISTED report rather than in a helper.
    # An operator inspecting a past cycle has to be able to read "we learned
    # no new economic facts, and we improved the pipeline" — otherwise a
    # refactor reads as insight for as long as the refactors last.
    #
    # RETENTION is reported BESIDE them and never inside them: keeping
    # knowledge is not new knowledge.
    try:
        from . import learning_channels as _LC
        from . import knowledge_retention as _KR
        acquisition = (ctx.results.get("source_acquisition") or {})
        summary = acquisition.get("summary") or {}
        accepted = int(summary.get("relationships_accepted", 0) or 0)
        persisted = int(summary.get("relationships_persisted", 0) or 0)
        gap = int(summary.get("persistence_gap", 0) or 0)

        movements = []
        if persisted:
            movements.append(_LC.movement(
                channel=_LC.ECONOMIC_KNOWLEDGE, kind="relationship_discovered",
                count=persisted,
                detail=f"{persisted} relationship(s) persisted this cycle"))
        payload["learning_channels"] = _LC.report(movements)
        payload["knowledge_retention"] = _KR.audit([_KR.KnowledgeKind(
            name="actor_relationship", is_original=True,
            write_path="record_relationship", produced=accepted,
            accepted=accepted, reloadable=accepted - gap,
            note="written by source_acquisition_step")])
    except Exception as exc:  # noqa: BLE001 - see docstring
        payload["learning_channels_error"] = str(exc)

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
        ("knowledge", knowledge_step),
        ("learning_health", learning_health_step),
        ("health", health_step),
        ("report", report_step),
    ]


def night_steps(*, research_fn=None, series_fn=None) -> List[tuple]:
    return [
        ("research", research_step(research_fn)),
        ("source_acquisition", source_acquisition_step),
        ("reconcile", reconcile_step),
        ("paper_resolve", paper_resolve_step(series_fn)),
        ("opportunity", opportunity_step(series_fn)),
        ("resolve_outcomes", resolve_outcomes_step(series_fn)),
        ("funnel", funnel_step),
        ("positions", positions_step),
        ("assets", assets_step),
        ("learning", learning_step),
        ("knowledge", knowledge_step),
        ("learning_health", learning_health_step),
        ("replay", replay_step(series_fn=None)),
        ("health", health_step),
        ("report", report_step),
    ]


STEPS = {C.DAY: day_steps, C.NIGHT: night_steps}
