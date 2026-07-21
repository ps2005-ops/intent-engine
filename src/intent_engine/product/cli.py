"""Product CLI (T020) — reads and idempotent consumption only.

    PYTHONPATH=src python -m intent_engine.product portfolio <id>
    PYTHONPATH=src python -m intent_engine.product opportunity-show <id>
    PYTHONPATH=src python -m intent_engine.product proposal-show <id> [--version N]
    PYTHONPATH=src python -m intent_engine.product spec-show <id>
    PYTHONPATH=src python -m intent_engine.product scores <proposal_id>
    PYTHONPATH=src python -m intent_engine.product lineage <proposal_id>
    PYTHONPATH=src python -m intent_engine.product pending-reviews
    PYTHONPATH=src python -m intent_engine.product roadmap-diff <proposal_id>
    PYTHONPATH=src python -m intent_engine.product snapshot <id> [--json]
    PYTHONPATH=src python -m intent_engine.product consume

There is no accept command, no apply command, and no schedule command:
acceptance is a founder act performed through ProductService, applying a
diff is a person's edit, and this subsystem schedules nothing.
`roadmap-diff` prints to stdout; it never writes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from intent_engine.product.service import ProductService
from intent_engine.product.store import DEFAULT_PRODUCT_PATH

_DEFAULT_AS_OF = "9999-12-31T00:00:00+00:00"


def _dump(value) -> None:
    print(json.dumps(value, sort_keys=True, default=str))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="intent_engine.product")
    ap.add_argument("--path", default=str(DEFAULT_PRODUCT_PATH))
    ap.add_argument("--as-of", default=_DEFAULT_AS_OF)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("portfolio")
    pf.add_argument("portfolio_id")
    for name in ("opportunity-show", "spec-show", "scores", "lineage"):
        p = sub.add_parser(name)
        p.add_argument("subject_id")
    pr = sub.add_parser("proposal-show")
    pr.add_argument("proposal_id")
    pr.add_argument("--version", type=int, default=None)
    rd = sub.add_parser("roadmap-diff")
    rd.add_argument("proposal_id")
    rd.add_argument("--roadmap", default="ROADMAP.md",
                    help="read-only: the current roadmap text is read and "
                         "diffed; it is never written")
    sn = sub.add_parser("snapshot")
    sn.add_argument("subject_id")
    sn.add_argument("--json", action="store_true")
    sub.add_parser("pending-reviews")
    cm = sub.add_parser("consume")
    cm.add_argument("--events-dir", default="events")

    args = ap.parse_args(argv)
    svc = ProductService(args.path)

    if args.cmd == "portfolio":
        _dump(svc.portfolio(args.portfolio_id, as_of=args.as_of))
    elif args.cmd == "opportunity-show":
        index = svc.get_index()
        opportunity = index.opportunities.get(args.subject_id)
        if opportunity is None:
            print(f"no such opportunity: {args.subject_id}", file=sys.stderr)
            return 1
        _dump({**opportunity,
               "proposals": [p["proposal_id"] for p in index.proposals.values()
                             if p["opportunity_id"] == args.subject_id],
               "problem": index.problem_index.lineage_of(
                   opportunity["problem_id"])})
    elif args.cmd == "proposal-show":
        _dump(svc.get_proposal(args.proposal_id, args.version))
    elif args.cmd == "spec-show":
        _dump({"spec": svc.get_spec(args.subject_id),
               "spec_debt": svc.get_spec_debt(args.subject_id)})
    elif args.cmd == "scores":
        _dump(svc.score_proposal(args.subject_id, as_of=args.as_of,
                                 record=False))
    elif args.cmd == "lineage":
        _dump(svc.lineage(args.subject_id))
    elif args.cmd == "pending-reviews":
        _dump(svc.list_pending_reviews())
    elif args.cmd == "roadmap-diff":
        # Read-only. The diff is printed for a person to apply.
        roadmap_text = Path(args.roadmap).read_text(encoding="utf-8")
        candidate = svc.get_roadmap_candidate(args.proposal_id)
        from intent_engine.product.roadmap_diff import render_roadmap_diff
        diff = render_roadmap_diff(candidate, roadmap_text)
        print(diff["diff"])
        print("# emitted, not applied — ROADMAP.md is unchanged by this "
              "command")
    elif args.cmd == "snapshot":
        from intent_engine.product.snapshots import (
            capture_portfolio_snapshot, capture_proposal_snapshot,
        )
        state = svc.get_state()
        if args.subject_id in state.proposals:
            snapshot = capture_proposal_snapshot(svc, args.subject_id,
                                                 as_of=args.as_of)
        else:
            snapshot = capture_portfolio_snapshot(svc, args.subject_id,
                                                  as_of=args.as_of)
        _dump(snapshot) if args.json else _dump(
            {k: v for k, v in snapshot.items()
             if k in ("snapshot_id", "as_of", "computed_at", "versions",
                      "source_high_watermarks")})
    else:
        from intent_engine.events import CompanyEventBus, drain
        from intent_engine.product.consumer import ProductCompanyEventConsumer
        bus = CompanyEventBus(args.events_dir)
        consumer = ProductCompanyEventConsumer(svc)
        report = drain(bus, consumer)
        out = dict(report.__dict__)
        out.update(candidates=consumer.candidates, skipped=consumer.skipped)
        _dump(out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
