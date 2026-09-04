"""The attrition breakdown has to be subtractable.

MEASURED on 743df06, UnitedHealth Group:

    compose=13 usable=9 families=... stored=16 attempt=2 dropped=0/0/2/0

Thirteen documents, two named as dropped, nine usable. Two are unaccounted
for. They were not lost by a filter -- they were counted by a DIFFERENT
measurement: the four `dropped_*` numbers were computed at first composition
and the re-gate then overwrote `compose` and `usable` with a later document
set, leaving one header describing two things.

A breakdown whose arithmetic does not close is worse than no breakdown,
because it looks like an answer. These pin that it closes, and that anything
it cannot name is reported rather than absorbed.
"""
from intent_engine.company_ingestion.readiness import (
    assess_readiness, readiness_inputs,
)


def _doc(i, *, status="OK", text=None, lang="en"):
    prose = {
        "en": f"Document {i}. The registrant operates a national freight "
              f"network and reports segment revenue for period {i}. ",
        "de": f"Dokument {i}. Die Gesellschaft betreibt ein Schienennetz und "
              f"veroeffentlicht Umsatzerloese fuer den Zeitraum {i}. ",
    }[lang]
    return {"source_id": f"s{i}", "source_type": "external_approved",
            "source_class": "investor_material", "retrieval_status": status,
            "title": f"SEC 10-Q ({i})",
            "text_content": (prose if text is None else text) * 8,
            "filing": {"form": "10-Q"}}


def _closes(inputs):
    named = sum(inputs[k] for k in ("dropped_not_ok", "dropped_empty",
                                    "dropped_duplicate", "dropped_language"))
    return (inputs["documents_at_compose"] - named
            == inputs["usable_at_compose"])


def _inputs_for(documents):
    verdict = assess_readiness(documents=documents,
                               identity={"entity_resolved": True})
    return readiness_inputs(documents, verdict)


def test_a_clean_set_closes():
    inputs = _inputs_for([_doc(i) for i in range(6)])
    assert _closes(inputs), inputs
    assert inputs["dropped_unexplained"] == 0


def test_a_refused_fetch_is_named_and_closes():
    docs = [_doc(0), _doc(1), _doc(2, status="BLOCKED"), _doc(3)]
    inputs = _inputs_for(docs)
    assert inputs["dropped_not_ok"] == 1
    assert _closes(inputs), inputs
    assert inputs["dropped_unexplained"] == 0


def test_an_empty_body_is_named_and_closes():
    docs = [_doc(0), _doc(1), _doc(2, text="   "), _doc(3)]
    inputs = _inputs_for(docs)
    assert inputs["dropped_empty"] + inputs["dropped_duplicate"] >= 1
    assert _closes(inputs), inputs


def test_a_duplicate_is_named_and_closes():
    same = "The registrant operates a national freight network. " * 20
    docs = [_doc(0), _doc(1, text=same), _doc(2, text=same), _doc(3)]
    inputs = _inputs_for(docs)
    assert inputs["dropped_duplicate"] == 1, inputs
    assert _closes(inputs), inputs


def test_an_unreadable_language_is_named_and_closes():
    docs = [_doc(i) for i in range(5)] + [_doc(9, lang="de")]
    inputs = _inputs_for(docs)
    assert _closes(inputs), inputs


def test_every_filter_at_once_still_closes():
    same = "One page served under several URLs, again and again. " * 20
    docs = [_doc(0), _doc(1), _doc(2, status="BLOCKED"), _doc(3, text="  "),
            _doc(4, text=same), _doc(5, text=same), _doc(6, lang="de"),
            _doc(7)]
    inputs = _inputs_for(docs)
    assert _closes(inputs), inputs
    assert inputs["dropped_unexplained"] == 0


def test_the_unexplained_remainder_is_reported_not_hidden():
    """A gate that drops for an uninstrumented reason must SAY so."""
    docs = [_doc(i) for i in range(6)]
    verdict = assess_readiness(documents=docs,
                               identity={"entity_resolved": True})
    verdict["document_count"] = verdict["document_count"] - 2   # a 5th filter
    inputs = readiness_inputs(docs, verdict)
    assert inputs["dropped_unexplained"] == 2, inputs
    assert not _closes(inputs)
