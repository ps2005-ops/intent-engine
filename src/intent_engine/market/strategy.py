"""Versioned strategy registry, isolation, and the competition lifecycle.

WHAT A STRATEGY IS HERE
-----------------------
A falsifiable economic claim, a fixed set of horizons, an explicit cost model,
and a set of preregistered conditions under which it dies. Not a function that
returns a number.

IMMUTABILITY IS THE LOAD-BEARING PROPERTY
-----------------------------------------
Once a version has produced a single live-paper observation, its specification
is frozen. Editing a threshold on a running strategy silently pools two
different experiments under one name, and the resulting track record describes
nothing that ever existed. A material change makes a NEW version; `v1` keeps its
record, including the record of having failed.

`freeze()` is what enforces it, and it is checked on every mutation attempt
rather than trusted to discipline.

ISOLATION
---------
Each strategy version owns its signals, its paper portfolio, its costs, its
metrics and its ledger entries. Pooling them would let one high-frequency
strategy's trades dominate an aggregate that then gets read as "the engine's"
win rate. The aggregate layer exists, but it is a COMPARISON, never a merge.

THE PRIOR THIS REGISTRY STARTS FROM
-----------------------------------
Eleven hypotheses proposed, eleven retired, and the one wired signal measured at
0.500. Every strategy here starts at RESEARCH with an expectation of no edge.
A registry whose default state was "promising" would be lying before it ran.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from intent_engine.market.costs import DEFAULT as DEFAULT_COSTS, CostModel
from intent_engine.market.horizons import HorizonSet

# --- lifecycle --------------------------------------------------------------
RESEARCH = "RESEARCH"
REPLAY_ELIGIBLE = "REPLAY_ELIGIBLE"
PAPER_CHALLENGER = "PAPER_CHALLENGER"
PAPER_CHAMPION = "PAPER_CHAMPION"
UNDER_REVIEW = "UNDER_REVIEW"
RETIRED = "RETIRED"

STATES = (RESEARCH, REPLAY_ELIGIBLE, PAPER_CHALLENGER, PAPER_CHAMPION,
          UNDER_REVIEW, RETIRED)

# Legal transitions. RETIRED is terminal: reviving a retired strategy is
# forbidden project-wide, so the state machine cannot express it. Reaching the
# same idea again requires a new version, whose record sits beside the old
# retirement rather than replacing it.
_TRANSITIONS = {
    RESEARCH: {REPLAY_ELIGIBLE, RETIRED},
    REPLAY_ELIGIBLE: {PAPER_CHALLENGER, UNDER_REVIEW, RETIRED},
    PAPER_CHALLENGER: {PAPER_CHAMPION, UNDER_REVIEW, RETIRED},
    PAPER_CHAMPION: {UNDER_REVIEW, RETIRED},
    UNDER_REVIEW: {PAPER_CHALLENGER, PAPER_CHAMPION, RETIRED},
    RETIRED: set(),
}

# --- validation gates -------------------------------------------------------
GATES = (
    "GATE_1_DATA_AVAILABILITY",
    "GATE_2_ECONOMIC_RATIONALE",
    "GATE_3_IMPLEMENTATION_INTEGRITY",
    "GATE_4_REPLAY_ADEQUACY",
    "GATE_5_COST_ROBUSTNESS",
    "GATE_6_HOLDOUT_BEHAVIOUR",
    "GATE_7_MULTIPLE_TESTING_CONTROL",
    "GATE_8_PAPER_CHALLENGER_APPROVAL",
)

DEFAULT_PATH = "reports/market/strategies.jsonl"


class StrategyError(ValueError):
    """A registry operation that would break versioning or isolation."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class StrategySpec:
    """The durable specification. Frozen once live."""
    strategy_id: str
    family: str
    version: str
    economic_hypothesis: str
    required_data: tuple
    signal_direction: str            # "long_only" | "long_short"
    thresholds: dict
    entry_timing: str
    exit_timing: str
    horizons: HorizonSet
    invalidation: str
    universe_tier: int
    cost_model: CostModel = field(default_factory=lambda: DEFAULT_COSTS)
    benchmark: str = "SPY"
    preregistered_at: str = field(default_factory=_now)
    research_window: Tuple[str, str] = ("1900-01-01", "2022-12-31")
    validation_window: Tuple[str, str] = ("2023-01-01", "2024-12-31")
    holdout_window: Tuple[str, str] = ("2025-01-01", "2099-12-31")
    live_paper_activated_at: Optional[str] = None
    retirement_rules: tuple = ()
    _frozen: bool = False

    @property
    def key(self) -> str:
        return f"{self.strategy_id}.{self.version}"

    def freeze(self) -> "StrategySpec":
        self._frozen = True
        return self

    def __setattr__(self, name, value):
        if getattr(self, "_frozen", False) and name != "_frozen":
            raise StrategyError(
                f"{self.strategy_id}.{self.version} is frozen: it has produced "
                f"observations, so changing {name!r} would pool two different "
                f"experiments under one name. Create a new version.")
        object.__setattr__(self, name, value)

    def as_dict(self) -> dict:
        return {"strategy_id": self.strategy_id, "family": self.family,
                "version": self.version,
                "economic_hypothesis": self.economic_hypothesis,
                "required_data": list(self.required_data),
                "signal_direction": self.signal_direction,
                "thresholds": dict(self.thresholds),
                "entry_timing": self.entry_timing,
                "exit_timing": self.exit_timing,
                "horizons": self.horizons.as_dict(),
                "invalidation": self.invalidation,
                "universe_tier": self.universe_tier,
                "cost_model": self.cost_model.version,
                "round_trip_bps": self.cost_model.round_trip_bps,
                "benchmark": self.benchmark,
                "preregistered_at": self.preregistered_at,
                "research_window": list(self.research_window),
                "validation_window": list(self.validation_window),
                "holdout_window": list(self.holdout_window),
                "live_paper_activated_at": self.live_paper_activated_at,
                "retirement_rules": list(self.retirement_rules),
                "frozen": self._frozen}


