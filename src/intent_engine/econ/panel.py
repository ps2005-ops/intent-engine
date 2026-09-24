"""§6/§7: the canonical historical observation panel, vintage-correct.

WHY A PANEL AND NOT JUST THE NODE STORE
---------------------------------------
The evidence store answers "what do we know". A forecasting experiment needs
"what did we know ON DATE T", repeatedly, for hundreds of T. Those are
different access patterns, and building the second out of the first by
filtering on every read is how a replay becomes too slow to run and therefore
never runs.

So the panel is a dense (date x series) structure built ONCE from vintage
observations, with the vintage carried per cell rather than per file.

THE ONE RULE
------------
`as_known_at(t)` may only return values whose `vintage_at <= t`. Not
`observed_at <= t` -- that is the mistake that looks correct and leaks
anyway. An observation FOR June 2008 published in September 2008 is not
knowable in July 2008, and a wall keyed on the reference date lets it
through.

Both dates are stored on every cell for exactly this reason, and
`assert_no_leak` is a real function that a replay calls rather than a
principle a replay respects.

WHY MISSING IS A VALUE
----------------------
A cell can be absent for three different reasons: the series had not started,
the figure was not yet published, or the publisher skipped the period. They
support different decisions, so `Cell.absence` names which one it is instead
of leaving a hole that reads as zero.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_panel.v1"

NOT_STARTED = "NOT_STARTED"
NOT_YET_PUBLISHED = "NOT_YET_PUBLISHED"
SKIPPED = "SKIPPED"
ABSENCES = (NOT_STARTED, NOT_YET_PUBLISHED, SKIPPED)


class VintageLeak(EconError):
    """A value was read that was not knowable at the time it was read for."""


#: How a cell's vintage was established. The difference matters: a
#: PUBLISHER_VINTAGE cell was served by ALFRED as the value in force on that
#: date; a MEASURED_STABLE cell carries today's value on the strength of a
#: recorded revision measurement. Only the second can be wrong, and only if
#: the measurement did not cover the window -- which is why the basis is a
#: field and not a comment.
PUBLISHER_VINTAGE = "PUBLISHER_VINTAGE"
MEASURED_STABLE = "MEASURED_STABLE"
ASSUMED_LAG = "ASSUMED_LAG"
REVISION_STATES = (PUBLISHER_VINTAGE, MEASURED_STABLE, ASSUMED_LAG)


@dataclass(frozen=True)
class Cell:
    """One observation of one series, with all of its dates.

    §3 requires eight fields per observation and this is them. The three
    added ones are not bookkeeping:

      `released_at`   when the publisher first put the period out. Distinct
                      from `vintage_at`, which is when THIS value was in
                      force. For a first print they coincide; for a revision
                      the release date stays put and the vintage moves.
      `frequency`     so a quarterly series can be refused at monthly
                      resolution instead of being silently interpolated.
      `revision_state` how the vintage was established -- see above. The
                      panel-level guard reads this field, so "no assumed-lag
                      cell for a revising series" is checkable rather than
                      merely intended.
    """

    series_id: str
    observed_at: str          # the period the figure describes
    vintage_at: str           # when THIS value became the one in force
    value: float
    unit: str = ""
    kind: str = ""
    node_class: str = ""
    #: When the period was FIRST published. Empty when unknown, which is
    #: itself informative and is not silently filled in with the vintage.
    released_at: str = ""
    frequency: str = ""
    source: str = ""
    revision_state: str = ""

    def __post_init__(self) -> None:
        require(self.vintage_at >= self.observed_at,
                f"{self.series_id} {self.observed_at}: vintage "
                f"{self.vintage_at} precedes the period it describes; a "
                "figure cannot be published before the month it measures")
        if self.revision_state:
            require(self.revision_state in REVISION_STATES,
                    f"{self.series_id}: unknown revision state "
                    f"{self.revision_state!r}")

    def knowable_at(self, t: str) -> bool:
        return self.vintage_at <= t


@dataclass
class Panel:
    """Every observation, indexed for repeated as-of reads."""

    cells: Dict[str, List[Cell]] = field(default_factory=dict)

    def add(self, cell: Cell) -> "Panel":
        self.cells.setdefault(cell.series_id, []).append(cell)
        return self

    def add_nodes(self, nodes: Iterable) -> "Panel":
        """Fold evidence nodes into the panel.

        Reads `available_at` as the vintage. A node whose availability was
        assumed from a publication lag is still usable -- the assumption is
        recorded on the node's provenance -- but a node with no availability
        at all is refused, because a cell with no vintage cannot be walled.
        """
        for n in nodes:
            v = getattr(n, "available_at", "")
            o = getattr(n, "occurred_at", "")
            val = getattr(n, "value", None)
            if val is None or not o:
                continue
            if not v:
                raise VintageLeak(
                    f"{getattr(n, 'node_id', '?')} has no available_at; a "
                    "cell with no vintage cannot be walled, and admitting it "
                    "would make every as-of read silently wrong for it")
            self.add(Cell(
                series_id=getattr(n.provenance, "document_id", "") or n.kind,
                observed_at=o, vintage_at=v, value=float(val),
                unit=getattr(n, "unit", ""), kind=getattr(n, "kind", ""),
                node_class=getattr(n, "node_class", "")))
        return self

    def finalise(self) -> "Panel":
        """Sort, and build the (series, period) -> vintages index.

        WHY AN INDEX AND NOT A SCAN. `history()` originally found the
        periods by scanning a series' cells, then called
        `latest_vintage_of` per period, which scanned them again -- O(cells^2)
        per call. On the real panel that is 1.5s for ONE call to a series with
        73,000 cells, and the experiment makes 115 x 23 of them: 68 minutes,
        measured, not estimated. The index makes the same call ~0.001s.

        The cost is one pass at load and a dict the size of the panel, which
        is the right trade for a structure whose entire purpose is repeated
        as-of reads.
        """
        self._index = {}
        for sid in self.cells:
            self.cells[sid].sort(key=lambda c: (c.observed_at, c.vintage_at))
            per_period: Dict[str, List[Cell]] = {}
            for c in self.cells[sid]:
                per_period.setdefault(c.observed_at, []).append(c)
            # Each period's revisions, oldest vintage first.
            for period in per_period:
                per_period[period].sort(key=lambda c: c.vintage_at)
            self._index[sid] = per_period
        return self

    def _periods(self, series_id: str) -> Dict[str, List[Cell]]:
        idx = getattr(self, "_index", None)
        if idx is None:
            self.finalise()
            idx = self._index
        return idx.get(series_id, {})

    # --- reading ------------------------------------------------------------
    @property
    def series_ids(self) -> List[str]:
        return sorted(self.cells)

    def latest_vintage_of(self, series_id: str, period: str,
                          as_of: str) -> Optional[Cell]:
        """The most recent revision of `period` that was knowable by `as_of`."""
        revisions = self._periods(series_id).get(period)
        if not revisions:
            return None
        best = None
        # Sorted oldest-first, so the last knowable one wins.
        for c in revisions:
            if c.vintage_at <= as_of:
                best = c
            else:
                break
        return best

    def as_known_at(self, as_of: str, *, series: Sequence[str] = ()
                    ) -> Dict[str, Cell]:  # noqa: D401
        """The most recent knowable observation of each series, at `as_of`.

        The core primitive. Everything a replay reads goes through here, so
        there is exactly one place the wall can be wrong.
        """
        wanted = list(series) if series else self.series_ids
        out: Dict[str, Cell] = {}
        for sid in wanted:
            best = None
            for c in self.cells.get(sid, ()):
                if not c.knowable_at(as_of):
                    continue
                if best is None or (c.observed_at, c.vintage_at) > (
                        best.observed_at, best.vintage_at):
                    best = c
            if best is not None:
                out[sid] = best
        return out

    def absence(self, series_id: str, as_of: str) -> str:
        """Why a series has no value at `as_of`."""
        cells = self.cells.get(series_id, ())
        if not cells:
            return NOT_STARTED
        if min(c.observed_at for c in cells) > as_of:
            return NOT_STARTED
        if all(not c.knowable_at(as_of) for c in cells):
            return NOT_YET_PUBLISHED
        return SKIPPED

    def history(self, series_id: str, *, as_of: str,
                lookback: int = 0) -> List[Tuple[str, float]]:
        """The series as it stood at `as_of`, oldest first.

        For each period, the latest revision knowable by `as_of`. This is what
        a model would actually have had in front of it, revisions and all.
        """
        idx = self._periods(series_id)
        out = []
        for period in sorted(idx):
            if period > as_of:
                break
            c = self.latest_vintage_of(series_id, period, as_of)
            if c is not None:
                out.append((period, c.value))
        return out[-lookback:] if lookback else out

    # --- the wall -----------------------------------------------------------
    def assert_no_leak(self, as_of: str, used: Dict[str, Cell]) -> None:
        """Every value a model consumed must have been knowable."""
        leaked = [f"{sid} (vintage {c.vintage_at})"
                  for sid, c in used.items() if not c.knowable_at(as_of)]
        if leaked:
            raise VintageLeak(
                f"{len(leaked)} value(s) read at {as_of} were not knowable "
                f"then: {leaked[:5]}. A backtest that consumes these is "
                "reading revisions published later and reporting the result "
                "as a forecast.")

    def summarise(self) -> dict:
        total = sum(len(v) for v in self.cells.values())
        revised = 0
        for sid, cells in self.cells.items():
            seen: Dict[str, int] = {}
            for c in cells:
                seen[c.observed_at] = seen.get(c.observed_at, 0) + 1
            revised += sum(1 for n in seen.values() if n > 1)
        spans = {sid: (min(c.observed_at for c in cs),
                       max(c.observed_at for c in cs))
                 for sid, cs in self.cells.items() if cs}
        by_state: Dict[str, int] = {}
        for cs in self.cells.values():
            for c in cs:
                k = c.revision_state or "UNRECORDED"
                by_state[k] = by_state.get(k, 0) + 1
        return {"contract": CONTRACT, "series": len(self.cells),
                "cells": total,
                "content_hash": self.content_hash(),
                "cells_by_revision_state": by_state,
                "periods_with_more_than_one_vintage": revised,
                "earliest": min((s for s, _ in spans.values()), default=""),
                "latest": max((e for _, e in spans.values()), default=""),
                "spans": {k: list(v) for k, v in sorted(spans.items())}}

    # --- compaction ---------------------------------------------------------
    def compact(self) -> "Panel":
        """Drop cells that repeat the previous vintage's value, losslessly.

        WHY THIS IS SAFE, EXACTLY. `latest_vintage_of` returns the LAST cell
        for a period whose vintage is <= as_of. If vintages V1..V5 all carry
        the same value and V2..V5 are dropped, a read at V3 returns V1's cell
        -- same value, and a `vintage_at` that is the truthful "in force
        since". Every value any as-of read can return is unchanged. The one
        thing that changes is that `periods_with_more_than_one_vintage` stops
        counting re-prints and starts counting REVISIONS, which is the number
        anyone actually wanted.

        WHY IT IS NEEDED. A monthly vintage grid multiplies requests by three
        and cells by three, and a series like INDPRO carries its whole history
        back to 1919 in EVERY vintage. Uncompacted, the monthly panel is
        several gigabytes of mostly identical numbers and cannot be held in
        memory; compacted it is a few hundred megabytes, because a revision is
        rare and a re-print is not.
        """
        kept = 0
        for sid, cells in self.cells.items():
            cells.sort(key=lambda c: (c.observed_at, c.vintage_at))
            out, last_period, last_value = [], None, None
            for c in cells:
                if c.observed_at != last_period:
                    out.append(c)
                    last_period, last_value = c.observed_at, c.value
                    continue
                if last_value is not None and c.value == last_value:
                    continue          # same number, later vintage: no news
                out.append(c)
                last_value = c.value
            self.cells[sid] = out
            kept += len(out)
        self._index = None
        return self.finalise()

    # --- structural guards --------------------------------------------------
    def assert_no_assumed_lag(self, series_ids: Sequence[str]) -> None:
        """These series may not carry a cell whose vintage was assumed.

        The guard that would have caught the leaked panel. A series measured
        to revise must be represented by PUBLISHER_VINTAGE cells only; an
        ASSUMED_LAG cell for it carries today's number under a historical
        date, which is invisible in every summary and wrong in every read.
        """
        bad = []
        for sid in series_ids:
            for c in self.cells.get(sid, ()):
                if c.revision_state == ASSUMED_LAG:
                    bad.append(f"{sid} {c.observed_at}@{c.vintage_at}")
                    break
        if bad:
            raise VintageLeak(
                f"{len(bad)} series that revise carry assumed-lag cells: "
                f"{bad[:5]}. Those cells hold TODAY'S value under a "
                "historical date; every walled read of them is a leak that "
                "no summary will show.")

    def assert_frequency_honoured(self) -> None:
        """No quarterly series may appear at monthly resolution.

        §3's rule, checked against the cells rather than trusted. An
        interpolated month is not data: it adds a row, adds no information,
        and inflates every count computed downstream.
        """
        from . import release as _rel
        for sid, cells in self.cells.items():
            if not cells:
                continue
            freqs = {c.frequency for c in cells if c.frequency}
            if "QUARTERLY" not in freqs:
                continue
            _rel.refuse_interpolation(
                sid, sorted({c.observed_at for c in cells}))

    def content_hash(self) -> str:
        """A hash of the VALUES, independent of field order or file layout.

        The frozen V1 baseline recorded `panel_hash 6936e55e1eacd426` under a
        formula nobody wrote down, so when the panel was later overwritten
        there was no way to tell. This is the formula, in code, and
        `summarise()` reports it.
        """
        import hashlib
        h = hashlib.sha256()
        for sid in self.series_ids:
            h.update(sid.encode())
            for c in self.cells[sid]:
                h.update(f"|{c.observed_at}|{c.vintage_at}|{c.value!r}"
                         .encode())
        return h.hexdigest()[:16]

    # --- durability ---------------------------------------------------------
    def write(self, path) -> pathlib.Path:
        dest = pathlib.Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            for sid in self.series_ids:
                for c in self.cells[sid]:
                    fh.write(json.dumps({
                        "series_id": c.series_id, "observed_at": c.observed_at,
                        "vintage_at": c.vintage_at, "value": c.value,
                        "unit": c.unit, "kind": c.kind,
                        "node_class": c.node_class,
                        "released_at": c.released_at,
                        "frequency": c.frequency, "source": c.source,
                        "revision_state": c.revision_state},
                        sort_keys=True) + "\n")
        return dest

    @classmethod
    def read(cls, path) -> "Panel":
        p = cls()
        src = pathlib.Path(path)
        if not src.exists():
            return p
        for line in src.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            p.add(Cell(series_id=r["series_id"], observed_at=r["observed_at"],
                       vintage_at=r["vintage_at"], value=r["value"],
                       unit=r.get("unit", ""), kind=r.get("kind", ""),
                       node_class=r.get("node_class", ""),
                       released_at=r.get("released_at", ""),
                       frequency=r.get("frequency", ""),
                       source=r.get("source", ""),
                       revision_state=r.get("revision_state", "")))
        return p.finalise()
