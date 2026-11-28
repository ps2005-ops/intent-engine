"""Verified identity for the 98 positions. Writes docs/engineering/prospect98/IDENTITY_REGISTRY.json.

Every row was checked 2026-11-28:
  * domain: fetched through the product's own safe_fetch
    (reports/prospect98/identity/domain_verification*.json); the title and text
    head name the company, or the row says the site refused the fetcher;
  * SEC identity: sec.gov company_tickers.json (current filers) and
    data.sec.gov submissions (former filers: 25-NSE / 15-12G dates);
  * ownership change: cited by URL in `status.evidence` (acquirer, target or
    regulator announcement first; trade press only as corroboration).

hq_country is EMPTY where it could not be stated with confidence (a wrong
country renders a falsehood under the company's name). An ownership state with
no deal found in the 2026-11-28 sweep is recorded as such, never as a proof
that no deal exists.

Position, category and the as-listed name are copied from UNIVERSE_AS_LISTED.tsv
and never edited; the analysis target is a separate field.
"""
from __future__ import annotations
import csv, hashlib, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
D = ROOT / "docs/engineering/prospect98"
US, UK, CA, NL, ZA = "United States", "United Kingdom", "Canada", "Netherlands", "South Africa"

def S(state, effective, counterparty, summary, evidence, cik=""):
    return {"state": state, "effective": effective, "counterparty": counterparty,
            "counterparty_cik": cik, "summary": summary, "evidence": list(evidence)}

