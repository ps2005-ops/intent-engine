#!/usr/bin/env python3
"""Break the large-filer index budget deliberately.

The defect: a filer whose submissions index exceeds the response cap is cut
off mid-JSON, the parse fails, a broad `except` returns an empty candidate
list, and the customer is told no source could be retrieved. Measured on
JPMorgan — 4,573,499 bytes against a 2,000,000-byte cap, zero candidates,
while its 10-K sat at the top of that index.

Run:  PYTHONPATH=src python3 scripts/break_proofs_large_filer.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all       # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
E = ROOT / "src/intent_engine/company_ingestion/edgar.py"
T = "tests/test_a_large_filer_is_not_invisible.py"

PROOFS = [
    ("A1. the index shares the document cap again",
     E,
     "MAX_SUBMISSIONS_BYTES = 32_000_000",
     "MAX_SUBMISSIONS_BYTES = 2_000_000",
     f"{T}::test_the_submissions_budget_is_larger_than_the_document_cap",
     "assert"),

    ("A2. the budget stops clearing the largest real index",
     E,
     "MAX_SUBMISSIONS_BYTES = 32_000_000",
     "MAX_SUBMISSIONS_BYTES = 4_600_000",
     f"{T}::test_the_submissions_budget_clears_the_largest_real_index",
     "assert"),

    ("B1. truncated bytes are returned instead of refused",
     E,
     "    if exceeded:\n        raise SubmissionsTruncated(",
     "    if False:\n        raise SubmissionsTruncated(",
     f"{T}::test_truncation_raises_rather_than_returning_half_a_document",
     "SubmissionsTruncated"),

    ("B2. an untruncated fetch is refused anyway",
     E,
     "    if exceeded:\n        raise SubmissionsTruncated(",
     "    if True:\n        raise SubmissionsTruncated(",
     f"{T}::test_an_untruncated_fetch_does_not_raise",
     "SubmissionsTruncated"),

    ("C1. registrant_classification stops asking for the index budget",
     E,
     """            transport=transport, resolver=resolver,
            max_bytes=MAX_SUBMISSIONS_BYTES)""",
     """            transport=transport, resolver=resolver)""",
     f"{T}::test_every_reader_of_the_index_asks_for_the_index_budget",
     "registrant_classification"),

    ("C2. submissions stops asking for the index budget",
     E,
     """                           transport=transport, resolver=resolver,
                           max_bytes=MAX_SUBMISSIONS_BYTES)""",
     """                           transport=transport, resolver=resolver)""",
     f"{T}::test_every_reader_of_the_index_asks_for_the_index_budget",
     "submissions"),

    ("D1. a legacy transport without the budget argument breaks",
     E,
     "        except TypeError:",
     "        except ZeroDivisionError:",
     f"{T}::test_a_legacy_transport_without_a_budget_still_works",
     "TypeError"),
]


if __name__ == "__main__":
    raise SystemExit(run_all(
        [Proof(*p) for p in PROOFS],
        title=f"large filer index budget: {len(PROOFS)} proofs"))
