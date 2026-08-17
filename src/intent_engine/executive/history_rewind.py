"""Rewind the company to a date, and see only what was visible then.

WHY THIS EXISTS
---------------
A strategy looks obvious once you know how it turned out. Every executive
knows this and almost no analysis is built to resist it: the report explaining
why a decision was right is written after the outcome, from sources published
after the outcome, and the reader has no way to tell which parts were
knowable at the time. That is not history. It is hindsight with a date on it.

This surface answers a different question -- *what did the record actually
show on this date, and what would a reasonable executive have concluded from
it?* -- and then, separately and visibly, what happened next.

THE VINTAGE WALL (§44)
----------------------
The reading at date T is composed from filings whose FILING DATE is on or
before T, and from nothing else. Not from later filings, not from the current
market snapshot, not from this run's conclusion. The later material exists on
the same page, in a panel of its own, under a heading that says what it is.

The wall is enforced structurally rather than by care: `_before` is the only
way material enters a vintage, it takes the cutoff as an argument, and the
"what happened afterward" panel is built by a DIFFERENT function that takes
the complement. There is no code path in which a later document can reach an
earlier panel, so the wall cannot be breached by someone adding a field.

THREE STATES, AND ONLY ONE IS A REPLAY (§45)
--------------------------------------------
    HISTORICAL_REPLAY     we hold filings from before this date AND filings
                          after it, so a belief formed then can be scored
                          against what followed
    DESCRIPTIVE_HISTORY   we hold filings from before this date and nothing
                          after, so we can describe the vintage and may not
                          claim it was tested
    REPLAY_NOT_YET_VALID  we hold nothing from before this date

`economic_history` already draws this distinction for the market engine's
observation archive. This is the same discipline applied to the regulatory
record, which is the only per-company dated series a first run actually
holds. The two are not merged: this one says what the COMPANY had published,
that one says what THIS SYSTEM had observed, and conflating them would let an
archive gap read as a company that disclosed nothing.

WHAT IS NOT FABRICATED
----------------------
No founding date, no revenue series, no market capitalisation, no product
launch this system did not read. A filing date and a filing form are facts;
everything composed from them is marked as composed. Where a chart would need
numbers that were not retrieved, there is no chart -- §30's rule, applied by
having nothing to draw with rather than by remembering not to.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import re
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "history_rewind.v1"

HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
DESCRIPTIVE_HISTORY = "DESCRIPTIVE_HISTORY"
REPLAY_NOT_YET_VALID = "REPLAY_NOT_YET_VALID"

STATES = (HISTORICAL_REPLAY, DESCRIPTIVE_HISTORY, REPLAY_NOT_YET_VALID)

#: How each state is said to a reader. No enum reaches a page (§73).
STATE_PROSE = {
    HISTORICAL_REPLAY:
        "We hold filings from before this date and after it, so what the "
        "record supported then can be scored against what followed.",
    DESCRIPTIVE_HISTORY:
        "We hold filings from before this date but none after it, so this "
        "describes the vintage. Nothing here has been tested against an "
        "outcome.",
    REPLAY_NOT_YET_VALID:
        "We hold no filing from before this date, so there is nothing to "
        "replay. This is a limit of what was retrieved, not a statement "
        "about the company.",
}

#: What each form tells a reader about the company at that moment. The form
#: is a fact; this is what the form MEANS, which is the same for every filer
#: and is therefore safe to state.
FORM_MEANING = {
    "10-K": ("the annual account", "a full description of the business, its "
             "risks and its results for the year"),
    "20-F": ("the annual account", "the annual report of a foreign private "
             "issuer, equivalent in scope to a 10-K"),
    "40-F": ("the annual account", "the annual report of a Canadian issuer "
             "filed under the multijurisdictional system"),
    "10-Q": ("a quarter's results", "results and any material change since "
             "the annual account"),
    "8-K": ("something the company had to report at once",
            "an event material enough that the company could not wait for "
            "the next scheduled report"),
    "6-K": ("something reported out of cycle",
            "material information a foreign issuer made public elsewhere"),
    "DEF 14A": ("what management asked owners to approve",
                "the proxy statement, which is where incentives and "
                "governance are visible"),
    "S-1": ("a first sale of securities to the public",
            "the registration statement, which is the fullest self-"
            "description a company ever files"),
    "424B4": ("a completed offering", "the final prospectus for a securities "
              "sale"),
}

_ANNUAL = ("10-K", "20-F", "40-F")
_QUARTER = ("10-Q",)
_EVENT = ("8-K", "6-K")

#: THE FORMS THAT ARE ABOUT THE COMPANY.
#:
#: EDGAR's recent-submissions list is dominated by ownership reports -- Form 4
#: is filed every time an officer's shares vest, Form 144 every time they are
#: sold. Measured on Cloudflare: 40 consecutive filings covered SEVEN WEEKS
#: and 23 of them were Forms 4 and 144. A "history rewind" built on that
#: window rewinds to the summer, prints "16 x 4, 7 x 144" as though those were
#: forms a reader has heard of, and never reaches a single annual account.
#:
#: These are not filtered because they are unimportant -- insider selling is
#: real information. They are filtered because they are about PEOPLE, and this
#: timeline is about the COMPANY, and mixing them makes the company's own
#: story unreadable at any zoom level.
COMPANY_FORMS = frozenset({
    "10-K", "10-K/A", "20-F", "20-F/A", "40-F",
    "10-Q", "10-Q/A", "8-K", "8-K/A", "6-K",
    "DEF 14A", "DEFA14A", "S-1", "S-1/A", "424B4", "424B3",
    "S-3", "S-3ASR", "11-K",
})


def _date(value) -> Optional[_dt.date]:
    text = str(value or "").strip()[:10]
    try:
        return _dt.date.fromisoformat(text)
    except ValueError:
        return None


def _clean(text) -> str:
    return " ".join(str(text or "").split())


@dataclasses.dataclass(frozen=True)
class Filing:
    form: str
    date: _dt.date
    url: str = ""
    title: str = ""

    @property
    def iso(self) -> str:
        return self.date.isoformat()


@dataclasses.dataclass(frozen=True)
class Panel:
    """One of §43's eight readings at a date."""
    key: str
    title: str
    body: str
    #: True only for the panel that is allowed to use later material.
    after_the_wall: bool = False


