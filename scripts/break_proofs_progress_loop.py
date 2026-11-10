#!/usr/bin/env python3
"""Can the redirect-loop guards fail? Mutate a mirror, require RED.

The loop was a three-node cycle, so a mutation at ONE node must still be
caught: that is the property the first attempt at this fix did not have.
"""
from __future__ import annotations

import hashlib
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUITE = ("tests/test_webapp_progress_never_loops.py",)
APP = "src/intent_engine/webapp/app.py"

_PRED = ("        if not self._availability(run_id).get(\"in_flight\"):\n"
         "            return False\n"
         "        return not self.result_readiness(run_id)[\"opens_result\"]")

MUTATIONS = [
    ("A. the predicate ignores readiness entirely", APP,
     _PRED,
     "        return bool(self._availability(run_id).get(\"in_flight\"))",
     "every surface bounces to progress while a result is openable -- the "
     "original loop, restored"),

    ("B. the run page bounces again", APP,
     "            avail = self._availability(run_id)\n"
     "            if self.only_watchable(run_id):",
     "            avail = self._availability(run_id)\n"
     "            if avail[\"in_flight\"]:",
     "the entry route re-enters the cycle"),

    ("C. the six-step guard bounces again", APP,
     "        if self.only_watchable(run_id):\n"
     "            return self._redirect(f\"/runs/{run_id}/progress\")\n"
     "        # ONE RUN MAY NOT SAY TWO THINGS.",
     "        if availability.get(\"in_flight\"):\n"
     "            return self._redirect(f\"/runs/{run_id}/progress\")\n"
     "        # ONE RUN MAY NOT SAY TWO THINGS.",
     "/intro re-enters the cycle -- the node the first fix missed"),

    ("D. the deck bounces again", APP,
     "            if self.only_watchable(run_id):\n"
     "                return self._redirect(f\"/runs/{run_id}/progress\")\n"
     "            if not avail[\"slides_ready\"]:",
     "            if avail[\"in_flight\"]:\n"
     "                return self._redirect(f\"/runs/{run_id}/progress\")\n"
     "            if not avail[\"slides_ready\"]:",
     "the presentation re-enters the cycle"),

    ("E. the predicate never sends anyone to progress", APP,
     _PRED,
     "        return False",
     "a reader races the worker on a half-built run -- the 400s and 500s "
     "the bounce exists to prevent"),
]


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
            source = target.read_text()
            if find not in source:
                results.append((name, "ANCHOR_MISSING", meaning))
                continue
            mutated = source.replace(find, replace, 1)
            if mutated == source:
                results.append((name, "NO_OP", meaning))
                continue
            target.write_text(mutated)
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", *SUITE, "-q", "-x",
                 "--no-header", "-p", "no:cacheprovider"],
                cwd=mirror, capture_output=True, text=True)
            results.append((name, "CAUGHT" if proc.returncode
                            else "NOT_CAUGHT", meaning))
    intact = digest(ROOT / APP) == before
    width = max(len(n) for n, _, _ in results)
    for name, verdict, meaning in results:
        print(f"{verdict:<14} {name:<{width}}")
        if verdict != "CAUGHT":
            print(f"{'':<14} -> green means: {meaning}")
    caught = sum(1 for _, v, _ in results if v == "CAUGHT")
    print(f"\n{caught}/{len(results)} caught; "
          f"app.py {'INTACT' if intact else 'MODIFIED'}")
    return 0 if caught == len(results) and intact else 1


if __name__ == "__main__":
    raise SystemExit(main())
