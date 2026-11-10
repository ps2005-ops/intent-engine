"""Browser matrix over every captured surface: 10 widths x 2 themes.

Runs under any Python with Playwright installed (this repo's venv has none;
`~/job-application-agent/.venv` does, and the script imports nothing from
intent_engine). The captures are the bytes the server returned -- the app
inlines its CSS -- so a saved page lays out as the served one did. Loaded
from file://, so no server and no session are involved; navigation and server
time are measured separately (perf_matrix.py).

Per page, per width, per theme, measured in the page itself:

  overflow      document wider than the viewport (horizontal page scroll)
  offenders     the widest elements causing it, outside any element that is
                allowed to scroll sideways (overflow-x auto/scroll)
  small_targets interactive elements smaller than 24x24 CSS px (WCAG 2.2
                2.5.8), excluding inline links inside running text, which the
                criterion exempts
  contrast      text elements below 4.5:1 (3:1 for large text), computed
                from the resolved colours against the first opaque ancestor
                background
  missing_alt   <img> without alt; role=img without an accessible name
  h1 / main     landmark counts (exactly one of each expected)
  dark_applied  in dark emulation, the body background is actually dark
  focus_visible once per page (390 px, light): Tab to the first focusable
                element and require a visible outline or box-shadow

Usage:
  ~/job-application-agent/.venv/bin/python scripts/prospect100/ui_matrix.py \
      --captures reports/prospect100_pass3/captures --out docs/.../ui_matrix.json \
      [--screens DIR --screen-slugs a,b,c] [--workers 6]
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import json
import pathlib
import time

WIDTHS = (320, 375, 390, 430, 768, 820, 1024, 1280, 1440, 1920)
THEMES = ("light", "dark")
HEIGHT = 900

_PROBE = r"""
() => {
  const W = window.innerWidth;
  const de = document.documentElement, b = document.body;
  const sw = Math.max(de.scrollWidth, b ? b.scrollWidth : 0);
  const scrollsX = el => {
    for (let p = el.parentElement; p && p !== b; p = p.parentElement) {
      const o = getComputedStyle(p).overflowX;
      if (o === 'auto' || o === 'scroll' || o === 'hidden') return true;
    }
    return false;
  };
  // Visually-hidden text (the .sr pattern: 1px, clipped) is for screen
  // readers and is never painted for a sighted reader to read.
  const visible = el => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (r.width <= 1 || r.height <= 1) return false;
    if (cs.clip && cs.clip.startsWith('rect(0')) return false;
    if (cs.clipPath && cs.clipPath.includes('inset(50%')) return false;
    return cs.visibility !== 'hidden' && cs.display !== 'none' &&
           parseFloat(cs.opacity) > 0;
  };
  const label = el => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    else if (el.className && typeof el.className === 'string')
      s += '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.');
    return s;
  };
  // ---- overflow offenders
  const offenders = [];
  if (sw > W + 1) {
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (r.right > W + 1 && r.width > 0 && !scrollsX(el)) {
        offenders.push([label(el), Math.round(r.right - W)]);
        if (offenders.length >= 4) break;
      }
    }
  }
  // ---- touch targets (WCAG 2.5.8, inline-in-text exempt)
  // WCAG 2.5.8 has two exceptions this honours: an inline link in running
  // text, and SPACING -- an undersized target passes when a 24px circle on
  // its centre intersects no other target (nor another undersized target's
  // circle). Without the spacing rule a well-spaced nav row reads as failing.
  let small = 0; const smallEx = [];
  const targets = [...document.querySelectorAll(
      'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button]')]
      .filter(visible).map(el => ({el, r: el.getBoundingClientRect()}));
  const under = t => t.r.width < 24 || t.r.height < 24;
  const centre = t => [t.r.left + t.r.width / 2, t.r.top + t.r.height / 2];
  const distToRect = ([x, y], r) => {
    const dx = Math.max(r.left - x, 0, x - r.right);
    const dy = Math.max(r.top - y, 0, y - r.bottom);
    return Math.hypot(dx, dy);
  };
  for (const t of targets) {
    if (!under(t)) continue;
    const cs = getComputedStyle(t.el);
    if (t.el.tagName === 'A' && cs.display === 'inline' &&
        t.el.closest('p, li, dd, td, figcaption, blockquote, q, span.src'))
      continue;                        // inline link in running text: exempt
    const c = centre(t);
    let crowded = false;
    for (const o of targets) {
      if (o === t || o.el.contains(t.el) || t.el.contains(o.el)) continue;
      const d = under(o) ? Math.hypot(c[0] - centre(o)[0], c[1] - centre(o)[1]) < 24
                         : distToRect(c, o.r) < 12;
      if (d) { crowded = true; break; }
    }
    if (!crowded) continue;            // spacing exception
    small += 1;
    if (smallEx.length < 3) smallEx.push([label(t.el), Math.round(t.r.width), Math.round(t.r.height)]);
  }
  // ---- contrast
  const parse = c => {
    const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const v = m[1].split(',').map(x => parseFloat(x));
    return {r: v[0], g: v[1], b: v[2], a: v.length > 3 ? v[3] : 1};
  };
  const lum = c => {
    const f = x => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  // A background IMAGE (a gradient hero) has no single colour, so text over
  // one is reported as unmeasurable, never as failing: the first version
  // walked past the gradient to the white body and reported every hero
  // heading at 1.23:1 -- a uniform defect, which is an instrument tell.
  const bgOf = el => {
    for (let p = el; p; p = p.parentElement) {
      const st = getComputedStyle(p);
      if (st.backgroundImage && st.backgroundImage !== 'none') return null;
      const c = parse(st.backgroundColor);
      if (c && c.a > 0.5) return c;
    }
    // NOTHING OPAQUE ALL THE WAY UP: the browser paints its canvas, which
    // is white -- or near-black only when the page opts into a dark colour
    // scheme and the dark preference is active. The first version parsed the
    // transparent root as rgb(0,0,0) and scored dark text at 1.23:1.
    const scheme = getComputedStyle(de).colorScheme || '';
    const darkCanvas = scheme.includes('dark') &&
        matchMedia('(prefers-color-scheme: dark)').matches;
    return darkCanvas ? {r: 18, g: 18, b: 18, a: 1} : {r: 255, g: 255, b: 255, a: 1};
  };
  let checked = 0, lowC = 0, minC = 99, unmeasured = 0; const lowEx = [];
  for (const el of document.querySelectorAll(
      'p, li, h1, h2, h3, h4, dt, dd, td, th, a, button, label, figcaption, span, small, q')) {
    if (checked >= 400) break;
    if (!visible(el)) continue;
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1);
    if (!own) continue;
    const cs = getComputedStyle(el);
    const fg = parse(cs.color); if (!fg) continue;
    const bg = bgOf(el);
    if (!bg) { unmeasured += 1; continue; }
    const L1 = lum(fg), L2 = lum(bg);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700;
    const large = size >= 24 || (bold && size >= 18.66);
    checked += 1;
    minC = Math.min(minC, ratio);
    if (ratio < (large ? 3 : 4.5)) {
      lowC += 1;
      if (lowEx.length < 3) lowEx.push([label(el), Math.round(ratio * 100) / 100,
                                        el.textContent.trim().slice(0, 40)]);
    }
  }
  // ---- names
  let missingAlt = 0;
  for (const img of document.querySelectorAll('img')) if (!img.hasAttribute('alt')) missingAlt++;
  for (const el of document.querySelectorAll('[role=img]')) {
    const named = el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') ||
                  el.querySelector('title');
    if (!named) missingAlt++;
  }
  const bodyBg = parse(getComputedStyle(b).backgroundColor) || parse(getComputedStyle(de).backgroundColor);
  return {
    overflow: sw > W + 1, scroll_width: sw, offenders,
    small_targets: small, small_examples: smallEx,
    contrast_checked: checked, contrast_low: lowC, contrast_min: Math.round(minC * 100) / 100,
    contrast_examples: lowEx, contrast_unmeasured: unmeasured, missing_alt: missingAlt,
    h1: document.querySelectorAll('h1').length,
    main: document.querySelectorAll('main, [role=main]').length,
    body_luminance: bodyBg ? Math.round(lum(bodyBg) * 1000) / 1000 : null,
    dark_query: matchMedia('(prefers-color-scheme: dark)').matches,
  };
}
"""

_FOCUS = r"""
() => {
  const el = document.activeElement;
  if (!el || el === document.body) return {focused: false};
  const cs = getComputedStyle(el);
  const outline = cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0;
  const shadow = cs.boxShadow && cs.boxShadow !== 'none';
  return {focused: true, tag: el.tagName.toLowerCase(), visible: outline || shadow};
}
"""


async def _measure(browser, files, out, screens, screen_slugs, progress):
    ctx = await browser.new_context(viewport={"width": 390, "height": HEIGHT})
    page = await ctx.new_page()
    for f in files:
        slug, _, surface = f.stem.rpartition("-")
        url = f.resolve().as_uri()
        rows = {}
        for theme in THEMES:
            await page.emulate_media(color_scheme=theme)
            for width in WIDTHS:
                await page.set_viewport_size({"width": width, "height": HEIGHT})
                try:
                    await page.goto(url, wait_until="load", timeout=30000)
                    m = await page.evaluate(_PROBE)
                except Exception as exc:                      # noqa: BLE001
                    m = {"error": str(exc)[:200]}
                rows[f"{theme}:{width}"] = m
                if screens and slug in screen_slugs and width in (320, 768, 1440):
                    shot = screens / f"{slug}-{surface}-{width}-{theme}.jpg"
                    await page.screenshot(path=str(shot), type="jpeg",
                                          quality=55, full_page=False)
        # keyboard focus, once
        try:
            await page.emulate_media(color_scheme="light")
            await page.set_viewport_size({"width": 390, "height": HEIGHT})
            await page.goto(url, wait_until="load", timeout=30000)
            await page.keyboard.press("Tab")
            focus = await page.evaluate(_FOCUS)
        except Exception as exc:                              # noqa: BLE001
            focus = {"error": str(exc)[:200]}
        out.append({"slug": slug, "surface": surface, "file": f.name,
                    "matrix": rows, "focus": focus})
        progress[0] += 1
    await ctx.close()


def summarise(results):
    per_company = collections.defaultdict(lambda: collections.Counter())
    totals = collections.Counter()
    examples = collections.defaultdict(list)
    for r in results:
        c = per_company[r["slug"]]
        for key, m in r["matrix"].items():
            theme, width = key.split(":")
            totals["measurements"] += 1
            if m.get("error"):
                c["errors"] += 1; totals["errors"] += 1
                continue
            if m["overflow"]:
                c["overflow"] += 1; totals["overflow"] += 1
                if len(examples["overflow"]) < 12:
                    examples["overflow"].append((r["file"], key, m["offenders"][:2]))
            if m["small_targets"]:
                c["small_target_pages"] += 1; totals["small_target_pages"] += 1
                if len(examples["small_targets"]) < 12:
                    examples["small_targets"].append((r["file"], key, m["small_examples"][:2]))
            if m["contrast_low"]:
                c["contrast_pages"] += 1; totals["contrast_pages"] += 1
                if len(examples["contrast"]) < 12:
                    examples["contrast"].append((r["file"], key, m["contrast_examples"][:2]))
            if m["missing_alt"]:
                c["missing_alt"] += 1; totals["missing_alt"] += 1
            if theme == "dark" and (m.get("body_luminance") or 0) > 0.4:
                c["dark_not_applied"] += 1; totals["dark_not_applied"] += 1
            if m["h1"] != 1:
                c["h1_not_one"] += 1; totals["h1_not_one"] += 1
        f = r["focus"]
        if f.get("focused") and not f.get("visible"):
            c["focus_invisible"] += 1; totals["focus_invisible"] += 1
    status = {}
    for slug, c in per_company.items():
        hard = c["overflow"] + c["dark_not_applied"] + c["errors"]
        status[slug] = {"status": "PASS" if not hard and not c["contrast_pages"]
                        and not c["small_target_pages"] and not c["focus_invisible"]
                        else ("FAIL" if hard else "PASS_WITH_A11Y_FINDINGS"),
                        **dict(c)}
    return {"totals": dict(totals), "per_company": status,
            "examples": {k: v for k, v in examples.items()}}


async def main_async(args):
    from playwright.async_api import async_playwright
    files = sorted(pathlib.Path(args.captures).glob("*.html"))
    if args.slugs:
        keep = set(args.slugs.split(","))
        files = [f for f in files if f.stem.rpartition("-")[0] in keep]
    screens = pathlib.Path(args.screens) if args.screens else None
    if screens:
        screens.mkdir(parents=True, exist_ok=True)
    screen_slugs = set((args.screen_slugs or "").split(","))
    results, progress = [], [0]
    t0 = time.time()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        chunks = [files[i::args.workers] for i in range(args.workers)]
        await asyncio.gather(*(_measure(browser, c, results, screens,
                                        screen_slugs, progress)
                               for c in chunks if c))
        await browser.close()
    summary = summarise(results)
    summary["pages"] = len(files)
    summary["widths"] = list(WIDTHS)
    summary["themes"] = list(THEMES)
    summary["seconds"] = round(time.time() - t0, 1)
    pathlib.Path(args.out).write_text(json.dumps(
        {"summary": summary, "results": results}, indent=1))
    print(json.dumps({k: summary[k] for k in ("pages", "seconds", "totals")},
                     indent=1))
    for k, v in summary["examples"].items():
        print(k)
        for e in v[:6]:
            print("   ", e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--captures", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--slugs", default="")
    ap.add_argument("--screens", default="")
    ap.add_argument("--screen-slugs", default="")
    ap.add_argument("--workers", type=int, default=6)
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
