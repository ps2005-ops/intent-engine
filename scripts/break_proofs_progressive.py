"""§48: mutations of the CORE/DEEP split and the concurrency defect it rests on.

Each removes one guarantee the progressive architecture is built on, and each
must turn its OWN paired test red for its OWN stated reason. No proof mutates
a test: every `path` is under `src/`.

WHAT IS AND IS NOT PROVEN HERE. §48 lists twelve mutations. Nine of them
correspond to behaviour this run actually built. Three do not — an evidence
snapshot/prewarm layer (§32), a separate worker process (§28) and a job-state
machine with DEEP_ANALYSING as a persisted state (§34) were not built, so
there is nothing to mutate and a proof against them would be theatre. They
are named in the report as not-built rather than counted as held.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all      # noqa: E402

S = ROOT / "src" / "intent_engine"
CI = S / "company_ingestion"
T = "tests/test_progressive_analysis.py"

PROOFS = [
    ("g-1. the core waits for the deep reading",
     CI / "service.py",
     "        if not deep:\n            payload[\"deep_status\"] = DEEP_PENDING",
     "        if False:\n            payload[\"deep_status\"] = DEEP_PENDING",
     f"{T}::test_the_core_is_readable_before_the_model_has_run",
     "the reader waited for the model"),

    ("g-2. the worker composes deep first, so nothing is publishable early",
     S / "webapp" / "app.py",
     # Anchor follows the call site: a `trace=` argument was added after
     # this proof was written, and an ANCHOR_MISSING proof is an UNVERIFIED
     # guard, not a passing one.
     "                core = self._compose(run_id, deep=False, trace=trace)",
     "                core = self._compose(run_id, deep=True, trace=trace)",
     f"{T}::test_the_core_is_readable_before_the_model_has_run",
     "the reader waited for the model"),

    # The first draft mutated `self._results[run_id] = X` to
    # `... = None or X`, which evaluates to X — a no-op, and exactly the trap
    # the harness was built for. What actually carries the guarantee is that
    # the failure path returns the SAME result rather than an empty one.
    ("g-3. a deep failure destroys the core the customer is reading",
     CI / "service.py",
     "            report[\"deep_seconds\"] = round(_time.monotonic() - started, 2)\n"
     "            return result\n",
     "            report[\"deep_seconds\"] = round(_time.monotonic() - started, 2)\n"
     "            return {}\n",
     f"{T}::test_a_failed_deep_pass_leaves_the_core_readable",
     "took the customer's result with it"),

    # Retargeted: mutating the service-level handler was masked by the
    # worker's own try/except — two guards, and only one of them is reachable
    # for this test. The worker's is the load-bearing one, because it is what
    # keeps a model failure out of the run's FAILED transition.
    ("g-4. a failed model marks the whole analysis FAILED",
     S / "webapp" / "app.py",
     "            try:\n                self._results[run_id] = self.ci.enrich_deep(",
     "            if True:\n                self._results[run_id] = self.ci.enrich_deep(",
     f"{T}::test_the_run_is_not_marked_failed_because_the_model_was",
     "assert"),

    ("g-5. the core tells the reader the model is unconfigured",
     CI / "service.py",
     "            payload[\"result_state_detail\"] = \\\n"
     "                ResultState.EXPLANATION[ResultState.DEEP_PENDING]",
     "            payload[\"result_state_detail\"] = (\n"
     "                \"No reasoning backend is configured.\")",
     f"{T}::test_the_core_carries_evidence_and_provenance_not_scaffolds",
     "fix the wrong thing"),

    ("g-6. the core asserts a strategic reading it has not made",
     CI / "service.py",
     "        payload[\"strategic_analysis\"] = None\n"
     "        # CORE STOPS HERE",
     "        payload[\"strategic_analysis\"] = {\"decisions\": []}\n"
     "        # CORE STOPS HERE",
     f"{T}::test_the_core_carries_evidence_and_provenance_not_scaffolds",
     "assert"),

    ("g-7. deep rewrites a material decision field silently",
     CI / "service.py",
     "        report[\"deep_changes\"] = [\n"
     "            {\"field\": k, \"core\": before[k], \"deep\": after[k]}\n"
     "            for k in DEEP_MATERIAL_FIELDS if before[k] != after[k]]",
     "        report[\"deep_changes\"] = []",
     f"{T}::test_a_material_deep_change_is_recorded_not_silent",
     "assert"),

    ("g-8. deep replaces the analysis instead of merging into it",
     CI / "service.py",
     "        for key in (\"strategic_analysis\", \"result_state\",",
     "        report.clear()\n        for key in (\"strategic_analysis\", \"result_state\",",
     f"{T}::test_deep_merges_into_the_same_analysis",
     "dropped the core evidence"),

    ("g-9. enrichment re-runs the model on an already-deep analysis",
     CI / "service.py",
     "        if report.get(\"deep_status\") not in (DEEP_PENDING, None):\n"
     "            return result                     # already enriched, or refused",
     "        if False:\n            return result",
     f"{T}::test_enrichment_is_idempotent",
     "enrichment ran twice"),

    ("g-10. the retry ledger loses charges under concurrent retrieval",
     CI / "transient.py",
     "    def charge(self, host: str, seconds: float) -> None:\n"
     "        key = host or \"\"\n"
     "        with self._lock:",
     "    def charge(self, host: str, seconds: float) -> None:\n"
     "        key = host or \"\"\n"
     "        if True:",
     f"{T}::test_the_retry_ledger_guards_its_counters",
     "without the lock"),

    # g-11/g-12 were found by reading the CORE payload against the layer that
    # renders it, not by a failing test — both shipped green.
    ("g-11. the core ships the pattern library as this company's finding",
     S / "founder_brief" / "build.py",
     "    if str(report.get(\"reasoning_provenance\") or \"\") "
     "== _SCAFFOLD_PROVENANCE:\n        return []",
     "    if False:\n        return []",
     f"{T}::test_a_core_never_ships_library_scaffolds_as_findings",
     "let the pattern library reach the page"),

    ("g-12. the retry budget is read as two numbers from two moments",
     CI / "transient.py",
     "        with self._lock:\n            return max(0.0, min(\n"
     "                self.policy.total_retry_budget_s - self.spent(host),\n"
     "                self.policy.run_retry_budget_s - self.spent_total()))",
     "        if True:\n            return max(0.0, min(\n"
     "                self.policy.total_retry_budget_s - self.spent(host),\n"
     "                self.policy.run_retry_budget_s - self.spent_total()))",
     f"{T}::test_remaining_is_read_atomically",
     "a budget the ledger never held"),
]


def main() -> int:
    return run_all([Proof(*row) for row in PROOFS],
                   title="Progressive analysis break proofs (§48)")


if __name__ == "__main__":
    sys.exit(main())
