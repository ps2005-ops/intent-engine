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
    # WHAT IT WAS WATCHING IS A REAL ANSWER; A RETRIEVAL REPORT IS NOT.
    #
    # This panel used to open "No estimate or share-price series was
    # retrieved, so what the market expected is not measured here" — a true
    # sentence about our feed, offered to someone who asked a question about
    # a company, with nothing after it. The business model determines what a
    # market watches for this kind of business, which is knowable without any
    # price series at all, and it is stated first. The limit is still stated;
    # it is no longer the headline, and it now says what would remove it.
    drivers = tuple(getattr(profile, "primary_revenue_drivers", ()) or ())
    if not drivers:
        return ("What a market watches for this kind of business is not "
                "established here, because the business was not classified "
                "in this run. What would settle it: any filing or investor "
                "page that describes how the company earns its revenue.")
    return _stop(
        f"What a market watches for a business of this kind is set by how it "
        f"earns money: {_join([_lower(d) for d in drivers[:3]])}. Those are "
        f"the measures a reader at this date would have been tracking. No "
        f"contemporaneous price or estimate series was retrieved to check "
        f"the level against, so the direction here carries no magnitude — "
        f"what would settle that is a published price history for this "
        f"company covering the vintage")


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


# ===========================================================================
# WHICH REWIND THIS COMPANY CAN HAVE (§I)
# ===========================================================================
#
# THE DEFECT THIS REPLACES, reported from the live demo on b88df2bb.
# Highspot's history page was headed "Highspot — the strategy simulator" and
# opened "Pick a year. The chart holds the path the company actually took...".
# Underneath, it said Highspot is not an SEC filer, has no dated regulator
# series, that the chart cannot be drawn, and asked the reader to supply three
# years of reported revenue.
#
# Every one of those sentences is true. Together they are a page that promises
# an experience in its heading and withdraws it in its body, which reads as a
# broken feature rather than an honest bound. The heading was written before
# anything was known about what could be drawn -- it is a constant at the top
# of the renderer -- so it made the same promise to every company on earth.
#
# The fix is not softer wording. It is to decide WHAT KIND OF REWIND THIS
# COMPANY SUPPORTS, name the page after that, and fill it accordingly.
#
#: A dated financial or operating series exists: the three-line chart.
LEVEL_SERIES = "LEVEL_A_SERIES"
#: No series, but the company's own dated record can be walked: a bounded
#: strategic rewind. Events and positions, no chart, vintage wall intact.
LEVEL_BOUNDED = "LEVEL_B_BOUNDED"
#: Not enough dated evidence for either: an explicit evidence-gap rewind that
#: says what is missing and what would close it.
LEVEL_GAP = "LEVEL_C_GAP"

#: How the page names itself at each level. A heading is a promise.
LEVEL_TITLES = {
    LEVEL_SERIES: "the strategy simulator",
    LEVEL_BOUNDED: "a bounded strategic rewind",
    LEVEL_GAP: "what the dated record does not yet support",
}

# --- WHETHER A STOP COULD BE GIVEN ITS ECONOMIC WEATHER ----------------------
#
# WHY A STATE AND NOT A BLANK. A LEVEL B rewind walked the company's own dates
# and said, at every stop, the same two sentences with the counts swapped:
# "By <month>, N dated page(s) ... had been retrieved" and "A reader on this
# date could establish what <company> said it did and who it said it served".
# Those sentences are true of every company that has ever published a web
# page, which makes them a template rather than a rewind -- and a template is
# exactly what §19 refuses.
#
# Two things are wrong with it and they are separate. The first is that the
# company's OWN record was summarised as a count instead of being read. The
# second is that the economic world the company was operating in at that date
# was not consulted at all: measured 2026-09-11, this module contained one
# occurrence of the string "econom", in a docstring.
#
# The economic read is vintage-safe BY CONSTRUCTION, not by promise:
# `econ_at` is handed a date and must return the state published on or before
# it. A deployment that published no state by that date gets
# ECON_NO_STATE_FOR_DATE and the page SAYS SO -- which is the honest answer
# and the one §11 asks for, rather than today's weather presented as 2019's.
ECON_LINKED = "ECONOMIC_CONTEXT_LINKED"
ECON_NO_STATE_FOR_DATE = "NO_ECONOMIC_STATE_PUBLISHED_FOR_THIS_DATE"
ECON_NOT_ATTEMPTED = "ECONOMIC_CONTEXT_NOT_ATTEMPTED"
ECON_STATES = (ECON_LINKED, ECON_NO_STATE_FOR_DATE, ECON_NOT_ATTEMPTED)

