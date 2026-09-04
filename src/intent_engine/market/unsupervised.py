"""Structure the engine was not told to look for.

WHAT UNSUPERVISED LEARNING IS FOR HERE
--------------------------------------
It is a HYPOTHESIS GENERATOR and nothing else. A clustering of the last two
years of macro data can suggest that the economy has been in two distinguishable
states; it cannot establish that either of them is "stagflation", that a
company belongs to one, or that anything follows. The single most dangerous
thing this module could do is let a cluster label become a fact, so a
`Discovery` carries the standing DISCOVERED, it has no path to OBSERVED, and
`as_fact` raises rather than returning something usable.

WHY THE CLUSTERS ARE CALLED REGIME_1
------------------------------------
Because that is what the method found. Naming a cluster "tightening" imports an
economic claim the arithmetic did not make, and once the name exists every
later reader treats it as a finding. Interpretation is a separate, evidenced
step; until then the labels are ordinals.

WHY A DETERMINISTIC RULE IS BENCHMARKED ALONGSIDE
-------------------------------------------------
A rule that says "rates up and inflation up is tightening" is free, legible and
often right. A mixture model that agrees with it has told you nothing you did
not have; a mixture model that disagrees is either a discovery or a bug, and
you cannot tell which without the rule to disagree WITH. So both run, and both
are scored on the same four questions.

HOW A DISCOVERY IS SCORED
-------------------------
Not by silhouette alone. A geometrically tidy partition of noise is tidy noise.
Four scores, reported separately because they fail separately:

    separation   are the groups distinguishable at all
    coherence    do they persist in time, or alternate every month
    stability    do they survive being refitted without the last few months
    utility      does knowing the group reduce forecast error on a held-out
                 series, compared with not knowing it

Only the last one is economic. A discovery that scores well on the first three
and nothing on the fourth is a pattern in the data, which is not the same thing
as a pattern in the economy.
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import macro_state as MS

CONTRACT = "unsupervised.v1"

# --- what was discovered ----------------------------------------------------
REGIME = "REGIME"                  # a state of the economy over time
EXPOSURE_CLUSTER = "EXPOSURE_CLUSTER"   # companies that look alike
ANOMALY = "ANOMALY"                # a period or actor that fits nothing
DISCOVERY_KINDS = (REGIME, EXPOSURE_CLUSTER, ANOMALY)

# --- how firmly ---------------------------------------------------------------
#
# One value, deliberately. There is no promotion ladder inside this module,
# because every rung would be a way for a cluster to become more true without
# any evidence arriving. Promotion happens elsewhere, by finding evidence.
DISCOVERED = "DISCOVERED"

# --- the methods --------------------------------------------------------------
RULE = "RULE"                      # a stated deterministic partition
KMEANS = "KMEANS"
GAUSSIAN_MIXTURE = "GAUSSIAN_MIXTURE"
CHANGE_POINT = "CHANGE_POINT"
ISOLATION = "ISOLATION"            # anomaly scoring
METHODS = (RULE, KMEANS, GAUSSIAN_MIXTURE, CHANGE_POINT, ISOLATION)

#: The opponent for regime discovery, as the random walk is for forecasting.
BASELINE_METHOD = RULE


class DiscoveryRejected(ValueError):
    """A discovery that claimed more than a partition can claim."""


class NotEvidence(DiscoveryRejected):
    """Raised when a caller asks a cluster to behave like an observation."""


@dataclass(frozen=True)
class Discovery:
    """One group the data suggested, with no claim that it means anything."""

    kind: str
    method: str
    label: str
    #: What is in the group: period strings for a regime, company ids for an
    #: exposure cluster, a single period or company for an anomaly.
    members: Tuple[str, ...] = ()
    #: The features that separate this group from the others, most first.
    distinguishing: Tuple[Tuple[str, float], ...] = ()
    #: The question that would turn this into knowledge. A discovery without
    #: one is a decoration.
    research_question: str = ""
    as_of: str = ""
    standing: str = DISCOVERED
    note: str = ""

    def __post_init__(self) -> None:
        if self.kind not in DISCOVERY_KINDS:
            raise DiscoveryRejected(f"unknown discovery kind {self.kind!r}")
        if self.method not in METHODS:
            raise DiscoveryRejected(f"unknown method {self.method!r}")
        if self.standing != DISCOVERED:
            raise DiscoveryRejected(
                "a discovery has exactly one standing; anything stronger has "
                "to be earned by evidence outside this module")
        if not self.research_question:
            raise DiscoveryRejected(
                "a discovery must name the observation that would test it: a "
                "cluster nobody can go and check is not a hypothesis, it is a "
                "picture")

    def as_fact(self, *_a, **_k):
        """Deliberately not implemented, and deliberately present.

        Every consumer of a clustering eventually wants to write down that
        company X IS capital-intensive because it landed beside three
        companies that are. That inference has no evidence in it — the
        clustering used the very fields it would be attesting to, or fields
        correlated with them — and it would put a manufactured exposure into
        the ledger with a real-looking provenance.
        """
        raise NotEvidence(
            f"{self.label} is a group the data suggested, not something a "
            "source stated; ask the research question and record what comes "
            "back")

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT, members=list(self.members),
                 distinguishing=[list(x) for x in self.distinguishing],
                 size=len(self.members))
        return d


@dataclass(frozen=True)
class DiscoveryScore:
    """How well one partition did on the four questions that matter."""

    method: str
    groups: int
    separation: Optional[float] = None
    coherence: Optional[float] = None
    stability: Optional[float] = None
    utility: Optional[float] = None
    n: int = 0
    note: str = ""

    @property
    def economically_useful(self) -> bool:
        """Utility is the only score that can answer this, and it may be None.

        None is not False and not True. An unmeasured utility means the
        held-out test could not be run, and reporting that as "not useful"
        would let a missing measurement look like a negative result.
        """
        return bool(self.utility is not None and self.utility > 0)

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT,
                 economically_useful=self.economically_useful)
        return d


# --- turning a ledger of figures into a panel --------------------------------

def monthly_panel(observations: Sequence[MS.MacroObservation], *, as_of: str,
                  min_series: int = 3) -> Tuple[List[str], List[str],
                                                List[List[float]]]:
    """(periods, series ids, values) — one row per month, one column per series.

    VINTAGE-CORRECT PER MONTH, not vintage-correct once. For month M the panel
    holds the latest figure for a period at or before M that was PUBLISHED by
    the end of M — which is what a reader had that month, and is usually not
    the figure that describes M. Building the panel from today's vintage and
    then labelling history with it is the leak that makes every regime model
    look prescient.

    Series that are absent for a month are carried forward from the last month
    they were present, and a month is dropped entirely if fewer than
    `min_series` columns have ever been seen: a row that is mostly carried
    values is mostly one month repeated.
    """
    known = MS.as_known_at(observations, as_of)
    if not known:
        return [], [], []
    months = sorted({o.reference_period[:7] for o in known})
    series_ids = sorted({o.series_id for o in known})

    by_series: Dict[str, List[MS.MacroObservation]] = {}
    for obs in known:
        by_series.setdefault(obs.series_id, []).append(obs)

    rows: List[List[float]] = []
    kept: List[str] = []
    carried: Dict[str, float] = {}
    previous: Optional[List[float]] = None
    for month in months:
        for sid in series_ids:
            candidates = [o for o in by_series[sid]
                          if o.reference_period[:7] <= month
                          and o.published_at[:7] <= month]
            if candidates:
                carried[sid] = max(
                    candidates,
                    key=lambda o: (o.reference_period, o.published_at)).value
        if len(carried) < min_series:
            continue
        row = [carried.get(sid, float("nan")) for sid in series_ids]
        # FRESHNESS IS "SOMETHING CHANGED", NOT "THIS MONTH'S FIGURE ARRIVED".
        # A monthly statistic is published weeks after the month it describes,
        # so no row ever contains its own month's figure — requiring one
        # emptied the panel completely and every regime model above it
        # silently reported "not enough history".
        if previous is not None and _same_row(row, previous):
            continue
        previous = row
        kept.append(month)
        rows.append(row)

    if not rows:
        return [], [], []

    # TRIM THE START, DO NOT DROP THE SERIES. A monthly figure is not readable
    # in the month it describes, so every slow publisher is missing from the
    # panel's first row — and requiring a column to be complete everywhere
    # deleted the US Treasury rate, the Canadian CPI and the policy rate over
    # one absent cell each. Keep a column if it is present for most of the
    # window, then cut leading months until the kept columns are all there.
    # Months are cheaper than conditions: a panel of three series over
    # twenty-five months can only discover something about three series.
    threshold = 0.8
    present = {i: sum(1 for r in rows if not math.isnan(r[i]))
               for i in range(len(series_ids))}
    usable = [i for i, n in present.items() if n >= threshold * len(rows)]
    if not usable:
        usable = [i for i, n in present.items() if n == len(rows)]
    start = 0
    for idx, row in enumerate(rows):
        if all(not math.isnan(row[i]) for i in usable):
            start = idx
            break
    else:
        return [], [], []
    return (kept[start:], [series_ids[i] for i in usable],
            [[r[i] for i in usable] for r in rows[start:]])


def _same_row(a: Sequence[float], b: Sequence[float]) -> bool:
    """Two panel rows that carry identical values, NaNs included."""
    if len(a) != len(b):
        return False
    return all((math.isnan(x) and math.isnan(y)) or x == y
               for x, y in zip(a, b))


def _standardise(matrix: Sequence[Sequence[float]]) -> List[List[float]]:
    """Z-score each column. A column with no variance becomes zeros.

    Unscaled features let one series decide the partition purely by being
    denominated in thousands of dollars rather than percent — the clustering
    would be reading the units.
    """
    if not matrix:
        return []
    cols = list(zip(*matrix))
    out_cols = []
    for col in cols:
        mean = sum(col) / len(col)
        var = sum((v - mean) ** 2 for v in col) / max(1, len(col) - 1)
        sd = math.sqrt(var)
        out_cols.append([0.0] * len(col) if sd <= 1e-12
                        else [(v - mean) / sd for v in col])
    return [list(r) for r in zip(*out_cols)]


def _differences(matrix: Sequence[Sequence[float]]) -> List[List[float]]:
    """Month-over-month change. A regime is about movement, not level.

    Levels alone cluster by WHEN, because most macro series trend: the model
    would rediscover the calendar and call it a regime.
    """
    return [[b - a for a, b in zip(prev, cur)]
            for prev, cur in zip(matrix, matrix[1:])]


# --- the deterministic opponent ----------------------------------------------

#: Which direction of which condition the rule reads. Stated, so the rule can
#: be wrong in a way somebody can point at.
_RULE_CONDITIONS = ((MS.MARKET_RATE, "rates"), (MS.INFLATION, "prices"),
                    (MS.EMPLOYMENT, "slack"))


def rule_regime(states: Sequence[MS.EconomicState]) -> str:
    """A legible partition, for the mixture model to have to beat.

    Four names and an explicit fifth for "the measured conditions do not
    combine into any of them". The fifth is the important one: a rule that
    always returns a regime is not a rule, it is a random label generator with
    good manners.
    """
    read = {}
    for kind, name in _RULE_CONDITIONS:
        got = [s for s in states if s.state_kind == kind and s.known]
        if got:
            read[name] = got[0].moved
    if len(read) < 2:
        return "UNCLASSIFIED"
    rates, prices = read.get("rates"), read.get("prices")
    if rates == MS.UP and prices == MS.UP:
        return "RULE_TIGHTENING_INTO_PRICES"
    if rates == MS.DOWN and prices == MS.DOWN:
        return "RULE_EASING_INTO_DISINFLATION"
    if rates == MS.UP and prices == MS.DOWN:
        return "RULE_RESTRICTIVE"
    if rates == MS.DOWN and prices == MS.UP:
        return "RULE_ACCOMMODATIVE"
    return "UNCLASSIFIED"


def _rule_labels(changes: Sequence[Sequence[float]], series_ids: Sequence[str],
                 kinds: Dict[str, str]) -> List[str]:
    """Apply `rule_regime` month by month, from the panel's own movements.

    Builds the minimum EconomicState each month needs to be classified: the
    direction of the conditions the rule reads. Anything the panel does not
    carry stays absent, and the rule answers UNCLASSIFIED rather than guessing
    — which is why UNCLASSIFIED shows up in the scores as a group of its own.
    """
    wanted = {kind for kind, _ in _RULE_CONDITIONS}
    columns = [(i, kinds.get(sid, "")) for i, sid in enumerate(series_ids)
               if kinds.get(sid, "") in wanted]
    out = []
    for row in changes:
        states = []
        for idx, kind in columns:
            moved = (MS.UP if row[idx] > 0 else
                     MS.DOWN if row[idx] < 0 else MS.FLAT)
            states.append(MS.EconomicState(
                state_kind=kind, standing=MS.OBSERVED, moved=moved,
                reason="panel movement"))
        out.append(rule_regime(states))
    return out


# --- scoring a partition ------------------------------------------------------

def _mean_run_length(labels: Sequence[int]) -> float:
    if not labels:
        return 0.0
    runs, current = 1, labels[0]
    for lab in labels[1:]:
        if lab != current:
            runs += 1
            current = lab
    return len(labels) / runs


def coherence(labels: Sequence[int]) -> Optional[float]:
    """Mean run length relative to what shuffling the same labels would give.

    Above 1 means the groups persist; at or below 1 they alternate, which is
    what a partition of noise looks like however good its geometry is.
    """
    if len(labels) < 4 or len(set(labels)) < 2:
        return None
    counts: Dict[int, int] = {}
    for lab in labels:
        counts[lab] = counts.get(lab, 0) + 1
    n = len(labels)
    # Expected number of runs for a random arrangement of the same multiset.
    expected_switches = sum(
        (n - c) * c for c in counts.values()) / (2.0 * n) if n else 0
    expected_runs = 1 + 2 * expected_switches
    if expected_runs <= 0:
        return None
    return round(_mean_run_length(labels) / (n / expected_runs), 4)


def separation(features: Sequence[Sequence[float]],
               labels: Sequence[int]) -> Optional[float]:
    """Silhouette, when the shapes allow it. Geometry only — never economics."""
    if len(set(labels)) < 2 or len(features) != len(labels) or \
            len(features) < 3:
        return None
    try:
        from sklearn.metrics import silhouette_score
    except Exception:  # pragma: no cover - sklearn is a hard dependency here
        return None
    try:
        return round(float(silhouette_score(features, labels)), 4)
    except Exception:  # noqa: BLE001 - degenerate partitions raise
        return None


def stability(features: Sequence[Sequence[float]], *, groups: int,
              method: str, holdout: int = 3) -> Optional[float]:
    """Agreement between the fit on everything and the fit without the tail.

    A regime model that reassigns half of history when three months are
    withheld has not found regimes; it has found this particular sample.
    """
    if len(features) < holdout + 6:
        return None
    full = _fit_labels(features, groups=groups, method=method)
    partial = _fit_labels(features[:-holdout], groups=groups, method=method)
    if full is None or partial is None:
        return None
    try:
        from sklearn.metrics import adjusted_rand_score
    except Exception:  # pragma: no cover
        return None
    return round(float(adjusted_rand_score(full[:-holdout], partial)), 4)


def utility(labels: Sequence[int], target: Sequence[float]) -> Optional[float]:
    """Does knowing the group reduce error on the next change in `target`?

    Compares "the next change is this group's mean change" against "the next
    change is the overall mean change", leave-one-out so a group is never
    scored against a mean it is inside. Positive is a real reduction in RMSE;
    zero or negative means the partition costs more than it explains.

    THE ONLY ECONOMIC SCORE HERE. Separation, coherence and stability all
    describe the partition. This one asks whether the partition tells you
    anything you did not already know.
    """
    if len(labels) != len(target) or len(target) < 6 or len(set(labels)) < 2:
        return None
    n = len(target)
    grouped, pooled = [], []
    for i in range(n):
        others = [j for j in range(n) if j != i]
        same = [j for j in others if labels[j] == labels[i]]
        if not same:
            continue
        grouped.append((target[i] - sum(target[j] for j in same)
                        / len(same)) ** 2)
        pooled.append((target[i] - sum(target[j] for j in others)
                       / len(others)) ** 2)
    if len(grouped) < 4:
        return None
    rmse_g = math.sqrt(sum(grouped) / len(grouped))
    rmse_p = math.sqrt(sum(pooled) / len(pooled))
    if rmse_p <= 0:
        return None
    return round(1.0 - rmse_g / rmse_p, 4)


def _fit_labels(features: Sequence[Sequence[float]], *, groups: int,
                method: str) -> Optional[List[int]]:
    """A deterministic fit, or nothing. Never a random one."""
    if len(features) < groups or groups < 2:
        return None
    try:
        if method == KMEANS:
            from sklearn.cluster import KMeans
            model = KMeans(n_clusters=groups, n_init=10, random_state=0)
        elif method == GAUSSIAN_MIXTURE:
            from sklearn.mixture import GaussianMixture
            model = GaussianMixture(n_components=groups, random_state=0,
                                    covariance_type="diag")
        else:
            return None
        return [int(x) for x in model.fit_predict(list(features))]
    except Exception:  # noqa: BLE001 - a degenerate fit is an absence
        return None


def discover_regimes(observations: Sequence[MS.MacroObservation], *,
                     as_of: str, groups: int = 2,
                     methods: Sequence[str] = (KMEANS, GAUSSIAN_MIXTURE),
                     target_series: str = "") -> dict:
    """Look for states of the economy nobody wrote down.

    Returns the partitions AND their scores, including the ones that failed,
    because a discovery layer that only reports what it liked cannot be
    audited. Every group comes back as a `Discovery` with a research question
    attached and no path to becoming a fact.
    """
    periods, series_ids, levels = monthly_panel(observations, as_of=as_of)
    if len(periods) < 8:
        return {"contract": CONTRACT, "as_of": as_of,
                "periods": len(periods), "discoveries": [], "scores": [],
                "note": (f"{len(periods)} months of panel is not enough to "
                         "separate a regime from a coincidence; 8 needed")}

    # Movement, standardised. Levels would rediscover the calendar.
    changes = _standardise(_differences(levels))
    change_periods = periods[1:]

    target_idx = (series_ids.index(target_series)
                  if target_series in series_ids else None)
    target = ([row[target_idx] for row in _differences(levels)]
              if target_idx is not None else [])

    # THE OPPONENT RUNS FIRST. A mixture model is only interesting relative to
    # the legible rule it is supposed to improve on, and scoring it alone
    # leaves nothing to compare a silhouette of 0.46 against.
    discoveries: List[Discovery] = []
    scores: List[DiscoveryScore] = []
    kinds = {o.series_id: o.state_kind
             for o in MS.as_known_at(observations, as_of)}
    rule_names = _rule_labels(_differences(levels), series_ids, kinds)
    rule_index = {name: i for i, name in enumerate(sorted(set(rule_names)))}
    rule_ints = [rule_index[n] for n in rule_names]
    scores.append(DiscoveryScore(
        method=RULE, groups=len(rule_index), n=len(changes),
        separation=separation(changes, rule_ints),
        coherence=coherence(rule_ints),
        stability=1.0,   # a stated rule cannot be refit, so it cannot move
        utility=utility(rule_ints, target) if target else None,
        note="a stated partition; stability is 1.0 by construction, not by "
             "measurement"))
    for group_name in sorted(set(rule_names)):
        discoveries.append(Discovery(
            kind=REGIME, method=RULE, label=group_name,
            members=tuple(p for p, n in zip(change_periods, rule_names)
                          if n == group_name),
            as_of=as_of,
            research_question=("does any company report different economics "
                               "in these months than in the others?"),
            note="a stated rule over measured directions, not a fitted model"))

    for method in methods:
        labels = _fit_labels(changes, groups=groups, method=method)
        if labels is None:
            scores.append(DiscoveryScore(method=method, groups=groups,
                                         n=len(changes),
                                         note="fit did not converge"))
            continue
        scores.append(DiscoveryScore(
            method=method, groups=groups, n=len(changes),
            separation=separation(changes, labels),
            coherence=coherence(labels),
            stability=stability(changes, groups=groups, method=method),
            utility=utility(labels, target) if target else None,
            note=("utility unmeasured: no target series given"
                  if not target else "")))
        for group in sorted(set(labels)):
            members = tuple(p for p, lab in zip(change_periods, labels)
                            if lab == group)
            discoveries.append(Discovery(
                kind=REGIME, method=method,
                label=f"REGIME_{group + 1}",
                members=members,
                distinguishing=_distinguishing(changes, labels, group,
                                               series_ids),
                as_of=as_of,
                research_question=(
                    "what did the conditions that separate these months have "
                    "in common, and did any company's reported economics "
                    "differ between them?"),
                note=("an ordinal label; naming it after an economic regime "
                      "would import a claim the arithmetic did not make")))

    return {
        "contract": CONTRACT,
        "as_of": as_of,
        "periods": len(change_periods),
        "series": series_ids,
        "groups": groups,
        "baseline": BASELINE_METHOD,
        "discoveries": [d.as_dict() for d in discoveries],
        "scores": [s.as_dict() for s in scores],
        "any_economically_useful": any(s.economically_useful for s in scores),
        "note": ("a discovery is a hypothesis with a research question; "
                 "nothing here is evidence that any regime exists"),
    }


def _distinguishing(features: Sequence[Sequence[float]],
                    labels: Sequence[int], group: int,
                    names: Sequence[str], top: int = 3
                    ) -> Tuple[Tuple[str, float], ...]:
    """Which columns pull this group away from the rest, largest gap first."""
    inside = [f for f, lab in zip(features, labels) if lab == group]
    outside = [f for f, lab in zip(features, labels) if lab != group]
    if not inside or not outside:
        return ()
    gaps = []
    for idx, name in enumerate(names[:len(features[0])]):
        mi = sum(r[idx] for r in inside) / len(inside)
        mo = sum(r[idx] for r in outside) / len(outside)
        gaps.append((name, round(mi - mo, 4)))
    gaps.sort(key=lambda x: -abs(x[1]))
    return tuple(gaps[:top])


# --- companies that look alike -------------------------------------------------

def discover_exposure_clusters(profiles: Dict[str, Dict[str, object]], *,
                               as_of: str, groups: int = 3,
                               method: str = KMEANS) -> dict:
    """Group companies by the shape of their exposure profile.

    THE TRAP THIS AVOIDS. The obvious use of this — "these four look alike, so
    the unrated one probably shares the rated one's exposure" — is exactly the
    inference `Discovery.as_fact` refuses. Clustering on exposure ratings and
    then attesting an exposure from cluster membership is circular: the
    similarity was computed FROM the ratings. What a cluster earns is a place
    in the research queue, and the question is stated on every one.
    """
    from . import company_exposure as CX

    companies = sorted(profiles)
    dimensions = sorted(CX.DIMENSIONS) if hasattr(CX, "DIMENSIONS") else []
    if not dimensions:
        dimensions = sorted({d for p in profiles.values() for d in p})
    rows = []
    for company in companies:
        profile = profiles[company]
        rows.append([_exposure_number(profile.get(dim)) for dim in dimensions])

    rated = [i for i, r in enumerate(rows) if any(v != 0.0 for v in r)]
    if len(rated) < groups or len(companies) < groups + 1:
        return {"contract": CONTRACT, "as_of": as_of,
                "companies": len(companies), "rated": len(rated),
                "discoveries": [], "scores": [],
                "note": (f"{len(rated)} companies carry any exposure rating; "
                         "clustering mostly-empty profiles would group them "
                         "by their emptiness")}

    features = _standardise(rows)
    labels = _fit_labels(features, groups=groups, method=method)
    if labels is None:
        return {"contract": CONTRACT, "as_of": as_of, "discoveries": [],
                "scores": [], "note": "fit did not converge"}

    discoveries = [Discovery(
        kind=EXPOSURE_CLUSTER, method=method, label=f"CLUSTER_{g + 1}",
        members=tuple(c for c, lab in zip(companies, labels) if lab == g),
        distinguishing=_distinguishing(features, labels, g, dimensions),
        as_of=as_of,
        research_question=(
            "do the companies in this group make the same claim about this "
            "exposure in their own filings, or only resemble each other in "
            "what the engine has already rated?"),
        note="similarity computed from the ratings themselves; it cannot "
             "attest a rating") for g in sorted(set(labels))]

    score = DiscoveryScore(
        method=method, groups=groups, n=len(companies),
        separation=separation(features, labels),
        note="coherence and utility are undefined for a non-temporal grouping")
    return {"contract": CONTRACT, "as_of": as_of,
            "companies": len(companies), "rated": len(rated),
            "dimensions": dimensions,
            "discoveries": [d.as_dict() for d in discoveries],
            "scores": [score.as_dict()],
            "note": "cluster membership is a research priority, not a rating"}


#: An exposure's standing as a number. There is no intensity in the exposure
#: model — a company either established a sensitivity or it did not — so what
#: is encoded is HOW WELL IT IS KNOWN, and the ordering says a filing outranks
#: a news report. Reading these as magnitudes would turn "we have a document"
#: into "they are highly exposed".
_STANDING_WEIGHT = {"OBSERVED": 2.0, "INFERRED": 1.0, "UNKNOWN": 0.0}


def _exposure_number(rating) -> float:
    """An exposure as a number, with UNKNOWN a true zero of signal."""
    standing = getattr(rating, "standing", None)
    if standing is None and isinstance(rating, dict):
        standing = rating.get("standing")
    return _STANDING_WEIGHT.get(str(standing), 0.0)


# --- what fits nothing --------------------------------------------------------

def find_anomalies(observations: Sequence[MS.MacroObservation], *, as_of: str,
                   sigma: float = 2.5) -> dict:
    """Months where a series moved unlike itself.

    Deliberately univariate and deliberately crude. A sophisticated detector
    on twenty-four monthly points would be fitting the detector to the sample;
    what is wanted is the short list of months worth asking a question about,
    and a robust z-score on the changes produces it without pretending to more.
    """
    known = MS.as_known_at(observations, as_of)
    by_series: Dict[str, List[MS.MacroObservation]] = {}
    for obs in known:
        by_series.setdefault(obs.series_id, []).append(obs)

    discoveries: List[Discovery] = []
    examined = 0
    for series_id, rows in sorted(by_series.items()):
        rows.sort(key=lambda o: o.reference_period)
        if len(rows) < 8:
            continue
        examined += 1
        changes = [(b.reference_period, b.value - a.value)
                   for a, b in zip(rows, rows[1:])]
        values = [c for _, c in changes]
        median = sorted(values)[len(values) // 2]
        deviations = [abs(v - median) for v in values]
        mad = sorted(deviations)[len(deviations) // 2]
        # 1.4826 scales the median absolute deviation to a standard deviation
        # for normal data; used as a robust yardstick, not a distributional
        # claim.
        scale = 1.4826 * mad
        if scale <= 0:
            # A SERIES THAT SITS STILL AND THEN JUMPS HAS A MAD OF ZERO, and
            # dividing by it skipped the series entirely — so the single most
            # obvious anomaly a series can contain was the one shape this
            # detector could not see. Fall back to the mean deviation, which
            # is only zero when the series genuinely never moves.
            mean_dev = sum(deviations) / len(deviations)
            if mean_dev <= 0:
                continue
            scale = mean_dev
        for period, change in changes:
            z = (change - median) / scale
            if abs(z) < sigma:
                continue
            discoveries.append(Discovery(
                kind=ANOMALY, method=ISOLATION,
                label=f"{series_id}@{period}",
                members=(period,),
                distinguishing=((series_id, round(z, 3)),),
                as_of=as_of,
                research_question=(
                    f"what happened to {series_id} in {period}, and was it a "
                    "revision, a definitional change or an economic event?"),
                note=("a robust z-score on month-over-month change; large is "
                      "unusual for this series, not necessarily important")))
    return {"contract": CONTRACT, "as_of": as_of,
            "series_examined": examined,
            "discoveries": [d.as_dict() for d in discoveries],
            "note": ("an anomaly is a question, and the most common answer is "
                     "a data revision rather than an economic event")}


def summarise(*payloads: dict) -> dict:
    """One view over every discovery this cycle made."""
    found: List[dict] = []
    scores: List[dict] = []
    for payload in payloads:
        found.extend(payload.get("discoveries") or [])
        scores.extend(payload.get("scores") or [])
    by_kind: Dict[str, int] = {}
    for d in found:
        by_kind[d["kind"]] = by_kind.get(d["kind"], 0) + 1
    useful = [s for s in scores if s.get("economically_useful")]
    return {
        "contract": CONTRACT,
        "discoveries": len(found),
        "by_kind": by_kind,
        "methods_scored": len(scores),
        "methods_economically_useful": len(useful),
        "all_have_a_research_question": all(d.get("research_question")
                                            for d in found),
        "note": ("count of hypotheses generated, not of things learned; the "
                 "next number that matters is how many survived evidence"),
    }
