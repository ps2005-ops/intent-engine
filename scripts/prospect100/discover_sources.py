"""Find each prospect's official pages from its OWN navigation, then attest them.

The catalog contract (company_ingestion/catalog.py) is that every URL was
fetched through `safe_fetch` before it was written down, and that paths come
from the publisher's navigation rather than a list of plausible slugs. This
script does exactly that and nothing more:

  1. read the homepage (with a raised byte budget, because several marketing
     homepages are 2-3 MB -- this read is only to see the navigation);
  2. collect same-site links and bucket them by what the path says it is
     (about / platform / customers / newsroom / pricing);
  3. fetch the best candidate per bucket through the product's `safe_fetch`
     at its DEFAULT budget -- the budget a live run will use -- and keep it
     only if it answered 200, stayed on the host, carried real text, and is
     not the homepage's body again (an SPA answers every path with its shell).

Output is a proposal for a human-reviewed catalog row, not the row itself.

Usage:
  PYTHONPATH=src python scripts/prospect100/discover_sources.py \
      --hosts hosts.json --out OUT.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import html
import json
import re
from urllib.parse import urljoin, urlparse

from intent_engine.company_ingestion.fetch import safe_fetch

_HREF = re.compile(rb"""<a\b[^>]*?href\s*=\s*["']([^"'#]+)["']""", re.I)

#: kind -> (path keywords in priority order, catalog label)
_BUCKETS = (
    ("corporate", ("about-us", "about", "company", "who-we-are", "our-story",
                   "leadership"), "about"),
    ("segment", ("platform", "products", "product", "solutions"), "platform"),
    ("customers", ("customers", "customer-stories", "case-studies",
                   "success-stories"), "customers"),
    ("newsroom", ("newsroom", "press-releases", "press", "news"), "news"),
    ("pricing", ("pricing", "plans"), "pricing"),
)

MIN_TEXT = 600


def _text(body: bytes) -> str:
    t = body.decode("utf-8", "replace")
    t = re.sub(r"(?is)<!--.*?-->", " ", t)
    t = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1>", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return " ".join(html.unescape(t).split())


def _site(host: str) -> str:
    parts = host.lower().removeprefix("www.").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _links(base: str, body: bytes):
    host = urlparse(base).netloc.lower()
    out = []
    for raw in _HREF.findall(body or b""):
        href = raw.decode("utf-8", "replace").strip()
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(base, href).split("?")[0].rstrip("/")
        p = urlparse(url)
        if p.scheme != "https":
            continue
        # SAME HOST ONLY. A subdomain (docs., community., investors.) is a
        # different publishing surface and is left to a human to add.
        if p.netloc.lower() != host:
            continue
        out.append(url)
    return list(dict.fromkeys(out))


def _bucket(urls):
    chosen = {}
    for kind, keys, label in _BUCKETS:
        best = None
        for key in keys:
            for u in urls:
                path = urlparse(u).path.lower().strip("/")
                segs = path.split("/")
                # the keyword must BE a path segment, and the page must be a
                # section root or one level under it -- not an article.
                if key in segs and len(segs) <= 2:
                    if best is None or len(path) < len(urlparse(best).path):
                        best = u
            if best:
                break
        if best:
            chosen[kind] = (best, label)
    return chosen


def discover(pid: int, host: str) -> dict:
    home = f"https://{host}/"
    res = safe_fetch(home, timeout=20, max_bytes=8_000_000)
    body = res.get("body") or b""
    if isinstance(body, str):
        body = body.encode("utf-8", "replace")
    row = {"prospect_id": pid, "host": host,
           "home_ok": bool(res.get("ok")),
           "home_failure": res.get("failure_type") or "",
           "home_status": res.get("status_code"), "accepted": [],
           "rejected": []}
    if not body:
        return row
    home_sha = hashlib.sha1(body).hexdigest()
    home_text = _text(body)
    for kind, (url, label) in _bucket(_links(home, body)).items():
        r = safe_fetch(url, timeout=20)           # the live-run budget
        b = r.get("body") or b""
        if isinstance(b, str):
            b = b.encode("utf-8", "replace")
        txt = _text(b) if b else ""
        final = r.get("final_url") or url
        why = ""
        if not r.get("ok"):
            why = f"fetch:{r.get('failure_type') or r.get('status_code')}"
        elif urlparse(final).netloc.lower() != host:
            why = f"left host:{urlparse(final).netloc}"
        elif hashlib.sha1(b).hexdigest() == home_sha or txt == home_text:
            why = "same body as homepage (SPA shell)"
        elif len(txt) < MIN_TEXT:
            why = f"thin:{len(txt)} chars"
        rec = {"kind": kind, "label": label, "url": url,
               "text_chars": len(txt)}
        (row["rejected"] if why else row["accepted"]).append(
            {**rec, **({"why": why} if why else {})})
    # The homepage itself is a usable corporate source when nothing better
    # was attested and the product can read it at the default budget.
    if not any(a["kind"] == "corporate" for a in row["accepted"]):
        plain = safe_fetch(home, timeout=20)
        if plain.get("ok") and len(home_text) >= MIN_TEXT:
            row["accepted"].insert(0, {"kind": "corporate", "label": "home",
                                       "url": home.rstrip("/"),
                                       "text_chars": len(home_text)})
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hosts", required=True, help="JSON {prospect_id: host}")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()
    hosts = json.load(open(args.hosts))
    out = []
    with cf.ThreadPoolExecutor(args.workers) as pool:
        futs = {pool.submit(discover, int(k), v): k for k, v in hosts.items()}
        for f in cf.as_completed(futs):
            try:
                out.append(f.result())
            except Exception as exc:                       # noqa: BLE001
                out.append({"prospect_id": int(futs[f]), "error": repr(exc)})
    out.sort(key=lambda r: r["prospect_id"])
    json.dump(out, open(args.out, "w"), indent=1)
    ok = sum(1 for r in out if r.get("accepted"))
    print(f"{ok}/{len(out)} hosts yielded at least one attested source")


if __name__ == "__main__":
    main()