#: What a published page of each kind lets a reader establish. The VALUE is
#: what the reader learns, so a company whose record is three newsroom posts
#: gets a different sentence from one whose record is a pricing page and a
#: customer list -- which is the point, and is derived from its own evidence
#: rather than asserted about it.
_KNOWABLE_BY_KIND = {
    "corporate": "how it described itself and what it claimed to be for",
    "segment": "what it said it sold and to whom",
    "customers": "who it was willing to name as a customer",
    "pricing": "how it said it charged, which is the clearest statement a "
               "company makes about who it is built for",
    "newsroom": "what it chose to announce, and therefore what it wanted "
                "read as progress",
    "page": "what it had published about itself",
}


#: Two dated points is the floor for a REWIND. One date is a fact about a
#: document, not a path: there is no "before" to stand in and no "after" to
#: have been surprised by, so a one-point page would be a rewind in name.
MIN_BOUNDED_POINTS = 2


@dataclasses.dataclass(frozen=True)
class DatedRecord:
    """One thing this company published, and when it said so.

    NOT A FILING, and deliberately a different type. `Filing` carries a
    regulator's form code and the prose built from it says "filings on the
    public record". Pushing a marketing page through that vocabulary would
    describe an About page as a filing, which is a smaller lie than an
    invented chart and still a lie.
    """
    date: _dt.date
    title: str
    url: str
    kind: str = "page"          #: corporate / newsroom / segment / pricing
    source_class: str = ""
    #: WHERE the date came from, so the page can say. "metadata" is the
    #: publisher's own schema.org/OpenGraph date; "url_path" is a dated
    #: path segment the publisher chose. Never "retrieval".
    date_source: str = "metadata"

    @property
    def iso(self) -> str:
        return self.date.isoformat()


#: A dated path segment, as publishers structure article URLs:
#: `/insights/articles/2023/08/learn-to-thrive`. BOTH a four-digit year and a
#: two-digit month, ADJACENT and separated by slashes.
#:
#: WHY THIS IS NOT "READING A DATE OUT OF A URL". A bare four-digit number in
#: a path is a coincidence waiting to happen -- a product name, an SKU, a
#: pagination offset. A year segment followed immediately by a valid month
#: segment is a publishing convention, and the publisher chose it. Measured
#: 2026-09-11: Point B publishes every article under `/Insights/Articles/
#: YYYY/MM/`, and reading only metadata put that company on the evidence-gap
#: page while its own URLs carried the dates.
#:
#: The day is not taken even when a third segment looks like one: month
#: precision is what the convention actually asserts, so the first of the
#: month is used and the page never claims a day it was not told.
_URL_DATE = re.compile(r"/((?:19|20)\d{2})/(0[1-9]|1[0-2])(?:/|$)")


def _date_from_url(url: str) -> Optional[_dt.date]:
    found = _URL_DATE.search(str(url or ""))
    if not found:
        return None
    try:
        return _dt.date(int(found.group(1)), int(found.group(2)), 1)
    except ValueError:
        return None


