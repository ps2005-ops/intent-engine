"""The economy as it could have been known on a past date, reconstructed today.

WHY THIS EXISTS
---------------
History Rewind places each dated stop in its economic period through the
PUBLISHED economic state. The market engine had published one state (dated
2026-11-25), so every stop before it -- 48 private-company timelines in
prospect-100 round 6 -- read "no economic state had been published on or
before this date". True, and it left the rewind with no economy at all.

WHAT THIS IS, AND IS NOT
------------------------
The engine's own dated observations (`node` records) carry two dates: the
period a value describes (`occurred_at`) and when it became available
(`available_at`). For a stop at date d this uses ONLY observations with
`available_at <= d`, so release timing is respected and nothing published
after the stop is read. What it cannot respect is revision: the values are as
currently published, not the vintage a reader saw then. CPI (not seasonally
adjusted) is not revised; unemployment and earnings are, modestly. That is
stated on the page every time.

It is labelled RECONSTRUCTED everywhere it appears and is never counted as a
state the engine published at the time.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Optional

#: The kinds a stop is placed by. Each is a published monthly statistic.
KINDS = ("treasury_10y", "inflation", "labour", "wages")
#: What each kind IS, in the reader's words. "labour up at 3.9 %" read as
#: the labour market rising when it is the unemployment rate.
PLAIN_NAMES = {"treasury_10y": "the 10-year Treasury yield",
               "inflation": "the consumer price index",
               "labour": "the unemployment rate",
               "wages": "average hourly earnings"}
REVISION_NOTE = ("reconstructed today from values as currently published; "
                 "release timing respected, later revisions not excluded")


def reconstruct_at(runtime_root, iso_date: str) -> Optional[object]:
    """A context-shaped reading as of `iso_date`, or None. Never raises."""
    try:
        from intent_engine.econ import store as EST
        rows = EST.load(runtime_root, "node")
    except Exception:                                      # noqa: BLE001
        return None
    by_kind = {}
    for row in rows or ():
        if not isinstance(row, dict) or row.get("kind") not in KINDS:
            continue
        available = str(row.get("available_at") or "")[:10]
        if not available or available > iso_date:
            continue
        by_kind.setdefault(row["kind"], []).append(row)
    conditions, newest = {}, ""
    for kind, items in by_kind.items():
        items.sort(key=lambda r: (str(r.get("occurred_at") or ""),
                                  str(r.get("available_at") or "")))
        last = items[-1]
        prior = next((r for r in reversed(items[:-1])
                      if str(r.get("occurred_at") or "")
                      < str(last.get("occurred_at") or "")), None)
        direction = ""
        if prior is not None and isinstance(last.get("value"), (int, float)) \
                and isinstance(prior.get("value"), (int, float)):
            direction = ("UP" if last["value"] > prior["value"] else
                         "DOWN" if last["value"] < prior["value"] else "FLAT")
        conditions[kind] = {"known": True, "direction": direction,
                            "value": last.get("value"),
                            "unit": last.get("unit") or "",
                            "as_of": str(last.get("occurred_at") or "")[:10],
                            "available_at": str(last.get("available_at"))[:10]}
        newest = max(newest, str(last.get("available_at") or "")[:10])
    if not conditions:
        return None
    return SimpleNamespace(available=True, reconstructed=True, area="US",
                           as_of=newest, conditions=conditions, shocks=(),
                           note=REVISION_NOTE, plain_names=PLAIN_NAMES)