NOTFOUND = "no ownership change found in the 2026-11-28 search sweep"
# pos: (target, legal, domain, hq, aliases, extra)
R = {
 1: ("Alteryx", "Alteryx, Inc.", "alteryx.com", US, ["alteryx"], dict(former={"cik": "1689923", "until": "2024-03-19"},
     status=S("TAKEN_PRIVATE", "2024-03-19", "Clearlake Capital Group and Insight Partners", "Taken private for about $4.4B; Nasdaq delisting (25-NSE) 2024-03-19",
     ["https://clearlake.com/wp-content/uploads/2024/03/04_Hideaway-Closing_Press-Release_v20240318_2-1.pdf"]),
     collisions=["Insight Partners (co-owner) is not Insight Enterprises (#92) nor insightsoftware (#57)"])),
 2: ("Domo", "Domo", "domo.com", US, ["domo", "domo inc"], dict(
     former={"cik": "1505952", "until": "2026-09", "now_named": "Huckleberry.ai, Inc. (HUCK)"},
     status=S("ACQUIRED_OPERATING", "2026-09", "Progress Software Corporation", "Progress bought substantially all Domo assets and employees for $400M (announced 2026-07-22); the listed shell kept the NOLs and is now Huckleberry.ai, Inc.",
     ["https://www.businesswire.com/news/home/20260722324001/en/", "https://www.progress.com/blogs/progress-software-acquires-domo-to-strengthen-its-ai-data-platform"], cik="876167"),
     refused="domo.com answers 405 to automated readers (2026-11-28)",
     collisions=["CIK 1505952 is now Huckleberry.ai, a shell: its filings after the asset sale are NOT Domo's",
                 "closing month from the Progress blog (updated 2026-09-22); no independent confirmation of the closing date found"])),
 3: ("StarTree", "StarTree, Inc.", "startree.ai", US, ["startree"], {}),
 4: ("ClickHouse", "ClickHouse, Inc.", "clickhouse.com", US, ["clickhouse"], {}),
 5: ("Firebolt", "Firebolt Analytics, Inc.", "firebolt.io", "", ["firebolt"], dict(collisions=["Firebolt is also a common product/brand word (e.g. Firebolt smartwatches)"])),
 6: ("MotherDuck", "MotherDuck Corporation", "motherduck.com", US, ["motherduck"], {}),
 7: ("Astronomer", "Astronomer, Inc.", "astronomer.io", US, ["astronomer", "astro"], dict(collisions=["common noun; requires the domain or 'Airflow' context"])),
 8: ("FalkorDB", "FalkorDB", "falkordb.com", "", ["falkordb"], {}),
 9: ("Pinecone", "Pinecone Systems, Inc.", "pinecone.io", US, ["pinecone", "pinecone systems"], dict(collisions=["common noun"])),
 10: ("Weaviate", "Weaviate B.V.", "weaviate.io", NL, ["weaviate", "semi technologies"], {}),
 11: ("Zilliz", "Zilliz", "zilliz.com", US, ["zilliz", "milvus"], {}),
 12: ("Glean", "Glean Technologies, Inc.", "glean.com", US, ["glean"], dict(collisions=["common verb; exposed in unseen-20"])),
 13: ("Writer", "Writer, Inc.", "writer.com", US, ["writer", "writer.com"], dict(collisions=["common noun; 'Writer' must resolve only with the domain or enterprise-AI context"])),
 14: ("C3 AI", "C3.ai, Inc.", "c3.ai", US, ["c3 ai", "c3.ai", "c3"], dict(ticker="AI", exchange="NYSE", cik="1577526",
     collisions=["ticker 'AI' is a common word"])),
 15: ("Domino Data Lab", "Domino Data Lab, Inc.", "domino.ai", US, ["domino data lab", "domino", "dominodatalab"], dict(
     collisions=["'Domino' alone collides with Domino's Pizza (DPZ) and Domino Printing; dominodatalab.com now redirects off-host (refused by safe_fetch)"])),
 16: ("Fiddler AI", "Fiddler Labs, Inc.", "fiddler.ai", US, ["fiddler", "fiddler ai", "fiddler labs"], dict(
     status=S("ACQUISITION_PENDING", "2026-11-03", "CrowdStrike Holdings, Inc.", "CrowdStrike agreed to acquire Fiddler (to become Falcon Observe); signed, not closed as of 2026-11-28",
     ["https://ir.crowdstrike.com/news-releases/news-release-details/crowdstrike-acquire-fiddler-deliver-agent-observability-ai-trust"], cik="1535527"))),
 17: ("Arthur AI", "Arthur", "arthur.ai", US, ["arthur", "arthur ai"], dict(collisions=["personal first name"])),
 18: ("Tonic.ai", "Tonic AI, Inc.", "tonic.ai", US, ["tonic", "tonic.ai", "tonic ai"], {}),
 19: ("Unstructured", "Unstructured Technologies, Inc.", "unstructured.io", US, ["unstructured", "unstructured.io"], dict(collisions=["common adjective ('unstructured data')"])),
 20: ("LandingAI", "LandingAI", "landing.ai", US, ["landingai", "landing ai", "landing.ai"], {}),
 21: ("Snorkel AI", "Snorkel AI, Inc.", "snorkel.ai", US, ["snorkel", "snorkel ai"], {}),
 22: ("Labelbox", "Labelbox, Inc.", "labelbox.com", US, ["labelbox"], {}),
 23: ("Hyperscience", "Hyperscience", "hyperscience.ai", US, ["hyperscience", "hyperscience.com"], dict(note="hyperscience.com redirects to hyperscience.ai")),
 24: ("Alkymi", "Alkymi, Inc.", "alkymi.io", US, ["alkymi"], {}),
 25: ("Ocrolus", "Ocrolus, Inc.", "ocrolus.com", US, ["ocrolus"], {}),
 26: ("Amplitude", "Amplitude, Inc.", "amplitude.com", US, ["amplitude", "ampl"], dict(ticker="AMPL", exchange="NASDAQ", cik="1866692", collisions=["common noun"])),
 27: ("Pendo", "Pendo.io, Inc.", "pendo.io", US, ["pendo", "pendo.io"], {}),
 28: ("Fullstory", "FullStory, Inc.", "fullstory.com", US, ["fullstory", "full story"], {}),
 29: ("Coupa", "Coupa Software Inc", "coupa.com", US, ["coupa", "coupa software"], dict(former={"cik": "1385867", "until": "2023-02-28"},
     status=S("TAKEN_PRIVATE", "2023-02-28", "Thoma Bravo", "Taken private by Thoma Bravo; Nasdaq delisting (25-NSE) 2023-02-28", ["https://data.sec.gov/submissions/CIK0001385867.json"]),
     refused="coupa.com 403 to the product's fetcher (2026-11-28)",
     collisions=["prefix 'coupa' matches Coupang, Inc. (CPNG) in the EDGAR typeahead", "acquired Tonkean (#72) in 2026: corporate-family overlap inside the universe", "exposed in unseen-20"])),
 30: ("JAGGAER", "JAGGAER, LLC", "jaggaer.com", US, ["jaggaer", "sciquest"], dict(refused="403 to the product's fetcher (2026-11-28)", note="owned by Vista Equity Partners (per Tracxn; acquirer announcement not retrieved)")),
 31: ("GEP", "GEP Worldwide", "gep.com", US, ["gep", "gep worldwide"], dict(collisions=["three-letter acronym (e.g. GE HealthCare products, Gruppo...); requires domain"])),
 32: ("Ivalua", "Ivalua", "ivalua.com", "", ["ivalua"], dict(refused="connection refused / 403 to automated readers (2026-11-28)")),
 33: ("Manhattan Associates", "Manhattan Associates, Inc.", "manh.com", US, ["manhattan associates", "manh"], dict(ticker="MANH", exchange="NASDAQ", cik="1056696",
     collisions=["'Manhattan' alone collides with Manhattan Bridge Capital and place names"])),
 34: ("ToolsGroup", "ToolsGroup", "toolsgroup.com", US, ["toolsgroup", "tools group"], {}),
 35: ("Netstock", "Netstock", "netstock.com", "", ["netstock"], {}),
 36: ("SourceDay", "SourceDay, Inc.", "sourceday.com", US, ["sourceday"], {}),
 37: ("LevaData", "LevaData, Inc.", "levadata.com", US, ["levadata"], {}),
 38: ("Arkestro", "Arkestro, Inc.", "arkestro.com", US, ["arkestro"], {}),
 39: ("Fairmarkit", "Fairmarkit, Inc.", "fairmarkit.com", US, ["fairmarkit"], {}),
 40: ("Zip", "Zip", "zip.com", US, ["zip", "ziphq", "zip hq", "zip procurement"], dict(
     note="ziphq.com redirects to zip.com (fetched 2026-11-28); company press through Jan 2026 still cites ziphq.com",
     collisions=["Zip Co Limited (ASX: ZIP, zip.co) is an unrelated BNPL lender", "zip codes, ZipRecruiter (ZIP on NYSE)", "legal entity name not confirmed from a primary source"])),
 41: ("Order.co", "Order.co", "order.co", US, ["order.co", "orderco"], dict(collisions=["'order' is a common word; requires the domain"])),
 42: ("Avetta", "Avetta, LLC", "avetta.com", US, ["avetta"], {}),
 43: ("RapidRatings", "RapidRatings International Inc.", "rapidratings.com", US, ["rapidratings", "rapid ratings"], dict(collisions=["Rapid7 (#84) shares a prefix"])),
 44: ("Fusion Risk Management", "Fusion Risk Management, Inc.", "fusionrm.com", US, ["fusion risk management", "fusion risk", "fusionrm"], dict(collisions=["'Fusion' alone is ambiguous"])),
 45: ("Riskonnect", "Riskonnect, Inc.", "riskonnect.com", US, ["riskonnect"], {}),
 46: ("MetricStream", "MetricStream, Inc.", "metricstream.com", US, ["metricstream"], {}),
 47: ("NAVEX", "NAVEX Global, Inc.", "navex.com", US, ["navex", "navex global"], {}),
 48: ("SAFE", "Safe Security, Inc.", "safe.security", US, ["safe security", "safe", "risklens", "safe one"], dict(
     status=S("ACQUIRED_ABSORBED", "2023-07-12", "Safe Security, Inc.", "Safe Security acquired RiskLens (FAIR cyber-risk quantification); RiskLens platform was to be retired into SAFE; risklens.com no longer answers the product's fetcher",
     ["https://safe.security/resources/press-release/safe-security-acquires-risklens/", "https://siliconangle.com/2023/07/13/safe-security-acquires-risklens-enhanced-risk-management/"]),
     note="analysis target is SAFE (the successor that operates RiskLens's FAIR business); RiskLens is a former brand",
     collisions=["'safe' is a common word: entry requires 'Safe Security', the domain, or 'RiskLens'"])),
 49: ("KPA", "KPA Services, LLC", "kpa.io", US, ["kpa", "kpa.io"], dict(collisions=["three-letter acronym; homepage describes EHS and automotive-dealer compliance", "legal entity name not confirmed from a primary source"])),
 50: ("RANE", "RANE", "ranenetwork.com", US, ["rane", "rane network", "ranenetwork"], dict(collisions=["RANE (Rane Corp) audio equipment; requires the domain"])),
 51: ("Eurasia Group", "Eurasia Group", "eurasiagroup.net", US, ["eurasia group"], dict(note="safe_fetch connection failure on the bare domain; www host answers 200 to curl")),
 52: ("Oxford Economics", "Oxford Economics Ltd", "oxfordeconomics.com", UK, ["oxford economics"], dict(refused="403 to the product's fetcher (2026-11-28)")),
 53: ("Gartner", "Gartner, Inc.", "gartner.com", US, ["gartner"], dict(ticker="IT", exchange="NYSE", cik="749251", refused="403 to the product's fetcher (2026-11-28)",
     collisions=["ticker 'IT' is a common word"])),
 54: ("Forrester", "Forrester Research, Inc.", "forrester.com", US, ["forrester", "forrester research"], dict(ticker="FORR", exchange="NASDAQ", cik="1023313")),
 55: ("CB Insights", "CB Insights", "cbinsights.com", US, ["cb insights", "cbinsights"], dict(collisions=["CB Insights pages about OTHER companies are third-party profiles, not their own statements"])),
 56: ("OneStream", "OneStream, Inc.", "onestream.com", US, ["onestream", "onestream software"], dict(former={"cik": "1889956", "until": "2026-04-01"},
     status=S("TAKEN_PRIVATE", "2026-04-01", "Hg", "Taken private by Hg for about $6.4B ($24.00/share); 15-12G filed 2026-04-13",
     ["https://www.onestream.com/news/onestream-announces-completion-of-acquisition-by-hg-for-usd6-4-billion/", "https://www.cfodive.com/news/onestream-closes-64b-go-private-deal-hg/816799/"]),
     collisions=["listed as public in the split prior; corrected here, split NOT recomputed"])),
 57: ("insightsoftware", "insightsoftware", "insightsoftware.com", US, ["insightsoftware", "insight software"], dict(collisions=["Insight Enterprises (#92) and Insight Partners share the stem"])),
 58: ("Prophix", "Prophix Software Inc.", "prophix.com", CA, ["prophix"], dict(refused="403 to the product's fetcher (2026-11-28)")),
 59: ("cfo.ai", "Runway Financial, Inc.", "cfo.ai", US, ["runway financial", "cfo.ai", "runway fp&a"], dict(
     status=S("RENAMED_SUCCESSOR", "2026-08", "", "Runway Financial pivoted from FP&A software and operates as cfo.ai (AI CFO 'Ari'); the runway.com domain now belongs to Runway AI, Inc. (generative video)",
     ["https://siliconangle.com/?p=837986", "https://ffnews.com/news/cfo-ai-launches-an-ai-cfo-built-for-founders-b684fc82"]),
     collisions=["runway.com = Runway AI, Inc. (video generation): fetching it analyses the WRONG company", "'runway' alone also means cash runway; never resolve the bare word",
                 "rebrand month differs between sources (Aug vs Sep 2026)"])),
 60: ("Drivetrain", "Drivetrain", "drivetrain.ai", "", ["drivetrain", "drivetrain.ai"], dict(refused="429 to the product's fetcher (2026-11-28)", collisions=["common automotive noun"])),
 61: ("Abacum", "Abacum", "abacum.ai", "", ["abacum"], {}),
 62: ("Maxio", "Maxio", "maxio.com", US, ["maxio", "saasoptics", "chargify"], dict(
     status=S("RENAMED_SUCCESSOR", "2022-04-13", "", "SaaSOptics and Chargify merged and rebranded as Maxio; saasoptics.com and chargify.com redirect to maxio.com",
     ["https://www.businesswire.com/news/home/20220413005024/en/SaaSOptics-and-Chargify-Announce-Merger-Rebrand-to-Maxio"]),
     note="Maxio, not Chargebee, is the successor of SaaSOptics and Chargify")),
 63: ("Chargebee", "Chargebee, Inc.", "chargebee.com", US, ["chargebee"], dict(
     note="As listed ('SaaSOptics / Chargify successor alternatives — Chargebee'): Chargebee is an ALTERNATIVE, not a successor. No ownership relationship to SaaSOptics, Chargify or Maxio was found; Chargebee markets itself as a Maxio alternative and migrates Chargify/SaaSOptics customers.",
     evidence=["https://www.chargebee.com/compare-competitors/chargify/"])),
 64: ("Deltek", "Deltek, Inc.", "deltek.com", US, ["deltek"], dict(note="a Roper Technologies business since 2016 (Roper ARS FY2025 lists Deltek); parent filer CIK 882835")),
 65: ("ECI Software Solutions", "ECI Software Solutions, Inc.", "ecisolutions.com", US, ["eci software solutions", "eci"], dict(collisions=["'ECI' alone collides with ECI Telecom and others"])),
 66: ("Aptean", "Aptean, Inc.", "aptean.com", US, ["aptean"], {}),
 67: ("SYSPRO", "SYSPRO", "syspro.com", ZA, ["syspro"], {}),
 68: ("Appian", "Appian Corporation", "appian.com", US, ["appian"], dict(ticker="APPN", exchange="NASDAQ", cik="1441683", collisions=["Appian Way / Appian Capital"])),
 69: ("Pegasystems", "Pegasystems Inc.", "pega.com", US, ["pegasystems", "pega"], dict(ticker="PEGA", exchange="NASDAQ", cik="1013857")),
 70: ("Celonis", "Celonis SE", "celonis.com", "Germany", ["celonis"], dict(collisions=["exposed in unseen-20"])),
 71: ("Kissflow", "Kissflow", "kissflow.com", "India", ["kissflow", "orangescape"], {}),
 72: ("Tonkean", "Tonkean, Inc.", "tonkean.com", US, ["tonkean"], dict(
     status=S("ACQUIRED_OPERATING", "2026-05-21", "Coupa Software", "Coupa acquired Tonkean (agentic intake and orchestration); tonkean.com still publishes as Tonkean",
     ["https://www.prnewswire.com/il/news-releases/coupa-acquires-tonkean-to-accelerate-agentic-intake-and-orchestration-for-global-trade-302779619.html"]),
     collisions=["parent Coupa (#29) is in the same universe"])),
 73: ("Nintex", "Nintex", "nintex.com", US, ["nintex"], {}),
 74: ("UiPath", "UiPath, Inc.", "uipath.com", US, ["uipath", "ui path"], dict(ticker="PATH", exchange="NYSE", cik="1734722", collisions=["ticker 'PATH' is a common word"])),
 75: ("Kantata", "Kantata, Inc.", "kantata.com", US, ["kantata", "mavenlink", "kimble"], dict(note="formed from Mavenlink and Kimble")),
 76: ("HighRadius", "HighRadius Corporation", "highradius.com", US, ["highradius", "high radius"], {}),
 77: ("SecurityScorecard", "SecurityScorecard, Inc.", "securityscorecard.com", US, ["securityscorecard", "security scorecard"], {}),
 78: ("BitSight", "BitSight Technologies, Inc.", "bitsight.com", US, ["bitsight"], dict(refused="403 to the product's fetcher (2026-11-28)")),
 79: ("Censys", "Censys, Inc.", "censys.com", US, ["censys"], dict(collisions=["census (spelling neighbour)"])),
 80: ("Wiz", "Wiz, Inc.", "wiz.io", US, ["wiz"], dict(
     status=S("ACQUIRED_OPERATING", "2026-03-11", "Alphabet Inc. (Google Cloud)", "Google completed its $32B acquisition; Wiz keeps its brand inside Google Cloud and stays multi-cloud",
     ["https://www.nasdaq.com/press-release/google-completes-acquisition-wiz-2026-03-11", "https://cloud.google.com/blog/products/identity-security/google-completes-acquisition-of-wiz"], cik="1652044"),
     collisions=["'wiz' is slang/common; Wizz Air; WiZ smart lighting (Signify)"])),
 81: ("Aqua Security", "Aqua Security Software Ltd.", "aquasec.com", US, ["aqua security", "aquasec", "aqua"], dict(collisions=["'Aqua' alone is ambiguous"])),
 82: ("Sysdig", "Sysdig, Inc.", "sysdig.com", US, ["sysdig"], dict(refused="safe_fetch connection failure on sysdig.com and no attested source from www.sysdig.com (2026-11-28)", note="www.sysdig.com answers 200 to curl")),
 83: ("Tenable", "Tenable Holdings, Inc.", "tenable.com", US, ["tenable"], dict(ticker="TENB", exchange="NASDAQ", cik="1660280", collisions=["common adjective"])),
 84: ("Rapid7", "Rapid7, Inc.", "rapid7.com", US, ["rapid7", "rapid 7"], dict(ticker="RPD", exchange="NASDAQ", cik="1560327")),
 85: ("SentinelOne", "SentinelOne, Inc.", "sentinelone.com", US, ["sentinelone", "sentinel one", "s1"], dict(ticker="S", exchange="NYSE", cik="1583708",
     refused="429 to the product's fetcher (2026-11-28)", collisions=["single-letter ticker 'S'", "Microsoft Sentinel"])),
 86: ("Claroty", "Claroty Ltd.", "claroty.com", US, ["claroty"], {}),
 87: ("Forescout", "Forescout Technologies, Inc.", "forescout.com", US, ["forescout"], dict(note="former SEC filer (taken private by Advent, 2020); not checked for filings")),
 88: ("Corelight", "Corelight, Inc.", "corelight.com", US, ["corelight"], {}),
 89: ("Critical Start", "Critical Start, Inc.", "criticalstart.com", US, ["critical start", "criticalstart"], {}),
 90: ("ePlus", "ePlus inc.", "eplus.com", US, ["eplus", "e plus"], dict(ticker="PLUS", exchange="NASDAQ", cik="1022408", collisions=["ticker 'PLUS' is a common word"])),
 91: ("SHI International", "SHI International Corp.", "shi.com", US, ["shi international", "shi"], dict(refused="403 to the product's fetcher (2026-11-28)", collisions=["'SHI' alone is ambiguous"])),
 92: ("Insight Enterprises", "Insight Enterprises, Inc.", "insight.com", US, ["insight enterprises", "nsit"], dict(ticker="NSIT", exchange="NASDAQ", cik="932696",
     refused="403 to the product's fetcher (2026-11-28)", collisions=["'insight' is a common word; insightsoftware (#57) and Insight Partners share the stem"])),
 93: ("Concentric AI", "Concentric AI", "concentric.ai", US, ["concentric ai", "concentric", "concentric.ai"], dict(collisions=["'Concentric' alone collides with Concentric (engineering) and others"])),
 94: ("Improving", "Improving Enterprises, Inc.", "improving.com", US, ["improving", "improving enterprises"], dict(collisions=["common verb: entry requires the domain"])),
 95: ("Launch Consulting", "Launch Consulting Group", "launchconsulting.com", US, ["launch consulting", "launch consulting group"], dict(
     collisions=["NOT 'Launch by NTT DATA' (an NTT DATA unit formed 2023 from Nexient, Postlight, Umvel and Vectorform); no NTT DATA acquisition of Launch Consulting was found", "'launch' is a common word"])),
 96: ("Sparq", "Sparq", "teamsparq.com", US, ["sparq", "teamsparq"], dict(collisions=["Spark / SPARQ (SPARQL); requires the domain"])),
 97: ("Bounteous", "Bounteous", "bounteous.com", US, ["bounteous", "bounteous x accolite", "accolite"], dict(
     status=S("RENAMED_SUCCESSOR", "2025-01-13", "", "Bounteous and Accolite merged (2024-02-01, New Mountain Capital) and operate as Bounteous since 2025",
     ["https://www.bounteous.com/insights/2024/02/01/press-release-bounteous-and-accolite-join-forces-forming-global-leader-digital/", "https://bounteous.com/insights/2025/01/13/press-release-bounteous-x-accolite-rebrand-bounteous"]))),
 98: ("SoftServe", "SoftServe, Inc.", "softserveinc.com", US, ["softserve", "soft serve"], dict(collisions=["soft-serve ice cream"])),
}

