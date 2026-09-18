"""One command per verb. Large output goes to files; the terminal gets a
summary and a path, because pasting an artifact into a reader's context is
the most expensive way to convey a number."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

DEFAULT_ROOT = pathlib.Path("docs/execution/v5/pre100_60/live_captures")


def _already_captured(root, sha, name, rows) -> bool:
    """Was this company already captured READY on THIS sha?

    Never across shas: a capture from another build is not evidence about
    this one, and a resume that silently inherited one would produce a wave
    report spread over several builds -- which is how eight companies once
    came to be compared across five.
    """
    done = pathlib.Path(root) / sha / _slug(name) / "manifest.json"
    if not done.exists():
        return False
    try:
        prior = json.loads(done.read_text("utf-8"))
    except Exception:                                       # noqa: BLE001
        return False
    if prior.get("status") != "READY":
        return False
    rows.append({"company": name, "status": "READY", "resumed": True,
                 "run_id": prior.get("run_id", ""),
                 "capture_path": str(done.parent)})
    return True


def _slug(name: str) -> str:
    from intent_engine.pre100.capture import slug
    return slug(name)


class _nothing:
    """A context manager that does nothing, so the wave body has one shape."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _write(path: pathlib.Path, payload) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), "utf-8")
    return path


def cmd_batch(args) -> int:
    """One wave, paced, resumable, and written as it goes.

    THREE THINGS THIS MUST SURVIVE, all measured rather than anticipated:

    the demo quota      ten analyses per IP per rolling hour. `--gap` is not
                        a politeness setting; below 360s the wave spends its
                        own budget and the tail returns "limit reached".
    a lost session      the preview keeps runs on the instance that made
                        them. `capture` writes each route as it settles and
                        names a lost run rather than storing the error page.
    an interrupted run  `--resume` skips companies already captured on THIS
                        sha, so a wave that stops halfway costs nothing to
                        continue. It never skips across shas: a capture from
                        another build is not evidence about this one.
    """
    import time as _time
    from intent_engine.pre100 import capture as C
    companies = []
    for entry in args.companies:
        name, _, rest = entry.partition(":")
        cik, _, ticker = rest.partition(":")
        companies.append((name, cik, ticker))
    try:
        sha = C.require_deployed_sha(args.base)
    except C.UnknownDeployment as exc:
        print(f"REFUSED: {exc}")
        return 2
    root = pathlib.Path(args.capture_dir)
    print(f"sha={sha} companies={len(companies)} gap={args.gap}s")
    rows, started = [], None
    with (C.KeepWarm(args.base) if args.keep_warm else _nothing()):
        for name, cik, ticker in companies:
            if args.resume and _already_captured(root, sha, name, rows):
                print(f"{'SKIP':10s} {name[:28]:28s} already on {sha}")
                continue
            if started is not None and args.gap:
                # Quiet. A wave that narrates its own waiting spends model
                # turns on the least informative thing it does.
                _time.sleep(max(0.0, args.gap - (_time.time() - started)))
            started = _time.time()
            row = C.capture_company(name, cik, ticker, base=args.base,
                                    root=args.capture_dir, sha=sha)
            rows.append(row)
            note = ""
            if row["status"] == C.RUN_LOST:
                note = f" restart_observed={row.get('restart_observed')}"
            elif row["status"] == C.UNREADABLE:
                note = f" because={row.get('unreadable_because')}"
            print(f"{row['status']:10s} {name[:28]:28s} "
                  f"{row.get('seconds', '-')}s "
                  f"run={row.get('run_id', '-')[:12]}{note}")
            _write(root / sha / "batch.json", rows)     # after EVERY company
            if row["status"] == C.BLOCKED and not args.keep_going:
                print("BLOCKED — stopping so the rest of the quota is not "
                      "spent")
                break
    out = _write(root / sha / "batch.json", rows)
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
        within = company.get("qa_within_company") or {}
        line = f"  {company['company'][:26]:26s}"
        if within.get("answers"):
            line += (f" qa {within['distinct']}/{within['answers']} distinct")
        if company["flags"]:
            line += f"  {', '.join(company['flags'][:4])}"
        if company["flags"] or within.get("answers"):
            print(line)
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
    batch.add_argument("--gap", type=int, default=360,
                       help="seconds between analyses; the default IS the "
                            "demo quota (10 per IP per rolling hour)")
    batch.add_argument("--no-keep-warm", dest="keep_warm",
                       action="store_false", default=True,
                       help="do not hold the preview awake between "
                            "companies; leaves idle recycles in the data")
    batch.add_argument("--resume", action="store_true",
                       help="skip companies already captured READY on this "
                            "deployed sha")
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
