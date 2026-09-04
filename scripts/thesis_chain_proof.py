"""The repaired path, end to end, on the ORDINARY entry: a website and a name.

WHAT THIS PROVES THAT THE SUITE CANNOT. The unit tests hand `profile_for` an
SEC industry code directly. Production has to GO AND GET one, and the defect
was entirely in the going: a run started from a domain carries no
`meta["cik"]`, so nothing was ever fetched and every company reached the
pattern gate as UNKNOWN.

So this starts a run the way a customer does -- name plus website, no CIK --
and prints the whole chain:

    canonical name -> subject CIK -> registrant -> business model
                   -> eligible patterns -> excluded patterns

Run it against the network. It is a proof, not a test.
"""
from __future__ import annotations

import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.company_ingestion.service import (      # noqa: E402
    CompanyIngestionService, _business_model_of, _patterns_for_company,
)
from intent_engine.strategic_intelligence.patterns import (  # noqa: E402
    PATTERN_LIBRARY,
)

AS_OF = "2026-09-04T00:00:00+00:00"
CAPACITY = "capacity_ahead_of_demand"

#: THE CANONICAL NAMES THE PRODUCT ITSELF SUBMITS, not display names.
#:
#: `company_suggest.v1` binds the chosen row's `legal_name` into the analyse
#: form, and that is the string every downstream producer sees. Proving this
#: chain on a display name measures a string no run ever carries: "Lowe's
#: Companies" tokenises to {lowe, s, companies} and matches no registrant,
#: while the name the product actually submits -- "Lowes Companies Inc" --
#: resolves to CIK 60667. Reading the deployed suggest contract for these was
#: the difference between a residual UNKNOWN and a proof.
SUBJECTS = [
    ("Synopsys Inc", "synopsys.com"),
    ("Emerson Electric Co", "emerson.com"),
    ("Lowes Companies Inc", "lowes.com"),
    ("BlackRock, Inc.", "blackrock.com"),
    ("Slb Limited", "slb.com"),
]


def chain(ci, name, domain) -> dict:
    run = ci.create_run(company_name=name, website=f"https://{domain}",
                        user_id="proof", as_of=AS_OF)
    rid = run["run_id"]
    meta = ci.run_meta(rid) or {}
    recorded = str(meta.get("cik") or "")
    subject = ci.subject_cik(meta)
    cls = ci.classification_inputs(rid, name, documents=[])
    registrant = cls.get("registrant") or {}
    # `_business_model_of` answers "" for a company it cannot classify; the
    # gate calls that UNKNOWN, and the two must not be printed differently.
    model = _business_model_of(name, domain=domain, registrant=registrant,
                               evidence_text=cls.get("evidence_text")
                               or "") or "UNKNOWN"
    eligible = [p.pattern_id for p in _patterns_for_company(
        name, domain=domain, registrant=registrant,
        evidence_text=cls.get("evidence_text") or "")]
    excluded = sorted({p.pattern_id for p in PATTERN_LIBRARY} - set(eligible))
    return {"company": name, "meta_cik": recorded, "subject_cik": subject,
            "registrant": registrant.get("sic") or "", "model": model,
            "eligible": eligible, "excluded": excluded,
            "capacity_offered": CAPACITY in eligible}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        ci = CompanyIngestionService(pathlib.Path(tmp) / "ci.jsonl")
        rows = [chain(ci, name, domain) for name, domain in SUBJECTS]
    print(f"{'COMPANY':<22}{'meta.cik':>9}{'subject':>9}{'SIC':>7}  "
          f"{'BUSINESS MODEL':<26}{'elig':>5}{'excl':>5}  capacity")
    for r in rows:
        print(f"{r['company']:<22}{r['meta_cik'] or '--':>9}"
              f"{r['subject_cik'] or '--':>9}{str(r['registrant']) or '--':>7}  "
              f"{r['model']:<26}{len(r['eligible']):>5}"
              f"{len(r['excluded']):>5}  "
              f"{'OFFERED' if r['capacity_offered'] else 'REFUSED'}")
    print()
    for r in rows:
        print(f"{r['company']}: excluded = {', '.join(r['excluded']) or '(none)'}")
    unknown = [r["company"] for r in rows if r["model"] == "UNKNOWN"]
    print(f"\nUNKNOWN: {len(unknown)}/{len(rows)}"
          + (f" -- {unknown}" if unknown else ""))
    return 0 if not unknown else 1


if __name__ == "__main__":
    raise SystemExit(main())
