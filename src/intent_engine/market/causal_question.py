"""Formulating a causal question from what the engine holds, and adjudicating it.

WHAT THIS IS FOR
----------------
`synthetic_control` can fit a counterfactual and `causal_diagnostics` can attack
it. Neither has ever run, because nothing in the engine turns "this happened to
that company on that date" into a panel. This file is that step, and it is
mostly a set of reasons to refuse.

THE MEASUREMENT THAT SHAPED THIS FILE
-------------------------------------
Before writing it, the live ledger was counted rather than guessed at:

    423 dated company events across 8 types
      (EARNINGS_RESULT 195, GUIDANCE_REVISION 52, LAYOFF 21, ...)
      0 of them carry any numeric value
    18 macro series, largest comparable group 4
      (MARKET_RATE in %, of which only 2 share a frequency)

So the engine holds TREATMENTS and does not hold OUTCOMES. Every dated event
names a company whose measured path does not exist anywhere in the system.
That is not a gap to be worked around; it is the answer, and the job of this
file is to reach it precisely — naming which prerequisite is missing, for which
question — rather than to reach it by producing nothing.

A causal capability whose honest output today is "I cannot identify this, and
here is the one input that would change that" is worth more than one that
quietly never runs. The second is what the engine had.

WHY THE ORIGIN FIELD NEVER DISAPPEARS
-------------------------------------
`question_origin` separates a question derived from a real dated event from one
constructed to exercise the machinery. The tests need panels that reach
ESTIMATE_SUPPORTED, and those panels are fabricated — legitimately, to prove
the state is reachable. The moment a SYNTHETIC_TEST resolution could be counted
alongside an EVENT_DERIVED one, the capability would report itself working on
evidence it manufactured. The field is required, validated, and carried into
every persisted row.

THE STATE MACHINE IS THE PRODUCT
--------------------------------
Not the estimate. `PANEL_UNAVAILABLE`, `DONOR_SUPPORT_INSUFFICIENT` and
`PLACEBO_UNRESOLVED` are three different things a decision-maker would do
something different about, and all three are currently collapsed by every
system that reports "no significant effect".

    missing panel          is not a zero effect
    failed placebo         is not no effect
    insufficient donors    is not a treatment that failed
"""
from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import causal_diagnostics as CD
from . import economic_method as EM
from . import synthetic_control as SC

CONTRACT = "causal_question.v1"

# --- where the question came from ---------------------------------------------

#: The engine asked it forward, before the answer was available.
PROSPECTIVE = "PROSPECTIVE"
#: Derived from a dated event already on the ledger. The date is the event's,
#: never chosen by looking at the outcome.
EVENT_DERIVED = "EVENT_DERIVED"
#: Assembled from a past whose answer is already on record. Never counted
#: toward a prospective gate; see historical_corpus.
HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
#: Constructed to exercise the machinery. Legitimate, and never evidence.
SYNTHETIC_TEST = "SYNTHETIC_TEST"
ORIGINS = (PROSPECTIVE, EVENT_DERIVED, HISTORICAL_REPLAY, SYNTHETIC_TEST)

#: Origins whose resolutions describe the real world. A count that mixes in
#: SYNTHETIC_TEST is reporting the test suite as a finding.
REAL_ORIGINS = (PROSPECTIVE, EVENT_DERIVED, HISTORICAL_REPLAY)

# --- the state machine --------------------------------------------------------

QUESTION_IDENTIFIED = "QUESTION_IDENTIFIED"
PANEL_UNAVAILABLE = "PANEL_UNAVAILABLE"
DONOR_SUPPORT_INSUFFICIENT = "DONOR_SUPPORT_INSUFFICIENT"
PRE_FIT_FAILED = "PRE_FIT_FAILED"
PLACEBO_UNRESOLVED = "PLACEBO_UNRESOLVED"
ESTIMATE_BOUNDED = "ESTIMATE_BOUNDED"
ESTIMATE_SUPPORTED = "ESTIMATE_SUPPORTED"
REFUSED = "REFUSED"
STATES = (QUESTION_IDENTIFIED, PANEL_UNAVAILABLE, DONOR_SUPPORT_INSUFFICIENT,
          PRE_FIT_FAILED, PLACEBO_UNRESOLVED, ESTIMATE_BOUNDED,
          ESTIMATE_SUPPORTED, REFUSED)