@dataclasses.dataclass(frozen=True)
class Counterfactual:
    """§46. An alternative that was available AT THE TIME."""
    actual_choice: str
    information_available: str
    alternative: str
    expected_outcome: str
    observed_outcome: str
    mechanism: str
    lesson: str


@dataclasses.dataclass(frozen=True)
class Vintage:
    """The company as the record showed it on one date."""
    date: str
    label: str
    state: str
    state_prose: str
    filings_before: int
    filings_after: int
    latest_before: str          #: the most recent form filed by this date
    panels: Tuple[Panel, ...] = ()
    counterfactual: Optional[Counterfactual] = None

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        return out


@dataclasses.dataclass(frozen=True)
class Timeline:
    company: str
    contract: str = CONTRACT
    vintages: Tuple[Vintage, ...] = ()
    #: Why the timeline is as short or as long as it is. Never silent: a
    #: two-point timeline with no explanation reads as a broken feature.
    coverage_note: str = ""
    #: The dated facts the whole surface rests on, for the provenance drawer.
    filings: Tuple[dict, ...] = ()

    @property
    def available(self) -> bool:
        return bool(self.vintages)

    def as_dict(self) -> dict:
        return {"contract": self.contract, "company": self.company,
                "coverage_note": self.coverage_note,
                "filings": list(self.filings),
                "vintages": [v.as_dict() for v in self.vintages]}


# ===========================================================================
# the vintage wall
# ===========================================================================
def _before(filings: Sequence[Filing], cutoff: _dt.date) -> List[Filing]:
    """Everything filed on or before the cutoff. THE ONLY WAY IN."""
    return [f for f in filings if f.date <= cutoff]


def _after(filings: Sequence[Filing], cutoff: _dt.date) -> List[Filing]:
    """Everything filed after the cutoff. Feeds exactly one panel."""
    return [f for f in filings if f.date > cutoff]


def cik_from_urls(urls: Sequence[str]) -> str:
    """The filer's CIK, from an EDGAR archive URL the run already fetched.

    Cheaper and more reliable than re-resolving the company by name, and it
    cannot resolve to a DIFFERENT company: the URL is one this run retrieved.
    """
    for url in urls or ():
        found = re.search(r"/edgar/data/(\d+)/", str(url or ""))
        if found:
            return found.group(1)
    return ""


