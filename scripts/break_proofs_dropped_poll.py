#!/usr/bin/env python3
"""Can the dropped-poll guard fail? Mutate a mirror, require RED."""
from __future__ import annotations
import hashlib, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUITE = ("tests/test_a_dropped_poll_is_not_a_dead_run.py",)
CAP = "src/intent_engine/pre100/capture.py"

MUTATIONS = [
    ("A. one transport error ends the run again", CAP,
     "MAX_POLL_ERRORS = 3",
     "MAX_POLL_ERRORS = 1",
     "the live defect restored: two live analyses discarded by the "
     "instrument that was measuring them"),

    ("B. a dead service is waited on forever", CAP,
     "            if transport_errors >= MAX_POLL_ERRORS:\n"
     "                return FAILED, url, round(time.time() - started), samples",
     "            if False:\n"
     "                return FAILED, url, round(time.time() - started), samples",
     "a service that stopped answering is never called failed"),

    ("C. the poll goes back to the session timeout", CAP,
     "POLL_TIMEOUT = 45.0",
     "POLL_TIMEOUT = 180.0",
     "one hung poll consumes three minutes again"),

    ("D. the short timeout is defined and never passed", CAP,
     '        status, url, page = session.get(f"/runs/{run_id}/progress",\n'
     '                                        timeout=POLL_TIMEOUT)',
     '        status, url, page = session.get(f"/runs/{run_id}/progress")',
     "the constant exists and nothing uses it"),

    ("E. the error counter never resets", CAP,
     "        transport_errors = 0\n"
     '        if "/progress" not in url:',
     '        if "/progress" not in url:',
     "scattered errors across a long run accumulate into a false failure"),
]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    before = digest(ROOT / CAP)
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
    intact = digest(ROOT / CAP) == before
    width = max(len(n) for n, _, _ in results)
    for name, verdict, meaning in results:
        print(f"{verdict:<14} {name:<{width}}")
        if verdict != "CAUGHT":
            print(f"{'':<14} -> green means: {meaning}")
    caught = sum(1 for _, v, _ in results if v == "CAUGHT")
    print(f"\n{caught}/{len(results)} caught; capture.py "
          f"{'INTACT' if intact else 'MODIFIED'}")
    return 0 if caught == len(results) and intact else 1


if __name__ == "__main__":
    raise SystemExit(main())
