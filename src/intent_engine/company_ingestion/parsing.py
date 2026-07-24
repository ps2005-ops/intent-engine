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
        self.headings: list = []
        self.blocks: list = []
        self.links: list = []
        self._skip_depth = 0
        self._block_stack: list = []
        self._buffer: list = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip_depth += 1
            return
        attrs = dict(attrs)
        if tag == "meta":
            if (attrs.get("name") or "").lower() == "description":
                self.meta_description = (attrs.get("content") or "").strip()
        if tag == "link" and (attrs.get("rel") or "").lower() == "canonical":
            self.canonical_url = attrs.get("href")
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag in _BLOCK:
            self._block_stack.append(tag)
            self._buffer = []

    def handle_endtag(self, tag):
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
        if self._skip_depth == 0 and self._block_stack:
            self._buffer.append(data)


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
    return {
        "title": extractor.title,
        "meta_description": extractor.meta_description,
        "canonical_url": extractor.canonical_url,
        "headings": extractor.headings,
        "text": text,
        "links": extractor.links,
        "content_hash": hashlib.sha256((html or "").encode()).hexdigest(),
        "parser_version": PARSER_VERSION,
    }
