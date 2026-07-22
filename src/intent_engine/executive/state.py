"""Folded executive state and the lifecycle rules (T021).

    Candidate -> Context -> Package -> Founder Review -> Decision Record
                                                      -> Outcome
                                                      -> Knowledge

Nothing skips a step, and each rule below is individually tested:

    a Context requires a Candidate, and carries a horizon and a class
    a Package RENDERS a context at an exact version
    a Package heading to review carries at least TWO options, or an
        explicit no-recommendation with its reason and review date
    Founder Review is HUMAN-only and binds to an exact package version
    a revised Package is a NEW version; a review of version N does not
        carry to version N+1
    a Decision Record link requires an ACCEPTED review
    an Outcome requires a linked Decision Record
    a Knowledge candidate requires an observed Outcome
"""
from __future__ import annotations

from dataclasses import dataclass, field

from intent_engine.executive.records import (
    DECISION_CLASSES, DECISION_DEBT_KINDS, DECISION_HORIZONS,
    DISPOSITION_ACCEPTED, OUTCOME_NO_RECOMMENDATION, OUTCOME_RECOMMENDATION,
    RECORDED_EDGES, REQUIRED_OPTION_PARTS, REVERSIBILITY_LEVELS,
    REVIEW_DISPOSITIONS, ExecutiveError,
)


@dataclass(frozen=True)
class ExecutiveState:
    candidates: dict = field(default_factory=dict)
    contexts: dict = field(default_factory=dict)
    packages: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)      # option_id -> record
    conflicts: dict = field(default_factory=dict)
    debt: dict = field(default_factory=dict)         # candidate -> [items]
    reviews: dict = field(default_factory=dict)      # "pkg:ver" -> record
    overrides: dict = field(default_factory=dict)
    outcomes: dict = field(default_factory=dict)
    knowledge_requests: dict = field(default_factory=dict)
    expired: frozenset = frozenset()
    alignments: dict = field(default_factory=dict)
    budgets: dict = field(default_factory=dict)
    edges: tuple = ()

    # --- convenience reads ---------------------------------------------------
    def current_context(self, candidate_id: str):
        for context_id, context in sorted(self.contexts.items()):
            if context["candidate_id"] == candidate_id:
                return context_id, context
        return None, None

    def options_for(self, package_id: str) -> list:
        return sorted((o for o in self.options.values()
                       if o["package_id"] == package_id),
                      key=lambda o: o["option_id"])

    def package_for_candidate(self, candidate_id: str):
        for package_id, package in sorted(self.packages.items()):
            if package["candidate_id"] == candidate_id:
                return package_id, package
        return None, None


