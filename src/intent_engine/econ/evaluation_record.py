"""§2: correct the statistical record by APPENDING, never by rewriting.

THE PROBLEM WITH FIXING A NUMBER
--------------------------------
`GLOBAL_COLLECTIVE_HUMAN_STATE_V1` was frozen with an interval computed by a
bootstrap that resampled ROWS. Clustered and episode-aware inference now
exist, so the stored interval is known to have been produced by a method the
engine no longer trusts.

There are two wrong responses. One is to leave it and quietly compare later
variants against a number nobody believes. The other is to edit it, which
destroys the evidence of what the system believed when it believed it, and
makes the registry unfalsifiable -- a comparator that changes to whatever the
current method produces has stopped being a comparator.

So a correction is an APPEND. The original record stays exactly as it was;
the correction names it in `supersedes`, states the method that produced each
interval, and carries the four sample numbers §2 demands. Reading the
registry in order shows both what was believed and why it changed.

WHAT A CORRECTION MUST CARRY
----------------------------
    evaluation_id / supersedes / reason
    original_method / corrected_method
    original_ci / corrected_ci
    origin_count / episode_count / n_eff
    code_sha

Everything except `reason` is machine-checkable, and `reason` is required to
be non-empty because a correction whose motivation is not written down is
indistinguishable from a result that was re-run until it looked better.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_evaluation_record.v1"

REGISTRY_PATH = pathlib.Path("reports/evaluation_registry.jsonl")

ROW_BOOTSTRAP = "ROW_BOOTSTRAP"
CLUSTER_BOOTSTRAP = "ORIGIN_CLUSTER_BOOTSTRAP"
EPISODE_AWARE = "EPISODE_AWARE_CLUSTER_BOOTSTRAP"
METHODS = (ROW_BOOTSTRAP, CLUSTER_BOOTSTRAP, EPISODE_AWARE)


class RegistryViolation(EconError):
    """Something tried to change history instead of adding to it."""


@dataclass(frozen=True)
class Evaluation:
    """One measured result, with the sample it rests on stated four ways."""

    evaluation_id: str
    #: The evaluation this one corrects, or "" for an original.
    supersedes: str
    reason: str
    method: str
    delta: float
    ci_low: float
    ci_high: float
    #: Never displayed alone. `headline` refuses to render without the rest.
    raw_rows: int
    unique_origins: int
    effective_origins: float
    independent_episodes: int
    code_sha: str
    panel_hash: str
    preregistration_hash: str
    at: str
    original_method: str = ""
    original_ci: Tuple[float, float] = (0.0, 0.0)
    mde: Optional[float] = None
    note: str = ""

    def __post_init__(self) -> None:
        require(self.method in METHODS,
                f"{self.evaluation_id}: unknown method {self.method!r}")
        require(bool(self.reason.strip()),
                f"{self.evaluation_id}: a correction with no stated reason "
                "cannot be told apart from a result re-run until it looked "
                "better")
        require(self.raw_rows >= 0 and self.unique_origins >= 0,
                f"{self.evaluation_id}: negative sample counts")
        if self.supersedes:
            require(bool(self.original_method),
                    f"{self.evaluation_id}: a correction must name the "
                    "method it is correcting, or the reader cannot tell what "
                    "changed")

    @property
    def robust(self) -> bool:
        """Interval clear of zero AND resting on enough separate events."""
        from .incremental import MIN_EPISODES
        return ((self.ci_low > 0 or self.ci_high < 0)
                and self.independent_episodes >= MIN_EPISODES)

    def headline(self) -> str:
        return (f"{self.evaluation_id}: delta {self.delta:+.5f} "
                f"[{self.ci_low:+.5f}, {self.ci_high:+.5f}] "
                f"({self.method}) on {self.raw_rows} rows / "
                f"{self.unique_origins} origins / "
                f"{self.effective_origins:.1f} effective / "
                f"{self.independent_episodes} episodes")

    def as_dict(self) -> dict:
        return {"evaluation_id": self.evaluation_id,
                "supersedes": self.supersedes, "reason": self.reason,
                "method": self.method, "delta": self.delta,
                "ci": [self.ci_low, self.ci_high],
                "original_method": self.original_method,
                "original_ci": list(self.original_ci),
                "raw_rows": self.raw_rows,
                "unique_origins": self.unique_origins,
                "effective_origins": round(self.effective_origins, 2),
                "independent_episodes": self.independent_episodes,
                "mde": self.mde, "code_sha": self.code_sha,
                "panel_hash": self.panel_hash,
                "preregistration_hash": self.preregistration_hash,
                "at": self.at, "robust": self.robust, "note": self.note,
                "headline": self.headline()}


def load(path: pathlib.Path = None) -> List[Evaluation]:
    p = path or REGISTRY_PATH
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out.append(Evaluation(
            evaluation_id=r["evaluation_id"], supersedes=r.get("supersedes", ""),
            reason=r["reason"], method=r["method"], delta=r["delta"],
            ci_low=r["ci"][0], ci_high=r["ci"][1],
            raw_rows=r["raw_rows"], unique_origins=r["unique_origins"],
            effective_origins=r["effective_origins"],
            independent_episodes=r["independent_episodes"],
            code_sha=r.get("code_sha", ""), panel_hash=r.get("panel_hash", ""),
            preregistration_hash=r.get("preregistration_hash", ""),
            at=r.get("at", ""), original_method=r.get("original_method", ""),
            original_ci=tuple(r.get("original_ci", (0.0, 0.0))),
            mde=r.get("mde"), note=r.get("note", "")))
    return out


def append(ev: Evaluation, *, path: pathlib.Path = None) -> pathlib.Path:
    """Add one evaluation. Refuses to reuse an id or to orphan a correction."""
    p = path or REGISTRY_PATH
    existing = load(p)
    by_id = {e.evaluation_id: e for e in existing}
    if ev.evaluation_id in by_id:
        raise RegistryViolation(
            f"{ev.evaluation_id} is already in the registry. A correction "
            "gets a NEW id and names the old one in `supersedes`; reusing "
            "the id would overwrite the record of what was believed.")
    if ev.supersedes and ev.supersedes not in by_id:
        # An original may live in the frozen-baseline registry rather than
        # here; that is legitimate and is recorded rather than refused.
        from . import baseline_registry as BR
        if ev.supersedes not in BR.load():
            raise RegistryViolation(
                f"{ev.evaluation_id} supersedes {ev.supersedes!r}, which is "
                "in neither registry. A correction that names nothing "
                "corrects nothing.")
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(ev.as_dict(), sort_keys=True) + "\n")
    return p


def chain(evaluation_id: str, *, path: pathlib.Path = None) -> List[Evaluation]:
    """An evaluation and everything that has corrected it, oldest first."""
    evs = load(path)
    out, frontier = [], {evaluation_id}
    for e in evs:
        if e.evaluation_id in frontier or e.supersedes in frontier:
            out.append(e)
            frontier.add(e.evaluation_id)
    return out


def current(evaluation_id: str, *, path: pathlib.Path = None
            ) -> Optional[Evaluation]:
    """The LATEST correction of an evaluation -- what to believe today."""
    c = chain(evaluation_id, path=path)
    return c[-1] if c else None


def summarise(path: pathlib.Path = None) -> dict:
    evs = load(path)
    return {"contract": CONTRACT, "evaluations": len(evs),
            "corrections": sum(1 for e in evs if e.supersedes),
            "robust": sum(1 for e in evs if e.robust),
            "by_method": {m: sum(1 for e in evs if e.method == m)
                          for m in METHODS},
            "records": [e.as_dict() for e in evs]}
