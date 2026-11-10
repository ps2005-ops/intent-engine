"""Break proofs for the Living Decision Record.

The three collapses this record exists to prevent are all INVISIBLE on screen:
a recommendation rendered as a decision, a decision's history quietly growing
into a heartbeat, and decision quality inferred from a lucky outcome. Nothing
about any of those looks wrong in a UI, which is why each one gets a mutation.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

LDR = ROOT / "src/intent_engine/executive/living_decision.py"
APP = ROOT / "src/intent_engine/webapp/app.py"
T = "tests/test_living_decision.py"

PROOFS = [
    ("A. a recommendation may execute without a human",
     LDR,
     "    RECOMMENDATION_READY: (HUMAN_DECIDED, EVIDENCE_GATHERING, ABANDONED),",
     "    RECOMMENDATION_READY: (HUMAN_DECIDED, EVIDENCE_GATHERING, ABANDONED,\n"
     "                           EXECUTING),",
     f"{T}::test_a_recommendation_cannot_jump_to_executing"),

    ("B. the transition table stops being consulted",
     LDR,
     "        if not can_transition(record.status, status):",
     "        if False:",
     f"{T}::test_a_recommendation_cannot_jump_to_executing"),

    ("C. a decided record no longer has to name the human",
     LDR,
     "        if self.status not in NOT_YET_DECIDED and \\\n"
     "                self.status not in (ABANDONED,) and not self.decided_by:",
     "        if False:",
     f"{T}::test_a_decided_record_must_name_the_human_who_chose"),

    ("D. an identical re-derivation appends a revision",
     LDR,
     "    if candidate.content_digest() == record.content_digest():",
     "    if False:",
     f"{T}::test_a_revision_that_changes_nothing_is_refused"),

    ("E. a lucky outcome makes the episode learnable",
     LDR,
     "        return self.decision_quality in (GOOD, WEAK)",
     "        return self.outcome_quality in (GOOD, WEAK)",
     f"{T}::test_an_unassessed_decision_is_not_learnable"),

    ("F. an exogenous shock stops disqualifying the lesson",
     LDR,
     "        if self.exogenous_shock:\n            return False",
     "        if False:\n            return False",
     f"{T}::test_an_exogenous_shock_makes_the_episode_unlearnable"),

    ("G. an unmeasurable outcome becomes learnable",
     LDR,
     "        if self.measurement_quality in (UNMEASURABLE, UNKNOWN):\n"
     "            return False",
     "        if False:\n            return False",
     f"{T}::test_an_unmeasurable_outcome_is_not_learnable"),

    ("H. the decision store stops partitioning by tenant",
     LDR,
     "        digest = hashlib.sha256(\n"
     "            scope_cache_key(got).encode(\"utf-8\")).hexdigest()\n"
     "        return self.root / f\"{digest}.jsonl\"",
     "        return self.root / \"all.jsonl\"",
     f"{T}::test_two_tenants_never_see_each_others_decisions"),

    ("I. a scopeless reader is shown an empty decision list",
     APP,
     '            payload = {"contract": "living_decisions_view.v1", "scoped": False,\n'
     '                       "state": "DECISIONS_UNAVAILABLE",',
     '            payload = {"contract": "living_decisions_view.v1", "scoped": False,\n'
     '                       "state": "NO_OPEN_DECISIONS",',
     f"{T}::test_a_scopeless_reader_is_told_unavailable_not_shown_an_empty_list"),

    ("J. the surface stops distinguishing a recommendation from a decision",
     LDR,
     "        return self.status in NOT_YET_DECIDED",
     "        return False",
     f"{T}::test_the_rendered_page_says_a_recommendation_is_not_a_decision"),

    ("K. what_changed narrates instead of comparing stored rows",
     LDR,
     "        changed = {k: (before.get(k), after.get(k)) for k in after\n"
     "                   if k not in (\"revision\", \"updated_at\", \"runtime_sha\")\n"
     "                   and before.get(k) != after.get(k)}",
     "        changed = {k: (before.get(k), after.get(k)) for k in after\n"
     "                   if k not in (\"revision\", \"updated_at\", \"runtime_sha\")}",
     f"{T}::test_what_changed_is_computed_from_stored_rows"),
]


if __name__ == "__main__":
    sys.exit(run_all([Proof(*p) for p in PROOFS],
                     title="E-LDR-001 -- the Living Decision Record"))
