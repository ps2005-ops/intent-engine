"""Generate company_ingestion/catalog_prospects.py from the reviewed identity
table and the attested-source discovery runs.

The generated module is static data, reviewed in the diff like any catalog
edit. Nothing reads discovery JSON at import time.

Usage:
  PYTHONPATH=src python scripts/prospect100/gen_catalog.py \
      --discovery docs/engineering/prospect100/source_discovery.json \
      [--discovery more.json ...] --out src/intent_engine/company_ingestion/catalog_prospects.py
"""
from __future__ import annotations

import argparse
import json
import pprint
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
import identity_table as T  # noqa: E402

_KIND = {"corporate": "_CORPORATE", "segment": "_SEGMENT",
         "customers": "_CUSTOMERS", "newsroom": "_NEWSROOM",
         "pricing": "_PRICING"}
_AUTH = {"corporate": "_P", "segment": "_P", "pricing": "_P",
         "customers": "_S", "newsroom": "_S"}


def _keep(src: dict) -> bool:
    path = urlparse(src["url"]).path.strip("/").split("/")
    # A single customer's story is not the customers page; one named customer
    # would read as the company's whole customer base.
    if src["kind"] == "customers" and len(path) == 2:
        return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--discovery", action="append", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    found: dict = {}
    for path in args.discovery:                 # later files override earlier
        for row in json.load(open(path)):
            found[(row["prospect_id"], row.get("host", ""))] = row

    def sources_for(pid, host):
        row = found.get((pid if pid is not None else -1, host))
        if row is None:
            row = next((r for (p, h), r in found.items() if h == host), None)
        out = []
        for s in (row or {}).get("accepted", []):
            if _keep(s):
                out.append((s["url"], s["kind"], s["label"]))
        return out

    blocks = []
    for r in T.ROWS + T.SIBLINGS:
        srcs = sources_for(r["pid"], r["host"]) if r["host"] else []
        lines = ["    {",
                 f'        "entity_id": {r["id"]!r},',
                 f'        "legal_name": {r["legal"]!r},',
                 f'        "common_name": {r["common"]!r},',
                 f'        "country": {r["country"]!r},',
                 f'        "primary_domain": {r["domain"]!r},',
                 f'        "aliases": {tuple(r["aliases"])!r},']
        if r.get("pid") is not None:
            lines.append(f'        "prospect_id": {r["pid"]!r},')
        if r.get("listings"):
            lines.append(f'        "listings": {tuple(r["listings"])!r},')
        if r.get("cik"):
            lines.append(f'        "sec_cik": {r["cik"]!r},')
        if r.get("parent"):
            lines.append(f'        "parent_entity_id": {r["parent"]!r},')
        if r.get("group"):
            lines.append(f'        "disambiguation_group": {r["group"]!r},')
        if r.get("refused"):
            lines.append(f'        "retrieval_note": {r["refused"]!r},')
        if r.get("note"):
            lines.append(f'        "ambiguity_notes": {r["note"]!r},')
        if r.get("status"):
            body = pprint.pformat(r["status"], width=70, sort_dicts=False)
            body = body.replace("\n", "\n        ")
            lines.append(f'        "corporate_status": {body},')
        if srcs:
            lines.append('        "sources": (')
            for url, kind, label in srcs:
                lines.append(f'            ({url!r}, {_KIND[kind]}, '
                             f'{label!r}, {_AUTH[kind]}),')
            lines.append("        ),")
        lines.append("    },")
        blocks.append("\n".join(lines))

    header = f'''"""Catalog rows for the 100-company prospect universe. GENERATED -- edit
scripts/prospect100/identity_table.py and re-run gen_catalog.py.

Same contract as `catalog.CATALOG`: IDENTITY and the company's own publishing
surface only, never analysis. Every source URL below was fetched through
`safe_fetch` at the live-run byte budget on 2026-11-09, came from a link on
the company's own homepage, answered 200 on the same host, and returned a body
distinct from the homepage (an SPA answers every path with its shell).

A company with NO sources is either one whose site refuses automated readers
(403/429/too large) or one that no longer publishes as itself -- see its
`corporate_status`. Neither is a claim that the company publishes nothing.

Evidence for every ownership change is the URL in `corporate_status`. Full
provenance: docs/engineering/prospect100/PROSPECT_REGISTRY.yaml.
"""
from __future__ import annotations

_CORPORATE = "corporate"
_SEGMENT = "segment"
_CUSTOMERS = "customers"
_NEWSROOM = "newsroom"
_PRICING = "pricing"
_P = "official_primary"
_S = "official_secondary"

PROSPECT_CATALOG_VERSION = "prospect100.v1"

PROSPECT_CATALOG = (
'''
    Path(args.out).write_text(header + "\n".join(blocks) + "\n)\n")
    print(f"wrote {len(blocks)} rows to {args.out}")


if __name__ == "__main__":
    main()
