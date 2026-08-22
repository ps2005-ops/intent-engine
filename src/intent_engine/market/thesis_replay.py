"""What the engine would have believed then, and what happened instead.

WHY THIS IS NOT A BACKTEST
--------------------------
A backtest asks whether a rule made money. This asks a harder and more useful
question: at historical instant T0, using only what was observable at T0, what
would the engine have claimed, why, and did reality agree — for the reason it
gave, or for a different one?

The distinction is the whole point. A thesis that predicted margin compression
because rates rose, in a quarter where margins compressed because a factory
burned down, was RIGHT and learned nothing. Scoring it as a success teaches the
engine to keep reasoning that way.

THE SELECTION HAPPENS BEFORE THE ANSWER IS VISIBLE
--------------------------------------------------
Episodes come from `vintage.episodes`: a fixed cadence over a stated window,
kept only where enough rows existed to build a state from. Nothing in the
selection rule can read what happened next. A hand-picked list of interesting
historical moments is a list of moments somebody already knows the answer to,
and every result computed from it is contaminated by the choosing.

`ReplaySelection` records the rule, the window, the cadence and the exclusions,
so the sample can be audited rather than trusted.

WHAT IS ACTUALLY RESOLVABLE, AND WHAT IS NOT
--------------------------------------------
A thesis built from a transmission makes two claims at once:

  the ECONOMIC claim — this condition will move this way;
  the TRANSMISSION claim — and it will reach this company through this route.

Only the first is resolvable against the corpus this engine holds. The second
predicts a company-level observable — capital spending, interest expense —
that a press-release corpus does not carry, so it resolves UNRESOLVED and says
so. That is not a gap in the replay; it is the replay reporting the state of
the evidence, and it is exactly the separation that makes
OUTCOME_RIGHT_MECHANISM_WRONG a reachable verdict rather than a category in a
docstring.

Counting those two legs together would let a correct macro call carry an
untested mechanism to a passing grade, which is the failure this module exists
to make impossible.

NOTHING AT T1 EDITS ANYTHING FROM T0
------------------------------------
The T0 package is built, digested and persisted before any later observation
is read. Resolution appends. A replay that could rewrite its own prediction
would be a record of what the engine wishes it had thought.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "thesis_replay.v1"

# --- how a replayed thesis came out -------------------------------------------
#
# Outcome and mechanism are scored apart. A thesis is not "correct" because the
# number went the predicted way; it is correct when the number went that way
# BECAUSE the stated route carried it.
OUTCOME_RIGHT_MECHANISM_RIGHT = "OUTCOME_RIGHT_MECHANISM_RIGHT"
OUTCOME_RIGHT_MECHANISM_WRONG = "OUTCOME_RIGHT_MECHANISM_WRONG"
OUTCOME_WRONG_MECHANISM_PLAUSIBLE = "OUTCOME_WRONG_MECHANISM_PLAUSIBLE"
OUTCOME_WRONG_MECHANISM_WRONG = "OUTCOME_WRONG_MECHANISM_WRONG"
UNRESOLVED = "UNRESOLVED"
VERDICTS = (OUTCOME_RIGHT_MECHANISM_RIGHT, OUTCOME_RIGHT_MECHANISM_WRONG,
            OUTCOME_WRONG_MECHANISM_PLAUSIBLE, OUTCOME_WRONG_MECHANISM_WRONG,
            UNRESOLVED)

#: The three states either leg can be in. UNTESTED is not a third kind of
#: wrong — a mechanism nobody could check has not failed, and treating it as a
#: failure would make an unobservable route look refuted.
RIGHT = "RIGHT"
WRONG = "WRONG"
UNTESTED = "UNTESTED"
LEG_STATES = (RIGHT, WRONG, UNTESTED)


class ReplayRefused(ValueError):
    """A replay that would have known something it could not have known."""


def _digest(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]


# --- the sample, chosen without reading the answer ------------------------------

@dataclass(frozen=True)
class ReplaySelection:
    """One historical instant, and the rule that picked it.

    `selection_rule` is stored as text rather than inferred later because the
    honest question about any historical result is "how were these episodes
    chosen", and an answer reconstructed after the fact is not evidence.
    """

    replay_id: str
    t0: str
    t1: str
    selection_rule: str
    selected_at: str
    rows_visible_at_t0: int
    eligibility: Tuple[str, ...] = ()
    exclusions: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.t0 or not self.t1:
            raise ReplayRefused("an episode needs both instants")
        if self.t1 <= self.t0:
            raise ReplayRefused(
                f"t1 {self.t1} is not after t0 {self.t0}; an episode that "
                "resolves before it is formed is a lookup")
        if not self.selection_rule.strip():
            raise ReplayRefused(
                "an episode with no stated selection rule cannot be audited "
                "for the one bias that matters here")

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        for name in ("eligibility", "exclusions"):
            out[name] = list(getattr(self, name))
        out.update(contract=CONTRACT, record="replay_selection")
        return out


def select_episodes(rows: Sequence[dict], *, starting: str, ending: str,
                    horizon_days: int, every_days: int = 30,
                    minimum_rows: int = 1, selected_at: str = ""
                    ) -> List[ReplaySelection]:
    """Deterministic episodes over a stated window. Reads no outcome.

    The cadence and the window are the entire rule. Nothing here inspects what
    a thesis formed at an instant would later have got right, because a sample
    filtered on that is a sample of the engine's own successes.
    """
    import datetime as _dt

    from . import vintage as V

    if horizon_days <= 0:
        raise ReplayRefused("a resolution horizon must be positive")
    instants = V.episodes(rows, starting=starting, ending=ending,
                          every_days=every_days, minimum_rows=minimum_rows)
    rule = (f"every {every_days}d from {starting} to {ending}; kept where the "
            f"vintage held >= {minimum_rows} rows; resolved at t0 + "
            f"{horizon_days}d. No outcome is read during selection.")
    out: List[ReplaySelection] = []
    for t0 in instants:
        t1 = (_dt.date.fromisoformat(t0[:10])
              + _dt.timedelta(days=horizon_days)).isoformat()
        if t1 > str(ending)[:10]:
            # The horizon runs past the corpus. Excluded for a reason that is
            # a property of the CALENDAR, not of what happened — dropping
            # episodes because their outcome is inconvenient is the bias this
            # whole module is arranged against.
            continue
        frozen = V.freeze(rows, as_of=t0)
        out.append(ReplaySelection(
            replay_id="rep_" + _digest({"t0": t0, "t1": t1, "rule": rule}),
            t0=t0, t1=t1, selection_rule=rule,
            selected_at=selected_at or t0,
            rows_visible_at_t0=len(frozen.admitted),
            eligibility=(f"{len(frozen.admitted)} rows observable by {t0}",),
            exclusions=(f"{len(frozen.withheld_not_yet_known)} rows existed "
                        f"but were not yet observed",)))
    return out


# --- the prediction, locked before anything later is read -----------------------

@dataclass(frozen=True)
class HistoricalExpectation:
    """What the engine committed to at T0, and how it may be judged.

    Carries its own digest. The digest is over the prediction alone, so a
    resolution appended later cannot quietly change what was predicted — a
    record that can be edited after the answer arrives is a record of
    hindsight.
    """

    replay_id: str
    thesis_id: str
    subject: str
    made_at: str
    #: The economic leg: the condition and which way it was expected to go.
    condition: str
    predicted_direction: str
    #: The transmission leg: the route, and the thing that would show it ran.
    expected_mechanism: str
    expected_observable: str
    resolution_window_days: int
    falsifier: str
    uncertainty: str = ""
    expected_value: Optional[float] = None
    series_id: str = ""
    target_period: str = ""

    def __post_init__(self) -> None:
        if not self.falsifier.strip():
            raise ReplayRefused(
                "a historical expectation with no falsifier cannot come out "
                "wrong, and one that cannot come out wrong teaches nothing")
        if not self.expected_observable.strip():
            raise ReplayRefused(
                "an expectation must name what would show the mechanism ran; "
                "without it the mechanism leg can only ever be UNTESTED for a "
                "reason nobody stated")

    @property
    def expectation_id(self) -> str:
        return "hex_" + _digest(self.as_prediction())

    def as_prediction(self) -> dict:
        """Exactly the fields that constitute the commitment."""
        return {
            "replay_id": self.replay_id, "thesis_id": self.thesis_id,
            "subject": self.subject, "made_at": self.made_at,
            "condition": self.condition,
            "predicted_direction": self.predicted_direction,
            "expected_mechanism": self.expected_mechanism,
            "expected_observable": self.expected_observable,
            "resolution_window_days": self.resolution_window_days,
            "falsifier": self.falsifier,
            "expected_value": self.expected_value,
            "series_id": self.series_id,
            "target_period": self.target_period,
        }

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out.update(contract=CONTRACT, record="historical_expectation",
                   expectation_id=self.expectation_id)
        return out


# --- the answer, appended and never merged back ---------------------------------

@dataclass(frozen=True)
class ReplayResolution:
    """What later observation said about one locked expectation."""

    replay_id: str
    thesis_id: str
    expectation_id: str
    resolved_at: str
    outcome: str
    mechanism: str
    verdict: str
    observed_value: Optional[float] = None
    surprise: Optional[float] = None
    reason: str = ""
    mechanism_reason: str = ""

    def __post_init__(self) -> None:
        if self.outcome not in LEG_STATES:
            raise ReplayRefused(f"unknown outcome leg {self.outcome!r}")
        if self.mechanism not in LEG_STATES:
            raise ReplayRefused(f"unknown mechanism leg {self.mechanism!r}")
        if self.verdict not in VERDICTS:
            raise ReplayRefused(f"unknown verdict {self.verdict!r}")
        if self.mechanism == UNTESTED and not self.mechanism_reason.strip():
            raise ReplayRefused(
                "an untested mechanism must say why it could not be tested; "
                "'we did not check' and 'nothing could have checked it' are "
                "different findings and only one of them is about the corpus")

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out.update(contract=CONTRACT, record="replay_resolution")
        return out


def verdict_for(outcome: str, mechanism: str) -> str:
    """Combine the two legs. UNTESTED never becomes a pass or a failure.

    THE TABLE IS THE POINT. A right outcome with an untested mechanism is
    UNRESOLVED, not a win: the engine has no evidence its reasoning had
    anything to do with the result, and recording it as success is precisely
    how a system learns to be lucky.
    """
    if outcome == UNTESTED:
        return UNRESOLVED
    if outcome == RIGHT:
        if mechanism == RIGHT:
            return OUTCOME_RIGHT_MECHANISM_RIGHT
        if mechanism == WRONG:
            return OUTCOME_RIGHT_MECHANISM_WRONG
        return UNRESOLVED
    if mechanism == WRONG:
        return OUTCOME_WRONG_MECHANISM_WRONG
    if mechanism == RIGHT:
        # The route ran and the prediction still missed: the mechanism is
        # real and something else dominated it. Worth keeping apart from a
        # mechanism that was simply wrong.
        return OUTCOME_WRONG_MECHANISM_PLAUSIBLE
    return UNRESOLVED


#: What the corpus can and cannot resolve, stated once so every UNTESTED
#: mechanism cites the same reason rather than inventing its own wording.
_NO_COMPANY_OBSERVABLE = (
    "the mechanism predicts a company-level observable ({observable}) and the "
    "corpus holds no measurement of it for this subject; nothing available at "
    "t1 could confirm or refute that the route ran")


def run_episode(rows: Sequence[dict], selection: ReplaySelection, *,
                series_id: str, area: str, state_kind: str,
                method: str = "") -> Tuple[List[HistoricalExpectation],
                                           List[ReplayResolution], dict]:
    """Form a thesis at T0 from the T0 vintage, then reveal T1.

    THE WALL IS AN OBJECT, NOT A FILTER APPLIED ONCE. Every read of the T0
    corpus goes through it, so a helper added later that takes the full row
    list raises instead of quietly leaking. The T1 reveal builds a SECOND wall
    rather than advancing the first, because `VintageWall.at` refuses to move
    forward — a replay that walks its own vintage into the future is a
    lookahead with extra steps.
    """
    import datetime as _dt

    from . import macro_expectation as ME
    from . import macro_state as MS
    from . import vintage as V

    t0_wall = V.VintageWall(rows, as_of=selection.t0,
                            label=f"replay {selection.replay_id} t0")
    observed_rows = t0_wall.rows(record="macro_observation")
    history = [MS.from_dict(r) for r in observed_rows]

    # The target period is the one whose figure had NOT been published by t0.
    # Choosing it from the t0 vintage rather than from the full corpus is what
    # keeps the target itself free of hindsight.
    seen_periods = {o.reference_period for o in history
                    if o.series_id == series_id}
    if not seen_periods:
        return [], [], {"skipped": f"{series_id} unseen at {selection.t0}"}
    target = max(seen_periods)

    full = [MS.from_dict(r) for r in rows if r.get("record") ==
            "macro_observation"]
    later = sorted({o.reference_period for o in full
                    if o.series_id == series_id
                    and o.reference_period > target})
    if not later:
        return [], [], {"skipped": "no later period exists to resolve against"}
    target = later[0]

    expectation = ME.forecast(history, series_id=series_id,
                              target_period=target, made_at=selection.t0,
                              method=method or ME.AR1)
    if expectation is None:
        return [], [], {"skipped": "the visible history cannot support the "
                                   "method; an under-determined forecast is "
                                   "an absence, not a zero"}

    # --- the two legs, both locked before anything later is read -----------
    state = MS.state_of(state_kind, history, as_of=selection.t0, area=area)
    direction = ("UP" if expectation.value > (state.observation.value
                                              if state.observation else
                                              expectation.value)
                 else "DOWN" if state.observation and
                 expectation.value < state.observation.value else "FLAT")
    locked = HistoricalExpectation(
        replay_id=selection.replay_id,
        thesis_id="th_replay_" + _digest({"s": series_id, "t": selection.t0}),
        subject=f"{area}:{state_kind}", made_at=selection.t0,
        condition=f"{area}:{state_kind}", predicted_direction=direction,
        expected_mechanism=("the series continues from its own recent level "
                            "under a first-order autoregression"),
        expected_observable=f"{series_id} for {target}",
        resolution_window_days=(
            _dt.date.fromisoformat(selection.t1[:10])
            - _dt.date.fromisoformat(selection.t0[:10])).days,
        falsifier=(f"{series_id} for {target} lands outside the stated "
                   "interval, or moves against the predicted direction"),
        uncertainty=("interval " + str((expectation.low, expectation.high))
                     if expectation.has_interval else
                     "no interval: the visible history could not support one"),
        expected_value=expectation.value, series_id=series_id,
        target_period=target)

    # --- reveal ------------------------------------------------------------
    t1_wall = V.VintageWall(rows, as_of=selection.t1,
                            label=f"replay {selection.replay_id} t1")
    revealed = [MS.from_dict(r)
                for r in t1_wall.rows(record="macro_observation")]
    try:
        surprise = ME.reconcile(expectation, revealed, as_of=selection.t1)
    except ME.Foresight as exc:
        # The figure was already public when the forecast was made. Refusing
        # is the correct answer: scoring it would measure the engine's ability
        # to read.
        return [locked], [], {"skipped": f"foresight refused: {exc}"}
    if surprise is None:
        return [locked], [], {"skipped": "the target figure had not arrived "
                                         "by t1"}

    outcome = (RIGHT if (expectation.has_interval and surprise.covered)
               else RIGHT if (not expectation.has_interval
                              and surprise.surprise == 0)
               else WRONG)
    resolution = ReplayResolution(
        replay_id=selection.replay_id, thesis_id=locked.thesis_id,
        expectation_id=locked.expectation_id, resolved_at=selection.t1,
        outcome=outcome,
        # UNTESTED, and it says why. The transmission leg of a real thesis
        # predicts company capital spending or interest expense; a
        # press-release corpus carries neither, so nothing at t1 could show
        # the route ran. Scoring it as agreement would let the macro call
        # carry an unexamined mechanism to a passing grade.
        mechanism=UNTESTED,
        mechanism_reason=_NO_COMPANY_OBSERVABLE.format(
            observable="capital spending or interest expense"),
        verdict=verdict_for(outcome, UNTESTED),
        observed_value=surprise.observed, surprise=surprise.surprise,
        reason=(f"expected {expectation.value:.4f}, observed "
                f"{surprise.observed:.4f} for {target}"))
    return [locked], [resolution], {
        "t0_wall": t0_wall.as_dict(), "t1_wall": t1_wall.as_dict()}


def summarise(resolutions: Sequence[ReplayResolution]) -> dict:
    """Counted by verdict, and never collapsed into an accuracy."""
    import collections

    by_verdict = collections.Counter(r.verdict for r in resolutions)
    tested = [r for r in resolutions if r.outcome != UNTESTED]
    right = [r for r in tested if r.outcome == RIGHT]
    mechanism_tested = [r for r in resolutions if r.mechanism != UNTESTED]
    return {
        "contract": CONTRACT,
        "resolutions": len(resolutions),
        "by_verdict": {v: by_verdict.get(v, 0) for v in VERDICTS},
        "outcome_tested": len(tested),
        "outcome_right": len(right),
        "mechanism_tested": len(mechanism_tested),
        # DELIBERATELY NOT A HIT RATE. Dividing right by tested would produce
        # a number that reads as accuracy while the mechanism leg — the half
        # that says whether the engine reasoned correctly — is untested on
        # every row. The two counts are reported and the reader does the
        # division knowing what is in it.
        "unresolved": by_verdict.get(UNRESOLVED, 0),
        "note": ("outcome and mechanism are scored apart; a right outcome "
                 "with an untested mechanism is UNRESOLVED rather than a win, "
                 "because nothing shows the engine's reasoning produced it"),
    }
