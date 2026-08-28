"""§30/§32/§33/§34: the deployed product, driven against ten real companies.

WHY THIS IS NOT CURL AND NOT A BROWSER
--------------------------------------
`curl` cannot hold the anonymous session: it is minted in the 303 that answers
`POST /analyze`, and a client that follows the redirect without a cookie jar
lands on `/login`, reports "no run" for every company -- and still spends one
of the ten analyses the deployment allows per IP per hour. That failure looks
exactly like a product failure and is not one.

So this carries a real cookie jar and one session per company, and it reads
the rendered pages the way a customer's browser would receive them.

THE QUOTA IS THE BUDGET
-----------------------
Ten analyses per client IP per rolling hour. The matrix is ten companies, so
one run is the entire hour. A retry is not free; a bad harness burns the hour
invisibly. Every request is therefore logged with its status before the next
one is made, and the run stops on the first 429 rather than spending what is
left proving the same thing.

STRIPPING TAGS BEFORE COMMENTS IS A KNOWN TRAP
----------------------------------------------
`<[^>]+>` deletes only up to a comment's first `>`, so a developer note in the
shared shell -- which names another company -- spills into "visible text" and
every subject reports a cross-company leak. Comments and script/style blocks
come out first.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://intent-engine-preview-bridge.onrender.com"
OUT = pathlib.Path("reports/live_econ_matrix.json")

#: §19/§32. Ten companies chosen for SPREAD, not for a happy path: a scale
#: retailer, a branded consumer brand, a bank, a payments network, an
#: industrial, two software companies of different kinds, a chip designer, a
#: rate-base asset owner, and one that is deliberately hard.
COMPANIES = [
    ("Walmart", "walmart.com"),
    ("Nike", "nike.com"),
    ("JPMorgan Chase", "jpmorganchase.com"),
    ("Visa", "visa.com"),
    ("Caterpillar", "caterpillar.com"),
    ("Meta Platforms", "meta.com"),
    ("NVIDIA", "nvidia.com"),
    ("Salesforce", "salesforce.com"),
    ("Union Pacific", "up.com"),
    ("Cloudflare", "cloudflare.com"),
]

SURFACES = ("", "/brief", "/full")


def _opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPRedirectHandler), jar


#: How long a page fetch may take before the harness gives up.
#:
#: THE FIRST MATRIX RECORDED FOUR "FAILURES" THAT WERE TIMEOUTS AT EXACTLY
#: 180.1s, and a timeout is not a failure -- it is the harness deciding to
#: stop waiting. Measured locally, the primary screen and the full analysis
#: cost 0.86s each with the economic context and 0.73s without, so the live
#: figure is the free instance's CPU quota rather than the work. An
#: instrument that reports "the page failed" when what happened is "the page
#: is slow" sends the next session looking for the wrong thing.
PAGE_TIMEOUT = 300


def _get(op, path, timeout=PAGE_TIMEOUT):
    req = urllib.request.Request(BASE + path,
                                 headers={"User-Agent": "econ-matrix/1"})
    started = time.monotonic()
    try:
        with op.open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), \
                r.geturl(), time.monotonic() - started
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), \
            BASE + path, time.monotonic() - started
    except Exception as e:                                  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}", BASE + path, \
            time.monotonic() - started


def _post(op, path, fields, timeout=PAGE_TIMEOUT):
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        BASE + path, data=body,
        headers={"User-Agent": "econ-matrix/1",
                 "Content-Type": "application/x-www-form-urlencoded"})
    started = time.monotonic()
    try:
        with op.open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), \
                r.geturl(), time.monotonic() - started
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), \
            BASE + path, time.monotonic() - started
    except Exception as e:                                  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}", BASE + path, \
            time.monotonic() - started


def visible(html: str) -> str:
    """What a reader actually sees. Comments and scripts first, then tags."""
    s = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    s = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&#x27;", "'").replace("&quot;", '"')
          .replace("&ldquo;", '"').replace("&rdquo;", '"')
          .replace("&rsquo;", "'").replace("&nbsp;", " "))
    return " ".join(s.split())


ECON_MARKERS = ("Economic impact",)
ABSTAIN_MARKER = "do not materially change the strategic recommendation"
SPEAK_MARKER = "of this recommendation"
PRE_CAL = "no accuracy record to quote"
BLOCKED_MARKER = "rests entirely on the company's own evidence"


def score(name: str, pages: dict, section: str = "") -> dict:
    """§32's scorecard, computed from what the deployed pages actually say.

    `section` is the ECONOMIC SECTION's own text. Two of these checks are
    about what one section says about itself, and scoring them against the
    whole joined page is how Caterpillar was reported as contradicting
    itself: its economic section is internally consistent, and the phrase the
    check looked for appears elsewhere on the full analysis. A
    self-contradiction check has to read the thing that would be
    contradicting itself.
    """
    text = {k: visible(v["body"]) for k, v in pages.items()}
    joined = " ".join(text.values())
    section = section or ""
    section = any(m in joined for m in ECON_MARKERS)
    abstained = ABSTAIN_MARKER in joined
    spoke = SPEAK_MARKER in joined and "changes" in joined
    return {
        "economic_section_present": section,
        "abstained": abstained,
        "spoke": spoke,
        # §21: one canonical state. The brief and the full analysis may not
        # land on opposite verdicts for the same run.
        "cross_surface_contradiction": (
            ABSTAIN_MARKER in text.get("/brief", "")
            and SPEAK_MARKER in text.get("/full", "")
            and "changes" in text.get("/full", "")),
        "blocked_stated": BLOCKED_MARKER in joined,
        "pre_calibration_language": PRE_CAL in joined,
        # §41: no enum soup on a customer surface.
        "internal_enums_leaked": sorted(
            {e for e in ("NO_MATERIAL_ECONOMIC_DELTA", "BLOCKED_DATA",
                         "CANDIDATE_NOT_PROVEN", "PRE_CALIBRATION",
                         "INSUFFICIENT_EVIDENCE", "SUBSCRIPTION_SOFTWARE",
                         "BALANCE_SHEET_OR_NETWORK", "MARKET_RATE",
                         # Added after it was measured on a rendered page:
                         # "rising to 6.66 percentage_point".
                         "percentage_point")
             if e in joined}),
        # THE SELF-CONTRADICTION FOUND IN THE FIRST MATRIX. Five of ten
        # companies were told they had no evidenced exposure to anything the
        # state measures, and the very next sentence listed the state's
        # reading of the conditions they were exposed to.
        "denies_exposure_then_shows_one": (
            "no exposure to any condition" in section
            and "the shared economic state reads" in section),
        # Three of ten reported the economic reading "unavailable" while the
        # state was published and dated the previous day.
        "reading_called_unavailable": "(unavailable)" in section,
        "words": {k: len(v.split()) for k, v in text.items()},
    }


def econ_excerpt(pages: dict, width: int = 900) -> str:
    for key in ("/brief", "/full", ""):
        t = visible(pages.get(key, {}).get("body", ""))
        i = t.find("Economic impact")
        if i >= 0:
            return t[i:i + width]
    return ""


def analyse(name, domain, *, poll_seconds, verbose=True):
    op, _jar = _opener()
    row = {"company": name, "domain": domain, "requests": []}
    # THE ENTRY SCREEN FIRST, AND ITS CSRF TOKEN CARRIED.
    #
    # Posting straight to /analyze with no cookie also works -- the router
    # mints an anonymous session and skips the CSRF gate for exactly that
    # case -- but it is not what the customer's browser does. Once /demo has
    # minted a session the gate applies, and a harness that skips the entry
    # screen to dodge it is sending LESS than the real form does, which is
    # bypassing the customer flow rather than testing it.
    st, entry, _u, dt = _get(op, "/demo")
    row["requests"].append({"path": "/demo", "status": st,
                            "seconds": round(dt, 1)})
    m_csrf = re.search(r'name="csrf"\s+value="([^"]+)"', entry)
    fields = {"consent": "on", "company_name": name,
              "website": f"https://{domain}"}
    if m_csrf:
        fields["csrf"] = m_csrf.group(1)
    row["carried_csrf"] = bool(m_csrf)
    st, body, url, dt = _post(op, "/analyze", fields)
    row["requests"].append({"path": "/analyze", "status": st,
                            "seconds": round(dt, 1), "landed": url})
    if st == 429:
        row["state"] = "QUOTA_EXHAUSTED"
        row["detail"] = visible(body)[:300]
        return row
    m = re.search(r"/runs/([A-Za-z0-9_-]+)", url) or \
        re.search(r"/runs/([A-Za-z0-9_-]+)", body)
    if not m:
        row["state"] = "NO_RUN"
        row["detail"] = visible(body)[:400]
        return row
    run_id = m.group(1)
    row["run_id"] = run_id

    deadline = time.time() + poll_seconds
    ready = False
    while time.time() < deadline:
        st, body, url, _dt = _get(op, f"/runs/{run_id}/brief")
        if st == 200 and "progress" not in url and len(visible(body)) > 800:
            ready = True
            break
        time.sleep(15)
    row["ready"] = ready
    row["seconds_to_read"] = round(poll_seconds - max(0, deadline - time.time()), 1)

    pages = {}
    for suffix in SURFACES:
        st, body, url, dt = _get(op, f"/runs/{run_id}{suffix}")
        pages[suffix] = {"status": st, "body": body, "seconds": round(dt, 1),
                         "url": url}
        row["requests"].append({"path": f"/runs/{run_id}{suffix}",
                                "status": st, "seconds": round(dt, 1),
                                "chars": len(body)})
    row["state"] = "READ" if ready else "TIMED_OUT"
    row["econ_excerpt"] = econ_excerpt(pages)
    row["score"] = score(name, pages, section=row["econ_excerpt"])
    # A TIMEOUT AND A 500 ARE DIFFERENT FINDINGS. Status 0 is this client
    # giving up; a 4xx/5xx is the server answering badly. Counting them
    # together is what made the first matrix report "4 requests with a
    # 4xx/5xx" when there was one.
    row["failures"] = [r for r in row["requests"]
                       if str(r["status"]).startswith(("4", "5"))]
    row["timeouts"] = [r for r in row["requests"] if r["status"] == 0]
    row["slowest_seconds"] = max((r["seconds"] for r in row["requests"]),
                                 default=0.0)
    if verbose:
        s = row["score"]
        print(f"  {name:<18}{row['state']:<12}"
              f"section={'Y' if s['economic_section_present'] else 'n'} "
              f"{'ABSTAIN' if s['abstained'] else ('SPEAKS' if s['spoke'] else ('BLOCKED' if s['blocked_stated'] else '-')):<8}"
              f"contradiction={'Y' if s['cross_surface_contradiction'] else 'n'} "
              f"leaks={s['internal_enums_leaked'] or '-'}")
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--poll", type=int, default=420)
    ap.add_argument("--only", default="")
    ap.add_argument("--skip", default="",
                    help="comma-separated names to leave for a browser "
                         "journey, so the hourly quota covers both")
    ap.add_argument("--label", default="first")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    op, _ = _opener()
    st, body, _u, _d = _get(op, "/version", timeout=180)
    version = json.loads(body) if st == 200 else {"error": body[:200]}
    print(f"deployed commit  {version.get('commit', '?')}")
    st, ready_body, _u, _d = _get(op, "/readyz", timeout=180)
    readyz = json.loads(ready_body) if st == 200 else {}
    print(f"runtime_root     {readyz.get('runtime_root', '?')}")
    print(f"storage          "
          f"{(readyz.get('storage') or {}).get('durability', '?')}\n")

    skip = {x.strip().lower() for x in args.skip.split(",") if x.strip()}
    todo = [c for c in COMPANIES
            if (not args.only or args.only.lower() in c[0].lower())
            and c[0].lower() not in skip]
    rows = []
    for name, domain in todo:
        rows.append(analyse(name, domain, poll_seconds=args.poll))
        if rows[-1].get("state") == "QUOTA_EXHAUSTED":
            print("  quota exhausted; stopping rather than spending the rest "
                  "of the hour proving the same thing")
            break

    read = [r for r in rows if r.get("state") == "READ"]
    spoke = [r for r in read if r["score"]["spoke"]]
    abst = [r for r in read if r["score"]["abstained"]]
    section = [r for r in read if r["score"]["economic_section_present"]]
    contra = [r for r in read if r["score"]["cross_surface_contradiction"]]
    leaks = [r for r in read if r["score"]["internal_enums_leaked"]]
    denies = [r for r in read if r["score"]["denies_exposure_then_shows_one"]]
    unavail = [r for r in read if r["score"]["reading_called_unavailable"]]
    fails = [r for r in rows if r.get("failures")]
    slow = [r for r in rows if r.get("timeouts")]
    print(f"\n=== LIVE MATRIX ({args.label}) ===")
    print(f"  attempted                {len(rows)}")
    print(f"  read a result            {len(read)}")
    print(f"  economic section present {len(section)}")
    print(f"  spoke (material delta)   {len(spoke)}")
    print(f"  abstained                {len(abst)}")
    print(f"  cross-surface conflict   {len(contra)}  (requires 0)")
    print(f"  internal enum leaks      {len(leaks)}  (requires 0)")
    print(f"  denies-then-shows exposure{len(denies):>3}  (requires 0)")
    print(f"  reading called unavailable{len(unavail):>3}  (requires 0)")
    print(f"  server errors (4xx/5xx)  {len(fails)}")
    print(f"  client timeouts >{PAGE_TIMEOUT}s   {len(slow)}")
    payload = {"contract": "live_econ_matrix.v1", "label": args.label,
               "base": BASE, "version": version,
               "readyz": {k: readyz.get(k) for k in
                          ("runtime_root", "storage", "market_bridge")},
               "summary": {"attempted": len(rows), "read": len(read),
                           "section": len(section), "spoke": len(spoke),
                           "abstained": len(abst),
                           "contradictions": len(contra),
                           "enum_leaks": len(leaks),
                           "denies_then_shows_exposure": len(denies),
                           "reading_called_unavailable": len(unavail),
                           "http_failures": len(fails),
                           "client_timeouts": len(slow)},
               "rows": rows}
    out = pathlib.Path(args.out) if args.out else OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True,
                              default=str))
    print(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
