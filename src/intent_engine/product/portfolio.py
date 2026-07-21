"""Portfolio rollup, balance, readiness, and the executive summary (T020).

    Portfolio -> Strategic Themes -> Initiatives -> Opportunities
              -> Proposals -> Specs

The portfolio is a ROLLUP VIEW folded from the log. It is not a second
store, and it holds no fact that is not already recorded somewhere else.

Strategic themes are always human-created. An agent may report that a
theme is empty or overloaded; it may not decide what the themes are.

Four things this module keeps apart that are routinely collapsed into
one, to the founder's cost:

    PRIORITY     how valuable this looks from recorded facts
    SEQUENCING   what order the dependency graph permits
    BLOCKING     what is actually in the way right now
    READINESS    whether this could be started at all

Highest priority does not imply build first. A dependency can put a
lower-priority proposal ahead of a higher-priority one, and a system that
reports only a priority ordering hides that.

BALANCE is reported against a human-declared target band. With no band
declared, the distribution is reported and the verdict is withheld —
"too much technical debt" is a judgment about strategy, and strategy
comes from a person.
"""
from __future__ import annotations

from intent_engine.product.graph import sequence
from intent_engine.product.records import (
    STATUS_ACCEPTED, STATUS_EXECUTION_CANDIDATE, STATUS_RETIRED,
    STATUS_REVIEW_REQUESTED, WORK_CATEGORIES,
)
from intent_engine.product.scoring import OK, UNAVAILABLE

ROLLUP_VERSION = "portfolio_rollup.v1"
BALANCE_VERSION = "portfolio_balance.v1"
READINESS_VERSION = "portfolio_readiness.v1"
SUMMARY_VERSION = "executive_summary.v1"

READY = "READY"
BLOCKED = "BLOCKED"
NEEDS_SPEC = "NEEDS_SPEC"
NEEDS_REVIEW = "NEEDS_REVIEW"
NEEDS_DECISION = "NEEDS_DECISION"
RETIRED = "RETIRED"


def _score_value(block: dict, path: str):
    """Read one scalar out of a score block without inventing one when the
    block is UNAVAILABLE."""
    if not block:
        return None
    if path == "opportunity_score":
        item = block.get("opportunity_score") or {}
    elif path == "cost_of_delay":
        item = block.get("cost_of_delay") or {}
    else:
        item = (block.get("confidence") or {}).get(path) or {}
    return item.get("value") if item.get("status") == OK else None


