"""Wave 5 (local): status pages and search, every width x theme, in a real browser.

For each of the five status-only companies, types the legal name on /demo,
submits, and records on the resulting page, per viewport and colour scheme:
  * HTTP status, final URL, whether a run was opened (it must not be);
  * whether the page says the company is no longer independent;
  * whether it names and links the acquirer (successor navigation);
  * horizontal overflow (scrollWidth > innerWidth), console errors, failed
    same-origin requests;
  * a screenshot.
Also measures /api/companies for all 100 listed names (exact-name rank 1).

Local only: the base URL is a local server. Nothing here is a production
measurement.

Usage:
  .venv/bin/python scripts/prospect100/resume/status_and_search_matrix.py \
      --base http://127.0.0.1:8611 --out docs/engineering/prospect100/resume/wave5
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[3]
WIDTHS = (375, 390, 768, 1024, 1440)
SCHEMES = ("light", "dark")


def search_matrix(base):
    reg = yaml.safe_load(open(ROOT / "docs/engineering/prospect100/"
                              "PROSPECT_REGISTRY.yaml"))["prospects"]
    rows, lat = [], []
    for r in reg:
        for typed in {r.get("common_name") or r["name_as_listed"], r.get("legal_name") or r["name_as_listed"]}:
            t0 = time.perf_counter()
            body = urllib.request.urlopen(
                f"{base}/api/companies?q={urllib.parse.quote(typed)}",
                timeout=30).read()
            lat.append((time.perf_counter() - t0) * 1000)
            got = json.loads(body).get("companies") or []
            first = got[0]["entity_id"] if got else None
            rows.append({"prospect_id": r["prospect_id"], "typed": typed,
                         "expected": r["entity_id"], "first": first,
                         "rank1": first == r["entity_id"],
                         "in_list": r["entity_id"] in [g["entity_id"] for g in got]})
    lat.sort()
    q = lambda p: round(lat[min(len(lat) - 1, int(p * len(lat)))], 1)
    return {"queries": len(rows),
            "rank1": sum(x["rank1"] for x in rows),
            "in_list": sum(x["in_list"] for x in rows),
            "misses": [x for x in rows if not x["rank1"]],
            "latency_ms_local": {"p50": q(.5), "p95": q(.95), "p99": q(.99),
                                 "mean": round(statistics.mean(lat), 1)}}


def status_matrix(base, out):
    reg = yaml.safe_load(open(ROOT / "docs/engineering/prospect100/"
                              "PROSPECT_REGISTRY.yaml"))["prospects"]
    # Only companies the registry stops at the door. An ownership change that
    # leaves the business operating (ACQUIRED_OPERATING, TAKEN_PRIVATE,
    # RENAMED_SUCCESSOR) correctly opens an analysis.
    stops = [r for r in reg
             if str(r.get("entry_readiness", "")).startswith("STOP_")]
    shots = out / "screens"
    shots.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("PW_CHROMIUM", "/opt/pw-browsers/chromium"))
        for r in stops:
            cs = r["corporate_status"]
            for scheme in SCHEMES:
                for w in WIDTHS:
                    ctx = browser.new_context(
                        viewport={"width": w, "height": 900 if w > 500 else 812},
                        color_scheme=scheme, device_scale_factor=1)
                    page = ctx.new_page()
                    console, failed = [], []
                    page.on("console", lambda m: console.append(m.text)
                            if m.type == "error" else None)
                    page.on("requestfailed", lambda q: failed.append(q.url)
                            if q.url.startswith(base) else None)
                    page.goto(f"{base}/login", wait_until="networkidle")
                    page.fill("#email", os.environ.get("QUAL_EMAIL", "qual@local.test"))
                    page.fill("#password", os.environ["QUAL_PASSWORD"])
                    with page.expect_navigation():
                        page.click("form[action='/login'] [type=submit]")
                    console.clear(); failed.clear()
                    t0 = time.perf_counter()
                    page.goto(f"{base}/demo", wait_until="networkidle")
                    box = page.locator("input[name=company_name]").first
                    box.fill(r["legal_name"])
                    consent = page.locator("input[name=consent]")
                    if consent.count() and consent.first.is_visible():
                        try:
                            consent.first.check()
                        except Exception:                    # noqa: BLE001
                            pass
                    with page.expect_navigation(wait_until="networkidle"):
                        page.locator("form:has(input[name=company_name]) "
                                     "[type=submit]").first.click()
                    elapsed = (time.perf_counter() - t0) * 1000
                    text = page.inner_text("body")
                    overflow = page.evaluate(
                        "document.documentElement.scrollWidth - window.innerWidth")
                    succ = re.sub(r",?\s*(Inc|Ltd|LLC|plc|S\.A)\.?$", "",
                                  cs.get("counterparty") or "").strip()
                    links = page.eval_on_selector_all(
                        "a[href]", "els => els.map(e => [e.innerText, e.href])")
                    succ_link = any(
                        (cs.get("counterparty_domain") or "~") in h or
                        (succ and succ.split()[0].strip(",.").lower() in (t or "").lower())
                        for t, h in links)
                    name = f"{r['entity_id']}-{w}-{scheme}.png"
                    page.screenshot(path=str(shots / name), full_page=True)
                    res = {
                        "entity_id": r["entity_id"], "width": w, "scheme": scheme,
                        "final_url": page.url.replace(base, ""),
                        "opened_run": "/runs/" in page.url,
                        "says_not_independent": bool(re.search(
                            r"is now part of|no longer operates|acquired",
                            text, re.I)),
                        "names_successor": bool(succ) and succ.split()[0].strip(",.") in text,
                        "successor_link": succ_link,
                        "h_overflow_px": overflow,
                        "console_errors": console,
                        "failed_requests": failed,
                        "submit_to_page_ms_local": round(elapsed),
                        "screenshot": f"screens/{name}",
                    }
                    res["pass"] = (not res["opened_run"] and
                                   res["says_not_independent"] and
                                   res["names_successor"] and
                                   overflow <= 0 and not console and not failed)
                    results.append(res)
                    ctx.close()
        browser.close()
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8611")
    ap.add_argument("--out", default=str(ROOT / "docs/engineering/prospect100/"
                                         "resume/wave5"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    s = search_matrix(a.base)
    (out / "search_local.json").write_text(json.dumps(s, indent=1))
    print("search", {k: v for k, v in s.items() if k != "misses"},
          "misses:", [(m["typed"], m["first"]) for m in s["misses"]])
    st = status_matrix(a.base, out)
    (out / "status_pages_local.json").write_text(json.dumps(st, indent=1))
    bad = [x for x in st if not x["pass"]]
    print(f"status cells {len(st)}; pass {len(st) - len(bad)}")
    for b in bad[:40]:
        print(" FAIL", b["entity_id"], b["width"], b["scheme"],
              {k: b[k] for k in ("opened_run", "says_not_independent",
                                 "names_successor", "h_overflow_px",
                                 "console_errors", "failed_requests")})


if __name__ == "__main__":
    main()
