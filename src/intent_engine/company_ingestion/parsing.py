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

# Chrome: the parts of a page that are the SITE rather than the page. Their
# text is real and visible, and it is never about this company in the way an
# analysis needs — it is the menu, the cookie bar, the footer's legal links.
#
# Keeping it cost a real reader a real answer. Asked what Shopify does, the
# product replied "What to build How to build After we build Personal practice
# Go forth and build Everyone at Shopify works on product." — six navigation
# labels and a heading, welded into something that parses as a sentence.
# Downstream filters can reject that, but only after it has already crowded
# out the paragraph that would have answered the question.
_CHROME = {"nav", "header", "footer", "aside"}

# Where a page keeps its actual content. When a page marks this up, the marked
# region is the page and everything else is furniture.
_MAIN = {"main", "article"}

# Chrome removal must never empty a page. Some sites wrap everything in
# <header>, and a page reduced to nothing is a worse outcome than a page with
# a menu in it — so the stripped text is used only when something survives.
#
# Deliberately the same floor `usable_documents` applies: "survived" means
# there is a document here, not "there is a lot here". Set higher, a short but
# perfectly good <main> loses to the whole page including its menu, which is
# the failure this exists to prevent rather than a safeguard against it.
MIN_MAIN_TEXT_CHARS = 40
# Below this much block-level body text, a page is treated as a hydration shell
# and its server-rendered state is read as well. Sites that genuinely serve
# their content as HTML clear this easily (Shopify's /about extracts 3.3k), so
# the ordinary path is untouched.
MIN_BODY_TEXT_CHARS = 600
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
        self._state_raw: list = []
        self._in_jsonld = False
        self._in_state = False
        self._skip_depth = 0
        self._block_stack: list = []
        self._buffer: list = []
        # Open chrome/main regions, innermost last, as (tag, kind). A stack
        # rather than counters because the region can be opened by a role
        # attribute on a <div>, and the closing tag carries no attributes —
        # so the only way to know what a </div> closes is to have recorded it.
        # Tracked during parsing rather than filtered afterwards, because by
        # the time a menu label is a line of text it is indistinguishable from
        # a heading.
        self._regions: list = []
        # Blocks that were inside <main>/<article>, and blocks that were not
        # inside chrome. Collected alongside `blocks` so the caller can choose,
        # and so a page that marks up nothing still behaves exactly as before.
        self.main_blocks: list = []
        self.body_blocks: list = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and (attrs.get("type") or "").lower() == \
                "application/ld+json":
            self._in_jsonld = True          # capture the structured-data body
            return
        if tag == "script" and _is_state_script(attrs):
            self._in_state = True           # server-rendered page state
            return
        if tag in _SKIP:
            self._skip_depth += 1
            return
        role = (attrs.get("role") or "").lower()
        if tag in _CHROME or role in ("navigation", "banner", "contentinfo",
                                      "complementary"):
            self._regions.append((tag, "chrome"))
        elif tag in _MAIN or role == "main":
            self._regions.append((tag, "main"))
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
        if tag == "script" and self._in_state:
            self._in_state = False
            return
        if tag in _SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        # Close the innermost region this tag opened, discarding anything left
        # open inside it. Real pages leave tags unclosed, and a region that
        # never closes would swallow the rest of the document.
        for index in range(len(self._regions) - 1, -1, -1):
            if self._regions[index][0] == tag:
                del self._regions[index:]
                break
        if tag in _BLOCK and self._block_stack:
            self._block_stack.pop()
            text = " ".join("".join(self._buffer).split())
            self._buffer = []
            if not text:
                return
            if tag == "title" and not self.title:
                self.title = text
                return
            if tag.startswith("h") and len(tag) == 2:
                self.headings.append((tag, text))
            self.blocks.append(text)
            kinds = {kind for _, kind in self._regions}
            if "chrome" not in kinds:
                self.body_blocks.append(text)
                if "main" in kinds:
                    self.main_blocks.append(text)

    def handle_data(self, data):
        if self._in_jsonld:
            self._jsonld_raw.append(data)
            return
        if self._in_state:
            self._state_raw.append(data)
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