@dataclass(frozen=True)
class LifecycleEvent:
    strategy_key: str
    at: str
    state: str
    reason: str
    evidence: tuple = ()
    gates: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"record": "lifecycle", "strategy_key": self.strategy_key,
                "at": self.at, "state": self.state, "reason": self.reason,
                "evidence": list(self.evidence), "gates": dict(self.gates)}


class StrategyRegistry:
    """Append-only. Specs are declared once; state changes are appended."""

    def __init__(self, path=DEFAULT_PATH):
        self.path = pathlib.Path(path)
        self._specs: Dict[str, StrategySpec] = {}

    # --- declaration ---------------------------------------------------------
    def register(self, spec: StrategySpec) -> StrategySpec:
        if spec.key in self._specs:
            raise StrategyError(f"{spec.key} is already registered; a material "
                                f"change requires a new version")
        self._specs[spec.key] = spec
        self._append({"record": "spec", **spec.as_dict()})
        self._append(LifecycleEvent(spec.key, _now(), RESEARCH,
                                    "registered").as_dict())
        return spec

    def get(self, key: str) -> Optional[StrategySpec]:
        return self._specs.get(key)

    def all(self) -> List[StrategySpec]:
        return list(self._specs.values())

    # --- lifecycle -----------------------------------------------------------
    def state_of(self, key: str) -> str:
        events = [e for e in self._events() if e.get("strategy_key") == key]
        return events[-1]["state"] if events else RESEARCH

    def transition(self, key: str, state: str, reason: str, *,
                   evidence: Sequence[str] = (),
                   gates: Optional[dict] = None) -> LifecycleEvent:
        if state not in STATES:
            raise StrategyError(f"unknown state {state!r}")
        if not reason:
            raise StrategyError("a lifecycle transition must state its reason")
        current = self.state_of(key)
        if state not in _TRANSITIONS[current]:
            extra = (" (a retired strategy is never reactivated; register a "
                     "new version)" if current == RETIRED else "")
            raise StrategyError(
                f"{key}: {current} -> {state} is not a legal transition{extra}")
        # Entering live paper freezes the spec.
        if state in (PAPER_CHALLENGER, PAPER_CHAMPION):
            spec = self._specs.get(key)
            if spec is not None and not spec._frozen:
                spec.freeze()
        event = LifecycleEvent(key, _now(), state, reason, tuple(evidence),
                               dict(gates or {}))
        self._append(event.as_dict())
        return event

    def qualify_challenger(self, key: str, gates: dict) -> LifecycleEvent:
        """Promotion to challenger requires EVERY gate to pass.

        A failed gate stays visible in the record rather than blocking silently:
        the reason a strategy is not running is itself a research finding.
        """
        failed = [g for g in GATES if not gates.get(g, {}).get("passed")]
        if failed:
            raise StrategyError(
                f"{key} cannot become a challenger; failed: {failed}")
        return self.transition(key, PAPER_CHALLENGER,
                               "passed all eight validation gates", gates=gates)

    # --- storage -------------------------------------------------------------
    def _append(self, row: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")

    def _events(self) -> List[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("record") == "lifecycle":
                out.append(row)
        return out

    def history(self, key: str) -> List[dict]:
        return [e for e in self._events() if e.get("strategy_key") == key]


# ---------------------------------------------------------------------------
# ISOLATION — one book per strategy version.
# ---------------------------------------------------------------------------
@dataclass
class StrategyBook:
    """A strategy version's own observations. Never pooled with another's."""
    strategy_key: str
    observations: List[dict] = field(default_factory=list)

    def record(self, **row) -> None:
        row["strategy_key"] = self.strategy_key
        self.observations.append(row)

    @property
    def n_raw(self) -> int:
        return len(self.observations)

    def net_returns(self) -> List[float]:
        return [o["net_return"] for o in self.observations
                if o.get("net_return") is not None]


class IsolationError(RuntimeError):
    """Two strategies' observations were about to be pooled."""


def assert_isolated(books: Sequence[StrategyBook]) -> None:
    """No observation may carry a strategy_key other than its book's.

    Cheap to check and catches the failure that would otherwise be invisible:
    a metric computed over a merged list reads perfectly plausibly.
    """
    for book in books:
        for obs in book.observations:
            if obs.get("strategy_key") != book.strategy_key:
                raise IsolationError(
                    f"{book.strategy_key} contains an observation belonging to "
                    f"{obs.get('strategy_key')!r}")


def overlap(a: StrategyBook, b: StrategyBook) -> dict:
    """How much two strategies are actually the same experiment.

    Six strategies firing on the same security on the same day for the same
    reason are not six independent experiments, and a leaderboard that ranks
    them as if they were is ranking noise.
    """
    def keys(book):
        return {(o.get("security"), o.get("as_of")) for o in book.observations}

    ka, kb = keys(a), keys(b)
    shared = ka & kb
    union = ka | kb
    sec_a = {o.get("security") for o in a.observations}
    sec_b = {o.get("security") for o in b.observations}
    dates_a = {o.get("as_of") for o in a.observations}
    dates_b = {o.get("as_of") for o in b.observations}
    return {"pair": (a.strategy_key, b.strategy_key),
            "shared_decisions": len(shared),
            "jaccard": round(len(shared) / len(union), 4) if union else None,
            "security_overlap": round(
                len(sec_a & sec_b) / len(sec_a | sec_b), 4)
                if (sec_a | sec_b) else None,
            "date_overlap": round(
                len(dates_a & dates_b) / len(dates_a | dates_b), 4)
                if (dates_a | dates_b) else None,
            "independent": len(shared) == 0}
