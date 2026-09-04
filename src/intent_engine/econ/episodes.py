"""Historical regimes, as vintage-walled test beds (Sections 19, 20, 40, 41).

WHY EPISODES AND NOT ONE LONG SAMPLE
------------------------------------
Section 41 requires a regime holdout and a crisis holdout, and neither is
constructible from an undifferentiated time series. An episode names its
window, its regime, and what was distinctive about it, so that a construct
tested on 2008 and validated on 2021 has demonstrably not been tuned on the
period it was tested against.

WHY EVERY EPISODE CARRIES A CONSENSUS AND AN ALTERNATIVE
--------------------------------------------------------
Section 21: the engine is supposed to attack conventional beliefs, not
restate them. An episode with no stated consensus cannot be used to test
whether the collective-state layer added anything, because "the model
explains 2008" is satisfied by any model that has seen 2008. What is testable
is whether the behavioural reading gave a signal BEFORE the conventional
variables moved -- so each episode records the conventional expectation and
the behavioural alternative as two separate, separately falsifiable claims.

THE HOLDOUT DISCIPLINE
----------------------
`training()`, `validation()` and `holdout()` partition the episodes and the
partition is FIXED IN THIS FILE. Section 41's real requirement is not that a
holdout exists but that nobody re-tunes on it; a partition computed at call
time from whatever is available would drift silently as episodes are added.

WHAT THIS MODULE DOES NOT CONTAIN
---------------------------------
Data. Not one observation. An episode is a WINDOW and a QUESTION; the
observations must come from the store, vintage-walled by `replay`. A module
that shipped its own 2008 numbers would be shipping a fit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from .vocabulary import COLLECTIVE_DIMENSIONS, EconError, require

CONTRACT = "econ_episodes.v1"

TRAINING, VALIDATION, HOLDOUT = "TRAINING", "VALIDATION", "HOLDOUT"
PARTITIONS = (TRAINING, VALIDATION, HOLDOUT)


@dataclass(frozen=True)
class Episode:
    """One historical regime, with the two accounts it can discriminate."""

    key: str
    label: str
    regime: str
    start: str
    end: str
    partition: str
    #: What conventional economic models expected during this window.
    consensus: str
    #: The behavioural account that would have said something different.
    behavioural_alternative: str
    #: Which constructs the alternative depends on. These are the ones the
    #: episode can actually test; a construct not named here cannot be
    #: credited for the episode however well the story fits.
    constructs: Tuple[str, ...]
    #: What would show the behavioural account was WRONG here. Required: an
    #: episode that cannot embarrass the alternative is a demonstration.
    falsifier: str
    note: str = ""

    def __post_init__(self) -> None:
        require(self.partition in PARTITIONS,
                f"unknown partition {self.partition!r}")
        require(self.start < self.end, f"{self.key}: empty window")
        require(bool(self.consensus.strip()),
                f"{self.key}: an episode with no stated consensus cannot "
                "show that anything beat the consensus")
        require(bool(self.falsifier.strip()),
                f"{self.key}: an episode that cannot embarrass the "
                "behavioural account is a demonstration, not a test")
        for c in self.constructs:
            require(c in COLLECTIVE_DIMENSIONS,
                    f"{self.key} names construct {c!r}, which is not declared")

    def covers(self, date: str) -> bool:
        return self.start <= date <= self.end

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "regime": self.regime,
                "window": [self.start, self.end],
                "partition": self.partition, "consensus": self.consensus,
                "behavioural_alternative": self.behavioural_alternative,
                "constructs": list(self.constructs),
                "falsifier": self.falsifier, "note": self.note}


#: The declared episodes. Partition assignments are DELIBERATE:
#:  - the two crises everyone has already reasoned about (2008, COVID) are
#:    split across training and holdout, so a construct cannot be tuned on
#:    the famous one and validated on the other famous one;
#:  - the inflation shock is the holdout, because it is the regime where the
#:    behavioural story is most obviously appealing and therefore the one
#:    where over-fitting would be least visible.
EPISODES: Tuple[Episode, ...] = (
    Episode(
        key="stagflation_1970s", label="1970s inflation", regime="INFLATION",
        start="1972-01-01", end="1982-12-31", partition=TRAINING,
        consensus="a Phillips-curve trade-off: sustained inflation would be "
                  "accompanied by low unemployment, and expectations would "
                  "follow realised inflation with a lag",
        behavioural_alternative="household inflation EXPECTATIONS de-anchored "
                                "ahead of realised wage settlements, so "
                                "expectation was a leading rather than a "
                                "lagging variable",
        constructs=("future_orientation", "certainty"),
        falsifier="survey expectation series turn at or after realised "
                  "inflation in each of the three acceleration phases",
        note="the episode that produced the expectations literature; it is "
             "training rather than holdout precisely because it has already "
             "shaped everyone's priors"),
    Episode(
        key="crash_1987", label="October 1987", regime="CRASH",
        start="1987-06-01", end="1988-06-30", partition=TRAINING,
        consensus="a repricing of fundamentals, with portfolio insurance as "
                  "an amplifier",
        behavioural_alternative="a market-participant cascade with almost no "
                                "household behavioural precursor -- included "
                                "as a NEGATIVE case, where the collective "
                                "layer should add nothing",
        constructs=(),
        falsifier="a household construct shows a usable lead into October "
                  "1987; that would suggest the layer is finding signal in "
                  "noise, since the recovery was near-complete within two "
                  "years",
        note="deliberately an episode where the answer should be NO. A "
             "programme with no negative cases cannot distinguish a real "
             "signal from a flexible one."),
    Episode(
        key="dotcom", label="dot-com bubble and unwind", regime="BUBBLE",
        start="1998-01-01", end="2003-12-31", partition=TRAINING,
        consensus="an equity valuation cycle driven by earnings expectations "
                  "for a new technology",
        behavioural_alternative="household risk appetite and willingness to "
                                "experiment rose ahead of the valuation "
                                "expansion, visible in participation rather "
                                "than in prices",
        constructs=("risk_appetite", "willingness_to_experiment"),
        falsifier="household equity participation rises only after, not "
                  "before, the valuation expansion"),
    Episode(
        key="gfc_2008", label="housing and financial crisis", regime="CREDIT_CRISIS",
        start="2005-01-01", end="2010-12-31", partition=TRAINING,
        consensus="a credit event: mortgage underwriting quality deteriorated "
                  "and the losses propagated through leveraged intermediaries",
        behavioural_alternative="Section 20's chain: perceived wealth raised "
                                "risk appetite, which raised borrowing, which "
                                "raised prices -- and the downswing ran the "
                                "same loop backwards through anxiety",
        constructs=("perceived_security", "risk_appetite",
                    "financial_anxiety", "perceived_control"),
        falsifier="each edge of the loop is tested SEPARATELY and at least "
                  "one fails; the chain is refused whole rather than "
                  "credited for the half that fits. For perceived_control "
                  "specifically: the quits rate falls only after, not "
                  "before, the unemployment rate rises",
        note="Section 20 is explicit that this must not start from 'fear "
             "caused the crash'. The upswing and downswing are separate "
             "chains in `transmission_seed` for exactly this reason."),
    Episode(
        key="euro_crisis", label="euro sovereign crisis", regime="CREDIT_CRISIS",
        start="2010-01-01", end="2013-12-31", partition=VALIDATION,
        consensus="a sovereign solvency and currency-union design problem",
        behavioural_alternative="institutional trust fell ahead of spreads in "
                                "the periphery, and the trust move was "
                                "country-specific where the spread move was "
                                "correlated",
        constructs=("institutional_trust",),
        falsifier="trust measures move with spreads rather than ahead of "
                  "them, or move identically across countries",
        note="the geography holdout Section 41 asks for: a non-US episode, "
             "where US-fitted proxies should transfer badly if they are "
             "fitted rather than real"),
    Episode(
        key="covid_crash", label="COVID crash", regime="SHOCK",
        start="2020-01-01", end="2020-06-30", partition=VALIDATION,
        consensus="an exogenous shock with a policy response; no behavioural "
                  "precursor was possible because the cause was exogenous",
        behavioural_alternative="search and mobility behaviour moved days to "
                                "weeks ahead of both policy and prices",
        constructs=("stress", "time_horizon"),
        falsifier="behavioural series turn at the same time as or after "
                  "mobility restrictions, making them a record of policy "
                  "rather than a leading signal"),
    Episode(
        key="covid_recovery", label="COVID recovery and speculation",
        regime="BUBBLE", start="2020-07-01", end="2021-12-31",
        partition=VALIDATION,
        consensus="fiscal transfer plus supply constraint produced demand "
                  "that outran capacity",
        behavioural_alternative="risk appetite and willingness to experiment "
                                "rose far beyond what transfer size implies, "
                                "and the excess showed up first in "
                                "participation, not in prices",
        constructs=("risk_appetite", "willingness_to_experiment", "hope",
                    "perceived_control"),
        falsifier="the speculative participation surge is fully explained by "
                  "transfer timing and size. For perceived_control: the "
                  "quits surge tracks job openings contemporaneously rather "
                  "than leading any outcome, making it a labour-market "
                  "statistic rather than a reading of how workers saw their "
                  "own options",
        note="the quits surge of 2021 is the cleanest available test of "
             "perceived_control, and it is deliberately in VALIDATION rather "
             "than HOLDOUT -- perceived_control is the one construct this "
             "engine can actually measure today, so a partition that let it "
             "be tested only on the holdout would consume the holdout on the "
             "first real experiment"),
    Episode(
        key="inflation_2022", label="2022 inflation and rate shock",
        regime="INFLATION_SHOCK", start="2021-10-01", end="2023-12-31",
        partition=HOLDOUT,
        consensus="a demand-supply imbalance corrected by policy tightening; "
                  "consumption should fall roughly with real income",
        behavioural_alternative="sentiment collapsed to recessionary levels "
                                "while consumption held, which is either the "
                                "clearest disconfirmation of the whole "
                                "behavioural layer or evidence that the "
                                "sentiment INSTRUMENT rather than the state "
                                "broke",
        constructs=("financial_anxiety", "perceived_control", "time_horizon"),
        falsifier="the sentiment-consumption divergence persists across the "
                  "whole window with no construct able to reconcile it",
        note="THE MOST IMPORTANT EPISODE HERE, and the reason it is the "
             "holdout. 2022 is the period where stated sentiment and "
             "revealed behaviour diverged most sharply in the modern record. "
             "A collective-state layer that cannot survive it should be "
             "retired, and one that is tuned on it proves nothing."),
    Episode(
        key="regional_banks_2023", label="regional bank failures",
        regime="CREDIT_CRISIS", start="2023-01-01", end="2023-12-31",
        partition=HOLDOUT,
        consensus="a duration and deposit-concentration problem at specific "
                  "institutions",
        behavioural_alternative="depositor trust moved as a network effect "
                                "rather than as a response to balance-sheet "
                                "disclosure, and moved in hours",
        constructs=("institutional_trust",),
        falsifier="deposit flight tracks published balance-sheet metrics "
                  "rather than leading them",
        note="the lag model matters more here than anywhere: an "
             "institutional-trust construct with a 90-day band cannot "
             "describe a three-day bank run, and pretending it can is how a "
             "lag model becomes decoration"),
)

BY_KEY: Dict[str, Episode] = {e.key: e for e in EPISODES}


def partition(name: str) -> List[Episode]:
    require(name in PARTITIONS, f"unknown partition {name!r}")
    return [e for e in EPISODES if e.partition == name]


def training() -> List[Episode]:
    return partition(TRAINING)


def validation() -> List[Episode]:
    return partition(VALIDATION)


def holdout() -> List[Episode]:
    return partition(HOLDOUT)


def regimes() -> List[str]:
    return sorted({e.regime for e in EPISODES})


def testable(construct: str) -> List[Episode]:
    """Episodes that can say something about this construct.

    An episode that does not name the construct cannot corroborate it. This
    is the guard against the most flattering possible error: running a
    construct against every episode, finding it fits somewhere, and reporting
    that it explains history.
    """
    return [e for e in EPISODES if construct in e.constructs]


def negative_cases() -> List[Episode]:
    """Episodes where the layer is EXPECTED to add nothing."""
    return [e for e in EPISODES if not e.constructs]


def assert_partition_discipline(episodes: Sequence[Episode] = ()) -> None:
    """No construct may be testable ONLY inside the holdout.

    If a construct's only episodes are holdout episodes, then testing it at
    all means touching the holdout, and Section 41's "do not tune repeatedly
    on the final historical crisis set" becomes unenforceable for it.

    TAKES AN EPISODE SET so it can be shown to FIRE. A guard that can only
    ever run against the production episode list -- which by construction
    satisfies it -- is a guard nobody can demonstrate is able to fail. The
    test suite passes a deliberately violating set as a positive control and
    the real one as the actual assertion.
    """
    eps_all = list(episodes) if episodes else list(EPISODES)
    offenders = {}
    for c in COLLECTIVE_DIMENSIONS:
        eps = [e for e in eps_all if c in e.constructs]
        if eps and all(e.partition == HOLDOUT for e in eps):
            offenders[c] = [e.key for e in eps]
    if offenders:
        raise EconError(
            f"{sorted(offenders)} can only be tested inside the holdout, "
            "which means any test of them consumes it. Add a training or "
            "validation episode that names the construct, or accept that it "
            "cannot be validated. Offenders: " + repr(offenders))


def summarise() -> dict:
    by_partition = {p: [e.key for e in partition(p)] for p in PARTITIONS}
    coverage = {c: [e.key for e in testable(c)]
                for c in COLLECTIVE_DIMENSIONS}
    return {"contract": CONTRACT, "episodes": len(EPISODES),
            "by_partition": by_partition,
            "regimes": regimes(),
            "negative_cases": [e.key for e in negative_cases()],
            "constructs_testable": sorted(c for c, v in coverage.items() if v),
            "constructs_untestable": sorted(c for c, v in coverage.items()
                                            if not v),
            "construct_coverage": coverage,
            "span": [min(e.start for e in EPISODES),
                     max(e.end for e in EPISODES)]}


# =============================================================================
# §7: THE DISCOVERED CATALOG
# =============================================================================
# `EPISODES` above is a hand-written test bed: windows somebody chose, with a
# consensus and an alternative attached. It is useful and it cannot be used to
# COUNT independent events, because the count would then be a property of the
# list rather than of the data.
#
# `EconomicEpisode` is the other object. It is DISCOVERED from the
# contemporaneous regime classifier reading the walled panel at each origin,
# so an episode exists because the data said so at the time, not because we
# remember it happening. The named list in §7 of the run prompt -- 1973-75,
# 1979-82, 1987, 1990-91 and the rest -- is used for COVERAGE AUDIT only:
# `coverage_audit` reports which of those windows the discovery actually
# found, which is a check on the classifier, not an input to it.

STRESS_REGIMES = ("CREDIT_STRESS", "LIQUIDITY_STRESS", "INFLATION_SHOCK",
                  "LABOUR_DETERIORATION")

#: How many consecutive calm origins end an episode. Two quarters of nothing
#: happening is a normalisation; one month is a gap in the data.
NORMALISATION_ORIGINS = 6


@dataclass(frozen=True)
class EconomicEpisode:
    """A stretch of stress the classifier found, with its evidence."""

    episode_id: str
    start_as_known: str
    end_as_known: str
    regime_sequence: Tuple[str, ...]
    #: What fired first, and its reading. The trigger is recorded as the
    #: evidence at the FIRST origin rather than the worst one, because an
    #: episode is dated by when it became visible.
    trigger_evidence: Dict[str, float]
    peak_stress: int
    #: The origin at which every stress condition had cleared, or "" when the
    #: episode ran to the end of the sample.
    normalization: str
    #: The last date any input to the classification was knowable. Equal to
    #: the last origin: an episode discovered this way carries no hindsight.
    information_cutoff: str
    provenance: str
    origins: Tuple[str, ...] = ()

    @property
    def origin_count(self) -> int:
        return len(self.origins)

    @property
    def resolved(self) -> bool:
        return bool(self.normalization)

    def covers(self, date: str) -> bool:
        return self.start_as_known <= date <= self.end_as_known

    def as_dict(self) -> dict:
        return {"episode_id": self.episode_id,
                "start_as_known": self.start_as_known,
                "end_as_known": self.end_as_known,
                "regime_sequence": list(self.regime_sequence),
                "trigger_evidence": dict(self.trigger_evidence),
                "peak_stress": self.peak_stress,
                "normalization": self.normalization,
                "information_cutoff": self.information_cutoff,
                "provenance": self.provenance,
                "origins": len(self.origins),
                "resolved": self.resolved}


def discover(readings: Sequence) -> List[EconomicEpisode]:
    """Find stress episodes in a time-ordered run of RegimeReadings.

    An episode OPENS at the first origin where any stress regime holds, and
    CLOSES after `NORMALISATION_ORIGINS` consecutive origins with none. The
    closing rule is what stops one long expansion punctuated by single
    readings from being counted as a dozen separate crises -- the failure
    mode the run prompt names explicitly ("treat one contiguous crisis as 20
    independent episodes").
    """
    ordered = sorted(readings, key=lambda r: r.as_of)
    out: List[EconomicEpisode] = []
    open_ep = None
    calm_run = 0
    for r in ordered:
        stressed = [x for x in r.regimes if x in STRESS_REGIMES]
        if stressed:
            calm_run = 0
            if open_ep is None:
                open_ep = {"start": r.as_of, "origins": [], "seq": [],
                           "trigger": dict(r.evidence), "peak": 0,
                           "last": r.as_of}
            open_ep["origins"].append(r.as_of)
            open_ep["seq"].extend(x for x in stressed
                                  if x not in open_ep["seq"])
            open_ep["peak"] = max(open_ep["peak"], len(stressed))
            open_ep["last"] = r.as_of
        elif open_ep is not None:
            calm_run += 1
            if calm_run >= NORMALISATION_ORIGINS:
                out.append(_close(open_ep, r.as_of))
                open_ep, calm_run = None, 0
    if open_ep is not None:
        out.append(_close(open_ep, ""))
    return out


def _close(ep: dict, normalised_at: str) -> EconomicEpisode:
    return EconomicEpisode(
        episode_id=f"EP_{ep['start'][:7].replace('-', '')}",
        start_as_known=ep["start"], end_as_known=ep["last"],
        regime_sequence=tuple(ep["seq"]), trigger_evidence=ep["trigger"],
        peak_stress=ep["peak"], normalization=normalised_at,
        information_cutoff=ep["last"],
        provenance=("econ.regime.classify over the walled panel; no window "
                    "was supplied and no outcome was consulted"),
        origins=tuple(ep["origins"]))


#: Windows the run prompt lists. USED FOR COVERAGE AUDIT ONLY -- never to
#: label, never to seed discovery. A period in this list that discovery did
#: NOT find is a finding about the classifier or about the data reach; a
#: period discovery found that is not here is not an error at all.
AUDIT_WINDOWS: Tuple[Tuple[str, str, str], ...] = (
    ("late_1960s_inflation", "1966-01-01", "1970-12-31"),
    ("1973_75", "1973-01-01", "1975-12-31"),
    ("1979_82", "1979-01-01", "1982-12-31"),
    ("1987", "1987-08-01", "1988-03-31"),
    ("1990_91", "1990-01-01", "1991-12-31"),
    ("1994_tightening", "1994-01-01", "1995-06-30"),
    ("1997_98", "1997-07-01", "1998-12-31"),
    ("2000_02", "2000-03-01", "2002-12-31"),
    ("2007_09", "2007-06-01", "2009-12-31"),
    ("2011", "2011-06-01", "2012-03-31"),
    ("2015_16", "2015-06-01", "2016-06-30"),
    ("2018", "2018-09-01", "2019-01-31"),
    ("2020", "2020-02-01", "2020-12-31"),
    ("2021_23", "2021-04-01", "2023-12-31"),
    ("2023_banking", "2023-03-01", "2023-09-30"),
)


def coverage_audit(found: Sequence[EconomicEpisode],
                   origin_span: Tuple[str, str] = ("", "")) -> dict:
    """Which known windows the discovery reached, and why it missed the rest.

    A window outside the origin span was NOT MISSED -- there were no origins
    in it to classify. Reporting those as misses would turn a data-reach
    limit into a classifier defect, which is the wrong lesson from the same
    number.
    """
    lo, hi = origin_span
    rows = []
    for key, start, end in AUDIT_WINDOWS:
        in_reach = (not lo) or (start <= hi and end >= lo)
        hit = [e.episode_id for e in found
               if e.start_as_known <= end and e.end_as_known >= start]
        rows.append({"window": key, "start": start, "end": end,
                     "in_origin_reach": in_reach,
                     "episodes_found": hit,
                     "status": ("FOUND" if hit else
                                ("MISSED" if in_reach else "OUT_OF_REACH"))})
    return {"contract": CONTRACT + "/coverage",
            "origin_span": list(origin_span),
            "windows": rows,
            "found": sum(1 for r in rows if r["status"] == "FOUND"),
            "missed": sum(1 for r in rows if r["status"] == "MISSED"),
            "out_of_reach": sum(1 for r in rows
                                if r["status"] == "OUT_OF_REACH"),
            "discovered_episodes": [e.as_dict() for e in found]}


class EpisodeSplitRefused(EconError):
    """Episodes were cut finer than the data supports, to clear a floor."""


def assert_no_artificial_split(eps: Sequence[EconomicEpisode], *,
                               normalisation_origins: int = None) -> None:
    """Two episodes must be separated by a real normalisation.

    §15's guard. The episode floor is three, and the cheapest way to clear it
    is to cut one long crisis into four -- which `discover` will not do, but
    any caller assembling an episode list by hand could. This checks the
    property on the LIST rather than trusting the producer.

    The 2008-2010 episode contains 29 monthly origins and would happily yield
    five "episodes" at a two-month gap rule. It is one event, and a floor
    that can be satisfied by re-cutting the same event is not a floor.
    """
    import datetime as _dt
    need = (normalisation_origins if normalisation_origins is not None
            else NORMALISATION_ORIGINS)
    ordered = sorted(eps, key=lambda e: e.start_as_known)
    bad = []
    for a, b in zip(ordered, ordered[1:]):
        d0 = _dt.date(int(a.end_as_known[:4]), int(a.end_as_known[5:7]),
                      int(a.end_as_known[8:10]))
        d1 = _dt.date(int(b.start_as_known[:4]), int(b.start_as_known[5:7]),
                      int(b.start_as_known[8:10]))
        months = (d1 - d0).days / 30.4
        if months < need:
            bad.append(f"{a.episode_id} ends {a.end_as_known} and "
                       f"{b.episode_id} starts {b.start_as_known}: "
                       f"{months:.1f} months apart, below the {need}-origin "
                       "normalisation")
    if bad:
        raise EpisodeSplitRefused(
            f"{len(bad)} episode pair(s) are not separated by a real "
            f"normalisation:\n  " + "\n  ".join(bad[:5]))


def ledger(eps: Sequence[EconomicEpisode], *, panel=None,
           behavioural: Sequence[str] = (), targets: Sequence[str] = ()
           ) -> dict:
    """§15: the canonical episode record, with what could be READ during it.

    `behavioural_available` is the part that matters for a later run: an
    episode with no walled behavioural series in it cannot test a
    behavioural hypothesis however dramatic it was.
    """
    rows = []
    for e in eps:
        avail = []
        if panel is not None:
            mid = e.origins[len(e.origins) // 2] if e.origins else \
                e.start_as_known
            for sid in behavioural:
                if panel.history(sid, as_of=mid, lookback=2):
                    avail.append(sid)
        rows.append({
            **e.as_dict(),
            "behavioural_available": sorted(avail),
            "behavioural_missing": sorted(set(behavioural) - set(avail)),
            "targets": list(targets),
            "testable_for_behaviour": len(avail) >= 2})
    return {"contract": CONTRACT + "/ledger", "episodes": len(rows),
            "testable_for_behaviour": sum(1 for r in rows
                                          if r["testable_for_behaviour"]),
            "detail": rows}
