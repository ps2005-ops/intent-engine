"""Break proofs for the DecisionImpact comparability wall.

Proof A is the one to read. It treats an unrecorded evidence window as a
matching one, which is how "the engine changed its mind" quietly becomes "the
engine saw three more weeks of filings" — and the substitution cannot be
detected after the fact, which is why the wall was built while comparable
pairs are still zero.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

E = ROOT / "src/intent_engine/external_intel"
T = "tests"
CP = f"{T}/test_founder_impact_comparability.py"

PROOFS = [
    ("A. an unrecorded evidence window counts as a matching one",
     E / "decision_impact.py",
     "        if not self.before_known_at or not self.after_known_at:\n"
     "            return UNKNOWN_WINDOW",
     "        if False:\n"
     "            return UNKNOWN_WINDOW",
     f"{CP}::test_unrecorded_windows_are_not_matching_windows"),

    ("B. a wider window becomes attributable to reasoning",
     E / "decision_impact.py",
     "        if self.before_known_at == self.after_known_at:\n"
     "            return SAME_WINDOW\n"
     "        return WIDER_WINDOW",
     "        return SAME_WINDOW",
     f"{CP}::test_a_wider_window_is_not_attributable_to_reasoning"),

    ("C. anything at all becomes attributable",
     E / "decision_impact.py",
     "        return self.comparability == SAME_WINDOW",
     "        return True",
     f"{CP}::test_a_wider_window_is_not_attributable_to_reasoning"),

    ("D. a large change is attributable regardless of the window",
     E / "decision_impact.py",
     "    @property\n"
     "    def attributable(self) -> bool:\n"
     '        """Whether this row may enter a rate about the engine\'s value."""\n'
     "        return self.comparability == SAME_WINDOW",
     "    @property\n"
     "    def attributable(self) -> bool:\n"
     '        """Whether this row may enter a rate about the engine\'s value."""\n'
     "        return (self.comparability == SAME_WINDOW\n"
     "                or self.materiality == DECISION_CHANGING)",
     f"{CP}::test_attribution_is_independent_of_how_large_the_change_was"),

    ("E. the windows stop reaching the persisted row",
     E / "decision_impact.py",
     '            "before_known_at": self.before_known_at,',
     '            "before_known_at": "",',
     f"{CP}::test_the_windows_and_lineage_reach_the_persisted_row"),

    ("F. adding a window changes the comparison's identity",
     E / "decision_impact.py",
     '        raw = "|".join((self.analysis_id, self.company_id,\n'
     "                        self.dossier_revision, self.belief_id))",
     '        raw = "|".join((self.analysis_id, self.company_id,\n'
     "                        self.dossier_revision, self.belief_id,\n"
     "                        self.before_known_at))",
     f"{CP}::test_the_windows_do_not_change_the_impact_identity"),
]


if __name__ == "__main__":
    sys.exit(run_all(
        [Proof(*p) for p in PROOFS],
        title=(f"comparability — the evidence window behind an impact: "
               f"{len(PROOFS)} proofs")))
