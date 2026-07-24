"""V1.1 — domain validation, SSRF wall, redirect policy, parsing."""
import pytest

from intent_engine.company_ingestion.fetch import safe_fetch
from intent_engine.company_ingestion.parsing import parse_html
from intent_engine.company_ingestion.validation import (
    UnsafeURLRejected, redirect_allowed, resolve_public_addresses,
    validate_candidate_url,
)


# --- URL validation -----------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://localhost/x", "http://127.0.0.1/", "http://[::1]/",
    "http://10.0.0.8/", "http://192.168.1.1/", "http://169.254.1.1/",
    "ftp://example.com/", "file:///etc/passwd", "gopher://example.com",
    "javascript:alert(1)", "data:text/html,x", "http://example.com:2222/",
    "http://user:pass@example.com/", "http://nodots/",
])
def test_unsafe_urls_rejected(url):
    with pytest.raises((UnsafeURLRejected, ValueError)):
        validate_candidate_url(url)


def test_valid_public_url_accepted():
    assert validate_candidate_url("https://example.com/pricing")
    assert validate_candidate_url("http://example.com:80/")


def test_dns_resolution_must_be_public():
    with pytest.raises(UnsafeURLRejected, match="non-public"):
        resolve_public_addresses("evil.example",
                                 resolver=lambda h: ["10.0.0.5"])
    with pytest.raises(UnsafeURLRejected, match="non-public"):
        resolve_public_addresses("rebind.example",
                                 resolver=lambda h: ["1.2.3.4", "127.0.0.1"])
    assert resolve_public_addresses("ok.example",
                                    resolver=lambda h: ["93.184.216.34"])


def test_dns_failure_is_rejected_loudly():
    def failing(_):
        raise OSError("no dns")
    with pytest.raises(UnsafeURLRejected, match="DNS resolution failed"):
        resolve_public_addresses("nope.example", resolver=failing)


# --- redirect policy ----------------------------------------------------------

def test_redirects_apex_www_and_https_allowed():
    assert redirect_allowed("http://example.com/", "https://example.com/")
    assert redirect_allowed("https://example.com/", "https://www.example.com/")
    assert redirect_allowed("https://www.example.com/", "https://example.com/")


def test_redirects_to_unrelated_or_private_rejected():
    assert not redirect_allowed("https://example.com/",
                                "https://unrelated-company.com/")
    assert not redirect_allowed("https://example.com/",
                                "http://127.0.0.1/")
    assert not redirect_allowed("https://example.com/",
                                "ftp://example.com/")


def test_fetch_rejects_unsafe_target_before_any_transport():
    called = {"n": 0}
    def transport(url, timeout):
        called["n"] += 1
        return (200, {}, b"", False)
    result = safe_fetch("http://127.0.0.1/", transport=transport,
                        resolver=False)
    assert result["ok"] is False and result["failure_type"] == "blocked"
    assert called["n"] == 0                      # rejected BEFORE retrieval


def test_fetch_rejects_unrelated_redirect():
    import urllib.error, email
    def transport(url, timeout):
        raise urllib.error.HTTPError(
            url, 301, "moved",
            email.message_from_string("Location: https://other-co.com/\n"),
            None)
    result = safe_fetch("https://example.com/", transport=transport,
                        resolver=False)
    assert result["failure_type"] == "unsafe_redirect"


def test_fetch_enforces_mime_and_size():
    def bad_mime(url, timeout):
        return (200, {"content-type": "application/octet-stream"},
                b"\x00\x01", False)
    assert safe_fetch("https://example.com/", transport=bad_mime,
                      resolver=False)["failure_type"] == "bad_mime"
    def too_big(url, timeout):
        return (200, {"content-type": "text/html"}, b"x", True)
    assert safe_fetch("https://example.com/", transport=too_big,
                      resolver=False)["failure_type"] == "too_large"


def test_fetch_marks_429_retryable_and_403_not():
    import urllib.error, email
    def make(code):
        def t(url, timeout):
            raise urllib.error.HTTPError(url, code, "x",
                                         email.message_from_string(""), None)
        return t
    r429 = safe_fetch("https://example.com/", transport=make(429),
                      resolver=False)
    r403 = safe_fetch("https://example.com/", transport=make(403),
                      resolver=False)
    assert r429["retryable"] is True and r403["retryable"] is False
    assert r403["failure_type"] == "http_status"   # honest, no evasion


# --- parsing -------------------------------------------------------------------

def test_parse_extracts_and_reduces_boilerplate():
    html = """<html><head><title>T</title>
    <meta name="description" content="D"></head><body>
    <h1>Heading</h1><p>Body text.</p><p>Body text.</p>
    <script>var hidden = 'SECRET_JS';</script>
    <style>.x{color:red}</style></body></html>"""
    parsed = parse_html(html)
    assert parsed["title"] == "T"
    assert parsed["meta_description"] == "D"
    assert "SECRET_JS" not in parsed["text"]
    assert parsed["text"].count("Body text.") == 1   # deduped
    assert parsed["content_hash"] and parsed["parser_version"]


def test_parse_extracts_modified_date():
    html = ('<html><head><meta property="article:modified_time" '
            'content="2024-01-15T00:00:00+00:00"></head>'
            '<body><p>x</p></body></html>')
    assert parse_html(html)["modified_date"].startswith("2024-01-15")
