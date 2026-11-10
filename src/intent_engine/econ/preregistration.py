"""§7/§8: the forecast families, committed before any result is seen.

WHY A HASH
----------
"We decided the targets in advance" is unfalsifiable if the targets live in a
file anyone can edit after the fact. So the declaration below is hashed, the
hash is written into the experiment output, and `assert_unchanged` refuses to
run an experiment against a declaration that moved.

That does not make cheating impossible -- nothing does, in a repository one
person controls. It makes cheating VISIBLE, which is the achievable version.

WHAT IS DECLARED
----------------
For each family: the target series, the horizon, what counts as the event,
the loss function, and the baseline the model has to beat. Fixed before any
model is fitted, because the alternative -- choosing the horizon after seeing
which one worked -- is the single easiest way to manufacture a result, and it
leaves no trace at all.

WHY DIRECTIONAL EVENTS
----------------------
Every family is "did this quantity rise over the horizon". Not because
direction is the most interesting question but because it is the one where a
Brier score means something and where the base rate is a real benchmark.
Magnitude forecasts on revised macro series mostly measure the revision.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_preregistration.v1"

DIRECTIONAL = "DIRECTIONAL"
BRIER = "BRIER"


@dataclass(frozen=True)
class Family:
    """One forecast family, fixed in advance."""

    family_id: str
    label: str
    target_series: str
    horizon_days: int
    event: str
    loss: str
    baselines: Tuple[str, ...]
    rationale: str
    #: Which measurable constructs are hypothesised to matter here, declared
    #: up front so a construct cannot be credited for a family nobody
    #: expected it to help with.
    expected_constructs: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require(self.horizon_days > 0, "a forecast looks forward")
        require(bool(self.event.strip()), "state what counts as the event")
        require(bool(self.baselines),
                f"{self.family_id}: name the baseline the model must beat, "
                "or 'improvement' means improvement over nothing")

    @property
    def target_id_prefix(self) -> str:
        return f"{self.target_series}/{self.horizon_days}d"

    def as_dict(self) -> dict:
        return {"family_id": self.family_id, "label": self.label,
                "target_series": self.target_series,
                "horizon_days": self.horizon_days, "event": self.event,
                "loss": self.loss, "baselines": list(self.baselines),
                "rationale": self.rationale,
                "expected_constructs": list(self.expected_constructs),
                "target_id_prefix": self.target_id_prefix}


#: §7's minimum families. Two horizons each: roughly two and four quarters.
FAMILIES: Tuple[Family, ...] = tuple(
    Family(family_id=f"{fid}_{h}d", label=f"{label} ({h}d)",
           target_series=series, horizon_days=h, event=event, loss=BRIER,
           baselines=("base_rate", "persistence", "base_economic_model"),
           rationale=rationale, expected_constructs=constructs)
    for fid, label, series, event, rationale, constructs in (
        ("consumption", "real consumption", "PCEC96",
         "real personal consumption is higher at the horizon than at the "
         "origin",
         "the collective layer's central claim is that households defer "
         "spending before the aggregates show it; this is where that claim "
         "is most directly testable",
         ("financial_anxiety", "future_orientation", "time_horizon")),
        ("labour", "labour deterioration", "UNRATE",
         "the unemployment rate is higher at the horizon than at the origin",
         "workers' read of their own options is hypothesised to move before "
         "the unemployment rate does; if it does not, perceived_control is a "
         "labour statistic wearing a psychological name",
         ("perceived_control", "perceived_security")),
        ("credit_stress", "credit stress", "DRCCLACBS",
         "credit card delinquency is higher at the horizon than at the origin",
         "delinquency is a lagging record of a decision made months earlier, "
         "so anything that leads it is genuinely early information",
         ("financial_anxiety", "perceived_security")),
        ("housing", "housing activity", "HOUST",
         "housing starts are higher at the horizon than at the origin",
         "Section 21's consensus-attacking case: rate cuts are supposed to "
         "revive housing, and the alternative is that insecurity blocks the "
         "transmission",
         ("financial_anxiety", "time_horizon")),
        ("industrial", "industrial production", "INDPRO",
         "industrial production is higher at the horizon than at the origin",
         "a downstream test: household behaviour reaching manufacturing "
         "through orders should be slower and weaker than the direct "
         "consumption channel, and if it is not, something is wrong",
         ("future_orientation", "time_horizon")),
    )
    for h in (180, 360)
)

BY_ID: Dict[str, Family] = {f.family_id: f for f in FAMILIES}
TARGET_SERIES: Tuple[str, ...] = tuple(sorted({f.target_series
                                               for f in FAMILIES}))
HORIZONS: Tuple[int, ...] = tuple(sorted({f.horizon_days for f in FAMILIES}))


def declaration() -> dict:
    """Everything that was fixed in advance, in one hashable object."""
    return {"contract": CONTRACT,
            "families": [f.as_dict() for f in FAMILIES],
            "target_series": list(TARGET_SERIES),
            "horizons": list(HORIZONS),
            "loss": BRIER,
            "rule": ("every family is scored the same way, on the same "
                     "origins, with the same folds; the ONLY difference "
                     "between the two models is the feature block")}


def declaration_hash() -> str:
    return hashlib.sha256(
        json.dumps(declaration(), sort_keys=True).encode()).hexdigest()[:16]


def assert_unchanged(expected: str) -> None:
    """Refuse to run against a declaration that moved."""
    actual = declaration_hash()
    if actual != expected:
        raise EconError(
            f"the preregistered declaration changed: expected {expected}, "
            f"now {actual}. Targets or horizons were edited after the "
            "experiment was designed, which is the easiest way to manufacture "
            "a result and leaves no other trace.")


def families_for(construct: str) -> List[Family]:
    """Families this construct was expected to help with, declared up front."""
    return [f for f in FAMILIES if construct in f.expected_constructs]


def summarise() -> dict:
    return {"contract": CONTRACT, "families": len(FAMILIES),
            "declaration_hash": declaration_hash(),
            "target_series": list(TARGET_SERIES),
            "horizons": list(HORIZONS),
            "by_family": {f.family_id: f.as_dict() for f in FAMILIES}}


# =============================================================================
# §4: THE REGIME-CONDITIONAL HYPOTHESIS
# =============================================================================
# Declared BEFORE any regime-conditional result was computed. The global test
# (GLOBAL_COLLECTIVE_HUMAN_STATE_V1) is frozen at delta -0.00948, CI
# [-0.02618, +0.00661]; it did not clear the bar. This is the ONE follow-up
# hypothesis, stated in advance so that it is a test rather than a search.
#
# WHY THIS HYPOTHESIS AND NOT ANOTHER. The global run's regime breakdown
# showed +0.029 in credit stress against negative deltas in calm regimes, at
# n=80 with an MDE of 0.040 -- suggestive and unresolved. Following it is
# legitimate; following whichever subgroup happened to look best after seeing
# ALL of them would not be, which is why exactly one is declared here and the
# negative control is declared with it.

REGIME_HYPOTHESIS = {
    "hypothesis_id": "H2_REGIME_CONDITIONAL",
    "statement": (
        "CollectiveHumanState provides greater incremental predictive value "
        "during credit and liquidity stress than during calm expansion."),
    "primary_regimes": ("CREDIT_STRESS", "LIQUIDITY_STRESS"),
    #: The regime where the layer is expected to add NOTHING. A layer that
    #: claims value here as well is claiming value everywhere, and that is a
    #: reason to disbelieve the crisis result rather than to celebrate both.
    "negative_control_regime": "LOW_VOL_EXPANSION",
    "primary_targets": ("credit_stress", "consumption", "housing", "labour"),
    "primary_horizons": (180, 360),
    "prediction": (
        "delta in the primary regimes is positive and its interval excludes "
        "zero, AND delta in the negative-control regime is not positive"),
    "falsifier": (
        "delta in the primary regimes does not exceed the negative-control "
        "delta by more than the sampling error of both, or the layer shows "
        "the same value in calm periods as in stressed ones"),
    "decision_rule": (
        "PROMOTE_REGIME_CONDITIONAL only if the stressed-regime interval "
        "excludes zero AND the calm-regime interval does not. Anything else "
        "is TESTED_NOT_PROMOTED or INSUFFICIENT_DATA -- never a global "
        "promotion, because a global claim was already tested and failed."),
    "comparator": "GLOBAL_COLLECTIVE_HUMAN_STATE_V1",
}


def regime_declaration() -> dict:
    return {"contract": CONTRACT, "hypothesis": REGIME_HYPOTHESIS,
            "families": [f.as_dict() for f in FAMILIES]}


def regime_hypothesis_hash() -> str:
    return hashlib.sha256(
        json.dumps(regime_declaration(), sort_keys=True).encode()
    ).hexdigest()[:16]


# =============================================================================
# §11: THE V2 HYPOTHESES
# =============================================================================
# Declared BEFORE the monthly panel finished building and BEFORE any result on
# it was computed. The ordering matters more than usual here: the previous
# cycle's most attractive number (INFLATION_SHOCK +0.171) was not
# preregistered, and scrutinising it cost more than testing it would have.
#
# Four hypotheses, four different CLAIMS, because "does the collective layer
# help" has been answered no and the interesting question is now what it
# might be FOR. A layer can be useless for probability accuracy and useful for
# lead time, and collapsing those into one test is how a real narrow effect
# gets buried under a broad null.
#
# Each names its own falsifier and its own decision rule. None may be edited
# after `V2_HASH` is recorded in a result.

V2_HYPOTHESES = (
    {
        "hypothesis_id": "H3_GLOBAL_MONTHLY",
        "statement": (
            "On the monthly vintage-safe panel, adding the collective-state "
            "block improves out-of-sample Brier score globally."),
        "primary_metric": "paired Brier delta, base minus augmented",
        "prediction": (
            "delta > 0 with an origin-clustered 95% interval excluding zero, "
            "on at least 3 independent episodes"),
        "falsifier": (
            "the interval includes zero at a sample whose MDE is below the "
            "delta the frozen V1 interval still admits (+0.00661) -- i.e. the "
            "monthly panel could have resolved an effect of the size V1 left "
            "open, and did not"),
        "decision_rule": (
            "SUPPORTED only if the interval excludes zero AND >=3 episodes. "
            "NOT_SUPPORTED if the interval includes zero and the MDE is "
            "below 0.00661. INSUFFICIENT_POWER otherwise."),
        "negative_control": "LOW_VOL_EXPANSION",
    },
    {
        "hypothesis_id": "H4_STRESS_CONDITIONAL",
        "statement": (
            "The collective-state block adds value specifically when "
            "financial or economic stress is elevated, and not in calm "
            "expansion."),
        "primary_metric": "paired Brier delta within contemporaneously "
                          "classified stress regimes",
        "prediction": (
            "delta in stressed origins is positive with an interval "
            "excluding zero, on >=3 independent episodes, AND the calm "
            "control's interval does not exclude zero on the positive side"),
        "falsifier": (
            "the stressed interval includes zero at adequate power, OR the "
            "calm control shows the same effect -- which would make it a "
            "global claim that H3 already tests"),
        "decision_rule": (
            "PROMOTE_REGIME_CONDITIONAL only on both halves. A stressed win "
            "alongside a calm win is TESTED_NOT_PROMOTED, not two wins."),
        "negative_control": "LOW_VOL_EXPANSION",
    },
    {
        "hypothesis_id": "H5_EARLY_WARNING",
        "statement": (
            "Collective-state features raise the alarm on a deterioration "
            "episode EARLIER than the economic block alone, even where final "
            "probability accuracy does not improve."),
        "primary_metric": ("days between first sustained warning and the "
                           "episode's first stressed origin, augmented minus "
                           "base"),
        "prediction": (
            "median lead-time delta > 0 across episodes, WITHOUT an increase "
            "in the false-alarm rate outside episodes"),
        "falsifier": (
            "lead time improves only because the augmented model warns more "
            "often -- measured as a false-alarm rate that rises at least as "
            "fast as the lead time"),
        "decision_rule": (
            "PROMOTE_EARLY_WARNING requires a positive lead-time delta on "
            ">=3 episodes AND a false-alarm rate no worse than the base "
            "model's. A model that warns 60 days earlier by warning "
            "constantly has not improved."),
        "negative_control": "false-alarm rate in LOW_VOL_EXPANSION origins",
    },
    {
        "hypothesis_id": "H6_TRANSMISSION",
        "statement": (
            "Collective-state features explain residual variation left by "
            "conventional economic transmission -- the cases where the "
            "mechanism predicted a move and the target did not respond."),
        "primary_metric": ("Brier on the subset of origins where the "
                           "conventional mechanism's signal and the realised "
                           "outcome disagree"),
        "prediction": (
            "the collective block reduces loss on transmission-failure "
            "origins by more than it does on transmission-success origins"),
        "falsifier": (
            "the improvement on failure origins is no larger than on "
            "success origins, or the failure subset is too small to "
            "separate the two"),
        "decision_rule": (
            "PROMOTE_TRANSMISSION_CONTEXT requires the failure-subset delta "
            "to exceed the success-subset delta with an interval on the "
            "DIFFERENCE that excludes zero. Better fit alone is not causal "
            "and is not enough."),
        "negative_control": "transmission-success origins",
    },
)

BY_HYPOTHESIS: Dict[str, dict] = {h["hypothesis_id"]: h
                                  for h in V2_HYPOTHESES}


def v2_declaration() -> dict:
    return {"contract": CONTRACT,
            "hypotheses": list(V2_HYPOTHESES),
            "families": [f.as_dict() for f in FAMILIES],
            "supersedes": "H2_REGIME_CONDITIONAL",
            "rule": ("declared before the monthly panel produced a single "
                     "result; every reported V2 number carries this hash, "
                     "and `assert_v2_unchanged` refuses a run against a "
                     "declaration that moved")}


def v2_hash() -> str:
    return hashlib.sha256(
        json.dumps(v2_declaration(), sort_keys=True).encode()).hexdigest()[:16]


def assert_v2_unchanged(expected: str) -> None:
    actual = v2_hash()
    if actual != expected:
        raise EconError(
            f"the V2 declaration changed: expected {expected}, now {actual}. "
            "H3-H6 were fixed before the monthly panel produced a result; "
            "editing them afterwards is the mutation break proof 11 exists "
            "to catch.")


# =============================================================================
# §7: H7 — THE SENTIMENT LEAD, AS A FIRST-CLASS HYPOTHESIS
# =============================================================================
# The previous run found ONE replicated result: consumer sentiment leads
# housing starts by 6-8 months and industrial production by 7-8 months, on
# vintage-walled data, in two independent arms. It was recorded OBSERVED and
# explicitly NOT predictive.
#
# That is the right state for a temporal-order measurement and the wrong place
# to leave it. A lead is necessary for early warning and not sufficient: the
# lead can be entirely explained by variables the economic model already has,
# in which case sentiment is LEADING_BUT_REDUNDANT -- a real relationship with
# no incremental value. H7 is the test that separates those.
#
# DECLARED BEFORE THE V3 PANEL WAS EVALUATED. The targets, horizons, feature
# set, metrics, partitions and episode floor are all fixed here, and
# `assert_h7_unchanged` refuses a run against a declaration that moved.
#
# WHY SENTIMENT ALONE AND NOT THE WHOLE BLOCK. H3 already tested the block and
# was not supported. Testing the block again under a new name would be the
# same hypothesis with the failures discarded. H7 adds exactly one column.

H7 = {
    "hypothesis_id": "H7_SENTIMENT_EARLY_WARNING",
    "statement": (
        "Contemporaneously available consumer sentiment (UMCSENT, read at the "
        "forecast origin through the vintage wall) contains incremental "
        "information about future housing activity and industrial production "
        "at a 6-8 month horizon, BEYOND the conventional economic block."),
    "targets": ("HOUST", "INDPRO"),
    #: 180 and 240 days. The measured lead was 6-8 months for housing and 7-8
    #: for industrial production; these bracket it. Fixed now so that the
    #: horizon cannot be chosen after seeing which one worked.
    "horizons": (180, 240),
    "feature_added": ("UMCSENT",),
    "base_block": ("UNRATE", "CPIAUCSL", "DFF", "DGS2", "DGS10", "HOUST",
                   "INDPRO", "PCEC96", "BAA", "BAA10Y", "AAA10Y", "T10Y3M"),
    "metrics": ("paired_brier_delta", "origin_clustered_interval",
                "episode_aware_interval", "lead_time_raw",
                "lead_time_alarm_matched", "false_alarm_rate"),
    "partitions": ("blocked_expanding_folds", "folds=5", "embargo_days=45",
                   "purge_outcomes_resolving_into_test_window"),
    "episode_floor": 3,
    "prediction": (
        "the paired Brier delta is positive with an episode-aware interval "
        "excluding zero on at least 3 independent episodes, OR the "
        "alarm-matched lead time is positive on at least 3 episodes without "
        "an increase in the false-alarm rate"),
    "falsifier": (
        "the episode-aware interval includes zero at a sample whose "
        "detectable effect is smaller than the interval V2 still admits, AND "
        "the alarm-matched lead-time delta is not positive. A lead that "
        "disappears once the economic block is conditioned on is "
        "LEADING_BUT_REDUNDANT, which is a refutation of H7 and not a "
        "weaker form of support."),
    "decision_rule": (
        "PROMOTE_GLOBAL_FORECAST on a supported Brier delta. "
        "PROMOTE_EARLY_WARNING on a supported alarm-matched lead time with no "
        "worse false alarms. LEADING_BUT_REDUNDANT when the temporal order "
        "holds and neither metric clears. INSUFFICIENT_POWER when the sample "
        "could not have resolved either. Never a global promotion on a "
        "lead-time result, and never an early-warning promotion on a raw "
        "lead time that vanishes when alarms are matched."),
    "negative_control": (
        "the same test on the calm regime, and the raw-versus-alarm-matched "
        "comparison. A model that warns earlier only because it warns more "
        "has not warned earlier."),
    "supersedes_observation": ("UMCSENT->HOUST and UMCSENT->INDPRO, recorded "
                               "OBSERVED in WORLD_MODEL_RESEARCH_V2"),
}


def h7_declaration() -> dict:
    return {"contract": CONTRACT, "hypothesis": H7,
            "rule": ("declared before the V3 panel was evaluated; every "
                     "reported H7 number carries this hash")}


def h7_hash() -> str:
    return hashlib.sha256(
        json.dumps(h7_declaration(), sort_keys=True).encode()).hexdigest()[:16]


def assert_h7_unchanged(expected: str) -> None:
    actual = h7_hash()
    if actual != expected:
        raise EconError(
            f"the H7 declaration changed: expected {expected}, now {actual}. "
            "The targets, horizons and feature set were fixed before the V3 "
            "panel produced a number; editing them afterwards is break proof "
            "8's mutation.")
