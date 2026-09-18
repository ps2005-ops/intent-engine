#!/usr/bin/env python3
"""Break the Batch-13 guards deliberately, one at a time.

Same hardened harness as `v5_independence_break_proofs.py`: the mutation must
actually change the file, the named test must go RED rather than error, and
the restore must be byte-exact with a bumped mtime so CPython cannot serve
stale bytecode from a same-length edit.

Every mutation is a PLAUSIBLE implementation — in several cases the exact one
that was there before this batch — because a proof is only worth running
against a version someone might actually write.

Run:  PYTHONPATH=src python3 scripts/v5_batch13_break_proofs.py
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

ORIGIN = "tests/test_independent_author_origin.py"
LEARN = "tests/test_learning_attribution.py"
BRIDGE = "tests/test_dossier_independence_bridge.py"

#: (name, file, find, replace, test node that must go RED)
MUTATIONS = [
    # --- §39 discovery ------------------------------------------------------
    # 1. THE EXACT PRE-BATCH-13 BEHAVIOUR: an attested third-party filing and
    #    a slug-built review URL tie, so insertion order takes the slot.
    # REPOINTED after NOT_CAUGHT, and the investigation is the finding.
    # `test_attested_filing_takes_the_independent_slot_over_a_guess` is
    # defended TWICE — the filing is promoted to tier 1 AND the review guess
    # is demoted to tier 5 — so removing either one leaves the other holding
    # and the mutation is invisible. The promotion is only load-bearing
    # against an attested peer that is NOT demoted, which is what the
    # repointed test builds.
    ("a guessed review URL crowds out an attested independent filing",
     SRC / "webapp/app.py",
     '            if method == "third_party_filing":\n'
     '                return 1\n',
     '',
     f"{ORIGIN}::test_filing_outranks_an_equally_attested_independent_peer"),

    # 2. off-domain candidate admitted without checking whose filing it is
    ("the subject's own filing is proposed as an independent source",
     SRC / "company_ingestion/third_party_filings.py",
     "        if _same_organisation(filer, company_name):\n"
     "            continue\n",
     '',
     f"{ORIGIN}::test_subject_own_filing_is_dropped_when_cik_resolution_"
     f"failed"),

    # 3. source concentration ignored when spending the budget
    ("origin diversity is ignored, so one host takes every slot",
     SRC / "webapp/app.py",
     "                choice = next(\n"
     "                    (c for c in pool\n"
     "                     if _relevance_first(c) == best_tier\n"
     "                     and origin_family(c.get(\"url\", \"\")) "
     "not in seen_origins),\n"
     "                    pool[0])",
     "                choice = pool[0]",
     f"{ORIGIN}::test_leftover_budget_prefers_an_unseen_origin_within_a_tier"),

    # 4. duplicate origin treated as diversity — the venue/author collapse,
    #    reintroduced by reading the host for filings too.
    ("a filing's origin is its host, so two registrants are one origin",
     SRC / "company_ingestion/independence.py",
     "    author = filing_author(url)\n"
     "    if author:\n"
     "        return f\"sec.gov/filer/{author}\"\n",
     '',
     f"{ORIGIN}::test_two_registrants_are_two_origins"),

    # 5. the reverse error: every URL its own origin, so copies read as
    #    separate accounts.
    # REPOINTED after NOT_CAUGHT. This mutation targets the HOST fallback,
    # and an EDGAR URL returns from `filing_author` before ever reaching it —
    # so a filing fixture cannot observe it. The non-filing case is where
    # this line is load-bearing.
    ("each URL becomes its own origin, so one publisher reads as many",
     SRC / "company_ingestion/independence.py",
     "    labels = [label for label in host.split(\".\") if label]\n"
     "    if len(labels) <= 2:\n"
     "        return \".\".join(labels)\n"
     "    return \".\".join(labels[-2:])",
     "    return url",
     f"{ORIGIN}::test_non_filing_hosts_keep_host_grouping"),

    # --- §40 attribution ----------------------------------------------------
    # 6. evidence ABOUT a belief counted as evidence that CHANGED it
    ("evidence that merely mentions a thesis counts as having moved it",
     SRC / "company_ingestion/learning_attribution.py",
     "            if self.before_state == self.after_state:\n"
     "                raise NotAChange(",
     "            if False:\n"
     "                raise NotAChange(",
     f"{LEARN}::test_evidence_merely_about_a_thesis_is_not_a_change"),

    # 7. raw effect count used as the numerator over evidence rows
    ("the effect count becomes the numerator over evidence rows",
     SRC / "company_ingestion/learning_attribution.py",
     '        "effect_producing_evidence_rows": len(producing),',
     '        "effect_producing_evidence_rows": len(changing),',
     f"{LEARN}::test_numerator_counts_rows_not_effects"),

    # 8. a blocked backend reported as a measured zero
    ("a blocked reasoning backend reports zero learning",
     SRC / "company_ingestion/learning_attribution.py",
     '            "learning_conversion": UNAVAILABLE,\n'
     '            "independent_learning_conversion": UNAVAILABLE,',
     '            "learning_conversion": 0.0,\n'
     '            "independent_learning_conversion": 0.0,',
     f"{LEARN}::test_blocked_backend_is_not_a_measured_zero"),

    # 9. independent-origin metadata discarded from a change's support
    ("the origins behind a change are discarded",
     SRC / "company_ingestion/learning_attribution.py",
     '    independent = sorted({str(r.get("origin_family") or "") for r in rows\n'
     '                          if r.get("independence_bearing")\n'
     '                          and r.get("origin_family")})',
     '    independent = []',
     f"{LEARN}::test_a_change_carries_the_structure_of_its_support"),

    # --- §41 dossier --------------------------------------------------------
    # 10. the block is dropped from the allowed contract — the "bridge never
    #     opened" failure, where a refused field and an unanalysed company
    #     look identical.
    ("evidence_independence is removed from the founder contract",
     SRC / "demo_dossier/contracts.py",
     '    "evidence_independence": _INDEPENDENCE_BLOCK,\n',
     '',
     f"{BRIDGE}::test_independence_block_is_not_dropped_into_unknown_fields"),

    # 11. THE PRE-BATCH-13 PRODUCER: a constant where a measurement belongs.
    ("the producer hardcodes independence as unavailable",
     SRC / "external_intel/founder_demo_snapshot.py",
     '        "evidence_independence_state": _independence_state(independence),',
     '        "evidence_independence_state": V.INDEPENDENCE_UNAVAILABLE,',
     f"{BRIDGE}::test_measured_independence_reaches_the_dossier_as_available"),

    # 12. syndicated copies rendered to a founder as separate sources
    ("ten copies of one release are rendered as ten independent sources",
     SRC / "company_ingestion/independence.py",
     '    if independent == 0:\n'
     '        return (f"{documents} support this view, none of them from a '
     'vantage "\n'
     '                "point outside the company.")',
     '    if False:\n'
     '        return ""',
     f"{BRIDGE}::test_ten_copies_of_one_release_are_never_rendered_as_ten_"
     f"sources"),

    # 13. unknown lineage rendered as though it were established.
    #     THE ANCHOR IS DELIBERATELY LONG. `if unknown == rows:` occurs first
    #     in `_corroboration`, so the short form mutated a different function
    #     entirely and the proof reported NOT_CAUGHT against a guard it had
    #     never touched — a false negative from an ambiguous target, not from
    #     a missing test.
    ("unknown lineage is rendered as if it were independent",
     SRC / "company_ingestion/independence.py",
     "    if unknown == rows:\n"
     "        # SAY SO (§25). Unknown lineage rendered as independence is the\n"
     "        # single cheapest way to manufacture corroboration.",
     "    if False:\n"
     "        # SAY SO (§25). Unknown lineage rendered as independence is the\n"
     "        # single cheapest way to manufacture corroboration.",
     f"{BRIDGE}::test_unknown_lineage_is_said_to_be_unknown_not_independent"),
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
    print(f"\n{'=' * 78}\nV5 BATCH-13 BREAK PROOFS — {caught}/"
          f"{len(results)} CAUGHT\n{'=' * 78}")
    for status, name, node, tail in results:
        print(f"{status:<{width}}  {name}")
        if status != "CAUGHT":
            print(f"{'':<{width}}  ↳ {node}\n{'':<{width}}    {tail}")
    print()
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
