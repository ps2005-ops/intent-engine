#!/usr/bin/env python3
"""§13. The deployed customer journey, captured route by route, in full.

WHY THIS REPLACES THE EARLIER HARNESSES. They proved the journey ran and
recorded character counts and one sentence each. The governing rule for this
phase is that nothing counts until it is verified through the deployed
customer UI, and a character count is not a verification: the previous pass
scored a competitive repair from a backend object and shipped it inert twice.

This walks landing -> try demo -> entry -> analyse -> progress -> the six
steps -> Q&A, and writes every rendered page to disk WHOLE, plus the sources
and evidence routes, so a score can be checked against the text a customer
actually saw.

Usage:
  python scripts/pre100_ui_journey.py OUTDIR "Name:CIK:TICKER"
"""
from __future__ import annotations

import html
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("PRE100_BASE",
                      "https://intent-engine-preview-bridge.onrender.com")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

#: The six customer steps, in the order the product walks them.
STEPS = ["intro", "slides", "full", "story", "history", "connect"]
#: Routes a reader can reach from the steps, captured for the matrix.
EXTRA = ["sources", "report", "answer", "evidence", "brief", "dashboard"]

#: §14. Copy that means the product gave up, OR that it bounded itself
#: honestly. The two are NOT the same and the classification is the point,
#: so they are captured separately rather than counted together.
FAILURE_LANGUAGE = [
    "analysis failed", "could not be completed", "no result to show",
    "internal failure", "something went wrong",
]
ABSENCE_LANGUAGE = [
    "no strategic reading", "not retrieved", "no data available",
    "no estimate retrieved", "nothing found", "unable to determine",
    "no competitor", "no history available", "no market expectation",
    "not available", "unavailable",
]
BOUNDED_LANGUAGE = [
    "limited analysis", "some kinds of evidence are missing",
    "bounded", "where it stands",
]

BOARD_QUESTIONS = [
    "What should management do?",
    "Why now?",
    "What's the biggest risk?",
    "What would prove this wrong?",
    "Who's the real competitor?",
    "What does the market believe?",
    "What's the weakest assumption?",
    "What impossible hypothesis should we test?",
    "What should we measure next?",
    "What would you tell the board?",
]


def text_of(page: str) -> str:
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", html.unescape(body)).strip()


def classify(body: str) -> dict:
    low = body.lower()
    return {
        "failure": sorted({p for p in FAILURE_LANGUAGE if p in low}),
        "absence": sorted({p for p in ABSENCE_LANGUAGE if p in low}),
        "bounded": sorted({p for p in BOUNDED_LANGUAGE if p in low}),
    }


class UI:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.o = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.errors: list = []

    def get(self, path):
        req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
        try:
            with self.o.open(req, timeout=150) as r:
                return r.status, r.geturl(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, BASE + path, e.read().decode("utf-8", "replace")
        except Exception as exc:                            # noqa: BLE001
            self.errors.append(f"GET {path}: {type(exc).__name__}")
            return 0, BASE + path, ""

    def post(self, path, data, ref="/demo"):
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(BASE + path, data=body, headers={
            "User-Agent": UA, "Origin": BASE, "Referer": BASE + ref,
            "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with self.o.open(req, timeout=200) as r:
                return r.status, r.geturl(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, BASE + path, e.read().decode("utf-8", "replace")
        except Exception as exc:                            # noqa: BLE001
            self.errors.append(f"POST {path}: {type(exc).__name__}")
            return 0, BASE + path, ""

    @staticmethod
    def csrf(page):
        m = re.search(r'name="csrf" value="([^"]+)"', page)
        return m.group(1) if m else ""


def journey(name, cik, ticker, outdir):
    ui = UI()
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    d = os.path.join(outdir, slug)
    os.makedirs(d, exist_ok=True)
    out = {"company": name, "cik": cik, "ticker": ticker, "routes": {},
           "progress": []}

    ui.get("/")
    ui.post("/demo", {})
    _, _, entry = ui.get("/demo")
    csrf = UI.csrf(entry)
    if not csrf:
        out["error"] = "no csrf on the entry page"
        json.dump(out, open(os.path.join(d, "run.json"), "w"), indent=2)
        return out

    t0 = time.time()
    st, url, page = ui.post("/analyze", {
        "csrf": csrf, "consent": "on", "company_name": name,
        "suggest_confirmed": name, "suggest_cik": cik,
        "suggest_ticker": ticker})
    if "/runs/" not in url:
        out["error"] = f"analyze did not open a run (HTTP {st})"
        out["entry_text"] = text_of(page)[:800]
        json.dump(out, open(os.path.join(d, "run.json"), "w"), indent=2)
        return out
    run_id = url.split("/runs/")[1].split("/")[0]
    out["run_id"] = run_id

    landed = None
    for i in range(75):
        st, purl, page = ui.get(f"/runs/{run_id}/progress")
        body = text_of(page)
        if i < 4 or i % 12 == 0:
            out["progress"].append({"poll": i, "text": body[:400]})
        if "/progress" not in purl:
            landed = purl
            break
        time.sleep(6)
    out["seconds"] = round(time.time() - t0)
    out["auto_advanced"] = bool(landed)
    out["landed_on"] = landed

    for route in ["", *STEPS, *EXTRA]:
        path = f"/runs/{run_id}" + (f"/{route}" if route else "")
        st, rurl, raw = ui.get(path)
        body = text_of(raw)
        key = route or "run"
        with open(os.path.join(d, f"{key}.txt"), "w") as fh:
            fh.write(body)
        if key in ("full", "slides", "history"):
            with open(os.path.join(d, f"{key}.html"), "w") as fh:
                fh.write(raw)
        title = re.search(r"(?is)<title>(.*?)</title>", raw)
        out["routes"][key] = {
            "status": st, "final_url": rurl, "chars": len(body),
            "title": html.unescape(title.group(1)).strip() if title else "",
            "names_company": name.split(",")[0].split(" Inc")[0] in body,
            "language": classify(body),
            "charts": raw.count("<svg") + raw.count("<canvas"),
            "nav_next": bool(re.search(r"(?i)>\s*(next|continue)", raw)),
            "nav_back": bool(re.search(r"(?i)>\s*(back|previous)", raw)),
        }

    _, _, answer_page = ui.get(f"/runs/{run_id}/answer")
    tok = UI.csrf(answer_page) or csrf
    qa = {}
    for q in BOARD_QUESTIONS:
        st, _, raw = ui.post(f"/runs/{run_id}/conversation",
                             {"csrf": tok, "question": q},
                             ref=f"/runs/{run_id}/answer")
        body = text_of(raw)
        qa[q] = {"status": st, "text": body}
        tok = UI.csrf(raw) or tok
    out["qa"] = qa
    json.dump(qa, open(os.path.join(d, "qa.json"), "w"), indent=2)

    out["transport_errors"] = ui.errors
    json.dump(out, open(os.path.join(d, "run.json"), "w"), indent=2)
    return out


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    for arg in sys.argv[2:]:
        parts = arg.split(":")
        name = parts[0]
        print(f"--- {name}", flush=True)
        try:
            row = journey(name, parts[1] if len(parts) > 1 else "",
                          parts[2] if len(parts) > 2 else "", outdir)
        except Exception as exc:                            # noqa: BLE001
            row = {"company": name, "error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps({k: v for k, v in row.items()
                          if k in ("run_id", "seconds", "auto_advanced",
                                   "error")}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