def dated_records(documents: Sequence[dict]) -> Tuple[DatedRecord, ...]:
    """Everything the run retrieved that carries a PUBLISHER-ASSERTED date.

    The date comes from `published_date` -- the schema.org / OpenGraph date
    the publisher put on the page -- and from nowhere else. Not from the URL,
    not from the first four digits that look like a year in the body, and
    above all NOT from when we fetched it: retrieval time is the one date
    that is always available and never means anything about the company.

    De-duplicated by (date, url) and returned oldest first.
    """
    out, seen = [], set()
    for document in documents or ():
        if not isinstance(document, dict):
            continue
        url_early = str(document.get("final_url")
                        or document.get("original_url") or "")
        raw = str(document.get("published_date") or "").strip()
        when = _date(raw[:10]) if raw else None
        origin = "metadata"
        if when is None:
            # Metadata first, the publisher's own URL convention second.
            when = _date_from_url(url_early)
            origin = "url_path"
        if when is None:
            continue
        # A publisher date in the future is a template placeholder or a
        # scheduled post, not evidence of something that has happened.
        if when > _dt.date.today():
            continue
        url = str(document.get("final_url") or document.get("original_url")
                  or "")
        key = (when, url)
        if key in seen:
            continue
        seen.add(key)
        out.append(DatedRecord(
            date=when, title=_clean(document.get("title") or ""), url=url,
            kind=str(document.get("source_type") or "page"),
            source_class=str(document.get("source_class") or ""),
            date_source=origin))
    return tuple(sorted(out, key=lambda r: r.date))


def rewind_level(timeline=None, records: Sequence[DatedRecord] = ()) -> str:
    """Which of the three rewinds this company's evidence supports.

    Read in order of strength, and each rung is decided by what EXISTS rather
    than by what kind of company this is. A private company with a rich dated
    record outranks a listed one whose filings we failed to retrieve, which
    is the correct ordering: the page is about evidence, not status.
    """
    if timeline is not None and getattr(timeline, "available", False):
        return LEVEL_SERIES
    if len(records or ()) >= MIN_BOUNDED_POINTS:
        return LEVEL_BOUNDED
    return LEVEL_GAP


@dataclasses.dataclass(frozen=True)
class BoundedStop:
    """One date in a bounded rewind, with the wall held at that date."""
    date: str
    label: str
    record_then: str            #: what had been published by this date
    knowable: str               #: what a reader could have established
    unknowable: str             #: what no one could have known yet
    later: str                  #: what followed -- AFTER the wall, labelled
    count_before: int = 0
    count_after: int = 0
    #: The economic world as it was PUBLISHED ON OR BEFORE this date. Empty
    #: when no state had been published by then; never today's state.
    economic_then: str = ""
    economic_state: str = ECON_NOT_ATTEMPTED
    #: What this stop teaches about the company, read off its own record.
    lesson: str = ""


@dataclasses.dataclass(frozen=True)
class BoundedRewind:
    """§I LEVEL B. A rewind with no chart, and no pretence of one."""
    company: str
    level: str = LEVEL_BOUNDED
    stops: Tuple[BoundedStop, ...] = ()
    span: str = ""
    coverage_note: str = ""
    open_question: str = ""
    what_would_upgrade: str = ""
    #: How many stops carry a vintage-safe economic reading, and what that
    #: means. Zero is a legitimate, stated outcome.
    economic_links: int = 0
    economic_note: str = ""

    @property
    def available(self) -> bool:
        return bool(self.stops)


def _kinds_of(records: Sequence[DatedRecord]) -> List[str]:
    """The kinds of page present, in a stable order. Never invented."""
    order = ("corporate", "segment", "customers", "pricing", "newsroom",
             "page")
    present = {str(r.kind or "page").lower() for r in records}
    return [k for k in order if k in present]


def _titles_of(records: Sequence[DatedRecord], limit: int = 3) -> str:
    """The company's OWN words for its own pages."""
    seen, out = set(), []
    for record in reversed(list(records)):
        title = " ".join(str(record.title or "").split())
        key = title.lower()
        if not title or key in seen:
            continue
        seen.add(key)
        out.append(title if len(title) <= 70 else title[:67] + "...")
        if len(out) >= limit:
            break
    return _join(out)