#: States in which no effect was estimated. Named as a set because the mistake
#: this file exists to prevent is reading any of them as "no effect".
NOT_AN_ESTIMATE = (QUESTION_IDENTIFIED, PANEL_UNAVAILABLE,
                   DONOR_SUPPORT_INSUFFICIENT, PRE_FIT_FAILED,
                   PLACEBO_UNRESOLVED, REFUSED)

# --- what was missing ---------------------------------------------------------
#
# A prerequisite, not an error. Each names a specific input whose arrival would
# change the answer, which is what makes a refusal actionable rather than a
# shrug.

NO_OUTCOME_SERIES = "NO_OUTCOME_SERIES_FOR_TREATED_UNIT"
NO_COMPARABLE_UNITS = "NO_COMPARABLE_UNITS_FOR_DONOR_POOL"
TOO_FEW_DONORS = "TOO_FEW_COMPARABLE_UNITS"
SHORT_PRE_PERIOD = "TOO_FEW_PRE_TREATMENT_OBSERVATIONS"
NO_POST_PERIOD = "NO_POST_TREATMENT_OBSERVATIONS"
RAGGED_FREQUENCY = "COMPARABLE_UNITS_ON_A_DIFFERENT_FREQUENCY"
PREREQUISITES = (NO_OUTCOME_SERIES, NO_COMPARABLE_UNITS, TOO_FEW_DONORS,
                 SHORT_PRE_PERIOD, NO_POST_PERIOD, RAGGED_FREQUENCY)


class QuestionRejected(ValueError):
    """A question that could not be constructed, as distinct from one that
    could not be answered. The second is a finding; the first is a bug."""


@dataclass(frozen=True)
class DonorDecision:
    """One candidate unit and why it is or is not in the pool.

    RECORDED BEFORE THE OUTCOME IS LOOKED AT. Donor eligibility here depends
    only on comparability — the same measured quantity, the same unit, the same
    frequency, covering the window. Nothing in this object may depend on how
    well the donor fits or on what the effect turns out to be, because a pool
    chosen after seeing the answer is the single easiest way to manufacture one
    and it leaves no trace in the estimate.
    """

    unit: str
    included: bool
    reason: str

    def as_dict(self) -> dict:
        return {"unit": self.unit, "included": self.included,
                "reason": self.reason}


@dataclass(frozen=True)
class CausalQuestion:
    """What is being asked, of whom, about when."""

    causal_question_id: str
    company_id: str
    treatment_event_id: str
    treatment_type: str
    treatment_at: str
    outcome_variable: str
    question_origin: str
    known_at: str = ""
    source: str = ""
    pre_period: Tuple[str, str] = ("", "")
    post_period: Tuple[str, str] = ("", "")
    donor_candidates: Tuple[str, ...] = ()
    donor_exclusions: Tuple[DonorDecision, ...] = ()

    def __post_init__(self) -> None:
        if self.question_origin not in ORIGINS:
            raise QuestionRejected(
                f"unknown question_origin {self.question_origin!r}; a question "
                f"must declare one of {list(ORIGINS)} rather than leave a "
                "counter to work out whether it describes the world")
        if not self.treatment_at:
            raise QuestionRejected(
                "a causal question with no treatment date is a comparison, "
                "not a question")
        if not self.outcome_variable:
            raise QuestionRejected(
                "a causal question must name the outcome it is about before "
                "the data are looked at; choosing it afterwards is choosing "
                "the one that moved")

    @property
    def describes_the_world(self) -> bool:
        return self.question_origin in REAL_ORIGINS

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["donor_exclusions"] = [d.as_dict() for d in self.donor_exclusions]
        out["donor_candidates"] = list(self.donor_candidates)
        out["pre_period"] = list(self.pre_period)
        out["post_period"] = list(self.post_period)
        out.update(contract=CONTRACT,
                   describes_the_world=self.describes_the_world)
        return out


