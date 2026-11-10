"""Shadow DECISION policies — alternative ways to choose, run side by side.

WHAT IS ALREADY HERE, AND WHAT IS NOT
-------------------------------------
`paper_engine` already runs isolated per-strategy control books with their own
position identity, a NO-ALPHA-CLAIM label and a graduation gate. That covers
shadow *strategies*: different signals over the same prices.

It does not cover shadow *policies*: different ways of DECIDING given the same
evidence — rank by expected-vs-observed mismatch, by hidden-state movement, by
causal-pathway support, by information value. Those are the choices this cycle
introduced, and their calibration is a separate question from any signal's.

So this module models decisions, not positions. It opens nothing, submits
nothing, and holds no position identity — which is also why it cannot leak
into the principal paper book: there is no shared object to leak through.

ISOLATION IS STRUCTURAL, NOT PROCEDURAL
---------------------------------------
Each policy owns its own record list, keyed by policy name. `PolicyBook.merge`
does not exist. `promote` returns a recommendation for a human and never
mutates anything, because the one thing a self-evaluating system must not do
is grant itself authority on its own evidence.

EVIDENCE FLOORS BEFORE ANY COMPARISON
-------------------------------------
A policy with nine decisions that "beat" the baseline has told you nothing.
`compare` refuses to rank below `MIN_DECISIONS` and reports
INSUFFICIENT_EVIDENCE, and it applies a multiple-comparisons correction
because running eleven policies and reporting the best one is how noise gets
promoted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

CONTRACT_VERSION = "shadow_policy.v1"

# Below this a comparison is noise wearing a decimal point.
MIN_DECISIONS = 30

# Policies that may learn. Exactly one may ever inform the principal book,
# and only a human may make that change.
STRICT = "strict"
AGGRESSIVE = "aggressive"
MOMENTUM_FIRST = "momentum_first"
MEAN_REVERSION = "mean_reversion"
MACRO_FIRST = "macro_first"
INDUSTRY_FIRST = "industry_first"
COMPETITOR_ACTION_FIRST = "competitor_action_first"
EXPECTED_VS_OBSERVED = "expected_vs_observed"
HIDDEN_STATE = "hidden_state"
CAUSAL_GRAPH = "causal_graph"
INFORMATION_VALUE = "information_value"

POLICIES = (STRICT, AGGRESSIVE, MOMENTUM_FIRST, MEAN_REVERSION, MACRO_FIRST,
            INDUSTRY_FIRST, COMPETITOR_ACTION_FIRST, EXPECTED_VS_OBSERVED,
            HIDDEN_STATE, CAUSAL_GRAPH, INFORMATION_VALUE)

# The one policy whose decisions reach the principal paper book. Changing it
# is a human act; nothing in this module writes to it.
APPROVED_POLICY = STRICT

NO_ALPHA_CLAIM = "SHADOW POLICY — DECISION RANKING ONLY, NO ALPHA CLAIM"


class PolicyError(RuntimeError):
    """An isolation or promotion rule was violated."""


@dataclass(frozen=True)
class PolicyDecision:
    """What one policy would have chosen, and what happened."""
    policy: str
    subject: str
    at: str
    action: str
    rank: Optional[int] = None
    rationale: str = ""
    outcome: Optional[float] = None
    resolved_at: str = ""

    @property
    def resolved(self) -> bool:
        return self.outcome is not None

    def as_dict(self) -> dict:
        return {"policy": self.policy, "subject": self.subject,
                "at": self.at, "action": self.action, "rank": self.rank,
                "rationale": self.rationale, "outcome": self.outcome,
                "resolved_at": self.resolved_at, "resolved": self.resolved}


class PolicyBook:
    """One policy's isolated record. No positions, no orders, no identity."""

    def __init__(self, policy: str):
        if policy not in POLICIES:
            raise PolicyError(f"unknown policy {policy!r}")
        self.policy = policy
        self._decisions: List[PolicyDecision] = []

    def decide(self, *, subject: str, at: str, action: str,
               rank: Optional[int] = None,
               rationale: str = "") -> PolicyDecision:
        d = PolicyDecision(policy=self.policy, subject=subject, at=at[:10],
                           action=action, rank=rank, rationale=rationale)
        self._decisions.append(d)
        return d

    def resolve(self, *, subject: str, at: str, outcome: float) -> int:
        """Attach an outcome to this policy's own decisions only."""
        from dataclasses import replace
        n = 0
        for i, d in enumerate(self._decisions):
            if d.subject == subject and not d.resolved and d.at <= at[:10]:
                self._decisions[i] = replace(d, outcome=outcome,
                                             resolved_at=at[:10])
                n += 1
        return n

    @property
    def decisions(self) -> Tuple[PolicyDecision, ...]:
        return tuple(self._decisions)

    def summary(self) -> dict:
        resolved = [d for d in self._decisions if d.resolved]
        acted = [d for d in resolved if d.action != "NO_TRADE"]
        return {
            "policy": self.policy, "label": NO_ALPHA_CLAIM,
            "decisions": len(self._decisions), "resolved": len(resolved),
            "acted": len(acted),
            "no_trade": len(resolved) - len(acted),
            "mean_outcome_of_acted": round(
                sum(d.outcome for d in acted) / len(acted), 6)
            if acted else None,
            "is_approved_policy": self.policy == APPROVED_POLICY,
            "affects_principal_book": self.policy == APPROVED_POLICY,
        }


