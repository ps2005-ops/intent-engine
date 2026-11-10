"""Re-render a captured live run with no network, no Render, no model.

WHY. The expensive loop was: change a line, run a full guard, deploy, wait
for Render, spend a live analysis, read a page — to learn that a field never
crossed a projection. That is minutes and a scarce quota slot to answer a
question the captured artifact already contains.

A defect that reproduces from a capture is diagnosed locally in seconds. One
that does NOT reproduce is itself a finding — RUNTIME_ONLY_DEFECT — and is
the only kind that earns another live run. Naming that outcome is the point:
"could not reproduce" was previously indistinguishable from "did not look
hard enough".

This is for DIAGNOSIS and regression. It is not a substitute for final live
verification, and it cannot be: it renders what the run produced, not what
the deployed service would produce today.
"""
from __future__ import annotations

import json
import pathlib

REPRODUCED = "REPRODUCED"
NOT_REPRODUCED = "RUNTIME_ONLY_DEFECT"
UNREADABLE = "UNREADABLE"


def load(capture: pathlib.Path) -> dict:
    """The captured run as one object: manifest, every route, the answers."""
    capture = pathlib.Path(capture)
    if capture.is_file():
        capture = capture.parent
    from intent_engine.pre100 import audit as A
    bundle = {"path": str(capture), "manifest": A._manifest(capture),
              "routes": {}, "qa": []}
    for path in sorted(capture.glob("*.txt")):
        bundle["routes"][path.stem] = path.read_text("utf-8")
    qa = capture / "qa.json"
    if qa.exists():
        try:
            bundle["qa"] = json.loads(qa.read_text("utf-8"))
        except Exception:                                   # noqa: BLE001
            bundle["qa"] = []
    return bundle


def find(capture: pathlib.Path, needle: str, *,
         routes=None, case_sensitive: bool = False) -> dict:
    """Where does this string actually appear in what the customer saw?

    Reports the DENOMINATOR it searched. A zero denominator is UNREADABLE,
    not a pass — a grep whose pattern had silently narrowed returned nothing
    this morning and was thirty seconds from being reported as a fix.
    """
    bundle = load(capture)
    pool = bundle["routes"]
    if routes:
        pool = {k: v for k, v in pool.items() if k in set(routes)}
    if not pool and not bundle["qa"]:
        return {"status": UNREADABLE, "searched_routes": 0,
                "why": "the capture holds no rendered text at all"}
    probe = needle if case_sensitive else needle.lower()
    hits = []
    for name, text in pool.items():
        body = text if case_sensitive else text.lower()
        if probe in body:
            index = body.index(probe)
            hits.append({"route": name, "count": body.count(probe),
                         "context": text[max(0, index - 90):index + 150]})
    for row in bundle["qa"]:
        body = row.get("answer") or ""
        cmp_body = body if case_sensitive else body.lower()
        if probe in cmp_body:
            hits.append({"route": "qa", "question": row.get("question", ""),
                         "count": cmp_body.count(probe),
                         "context": body[:240]})
    return {"status": REPRODUCED if hits else NOT_REPRODUCED,
            "needle": needle,
            "searched_routes": len(pool),
            "searched_answers": len(bundle["qa"]),
            "hits": hits}


def delta(before: pathlib.Path, after: pathlib.Path) -> dict:
    """What CHANGED between two captures of one company.

    A repair validated by re-reading every route reads mostly unchanged
    text. Reading only what moved is the same evidence at a fraction of the
    cost — and a section whose producer was untouched and whose text is
    identical may inherit its previous pass during an intermediate loop.
    """
    a, b = load(before), load(after)
    rows = []
    for name in sorted(set(a["routes"]) | set(b["routes"])):
        old, new = a["routes"].get(name, ""), b["routes"].get(name, "")
        rows.append({"route": name, "changed": old != new,
                     "chars_before": len(old), "chars_after": len(new),
                     "delta": len(new) - len(old)})
    answers = []
    for old, new in zip(a["qa"], b["qa"]):
        if (old.get("answer") or "") != (new.get("answer") or ""):
            answers.append({"question": new.get("question", ""),
                            "before": (old.get("answer") or "")[:200],
                            "after": (new.get("answer") or "")[:200]})
    changed = [r["route"] for r in rows if r["changed"]]
    return {"before": str(before), "after": str(after),
            "routes": rows, "routes_changed": changed,
            "routes_unchanged_may_inherit_pass": [
                r["route"] for r in rows if not r["changed"]],
            "answers_changed": answers}
