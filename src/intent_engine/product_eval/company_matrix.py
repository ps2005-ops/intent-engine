"""The 100-company defect matrix, and the loop that shrinks it.

WHAT THIS IS AND WHEN IT RUNS
-----------------------------
Built now, run later. The Pre-100 gate exists precisely so that a hundred
companies are not driven through a product whose defects are still systemic —
a wave that finds the same defect a hundred times has cost a hundred runs to
learn one thing.

What it does is close a loop the programme has been running by hand:

    RUN -> RUBRIC -> DEFECTS -> CLUSTER -> REPAIR -> RERUN -> DELTA -> PROMOTE

The two steps that matter and that hand-running keeps skipping are CLUSTER and
DELTA. Cluster, because a defect seen on one company is an anecdote and the
same defect on six is a rule with a repair class attached. Delta, because a
repair that was not re-measured on the companies it was supposed to fix is a
belief, and this programme has shipped inert repairs before.

WHY IT REFUSES PER-COMPANY PATCHES (§103)
-----------------------------------------
`cluster` groups on the defect code and then reports the SHARED ATTRIBUTES of
the affected companies — business model class, sector, data state. A cluster
whose members share a business model gets a business-model repair; one whose
members share only the defect gets a universal repair. A cluster of one gets
nothing, deliberately: the honest response to a single company failing is
another observation, not a special case.

THE MEASURE OF THE LOOP IS NOT THE MEAN (§66)
---------------------------------------------
It is the WORST company and the RECURRENCE rate. A mean rises when the easy
companies get easier, which is the failure mode of every quality programme
that reports one number — and the worst company is the one a customer will
find, because they did not pick from our list.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import json
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "company_defect_matrix.v1"

#: §63. What is captured per company. Every field is either measured by the
#: rubric or read off the run — none is a judgement typed in afterwards.
MEASURES = (
    "overall", "identity_correctness", "strategic_synthesis",
    "history", "history_expectation", "history_counterfactual",
    "history_economics", "data_resolution", "data_completeness",
    "macroeconomics", "microeconomics", "competition",
    "company_specificity", "presentation_quality", "full_analysis_quality",
    "story_quality", "qa_quality", "actionability", "feedback_loop",
    "flow_quality", "learning",
)

#: The waves, in the order §100 runs them. Membership comes from the
#: manifest's cohorts, never from a list typed here.
WAVES = (("BREAKER_10", 10), ("WAVE_30", 30), ("WAVE_50", 50),
         ("WAVE_100", 100))


@dataclasses.dataclass(frozen=True)
class CompanyRow:
    """One company's measured result. The unit the whole loop operates on."""
    company: str
    company_id: str = ""
    model_class: str = ""
    sector: str = ""
    public_private: str = ""
    sparse: bool = False
    scores: Dict[str, float] = dataclasses.field(default_factory=dict)
    #: Defect codes found, with the surface each was found on.
    defects: Tuple[Tuple[str, str], str] = ()
    latency_s: float = 0.0
    run_id: str = ""
    at: str = ""

    @property
    def overall(self) -> float:
        return float(self.scores.get("overall", 0.0))

    @property
    def codes(self) -> Tuple[str, ...]:
        return tuple(sorted({code for code, _ in (self.defects or ())}))

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["defects"] = [list(d) for d in (self.defects or ())]
        return out


@dataclasses.dataclass(frozen=True)
class Cluster:
    """A defect seen on more than one company, and what it has in common."""
    code: str
    severity: str
    repair_class: str
    companies: Tuple[str, ...]
    surfaces: Tuple[str, ...]
    #: The attribute all affected companies share, if any. THE WHOLE POINT.
    shared: Dict[str, str] = dataclasses.field(default_factory=dict)

    @property
    def scope(self) -> str:
        """§62. What kind of rule fixes this. Never "this company"."""
        if "model_class" in self.shared:
            return f"business-model rule ({self.shared['model_class']})"
        if "sector" in self.shared:
            return f"sector rule ({self.shared['sector']})"
        if "public_private" in self.shared or "sparse" in self.shared:
            return "data-state rule"
        return "universal rule"

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["scope"] = self.scope
        return out


