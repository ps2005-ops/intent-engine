"""Reader-facing projections of the read model.

WHY THE VIEWS LIVE HERE AND NOT IN THE WEB LAYER
-------------------------------------------------
Redaction that only exists inside a request handler is redaction that can be
skipped by the next caller — a script, a second endpoint, an export job. Put
here, it is a property of the read model itself, unit-testable without an HTTP
server, and the web layer becomes routing.

PRIVATE REFERENCES ARE REDACTED FOR EVERYONE, INCLUDING THE OWNER
------------------------------------------------------------------
`living_decision_refs`, `mdr_refs` and `mve_refs` point at tenant-partitioned
rows. This surface never emits their IDS — not to an anonymous reader, not to
an operator, not to the tenant who owns them.

That is deliberately stronger than redacting conditionally. A conditional rule
needs an authority check, the check needs the dossier to carry a tenant
identity, and the moment the neutral read model carries tenant identity it has
started to be an authorization boundary — which the ADR says it is not. With
no private id ever emitted, the cross-tenant attack has nothing to reach:
Tenant B asking for Tenant A's dossier gets the same redacted counts anybody
else gets.

The rows themselves remain reachable at `/decisions`, which already
establishes a scope and writes a tenant receipt. One authorization boundary,
in the place that already had one.

REDACTION MUST NOT LOOK LIKE ABSENCE
-------------------------------------
A redacted block keeps its state and its count and says WHY the ids are gone.
Emitting an empty `ids` list would make "you may not see these" read as "there
are none", which is the same missing-vs-zero defect this contract exists to
refuse — committed at the last possible moment, on the way out the door.
"""
from __future__ import annotations

from typing import Any, Dict, List

from intent_engine.demo_dossier import vocabulary as V
from intent_engine.demo_dossier.dossier import CompanyDemoDossier

INDEX_CONTRACT = "company_demo_dossier_index.v1"
DETAIL_CONTRACT = "company_demo_dossier_detail.v1"

#: Founder blocks whose ids point at tenant-partitioned rows.
PRIVATE_BLOCKS = ("living_decisions", "minimum_data_requests",
                  "minimum_viable_experiments")

REDACTED_NOTE = ("reference ids are not published on this surface; the rows "
                 "are tenant-partitioned and are read at /decisions under an "
                 "established scope")


def _redact(block: Dict[str, Any]) -> Dict[str, Any]:
    """Drop the ids, keep everything that makes the block readable.

    `state`, `count` and `is_measured_zero` survive, so a reader can still
    tell "three exist and you may not see them" from "none exist" from
    "nobody looked".
    """
    out = dict(block)
    out["ids"] = []
    out["ids_redacted"] = True
    out["redaction_reason"] = REDACTED_NOTE
    return out


def index_row(dossier: CompanyDemoDossier) -> Dict[str, Any]:
    """One line of the index. Bounded on purpose (§4): no evidence bodies,
    no reference lists, nothing that grows with the size of an analysis."""
    return {
        "company_id": dossier.company_id,
        "canonical_name": dossier.canonical_name,
        "domain": dossier.domain,
        "cohort": dossier.cohort,
        "manifest_version": dossier.manifest_version,
        "dossier_id": dossier.dossier_id,
        "dossier_version": dossier.dossier_version,
        "readiness": dossier.readiness,
        "crossing_state": dossier.crossing_state,
        "market_availability": dossier.market_block.get("availability"),
        "founder_availability": dossier.founder_block.get("availability"),
        "coverage_class": dossier.coverage_class,
        "effective_evidence_cutoff": dossier.effective_evidence_cutoff,
        "market_runtime_sha": dossier.market_runtime_sha,
        "founder_runtime_sha": dossier.founder_runtime_sha,
        "temporal_compatibility": dossier.temporal_compatibility,
        "population_compatibility": dossier.population_compatibility,
        "synthetic_label": dossier.synthetic_label,
        "decision_impact_state": dossier.decision_impact_state,
        "quarantined": dossier.quarantined,
        "quarantine_reasons": list(dossier.quarantine_reasons),
        "generated_at": dossier.generated_at,
    }


def index(dossiers) -> Dict[str, Any]:
    """The whole index, with the states summarised rather than scored.

    There is deliberately no single readiness percentage here. A vanity score
    would average a quarantined dossier against a ready one and produce a
    number that is true of neither.
    """
    rows: List[Dict[str, Any]] = [index_row(d) for d in dossiers]
    return {
        "contract": INDEX_CONTRACT,
        "count": len(rows),
        "state": "NO_DOSSIERS" if not rows else "DOSSIERS_PRESENT",
        "note": ("no company has been analysed in this deployment"
                 if not rows else ""),
        "by_readiness": _tally(rows, "readiness"),
        "by_crossing": _tally(rows, "crossing_state"),
        "quarantined": sum(1 for r in rows if r["quarantined"]),
        "dossiers": rows,
    }


def _tally(rows, field) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in rows:
        out[str(row.get(field))] = out.get(str(row.get(field)), 0) + 1
    return dict(sorted(out.items()))


def detail(dossier: CompanyDemoDossier) -> Dict[str, Any]:
    """One dossier, whole, with private reference ids removed.

    Every block keeps its own state, so UNAVAILABLE, NOT_ATTEMPTED, REFUSED,
    STALE, DEGRADED and available-and-empty all survive to the reader. That
    is the entire point of the surface: an operator looking at 100 companies
    needs to see which absences are ours and which are the company's.
    """
    payload = dossier.as_dict()
    payload["contract"] = DETAIL_CONTRACT
    founder = dict(payload.get("founder_block") or {})
    blocks = dict(founder.get("blocks") or {})
    for name in PRIVATE_BLOCKS:
        if name in blocks:
            blocks[name] = _redact(blocks[name])
    founder["blocks"] = blocks
    payload["founder_block"] = founder
    payload["private_references_published"] = False
    return payload


def with_executive_read(payload: Dict[str, Any],
                        read: Any) -> Dict[str, Any]:
    """Attach a composed executive read to a detail payload.

    THE COMPOSITION HAPPENS IN THE CALLER, NOT HERE. The synthesis is
    founder-side reasoning and this package is the neutral seam; importing
    it — even inside a function — puts founder logic in the seam's import
    graph, and the structural guard tokenizes the source rather than reading
    the comment above it, so it catches exactly that. It caught this.

    What this function owns is the SHAPE: the read travels on the same
    payload as the blocks it was computed from, so a surface cannot pair a
    recommendation with evidence from a different assembly.

    `read` of None is a STATE, not an omission: "the read could not be
    built" must not be indistinguishable from "this company has no read".
    """
    out = dict(payload)
    out["executive_read"] = read if read is not None else {
        "state": "EXECUTIVE_READ_UNAVAILABLE",
        "reason": ("no executive read was composed for this dossier in this "
                   "deployment; this is a statement about the composer, not "
                   "about the company")}
    return out


def not_found(company_id: str) -> Dict[str, Any]:
    """A company with no dossier is a STATE, not an error page.

    "Nobody has analysed this company" and "this company was analysed and
    refused" are different answers, and a bare 404 gives the reader neither.
    """
    return {
        "contract": DETAIL_CONTRACT,
        "company_id": company_id,
        "state": V.NOT_STARTED,
        "reason": ("no dossier has been assembled for this company in this "
                   "deployment; it has not been analysed here, which is not "
                   "a statement about the company"),
    }
