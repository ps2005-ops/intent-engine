"""A source list is only useful if a human can tell the rows apart.

MEASURED: an SEC exhibit's own <title> is its accession filename --
"duol-20260603", "exhibit991", "a8-kexhibit991". Discovery had already
attached a readable title ("SEC 8-K exhibit (2026-06-03)"), and the fetch
threw it away because the document's own title was non-empty.
"""
from intent_engine.company_ingestion.parsing import readable_title


def test_an_accession_filename_loses_to_the_filing_label():
    assert readable_title("duol-20260603",
                          "SEC 10-Q (2026-06-03)") == "SEC 10-Q (2026-06-03)"
    assert readable_title("exhibit991",
                          "SEC 8-K exhibit (2026-04-30)") == \
        "SEC 8-K exhibit (2026-04-30)"
    assert readable_title("a8-kexhibit991",
                          "SEC 8-K exhibit") == "SEC 8-K exhibit"
    assert readable_title("tsla-20260930.htm",
                          "SEC 10-K (2026-09-30)") == "SEC 10-K (2026-09-30)"


def test_a_real_headline_beats_the_generic_filing_label():
    """The document title is preferred whenever it is genuinely readable --
    a press release headline says more than "SEC 8-K exhibit"."""
    assert readable_title(
        "Tesla Reports Second Quarter 2026 Financial Results",
        "SEC 8-K exhibit (2026-07-23)"
    ) == "Tesla Reports Second Quarter 2026 Financial Results"
    assert readable_title("Investor Relations | Shopify", "SEC 10-K") == \
        "Investor Relations | Shopify"


def test_no_invention_when_there_is_nothing_to_fall_back_to():
    """Never manufacture a title the metadata cannot support."""
    assert readable_title("exhibit991", "") == "exhibit991"
    assert readable_title("exhibit991", None) == "exhibit991"
    assert readable_title("", "SEC 10-K") == "SEC 10-K"
    assert readable_title("", "") == ""


def test_ordinary_short_company_titles_are_left_alone():
    assert readable_title("Duolingo", "SEC 10-K") == "Duolingo"
    assert readable_title("Costco Wholesale Corporation", "") == \
        "Costco Wholesale Corporation"
