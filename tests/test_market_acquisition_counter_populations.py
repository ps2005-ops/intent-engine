"""The acquisition counters, exercised through the PRODUCER, not a fixture.

A break proof that mutated `report.document_attempts += len(documents)` to
`+= 1` went NOT_CAUGHT, and the investigation was the finding: every existing
test wrote a ledger row by hand, so `measure()` itself — the only place the
two populations are established — had no coverage at all. Contract fixtures
cannot catch a producer that miscounts.

The case that matters is one subject returning several documents. That is
precisely the shape that made `documents_retrieved / documents_attempted`
exceed 1.0 in 22 of 40 live rows.
"""
from intent_engine.market import counterparty_sources as CS


def document(subject, n):
    return CS.Document(document_id=f"{subject}-{n}", family="customer_case",
                       subject=subject, title=f"doc {n}",
                       text=f"{subject} works with Northwind on logistics.",
                       url=f"https://example.com/{subject}/{n}")


def extract(doc, subject, aliases):
    return ([], [], {})


def test_one_subject_returning_three_documents_counts_one_subject(monkeypatch):
    """subjects_attempted counts SUBJECTS; document_attempts counts DOCUMENTS."""
    subjects = [("acme", ("Acme",))]

    def fetch(subject, aliases, as_of):
        return [document(subject, i) for i in range(3)]

    _, report = CS.measure("customer_case", subjects=subjects, fetch=fetch,
                           extract=extract, as_of="2026-08-12")
    assert report.subjects_attempted == 1
    assert report.document_attempts == 3
    assert report.documents_retrieved == 3
    # The defect, stated as an invariant: a document-level yield must never
    # exceed 1. Before the repair this ratio was 3.0.
    assert report.documents_retrieved <= report.document_attempts


def test_many_subjects_each_returning_many_documents():
    subjects = [(f"c{i}", (f"C{i}",)) for i in range(4)]

    def fetch(subject, aliases, as_of):
        return [document(subject, i) for i in range(2)]

    _, report = CS.measure("customer_case", subjects=subjects, fetch=fetch,
                           extract=extract, as_of="2026-08-12")
    assert report.subjects_attempted == 4
    assert report.document_attempts == 8
    assert report.documents_retrieved <= report.document_attempts


def test_a_subject_that_fails_is_attempted_but_yields_no_documents():
    """An unreachable subject must still count as attempted.

    Otherwise a family that fails everywhere reports a perfect yield over the
    handful of subjects that happened to answer.
    """
    def fetch(subject, aliases, as_of):
        if subject == "broken":
            raise OSError("unreachable")
        return [document(subject, 0)]

    _, report = CS.measure("customer_case",
                           subjects=[("broken", ()), ("ok", ())],
                           fetch=fetch, extract=extract, as_of="2026-08-12")
    assert report.subjects_attempted == 2
    assert report.document_attempts == 1
    assert report.documents_retrieved == 1
    assert report.errors


def test_the_emitted_row_carries_both_populations():
    def fetch(subject, aliases, as_of):
        return [document(subject, 0), document(subject, 1)]

    _, report = CS.measure("customer_case", subjects=[("acme", ())],
                           fetch=fetch, extract=extract, as_of="2026-08-12")
    row = report.as_dict()
    assert row["subjects_attempted"] == 1
    assert row["document_attempts"] == 2
    # The misnamed field is gone from new rows; its absence is what marks a
    # row as legacy downstream.
    assert "documents_attempted" not in row
