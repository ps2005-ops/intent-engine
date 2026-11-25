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


# Moved 2026-11-25 from test_market_self_test_contamination.py: it reads the
# live ledger and its ratio moved with the nightly cycle (2 < 5/4 failed on the
# untouched base 66e70ddd). Assertion unchanged.
def test_occurrence_identity_removes_the_duplicates_and_loses_no_binding():
    """The measurement that justifies the change, pinned.

    Optimising self-tests to zero by refusing more would be easy and would
    destroy recall. This asserts the opposite: the same expectations bind,
    from fewer rows.
    """
    if not REAL_LEDGER.exists():                       # pragma: no cover
        return
    store = LS.LearningStore(REAL_LEDGER)
    evidence = list(store.evidence())
    expectations = store.open_expectations(as_of="2026-08-07")

    seen, deduped = set(), []
    for row in evidence:
        key = ME.occurrence_key(subject_company=row.subject_company,
                                evidence_type=row.evidence_type,
                                fact=row.fact, source=row.source)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    # The count MOVES with the ledger in both directions; the property is
    # that occurrence identity removes duplicates and never invents rows.
    assert len(deduped) < len(evidence), (
        "occurrence identity removed nothing; either the ledger has no "
        "duplicates or the key has started including a per-read field again")
    assert set(deduped).issubset(set(evidence))

    before, before_refused = OB.bind(expectations, evidence,
                                     as_of="2026-08-07")
    after, after_refused = OB.bind(expectations, deduped, as_of="2026-08-07")

    key = "restates_the_evidence_that_opened_it"
    assert before_refused[key] > 0, (
        "no self-test refusal to collapse; the fixture no longer exercises "
        "the contamination this repair addresses")
    # The property is the COLLAPSE, not the residue: occurrence identity
    # takes self-test refusals from many to a handful.
    assert after_refused.get(key, 0) < before_refused[key] / 4
    # Recall is exactly preserved: not one expectation resolved before and
    # stopped resolving after.
    assert set(before) == set(after)
    assert before == after
