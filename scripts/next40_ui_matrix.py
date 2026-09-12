#!/usr/bin/env python3
"""§17 UI matrix for forty companies: 5 widths x 2 themes, no sampling.

TWO KINDS OF CHECK, AND ONLY ONE OF THEM NEEDS A BROWSER.

The textual defects -- a raw enum on a customer surface, a literal "None", an
internal engineering word, an unbreakable 90-character URL, a stale spinner,
missing navigation -- are properties of the HTML. They are measured here for
every company and every surface, free, with no renderer involved.

Overflow and contrast are properties of LAYOUT and genuinely need a browser.
Forty companies x five widths x two themes x several surfaces is 1,200+
measurements, and driving that as 1,200 navigations is how a matrix becomes a
sample. So this writes ONE harness page per company that embeds its surfaces
in iframes at all five widths; the browser then measures every width in a
single pass, twice (light and dark). Eighty navigations, no sampling.

The captures are the same bytes the live run returned -- the app inlines its
CSS, so a saved page lays out as the served one did.
"""
from __future__ import annotations

import argparse
import html as _html
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
WIDTHS = (375, 390, 768, 1280, 1440)
THEMES = ("light", "dark")
SURFACES = ("intro", "brief", "full", "history", "evidence", "xray")

#: A constant that escaped to a customer surface. Deliberately narrow: it must
#: match SCREAMING_SNAKE and not a form type ("10-K"), a ticker or a country.
_ENUM = re.compile(r"\b[A-Z][A-Z0-9]{2,}(?:_[A-Z0-9]+)+\b")
#: Engineering vocabulary with no business meaning to a reader.
_INTERNAL = re.compile(
    r"\b(traceback|stacktrace|nonetype|dataclass|kwargs|null pointer|"
    r"not implemented|todo|fixme|assertion|httperror|json decode|"
    r"keyerror|attributeerror|typeerror)\b", re.I)
_LITERAL_NONE = re.compile(r"(?<![A-Za-z])(None|null|nan|undefined)(?![A-Za-z])")
_SPINNER = re.compile(r"(still working|analysing|analyzing|please wait|"
                      r"loading)", re.I)


def _visible(raw: str) -> str:
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw or "",
                  flags=re.S | re.I)
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", body)).split())


def scan_html(raw: str, *, terminal: bool = True) -> dict:
    """Every textual defect §17 names. Returns counts AND the evidence."""
    text = _visible(raw)
    enums = sorted({m for m in _ENUM.findall(text)})
    internal = sorted({m.lower() for m in _INTERNAL.findall(text)})
    nones = sorted({m for m in _LITERAL_NONE.findall(text)})
    # The longest token that cannot be broken: the real overflow risk at 375px.
    tokens = [t for t in re.findall(r"\S+", text) if len(t) > 24]
    longest = max((len(t) for t in tokens), default=0)
    spinner = bool(_SPINNER.search(text)) and terminal
    nav = bool(re.search(r"<a [^>]*href=", raw or "", re.I))
    # Identical long paragraphs on ONE page.
    paras = [_visible(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", raw or "",
                                             re.S | re.I)]
    longs = [p for p in paras if len(p) > 120]
    dupes = len(longs) - len(set(longs))
    return {"chars": len(text), "raw_enums": enums, "internal": internal,
            "literal_none": nones, "longest_token": longest,
            "stale_spinner": spinner, "has_nav": nav,
            "duplicate_paragraphs": dupes,
            "longest_token_sample": max(tokens, key=len)[:120]
            if tokens else ""}


def harness_page(company: str, captures: dict) -> str:
    """One page embedding one company's surfaces at all five widths."""
    frames = []
    for name, rel in sorted(captures.items()):
        for width in WIDTHS:
            frames.append(
                f'<div class="cell"><p class="lab">{_html.escape(name)} '
                f'@{width}</p>'
                f'<iframe data-surface="{_html.escape(name)}" '
                f'data-width="{width}" width="{width}" height="900" '
                f'loading="eager" src="{_html.escape(rel)}"></iframe></div>')
    return (
        "<!doctype html><meta charset=utf-8>"
        f"<title>{_html.escape(company)} UI matrix</title>"
        "<style>body{margin:0;font:12px system-ui}"
        ".cell{display:inline-block;vertical-align:top;margin:4px}"
        ".lab{margin:0 0 2px;font:11px/1.2 monospace;color:#666}"
        "iframe{border:1px solid #ccc;background:#fff}</style>"
        f"<h1 style='font:14px system-ui;margin:6px'>"
        f"{_html.escape(company)}</h1>" + "".join(frames))


