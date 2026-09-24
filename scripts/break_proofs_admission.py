#!/usr/bin/env python3
"""Break proofs for pre-run admission refusal.

Every mutation is applied to a COPY of the tree and must turn a green test
red for the stated reason. Each one mutates a PRODUCTION site — the category
table, the classifier, or the admission branch itself — never a test.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
T = "tests/test_admission_refusal_is_truthful.py"
C = "tests/test_capacity_boundary.py"

MUTATIONS = [
    dict(name="A1 the refusal falls back to substring classification",
         path="src/intent_engine/webapp/app.py",
         old="                            category=_failures.ADMISSION_REFUSED)",
         new="                            )",
         tests=[f"{T}::test_the_admission_call_site_names_the_category_itself"]),
    dict(name="A2 the classifier loses the admission signature",
         path="src/intent_engine/webapp/failures.py",
         old='    ("already running as many analyses", ADMISSION_REFUSED),',
         new="",
         tests=[f"{T}::"
                "test_the_refusal_message_no_longer_classifies_as_credit_exhaustion"]),
    dict(name="A3 the refusal page claims evidence was retrieved",
         path="src/intent_engine/webapp/failures.py",
         old='''    ADMISSION_REFUSED: "Your request arrived and your session is intact. "
                       "No analysis credit was used.",''',
         new='''    ADMISSION_REFUSED: "The company was identified and its public "
                       "evidence was retrieved.",''',
         tests=[f"{T}::test_the_refusal_page_claims_no_work_it_did_not_do"]),
    dict(name="A4 the refusal stops being retryable",
         path="src/intent_engine/webapp/failures.py",
         old='''        "Try again in a few minutes — the same company will run normally "
        "once a slot frees up.",
        True,''',
         new='''        "Try again in a few minutes — the same company will run normally "
        "once a slot frees up.",
        False,''',
         tests=[f"{T}::test_the_refusal_is_terminal_and_retryable_and_says_so"]),
    dict(name="A5 a refused submission redirects to a progress page",
         path="src/intent_engine/webapp/app.py",
         old="""                    if not started and not (
                            run_id in self._results
                            or self.ci.store.run_state(run_id)
                            in self.TERMINAL_STATES):""",
         new="""                    if False:""",
         tests=[f"{C}::test_a_refused_submission_never_reaches_a_progress_page",
                f"{C}::test_a_refused_submission_creates_no_run"]),
    dict(name="A6 a refused submission consumes the demo quota",
         path="src/intent_engine/webapp/app.py",
         old="""                        self._release_demo_quota(session, remote,
                                                 _reserved)""",
         new="""                        pass""",
         tests=[f"{C}::test_a_refused_submission_gives_back_its_quota"]),
]


def run(tests, cwd):
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "--no-header",
                        *tests], cwd=cwd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr)[-1800:]


def main() -> int:
    held, broke = 0, []
    for m in MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            tree = pathlib.Path(tmp) / "t"
            shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(
                ".git", ".venv", "__pycache__", "*.pyc", "reports", "data"))
            target = tree / m["path"]
            text = target.read_text()
            if m["old"] not in text:
                broke.append((m["name"], "MUTATION SITE NOT FOUND"))
                continue
            code, out = run(m["tests"], tree)
            if code != 0:
                broke.append((m["name"], f"NOT GREEN BEFORE:\n{out}"))
                continue
            target.write_text(text.replace(m["old"], m["new"], 1))
            code, out = run(m["tests"], tree)
            target.write_text(text)
            assert target.read_text() == text
            if code == 0:
                broke.append((m["name"], f"NOT_CAUGHT:\n{out}"))
                continue
            held += 1
            print(f"HELD   {m['name']}")
    for name, why in broke:
        print(f"FAILED {name}\n{why}\n")
    print(f"\n{held}/{len(MUTATIONS)} mutations held")
    return 0 if held == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
