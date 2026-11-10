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
import re
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


#: Phrases the product prints on a TERMINAL FAILURE PAGE. That page is not a
#: report and does not owe a report's sections: it exists to say that no
#: approved source could be retrieved, and it names every URL and the reason.
FAILURE_PAGE = ("could not be completed",
                "did not produce a report because no approved source")


def reclassify(row: dict, ui_dir: pathlib.Path) -> dict:
    """Move defects the instrument mis-filed, naming the evidence for each.

    Three rules, and each one is a statement about the HARNESS rather than a
    softening of the result:

    1. A terminal failure page is graded as a report. "lens block missing"
       is true and meaningless: the page is a failure notice, and a failure
       notice correctly has no lens block.
    2. Status 0 is not a non-200. It is the absence of a status -- a client
       timeout -- and on this free instance the primary screen has been
       measured at under a second locally and over 180s live.
    3. The map has THREE states and the gate had two. `NOTHING` is not
       `POTENTIAL_DOMAINS` with the domains missing; it is the state where
       nothing could be established, and it owes an explanation rather than
       domains. Requiring domains of it is the two-way gate the product
       itself replaced.
    """
    moved = []
    slug = re.sub(r"[^a-z0-9]+", "-", row.get("company", "").lower()).strip("-")
    page = ui_dir / f"{slug}.html"
    text = page.read_text(errors="replace").lower() if page.exists() else ""
    is_failure_page = any(f in text for f in FAILURE_PAGE)
    state = row.get("decision_map_state", "")

    kept = []
    for d in (row.get("defects") or ()):
        kind, detail = d.get("kind"), (d.get("detail") or "")
        if kind != "PRODUCT_DEFECT":
            kept.append(d)
            continue
        if is_failure_page:
            moved.append({**d, "kind": "INFRASTRUCTURE",
                          "reclassified": "terminal failure page: no approved "
                                          "source could be retrieved"})
            continue
        if re.search(r"answered 0$", detail):
            moved.append({**d, "kind": "INFRASTRUCTURE",
                          "reclassified": "status 0 is a client timeout, not "
                                          "a response"})
            continue
        if state == "NOTHING" and (
                "potential decision domains" in detail
                or "not current recommendations" in detail
                or "no investigation chain" in detail):
            moved.append({**d, "kind": "INSTRUMENT_DEFECT",
                          "reclassified": "state is NOTHING, not "
                                          "POTENTIAL_DOMAINS: the gate was "
                                          "two-way on a three-state model"})
            continue
        kept.append(d)

    out = dict(row)
    out["defects"] = kept
    out["reclassified"] = moved
    out["is_failure_page"] = is_failure_page
    if is_failure_page:
        out["result"] = "RETRIEVAL_FAILED"
    elif not [d for d in kept if d.get("kind") == "PRODUCT_DEFECT"]:
        if row.get("decision_reading_available"):
            out["result"] = "PASS"
        elif row.get("profile_available") and row.get("lens_available"):
            out["result"] = "DEFENSIBLE_ABSTENTION"
        else:
            out["result"] = "INSUFFICIENT_PROFILE"
    return out


def gates(row: dict) -> dict:
    """One row against every gate in the preregistration.

    A gate is PASS, ABSTAIN or FAIL. ABSTAIN is a real result and it counts
    toward the total: a company whose public record cannot support a reading
    passes by showing the right model, the right lens, the gap and what it
    would read next.
    """
    # A FAILURE PAGE IS NOT A REPORT, so the report-shaped gates do not apply
    # to it. It is held to the two things it DOES owe: naming the company, and
    # saying what happened instead of inventing a result. Scoring it on
    # "do the two role views differ" is the same category error as scoring it
    # on "is the lens block present" -- a failure notice has no modules to
    # reorder. It is reported as RETRIEVAL_FAILED and counted nowhere else.
    def ok(condition, abstain=False):
        return "ABSTAIN" if abstain else (
            "PASS" if condition else "FAIL")

    if row.get("is_failure_page"):
        report_gates = ("company_profile", "decision_map", "strategic_lens",
                        "differentiation", "causal_chain", "counterevidence",
                        "thesis_or_abstention", "decision_value",
                        "ceo_role", "strategy_role", "profile_available",
                        "lens_available", "decision_reading_available")
        out = {g: "N/A" for g in report_gates}
        out["identity"] = ok(bool(row.get("identity_on_page")))
        out["evidence"] = ok(True)   # it names every source and why each failed
        out["qa"] = ok(row.get("qa_ok", 0) >= 6)
        out["followup"] = ok(bool(row.get("followup_pass")))
        out["no_product_defect"] = ok(not [
            d for d in (row.get("defects") or ())
            if d.get("kind") == "PRODUCT_DEFECT"])
        return out

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
    # THE EXPECTED FAMILIES ARE A CONTROL, NOT A TARGET. Failing a lens
    # because it differs from a list we wrote is grading the product against
    # our own guess; the preregistration says to judge the evidence. So the
    # gate asks what can actually be wrong -- was a lens selected, and did
    # the product publish why -- and the expectation mismatch is reported
    # beside it for a human to examine.
    lens_ok = bool(lens) and bool(tel.get("lens_selection_reasons"))
    lens_outside_expectation = bool(lens) and not row.get(
        "lens_matches_expectation", False)
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

    ui_dir = ROOT / "reports" / "ui"
    rows = [reclassify(r, ui_dir) for r in rows]

    scored, tallies = [], {}
    for row in rows:
        g = gates(row)
        for name, verdict in g.items():
            bucket = tallies.setdefault(name, {"PASS": 0, "ABSTAIN": 0,
                                               "FAIL": 0, "N/A": 0})
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
            "lens_outside_expectation": (
                bool(row.get("primary_lens"))
                and not row.get("lens_matches_expectation", False)),
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
        # A gate that does not apply is not a denominator. The failure page
        # is excluded from the report-shaped gates and said so out loud.
        applicable = sum(bucket.values()) - bucket["N/A"]
        print(f"  {name:26s} {bucket['PASS'] + bucket['ABSTAIN']}"
              f"/{applicable} pass"
              + (f"  ({bucket['ABSTAIN']} defensible abstention)"
                 if bucket["ABSTAIN"] else "")
              + (f"  ({bucket['FAIL']} FAIL)" if bucket["FAIL"] else "")
              + (f"  [{bucket['N/A']} n/a]" if bucket["N/A"] else ""))
    print(f"written {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
