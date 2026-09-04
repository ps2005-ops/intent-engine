"""Break proofs for the Deploy-A reliability wave.

Each mutation is the exact shape the defect had in production, not an edit
near it.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all       # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "src/intent_engine/webapp/app.py"

TQ = "tests/test_demo_quota_commit_on_success.py"
TW = "tests/test_pre100_convergence_wave.py"

PROOFS = [
    Proof("R1. a failed run creation charges the visitor again",
          APP,
          "                self._release_demo_quota(session, remote, "
          "_reserved)\n"
          "                return self._error_page(\n"
          "                    503, \"We could not start this analysis",
          "                return self._error_page(\n"
          "                    503, \"We could not start this analysis",
          f"{TQ}::test_every_early_return_after_reservation_releases_it",
          "failure paths hand the reservation back"),

    Proof("R2. the store's exception becomes an unhandled 500 again",
          APP,
          "            except Exception:                               "
          "# noqa: BLE001\n"
          "                # OPENING A RUN CAN FAIL FOR REASONS THAT ARE NOT "
          "THE INPUT.",
          "            except ZeroDivisionError:\n"
          "                # OPENING A RUN CAN FAIL FOR REASONS THAT ARE NOT "
          "THE INPUT.",
          f"{TW}::test_a_store_failure_does_not_become_an_unhandled_500",
          "unhandled 500"),

    Proof("R3. a refused schedule pretends the run started",
          APP,
          "                    started = self._schedule_analysis(session"
          "[\"user_id\"],\n"
          "                                                      run_id)",
          "                    started = True; self._schedule_analysis("
          "session[\"user_id\"], run_id)",
          f"{TW}::test_a_refused_schedule_is_not_reported_as_started",
          "assert"),

    # THE MEMBERSHIP TEST IS THE GUARD. A first version of this proof
    # mutated `hits.remove(stamp)` into a comprehension that drops "all
    # occurrences" -- which removes exactly one element when the timestamp is
    # unique, so the source changed and the behaviour did not. NOT_CAUGHT was
    # the correct verdict. What actually makes the release idempotent is
    # refusing to refund a stamp that is no longer reserved.
    Proof("R4. the release refunds a stamp it no longer holds",
          APP,
          "        if hits and stamp in hits:\n            hits.remove(stamp)",
          "        if hits:\n            hits.pop()",
          f"{TQ}::test_a_double_release_cannot_refund_twice",
          "refunded twice"),

    Proof("R5. a 429 charges the visitor",
          APP,
          "        if len(ip_hits) >= self.config.demo_ip_analyses_per_hour:\n"
          "            self._demo_ip_hits[remote] = ip_hits",
          "        if len(ip_hits) >= self.config.demo_ip_analyses_per_hour:\n"
          "            self._demo_ip_hits[remote] = ip_hits + [now]",
          f"{TQ}::test_a_429_consumes_no_new_quota",
          "charged the visitor"),
]

if __name__ == "__main__":
    raise SystemExit(run_all(PROOFS, title=__doc__.splitlines()[0]))
