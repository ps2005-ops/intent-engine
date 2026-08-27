"""§4: one canonical row per construct, saying how it could be measured.

WHY A MAP RATHER THAN A COVERAGE NUMBER
---------------------------------------
"1 of 16 measurable" was the previous run's headline, and it was wrong -- not
because the arithmetic was wrong but because the input was. A single probe
with a 12-second deadline had classified a keyless endpoint as needing a key,
and a coverage number computed from that read as a fact about the world.

A number cannot be audited. A row can. Every construct below states its
candidate proxies, the series behind them, where the history starts, whether
vintages exist, the expected direction, the known confounders, and the
measurement risk -- so the next person to disagree with the classification
has something specific to disagree with.

THE FOUR CLASSIFICATIONS
    MEASURABLE_LIVE          a live series exists and this engine calls it
    MEASURABLE_HISTORICAL    history exists; the current print does not
    PROXY_ONLY               measurable only through a contested instrument
    KEY_REQUIRED             a real series behind a credential we lack
    NO_DEFENSIBLE_INSTRUMENT nothing public measures this without inventing it

THE LAST ONE IS A RESULT, NOT A GAP
-----------------------------------
Section 34: "Only 5 of 16 constructs are measurable" is a better outcome than
fabricating proxies. A construct with no defensible instrument should be
retired, and this module is what makes that a recorded decision with a reason
rather than a silence.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import proxies as PX
from . import series as SER
from .vocabulary import COLLECTIVE_DIMENSIONS, EconError, require

CONTRACT = "econ_instrument_map.v1"

MEASURABLE_LIVE = "MEASURABLE_LIVE"
MEASURABLE_HISTORICAL = "MEASURABLE_HISTORICAL"
PROXY_ONLY = "PROXY_ONLY"
KEY_REQUIRED = "KEY_REQUIRED"
NO_DEFENSIBLE_INSTRUMENT = "NO_DEFENSIBLE_INSTRUMENT"
CLASSIFICATIONS = (MEASURABLE_LIVE, MEASURABLE_HISTORICAL, PROXY_ONLY,
                   KEY_REQUIRED, NO_DEFENSIBLE_INSTRUMENT)


@dataclass(frozen=True)
class ConstructRow:
    """§4's canonical row. Every field is something a reader can check."""

    construct_id: str
    definition: str
    population: str
    expected_direction: str
    confounders: Tuple[str, ...]
    measurement_risk: str
    #: Filled from the proxy and series registries rather than restated here,
    #: so a row cannot drift from the code that does the measuring.
    proxies: Tuple[dict, ...] = ()
    classification: str = NO_DEFENSIBLE_INSTRUMENT
    history_start: str = ""
    frequency: str = ""
    vintage_available: bool = False
    revision_policy: str = ""
    retire_reason: str = ""

    def __post_init__(self) -> None:
        require(self.construct_id in COLLECTIVE_DIMENSIONS,
                f"{self.construct_id!r} is not a declared construct")
        require(self.classification in CLASSIFICATIONS,
                f"unknown classification {self.classification!r}")
        require(bool(self.definition.strip()),
                f"{self.construct_id}: a construct with no definition cannot "
                "be measured, because nobody can say what would count")
        require(bool(self.measurement_risk.strip()),
                f"{self.construct_id}: state what could make this "
                "measurement wrong. A proxy with no stated risk is an "
                "assumption wearing a number")
        if self.classification == NO_DEFENSIBLE_INSTRUMENT:
            require(bool(self.retire_reason.strip()),
                    f"{self.construct_id}: a construct declared unmeasurable "
                    "must say what was looked for and not found")

    @property
    def measurable(self) -> bool:
        return self.classification in (MEASURABLE_LIVE, MEASURABLE_HISTORICAL)

    def as_dict(self) -> dict:
        return {"construct_id": self.construct_id,
                "definition": self.definition,
                "population": self.population,
                "classification": self.classification,
                "measurable": self.measurable,
                "expected_direction": self.expected_direction,
                "confounders": list(self.confounders),
                "measurement_risk": self.measurement_risk,
                "proxies": [dict(p) for p in self.proxies],
                "history_start": self.history_start,
                "frequency": self.frequency,
                "vintage_available": self.vintage_available,
                "revision_policy": self.revision_policy,
                "retire_reason": self.retire_reason}


