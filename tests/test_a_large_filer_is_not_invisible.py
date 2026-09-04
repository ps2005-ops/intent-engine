"""A company that files a lot may not disappear because its index is big.

MEASURED. JPMorgan Chase (CIK 19617) returned ZERO filing candidates while
every other Batch-A company returned four, and the customer was shown "no
approved source could be retrieved" for a company whose 10-K
(`jpm-20251231.htm`) sits at the top of its own index.

The cause is a byte budget, not EDGAR and not the 429s that were blamed:

    JPMorgan     4,573,499 bytes of submissions JSON
    Caterpillar    168,550
    Meta           157,613
    Walmart        158,207
    NVIDIA         161,393
    Amazon         159,828
    Eli Lilly      159,541
    Exxon          162,232

    MAX_RESPONSE_BYTES  2,000,000

JPMorgan files 25,746 recent documents, 22,368 of them 424B2 structured-note
prospectuses. The transport cut the index at exactly 2 MB, `json.loads`
raised on the half-object, and a broad `except` turned that into an empty
list — a defect in us, displayed as a fact about the company.

It scales with FILING COUNT, not company size, so the affected set is every
frequent filer: the large banks and the shelf issuers. Fixing it for
JPMorgan alone would leave the rest of that set invisible.
"""
from __future__ import annotations

import json

import pytest

from intent_engine.company_ingestion import edgar


def _index(n_filings: int) -> bytes:
    """A submissions index shaped like the real one, sized to order."""
    return json.dumps({"filings": {"recent": {
        "form": ["10-K"] + ["424B2"] * n_filings,
        "accessionNumber": ["0001628280-26-008131"] + ["0001-26-1"] * n_filings,
        "primaryDocument": ["jpm-20251231.htm"] + ["x.htm"] * n_filings,
        "filingDate": ["2026-02-20"] + ["2026-01-01"] * n_filings,
    }}}).encode()


def _transport(body: bytes):
    """A transport that enforces a byte budget exactly as the real one does."""
    def tx(url, timeout, max_bytes=edgar.MAX_RESPONSE_BYTES):
        capped = body[:max_bytes]
        return 200, {}, capped, len(body) > max_bytes
    return tx


# ===========================================================================
# The budget
# ===========================================================================
#: JPMorgan's submissions index, measured 2026-08-18. Named so the headroom
#: below is a stated multiple of a real observation rather than a round number.
LARGEST_OBSERVED_INDEX_BYTES = 4_573_499


def test_the_submissions_budget_clears_the_largest_real_index():
    """It grows with every prospectus JPMorgan files, so the budget carries
    real headroom rather than just clearing today's size."""
    assert edgar.MAX_SUBMISSIONS_BYTES >= 4 * LARGEST_OBSERVED_INDEX_BYTES


def test_the_submissions_budget_is_larger_than_the_document_cap():
    """An INDEX is machine-readable metadata, not a fetched web document, and
    sharing the document cap is what hid a filer."""
    from intent_engine.company_ingestion.records import MAX_RESPONSE_BYTES
    assert edgar.MAX_SUBMISSIONS_BYTES > MAX_RESPONSE_BYTES


# ===========================================================================
# A large index is read, not truncated
# ===========================================================================
def test_a_large_index_still_yields_candidates():
    body = _index(50_000)
    assert len(body) > 2_000_000, "fixture must exceed the document cap"
    resolved = {"cik": "19617", "cik10": "0000019617",
                "name": "JPMorgan Chase & Co.", "ticker": "JPM"}
    got = edgar.filing_candidates(resolved, transport=_transport(body),
                                  resolver=False, limit=4)
    assert got, "a filer with a large index returned no candidates"
    assert any("jpm-20251231.htm" in c["url"] for c in got)


def test_a_small_index_is_unchanged():
    body = _index(5)
    resolved = {"cik": "18230", "cik10": "0000018230",
                "name": "Caterpillar Inc.", "ticker": "CAT"}
    got = edgar.filing_candidates(resolved, transport=_transport(body),
                                  resolver=False, limit=4)
    assert got


# ===========================================================================
# Truncation is a distinct fact, not an empty filer
# ===========================================================================
def test_truncation_raises_rather_than_returning_half_a_document():
    """THE DEFECT. Returning the cut-off bytes hands broken JSON to a parser
    whose failure is indistinguishable from a company with nothing on file."""
    body = _index(50_000)

    def tiny(url, timeout, max_bytes=None):
        return 200, {}, body[:1000], True

    with pytest.raises(edgar.SubmissionsTruncated):
        edgar._fetch_bytes("https://data.sec.gov/submissions/CIK0000019617.json",
                           transport=tiny, resolver=False,
                           max_bytes=edgar.MAX_SUBMISSIONS_BYTES)


def test_an_untruncated_fetch_does_not_raise():
    body = _index(5)

    def ok(url, timeout, max_bytes=None):
        return 200, {}, body, False

    assert edgar._fetch_bytes(
        "https://data.sec.gov/submissions/CIK0000018230.json",
        transport=ok, resolver=False,
        max_bytes=edgar.MAX_SUBMISSIONS_BYTES) == body


def test_a_legacy_transport_without_a_budget_still_works():
    """Every test double in the suite predates the budget argument."""
    body = _index(3)

    def legacy(url, timeout):
        return 200, {}, body, False

    assert edgar._fetch_bytes(
        "https://data.sec.gov/submissions/CIK0000018230.json",
        transport=legacy, resolver=False,
        max_bytes=edgar.MAX_SUBMISSIONS_BYTES) == body


# ===========================================================================
# The seam: BOTH readers of the index ask for the index budget
# ===========================================================================
def test_every_reader_of_the_index_asks_for_the_index_budget():
    """EVERY reader, DISCOVERED rather than named.

    There are three — `registrant_classification`, `submissions` and
    `filing_candidates` — and the first version of this test named two, so a
    break proof against the third passed while that reader still hid large
    filers. It matters: `registrant_classification` is what resolves SIC to a
    business-model class, so a truncated index there means the company is not
    just sourceless but unclassified.

    Enumerating by AST means a fourth reader added later is covered the day
    it is written.

    READ BY AST, NOT BY LINE NUMBER. `inspect.getsource` resolves a function
    to a line SPAN, so a mutation that deletes a line inside one function
    shifts the span and the test reads part of its neighbour.
    """
    import ast
    import pathlib
    tree = ast.parse(pathlib.Path(edgar.__file__).read_text())
    readers = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        if "SUBMISSIONS_URL" in names:
            readers[node.name] = "MAX_SUBMISSIONS_BYTES" in names
    assert len(readers) >= 3, f"expected every index reader, found {readers}"
    starved = sorted(n for n, ok in readers.items() if not ok)
    assert not starved, (
        f"{starved} read the submissions index without asking for the index "
        f"budget, so they still hide filers whose index exceeds the document "
        f"cap")