@dataclass(frozen=True)
class CausalResolution:
    """What became of one question, and what would change the answer."""

    question: CausalQuestion
    state: str
    detail: str
    missing_prerequisite: str = ""
    information_requirement: str = ""
    fit: Optional[SC.SyntheticControlFit] = None
    diagnostics: Optional[dict] = None
    donors_considered: int = 0
    donors_included: int = 0

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise QuestionRejected(f"unknown state {self.state!r}")

    @property
    def estimated(self) -> bool:
        return self.state not in NOT_AN_ESTIMATE

    @property
    def resolution_id(self) -> str:
        raw = "|".join((self.question.causal_question_id, self.state))
        return "cres_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT,
            "record": "causal_resolution",
            "resolution_id": self.resolution_id,
            "question": self.question.as_dict(),
            "question_origin": self.question.question_origin,
            "describes_the_world": self.question.describes_the_world,
            "state": self.state,
            "detail": self.detail,
            "missing_prerequisite": self.missing_prerequisite,
            "information_requirement": self.information_requirement,
            "donors_considered": self.donors_considered,
            "donors_included": self.donors_included,
            "estimated": self.estimated,
            "fit": self.fit.as_dict() if self.fit is not None else None,
            "diagnostics": self.diagnostics,
            # SPELLED OUT ON EVERY ROW. A later reader with only this record in
            # front of them must not be able to read a refusal as a null
            # result, which is what every "no significant effect" line in every
            # competitive-intelligence product actually means.
            "note": ("a state other than ESTIMATE_SUPPORTED or "
                     "ESTIMATE_BOUNDED is not a zero effect; it is an "
                     "identification that was not available"),
        }


# --- building questions from what is on the ledger ------------------------------

def questions_from_events(events: Sequence[dict], *, as_of: str,
                          outcome_variable: str = "",
                          limit: int = 0) -> List[CausalQuestion]:
    """One question per dated company event.

    THE TREATMENT DATE IS THE EVENT'S. It is read from the record and never
    searched for. A date chosen by scanning the outcome for its largest move is
    the defect the in-time placebo exists to catch, and the cheapest place to
    prevent it is here, where the date is assigned.

    `outcome_variable` names what the question is about and defaults to the
    company's own measured path. It is set BEFORE any data are looked at; a
    caller that picked it after seeing which series moved would be choosing the
    answer.
    """
    out: List[CausalQuestion] = []
    for row in events:
        company = str(row.get("subject_company") or "").strip()
        occurred = str(row.get("observed_at") or "").strip()
        if not company or not occurred:
            # An event with no subject or no date cannot anchor a question.
            # Skipped rather than defaulted: a treatment assigned to "today"
            # because the record had no date is a fabricated treatment.
            continue
        evidence_id = str(row.get("evidence_id") or "")
        outcome = outcome_variable or f"{company}:outcome_path"
        out.append(CausalQuestion(
            causal_question_id="cq_" + hashlib.sha256(
                f"{company}|{evidence_id}|{occurred}".encode("utf-8")
            ).hexdigest()[:16],
            company_id=company,
            treatment_event_id=evidence_id,
            treatment_type=str(row.get("evidence_type") or "UNKNOWN"),
            treatment_at=occurred,
            outcome_variable=outcome,
            question_origin=EVENT_DERIVED,
            known_at=str(row.get("available_at") or occurred),
            source=str(row.get("source") or ""),
        ))
        if limit and len(out) >= limit:
            break
    return out


