#!/usr/bin/env python3
"""Can the late-evidence guard fail? Mutate a mirror, require RED."""
from __future__ import annotations
import hashlib, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUITE = ("tests/test_gate_judges_the_evidence_that_arrived.py",)
APP = "src/intent_engine/webapp/app.py"
SVC = "src/intent_engine/company_ingestion/service.py"

MUTATIONS = [
    ("A. the run never looks again", APP,
     "            if stored > seen:",
     "            if False:",
     "the live Meta defect restored: the gate judges 1 of 7 documents and "
     "the customer is told the evidence is scarce"),

    ("B. it recomposes on every run, not only late arrivals", APP,
     "            if stored > seen:",
     "            if True:",
     "every customer pays for a second synthesis that changes nothing"),

    ("E. a second synthesis is paid for even when the verdict is unchanged",
     APP,
     '                changed = (verdict or {}).get("may_synthesize") and \\\n'
     '                    not result.get("strategic_report")',
     "                changed = True",
     "five minutes of a single-worker deployment serving nobody, for a page "
     "that says the same thing"),

    ("F. the gate is never re-run, so the numbers stay wrong", APP,
     "                verdict = self._readiness_on_current_evidence(run_id)",
     "                verdict = None",
     "the customer still reads a count taken from a document set the run "
     "has outgrown"),

    ("C. the gate stops recording what it was given", SVC,
     '            "documents_at_compose": len(documents),',
     '            "documents_at_compose": 0,',
     "the measurement that found this stops being able to find it again"),

    ("D. the store count is read as the gate's count", APP,
     "                stored = len(self.ci.store.retrieved(run_id))",
     "                stored = seen",
     "the comparison can never be unequal, so the guard never fires"),
]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    before = {rel: digest(ROOT / rel) for rel in (APP, SVC)}
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
    intact = all(digest(ROOT / rel) == sha for rel, sha in before.items())
    width = max(len(n) for n, _, _ in results)
    for name, verdict, meaning in results:
        print(f"{verdict:<14} {name:<{width}}")
        if verdict != "CAUGHT":
            print(f"{'':<14} -> green means: {meaning}")
    caught = sum(1 for _, v, _ in results if v == "CAUGHT")
    print(f"\n{caught}/{len(results)} caught; sources "
          f"{'INTACT' if intact else 'MODIFIED'}")
    return 0 if caught == len(results) and intact else 1


if __name__ == "__main__":
    raise SystemExit(main())
