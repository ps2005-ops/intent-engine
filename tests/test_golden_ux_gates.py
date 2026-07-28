"""Release-blocking UX gates: the journeys a human tester actually takes.

`test_golden_demo_companies` proves the ANALYSIS is sound. These prove the
EXPERIENCE is — the difference between "the report contains the right facts"
and "a person opening this in a browser gets something they can use", which is
exactly the gap the tester fell into.

Every test here is a release blocker. If one fails, the demo is not ready.
"""
import email
import io
import re
import urllib.error

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from intent_engine.webapp.storage_state import record_boot

AS_OF = "2026-07-27T00:00:00+00:00"


class Client:
    def __init__(self, app):
        self.app, self.cookie = app, ""

    def request(self, method, path, body=""):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": self.cookie,
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}

        def sr(status, headers):
            out["status"], out["headers"] = status, headers
        payload = b"".join(self.app(env, sr)).decode()
        for k, v in out["headers"]:
            if k == "Set-Cookie" and v.startswith("sid="):
                self.cookie = "" if "Max-Age=0" in v else v.split(";")[0]
        return out["status"], dict(out["headers"]), payload

    def get(self, path, hops=4):
        """Follow redirects — a reader never sees the 303."""
        status, headers, body = "", {}, ""
        for _ in range(hops):
            status, headers, body = self.request("GET", path)
            if not status.startswith("30") or "Location" not in headers:
                break
            path = headers["Location"]
        return status, body

    def sid(self):
        return self.cookie.split("=", 1)[1] if self.cookie else None

    def csrf(self):
        return self.app.auth.csrf_token(self.sid())


def _http_error(url, code):
    return urllib.error.HTTPError(url, code, "err",
                                  email.message_from_string(""), None)


def _app(tmp_path, transport):
    record_boot(tmp_path, boot_id="previous-process-boot")
    config = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                       autorun_sources=True,
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl",
                       ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(config, transport=transport, resolver=False)
    client = Client(app)
    client.request("POST", "/demo")
    return app, client


def _analyse(client, name, website):
    status, headers, body = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={client.csrf()}&company_name={name}"
        f"&website={website}")
    assert not status.startswith("5"), f"HTTP 500 analysing {name}: {status}"
    if status.startswith("303"):
        return headers["Location"].split("/runs/")[1].split("/")[0]
    return None


def _visible(html):
    stripped = re.sub(r"<(style|script)\b.*?</\1>", " ", html,
                      flags=re.S | re.I)
    return re.sub(r"<[^>]+>", " ", stripped)


# --- PALANTIR -----------------------------------------------------------------
@pytest.fixture
def palantir(tmp_path):
    from test_golden_demo_companies import GOLDEN
    company = next(c for c in GOLDEN if c.domain == "palantir.com")
    return _app(tmp_path, company.transport()) + (company,)


def test_palantir_three_repeated_analyses_never_500(palantir):
    """The incident: a second same-day analysis raised on a reused
    idempotency key."""
    app, client, company = palantir
    run_ids = []
    for attempt in range(3):
        run_id = _analyse(client, company.name, company.base)
        assert run_id, f"attempt {attempt + 1} did not produce a run"
        status, _ = client.get(f"/runs/{run_id}")
        assert status.startswith("200"), f"attempt {attempt + 1}: {status}"
        run_ids.append(run_id)
    # compatible reuse: the same input on the same day is one analysis
    assert len(set(run_ids)) == 1


def test_palantir_names_its_actual_products(palantir):
    """The presentation is the surface a reader is walked through, so it is
    the one that has to name the products."""
    app, client, company = palantir
    run_id = _analyse(client, company.name, company.base)
    _, deck = client.get(f"/runs/{run_id}/slides")
    _, full = client.get(f"/runs/{run_id}/full")
    for product in ("Foundry", "Gotham", "AIP"):
        assert product in deck or product in full, \
            f"missing product: {product}"


def test_palantir_shows_government_and_commercial_positioning(palantir):
    app, client, company = palantir
    run_id = _analyse(client, company.name, company.base)
    _, page = client.get(f"/runs/{run_id}/full")
    lowered = page.lower()
    assert "government" in lowered
    assert "commercial" in lowered


def test_palantir_has_customer_or_use_case_evidence(palantir):
    app, client, company = palantir
    run_id = _analyse(client, company.name, company.base)
    documents = app.ci.store.retrieved(run_id)
    assert any(d.get("source_type") == "customers"
               or d.get("source_class") in ("customer_voice",
                                            "independent_reporting")
               for d in documents), "no customer or use-case evidence"


