"""Find sentences a page says more than once, across every captured surface.

Reads the pass captures (raw HTML), strips markup the way a reader sees it,
splits into sentences, and reports each sentence of >= 40 characters that
appears two or more times on ONE page. Also reports sentences that appear on
every company's page of a surface (template text shared across companies).

Usage: python scripts/prospect100/repetition_audit.py [captures_dir] [--json out]
"""
from __future__ import annotations

import collections
import html as H
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "reports/prospect100_pass2/reports/next40_ui"


def visible(page: str) -> str:
    # <title> and <desc> are never painted: the page title sits in <head>,
    # and an SVG chart's title/desc are its screen-reader name. Counting them
    # reported every chart as saying its sentence three times.
    page = re.sub(r"(?is)<(script|style|noscript|template|title|desc)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?is)<(br|p|div|li|h[1-6]|section|article|tr|td|th|dt|dd)[^>]*>", "\n", page)
    page = re.sub(r"(?s)<[^>]+>", " ", page)
    return H.unescape(page)


def sentences(text: str):
    for block in text.split("\n"):
        block = " ".join(block.split())
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(])", block):
            s = s.strip()
            if len(s) >= 40:
                yield s


def audit(captures: pathlib.Path, strip_svg: bool = False):
    per_page = {}
    by_surface = collections.defaultdict(lambda: collections.defaultdict(set))
    companies = set()
    for f in sorted(captures.glob("*.html")):
        slug, _, surface = f.stem.rpartition("-")
        companies.add(slug)
        raw = f.read_text(errors="replace")
        if strip_svg:
            # A chart's painted labels restate the passage by design; this
            # audit counts PROSE said twice.
            raw = re.sub(r"(?is)<svg.*?</svg>", " ", raw)
        sents = list(sentences(visible(raw)))
        c = collections.Counter(sents)
        dup = {s: n for s, n in c.items() if n >= 2}
        if dup:
            per_page[f.name] = dup
        for s in set(sents):
            by_surface[surface][s].add(slug)
    shared = {}
    n = len(companies)
    for surface, m in by_surface.items():
        common = [s for s, who in m.items() if len(who) == n and n > 1]
        if common:
            shared[surface] = common
    return {"companies": n, "pages_with_repeats": len(per_page),
            "pages": len(list(captures.glob("*.html"))),
            "repeats": per_page, "shared_across_all_companies": shared}


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--json" in argv:
        i = argv.index("--json"); argv = argv[:i] + argv[i + 2:]
    args = [a for a in argv if not a.startswith("--")]
    cap = pathlib.Path(args[0]) if args else DEFAULT
    out = audit(cap)
    if "--json" in sys.argv:
        pathlib.Path(sys.argv[sys.argv.index("--json") + 1]).write_text(
            json.dumps(out, indent=1))
    print(f"{out['pages_with_repeats']} of {out['pages']} pages repeat a sentence "
          f"({out['companies']} companies)")
    agg = collections.Counter()
    for page, dup in out["repeats"].items():
        for s, k in dup.items():
            agg[(page.rpartition('-')[2], s[:110])] += 1
    for (surface, s), k in agg.most_common(25):
        print(f"  {k:>3} pages  {surface:14s} {s}")