def _shared_attributes(rows: Sequence[CompanyRow],
                       population: Sequence[CompanyRow] = ()
                       ) -> Dict[str, str]:
    """Attributes that DISTINGUISH the affected companies. Empty = universal.

    "Shared" is not enough on its own. Ninety of the hundred companies in the
    validation universe are public, so two affected companies both being
    public says nothing about why they failed — and scoping the repair as a
    "data-state rule" on that basis would send someone to fix the public-
    company path for a defect that has nothing to do with it.

    An attribute counts only when the cluster shares it AND somebody outside
    the cluster does not. That makes it a discriminator rather than a
    coincidence, which is the only kind of attribute a repair can be aimed at.
    """
    if len(rows) < 2:
        return {}
    affected = {r.company for r in rows}
    others = [r for r in (population or ()) if r.company not in affected]
    # A DEFECT THAT HIT EVERYTHING IS EXPLAINED BY NOTHING.
    #
    # When the cluster IS the population there is no unaffected group to
    # contrast against, so no attribute can be a discriminator — whatever the
    # members happen to share, they share it with every company that failed
    # and with every company that did not, because there are none. The
    # honest scope is universal, and reporting "data-state rule" because two
    # affected companies were both public would send the repair at the
    # public-company path for a defect that has nothing to do with it.
    if not others:
        return {}
    shared = {}
    for field in ("model_class", "sector", "public_private"):
        values = {getattr(r, field, "") for r in rows}
        values.discard("")
        if len(values) != 1:
            continue
        value = values.pop()
        if all(getattr(r, field, "") == value for r in others):
            continue                    # everyone has it; it explains nothing
        shared[field] = value
    if all(r.sparse for r in rows) and not all(r.sparse for r in others):
        shared["sparse"] = "sparse_or_withheld"
    return shared


def cluster(rows: Sequence[CompanyRow], *, minimum: int = 2) -> List[Cluster]:
    """Defects grouped by code, most widespread first.

    `minimum` is 2 and is the load-bearing parameter. A defect on one company
    is not a cluster and must not produce a repair: the repair would be a
    special case, and special cases are what §103 exists to forbid. It is
    still recorded on the row, so the next wave can promote it.
    """
    from intent_engine.product_eval import defect_taxonomy as DT
    by_code: Dict[str, List[Tuple[CompanyRow, str]]] = {}
    for row in rows or ():
        for code, surface in (row.defects or ()):
            by_code.setdefault(code, []).append((row, surface))
    out = []
    for code, hits in by_code.items():
        members = list({r.company: r for r, _ in hits}.values())
        if len(members) < minimum:
            continue
        detector = DT.BY_CODE.get(code)
        out.append(Cluster(
            code=code,
            severity=getattr(detector, "severity", DT.SEV3),
            repair_class=getattr(detector, "repair_class", "UNKNOWN"),
            companies=tuple(sorted(r.company for r in members)),
            surfaces=tuple(sorted({s for _, s in hits})),
            shared=_shared_attributes(members, rows)))
    return sorted(out, key=lambda c: (-len(c.companies), c.code))


@dataclasses.dataclass(frozen=True)
class WaveResult:
    """One pass over a cohort. Comparable to the pass before it."""
    wave: str
    rows: Tuple[CompanyRow, ...]
    at: str = ""

    @property
    def mean(self) -> float:
        live = [r.overall for r in self.rows if r.overall]
        return round(sum(live) / len(live), 2) if live else 0.0

    @property
    def worst(self) -> Optional[CompanyRow]:
        live = [r for r in self.rows if r.overall]
        return min(live, key=lambda r: r.overall) if live else None

    @property
    def defects_per_company(self) -> float:
        if not self.rows:
            return 0.0
        return round(sum(len(r.defects or ()) for r in self.rows)
                     / len(self.rows), 2)

    def dimension_mean(self, dimension: str) -> float:
        live = [r.scores.get(dimension) for r in self.rows
                if r.scores.get(dimension) is not None]
        return round(sum(live) / len(live), 2) if live else 0.0

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "wave": self.wave, "at": self.at,
                "companies": len(self.rows), "mean": self.mean,
                "worst": (self.worst.company if self.worst else ""),
                "worst_score": (self.worst.overall if self.worst else 0.0),
                "defects_per_company": self.defects_per_company,
                "by_dimension": {d: self.dimension_mean(d) for d in MEASURES},
                "clusters": [c.as_dict() for c in cluster(self.rows)],
                "rows": [r.as_dict() for r in self.rows]}


