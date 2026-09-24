#!/usr/bin/env python3
"""Point the forty's analysis scripts at the twenty-five's state (§40, §44).

WHY A SHIM AND NOT TEN FORKS
----------------------------
Ten analysis scripts hard-code `reports/next40_state.json` and
`reports/next40_ui`. Forking each to change two strings would fork every
instrument correction with it, and the whole reason the 25 reuse the 40's
harness is that those corrections were expensive and are invisible until they
are missing.

So each module is imported and its two path constants are rebound before its
`main()` is called. The measurement code is byte-identical, which is what
makes §40's comparison legitimate: a different instrument would make the two
cohorts incomparable and the comparison is the point.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent

STATE = ROOT / "reports/asi25_state.json"
UI = ROOT / "reports/asi25_ui"

#: module -> (output basename, extra argv)
STEPS = (
    ("next40_analysis", "asi25_analysis.json", ["--cohort", "ALL"]),
    ("next40_ten_dimensions", "asi25_ten_dimensions.json", ["--cohort", "ALL"]),
    ("next40_qa_audit", "asi25_qa_audit.json", ["--cohort", "ALL"]),
    ("next40_overlap", "asi25_overlap.json", ["--cohort", "ALL"]),
    ("next40_econ_chain", "asi25_econ_chain.json", ["--cohort", "ALL"]),
    ("next40_differentiation", "asi25_template.json", []),
    ("next40_convergence", "asi25_convergence.json", []),
)

#: REBINDING A MODULE CONSTANT IS NOT ENOUGH. Several of these scripts read
#: their paths from an argparse DEFAULT STRING or a literal inside main(),
#: so `mod.STATE = ...` changes nothing. Aliasing the files onto the names
#: they expect is the honest alternative: one file, two names, and no fork
#: of eight measurement scripts. This worktree carries no next40 run, so
#: there is nothing to collide with.
ALIASES = (
    ("reports/asi25_state.json", "reports/next40_state.json"),
    ("reports/asi25_ui", "reports/next40_ui"),
    ("reports/asi25_ui_widths.json", "reports/next40_ui_widths.json"),
)


def _alias():
    import shutil
    made = []
    for src, dst in ALIASES:
        s, d = ROOT / src, ROOT / dst
        if not s.exists():
            continue
        if d.exists() or d.is_symlink():
            continue
        d.symlink_to(s.resolve())
        made.append(dst)
    return made


#: `next40_ten_dimensions` reads the layout measurements from a HARDCODED
#: path (`reports/next40_ui_widths.json`, ~line 337) rather than from its UI
#: constant. Left alone it would score the twenty-five against the FORTY's
#: layout numbers -- a silent cross-cohort read, and the reader would have no
#: way to see it. The asi25 file is copied onto that name first, so the
#: hardcoded path resolves to this cohort's own measurements.
WIDTHS_SRC = ROOT / "reports/asi25_ui_widths.json"
WIDTHS_DST = ROOT / "reports/next40_ui_widths.json"


def _align_widths():
    if not WIDTHS_SRC.exists():
        return "no asi25 widths file yet; run the UI matrix first"
    import shutil
    if WIDTHS_DST.exists():
        shutil.copy2(WIDTHS_DST, WIDTHS_DST.with_suffix(".forty.json"))
    shutil.copy2(WIDTHS_SRC, WIDTHS_DST)
    return f"widths aligned: {WIDTHS_SRC.name} -> {WIDTHS_DST.name}"


def _rebind(mod):
    """Every next40 path constant, pointed at the twenty-five."""
    for attr, value in (("STATE", STATE), ("UI", UI),
                        ("CAPTURES", UI), ("STATE_PATH", STATE)):
        if hasattr(mod, attr):
            setattr(mod, attr, value)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", default=None)
    args = ap.parse_args()
    import importlib
    print("aliased:", _alias() or "(already present)", flush=True)
    failures = []
    for name, out, extra in STEPS:
        if args.only and name not in args.only:
            continue
        try:
            mod = _rebind(importlib.import_module(name))
        except Exception as exc:                             # noqa: BLE001
            failures.append((name, f"import: {type(exc).__name__}: {exc}"))
            continue
        argv = sys.argv[:1] + extra
        old = sys.argv
        # LET EACH SCRIPT WRITE ITS OWN DEFAULT NAME. Redirecting the first
        # one with --out meant the ones downstream of it looked for a file
        # that had been written somewhere else. They are collected to the
        # asi25 names afterwards instead.
        sys.argv = argv
        try:
            rc = mod.main()
            print(f"{name:28s} rc={rc}", flush=True)
            if rc not in (0, None):
                failures.append((name, f"rc={rc}"))
        except SystemExit as e:
            if e.code not in (0, None):
                failures.append((name, f"exit={e.code}"))
        except Exception as exc:                             # noqa: BLE001
            failures.append((name, f"{type(exc).__name__}: {exc}"))
        finally:
            sys.argv = old
    # Collect anything written under a next40 name back to its asi25 name,
    # so the artifacts a reader is given are named for the cohort they
    # describe rather than for the harness they borrowed.
    # ALWAYS OVERWRITE. `if not target.exists()` is how the central
    # measurement of this programme came to be wrong: a SEVENTEEN-company
    # `asi25_differentiation.json` written mid-run at 03:17 survived every
    # later pass, because the freshly computed 25-company result was only
    # copied when no file was in the way. Every differentiation headline in
    # the V2 close described 17 companies and was reported as 25. A
    # collector that declines to collect is worse than no collector: it
    # leaves something that LOOKS current.
    import shutil
    state_mtime = (ROOT / "reports/asi25_state.json").stat().st_mtime \
        if (ROOT / "reports/asi25_state.json").exists() else 0
    for n40 in sorted(ROOT.glob("reports/next40_*.json")):
        if n40.is_symlink():
            continue
        target = ROOT / "reports" / n40.name.replace("next40_", "asi25_")
        shutil.copy2(n40, target)
        print(f"collected {n40.name} -> {target.name}", flush=True)
    # AND SAY SO WHEN ONE IS STILL BEHIND THE STATE IT DESCRIBES.
    behind = [p.name for p in sorted(ROOT.glob("reports/asi25_*.json"))
              if p.name != "asi25_state.json"
              and p.stat().st_mtime < state_mtime]
    if behind:
        print("STALE — these describe an earlier state than reports/"
              "asi25_state.json: " + ", ".join(behind), file=sys.stderr)
        failures.append(("artifact_freshness", ", ".join(behind)))
    for name, why in failures:
        print(f"FAILED {name}: {why}", file=sys.stderr)
    return 1 if failures else 0


def _takes_out(mod) -> bool:
    import inspect
    try:
        src = inspect.getsource(mod.main)
    except Exception:                                        # noqa: BLE001
        return False
    return '"--out"' in src or "'--out'" in src


if __name__ == "__main__":
    raise SystemExit(main())
