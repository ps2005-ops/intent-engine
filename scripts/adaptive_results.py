#!/usr/bin/env python3
"""Turn the raw matrix rows into the qualification RESULTS document.

Separate from the harness on purpose. The harness measures and persists; this
reads what it persisted and decides what the numbers MEAN. Keeping them apart
is what makes it possible to re-score a frozen run without re-running it --
and a scorer bug that silently spends a live quota is the recorded failure
this separation answers.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def gates(row: dict) -> dict:
    """One row against every gate in the preregistration.

    A gate is PASS, ABSTAIN or FAIL. ABSTAIN is a real result and it counts
    toward the total: a company whose public record cannot support a reading
    passes by showing the right model, the right lens, the gap and what it
    would read next.
    """
    tel = row.get("telemetry") or {}
    lens = row.get("primary_lens", "")
    product = [d for d in (row.get("defects") or [])
               if d.get("kind") == "PRODUCT_DEFECT"]

    def ok(condition, abstain=False):
        return "ABSTAIN" if abstain else ("PASS" if condition else "FAIL")

    identity_ok = (row.get("identity_on_page")
                   and row.get("resolved_identity", "")
                   and not row.get("leaks"))
    profile_ok = (row.get("business_model", "UNKNOWN") != "UNKNOWN"
                  and row.get("profile_source", "NONE") != "NONE")
    # THE THREE STATES, read from the product rather than inferred from
    # whether a lens happened to be selected.
    reading = bool(tel.get("decision_reading_available"))
    has_profile = bool(tel.get("profile_available"))
    has_lens = bool(tel.get("lens_available"))
    domains = list(tel.get("potential_domains") or ())

    # A decision-grade run owes ranked opportunities and a causal chain; a
    # bounded run owes potential domains and an investigation chain. Holding
    # a bounded run to the decision-grade gate is how an instrument reports a
    # correct refusal as a defect.
    map_ok = (row.get("decision_opportunity_count", 0) >= 1 if reading
              else bool(domains))
    lens_ok = bool(lens) and row.get("lens_matches_expectation", False)
    diff_ok = (row.get("has_why_different", False)
               and bool(tel.get("differentiation_carried_by")))
    chain_ok = (row.get("causal_chain_nodes", 0) >= 3 if reading
                else bool(row.get("has_investigation_chain")))
    evidence_ok = (row.get("evidence_status") == 200
                   or row.get("causal_evidence_coverage", 0) > 0)
    counter_ok = (bool(tel.get("counterevidence_present")) if reading
                  else bool(tel.get("evidence_limitation")))
    value_ok = bool(tel.get("information_priority")) or bool(
        tel.get("what_would_unlock_a_decision")) or map_ok
    qa_ok = row.get("qa_ok", 0) >= 6
    follow_ok = row.get("followup_pass", False)
    ceo_ok = row.get("role_ceo_status") == 200
    cso_ok = (row.get("role_cso_status") == 200
              and row.get("role_views_differ", False)
              and row.get("role_facts_identical", True))

    # ABSTENTION is only defensible when the model, the gap and the next step
    # are all present. An empty page is not an abstention.
    # A DEFENSIBLE ABSTENTION is: we read the company, we know which
    # decisions tend to matter for it, and the evidence will not carry a
    # recommendation -- and it says all three. An empty page is not one.
    abstaining = (not reading and has_profile and has_lens
                  and bool(tel.get("evidence_limitation"))
                  and bool(tel.get("what_would_unlock_a_decision")))
    return {
        "identity": ok(identity_ok),
        "company_profile": ok(profile_ok),
        "decision_map": ok(map_ok, abstain=not map_ok and abstaining),
        # ABSTAIN ONLY WHEN THE GATE ITSELF DID NOT PASS. Every other
        # gate here reads `not X_ok and abstaining`; this one did not,
        # so a company with a correct, defensible lens was recorded as
        # abstaining ON THE LENS -- understating the result it was
        # built to measure.
        "strategic_lens": ok(lens_ok, abstain=abstaining and not lens_ok),
        "differentiation": ok(diff_ok),
        "causal_chain": ok(chain_ok, abstain=not chain_ok and abstaining),
        "evidence": ok(evidence_ok),
        "counterevidence": ok(counter_ok, abstain=not counter_ok
                              and abstaining),
        "thesis_or_abstention": ok((reading and map_ok) or abstaining),
        "profile_available": ok(has_profile),
        "lens_available": ok(has_lens),
        "decision_reading_available": ok(reading, abstain=not reading
                                         and abstaining),
        "decision_value": ok(value_ok),
        "qa": ok(qa_ok),
        "followup": ok(follow_ok),
        "ceo_role": ok(ceo_ok),
        "strategy_role": ok(cso_ok),
        "no_product_defect": ok(not product),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", default="reports/adaptive_ten_matrix.json")
    ap.add_argument("--out",
                    default="docs/ADAPTIVE_STRATEGIC_INTELLIGENCE_RESULTS.json")
    a = ap.parse_args()
    raw = json.loads((ROOT / a.matrix).read_text())
    rows = raw.get("rows", [])

    scored, tallies = [], {}
    for row in rows:
        g = gates(row)
        for name, verdict in g.items():
            bucket = tallies.setdefault(name, {"PASS": 0, "ABSTAIN": 0,
                                               "FAIL": 0})
            bucket[verdict] += 1
        tel = row.get("telemetry") or {}
        scored.append({
            "company": row.get("company"),
            "result": row.get("result"),
            "resolved_identity": row.get("resolved_identity"),
            "business_model": row.get("business_model"),
            "profile_source": row.get("profile_source"),
            "specificity": row.get("specificity"),
            "customer_job": tel.get("customer_job", "")[:200],
            "strategic_assets": tel.get("strategic_assets", []),
            "critical_dependencies": tel.get("critical_dependencies", []),
            "primary_lens": row.get("primary_lens"),
            "primary_lens_name": tel.get("primary_lens_name"),
            "secondary_lenses": row.get("secondary_lenses"),
            "lens_confidence": row.get("lens_confidence"),
            "why_lens_selected": tel.get("lens_selection_reasons", ""),
            "lens_refusals": tel.get("lens_refusals", [])[:3],
            "decision_opportunities": row.get("decision_opportunity_count"),
            "top_decision_domain": row.get("top_decision_domain"),
            "top_decision_priority": row.get("top_decision_priority"),
            "top_decision_components": tel.get("top_decision_components", {}),
            "causal_chain_nodes": row.get("causal_chain_nodes"),
            "causal_evidence_coverage": row.get("causal_evidence_coverage"),
            "genericity_flags": row.get("genericity_flags"),
            "differentiation_carried_by": tel.get(
                "differentiation_carried_by", []),
            "counterevidence": tel.get("counterevidence_present"),
            "information_priority": tel.get("information_priority", "")[:200],
            "abstention_reason": row.get("abstention_reason", "")[:300],
            "qa_ok": row.get("qa_ok"),
            "qa_company_specific": row.get("qa_company_specific"),
            "followup_pass": row.get("followup_pass"),
            "ceo_status": row.get("role_ceo_status"),
            "strategy_status": row.get("role_cso_status"),
            "role_views_differ": row.get("role_views_differ"),
            "role_facts_identical": row.get("role_facts_identical"),
            "core_s": row.get("core_s"),
            "leaks": row.get("leaks", []),
            "defects": row.get("defects", []),
            "gates": g,
        })

    cores = [r["core_s"] for r in scored if r.get("core_s")]
    lenses = [r["primary_lens"] for r in scored if r.get("primary_lens")]
    out = {
        "live_commit": raw.get("live_commit"),
        "base": raw.get("base"),
        "companies": len(scored),
        "distinct_primary_lenses": len(set(lenses)),
        "gate_tallies": tallies,
        "core_p50_s": round(statistics.median(cores), 1) if cores else None,
        "core_max_s": max(cores) if cores else None,
        "total_product_defects": sum(
            1 for r in scored for d in r["defects"]
            if d.get("kind") == "PRODUCT_DEFECT"),
        "total_leaks": sum(len(r["leaks"]) for r in scored),
        "rows": scored,
    }
    (ROOT / a.out).write_text(json.dumps(out, indent=2))
    print(f"{len(scored)} companies, {out['distinct_primary_lenses']} distinct "
          f"lenses")
    for name, bucket in tallies.items():
        total = sum(bucket.values())
        print(f"  {name:24s} {bucket['PASS']}/{total} pass"
              + (f"  ({bucket['ABSTAIN']} defensible abstention)"
                 if bucket["ABSTAIN"] else "")
              + (f"  ({bucket['FAIL']} FAIL)" if bucket["FAIL"] else ""))
    print(f"written {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