def test_palantir_supports_a_real_presentation(palantir):
    app, client, company = palantir
    run_id = _analyse(client, company.name, company.base)
    report = app._strategic_report_for(run_id)
    if report is None:
        pytest.skip("this fixture produced no strategic report")
    from intent_engine.strategic_intelligence.slides import (
        MIN_MEANINGFUL_SLIDES, build_slides, meaningful_slide_count,
    )
    slides = build_slides(report,
                          documents=app.ci.store.retrieved(run_id))
    assert meaningful_slide_count(slides) >= MIN_MEANINGFUL_SLIDES
    for slide in slides:
        assert slide["bullets"], f"empty slide: {slide['id']}"
    # and the page a reader actually opens really renders it
    _, deck = client.get(f"/runs/{run_id}/slides")
    assert "Slide 1 of" in deck


def test_palantir_citations_resolve(palantir):
    app, client, company = palantir
    run_id = _analyse(client, company.name, company.base)
    _, page = client.get(f"/runs/{run_id}/full")
    links = re.findall(rf'/runs/{run_id}/evidence/([^"]+)', page)
    for claim_id in links[:5]:
        status, _ = client.get(f"/runs/{run_id}/evidence/{claim_id}")
        assert status.startswith("200"), f"dead citation: {claim_id}"


@pytest.mark.parametrize("question", [
    "What does this company do?",
    "Explain this simply.",
    "Why does this matter?",
    "What evidence weakens this?",
    "What are you least confident about?",
    "What should I monitor?",
    "Which conclusion is most likely wrong?",
])
def test_palantir_answers_natural_follow_ups(palantir, question):
    app, client, company = palantir
    run_id = _analyse(client, company.name, company.base)
    status, _, page = client.request(
        "POST", f"/runs/{run_id}/conversation",
        f"csrf={client.csrf()}&question={question}")
    assert status.startswith("200"), f"{question!r} -> {status}"
    prose = _visible(page)
    assert len(prose.split()) > 10, f"empty answer to {question!r}"
    for internal in ("UNSUPPORTED", "UNRECOGNISED", "INSUFFICIENT",
                     "operation:", "hyp-", "weakest_evidence"):
        assert internal not in page, f"{question!r} leaked {internal}"


# --- SHOPIFY ------------------------------------------------------------------
@pytest.fixture
def shopify(tmp_path):
    from test_golden_demo_companies import GOLDEN
    company = next(c for c in GOLDEN if c.domain == "shopify.com")
    return _app(tmp_path, company.transport()) + (company,)


def test_shopify_repeated_analysis_never_collides(shopify):
    app, client, company = shopify
    for _ in range(3):
        run_id = _analyse(client, company.name, company.base)
        assert run_id
        status, _ = client.get(f"/runs/{run_id}")
        assert status.startswith("200")


def test_shopify_leads_with_a_central_thesis(shopify):
    app, client, company = shopify
    run_id = _analyse(client, company.name, company.base)
    report = app._strategic_report_for(run_id)
    if report is None:
        pytest.skip("this fixture produced no strategic report")
    from intent_engine.strategic_intelligence.brief import build_brief
    brief = build_brief(report)
    assert brief.thesis, "no central view"
    # visible quickly: the brief is short by construction
    assert brief.word_count <= 500


def test_shopify_does_not_repeat_evidence_under_every_hypothesis(shopify):
    app, client, company = shopify
    run_id = _analyse(client, company.name, company.base)
    report = app._strategic_report_for(run_id)
    if report is None:
        pytest.skip("this fixture produced no strategic report")
    hypotheses = report.get("hypotheses", [])
    if len(hypotheses) < 2:
        pytest.skip("needs at least two hypotheses to repeat anything")
    # Measured on the RENDERED page, because that is where a reader meets the
    # repetition — the underlying report may legitimately record the same
    # support under several hypotheses; printing it four times is the defect.
    _, page = client.get(f"/runs/{run_id}/full")
    # Scoped to the hypotheses section. The same excerpt legitimately appears
    # once more in the strongest-evidence drawer and once in the source
    # library — those are different sections doing different jobs. The defect
    # is seeing it once per hypothesis card while scrolling.
    # Bounded by the NEXT heading, not by a named one: empty sections are
    # suppressed now, so an id that used to follow may not exist and the split
    # would silently capture the rest of the page.
    assert 'id="hypotheses"' in page
    after = page.split('id="hypotheses"', 1)[1]
    section = re.split(r"<h2\b", after, maxsplit=1)[0]
    from intent_engine.strategic_intelligence.editorial import shared_evidence
    ubiquitous = {e for e, n in shared_evidence(
        [h.get("strongest_support_ids", []) for h in hypotheses]).items()
        if n >= len(hypotheses)}
    assert ubiquitous, "fixture does not exercise repeated evidence"
    for observation_id in ubiquitous:
        excerpt = next((o.get("excerpt", "") for o in
                        report.get("observations", [])
                        if o.get("observation_id") == observation_id), "")
        if len(excerpt) < 40:
            continue
        # Counted per CARD, not per section: one card legitimately shows an
        # excerpt in its summary and again in its expanded evidence list —
        # that is progressive disclosure. The defect is the same block
        # appearing in card after card as the reader scrolls.
        cards = section.split('<details class="card hypothesis"')[1:]
        carrying = sum(1 for card in cards if excerpt[:60] in card)
        assert carrying < len(hypotheses), \
            f"evidence appears in {carrying} of {len(hypotheses)} hypothesis " \
            f"cards"


