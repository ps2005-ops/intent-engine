"""LIVE ACCEPTANCE CHECKS -- read the real production ledger.

Split out of `test_market_calibration_consistency.py` on 2026-10-11. These tests read
`/Users/prathamsharma/intent-engine-market` directly, so their results move
whenever a scheduled cycle appends. That makes them **monitors of production
state**, not regression tests: a legitimate new observation can turn one red
with nothing broken, and a concurrent cycle writing the ledger makes them
nondeterministic outright.

They are deliberately NOT weakened and NOT skipped. Every assertion is
unchanged and they remain runnable on demand:

    env PYTHONPATH=src python -m pytest tests/test_market_calibration_consistency_live.py

Repository convention: live tests live in `tests/test_*_live.py` and the
pre-commit guard deselects them by filename, alongside
`test_calendar_live.py`, `test_macro_data_live.py` and the others. The
invariants stay covered in the offline suite by the 9 deterministic
tests remaining in `test_market_calibration_consistency.py`.
"""
from __future__ import annotations

import json
import pathlib

from intent_engine.market import belief_maturity as BM
from intent_engine.market import calibration_consistency as CK
from intent_engine.market import causal_calibration as CC
from intent_engine.market import mechanism_calibration as MC

REAL_LEDGER = pathlib.Path(
    "/Users/prathamsharma/intent-engine-market/reports/market/"
    "learning_ledger.jsonl")


class Maturity:
    def __init__(self, state, belief_id="b1", subject="shopify"):
        self.state, self.belief_id, self.subject = state, belief_id, subject


class Mechanism:
    def __init__(self, key, maturity):
        self.key, self.maturity = key, maturity


class Causal:
    def __init__(self, family, status):
        self.causal_family, self.status = family, status


def test_the_real_ledger_is_currently_coherent():
    """Zero is the finding, and the guard exists for when it is not."""
    if not REAL_LEDGER.exists():                       # pragma: no cover
        return
    from intent_engine.universe.companies import default_universe

    rows = [json.loads(line) for line in
            REAL_LEDGER.read_text().splitlines() if line.strip()]
    industry = {c.company_id: (getattr(c, "industry", "") or "")
                for c in default_universe().prediction_companies()}
    family_of = {r.get("hypothesis_id"): r.get("metric") for r in rows
                 if r.get("record") == "expectation"}
    got = CK.check(maturities=BM.classify(rows, as_of="2026-08-07"),
                   mechanisms=MC.calibrate(rows),
                   causal_families=CC.calibrate(rows, industry_of=industry),
                   family_of=family_of)
    assert got == ()
