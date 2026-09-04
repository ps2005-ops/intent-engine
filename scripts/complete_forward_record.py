"""Append the creation date a forward record was written without.

WHAT HAPPENED
-------------
`open_relation_expectations.py` appended straight to the forward ledger rather
than going through `belief.Expectation`, which requires an
`information_cutoff` AND a `created_at`. The one record it opened,
`rl-b669edc0cdcd5c`, carries the cutoff and not the date it was made — so it
could not answer the single question preregistration exists to answer: did
this prediction use evidence that arrived after it was written down.

WHY THIS APPENDS RATHER THAN EDITS
----------------------------------
`created_at` is not in the ledger's immutable core (`information_cutoff`,
`horizon_days`, `expires_at`, `resolution_rule`, `confidence`, `quantity`,
`expected_direction`), so adding it moves nothing about the prediction. The
record accumulates; `by_id` reads the last row.

AND THE DATE IS ESTABLISHED, NOT CHOSEN
---------------------------------------
The record carries `code_sha`. `git log -1 --format=%cs <sha>` is the date
that commit was made, and the row is written with the note saying so. If the
sha is not in this repository the script refuses rather than guessing.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import forward_ledger as FL           # noqa: E402


def commit_date(sha: str) -> str:
    out = subprocess.run(["git", "log", "-1", "--format=%cs", sha],
                         capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else ""


def main() -> int:
    records = FL.by_id()
    incomplete = [r for r in records.values() if not r.get("created_at")]
    if not incomplete:
        print("every forward record carries its creation date")
        return 0
    completions = []
    for r in incomplete:
        sha = str(r.get("code_sha") or "")
        when = commit_date(sha) if sha else ""
        if not when:
            print(f"  REFUSED {r['expectation_id']}: its code_sha {sha!r} is "
                  "not in this repository, so the date it was made cannot be "
                  "established. Guessing one would be backdating.")
            continue
        cutoff = str(r.get("information_cutoff") or "")
        if cutoff and cutoff > when:
            print(f"  REFUSED {r['expectation_id']}: its cutoff {cutoff} is "
                  f"after the commit date {when}, which is a hindsight leak "
                  "rather than a missing field.")
            continue
        completions.append(dict(r, created_at=when, note=(
            f"{r.get('note', '')} created_at established from code_sha "
            f"{sha}, committed {when}; the generator wrote the cutoff and "
            f"not the creation date and has been repaired.").strip()))
        print(f"  {r['expectation_id']}: created_at = {when} (from {sha})")
    if completions:
        FL.append(completions, path=FL.DEFAULT_PATH)
    life = FL.assert_lifecycle()
    print(f"\n  ledger holds {life['expectations']} expectations, "
          f"{life['open']} open, {life['resolved']} resolved")
    print(f"  all lifecycle facts hold: {life['all_seven_hold']}")
    print(f"  facts: {json.dumps(life['facts'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