def filings_from_submissions(payload: dict, *, limit: int = 60
                             ) -> Tuple[Filing, ...]:
    """Dated filings from EDGAR's submissions JSON. Never raises."""
    try:
        recent = (payload or {})["filings"]["recent"]
        forms = list(recent.get("form") or ())
        dates = list(recent.get("filingDate") or ())
        accs = list(recent.get("accessionNumber") or ())
        docs = list(recent.get("primaryDocument") or ())
    except Exception:                                       # noqa: BLE001
        return ()
    cik = str((payload or {}).get("cik") or "").lstrip("0")
    out = []
    for i, form in enumerate(forms):
        if str(form) not in COMPANY_FORMS:
            continue
        when = _date(dates[i] if i < len(dates) else "")
        if when is None:
            continue
        url = ""
        if cik and i < len(accs) and i < len(docs) and accs[i] and docs[i]:
            url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                   f"{str(accs[i]).replace('-', '')}/{docs[i]}")
        out.append(Filing(form=str(form), date=when, url=url,
                          title=f"SEC {form} ({when.isoformat()})"))
        if len(out) >= limit:
            break
    return tuple(sorted(out, key=lambda f: f.date))


def filings_from_documents(documents: Sequence[dict]) -> Tuple[Filing, ...]:
    """Fallback: the dated filings THIS RUN retrieved.

    Always available, and always small -- a run retrieves two or three
    filings, which is a two-or-three-point timeline. That is a real timeline
    and the coverage note says how short it is, which is better than a rich
    one built from dates nobody read.
    """
    out = []
    for document in documents or ():
        if not isinstance(document, dict):
            continue
        url = str(document.get("final_url") or document.get("url") or "")
        if "sec.gov" not in url:
            continue
        filing = document.get("filing")
        form = str((filing or {}).get("form") or "") if isinstance(
            filing, dict) else ""
        title = str(document.get("title") or "")
        when = _date(_date_in(title)) or _date(_date_in(url))
        if when is None or not form:
            continue
        out.append(Filing(form=form, date=when, url=url, title=title))
    return tuple(sorted(dict.fromkeys(out), key=lambda f: f.date))


def _date_in(text: str) -> str:
    found = re.search(r"(20\d{2})[-/]?(\d{2})[-/]?(\d{2})", str(text or ""))
    return f"{found.group(1)}-{found.group(2)}-{found.group(3)}" if found else ""


# ===========================================================================
# composing one vintage
# ===========================================================================
def _label(when: _dt.date, filing: Optional[Filing]) -> str:
    month = when.strftime("%B %Y")
    if filing is None:
        return month
    meaning = FORM_MEANING.get(filing.form, ("a filing", ""))[0]
    return f"{month} — {meaning}"


def _state(before: Sequence[Filing], after: Sequence[Filing]) -> str:
    if not before:
        return REPLAY_NOT_YET_VALID
    return HISTORICAL_REPLAY if after else DESCRIPTIVE_HISTORY


def _company_state(company, profile, before, when) -> str:
    if not before:
        return (f"Nothing {company} had filed by {when.strftime('%B %Y')} was "
                f"retrieved, so its state at this date is not established "
                f"here.")
    annual = [f for f in before if f.form in _ANNUAL]
    quarters = [f for f in before if f.form in _QUARTER]
    events = [f for f in before if f.form in _EVENT]
    latest = before[-1]
    clauses = [f"By {when.strftime('%B %Y')}, {company} had put "
               f"{len(before)} company filing(s) on the public record"]
    if annual:
        clauses.append(f"the most recent full account of the business was the "
                       f"{annual[-1].form} filed {annual[-1].iso}")
    if quarters:
        clauses.append(f"{len(quarters)} quarterly report(s) had followed it")
    if events:
        clauses.append(f"{len(events)} event(s) had been material enough to "
                       f"report out of cycle")
    out = _stop("; ".join(clauses))
    model = _clean(getattr(profile, "business_model", ""))
    if model and model != "UNKNOWN":
        out += (f" The business those filings describe runs on "
                f"{_stop(_lower(model.partition(':')[2] or model))}")
    return out


def _market_state(profile, before, when) -> str:
    structure = _clean(getattr(profile, "industry_structure", ""))
    if not structure or structure == "UNKNOWN":
        return (f"The structure of the market at {when.strftime('%B %Y')} is "
                f"not established from what was retrieved.")
    cyclical = _clean(getattr(profile, "cyclical_exposure", ""))
    out = (f"The market it sold into was {_lower(structure)}")
    if cyclical and cyclical != "UNKNOWN":
        # `cyclical_exposure` reads "SECULAR: demand is driven by adoption",
        # so prefixing "Demand in this industry is" produced "Demand in this
        # industry is demand is driven by".
        out += f". In this industry, {_lower(cyclical.partition(':')[2] or cyclical)}"
    return _stop(out) + (
        " This describes the industry rather than the month, and is carried "
        "forward unchanged across dates for that reason.")


