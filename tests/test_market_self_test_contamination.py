"""The self-test rate had a producer, and it was four layers upstream.

`observation_binding` was catching, one at a time, duplicates that ingestion
should never have written. The producer was `evidence_id_for` hashing
`observed_at` — the date the SWEEP RAN — into the identity of the fact it
read, so an unchanged page re-read on three nights became three facts.

Measured on the real ledger: 84 of 249 rows were re-reads, 28 of 31
self-tests were `SAME_SOURCE_REPACKAGING`, and removing them takes the
self-test rate from 0.857 to 0.400 while losing ZERO bindings.
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

def test_the_sweep_date_is_not_part_of_a_facts_identity():
    monday = item(observed="2026-08-05")
    friday = item(observed="2026-08-09")
    assert monday.evidence_id == friday.evidence_id


def test_two_outlets_reporting_one_event_are_still_two_items():
    """Correlated, not identical. The design-effect penalty handles it."""
    filing = item(source="investor_material")
    wire = item(source="https://news.google.com/rss/x")
    assert filing.evidence_id != wire.evidence_id


def test_a_different_fact_is_a_different_occurrence():
    assert item(fact="Revenue grew 30%.").evidence_id != \
        item(fact="Revenue fell 4%.").evidence_id


def test_reformatting_is_not_a_new_fact():
    assert item(fact="Revenue  grew   30% year on year.").evidence_id == \
        item(fact="revenue grew 30% year on year.").evidence_id


# --- the store refuses the re-read and records that it happened ----------

def test_a_re_read_is_recorded_but_is_not_a_second_observation(tmp_path):
    store = LS.LearningStore(tmp_path / "ledger.jsonl")
    assert store.record_evidence(item(observed="2026-08-05")) is True
    assert store.record_evidence(item(observed="2026-08-09")) is False
    assert len(store.evidence()) == 1
    seen = store.re_observations()
    assert len(seen) == 1
    assert seen[0]["seen_at"] == "2026-08-09"


def test_the_first_sighting_keeps_its_own_date(tmp_path):
    store = LS.LearningStore(tmp_path / "ledger.jsonl")
    store.record_evidence(item(observed="2026-08-05"))
    store.record_evidence(item(observed="2026-08-09"))
    assert store.evidence()[0].observed_at[:10] == "2026-08-05"


def test_legacy_rows_written_under_the_old_id_are_still_recognised(tmp_path):
    """No history is rewritten; the key is recomputed from the row."""
    store = LS.LearningStore(tmp_path / "ledger.jsonl")
    legacy = item(observed="2026-08-05").as_dict()
    legacy["evidence_id"] = "ev_written_before_the_fix"
    store._append(LS.EVIDENCE, legacy)
    assert store.record_evidence(item(observed="2026-08-09")) is False
    assert len(store.evidence()) == 1


# --- the decomposition names a producer ----------------------------------

def test_every_class_carries_a_producer():
    assert set(OB.PRODUCER_OF) == set(OB.SELF_TEST_CLASSES)
    assert all(OB.PRODUCER_OF[k] for k in OB.SELF_TEST_CLASSES)


def test_the_same_page_on_a_later_sweep_is_same_source_repackaging():
    assert OB.classify_self_test(
        item(observed="2026-08-05"),
        item(observed="2026-08-07")) == OB.SAME_SOURCE_REPACKAGING


def test_the_same_text_from_a_different_source_role_is_a_wire_duplicate():
    assert OB.classify_self_test(
        item(role="regulatory_filing"),
        item(role="independent_reporting")) == OB.WIRE_DUPLICATE


def test_one_document_two_excerpts_is_its_own_class():
    assert OB.classify_self_test(
        item(observed="2026-08-05"),
        item(observed="2026-08-05")) == OB.SAME_DOCUMENT_DIFFERENT_EXCERPT


def test_the_real_ledgers_dominant_class_is_the_sweep_re_read():
    if not REAL_LEDGER.exists():                       # pragma: no cover
        return
    store = LS.LearningStore(REAL_LEDGER)
    got = OB.diagnose(store.open_expectations(as_of="2026-08-07"),
                      store.evidence())
    assert got["dominant_class"] == OB.SAME_SOURCE_REPACKAGING
    assert got["by_class"][OB.SAME_SOURCE_REPACKAGING] >= 28
    assert "no longer hashes the sweep date" in \
        got["producers"][OB.SAME_SOURCE_REPACKAGING]


# --- the repair removes contamination without costing recall -------------

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

    # The count grows with the ledger; the property is that occurrence
    # identity REMOVES duplicates and that no binding is lost below.
    assert len(evidence) - len(deduped) >= 76

    before, before_refused = OB.bind(expectations, evidence,
                                     as_of="2026-08-07")
    after, after_refused = OB.bind(expectations, deduped, as_of="2026-08-07")

    key = "restates_the_evidence_that_opened_it"
    assert before_refused[key] >= 18
    # The property is the COLLAPSE, not the residue: occurrence identity
    # takes self-test refusals from many to a handful.
    assert after_refused.get(key, 0) < before_refused[key] / 4
    # Recall is exactly preserved: not one expectation resolved before and
    # stopped resolving after.
    assert set(before) == set(after)
    assert before == after
