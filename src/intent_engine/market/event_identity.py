"""What happened, as distinct from who said it happened.

TWO IDENTITIES, AND THE PROJECT HAS ONLY EVER HAD ONE
-----------------------------------------------------
    evidence identity   this outlet, this wording, this URL
    event identity      the occurrence in the world all of them describe

`micro_evidence.occurrence_key` is an EVIDENCE identity: it includes the
source, deliberately, because two outlets reporting one event really are two
items and the design-effect penalty in `beliefs` exists to handle their
correlation.

That is right for counting evidence and wrong for testing expectations. A
belief opened by Reuters' account of Cloudflare's Q2 print must not be
"confirmed" by Bloomberg's account of the same print. Both are real, both are
independent, and neither is a LATER OUTCOME — they are the same moment
described twice.

    CORROBORATES        several independent sources saw the same event
    TESTS_EXPECTATION   a LATER event went the way the belief predicted

Collapsing them either triple-counts a confirmation or throws away source
diversity, and this project has done both.

WHY EVIDENCE PLURALITY SURVIVES
-------------------------------
Nothing here merges evidence rows. Every row stays, keeps its source and its
id, and gains an `event_id` it shares with the others. The ledger can then
say "three independent sources corroborated the opening event, and none of
them counted as a later outcome", which is the sentence neither previous
design could produce.
"""
from __future__ import annotations

import collections
import datetime as _dt
import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "event_identity.v1"

#: Two reports of one event arrive within a few days of each other. Beyond
#: this they are more likely to be two events of the same KIND — a quarterly
#: print and the next quarterly print — and merging those would be the
#: opposite error.
SAME_EVENT_WINDOW_DAYS = 4

#: Words that carry no event content. Stripped before hashing so "Cloudflare
#: Q2 revenue rises 36%" and "Revenue rises 36% at Cloudflare, says filing"
#: reach the same core.
_NOISE = re.compile(
    r"\b(?:the|a|an|of|in|on|at|to|for|and|or|as|is|are|was|were|says?|"
    r"said|reports?|reported|according|inc|corp|ltd|plc|company|update|"
    r"exclusive|breaking|analysis|shares?|stock)\b", re.I)


#: A period marker is not a figure. "Q2", "2026", "FY2027" appear in one
#: account of a print and not the other, and including them splits accounts
#: of one event. The date window already carries period.
_PERIOD = re.compile(r"^(?:q[1-4]|fy\d{2,4}|cy\d{2,4}|\d{4}|h[12])$", re.I)


def _date(value: object) -> Optional[_dt.date]:
    try:
        return _dt.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def event_core(subject: str, evidence_type: str, fact: str) -> str:
    """The occurrence, with the reporting stripped off.

    Numbers are KEPT and are what mostly does the work: "revenue rises 36%"
    and "revenue rises 4%" are different events however similar the wording,
    and two accounts of one print agree on the figure.
    """
    text = _NOISE.sub(" ", (fact or "").lower())
    text = re.sub(r"[^a-z0-9%. ]+", " ", text)
    tokens = sorted(set(text.split()))
    numeric = sorted(t for t in (x.strip(".") for x in tokens)
                     if any(c.isdigit() for c in t) and not _PERIOD.match(t))
    head = [(subject or "").strip().lower(), (evidence_type or "").strip()]
    if numeric:
        # FIGURES ARE THE KEY when a fact has any. Two accounts of one print
        # agree on the number and disagree on everything else — "revenue
        # rises 36% as restructuring widens the loss" and "revenue rises 36%
        # at Cloudflare, filing shows" share one token and nine words of
        # difference. A word bag calls those two events; the figure does not.
        return "|".join(head + [" ".join(numeric)])
    # No figures: fall back to the content words, which is brittle across
    # rewordings and is the best available for a qualitative statement.
    words = [t for t in tokens if len(t) > 3][:12]
    return "|".join(head + ["", " ".join(words)])


