"""Marketing CLI (T017) — read and operator commands.

    PYTHONPATH=src python -m intent_engine.marketing campaign-show <id>
    PYTHONPATH=src python -m intent_engine.marketing review-pending
    PYTHONPATH=src python -m intent_engine.marketing handoff-show <id>
    PYTHONPATH=src python -m intent_engine.marketing pages --ledger ... --out ...
    PYTHONPATH=src python -m intent_engine.marketing roadmap-page --out ...
    PYTHONPATH=src python -m intent_engine.marketing consume --events-dir events

There is deliberately NO publish command and NO approve command: human
approvals go through MarketingService with an explicit human actor, and
publication is always performed outside this repository.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from intent_engine.marketing.service import DEFAULT_MARKETING_PATH, MarketingService


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="intent_engine.marketing")
    ap.add_argument("--path", default=str(DEFAULT_MARKETING_PATH))
    sub = ap.add_subparsers(dest="cmd", required=True)
    cs = sub.add_parser("campaign-show")
    cs.add_argument("campaign_id")
    sub.add_parser("review-pending")
    hs = sub.add_parser("handoff-show")
    hs.add_argument("handoff_id")
    pg = sub.add_parser("pages")
    pg.add_argument("--ledger", default="data/prediction_ledger.db")
    pg.add_argument("--out", required=True)
    rp = sub.add_parser("roadmap-page")
    rp.add_argument("--out", required=True)
    cm = sub.add_parser("consume")
    cm.add_argument("--events-dir", default="events")
    cm.add_argument("--ledger", default="data/prediction_ledger.db")
    cm.add_argument("--drafts-root", default="marketing/content_engine/drafts")

    args = ap.parse_args(argv)
    svc = MarketingService(args.path)

    if args.cmd == "campaign-show":
        print(json.dumps(dataclasses.asdict(svc.get_state(args.campaign_id)),
                         sort_keys=True, default=str))
    elif args.cmd == "review-pending":
        print(json.dumps(svc.list_pending_reviews(), sort_keys=True))
    elif args.cmd == "handoff-show":
        print(json.dumps(svc.get_handoff(args.handoff_id), sort_keys=True,
                         default=str))
    elif args.cmd == "pages":
        from intent_engine.marketing.generators import render_public_pages
        pages = render_public_pages(args.ledger, drafts_root=args.out)
        print(json.dumps(sorted(pages), sort_keys=True))
    elif args.cmd == "roadmap-page":
        from intent_engine.marketing.generators import render_roadmap_page
        render_roadmap_page(drafts_root=args.out)
        print(f"roadmap page drafted (NOT published): {args.out}")
    else:
        from intent_engine.events import CompanyEventBus, drain
        from intent_engine.marketing.consumer import MarketingCompanyEventConsumer
        bus = CompanyEventBus(args.events_dir)
        consumer = MarketingCompanyEventConsumer(
            drafts_root=args.drafts_root, ledger_path=args.ledger)
        rep = drain(bus, consumer)
        out = dict(rep.__dict__)
        out.update(drafted=consumer.drafted, skipped=consumer.skipped)
        print(json.dumps(out, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
