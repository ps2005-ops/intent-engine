"""Read-only analytics CLI (T015).

    PYTHONPATH=src python -m intent_engine.analytics summary [--window 30d]
    PYTHONPATH=src python -m intent_engine.analytics decisions --window 30d
    PYTHONPATH=src python -m intent_engine.analytics calibration
    PYTHONPATH=src python -m intent_engine.analytics crm-funnel
    PYTHONPATH=src python -m intent_engine.analytics consumers
    [--as-of ISO] [--json]

Nothing here writes anywhere. UNAVAILABLE sections stay UNAVAILABLE.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict


def _build_service(args):
    from intent_engine.analytics.service import AnalyticsService
    ds = crm = store = None
    ledger = None
    try:
        from intent_engine.core.decision_record import (
            DEFAULT_DECISIONS_DB, DecisionService,
        )
        if DEFAULT_DECISIONS_DB.exists():
            ds = DecisionService(str(DEFAULT_DECISIONS_DB))
    except Exception:  # noqa: BLE001 - absent store -> honest UNAVAILABLE
        pass
    try:
        from intent_engine.crm.service import DEFAULT_CRM_PATH, CRMService
        if DEFAULT_CRM_PATH.exists():
            crm = CRMService(DEFAULT_CRM_PATH)
    except Exception:  # noqa: BLE001
        pass
    try:
        from intent_engine.events.store import EventStore
        from pathlib import Path
        if Path(args.events_dir, "events.jsonl").exists():
            store = EventStore(args.events_dir)
    except Exception:  # noqa: BLE001
        pass
    from pathlib import Path
    if Path(args.ledger).exists():
        ledger = args.ledger
    return AnalyticsService(decision_service=ds, crm_service=crm,
                            event_store=store, ledger_path=ledger)


def _emit(data, as_json):
    if as_json:
        print(json.dumps(data, sort_keys=True, default=str))
        return
    for name, metric in sorted(data.items()):
        m = asdict(metric) if hasattr(metric, "metric_name") else metric
        line = f"{name}: {m.get('value')}"
        if m.get("status") not in ("OK", None):
            line += f"  [{m['status']}]"
        print(line)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="intent_engine.analytics")
    ap.add_argument("--window", default="all")
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--events-dir", default="events")
    ap.add_argument("--ledger", default="data/prediction_ledger.db")
    ap.add_argument("command", choices=["summary", "decisions", "calibration",
                                        "crm-funnel", "reports", "consumers"])
    args = ap.parse_args(argv)
    svc = _build_service(args)

    if args.command == "summary":
        print(json.dumps(svc.snapshot(args.window, args.as_of),
                         sort_keys=True, default=str))
        return 0
    section = {
        "decisions": svc.decision_metrics,
        "calibration": svc.calibration_metrics,
        "crm-funnel": svc.crm_funnel_metrics,
        "reports": svc.report_metrics,
        "consumers": svc.consumer_health,
    }[args.command]
    _emit(section(args.window, args.as_of), args.json)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
