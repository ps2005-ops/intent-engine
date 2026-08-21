#!/usr/bin/env python3
"""Can the one-outcome guards fail? Mutate a mirror, require RED.

Every mutation below restores a defect that was ACTUALLY SHIPPED, or removes
a rule whose absence is what shipped it. A guard that stays green under these
is a guard that would not have caught Meta, and there is no point owning it.
"""
from __future__ import annotations
import hashlib, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUITE = ("tests/test_one_outcome_producer.py",
         "tests/test_full_agrees_with_every_other_surface.py",
         "tests/test_acceptance_instrument.py")
APP = "src/intent_engine/webapp/app.py"
OUT = "src/intent_engine/webapp/outcome.py"
VER = "src/intent_engine/pre100/verdict.py"

MUTATIONS = [
    ("A. /full is gated on the default layer again", APP,
     '                if avail["documents"] and avail["has_result"]:',
     '                if avail["documents"] and avail["has_result"] \\\n'
     '                        and layer == "default":',
     "the live Meta defect restored: /full renders a failure page over a "
     "composed result six other surfaces render"),

    ("B. a bounded page counts as the full analysis", OUT,
     '    if readiness.get("opens_result") and not readiness.get("degraded"):',
     '    if readiness.get("opens_result"):',
     "'Limited analysis' scores as a success, which is the false pass"),

    ("C. scarcity is claimed when nothing is known", OUT,
     '    # for. Refuse to call it scarcity on no information.\n'
     '    return RETRIEVAL_TEMPORARILY_UNAVAILABLE',
     '    # for. Refuse to call it scarcity on no information.\n'
     '    return TRUE_EVIDENCE_SCARCITY',
     "an unexplained stop becomes a statement about the company"),

    ("D. documents filed by other registrants count as the subject's", APP,
     '            "displaced_by_foreign": own == 0 and foreign > 0,',
     '            "displaced_by_foreign": False,',
     "Meta's run reading four other registrants' filings reads as scarcity"),

    ("E. the outcome is never stated on the response", APP,
     '        run_id = self._run_id_of(environ.get("PATH_INFO", ""))\n'
     '        if run_id:',
     '        run_id = self._run_id_of(environ.get("PATH_INFO", ""))\n'
     '        if False:',
     "every consumer goes back to guessing the outcome from prose"),

    ("F. the instrument stops reading failure language", VER,
     '        if row and row.get("failure_language"):',
     '        if False and row.get("failure_language"):',
     "'Analysis could not be completed' scores green again"),

    ("G. a chrome-only page counts as a rendered surface", VER,
     "THIN = 1200",
     "THIN = 0",
     "755 characters of apology passes as an analysis"),

    ("H. a bounded page for a registrant is accepted", VER,
     '        if expected_full(manifest) and stated == O.TRUE_EVIDENCE_SCARCITY:',
     '        if False and stated == O.TRUE_EVIDENCE_SCARCITY:',
     "Limited analysis becomes a graceful fallback for broken retrieval"),

    ("I. the instrument ignores a surface disagreement", VER,
     '    if manifest.get("outcome_disagreement"):',
     '    if False:',
     "one run telling two stories is recorded and never scored"),

    ("J. a stated success is trusted over the rendered page", VER,
     '    if stated in O.SUCCESSFUL and prose_failed:',
     '    if False and prose_failed:',
     "the only check that can catch the NEXT Meta is switched off"),
]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    before = {rel: digest(ROOT / rel) for rel in (APP, OUT, VER)}
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
                results.append((name, "ANCHOR_MISSING", meaning))
                continue
            out = src.replace(find, replace, 1)
            if out == src:
                results.append((name, "NO_OP", meaning))
                continue
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
    print(f"\n{caught}/{len(results)} caught; "
          f"sources {'INTACT' if intact else 'MODIFIED'}")
    return 0 if caught == len(results) and intact else 1


if __name__ == "__main__":
    raise SystemExit(main())
