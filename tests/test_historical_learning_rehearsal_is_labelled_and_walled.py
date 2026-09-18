"""The rehearsal must be walled from hindsight, and must never read as real.

TWO PROPERTIES, BOTH LOAD-BEARING
---------------------------------
§20 forbids hindsight expectation creation: an expectation formed at T0 may
not have been informed by a document that arrived after T0. §22 forbids
counting a rehearsal as forward learning: the frozen 40 ended
`CALIBRATION_STATUS = PRE_CALIBRATION` and every real counter at zero, and
that remains true.

Both are properties of the OUTPUT, so both are testable without a network.
"""
from __future__ import annotations

from intent_engine.executive import learning_rehearsal as LR
from intent_engine.executive.analysis_selection import select

_SUB = ("We sell software on an annual subscription and recognise revenue "
        "ratably over the contract term.")


def _read(name):
    return lambda text: select(name=name, published_text=text,
                               evidence_text=text)


def _docs():
    return [
        {"filed": "2024-02-01", "form": "10-K",
         "text": f"Acme is built for IT operations teams. {_SUB}"},
        {"filed": "2024-06-01", "form": "8-K",
         "text": f"Acme continues to serve IT operations teams. {_SUB}"},
        {"filed": "2025-03-01", "form": "10-K",
         "text": (f"Acme is built for security operations teams. Pricing is "
                  f"based on the number of managed endpoints. {_SUB}")},
    ]


# --- the wall ---------------------------------------------------------------

def test_the_t0_reading_cannot_see_a_document_filed_after_t0():
    """The whole rehearsal is worthless if the earlier reading peeks."""
    seen = []
    r = LR.rehearse(company="Acme", documents=_docs(),
                    read=lambda t: (seen.append(t), _read("Acme")(t))[1])
    assert r.available, r.refused
    first = seen[0]
    assert "managed endpoints" not in first, (
        "the T0 reading was given text from a document filed after T0")
    assert "security operations" not in first


def test_the_expectation_is_created_at_the_t0_cutoff_not_now():
    """An expectation stamped 'now' cannot be checked for hindsight."""
    r = LR.rehearse(company="Acme", documents=_docs(), read=_read("Acme"))
    assert r.expectation.created_at == r.t0
    assert r.reconciliation.observation_date > r.expectation.created_at, (
        "the observation that resolved the expectation does not postdate it")


# --- the label --------------------------------------------------------------

def test_every_emitted_row_carries_the_rehearsal_label():
    r = LR.rehearse(company="Acme", documents=_docs(), read=_read("Acme"))
    out = r.as_dict()
    assert out["label"] == LR.HISTORICAL_REHEARSAL
    for key in ("belief", "expectation", "reconciliation", "delta"):
        assert out[key]["label"] == LR.HISTORICAL_REHEARSAL, (
            f"{key} could reach a table without saying it is a rehearsal")


def test_the_label_cannot_be_overridden_by_construction():
    """A caller who sets label='REAL_FORWARD' must not be believed."""
    forged = LR.LearningDecisionDelta(company="Acme", label="REAL_FORWARD")
    assert forged.as_dict()["label"] == LR.HISTORICAL_REHEARSAL


# --- the outcomes are honest ------------------------------------------------

def test_a_decision_that_keeps_its_archetype_is_not_called_reversed():
    """Inflating the one count a reader trusts most is the failure mode."""
    r = LR.rehearse(company="Acme", documents=_docs(), read=_read("Acme"))
    assert r.delta.change_type == LR.MEASURE_REVISED, (
        f"a re-measured question was classified {r.delta.change_type}")


def test_a_decision_that_becomes_a_different_decision_is_reversed():
    """The negative control must be able to fail: REVERSED must be reachable."""
    docs = [
        {"filed": "2024-02-01", "form": "10-K",
         "text": f"Beta is built for IT teams. {_SUB}"},
        {"filed": "2025-03-01", "form": "10-K",
         "text": (f"Beta is built for IT teams. We rely on carrier networks, "
                  f"freight forwarders, customs brokers, logistics partners, "
                  f"shipment tracking, supplier records, procurement systems "
                  f"and lead time data. {_SUB}")},
    ]
    r = LR.rehearse(company="Beta", documents=docs, read=_read("Beta"))
    assert r.delta.change_type == LR.REVERSED


def test_an_unchanged_record_does_not_manufacture_a_change():
    """§24: if the data does not support a reversal, do not produce one."""
    same = f"Gamma is built for IT operations teams. {_SUB}"
    docs = [{"filed": "2024-02-01", "form": "10-K", "text": same},
            {"filed": "2025-03-01", "form": "10-K", "text": same}]
    r = LR.rehearse(company="Gamma", documents=docs, read=_read("Gamma"))
    assert r.delta.change_type in (LR.REINFORCED, LR.NO_MATERIAL_CHANGE)
    assert not r.delta.changed


# --- refusal ----------------------------------------------------------------

def test_a_corpus_that_cannot_be_split_is_refused_with_a_reason():
    r = LR.rehearse(company="Thin",
                    documents=[{"filed": "2025-01-01", "text": "x"}],
                    read=_read("Thin"))
    assert not r.available
    assert "before and an after" in r.refused


def test_documents_all_on_one_date_are_refused():
    docs = [{"filed": "2025-01-01", "form": "10-K", "text": "a" * 300},
            {"filed": "2025-01-01", "form": "8-K", "text": "b" * 300}]
    r = LR.rehearse(company="Flat", documents=docs, read=_read("Flat"))
    assert not r.available
    assert "same date" in r.refused


def test_a_reader_that_raises_is_reported_not_propagated():
    def _boom(_text):
        raise RuntimeError("reader failed")
    r = LR.rehearse(company="Acme", documents=_docs(), read=_boom)
    assert not r.available
    assert "RuntimeError" in r.refused