def _stop_label(when: _dt.date, records: Sequence[DatedRecord],
                same_month: bool) -> str:
    """How a stop names its own date.

    MEASURED on Cohesity, whose six dated pages span 2026-07-10 to 2026-08-27:
    the rewind rendered five stops headed "July 2026, July 2026, July 2026,
    August 2026, August 2026". The dates differ; the LABEL collapsed them, and
    three identical headings read as a broken page.

    The day is added ONLY where a publisher asserted one. `_URL_DATE` extracts
    month precision on purpose -- a dated path segment asserts the month, not
    the day -- so a URL-derived stop keeps its month and is separated by its
    position instead. Inventing a day to make a heading unique would trade a
    confusing page for a false one.
    """
    if not same_month:
        return when.strftime("%B %Y")
    asserted = any(r.date == when and r.date_source == "metadata"
                   for r in records)
    if asserted:
        return when.strftime("%-d %B %Y") if hasattr(when, "strftime") \
            else when.isoformat()
    return f"{when.strftime('%B %Y')} (week {((when.day - 1) // 7) + 1})"


def _record_then(company: str, before: Sequence[DatedRecord],
                 when: _dt.date) -> str:
    """What this company had actually said by this date -- not how many pages.

    Reads the titles and the kinds on record. A count alone is the same
    sentence for every company in the world.
    """
    month = when.strftime("%B %Y")
    titles = _titles_of(before)
    kinds = _kinds_of(before)
    bits = [f"By {month}, {company}'s own dated record ran to "
            f"{len(before)} page(s)"]
    if kinds:
        bits.append("covering " + _join([k.replace("_", " ") for k in kinds]))
    if titles:
        bits.append(f"most recently {titles}")
    return _stop(", ".join(bits))


def _bounded_knowable(company: str, before: Sequence[DatedRecord],
                      since: Sequence[DatedRecord] = ()) -> str:
    """What a reader ON THIS DATE could establish, and what was new about it.

    STOP-RELATIVE, BECAUSE A REWIND IS ABOUT CHANGE. A first version derived
    this from the SET OF KINDS on record, and kinds rarely change between two
    adjacent dates: measured on Cohesity, whose six pages all classified as
    the same kind, all five stops rendered the identical sentence. Five cards
    saying the same thing is the template collapse this page exists to avoid,
    arriving inside a single company instead of across two.

    So the sentence names what the stop ADDED -- the pages that had appeared
    since the previous stop, by their own titles -- and falls back to the
    standing position only at the first stop, where nothing has changed yet
    because there is no earlier stop to change from.
    """
    kinds = _kinds_of(before)
    learns = [_KNOWABLE_BY_KIND[k] for k in kinds if k in _KNOWABLE_BY_KIND]
    standing = (_join(learns) if learns else "")
    new_titles = _titles_of(since, 2)
    if since and new_titles:
        return _stop(
            f"By this date {company} had added {len(since)} page(s) a reader "
            f"could not have seen at the previous stop -- {new_titles} -- so "
            f"what is newly establishable here is whatever those state"
            + (f", on top of {standing}" if standing else ""))
    if not standing:
        return _stop(f"Nothing on {company}'s record by this date states "
                     f"what it sold or who it served")
    return _stop(f"A reader on this date could establish {standing} -- all of "
                 f"it from material {company} had itself published by then")


def _bounded_unknowable(company: str, before: Sequence[DatedRecord],
                        after: Sequence[DatedRecord], when: _dt.date) -> str:
    """What was withheld. Named by KIND, never by a later title.

    The kinds not yet on record are the honest statement of the gap: saying
    WHICH later page existed would put a fact from after the wall inside the
    field whose job is to hold the wall. That belongs in `later`, which is
    labelled as hindsight.
    """
    month = when.strftime("%B %Y")
    if not after:
        return _stop(f"This is the most recent dated material retrieved for "
                     f"{company}, so there is no later record being withheld")
        # (unreachable fall-through kept explicit for the reader)
    missing = [k for k in _kinds_of(after) if k not in _kinds_of(before)]
    extra = (f", including the first {_join(missing)} page(s) it would publish"
             if missing else "")
    return _stop(f"Nothing {company} published after {month} was available: "
                 f"{len(after)} of the dated page(s) read here did not exist "
                 f"yet{extra}")


