#!/usr/bin/env python3
"""Break the capture/replay/audit harness deliberately.

This harness is what the programme will trust INSTEAD of re-reading pages and
re-running companies. A silent defect in it is worse than a silent defect in
a renderer: a renderer defect is visible to a reader, and a measurement
defect makes the reader confident.

Run:  PYTHONPATH=src python3 scripts/break_proofs_pre100_harness.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from break_proof_harness import Proof, run_all       # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
A = ROOT / "src/intent_engine/pre100/audit.py"
C = ROOT / "src/intent_engine/pre100/capture.py"
R = ROOT / "src/intent_engine/pre100/replay.py"
T = "tests/test_pre100_capture_replay_harness.py"
T = "tests/test_pre100_capture_replay_audit.py"

PROOFS = [
    ("A1. a route stops being written the moment it settles",
     C,
     "        self.manifest[\"routes\"][name] = {\n"
     "            \"status\": status, \"final_url\": url, \"chars\": len(body),\n"
     "            \"html_chars\": len(raw)}\n"
     "        self.flush()",
     "        self.manifest[\"routes\"][name] = {\n"
     "            \"status\": status, \"final_url\": url, \"chars\": len(body),\n"
     "            \"html_chars\": len(raw)}",
     f"{T}::test_a_route_is_on_disk_before_the_journey_finishes",
     "only written at the end"),

    ("A2. the raw html is dropped, keeping only text",
     C,
     "        (self.dir / f\"{name}.html\").write_text(raw, \"utf-8\")",
     "        pass",
     f"{T}::test_the_raw_html_is_kept_beside_the_text",
     "assert"),

    ("B1. variants are masked in arbitrary order again",
     A,
     "    return sorted({v for v in variants if len(v) > 2}, key=len, "
     "reverse=True)",
     "    return sorted({v for v in variants if len(v) > 2})",
     f"{T}::test_variants_are_masked_longest_first",
     "assert"),

    ("B2. the boundary goes back to \\\\b, so a suffix survives",
     A,
     '        body = re.sub(r"(?<!\\w)" + re.escape(variant) + r"(?!\\w)", "<CO>",',
     '        body = re.sub(r"\\b" + re.escape(variant) + r"\\b", "<CO>",',
     f"{T}::test_variants_are_masked_longest_first",
     "assert"),

    ("B3. a generic leading word is masked again",
     A,
     "    if (len(first) >= _MIN_LEADING_TOKEN\n"
     "            and first.lower() not in _GENERIC_LEADING):",
     "    if len(first) >= _MIN_LEADING_TOKEN:",
     f"{T}::test_a_leading_word_that_is_also_a_word_is_not_masked",
     "assert"),

    ("B4. the boilerplate tail is compared again",
     A,
     "    if marker and marker.start() > 0:\n        body = body[:marker.start()]",
     "    if False:\n        body = body[:marker.start()]",
     f"{T}::test_the_boilerplate_tail_is_truncated",
     "run-varying chrome"),

    ("C1. giving up and bounding honestly are counted together",
     A,
     "        \"failure_language\": _hits(text, FAILURE_LANGUAGE),\n"
     "        \"absence_language\": _hits(text, ABSENCE_LANGUAGE),",
     "        \"failure_language\": _hits(text, FAILURE_LANGUAGE "
     "+ ABSENCE_LANGUAGE),\n"
     "        \"absence_language\": _hits(text, ABSENCE_LANGUAGE),",
     f"{T}::test_giving_up_and_bounding_honestly_are_not_the_same",
     "assert"),

    ("C2. a contradiction stops being reported",
     A,
     "    if named and denied:",
     "    if False:",
     f"{T}::test_a_contradiction_is_computed_not_spotted",
     "assert"),

    ("D1. a zero denominator reads as absence instead of UNREADABLE",
     R,
     "    if not pool and not bundle[\"qa\"]:",
     "    if False:",
     f"{T}::test_an_empty_capture_is_unreadable_not_a_pass",
     "assert"),

    ("D2. the denominator stops being reported at all",
     R,
     "            \"searched_routes\": len(pool),",
     "            \"searched_routes\": 0,",
     f"{T}::test_the_denominator_is_always_reported",
     "assert"),

    ("E1. the other harness's layout stops being read",
     A,
     "_ROUTE_ALIASES = {\"step6\": (\"step6\", \"connect\"),\n"
     "                  \"connect\": (\"connect\", \"step6\")}",
     "_ROUTE_ALIASES = {}",
     f"{T}::test_either_harnesss_layout_reads",
     "connect.txt was not read"),
]


if __name__ == "__main__":
    raise SystemExit(run_all([Proof(*p) for p in PROOFS]))