#: Business-model class from the reviewed registry, consulted by the analysis ONLY where no
#: regulator classifies the company. Basis = the company's own homepage description as fetched
#: at identity verification. Mixed or unclear businesses are deliberately absent
#: (GEP, KPA, Order.co, RANE, Oxford Economics, Critical Start, SHI).
BUSINESS_MODEL = {1: 'SUBSCRIPTION_SOFTWARE', 2: 'SUBSCRIPTION_SOFTWARE', 3: 'SUBSCRIPTION_SOFTWARE', 4: 'SUBSCRIPTION_SOFTWARE', 5: 'SUBSCRIPTION_SOFTWARE', 6: 'SUBSCRIPTION_SOFTWARE', 7: 'SUBSCRIPTION_SOFTWARE', 8: 'SUBSCRIPTION_SOFTWARE', 9: 'SUBSCRIPTION_SOFTWARE', 10: 'SUBSCRIPTION_SOFTWARE', 11: 'SUBSCRIPTION_SOFTWARE', 12: 'SUBSCRIPTION_SOFTWARE', 13: 'SUBSCRIPTION_SOFTWARE', 15: 'SUBSCRIPTION_SOFTWARE', 16: 'SUBSCRIPTION_SOFTWARE', 17: 'SUBSCRIPTION_SOFTWARE', 18: 'SUBSCRIPTION_SOFTWARE', 19: 'SUBSCRIPTION_SOFTWARE', 20: 'SUBSCRIPTION_SOFTWARE', 21: 'SUBSCRIPTION_SOFTWARE', 22: 'SUBSCRIPTION_SOFTWARE', 23: 'SUBSCRIPTION_SOFTWARE', 24: 'SUBSCRIPTION_SOFTWARE', 25: 'SUBSCRIPTION_SOFTWARE', 27: 'SUBSCRIPTION_SOFTWARE', 28: 'SUBSCRIPTION_SOFTWARE', 29: 'SUBSCRIPTION_SOFTWARE', 30: 'SUBSCRIPTION_SOFTWARE', 32: 'SUBSCRIPTION_SOFTWARE', 34: 'SUBSCRIPTION_SOFTWARE', 35: 'SUBSCRIPTION_SOFTWARE', 36: 'SUBSCRIPTION_SOFTWARE', 37: 'SUBSCRIPTION_SOFTWARE', 38: 'SUBSCRIPTION_SOFTWARE', 39: 'SUBSCRIPTION_SOFTWARE', 40: 'SUBSCRIPTION_SOFTWARE', 42: 'SUBSCRIPTION_SOFTWARE', 43: 'SUBSCRIPTION_SOFTWARE', 44: 'SUBSCRIPTION_SOFTWARE', 45: 'SUBSCRIPTION_SOFTWARE', 46: 'SUBSCRIPTION_SOFTWARE', 47: 'SUBSCRIPTION_SOFTWARE', 48: 'SUBSCRIPTION_SOFTWARE', 55: 'SUBSCRIPTION_SOFTWARE', 56: 'SUBSCRIPTION_SOFTWARE', 57: 'SUBSCRIPTION_SOFTWARE', 58: 'SUBSCRIPTION_SOFTWARE', 59: 'SUBSCRIPTION_SOFTWARE', 60: 'SUBSCRIPTION_SOFTWARE', 61: 'SUBSCRIPTION_SOFTWARE', 62: 'SUBSCRIPTION_SOFTWARE', 63: 'SUBSCRIPTION_SOFTWARE', 64: 'SUBSCRIPTION_SOFTWARE', 65: 'SUBSCRIPTION_SOFTWARE', 66: 'SUBSCRIPTION_SOFTWARE', 67: 'SUBSCRIPTION_SOFTWARE', 70: 'SUBSCRIPTION_SOFTWARE', 71: 'SUBSCRIPTION_SOFTWARE', 72: 'SUBSCRIPTION_SOFTWARE', 73: 'SUBSCRIPTION_SOFTWARE', 75: 'SUBSCRIPTION_SOFTWARE', 76: 'SUBSCRIPTION_SOFTWARE', 77: 'SUBSCRIPTION_SOFTWARE', 78: 'SUBSCRIPTION_SOFTWARE', 79: 'SUBSCRIPTION_SOFTWARE', 80: 'SUBSCRIPTION_SOFTWARE', 81: 'SUBSCRIPTION_SOFTWARE', 82: 'SUBSCRIPTION_SOFTWARE', 86: 'SUBSCRIPTION_SOFTWARE', 87: 'SUBSCRIPTION_SOFTWARE', 88: 'SUBSCRIPTION_SOFTWARE', 93: 'SUBSCRIPTION_SOFTWARE', 51: 'PEOPLE_OR_ROUTE_BASED_SERVICES', 94: 'PEOPLE_OR_ROUTE_BASED_SERVICES', 95: 'PEOPLE_OR_ROUTE_BASED_SERVICES', 96: 'PEOPLE_OR_ROUTE_BASED_SERVICES', 97: 'PEOPLE_OR_ROUTE_BASED_SERVICES', 98: 'PEOPLE_OR_ROUTE_BASED_SERVICES'}

