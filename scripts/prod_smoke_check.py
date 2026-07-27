#!/usr/bin/env python
"""Production smoke check — drives the REAL guest flow over HTTP.

This is deliberately different from scripts/live_report_check.py. That script
imports the services and runs them IN-PROCESS on the local machine; it proves
the code works, but it never touches a deployment. This one speaks HTTP to a
deployed instance, so it is the only thing here that can say anything about
production at all.

What it proves:
  * the deployed build is the commit you think it is (/version)
  * an anonymous visitor can complete a real analysis end to end
  * the report renders with real, resolvable citations

What it does NOT prove: report quality. Quality is measured by the golden
suite and scripts/live_report_check.py. Treat a PASS here as "the deployed
path works", not "the deployed report is good".

Note on timing: with WEBAPP_AUTORUN_SOURCES=1 the whole analysis (discover,
retrieve every approved source, compose) happens SYNCHRONOUSLY inside the
POST /analyze request. A slow or sleeping instance can therefore be killed by
an upstream proxy mid-analysis; that failure is a real production finding and
is reported as such rather than retried away.

Usage:
    python scripts/prod_smoke_check.py --base-url https://example.onrender.com \
        --companies shopify.com --out prod-smoke.json
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

KNOWN = {
    "palantir.com": ("Palantir Technologies", "https://www.palantir.com"),
    "microsoft.com": ("Microsoft", "https://www.microsoft.com"),
    "nvidia.com": ("NVIDIA", "https://www.nvidia.com"),
    "apple.com": ("Apple", "https://www.apple.com"),
    "shopify.com": ("Shopify", "https://www.shopify.com"),
    "snowflake.com": ("Snowflake", "https://www.snowflake.com"),
}

UA = "intent-engine-prod-smoke/1.0 (release validation)"


class Client:
    """Cookie-aware HTTP client that does NOT auto-follow redirects.

    Redirects are followed by hand so each hop's status and Location can be
    recorded — a 302 to /login instead of /runs/<id>/progress is a meaningful
    production failure, and an auto-following client would hide it.
    """

    def __init__(self, base_url: str, timeout: float):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            _NoRedirect(),
        )

    def request(self, path: str, data: dict | None = None) -> tuple:
        url = path if path.startswith("http") else self.base + path
        body = None
        if data is not None:
            body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(url, data=body, headers={"User-Agent": UA})
        started = time.time()
        try:
            resp = self.opener.open(req, timeout=self.timeout)
            text = resp.read().decode("utf-8", "replace")
            return resp.status, _headers(resp), text, time.time() - started
        except urllib.error.HTTPError as exc:
            # A 3xx arrives here because redirects are not followed.
            text = exc.read().decode("utf-8", "replace")
            return exc.code, _headers(exc), text, time.time() - started


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _headers(resp) -> dict:
    """Lower-cased header map. HTTP header names are case-insensitive and
    plain dict() over the message object is not, which silently loses
    'Location' whenever the server spells it differently.
    """
    return {k.lower(): v for k, v in resp.headers.items()}


def _csrf(html: str) -> str | None:
    m = re.search(r'name="csrf"\s+value="([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r'value="([^"]+)"\s+name="csrf"', html)
    return m.group(1) if m else None


def check(base_url: str, domain: str, timeout: float) -> dict:
    name, website = KNOWN.get(domain, (domain, f"https://{domain}"))
    out: dict = {"company": name, "domain": domain, "steps": []}
    c = Client(base_url, timeout)

    def step(label, status, elapsed, **extra):
        rec = {"step": label, "status": status, "seconds": round(elapsed, 1)}
        rec.update(extra)
        out["steps"].append(rec)
        return rec

    # 0. which build is live
    status, _, text, el = c.request("/version")
    version = {}
    if status == 200:
        try:
            version = json.loads(text)
        except ValueError:
            pass
    out["deployed_version"] = version
    step("version", status, el, **version)

    # 1. anonymous demo session (CSRF-exempt only while DEMO_MODE is on)
    status, _, text, el = c.request("/demo", data={})
    step("demo_session", status, el)
    if status not in (302, 303):
        out["outcome"] = "FAIL"
        out["reason"] = ("could not start an anonymous demo session "
                         f"(HTTP {status}) — is DEMO_MODE enabled?")
        return out

    # 2. landing page carries the CSRF token for the analyze form
    status, _, html, el = c.request("/")
    token = _csrf(html)
    step("landing", status, el, csrf_present=bool(token))
    if status != 200 or not token:
        out["outcome"] = "FAIL"
        out["reason"] = f"landing page gave HTTP {status} / csrf={bool(token)}"
        return out

    # 3. the analysis itself — synchronous, and the step that actually matters
    status, headers, text, el = c.request("/analyze", data={
        "company_name": name,
        "website": website,
        "requester_role": "release validation",
        "business_question": "production smoke check",
        "consent": "on",
        "csrf": token,
    })
    location = headers.get("location", "")
    step("analyze", status, el, location=location)
    out["analyze_seconds"] = round(el, 1)
    if status == 429:
        out["outcome"] = "RATE_LIMITED"
        out["reason"] = "demo rate limit reached for this IP/session"
        return out
    if status not in (302, 303):
        out["outcome"] = "FAIL"
        out["reason"] = (f"analyze returned HTTP {status} after {el:.0f}s "
                         "(a 502/504 here means the upstream proxy killed the "
                         "synchronous analysis)")
        return out

    m = re.search(r"/runs/([^/]+)/", location)
    if not m:
        out["outcome"] = "FAIL"
        out["reason"] = f"no run id in redirect target {location!r}"
        return out
    run_id = m.group(1)
    out["run_id"] = run_id

    # 4. progress page must belong to this session (302 -> /login means the
    #    ephemeral session secret was regenerated mid-run)
    status, _, text, el = c.request(f"/runs/{run_id}/progress")
    step("progress", status, el)
    if status != 200:
        out["outcome"] = "FAIL"
        out["reason"] = f"progress page HTTP {status}"
        return out

    # 5. the FULL result page. Not /runs/<id>/report — that is only the
    #    shareable preview and deliberately omits the evidence library, so
    #    counting citations there always yields zero.
    status, _, report, el = c.request(f"/runs/{run_id}")
    #    A strategic report cites through source-detail links; the legacy
    #    layout uses /evidence/. Accept either so this keeps working.
    citations = sorted(set(re.findall(
        r"/runs/[^/]+/(?:sources|evidence)/([A-Za-z0-9_.:-]+)", report)))
    step("result", status, el, bytes=len(report), citations=len(citations))
    out["result_bytes"] = len(report)
    out["citation_count"] = len(citations)
    if status != 200:
        out["outcome"] = "FAIL"
        out["reason"] = f"result page HTTP {status}"
        return out

    plain = re.sub(r"\s+", " ", re.sub(
        r"(?is)<(style|script)[^>]*>.*?</\1>|<[^>]+>", " ", report)).strip()
    out["coverage_banner"] = next(
        (b for b in ("Partial — limited source diversity", "Partial", "LIMITED")
         if b in plain), None)
    # "Company · 6 Investor · 3". The count is bounded to 1-2 digits and must
    # not run into a longer number, or "Last researched: 2026-07-27" sitting
    # next to the badge gets captured as the count.
    out["family_counts"] = dict(re.findall(
        r"(Company|Investor|Customer|External|Executive|Product|Pricing)"
        r"\s*·\s*(\d{1,2})(?![\d-])", plain))
    out["company_named"] = name.split()[0].lower() in plain.lower()

    resolved = 0
    for cid in citations[:3]:               # sample; each is a real request
        st, _, _, _ = c.request(f"/runs/{run_id}/sources/{cid}")
        if st == 200:
            resolved += 1
    out["citations_sampled"] = min(3, len(citations))
    out["citations_resolved"] = resolved

    if not citations:
        out["outcome"] = "DEGRADED"
        out["reason"] = ("the flow completed but the result carries no "
                         "resolvable source citations")
        return out
    if resolved != out["citations_sampled"]:
        out["outcome"] = "DEGRADED"
        out["reason"] = (f"only {resolved}/{out['citations_sampled']} sampled "
                         "citations resolved")
        return out
    if not out["company_named"]:
        out["outcome"] = "DEGRADED"
        out["reason"] = "the result never names the company"
        return out

    out["outcome"] = "PASS"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--companies", default="shopify.com")
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--out")
    args = ap.parse_args()

    domains = [d.strip() for d in args.companies.split(",") if d.strip()]
    results = []
    for d in domains:
        print(f"--- {d} ---", flush=True)
        r = check(args.base_url, d, args.timeout)
        for s in r["steps"]:
            print(f"  {s['step']:<14} HTTP {s['status']:<4} {s['seconds']:>6}s",
                  flush=True)
        print(f"  => {r['outcome']}"
              + (f" — {r.get('reason')}" if r.get("reason") else ""), flush=True)
        results.append(r)

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(results, fh, indent=2)
        print(f"\nwrote {args.out}")

    ok = all(r["outcome"] == "PASS" for r in results)
    print("\nSMOKE: " + ("PASS" if ok else "NOT PASS"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
