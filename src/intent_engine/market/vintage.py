"""What was knowable at time T, and nothing else.

WHY A REPLAY NEEDS A WALL AND NOT A FILTER
------------------------------------------
Historical replay is the only route to testing V4's causal hypotheses on a
useful timescale: the live ones resolve in months. But a replay that can see
one row it should not is worse than no replay, because it produces a
confident, wrong number and there is nothing in the output that says so.

So this is a wall, not a convenience. Reading past the vintage raises. It does
not warn, drop, or return an empty result — each of those lets a caller carry
on with a partial answer that looks like a complete one.

THE DISTINCTION THAT DOES THE WORK
----------------------------------
A row is visible at T when it was KNOWN by T, not when it HAPPENED by T.

Those come apart constantly and the difference is exactly the leak. A company
signed a contract on the 3rd; the press release appeared on the 11th. An engine
replaying the 5th and filtering on occurrence time sees the contract, forms a
thesis that depends on it, and scores well — on information nobody had. The
engine would not have known.

This project has already been bitten by the inverse: actions inherited the
RETRIEVAL date, so occurrence time was silently the observation time and 23
records shared one timestamp. That defect made occurrence unusable; this one
makes observation load-bearing. Both are the same lesson from opposite sides,
which is why the wall demands both fields and refuses a row carrying neither.

WHAT "UNKNOWN" MEANS HERE
-------------------------
A row with no observation time cannot be placed on either side of the wall. It
is EXCLUDED and counted, never admitted on the grounds that it is probably old
enough. A replay that admits undated rows is a replay whose vintage is a
guess, and the count is reported so a caller can see how much of the corpus
that was.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

CONTRACT = "vintage.v1"

#: Fields that carry WHEN THE ENGINE LEARNED a row, most trustworthy first.
#: `observed_at` is the canonical one; the others exist on older records.
OBSERVATION_FIELDS = ("observed_at", "first_seen_at", "retrieved_at",
                      "created_at", "chosen_at")

#: Fields that carry WHEN THE THING HAPPENED. Never used for admission — only
#: reported, so a caller can see the publication lag they are living with.
OCCURRENCE_FIELDS = ("occurred_at", "published_at", "event_date", "as_of")


class VintageViolation(AssertionError):
    """A read that would have used information nobody had yet."""


def _first(row: dict, fields: Sequence[str]) -> str:
    for name in fields:
        value = row.get(name)
        if value:
            return str(value)[:19]
    return ""


def observation_time(row: dict) -> str:
    return _first(row, OBSERVATION_FIELDS)


def occurrence_time(row: dict) -> str:
    return _first(row, OCCURRENCE_FIELDS)


@dataclass(frozen=True)
class Vintage:
    """The state of knowledge as of one instant.

    `admitted` is what the engine had. `withheld_not_yet_known` is what
    existed but had not been observed — the rows a naive occurrence-time
    filter would have leaked, counted so the size of the avoided error is
    visible rather than assumed to be small.
    """

    as_of: str
    admitted: Tuple[dict, ...]
    withheld_not_yet_known: Tuple[dict, ...] = ()
    withheld_undated: Tuple[dict, ...] = ()

    @property
    def leak_surface(self) -> int:
        """How many rows an occurrence-time filter would have admitted."""
        return sum(1 for r in self.withheld_not_yet_known
                   if occurrence_time(r) and occurrence_time(r) <= self.as_of)

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "as_of": self.as_of,
            "admitted": len(self.admitted),
            "withheld_not_yet_known": len(self.withheld_not_yet_known),
            "withheld_undated": len(self.withheld_undated),
            "leak_surface": self.leak_surface,
            "note": ("leak_surface is the number of rows that had already "
                     "HAPPENED by as_of but had not been OBSERVED by then; a "
                     "replay filtering on occurrence time would have used "
                     "every one of them"),
        }


def freeze(rows: Iterable[dict], *, as_of: str) -> Vintage:
    """Partition a corpus into what was known at `as_of` and what was not."""
    if not as_of:
        raise VintageViolation(
            "a vintage needs an instant; freezing at an unspecified time "
            "admits everything, which is the leak this exists to stop")
    cut = str(as_of)[:19]
    admitted: List[dict] = []
    later: List[dict] = []
    undated: List[dict] = []
    for row in rows:
        seen = observation_time(row)
        if not seen:
            undated.append(row)
        elif seen <= cut:
            admitted.append(row)
        else:
            later.append(row)
    return Vintage(as_of=cut, admitted=tuple(admitted),
                   withheld_not_yet_known=tuple(later),
                   withheld_undated=tuple(undated))


class VintageWall:
    """A read-through guard. Every access is checked, not just the first.

    Held as an object rather than applied once as a filter because a replay
    makes many reads over its lifetime, and the one that leaks is always the
    one added later by someone who did not know the filter existed.
    """

    def __init__(self, rows: Sequence[dict], *, as_of: str,
                 label: str = "replay"):
        self.as_of = str(as_of)[:19]
        self.label = label
        self._vintage = freeze(rows, as_of=as_of)
        self._reads = 0

    @property
    def vintage(self) -> Vintage:
        return self._vintage

    @property
    def reads(self) -> int:
        return self._reads

    def rows(self, *, record: str = "") -> Tuple[dict, ...]:
        """Everything known at the wall's instant, optionally by kind."""
        self._reads += 1
        got = self._vintage.admitted
        if record:
            got = tuple(r for r in got if r.get("record") == record)
        return got

    def at(self, when: str) -> "VintageWall":
        """A wall at an EARLIER instant. Moving forward is refused.

        A replay walks forward through time by construction, so the natural
        mistake is to advance the wall and keep reading — which is not a
        replay any more, it is a lookahead with extra steps. Widening the
        window has to be an explicit new wall built from the full corpus, so
        it appears in a diff.
        """
        target = str(when)[:19]
        if target > self.as_of:
            raise VintageViolation(
                f"{self.label}: cannot move the wall forward from "
                f"{self.as_of} to {target}; a replay that advances its own "
                "vintage is reading the future one step at a time")
        rows = self._vintage.admitted + self._vintage.withheld_not_yet_known
        return VintageWall(rows, as_of=target, label=self.label)

    def check(self, row: dict) -> dict:
        """Assert one row was knowable. Raises rather than filtering.

        Used where a row arrives from somewhere the wall did not hand it out —
        a cache, a join, a helper that took the full corpus. That is where
        leaks actually come from.
        """
        seen = observation_time(row)
        if not seen:
            raise VintageViolation(
                f"{self.label}: a row with no observation time cannot be "
                f"placed against the {self.as_of} wall; admitting it would "
                "make the vintage a guess "
                f"({str(row.get('record') or row)[:80]})")
        if seen > self.as_of:
            happened = occurrence_time(row)
            raise VintageViolation(
                f"{self.label}: row observed {seen} is after the "
                f"{self.as_of} wall"
                + (f" (it occurred {happened}, so an occurrence-time filter "
                   "would have admitted it — that is the leak)"
                   if happened and happened <= self.as_of else "")
                + "; nobody knew this yet")
        return row

    def guard(self, rows: Iterable[dict]) -> Tuple[dict, ...]:
        """Assert an entire sequence was knowable."""
        return tuple(self.check(r) for r in rows)

    def as_dict(self) -> dict:
        out = self._vintage.as_dict()
        out.update(label=self.label, reads=self._reads)
        return out


def episodes(rows: Sequence[dict], *, starting: str, ending: str,
             every_days: int = 30, minimum_rows: int = 1) -> List[str]:
    """Candidate replay instants, chosen WITHOUT looking at any outcome.

    Deterministic by construction: a fixed cadence over a stated window, kept
    only where the vintage holds enough rows to build a state from. Selection
    never reads what happened next, because an episode list filtered by
    interestingness is a list of episodes the engine already knows the answer
    to.
    """
    import datetime as _dt

    try:
        start = _dt.date.fromisoformat(str(starting)[:10])
        end = _dt.date.fromisoformat(str(ending)[:10])
    except ValueError as exc:
        raise VintageViolation(f"episode window is not a date range: {exc}")
    if every_days <= 0:
        raise VintageViolation("an episode cadence must be positive")
    out: List[str] = []
    cursor = start
    while cursor <= end:
        stamp = cursor.isoformat()
        if len(freeze(rows, as_of=stamp).admitted) >= minimum_rows:
            out.append(stamp)
        cursor += _dt.timedelta(days=every_days)
    return out