TODAY = "2026-11-28"
#: Headquarters provenance per position (statuses: company_ingestion.entities.HQ_*).
#: A position not listed here keeps its curated country as CURATED_UNSOURCED.
HQ = {
 5: dict(status="CONFLICTING", country="", note="official /about lists San Francisco, Munich, Tel Aviv and Bangalore and names no headquarters; the company LinkedIn profile says Palo Alto (lead supplied by the program owner); aggregators disagree (Tel Aviv, Palo Alto, San Francisco). Not displayed.",
         sources=(("https://www.firebolt.io/about", TODAY, "locations: San Francisco, Munich, Tel Aviv, Bangalore; no HQ named"),
                  ("https://www.linkedin.com/company/firebolt/", "", "Palo Alto, California (owner-supplied lead; not re-fetched: LinkedIn refuses automated readers)"),
                  ("https://www.cbinsights.com/company/firebolt", TODAY, "aggregator: HQ listed differently by source"))),
 8: dict(status="COMPANY_REPORTED", country="Israel", note="Tel Aviv per the company's LinkedIn profile (owner-supplied lead; not re-fetched: LinkedIn refuses automated readers; falkordb.com/about answers 404)",
         sources=(("https://www.linkedin.com/company/falkordb/", "", "headquarters Tel Aviv"),)),
 11: dict(status="VERIFIED", country="United States", note="Redwood City, California",
          sources=(("https://zilliz.com/contact-sales", TODAY, "Headquarters: 201 Redwood Shores Pkwy, Suite 330, Redwood City, CA 94065"),)),
 32: dict(status="VERIFIED", country="France", note="global headquarters Paris; Americas headquarters Redwood City", domicile="France (Ivalua SAS)",
          regional=(("Americas", "Redwood City, United States"),),
          sources=(("https://info.ivalua.com/hubfs/2025-2026%20-%20Ivalua%20Sustainability%20Report.pdf", TODAY, "Headquartered in Paris, France; Ivalua SAS serving as the company headquarters in France"),)),
 34: dict(status="CORROBORATED", country="United States", note="Boston, Massachusetts (two aggregators agree)",
          sources=(("https://www.zoominfo.com/c/toolsgroup-inc/38486276", TODAY, "Boston, MA"), ("https://www.crunchbase.com/organization/toolsgroup", TODAY, "Boston, MA"))),
 35: dict(status="COMPANY_REPORTED", country="United States", note="United States per the company's LinkedIn profile, its Gartner vendor profile and its privacy policy (owner-supplied leads; netstock.com answers 403 to our reader); city not reconciled, so not stated",
          sources=(("https://www.linkedin.com/company/netstock/", "", "United States"), ("https://www.gartner.com/reviews/market/supply-chain-planning-solutions/vendor/netstock", "", "United States"), ("https://www.netstock.com/privacy-policy/", "", "United States (legal notice)"))),
 60: dict(status="COMPANY_REPORTED", country="United States", note="Sunnyvale, California per the company's LinkedIn profile (owner-supplied lead; drivetrain.ai answers 429 to our reader)",
          sources=(("https://www.linkedin.com/company/drivetrainai/", "", "Sunnyvale, California"),)),
 61: dict(status="VERIFIED", country="United States", note="New York City (company-stated on two official pages)",
          sources=(("https://www.abacum.ai/company/about", TODAY, "a global company headquartered in New York City, with offices in Barcelona, Toronto and Buenos Aires"),
                   ("https://www.abacum.ai/newsroom/series-b-announcement", TODAY, "Headquartered in New York"))),
 63: dict(status="CORROBORATED", country="United States", note="North Bethesda, Maryland (Crunchbase, TexAu); engineering in Chennai and Bengaluru",
          sources=(("https://www.crunchbase.com/organization/chargebee", TODAY, "Bethesda, MD"), ("https://texau.com/profiles/chargebee", TODAY, "Bethesda, MD"))),
 70: dict(status="CORROBORATED", country="Germany", note="Munich; secondary headquarters New York",
          regional=(("Secondary", "New York, United States"),),
          sources=(("https://en.wikipedia.org/wiki/Celonis", TODAY, "headquartered in Munich, Germany"), ("https://www.cbinsights.com/company/celonis1", TODAY, "Munich"))),
 71: dict(status="CURATED_UNSOURCED", country="India", note="Chennai (one listing agrees with the curated value)",
          sources=(("https://www.guvi.in/blog/top-product-based-companies-in-chennai/", TODAY, "Chennai"),)),
 80: dict(status="CORROBORATED", country="United States", note="New York; part of Alphabet (Google Cloud) since 2026-03-11",
          sources=(("https://en.wikipedia.org/wiki/Wiz,_Inc.", TODAY, "New York City"), ("https://www.cbinsights.com/company/wiz", TODAY, "New York"))),
 81: dict(status="PROVISIONAL", country="", note="Burlington, Massachusetts per one aggregator only; founded in Israel. Not displayed until a primary source is read.",
          sources=(("https://www.crunchbase.com/organization/aquasecurity", TODAY, "Burlington, MA"),)),
 86: dict(status="CURATED_UNSOURCED", country="United States", note="New York (one aggregator agrees with the curated value)",
          sources=(("https://www.cbinsights.com/company/claroty", TODAY, "1 Pennsylvania Plaza, New York"),)),
 98: dict(status="CORROBORATED", country="United States", note="Austin, Texas (global); European headquarters Lviv, Ukraine",
          regional=(("Europe", "Lviv, Ukraine"),),
          sources=(("https://en.wikipedia.org/wiki/SoftServe", TODAY, "Austin, Texas (Global)"),)),
}