def _bounded_lesson(company: str, before: Sequence[DatedRecord],
                    after: Sequence[DatedRecord],
                    since: Sequence[DatedRecord] = (),
                    gap_days: int = 0) -> str:
    """What this stop teaches, read off the shape of the record itself.

    DESCRIPTIVE, NOT CONCLUDED. It says what the company's own publishing
    shows; it does not rate the strategy, because a page count is not evidence
    about whether a strategy worked.

    Like `_bounded_knowable`, it is stop-relative. Keyed only on which KINDS
    were still to come, it returned one sentence for four of Cohesity's five
    stops -- true of each, and useless as a walk, because a reader learns
    nothing from being told the same thing four times.
    """
    gained = [k for k in _kinds_of(after) if k not in _kinds_of(before)]
    if gained:
        return _stop(f"What {company} had not yet put on the record by this "
                     f"date is as telling as what it had: its "
                     f"{_join([g.replace('_', ' ') for g in gained])} "
                     f"material came later, so a reader here could not have "
                     f"judged it on that")
    if not after:
        return _stop(f"This is the end of {company}'s dated record as "
                     f"retrieved, so everything a reader can check about its "
                     f"current position rests on material up to this point")
    # NOTHING NEW IN KIND. What is left to say is about PACE and VOLUME, and
    # those differ stop to stop even when the subject matter does not.
    if since and gap_days:
        # NAME WHAT ARRIVED. Two stops can share a pace -- one page, seven days
        # -- and then the sentence is true twice and informative once. The
        # page's own title is what actually differs, and it costs nothing to
        # say.
        which = _titles_of(since, 1)
        return _stop(
            f"{company} put {len(since)} page(s) on the record in the "
            f"{gap_days} day(s) before this date"
            + (f" ({which})" if which else "")
            + ", and none of them opened a subject it had not already "
              "covered, so the change here is cadence rather than direction")
    if since:
        return _stop(
            f"The {len(since)} page(s) added by this date stayed within "
            f"subjects {company} was already publishing on, so this stop "
            f"marks continuity rather than a turn")
    return _stop(f"{company} published nothing new by this date that the "
                 f"previous stop had not already shown, so the record itself "
                 f"is the evidence of a pause")


def _economic_then(econ_at, when: _dt.date, company: str) -> tuple:
    """The economic world AS PUBLISHED ON OR BEFORE `when`. Never raises.

    `econ_at` is injected rather than imported so this module keeps no
    dependency on the economic store, and so a test can prove the wall holds
    without publishing one.

    THE WALL IS CHECKED HERE TOO. A reader that returned a state dated AFTER
    the stop would leak hindsight into the one page whose entire promise is
    that it does not, so a late state is refused rather than rendered.
    """
    if econ_at is None:
        return "", ECON_NOT_ATTEMPTED
    try:
        context = econ_at(when.isoformat())
    except Exception:                                      # noqa: BLE001
        return "", ECON_NO_STATE_FOR_DATE
    if context is None or not getattr(context, "available", False):
        return "", ECON_NO_STATE_FOR_DATE
    as_of = str(getattr(context, "as_of", "") or "")
    if as_of and as_of > when.isoformat():
        # The reader handed back a LATER state. Refused: see above.
        return "", ECON_NO_STATE_FOR_DATE
    conditions = getattr(context, "conditions", None) or {}
    shocks = tuple(getattr(context, "shocks", ()) or ())
    area = str(getattr(context, "area", "") or "the economy")
    named = _join([f"{str(k).replace('_', ' ')} {str(v)}"
                   for k, v in sorted(conditions.items())[:3]])
    said = [f"The economic state published for {area} as at "
            f"{as_of or when.isoformat()}"]
    if named:
        said.append(f"recorded {named}")
    if shocks:
        said.append(f"with {len(shocks)} named shock(s) on the record")
    if not named and not shocks:
        said.append("carried no condition this rewind can read")
    return (_stop(", ".join(said)
                  + f". Nothing published after {when.isoformat()} was used"),
            ECON_LINKED)