def _precondition(state: ExecutiveState, row) -> tuple[bool, str]:
    et = row.event_type
    p = row.payload or {}

    # --- candidates ----------------------------------------------------------
    if et == "executive.candidate_registered":
        if row.candidate_id in state.candidates:
            return (False, "a candidate is registered once")
        if not p.get("references"):
            return (False, "a decision candidate with no reference is "
                           "invalid — it would resolve to nothing")
        return (True, "")
    if et in ("executive.candidate_linked", "executive.candidate_superseded",
              "executive.candidate_dismissed", "executive.decision_expired",
              "executive.decision_debt_recorded",
              "executive.decision_debt_cleared",
              "executive.readiness_computed", "executive.conflict_detected"):
        if row.candidate_id and row.candidate_id not in state.candidates:
            return (False, f"{et} references an unregistered candidate")
        if et == "executive.decision_debt_recorded" \
                and p.get("kind") not in DECISION_DEBT_KINDS:
            return (False, f"a decision-debt kind is one of "
                           f"{sorted(DECISION_DEBT_KINDS)}")
        return (True, "")

    # --- context -------------------------------------------------------------
    if et == "executive.context_built":
        if row.candidate_id not in state.candidates:
            return (False, "a context requires a registered candidate")
        if row.context_id in state.contexts:
            return (False, "a context is built once; a change is a rebuild")
        if row.context_version != 1:
            return (False, "the first version of a context is version 1")
        if p.get("decision_horizon") not in DECISION_HORIZONS:
            return (False, f"a context carries a horizon from "
                           f"{list(DECISION_HORIZONS)}")
        if p.get("decision_class") not in DECISION_CLASSES:
            return (False, f"a context carries a class from "
                           f"{sorted(DECISION_CLASSES)}")
        return (True, "")
    if et == "executive.context_rebuilt":
        context = state.contexts.get(row.context_id)
        if context is None:
            return (False, "a rebuild requires an existing context")
        if row.context_version != context["version"] + 1:
            return (False, f"a rebuild is version {context['version'] + 1}, "
                           f"got {row.context_version}")
        return (True, "")

    # --- packages ------------------------------------------------------------
    if et == "executive.package_drafted":
        if row.package_id in state.packages:
            return (False, "a package is drafted once; a change is a revision")
        context = state.contexts.get(row.context_id)
        if context is None:
            return (False, "a package renders a context; none was built")
        if row.context_version != context["version"]:
            return (False, f"a package renders the context at its exact "
                           f"current version ({context['version']}), got "
                           f"{row.context_version}")
        if row.package_version != 1:
            return (False, "the first version of a package is version 1")
        return (True, "")
    if et == "executive.package_revised":
        package = state.packages.get(row.package_id)
        if package is None:
            return (False, "a revision requires an existing package")
        if row.package_version != package["version"] + 1:
            return (False, f"a revision is version {package['version'] + 1}, "
                           f"got {row.package_version}")
        return (True, "")
    if et == "executive.option_recorded":
        if row.package_id not in state.packages:
            return (False, "an option belongs to a drafted package")
        # benefits / costs / risks / unknowns must be examined, not omitted;
        # `dependencies` may legitimately be empty (an independent option),
        # so its KEY must be present but its list may be empty.
        must_be_nonempty = [part for part in REQUIRED_OPTION_PARTS
                            if part not in ("dependencies", "reversibility")]
        missing = [part for part in must_be_nonempty if not p.get(part)]
        if missing:
            return (False, f"an option states its {must_be_nonempty}; "
                           f"missing {missing}")
        if "dependencies" not in p:
            return (False, "an option states its dependencies (possibly an "
                           "empty list, stated rather than omitted)")
        if p.get("reversibility") not in REVERSIBILITY_LEVELS:
            return (False, f"an option declares reversibility from "
                           f"{list(REVERSIBILITY_LEVELS)} — it is declared, "
                           "not inferred")
        return (True, "")
    if et == "executive.no_recommendation_recorded":
        if row.package_id not in state.packages:
            return (False, "a no-recommendation belongs to a drafted package")
        for part in ("reason", "evidence_gap", "review_date"):
            if not str(p.get(part) or "").strip():
                return (False, f"a no-recommendation states its {part}")
        return (True, "")
    if et == "executive.escalation_assigned":
        return (row.package_id in state.packages,
                "an escalation belongs to a drafted package")

    # --- review --------------------------------------------------------------
    if et == "executive.review_requested":
        package = state.packages.get(row.package_id)
        if package is None:
            return (False, "a review request requires a package")
        if package["outcome"] == OUTCOME_NO_RECOMMENDATION:
            return (True, "")
        options = state.options_for(row.package_id)
        current = [o for o in options
                   if o["package_version"] == package["version"]]
        if len(current) < 2:
            return (False, "a package heading to review carries at least two "
                           "options, or an explicit no-recommendation — "
                           "approve/reject is not a choice between "
                           "alternatives")
        return (True, "")
    if et == "executive.reviewed":
        package = state.packages.get(row.package_id)
        if package is None:
            return (False, "a review requires a package")
        if package["status"] != "review_requested":
            return (False, "a review requires a prior review request")
        if row.package_version != package["version"]:
            return (False, "a review binds to the package version under "
                           "review; a later version requires a fresh review")
        if p.get("disposition") not in REVIEW_DISPOSITIONS:
            return (False, f"a review disposition is one of "
                           f"{sorted(REVIEW_DISPOSITIONS)}")
        return (True, "")
    if et == "executive.override_recorded":
        package = state.packages.get(row.package_id)
        if package is None:
            return (False, "an override requires a package")
        key = f"{row.package_id}:{row.package_version}"
        if key not in state.reviews:
            return (False, "an override records what the founder chose "
                           "against a recorded preference; the review comes "
                           "first")
        for part in ("chosen_option_id", "preferred_option_id", "reason"):
            if not str(p.get(part) or "").strip():
                return (False, f"an override states its {part}")
        return (True, "")
    if et == "executive.decision_linked":
        package = state.packages.get(row.package_id)
        if package is None:
            return (False, "a decision link requires a package")
        if package["status"] != DISPOSITION_ACCEPTED:
            return (False, "a decision link follows an accepted review")
        return (bool(row.decision_id),
                "a decision link requires a decision id")
    if et == "executive.outcome_observed":
        package = state.packages.get(row.package_id)
        if package is None:
            return (False, "an outcome requires a package")
        if not package.get("decision_id"):
            return (False, "an outcome requires a linked Decision Record "
                           "created through DecisionService")
        return (True, "")
    if et == "executive.knowledge_candidate_requested":
        return (row.package_id in state.outcomes,
                "a knowledge candidate requires an observed outcome")

    # --- graph ---------------------------------------------------------------
    if et == "executive.decision_edge_recorded":
        if p.get("edge") not in RECORDED_EDGES:
            return (False, f"{p.get('edge')!r} is a derived edge; it is not "
                           "recorded separately, so it cannot drift from the "
                           "rows that created it")
        return (True, "")

    return (True, "")


