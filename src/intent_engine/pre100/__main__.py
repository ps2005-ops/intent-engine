"""One command per verb. Large output goes to files; the terminal gets a
summary and a path, because pasting an artifact into a reader's context is
the most expensive way to convey a number."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

DEFAULT_ROOT = pathlib.Path("docs/execution/v5/pre100_60/live_captures")


def _write(path: pathlib.Path, payload) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), "utf-8")
    return path


def cmd_batch(args) -> int:
    from intent_engine.pre100 import capture as C
    companies = []
    for entry in args.companies:
        name, _, rest = entry.partition(":")
        cik, _, ticker = rest.partition(":")
        companies.append((name, cik, ticker))
    sha = C.deployed_sha(args.base)
    print(f"sha={sha} companies={len(companies)}")
    rows = []
    for name, cik, ticker in companies:
        row = C.capture_company(name, cik, ticker, base=args.base,
                                root=args.capture_dir, sha=sha)
        rows.append(row)
        print(f"{row['status']:8s} {name[:28]:28s} "
              f"{row.get('seconds', '-')}s run={row.get('run_id', '-')[:12]} "
              f"{row['capture_path']}")
        if row["status"] == C.BLOCKED and not args.keep_going:
            print("BLOCKED — stopping so the rest of the quota is not spent")
            break
    out = _write(pathlib.Path(args.capture_dir) / sha / "batch.json", rows)
    print(f"\nwrote {out}")
    return 0 if all(r["status"] == C.READY for r in rows) else 1


def cmd_audit(args) -> int:
    from intent_engine.pre100 import audit as A
    report = A.audit_batch(args.capture_root)
    out = _write(pathlib.Path(args.capture_root) / "audit.json", report)
    summary = report["summary"]
    print(f"captured={summary['captured']} "
          f"with_flags={summary['with_flags']}")
    for company in report["companies"]:
        if company["flags"]:
            print(f"  {company['company'][:26]:26s} "
                  f"{', '.join(company['flags'][:5])}")
    worst = (report.get("collapse") or {}).get("worst") or {}
    for surface, pair in worst.items():
        if surface == "qa":
            print(f"  worst qa   {pair['a'][:16]}/{pair['b'][:16]} "
                  f"{pair['identical_answers']}/{pair['of']} identical")
        else:
            print(f"  worst {surface:8s} {pair['a'][:16]}/{pair['b'][:16]} "
                  f"{pair['similarity']}")
    print(f"\nwrote {out}")
    return 0


def cmd_replay(args) -> int:
    from intent_engine.pre100 import replay as R
    result = R.find(args.capture, args.find, routes=args.routes)
    print(json.dumps({k: v for k, v in result.items() if k != "hits"},
                     indent=2))
    for hit in result.get("hits", [])[:5]:
        print(f"  {hit['route']}: ...{hit['context'][:150]}...")
    return 0 if result["status"] == R.REPRODUCED else 1


def cmd_delta(args) -> int:
    from intent_engine.pre100 import replay as R
    result = R.delta(args.before, args.after)
    print("changed:   " + ", ".join(result["routes_changed"]) or "changed: -")
    print("unchanged: " + ", ".join(
        result["routes_unchanged_may_inherit_pass"]))
    for row in result["answers_changed"][:5]:
        print(f"  Q {row['question'][:60]}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="intent_engine.pre100")
    sub = parser.add_subparsers(dest="cmd", required=True)

    batch = sub.add_parser("batch", help="capture companies through the "
                                         "real customer journey")
    batch.add_argument("companies", nargs="+",
                       help='"Name:CIK:TICKER", CIK and ticker optional')
    batch.add_argument("--base",
                       default="https://intent-engine-preview-bridge."
                               "onrender.com")
    batch.add_argument("--capture-dir", default=str(DEFAULT_ROOT))
    batch.add_argument("--keep-going", action="store_true")
    batch.set_defaults(func=cmd_batch)

    audit = sub.add_parser("audit", help="mechanical audit over a wave")
    audit.add_argument("capture_root")
    audit.set_defaults(func=cmd_audit)

    replay = sub.add_parser("replay", help="does a defect reproduce offline?")
    replay.add_argument("capture")
    replay.add_argument("--find", required=True)
    replay.add_argument("--routes", nargs="*")
    replay.set_defaults(func=cmd_replay)

    delta = sub.add_parser("delta", help="what changed between two captures")
    delta.add_argument("before")
    delta.add_argument("after")
    delta.set_defaults(func=cmd_delta)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