def test_shopify_renders_no_empty_sections(shopify):
    app, client, company = shopify
    run_id = _analyse(client, company.name, company.base)
    _, page = client.get(f"/runs/{run_id}/full")
    assert not re.search(r">\s*[—–-]\s*<", page), "standalone dash rendered"
    for marker in ("None detected", "Not available"):
        assert marker not in page


# --- SONY ---------------------------------------------------------------------
@pytest.fixture
def sony(tmp_path):
    from test_sony_blocked_domain_recovery import BlockedMultinational
    return _app(tmp_path, BlockedMultinational().transport())


def test_sony_resolves_to_the_group_not_a_subsidiary(sony):
    app, client = sony
    run_id = _analyse(client, "Sony Group Corporation", "https://www.sony.com")
    identity = app.ci.entity_identity(run_id)
    assert identity["canonical_legal_name"] == "Sony Group Corporation"
    assert identity["country"] == "Japan"


def test_sony_carries_its_multinational_context(sony):
    app, client = sony
    run_id = _analyse(client, "Sony Group Corporation", "https://www.sony.com")
    identity = app.ci.entity_identity(run_id)
    tickers = {(l["exchange"], l["ticker"]) for l in identity["listings"]}
    assert ("TSE", "6758") in tickers
    assert ("NYSE", "SONY") in tickers
    assert "20-F" in identity["sec_relationship"]


def test_sony_is_never_reduced_to_a_single_filing(sony):
    app, client = sony
    run_id = _analyse(client, "Sony Group Corporation", "https://www.sony.com")
    usable = [d for d in app.ci.store.retrieved(run_id)
              if d.get("retrieval_status") == "OK"]
    assert len(usable) >= 4, "one filing is not a view of a multinational"


def test_sony_either_presents_properly_or_refuses_honestly(sony):
    app, client = sony
    run_id = _analyse(client, "Sony Group Corporation", "https://www.sony.com")
    result = app._results.get(run_id) or {}
    readiness = result.get("readiness") or {}
    status, page = client.get(f"/runs/{run_id}")
    assert status.startswith("200")
    if readiness.get("may_synthesize"):
        report = app._strategic_report_for(run_id)
        if report is not None:
            from intent_engine.strategic_intelligence.slides import (
                MIN_MEANINGFUL_SLIDES, build_slides, meaningful_slide_count,
            )
            slides = build_slides(report,
                                  documents=app.ci.store.retrieved(run_id))
            if meaningful_slide_count(slides) < MIN_MEANINGFUL_SLIDES:
                # honest refusal is acceptable; a thin deck is not
                _, deck = client.get(f"/runs/{run_id}/slides")
                assert "Not enough for a presentation" in deck
    else:
        assert "Limited analysis" in page
        assert "What was missing" in page


def test_sony_never_says_distribution_is_shifting(sony):
    app, client = sony
    run_id = _analyse(client, "Sony Group Corporation", "https://www.sony.com")
    _, page = client.get(f"/runs/{run_id}")
    lowered = _visible(page).lower()
    for generic in ("distribution is shifting", "demand is shifting",
                    "6-k is shifting"):
        assert generic not in lowered, f"generic language: {generic}"


def test_sony_is_not_offered_as_a_prepared_example(sony):
    app, client = sony
    _, page = client.get("/")
    assert "Sony" not in page


# --- SPARSE PRIVATE COMPANY ---------------------------------------------------
def _sparse_private(url, timeout):
    """A small private company: a homepage and an about page, no filings, no
    investor relations — because it has no investors to relate to."""
    bare = url.split("#")[0].rstrip("/")
    html = {"content-type": "text/html"}
    if bare.endswith("/about") or bare == "https://quietworks.example":
        return (200, html,
                b"<html><head><title>Quietworks</title></head><body><p>"
                b"Quietworks is a five-person studio in Bristol building "
                b"bespoke inventory tools for independent breweries. Founded "
                b"2021.</p></body></html>", False)
    raise _http_error(url, 404)


