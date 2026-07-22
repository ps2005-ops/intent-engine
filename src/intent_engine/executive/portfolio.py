"""Executive portfolio and the health dashboard (T021).

The portfolio READS T020's rollup and extends it with decision packages
and candidates. It does NOT stand up a second hierarchy: strategic themes
and initiatives are human-created in T020, and a second, differently
ordered hierarchy of the same thing is a defect, not a feature.

    Portfolio -> Strategic Themes -> Initiatives -> Opportunities ->
        Proposals -> Specs           (all owned by T020, read here)
              +  Decision Candidates  (owned here)
              +  Decision Packages    (owned here)

The health dashboard is the daily-briefing substrate for T023 (Personal
AI): one deterministic read that answers "what is the shape of the
founder's decision load right now?".
"""
from __future__ import annotations

PORTFOLIO_VERSION = "executive_portfolio.v1"
DASHBOARD_VERSION = "executive_health.v1"


def executive_portfolio(index, *, product_rollup=None,
                        candidate_initiatives=None) -> dict:
    """Extends T020's rollup rather than replacing it. `product_rollup` is
    the object T020's `portfolio_rollup` already returns; this attaches the
    executive layer to it without recomputing any of it."""
    candidate_initiatives = candidate_initiatives or {}
    rollup = product_rollup or {"initiatives": {}, "themes": {},
                                "totals": {}, "note": "no product rollup "
                                "supplied"}

    initiatives = {}
    for initiative_id, initiative in rollup.get("initiatives", {}).items():
        attached = candidate_initiatives.get(initiative_id, [])
        packages = [pid for pid, package in index.packages.items()
                    if package["candidate_id"] in set(attached)]
        initiatives[initiative_id] = {
            **initiative,
            "decision_candidates": sorted(attached),
            "decision_packages": sorted(packages),
        }

    unattached = sorted(c["candidate_id"] for c in index.open_candidates()
                        if not any(c["candidate_id"] in v
                                   for v in candidate_initiatives.values()))

    return {
        "portfolio_version": PORTFOLIO_VERSION,
        "reads_product_rollup": rollup.get("rollup_version"),
        "themes": rollup.get("themes", {}),
        "initiatives": initiatives,
        "product_totals": rollup.get("totals", {}),
        "decision_totals": {
            "open_candidates": len(index.open_candidates()),
            "packages": len(index.packages),
            "expired": len(index.expired),
        },
        "unattached_candidates": unattached,
        "note": ("extends T020's hierarchy with decisions; it does not "
                 "recompute or duplicate that hierarchy, and strategic "
                 "themes remain human-created in T020"),
    }


def health_dashboard(index, *, research_debt=0, spec_debt=0) -> dict:
    """One deterministic read: the shape of the founder's decision load.

    This becomes Personal AI's daily briefing. Every figure resolves to a
    recorded fact; a gap is named rather than filled with a zero.
    """
    open_candidates = index.open_candidates()
    blocked = index.blocked_candidates()
    open_debt = index.open_decision_debt()
    conflicts = list(index.conflicts.values())
    by_conflict_kind = {}
    for conflict in conflicts:
        by_conflict_kind.setdefault(conflict["kind"], 0)
        by_conflict_kind[conflict["kind"]] += 1

    # packages resting on an UNAVAILABLE readiness input, surfaced honestly
    unavailable_packages = []
    for package_id, package in sorted(index.packages.items()):
        if package["outcome"] == "no_recommendation":
            unavailable_packages.append(package_id)

    return {
        "dashboard_version": DASHBOARD_VERSION,
        "decision_backlog": len(open_candidates),
        "conflict_count": len(conflicts),
        "conflicts_by_kind": dict(sorted(by_conflict_kind.items())),
        "decision_debt": len(open_debt),
        "decision_debt_by_kind": _count_kinds(open_debt),
        "research_debt": research_debt,
        "spec_debt": spec_debt,
        "expired_decisions": len(index.expired),
        "no_recommendation_packages": unavailable_packages,
        "blocked_decisions": len(blocked),
        "review_queue": len(index.review_packages()),
        "note": ("a single deterministic read of the founder's decision "
                 "load; every count resolves to a recorded fact, and a gap "
                 "is named rather than shown as zero"),
    }


def _count_kinds(items: list) -> dict:
    out = {}
    for item in items:
        out.setdefault(item["kind"], 0)
        out[item["kind"]] += 1
    return dict(sorted(out.items()))
