"""Attest each prospect's candidate web domain before it is written down.

For every candidate domain:
  1. follow redirects with plain urllib to learn where the site actually lives
     today (an acquired company often 301s to its parent -- that IS the finding);
  2. fetch the final host's homepage through the product's own `safe_fetch`,
     which refuses cross-domain redirects, so a domain only counts as verified
     when the PRODUCT can read it, not merely when curl can;
  3. record <title>, the visible-text length and a body hash (an SPA shell
     answers 200 with the same body for every path; the hash lets the source
     discovery step reject those).

Candidates are hypotheses typed by a person. Nothing here is trusted until the
fetch says so.

Usage:
  PYTHONPATH=src python scripts/prospect100/verify_domains.py \
      --candidates candidates.json --out OUT.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import html
import json
import re
import ssl
import urllib.request

from intent_engine.company_ingestion.fetch import safe_fetch
from intent_engine.company_ingestion.edgar import USER_AGENT

_TITLE = re.compile(rb"<title[^>]*>(.*?)</title>", re.I | re.S)


def visible_text(body: bytes) -> str:
    text = body.decode("utf-8", "replace")
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return " ".join(html.unescape(text).split())


def _follow(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=20,
                                    context=ssl.create_default_context()) as r:
            return {"final_url": r.geturl(), "status": r.status}
    except Exception as exc:                               # noqa: BLE001
        return {"final_url": "", "status": 0,
                "error": f"{type(exc).__name__}: {str(exc)[:120]}"}


def _host(url: str) -> str:
    m = re.match(r"https?://([^/:]+)", url or "")
    return m.group(1).lower() if m else ""


def probe(pid: int, domain: str) -> dict:
    followed = _follow(f"https://{domain}/")
    final_host = _host(followed.get("final_url", "")) or domain
    target = f"https://{final_host}/"
    res = safe_fetch(target, timeout=20)
    body = res.get("body") or b""
    if isinstance(body, str):
        body = body.encode("utf-8", "replace")
    title = ""
    m = _TITLE.search(body or b"")
    if m:
        title = " ".join(html.unescape(
            m.group(1).decode("utf-8", "replace")).split())[:160]
    text = visible_text(body) if body else ""
    return {
        "prospect_id": pid, "candidate_domain": domain,
        "followed": followed, "final_host": final_host,
        "redirected_off_domain": (final_host.removeprefix("www.")
                                  != domain.removeprefix("www.")),
        "safe_fetch_ok": bool(res.get("ok")),
        "safe_fetch_status": res.get("status_code"),
        "safe_fetch_failure": res.get("failure_type") or "",
        "title": title, "text_chars": len(text),
        "body_sha1": hashlib.sha1(body).hexdigest() if body else "",
        "text_head": text[:300],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True,
                    help="JSON {prospect_id: [domain, ...]}")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    cands = json.load(open(args.candidates))
    jobs = [(int(pid), d) for pid, ds in cands.items() for d in ds]
    out = []
    with cf.ThreadPoolExecutor(args.workers) as pool:
        futs = {pool.submit(probe, pid, d): (pid, d) for pid, d in jobs}
        for f in cf.as_completed(futs):
            pid, d = futs[f]
            try:
                out.append(f.result())
            except Exception as exc:                       # noqa: BLE001
                out.append({"prospect_id": pid, "candidate_domain": d,
                            "error": repr(exc)[:200]})
    out.sort(key=lambda r: (r["prospect_id"], r["candidate_domain"]))
    json.dump(out, open(args.out, "w"), indent=1)
    print(f"probed {len(out)} domains -> {args.out}")


if __name__ == "__main__":
    main()
