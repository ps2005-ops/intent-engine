"""Market CLI — the entry point launchd calls and a human types.

    python -m intent_engine.market day     [--root DIR] [--as-of DATE] [--dry-run]
    python -m intent_engine.market night   [--root DIR] [--as-of DATE] [--dry-run]
    python -m intent_engine.market status  [--root DIR] [--json]
    python -m intent_engine.market runs    [--root DIR] [--limit N]

Follows the repository's established runtime-CLI convention
(`python -m intent_engine.runtime <job>`): a module `__main__` with subcommands,
`--root` for the runtime tree, and a nonzero exit status on failure so the
scheduler sees it.

EXIT STATUS IS THE ALERTING CHANNEL
-----------------------------------
launchd records the exit status of every run. A failed or partial cycle exits
nonzero, which is what makes `status` able to say "the night cycle has been
failing since Tuesday" without any external monitoring service. There is no
paid dependency here and none is needed.

--dry-run WRITES TO A SEPARATE ROOT
-----------------------------------
`<root>/dryrun`. A rehearsal must not append to the real funnel history or the
real asset ledger — fabricated observations are indistinguishable from data
after the fact, and this project's measurements are the only thing it has.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import sys

from intent_engine.market import cycle as C
from intent_engine.market import health as H
from intent_engine.market import learning_status as LS
from intent_engine.market import learning_report as LR
from intent_engine.market import learning_watchdog as LW
from intent_engine.market import session as S
from intent_engine.market import steps as STEPS


#: Env var naming the canonical runtime tree, for operators who are not
#: launchd. `--root` still wins; this only replaces the relative default.
ROOT_ENV = "MARKET_ROOT"

#: The old default. Relative, so it resolved against whatever directory the
#: operator happened to be standing in.
FALLBACK_ROOT = "data"


def resolve_root(value) -> pathlib.Path:
    """The tree an operator command is actually reading, absolute.

    THE DEFECT THIS CLOSES. `--root` defaulted to the relative string `data`,
    while launchd passes `/Users/.../intent-engine-market`. So
    `python -m intent_engine.market runs` typed from anywhere else resolved to
    an empty `./data` and printed "no cycle has run yet" -- which is the same
    sentence a genuinely idle engine prints, and there was no way to tell the
    two apart. An operator checking whether the night cycle ran got a confident
    "no" about a directory they never meant to ask about.

    Absolute now, and the reading commands PRINT the root they resolved, so the
    answer always names the tree it is about. That is the same discipline the
    rest of this program applies to every other empty result: an absence has to
    say what it is an absence of.
    """
    return pathlib.Path(
        value or os.environ.get(ROOT_ENV) or FALLBACK_ROOT).expanduser().resolve()


def _root(args) -> pathlib.Path:
    root = resolve_root(getattr(args, "root", None))
    return root / "dryrun" if getattr(args, "dry_run", False) else root


def _probe_latest_bar(symbol: str):
    """Ask the price source what the newest completed bar actually is.

    An unattended cycle cannot be handed `--latest-bar`, so it has to find out.
    A reference index is used rather than a company: the question is "has the
    market printed a session?", which is a property of the market, not of any
    one instrument that might be halted or delisted.

    A failure returns None, which the session classifies as BAR_UNAVAILABLE --
    reported honestly, never guessed from the calendar. Inferring a bar from
    "it was a weekday" is precisely the fabrication this refuses.
    """
    try:
        from intent_engine.market.prices import fetch_series
        return fetch_series(symbol, days=10).as_of
    except Exception as exc:  # noqa: BLE001 - unavailable is a real answer
        print(f"  (price probe failed: {type(exc).__name__}: {exc})")
        return None


def cmd_cycle(name: str, args) -> int:
    root = _root(args)
    root.mkdir(parents=True, exist_ok=True)
    latest_bar = args.latest_bar
    if latest_bar is None and not args.dry_run:
        latest_bar = _probe_latest_bar(args.reference_symbol)
    result = C.run_cycle(
        name, root=root, steps=STEPS.STEPS[name](),
        as_of=args.as_of, dry_run=args.dry_run,
        enforce_window=args.enforce_window,
        latest_bar=latest_bar)
    print(f"{result.run_id}  {result.status}")
    if result.reason:
        print(f"  {result.reason}")
    for step in result.steps:
        mark = "ok " if step.ok else "FAIL"
        extra = f"  [{step.code}] {step.error}" if step.error else ""
        print(f"  {mark} {step.name}{extra}")
    if result.report_paths.get("md"):
        print(f"  report: {result.report_paths['md']}")
    return result.exit_code


def cmd_status(args) -> int:
    root = resolve_root(args.root)
    health = H.check(root)
    if args.json:
        print(json.dumps(health.as_dict(), indent=1, sort_keys=True,
                         default=str))
    else:
        print(H.render(health))
    return 0 if health.overall in (H.OK, H.UNKNOWN) else 1


def cmd_runs(args) -> int:
    root = resolve_root(args.root)
    rows = C.RunStore(root).all()[-args.limit:]
    # Named on both branches. An empty answer that does not say which tree it
    # read is indistinguishable from a wrong-tree answer, which is exactly how
    # this command reported an idle engine that had run all week.
    print(f"root: {root}")
    if not rows:
        print("no cycle has run yet under this root")
        return 0
    print(f"{'run id':<44}{'status':<32}{'steps':>6}")
    for row in rows:
        steps = row.get("steps") or []
        ok = sum(1 for s in steps if s.get("status") == "ok")
        print(f"{row.get('run_id', ''):<44}{row.get('status', ''):<32}"
              f"{ok}/{len(steps):>4}")
    return 0


def cmd_learning_status(args) -> int:
    """What the SYSTEM OF RECORD has learned.

    Resolves every path through the declaration, so this command cannot read
    a legacy store even by accident — which is the whole reason it exists.
    """
    root = _root(args)
    status = LS.collect(root=root, window=args.window)
    if args.json:
        print(json.dumps(status, indent=2, sort_keys=False))
    else:
        print(LS.render(status))
    # Nonzero when the canonical ledger is absent: an operator asking what the
    # system learned and getting a clean empty screen would read it as "it
    # learned nothing", which is the exact failure this replaces.
    return 0 if status["system_of_record"]["ledger_exists"] else 1


def cmd_learning_report(args) -> int:
    """Generate and persist a canonical learning report.

    The JSON artifact is authoritative; the printed view is a projection of
    it, so an operator and a later weekly synthesis read the same numbers.
    """
    root = _root(args)
    report = LR.build(args.period, root=root)
    path = LR.persist(report, root=root)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=False))
    else:
        print(LR.render(report))
        print(f"\nwrote {path}")
    return 0


def cmd_watchdog(args) -> int:
    """Is the system still LEARNING — not merely still running.

    Exit status is the alerting channel, as everywhere else in this CLI: 2 on
    CRITICAL, 1 on WARNING, 0 on OK, so launchd records a watchdog finding
    without any external monitoring service.
    """
    root = _root(args)
    founder = root / "reports" / "market" / "dossier_revisions.jsonl"
    last_write = ""
    if founder.exists():
        last_write = _dt.datetime.fromtimestamp(
            founder.stat().st_mtime, _dt.timezone.utc).isoformat()
    report = LW.evaluate(root=root, window=args.window,
                         founder_last_write=last_write)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=False))
    else:
        print(LW.render(report))
    return {LW.CRITICAL: 2, LW.WARNING: 1}.get(report["status"], 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m intent_engine.market",
        description="Market learning engine — unattended operating cycles "
                    "(paper trading only; no broker, no orders, no capital).")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in C.CYCLES:
        hour, minute = C.SCHEDULE[name]
        p = sub.add_parser(name, help=f"run the {name} cycle "
                                      f"({hour:02d}:{minute:02d} "
                                      f"{S.TIMEZONE})")
        p.add_argument("--root", default=None,
                       help=f"runtime tree (default: ${ROOT_ENV}, else "
                            f"./{FALLBACK_ROOT})")
        p.add_argument("--as-of", default=None,
                       help="operating day (default: today in "
                            f"{S.TIMEZONE})")
        p.add_argument("--dry-run", action="store_true",
                       help="rehearse against <root>/dryrun; writes nothing "
                            "durable")
        p.add_argument("--latest-bar", default=None,
                       help="newest completed bar date; probed from the "
                            "reference symbol when omitted")
        p.add_argument("--reference-symbol", default="SPY",
                       help="instrument probed to find the newest completed "
                            "market bar (default: SPY)")
        p.add_argument("--enforce-window", action="store_true",
                       help="refuse to run outside the scheduled local-time "
                            "window (used by launchd; guards DST)")

    p = sub.add_parser("status", help="operational health, one screen")
    p.add_argument("--root", default=None,
                   help=f"runtime tree (default: ${ROOT_ENV}, else "
                        f"./{FALLBACK_ROOT})")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("runs", help="recent cycle records")
    p.add_argument("--root", default=None,
                   help=f"runtime tree (default: ${ROOT_ENV}, else "
                        f"./{FALLBACK_ROOT})")
    p.add_argument("--limit", type=int, default=20)

    # The answer to "what has this system learned?", so that question never
    # again has to be answered by whichever store an explorer finds first.
    p = sub.add_parser("learning-report",
                       help="daily/weekly/monthly canonical learning report")
    p.add_argument("--root", default=None)
    p.add_argument("--period", default="day", choices=list(LR.PERIODS))
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("watchdog",
                       help="is the system still learning (typed alerts)")
    p.add_argument("--root", default=None)
    p.add_argument("--window", default="7d", choices=sorted(LS.WINDOWS))
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("learning-status",
                       help="what the system of record has learned")
    p.add_argument("--root", default=None,
                   help=f"runtime tree (default: ${ROOT_ENV}, else "
                        f"./{FALLBACK_ROOT})")
    p.add_argument("--window", default="7d",
                   choices=sorted(LS.WINDOWS),
                   help="rolling window over the canonical ledger")
    p.add_argument("--json", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in C.CYCLES:
        return cmd_cycle(args.command, args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "runs":
        return cmd_runs(args)
    if args.command == "learning-status":
        return cmd_learning_status(args)
    if args.command == "watchdog":
        return cmd_watchdog(args)
    if args.command == "learning-report":
        return cmd_learning_report(args)
    return 2  # pragma: no cover - argparse rejects unknown commands


if __name__ == "__main__":
    sys.exit(main())
