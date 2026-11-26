"""History Rewind: the ORIGINAL grade beside an EXPANDED private-company grade.

The original rubric (qualify100.py) is untouched and reported first:
    A (filed multi-year financial series) = PASS; B or C = BOUNDED; else FAIL.
A private company can never reach A -- it files no series -- so the original
grade measures listing status as much as historical intelligence.

The EXPANDED grade is a separate, stated standard for a private company's
evidence-based rewind (level B). It is never merged into the original score:

  PASS     a bounded rewind with the hindsight wall PRESENT, >= 4 dated stops,
           a span >= 24 months between the earliest and latest dated record,
           and >= 1 stop carrying an economic reading published ON OR BEFORE
           that stop's date (vintage-safe, never today's state)
  BOUNDED  a bounded rewind with the wall present and >= 2 dated stops
  FAIL     anything less (or a missing hindsight wall, which is disqualifying)

Why these are equivalent in kind to level A's purpose: A exists so a reader
can stand at a past date, see what was knowable then, and compare it with
what followed. Four dated stops over two years with the wall held is that
exercise on the record a private company actually leaves; the economic
reading is the context A gets for free from a filed series' own dates.
What it is NOT: a financial series. No figure is reconstructed, and a stop
says what was published, not what management "forecast".

  python scripts/prospect100/resume/history_expanded.py ROUND_DIR [OUT.json]
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import pathlib
import sys

ORIGINAL = {"A": "PASS", "B": "BOUNDED", "C": "BOUNDED"}


def _months(a: str, b: str) -> int:
    try:
        x, y = dt.date.fromisoformat(a[:10]), dt.date.fromisoformat(b[:10])
    except ValueError:
        return 0
    return (y.year - x.year) * 12 + (y.month - x.month)


def expanded(history: dict) -> tuple:
    h = history or {}
    level = h.get("level")
    stops = int(h.get("stops") or 0)
    wall = h.get("hindsight_wall") == "PRESENT"
    span = _months(str(h.get("earliest") or ""), str(h.get("latest") or ""))
    econ = int(h.get("economic_links") or 0)
    # Reconstructed readings (official statistics as released by the stop's
    # date, rebuilt today) are counted SEPARATELY and named in the reason: they
    # respect release timing and are labelled on the page, but they are not a
    # state the engine published at the time.
    rebuilt = int((h.get("econ_states") or {}).get(
        "ECONOMIC_CONTEXT_RECONSTRUCTED", 0) or 0)
    if level == "A":
        return "PASS", "a filed multi-year series (original level A)"
    if level != "B" or not wall:
        return "FAIL", ("no bounded rewind" if level != "B"
                        else "hindsight wall missing")
    missing = [w for w, ok in (
        (f"{stops} dated stop(s) of 4", stops >= 4),
        (f"a {span}-month span of 24", span >= 24),
        ("no economic reading placed on any stop", econ + rebuilt >= 1))
        if not ok]
    if not missing:
        basis = (f"{econ} published" if econ else "") + \
                (" and " if econ and rebuilt else "") + \
                (f"{rebuilt} reconstructed (release-timed)" if rebuilt else "")
        return "PASS", f"{stops} stops over {span} months; economy: {basis}"
    if stops >= 2:
        return "BOUNDED", "; ".join(missing)
    return "FAIL", "; ".join(missing)


def main() -> int:
    root = pathlib.Path(sys.argv[1])
    rows = []
    for f in sorted(root.glob("s[0-9]*/state.json")):
        rows += [r for r in json.loads(f.read_text())["rows"].values()
                 if r.get("final_class")]
    table, orig, exp = [], collections.Counter(), collections.Counter()
    for r in sorted(rows, key=lambda r: r.get("n") or 0):
        h = r.get("history") or {}
        lvl = h.get("level") or r.get("history_level")
        o = ORIGINAL.get(lvl, "FAIL")
        e, why = expanded(h)
        orig[o] += 1
        exp[e] += 1
        table.append({"prospect_id": r.get("n"), "company": r["company"],
                      "level": lvl, "original": o, "expanded": e, "why": why,
                      "stops": h.get("stops"), "earliest": h.get("earliest"),
                      "latest": h.get("latest"),
                      "economic_links": h.get("economic_links"),
                      "reconstructed_links": (h.get("econ_states") or {}).get(
                          "ECONOMIC_CONTEXT_RECONSTRUCTED", 0),
                      "econ_states": h.get("econ_states")})
    summary = {"original": dict(orig), "expanded": dict(exp),
               "blocking_reasons": dict(collections.Counter(
                   part.split(" of ")[0].split(" on ")[0].lstrip("0123456789 ")
                   for t in table if t["expanded"] != "PASS"
                   for part in t["why"].split("; ")).most_common(6))}
    print(json.dumps(summary, indent=1))
    if len(sys.argv) > 2:
        pathlib.Path(sys.argv[2]).write_text(json.dumps(
            {"summary": summary, "companies": table}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
