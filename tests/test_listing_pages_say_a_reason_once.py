"""Evidence rows: a filing is quoted past its cover page, and a reason
shared by several rows is stated once (prospect-98 round 8)."""
import inspect

from intent_engine.company_ingestion import provenance as PRV

COVER = ("UNITED STATES SECURITIES AND EXCHANGE COMMISSION Washington, D.C. 20549 FORM 10-K "
         "(Mark One) ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE SECURITIES EXCHANGE ACT OF 1934 ")
BODY = ("PART I\nItem 1. Business\nOverview\nAcme builds data infrastructure software for "
        "enterprises, sold by subscription to customers in regulated industries worldwide. "
        "Customers deploy it in their own clouds and pay for capacity as usage grows.\n"
        "Item 1A. Risk Factors\nOur business is subject to many risks.")


def test_a_filing_is_quoted_from_its_substance_not_its_cover():
    doc = {"filing": True, "form": "10-K", "text_content": COVER * 4 + BODY,
           "final_url": "https://www.sec.gov/Archives/edgar/data/1/0001/a10k.htm"}
    passage = PRV._passage(doc)
    assert "ANNUAL REPORT PURSUANT" not in passage and "Mark One" not in passage


def test_a_shared_reason_is_stated_once_and_still_accounted_for():
    from intent_engine.webapp.app import WebApp
    src = inspect.getsource(WebApp._evidence_screen)
    assert "Same reason as above." in src and "seen_reasons" in src
