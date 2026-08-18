#!/usr/bin/env python3
"""Batch A, §4: does the assigned model class describe how each company earns?

Runs the PRODUCTION classification path for the eight Batch-A companies:
the registrant's SIC from its own CIK, plus its own filing text, exactly as
`WebApp.classification_inputs` supplies them.

Reports the class each company receives and the economics that class asserts,
so the missing classes can be named rather than guessed.

Run:  PYTHONPATH=src python scripts/batch_a_ontology.py
"""
from __future__ import annotations

import json
import re
import sys

from intent_engine.company_ingestion.edgar import (
    MAX_FILING_BYTES, propose_edgar_candidates, registrant_classification,
)
from intent_engine.company_ingestion.fetch import safe_fetch
from intent_engine.executive.company_profile import (
    _ECONOMICS, profile_for, revenue_model_hint,
)

# (display name, CIK) — Batch A, deliberately cross-industry.
BATCH_A = [
    ("Meta Platforms, Inc.", "1326801"),
    ("Amazon.com, Inc.", "1018724"),
    ("NVIDIA Corporation", "1045810"),
    ("JPMorgan Chase & Co.", "19617"),
    ("Walmart Inc.", "104169"),
    ("Eli Lilly and Company", "59478"),
    ("Caterpillar Inc.", "18230"),
    ("Exxon Mobil Corporation", "34088"),
]

#: What each company's economics actually are, as a hypothesis to test the
#: ontology against. NOT a rule the product uses — it exists only so this
#: script can say "the class assigned does not describe this business".
EXPECTED = {
    "Meta Platforms, Inc.": "ADVERTISING_PLATFORM",
    "Amazon.com, Inc.": "MULTI_ENGINE_PLATFORM",
    "NVIDIA Corporation": "SEMICONDUCTOR_PLATFORM",
    "JPMorgan Chase & Co.": "BANK",
    "Walmart Inc.": "SCALE_RETAIL",
    "Eli Lilly and Company": "PHARMA",
    "Caterpillar Inc.": "INDUSTRIAL_EQUIPMENT",
    "Exxon Mobil Corporation": "INTEGRATED_ENERGY",
}


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or ""))


def subject_text(name: str, cik: str) -> str:
    """The company's own annual filing, as the run would hold it."""
    candidates = propose_edgar_candidates(company_name=name, cik=cik)
    annual = [c for c in candidates if "10-K" in c["title"]
              and "exhibit" not in c["title"].lower()]
    if not annual:
        annual = candidates[:1]
    if not annual:
        return ""
    result = safe_fetch(annual[0]["url"], accept_truncated=True,
                        max_bytes=MAX_FILING_BYTES)
    return _plain(result.get("body") or "") if result.get("ok") else ""


def main() -> int:
    rows = []
    for name, cik in BATCH_A:
        digits = cik.lstrip("0")
        registrant = registrant_classification(
            {"cik": int(digits), "cik10": f"{int(digits):010d}"}) or {}
        text = subject_text(name, cik)
        profile = profile_for(name=name, registrant=registrant,
                              evidence_text=text)
        economics = _ECONOMICS.get(profile.business_model_class) or {}
        row = {
            "company": name,
            "sic": registrant.get("sic", ""),
            "sic_description": registrant.get("sic_description", ""),
            "filing_chars": len(text),
            "assigned_class": profile.business_model_class,
            "sector": profile.sector,
            "known": profile.known,
            "profile_state": profile.profile_state,
            "revenue_hint": revenue_model_hint(text),
            "expected_class": EXPECTED[name],
            "class_describes_business":
                profile.business_model_class == EXPECTED[name],
            "asserted_business_model": economics.get("business_model", ""),
            "asserted_revenue_drivers":
                list(economics.get("revenue_drivers", ())),
            "asserted_macro": list(economics.get("macro", ())),
        }
        rows.append(row)
        flag = "OK " if row["class_describes_business"] else "MISS"
        print(f"{flag} {name:32s} SIC {row['sic']:5s} -> "
              f"{row['assigned_class']:24s} (want {row['expected_class']})")
        if not row["class_describes_business"]:
            print(f"       asserts: "
                  f"{row['asserted_business_model'][:110]}")
    print()
    miss = [r for r in rows if not r["class_describes_business"]]
    print(f"ontology coverage: {len(rows) - len(miss)}/{len(rows)}")
    print("missing classes:",
          sorted({r["expected_class"] for r in miss}))
    with open("docs/execution/v5/pre100_60/batch_a_ontology.json", "w") as fh:
        json.dump(rows, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
