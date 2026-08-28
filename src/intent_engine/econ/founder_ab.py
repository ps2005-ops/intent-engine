"""§2-§8: does the world model change a DECISION, or only the prose?

THE MEASUREMENT THAT WAS INVALID
--------------------------------
`DecisionDelta = 10/10` was scored against a constant placeholder. Every
field differed by construction, so the number measured the placeholder. It is
kept in the record marked INVALID_COMPARATOR_FOR_PRODUCT_VALUE and is not
reported as product evidence again.

WHY THE DECISION FIELDS ARE STRUCTURED
--------------------------------------
The obvious way to compare two analyses is to diff their text, and it is
useless: a synonym, a reordering, an extra macro paragraph all register as
change. So the fields a founder acts on are ENUMS AND IDENTIFIERS, not
sentences —

    action           one of a fixed vocabulary
    top_priority     a channel id
    risk severity    an ordinal
    scenario band    an ordinal
    confidence       an ordinal

A wording change literally cannot move any of them. `materiality` therefore
does not have to detect prose changes and refuse them; it cannot see prose at
all.

BASELINE A IS A REAL ANALYSIS
-----------------------------
§3 is explicit and it is the load-bearing requirement. A is not a stub, not
an empty analysis, not a crippled model. It reads the company's own
structural economics — sector, business model, financing posture, the
exposures established from company evidence — and produces a genuine
recommendation. The treatment is WORLD-MODEL INFORMATION, and if A is weak the
comparison measures the crippling instead.

`assert_baseline_is_real` refuses an A that produced no priority, no risk and
no information request, because that is the shape a crippled baseline has.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_founder_ab.v1"

A, B = "A", "B"

# --- structured decision vocabulary -----------------------------------------
#: The action a founder can take. Fixed, ordinal where it matters.
HOLD = "HOLD"
MONITOR = "MONITOR"
INVESTIGATE = "INVESTIGATE"
PREPARE = "PREPARE"
ACT = "ACT"
ACTIONS = (HOLD, MONITOR, INVESTIGATE, PREPARE, ACT)
ACTION_RANK = {a: i for i, a in enumerate(ACTIONS)}

SEVERITY = ("NONE", "LOW", "MEDIUM", "HIGH", "SEVERE")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITY)}
CONFIDENCE = ("UNKNOWN", "LOW", "MEDIUM", "HIGH")
CONFIDENCE_RANK = {c: i for i, c in enumerate(CONFIDENCE)}
BANDS = ("UNLIKELY", "POSSIBLE", "LIKELY", "EXPECTED")
BAND_RANK = {b: i for i, b in enumerate(BANDS)}

OBSERVED, INFERRED, UNKNOWN = "OBSERVED", "INFERRED", "UNKNOWN"


class AnalysisDefect(EconError):
    """An analysis is not in a state that can be compared."""


@dataclass(frozen=True)
class Risk:
    """One risk, with the standing of the claim behind it."""

    risk_id: str
    severity: str
    channel: str
    mechanism: str
    standing: str
    evidence: Tuple[str, ...] = ()
    #: The economic condition this risk comes THROUGH, when it is an economic
    #: risk at all. Empty for a risk that rests on the company's own evidence.
    #:
    #: DECLARED, NOT PARSED OUT OF THE ID. The first version of the damage
    #: detector decided "is this an economic risk" from an id prefix
    #: (`econ:`), which only the product arm uses -- so the research arm's
    #: risks all read as non-economic and UNNECESSARY_CHANGE and
    #: MISSED_MATERIAL_RISK fired on 25 of 25 material cases. A uniform count
    #: is what a broken instrument looks like, not a finding.
    quantity: str = ""

    def __post_init__(self) -> None:
        require(self.severity in SEVERITY, f"unknown severity "
                                           f"{self.severity!r}")
        require(self.standing in (OBSERVED, INFERRED, UNKNOWN),
                f"unknown standing {self.standing!r}")

    def as_dict(self) -> dict:
        return {"risk_id": self.risk_id, "severity": self.severity,
                "channel": self.channel, "mechanism": self.mechanism,
                "standing": self.standing, "evidence": list(self.evidence),
                "quantity": self.quantity}


@dataclass(frozen=True)
class Analysis:
    """One founder analysis. The decision fields are structured, not prose."""

    company_id: str
    as_of: str
    variant: str
    top_priority: str
    action: str
    risks: Tuple[Risk, ...] = ()
    opportunities: Tuple[str, ...] = ()
    scenario: str = "POSSIBLE"
    confidence: str = "LOW"
    information_requests: Tuple[str, ...] = ()
    falsifiers: Tuple[str, ...] = ()
    evidence: Tuple[str, ...] = ()
    unknowns: Tuple[str, ...] = ()
    #: Only B carries these. Every one must trace to a world-model fact.
    economic_inputs: Tuple[str, ...] = ()
    prose: str = ""

    def __post_init__(self) -> None:
        require(self.variant in (A, B), f"unknown variant {self.variant!r}")
        require(self.action in ACTIONS, f"unknown action {self.action!r}")
        require(self.scenario in BANDS, f"unknown band {self.scenario!r}")
        require(self.confidence in CONFIDENCE,
                f"unknown confidence {self.confidence!r}")

    # --- §6 structural metrics, no judge involved -----------------------
    @property
    def top_risks(self) -> Tuple[str, ...]:
        return tuple(r.risk_id for r in sorted(
            self.risks, key=lambda x: -SEVERITY_RANK[x.severity])[:3])

    @property
    def unsupported_claims(self) -> int:
        """Risks asserted with neither evidence nor an INFERRED standing."""
        return sum(1 for r in self.risks
                   if r.standing == OBSERVED and not r.evidence)

    @property
    def provenance_coverage(self) -> float:
        if not self.risks:
            return 0.0
        return round(sum(1 for r in self.risks if r.evidence)
                     / len(self.risks), 3)

    @property
    def mechanism_completeness(self) -> float:
        if not self.risks:
            return 0.0
        return round(sum(1 for r in self.risks if r.mechanism.strip())
                     / len(self.risks), 3)

    @property
    def distinct_channels(self) -> int:
        return len({r.channel for r in self.risks})

    def metrics(self) -> dict:
        return {"risks": len(self.risks),
                "distinct_channels": self.distinct_channels,
                "unsupported_claims": self.unsupported_claims,
                "provenance_coverage": self.provenance_coverage,
                "mechanism_completeness": self.mechanism_completeness,
                "falsifiers": len(self.falsifiers),
                "information_requests": len(self.information_requests),
                "unknowns_surfaced": len(self.unknowns),
                "evidence_citations": len(self.evidence),
                "economic_inputs": len(self.economic_inputs)}

    def as_dict(self) -> dict:
        return {"company_id": self.company_id, "as_of": self.as_of,
                "variant": self.variant, "top_priority": self.top_priority,
                "action": self.action,
                "risks": [r.as_dict() for r in self.risks],
                "opportunities": list(self.opportunities),
                "scenario": self.scenario, "confidence": self.confidence,
                "information_requests": list(self.information_requests),
                "falsifiers": list(self.falsifiers),
                "evidence": list(self.evidence),
                "unknowns": list(self.unknowns),
                "economic_inputs": list(self.economic_inputs),
                "top_risks": list(self.top_risks),
                "metrics": self.metrics(), "prose": self.prose}


def assert_baseline_is_real(a: Analysis) -> None:
    """§3: Baseline A must be a legitimate analysis, not a stub.

    A crippled A makes every comparison flattering, and it is the easiest
    possible way to manufacture product value. The shape of a crippled
    baseline is: no priority, no risk, no information request. All three
    absent is refused.
    """
    require(a.variant == A, "this checks Baseline A")
    # A BASELINE WITH NO RISK IS CRIPPLED, ON ITS OWN.
    #
    # The first version refused only when TWO of the three were missing, so an
    # A with a priority and an information request but zero risks passed --
    # and break proof 14 emptied exactly that field and was not caught. Two of
    # the seven material fields (`top_risks`, `risk_severity`) are computed
    # FROM the risks, so an A with none of them hands B two automatic wins.
    if not a.risks:
        raise AnalysisDefect(
            f"Baseline A for {a.company_id} carries no risks. `top_risks` "
            "and `risk_severity` are two of the seven material fields and "
            "both are computed from them, so an A with none concedes them "
            "before the comparison starts.")
    empty = [n for n, v in (("top_priority", a.top_priority),
                            ("risks", a.risks),
                            ("information_requests", a.information_requests))
             if not v]
    if len(empty) >= 2:
        raise AnalysisDefect(
            f"Baseline A for {a.company_id} is missing {empty}. A baseline "
            "with no priority, no risk and no information request is a stub, "
            "and every delta measured against it measures the stub. §3 "
            "requires a legitimate analysis without the economic state, not "
            "an absent one.")
    if a.economic_inputs:
        raise AnalysisDefect(
            f"Baseline A for {a.company_id} carries economic inputs "
            f"{list(a.economic_inputs)}. A is defined by their ABSENCE; an A "
            "that has seen the state is not a control.")


# =============================================================================
# §7/§8 THE TYPED DECISION DELTA AND THE MATERIALITY GATE
# =============================================================================

#: What counts as material. Declared before any A/B pair was scored.
MATERIAL_FIELDS = ("top_priority", "action", "top_risks", "scenario",
                   "confidence", "information_priority", "risk_severity")


@dataclass(frozen=True)
class FieldDelta:
    """One decision field that moved, and what moved it."""

    field: str
    before: Any
    after: Any
    material: bool
    trigger: str
    mechanism: str
    provenance: Tuple[str, ...]
    why_material: str = ""

    def as_dict(self) -> dict:
        return {"field": self.field, "before": self.before,
                "after": self.after, "material": self.material,
                "trigger": self.trigger, "mechanism": self.mechanism,
                "provenance": list(self.provenance),
                "why_material": self.why_material}


@dataclass(frozen=True)
class DecisionDelta:
    """A against B, on structured fields only."""

    company_id: str
    regime: str
    fields: Tuple[FieldDelta, ...]
    a_metrics: Dict[str, Any] = field(default_factory=dict)
    b_metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def material_fields(self) -> Tuple[str, ...]:
        return tuple(f.field for f in self.fields if f.material)

    @property
    def is_material(self) -> bool:
        return bool(self.material_fields)

    @property
    def attributable(self) -> bool:
        """§13: no attribution, no credited improvement."""
        mats = [f for f in self.fields if f.material]
        return bool(mats) and all(f.provenance and f.mechanism.strip()
                                  for f in mats)

    @property
    def verdict(self) -> str:
        if not self.is_material:
            return "NO_MATERIAL_ECONOMIC_DELTA"
        if not self.attributable:
            return "MATERIAL_BUT_UNATTRIBUTED"
        return "MATERIAL_AND_ATTRIBUTED"

    def as_dict(self) -> dict:
        return {"company_id": self.company_id, "regime": self.regime,
                "fields": [f.as_dict() for f in self.fields],
                "material_fields": list(self.material_fields),
                "is_material": self.is_material,
                "attributable": self.attributable,
                "verdict": self.verdict,
                "a_metrics": dict(self.a_metrics),
                "b_metrics": dict(self.b_metrics)}


def compare(a: Analysis, b: Analysis, *, regime: str,
            triggers: Dict[str, Tuple[str, str, Tuple[str, ...]]] = None
            ) -> DecisionDelta:
    """A against B. Only structured fields are inspected.

    `triggers` maps a field name to (trigger, mechanism, provenance) — the
    world-model fact that moved it. A field that moved with no trigger is
    recorded MATERIAL and UNATTRIBUTED, which §13 refuses to credit.
    """
    require(a.company_id == b.company_id,
            "A and B must be the same company")
    require(a.as_of == b.as_of,
            f"{a.company_id}: A is dated {a.as_of} and B {b.as_of}. §4 "
            "requires an identical evidence cutoff; different cutoffs make "
            "the treatment 'more recent data' rather than 'the world model'.")
    triggers = triggers or {}
    out: List[FieldDelta] = []

    def add(name, before, after, material, why):
        t, m, p = triggers.get(name, ("", "", ()))
        out.append(FieldDelta(field=name, before=before, after=after,
                              material=material, trigger=t, mechanism=m,
                              provenance=tuple(p), why_material=why))

    if a.top_priority != b.top_priority:
        add("top_priority", a.top_priority, b.top_priority, True,
            "the channel a founder would look at first changed")
    if a.action != b.action:
        add("action", a.action, b.action, True,
            f"the action moved from {a.action} to {b.action}")
    if a.top_risks != b.top_risks:
        add("top_risks", list(a.top_risks), list(b.top_risks), True,
            "the top-three risks were reordered or replaced")
    if a.scenario != b.scenario:
        add("scenario", a.scenario, b.scenario, True,
            "the scenario band moved")
    if a.confidence != b.confidence:
        add("confidence", a.confidence, b.confidence, True,
            "stated confidence moved")
    if a.information_requests[:1] != b.information_requests[:1]:
        add("information_priority", list(a.information_requests[:1]),
            list(b.information_requests[:1]), True,
            "the most valuable missing information changed")
    sev_a = {r.risk_id: r.severity for r in a.risks}
    sev_b = {r.risk_id: r.severity for r in b.risks}
    moved = sorted(k for k in set(sev_a) & set(sev_b)
                   if sev_a[k] != sev_b[k])
    if moved:
        add("risk_severity", {k: sev_a[k] for k in moved},
            {k: sev_b[k] for k in moved}, True,
            f"{len(moved)} existing risk(s) changed severity")
    # NON-MATERIAL by construction: prose is recorded and never counted.
    if a.prose != b.prose:
        add("prose", "<A>", "<B>", False,
            "wording differs; §8 does not count it")
    return DecisionDelta(company_id=a.company_id, regime=regime,
                         fields=tuple(out), a_metrics=a.metrics(),
                         b_metrics=b.metrics())


# =============================================================================
# §14 DECISION DAMAGE
# =============================================================================

#: THREE OF THESE COULD NEVER FIRE.
#:
#: `FALSE_SPECIFICITY`, `WRONG_EXPOSURE` and `GENERIC_RECOMMENDATION` were
#: declared and no detector referenced them, so "DecisionDamage = 0" was in
#: part a statement about a vocabulary rather than about the analyses. A
#: declared kind with no detector is the same defect as a test that cannot
#: fail: it reports the absence of something nothing was looking for.
#:
#: Each now has a detector, and two more kinds are added for the two damages
#: §9 names that the pairwise detector could see and did not:
#: `UNNECESSARY_CHANGE` (the recommendation moved with nothing driving it) and
#: `MISSED_MATERIAL_RISK` (an adverse condition moved and B stayed silent).
DAMAGE_KINDS = ("IRRELEVANT_MACRO", "FALSE_SPECIFICITY",
                "UNSUPPORTED_MECHANISM", "EXCESSIVE_CONFIDENCE",
                "WRONG_EXPOSURE", "STALE_STATE", "DUPLICATED_EVIDENCE",
                "GENERIC_RECOMMENDATION", "UNNECESSARY_CHANGE",
                "MISSED_MATERIAL_RISK", "WRONG_SIGN")


@dataclass(frozen=True)
class DecisionDamage:
    """Where B made the analysis worse. Measured, never hidden."""

    company_id: str
    regime: str
    kind: str
    detail: str
    evidence: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require(self.kind in DAMAGE_KINDS, f"unknown damage {self.kind!r}")

    def as_dict(self) -> dict:
        return {"company_id": self.company_id, "regime": self.regime,
                "kind": self.kind, "detail": self.detail,
                "evidence": list(self.evidence)}


def detect_damage(a: Analysis, b: Analysis, *, regime: str,
                  stale_days: Optional[int] = None,
                  evidenced_exposures: Sequence[str] = (),
                  adverse_conditions: Sequence[str] = (),
                  ) -> List[DecisionDamage]:
    """Structural damage checks. No judge, no opinion.

    `evidenced_exposures` are the quantities this company's OWN evidence
    establishes it is exposed to, and `adverse_conditions` are the ones the
    state says are moving against it. Both are optional: a caller that cannot
    supply them gets the checks that do not need them, and the checks that do
    stay silent rather than guessing. Silence here is not a pass — see
    `damage_coverage`.
    """
    out = []
    # --- WRONG_EXPOSURE: a risk on a channel this company is not exposed to.
    #
    # The whole product rests on "no evidenced exposure, no reading", and
    # nothing was checking the OUTPUT against that rule. A B that raised a
    # commodity risk for a company whose evidence names only rates would have
    # passed every other check here.
    if evidenced_exposures:
        allowed = {str(x) for x in evidenced_exposures}
        for r in b.risks:
            quantity = r.quantity
            if not quantity:
                continue
            if quantity not in allowed:
                out.append(DecisionDamage(
                    company_id=b.company_id, regime=regime,
                    kind="WRONG_EXPOSURE",
                    detail=(f"B raises a risk through {quantity!r}, which is "
                            f"not among this company's evidenced exposures "
                            f"{sorted(allowed)[:4]}"),
                    evidence=r.evidence))
    # --- FALSE_SPECIFICITY: a figure in the prose that no evidence carries.
    #
    # A mechanism that names a number the analysis cannot source is the
    # false-precision failure in miniature: it reads as measurement and is
    # decoration.
    cited = " ".join(list(b.evidence) + list(b.economic_inputs)
                     + [r.trigger_text for r in () ])
    for r in b.risks:
        if r.standing != OBSERVED:
            continue
        figures = _figures(r.mechanism)
        unsourced = [f for f in figures if f not in cited]
        if unsourced:
            out.append(DecisionDamage(
                company_id=b.company_id, regime=regime,
                kind="FALSE_SPECIFICITY",
                detail=(f"risk {r.risk_id} states {unsourced[:2]} as observed "
                        "and no cited evidence carries the figure"),
                evidence=r.evidence))
    # --- UNNECESSARY_CHANGE: the action moved with nothing driving it.
    econ_risks = [r for r in b.risks if r.quantity]
    if (ACTION_RANK[b.action] != ACTION_RANK[a.action] and not econ_risks):
        out.append(DecisionDamage(
            company_id=b.company_id, regime=regime,
            kind="UNNECESSARY_CHANGE",
            detail=(f"the action moved {a.action} -> {b.action} and B carries "
                    "no economic risk; a recommendation that changes with "
                    "nothing behind it is worse than one that does not move")))
    # --- WRONG_SIGN: a risk raised on a condition moving the FAVOURABLE way.
    #
    # The sign lives on the company profile and the product reads it there,
    # so this is the output check for the same rule: a risk whose own trigger
    # says the condition moved the way that HELPS this business is the
    # generic-macro failure with a mechanism attached.
    for r in b.risks:
        if not r.quantity or r.standing != OBSERVED:
            continue
        quantity = r.quantity
        if adverse_conditions and quantity not in set(adverse_conditions):
            out.append(DecisionDamage(
                company_id=b.company_id, regime=regime, kind="WRONG_SIGN",
                detail=(f"B raises {quantity!r} as a risk while the state has "
                        "it moving the way that helps this business"),
                evidence=r.evidence))
    # --- MISSED_MATERIAL_RISK: an adverse condition moved and B stayed quiet.
    if adverse_conditions and not econ_risks:
        out.append(DecisionDamage(
            company_id=b.company_id, regime=regime,
            kind="MISSED_MATERIAL_RISK",
            detail=(f"{sorted(adverse_conditions)[:3]} moved adversely through "
                    "an established channel and B raised no risk; abstention "
                    "is a result only when the state does not bear on the "
                    "decision")))
    if b.unsupported_claims > a.unsupported_claims:
        out.append(DecisionDamage(
            company_id=b.company_id, regime=regime,
            kind="UNSUPPORTED_MECHANISM",
            detail=(f"B asserts {b.unsupported_claims} risk(s) as OBSERVED "
                    f"with no evidence against A's {a.unsupported_claims}")))
    # EXCESSIVE CONFIDENCE, MEASURED CORRECTLY.
    #
    # The first version compared `provenance_coverage`, a RATIO. Baseline A
    # carries one risk with one citation, so its coverage is 1.0 and can
    # never improve -- the check fired on every single material comparison,
    # 24 of 24, which is what a broken instrument looks like rather than a
    # finding.
    #
    # Rising confidence is justified when B is standing on MORE grounded
    # observations than A, so the comparison is the COUNT of risks whose
    # standing is OBSERVED and which carry evidence.
    grounded_a = sum(1 for r in a.risks if r.standing == OBSERVED and r.evidence)
    grounded_b = sum(1 for r in b.risks if r.standing == OBSERVED and r.evidence)
    if (CONFIDENCE_RANK[b.confidence] > CONFIDENCE_RANK[a.confidence]
            and grounded_b <= grounded_a):
        out.append(DecisionDamage(
            company_id=b.company_id, regime=regime,
            kind="EXCESSIVE_CONFIDENCE",
            detail=(f"confidence rose {a.confidence} -> {b.confidence} on "
                    f"{grounded_b} grounded observation(s) against A's "
                    f"{grounded_a}; the extra confidence rests on nothing "
                    "new")))
    if b.economic_inputs and b.top_priority == a.top_priority \
            and b.action == a.action and len(b.risks) > len(a.risks):
        out.append(DecisionDamage(
            company_id=b.company_id, regime=regime,
            kind="IRRELEVANT_MACRO",
            detail=(f"B added {len(b.risks) - len(a.risks)} risk(s) and "
                    "changed neither the priority nor the action; the macro "
                    "content is commentary rather than decision input")))
    if stale_days is not None and stale_days > 120 and b.economic_inputs:
        out.append(DecisionDamage(
            company_id=b.company_id, regime=regime, kind="STALE_STATE",
            detail=f"the economic state is {stale_days} days old"))
    if len(set(b.evidence)) < len(b.evidence):
        out.append(DecisionDamage(
            company_id=b.company_id, regime=regime,
            kind="DUPLICATED_EVIDENCE",
            detail=f"{len(b.evidence) - len(set(b.evidence))} repeated "
                   "citation(s)"))
    return out


def _figures(text: str) -> List[str]:
    """Numeric claims in a sentence, as they are written."""
    import re
    return [m.group(0) for m in re.finditer(r"\d+(?:[.,]\d+)?%?", str(text))]


def detect_generic(analyses: Sequence[Analysis], *,
                   regime: str = "corpus") -> List[DecisionDamage]:
    """GENERIC_RECOMMENDATION, which no pairwise check can see.

    "The same recommendation for every company" is a property of a CORPUS,
    and the pairwise detector had no way to look at one — which is why the
    kind was declared and dead. A mechanism or a priority shared by most of a
    set of different businesses is the template collapse this product keeps
    rediscovering, and it is now measured rather than assumed absent.
    """
    if len(analyses) < 3:
        return []
    out: List[DecisionDamage] = []
    threshold = max(3, (len(analyses) * 2) // 3)
    for label, values in (
            ("top_priority", [x.top_priority for x in analyses]),
            ("mechanism", [r.mechanism for x in analyses for r in x.risks
                           if r.quantity])):
        counts: Dict[str, int] = {}
        for v in values:
            key = " ".join(str(v).lower().split())
            if key:
                counts[key] = counts.get(key, 0) + 1
        for key, n in counts.items():
            if n >= threshold:
                out.append(DecisionDamage(
                    company_id="*", regime=regime,
                    kind="GENERIC_RECOMMENDATION",
                    detail=(f"{n} of {len(analyses)} companies share one "
                            f"{label}: {key[:90]!r}")))
    return out


def damage_coverage() -> dict:
    """Which declared kinds a detector can actually produce.

    Reported so "DecisionDamage = 0" can be read against the number of things
    that were being looked for. A kind with no detector makes the zero mean
    less than it appears to.
    """
    import inspect
    src = (inspect.getsource(detect_damage)
           + inspect.getsource(detect_generic))
    live = tuple(k for k in DAMAGE_KINDS if f'"{k}"' in src)
    return {"declared": list(DAMAGE_KINDS), "with_detector": list(live),
            "without_detector": [k for k in DAMAGE_KINDS if k not in live]}


# =============================================================================
# §5 THE PREREGISTERED RUBRIC
# =============================================================================

RUBRIC = {
    "rubric_id": "DECISION_VALUE_V1",
    "frozen_before": "any A/B pair was scored",
    "judge": ("STRUCTURAL ONLY. No LLM judge is used as a scorer anywhere in "
              "this rubric; every criterion below is computed from the "
              "structured analysis object, so the score cannot flatter the "
              "system that produced it."),
    "criteria": {
        "decision_relevance": "did a decision field move at all",
        "priority_quality": "did top_priority name a channel with an "
                            "adverse reading",
        "company_specificity": "distinct channels across companies",
        "mechanism_quality": "share of risks carrying a mechanism",
        "evidence_quality": "share of risks carrying provenance",
        "uncertainty_honesty": "each risk carries a standing of "
                               "OBSERVED, INFERRED or UNKNOWN, and unknowns "
                               "are listed explicitly",
        "actionability": "action is not HOLD when an adverse channel exists",
        "falsifiability": "count of falsifiers",
        "information_value": "count and movement of information requests",
        "non_redundancy": "B's material fields must carry economic_inputs "
                          "A did not have",
    },
    "materiality": {
        "counts": list(MATERIAL_FIELDS),
        "never_counts": ["prose", "wording", "ordering of sentences",
                         "an extra macro paragraph", "formatting"],
    },
    "attribution_rule": ("a material field with no trigger, mechanism and "
                         "provenance is MATERIAL_BUT_UNATTRIBUTED and is not "
                         "credited"),
    "abstention_rule": ("NO_MATERIAL_ECONOMIC_DELTA is a SUCCESSFUL result "
                        "when the state genuinely does not bear on the "
                        "decision; the world model is not required to speak"),
}


def rubric_hash() -> str:
    return hashlib.sha256(
        json.dumps(RUBRIC, sort_keys=True).encode()).hexdigest()[:16]


def assert_rubric_unchanged(expected: str) -> None:
    actual = rubric_hash()
    if actual != expected:
        raise AnalysisDefect(
            f"the decision-value rubric changed: expected {expected}, now "
            f"{actual}. It was frozen before any A/B pair was scored, and "
            "editing it afterwards is choosing the measure with the answer "
            "in view.")