def comparable_units(observations: Sequence[dict], *, outcome_variable: str
                     ) -> Tuple[List[str], List[DonorDecision]]:
    """Which other units measure the same thing, and why the rest do not.

    Comparability is decided on the metadata a series carries about itself —
    what it measures, in what unit, at what frequency — and never on how the
    numbers behave. Every rejection is recorded with its reason, so a thin pool
    is visibly thin rather than silently small.
    """
    by_series: Dict[str, List[dict]] = {}
    for row in observations:
        by_series.setdefault(str(row.get("series_id") or ""), []).append(row)
    by_series.pop("", None)

    treated = by_series.get(outcome_variable)
    if not treated:
        return [], []

    kind = treated[0].get("state_kind")
    unit = treated[0].get("unit")
    treated_n = len(treated)

    included, decisions = [], []
    for series_id, rows in sorted(by_series.items()):
        if series_id == outcome_variable:
            continue
        if rows[0].get("state_kind") != kind:
            decisions.append(DonorDecision(
                series_id, False,
                f"measures {rows[0].get('state_kind')!r}, not {kind!r}"))
            continue
        if rows[0].get("unit") != unit:
            decisions.append(DonorDecision(
                series_id, False,
                f"in {rows[0].get('unit')!r}, not {unit!r}; a weighted "
                "average across units is not a counterfactual"))
            continue
        # FREQUENCY, VIA OBSERVATION COUNT OVER THE SAME HISTORY. A monthly
        # series cannot be a donor for a daily one: the panel would be ragged,
        # and the alternative — resampling — silently changes which
        # observations the fit saw.
        ratio = len(rows) / treated_n if treated_n else 0.0
        if not 0.5 <= ratio <= 2.0:
            decisions.append(DonorDecision(
                series_id, False,
                f"{len(rows)} observations against the treated unit's "
                f"{treated_n}; a different frequency makes a ragged panel"))
            continue
        included.append(series_id)
        decisions.append(DonorDecision(series_id, True,
                                       f"same {kind} in {unit}, "
                                       f"{len(rows)} observations"))
    return included, decisions