def _management_strategy(company, profile, selection, before, when) -> str:
    if not before:
        return (f"What management was doing at this date is not established "
                f"from what was retrieved.")
    levers = tuple(getattr(profile, "primary_management_levers", ()) or ())
    latest = before[-1]
    meaning = FORM_MEANING.get(latest.form, ("a filing", "a disclosure"))[1]
    out = (f"The most recent thing {company} had said about itself was its "
           f"{latest.form} of {latest.iso} — {meaning}")
    if levers:
        out += (f". For a business of this kind the levers management holds "
                f"are {_join([_lower(l) for l in levers[:3]])}, and a "
                f"strategy at this date is a choice among those")
    return _stop(out)


def _market_expected(profile, before, when) -> str:
    """§43. What the market expected -- bounded, never a price target."""
    if not before:
        return ("With nothing filed by this date in hand, what the market "
                "expected cannot be read from the record.")
    drivers = tuple(getattr(profile, "primary_revenue_drivers", ()) or ())
    if not drivers:
        return ("What the market expected is not established. No share-price "
                "or estimate series was retrieved, and inferring expectation "
                "from a later outcome is the error this page exists to "
                "avoid.")
    return _stop(
        f"No estimate or share-price series was retrieved, so what the market "
        f"expected is not measured here. What it would have been watching is "
        f"determined by the business model: "
        f"{_join([_lower(d) for d in drivers[:3]])}")


def _knowable(before, when) -> str:
    if not before:
        return (f"Nothing. No filing dated on or before "
                f"{when.strftime('%d %B %Y')} was retrieved in this run.")
    forms = {}
    for f in before:
        forms[f.form] = forms.get(f.form, 0) + 1
    listed = _join([f"{n} × {form}" for form, n in
                    sorted(forms.items(), key=lambda kv: -kv[1])][:4])
    return _stop(
        f"Exactly this: {listed}, the most recent filed {before[-1].iso}. "
        f"Everything in the panels above is composed from those and from how "
        f"this kind of business works — nothing filed after "
        f"{when.strftime('%d %B %Y')} reached them")


def _what_happened(company, after, when) -> str:
    """THE ONLY PANEL ALLOWED PAST THE WALL."""
    if not after:
        return (f"Nothing later than {when.strftime('%B %Y')} was retrieved, "
                f"so this vintage has not been tested against an outcome.")
    annual = [f for f in after if f.form in _ANNUAL]
    out = (f"{company} filed {len(after)} more time(s) after this date, up to "
           f"{after[-1].iso}")
    if annual:
        out += (f", including a further annual account ({annual[-1].form}, "
                f"{annual[-1].iso}) — the document that would settle whether "
                f"the reading above held")
    return _stop(out) + (
        " This panel is the only place on this page that uses material filed "
        "after the selected date.")


def _alternative(company, profile, selection, before) -> str:
    scenarios = tuple(getattr(selection, "scenarios", ()) or ())
    alt = next((s for s in scenarios
                if str(getattr(s, "name", "")).upper() != "BASE"), None)
    if alt is None:
        levers = tuple(getattr(profile, "primary_management_levers", ()) or ())
        if not levers:
            return ("No alternative strategy is put forward: the levers this "
                    "business holds are not established here.")
        return _stop(
            f"The alternative available at this date was the other end of the "
            f"same lever — {_lower(levers[0])} in the opposite direction, "
            f"which is a real choice and not a better-informed one")
    return _stop(
        f"{_clean(getattr(alt, 'lever', 'A different move'))} — "
        f"{_lower(_clean(getattr(alt, 'first_order', '')))}")


def _lesson(profile, state) -> str:
    if state == HISTORICAL_REPLAY:
        return ("The test of the reading above is whether the later filings "
                "show the mechanism operating, not whether the outcome was "
                "good. A right answer for the wrong reason is a worse guide "
                "to the next decision than a wrong answer for the right one.")
    if state == DESCRIPTIVE_HISTORY:
        return ("This vintage has not been scored. Treat it as a record of "
                "what was arguable at the time, which is what a decision has "
                "to be judged against — and not as a verdict.")
    return ("The honest lesson from a date we hold nothing for is that the "
            "archive, not the company, is the limit here.")


