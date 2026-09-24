#!/usr/bin/env python3
"""Break the dossier's guards deliberately, one at a time.

WHY THE HARNESS IS HARDENED
----------------------------
A break proof that reports CAUGHT without having changed anything is worse
than no break proof: it certifies a guard that may not exist. This program has
recorded three distinct ways that happens, and each is checked here.

1. THE MUTATION MUST ACTUALLY MUTATE. If the target string is not found, or
   the file's hash is unchanged after writing, the run is a NO-OP and is
   reported as an error, never as CAUGHT.

2. THE TEST MUST GO RED FOR THE STATED REASON. A test that errors on an
   unrelated ImportError is not evidence about the guard, so the named test
   must FAIL (not error out at collection) and the run records which.

3. THE RESTORE MUST BE EXACT, AND MUST BUMP mtime. A same-length mutation
   restored in place leaves CPython running the cached bytecode from the
   mutated source — the next proof then measures a file that is no longer
   what is on disk. Every write bumps mtime and the final hash is compared to
   the original.

Run:  PYTHONPATH=src python3 scripts/v5_dossier_break_proofs.py
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
TESTS = ROOT / "tests"

JOIN = "tests/test_a_company_dossier_joins_two_systems.py"
NEUTRAL = "tests/test_the_dossier_seam_stays_neutral.py"
REAL = "tests/test_the_dossier_survives_real_companies.py"
SURFACE = "tests/test_the_dossier_is_reachable_by_a_human.py"
UNIVERSE = "tests/test_the_validation_universe_is_locked.py"

#: (name, file, find, replace, test node that must go RED)
MUTATIONS = [
    ("founder code imports a market module",
     SRC / "demo_dossier/assembler.py",
     "from dataclasses import replace",
     "from dataclasses import replace\nfrom intent_engine.external_intel "
     "import pack  # noqa: F401",
     f"{NEUTRAL}::test_the_neutral_package_imports_neither_side"),

    ("a missing market block becomes zero market signals",
     SRC / "demo_dossier/assembler.py",
     '"is_measured_zero": blk.is_zero',
     '"is_measured_zero": blk.count == 0',
     f"{JOIN}::test_an_absent_market_snapshot_is_not_zero_market_signals"),

    # REPOINTED after going NOT_CAUGHT. This mutation targets the path where
    # the producer OMITS a block; the test it first named exercises the path
    # where the producer declares it UNAVAILABLE. Two different absences, and
    # only one had an assertion — the guard was real and unasserted, so the
    # missing test was written rather than the proof softened.
    ("an omitted block becomes an available empty one",
     SRC / "demo_dossier/contracts.py",
     'return RefBlock(state=REF_UNAVAILABLE,\n'
     '                        note="the producer sent no block here")',
     'return RefBlock(state=REF_AVAILABLE,\n'
     '                        note="the producer sent no block here")',
     f"{JOIN}::test_a_block_the_producer_omitted_entirely_is_not_a_zero"),

    ("a declared-unavailable block becomes an available one",
     SRC / "demo_dossier/contracts.py",
     "    state = str(node.get(\"state\") or REF_UNAVAILABLE)",
     "    state = str(node.get(\"state\") or REF_AVAILABLE)",
     f"{JOIN}::test_a_block_that_declares_no_state_is_not_assumed_available"),

    ("a missing internal impact becomes no internal impact",
     SRC / "demo_dossier/contracts.py",
     'internal_impact_state=str(payload.get("internal_impact_state")\n'
     '                                  or "INTERNAL_DATA_UNAVAILABLE"),',
     'internal_impact_state=str(payload.get("internal_impact_state")\n'
     '                                  or "NO_INTERNAL_IMPACT"),',
     f"{JOIN}::test_an_omitted_internal_impact_reads_unavailable_"
     f"not_no_impact"),

    ("a first observation is reported as change",
     SRC / "demo_dossier/diff.py",
     "return DossierDiff(state=V.FIRST_OBSERVATION,",
     "return DossierDiff(state=V.CHANGED,",
     f"{JOIN}::test_the_first_dossier_is_first_observation_not_"
     f"everything_changed"),

    ("a first observation is reported as measurable impact",
     SRC / "demo_dossier/assembler.py",
     "        return V.IMPACT_UNMEASURABLE_FIRST_OBSERVATION",
     "        return V.IMPACT_MEASURED",
     f"{JOIN}::test_a_first_dossier_is_unmeasurable_not_no_impact"),

    ("the evidence window is dropped from the dossier identity",
     SRC / "demo_dossier/dossier.py",
     '"effective_evidence_cutoff": self.effective_evidence_cutoff,',
     "",
     f"{JOIN}::test_a_changed_evidence_window_creates_a_new_version"),

    ("the runtime sha is dropped from the dossier identity",
     SRC / "demo_dossier/dossier.py",
     '"market_runtime_sha": self.market_runtime_sha,',
     "",
     f"{JOIN}::test_a_changed_runtime_sha_creates_a_new_version"),

    ("the synthetic label is removed",
     SRC / "demo_dossier/assembler.py",
     'synthetic_label=("This joins synthetic data and is a product proof, "\n'
     '                         "not real intelligence about this company."\n'
     "                         if population in V.MUST_LABEL_SYNTHETIC "
     'else ""),',
     'synthetic_label="",',
     f"{JOIN}::test_a_synthetic_product_proof_must_carry_its_label"),

    ("quarantine no longer blocks a demo state",
     SRC / "demo_dossier/assembler.py",
     "    if quarantined:\n        return V.QUARANTINED",
     "    if False:\n        return V.QUARANTINED",
     f"{JOIN}::test_quarantine_blocks_every_demo_state"),

    # REPOINTED after going NOT_CAUGHT. Removing `tenant_id` from the refusal
    # set changed nothing, because the allowlist walk refuses it too — that is
    # defense in depth working, not a missing guard. But the allowlist walk
    # never descends into LISTS, so the depth scan is the only layer there,
    # and that case had no assertion until this proof asked for one.
    ("tenant authority is accepted from a market snapshot",
     SRC / "demo_dossier/contracts.py",
     '_MARKET_FORBIDDEN = frozenset({\n    "tenant_id",',
     '_MARKET_FORBIDDEN = frozenset({\n    "__never__",',
     f"{JOIN}::test_a_tenant_id_hidden_inside_a_list_is_still_refused"),

    ("a forged private reference from market is not detected",
     SRC / "demo_dossier/assembler.py",
     "    if _tenant_leak(market, founder):\n"
     "        reasons.append(V.TENANT_LEAK)",
     "    if False:\n        reasons.append(V.TENANT_LEAK)",
     f"{JOIN}::test_the_assembler_does_not_adopt_tenant_authority_"
     f"from_market"),

    ("an unknown security-sensitive field stops failing closed",
     SRC / "demo_dossier/contracts.py",
     "    return any(token in low for token in _SECURITY_SENSITIVE)",
     "    return False",
     f"{JOIN}::test_an_unknown_security_field_fails_closed"),

    ("persistence and reload lose block availability",
     SRC / "demo_dossier/dossier.py",
     "        known = {f for f in cls.__dataclass_fields__}",
     '        known = {f for f in cls.__dataclass_fields__\n'
     '                 if f != "market_block"}',
     f"{JOIN}::test_reload_in_a_fresh_store_keeps_block_availability"),

    ("the producer is never called by the real analysis path",
     SRC / "webapp/app.py",
     "        self._publish_demo_dossier(run_id, stamped)",
     "        pass  # producer call removed",
     f"{REAL}::test_a_real_web_analysis_publishes_a_dossier_by_itself"),

    # --- the inspection surface -------------------------------------------
    ("the inspection surface publishes private reference ids",
     SRC / "demo_dossier/views.py",
     "    out[\"ids\"] = []\n    out[\"ids_redacted\"] = True",
     "    out[\"ids_redacted\"] = True",
     f"{SURFACE}::test_private_reference_ids_are_never_published"),

    ("redaction is applied but reads as absence",
     SRC / "demo_dossier/views.py",
     '    out = dict(block)\n    out["ids"] = []',
     '    out = {"ids": []}',
     f"{SURFACE}::test_private_reference_ids_are_never_published"),

    ("the detail route skips redaction entirely",
     SRC / "demo_dossier/views.py",
     "        if name in blocks:\n            blocks[name] = _redact("
     "blocks[name])",
     "        if False:\n            blocks[name] = _redact(blocks[name])",
     f"{SURFACE}::test_private_reference_ids_are_never_published"),

    ("an unanalysed company returns a bare 404 with no stated reason",
     SRC / "demo_dossier/views.py",
     '        "state": V.NOT_STARTED,',
     '        "state": "UNKNOWN",',
     f"{SURFACE}::test_an_unknown_company_is_a_stated_absence_not_a_bare_404"),

    ("the telemetry route is shadowed by the detail route",
     SRC / "webapp/app.py",
     '        if path == "/demo-dossiers/telemetry" and method == "GET":\n'
     "            return self._ok_json(self._demo_telemetry.as_dict())\n",
     "",
     f"{SURFACE}::test_the_telemetry_route_is_not_shadowed_by_the_"
     f"detail_route"),

    ("the index dumps whole blocks instead of indexing",
     SRC / "demo_dossier/views.py",
     '        "generated_at": dossier.generated_at,\n    }',
     '        "generated_at": dossier.generated_at,\n'
     '        "market_block": dossier.market_block,\n    }',
     f"{SURFACE}::test_the_index_is_an_index_and_carries_no_reference_ids"),

    # --- the validation universe (Batch 9) --------------------------------
    ("the exactly-one-hundred guard is removed",
     SRC / "validation/manifest.py",
     "    if len(cs) != TOTAL:",
     "    if False:",
     f"{UNIVERSE}::test_a_hundred_and_first_company_fails"),

    ("the unique company-id guard is removed",
     SRC / "validation/manifest.py",
     '        problems.append(f"duplicate company_id: {sorted(dupes)}")',
     "        pass",
     f"{UNIVERSE}::test_a_duplicate_company_id_fails"),

    ("a duplicate canonical entity is accepted",
     SRC / "validation/manifest.py",
     '        problems.append(f"duplicate canonical_name: '
     '{sorted(dupe_names)}")',
     "        pass",
     f"{UNIVERSE}::test_a_duplicate_canonical_name_fails"),

    ("an undeclared shared domain is accepted",
     SRC / "validation/manifest.py",
     "        if len(rows) > 1 and not any(r.parent_company_id "
     "for r in rows):",
     "        if False:",
     f"{UNIVERSE}::test_an_undeclared_duplicate_domain_fails"),

    ("the North American scope guard is removed",
     SRC / "validation/manifest.py",
     "    outside = sorted({c.country for c in cs} - NORTH_AMERICA)",
     "    outside = []",
     f"{UNIVERSE}::test_a_company_outside_north_america_fails"),

    ("the heterogeneity gate is removed",
     SRC / "validation/manifest.py",
     "    for sector, minimum in sorted(SECTOR_MINIMUMS.items()):",
     "    for sector, minimum in []:",
     f"{UNIVERSE}::test_gutting_a_sector_fails"),

    ("the holdout lock is removed",
     SRC / "validation/manifest.py",
     '        problems.append(f"blind holdout not locked: '
     '{sorted(unlocked)}")',
     "        pass",
     f"{UNIVERSE}::test_an_unlocked_holdout_fails"),

    ("a cohort may be hand-edited away from the documented rule",
     SRC / "validation/manifest.py",
     "        derived = derive_cohorts(cs)",
     "        derived = {c.company_id: c.cohort for c in cs}",
     f"{UNIVERSE}::test_moving_a_company_between_cohorts_fails"),

    ("the breaker selector stops preferring unseen shapes",
     SRC / "validation/manifest.py",
     "        pick = min(matches, key=lambda c: (\n"
     "            (c.sector, c.country) in seen_pairs,\n"
     "            c.sector in seen_sectors,\n"
     "            c.company_id))",
     "        pick = min(matches, key=lambda c: c.company_id)",
     f"{UNIVERSE}::test_the_breaker_ten_does_not_spend_two_slots_on_one_"
     f"shape"),

    ("a holdout company can reach the breaker wave",
     SRC / "validation/manifest.py",
     '    pool = sorted(manifest.cohort("DEVELOPMENT"), '
     "key=lambda c: c.company_id)",
     "    pool = sorted(manifest.companies, key=lambda c: c.company_id)",
     f"{UNIVERSE}::test_no_holdout_company_can_reach_the_breaker_wave"),

    ("runtime data can mutate a manifest record",
     SRC / "validation/manifest.py",
     "@dataclass(frozen=True)\nclass Company:",
     "@dataclass\nclass Company:",
     f"{UNIVERSE}::test_analysed_web_content_cannot_move_a_company_"
     f"between_cohorts"),

    ("a manifest row may encode an expected answer",
     SRC / "validation/manifest.py",
     "        if low in FORBIDDEN_FIELDS or any(low.startswith(p)",
     "        if False or any(low.startswith('__never__')",
     f"{UNIVERSE}::test_a_row_carrying_an_expected_answer_is_refused"),

    ("the dossier drops the manifest version from its identity",
     SRC / "demo_dossier/dossier.py",
     '            "manifest_version": self.manifest_version,',
     "",
     f"{UNIVERSE}::test_a_dossier_records_the_exact_manifest_version_"
     f"it_used"),

    ("the real analysis path stops stamping the cohort",
     SRC / "webapp/app.py",
     "            cohort, manifest_version = self._manifest_placement(key)",
     '            cohort, manifest_version = "", ""',
     f"{UNIVERSE}::test_the_real_analysis_path_stamps_the_cohort_onto_"
     f"the_dossier"),

    ("the depth scan for forbidden names is disabled entirely",
     SRC / "demo_dossier/contracts.py",
     '        _forbidden_scan(payload, _MARKET_FORBIDDEN)',
     '        pass  # depth scan disabled',
     f"{JOIN}::test_a_tenant_id_hidden_inside_a_list_is_still_refused"),
]


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: pathlib.Path, text: str) -> None:
    """Write and force a NEWER mtime.

    Without the bump, a same-length edit restored inside one second can leave
    CPython importing the cached bytecode of the mutated file. The next proof
    then measures source that is no longer on disk, and passes.
    """
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
    print(f"\n{'=' * 78}\nV5 DOSSIER BREAK PROOFS — {caught}/{len(results)} "
          f"CAUGHT\n{'=' * 78}")
    for status, name, node, tail in results:
        print(f"{status:<{width}}  {name}")
        if status != "CAUGHT":
            print(f"{'':<{width}}  ↳ {node}\n{'':<{width}}    {tail}")
    print()
    return 0 if caught == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
