#!/usr/bin/env python3
"""Can the one-denominator guard fail? Mutate a mirror, require RED."""
from __future__ import annotations
import hashlib, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUITE = ("tests/test_one_denominator_per_page.py",)
APP = "src/intent_engine/webapp/app.py"

MUTATIONS = [
    ("A. the compose-time count is printed over the live list again", APP,
     '            if usable < len(used):',
     '            if False:',
     "the live defect restored: '1 carried usable evidence' above seven"),

    ("B. the mismatch is hidden instead of explained", APP,
     '                read_line += (f"; the evidence gate was applied to '
     '{usable} "\n                              f"of them")',
     '                pass',
     "a reader sees seven documents and a limited verdict with no reason"),

    ("C. a true smaller usable count stops being reported", APP,
     '                read_line += f"; {usable} carried usable evidence"',
     '                pass',
     "pages that were read but carried nothing are silently equated with "
     "pages that carried evidence"),
]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    before = digest(ROOT / APP)
    results = []
    for name, rel, find, replace, meaning in MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            mirror = pathlib.Path(tmp) / "tree"
            shutil.copytree(ROOT, mirror, symlinks=True,
                            ignore=shutil.ignore_patterns(
                                ".git", ".venv", "node_modules", "__pycache__",
                                "reports", "data", "docs"))
            target = mirror / rel
            src = target.read_text()
            if find not in src:
                results.append((name, "ANCHOR_MISSING", meaning)); continue
            out = src.replace(find, replace, 1)
            if out == src:
                results.append((name, "NO_OP", meaning)); continue
            target.write_text(out)
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", *SUITE, "-q", "-x",
                 "--no-header", "-p", "no:cacheprovider"],
                cwd=mirror, capture_output=True, text=True)
            results.append((name, "CAUGHT" if proc.returncode else
                            "NOT_CAUGHT", meaning))
    intact = digest(ROOT / APP) == before
    width = max(len(n) for n, _, _ in results)
    for name, verdict, meaning in results:
        print(f"{verdict:<14} {name:<{width}}")
        if verdict != "CAUGHT":
            print(f"{'':<14} -> green means: {meaning}")
    caught = sum(1 for _, v, _ in results if v == "CAUGHT")
    print(f"\n{caught}/{len(results)} caught; app.py "
          f"{'INTACT' if intact else 'MODIFIED'}")
    return 0 if caught == len(results) and intact else 1


if __name__ == "__main__":
    raise SystemExit(main())
