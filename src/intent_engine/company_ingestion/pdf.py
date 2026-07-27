"""Bounded PDF evidence extraction.

Investor presentations, earnings decks, shareholder letters and annual reports
are frequently PDFs. Without this they are simply unavailable, and the strategy
/ financial evidence families stay empty for companies that publish there.

Everything is bounded and defensive: size, page count and time are capped; an
encrypted, malformed, or image-only PDF is REJECTED rather than admitted as
empty evidence; nothing embedded is executed; and every extraction records the
page it came from so a citation can resolve to document + page.

pypdf is the only new dependency and is imported lazily, so a deployment
without it degrades to "PDF unsupported" instead of failing to boot.
"""
from __future__ import annotations

import hashlib
import io
import re

PDF_MIME_PREFIXES = ("application/pdf", "application/x-pdf")
MAX_PDF_BYTES = 8_000_000          # investor decks are large but not huge
MAX_PDF_PAGES = 60                 # bounded work per document
# A scanned/image-only PDF extracts ~zero words, so this only has to separate
# "real prose" from "no text at all" — set too high it rejects a legitimately
# short one-page shareholder letter.
MIN_MEANINGFUL_WORDS = 60
# A page whose text is mostly non-alphabetic is a scan/figure, not text.
MIN_ALPHA_RATIO = 0.55

# Outcomes
PDF_OK = "OK"
PDF_ENCRYPTED = "ENCRYPTED"
PDF_MALFORMED = "PARSE_FAILED"
PDF_IMAGE_ONLY = "IMAGE_ONLY"
PDF_TOO_LARGE = "TOO_LARGE"
PDF_UNSUPPORTED = "UNSUPPORTED"


def is_pdf(url: str = "", mime: str = "", body: bytes = b"") -> bool:
    """Identify a PDF by MIME, magic bytes, or extension — in that order."""
    if mime and any(mime.lower().startswith(p) for p in PDF_MIME_PREFIXES):
        return True
    if body[:5] == b"%PDF-":
        return True
    return url.lower().split("?")[0].endswith(".pdf")


def _alpha_ratio(text: str) -> float:
    stripped = re.sub(r"\s", "", text or "")
    if not stripped:
        return 0.0
    alpha = sum(1 for ch in stripped if ch.isalpha())
    return alpha / len(stripped)


def extract_pdf(body: bytes, *, url: str = "") -> dict:
    """Extract text and page references from PDF bytes.

    Returns {status, text, pages, page_count, title, published, content_hash,
    reason}. Never raises: a bad document yields a status the caller records as
    an honest per-source failure.
    """
    result = {"status": PDF_UNSUPPORTED, "text": "", "pages": [],
              "page_count": 0, "title": "", "published": "",
              "content_hash": hashlib.sha256(body or b"").hexdigest(),
              "reason": ""}
    if not body:
        result["reason"] = "empty document"
        result["status"] = PDF_MALFORMED
        return result
    if len(body) > MAX_PDF_BYTES:
        result["status"] = PDF_TOO_LARGE
        result["reason"] = (f"PDF exceeded the {MAX_PDF_BYTES} byte budget")
        return result
    try:
        from pypdf import PdfReader
    except ImportError:                                     # noqa: BLE001
        result["reason"] = "PDF support is not installed in this deployment"
        return result

    try:
        reader = PdfReader(io.BytesIO(body))
        if getattr(reader, "is_encrypted", False):
            # Never attempt to defeat protection; an encrypted document is
            # simply not readable evidence.
            result["status"] = PDF_ENCRYPTED
            result["reason"] = "the document is password-protected"
            return result
        pages = reader.pages[:MAX_PDF_PAGES]
        extracted = []
        for number, page in enumerate(pages, start=1):
            try:
                text = " ".join((page.extract_text() or "").split())
            except Exception:                               # noqa: BLE001
                continue                    # one bad page never kills the doc
            if text:
                extracted.append({"page": number, "text": text})
        meta = getattr(reader, "metadata", None) or {}
        title = str(meta.get("/Title", "") or "").strip()
        published = str(meta.get("/CreationDate", "") or "").strip()
    except Exception as exc:                                # noqa: BLE001
        result["status"] = PDF_MALFORMED
        result["reason"] = f"the document could not be parsed ({type(exc).__name__})"
        return result

    joined = "\n".join(p["text"] for p in extracted)
    word_count = len(joined.split())
    result.update({"pages": extracted, "page_count": len(pages),
                   "title": title, "published": published, "text": joined})
    if word_count < MIN_MEANINGFUL_WORDS or _alpha_ratio(joined) < MIN_ALPHA_RATIO:
        # A scanned or figure-only deck. We do not OCR, and we do not admit an
        # empty document as evidence.
        result["status"] = PDF_IMAGE_ONLY
        result["reason"] = ("the document has no extractable text (it appears "
                            "to be scanned or image-only); text recognition is "
                            "not performed")
        return result
    result["status"] = PDF_OK
    return result


def page_citation(url: str, page: int) -> str:
    """A citation that resolves to the document AND the page it came from."""
    return f"{url}#page={page}"
