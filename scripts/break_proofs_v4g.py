#!/usr/bin/env python3
"""Break proofs for historical replay and its vintage wall.

D-REP-002. The failure this guards is the most seductive one in the whole
program: a replay that quietly reads publication time instead of observation
time produces episodes, resolves them, and reports a healthy hit rate — while
reasoning from figures nobody had seen. On the live corpus that shortcut would
admit 1572 rows at 2026-01-01.

    python3 scripts/break_proofs_v4g.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
S = ROOT / "src" / "intent_engine" / "market"

TR = S / "thesis_replay.py"
VG = S / "vintage.py"

R = "tests/test_market_thesis_replay.py"

PROOFS = [
    # --- the wall reads observation time ----------------------------------
    ("v4g-1. the vintage admits on occurrence time instead of observation",
     VG,
     "        seen = observation_time(row)\n        if not seen:\n            undated.append(row)",
     "        seen = occurrence_time(row)\n        if not seen:\n            undated.append(row)",
     f"{R}::test_a_figure_published_before_t0_but_seen_after_it_is_withheld",
     "assert"),

    ("v4g-2. a row nobody had seen passes the read-through check",
     VG,
     "        if seen > self.as_of:",
     "        if False:",
     f"{R}::test_a_figure_published_before_t0_but_seen_after_it_is_withheld",
     "DID NOT RAISE"),

    ("v4g-3. an undated row is admitted rather than refused",
     VG,
     "        if not seen:\n            raise VintageViolation(",
     "        if False:\n            raise VintageViolation(",
     f"{R}::test_an_undated_row_cannot_be_placed_against_a_wall",
     "DID NOT RAISE"),

    ("v4g-4. the replay may advance its own wall into the future",
     VG,
     "        if target > self.as_of:",
     "        if False:",
     f"{R}::test_a_replay_cannot_advance_its_own_wall",
     "DID NOT RAISE"),

    ("v4g-5. the leak surface is not counted",
     VG,
     "        return sum(1 for r in self.withheld_not_yet_known\n                   if occurrence_time(r) and occurrence_time(r) <= self.as_of)",
     "        return 0",
     f"{R}::test_the_leak_surface_counts_what_a_publication_filter_would_admit",
     "assert"),

    # --- selection cannot read the answer ----------------------------------
    ("v4g-6. an episode that cannot resolve in the window is kept anyway",
     TR,
     "        if t1 > str(ending)[:10]:\n            # The horizon runs past the corpus.",
     "        if False:\n            # The horizon runs past the corpus.",
     f"{R}::test_an_episode_whose_horizon_runs_past_the_corpus_is_excluded",
     "assert"),

    ("v4g-7. an episode resolving before it is formed is accepted",
     TR,
     "        if self.t1 <= self.t0:",
     "        if False:",
     f"{R}::test_an_episode_that_resolves_before_it_is_formed_is_refused",
     "DID NOT RAISE"),

    ("v4g-8. an episode need not state how it was selected",
     TR,
     "        if not self.selection_rule.strip():",
     "        if False:",
     f"{R}::test_an_episode_with_no_stated_rule_is_refused",
     "DID NOT RAISE"),

    # --- outcome and mechanism stay apart -----------------------------------
    ("v4g-9. a right outcome with an untested mechanism counts as a win",
     TR,
     "    if outcome == RIGHT:\n        if mechanism == RIGHT:\n            return OUTCOME_RIGHT_MECHANISM_RIGHT",
     "    if outcome == RIGHT:\n        if mechanism != WRONG:\n            return OUTCOME_RIGHT_MECHANISM_RIGHT",
     f"{R}::test_a_right_outcome_with_an_untested_mechanism_is_unresolved",
     "assert"),

    ("v4g-10. a wrong outcome with a real mechanism is filed as simply wrong",
     TR,
     "    if mechanism == RIGHT:\n        # The route ran and the prediction still missed",
     "    if False:\n        # The route ran and the prediction still missed",
     f"{R}::test_a_wrong_outcome_with_a_real_mechanism_is_kept_apart",
     "assert"),

    ("v4g-11. an untested mechanism need not say why",
     TR,
     "        if self.mechanism == UNTESTED and not self.mechanism_reason.strip():",
     "        if False:",
     f"{R}::test_an_untested_mechanism_must_say_why",
     "DID NOT RAISE"),

    ("v4g-12. an expectation may be locked with no falsifier",
     TR,
     "        if not self.falsifier.strip():",
     "        if False:",
     f"{R}::test_an_expectation_without_a_falsifier_is_refused",
     "DID NOT RAISE"),

    ("v4g-13. an expectation need not name what would show the route ran",
     TR,
     "        if not self.expected_observable.strip():",
     "        if False:",
     f"{R}::test_an_expectation_must_name_what_would_show_the_mechanism_ran",
     "DID NOT RAISE"),
]


if __name__ == "__main__":
    sys.exit(run_all([Proof(*p) for p in PROOFS], title="V4g"))