# ===========================================================================
# §66 — did the loop actually learn anything?
# ===========================================================================
def improvement(before: WaveResult, after: WaveResult) -> dict:
    """What changed between two passes, and which repairs held.

    RECURRENCE IS THE HEADLINE, not the mean. A repair that raises the mean
    while the defect it targeted reappears on the same companies did not
    work; it moved something else. Recurrence names the defects that survived
    a repair aimed at them, per company, which is the only evidence that a
    fix reached production — this programme has shipped inert repairs, and
    a green suite did not catch a single one of them.
    """
    before_rows = {r.company: r for r in before.rows}
    after_rows = {r.company: r for r in after.rows}
    common = sorted(set(before_rows) & set(after_rows))
    recurring, fixed, new = [], [], []
    for company in common:
        was = set(before_rows[company].codes)
        now = set(after_rows[company].codes)
        recurring += [(company, c) for c in sorted(was & now)]
        fixed += [(company, c) for c in sorted(was - now)]
        new += [(company, c) for c in sorted(now - was)]
    moved = [(c, round(after_rows[c].overall - before_rows[c].overall, 2))
             for c in common]
    regressed = sorted([m for m in moved if m[1] < -0.05], key=lambda m: m[1])
    return {
        "contract": CONTRACT,
        "companies_compared": len(common),
        "mean_before": before.mean, "mean_after": after.mean,
        "mean_delta": round(after.mean - before.mean, 2),
        "worst_before": before.worst.overall if before.worst else 0.0,
        "worst_after": after.worst.overall if after.worst else 0.0,
        "defects_per_company_before": before.defects_per_company,
        "defects_per_company_after": after.defects_per_company,
        "fixed": fixed, "recurring": recurring, "new_classes": new,
        "regressed": regressed,
        # A repair "held" when nothing it targeted recurred AND nothing
        # regressed. Both halves are required: a fix that closes one defect
        # and opens another has not improved the product.
        "held": not recurring and not regressed,
    }


def promote(cluster_: Cluster, *, repair: str, before: float, after: float,
            regression_test: str) -> dict:
    """§65. A repair, recorded so the next wave can check it stayed fixed."""
    return {"contract": CONTRACT, "code": cluster_.code,
            "scope": cluster_.scope, "repair_class": cluster_.repair_class,
            "repair": repair, "companies": list(cluster_.companies),
            "score_before": before, "score_after": after,
            "delta": round(after - before, 2),
            "regression_test": regression_test,
            "promoted_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}


# ===========================================================================
# cohort selection — from the manifest, never from a list typed here
# ===========================================================================
def cohort(wave: str, *, manifest=None) -> Tuple[dict, ...]:
    """The companies in a wave, deterministically, from the manifest.

    Deterministic AND diverse: sorting by company_id alone accumulated the
    easy companies, which is the failure the manifest's own cohort derivation
    was written to avoid. The tie-break here spreads across business model
    class first, so a ten-company wave meets ten kinds of business rather
    than ten software companies.
    """
    size = dict(WAVES).get(wave)
    if size is None:
        raise ValueError(f"unknown wave {wave!r}")
    if manifest is None:
        from intent_engine.validation import manifest as M
        manifest = M.load()
    by_class: Dict[str, List] = {}
    for company in sorted(manifest.companies, key=lambda c: c.company_id):
        by_class.setdefault(company.business_model_class, []).append(company)
    picked, index = [], 0
    while len(picked) < size and any(by_class.values()):
        for key in sorted(by_class):
            bucket = by_class[key]
            if index < len(bucket) and len(picked) < size:
                picked.append(bucket[index])
        index += 1
        if index > 200:
            break
    return tuple({"company_id": c.company_id, "name": c.canonical_name,
                  "domain": c.domain, "model_class": c.business_model_class,
                  "sector": c.sector, "public_private": c.public_private,
                  "sparse": bool(c.sparse_or_withheld)} for c in picked[:size])


def load(path) -> WaveResult:
    """Read a wave back, so two runs can be compared across sessions."""
    raw = json.loads(str(path.read_text() if hasattr(path, "read_text")
                         else open(path).read()))
    rows = tuple(
        CompanyRow(company=r.get("company", ""),
                   company_id=r.get("company_id", ""),
                   model_class=r.get("model_class", ""),
                   sector=r.get("sector", ""),
                   public_private=r.get("public_private", ""),
                   sparse=bool(r.get("sparse")),
                   scores=r.get("scores") or {},
                   defects=tuple(tuple(d) for d in (r.get("defects") or ())),
                   latency_s=float(r.get("latency_s") or 0.0),
                   run_id=r.get("run_id", ""), at=r.get("at", ""))
        for r in (raw.get("rows") or ()))
    return WaveResult(wave=raw.get("wave", ""), rows=rows,
                      at=raw.get("at", ""))
