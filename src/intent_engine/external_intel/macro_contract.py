"""`macro_intel.v1` — a macro factor may not appear without a mechanism.

THE FAILURE THIS PREVENTS
-------------------------
"Interest rates affect technology companies." True of every technology company
ever, therefore worth nothing to any of them. A founder reading it learns
nothing they did not know, cannot check it, and cannot act on it -- and its
presence makes the rest of the page look like the same kind of filler.

So a factor is admissible only when all four hold:

  1. this COMPANY has a supported exposure mechanism -- supported by retrieved
     evidence, never inferred from its sector;
  2. the observation is current enough for its release frequency;
  3. the connection reaches a decision, KPI or scenario;
  4. the explanation states what it does not establish.

`validate_factor` refuses anything missing one of them. There is no path that
renders a macro section from a series alone, which is what made the old macro
work "render only when retrieved evidence happens to name a factor" -- present
by luck rather than by relevance.

WHY EXPOSURE IS EVIDENCE-BOUND RATHER THAN SECTOR-BOUND
--------------------------------------------------------
Sector classification says a defence contractor is exposed to defence
spending. It also says a payroll company and a chip designer are both
"technology", with opposite exposures to unemployment. Mapping sector to
exposure produces a sentence that is right often enough to feel reliable and
wrong exactly where it matters. So an exposure must name the retrieved
observation that establishes it, and that observation id travels onto the page.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple

SCHEMA_VERSION = "macro_intel.v1"

RISING, FALLING, FLAT = "rising", "falling", "broadly flat"

#: How current an observation must be to be worth putting in front of a
#: founder, by release frequency. A monthly series two quarters old is not
#: describing today's conditions, and presenting it as if it were is the
#: staleness failure in a different costume.
MAX_AGE_DAYS = {"monthly": 92, "quarterly": 190, "daily": 10, "weekly": 21}


class MacroRejected(ValueError):
    """A macro factor tried to appear without earning its place."""


@dataclass(frozen=True)
class MacroObservation:
    """One reading of one public series. Facts only, no interpretation."""
    factor_key: str
    label: str
    series_id: str
    current_value: Optional[float]
    prior_value: Optional[float]
    unit: str
    observation_date: str
    frequency: str
    source: str
    source_url: str = ""
    comparison_note: str = ""

    @property
    def direction(self) -> str:
        if self.current_value is None or self.prior_value is None:
            return ""
        # A band, not a sign test: a 0.1% wobble in a monthly series is noise,
        # and calling it "rising" invites a decision the data cannot carry.
        if not self.prior_value:
            return ""
        change = (self.current_value - self.prior_value) / abs(self.prior_value)
        if change > 0.005:
            return RISING
        if change < -0.005:
            return FALLING
        return FLAT

    @property
    def change_text(self) -> str:
        if self.current_value is None or self.prior_value is None:
            return ""
        delta = self.current_value - self.prior_value
        return f"{self.current_value:,.1f} {self.unit} (from {self.prior_value:,.1f}, {delta:+,.1f})"

    def age_days(self, today: str) -> Optional[int]:
        try:
            return (date.fromisoformat(today[:10])
                    - date.fromisoformat(self.observation_date[:10])).days
        except (ValueError, TypeError):  # pragma: no cover
            return None

    def is_current_enough(self, today: str) -> bool:
        age = self.age_days(today)
        if age is None:
            return False
        return age <= MAX_AGE_DAYS.get(self.frequency, 92)


@dataclass(frozen=True)
class Exposure:
    """Why THIS company is connected to a factor, and what says so."""
    factor_key: str
    mechanism: str
    business_consequence: str
    decision_implication: str
    evidence_ids: Tuple[str, ...] = ()
    matched_on: str = ""

    def __post_init__(self):
        if not self.mechanism:
            raise MacroRejected(
                f"{self.factor_key}: an exposure without a mechanism is the "
                f"generic macro sentence this contract exists to refuse")
        if not self.evidence_ids:
            raise MacroRejected(
                f"{self.factor_key}: an exposure must name the retrieved "
                f"observation that establishes it — sector is not evidence")


@dataclass(frozen=True)
class MacroFactor:
    """An observation joined to a company-specific exposure. The renderable
    unit: nothing reaches a founder that is not one of these."""
    observation: MacroObservation
    exposure: Exposure
    limitation: str
    confidence_basis: str

    @property
    def factor_key(self) -> str:
        return self.observation.factor_key

    def as_dict(self) -> dict:
        o, e = self.observation, self.exposure
        return {
            "schema_version": SCHEMA_VERSION,
            "factor": o.label,
            "factor_key": o.factor_key,
            "series_id": o.series_id,
            "current_value": o.current_value,
            "prior_value": o.prior_value,
            "unit": o.unit,
            "direction": o.direction,
            "change_text": o.change_text,
            "observation_date": o.observation_date,
            "frequency": o.frequency,
            "source": o.source,
            "source_url": o.source_url,
            "comparison_note": o.comparison_note,
            "company_exposure_mechanism": e.mechanism,
            "business_consequence": e.business_consequence,
            "affected_kpi_or_decision": e.decision_implication,
            "evidence_ids": list(e.evidence_ids),
            "matched_on": e.matched_on,
            "confidence_basis": self.confidence_basis,
            "limitation": self.limitation,
        }


def validate_factor(factor: MacroFactor, *, today: str) -> None:
    """The four conditions, checked rather than assumed."""
    o, e = factor.observation, factor.exposure
    if o.current_value is None:
        raise MacroRejected(
            f"{o.factor_key}: no current observation — an absent series is "
            f"reported as absent, never as unchanged")
    if not e.mechanism:  # pragma: no cover - Exposure refuses this first
        raise MacroRejected(f"{o.factor_key}: no exposure mechanism")
    if not e.evidence_ids:  # pragma: no cover - as above
        raise MacroRejected(f"{o.factor_key}: no supporting evidence")
    if not e.decision_implication:
        raise MacroRejected(
            f"{o.factor_key}: the connection reaches no decision, KPI or "
            f"scenario, so it is context a founder cannot use")
    if not factor.limitation:
        raise MacroRejected(
            f"{o.factor_key}: a macro factor must state what it does NOT "
            f"establish")
    if not o.is_current_enough(today):
        raise MacroRejected(
            f"{o.factor_key}: the reading is {o.age_days(today)} days old, "
            f"beyond what a {o.frequency} series may claim about today")


def admissible(factors, *, today: str) -> List[MacroFactor]:
    """Keep only the factors that pass. A rejection is a silence, not an error.

    Deliberately quiet: a factor that cannot establish its exposure is dropped
    rather than rendered with a caveat. A caveated generic macro sentence is
    still a generic macro sentence.
    """
    kept = []
    for factor in factors:
        try:
            validate_factor(factor, today=today)
        except MacroRejected:
            continue
        kept.append(factor)
    return kept
