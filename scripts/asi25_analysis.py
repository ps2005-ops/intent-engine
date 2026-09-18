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
    ("next40_learning_report", "asi25_learning.json", []),
)


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
    print(_align_widths(), flush=True)
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
        sys.argv = argv + (["--out", str(ROOT / "reports" / out)]
                           if _takes_out(mod) else [])
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