#: What each construct means, what would confound it, and what could make the
#: measurement wrong. Written per construct because a generic risk sentence
#: ("surveys are noisy") tells a reader nothing they could act on.
_DEFINITIONS: Dict[str, dict] = {
    "financial_anxiety": dict(
        definition="the degree to which households expect their own financial "
                   "position to worsen, and act to protect against it",
        expected_direction="rises with debt service burden and delinquency; "
                           "falls with sentiment",
        confounders=("news cycle drives stated sentiment independently of "
                     "experience",
                     "delinquency is a lagging record of a decision made "
                     "months earlier",
                     "partisan composition shifts survey levels without any "
                     "change in behaviour"),
        risk="the 2022 divergence — sentiment at recessionary levels while "
             "consumption held — is the standing evidence that the stated and "
             "revealed instruments here can disagree for years"),
    "perceived_control": dict(
        definition="the degree to which workers believe they can change their "
                   "own situation through their own action",
        expected_direction="rises with quits and participation; falls with "
                           "involuntary underemployment",
        confounders=("quits rise in a hot labour market regardless of how "
                     "anyone feels",
                     "participation falls for demographic reasons unrelated "
                     "to control"),
        risk="the quits rate is a labour-market statistic first and a "
             "psychological reading second; if it adds value, the value may "
             "belong to the labour market rather than to the construct"),
    "perceived_security": dict(
        definition="a household's sense that its current position is stable, "
                   "distinct from anxiety about the future",
        expected_direction="rises with the employment-population ratio; falls "
                           "with U-6 underemployment",
        confounders=("U-6 conflates 'could not find full-time' with 'chose "
                     "part-time'",
                     "employment ratio moves with retirement demographics"),
        risk="security and control share the labour market as their evidence "
             "base and may not be separable in practice; they are kept apart "
             "because their instruments differ, and the incremental-value "
             "test will say whether that distinction earns anything"),
    "risk_appetite": dict(
        definition="households' willingness to hold volatile assets and take "
                   "on future obligation",
        expected_direction="rises with the household equity share",
        confounders=("the equity share rises mechanically when equities rise, "
                     "with no change in behaviour — a valuation effect, not "
                     "an allocation decision",),
        risk="THE VALUATION CONFOUND IS SEVERE. A share-of-assets measure "
             "moves with prices. Any finding here must be checked against a "
             "flow measure before it means anything"),
    "time_horizon": dict(
        definition="how far ahead households are willing to commit resources",
        expected_direction="rises with durable-goods orders and home sales",
        confounders=("both instruments are rate-sensitive, and rates are in "
                     "the base economic model already",
                     "durable orders include defence and aircraft, which are "
                     "not household decisions at all"),
        risk="the rate sensitivity means this construct may add nothing over "
             "a base model that already holds rates; that is exactly what the "
             "incremental-value test is for"),
    "future_orientation": dict(
        definition="whether households are oriented toward improvement ahead "
                   "or toward protecting what they have",
        expected_direction="rises with the OECD confidence indicator",
        confounders=("the OECD indicator is itself partly built from national "
                     "surveys this engine also reads, which is a lineage "
                     "problem as much as a confounding one",),
        risk="LINEAGE: if the OECD indicator incorporates UMich, then using "
             "both is double counting. Marked and not yet resolved"),
    "stress": dict(
        definition="acute, near-term distress in the population",
        expected_direction="n/a",
        confounders=(),
        risk="no instrument"),
    "institutional_trust": dict(
        definition="confidence that institutions will behave predictably and "
                   "in good faith",
        expected_direction="n/a",
        confounders=(),
        risk="no instrument"),
    "anger": dict(
        definition="expressed collective anger",
        expected_direction="n/a", confounders=(), risk="no instrument"),
    "agency": dict(
        definition="belief in one's own capacity to act effectively",
        expected_direction="n/a", confounders=(), risk="no instrument"),
    "belonging": dict(
        definition="sense of connection to a community",
        expected_direction="n/a", confounders=(), risk="no instrument"),
    "certainty": dict(
        definition="confidence about the near-term future",
        expected_direction="n/a", confounders=(), risk="no instrument"),
    "hope": dict(
        definition="expectation that things will improve",
        expected_direction="n/a", confounders=(), risk="no instrument"),
    "interpersonal_trust": dict(
        definition="trust in other people rather than institutions",
        expected_direction="n/a", confounders=(), risk="no instrument"),
    "perceived_fairness": dict(
        definition="sense that outcomes are distributed justly",
        expected_direction="n/a", confounders=(), risk="no instrument"),
    "willingness_to_experiment": dict(
        definition="willingness to try unfamiliar options",
        expected_direction="n/a", confounders=(), risk="no instrument"),
}