# --- server-rendered page state ----------------------------------------------
# A modern framework site (Next.js, Nuxt, SvelteKit, Remix) ships its page
# content TWICE: once as DOM the browser will build, and once as a JSON blob the
# client hydrates from. Sites built with the Next.js Pages Router ship ONLY the
# JSON — the served <body> is an empty mount point, and every word of real
# copy lives in <script id="__NEXT_DATA__" type="application/json">.
#
# This is server-rendered, first-party content delivered in the ordinary
# response to an ordinary permitted request. Reading it is not a bypass of
# anything: no access control, no robots rule, and no client-side execution is
# involved — it is the same bytes the page already sent us, parsed as what they
# are. Discarding it was the reason a 692 KB Palantir page was admitted as 120
# characters of og:description.
_STATE_SCRIPT_IDS = {"__next_data__", "__nuxt_data__", "__nuxt__",
                     "__remix_context__", "__sveltekit_data__",
                     "__initial_state__", "__apollo_state__"}

# Keys whose values are machine identifiers, asset paths or layout hints rather
# than prose. Skipping them keeps image alt-junk ("SCE FC 23 Card (3:2)") out of
# the evidence text.
_STATE_NOISE_KEYS = {
    "id", "key", "slug", "url", "href", "src", "srcset", "path", "type",
    "class", "classname", "style", "width", "height", "color", "icon",
    "filename", "mimetype", "contenttype", "hash", "sha", "uuid", "guid",
    "buildid", "locale", "lang", "align", "variant", "theme", "token",
    "alt", "aria-label", "arialabel", "caption", "filepath", "asseturl",
}
MAX_STATE_STRINGS = 400
MAX_STATE_CHARS = 60_000


def _is_state_script(attrs: dict) -> bool:
    """True for a <script> that carries server-rendered page state as JSON."""
    script_id = (attrs.get("id") or "").strip().lower()
    if script_id in _STATE_SCRIPT_IDS:
        return True
    mime = (attrs.get("type") or "").strip().lower()
    return mime == "application/json" and bool(script_id)


def _looks_like_prose(text: str) -> bool:
    """Sentence-shaped copy, not an identifier, class name, or asset label."""
    stripped = text.strip()
    if len(stripped) < 25 or len(stripped) > 2000:
        return False
    words = stripped.split()
    if len(words) < 5:
        return False
    if stripped.startswith(("http://", "https://", "/", "#", "{", "[", "<")):
        return False
    # identifier-ish: no spaces around, or dominated by non-letters
    letters = sum(1 for ch in stripped if ch.isalpha() or ch.isspace())
    if letters / len(stripped) < 0.75:
        return False
    # camelCase / snake_case / kebab blobs masquerading as sentences
    if any(len(word) > 40 for word in words):
        return False
    return True


def _state_text(raw_blocks: list) -> list:
    """Prose recovered from server-rendered page state. Deterministic and
    bounded: document order, de-duplicated, capped in both count and size."""
    import json
    out: list = []
    seen: set = set()
    budget = {"chars": 0}

    def walk(node, key=""):
        if len(out) >= MAX_STATE_STRINGS or budget["chars"] >= MAX_STATE_CHARS:
            return
        if isinstance(node, dict):
            for child_key, value in node.items():
                walk(value, str(child_key).lower())
        elif isinstance(node, list):
            for item in node:
                walk(item, key)
        elif isinstance(node, str):
            if key in _STATE_NOISE_KEYS:
                return
            text = " ".join(node.split())
            if not _looks_like_prose(text):
                return
            fingerprint = text.lower()
            if fingerprint in seen:
                return
            seen.add(fingerprint)
            out.append(text)
            budget["chars"] += len(text)

    for raw in raw_blocks:
        try:
            walk(json.loads(raw))
        except (ValueError, TypeError, RecursionError):
            continue
    return out


