"""Three ways a run lost evidence it had, each measured on the prospect-100 store.

  * Sherweb: distinct pages sharing a ~400-character navigation header were
    deduplicated as one page (2 of 13 kept).
  * Softchoice: 13 of 13 pages were a 119-character "Browser not supported"
    notice, admitted as company documents.
  * BlackLine: six /de/ translations took the slots of their English
    originals, and the language gate then set all six aside (4 of 10 kept).

Each property is asserted at its caller, beside a positive control.
"""
from __future__ import annotations

from intent_engine.company_ingestion.parsing import is_block_notice
from intent_engine.company_ingestion.readiness import usable_documents
from intent_engine.webapp.app import WebApp

NAV = ("Marketplace. Platform. Partner platform. Your control panel for "
       "billing, provisioning and more. Self-Service Portal. Customer "
       "Management. Cloud Solutions. Microsoft 365. Azure. Security. Backup. "
       "Communications. Managed Teams. Partner Resources. Partner Success. "
       "Marketing Resources. Training. Events. Blog. Company. About. Careers. "
       "Newsroom. Our Team. Awards. Contact. Login. Become a partner. ") * 2


def _doc(text, sid):
    return {"source_id": sid, "retrieval_status": "OK", "text_content": text}


def test_pages_sharing_a_header_are_not_one_page():
    docs = [_doc(NAV + "About Sherweb: founded in 2002 in Sherbrooke.", "a"),
            _doc(NAV + "Services: onboarding, migration and support.", "b"),
            _doc(NAV + "Our team: the leadership of the company.", "c")]
    assert len(NAV) > 400, "fixture must exceed the old 400-character key"
    assert len(usable_documents(docs)) == 3


def test_the_same_page_under_two_urls_is_still_one_document():
    """POSITIVE CONTROL: the dedup still does its original job."""
    same = NAV + "About Sherweb: founded in 2002 in Sherbrooke."
    assert len(usable_documents([_doc(same, "a"), _doc(same, "b")])) == 1


SOFTCHOICE = ("Browser not supported. Sorry, softchoice.com is not compatible "
              "with Internet Explorer. Please try one of these browsers.")


def test_a_browser_refusal_notice_is_recognised():
    assert is_block_notice(SOFTCHOICE)
    assert is_block_notice("Attention Required! | Cloudflare. Please enable "
                           "cookies. Sorry, you have been blocked.")


def test_a_real_page_that_mentions_browsers_is_not_a_notice():
    """POSITIVE CONTROL: wording alone never decides it; a page is long."""
    article = ("Our platform runs in any modern browser. " * 20 +
               "If your browser is not supported, contact support.")
    assert not is_block_notice(article)
    assert not is_block_notice("")


def test_the_fetcher_records_a_notice_as_a_refusal_not_a_document(tmp_path):
    """THE CALLER: fetch_approved, with a site that answers every path with
    the notice. Nothing is admitted; each page is a recorded access failure."""
    from intent_engine.company_ingestion.service import CompanyIngestionService
    body = (f"<html><head><title>Softchoice</title></head><body><p>"
            f"{SOFTCHOICE}</p></body></html>").encode()

    def transport(url, timeout):
        return 200, {"content-type": "text/html"}, body, False
    ci = CompanyIngestionService(tmp_path / "ci.jsonl", transport=transport,
                                 resolver=False)
    run_id = ci.create_run(company_name="Softchoice",
                           website="https://www.softchoice.com", user_id="u1",
                           as_of="2026-11-26T00:00:00+00:00")["run_id"]
    candidates = ci.discover(run_id)
    assert candidates, "fixture must discover something to fetch"
    ci.approve(run_id, user_id="u1",
               approved_ids=[c["candidate_id"] for c in candidates][:4],
               rejected_ids=[])
    ci.fetch_approved(run_id)
    assert ci.store.retrieved(run_id) == []
    kinds = {f.get("failure_type") for f in ci.store.failures(run_id)}
    assert "javascript_only" in kinds


def _cand(cid, url, source_type="about"):
    return {"candidate_id": cid, "url": url, "source_type": source_type,
            "source_class": "company_owned", "discovery_method": "homepage_link",
            "why_relevant": "linked from the homepage"}


def test_an_english_page_outranks_its_translation():
    picked = WebApp._recommended_candidate_ids(
        [_cand("de", "https://www.blackline.com/de/about/"),
         _cand("en", "https://www.blackline.com/about/")])
    assert picked.index("en") < picked.index("de") if "de" in picked \
        else "en" in picked


def test_investor_relations_is_not_mistaken_for_a_language():
    """POSITIVE CONTROL: /ir/ and /hr/ are paths, not locales."""
    picked = WebApp._recommended_candidate_ids(
        [_cand("ir", "https://example.com/ir/overview"),
         _cand("de", "https://example.com/de/about/")])
    assert picked[0] == "ir"
