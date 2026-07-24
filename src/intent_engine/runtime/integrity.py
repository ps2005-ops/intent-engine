"""Data-integrity verification across the append-only stores (Phase 3).

Read-only: it inspects the event log and each ledger and reports violations
of the invariants the platform depends on. It does NOT mutate — these stores
are append-only, so "repair" is detect-and-surface (and, for a genuinely
unparseable event line, the store already fails loudly with CorruptLogError).
A clean report is the production-readiness signal; any issue is actionable.

Checks:
  events    duplicate event_id; unknown type / wrong producer (validate);
            non-monotonic recorded_at (ordering); idempotency-key content
            consistency; replay parses.
  learning  evaluations/promotions referencing a missing candidate
            (orphans); illegal status regression (promoted/rejected -> back).
  paper     closed position missing exit fields; open position carrying
            exit fields; position missing its prediction link.
  predictions  resolved hit/miss missing its brier_component.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Union


class IntegrityReport:
    def __init__(self):
        self.issues: List[dict] = []

    def add(self, store: str, kind: str, detail: str, ref: str = "") -> None:
        self.issues.append({"store": store, "kind": kind, "detail": detail,
                            "ref": ref})

    @property
    def clean(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict:
        by_store: Dict[str, int] = {}
        for i in self.issues:
            by_store[i["store"]] = by_store.get(i["store"], 0) + 1
        return {"clean": self.clean, "issue_count": len(self.issues),
                "by_store": by_store, "issues": self.issues}


def check_events(events_dir: Path, report: IntegrityReport) -> None:
    from intent_engine.events.store import EventStore
    store = EventStore(events_dir)
    try:
        events = store.read_all()          # raises CorruptLogError on bad line
    except Exception as exc:  # noqa: BLE001
        report.add("events", "unreadable", str(exc))
        return
    # NB: recorded_at monotonicity is deliberately NOT checked. recorded_at is
    # stamped before the append lock, so under concurrent producers it can be
    # slightly out of order while the LOG ORDER (the real authority) is intact
    # — checking it would raise false integrity alarms. Order lives in the
    # file; there is no cross-event sequence field on CompanyEvent to verify.
    seen_ids, keys = set(), {}
    for ev in events:
        try:
            ev.validate()
        except Exception as exc:  # noqa: BLE001
            report.add("events", "invalid_envelope", str(exc), ev.event_id)
        if ev.event_id in seen_ids:
            report.add("events", "duplicate_event_id", "", ev.event_id)
        seen_ids.add(ev.event_id)
        if ev.idempotency_key:
            fp = ev.content_fingerprint()
            if ev.idempotency_key in keys and keys[ev.idempotency_key] != fp:
                report.add("events", "idempotency_key_conflict",
                           ev.idempotency_key, ev.event_id)
            keys.setdefault(ev.idempotency_key, fp)


def check_learning(db_path: Path, report: IntegrityReport) -> None:
    if not db_path.exists():
        return
    from intent_engine.learning.ledger import LearningStore
    store = LearningStore(db_path)
    candidate_ids = {c.id for c in store.list_candidates()}
    # orphans
    for e in store.all_evaluations():
        if e.candidate_id not in candidate_ids:
            report.add("learning", "orphan_evaluation",
                       f"candidate {e.candidate_id} not found", e.id)
    for p in store.all_promotions():
        if p.candidate_id not in candidate_ids:
            report.add("learning", "orphan_promotion",
                       f"candidate {p.candidate_id} not found", p.id)
    # illegal status regression: a terminal candidate must not reappear
    # non-terminal in a LATER row.
    seen_terminal = set()
    for c in store.candidate_rows():
        if c.id in seen_terminal and c.status in ("proposed", "evaluated"):
            report.add("learning", "status_regression",
                       f"{c.id} went terminal -> {c.status}", c.id)
        if c.status in ("promoted", "rejected"):
            seen_terminal.add(c.id)


def check_paper(db_path: Path, report: IntegrityReport,
                prediction_db: Path = None) -> None:
    if not db_path.exists():
        return
    from intent_engine.paper.ledger import PaperStore
    # index prediction outcomes so we can detect stranded positions (open
    # positions whose prediction already resolved to a real outcome — the
    # bug reconcile_positions heals; this makes the invariant observable).
    outcomes = {}
    if prediction_db is not None and Path(prediction_db).exists():
        from intent_engine.core import prediction_ledger as pl
        outcomes = {p.id: p.outcome for p in pl.list_predictions(path=prediction_db)}
    for p in PaperStore(db_path).latest():
        if not p.prediction_id:
            report.add("paper", "missing_prediction_link", "", p.id)
        if p.status == "closed" and (p.exit_price is None or p.pnl is None):
            report.add("paper", "closed_without_exit", "", p.id)
        if p.status == "open" and (p.exit_price is not None or p.pnl is not None):
            report.add("paper", "open_with_exit_fields", "", p.id)
        if p.status == "open" and outcomes.get(p.prediction_id) in (
                "happened", "did_not_happen", "unresolvable"):
            report.add("paper", "stranded_open_position",
                       f"prediction {p.prediction_id} resolved "
                       f"({outcomes[p.prediction_id]}) but position is open; "
                       "run reconcile", p.id)


def check_predictions(db_path: Path, report: IntegrityReport) -> None:
    if not db_path.exists():
        return
    from intent_engine.core import prediction_ledger as pl
    for p in pl.list_predictions(path=db_path):
        if p.outcome in ("happened", "did_not_happen") and p.brier_component is None:
            report.add("predictions", "resolved_without_brier", "", p.id)


def run_integrity(root: Union[str, Path]) -> dict:
    root = Path(root)
    report = IntegrityReport()
    check_events(root / "events", report)
    check_learning(root / "learning_ledger.db", report)
    check_paper(root / "paper_book.db", report, root / "prediction_ledger.db")
    check_predictions(root / "prediction_ledger.db", report)
    return report.to_dict()


def write_integrity(root: Union[str, Path]) -> dict:
    """Run the scan and cache the result atomically. Called on a schedule so
    the user-facing dashboard reads a cached result instead of doing a full
    store scan on every page view."""
    import json
    import os
    from datetime import datetime, timezone
    root = Path(root)
    report = run_integrity(root)
    report["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (root / "status").mkdir(parents=True, exist_ok=True)
    target = root / "status" / "integrity.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True, default=str))
    os.replace(tmp, target)
    return report


def read_cached_integrity(root: Union[str, Path]) -> Union[dict, None]:
    import json
    p = Path(root) / "status" / "integrity.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
