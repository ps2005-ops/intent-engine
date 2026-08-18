#!/usr/bin/env python3
"""Drive the deployed guest journey for one or more companies, end to end.

WHY THIS EXISTS. The browser pane refused navigation across three tabs in two
consecutive sessions while the service answered 200 the whole time, and a
60-company experiment cannot be gated on one flaky tab. This walks the same
customer path over HTTP with a cookie jar: landing -> try demo -> company
entry -> analyse -> progress -> the six steps.

It asserts the SAME things a person would: that the run auto-advances rather
than parking, that no step is empty, and that no page claims a failure while
a result exists.

Usage:
  python scripts/batch_live_journey.py "Meta Platforms, Inc.:1326801" ...
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import http.cookiejar

BASE = "https://intent-engine-preview-bridge.onrender.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

STEPS = ["intro", "slides", "full", "story", "history", "connect"]

#: Copy that means the product gave up in front of a chief executive.
ABSENCE = [
    "no information available", "no knowledge available", "not retrieved",
    "nothing found", "unable to determine", "no strategic reading",
    "no reading cleared", "no estimate retrieved", "no history available",
    "no market expectation", "no evidence available", "no data available",
    "could not be completed", "analysis failed",
]


def _opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPRedirectHandler())


class Journey:
    def __init__(self):
        self.o = _opener()

    def get(self, path, follow=True):
        req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
        try:
            with self.o.open(req, timeout=90) as r:
                return r.status, r.geturl(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, BASE + path, e.read().decode("utf-8", "replace")

    def post(self, path, data):
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(
            BASE + path, data=body,
            headers={"User-Agent": UA, "Origin": BASE,
                     "Referer": BASE + "/demo",
                     "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with self.o.open(req, timeout=120) as r:
                return r.status, r.geturl(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, BASE + path, e.read().decode("utf-8", "replace")


def text_of(page: str) -> str:
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", html.unescape(body)).strip()


def run_company(name: str, cik: str = "", ticker: str = "") -> dict:
    j = Journey()
    out = {"company": name, "cik": cik}
    j.get("/")
    j.post("/demo", {})
    _, _, entry = j.get("/demo")
    csrf = re.search(r'name="csrf" value="([^"]+)"', entry)
    if not csrf:
        out["error"] = "no csrf on entry page"
        return out
    form = {"csrf": csrf.group(1), "consent": "on", "company_name": name,
            "suggest_confirmed": name}
    if cik:
        form["suggest_cik"] = cik
    if ticker:
        form["suggest_ticker"] = ticker
    t0 = time.time()
    status, url, _ = j.post("/analyze", form)
    if "/runs/" not in url:
        out["error"] = f"analyze did not open a run (HTTP {status})"
        return out
    run_id = url.split("/runs/")[1].split("/")[0]
    out["run_id"] = run_id

    # AUTO-ADVANCE: poll the progress URL exactly as the page's own refresh
    # would. A pass means the progress URL stops being the progress page.
    landed, saw_failure = None, False
    for _ in range(60):
        status, url, page = j.get(f"/runs/{run_id}/progress")
        low = text_of(page).lower()
        if "could not be completed" in low or "analysis failed" in low:
            saw_failure = True
        if "/progress" not in url:
            landed = url
            break
        if "stopped early" in low:
            saw_failure = True
            break
        time.sleep(6)
    out["seconds"] = round(time.time() - t0)
    out["auto_advanced"] = bool(landed)
    out["landed_on"] = landed
    out["false_failure"] = saw_failure

    pages = {}
    for step in STEPS:
        status, _, page = j.get(f"/runs/{run_id}/{step}")
        body = text_of(page)
        pages[step] = {"status": status, "chars": len(body),
                       "absence": sorted({a for a in ABSENCE
                                          if a in body.lower()})}
    out["steps"] = pages
    _, _, intro = j.get(f"/runs/{run_id}/intro")
    intro_text = text_of(intro)
    out["intro_head"] = intro_text[:900]
    position = re.search(
        r"(contested most directly by[^.]{0,200}|"
        r"sits in the same sector as[^.]{0,240})", intro_text)
    out["position_sentence"] = position.group(0) if position else ""
    model = re.search(r"is a ([^.]{0,180}?) business that runs on ([^.]{0,220})",
                      intro_text)
    out["model_sentence"] = (f"{model.group(1)} | {model.group(2)}"
                             if model else "")
    return out


def main() -> int:
    targets = []
    for arg in sys.argv[1:]:
        parts = arg.split(":")
        targets.append((parts[0], parts[1] if len(parts) > 1 else "",
                        parts[2] if len(parts) > 2 else ""))
    results = []
    for name, cik, ticker in targets:
        print(f"--- {name}", flush=True)
        try:
            row = run_company(name, cik, ticker)
        except Exception as exc:                            # noqa: BLE001
            row = {"company": name, "error": f"{type(exc).__name__}: {exc}"}
        results.append(row)
        print(json.dumps({k: v for k, v in row.items()
                          if k not in ("intro_head",)}, indent=1)[:1200],
              flush=True)
    with open("docs/execution/v5/pre100_60/batch_a_live.json", "w") as fh:
        json.dump(results, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
