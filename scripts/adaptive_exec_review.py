#!/usr/bin/env python3
"""Pre-derive the CHECKABLE half of the 20-point executive review.

Ten companies times twenty questions is two hundred judgements, and roughly
half of them are not judgements at all -- "is the company name on the page",
"is contrary evidence present", "did the follow-up retain context" are facts
the run already recorded. Deriving those leaves attention for the ones that
actually need a reader: is the lens DEFENSIBLE, is the domain USEFUL, would
this be SAFE to show the company's executive.

Every derived answer names the field it came from, so a reader can disagree
with the instrument rather than with an unattributed verdict. The subjective
rows are emitted as TODO and are filled in by reading the page.
"""
from __future__ import annotations

import argparse
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEN = ["Highspot", "BigID", "Cyera", "Monte Carlo Data", "Veeam", "Druva",
       "Slalom", "Sigma Computing", "ZoomInfo", "Point B"]

DERIVED = [
    ("1. Correct company?",
     lambda r: r.get("identity_on_page") and bool(r.get("resolved_identity")),
     "identity_on_page + resolved_identity"),
    ("2. Understands the business?",
     lambda r: r.get("business_model") not in ("", "UNKNOWN", None),
     "business_model"),
    # POPULATED, OR HONESTLY BOUNDED. The preregistration is explicit that an
    # unsupported field must not be REQUIRED to contain text -- only that its
    # absence is stated rather than hidden. A field the run could not
    # establish, and which says so with a provenance of NOT_ESTABLISHED, is
    # the profile behaving correctly; scoring it NO would grade the product
    # for the thinness of a company's public record.
    ("3. Correct customer job (or bounded)?",
     lambda r: bool((r.get("telemetry") or {}).get("customer_job"))
     or (r.get("telemetry") or {}).get("customer_job_provenance")
     == "NOT_ESTABLISHED",
     "telemetry.customer_job | customer_job_provenance"),
    ("4. Strategic asset plausible (or bounded)?",
     lambda r: bool((r.get("telemetry") or {}).get("strategic_assets"))
     or bool(r.get("evidence_limitation")),
     "telemetry.strategic_assets | evidence_limitation"),
    ("6. Why-this-company materially unique?",
     lambda r: r.get("has_why_different")
     and bool((r.get("telemetry") or {}).get("differentiation_carried_by")),
     "has_why_different + differentiation_carried_by"),
    ("7. Decision / potential domain present?",
     lambda r: bool(r.get("decision_opportunity_count"))
     or bool(r.get("potential_domains")),
     "decision_opportunity_count | potential_domains"),
    ("8. Causal or investigation chain present?",
     lambda r: r.get("has_causal_chain") or r.get("has_investigation_chain"),
     "has_causal_chain | has_investigation_chain"),
    ("9. Evidence clean?",
     lambda r: not r.get("broken_quotes") and r.get("quote_count", 0) > 0,
     "quote_count + broken_quotes"),
    ("10. Counterevidence or limitation visible?",
     lambda r: bool((r.get("telemetry") or {}).get("counterevidence_present"))
     or bool(r.get("evidence_limitation")),
     "counterevidence_present | evidence_limitation"),
    ("12. What-would-change-view present?",
     lambda r: bool(r.get("what_would_unlock"))
     or bool((r.get("telemetry") or {}).get("information_priority")),
     "what_would_unlock | information_priority"),
    ("13. Information priority present?",
     lambda r: bool((r.get("telemetry") or {}).get("information_priority"))
     or bool(r.get("what_would_unlock")),
     "information_priority | what_would_unlock"),
    ("14. CEO view renders?",
     lambda r: r.get("role_ceo_status") == 200, "role_ceo_status"),
    ("15. Strategy view renders?",
     lambda r: r.get("role_cso_status") == 200
     and r.get("role_views_differ") and r.get("role_facts_identical"),
     "role_cso_status + role_views_differ + role_facts_identical"),
    ("16. Q&A company-specific?",
     lambda r: r.get("qa_company_specific", 0) >= 5, "qa_company_specific"),
    ("17. Follow-up context retained?",
     lambda r: bool(r.get("followup_pass")), "followup_pass"),
    ("18. Uncertainty honest?",
     lambda r: bool(r.get("evidence_limitation"))
     or bool((r.get("telemetry") or {}).get("counterevidence_present")),
     "evidence_limitation | counterevidence_present"),
    ("19. UI executive-quality (no leaks, terminal)?",
     lambda r: not r.get("leaks") and not r.get("headline_is_generic"),
     "leaks + headline_is_generic"),
    ("20. Safe to show the real executive?",
     lambda r: not [d for d in (r.get("defects") or ())
                    if d.get("kind") == "PRODUCT_DEFECT"],
     "no PRODUCT_DEFECT on the page"),
]

SUBJECTIVE = ["5. Lens defensible?",
              "11. \"So what?\" useful?"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", default="reports/adaptive_ten_matrix.json")
    ap.add_argument("--out", default="reports/exec_review_derived.json")
    a = ap.parse_args()
    raw = json.loads((ROOT / a.matrix).read_text())
    rows = {r["company"]: r for r in raw.get("rows", [])}

    out = {}
    for name in TEN:
        r = rows.get(name)
        if r is None:
            continue
        scored, no_reasons = {}, []
        for label, fn, field in DERIVED:
            try:
                ok = bool(fn(r))
            except Exception:                                # noqa: BLE001
                ok = False
            scored[label] = 1 if ok else 0
            if not ok:
                no_reasons.append(f"{label} -> NO (from {field})")
        for label in SUBJECTIVE:
            scored[label] = None
        out[name] = {"derived": scored,
                     "derived_yes": sum(v for v in scored.values() if v),
                     "derived_total": len(DERIVED),
                     "needs_reading": SUBJECTIVE,
                     "no_reasons": no_reasons}
        print(f"{name:18s} {out[name]['derived_yes']:2d}/{len(DERIVED)} derived"
              + (f"   NO: {len(no_reasons)}" if no_reasons else ""))
        for reason in no_reasons:
            print(f"      {reason}")
    (ROOT / a.out).write_text(json.dumps(out, indent=2))
    print(f"\nwritten {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
