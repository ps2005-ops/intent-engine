"""Generate src/intent_engine/company_ingestion/catalog_prospects98.py from the
verified IDENTITY_REGISTRY.json and the attested source discovery.

Identity and the company's own publishing surface only, never analysis.
Former SEC filers carry NO sec_cik here: a CIK opens that registrant's whole
filing series, and Domo's former CIK now files as Huckleberry.ai (a shell), so
a former filer's history needs a bounded relationship, not a bare CIK.
"""
from __future__ import annotations
import json, pathlib, pprint, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/prospect100"))
from gen_catalog import _keep, _KIND, _AUTH  # noqa: E402

OUT = ROOT / "src/intent_engine/company_ingestion/catalog_prospects98.py"
CORP = {"ACQUIRED_OPERATING", "TAKEN_PRIVATE", "ACQUIRED_ABSORBED", "CEASED_OPERATING", "RENAMED_SUCCESSOR"}
#: Analysis targets whose catalog status is NOT the registry state: SAFE is the
#: acquirer that operates RiskLens's business (the absorbed brand is an alias);
#: Fiddler's sale is signed, not closed, so it is still independent.
STATUS_OVERRIDE = {48: None, 16: None}
IDS = {59: "cfo-ai", 48: "safe-security", 40: "zip-procurement", 13: "writer-ai", 95: "launch-consulting",
       94: "improving", 96: "sparq", 2: "domo", 63: "chargebee", 62: "maxio"}
GROUPS = {13: "writer", 40: "zip", 48: "safe", 59: "runway", 92: "insight", 57: "insight", 95: "launch"}
PARENT = {72: "coupa"}


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main():
    reg = json.loads((ROOT / "docs/engineering/prospect98/IDENTITY_REGISTRY.json").read_text())["companies"]
    found = {}
    for f in ("source_discovery.json", "source_discovery_retry.json"):
        for r in json.loads((ROOT / "reports/prospect98/identity" / f).read_text()):
            if r.get("accepted"):
                found[r["prospect_id"]] = r
    sys.path.insert(0, str(ROOT / "src"))
    from intent_engine.company_ingestion.catalog import CATALOG_REGISTRY
    from intent_engine.company_ingestion.catalog_prospects98 import PROSPECT98_CATALOG as _OWN
    taken = {p.entity_id for p in CATALOG_REGISTRY} - {r["entity_id"] for r in _OWN}
    blocks, ids = [], set()
    for c in reg:
        p = c["position"]
        eid = IDS.get(p) or _slug(c["analysis_target"])
        assert eid not in taken and eid not in ids, (p, eid)
        ids.add(eid)
        st = c["ownership"]
        status = None
        if st["state"] in CORP and STATUS_OVERRIDE.get(p, "keep") == "keep":
            status = {"state": st["state"], "effective": st["effective"], "counterparty": st["counterparty"],
                      "summary": st["summary"], "evidence": tuple(st["evidence"])}
        notes = "; ".join([x for x in [c["notes"]] + c["collision_risks"] if x])
        if p == 16:
            notes = (st["summary"] + "; " + notes).strip("; ")
        L = ["    {", f'        "entity_id": {eid!r},', f'        "legal_name": {c["legal_name"]!r},',
             f'        "common_name": {c["analysis_target"]!r},', f'        "country": {c["hq_country"]!r},',
             f'        "primary_domain": {c["primary_domain"]!r},', f'        "aliases": {tuple(c["aliases"])!r},',
             f'        "prospect98_position": {p!r},']
        if c.get("business_model") and c["business_model"]["basis"]:
            L.append(f'        "business_model_class": {c["business_model"]["class"]!r},')
            L.append(f'        "business_model_basis": {c["business_model"]["basis"]!r},')
        H = c["headquarters"]
        L.append(f'        "hq_status": {H["status"]!r},')
        if H["note"]:
            L.append(f'        "hq_note": {H["note"]!r},')
        if H["sources"]:
            L.append(f'        "hq_sources": {tuple(tuple(x) for x in H["sources"])!r},')
        if H["regional"]:
            L.append(f'        "regional_hq": {tuple(tuple(x) for x in H["regional"])!r},')
        if H["legal_domicile"]:
            L.append(f'        "legal_domicile": {H["legal_domicile"]!r},')
        if c.get("public_listing"):
            pl = c["public_listing"]
            L += [f'        "listings": (({pl["exchange"]!r}, {pl["ticker"]!r}),),',
                  f'        "sec_cik": {pl["cik"]!r},',
                  '        "sec_relationship": "US domestic filer: Form 10-K annual, 10-Q quarterly.",']
        if p in PARENT:
            L.append(f'        "parent_entity_id": {PARENT[p]!r},')
        if p in GROUPS:
            L.append(f'        "disambiguation_group": {GROUPS[p]!r},')
        if c["site_access"] != "readable by safe_fetch":
            L.append(f'        "retrieval_note": {c["site_access"]!r},')
        if notes:
            L.append(f'        "ambiguity_notes": {notes!r},')
        if status:
            body = pprint.pformat(status, width=70, sort_dicts=False).replace("\n", "\n        ")
            L.append(f'        "corporate_status": {body},')
        srcs = [s for s in (found.get(p) or {}).get("accepted", []) if _keep(s)]
        if srcs:
            L.append('        "sources": (')
            for s in srcs:
                L.append(f'            ({s["url"]!r}, {_KIND[s["kind"]]}, {s["label"]!r}, {_AUTH[s["kind"]]}),')
            L.append("        ),")
        L.append("    },")
        blocks.append("\n".join(L))
    header = '''"""Catalog rows for the 98-company prospect universe (prospect-98). GENERATED --
edit docs/engineering/prospect98/IDENTITY_REGISTRY.json (via
scripts/prospect98/identity_registry.py) and re-run scripts/prospect98/gen_catalog98.py.

Same contract as `catalog.CATALOG`: IDENTITY and the company's own publishing
surface only, never analysis. Every source URL was fetched through `safe_fetch`
on 2026-11-28, came from a link on the company's own homepage, answered 200 on
the same host, and returned a body distinct from the homepage. A company with
no sources refuses automated readers (see `retrieval_note`); that is not a
claim that it publishes nothing. Former SEC filers carry no `sec_cik`: a bare
CIK opens the registrant's whole series, and a former registrant may now be a
different business (Domo's CIK files as Huckleberry.ai).
"""
from __future__ import annotations

_CORPORATE = "corporate"
_SEGMENT = "segment"
_CUSTOMERS = "customers"
_NEWSROOM = "newsroom"
_PRICING = "pricing"
_P = "official_primary"
_S = "official_secondary"

PROSPECT98_CATALOG_VERSION = "prospect98.v1"

PROSPECT98_CATALOG = (
'''
    OUT.write_text(header + "\n".join(blocks) + "\n)\n")
    print(f"wrote {len(blocks)} rows to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
