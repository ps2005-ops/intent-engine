"""Probe candidate trade publishers with the channel's OWN admission probe.

A publisher joins `independent_reporting.PUBLISHERS` only when this probe
shows robots.txt allows the feed path for our user agent AND the feed parses
with items -- the rule the module states, never a hand-written entry.

Candidates cover the sectors the round-5 scorecard left without an outside
account (data infrastructure, security, MSP/channel, fintech, HR, ESG,
accounting). Each probe is a handful of requests through the live fetcher
(honest User-Agent, robots checked), once.

  PYTHONPATH=src python scripts/prospect100/resume/probe_publishers.py
"""
from __future__ import annotations

import json
import pathlib
import sys

from intent_engine.company_ingestion import independent_reporting as IR

#: (name, host, tag feed, search feed, sample companies from the 100)
CANDIDATES = (
    ("Blocks & Files", "blocksandfiles.com", "/tag/{slug}/feed/",
     "/?s={q}&feed=rss2", ("WEKA", "Hammerspace", "Pure Storage")),
    ("insideBIGDATA", "insidebigdata.com", "/tag/{slug}/feed/",
     "/?s={q}&feed=rss2", ("Qlik", "SingleStore", "Neo4j")),
    ("diginomica", "diginomica.com", "/tag/{slug}/feed/",
     "/?s={q}&feed=rss2", ("Workday", "Anaplan", "Epicor")),
    ("VentureBeat", "venturebeat.com", "/tag/{slug}/feed/",
     "/?s={q}&feed=rss2", ("Rippling", "Deel", "Ramp")),
    ("TechCrunch", "techcrunch.com", "/tag/{slug}/feed/",
     "/?s={q}&feed=rss2", ("Rippling", "Brex", "Gusto")),
    ("SDxCentral", "www.sdxcentral.com", "/tag/{slug}/feed/",
     "/?s={q}&feed=rss2", ("Auvik", "Barracuda", "Tanium")),
    ("FinTech Futures", "www.fintechfutures.com", "/tag/{slug}/feed/",
     "/?s={q}&feed=rss2", ("Brex", "Ramp", "BILL")),
)


def main() -> int:
    fetch, _fetch_json = IR.live_fetchers()
    out = []
    for name, host, tag, search, samples in CANDIDATES:
        pub = IR.Publisher(name, host, tag, search, "probe candidate")
        rows = [IR.probe_publisher(pub, s, fetch=fetch) for s in samples]
        tag_ok = [r.get("tag", {}) for r in rows]
        search_ok = [r.get("search", {}) for r in rows]
        verdict = {
            "publisher": name, "host": host, "samples": samples,
            "tag": tag_ok, "search": search_ok,
            "admit_tag": all(t.get("robots_allows") for t in tag_ok)
                         and sum(max(0, t.get("items", 0)) for t in tag_ok) > 0,
            "admit_search": all(s.get("robots_allows") for s in search_ok)
                            and sum(max(0, s.get("items", 0)) for s in search_ok) > 0,
        }
        out.append(verdict)
        print(json.dumps({k: verdict[k] for k in ("publisher", "admit_tag",
                                                  "admit_search")}),
              [(t.get("items"), s.get("items")) for t, s in zip(tag_ok, search_ok)],
              flush=True)
    dest = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if dest:
        dest.write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