def _apply(state: ExecutiveState, row) -> ExecutiveState:
    et, p = row.event_type, row.payload or {}
    d = dict(
        candidates={k: dict(v) for k, v in state.candidates.items()},
        contexts={k: dict(v) for k, v in state.contexts.items()},
        packages={k: dict(v) for k, v in state.packages.items()},
        options=dict(state.options), conflicts=dict(state.conflicts),
        debt={k: list(v) for k, v in state.debt.items()},
        reviews=dict(state.reviews), overrides=dict(state.overrides),
        outcomes=dict(state.outcomes),
        knowledge_requests=dict(state.knowledge_requests),
        expired=set(state.expired), alignments=dict(state.alignments),
        budgets=dict(state.budgets), edges=state.edges)

    if et == "executive.candidate_registered":
        d["candidates"][row.candidate_id] = {
            "candidate_id": row.candidate_id,
            "references": list(p.get("references", [])),
            "origin": dict(p.get("origin") or {}),
            "created_at": row.occurred_at,
            "input_fingerprint": p.get("input_fingerprint"),
            "status": "open", "dismissed_reason": None, "successor": None}
    elif et == "executive.candidate_superseded":
        d["candidates"][row.candidate_id].update(
            status="superseded", successor=p.get("successor"))
    elif et == "executive.candidate_dismissed":
        d["candidates"][row.candidate_id].update(
            status="dismissed", dismissed_reason=p.get("reason"))
    elif et == "executive.decision_expired":
        d["expired"].add(row.candidate_id)
        d["candidates"][row.candidate_id]["status"] = "expired"

    elif et == "executive.context_built":
        d["contexts"][row.context_id] = {
            "context_id": row.context_id, "candidate_id": row.candidate_id,
            "version": row.context_version,
            "decision_horizon": p.get("decision_horizon"),
            "decision_class": p.get("decision_class"),
            "input_fingerprint": p.get("input_fingerprint"),
            "built_at": row.occurred_at}
    elif et == "executive.context_rebuilt":
        d["contexts"][row.context_id].update(
            version=row.context_version,
            decision_horizon=p.get("decision_horizon",
                                   d["contexts"][row.context_id]["decision_horizon"]),
            decision_class=p.get("decision_class",
                                 d["contexts"][row.context_id]["decision_class"]),
            input_fingerprint=p.get("input_fingerprint"),
            built_at=row.occurred_at)

    elif et == "executive.package_drafted":
        d["packages"][row.package_id] = {
            "package_id": row.package_id, "candidate_id": row.candidate_id,
            "context_id": row.context_id,
            "context_version": row.context_version,
            "version": row.package_version, "status": "drafted",
            "outcome": p.get("outcome", OUTCOME_RECOMMENDATION),
            "escalation": None, "decision_id": None}
    elif et == "executive.package_revised":
        package = d["packages"][row.package_id]
        package["version"] = row.package_version
        # A review of version N does not carry to version N+1.
        package["status"] = "drafted"
    elif et == "executive.option_recorded":
        d["options"][row.option_id] = {
            "option_id": row.option_id, "package_id": row.package_id,
            "package_version": row.package_version,
            "label": p.get("label", ""),
            "reversibility": p.get("reversibility")}
    elif et == "executive.no_recommendation_recorded":
        d["packages"][row.package_id]["outcome"] = OUTCOME_NO_RECOMMENDATION
        d["packages"][row.package_id]["no_recommendation"] = {
            "reason": p.get("reason"), "evidence_gap": p.get("evidence_gap"),
            "review_date": p.get("review_date")}
    elif et == "executive.escalation_assigned":
        d["packages"][row.package_id]["escalation"] = p.get("level")

    elif et == "executive.review_requested":
        d["packages"][row.package_id]["status"] = "review_requested"
    elif et == "executive.reviewed":
        d["packages"][row.package_id]["status"] = p["disposition"]
        d["reviews"][f"{row.package_id}:{row.package_version}"] = {
            "package_id": row.package_id,
            "package_version": row.package_version,
            "disposition": p["disposition"], "reviewer": row.actor_id,
            "notes": p.get("notes", ""),
            "chosen_option_id": p.get("chosen_option_id"),
            "merged_into": p.get("merged_into"),
            "deferred_until_condition": p.get("deferred_until_condition")}
    elif et == "executive.override_recorded":
        d["overrides"][f"{row.package_id}:{row.package_version}"] = {
            "package_id": row.package_id,
            "package_version": row.package_version,
            "chosen_option_id": p.get("chosen_option_id"),
            "preferred_option_id": p.get("preferred_option_id"),
            "reason": p.get("reason"), "recorded_by": row.actor_id}
    elif et == "executive.decision_linked":
        d["packages"][row.package_id]["decision_id"] = row.decision_id
    elif et == "executive.outcome_observed":
        d["outcomes"][row.package_id] = {
            "package_id": row.package_id, "decision_id": row.decision_id,
            "observation": p.get("observation"),
            "observed_at": row.occurred_at}
    elif et == "executive.knowledge_candidate_requested":
        d["knowledge_requests"][row.package_id] = {
            "package_id": row.package_id, "knowledge_id": row.knowledge_id,
            "content": p.get("content")}

    elif et == "executive.conflict_detected":
        d["conflicts"][row.conflict_id] = {
            "conflict_id": row.conflict_id, "candidate_id": row.candidate_id,
            "kind": p.get("kind"), "sides": p.get("sides", []),
            "detail": p.get("detail", "")}
    elif et == "executive.decision_debt_recorded":
        items = list(d["debt"].get(row.candidate_id, []))
        items.append({"kind": p.get("kind"), "detail": p.get("detail", ""),
                      "clears_when": p.get("clears_when", ""),
                      "cleared": False})
        d["debt"][row.candidate_id] = items
    elif et == "executive.decision_debt_cleared":
        items = []
        for item in d["debt"].get(row.candidate_id, []):
            if item["kind"] == p.get("kind") and not item["cleared"]:
                item = {**item, "cleared": True,
                        "cleared_reason": p.get("reason", "")}
            items.append(item)
        d["debt"][row.candidate_id] = items

    elif et == "executive.alignment_declared":
        d["alignments"][row.subject_id] = {
            "level": p.get("level"), "declared_by": row.actor_id,
            "rationale": p.get("rationale", "")}
    elif et == "executive.budget_declared":
        d["budgets"][row.subject_id] = {
            "amount_available": p.get("amount_available"),
            "currency": p.get("currency"), "declared_by": row.actor_id}

    elif et == "executive.decision_edge_recorded":
        d["edges"] = state.edges + ({"edge": p["edge"], "from": p["from"],
                                     "to": p["to"]},)

    d["expired"] = frozenset(d["expired"])
    return ExecutiveState(**d)


def validate_executive_event(state: ExecutiveState, row) -> tuple[bool, str]:
    return _precondition(state, row)


def fold_executive(rows, *, validate: bool = False) -> ExecutiveState:
    state = ExecutiveState()
    for row in rows:
        if validate:
            ok, reason = _precondition(state, row)
            if not ok:
                raise ExecutiveError(
                    f"stored executive history is invalid at {row.event_type}:"
                    f" {reason}")
        state = _apply(state, row)
    return state