def readiness_report(state, index, *, scores_by_proposal=None) -> dict:
    """Priority, sequencing, blocking, and readiness — reported
    separately, because they answer four different questions."""
    scores_by_proposal = scores_by_proposal or {}
    graph = index.graph
    entries = {}

    for proposal_id, proposal in sorted(state.proposals.items()):
        spec_id, spec = state.spec_for_current_version(proposal_id)
        blockers = [b for b in graph.blockers_of(proposal_id)
                    if state.proposals.get(b, {}).get("status")
                    not in (STATUS_ACCEPTED, STATUS_EXECUTION_CANDIDATE)]
        status = proposal["status"]
        # Precedence, stated rather than implied: retirement ends the
        # question; an EXTERNAL block dominates a local gap, because
        # writing the missing spec would not unblock it; then the local
        # gaps in the order a person would close them. `blocked_by` is
        # reported separately regardless, so no information is lost to
        # this collapse into one label.
        if status == STATUS_RETIRED:
            readiness = RETIRED
        elif blockers:
            readiness = BLOCKED
        elif spec_id is None:
            readiness = NEEDS_SPEC
        elif status in (STATUS_ACCEPTED,) and not proposal.get("decision_id"):
            readiness = NEEDS_DECISION
        elif status == STATUS_EXECUTION_CANDIDATE:
            readiness = READY
        else:
            readiness = NEEDS_REVIEW
        block = scores_by_proposal.get(proposal_id) or {}
        entries[proposal_id] = {
            "proposal_id": proposal_id,
            "proposal_version": proposal["version"],
            "status": status,
            "readiness": readiness,
            "blocked_by": blockers,
            "depends_on": graph.dependencies_of(proposal_id),
            "alternatives": graph.alternatives_of(proposal_id),
            "spec_id": spec_id,
            "spec_version": spec["version"] if spec else None,
            "decision_id": proposal.get("decision_id"),
            "decision_debt": list(proposal.get("decision_debt") or []),
            "opportunity_score": _score_value(block, "opportunity_score"),
            "cost_of_delay": _score_value(block, "cost_of_delay"),
        }

    # PRIORITY — deterministic, and only over proposals that actually have
    # a composite. A proposal whose composite is UNAVAILABLE is listed with
    # the gap named rather than ranked against one that has a number.
    rankable = [e for e in entries.values()
                if e["opportunity_score"] is not None]
    unrankable = sorted(e["proposal_id"] for e in entries.values()
                        if e["opportunity_score"] is None)
    ordered = sorted(rankable,
                     key=lambda e: (-(e["cost_of_delay"] or 0.0),
                                    -e["opportunity_score"],
                                    e["proposal_id"]))
    for rank, entry in enumerate(ordered, 1):
        entries[entry["proposal_id"]]["priority_rank"] = rank
    for proposal_id in unrankable:
        entries[proposal_id]["priority_rank"] = None

    # SEQUENCING — the order the dependency graph permits, which is a
    # different question from priority.
    sequenced = sequence(graph, list(entries))
    for position, proposal_id in enumerate(sequenced, 1):
        entries[proposal_id]["sequence_position"] = position

    return {
        "readiness_version": READINESS_VERSION,
        "entries": entries,
        "priority_order": [e["proposal_id"] for e in ordered],
        "unrankable": unrankable,
        "sequence_order": sequenced,
        "note": ("priority, sequencing, blocking, and readiness are reported "
                 "separately; a higher priority does not imply an earlier "
                 "position when a dependency says otherwise"),
        "unrankable_note": (
            "a proposal whose composite score is UNAVAILABLE is listed here "
            "rather than ranked against one that has a number"),
    }


def balance_report(state, index, *, portfolio_id: str,
                   scores_by_proposal=None) -> dict:
    """Is the portfolio lopsided? Reported against a HUMAN-declared band.

    With no band declared this returns the distribution and withholds the
    verdict, because "too many growth bets" is a strategy judgment.
    """
    counts = {category: 0 for category in sorted(WORK_CATEGORIES)}
    for proposal in state.proposals.values():
        if proposal["status"] == STATUS_RETIRED:
            continue
        counts[proposal.get("work_category", "unknown")] += 1
    for opportunity in index.usable_opportunities():
        category = opportunity.get("work_category", "unknown")
        if category in counts:
            counts[f"{category}"] += 0     # opportunities are counted below

    opportunity_counts = {category: 0 for category in sorted(WORK_CATEGORIES)}
    for opportunity in index.usable_opportunities():
        opportunity_counts[opportunity.get("work_category", "unknown")] += 1

    total = sum(counts.values())
    shares = ({category: round(count / total, 4)
               for category, count in counts.items()} if total else {})
    bands = state.balance_targets.get(portfolio_id) or {}

    report = {
        "balance_version": BALANCE_VERSION,
        "portfolio_id": portfolio_id,
        "proposal_counts_by_category": counts,
        "opportunity_counts_by_category": opportunity_counts,
        "total_active_proposals": total,
        "shares": shares,
        "declared_bands": dict(bands),
    }
    if not bands:
        report["status"] = UNAVAILABLE
        report["findings"] = []
        report["note"] = (
            "no human balance target is declared for this portfolio, so the "
            "distribution is reported and the verdict is withheld — what "
            "counts as too much of one kind of work is a strategy judgment")
        return report
    if not total:
        report["status"] = UNAVAILABLE
        report["findings"] = []
        report["note"] = ("no active proposal is recorded, so a share cannot "
                          "honestly be computed")
        return report

    findings = []
    for category, band in sorted(bands.items()):
        low, high = band.get("min"), band.get("max")
        share = shares.get(category, 0.0)
        if low is not None and share < low:
            findings.append({
                "category": category, "share": share, "band": band,
                "finding": "below the declared band",
                "detail": f"{share} of active proposals against a declared "
                          f"minimum of {low}"})
        elif high is not None and share > high:
            findings.append({
                "category": category, "share": share, "band": band,
                "finding": "above the declared band",
                "detail": f"{share} of active proposals against a declared "
                          f"maximum of {high}"})
    report["status"] = OK
    report["findings"] = findings
    report["note"] = ("shares are measured against the bands a person "
                      "declared for this portfolio")
    return report


