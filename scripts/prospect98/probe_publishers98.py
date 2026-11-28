"""Category-specific publisher candidates for prospect-98, probed with the
channel's OWN admission rule (independent_reporting.probe_publisher): robots
allows the feed path for our user agent AND the feed parses with items.

Samples are DEVELOPMENT companies only (never validation or untouched).
Excluded on principle, not probed: FinSMEs and AIthority (funding/press-release
rewrites: the company speaking), Security Boulevard (syndicates vendor blogs:
company-authored), Unite.AI (vendor interviews).

  PYTHONPATH=src python scripts/prospect98/probe_publishers98.py OUT.json
"""
from __future__ import annotations
import json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "scripts/prospect100/resume"))
import probe_publishers as PP  # noqa: E402

T, S = "/tag/{slug}/feed/", "/?s={q}&feed=rss2"
PP.CANDIDATES = (
    # C1 data infrastructure / AI
    ("BigDATAwire", "www.bigdatawire.com", T, S, ("ClickHouse", "Pinecone", "Alteryx")),
    ("DevOps.com", "devops.com", T, S, ("ClickHouse", "Pinecone", "Labelbox")),
    ("SD Times", "sdtimes.com", T, S, ("Pendo", "Fullstory", "ClickHouse")),
    ("Solutions Review", "solutionsreview.com", T, S, ("Alteryx", "Domo", "Glean")),
    ("GeekWire", "www.geekwire.com", T, S, ("Pinecone", "Glean", "Writer")),
    # C2 procurement / supply chain / risk
    ("Spend Matters", "spendmatters.com", T, S, ("Coupa", "GEP", "Fairmarkit")),
    ("Logistics Viewpoints", "logisticsviewpoints.com", T, S, ("ToolsGroup", "Netstock", "Coupa")),
    ("PYMNTS", "www.pymnts.com", T, S, ("Coupa", "Zip", "Maxio")),
    ("Compliance Week", "www.complianceweek.com", T, S, ("NAVEX", "Riskonnect", "Avetta")),
    # C3 finance operations / automation
    ("Enterprise Times", "www.enterprisetimes.co.uk", T, S, ("Prophix", "Deltek", "Aptean")),
    ("CFO Dive", "www.cfodive.com", "", S, ("Prophix", "Drivetrain", "Abacum")),
    # C4 security / IT services
    ("CyberScoop", "cyberscoop.com", T, S, ("SentinelOne", "Wiz", "Claroty")),
    ("The Record", "therecord.media", T, S, ("SentinelOne", "Censys", "Forescout")),
    ("MSSP Alert", "www.msspalert.com", T, S, ("SecurityScorecard", "BitSight", "Corelight")),
    ("Channel E2E", "www.channele2e.com", T, S, ("SHI International", "SoftServe", "Bounteous")),
)

if __name__ == "__main__":
    raise SystemExit(PP.main())
