"""Break proofs for L-SRC-001: source health as a state.

The attacks here are the ways a dead feed goes unnoticed. The one that
matters most is proof 4: a degraded source must never be allowed to weaken
the claim it fed. Every other guard protects the bookkeeping; that one
protects the distinction the pillar exists for — the engine going blind
versus the economy going quiet.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

S = ROOT / "src/intent_engine/market"
T = "tests"
SH = f"{T}/test_market_source_health.py"

PROOFS = [
    # --- 1. an unrecognised failure is guessed -------------------------
    ("1. an unknown failure message is mapped onto the nearest known state",
     S / "source_health.py",
     "    return UNCLASSIFIED",
     "    return UNAVAILABLE",
     f"{SH}::test_an_unrecognised_failure_is_never_guessed"),

    # --- 2. a bad minute is called an outage ---------------------------
    ("2. the first failure is reported as UNAVAILABLE",
     S / "source_health.py",
     "    if state == UNAVAILABLE and streak < OUTAGE_STREAK:",
     "    if False:",
     f"{SH}::test_one_outage_is_degraded_and_three_is_unavailable"),

    # --- 3. the streak never accumulates -------------------------------
    ("3. every cycle rediscovers the outage instead of counting it",
     S / "source_health.py",
     "    streak = previous_streak + 1",
     "    streak = 1",
     f"{SH}::test_one_outage_is_degraded_and_three_is_unavailable"),

    # --- 4. THE RULE: a dark source weakens the claim ------------------
    ("4. a source outage is allowed to shade the claim's confidence",
     S / "source_health.py",
     '        "confidence": confidence,',
     '        "confidence": (confidence * 0.5 if hit and confidence\n'
     '                       else confidence),',
     f"{SH}::test_a_dark_source_never_weakens_the_claim"),

    # --- 5. reduced visibility reported as unchanged -------------------
    ("5. an impaired source raises no uncertainty",
     S / "source_health.py",
     '        "uncertainty": ("RAISED" if hit else "UNCHANGED"),',
     '        "uncertainty": "UNCHANGED",',
     f"{SH}::test_a_dark_source_never_weakens_the_claim"),

    # --- 6. an impaired state with no evidence -------------------------
    ("6. a source can be marked UNAVAILABLE with no failure recorded",
     S / "source_health.py",
     "        if self.state in IMPAIRED and not self.failure:",
     "        if False:",
     f"{SH}::test_an_impaired_state_must_carry_its_evidence"),

    # --- 7. only failures are logged -----------------------------------
    ("7. successes are dropped, so last_success can never be answered",
     S / "source_health.py",
     "    return [assess(source_family=family, failure=failures.get(family, \"\"),\n"
     "                   as_of=as_of, prior=prior.get(family))\n"
     "            for family in families]",
     "    return [assess(source_family=family, failure=failures[family],\n"
     "                   as_of=as_of, prior=prior.get(family))\n"
     "            for family in families if family in failures]",
     f"{SH}::test_from_collection_records_successes_not_only_failures"),

    # --- 8. last_success is forgotten on failure -----------------------
    ("8. a failure erases the date the source last worked",
     S / "source_health.py",
     "    last_success = prior.last_success if prior else \"\"",
     "    last_success = \"\"",
     f"{SH}::test_last_success_survives_a_failure"),

    # --- 9. a silent substitution --------------------------------------
    ("9. a fallback is taken without being recorded as one",
     S / "source_health.py",
     "    if preferred not in state or not state[preferred].impaired:\n"
     "        return None",
     "    if preferred not in state:\n"
     "        return None",
     f"{SH}::test_a_healthy_preferred_source_produces_no_fallback_record"),

    # --- 10. no source attempted reads as full visibility --------------
    ("10. an empty sweep reports complete observability",
     S / "source_health.py",
     '        return {"contract": CONTRACT, "sources": 0,\n'
     '                "observability": None,',
     '        return {"contract": CONTRACT, "sources": 0,\n'
     '                "observability": 1.0,',
     f"{SH}::test_no_source_attempted_is_unmeasured_not_complete"),

    # --- 11. the state never reaches the ledger ------------------------
    ("11. the cycle computes source health and never persists it",
     S / "steps.py",
     "            for health in healths:\n"
     "                store.record_source_health(health)",
     "            pass",
     f"{SH}::test_the_streak_survives_across_cycles"),

    # --- 12. repeats collapsed, destroying the streak ------------------
    ("12. the store dedupes repeated outages into one row",
     S / "learning_store.py",
     "        self._append(SOURCE_HEALTH, payload)",
     "        if payload.get('source_family') not in "
     "self.latest_source_health():\n"
     "            self._append(SOURCE_HEALTH, payload)",
     f"{SH}::test_the_streak_survives_across_cycles"),
]

# --- NOT_BUILT ------------------------------------------------------------
#
# "a STALE source is detected from its expected cadence" has no guard to
# break. `expected_cadence_days` is carried on the record and nothing computes
# staleness from it yet: the macro adapters do not publish a cadence, so the
# field is populated by callers and read by none. Writing a proof against it
# would be demonstrating the absence of a code path, which is the test that
# cannot fail. Recorded in the node rather than faked here.
NOT_BUILT = 1

if __name__ == "__main__":
    raise SystemExit(run_all(
        [Proof(*p) for p in PROOFS],
        title=(f"v4i — L-SRC-001 source health: {len(PROOFS)} proofs, "
               f"{NOT_BUILT} recorded NOT_BUILT")))
