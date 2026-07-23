"""Founder Intelligence CLI (T023.5) — reads/demo only, no action surface.

    PYTHONPATH=src python -m intent_engine.founder_intelligence demo [--html OUT]
    PYTHONPATH=src python -m intent_engine.founder_intelligence landing [--html OUT]
    PYTHONPATH=src python -m intent_engine.founder_intelligence status <run_id>

There is no publish/send/deploy command. `demo` runs the deterministic
synthetic company and can write an openable HTML result page.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from intent_engine.founder_intelligence.fixtures import (
    DEMO_AS_OF, DEMO_COMPANY_NAME, DEMO_DOMAIN, demo_claims,
)
from intent_engine.founder_intelligence.presentation import (
    render_landing_html, render_result_html,
)
from intent_engine.founder_intelligence.service import (
    FounderIntelligenceService,
)
from intent_engine.founder_intelligence.store import DEFAULT_FI_PATH


def _run_demo(path):
    svc = FounderIntelligenceService(path)
    return svc, svc.run(company_name=DEMO_COMPANY_NAME,
                        website=f"https://{DEMO_DOMAIN}",
                        claims_by_section=demo_claims(), as_of=DEMO_AS_OF)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="intent_engine.founder_intelligence")
    ap.add_argument("--path", default=str(DEFAULT_FI_PATH))
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo")
    d.add_argument("--html", default=None)
    lp = sub.add_parser("landing")
    lp.add_argument("--html", default=None)
    st = sub.add_parser("status")
    st.add_argument("run_id")

    args = ap.parse_args(argv)

    if args.cmd == "demo":
        _, result = _run_demo(args.path)
        if args.html:
            Path(args.html).write_text(render_result_html(result),
                                       encoding="utf-8")
            print(f"wrote {args.html}")
        else:
            print(json.dumps({"run_id": result["run_id"],
                              "status": result["status"],
                              "sections": [s["kind"] for s in result["sections"]],
                              "limitations": result["limitations"][:5]},
                             sort_keys=True, default=str))
    elif args.cmd == "landing":
        if args.html:
            Path(args.html).write_text(render_landing_html(), encoding="utf-8")
            print(f"wrote {args.html}")
        else:
            print(render_landing_html()[:200] + "...")
    elif args.cmd == "status":
        svc = FounderIntelligenceService(args.path)
        print(json.dumps({"run_id": args.run_id,
                          "status": svc.run_status(args.run_id)}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
