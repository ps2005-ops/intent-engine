"""V1.1 HTML → clean source document. Stdlib only; no business inference.

Extracts title, meta description, headings, visible paragraph/list text,
and same-page links (for bounded discovery). Drops script/style/noscript
/ template content entirely and reduces boilerplate by de-duplicating
repeated short lines (nav/footer repetition).
"""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser

from intent_engine.company_ingestion.records import PARSER_VERSION

_SKIP = {"script", "style", "noscript", "template", "svg", "iframe"}
_BLOCK = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th",
          "blockquote", "figcaption", "dt", "dd", "title"}


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta_description = ""
        self.canonical_url = None
        self.modified_date = ""
        self.headings: list = []
        self.blocks: list = []
        self.links: list = []
        self.og: dict = {}
        self._jsonld_raw: list = []
        self._in_jsonld = False
        self._skip_depth = 0
        self._block_stack: list = []
        self._buffer: list = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and (attrs.get("type") or "").lower() == \
                "application/ld+json":
            self._in_jsonld = True          # capture the structured-data body
            return
        if tag in _SKIP:
            self._skip_depth += 1
            return
        if tag == "meta":
            if (attrs.get("name") or "").lower() == "description":
                self.meta_description = (attrs.get("content") or "").strip()
            prop = (attrs.get("property") or "").lower()
            if prop in ("og:title", "og:description", "og:site_name"):
                self.og[prop] = (attrs.get("content") or "").strip()
            if prop in ("article:modified_time", "article:published_time",
                        "og:updated_time") and not self.modified_date:
                self.modified_date = (attrs.get("content") or "").strip()
        if tag == "time" and attrs.get("datetime") and not self.modified_date:
            self.modified_date = attrs["datetime"].strip()
        if tag == "link" and (attrs.get("rel") or "").lower() == "canonical":
            self.canonical_url = attrs.get("href")
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag in _BLOCK:
            self._block_stack.append(tag)
            self._buffer = []

    def handle_endtag(self, tag):
        if tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            return
        if tag in _SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag in _BLOCK and self._block_stack:
            self._block_stack.pop()
            text = " ".join("".join(self._buffer).split())
            self._buffer = []
            if not text:
                return
            if tag == "title" and not self.title:
                self.title = text
            elif tag.startswith("h") and len(tag) == 2:
                self.headings.append((tag, text))
                self.blocks.append(text)
            else:
                self.blocks.append(text)

    def handle_data(self, data):
        if self._in_jsonld:
            self._jsonld_raw.append(data)
            return
        if self._skip_depth == 0 and self._block_stack:
            self._buffer.append(data)


def _jsonld_text(raw_blocks: list) -> list:
    """Descriptive strings from JSON-LD structured data. JavaScript-rendered
    marketing sites almost always still ship server-rendered JSON-LD/OpenGraph,
    so this recovers real company/product description from a page whose body
    would otherwise extract as empty (the 2026-07 'javascript_only' gap)."""
    import json
    wanted = ("name", "legalName", "description", "alternateName", "slogan",
              "applicationCategory", "brand", "about")
    out: list = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in wanted and isinstance(value, str):
                    text = value.strip()
                    if len(text.split()) >= 2 and text not in out:
                        out.append(text)
                elif isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for raw in raw_blocks:
        try:
            walk(json.loads(raw))
        except (ValueError, TypeError):
            continue
    return out


def parse_html(html: str) -> dict:
    """Returns {title, meta_description, canonical_url, headings, text,
    links, content_hash, parser_version}. Deterministic."""
    extractor = _Extractor()
    try:
        extractor.feed(html or "")
    except Exception:                                      # noqa: BLE001
        pass                                # keep whatever was extracted
    # boilerplate reduction: drop exact-duplicate lines (nav/footer echoes)
    seen, lines = set(), []
    for block in extractor.blocks:
        key = block.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(block)
    text = "\n".join(lines)
    og = extractor.og
    meta_description = extractor.meta_description or og.get("og:description",
                                                            "")
    # SALVAGE: a JavaScript-rendered page yields no body text, but its
    # server-rendered metadata (title, OpenGraph, JSON-LD) still describes the
    # company. Recover that rather than discarding the source entirely — it is
    # directly observed, first-party content, not an inference.
    if not text.strip():
        salvaged = []
        for value in (extractor.title, og.get("og:title"),
                      og.get("og:site_name"), meta_description):
            if value and value.strip() and value.strip() not in salvaged:
                salvaged.append(value.strip())
        for value in _jsonld_text(extractor._jsonld_raw):
            if value not in salvaged:
                salvaged.append(value)
        text = "\n".join(salvaged)
    return {
        "title": extractor.title or og.get("og:title", ""),
        "meta_description": meta_description,
        "canonical_url": extractor.canonical_url,
        "modified_date": extractor.modified_date,
        "headings": extractor.headings,
        "text": text,
        "links": extractor.links,
        "content_hash": hashlib.sha256((html or "").encode()).hexdigest(),
        "parser_version": PARSER_VERSION,
    }
