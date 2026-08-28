"""§40: twelve mutations of the interactive performance and reliability path.

Each one removes a specific guarantee this run exists to establish, and each
must turn its OWN paired test red for its OWN reason. The harness enforces
the five conditions (source changed, green before, red after, red for the
stated reason, shared tree untouched), so "12/12" here is a claim about
load-bearing guards rather than about how many mutations were typed.

THE ANTI-TAUTOLOGY RULE. No proof below mutates a test. Every `path` is a
file under `src/`, and every `target` is a test node that reads it. A proof
that edited its own guard would prove only that assertions can be deleted.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all      # noqa: E402

S = ROOT / "src" / "intent_engine"
CI = S / "company_ingestion"
T = "tests/test_interactive_performance.py"

PROOFS = [
    # --- 1/2/8: independent work is overlapped, once, and bounded --------
    ("p-1. independent retrieval is serialised again",
     CI / "service.py",
     "        if len(pending) < 2:\n            return {}",
     "        if True:\n            return {}",
     f"{T}::test_independent_sources_are_fetched_concurrently",
     "concurrent waves should cost about"),

    ("p-2. concurrency is unbounded per host (a burst at one publisher)",
     CI / "service.py",
     "    _FETCH_PER_HOST = 2",
     "    _FETCH_PER_HOST = 64",
     f"{T}::test_concurrency_is_bounded_per_host",
     "concurrent requests to one host"),

    # The first draft mutated `elif candidate_id in prefetched:` and was
    # NOT_CAUGHT — correctly. That branch falling through re-fetches the same
    # URL serially and admits the same document, so the mutation is slower
    # and not wrong. The guarantee that CAN break under concurrency is the
    # dead-host breaker, which now has to fire before dispatch.
    # Two earlier drafts were NOT_CAUGHT, and both were findings rather than
    # failures. Mutating `elif candidate_id in prefetched:` only makes the
    # run slower — the same document is re-fetched serially and admitted.
    # Mutating the pre-pass breaker filter is masked by the second breaker
    # check inside the worker. What is singly load-bearing is THAT check: it
    # is the only thing that stops candidates already queued behind a dying
    # host from each paying their own timeout.
    ("p-3. a host that dies mid-pass keeps being dialled",
     CI / "service.py",
     """            with lock:
                if live_failures.get(host, 0) >= self._DEAD_HOST_AFTER:
                    return                    # died while we were queued""",
     "            pass",
     f"{T}::test_a_host_that_dies_mid_pass_stops_being_dialled",
     "the breaker did not trip inside the pass"),

    ("p-4. the global deadline is ignored by the sequential fallback",
     CI / "service.py",
     "            elif deadline is not None and not deadline.may_start():",
     "            elif False:",
     f"{T}::test_deadline_bounds_acquisition_and_records_the_gap",
     "still spent"),

    # Retargeted: `record_gap` is called at BOTH the dispatch site and the
    # sequential site for the same URL, and `record_gap` de-duplicates, so
    # removing one of them is invisible — NOT_CAUGHT, and correctly so. What
    # is singly-sited, and is the thing a reader actually loses, is the
    # per-source FAILURE record saying this source was never requested.
    ("p-5. an out-of-budget source is dropped silently instead of recorded",
     CI / "service.py",
     '''                failed.append(self._fail(
                    run_id, domain, candidate_id, "deadline_exceeded",
                    "not requested: the interactive time budget for this "
                    "analysis was spent before this source was reached",
                    True))
                continue''',
     "                continue",
     f"{T}::test_deadline_bounds_acquisition_and_records_the_gap",
     "deadline_exceeded"),

    ("p-6. a class share is applied per call, so N calls spend N shares",
     CI / "deadline.py",
     "        share = (CLASS_SHARE.get(source_class, 1.0) * self.total_s\n"
     "                 - self._spent.get(source_class, 0.0))",
     "        share = CLASS_SHARE.get(source_class, 1.0) * self.total_s",
     f"{T}::test_budget_is_shared_not_per_call",
     "assert"),

    ("p-7. a call is started that cannot possibly finish",
     CI / "deadline.py",
     "        if left < MIN_USEFUL_FETCH_S:\n            return 0.0",
     "        if False:\n            return 0.0",
     f"{T}::test_no_call_is_started_that_cannot_finish",
     "assert"),

    ("p-8. acquisition may spend the budget composition needs",
     CI / "deadline.py",
     "        view = Deadline(total_s=max(0.0, self.total_s - float(seconds)),",
     "        view = Deadline(total_s=self.total_s,",
     f"{T}::test_reserved_view_shares_one_clock",
     "assert"),

    ("p-9. the reserved view drifts onto its own clock",
     CI / "deadline.py",
     "        view.gaps = self.gaps               # shared by reference, on purpose",
     "        view.gaps = list(self.gaps)",
     f"{T}::test_reserved_view_shares_one_clock",
     "visible to the run that owns the budget"),

    ("p-10. batch runs are forced onto the interactive budget",
     CI / "deadline.py",
     "        return cls(total_s=float('inf'), tier=TIER_2)".replace("'", '"'),
     "        return cls(total_s=TIER1_HARD_S, tier=TIER_2)",
     f"{T}::test_batch_callers_are_not_held_to_an_interactive_budget",
     "assert"),

    # --- 18: discovery is inside the budget too --------------------------
    ("p-13. discovery enrichment ignores the budget entirely",
     CI / "service.py",
     "            optional_ok = (deadline is None\n"
     "                           or deadline.may_start(HIGH_VALUE_OPTIONAL))",
     "            optional_ok = True",
     f"{T}::test_discovery_optional_branches_are_bounded",
     "skipping enrichment without recording it"),

    ("p-14. a budget with time left silently deletes enrichment discovery",
     CI / "service.py",
     "            optional_ok = (deadline is None\n"
     "                           or deadline.may_start(HIGH_VALUE_OPTIONAL))",
     "            optional_ok = False",
     f"{T}::test_discovery_budget_does_not_bind_when_there_is_time",
     "changed the candidate set"),

    # --- 3/45: speed was not bought with evidence ------------------------
    ("p-11. the phrase prefilter skips a scan that could have matched",
     S / "strategic_intelligence" / "observations.py",
     "    return any(probe not in folded for probe in probes)",
     "    return True",
     f"{T}::test_phrase_prefilter_changes_no_answer",
     "assert"),

    ("p-12. the prefilter tests a word the pattern does not require",
     S / "strategic_intelligence" / "observations.py",
     "    words = [w.casefold() for w in phrase.split() if w.isascii()]",
     '    words = [w.casefold() for w in phrase.split() if w.isascii()] '
     '+ ["zzqq"]',
     f"{T}::test_prefilter_probe_is_a_necessary_condition",
     "assert"),
]


def main() -> int:
    return run_all([Proof(*row) for row in PROOFS],
                   title="Interactive performance break proofs (§40)")


if __name__ == "__main__":
    sys.exit(main())