def bounded_rewind(*, company: str, records: Sequence[DatedRecord],
                   profile=None, max_points: int = 6,
                   econ_at=None) -> BoundedRewind:
    """Walk the company's own dated record. Never raises.

    THE VINTAGE WALL IS THE SAME WALL. At each stop, `record_then` and
    `knowable` are built only from records dated on or before that stop, and
    everything after it goes in `later`, which is the one field allowed to
    use hindsight and is labelled as such on the page. That is the same
    contract `build()` holds for filings; it is restated here because a
    second surface with its own wall is a second chance to get it wrong.
    """
    records = tuple(sorted(records or (), key=lambda r: r.date))
    if len(records) < MIN_BOUNDED_POINTS:
        return BoundedRewind(company=company, coverage_note=(
            f"No document retrieved for {company} carried a date its "
            f"publisher had asserted, so there is no sequence to walk."
            if not records else
            f"One dated document was retrieved for {company}, and a rewind "
            f"needs at least {MIN_BOUNDED_POINTS}: with a single date there "
            f"is no earlier position to stand in."))
    dates = [r.date for r in records]
    # Every distinct date, newest-last, thinned to `max_points` by keeping
    # the ends and spreading the middle. No date is interpolated.
    distinct = sorted(dict.fromkeys(dates))
    if len(distinct) > max_points:
        step = (len(distinct) - 1) / float(max_points - 1)
        distinct = [distinct[int(round(i * step))]
                    for i in range(max_points)]
        distinct = sorted(dict.fromkeys(distinct))
    stops = []
    # Which stops share a month with another stop: only those need a finer
    # label, and only those pay for it.
    _months = [d.strftime("%Y-%m") for d in distinct]
    _crowded = {d for d in distinct
                if _months.count(d.strftime("%Y-%m")) > 1}
    _previous = None
    for when in distinct:
        before = [r for r in records if r.date <= when]
        after = [r for r in records if r.date > when]
        # What arrived since the PREVIOUS stop. Entirely on this side of the
        # wall: every record in it is dated on or before `when`.
        since = ([r for r in records if _previous < r.date <= when]
                 if _previous is not None else [])
        gap = (when - _previous).days if _previous is not None else 0
        # EVERY FIELD BELOW IS READ OFF THIS COMPANY'S OWN RECORD. The version
        # this replaces substituted two counts into two fixed sentences, so
        # every LEVEL B company's rewind was the same page.
        economic_then, economic_state = _economic_then(econ_at, when, company)
        stops.append(BoundedStop(
            date=when.isoformat(),
            label=_stop_label(when, records, when in _crowded),
            record_then=_record_then(company, before, when),
            knowable=_bounded_knowable(company, before, since),
            unknowable=_bounded_unknowable(company, before, after, when),
            later=_stop(
                f"{len(after)} dated page(s) followed this date"
                + (f", beginning with {_titles_of(after[:1], 1)}"
                   if after and _titles_of(after[:1], 1) else "")
                if after else "Nothing retrieved is dated after this point"),
            count_before=len(before), count_after=len(after),
            economic_then=economic_then, economic_state=economic_state,
            lesson=_bounded_lesson(company, before, after, since,
                                   gap)))
        _previous = when
    span = f"{records[0].iso} to {records[-1].iso}"
    linked = sum(1 for st in stops if st.economic_state == ECON_LINKED)
    return BoundedRewind(
        company=company, stops=tuple(stops), span=span,
        coverage_note=_stop(
            f"{len(records)} dated document(s) span {span}. These are pages "
            f"{company} published with a date on them, not a financial "
            f"series — the path of the business is not drawn here because no "
            f"reported figures were retrieved to draw it from"),
        open_question=_stop(
            f"What {company} was optimising for across this period cannot be "
            f"settled from dated pages alone; it needs reported results or a "
            f"dated statement of its own targets"),
        economic_links=linked,
        economic_note=(
            f"{linked} of {len(stops)} stop(s) could be placed beside the "
            f"economic state published at the time."
            if linked else
            "No economic state had been published to this deployment on or "
            "before any of these dates, so none of the stops is placed "
            "beside the economic conditions of its period. That is a gap in "
            "what this deployment has recorded, not a judgement that the "
            "period was uneventful."),
        what_would_upgrade=(
            "three or more years of reported revenue and operating result, "
            "or any dated filing series for this entity"))
