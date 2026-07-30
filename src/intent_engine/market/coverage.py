"""Opportunity coverage — which corner of the market the engine has seen.

"20–50 evaluations per day" says nothing about whether those fifty were fifty
technology large-caps in one regime. A system can look busy and well-tested
while having learned exactly one corner, and it will not discover that from
its own accuracy: it will be genuinely accurate, on the corner it knows.

This is the counterweight to novelty. Novelty asks whether a prediction is a
new SHAPE; coverage asks whether the universe those shapes are drawn from is
wide enough for the answer to generalise.

Reported as gaps rather than as a score. A single coverage number would invite
exactly the optimisation this project has just been burned by — and the useful
output is not "coverage is 0.4", it is "no healthcare, no small-cap, no
international", which names the next companies to add.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

# The dimensions a market lesson can fail to generalise across. Each is a
# separate way of being accidentally narrow.
DIMENSIONS = ("sector", "industry", "market_cap", "region", "regime")

# Market-cap buckets. Named rather than numeric so the bucket a company sits in
# survives a share-price move.
CAP_BUCKETS = ("mega", "large", "mid", "small", "micro")


def _value(company: Any, field: str) -> Optional[str]:
    value = getattr(company, field, None)
    if value is None and isinstance(company, dict):
        value = company.get(field)
    value = (str(value).strip() if value else "")
    return value or None


def observed(companies: Iterable[Any], *, regime: str = "") -> Dict[str, set]:
    """What the evaluated set actually covers, per dimension."""
    seen: Dict[str, set] = {d: set() for d in DIMENSIONS}
    for company in companies or ():
        for dimension in DIMENSIONS:
            if dimension == "regime":
                continue
            value = _value(company, dimension)
            if value:
                seen[dimension].add(value)
    if regime:
        seen["regime"].add(regime)
    return seen


def assess(companies: Sequence[Any], *, regime: str = "",
           expected: Optional[Dict[str, Sequence[str]]] = None) -> dict:
    """Coverage, and — more usefully — the gaps.

    `expected` names what a well-covered universe would contain. Without it
    this can only report what was seen, which cannot distinguish "we cover
    every sector" from "we know of one sector".
    """
    seen = observed(companies, regime=regime)
    result: Dict[str, Any] = {
        "evaluated": len(list(companies)),
        "observed": {d: sorted(v) for d, v in seen.items()},
        "counts": {d: len(v) for d, v in seen.items()},
    }
    if not expected:
        result["gaps"] = {}
        result["note"] = ("no expected universe supplied, so this reports what "
                          "was seen and cannot say what is missing")
        return result

    gaps = {}
    for dimension, wanted in expected.items():
        missing = sorted(set(wanted) - seen.get(dimension, set()))
        if missing:
            gaps[dimension] = missing
    result["gaps"] = gaps
    # The single most useful line: the dimension where the engine is most blind.
    result["widest_gap"] = (max(gaps, key=lambda d: len(gaps[d]))
                            if gaps else "")
    return result


def concentration(companies: Sequence[Any], dimension: str = "sector") -> float:
    """Share of the evaluated set sitting in its single largest bucket.

    1.0 means every company evaluated came from one sector — a system that will
    be confidently accurate about that sector and quietly wrong everywhere
    else. Reported alongside coverage because a set can touch six sectors and
    still be 80% one of them.
    """
    values: List[str] = [v for v in (_value(c, dimension) for c in companies)
                         if v]
    if not values:
        return 0.0
    top = max(values.count(v) for v in set(values))
    return round(top / len(values), 3)
