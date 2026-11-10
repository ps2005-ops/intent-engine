#!/usr/bin/env python3
"""Can the subject-ownership guards fail? Mutate a mirror, require RED."""
from __future__ import annotations
import hashlib, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUITE = ("tests/test_subject_filings_are_not_displaced.py",)
APP = "src/intent_engine/webapp/app.py"

MUTATIONS = [
    ("A. third-party mentions rank level with the subject again", APP,
     '            if subject_cik and not _filed_by_subject(candidate) and (\n'
     '                    method == "third_party_filing" or "SEC EDGAR" in why):\n'
     '                return 6',
     '            if False:\n                return 6',
     "the live defect restored: Oklo and Enbridge displace Meta's own 10-K"),

    ("B. ownership is never read from the URL", APP,
     '        return match.group(1).lstrip("0") == subject_cik',
     "        return True",
     "every filing counts as the subject's own, including other registrants'"),

    ("C. nothing is ever the subject's own", APP,
     '        return match.group(1).lstrip("0") == subject_cik',
     "        return False",
     "the subject's own filings are demoted to context rank"),

    ("D. leading zeros stop matching", APP,
     '        subject_cik = "".join(ch for ch in str(subject_cik or "")\n'
     '                              if ch.isdigit()).lstrip("0")',
     '        subject_cik = str(subject_cik or "")',
     "0001326801 from the form never equals 1326801 from the URL"),
]


def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()


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
            t = mirror / rel
            src = t.read_text()
            if find not in src:
                results.append((name, "ANCHOR_MISSING", meaning)); continue
            out = src.replace(find, replace, 1)
            if out == src:
                results.append((name, "NO_OP", meaning)); continue
            t.write_text(out)
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", *SUITE, "-q", "-x",
                 "--no-header", "-p", "no:cacheprovider"],
                cwd=mirror, capture_output=True, text=True)
            results.append((name, "CAUGHT" if proc.returncode else
                            "NOT_CAUGHT", meaning))
    intact = digest(ROOT / APP) == before
    w = max(len(n) for n, _, _ in results)
    for name, verdict, meaning in results:
        print(f"{verdict:<14} {name:<{w}}")
        if verdict != "CAUGHT":
            print(f"{'':<14} -> green means: {meaning}")
    caught = sum(1 for _, v, _ in results if v == "CAUGHT")
    print(f"\n{caught}/{len(results)} caught; "
          f"app.py {'INTACT' if intact else 'MODIFIED'}")
    return 0 if caught == len(results) and intact else 1


if __name__ == "__main__":
    raise SystemExit(main())
