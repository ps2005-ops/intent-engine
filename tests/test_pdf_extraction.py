"""Bounded PDF evidence extraction.

Investor decks, shareholder letters and annual reports are frequently PDFs.
These tests pin what may become evidence (real extractable text, with page
references) and — just as important — what may NOT: encrypted, malformed,
image-only, or oversized documents are honest failures, never empty evidence.

Every PDF here is generated in-process; no fixture binaries, no network.
"""
import pathlib
import tempfile

import pytest

pypdf = pytest.importorskip("pypdf")

from intent_engine.company_ingestion.pdf import (       # noqa: E402
    MAX_PDF_BYTES, PDF_ENCRYPTED, PDF_IMAGE_ONLY, PDF_MALFORMED, PDF_OK,
    PDF_TOO_LARGE, extract_pdf, is_pdf, page_citation,
)
from intent_engine.company_ingestion.service import (   # noqa: E402
    CompanyIngestionService,
)
from intent_engine.founder_intelligence.service import (  # noqa: E402
    FounderIntelligenceService,
)

AS_OF = "2026-07-27T00:00:00+00:00"

EARNINGS_TEXT = (
    "Fourth quarter revenue grew year over year driven by commercial customer "
    "expansion and platform adoption across government and enterprise "
    "accounts. Operating margin improved as the customer base expanded and "
    "the company deepened existing deployments. Remaining performance "
    "obligations increased, reflecting longer contract durations with "
    "strategic customers. Management highlighted continued investment in the "
    "artificial intelligence platform and its ontology driven workflows, "
    "noting strong demand from both defense and commercial segments during "
    "the period under review and into the coming fiscal year ahead."
)


def _make_pdf(pages_text, *, title="Earnings Release", encrypt=None):
    """Build a real PDF in memory using pypdf + a minimal page generator."""
    from pypdf import PdfWriter
    writer = PdfWriter()
    for text in pages_text:
        # A blank page carrying a content stream with the text drawn on it.
        page = writer.add_blank_page(width=612, height=792)
        stream = (b"BT /F1 10 Tf 40 700 Td ("
                  + text.replace("(", " ").replace(")", " ").encode("latin-1",
                                                                    "replace")
                  + b") Tj ET")
        from pypdf.generic import DecodedStreamObject, NameObject
        content = DecodedStreamObject()
        content.set_data(stream)
        page[NameObject("/Contents")] = writer._add_object(content)
        from pypdf.generic import DictionaryObject, ArrayObject
        font = DictionaryObject()
        font.update({NameObject("/Type"): NameObject("/Font"),
                     NameObject("/Subtype"): NameObject("/Type1"),
                     NameObject("/BaseFont"): NameObject("/Helvetica")})
        resources = DictionaryObject()
        fonts = DictionaryObject()
        fonts[NameObject("/F1")] = writer._add_object(font)
        resources[NameObject("/Font")] = fonts
        page[NameObject("/Resources")] = resources
    writer.add_metadata({"/Title": title})
    if encrypt:
        writer.encrypt(encrypt)
    import io
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


# --- identification ---------------------------------------------------------

def test_pdf_identified_by_mime_magic_and_extension():
    assert is_pdf(mime="application/pdf")
    assert is_pdf(body=b"%PDF-1.7 ...")
    assert is_pdf(url="https://x.com/deck.pdf")
    assert not is_pdf(url="https://x.com/page", mime="text/html")


# --- successful extraction --------------------------------------------------

def test_earnings_pdf_extracts_text_with_page_references():
    body = _make_pdf([EARNINGS_TEXT, "Second page " + EARNINGS_TEXT])
    result = extract_pdf(body, url="https://x.com/q4.pdf")
    assert result["status"] == PDF_OK, result["reason"]
    assert "revenue" in result["text"].lower()
    assert result["page_count"] == 2
    assert [p["page"] for p in result["pages"]] == [1, 2]
    assert result["title"] == "Earnings Release"
    assert result["content_hash"]


def test_shareholder_letter_pdf_is_usable_evidence():
    body = _make_pdf([EARNINGS_TEXT], title="Shareholder Letter")
    result = extract_pdf(body)
    assert result["status"] == PDF_OK
    assert result["title"] == "Shareholder Letter"


def test_page_citation_resolves_to_document_and_page():
    assert page_citation("https://x.com/q4.pdf", 3) == \
        "https://x.com/q4.pdf#page=3"


# --- rejected documents (never admitted as empty evidence) ------------------

def test_encrypted_pdf_is_rejected_not_bypassed():
    body = _make_pdf([EARNINGS_TEXT], encrypt="secret")
    result = extract_pdf(body)
    assert result["status"] == PDF_ENCRYPTED
    assert not result["text"]
    assert "password" in result["reason"].lower()


def test_malformed_pdf_is_an_honest_failure():
    result = extract_pdf(b"%PDF-1.4 this is not really a pdf at all")
    assert result["status"] == PDF_MALFORMED
    assert not result["text"]


def test_empty_body_is_an_honest_failure():
    assert extract_pdf(b"")["status"] == PDF_MALFORMED


def test_image_only_pdf_is_rejected_and_never_ocred():
    # pages with no extractable text — a scanned deck
    body = _make_pdf(["", ""])
    result = extract_pdf(body)
    assert result["status"] == PDF_IMAGE_ONLY
    assert "scanned" in result["reason"] or "image-only" in result["reason"]


