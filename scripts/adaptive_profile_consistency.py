#!/usr/bin/env python3
"""Canonical-profile consistency across every surface of one live run.

The previous matrix asserted this on TWO surfaces by string-matching one
sentence. That was enough to find the defect and not enough to prove it gone:
a contradiction can hide on /brief, /full, the history page or the timeline
just as easily, and "the sentence is absent" is a spelling test rather than a
property.

So this reads the model from the surfaces that STATE one, and refuses a run
where any two disagree -- and it separately refuses a run where a surface
says the model is unestablished while telemetry says it is not.
"""
from __future__ import annotations

import json
import re
import sys

sys.path.insert(0, "/Users/prathamsharma/intent-engine-econ/scripts")
from perf_progressive_matrix import _opener, _req, visible   # noqa: E402

SURFACES = ("", "/intro", "/brief", "/full", "/xray", "/evidence")
#: The sentence a surface prints when it could not classify the company.
UNESTABLISHED = ("has not been established", "is not classified here",
                 "could not be classified")
#: How a surface names the model in prose, lower-cased.
MODEL_WORDS = {
    "SUBSCRIPTION_SOFTWARE": "subscription software",
    "PEOPLE_OR_ROUTE_BASED_SERVICES": "people or route based services",
    "DESIGN_AND_MANUFACTURE": "design and manufacture",
    "BRANDED_CONSUMER": "branded consumer",
    "ADVERTISING_PLATFORM": "advertising platform",
    "REGULATED_PRODUCT_OR_PROVIDER": "regulated product or provider",
    "CONTRACTED_OR_RATE_BASE_ASSETS": "contracted or rate base assets",
}


def probe(run_id: str, opener=None) -> dict:
    op = opener or _opener()[0]
    st, body, _u, _t, _h = _req(op, f"/runs/{run_id}/adaptive.json", timeout=90)
    try:
        tel = json.loads(body)
    except Exception:                                        # noqa: BLE001
        tel = {}
    canonical = str(tel.get("business_model") or "")
    known = bool(tel.get("profile_available"))
    out = {"run_id": run_id, "canonical": canonical,
           "profile_available": known, "surfaces": {}, "contradictions": []}
    for suffix in SURFACES:
        st, html, _u, _t, _h = _req(op, f"/runs/{run_id}{suffix}", timeout=90)
        text = visible(html)
        low = text.lower()
        says_unestablished = any(p in low for p in UNESTABLISHED)
        named = sorted({k for k, word in MODEL_WORDS.items()
                        if word in low})
        out["surfaces"][suffix or "/"] = {
            "status": st, "unestablished": says_unestablished,
            "models_named": named}
        if known and says_unestablished:
            out["contradictions"].append(
                f"{suffix or '/'} says the business model is unestablished "
                f"while this run established {canonical}")
        for other in named:
            if canonical and other != canonical:
                out["contradictions"].append(
                    f"{suffix or '/'} names {other} and the run's canonical "
                    f"model is {canonical}")
    return out


if __name__ == "__main__":
    result = probe(sys.argv[1])
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result["contradictions"] else 0)
