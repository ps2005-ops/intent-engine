"""Core Web Vitals in a real browser, on the sessions perf_matrix.py opened.

Runs under a Python with Playwright (e.g. ~/job-application-agent/.venv);
imports nothing from intent_engine.

Conditions, per load:
  mobile   390x844, CPU slowed 4x, network 150 ms RTT / 1.6 Mbps down /
           750 kbps up (close to Lighthouse's "Slow 4G"), cache disabled
  desktop  1440x900, no throttling

Measured in the page with PerformanceObserver (buffered):
  LCP   largest-contentful-paint, last candidate before the first input
  CLS   sum of layout-shift values without recent input
  TTFB  responseStart from the navigation entry
  INP   the slowest Event Timing duration over real interactions driven
        through the browser's input pipeline: clicking up to three disclosure
        toggles (<summary>) or in-page controls that do not navigate. A page
        with no such control reports INP as NOT_MEASURED, never as zero.

Usage:
  ~/job-application-agent/.venv/bin/python scripts/prospect100/vitals.py \
      --base http://127.0.0.1:8601 --sessions DIR/sessions.json --out DIR/vitals.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import statistics

SURFACES = ("intro", "story", "full", "brief", "history", "connect")

_INIT = """
window.__v = {lcp: null, cls: 0, inp: null, events: 0};
new PerformanceObserver(l => { for (const e of l.getEntries())
  window.__v.lcp = e.renderTime || e.loadTime || e.startTime; })
  .observe({type: 'largest-contentful-paint', buffered: true});
new PerformanceObserver(l => { for (const e of l.getEntries())
  if (!e.hadRecentInput) window.__v.cls += e.value; })
  .observe({type: 'layout-shift', buffered: true});
new PerformanceObserver(l => { for (const e of l.getEntries()) {
  if (!e.interactionId) continue;
  window.__v.events += 1;
  window.__v.inp = Math.max(window.__v.inp || 0, e.duration); } })
  .observe({type: 'event', durationThreshold: 16, buffered: true});
"""

_READ = """() => {
  const n = performance.getEntriesByType('navigation')[0];
  return {lcp: window.__v.lcp, cls: window.__v.cls, inp: window.__v.inp,
          events: window.__v.events, ttfb: n ? n.responseStart : null};
}"""


async def _one(page, url, *, interact: bool):
    await page.goto(url, wait_until="load", timeout=120000)
    await page.wait_for_timeout(1500)
    clicked = 0
    if interact:
        for sel in ("summary", "button[type=button]", "[aria-expanded]"):
            for el in (await page.query_selector_all(sel))[:3 - clicked]:
                try:
                    if await el.is_visible():
                        await el.click(timeout=3000)
                        clicked += 1
                        await page.wait_for_timeout(300)
                except Exception:                              # noqa: BLE001
                    continue
            if clicked >= 3:
                break
        await page.wait_for_timeout(500)
    v = await page.evaluate(_READ)
    v["interactions"] = clicked
    if not clicked:
        v["inp"] = "NOT_MEASURED"
    elif v["inp"] is None:
        # Interactions happened and none crossed the 16 ms threshold.
        v["inp"] = "<16"
    return v


async def run(args):
    from playwright.async_api import async_playwright
    sessions = json.loads(pathlib.Path(args.sessions).read_text())
    host = args.base.split("//", 1)[1].split(":")[0]
    out = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for s in sessions:
            for profile in ("mobile", "desktop"):
                ctx = await browser.new_context(
                    viewport=({"width": 390, "height": 844} if profile == "mobile"
                              else {"width": 1440, "height": 900}),
                    is_mobile=(profile == "mobile"), has_touch=(profile == "mobile"))
                await ctx.add_cookies([{"name": c["name"], "value": c["value"],
                                        "domain": host, "path": c["path"]}
                                       for c in s["cookies"]])
                await ctx.add_init_script(_INIT)
                page = await ctx.new_page()
                cdp = await ctx.new_cdp_session(page)
                if profile == "mobile":
                    await cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
                    await cdp.send("Network.enable")
                    await cdp.send("Network.emulateNetworkConditions", {
                        "offline": False, "latency": 150,
                        "downloadThroughput": 1.6 * 1024 * 1024 / 8,
                        "uploadThroughput": 750 * 1024 / 8})
                    await cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
                for surface in SURFACES:
                    url = f"{args.base}/runs/{s['run_id']}/{surface}"
                    try:
                        v = await _one(page, url, interact=True)
                    except Exception as exc:                  # noqa: BLE001
                        v = {"error": str(exc)[:160]}
                    v.update(company=s["company"], surface=surface, profile=profile)
                    out.append(v)
                    print(profile, s["company"][:14], surface, {k: v.get(k) for k in
                          ("ttfb", "lcp", "cls", "inp", "interactions", "error")},
                          flush=True)
                await ctx.close()
        await browser.close()

    def p75(xs):
        xs = sorted(x for x in xs if isinstance(x, (int, float)))
        return round(xs[max(0, int(0.75 * len(xs) + 0.5) - 1)], 3) if xs else None

    summary = {}
    for profile in ("mobile", "desktop"):
        rows = [r for r in out if r["profile"] == profile and "error" not in r]
        inp = [r["inp"] for r in rows if isinstance(r["inp"], (int, float))]
        under16 = sum(1 for r in rows if r["inp"] == "<16")
        summary[profile] = {
            "loads": len(rows),
            "errors": sum(1 for r in out if r["profile"] == profile and "error" in r),
            "lcp_p75_ms": p75([r["lcp"] for r in rows]),
            "cls_p75": p75([r["cls"] for r in rows]),
            "cls_max": round(max((r["cls"] for r in rows), default=0), 4),
            "ttfb_p75_ms": p75([r["ttfb"] for r in rows]),
            # An interaction under the 16 ms Event Timing threshold is not
            # reported by the browser, so it is counted AT 16 ms -- an upper
            # bound, never an invented smaller number.
            "inp_p75_ms": p75(inp + [16] * under16) if (inp or under16) else None,
            "inp_measured_loads": len(inp) + under16,
            "inp_not_measured_loads": sum(1 for r in rows if r["inp"] == "NOT_MEASURED"),
            "lcp_over_2500": [f"{r['company']}/{r['surface']}" for r in rows
                              if (r["lcp"] or 0) > 2500],
        }
    pathlib.Path(args.out).write_text(json.dumps(
        {"conditions": __doc__.split("Measured")[0].strip(), "summary": summary,
         "loads": out}, indent=1))
    print(json.dumps(summary, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--sessions", required=True)
    ap.add_argument("--out", required=True)
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
