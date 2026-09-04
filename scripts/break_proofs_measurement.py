"""§101: mutations of the measurement apparatus itself.

A benchmark decides whether a release ships, so its sensors are production
guarantees and get production guards. Every mutation here removes one
property the published numbers depend on, and each must turn its OWN paired
test red for its OWN stated reason. Every `path` is under `src/`.

WHY THIS FILE EXISTS. The previous evidence counter searched the rendered
HTML for `https?://` while this product cites evidence through internal
routes, so it reported 0 for six of six Tier-1 companies and for Apple. It
was not caught by any test, because nothing asserted the counter could return
a non-zero number at all.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all      # noqa: E402

S = ROOT / "src" / "intent_engine"
T = "tests/test_measurement_is_canonical.py"

PROOFS = [
    ("m-1. canonical evidence exists and the sensor reports zero",
     S / "webapp" / "app.py",
     '            "evidence_count": len(documents),',
     '            "evidence_count": 0,',
     f"{T}::test_evidence_is_counted_from_documents_not_from_html",
     "assert"),

    ("m-2. the core_ready boundary is never recorded",
     S / "webapp" / "app.py",
     '            try:\n'
     '                self.ci.mark_lifecycle(run_id, "core_ready")',
     '            try:\n'
     '                pass',
     f"{T}::test_the_lifecycle_is_recorded_where_it_happens",
     "never recorded when"),

    ("m-3. a recorded timing can be moved by doing more work",
     S / "company_ingestion" / "service.py",
     '                     idempotency_key=f"ci-lifecycle:{run_id}:{marker}")',
     '                     idempotency_key=None)',
     f"{T}::test_a_marker_is_idempotent",
     "recorded twice"),

    ("m-4. the metric no longer says where it came from",
     S / "webapp" / "app.py",
     '                "evidence_count": "canonical_retrieved_documents",',
     '                "evidence_count": "regex_html",',
     f"{T}::test_timing_reports_a_latency_and_says_where_it_came_from",
     "assert"),

    ("m-5. an unknown marker is accepted, so the vocabulary means nothing",
     S / "company_ingestion" / "service.py",
     '        if marker not in LIFECYCLE_MARKERS:\n'
     '            raise IngestionError(f"unknown lifecycle marker: {marker!r}")',
     '        if False:\n'
     '            raise IngestionError(f"unknown lifecycle marker: {marker!r}")',
     f"{T}::test_an_unknown_marker_is_refused",
     "DID NOT RAISE"),

    ("m-6. the timing is held in memory, so a restart loses it",
     S / "company_ingestion" / "service.py",
     '        for row in self.store.for_run(run_id):\n'
     '            if row.event_type == "ci.lifecycle_marked":',
     '        for row in []:\n'
     '            if row.event_type == "ci.lifecycle_marked":',
     f"{T}::test_markers_survive_a_process_restart",
     "assert"),
]


def main() -> int:
    return run_all([Proof(*row) for row in PROOFS],
                   title="Measurement apparatus break proofs (§101)")


if __name__ == "__main__":
    sys.exit(main())
