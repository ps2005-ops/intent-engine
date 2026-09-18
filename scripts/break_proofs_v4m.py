"""Break proofs for L-ADV-001: the adversary that may not read a mind.

Proof 1 is the one to read. It removes the evidence requirement on a
counterparty response, which is the single line separating this module from
every competitive-intelligence layer that predicts a price cut because a
competitor exists.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

M = ROOT / "src/intent_engine/market"
T = "tests"
AC = f"{T}/test_market_adversary_case.py"

PROOFS = [
    ("1. a response may be evidenced without evidence",
     M / "adversary_case.py",
     "        if self.standing in EVIDENCED and not self.evidence_ids:\n"
     "            raise UnevidencedResponse(",
     "        if False:\n"
     "            raise UnevidencedResponse(",
     f"{AC}::test_a_response_may_not_exceed_hypothesised_without_evidence"),

    ("2. a rival's existence becomes a prediction",
     M / "adversary_case.py",
     "    raise UnevidencedResponse(\n"
     '        f"{rival} is a competitor of {subject}; that is not evidence '
     'it will "',
     "    return CounterpartyResponse(actor=rival, action=action)\n"
     "    raise UnevidencedResponse(\n"
     '        f"{rival} is a competitor of {subject}; that is not evidence '
     'it will "',
     f"{AC}::test_a_rivals_existence_predicts_nothing"),

    ("3. capability and incentive collapse into one claim",
     M / "adversary_case.py",
     '    CAPABILITY: "they have the means to do this; nothing says they '
     'intend to",',
     '    CAPABILITY: "they have a reason to do this; nothing says they can, '
     'or will",',
     f"{AC}::test_capability_and_incentive_are_not_the_same_claim"),

    ("4. an observed action needs no date",
     M / "adversary_case.py",
     "        if self.standing == OBSERVED_ACTION and not self.observed_at:\n"
     "            raise AdversaryRejected(",
     "        if False:\n"
     "            raise AdversaryRejected(",
     f"{AC}::test_an_observed_action_must_say_when"),

    ("5. a speculative case reads as a grounded one",
     M / "adversary_case.py",
     "        if any(r.evidenced for r in self.responses):\n"
     "            return GROUNDED\n"
     "        return SPECULATIVE",
     "        return GROUNDED",
     f"{AC}::test_a_case_with_no_evidenced_response_is_speculative_and_says_so"),

    ("6. a speculative case may drive a decision",
     M / "adversary_case.py",
     "        return self.standing in (GROUNDED, DEMONSTRATED)",
     "        return True",
     f"{AC}::test_a_case_with_no_evidenced_response_is_speculative_and_says_so"),

    ("7. an observed action stops being distinguishable from a capability",
     M / "adversary_case.py",
     "        if any(r.standing == OBSERVED_ACTION for r in self.responses):\n"
     "            return DEMONSTRATED",
     "        if False:\n"
     "            return DEMONSTRATED",
     f"{AC}::test_an_observed_action_demonstrates_it"),

    ("8. a case may be filed with no early warning",
     M / "adversary_case.py",
     "        if not self.early_warning:\n"
     "            raise AdversaryRejected(",
     "        if False:\n"
     "            raise AdversaryRejected(",
     f"{AC}::test_a_case_needs_an_early_warning"),

    ("9. a risk may be filed with no stopping rule",
     M / "adversary_case.py",
     "        if not self.kill_condition.strip():\n"
     "            raise AdversaryRejected(",
     "        if False:\n"
     "            raise AdversaryRejected(",
     f"{AC}::test_a_case_needs_a_stopping_rule"),

    ("10. the early warning is composed rather than read from the thesis",
     M / "adversary_case.py",
     "        early_warning=falsifiers,",
     '        early_warning=("watch for signs of deterioration",),',
     f"{AC}::test_the_early_warning_comes_from_the_thesis_falsifiers"),

    ("11. a thesis with no falsifier gets one invented for it",
     M / "adversary_case.py",
     "    if not falsifiers:\n"
     "        raise AdversaryRejected(",
     "    if not falsifiers:\n"
     '        falsifiers = ("the mechanism does not hold",)\n'
     "    if False:\n"
     "        raise AdversaryRejected(",
     f"{AC}::test_a_thesis_with_no_falsifier_is_refused_rather_than_filled_in"),

    ("12. the strongest case is ranked by how bad it sounds",
     M / "adversary_case.py",
     "    return max(cases, key=lambda c: (order[c.standing],\n"
     "                                     sum(1 for r in c.responses if r.evidenced),\n"
     "                                     len(c.early_warning)))",
     "    return max(cases, key=lambda c: len(c.failure_path))",
     f"{AC}::test_the_strongest_case_is_the_best_evidenced_not_the_worst_outcome"),
]


if __name__ == "__main__":
    sys.exit(run_all(
        [Proof(*p) for p in PROOFS],
        title=(f"v4m — L-ADV-001, the bounded adversary: {len(PROOFS)} "
               "proofs")))
