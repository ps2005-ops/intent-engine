#!/usr/bin/env python3
"""Can these guards fail? Mutate the product, require RED, restore exactly.

WHY A MIRROR AND NOT `src/`. A previous programme mutated the shared source
tree in place; another session's suite read the mutated file and a same-length
restore left an unchanged mtime, so a structural test kept reading stale
bytecode. Every mutation here is applied to a COPY of the tree, the suite runs
against the copy, and the original is never opened for writing.

WHY NOT_CAUGHT IS A FINDING, NOT A FAILURE OF THE SCRIPT. In this programme
four of four NOT_CAUGHT results named a real weak assertion. A mutation that
runs green is a report about the test, and it is printed as one.
"""
from __future__ import annotations

import hashlib
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUITE = ("tests/test_webapp_run_durability.py",
         "tests/test_pre100_harness_reads_real_pages.py",
         "tests/test_pre100_capture_over_a_real_socket.py")

APP = "src/intent_engine/webapp/app.py"
REC = "src/intent_engine/webapp/run_recovery.py"
CAP = "src/intent_engine/pre100/capture.py"


#: A MUTATION THAT WAS TRIED AND REMOVED, recorded so it is not re-tried as
#: if it were new. Deleting the `self._request.claim = None` line at the top
#: of `_route` runs GREEN, and that is correct rather than a weak test: every
#: path that READS the claim also assigns it a few lines later, so clearing
#: first changes no observable behaviour today. The line is defence-in-depth
#: against a future early return that reads the claim before assigning it,
#: and it is documented as that in the code -- not counted here as a guard it
#: is not.

#: (name, file, find, replace, what a green run would mean)
MUTATIONS = [
    ("A. a lost run gets no recovery at all", APP,
     "        state = self._missing_run_state(session, run_id)\n"
     "        if state != _recovery.RUN_RESTART_LOST:",
     "        state = self._missing_run_state(session, run_id)\n"
     "        if True:",
     "the recovery page is never rendered and nothing noticed"),

    ("B. the claim is never minted when a run opens", APP,
     "        if session is None or not session.get(\"user_id\") or not run_id:\n"
     "            return response",
     "        if True:\n"
     "            return response",
     "a run can open without a claim and recovery is unreachable"),

    ("C. any session may claim any run", REC,
     "    return (claim.get(\"run\") == run_id\n"
     "            and bool(user_id) and claim.get(\"uid\") == user_id)",
     "    return claim.get(\"run\") == run_id",
     "a copied cookie widens what another session is told"),

    ("D. the claim's signature is not checked", REC,
     "    if not hmac.compare_digest(_sign(secret, f\"{CLAIM_VERSION}.{body}\"), sig):\n"
     "        return None",
     "    if False:\n"
     "        return None",
     "a forged claim is honoured"),

    ("E. a claim never expires", REC,
     "    if moment - issued > CLAIM_TTL_SECONDS or issued - moment > 300:\n"
     "        return None                       # expired, or minted in the future",
     "    if False:\n"
     "        return None",
     "a stale or future-dated claim still proves something"),

    ("F. the claim does not carry the company", APP,
     "        token = _recovery.mint(self.config.secret,\n"
     "                               user_id=session[\"user_id\"], run_id=run_id,\n"
     "                               company=company)",
     "        token = _recovery.mint(self.config.secret,\n"
     "                               user_id=session[\"user_id\"], run_id=run_id,\n"
     "                               company=\"\")",
     "recovery hands the reader an empty form instead of a retry"),

    ("G. the harness posts questions at the dead route", CAP,
     "            f\"/runs/{run_id}/conversation\",\n"
     "            {\"csrf\": token, \"question\": question}, ref=f\"/runs/{run_id}\")",
     "            f\"/runs/{run_id}/answer\",\n"
     "            {\"csrf\": token, \"question\": question}, ref=f\"/runs/{run_id}\")",
     "ten 404 pages per company are stored as strategic answers"),

    ("H. a failure page counts as an answer", CAP,
     "    for marker in NOT_AN_ANSWER_MARKERS:\n"
     "        if marker in low:\n"
     "            return \"FAILURE_PAGE\"",
     "    for marker in ():\n"
     "        if marker in low:\n"
     "            return \"FAILURE_PAGE\"",
     "an unrecognised page is counted and scored for similarity"),

    ("I. the recovery page counts as an answer", CAP,
     '    "was lost when the service restarted",\n',
     "",
     "fifty recovery screens score as total cross-company collapse"),

    ("J. a restart is inferred rather than measured", CAP,
     "    if not a or not b:\n        return None",
     "    if not a or not b:\n        return False",
     "a missing sample is reported as 'no restart'"),
]


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    before = {name: digest(ROOT / name) for name in (APP, REC, CAP)}
    results = []
    for name, rel, find, replace, meaning in MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            mirror = pathlib.Path(tmp) / "tree"
            shutil.copytree(ROOT, mirror, symlinks=True, ignore=shutil.ignore_patterns(
                ".git", ".venv", "node_modules", "__pycache__", "reports",
                "data", "docs"))
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
            results.append((name, "CAUGHT" if proc.returncode else "NOT_CAUGHT",
                            meaning))

    after = {name: digest(ROOT / name) for name in (APP, REC, CAP)}
    intact = before == after

    width = max(len(n) for n, _, _ in results)
    for name, verdict, meaning in results:
        print(f"{verdict:<14} {name:<{width}}")
        if verdict != "CAUGHT":
            print(f"{'':<14} -> green means: {meaning}")
    caught = sum(1 for _, v, _ in results if v == "CAUGHT")
    print(f"\n{caught}/{len(results)} caught; "
          f"source tree {'INTACT' if intact else 'MODIFIED'}")
    return 0 if caught == len(results) and intact else 1


if __name__ == "__main__":
    raise SystemExit(main())
