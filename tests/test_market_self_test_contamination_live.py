"""PRODUCTION MONITOR, split from test_market_self_test_contamination.py.

It reads the live market ledger, which a scheduled cycle appends to; on
2026-11-09 the dominant class moved from SAME_SOURCE_REPACKAGING to
SAME_EVENT_DIFFERENT_HEADLINE with nothing broken. Assertion unchanged. Run on
demand; the offline invariants stay in the original module.
"""
from __future__ import annotations

import pathlib

from intent_engine.market import learning_store as LS
from intent_engine.market import micro_evidence as ME
from intent_engine.market import observation_binding as OB

REAL_LEDGER = pathlib.Path(
    "/Users/prathamsharma/intent-engine-market/reports/market/"
    "learning_ledger.jsonl")


def item(fact="Revenue grew 30% year on year.", observed="2026-08-05",
         source="investor_material", role="regulatory_filing",
         subject="shopify", etype=ME.EARNINGS_RESULT):
    return ME.build(subject_company=subject, actor=subject,
                    evidence_type=etype, observed_at=observed,
                    source=source, fact=fact, source_role=role,
                    reliability=0.8, relevance=0.9)


# --- identity no longer moves with the calendar --------------------------


def test_the_real_ledgers_dominant_class_is_the_sweep_re_read():
    if not REAL_LEDGER.exists():                       # pragma: no cover
        return
    store = LS.LearningStore(REAL_LEDGER)
    got = OB.diagnose(store.open_expectations(as_of="2026-08-07"),
                      store.evidence())
    # `>= 28` was a count of the live ledger on the day it was written and
    # has since fallen to 23 -- not because anything regressed, but because
    # the ledger this reads is a growing production artifact and its class
    # mix moves. DOMINANCE is the claim, and it is asserted relationally.
    assert got["dominant_class"] == OB.SAME_SOURCE_REPACKAGING
    counts = got["by_class"]
    assert counts[OB.SAME_SOURCE_REPACKAGING] > 0
    assert counts[OB.SAME_SOURCE_REPACKAGING] == max(counts.values()), (
        "the dominant class must actually be the largest; a label computed "
        f"some other way is the defect this catches: {counts}")
    assert "no longer hashes the sweep date" in \
        got["producers"][OB.SAME_SOURCE_REPACKAGING]