def portfolio_rollup(state, index, *, portfolio_id: str,
                     scores_by_proposal=None, research_debt_by_opportunity=None,
                     as_of: str = None) -> dict:
    """The single deterministic call T021 reads instead of reassembling
    this from seven subsystems."""
    scores_by_proposal = scores_by_proposal or {}
    research_debt_by_opportunity = research_debt_by_opportunity or {}

    themes = {tid: theme for tid, theme in sorted(state.themes.items())
              if theme["portfolio_id"] == portfolio_id}
    initiatives = {iid: initiative
                   for iid, initiative in sorted(state.initiatives.items())
                   if initiative["theme_id"] in themes}

    per_initiative = {}
    for initiative_id, initiative in initiatives.items():
        opportunities = [o for o in index.opportunities.values()
                         if o.get("initiative_id") == initiative_id]
        opportunity_ids = sorted(o["opportunity_id"] for o in opportunities)
        proposals = [p for p in index.proposals.values()
                     if p["opportunity_id"] in set(opportunity_ids)]
        by_status = {}
        for proposal in proposals:
            by_status[proposal["status"]] = by_status.get(
                proposal["status"], 0) + 1

        coverage_values, timestamps, debt = [], [], []
        for proposal in proposals:
            block = scores_by_proposal.get(proposal["proposal_id"]) or {}
            dimensions = block.get("dimensions") or {}
            evidence = dimensions.get("evidence_coverage") or {}
            if evidence.get("status") == OK:
                coverage_values.append(evidence["value"])
            fresh = dimensions.get("freshness") or {}
            for ts in (fresh.get("inputs") or {}).get("input_timestamps", []):
                timestamps.append(ts)
        for opportunity_id in opportunity_ids:
            debt.extend(research_debt_by_opportunity.get(opportunity_id, []))

        per_initiative[initiative_id] = {
            "initiative_id": initiative_id,
            "theme_id": initiative["theme_id"],
            "name": initiative.get("name", ""),
            "opportunity_count": len(opportunity_ids),
            "opportunity_ids": opportunity_ids,
            "proposal_count": len(proposals),
            "proposal_count_by_status": dict(sorted(by_status.items())),
            "aggregate_evidence_coverage": (
                round(sum(coverage_values) / len(coverage_values), 4)
                if coverage_values else None),
            "aggregate_evidence_coverage_status": (
                OK if coverage_values else UNAVAILABLE),
            "aggregate_research_debt": len(debt),
            "research_debt_kinds": sorted({d.get("kind") for d in debt
                                           if d.get("kind")}),
            "newest_load_bearing_input": max(timestamps) if timestamps else None,
            "oldest_load_bearing_input": min(timestamps) if timestamps else None,
        }

    unattached = sorted(o["opportunity_id"] for o in index.usable_opportunities()
                        if not o.get("initiative_id"))

    return {
        "rollup_version": ROLLUP_VERSION,
        "portfolio_id": portfolio_id,
        "as_of": as_of,
        "themes": {tid: {"theme_id": tid, "name": theme.get("name", ""),
                         "initiative_ids": sorted(
                             iid for iid, initiative in initiatives.items()
                             if initiative["theme_id"] == tid)}
                   for tid, theme in themes.items()},
        "initiatives": per_initiative,
        "unattached_opportunities": unattached,
        "totals": {
            "themes": len(themes),
            "initiatives": len(initiatives),
            "opportunities": len(index.usable_opportunities()),
            "proposals": len(index.proposals),
            "specs": len(state.specs),
        },
        "note": ("a rollup view folded from the append-only log; it holds no "
                 "fact that is not recorded elsewhere"),
    }