#: Why each unmeasurable construct is unmeasurable. Specific, so a future run
#: can check whether the reason still holds rather than re-deriving it.
_NO_INSTRUMENT_REASONS = {
    "stress": "search-volume series are the standard proxy and the trends "
              "APIs forbid the redistribution this would require. The "
              "alternative — distress-term frequency in public text — "
              "measures the news cycle, not the population",
    "institutional_trust": "the major trust barometers are proprietary and "
                           "annual. An annual figure cannot support a "
                           "quarterly-horizon forecast comparison, so even "
                           "licensing one would not make this testable at the "
                           "horizons this engine forecasts at",
    "anger": "requires a licensed text corpus. A tone index built from "
             "whatever happens to be scrapeable measures the scrape",
    "agency": "the only candidate instruments (business formation, quits) are "
              "already the instruments for perceived_control. Two constructs "
              "sharing one instrument set are one construct with two names",
    "belonging": "no public series measures it, and no behavioural proxy "
                 "discriminates it from participation measures already used "
                 "elsewhere",
    "certainty": "survey dispersion would be the right instrument and the "
                 "public releases publish central tendencies, not "
                 "distributions",
    "hope": "would share every instrument with future_orientation; kept "
            "distinct in the vocabulary and retired here rather than given a "
            "duplicate loading",
    "interpersonal_trust": "the General Social Survey measures it biennially "
                           "with a multi-year lag. Real, and far too slow for "
                           "any horizon this engine forecasts at",
    "perceived_fairness": "no public series; the survey instruments that "
                          "exist are annual, framing-sensitive and not "
                          "released as time series",
    "willingness_to_experiment": "would share business formation with "
                                 "perceived_control and agency; retired "
                                 "rather than triple-counted",
}


def _classify(construct: str) -> Tuple[str, str]:
    """Classify from the registries, never from a stored opinion."""
    proxies = PX.BY_DIMENSION.get(construct, ())
    if not proxies:
        return NO_DEFENSIBLE_INSTRUMENT, _NO_INSTRUMENT_REASONS.get(
            construct, "no proxy is declared for this construct")
    kinds = {p.kind for p in proxies}
    readable = {s.kind for s in SER.BEHAVIOURAL
                if s.availability in (SER.LIVE, SER.DERIVABLE)}
    keyed = {s.kind for s in SER.BEHAVIOURAL if s.availability == SER.KEYED}
    live = kinds & readable
    if live:
        discriminating = [p for p in proxies
                          if p.kind in live and not p.contested]
        if not discriminating:
            return PROXY_ONLY, ""
        return MEASURABLE_LIVE, ""
    if kinds & keyed:
        return KEY_REQUIRED, ""
    return NO_DEFENSIBLE_INSTRUMENT, _NO_INSTRUMENT_REASONS.get(
        construct, "every declared proxy names a series this engine cannot "
                   "read, and no alternative instrument was found")


def _series_facts(construct: str) -> dict:
    """History start, frequency and vintage availability, from the registry."""
    kinds = {p.kind for p in PX.BY_DIMENSION.get(construct, ())}
    specs = [s for s in SER.BEHAVIOURAL if s.kind in kinds
             and s.availability in (SER.LIVE, SER.DERIVABLE)]
    if not specs:
        return {"frequency": "", "vintage": False}
    freqs = sorted({s.frequency for s in specs})
    # Everything routed through ALFRED has vintages; that is the whole reason
    # for routing through it.
    vintage = any("ALFRED" in (s.publisher or "") for s in specs)
    return {"frequency": "/".join(freqs), "vintage": vintage}


def build() -> List[ConstructRow]:
    rows = []
    for c in sorted(COLLECTIVE_DIMENSIONS):
        d = _DEFINITIONS.get(c, {})
        cls, reason = _classify(c)
        facts = _series_facts(c)
        rows.append(ConstructRow(
            construct_id=c,
            definition=d.get("definition", c.replace("_", " ")),
            population="US_households",
            expected_direction=d.get("expected_direction", "n/a"),
            confounders=tuple(d.get("confounders", ())),
            measurement_risk=d.get("risk", "not assessed"),
            proxies=tuple(p.as_dict()
                          for p in PX.BY_DIMENSION.get(c, ())),
            classification=cls,
            frequency=facts["frequency"],
            vintage_available=facts["vintage"],
            revision_policy=("publisher vintages available through ALFRED"
                             if facts["vintage"] else ""),
            retire_reason=reason))
    return rows


def summarise(rows: Optional[Sequence[ConstructRow]] = None) -> dict:
    rows = list(rows) if rows is not None else build()
    by_class: Dict[str, List[str]] = {}
    for r in rows:
        by_class.setdefault(r.classification, []).append(r.construct_id)
    return {"contract": CONTRACT,
            "constructs_total": len(rows),
            "by_classification": {k: sorted(v)
                                  for k, v in sorted(by_class.items())},
            "measurable": sorted(r.construct_id for r in rows if r.measurable),
            "measurable_count": sum(1 for r in rows if r.measurable),
            "no_instrument": sorted(r.construct_id for r in rows
                                    if r.classification
                                    == NO_DEFENSIBLE_INSTRUMENT),
            "indistinguishable_pairs": PX.indistinguishable_pairs(),
            "rows": [r.as_dict() for r in rows]}


def write(path="reports/construct_coverage.json") -> pathlib.Path:
    dest = pathlib.Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(summarise(), indent=2, sort_keys=True))
    return dest
