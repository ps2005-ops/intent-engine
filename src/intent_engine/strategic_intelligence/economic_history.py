"""What happened last time conditions looked like this — and whether we are
entitled to say it.

THE DEFECT THIS CLOSES. `historical_playback` is read by the X-Ray and by the
presentation and was written by NOTHING. Both surfaces carried a hardcoded
sentence explaining its absence, so the product asserted, in prose, a fact
about a producer that did not exist. That is the same shape as the bare
independent-origin zero and the bare evidence family: a consumer wired to a
field nobody fills.

WHY A REPLAY IS NOT A LOOKUP
----------------------------
A chief executive asking "what happened last time?" is asking whether the
mechanism we are predicting has been observed to work before. Answering it by
reading today's record of an earlier period is not history, it is hindsight
wearing a date. The company's later results, the revised macro series, and the
filings published after the fact are all things nobody could have known at the
historical decision point — and every one of them makes a replayed decision
look better than it was.

So a replay is only valid when the system HELD ITS OWN OBSERVATIONS at the
historical date. That is a fact about our archive, not about the company, and
for a young archive the honest answer is that no replay is possible yet.

THREE STATES, AND ONLY ONE OF THEM IS A REPLAY
----------------------------------------------
    HISTORICAL_REPLAY_AVAILABLE   we held observations at T0 and can show
                                  what was believed then against what happened
    DESCRIPTIVE_HISTORY_ONLY      we can describe the period from the record
                                  as it stands today, and say so plainly
    HISTORICAL_REPLAY_BLOCKED_DATA  not enough archive depth yet, with the
                                  date on which that stops being true

A reader must never have to work out which of these they are looking at, and
the blocked case still has to be useful — the months we hold, the months we
need, and when it clears.
"""
from __future__ import annotations

import datetime as _dt
from typing import Dict, Sequence

CONTRACT = "economic_history.v1"

HISTORICAL_REPLAY_AVAILABLE = "HISTORICAL_REPLAY_AVAILABLE"
DESCRIPTIVE_HISTORY_ONLY = "DESCRIPTIVE_HISTORY_ONLY"
HISTORICAL_REPLAY_BLOCKED_DATA = "HISTORICAL_REPLAY_BLOCKED_DATA"

HISTORY_STATES = (HISTORICAL_REPLAY_AVAILABLE, DESCRIPTIVE_HISTORY_ONLY,
                  HISTORICAL_REPLAY_BLOCKED_DATA)

#: Only this state may present a belief as having been held BEFORE the outcome.
SUPPORTS_REPLAY = frozenset({HISTORICAL_REPLAY_AVAILABLE})

#: A replay needs enough distance for an outcome to have resolved. Six months
#: is the shortest window over which a strategic mechanism shows up in results
#: at all; below it we would be scoring noise and calling it a track record.
MIN_REPLAY_MONTHS = 6

#: And it needs more than one observation, or the "belief at T0" is a single
#: document rather than a position the system held.
MIN_EPISODE_OBSERVATIONS = 2

# --- luck discipline (§17) -----------------------------------------------------
#
# A right answer for the wrong reason is not intelligence, and scoring it as a
# hit is how a system learns to be lucky. Outcome and mechanism are scored
# SEPARATELY and neither is allowed to stand in for the other.
MECHANISM_CONFIRMED = "MECHANISM_CONFIRMED"
MECHANISM_CONTRADICTED = "MECHANISM_CONTRADICTED"
MECHANISM_UNRESOLVED = "MECHANISM_UNRESOLVED"

OUTCOME_AS_EXPECTED = "OUTCOME_AS_EXPECTED"
OUTCOME_AGAINST = "OUTCOME_AGAINST"
OUTCOME_UNRESOLVED = "OUTCOME_UNRESOLVED"

#: The four readings a reader actually needs to tell apart.
RIGHT_FOR_THE_RIGHT_REASON = "RIGHT_FOR_THE_RIGHT_REASON"
RIGHT_FOR_THE_WRONG_REASON = "RIGHT_FOR_THE_WRONG_REASON"
WRONG_BUT_SOUND = "WRONG_BUT_SOUND"
UNRESOLVED = "UNRESOLVED"


def _date(value):
    try:
        return _dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _months_between(earlier: _dt.date, later: _dt.date) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def judge(*, mechanism: str, outcome: str) -> str:
    """Which of the four readings this episode is. Never collapses them.

    A confirmed outcome with a contradicted mechanism is the single most
    dangerous row in a track record, because it is indistinguishable from
    skill if the two axes are averaged into one score.
    """
    if outcome == OUTCOME_UNRESOLVED or mechanism == MECHANISM_UNRESOLVED:
        return UNRESOLVED
    if outcome == OUTCOME_AS_EXPECTED:
        return (RIGHT_FOR_THE_RIGHT_REASON if mechanism == MECHANISM_CONFIRMED
                else RIGHT_FOR_THE_WRONG_REASON)
    return (WRONG_BUT_SOUND if mechanism == MECHANISM_CONFIRMED
            else UNRESOLVED)