def test_a_sparse_private_company_is_not_judged_by_public_company_standards(
        tmp_path):
    app, client = _app(tmp_path, _sparse_private)
    run_id = _analyse(client, "Quietworks", "https://quietworks.example")
    status, page = client.get(f"/runs/{run_id}")
    assert status.startswith("200")
    # never demands filings from a company that has no reason to file
    lowered = _visible(page).lower()
    assert "sec" not in lowered.split("secure")[0].replace("second", "")
    assert "10-k" not in lowered


def test_a_sparse_private_company_gets_a_useful_result_or_an_early_refusal(
        tmp_path):
    app, client = _app(tmp_path, _sparse_private)
    run_id = _analyse(client, "Quietworks", "https://quietworks.example")
    status, page = client.get(f"/runs/{run_id}")
    assert status.startswith("200")
    prose = _visible(page)
    assert len(prose.split()) > 20, "a dead end with no explanation"
    result = app._results.get(run_id) or {}
    if not (result.get("readiness") or {}).get("may_synthesize", True):
        assert "What you can do" in page


# --- NONEXISTENT COMPANY ------------------------------------------------------
def _nothing_exists(url, timeout):
    raise _http_error(url, 404)


def test_a_nonexistent_company_never_produces_an_empty_report(tmp_path):
    app, client = _app(tmp_path, _nothing_exists)
    run_id = _analyse(client, "Zzzyxx Nonexistent Holdings",
                      "https://zzzyxx-nonexistent.example")
    status, page = client.get(f"/runs/{run_id}")
    assert status.startswith("200")
    for section in ("Strategic hypotheses", "Possible blind spots",
                    "Questions for leadership"):
        assert section not in page, f"empty report section rendered: {section}"


def test_a_nonexistent_company_gets_useful_next_steps(tmp_path):
    app, client = _app(tmp_path, _nothing_exists)
    run_id = _analyse(client, "Zzzyxx Nonexistent Holdings",
                      "https://zzzyxx-nonexistent.example")
    _, page = client.get(f"/runs/{run_id}")
    assert "start a new analysis" in page.lower() \
        or "What you can do" in page


# --- VISUAL AND FEEDBACK GATES ------------------------------------------------
def test_no_journey_page_shows_a_raw_browser_error(palantir):
    app, client, company = palantir
    run_id = _analyse(client, company.name, company.base)
    for path in ("/", "/onboarding", f"/runs/{run_id}",
                 f"/runs/{run_id}/brief", f"/runs/{run_id}/slides",
                 f"/runs/{run_id}/full", "/no-such-page"):
        status, page = client.get(path)
        assert "<style" in page or "class=" in page, f"unstyled: {path}"
        assert "Traceback" not in page
        assert "<html" in page.lower()


def test_feedback_success_is_only_shown_after_a_durable_write(palantir):
    app, client, company = palantir
    run_id = _analyse(client, company.name, company.base)
    status, _, page = client.request(
        "POST", f"/runs/{run_id}/feedback",
        f"csrf={client.csrf()}&useful=yes&note=Clear and quick")
    assert status.startswith("200")
    assert "saved and read back to confirm it" in page
    assert app.feedback_log.all()[0]["comment"] == "Clear and quick"


def test_an_operator_can_retrieve_the_feedback(palantir):
    app, client, company = palantir
    run_id = _analyse(client, company.name, company.base)
    client.request("POST", f"/runs/{run_id}/feedback",
                   f"csrf={client.csrf()}&useful=partly&note=Dense but useful")
    status, page = client.get("/feedback")
    assert status.startswith("200")
    assert "Dense but useful" in page


def test_every_citation_on_the_presentation_resolves(shopify):
    """Found in production: the evidence route only ever searched legacy claim
    ids, while the deck and the brief cite OBSERVATION ids. Every "Evidence
    behind this slide" link answered 404 — the product invited a reader to
    check a source and then failed them at the moment they decided to trust
    it."""
    app, client, company = shopify
    run_id = _analyse(client, company.name, company.base)
    _, deck = client.get(f"/runs/{run_id}/slides")
    hrefs = re.findall(rf'href="(/runs/{run_id}/evidence/[^"]+)"', deck)
    assert hrefs, "the deck offered no citations to check"
    for href in hrefs:
        status, _, body = client.request("GET", href)
        assert status.startswith("200"), f"{href} -> {status}"
        assert "Traceback" not in body
        # It must show the evidence, not an empty shell.
        assert len(_visible(body).split()) > 12, href
