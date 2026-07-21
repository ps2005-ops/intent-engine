"""The Problem Index and the Opportunity Index — product memory (T020).

This is the product substrate, and it mirrors `research/index.py`
deliberately so that T021 can read both with one mental model.

    Customer signals (T014)   Research conclusions (T019 + Evidence Index)
    Growth learnings (T018)   Knowledge items (T016)   Metrics (T015)
                                  |
                            PROBLEM INDEX
                                  |
                          OPPORTUNITY INDEX
                                  |
              Proposals  ->  Spec drafts  ->  Founder review

Two properties make these memory rather than cache:

  * they are built ONLY from append-only rows, so they are reproducible;
  * they are NEVER written by a model. A model may draft prose; only
    deterministic code writes an index entry.

Where this differs from the Evidence Index, and why:

  1. It is TWO indexes. Research needed one substrate; product needs the
     Problem separated from the Opportunity, because one problem carries
     several competing opportunities and collapsing them destroys the
     fan-out a founder chooses between.
  2. The Evidence Index is scoped to one research request. There is no
     product equivalent of a request, so these indexes are company-wide
     and use freshness and supersession where research used scoping.
  3. The Evidence Index owns its leaves (evidence items). These indexes
     own NO primary facts: every leaf is a reference into the subsystem
     that owns it. So the orphan check here is cross-subsystem
     resolvability, not internal consistency — and resolution is
     delegated to that subsystem rather than reimplemented.
  4. Problems EVOLVE (split / merge / retire / supersede). Evidence only
     retires.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from intent_engine.product.graph import (
    assert_graph_invariants, build_graph,
)
from intent_engine.product.records import (
    OPPORTUNITY_REJECTED, OPPORTUNITY_SUPERSEDED, PROBLEM_ACTIVE,
    REFERENCE_KINDS, ProductError,
)
from intent_engine.product.state import fold_product

PROBLEM_INDEX_VERSION = "problem_index.v1"
OPPORTUNITY_INDEX_VERSION = "opportunity_index.v1"


@dataclass(frozen=True)
class ProblemIndex:
    """Normalized problem statements and their dedup keys."""
    index_version: str = PROBLEM_INDEX_VERSION
    problems: dict = field(default_factory=dict)     # problem_id -> record
    by_dedup_key: dict = field(default_factory=dict)  # dedup_key -> problem_id

    def active(self) -> list:
        return sorted((p for p in self.problems.values()
                       if p["state"] == PROBLEM_ACTIVE),
                      key=lambda p: p["problem_id"])

    def find_by_dedup_key(self, key: str):
        return self.by_dedup_key.get(key)

    def lineage_of(self, problem_id: str) -> dict:
        """Where this problem came from and where it went — split, merge,
        supersession, and retirement all preserved."""
        problem = self.problems.get(problem_id)
        if problem is None:
            raise KeyError(f"no such problem: {problem_id}")
        ancestors = [pid for pid, other in sorted(self.problems.items())
                     if problem_id in (other.get("children") or [])
                     or other.get("successor") == problem_id]
        return {"problem_id": problem_id, "state": problem["state"],
                "dedup_key": problem.get("dedup_key"),
                "children": list(problem.get("children") or []),
                "successor": problem.get("successor"),
                "ancestors": sorted(ancestors),
                "evidence_references": list(problem["evidence_references"]),
                "affected_customers": list(problem["affected_customers"])}


@dataclass(frozen=True)
class OpportunityIndex:
    """A reproducible read model. Construct with `build_index(rows)`."""
    index_version: str = OPPORTUNITY_INDEX_VERSION
    problem_index: ProblemIndex = field(default_factory=ProblemIndex)
    opportunities: dict = field(default_factory=dict)
    proposals: dict = field(default_factory=dict)
    edges: tuple = ()
    graph: object = None
    superseded: frozenset = frozenset()
    rejected: frozenset = frozenset()
    row_count: int = 0

    # --- reads ---------------------------------------------------------------
    def usable_opportunities(self) -> list:
        return sorted((o for o in self.opportunities.values()
                       if o["opportunity_id"] not in self.superseded
                       and o["opportunity_id"] not in self.rejected),
                      key=lambda o: o["opportunity_id"])

    def opportunities_for_problem(self, problem_id: str) -> list:
        return sorted((o for o in self.opportunities.values()
                       if o["problem_id"] == problem_id),
                      key=lambda o: o["opportunity_id"])

    def proposals_for_problem(self, problem_id: str) -> list:
        return sorted((p for p in self.proposals.values()
                       if p["problem_id"] == problem_id),
                      key=lambda p: p["proposal_id"])

    def evidence_references(self, opportunity_id: str) -> list:
        opportunity = self.opportunities.get(opportunity_id)
        if opportunity is None:
            raise KeyError(f"no such opportunity: {opportunity_id}")
        return list(opportunity["evidence_references"])

    # --- lineage -------------------------------------------------------------
    def lineage(self, proposal_id: str, *, evidence_resolver=None) -> dict:
        """proposal -> opportunity -> problem -> evidence -> source -> request.

        The last two hops belong to the Evidence Index, so they are
        delegated to `evidence_resolver` rather than reconstructed here.
        Passing no resolver returns the chain up to the reference, with
        the hop explicitly marked unresolved rather than silently absent.
        """
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            raise KeyError(f"no such proposal: {proposal_id}")
        opportunity = self.opportunities.get(proposal["opportunity_id"])
        if opportunity is None:
            raise ProductError(
                f"proposal {proposal_id} references unregistered opportunity "
                f"{proposal['opportunity_id']} — the index rejects orphans")
        problem = self.problem_index.problems.get(proposal["problem_id"])
        if problem is None:
            raise ProductError(
                f"proposal {proposal_id} references unrecorded problem "
                f"{proposal['problem_id']} — the index rejects orphans")

        resolved = []
        for ref in opportunity["evidence_references"]:
            entry = {"reference": dict(ref)}
            if evidence_resolver is None:
                entry["resolution"] = "unresolved: no resolver supplied"
            else:
                try:
                    entry["resolution"] = evidence_resolver(ref)
                except Exception as exc:            # noqa: BLE001
                    entry["resolution"] = {
                        "error_type": type(exc).__name__,
                        "note": "the owning subsystem could not resolve this "
                                "reference"}
            resolved.append(entry)

        return {
            "proposal_id": proposal_id,
            "proposal_version": proposal["version"],
            "proposal_status": proposal["status"],
            "opportunity_id": opportunity["opportunity_id"],
            "opportunity_state": opportunity["state"],
            "opportunity_origin": dict(opportunity.get("origin") or {}),
            "problem_id": problem["problem_id"],
            "problem_state": problem["state"],
            "problem_dedup_key": problem.get("dedup_key"),
            "affected_customers": list(problem["affected_customers"]),
            "evidence": resolved,
            "index_version": self.index_version,
            "problem_index_version": self.problem_index.index_version,
        }

    # --- invariants ----------------------------------------------------------
    def assert_invariants(self, *, resolver=None) -> dict:
        """The index enforces its own guarantees rather than assuming them."""
        problems = []

        for problem_id, problem in sorted(self.problem_index.problems.items()):
            if not problem["evidence_references"]:
                problems.append(
                    f"problem {problem_id} has no evidence reference "
                    "(orphan node)")
            for ref in problem["evidence_references"]:
                if ref.get("kind") not in REFERENCE_KINDS:
                    problems.append(f"problem {problem_id} carries an "
                                    f"unknown reference kind {ref.get('kind')!r}")

        for opportunity_id, opportunity in sorted(self.opportunities.items()):
            if not opportunity["evidence_references"]:
                problems.append(
                    f"opportunity {opportunity_id} has no evidence reference "
                    "— an opportunity with no evidence is invalid")
            if opportunity["problem_id"] not in self.problem_index.problems:
                problems.append(
                    f"opportunity {opportunity_id} references unrecorded "
                    f"problem {opportunity['problem_id']}")
            if resolver is not None:
                for ref in opportunity["evidence_references"]:
                    if not resolver(ref):
                        problems.append(
                            f"opportunity {opportunity_id} references "
                            f"{ref.get('kind')}:{ref.get('ref_id')}, which "
                            "the owning subsystem does not hold")

        for proposal_id, proposal in sorted(self.proposals.items()):
            if proposal["opportunity_id"] not in self.opportunities:
                problems.append(
                    f"proposal {proposal_id} references unregistered "
                    f"opportunity {proposal['opportunity_id']}")
            if proposal["problem_id"] not in self.problem_index.problems:
                problems.append(
                    f"proposal {proposal_id} references unrecorded problem "
                    f"{proposal['problem_id']}")

        if problems:
            raise ProductError(f"opportunity index invariants violated: "
                               f"{problems}")

        graph_report = assert_graph_invariants(self.graph)
        return {"index_version": self.index_version,
                "problem_index_version": self.problem_index.index_version,
                "problems": len(self.problem_index.problems),
                "opportunities": len(self.opportunities),
                "proposals": len(self.proposals),
                "superseded": len(self.superseded),
                "rejected": len(self.rejected),
                "graph": graph_report,
                "invariants": "ok"}


def build_problem_index(state) -> ProblemIndex:
    problems, by_key = {}, {}
    for problem_id, problem in sorted(state.problems.items()):
        problems[problem_id] = dict(problem)
        if problem.get("dedup_key"):
            by_key.setdefault(problem["dedup_key"], problem_id)
    return ProblemIndex(problems=problems, by_dedup_key=by_key)


def build_index(rows) -> OpportunityIndex:
    """Deterministically rebuild both indexes from append-only rows.

    Calling this twice on the same rows yields identical output — that is
    what makes every downstream artifact reproducible, and it is why no
    model may ever write here.
    """
    rows = list(rows)
    state = fold_product(rows)
    problem_index = build_problem_index(state)

    opportunities = {oid: dict(o) for oid, o in sorted(
        state.opportunities.items())}
    proposals = {pid: dict(p) for pid, p in sorted(state.proposals.items())}
    superseded = {oid for oid, o in opportunities.items()
                  if o["state"] == OPPORTUNITY_SUPERSEDED}
    rejected = {oid for oid, o in opportunities.items()
                if o["state"] == OPPORTUNITY_REJECTED}

    recorded_edges = []
    for row in rows:
        if row.event_type == "product.proposal_edge_recorded":
            payload = row.payload or {}
            recorded_edges.append({"edge": payload["edge"],
                                   "from": payload["from"],
                                   "to": payload["to"]})

    graph = build_graph(state, opportunities, problem_index.problems,
                        recorded_edges)

    return OpportunityIndex(
        problem_index=problem_index, opportunities=opportunities,
        proposals=proposals, edges=tuple(recorded_edges), graph=graph,
        superseded=frozenset(superseded), rejected=frozenset(rejected),
        row_count=len(rows))