def _terminated(line: str) -> str:
    """A block that does not end a sentence, made to end one.

    Headings and list items rarely carry a full stop, and every consumer that
    splits text into sentences then welds the heading onto the paragraph
    below it. A live run answered "what does this company do" with "We build
    our company around mission-driven engineering We send our engineers into
    the field…" — two separate blocks, read as one sentence.

    A newline is not a sentence boundary to a sentence splitter, so the
    boundary has to be in the text itself.
    """
    line = line.rstrip()
    if not line or line[-1] in ".!?:;,":
        return line
    return line + "."


def parse_html(html: str) -> dict:
    """Returns {title, meta_description, canonical_url, headings, text,
    links, content_hash, parser_version}. Deterministic."""
    extractor = _Extractor()
    try:
        extractor.feed(html or "")
    except Exception:                                      # noqa: BLE001
        pass                                # keep whatever was extracted
    # Prefer the page's own main region, then the page minus its chrome, then
    # everything. Each fallback only applies when the narrower choice does not
    # leave the page empty: stripping furniture must never cost a page that
    # wraps its content in <header>, where having a menu in the text is the
    # lesser harm.
    def _dedupe(blocks):
        """Drop exact-duplicate lines — the nav/footer echo left over when a
        site marks up none of its regions."""
        seen, lines = set(), []
        for block in blocks:
            key = block.lower()
            if key in seen:
                continue
            seen.add(key)
            lines.append(block)
        return lines

    for candidate in (extractor.main_blocks, extractor.body_blocks,
                      extractor.blocks):
        lines = _dedupe(candidate)
        if len("\n".join(lines).strip()) >= MIN_MAIN_TEXT_CHARS:
            break
    else:
        lines = _dedupe(extractor.blocks)
    seen = {line.lower() for line in lines}
    text = "\n".join(_terminated(line) for line in lines)
    blocks_found = len(lines)
    extraction_mode = "body" if text.strip() else "none"
    og = extractor.og
    meta_description = extractor.meta_description or og.get("og:description",
                                                            "")
    # SALVAGE, in order of how much the recovered text is worth.
    #
    # A framework-rendered page yields little or no BODY text, but the response
    # still carries the content in two other places: the server-rendered page
    # state (a JSON blob the client hydrates from) and the page metadata
    # (title, OpenGraph, JSON-LD). Both are first-party content already present
    # in the bytes we were served.
    #
    # Page state is tried FIRST because it is the real article — paragraphs,
    # product descriptions, named customers — whereas metadata is a one-line
    # summary. Admitting a 692 KB document as 120 characters of og:description
    # is what made a Palantir report that never mentioned Foundry look healthy
    # to every downstream gate.
    if len(text.strip()) < MIN_BODY_TEXT_CHARS:
        recovered = _state_text(extractor._state_raw)
        if recovered:
            body_lines = [line for line in lines if line.strip()]
            merged = body_lines + [r for r in recovered
                                   if r.lower() not in seen]
            # Terminated here too. A JavaScript-rendered page reaches the
            # reader through this branch, not the one above, so applying the
            # sentence boundary only to HTML blocks left exactly the pages
            # that need it most — the ones whose text is recovered from page
            # state — welding a heading onto the paragraph after it.
            text = "\n".join(_terminated(line) for line in merged)
            extraction_mode = "structured"
            blocks_found = len(merged)
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
        if text.strip():
            extraction_mode = "metadata"
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
        # Diagnostics: WHERE the text came from, and how many document blocks
        # the parser actually found. "we fetched 692 KB and admitted 120
        # characters of og:description" is otherwise invisible downstream.
        "extraction_mode": extraction_mode,
        "blocks_found": blocks_found,
    }
