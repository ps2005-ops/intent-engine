#!/usr/bin/env python3
"""Drive the deployed guest journey and capture EVERYTHING a score needs.

WHY THIS REPLACES `batch_live_journey.py`. That harness proved the journey
runs; it recorded six character counts and one sentence. §14 of the gauntlet
forbids scoring a surface that was not read, and twenty dimensions cannot be
scored from a length. This walks the same customer path -- landing, try demo,
company entry, analyse, progress, the six steps -- and then keeps the session
open to ask the ten board questions through the product's own Q&A route.

Everything read is written to disk verbatim, one directory per company, so a
score can be checked against the text it came from rather than trusted.

Usage:
  python scripts/pre100_batch_journey.py OUTDIR "Meta Platforms, Inc.:1326801:META" ...
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import http.cookiejar

BASE = os.environ.get("PRE100_BASE",
                      "https://intent-engine-preview-bridge.onrender.com")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

#: The six the demo flow walks IN ORDER, then the surfaces a reader reaches
#: from them. `brief` is not optional: SIX scored dimensions read it --
#: market belief, belief challenge, recommendation, falsifier, MVE and the
#: capital picture -- and a harness that does not fetch it makes all six
#: NOT_MEASURED, which fails the gate for a reason that is about the harness.
#: MEASURED on the f8c183f canary: Microsoft scored core_min 3 with
#: `market_belief` and `recommendation` both "surface did not render", on a
#: run whose brief was sitting one request away.
STEPS = ["intro", "slides", "full", "story", "history", "connect",
         "brief", "evidence", "sources", "report"]

#: Copy that means the product gave up in front of a chief executive.
ABSENCE = [
    "no information available", "no knowledge available", "not retrieved",
    "nothing found", "unable to determine", "no strategic reading",
    "no reading cleared", "no estimate retrieved", "no history available",
    "no market expectation", "no evidence available", "no data available",
    "could not be completed", "analysis failed",
]

#: §29. The ten questions, asked of every company through the live Q&A route.
BOARD_QUESTIONS = [
    "What should management do?",
    "Why now?",
    "What would prove this wrong?",
    "What's the biggest risk?",
    "Who's the real competitor?",
    "What does the market believe?",
    "What's the weakest assumption?",
    "What impossible hypothesis should we test?",
    "What should we measure next?",
    "What would you tell the board?",
]


def _opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPRedirectHandler())


def text_of(page: str) -> str:
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", html.unescape(body)).strip()


class Journey:
    """One guest session. Kept alive so follow-ups can reach the same run."""

    def __init__(self):
        self.o = _opener()
        self.transport_errors: list = []

    def get(self, path):
        req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
        try:
            with self.o.open(req, timeout=120) as r:
                return r.status, r.geturl(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, BASE + path, e.read().decode("utf-8", "replace")
        except Exception as exc:                            # noqa: BLE001
            self.transport_errors.append(f"GET {path}: {type(exc).__name__}")
            return 0, BASE + path, ""

    def post(self, path, data, referer="/demo"):
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(
            BASE + path, data=body,
            headers={"User-Agent": UA, "Origin": BASE,
                     "Referer": BASE + referer,
                     "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with self.o.open(req, timeout=180) as r:
                return r.status, r.geturl(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, BASE + path, e.read().decode("utf-8", "replace")
        except Exception as exc:                            # noqa: BLE001
            self.transport_errors.append(f"POST {path}: {type(exc).__name__}")
            return 0, BASE + path, ""

    def csrf(self, page: str) -> str:
        m = re.search(r'name="csrf" value="([^"]+)"', page)
        return m.group(1) if m else ""


# --- readers ---------------------------------------------------------------
#
# Each pulls ONE claim out of the page a customer sees. They read rendered
# text rather than the backend object on purpose: §14 says a score must come
# from the deployed output, and an object that never reaches a surface has not
# been shown to anybody.

def position_sentence(intro_text: str) -> str:
    m = re.search(r"(contested most directly by[^.]{0,240}"
                  r"|customers can substitute[^.]{0,240}"
                  r"|an adjacent threat[^.]{0,240}"
                  r"|sits in the same sector as[^.]{0,260})", intro_text)
    return m.group(0) if m else ""


def model_sentence(intro_text: str) -> str:
    m = re.search(r"is an? ([^.]{0,180}?) business that runs on ([^.]{0,240})",
                  intro_text)
    return f"{m.group(1)} | {m.group(2)}" if m else ""


def competition_rows(full_text: str) -> list:
    """The alternatives table as a reader sees it, with the basis note."""
    m = re.search(r"(Of \d+ alternatives below:[^|]{0,600}?\.)", full_text)
    basis = m.group(1) if m else ""
    rows = re.findall(
        r"([A-Z][^.]{2,80}?)\s+(?:wins the same evaluation|solves one part|"
        r"changes what the customer is buying|turns the decision into|"
        r"is already in place|leaves the customer|includes the capability|"
        r"sets the price the customer|reaches the customer without|"
        r"automates the task|builds the same outcome|is available on terms|"
        r"removes the occasion|operates the same business model)", full_text)
    return {"basis_note": basis, "rows": [r.strip() for r in rows]}


def section(text: str, start: str, stop: tuple = ()) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    j = len(text)
    for s in stop:
        k = text.find(s, i + len(start))
        if 0 <= k < j:
            j = k
    return text[i:j].strip()


def run_company(name: str, cik: str = "", ticker: str = "",
                outdir: str = ".") -> dict:
    j = Journey()
    company_dir = os.path.join(outdir, re.sub(r"[^a-z0-9]+", "_",
                                              name.lower()).strip("_"))
    os.makedirs(company_dir, exist_ok=True)
    out = {"company": name, "cik": cik, "ticker": ticker,
           "reliability": {"connection_reset": 0, "quota_block": False,
                           "retry_required": 0, "manual_recovery": 0},
           "blocked_external": False, "blocked_sources": []}

    j.get("/")
    j.post("/demo", {})
    _, _, entry = j.get("/demo")
    csrf = j.csrf(entry)
    if not csrf:
        low = text_of(entry).lower()
        out["error"] = "no csrf on entry page"
        out["reliability"]["quota_block"] = ("demo" in low and
                                             ("limit" in low or "quota" in low))
        return out

    form = {"csrf": csrf, "consent": "on", "company_name": name,
            "suggest_confirmed": name}
    if cik:
        form["suggest_cik"] = cik
    if ticker:
        form["suggest_ticker"] = ticker
    t0 = time.time()
    status, url, page = j.post("/analyze", form)
    if "/runs/" not in url:
        low = text_of(page).lower()
        out["error"] = f"analyze did not open a run (HTTP {status})"
        out["entry_text"] = text_of(page)[:600]
        out["entry_status"] = status
        out["entry_body"] = page[:20000]
        out["reliability"]["quota_block"] = ("limit" in low or "quota" in low
                                             or status == 429)
        out["reliability"]["connection_reset"] = len(j.transport_errors)
        return out
    run_id = url.split("/runs/")[1].split("/")[0]
    out["run_id"] = run_id

    # AUTO-ADVANCE. A pass means the progress URL stops being the progress
    # page on its own, exactly as the page's meta refresh would drive it.
    landed, saw_failure, failure_text = None, False, ""
    for _ in range(70):
        status, purl, page = j.get(f"/runs/{run_id}/progress")
        body = text_of(page)
        low = body.lower()
        if "could not be completed" in low or "analysis failed" in low:
            saw_failure, failure_text = True, body[:900]
        if "/progress" not in purl:
            landed = purl
            break
        if "stopped early" in low:
            saw_failure, failure_text = True, body[:900]
            break
        time.sleep(6)
    out["seconds"] = round(time.time() - t0)
    out["auto_advanced"] = bool(landed)
    out["landed_on"] = landed
    out["claimed_failure"] = saw_failure
    out["failure_text"] = failure_text
    # §39/§40. A SOURCE THE PRODUCT COULD NOT REACH IS NOT A PRODUCT DEFECT.
    #
    # MEASURED on 4952649: SEC EDGAR answered HTTP 429 to the preview's
    # egress for every company, while the same URLs with the same
    # User-Agent answered 200 from a laptop. That is a shared cloud IP being
    # throttled, and scoring it as a failed analysis would put an
    # infrastructure limit into the product's quality numbers. It is
    # recorded, loudly, and separately.
    low = (failure_text or "").lower()
    out["blocked_external"] = bool(
        re.search(r"rate.?limit|http 429|429\b|temporarily unavailable", low))
    out["blocked_sources"] = re.findall(
        r"(SEC [A-Z0-9\-]+[^—]*?) — ([a-z ]+)\s*:", failure_text or "")[:6]

    # --- the six steps, captured whole ------------------------------------
    pages, texts = {}, {}
    for step in STEPS:
        status, surl, raw = j.get(f"/runs/{run_id}/{step}")
        body = text_of(raw)
        texts[step] = body
        with open(os.path.join(company_dir, f"{step}.txt"), "w") as fh:
            fh.write(body)
        # THE RAW PAGE TOO, for the full analysis. `text_of` flattens an
        # aria-label and a chart's text alternative into the visible stream,
        # so a sentence that appears three times in the extract may appear
        # once on the screen. A duplication claim needs the markup.
        if step == "full":
            with open(os.path.join(company_dir, "full.html"), "w") as fh:
                fh.write(raw)
        pages[step] = {"status": status, "url": surl, "chars": len(body),
                       "absence": sorted({a for a in ABSENCE
                                          if a in body.lower()})}
        # §2.6. EVERY NON-2xx KEEPS ITS BODY.
        #
        # Nine surfaces answered HTTP 500 on two live runs and all that
        # survived was the integer. The body carries the product's own error
        # reference, which is the only thread back to the server log, and
        # `text_of` had already discarded it by the time anyone looked.
        if not str(status).startswith("2"):
            pages[step]["body"] = raw[:20000]
            pages[step]["text"] = body[:4000]
    out["steps"] = pages

    intro, full, story = texts["intro"], texts["full"], texts["story"]
    out["intro_head"] = intro[:900]
    out["position_sentence"] = position_sentence(intro)
    out["model_sentence"] = model_sentence(intro)
    out["competition"] = competition_rows(full)

    # §24/§25 the belief block, §27 the three history paths, §28 step 6.
    out["belief"] = section(
        full, "What the market believes",
        ("What would change our mind", "The alternatives", "History"))[:2600]
    out["history_paths"] = sorted(set(re.findall(
        r"(What actually happened|What the market expected|"
        r"A better strategy|Actual|Market expectation|Better strategy)",
        texts["history"])))
    out["history_vintages"] = sorted(
        set(re.findall(r"\b(?:19|20)\d{2}\b", texts["history"])))[:14]
    out["connect_text"] = texts["connect"][:3000]

    # --- §29 the ten board questions, through the product's own route ------
    _, _, answer_page = j.get(f"/runs/{run_id}/answer")
    csrf2 = j.csrf(answer_page) or j.csrf(full) or csrf
    answers = {}
    for q in BOARD_QUESTIONS:
        status, aurl, raw = j.post(f"/runs/{run_id}/conversation",
                                   {"csrf": csrf2, "question": q},
                                   referer=f"/runs/{run_id}/answer")
        body = text_of(raw)
        # The answer page repeats the chrome; keep the part after the question.
        idx = body.find(q)
        answers[q] = {"status": status,
                      "text": (body[idx + len(q):idx + len(q) + 1400]
                               if idx >= 0 else body[:1400])}
        csrf2 = j.csrf(raw) or csrf2
    out["qa"] = answers
    with open(os.path.join(company_dir, "qa.json"), "w") as fh:
        json.dump(answers, fh, indent=2)

    out["reliability"]["connection_reset"] = len(j.transport_errors)
    out["transport_errors"] = j.transport_errors
    with open(os.path.join(company_dir, "run.json"), "w") as fh:
        json.dump(out, fh, indent=2)
    return out


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    targets = []
    for arg in sys.argv[2:]:
        parts = arg.split(":")
        targets.append((parts[0], parts[1] if len(parts) > 1 else "",
                        parts[2] if len(parts) > 2 else ""))
    results = []
    for name, cik, ticker in targets:
        print(f"--- {name}", flush=True)
        try:
            row = run_company(name, cik, ticker, outdir)
        except Exception as exc:                            # noqa: BLE001
            row = {"company": name, "error": f"{type(exc).__name__}: {exc}"}
        results.append(row)
        print(json.dumps({k: v for k, v in row.items()
                          if k in ("run_id", "seconds", "auto_advanced",
                                   "claimed_failure", "blocked_external",
                                   "position_sentence",
                                   "model_sentence", "error", "reliability")},
                         indent=1)[:1400], flush=True)
        with open(os.path.join(outdir, "batch.json"), "w") as fh:
            json.dump(results, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
