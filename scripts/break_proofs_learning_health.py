"""Break proofs for market learning health and observation binding.

A test that passes proves nothing about whether it would CATCH the defect it
names. Each proof below mutates the source so that a specific self-flattering
behaviour becomes true, runs the guard that is supposed to notice, and demands
that it fails. Then it restores and demands green again.

RESTORE BUMPS mtime DELIBERATELY. A mutation of identical length restored in
place leaves CPython holding cached bytecode whose source hash and size both
still match, so the interpreter keeps running the mutated code and the proof
reports a false pass. Writing the original back is not enough; the file's
mtime has to move.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = "/Users/prathamsharma/intent-engine/.venv/bin/python"

HEALTH = ROOT / "src/intent_engine/market/learning_health.py"
BINDING = ROOT / "src/intent_engine/market/observation_binding.py"
TESTS = "tests/test_market_learning_health.py"

# (label, file, find, replace, test that must FAIL)
PROOFS = [
    ("1. duplicate evidence counts as new knowledge",
     HEALTH,
     "        return (self.beliefs_strengthened + self.beliefs_weakened\n"
     "                + self.beliefs_retired)",
     "        return (self.beliefs_strengthened + self.beliefs_weakened\n"
     "                + self.beliefs_retired + self.duplicate_evidence)",
     "test_duplicate_evidence_is_not_counted_as_new_knowledge"),

    ("2. belief count rises and health reports acceleration",
     HEALTH,
     "    if len(usable) < MIN_CYCLES_FOR_VELOCITY:\n"
     "        return {\"status\": NO_HISTORY,",
     "    if False:\n"
     "        return {\"status\": NO_HISTORY,",
     "test_classify_refuses_a_verdict_without_enough_cycles"),

    ("3. zero new evidence is reported as degradation",
     HEALTH,
     "    if not any(o.accepted_evidence for o in recent):\n"
     "        return {\"status\": NO_NEW_EVIDENCE,",
     "    if False:\n"
     "        return {\"status\": NO_NEW_EVIDENCE,",
     "test_no_new_evidence_is_not_reported_as_degradation"),

    ("4. untested beliefs count as survived",
     HEALTH,
     "            informative = [r for r in results\n"
     "                           if r.get(\"outcome\") in (\"CONFIRMED\",\n"
     "                                                   \"PARTIALLY_CONFIRMED\",\n"
     "                                                   \"CONTRADICTED\")]\n"
     "            if not informative:\n"
     "                continue\n"
     "            tested += 1",
     "            informative = [r for r in results\n"
     "                           if r.get(\"outcome\") in (\"CONFIRMED\",\n"
     "                                                   \"PARTIALLY_CONFIRMED\",\n"
     "                                                   \"CONTRADICTED\")]\n"
     "            tested += 1\n"
     "            if not informative:\n"
     "                supported += 1\n"
     "                continue",
     "test_untested_belief_does_not_count_as_survived"),

    ("5. stale beliefs are never surfaced",
     HEALTH,
     "        \"beliefs_without_recent_support\": sum(\n"
     "            1 for b in belief_rows if not b.get(\"last_validated\")),",
     "        \"beliefs_without_recent_support\": 0,",
     "test_stale_and_never_validated_beliefs_are_reported"),

    ("6. a reversal is recorded as support",
     HEALTH,
     "            else:\n"
     "                # Both directions observed: the belief was supported and then",
     "            elif False:\n"
     "                # Both directions observed: the belief was supported and then",
     "test_belief_supported_then_contradicted_is_a_reversal"),

    ("7. expectation backlog grows without an alert",
     HEALTH,
     "    if open_now > 0 and not tested:\n"
     "        fire(EXPECTATION_BACKLOG_GROWING,",
     "    if False:\n"
     "        fire(EXPECTATION_BACKLOG_GROWING,",
     "test_expectation_backlog_alert_fires_when_nothing_ever_resolves"),

    ("8. one broken stage is hidden by aggregate totals",
     HEALTH,
     "            if _is_number(before) and _is_number(after) \\\n"
     "                    and before > 0 and after == 0:",
     "            if False:",
     "test_pipeline_stage_regression_is_visible_despite_healthy_totals"),

    ("9. watchlist coverage hides a global collapse",
     HEALTH,
     "        \"off_watchlist_companies_observed\": len(observed - watch),",
     "        \"off_watchlist_companies_observed\": len(observed),",
     "test_watchlist_gain_cannot_hide_global_collapse"),

    ("10. rows rise, nothing is validated, status still says healthy",
     HEALTH,
     "    validated = seven[\"series\"].get(\"validated_knowledge\") or {}",
     "    validated = seven[\"series\"].get(\"accepted_evidence\") or {}",
     "test_accumulating_without_validating_is_a_plateau_not_health"),

    ("11. a belief is tested by the evidence that proposed it",
     BINDING,
     "            if item.evidence_id in basis:",
     "            if False:",
     "test_the_evidence_that_proposed_a_belief_never_tests_it"),

    ("12. an unfalsifiable family is bound anyway",
     BINDING,
     "        if family not in FALSIFIABLE:",
     "        if False:",
     "test_unfalsifiable_family_is_refused_with_a_reason"),

    ("13. only confirming evidence is admitted as a test",
     BINDING,
     "            if item.evidence_type not in relevant_types:",
     "            if family not in BF.routes_for(item):",
     "test_binding_produces_a_contradiction_when_evidence_points_the_other_way"),

    ("14. the kindest observation is chosen instead of the earliest",
     BINDING,
     "        by_subject[subject].sort(key=lambda e: (e.observed_at, e.evidence_id))",
     "        by_subject[subject].sort(key=lambda e: (e.observed_at, e.evidence_id),\n"
     "                                 reverse=True)",
     "test_the_earliest_qualifying_observation_wins_not_the_kindest"),

    ("15. evidence predating preregistration is scored",
     BINDING,
     "            if item.observed_at[:10] < exp.preregistered_at[:10]:",
     "            if False:",
     "test_evidence_predating_preregistration_never_binds"),
]


def run_test(name: str) -> bool:
    """True when the named test PASSES."""
    proc = subprocess.run(
        [PY, "-m", "pytest", f"{TESTS}::{name}", "-q", "--no-header"],
        cwd=ROOT, capture_output=True, text=True,
        env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"})
    return proc.returncode == 0


def main() -> int:
    failures = []
    for label, path, find, replace, test in PROOFS:
        original = path.read_text(encoding="utf-8")
        if find not in original:
            print(f"  SKIP  {label}\n        anchor not found in {path.name}")
            failures.append(label)
            continue

        # green before
        if not run_test(test):
            print(f"  FAIL  {label}\n        {test} was already red")
            failures.append(label)
            continue

        path.write_text(original.replace(find, replace, 1), encoding="utf-8")
        try:
            caught = not run_test(test)
        finally:
            path.write_text(original, encoding="utf-8")
            # See the module docstring: same-length restores need a new mtime
            # or CPython keeps executing the mutated bytecode.
            now = time.time() + 1
            import os
            os.utime(path, (now, now))

        if not run_test(test):
            print(f"  FAIL  {label}\n        did not go green after restore")
            failures.append(label)
        elif caught:
            print(f"  ok    {label}")
        else:
            print(f"  FAIL  {label}\n        mutation was NOT caught by {test}")
            failures.append(label)

    print()
    print(f"{len(PROOFS) - len(failures)}/{len(PROOFS)} break proofs held")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