def _counterfactual(company, profile, selection, before, after,
                    state) -> Optional[Counterfactual]:
    if not before:
        return None
    scenarios = tuple(getattr(selection, "scenarios", ()) or ())
    base = next((s for s in scenarios
                 if str(getattr(s, "name", "")).upper() == "BASE"),
                scenarios[0] if scenarios else None)
    alt = next((s for s in scenarios
                if str(getattr(s, "name", "")).upper() in
                ("DOWNSIDE", "ADVERSARIAL", "UPSIDE")), None)
    if base is None:
        return None
    return Counterfactual(
        actual_choice=_stop(
            f"Continue on the course the {before[-1].form} of "
            f"{before[-1].iso} describes — {_lower(_clean(getattr(base, 'lever', 'the standing plan')))}"),
        information_available=_knowable(before, before[-1].date),
        alternative=_alternative(company, profile, selection, before),
        expected_outcome=_stop(_clean(getattr(base, "first_order", ""))
                               or "not established"),
        observed_outcome=(
            _stop(f"Testable: {len(after)} later filing(s) exist, and the "
                  f"annual account among them is where the mechanism would "
                  f"show")
            if state == HISTORICAL_REPLAY else
            "Not testable from what was retrieved — no later filing is held."),
        mechanism=_stop(_clean(getattr(base, "second_order", ""))
                        or _clean(getattr(profile, "operating_leverage", ""))),
        lesson=_lesson(profile, state))


def _panels(company, profile, selection, before, after, when,
            state) -> Tuple[Panel, ...]:
    return (
        Panel("company", "The company at this date",
              _company_state(company, profile, before, when)),
        Panel("market", "The market at this date",
              _market_state(profile, before, when)),
        Panel("strategy", "What management was doing",
              _management_strategy(company, profile, selection, before, when)),
        Panel("expected", "What the market was watching",
              _market_expected(profile, before, when)),
        Panel("knowable", "What was knowable then",
              _knowable(before, when)),
        Panel("after", "What happened afterward",
              _what_happened(company, after, when), after_the_wall=True),
        Panel("alternative", "The alternative that was available",
              _alternative(company, profile, selection, before)),
        Panel("lesson", "The lesson", _lesson(profile, state)),
    )


def build(*, company: str, filings: Sequence[Filing],
          profile=None, selection=None, max_points: int = 8) -> Timeline:
    """The timeline. Never raises; an empty one still explains itself."""
    filings = tuple(sorted(filings or (), key=lambda f: f.date))
    if not filings:
        return Timeline(company=company, coverage_note=(
            "No dated regulatory filing was retrieved for this company, so "
            "there is no dated record to rewind. This is a limit of what was "
            "retrieved, not a statement about the company's history."))
    points = _points(filings, max_points)
    vintages = []
    for when in points:
        before, after = _before(filings, when), _after(filings, when)
        state = _state(before, after)
        anchor = before[-1] if before else None
        vintages.append(Vintage(
            date=when.isoformat(), label=_label(when, anchor), state=state,
            state_prose=STATE_PROSE[state],
            filings_before=len(before), filings_after=len(after),
            latest_before=anchor.form if anchor else "",
            panels=_panels(company, profile, selection, before, after, when,
                           state),
            counterfactual=_counterfactual(company, profile, selection,
                                           before, after, state)))
    span = f"{filings[0].iso} to {filings[-1].iso}"
    return Timeline(
        company=company, vintages=tuple(vintages),
        coverage_note=_stop(
            f"{len(filings)} dated filing(s) span {span}. The timeline has "
            f"{len(vintages)} point(s) because that is how many distinct "
            f"dates the record supports — it is not a fixed number of steps "
            f"and no point is interpolated"),
        filings=tuple({"form": f.form, "date": f.iso, "url": f.url,
                       "title": f.title} for f in filings))


def _points(filings: Sequence[Filing], limit: int) -> List[_dt.date]:
    """The dates worth stopping at.

    Annual accounts first -- they are the moments a company restates what it
    is -- then the most recent filings, then whatever is left, spread across
    the span rather than clustered at the end.
    """
    annual = [f.date for f in filings if f.form in _ANNUAL]
    chosen = list(dict.fromkeys(annual))
    if len(chosen) < limit:
        for f in reversed(filings):
            if f.date not in chosen:
                chosen.append(f.date)
            if len(chosen) >= limit:
                break
    return sorted(chosen)[:limit]


# --- small helpers ----------------------------------------------------------
def _lower(text: str) -> str:
    flat = _clean(text)
    if not flat:
        return ""
    head = flat.split(" ", 1)[0]
    if head.isupper() or (len(head) > 1 and head[1:].lower() != head[1:]):
        return flat
    return flat[0].lower() + flat[1:]


def _stop(text: str) -> str:
    flat = _clean(text)
    if not flat:
        return ""
    return flat if flat[-1] in ".?!" else flat.rstrip(",;:—- ") + "."


def _join(items) -> str:
    items = [i for i in (items or ()) if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]