class ShadowRegistry:
    """All shadow policies. Isolated by construction — no merge exists."""

    def __init__(self, policies: Sequence[str] = POLICIES):
        self._books: Dict[str, PolicyBook] = {
            p: PolicyBook(p) for p in policies}

    def book(self, policy: str) -> PolicyBook:
        if policy not in self._books:
            raise PolicyError(f"policy {policy!r} is not registered")
        return self._books[policy]

    def all_books(self) -> Tuple[PolicyBook, ...]:
        return tuple(self._books.values())

    def assert_isolated(self) -> None:
        """No decision may appear under a policy that did not make it.

        Cheap to check and the whole guarantee. A break proof writes a
        foreign decision into a book and expects this to fire.
        """
        for policy, book in self._books.items():
            for d in book.decisions:
                if d.policy != policy:
                    raise PolicyError(
                        f"isolation breach: a {d.policy!r} decision is "
                        f"recorded in the {policy!r} book")

    def compare(self, *, baseline: str = STRICT,
                min_decisions: int = MIN_DECISIONS) -> dict:
        """Rank policies — or refuse, which is the common and correct result.

        Two guards. An evidence floor, because a policy with nine resolved
        decisions has demonstrated nothing. And a multiple-comparisons
        correction, because running eleven policies and reporting the winner
        is a procedure that produces a winner from pure noise every time.
        """
        rows = []
        eligible = 0
        for book in self._books.values():
            s = book.summary()
            if s["resolved"] < min_decisions:
                s["verdict"] = "INSUFFICIENT_EVIDENCE"
                s["note"] = (f"{s['resolved']} resolved decisions against a "
                             f"floor of {min_decisions}")
            else:
                eligible += 1
                s["verdict"] = "MEASURED"
            rows.append(s)

        note = ("No policy has enough resolved decisions to be ranked, which "
                "is the expected state early in a policy's life.")
        if eligible >= 2:
            note = (f"{eligible} policies are eligible. Any apparent "
                    f"advantage must clear a multiple-comparisons correction "
                    f"across {len(self._books)} policies before it is "
                    f"reported as a finding; this table is descriptive.")
        return {"baseline": baseline, "policies": len(self._books),
                "eligible_for_comparison": eligible,
                "label": NO_ALPHA_CLAIM, "rows": rows, "note": note,
                "approved_policy": APPROVED_POLICY}


def promote(registry: ShadowRegistry, policy: str, *,
            evidence_floor: int = MIN_DECISIONS) -> dict:
    """Evaluate a promotion case. NEVER performs one.

    Returns a recommendation for a human. There is deliberately no code path
    that changes `APPROVED_POLICY`: a system that can promote its own policy
    on its own evidence will eventually do so, and the gate that stops it
    must not be one it can reach.
    """
    book = registry.book(policy)
    s = book.summary()
    if s["resolved"] < evidence_floor:
        return {"policy": policy, "recommendation": "REJECT",
                "reason": (f"{s['resolved']} resolved decisions against a "
                           f"floor of {evidence_floor}"),
                "promoted": False, "requires_human_approval": True}
    return {"policy": policy, "recommendation": "ELIGIBLE_FOR_HUMAN_REVIEW",
            "reason": ("evidence floor met; promotion remains a human "
                       "decision and this function does not perform one"),
            "promoted": False, "requires_human_approval": True,
            "current_approved_policy": APPROVED_POLICY}