def executive_summary(state, index, *, portfolio_id: str,
                      scores_by_proposal=None, readiness=None,
                      rollup=None) -> dict:
    """What T021 will read: the six questions a founder asks about a
    portfolio, each answered from recorded facts with its gaps named."""
    scores_by_proposal = scores_by_proposal or {}
    readiness = readiness or readiness_report(
        state, index, scores_by_proposal=scores_by_proposal)
    rollup = rollup or portfolio_rollup(state, index,
                                        portfolio_id=portfolio_id,
                                        scores_by_proposal=scores_by_proposal)
    entries = readiness["entries"]

    biggest_opportunities = [
        {"proposal_id": pid,
         "opportunity_score": entries[pid]["opportunity_score"],
         "cost_of_delay": entries[pid]["cost_of_delay"]}
        for pid in readiness["priority_order"][:5]]

    risks, unknowns, evidence_gaps = [], [], []
    for proposal_id, block in sorted(scores_by_proposal.items()):
        composite = block.get("opportunity_score") or {}
        for gap in composite.get("gaps", []):
            evidence_gaps.append({"proposal_id": proposal_id, "gap": gap})
        confidence = block.get("confidence") or {}
        proposal_conf = confidence.get("proposal_confidence") or {}
        if proposal_conf.get("status") == OK:
            unknown_count = (proposal_conf.get("inputs") or {}).get(
                "unknown_count", 0)
            open_count = (proposal_conf.get("inputs") or {}).get(
                "open_question_count", 0)
            unknowns.append({"proposal_id": proposal_id,
                             "unknown_count": unknown_count,
                             "open_question_count": open_count,
                             "proposal_confidence": proposal_conf.get("value")})
        cod = block.get("cost_of_delay") or {}
        components = cod.get("components") or {}
        growth = components.get("growth_urgency") or {}
        if growth.get("status") == OK and growth.get("value"):
            risks.append({"proposal_id": proposal_id,
                          "risk": "a linked experiment breached a "
                                  "pre-registered guardrail",
                          "detail": growth.get("note", "")})

    blocked_by_initiative = {}
    for initiative_id, initiative in rollup["initiatives"].items():
        blocked = []
        for opportunity_id in initiative["opportunity_ids"]:
            for proposal in index.proposals.values():
                if proposal["opportunity_id"] == opportunity_id:
                    entry = entries.get(proposal["proposal_id"])
                    if entry and entry["readiness"] == BLOCKED:
                        blocked.append(proposal["proposal_id"])
        blocked_by_initiative[initiative_id] = sorted(blocked)

    decision_debt = []
    for proposal_id, entry in sorted(entries.items()):
        for item in entry["decision_debt"]:
            decision_debt.append({"proposal_id": proposal_id,
                                  "kind": item.get("kind"),
                                  "detail": item.get("detail", "")})
    debt_by_kind = {}
    for item in decision_debt:
        debt_by_kind.setdefault(item["kind"], []).append(item["proposal_id"])

    pending = sorted(pid for pid, proposal in state.proposals.items()
                     if proposal["status"] == STATUS_REVIEW_REQUESTED)

    return {
        "summary_version": SUMMARY_VERSION,
        "portfolio_id": portfolio_id,
        "biggest_opportunities": biggest_opportunities,
        "biggest_risks": sorted(risks, key=lambda r: r["proposal_id"]),
        "biggest_unknowns": sorted(unknowns,
                                   key=lambda u: (-u["unknown_count"],
                                                  u["proposal_id"]))[:5],
        "largest_evidence_gaps": sorted(evidence_gaps,
                                        key=lambda g: g["proposal_id"]),
        "most_blocked_initiatives": sorted(
            ({"initiative_id": iid, "blocked_proposals": blocked}
             for iid, blocked in blocked_by_initiative.items() if blocked),
            key=lambda b: (-len(b["blocked_proposals"]), b["initiative_id"])),
        "highest_decision_debt": {
            "total": len(decision_debt),
            "by_kind": {k: sorted(v) for k, v in sorted(debt_by_kind.items())},
            "items": decision_debt},
        "pending_reviews": pending,
        "unrankable_proposals": readiness["unrankable"],
        "note": ("every line here resolves to a recorded fact; a gap is named "
                 "rather than filled in"),
    }
