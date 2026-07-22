"""The Decision Index — executive memory (T021).

The third canonical index, completing the layering the last three sessions
established:

    Evidence Index      (T019)  what is known
    Problem + Opportunity Index (T020)  what could be built
    DECISION INDEX      (T021)  what deserves a decision next

It holds open decisions, blocked decisions, expired decisions, decision
debt, decision candidates, conflicts, recommendations, and review
packages — and nothing else.

**The asymmetry this index has and the other two do not, and how it is
resolved.** The Evidence Index and the Opportunity Index are reproducible
because they fold only their own subsystem's append-only rows. Decision
state, though, lives in `DecisionService` (SQLite) — a different store
with a different shape. Mirroring it into the executive log would make
querying easier and would materialize a copy that drifts the moment
somebody records a decision event without passing through here.

So this index stores `decision_id` REFERENCES and treats `DecisionService`
as a RESOLVER, exactly as T020 treats evidence references. The index
folds from the executive log alone and stays reproducible; decision status
is resolved at read time by the subsystem that owns it. Mirroring is
rejected, and a source-inspection test asserts that no executive module
writes or materializes decision state.

Like both predecessors: built only from append-only rows, NEVER written by
a model, orphan-rejecting, self-checking, and lineage-answering.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from intent_engine.executive.graph import (
    assert_graph_invariants, build_graph,
)
from intent_engine.executive.records import (
    OUTCOME_NO_RECOMMENDATION, REFERENCE_KINDS, TERMINAL_DISPOSITIONS,
    ExecutiveError,
)
from intent_engine.executive.state import fold_executive

DECISION_INDEX_VERSION = "decision_index.v1"


@dataclass(frozen=True)
class DecisionIndex:
    """A reproducible read model. Construct with `build_index(rows)`."""
    index_version: str = DECISION_INDEX_VERSION
    candidates: dict = field(default_factory=dict)
    contexts: dict = field(default_factory=dict)
    packages: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)
    conflicts: dict = field(default_factory=dict)
    debt: dict = field(default_factory=dict)
    reviews: dict = field(default_factory=dict)
    overrides: dict = field(default_factory=dict)
    outcomes: dict = field(default_factory=dict)
    expired: frozenset = frozenset()
    graph: object = None
    row_count: int = 0

    # --- the reads the queue and the dashboard are built from ----------------
    def open_candidates(self) -> list:
        return sorted((c for c in self.candidates.values()
                       if c["status"] == "open"),
                      key=lambda c: c["candidate_id"])

    def expired_candidates(self) -> list:
        return sorted((self.candidates[cid] for cid in self.expired
                       if cid in self.candidates),
                      key=lambda c: c["candidate_id"])

    def blocked_candidates(self) -> list:
        """Blocked by an unmet dependency in the decision graph, or by
        decision debt that only a person clears."""
        blocked = []
        for candidate in self.open_candidates():
            cid = candidate["candidate_id"]
            unmet = [d for d in self.graph.dependencies_of(cid)
                     if self._unsettled(d)]
            open_debt = [item for item in self.debt.get(cid, [])
                         if not item["cleared"]]
            if unmet or open_debt:
                blocked.append({**candidate, "blocked_by_decisions": unmet,
                                "blocked_by_debt": open_debt})
        return blocked

    def _unsettled(self, candidate_id: str) -> bool:
        candidate = self.candidates.get(candidate_id)
        if candidate is None:
            return True
        package_id, package = self._package_for(candidate_id)
        if package is None:
            return True
        return package["status"] not in TERMINAL_DISPOSITIONS

    def _package_for(self, candidate_id: str):
        for package_id, package in sorted(self.packages.items()):
            if package["candidate_id"] == candidate_id:
                return package_id, package
        return None, None

    def open_decision_debt(self) -> list:
        out = []
        for candidate_id, items in sorted(self.debt.items()):
            for item in items:
                if not item["cleared"]:
                    out.append({"candidate_id": candidate_id, **item})
        return out

    def review_packages(self) -> list:
        return sorted((p for p in self.packages.values()
                       if p["status"] == "review_requested"),
                      key=lambda p: p["package_id"])

    def recommendations(self) -> list:
        return sorted((p for p in self.packages.values()
                       if p["outcome"] != OUTCOME_NO_RECOMMENDATION),
                      key=lambda p: p["package_id"])

    def conflicts_for(self, candidate_id: str) -> list:
        return sorted((c for c in self.conflicts.values()
                       if c["candidate_id"] == candidate_id),
                      key=lambda c: c["conflict_id"])

    # --- lineage -------------------------------------------------------------
    def lineage(self, package_id: str, *, decision_resolver=None,
                prediction_resolver=None, reference_resolver=None) -> dict:
        """package -> context -> candidate -> references, and forward
        through decision -> prediction -> outcome.

        Every hop outside this subsystem is DELEGATED to the subsystem that
        owns it. Passing no resolver marks the hop unresolved rather than
        silently dropping it.
        """
        package = self.packages.get(package_id)
        if package is None:
            raise KeyError(f"no such package: {package_id}")
        context = self.contexts.get(package["context_id"])
        if context is None:
            raise ExecutiveError(
                f"package {package_id} renders unregistered context "
                f"{package['context_id']} — the index rejects orphans")
        candidate = self.candidates.get(context["candidate_id"])
        if candidate is None:
            raise ExecutiveError(
                f"context {context['context_id']} references unregistered "
                f"candidate {context['candidate_id']} — the index rejects "
                "orphans")

        references = []
        for ref in candidate["references"]:
            entry = {"reference": dict(ref)}
            if reference_resolver is None:
                entry["resolution"] = "unresolved: no resolver supplied"
            else:
                try:
                    entry["resolution"] = reference_resolver(ref)
                except Exception as exc:                    # noqa: BLE001
                    entry["resolution"] = {
                        "error_type": type(exc).__name__,
                        "note": "the owning subsystem could not resolve this "
                                "reference"}
            references.append(entry)

        decision_id = package.get("decision_id")
        decision = "unresolved: no decision is linked yet"
        if decision_id and decision_resolver is not None:
            try:
                decision = decision_resolver(decision_id)
            except Exception as exc:                        # noqa: BLE001
                decision = {"error_type": type(exc).__name__,
                            "note": "DecisionService could not resolve this "
                                    "decision id"}
        elif decision_id:
            decision = {"decision_id": decision_id,
                        "resolution": "unresolved: no resolver supplied"}

        predictions = "unresolved: no resolver supplied"
        if decision_id and prediction_resolver is not None:
            predictions = prediction_resolver(decision_id)

        return {
            "package_id": package_id,
            "package_version": package["version"],
            "package_status": package["status"],
            "package_outcome": package["outcome"],
            "context_id": context["context_id"],
            "context_version": context["version"],
            "decision_horizon": context["decision_horizon"],
            "decision_class": context["decision_class"],
            "candidate_id": candidate["candidate_id"],
            "candidate_status": candidate["status"],
            "candidate_origin": dict(candidate.get("origin") or {}),
            "references": references,
            "decision": decision,
            "predictions": predictions,
            "outcome": self.outcomes.get(package_id,
                                         "no outcome observed yet"),
            "index_version": self.index_version,
        }

    # --- invariants ----------------------------------------------------------
    def assert_invariants(self, *, reference_resolver=None) -> dict:
        """The index enforces its own guarantees rather than assuming them.

        Includes the full reasoning chain the executive layer promises:
        package -> candidate -> reference, with the reference resolving
        into the subsystem that owns it (which in turn guarantees
        opportunity -> problem -> evidence -> source through T020 and
        T019, rather than restating those checks here).
        """
        problems = []

        for candidate_id, candidate in sorted(self.candidates.items()):
            if not candidate["references"]:
                problems.append(
                    f"candidate {candidate_id} has no reference — a decision "
                    "candidate that resolves to nothing is invalid")
            for ref in candidate["references"]:
                if ref.get("kind") not in REFERENCE_KINDS:
                    problems.append(
                        f"candidate {candidate_id} carries an unknown "
                        f"reference kind {ref.get('kind')!r}")
                if reference_resolver is not None and not reference_resolver(ref):
                    problems.append(
                        f"candidate {candidate_id} references "
                        f"{ref.get('kind')}:{ref.get('ref_id')}, which the "
                        "owning subsystem does not hold")

        for context_id, context in sorted(self.contexts.items()):
            if context["candidate_id"] not in self.candidates:
                problems.append(
                    f"context {context_id} references unregistered candidate "
                    f"{context['candidate_id']}")

        for package_id, package in sorted(self.packages.items()):
            if package["context_id"] not in self.contexts:
                problems.append(
                    f"package {package_id} renders unregistered context "
                    f"{package['context_id']}")
            if package["candidate_id"] not in self.candidates:
                problems.append(
                    f"package {package_id} references unregistered candidate "
                    f"{package['candidate_id']}")

        for option_id, option in sorted(self.options.items()):
            if option["package_id"] not in self.packages:
                problems.append(
                    f"option {option_id} belongs to unregistered package "
                    f"{option['package_id']}")

        for conflict_id, conflict in sorted(self.conflicts.items()):
            if conflict["candidate_id"] not in self.candidates:
                problems.append(
                    f"conflict {conflict_id} references unregistered "
                    f"candidate {conflict['candidate_id']}")

        if problems:
            raise ExecutiveError(f"decision index invariants violated: "
                                 f"{problems}")

        graph_report = assert_graph_invariants(self.graph)
        return {"index_version": self.index_version,
                "candidates": len(self.candidates),
                "contexts": len(self.contexts),
                "packages": len(self.packages),
                "options": len(self.options),
                "conflicts": len(self.conflicts),
                "open_debt": len(self.open_decision_debt()),
                "expired": len(self.expired),
                "graph": graph_report,
                "invariants": "ok"}


def build_index(rows) -> DecisionIndex:
    """Deterministically rebuild the index from append-only rows.

    Calling this twice on the same rows yields identical output. Nothing
    here reads another store, so the index stays reproducible from the
    executive log alone — decision status is resolved at read time by
    `DecisionService`, never copied in.
    """
    rows = list(rows)
    state = fold_executive(rows)
    recorded_edges = [dict(e) for e in state.edges]
    graph = build_graph(state, recorded_edges)

    return DecisionIndex(
        candidates={k: dict(v) for k, v in sorted(state.candidates.items())},
        contexts={k: dict(v) for k, v in sorted(state.contexts.items())},
        packages={k: dict(v) for k, v in sorted(state.packages.items())},
        options={k: dict(v) for k, v in sorted(state.options.items())},
        conflicts={k: dict(v) for k, v in sorted(state.conflicts.items())},
        debt={k: [dict(i) for i in v] for k, v in sorted(state.debt.items())},
        reviews={k: dict(v) for k, v in sorted(state.reviews.items())},
        overrides={k: dict(v) for k, v in sorted(state.overrides.items())},
        outcomes={k: dict(v) for k, v in sorted(state.outcomes.items())},
        expired=state.expired, graph=graph, row_count=len(rows))