def observations_known_by(observations: Sequence[dict], t0) -> list:
    """THE VINTAGE WALL. Only what the system had actually observed by T0.

    Filters on OBSERVED_AT -- when we recorded it -- not on any date inside
    the document. A filing about 2019 that we first read last week was not
    available at a 2019 decision point, and admitting it is precisely the
    hindsight leak that makes a replay worthless.

    An observation with no recorded observation time is EXCLUDED. That is
    deliberately the strict direction: including an undated row would let a
    single missing timestamp reopen the whole future.
    """
    cutoff = _date(t0)
    if cutoff is None:
        return []
    kept = []
    for row in observations or ():
        seen = _date((row or {}).get("observed_at"))
        if seen is not None and seen <= cutoff:
            kept.append(row)
    return kept


def assess(*, observations: Sequence[dict] = (), episodes: Sequence[dict] = (),
           today=None) -> Dict[str, object]:
    """Which of the three states this company's history is in, and why.

    MEASURED FROM THE ARCHIVE, NEVER SET. Every branch below is a fact about
    what we hold: how far back our own observations go, how many of them there
    are, and whether enough time has passed for an outcome to resolve.
    """
    now = _date(today) or _dt.date.today()
    seen = sorted(d for d in
                  (_date((o or {}).get("observed_at")) for o in observations or ())
                  if d is not None)
    have_months = _months_between(seen[0], now) if seen else 0
    earliest = seen[0].isoformat() if seen else ""

    # The date on which a replay becomes possible, stated so a reader is not
    # left wondering whether this is permanent.
    next_eligible = ""
    if seen:
        first = seen[0]
        month = first.month - 1 + MIN_REPLAY_MONTHS
        next_eligible = _dt.date(first.year + month // 12, month % 12 + 1,
                                 min(first.day, 28)).isoformat()

    base = {
        "contract": CONTRACT,
        "retrieval_months": have_months,
        "required_months": MIN_REPLAY_MONTHS,
        "observations_held": len(seen),
        "earliest_observation": earliest,
        "earliest_valid_t0": earliest,
        "next_eligible_date": next_eligible,
        "episodes": [],
    }

    if episodes:
        return dict(base, state=HISTORICAL_REPLAY_AVAILABLE,
                    episodes=list(episodes),
                    statement=(
                        f"{len(episodes)} earlier decision point(s) can be "
                        f"replayed from what the system actually held at the "
                        f"time."),
                    why_blocked="")

    if have_months >= MIN_REPLAY_MONTHS and len(seen) >= MIN_EPISODE_OBSERVATIONS:
        # Deep enough to replay, but no decision was recorded back then --
        # so the period can be described, not replayed.
        return dict(base, state=DESCRIPTIVE_HISTORY_ONLY,
                    statement=(
                        "We can describe this period from the record, but no "
                        "decision of ours was on file at the time, so there "
                        "is no earlier position to score."),
                    why_blocked="")

    short_by = max(0, MIN_REPLAY_MONTHS - have_months)
    return dict(base, state=HISTORICAL_REPLAY_BLOCKED_DATA,
                statement=(
                    f"We hold {have_months} month(s) of our own observations "
                    f"and a replay needs {MIN_REPLAY_MONTHS}. "
                    + (f"That clears on {next_eligible}."
                       if next_eligible else
                       "No observation of ours carries a date, so there is no "
                       "archive depth to measure.")),
                why_blocked=(
                    "Replaying a decision from today's record would let the "
                    "company's later results, revised macro figures and "
                    "filings published since the date all inform a view that "
                    "is presented as having been held before them. That is "
                    f"hindsight, not history. Short by {short_by} month(s)."))


def plain_statement(assessment: Dict[str, object]) -> str:
    """The sentence a surface may render verbatim.

    Carried rather than rebuilt per surface, so a deck and an X-Ray cannot
    describe the same archive differently -- which is exactly how the
    hardcoded version drifted from any measurement at all.
    """
    state = str((assessment or {}).get("state") or "")
    said = str((assessment or {}).get("statement") or "")
    if state == HISTORICAL_REPLAY_BLOCKED_DATA:
        return f"{said} {assessment.get('why_blocked', '')}".strip()
    return said
