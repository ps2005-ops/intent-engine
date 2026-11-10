"""When it happened, when it was published, and when we looked.

WHY THREE FIELDS AND NOT ONE
----------------------------
Every competitive action carried `event_time = document.retrieved_at`. Across
23 live actions there was exactly ONE distinct timestamp — the day of the
fetch. Nothing complained, because nothing had yet tried to ORDER actions.
The moment it did, a timeline would have sorted them by the order we happened
to download pages and would have been indistinguishable from a real history
of competitive reactions.

    occurred_at   when the actor did the thing
    published_at  when somebody wrote it down
    retrieved_at  when we fetched the page

Only the first belongs on a strategic timeline. The second is a usable upper
bound when the first is absent. The third is PROVENANCE and is never either.

WHY UNKNOWN IS A FIRST-CLASS ANSWER
-----------------------------------
"On June 12 we launched X", published June 14, read August 8, is three
different dates and the engine has to keep all three. A page that says only
"we recently launched X" establishes NEITHER an occurrence date nor a
publication one, and the honest answer is UNKNOWN. Defaulting it to the
retrieval date is how the original defect got in — the available number
substituted for the missing one, silently, and looked like data.
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

CONTRACT = "occurrence_time.v1"

# --- how well we know when it happened --------------------------------------
EXACT = "EXACT"                                   # a full date, stated
DATE_ONLY = "DATE_ONLY"                           # a day, no time
INFERRED_FROM_PUBLICATION = "INFERRED_FROM_PUBLICATION"
UNKNOWN = "UNKNOWN"

STANDINGS = (EXACT, DATE_ONLY, INFERRED_FROM_PUBLICATION, UNKNOWN)

#: Standings a strategic timeline may be ordered by. `INFERRED_FROM_
#: PUBLICATION` is included because a publication date is a real upper bound
#: on the occurrence — the thing happened at or before it was written about.
ORDERABLE = frozenset({EXACT, DATE_ONLY, INFERRED_FROM_PUBLICATION})

_MONTHS = ("january|february|march|april|may|june|july|august|september|"
           "october|november|december")

#: "On June 12, 2026, we launched", "Starting June 1, 2026"
_LONG_DATE = re.compile(
    r"\b(?P<month>" + _MONTHS + r")\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?"
    r"(?:,\s*|\s+)(?P<year>\d{4})\b", re.I)

#: ISO, as changelogs and structured metadata carry it.
_ISO = re.compile(r"\b(?P<year>20\d{2})-(?P<month>\d{2})-(?P<day>\d{2})\b")

#: Words that make a date a FUTURE commitment rather than a past act.
_FUTURE = re.compile(
    r"\b(?:will|going\s+to|plans?\s+to|coming\s+soon|next\s+(?:quarter|year|"
    r"month)|from\s+\w+\s+onwards?|starting|beginning|effective)\b", re.I)

#: Vague recency, which establishes no date at all.
_VAGUE = re.compile(
    r"\b(?:recently|last\s+(?:month|quarter|year|week)|earlier\s+this\s+"
    r"(?:year|quarter)|some\s+time\s+ago|in\s+the\s+past)\b", re.I)

#: A changelog index prefixes each entry with its own date and no year:
#: "08.03Oxygen is now available", "06.17WhatsApp marketing consent now
#: available". Anchored to the page's publication year, and required to sit
#: at the START of the entry immediately before a capital, which is what
#: separates it from a version number or a price in running text.
_ENTRY_PREFIX = re.compile(r"^(?P<month>0[1-9]|1[0-2])\.(?P<day>0[1-9]|[12]\d|3[01])(?=[A-Z])")


def _entry_prefix_date(text: str, published_at: str) -> Tuple[str, str]:
    """A dateless MM.DD entry marker, given a year to hang it on.

    Without a publication date there is no year and therefore no date: an
    entry marked 06.17 could be any June 17 in the site's history, and
    guessing the current year is the same substitution this module exists
    to prevent.
    """
    hit = _ENTRY_PREFIX.match(text or "")
    if not hit or not published_at:
        return "", ""
    year = published_at[:4]
    got = _iso(year, hit.group("month"), hit.group("day"))
    if not got:
        return "", ""
    # A marker LATER in the year than the page's publication date is
    # ambiguous, and rolling it back a year is a guess dressed as data.
    #
    # Measured live: shopify.dev/changelog reports modified_date 2026-07-21
    # while its newest entry is marked 08.03, so the metadata is older than
    # the page's own content. Assuming "previous year" turned an August 2026
    # entry into August 2025 — a fabricated date, on the exact axis a
    # timeline is ordered by. Refusing costs coverage; guessing costs the
    # timeline its meaning.
    if got > published_at[:10]:
        return "", ""
    return got, hit.group(0)


_MONTH_INDEX = {name: i + 1 for i, name in enumerate(_MONTHS.split("|"))}


@dataclass(frozen=True)
class ActionTime:
    """Three dates and how much the first one is worth."""
    occurred_at: str = ""
    published_at: str = ""
    retrieved_at: str = ""
    standing: str = UNKNOWN
    is_future: bool = False
    evidence: str = ""

    @property
    def orderable(self) -> bool:
        """Whether a timeline may sort by this at all.

        A future commitment is NOT orderable as an occurrence: "we will
        launch in Q4" has not happened, and placing it on a history of what
        rivals did would record an intention as an act.
        """
        return self.standing in ORDERABLE and not self.is_future

    @property
    def best_effort(self) -> str:
        """The date a timeline should sort on, or "" if there is none."""
        if not self.orderable:
            return ""
        return self.occurred_at or self.published_at

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "occurred_at": self.occurred_at,
            "published_at": self.published_at,
            "retrieved_at": self.retrieved_at, "standing": self.standing,
            "is_future": self.is_future, "orderable": self.orderable,
            "evidence": self.evidence,
        }


def _iso(year: str, month: str, day: str) -> str:
    try:
        return _dt.date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return ""


def _dates_in(text: str) -> Tuple[str, str]:
    """The first stated date in the text, and the span that stated it."""
    hit = _LONG_DATE.search(text or "")
    if hit:
        month = _MONTH_INDEX.get(hit.group("month").lower(), 0)
        got = _iso(hit.group("year"), str(month), hit.group("day"))
        if got:
            return got, hit.group(0)
    hit = _ISO.search(text or "")
    if hit:
        got = _iso(hit.group("year"), hit.group("month"), hit.group("day"))
        if got:
            return got, hit.group(0)
    return "", ""


def read(span: str, *, retrieved_at: str, published_at: str = "") -> ActionTime:
    """Read an action's three dates off its own sentence and its metadata.

    `retrieved_at` is recorded and NEVER promoted. That substitution is the
    defect this module exists to make impossible.
    """
    text = " ".join((span or "").split())
    published = (published_at or "")[:10]
    stated, evidence = _entry_prefix_date(text, published)
    entry_dated = bool(stated)
    if not stated:
        stated, evidence = _dates_in(text)
    future = bool(_FUTURE.search(text))

    if stated and not future:
        # A changelog marker gives a day and borrows its year, so it is
        # DATE_ONLY rather than EXACT: the day is stated, the year is not.
        return ActionTime(occurred_at=stated, published_at=published,
                          retrieved_at=retrieved_at[:10],
                          standing=DATE_ONLY if entry_dated else EXACT,
                          is_future=False, evidence=evidence)
    if stated and future:
        # A dated FUTURE commitment. The DATE is real and the EVENT has not
        # happened, so the precision is kept and `is_future` is what stops
        # it reaching a history. Collapsing this to UNKNOWN would throw away
        # a true date and make the is_future guard unreachable — the shape
        # this project has had to delete twice.
        return ActionTime(occurred_at="", published_at=published,
                          retrieved_at=retrieved_at[:10],
                          standing=DATE_ONLY if entry_dated else EXACT,
                          is_future=True,
                          evidence=f"{evidence} (stated as forthcoming)")
    if _VAGUE.search(text):
        return ActionTime(occurred_at="", published_at=published,
                          retrieved_at=retrieved_at[:10], standing=UNKNOWN,
                          evidence="the text places this only vaguely in "
                                   "the past")
    if published:
        # The publication bounds the occurrence from above: it happened at
        # or before somebody wrote about it.
        return ActionTime(occurred_at="", published_at=published,
                          retrieved_at=retrieved_at[:10],
                          standing=INFERRED_FROM_PUBLICATION,
                          evidence="no date in the text; the publication "
                                   "date bounds it from above")
    return ActionTime(occurred_at="", published_at="",
                      retrieved_at=retrieved_at[:10], standing=UNKNOWN,
                      evidence="neither the text nor the page states a date")


def summarise(times: Sequence[ActionTime]) -> dict:
    from collections import Counter
    by_standing = Counter(t.standing for t in times)
    orderable = [t for t in times if t.orderable]
    dates = {t.best_effort for t in orderable} - {""}
    return {
        "contract": CONTRACT,
        "actions": len(times),
        "by_standing": {s: by_standing.get(s, 0) for s in STANDINGS
                        if by_standing.get(s, 0)},
        "orderable": len(orderable),
        "future_commitments": sum(1 for t in times if t.is_future),
        "distinct_orderable_dates": len(dates),
        "note": ("retrieved_at is provenance and is never promoted to an "
                 "occurrence. A corpus whose distinct orderable dates number "
                 "one is not a timeline."),
    }