#: Run inside the browser against a harness page. Returns one row per
#: (surface, width): horizontal overflow and the worst text contrast found.
MEASURE_JS = r"""
(() => {
  const srgb = c => { c/=255; return c<=0.03928 ? c/12.92
      : Math.pow((c+0.055)/1.055, 2.4); };
  const lum = rgb => 0.2126*srgb(rgb[0])+0.7152*srgb(rgb[1])+0.0722*srgb(rgb[2]);
  const parse = s => {
    const m = (s||"").match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(",").map(x=>parseFloat(x));
    if (p.length>3 && p[3]===0) return null;
    return [p[0],p[1],p[2]];
  };
  const bgOf = el => {
    let n = el;
    while (n && n.nodeType===1) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c) return c;
      n = n.parentElement;
    }
    return [255,255,255];
  };
  const out = [];
  for (const f of document.querySelectorAll("iframe")) {
    const row = {surface: f.dataset.surface, width: +f.dataset.width,
                 ok: false};
    let d;
    try { d = f.contentDocument; } catch(e) { d = null; }
    if (!d || !d.body) { out.push(row); continue; }
    row.ok = true;
    const de = d.documentElement, b = d.body;
    row.scrollW = Math.max(de.scrollWidth, b.scrollWidth);
    row.clientW = f.clientWidth || +f.dataset.width;
    row.overflowPx = Math.max(0, row.scrollW - row.clientW);
    // which elements actually stick out -- a number alone is not actionable
    const wide = [];
    for (const el of d.body.querySelectorAll("*")) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.right > row.clientW + 1) {
        wide.push(el.tagName.toLowerCase() + "." +
                  (el.className||"").toString().split(" ")[0] +
                  ":" + Math.round(r.right));
        if (wide.length >= 6) break;
      }
    }
    row.overflowing = wide;
    // contrast on real text nodes only
    let worst = 99, fails = 0, checked = 0, sample = "";
    for (const el of d.body.querySelectorAll(
        "p,li,h1,h2,h3,h4,span,td,th,a,strong,em,blockquote,dt,dd,figcaption")) {
      const t = (el.textContent||"").trim();
      if (!t || t.length < 3) continue;
      if (el.children.length && el.childElementCount === el.children.length
          && !Array.from(el.childNodes).some(n=>n.nodeType===3
              && n.textContent.trim())) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility==="hidden" || cs.display==="none") continue;
      const fg = parse(cs.color); if (!fg) continue;
      const bg = bgOf(el);
      const L1 = lum(fg), L2 = lum(bg);
      const ratio = (Math.max(L1,L2)+0.05)/(Math.min(L1,L2)+0.05);
      const size = parseFloat(cs.fontSize)||16;
      const bold = (parseInt(cs.fontWeight,10)||400) >= 700;
      const large = size >= 24 || (bold && size >= 18.66);
      const need = large ? 3.0 : 4.5;
      checked++;
      if (ratio < need) {
        fails++;
        if (ratio < worst) { worst = ratio;
          sample = el.tagName+":"+t.slice(0,40)+" "+cs.color+" on rgb("+bg+")"; }
      }
    }
    row.contrastChecked = checked;
    row.contrastFails = fails;
    row.worstContrast = fails ? Math.round(worst*100)/100 : null;
    row.worstSample = sample;
    out.push(row);
  }
  return out;
})()
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="reports/next40_state.json")
    ap.add_argument("--captures", default="reports/next40_ui")
    args = ap.parse_args()
    state = json.loads((ROOT / args.state).read_text())
    root = ROOT / args.captures
    root.mkdir(parents=True, exist_ok=True)
    summary = {}
    for key, row in sorted(state.get("rows", {}).items(), key=lambda k: int(k[0])):
        company = row.get("company") or key
        slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")
        # The journey already wrote these; reading them back keeps the one
        # copy of each page rather than a second one inside the state file.
        written = dict(row.get("capture_files") or {})
        caps = {}
        for name, fname in list(written.items()):
            try:
                caps[name] = (root / fname).read_text()
            except OSError:
                written.pop(name, None)
        if not caps:
            continue
        (root / f"{slug}.matrix.html").write_text(
            harness_page(company, written))
        summary[company] = {
            "n": row.get("n"), "slug": slug,
            "harness": f"{slug}.matrix.html",
            "text": {name: scan_html(raw) for name, raw in caps.items()},
        }
    (root / "index.json").write_text(json.dumps(summary, indent=1))
    bad = {c: {s: v for s, v in d["text"].items()
               if v["raw_enums"] or v["internal"] or v["literal_none"]
               or v["stale_spinner"] or v["duplicate_paragraphs"]
               or not v["has_nav"]}
           for c, d in summary.items()}
    bad = {c: v for c, v in bad.items() if v}
    print(f"companies with captures {len(summary)}")
    print(f"textual defects         {len(bad)} company(ies)")
    for c, v in list(bad.items())[:12]:
        for s, d in v.items():
            print(f"  {c} /{s}: enums={d['raw_enums'][:3]} "
                  f"internal={d['internal'][:2]} none={d['literal_none'][:2]} "
                  f"spinner={d['stale_spinner']} dupes={d['duplicate_paragraphs']} "
                  f"nav={d['has_nav']}")
    print(f"\nharness pages in {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
