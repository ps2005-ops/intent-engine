#!/usr/bin/env python3
"""Break proofs for the paper-validation program.

Each proof re-creates a failure a backtest or a forward record can suffer,
by mutating the PRODUCER, never the guard that should catch it (the
anti-tautology rule, `econ.breakproof`). A proof counts only if the source
hash changes, the named test was green before, turns RED after, and the
failure text matches what the proof says it is about
(`break_proof_harness`).

Run it from INSIDE a pristine export of the tree under test, so the proof
measures committed bytes rather than a working copy:

    tree=$(git write-tree)        # or a commit
    mkdir -p "$EXPORT" && git archive "$tree" | tar -x -C "$EXPORT"
    cd "$EXPORT" && GUARD_PYTHON=/Users/prathamsharma/intent-engine/.venv/bin/python \\
        python3 scripts/break_proofs_paper_validation.py
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from break_proof_harness import Proof, run_all           # noqa: E402

ROOT = HERE.parent
PKG = ROOT / "src/intent_engine/paper_validation"
LEDGER_T = "tests/test_paper_validation_ledger.py"
REPLAY_T = "tests/test_paper_validation_replay.py"
CONTRACT_T = "tests/test_paper_validation_contracts.py"
FORWARD_T = "tests/test_paper_validation_forward.py"

PROOFS = [
    Proof(label="1. a price feature reads tomorrow's close",
          path=PKG / "features.py",
          find='    f = {"r21": _ret(c, t - 21, t), "r63": _ret(c, t - 63, t),',
          replace='    f = {"r21": _ret(c, t - 20, min(t + 1, len(c) - 1)), '
                  '"r63": _ret(c, t - 63, t),',
          target=f"{REPLAY_T}::TestTruncation::"
                 "test_price_features_do_not_change_when_the_future_is_deleted",
          expect_failure_contains="truncation_invariant"),
    Proof(label="2. the resolver stops waiting for the exit session",
          path=PKG / "forward.py",
          find="        if exit_ >= today:",
          replace="        if False:",
          target=f"{FORWARD_T}::TestResolver::"
                 "test_nothing_resolves_before_the_exit_session_is_over",
          expect_failure_contains="has not completed"),
    Proof(label="3. climatology counts outcomes not yet known",
          path=PKG / "observations.py",
          find="            j = bisect.bisect_right(exits, o.decision_date)",
          replace="            j = bisect.bisect_right(exits, o.exit_date)",
          target=f"{REPLAY_T}::TestReplay::"
                 "test_climatology_uses_only_outcomes_known_at_the_decision",
          expect_failure_contains="p_clim"),
    Proof(label="4. training history is not purged of unresolved labels",
          path=PKG / "replay.py",
          find="        return self._rows[:bisect.bisect_right(self._exits, d)]",
          replace="        return self._rows[:]",
          target=f"{REPLAY_T}::TestReplay::test_logit_training_is_purged",
          expect_failure_contains="exit_date <= d"),
    Proof(label="5. macro reads a revision published after the decision",
          path=PKG / "macro.py",
          find="    cell = panel.latest_vintage_of(sid, period, as_of)",
          replace='    cell = panel.latest_vintage_of(sid, period, "9999-12-31")',
          target=f"{REPLAY_T}::TestVintageWall::"
                 "test_macro_features_read_the_revision_in_force_at_the_decision",
          expect_failure_contains="a later revision leaked"),
    Proof(label="6. the chain hash stops covering the payload",
          path=PKG / "ledger.py",
          find='    body = {k: v for k, v in entry.items() if k != "hash"}',
          replace='    body = {k: v for k, v in entry.items() '
                  'if k not in ("hash", "payload")}',
          target=f"{LEDGER_T}::TestTheChain::test_an_edited_line_breaks_the_chain",
          expect_failure_contains="DID NOT RAISE"),
    Proof(label="7. a private company is handed a security",
          path=PKG / "universe.py",
          find="            ticker = listed_security(c)",
          replace="            ticker = str(c.ticker or c.company_id)",
          target=f"{CONTRACT_T}::TestUniverseWalls::"
                 "test_no_private_company_receives_a_security",
          expect_failure_contains="assert not"),
    Proof(label="8. the leak checker goes dead; the canary must stop the replay",
          path=PKG / "leakage.py",
          find="        d = evidence_date(eid)",
          replace='        d = "0000-00-00"',
          target=f"{REPLAY_T}::TestReplay::test_the_canary_is_refused_on_every_date",
          expect_failure_contains="checker is not live"),
    Proof(label="9. the econ state is built later than it says",
          path=PKG / "macro.py",
          find="        state = _publisher().build_state(panel, as_of=as_of)",
          replace='        state = _publisher().build_state(panel, '
                  'as_of="2026-08-27")',
          target=f"{FORWARD_T}::TestEconArmIsLive::"
                 "test_a_bank_reads_the_curve_and_the_flags_move_with_the_state",
          expect_failure_contains="from after it"),
    Proof(label="10. a record is mislabelled into the wrong ledger kind",
          path=PKG / "forward.py",
          find='        "ledger_kind": kind,',
          replace='        "ledger_kind": "FORWARD_SHADOW",',
          target=f"{FORWARD_T}::TestResolver::"
                 "test_it_resolves_once_the_window_has_closed",
          expect_failure_contains="may not enter"),
    Proof(label="11. the 'existing engine' policy stops calling the engine",
          path=PKG / "policies.py",
          find="        sig = SL.baseline_momentum(closes, security=o.symbol,",
          replace="        sig = SL.volatility_breakout(closes, security=o.symbol,",
          target=f"{CONTRACT_T}::TestPolicyHonesty::"
                 "test_the_engine_policies_call_the_engine",
          expect_failure_contains="calls"),
]


if __name__ == "__main__":
    raise SystemExit(run_all(PROOFS, title="paper-validation break proofs"))
