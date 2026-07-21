"""Folded product state and the lifecycle rules (T020).

    Portfolio -> Theme -> Initiative -> Opportunity -> Proposal -> Spec Draft
                                                    -> Founder Review
                                                    -> Decision Record
                                                    -> Execution Candidate

Nothing skips a step, and each rule below is individually tested:

    a Proposal requires an indexed Opportunity
    a Spec Draft requires a Proposal and binds to an exact proposal version
    Founder Review is HUMAN-only and binds to an exact spec version
    an Execution Candidate requires a linked Decision Record
    a revised Proposal is a NEW version; prior versions stay retrievable
    a review of version N does not carry to version N+1

Themes and initiatives are declared by humans. Strategy is not something
this subsystem infers.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from intent_engine.product.records import (
    OPPORTUNITY_ATTACHED, OPPORTUNITY_CANDIDATE, OPPORTUNITY_REJECTED,
    OPPORTUNITY_SUPERSEDED, PROBLEM_ACTIVE, PROBLEM_MERGED, PROBLEM_RETIRED,
    PROBLEM_SPLIT, PROBLEM_SUPERSEDED, RETIREMENT_REASONS,
    REVIEW_DISPOSITIONS, STATUS_ACCEPTED, STATUS_DRAFTED,
    STATUS_EXECUTION_CANDIDATE, STATUS_RETIRED, STATUS_REVIEW_REQUESTED,
    STATUS_SCORED, ProductError,
)

# A problem in one of these states no longer accepts new opportunities: it
# has been superseded, retired, or folded into another problem.
_CLOSED_PROBLEM_STATES = {PROBLEM_RETIRED, PROBLEM_SUPERSEDED, PROBLEM_MERGED}


@dataclass(frozen=True)
class ProductState:
    portfolios: frozenset = frozenset()
    themes: dict = field(default_factory=dict)         # theme_id -> record
    initiatives: dict = field(default_factory=dict)    # initiative_id -> rec
    problems: dict = field(default_factory=dict)       # problem_id -> record
    dedup_keys: dict = field(default_factory=dict)     # dedup_key -> problem
    opportunities: dict = field(default_factory=dict)  # opp_id -> record
    proposals: dict = field(default_factory=dict)      # proposal_id -> record
    specs: dict = field(default_factory=dict)          # spec_id -> record
    solution_sets: dict = field(default_factory=dict)  # set_id -> record
    reviews: dict = field(default_factory=dict)        # (pid, ver) -> record
    alignments: dict = field(default_factory=dict)     # subject_id -> record
    balance_targets: dict = field(default_factory=dict)  # portfolio -> bands
    bundles: dict = field(default_factory=dict)        # bundle_id -> record
    roadmap_candidates: dict = field(default_factory=dict)  # pid -> record

    # --- convenience reads ---------------------------------------------------
    def proposal_status(self, proposal_id: str) -> str:
        return self.proposals[proposal_id]["status"]

    def current_proposal_version(self, proposal_id: str) -> int:
        return self.proposals[proposal_id]["version"]

    def spec_for_current_version(self, proposal_id: str):
        version = self.proposals[proposal_id]["version"]
        for spec_id, spec in sorted(self.specs.items()):
            if spec["proposal_id"] == proposal_id \
                    and spec["proposal_version"] == version:
                return spec_id, spec
        return None, None


def _precondition(state: ProductState, row) -> tuple[bool, str]:
    et = row.event_type
    p = row.payload or {}

    # --- portfolio / themes / initiatives ------------------------------------
    if et == "product.portfolio_created":
        return (row.subject_id not in state.portfolios,
                "a portfolio is created once")
    if et == "product.theme_declared":
        return (row.portfolio_id in state.portfolios,
                "a strategic theme belongs to an existing portfolio")
    if et == "product.initiative_created":
        return (row.theme_id in state.themes,
                "an initiative belongs to an existing strategic theme")
    if et == "product.balance_target_declared":
        return (row.portfolio_id in state.portfolios,
                "a balance target belongs to an existing portfolio")
    if et == "product.alignment_declared":
        target = row.subject_id
        return (target in state.opportunities or target in state.initiatives,
                "a strategic-alignment declaration names an existing "
                "opportunity or initiative")

    # --- problems -------------------------------------------------------------
    if et == "product.problem_recorded":
        if row.problem_id in state.problems:
            return (False, "a problem is recorded once")
        if not p.get("evidence_references"):
            return (False, "a problem statement with zero evidence references "
                           "is rejected — evidence comes before problem")
        for part in ("why_now", "what_changes_if_ignored"):
            if not str(p.get(part) or "").strip():
                return (False, f"{part} is a required part of a problem "
                               "statement")
        return (True, "")
    if et in ("product.problem_evidence_linked", "product.problem_split",
              "product.problem_merged", "product.problem_retired",
              "product.problem_superseded"):
        problem = state.problems.get(row.problem_id)
        if problem is None:
            return (False, f"{et} references an unrecorded problem")
        if problem["state"] in _CLOSED_PROBLEM_STATES:
            return (False, f"problem is {problem['state']}; its history is "
                           "retained and its state is not reopened here")
        return (True, "")

    # --- opportunities --------------------------------------------------------
    if et == "product.opportunity_registered":
        if row.opportunity_id in state.opportunities:
            return (False, "an opportunity is registered once")
        problem = state.problems.get(row.problem_id)
        if problem is None:
            return (False, "an opportunity requires a recorded problem — a "
                           "solution recorded before its problem is rejected")
        if problem["state"] in _CLOSED_PROBLEM_STATES:
            return (False, f"the problem is {problem['state']}")
        if not p.get("evidence_references"):
            return (False, "an opportunity with no evidence reference is "
                           "invalid")
        return (True, "")
    if et in ("product.opportunity_evidence_linked",
              "product.opportunity_superseded", "product.opportunity_rejected"):
        return (row.opportunity_id in state.opportunities,
                f"{et} references an unregistered opportunity")
    if et == "product.opportunity_attached":
        if row.opportunity_id not in state.opportunities:
            return (False, "attachment references an unregistered opportunity")
        return (row.initiative_id in state.initiatives,
                "attachment requires an existing initiative")

    # --- solution sets --------------------------------------------------------
    if et == "product.solution_set_opened":
        return (row.problem_id in state.problems,
                "a solution set belongs to a recorded problem")

    # --- proposals ------------------------------------------------------------
    if et == "product.proposal_drafted":
        if row.proposal_id in state.proposals:
            return (False, "a proposal is drafted once; a revision is a new "
                           "version")
        opportunity = state.opportunities.get(row.opportunity_id)
        if opportunity is None:
            return (False, "a proposal requires an indexed opportunity")
        if opportunity["state"] in (OPPORTUNITY_SUPERSEDED,
                                    OPPORTUNITY_REJECTED):
            return (False, f"the opportunity is {opportunity['state']}")
        if row.problem_id not in state.problems:
            return (False, "a proposal referencing a problem that was not "
                           "recorded is rejected")
        if row.problem_id != opportunity["problem_id"]:
            return (False, "a proposal addresses the problem its opportunity "
                           "arose from; a mismatch is rejected")
        if row.proposal_version != 1:
            return (False, "the first version of a proposal is version 1")
        return (True, "")
    if et == "product.proposal_revised":
        proposal = state.proposals.get(row.proposal_id)
        if proposal is None:
            return (False, "a revision requires an existing proposal")
        if proposal["status"] in (STATUS_RETIRED,):
            return (False, "a retired proposal is not revised in place")
        if row.proposal_version != proposal["version"] + 1:
            return (False, f"a revision is version {proposal['version'] + 1}, "
                           f"got {row.proposal_version}")
        return (True, "")
    if et in ("product.proposal_scored", "product.proposal_edge_recorded",
              "product.decision_debt_recorded"):
        return (row.proposal_id in state.proposals,
                f"{et} references an undrafted proposal")
    if et == "product.proposal_retired":
        if row.proposal_id not in state.proposals:
            return (False, "retirement references an undrafted proposal")
        if p.get("reason") not in RETIREMENT_REASONS:
            return (False, f"a retirement reason is one of "
                           f"{sorted(RETIREMENT_REASONS)}")
        return (True, "")

    # --- specs ----------------------------------------------------------------
    if et == "product.spec_drafted":
        proposal = state.proposals.get(row.proposal_id)
        if proposal is None:
            return (False, "a spec draft requires a proposal")
        if row.proposal_version != proposal["version"]:
            return (False, f"a spec draft binds to the exact current proposal "
                           f"version ({proposal['version']}), got "
                           f"{row.proposal_version}")
        if row.spec_id in state.specs:
            return (False, "a spec is drafted once; a change is a revision")
        if row.spec_version != 1:
            return (False, "the first version of a spec is version 1")
        return (True, "")
    if et == "product.spec_revised":
        spec = state.specs.get(row.spec_id)
        if spec is None:
            return (False, "a revision requires an existing spec")
        if row.spec_version != spec["version"] + 1:
            return (False, f"a spec revision is version {spec['version'] + 1}")
        return (True, "")
    if et == "product.spec_debt_recorded":
        return (row.spec_id in state.specs,
                "spec debt references an undrafted spec")

    # --- review, decisions, execution ----------------------------------------
    if et == "product.review_requested":
        proposal = state.proposals.get(row.proposal_id)
        if proposal is None:
            return (False, "a review request requires a proposal")
        spec_id, _ = state.spec_for_current_version(row.proposal_id)
        if spec_id is None:
            return (False, "a review request requires a spec draft bound to "
                           "the proposal's current version")
        return (proposal["status"] in (STATUS_DRAFTED, STATUS_SCORED),
                f"a proposal in status {proposal['status']} is not queued for "
                "a fresh review")
    if et == "product.reviewed":
        proposal = state.proposals.get(row.proposal_id)
        if proposal is None:
            return (False, "a review requires a proposal")
        if proposal["status"] != STATUS_REVIEW_REQUESTED:
            return (False, "a review requires a prior review request")
        if row.proposal_version != proposal["version"]:
            return (False, "a review binds to the proposal version under "
                           "review; a later version requires a fresh review")
        spec_id, spec = state.spec_for_current_version(row.proposal_id)
        if row.spec_id != spec_id:
            return (False, "a review binds to the spec draft of the proposal "
                           "version under review")
        if row.spec_version != spec["version"]:
            return (False, f"a review binds to the exact spec version "
                           f"({spec['version']}), got {row.spec_version}")
        if p.get("disposition") not in REVIEW_DISPOSITIONS:
            return (False, f"a review disposition is one of "
                           f"{sorted(REVIEW_DISPOSITIONS)}")
        return (True, "")
    if et == "product.decision_linked":
        proposal = state.proposals.get(row.proposal_id)
        if proposal is None:
            return (False, "a decision link requires a proposal")
        if proposal["status"] != STATUS_ACCEPTED:
            return (False, "a decision link follows an accepted proposal")
        return (bool(row.decision_id), "a decision link requires a decision id")
    if et == "product.execution_candidate_marked":
        proposal = state.proposals.get(row.proposal_id)
        if proposal is None:
            return (False, "an execution candidate requires a proposal")
        if not proposal.get("decision_id"):
            return (False, "an execution candidate requires a linked Decision "
                           "Record created through DecisionService")
        return (True, "")

    # --- bundles, roadmap candidates -----------------------------------------
    if et == "product.bundle_assembled":
        missing = [pid for pid in p.get("proposal_ids", [])
                   if pid not in state.proposals]
        return (not missing, f"bundle references undrafted proposals: {missing}")
    if et == "product.roadmap_candidate_drafted":
        proposal = state.proposals.get(row.proposal_id)
        if proposal is None:
            return (False, "a roadmap candidate requires a proposal")
        spec_id, _ = state.spec_for_current_version(row.proposal_id)
        return (spec_id is not None,
                "a roadmap candidate requires a spec draft on the current "
                "proposal version")
    if et == "product.roadmap_diff_emitted":
        return (row.proposal_id in state.roadmap_candidates,
                "a diff requires a drafted roadmap candidate")

    return (True, "")


def _apply(state: ProductState, row) -> ProductState:
    et, p = row.event_type, row.payload or {}
    d = dict(
        portfolios=set(state.portfolios), themes=dict(state.themes),
        initiatives=dict(state.initiatives), problems=dict(state.problems),
        dedup_keys=dict(state.dedup_keys),
        opportunities=dict(state.opportunities),
        proposals={k: dict(v) for k, v in state.proposals.items()},
        specs={k: dict(v) for k, v in state.specs.items()},
        solution_sets={k: dict(v) for k, v in state.solution_sets.items()},
        reviews=dict(state.reviews), alignments=dict(state.alignments),
        balance_targets=dict(state.balance_targets),
        bundles=dict(state.bundles),
        roadmap_candidates=dict(state.roadmap_candidates))

    if et == "product.portfolio_created":
        d["portfolios"].add(row.subject_id)
    elif et == "product.theme_declared":
        d["themes"][row.theme_id] = {"theme_id": row.theme_id,
                                     "portfolio_id": row.portfolio_id,
                                     "name": p.get("name", "")}
    elif et == "product.initiative_created":
        d["initiatives"][row.initiative_id] = {
            "initiative_id": row.initiative_id, "theme_id": row.theme_id,
            "portfolio_id": row.portfolio_id, "name": p.get("name", "")}
    elif et == "product.balance_target_declared":
        d["balance_targets"][row.portfolio_id] = dict(p.get("bands", {}))
    elif et == "product.alignment_declared":
        d["alignments"][row.subject_id] = {
            "level": p.get("level"), "declared_by": row.actor_id,
            "rationale": p.get("rationale", ""), "theme_id": row.theme_id}

    elif et == "product.problem_recorded":
        d["problems"][row.problem_id] = {
            "problem_id": row.problem_id, "state": PROBLEM_ACTIVE,
            "dedup_key": p.get("dedup_key"),
            "first_observed_at": p.get("first_observed_at"),
            "evidence_references": list(p.get("evidence_references", [])),
            "affected_customers": list(p.get("affected_customers", [])),
            "successor": None, "children": []}
        if p.get("dedup_key"):
            d["dedup_keys"][p["dedup_key"]] = row.problem_id
    elif et == "product.problem_evidence_linked":
        problem = d["problems"][row.problem_id]
        refs = list(problem["evidence_references"])
        for ref in p.get("evidence_references", []):
            if ref not in refs:
                refs.append(ref)
        problem["evidence_references"] = refs
    elif et == "product.problem_split":
        problem = d["problems"][row.problem_id]
        problem["state"] = PROBLEM_SPLIT
        problem["children"] = list(p.get("children", []))
    elif et == "product.problem_merged":
        problem = d["problems"][row.problem_id]
        problem["state"] = PROBLEM_MERGED
        problem["successor"] = p.get("merged_into")
    elif et == "product.problem_retired":
        d["problems"][row.problem_id]["state"] = PROBLEM_RETIRED
    elif et == "product.problem_superseded":
        problem = d["problems"][row.problem_id]
        problem["state"] = PROBLEM_SUPERSEDED
        problem["successor"] = p.get("successor")

    elif et == "product.opportunity_registered":
        d["opportunities"][row.opportunity_id] = {
            "opportunity_id": row.opportunity_id, "problem_id": row.problem_id,
            "state": OPPORTUNITY_CANDIDATE, "initiative_id": None,
            "origin": p.get("origin", {}),
            "work_category": p.get("work_category", "unknown"),
            "evidence_references": list(p.get("evidence_references", []))}
    elif et == "product.opportunity_evidence_linked":
        opportunity = d["opportunities"][row.opportunity_id]
        refs = list(opportunity["evidence_references"])
        for ref in p.get("evidence_references", []):
            if ref not in refs:
                refs.append(ref)
        opportunity["evidence_references"] = refs
    elif et == "product.opportunity_attached":
        opportunity = dict(d["opportunities"][row.opportunity_id])
        opportunity["initiative_id"] = row.initiative_id
        opportunity["state"] = OPPORTUNITY_ATTACHED
        d["opportunities"][row.opportunity_id] = opportunity
    elif et == "product.opportunity_superseded":
        d["opportunities"][row.opportunity_id] = {
            **d["opportunities"][row.opportunity_id],
            "state": OPPORTUNITY_SUPERSEDED, "successor": p.get("successor")}
    elif et == "product.opportunity_rejected":
        d["opportunities"][row.opportunity_id] = {
            **d["opportunities"][row.opportunity_id],
            "state": OPPORTUNITY_REJECTED, "reason": p.get("reason")}

    elif et == "product.solution_set_opened":
        d["solution_sets"][row.subject_id] = {
            "solution_set_id": row.subject_id, "problem_id": row.problem_id,
            "proposal_ids": []}

    elif et == "product.proposal_drafted":
        d["proposals"][row.proposal_id] = {
            "proposal_id": row.proposal_id, "version": row.proposal_version,
            "status": STATUS_DRAFTED, "opportunity_id": row.opportunity_id,
            "problem_id": row.problem_id,
            "solution_set_id": p.get("solution_set_id"),
            "decision_id": None, "retired_reason": None,
            "work_category": p.get("work_category", "unknown"),
            "decision_debt": []}
        set_id = p.get("solution_set_id")
        if set_id in d["solution_sets"]:
            members = list(d["solution_sets"][set_id]["proposal_ids"])
            members.append(row.proposal_id)
            d["solution_sets"][set_id]["proposal_ids"] = sorted(set(members))
    elif et == "product.proposal_revised":
        proposal = d["proposals"][row.proposal_id]
        proposal["version"] = row.proposal_version
        # A review of version N does not carry to version N+1.
        proposal["status"] = STATUS_DRAFTED
    elif et == "product.proposal_scored":
        proposal = d["proposals"][row.proposal_id]
        if proposal["status"] == STATUS_DRAFTED:
            proposal["status"] = STATUS_SCORED
    elif et == "product.decision_debt_recorded":
        proposal = d["proposals"][row.proposal_id]
        debt = list(proposal["decision_debt"])
        debt.append({"kind": p.get("kind"), "detail": p.get("detail", "")})
        proposal["decision_debt"] = debt
    elif et == "product.proposal_retired":
        proposal = d["proposals"][row.proposal_id]
        proposal["status"] = STATUS_RETIRED
        proposal["retired_reason"] = p.get("reason")

    elif et == "product.spec_drafted":
        d["specs"][row.spec_id] = {
            "spec_id": row.spec_id, "proposal_id": row.proposal_id,
            "proposal_version": row.proposal_version,
            "version": row.spec_version, "debt": []}
    elif et == "product.spec_revised":
        d["specs"][row.spec_id]["version"] = row.spec_version
    elif et == "product.spec_debt_recorded":
        spec = d["specs"][row.spec_id]
        debt = list(spec["debt"])
        debt.append({"kind": p.get("kind"), "detail": p.get("detail", "")})
        spec["debt"] = debt

    elif et == "product.review_requested":
        d["proposals"][row.proposal_id]["status"] = STATUS_REVIEW_REQUESTED
    elif et == "product.reviewed":
        proposal = d["proposals"][row.proposal_id]
        proposal["status"] = p["disposition"]
        d["reviews"][f"{row.proposal_id}:{row.proposal_version}"] = {
            "proposal_id": row.proposal_id,
            "proposal_version": row.proposal_version,
            "spec_id": row.spec_id, "spec_version": row.spec_version,
            "disposition": p["disposition"], "reviewer": row.actor_id,
            "notes": p.get("notes", ""),
            "merged_into": p.get("merged_into"),
            "deferred_until_condition": p.get("deferred_until_condition")}
    elif et == "product.decision_linked":
        d["proposals"][row.proposal_id]["decision_id"] = row.decision_id
    elif et == "product.execution_candidate_marked":
        d["proposals"][row.proposal_id]["status"] = STATUS_EXECUTION_CANDIDATE

    elif et == "product.bundle_assembled":
        d["bundles"][row.bundle_id] = {
            "bundle_id": row.bundle_id,
            "proposal_ids": list(p.get("proposal_ids", [])),
            "name": p.get("name", "")}
    elif et == "product.roadmap_candidate_drafted":
        d["roadmap_candidates"][row.proposal_id] = {
            "proposal_id": row.proposal_id,
            "proposal_version": row.proposal_version,
            "spec_id": row.spec_id, "spec_version": row.spec_version,
            "status": p.get("status")}

    d["portfolios"] = frozenset(d["portfolios"])
    return ProductState(**d)


def validate_product_event(state: ProductState, row) -> tuple[bool, str]:
    return _precondition(state, row)


def fold_product(rows, *, validate: bool = False) -> ProductState:
    state = ProductState()
    for row in rows:
        if validate:
            ok, reason = _precondition(state, row)
            if not ok:
                raise ProductError(
                    f"stored product history is invalid at {row.event_type}: "
                    f"{reason}")
        state = _apply(state, row)
    return state
