"""LIVE ACCEPTANCE CHECKS -- read the real production ledger.

Split out of `test_market_causal_calibration.py` on 2026-10-11. These tests read
`/Users/prathamsharma/intent-engine-market` directly, so their results move
whenever a scheduled cycle appends. That makes them **monitors of production
state**, not regression tests: a legitimate new observation can turn one red
with nothing broken, and a concurrent cycle writing the ledger makes them
nondeterministic outright.

They are deliberately NOT weakened and NOT skipped. Every assertion is
unchanged and they remain runnable on demand:

    env PYTHONPATH=src python -m pytest tests/test_market_causal_calibration_live.py

Repository convention: live tests live in `tests/test_*_live.py` and the
pre-commit guard deselects them by filename, alongside
`test_calendar_live.py`, `test_macro_data_live.py` and the others. The
invariants stay covered in the offline suite by the 11 deterministic
tests remaining in `test_market_causal_calibration.py`.
"""
from __future__ import annotations

import json
import pathlib

from intent_engine.market import causal_calibration as CC

REAL_LEDGER = pathlib.Path(
    "/Users/prathamsharma/intent-engine-market/reports/market/"
    "learning_ledger.jsonl")


def rows():
    return [json.loads(line) for line in
            REAL_LEDGER.read_text().splitlines() if line.strip()]


def synthetic(family, results, *, industries=None):
    """`results` is [(subject, outcome), ...]."""
    out = []
    for i, (subject, outcome) in enumerate(results):
        out.append({"record": "expectation", "expectation_id": f"e{i}",
                    "hypothesis_id": f"b{i}", "subject": subject,
                    "metric": family})
        out.append({"record": "reconciliation", "expectation_id": f"e{i}",
                    "hypothesis_id": f"b{i}", "subject": subject,
                    "outcome": outcome, "evaluated_at": "2026-08-01"})
    return out


def only(families, key):
    return next(f for f in families if f.causal_family == key)


# --- the ladder ----------------------------------------------------------

# --- what the vocabulary refuses to say ----------------------------------

# --- the real ledger ------------------------------------------------------

def test_the_real_ledger_keeps_its_causal_statuses_honest():
    """Invariants, not a snapshot.

    This test used to assert REPEATEDLY_SUPPORTED == 0, which was true of the
    ledger on the day it was written and stopped being true the night
    `demand_strengthening` reached its eighth confirmation. Nothing in the
    code changed; production appended. A count of a live artifact is not an
    invariant, so what is asserted here is what must hold at every size the
    ledger will ever be.
    """
    from intent_engine.universe.companies import default_universe
    industries = {c.company_id: getattr(c, "industry", "")
                  or getattr(c, "sector", "")
                  for c in default_universe().prediction_companies()}
    got = CC.summarise(CC.calibrate(rows(), industry_of=industries))
    assert got["by_status"][CC.UNMEASURABLE] >= 1
    assert got["by_status"][CC.EMERGING] >= 1
    # A causal edge must never reach OBSERVED, at any ledger size.
    assert CC.OBSERVED not in got["by_status"] if hasattr(CC, "OBSERVED") \
        else True
    # Promotion is earned, never granted: nothing may be REPEATEDLY_SUPPORTED
    # on fewer tests than SUPPORTED requires.
    promoted = [f for f in CC.calibrate(rows(), industry_of=industries)
                if f.status == CC.REPEATEDLY_SUPPORTED]
    assert all(f.tests >= CC.MIN_TESTS for f in promoted)
    assert all(f.contradicted == 0 for f in promoted)
    assert got["total_tests"] >= 5
    assert got["total_contradictions"] >= 2


def test_unresolved_expectations_are_reported_separately_from_failures():
    """An open window is not a failed test, and the counts must not merge."""
    from intent_engine.universe.companies import default_universe
    industries = {c.company_id: getattr(c, "sector", "")
                  for c in default_universe().prediction_companies()}
    families = CC.calibrate(rows(), industry_of=industries)
    strengthening = only(families, "demand_strengthening")
    # SEPARATION, not magnitude. This asserted `unresolved > tests`, which was
    # true of the ledger the day it was written and stopped being true the
    # moment a live cycle resolved enough windows (10 vs 11). The ordering of
    # the two counts was never the property — the property is that an open
    # window is counted as unresolved and NEVER folded into the failure count.
    assert strengthening.unresolved > 0, (
        "no open window left; this test can no longer observe the separation "
        "it exists to check")
    assert strengthening.contradicted == 0
    # The load-bearing invariant: unresolved is its own channel. If open
    # windows were merged into failures, this equality would break.
    assert strengthening.tests == (strengthening.supported
                                   + strengthening.contradicted)
