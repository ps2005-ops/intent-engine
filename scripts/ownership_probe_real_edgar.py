#!/usr/bin/env python3
"""Is another registrant's filing kept out of this company's model? Live SEC.

WHY THIS EXISTS AND WHY IT IS NOT A UNIT TEST. The ownership repair shipped
TWICE against fixtures and was inert on the page both times. A fixture
encodes what its author believed production does; this reads the real
submissions index, retrieves the real primary documents, and runs them
through the production producer. It costs no demo quota — SEC only — so it
can be run before a deploy rather than after a customer finds the defect.

The measurement that matters is the FIRST line of output: production stamps
BOTH filers' documents `investor_material`, which is exactly why a
source_class gate could never separate them.

Run:  SEC_CONTACT_EMAIL=you@example.com PYTHONPATH=src \\
      python3 scripts/ownership_probe_real_edgar.py 19617 72971
"""
from __future__ import annotations

import os
import re
import sys
import time

from intent_engine.company_ingestion.edgar import filing_candidates
from intent_engine.company_ingestion.fetch import safe_fetch
from intent_engine.company_ingestion.filing_cache import FilingCache
from intent_engine.strategic_intelligence.model import build_mental_model
from intent_engine.strategic_intelligence.observations import (
    derive_observations,
)

CACHE = FilingCache(os.environ.get("PROBE_CACHE", "data/cache/sec_filings"))


def documents_for(cik: str, limit: int = 2) -> list:
    out = []
    resolved = {"cik": int(cik), "cik10": f"{int(cik):010d}"}
    for candidate in filing_candidates(resolved)[:limit]:
        _outcome, cached = CACHE.get(candidate["url"])
        if cached is None:
            result = safe_fetch(
                candidate["url"], accept_truncated=True,
                max_bytes=int(candidate.get("max_bytes") or 2_000_000))
            if not result["ok"]:
                continue
            body = result["body"]
            raw = body if isinstance(body, bytes) else body.encode()
            CACHE.put(candidate["url"], body=raw,
                      mime_type=result.get("mime_type", ""),
                      truncated=bool(result.get("truncated")))
            time.sleep(0.4)
        else:
            raw = cached["body"]
        text = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ",
                                          raw.decode("utf-8", "replace")))
        out.append({
            "final_url": candidate["url"],
            "source_class": candidate["source_class"],
            "source_id": candidate["url"][-24:], "title": candidate["title"],
            "text": text[:400_000], "text_content": text[:400_000],
            "content_hash": candidate["url"][-16:],
            "retrieved_at": "1970-01-01"})
    return out


def main(subject_cik: str, other_cik: str) -> int:
    subject = documents_for(subject_cik)
    other = documents_for(other_cik)
    if not subject or not other:
        print("could not retrieve both filers; SEC may be throttling")
        return 2
    classes = sorted({d["source_class"] for d in subject + other})
    print(f"source_class stamped by production on BOTH filers: {classes}")

    observations = derive_observations(
        subject + other, company=f"CIK {subject_cik}",
        subject_cik=subject_cik)
    marker = f"/data/{subject_cik.lstrip('0')}/"
    wrong = [o for o in observations
             if (marker in (o.origin or "")) is not o.subject_owned]
    for o in observations:
        who = "SUBJECT" if marker in (o.origin or "") else "OTHER  "
        print(f"  {who}  subject_owned={str(o.subject_owned):5s} "
              f"{(o.strategic_signal or '')[:52]}")
    if wrong:
        print(f"FAIL: {len(wrong)} observation(s) attributed to the wrong "
              f"filer")
        return 1

    model = build_mental_model(f"CIK {subject_cik}", list(observations), [],
                               now="1970-01-01T00:00:00+00:00")
    stated = " ".join(c.current_state for c in model.components.values())
    leaked = [o for o in observations
              if not o.subject_owned and (o.strategic_signal or "")[:40]
              and (o.strategic_signal or "")[:40] in stated]
    print(f"components stated: {list(model.components)}")
    if leaked:
        for o in leaked:
            print(f"LEAK: {(o.strategic_signal or '')[:60]}")
        return 1
    print("PASS — no other registrant's observation states a component")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:] or ["19617", "72971"]
    raise SystemExit(main(args[0], args[1]))
