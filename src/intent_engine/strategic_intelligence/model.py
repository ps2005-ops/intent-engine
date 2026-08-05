"""V1.3 CompanyMentalModel — a typed, persistent outside-in model of a company.

Built from the SAME evidence graph the report renders (never a parallel path).
Each component carries its current and prior state, the observations that
support and contradict it, confidence, freshness, and provenance, so the model
can be versioned, diffed, and replayed. The report is a view over this model.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from intent_engine.strategic_intelligence.evidence_classes import (
    INDEPENDENT_CLASSES as _INDEPENDENT,
)

# component -> (signals that inform it, contradicting signals, plain-language stem)
_COMPONENTS = {
    "value_proposition": (("merchant_outcome_positioning", "smb_simplicity",
                           "storefront_creation"), ("enterprise_expansion",),
                          "The core promise customers buy"),
    "growth_engine": (("enterprise_expansion", "product_breadth"),
                      ("smb_simplicity",), "Where new growth is coming from"),
    "distribution_model": (("distribution_shift", "agentic_commerce",
                            "data_network"), (),
                           "How demand is captured and reaches the company"),
    "strategic_assets": (("checkout_identity_rails", "platform_control",
                          "data_network"), (),
                         "Durable, hard-to-copy assets"),
    "core_products": (("product_breadth", "storefront_creation"), (),
                      "The established product surface"),
    "emerging_products": (("agentic_commerce",), (),
                          "New bets that could reshape the model"),
    "platform_ecosystem": (("partner_ecosystem_enablement", "platform_control"),
                           (), "Partner/app ecosystem and who controls it"),
    "competitive_position": (("infrastructure_positioning",),
                             ("smb_simplicity",),
                             "How the company is positioned in its market"),
}


@dataclass
class ModelComponent:
    name: str
    current_state: str
    prior_state: str = ""
    supporting_observation_ids: list = field(default_factory=list)
    contradicting_observation_ids: list = field(default_factory=list)
    confidence: str = "low"
    freshness: str = ""              # latest supporting evidence date
    first_seen_at: str = ""
    last_changed_at: str = ""
    change_reason: str = ""
    provenance: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class CompanyMentalModel:
    company: str
    version: int = 1
    created_at: str = ""
    components: dict = field(default_factory=dict)   # name -> ModelComponent
    priorities: list = field(default_factory=list)   # from top hypotheses
    tensions: list = field(default_factory=list)     # from blind spots

    def component(self, name):
        return self.components.get(name)

    def as_dict(self) -> dict:
        return {"company": self.company, "version": self.version,
                "created_at": self.created_at,
                "components": {k: v.as_dict() for k, v in self.components.items()},
                "priorities": list(self.priorities),
                "tensions": list(self.tensions)}


def _conf(n_support, classes):
    diversity = len(classes)
    indep = bool(set(classes) & set(_INDEPENDENT))
    if n_support >= 3 and diversity >= 2 and indep:
        return "high"
    if n_support >= 2 and diversity >= 2:
        return "moderate"
    if n_support >= 1:
        return "low"
    return "speculative"


def build_mental_model(company, observations, hypotheses, *, now,
                       previous=None, blind_spots=()) -> CompanyMentalModel:
    """Construct the current model from evidence. If ``previous`` is given,
    prior_state / change_reason / first_seen_at are carried and updated so the
    model versions rather than rebuilding from zero."""
    by_signal = {}
    for o in observations:
        for s in o.signals:
            by_signal.setdefault(s, []).append(o)

    prev_components = (previous.components if previous else {})
    components = {}
    for name, (sigs, anti, stem) in _COMPONENTS.items():
        support = []
        seen = set()
        for s in sigs:
            for o in by_signal.get(s, []):
                if o.observation_id not in seen and not o.weak:
                    seen.add(o.observation_id)
                    support.append(o)
        if not support:
            continue
        contra = []
        cseen = set()
        for s in anti:
            for o in by_signal.get(s, []):
                if o.observation_id not in cseen:
                    cseen.add(o.observation_id)
                    contra.append(o)
        classes = {o.source_class for o in support}
        dates = sorted((o.date for o in support if o.date), reverse=True)
        # a plain-language current state from the strongest observations
        detail = "; ".join(dict.fromkeys(
            o.strategic_signal or o.text for o in support[:3]))
        current = f"{stem}: {detail}."
        prev = prev_components.get(name)
        prior_state = prev.current_state if prev else ""
        changed = bool(prev) and prev.current_state != current
        components[name] = ModelComponent(
            name=name, current_state=current,
            prior_state=prior_state,
            supporting_observation_ids=[o.observation_id for o in support],
            contradicting_observation_ids=[o.observation_id for o in contra],
            confidence=_conf(len(support), classes),
            freshness=dates[0] if dates else "",
            first_seen_at=(prev.first_seen_at if prev else now),
            last_changed_at=(now if changed or not prev
                             else prev.last_changed_at),
            change_reason=("evidence updated the interpretation" if changed
                           else ("new component from latest evidence"
                                 if not prev else "unchanged")),
            provenance=[{"observation_id": o.observation_id,
                         "source_class": o.source_class} for o in support[:5]])

    version = (previous.version + 1) if previous else 1
    return CompanyMentalModel(
        company=company, version=version, created_at=now, components=components,
        priorities=[h.title for h in hypotheses[:3]],
        tensions=[b.observed_tension for b in blind_spots])


def diff_models(old: CompanyMentalModel, new: CompanyMentalModel) -> list:
    """What changed between two model versions — drives 'What changed our
    view?' and the intelligence feed."""
    changes = []
    old_c = old.components if old else {}
    for name, comp in new.components.items():
        prev = old_c.get(name)
        if prev is None:
            changes.append({"component": name, "kind": "added",
                            "previous_view": "", "new_view": comp.current_state,
                            "old_confidence": "", "new_confidence": comp.confidence,
                            "reason": "first observed from public evidence"})
        elif prev.current_state != comp.current_state or \
                prev.confidence != comp.confidence:
            changes.append({"component": name, "kind": "updated",
                            "previous_view": prev.current_state,
                            "new_view": comp.current_state,
                            "old_confidence": prev.confidence,
                            "new_confidence": comp.confidence,
                            "reason": comp.change_reason})
    for name, prev in old_c.items():
        if name not in new.components:
            changes.append({"component": name, "kind": "removed",
                            "previous_view": prev.current_state, "new_view": "",
                            "old_confidence": prev.confidence, "new_confidence": "",
                            "reason": "no longer supported by current evidence"})
    return changes
