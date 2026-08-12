#!/usr/bin/env python3
"""Break the independence guards deliberately, one at a time.

Same hardened harness as `v5_dossier_break_proofs.py`, for the same reason: a
proof that reports CAUGHT without having changed anything certifies a guard
that may not exist. The three checks are (1) the mutation must actually
mutate, (2) the named test must go RED rather than error, (3) the restore must
be byte-exact and must bump mtime so CPython cannot serve stale bytecode.

Every mutation here is a plausible implementation, not a syntactic wrecking
ball. "Count duplicates as independent" is what an unhardened version of this
module would have done by default, which is exactly why it needs a proof.

Run:  PYTHONPATH=src python3 scripts/v5_independence_break_proofs.py
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "intent_engine"

IND = "tests/test_evidence_independence.py"
WAVE = "tests/test_breaker_wave_measurements.py"
ORDER = "tests/test_attested_beats_guessed.py"

#: (name, file, find, replace, test node that must go RED)
MUTATIONS = [
    # 1. duplicates counted as independent
    ("a duplicate document counts as an independent observation",
     SRC / "company_ingestion/independence.py",
     "INDEPENDENCE_BEARING = frozenset({REGULATOR_OR_PRIMARY_FILING,\n"
     "                                  INDEPENDENT_EXTERNAL_SOURCE})",
     "INDEPENDENCE_BEARING = frozenset({REGULATOR_OR_PRIMARY_FILING,\n"
     "                                  INDEPENDENT_EXTERNAL_SOURCE,\n"
     "                                  SAME_DOCUMENT})",
     # REPOINTED after NOT_CAUGHT, and the investigation is the finding.
     # `test_ten_duplicates_do_not_add_independence` builds duplicates that
     # share an origin with their original, so ORIGIN GROUPING absorbs this
     # mutation and the lineage rule is never the thing under test — the
     # guard was real but that test could not see it. A document mirrored at
     # a DIFFERENT origin is the case where the two defences separate.
     f"{IND}::test_the_same_document_mirrored_on_two_domains_is_one_"
     f"observation"),

    # 2. UNKNOWN lineage counted as independent
    ("unknown lineage counts as an independent observation",
     SRC / "company_ingestion/independence.py",
     "INDEPENDENCE_BEARING = frozenset({REGULATOR_OR_PRIMARY_FILING,\n"
     "                                  INDEPENDENT_EXTERNAL_SOURCE})",
     "INDEPENDENCE_BEARING = frozenset({REGULATOR_OR_PRIMARY_FILING,\n"
     "                                  INDEPENDENT_EXTERNAL_SOURCE,\n"
     "                                  UNKNOWN_LINEAGE})",
     f"{IND}::test_a_second_unknown_url_does_not_manufacture_independence"),

    # 3. source-family grouping removed
    ("independence is counted per ROW instead of per ORIGIN",
     SRC / "company_ingestion/independence.py",
     "    independent_count = len(independent_origins) + (\n"
     "        1 if any(not row[\"origin_family\"] for row in independent_rows)"
     " else 0)",
     "    independent_count = len(independent_rows)",
     # REPOINTED after NOT_CAUGHT. While every row carries a URL, `classify`
     # has already labelled same-origin rows SAME_ORIGIN, so per-row counting
     # and per-origin counting agree and the mutation is invisible. Rows with
     # NO url are the only place this aggregation is load-bearing.
     f"{IND}::test_rows_with_no_url_collapse_into_one_unknown_origin"),

    # 4. a different URL is treated as a different source
    ("a different URL is treated as a different origin",
     SRC / "company_ingestion/independence.py",
     "    labels = [label for label in host.split(\".\") if label]\n"
     "    if len(labels) <= 2:\n"
     "        return \".\".join(labels)\n"
     "    return \".\".join(labels[-2:])",
     "    return host",
     f"{IND}::test_different_urls_from_one_publisher_are_one_vantage_point"),

    # 5. syndication allowed to strengthen corroboration
    ("a syndicated copy is allowed to add corroboration",
     SRC / "company_ingestion/independence.py",
     "                if _jaccard(mine, shingles[earlier]) >= "
     "_REPUBLICATION_JACCARD:",
     "                if False:",
     f"{IND}::test_replacing_an_independent_source_with_a_syndication_"
     f"never_helps"),

    # 6. contradiction preservation removed
    ("a contradiction is dropped instead of carried beside corroboration",
     SRC / "company_ingestion/independence.py",
     '        "contradicting_evidence_ids": list(contradicting_ids),',
     '        "contradicting_evidence_ids": [],',
     f"{IND}::test_a_contradiction_stays_visible_beside_corroboration"),

    # 7. zero denominator becomes zero instead of UNMEASURABLE
    ("a ratio with no denominator reports 0 instead of UNMEASURABLE",
     ROOT / "scripts/v5_breaker_wave.py",
     "    return (round(numerator / denominator, 4) if denominator\n"
     "            else UNMEASURABLE)",
     "    return round(numerator / denominator, 4) if denominator else 0.0",
     f"{WAVE}::test_a_ratio_with_no_denominator_is_unmeasurable_not_zero"),

    # 8. an absent producer collapses into a measured zero
    ("a company with no independence producer is counted as zero",
     ROOT / "scripts/v5_breaker_wave.py",
     '    measured = [r for r in records\n'
     '                if _dig(r, "evidence", "evidence_independence_state")\n'
     '                == "MEASURED"]',
     "    measured = list(records)",
     f"{WAVE}::test_a_company_whose_producer_did_not_run_is_excluded_"
     f"not_counted_zero"),

    # 9. the belief arm claims health it never measured
    ("the unmeasured belief arm reports STABLE",
     ROOT / "scripts/v5_breaker_wave.py",
     '        "belief_arm": UNMEASURABLE,\n'
     '        "belief_arm_reason": ("independent evidence → belief movement '
     'needs "',
     '        "belief_arm": "STABLE",\n'
     '        "belief_arm_reason": ("independent evidence → belief movement '
     'needs "',
     f"{WAVE}::test_the_belief_arm_is_never_claimed_stable"),

    # 10. the retrieval repair widened past the security boundary
    ("the reachability demotion is dropped, so guesses at a refusing host "
     "climb back above real evidence",
     SRC / "webapp/app.py",
     "            if _on_refusing_host(candidate):\n"
     "                return 9",
     "            if False:\n"
     "                return 9",
     f"{ORDER}::test_a_refusing_host_is_still_ranked_below_every_guess"),
]


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: pathlib.Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    future = time.time() + 1
    os.utime(path, (future, future))
    for cache in path.parent.glob("__pycache__/*.pyc"):
        cache.unlink(missing_ok=True)


def run_test(node: str) -> tuple:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", node, "-x", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"),
             "PYTHONDONTWRITEBYTECODE": "1"})
    out = proc.stdout + proc.stderr
    failed = " failed" in out or "FAILED" in out
    errored = " error" in out.lower() and not failed
    return failed, errored, out.strip().splitlines()[-1] if out else ""


def main() -> int:
    results = []
    for name, path, find, repl, node in MUTATIONS:
        original = path.read_text(encoding="utf-8")
        before = sha(path)

        if find not in original:
            results.append(("NO_OP_TARGET_MISSING", name, node,
                            "the mutation target was not found in the file"))
            continue

        write(path, original.replace(find, repl, 1))
        after = sha(path)
        try:
            if after == before:
                results.append(("NO_OP_HASH_UNCHANGED", name, node,
                                "the file did not change"))
                continue
            failed, errored, tail = run_test(node)
            if failed:
                results.append(("CAUGHT", name, node, tail))
            elif errored:
                results.append(("ERRORED_NOT_FAILED", name, node, tail))
            else:
                results.append(("NOT_CAUGHT", name, node, tail))
        finally:
            write(path, original)
            assert sha(path) == before, f"restore was not exact for {path}"

    width = max(len(r[0]) for r in results)
    caught = sum(1 for r in results if r[0] == "CAUGHT")
    print(f"\n{'=' * 78}\nV5 INDEPENDENCE BREAK PROOFS — {caught}/"
          f"{len(results)} CAUGHT\n{'=' * 78}")
    for status, name, node, tail in results:
        print(f"{status:<{width}}  {name}")
        if status != "CAUGHT":
            print(f"{'':<{width}}  ↳ {node}\n{'':<{width}}    {tail}")
    print()
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