def _series_values(observations: Sequence[dict], series_id: str
                   ) -> List[Tuple[str, float]]:
    out = []
    for row in observations:
        if str(row.get("series_id") or "") != series_id:
            continue
        period = str(row.get("reference_period") or "")
        try:
            out.append((period, float(row.get("value"))))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def resolve(question: CausalQuestion, observations: Sequence[dict], *,
            as_of: str = "") -> CausalResolution:
    """Walk the state machine, stopping at the first thing that is missing.

    Every exit names a prerequisite and, where one exists, the information that
    would change the answer. That second half is what makes this a decision
    rather than a shrug: `PANEL_UNAVAILABLE` on a company whose path nobody
    measures is not a dead end, it is a request for one series.
    """
    def stop(state, detail, prerequisite="", requirement="",
             considered=0, included=0, fit=None, diagnostics=None):
        return CausalResolution(
            question=question, state=state, detail=detail,
            missing_prerequisite=prerequisite,
            information_requirement=requirement,
            donors_considered=considered, donors_included=included,
            fit=fit, diagnostics=diagnostics)

    treated = _series_values(observations, question.outcome_variable)
    if not treated:
        return stop(
            PANEL_UNAVAILABLE,
            f"no measured path exists for {question.outcome_variable!r}; the "
            f"engine holds the {question.treatment_type} event and nothing it "
            "could have moved",
            NO_OUTCOME_SERIES,
            f"a dated series for {question.outcome_variable} spanning the "
            f"window around {question.treatment_at}; without it no method can "
            "identify anything, and no amount of donor data substitutes")

    donors, decisions = comparable_units(
        observations, outcome_variable=question.outcome_variable)
    considered = len(decisions)
    if not donors:
        return stop(
            DONOR_SUPPORT_INSUFFICIENT,
            f"{considered} other series were considered and none measures the "
            "same quantity in the same unit at the same frequency",
            NO_COMPARABLE_UNITS,
            "at least one other unit measuring the same quantity; a "
            "counterfactual built from a different quantity is an "
            "extrapolation with a confidence interval",
            considered=considered)

    # THE PLACEBO NEEDS A POPULATION, NOT A COMPANION. `causal_diagnostics`
    # ranks the treated unit against a distribution built by treating each
    # donor as treated, and with n donors the most extreme achievable rank is
    # 1/(n+1). Below the pool size at which that can clear the threshold, an
    # estimate could be produced and could never be defended, so the honest
    # stop is here rather than after a fit nothing can adjudicate.
    needed = int(round(1.0 / CD.PLACEBO_RANK_SHARE)) - 1
    if len(donors) < needed:
        return stop(
            DONOR_SUPPORT_INSUFFICIENT,
            f"{len(donors)} comparable unit(s) of {considered} considered, "
            f"against the {needed} a placebo distribution needs to reach "
            f"{CD.PLACEBO_RANK_SHARE:.0%}; a fit here could be produced and "
            "could not be defended",
            TOO_FEW_DONORS,
            f"at least {needed} comparable units; the shortfall is "
            f"{needed - len(donors)}",
            considered=considered, included=len(donors))

    periods = [p for p, _ in treated]
    pre = [i for i, p in enumerate(periods) if p < question.treatment_at]
    if len(pre) < SC.MINIMUM_PRE_PERIOD:
        # PANEL_UNAVAILABLE, not a donor problem: the donors are fine and the
        # treated unit's own history is too short. The prerequisite field
        # carries which of the two it was, because "get more donors" and "wait
        # for more history" are different actions.
        return stop(
            PANEL_UNAVAILABLE,
            f"{len(pre)} observation(s) before {question.treatment_at} against "
            f"a floor of {SC.MINIMUM_PRE_PERIOD}",
            SHORT_PRE_PERIOD,
            f"{SC.MINIMUM_PRE_PERIOD - len(pre)} more observation(s) before "
            "the treatment date",
            considered=considered, included=len(donors))
    treatment_index = len(pre)
    if treatment_index >= len(treated):
        return stop(
            PANEL_UNAVAILABLE,
            f"the treatment at {question.treatment_at} is at or after the last "
            "observation; there is no post-period to look at",
            NO_POST_PERIOD,
            "observations after the treatment date",
            considered=considered, included=len(donors))

    pool = {}
    for series_id in donors:
        values = _series_values(observations, series_id)
        by_period = dict(values)
        pool[series_id] = [by_period.get(p) for p in periods]
    ragged = [s for s, v in pool.items() if any(x is None for x in v)]
    for series_id in ragged:
        pool.pop(series_id)
    if len(pool) < needed:
        return stop(
            DONOR_SUPPORT_INSUFFICIENT,
            f"{len(ragged)} comparable unit(s) do not cover every period the "
            f"treated unit does, leaving {len(pool)} against {needed}",
            RAGGED_FREQUENCY,
            "comparable units observed on the same dates as the treated unit",
            considered=considered, included=len(pool))

    fit = SC.fit([v for _, v in treated], pool,
                 treatment_index=treatment_index,
                 treated_unit=question.outcome_variable, as_of=as_of)
    if not fit.fitted:
        state = PRE_FIT_FAILED if fit.status == SC.REFUSED_POOR_PRE_FIT \
            else DONOR_SUPPORT_INSUFFICIENT
        return stop(state, f"{fit.status}: {fit.refusal_detail}",
                    considered=considered, included=len(pool), fit=fit)

    stressed = CD.stress(fit, [v for _, v in treated], pool, as_of=as_of)
    placebo = next((d for d in stressed["diagnostics"]
                    if d["name"] == "in_space_placebo"), None)
    if placebo and placebo["result"] == EM.UNTESTED:
        return stop(PLACEBO_UNRESOLVED, placebo["evidence"],
                    considered=considered, included=len(pool), fit=fit,
                    diagnostics=stressed)
    state = ESTIMATE_SUPPORTED if stressed["causal_reading_allowed"] \
        else ESTIMATE_BOUNDED
    return stop(state, stressed["why"], considered=considered,
                included=len(pool), fit=fit, diagnostics=stressed)


def summarise(resolutions: Sequence[CausalResolution]) -> dict:
    """Telemetry. Every state present at zero, and the two populations apart.

    A count that mixes SYNTHETIC_TEST resolutions into the real ones would let
    the test suite report the capability as working. They are counted
    separately and the real count is the one the report leads with.
    """
    by_state = {state: 0 for state in STATES}
    by_prerequisite = {p: 0 for p in PREREQUISITES}
    real = [r for r in resolutions if r.question.describes_the_world]
    for got in real:
        by_state[got.state] = by_state.get(got.state, 0) + 1
        if got.missing_prerequisite:
            by_prerequisite[got.missing_prerequisite] = \
                by_prerequisite.get(got.missing_prerequisite, 0) + 1
    return {
        "contract": CONTRACT,
        "questions": len(real),
        "synthetic_excluded": len(resolutions) - len(real),
        "estimated": sum(1 for r in real if r.estimated),
        "by_state": by_state,
        "by_missing_prerequisite": by_prerequisite,
        "information_requirements": sorted({r.information_requirement
                                            for r in real
                                            if r.information_requirement}),
        "note": ("states other than ESTIMATE_* are identifications that were "
                 "not available, never effects of zero; every state is "
                 "present at zero so an empty category reads as measured"),
    }