@dataclass(frozen=True)
class Event:
    """One occurrence, and every account of it."""
    event_id: str
    subject: str
    evidence_type: str
    first_seen: str
    evidence_ids: Tuple[str, ...]
    sources: Tuple[str, ...]
    source_roles: Tuple[str, ...]
    core: str

    @property
    def independent_accounts(self) -> int:
        """Distinct SOURCE ROLES, not distinct outlets.

        Six aggregator rewrites of one wire story are one account. A filing
        and an independent report are two.
        """
        return len(set(self.source_roles))

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "event_id": self.event_id,
            "subject": self.subject, "evidence_type": self.evidence_type,
            "first_seen": self.first_seen,
            "evidence_ids": list(self.evidence_ids),
            "accounts": len(self.evidence_ids),
            "independent_accounts": self.independent_accounts,
            "sources": list(self.sources),
        }


def group(evidence: Sequence) -> Tuple[Event, ...]:
    """Fold evidence rows into events. No row is merged away."""
    buckets: Dict[str, List] = collections.defaultdict(list)
    for item in evidence:
        core = event_core(getattr(item, "subject_company", ""),
                          getattr(item, "evidence_type", ""),
                          getattr(item, "fact", ""))
        buckets[core].append(item)

    out: List[Event] = []
    for core, rows in buckets.items():
        rows = sorted(rows, key=lambda r: str(
            getattr(r, "observed_at", ""))[:10])
        # Split a bucket whose members are far apart in time: same wording,
        # different quarter, is two events.
        window: List = []
        anchor = _date(getattr(rows[0], "observed_at", ""))
        for row in rows:
            when = _date(getattr(row, "observed_at", ""))
            if window and anchor and when and \
                    (when - anchor).days > SAME_EVENT_WINDOW_DAYS:
                out.append(_event(core, window))
                window, anchor = [], when
            window.append(row)
        if window:
            out.append(_event(core, window))
    return tuple(out)


def _event(core: str, rows: Sequence) -> Event:
    return Event(
        event_id="evt_" + hashlib.sha256(
            (core + str(getattr(rows[0], "observed_at", ""))[:10]
             ).encode()).hexdigest()[:14],
        subject=getattr(rows[0], "subject_company", ""),
        evidence_type=getattr(rows[0], "evidence_type", ""),
        first_seen=str(getattr(rows[0], "observed_at", ""))[:10],
        evidence_ids=tuple(getattr(r, "evidence_id", "") for r in rows),
        sources=tuple(dict.fromkeys(getattr(r, "source", "") for r in rows)),
        source_roles=tuple(getattr(r, "source_role", "") for r in rows),
        core=core)


def index(events: Sequence[Event]) -> Dict[str, str]:
    """evidence_id -> event_id, for the binder to look up."""
    return {eid: event.event_id for event in events
            for eid in event.evidence_ids}


# --- what a later observation is allowed to be ------------------------------
CORROBORATES = "CORROBORATES"
TESTS_EXPECTATION = "TESTS_EXPECTATION"
NEITHER = "NEITHER"


def role_of(candidate_event_id: str, opener_event_ids: Sequence[str]) -> str:
    """Same event as the opener, or a later one.

    This is the whole point of the module in one branch: an observation that
    shares the opener's EVENT identity corroborates it and cannot test it,
    however different the outlet, the wording or the id.
    """
    if candidate_event_id and candidate_event_id in set(opener_event_ids):
        return CORROBORATES
    return TESTS_EXPECTATION


def summarise(events: Sequence[Event]) -> dict:
    multi = [e for e in events if len(e.evidence_ids) > 1]
    return {
        "contract": CONTRACT,
        "events": len(events),
        "evidence_rows": sum(len(e.evidence_ids) for e in events),
        "events_with_several_accounts": len(multi),
        "events_with_independent_accounts": sum(
            1 for e in events if e.independent_accounts > 1),
        "largest_account_count": max((len(e.evidence_ids) for e in events),
                                     default=0),
        "note": ("no evidence row is merged away: every row keeps its id and "
                 "its source and gains a shared event_id, so source "
                 "diversity survives while one occurrence stays one "
                 "occurrence"),
    }