def test_oversized_pdf_is_refused_before_parsing():
    result = extract_pdf(b"%PDF-" + b"x" * (MAX_PDF_BYTES + 1))
    assert result["status"] == PDF_TOO_LARGE


def test_near_empty_pdf_is_not_meaningful_evidence():
    """A near-textless document must not be admitted as evidence."""
    result = extract_pdf(_make_pdf(["Only a few words here."]))
    assert result["status"] == PDF_IMAGE_ONLY   # below the meaningful-word bar


# --- end-to-end through the retrieval path ---------------------------------

def test_pdf_source_becomes_investor_evidence_end_to_end(tmp_path):
    """A PDF investor deck retrieved through the normal approval path becomes
    real evidence with its text available to the report."""
    import email
    import urllib.error
    pdf_bytes = _make_pdf([EARNINGS_TEXT], title="Q4 Investor Presentation")
    base = "https://pdfco.example"

    def transport(url, timeout):
        html = {"content-type": "text/html"}
        if url.rstrip("/") == base:
            return (200, html,
                    b"<html><head><title>PDF Co</title>"
                    b'<meta name="description" content="PDF Co builds testing '
                    b'tools for teams.">'
                    b"</head><body><h1>PDF Co</h1>"
                    b"<p>We build developer testing tools for engineering "
                    b"teams at software companies.</p></body></html>", False)
        if url.endswith("/investor-deck.pdf"):
            return (200, {"content-type": "application/pdf"}, pdf_bytes, False)
        if url.endswith("/robots.txt"):
            return (200, {"content-type": "text/plain"}, b"", False)
        raise urllib.error.HTTPError(
            url, 404, "nf", email.message_from_string(""), None)

    ci = CompanyIngestionService(tmp_path / "ci.jsonl", transport=transport,
                                 resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run_id = ci.create_run(company_name="PDF Co", website=base,
                           user_id="u1", as_of=AS_OF)["run_id"]
    ci.discover(run_id)
    # inject the PDF as an approved investor candidate
    ci._append("ci.candidate_discovered", run_id=run_id, domain="pdfco.example",
               subject_type="candidate", subject_id="cand-pdf000000001",
               payload={"candidate_id": "cand-pdf000000001",
                        "company_id": "pdfco.example",
                        "url": f"{base}/investor-deck.pdf",
                        "canonical_url": f"{base}/investor-deck.pdf",
                        "source_type": "external_approved",
                        "title": "Q4 investor presentation",
                        "discovery_method": "external_proposed",
                        "same_domain": False,
                        "source_class": "investor_material",
                        "why_relevant": "official investor presentation",
                        "availability": "PROPOSED", "rank": 99},
               idempotency_key="cand:pdf:1")
    ci.approve(run_id, user_id="u1", approved_ids=["cand-pdf000000001"],
               rejected_ids=[])
    fetched = ci.fetch_approved(run_id)
    assert fetched["ok"], fetched["failed"]
    document = fetched["ok"][0]
    assert document["source_class"] == "investor_material"
    assert "revenue" in document["text_content"].lower()
    assert document["byte_count"] > 0


def test_broken_pdf_source_fails_without_polluting_evidence(tmp_path):
    """A malformed PDF must be recorded as a failure, not stored as an empty
    document that would pad the report."""
    import email
    import urllib.error
    base = "https://badpdf.example"

    def transport(url, timeout):
        if url.endswith("/broken.pdf"):
            return (200, {"content-type": "application/pdf"},
                    b"%PDF-1.4 corrupted", False)
        if url.rstrip("/") == base:
            return (200, {"content-type": "text/html"},
                    b"<html><head><title>Bad PDF Co</title></head><body>"
                    b"<p>We publish broken documents for testing.</p>"
                    b"</body></html>", False)
        raise urllib.error.HTTPError(
            url, 404, "nf", email.message_from_string(""), None)

    ci = CompanyIngestionService(tmp_path / "ci.jsonl", transport=transport,
                                 resolver=False)
    run_id = ci.create_run(company_name="Bad PDF Co", website=base,
                           user_id="u1", as_of=AS_OF)["run_id"]
    ci.discover(run_id)
    ci._append("ci.candidate_discovered", run_id=run_id,
               domain="badpdf.example", subject_type="candidate",
               subject_id="cand-badpdf00001",
               payload={"candidate_id": "cand-badpdf00001",
                        "company_id": "badpdf.example",
                        "url": f"{base}/broken.pdf",
                        "canonical_url": f"{base}/broken.pdf",
                        "source_type": "external_approved",
                        "title": "broken deck",
                        "discovery_method": "external_proposed",
                        "same_domain": False,
                        "source_class": "investor_material",
                        "why_relevant": "investor deck",
                        "availability": "PROPOSED", "rank": 99},
               idempotency_key="cand:badpdf:1")
    ci.approve(run_id, user_id="u1", approved_ids=["cand-badpdf00001"],
               rejected_ids=[])
    fetched = ci.fetch_approved(run_id)
    assert not fetched["ok"]
    assert fetched["failed"][0]["failure_type"] == "parse_error"
    assert not ci.store.retrieved(run_id)     # nothing polluted the evidence