def main():
    rows = list(csv.DictReader((D / "UNIVERSE_AS_LISTED.tsv").read_text().splitlines(), delimiter="\t"))
    split = {a["position"]: a for a in json.loads((D / "SPLIT_FROZEN.json").read_text())["assignment"]}
    ver = {}
    for f in ("domain_verification.json", "domain_verification_r2.json"):
        for v in json.loads((ROOT / "reports/prospect98/identity" / f).read_text()):
            ver.setdefault(v["prospect_id"], []).append(v)
    out = []
    for r in rows:
        p = int(r["position"]); t, legal, dom, hq, al, x = R[p]
        st = x.get("status") or {"state": "INDEPENDENT_OR_UNCHANGED", "summary": NOTFOUND, "evidence": []}
        probes = [{k: v.get(k) for k in ("candidate_domain", "final_host", "safe_fetch_status", "safe_fetch_failure", "title")}
                  for v in ver.get(p, [])]
        listed_now = bool(x.get("ticker"))
        out.append({
            "position": p, "category": r["category"], "name_as_listed": r["name_as_listed"],
            "split": split[p]["split"], "analysis_target": t, "legal_name": legal,
            "primary_domain": dom, "hq_country": (HQ[p]["country"] if p in HQ else hq), "aliases": al,
            "business_model": ({"class": BUSINESS_MODEL[p], "basis": next((v.get("title") for v in ver.get(p, []) if v.get("title") and v.get("safe_fetch_status") == 200), "")} if p in BUSINESS_MODEL else None),
            "headquarters": ({"status": HQ[p]["status"], "displayed_country": HQ[p]["country"], "note": HQ[p]["note"],
                              "sources": [list(x) for x in HQ[p]["sources"]], "regional": [list(x) for x in HQ[p].get("regional", ())],
                              "legal_domicile": HQ[p].get("domicile", "")} if p in HQ else
                             {"status": "CURATED_UNSOURCED" if hq else "UNKNOWN", "displayed_country": hq,
                              "note": "" if hq else "not established", "sources": [], "regional": [], "legal_domicile": ""}),
            "public_listing": ({"ticker": x["ticker"], "exchange": x["exchange"], "cik": x["cik"]} if listed_now else None),
            "former_sec_filer": x.get("former"), "ownership": st,
            "ownership_prior_in_split": split[p]["ownership_prior"],
            "ownership_prior_was_wrong": (split[p]["ownership_prior"] == "public") != listed_now,
            "site_access": x.get("refused") or "readable by safe_fetch",
            "collision_risks": x.get("collisions", []), "notes": x.get("note", ""),
            "extra_evidence": x.get("evidence", []), "domain_probes": probes,
            "identity_status": ("VERIFIED_WITH_CHANGE" if st["state"] != "INDEPENDENT_OR_UNCHANGED"
                                else "VERIFIED"),
            "last_verified": "2026-11-28",
        })
    txt = json.dumps({"program": "prospect98", "generated_by": "scripts/prospect98/identity_registry.py",
                      "rules": __doc__.strip(), "companies": out}, indent=1, ensure_ascii=False)
    (D / "IDENTITY_REGISTRY.json").write_text(txt)
    from collections import Counter
    print(Counter(o["ownership"]["state"] for o in out))
    print("prior wrong:", [(o["position"], o["analysis_target"]) for o in out if o["ownership_prior_was_wrong"]])
    print("listed now:", sum(1 for o in out if o["public_listing"]), "former filers:", sum(1 for o in out if o["former_sec_filer"]))
    print("refused sites:", sum(1 for o in out if o["site_access"] != "readable by safe_fetch"))


if __name__ == "__main__":
    main()
