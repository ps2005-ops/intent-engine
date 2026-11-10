"""Canonical extraction: segmentation, the furniture gate, window selection.

The regression that matters most here is the one this module was written for:
a production excerpt of `meta_description or text_content[:280]`, which turned
every marketing page into its own blurb and every filing into its cover page.
"""
import pytest

from intent_engine.strategic_intelligence import evidence_text as ET
from intent_engine.strategic_intelligence.observations import (
    derive_analyst_evidence, derive_observations,
)

# A real earnings exhibit's shape: a headline, a dateline with the event, and
# a table. Trimmed from Microsoft's 2026 Q4 exhibit and Caterpillar's Q2.
EARNINGS_DOC = {
    "source_id": "src-1",
    "final_url": "https://www.sec.gov/Archives/edgar/data/1/ex99.htm",
    "title": "Exhibit 99.1",
    "meta_description": "",
    "text_content": (
        "Exhibit 99.1.\n"
        "FOR IMMEDIATE RELEASE.\n"
        "Caterpillar Inc. Increases Dividend.\n"
        "IRVING, Texas, June 10, 2026 – The Board of Directors of "
        "Caterpillar Inc. (NYSE: CAT) voted today to raise the quarterly "
        "dividend by 12 cents, an eight percent increase, to one dollar and "
        "sixty-three cents ($1.63) per share of common stock.\n"
        "Second-quarter 2026 sales and revenues increased 24% to "
        "$20.5 billion.\n"
        "Caterpillar Contact: Tiffany Heikkila, tiffany.heikkila@cat.com.\n"
    ),
    "retrieved_at": "2026-08-05T00:00:00+00:00",
}

COVER_PAGE_DOC = {
    "source_id": "src-2",
    "final_url": "https://www.sec.gov/Archives/edgar/data/2/8k.htm",
    "title": "Form 8-K",
    "meta_description": "",
    "text_content": (
        "UNITED STATES.\nSECURITIES AND EXCHANGE COMMISSION.\n"
        "WASHINGTON, D.C. 20549.\nFORM 8-K.\nCURRENT REPORT.\n"
        "PURSUANT TO SECTION 13 OR 15(D).\n"
        "OF THE SECURITIES EXCHANGE ACT OF 1934.\n"
        "Date of Report (Date of earliest event reported) June 2, 2026.\n"
        "On June 2, 2026, Reid Hoffman, a member of the Board of Directors "
        "of the Company since 2017, informed the Company of his decision "
        "not to stand for re-election at the Annual Meeting.\n"
    ),
    "retrieved_at": "2026-08-05T00:00:00+00:00",
}

MARKETING_DOC = {
    "source_id": "src-3",
    "final_url": "https://www.example.test/store",
    "title": "Microsoft Store",
    "meta_description": ("Explore the Microsoft Store for apps and games on "
                         "Windows."),
    "text_content": (
        "Explore the Microsoft Store for apps and games on Windows.\n"
        "Play, buy, and enjoy new releases, and sale deals on the "
        "Microsoft Store.\n"
        "At Contoso, we believe that good software changes what "
        "institutions can do.\n"
    ),
    "retrieved_at": "2026-08-05T00:00:00+00:00",
}


# --- segmentation ---------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("Revenue was $90.0 billion. It grew 18%.", 2),
    ("Microsoft Corp. today announced results. The quarter ended June 30.", 2),
    ("Filed pursuant to Section 13 or 15(d). See Note 6.", 2),
    ("Contact No. 001-37845 was assigned. It is unchanged.", 2),
    ("J. P. Morgan advised on the deal. The fee was undisclosed.", 2),
])
def test_boundaries_are_decided_not_guessed(text, expected):
    assert len(ET.split_sentences(text)) == expected, text


def test_decimals_and_currency_survive_segmentation():
    parts = [s for _, s in ET.split_sentences(
        "Adjusted EPS was $4.81, up 32.5% year over year. Guidance held.")]
    assert "$4.81" in parts[0] and "32.5%" in parts[0]


def test_offsets_point_back_into_the_document():
    body = EARNINGS_DOC["text_content"]
    for offset, sentence in ET.split_sentences(body):
        assert body[offset:offset + 12] == sentence[:12]


# --- the furniture gate ---------------------------------------------------
@pytest.mark.parametrize("text,reason", [
    ("Explore the Microsoft Store for apps and games on Windows.",
     "marketing_imperative"),
    ("A featured collection of the latest Palantir blog posts.",
     "page_index"),
    ("At Palantir, we believe that with good data and the right software, "
     "institutions can solve their hardest problems.", "mission_statement"),
    ("ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE SECURITIES "
     "EXCHANGE ACT OF 1934.", "cover_page_boilerplate"),
    ("Skip to main content and browse the catalogue today.", "navigation"),
    ("© 2025 Palantir Technologies Inc. All rights reserved worldwide.",
     "legal_boilerplate"),
    ("Cash flow from investing activities: Capital expenditures – excluding "
     "equipment leased to others.", "financial_statement_line"),
    ("Contact: Tiffany Heikkila, tiffany.heikkila@cat.com, please write.",
     "contact_details"),
    ("Second Quarter.", "fragment"),
])
def test_real_furniture_is_named_by_its_reason(text, reason):
    assert ET.furniture_reason(text) == reason, text


def test_a_real_event_sentence_is_not_furniture():
    assert ET.furniture_reason(
        "IRVING, Texas, June 10, 2026 – The Board of Directors of "
        "Caterpillar Inc. (NYSE: CAT) voted today to raise the quarterly "
        "dividend by 12 cents.") == ""


def test_the_verb_check_does_not_eat_real_events():
    """`voted` was not in the lexicon and the dividend release was lost.

    The morphological fallback deliberately over-admits — "featured" and
    "finding" read as verbal — because a furniture sentence that reaches the
    classifier costs nothing and a real event that never does is gone.
    """
    assert ET.has_finite_verb("The Board voted today to raise the dividend.")
    assert ET.has_finite_verb("Palantir Joins Forces with the U.S. Army.")
    assert not ET.has_finite_verb("Blog: The Future of Drone Navigation")
    assert not ET.has_finite_verb("Net Income Attributable to Stockholders")


# --- the excerpt ----------------------------------------------------------
def test_excerpt_no_longer_starts_at_the_cover_page():
    """The measured defect, stated as a test."""
    old = (COVER_PAGE_DOC["meta_description"]
           or COVER_PAGE_DOC["text_content"][:280]).strip()
    assert "PURSUANT TO SECTION" in old          # what production used to see
    new = ET.evidence_excerpt(COVER_PAGE_DOC)
    assert "PURSUANT TO SECTION" not in new
    assert "not to stand for re-election" in new


def test_excerpt_prefers_body_over_meta_description():
    old = MARKETING_DOC["meta_description"]
    new = ET.evidence_excerpt(MARKETING_DOC)
    assert new != old


def test_excerpt_selects_the_dense_window_not_the_first_one():
    """A leading window is still a positional guess."""
    padding = ("The company operates in many regions and serves customers "
               "across several continents worldwide. ") * 12
    doc = dict(EARNINGS_DOC)
    doc["text_content"] = padding + EARNINGS_DOC["text_content"]
    excerpt = ET.evidence_excerpt(doc, max_chars=400)
    assert "raise the quarterly dividend" in excerpt


def test_a_thin_page_keeps_its_body_rather_than_vanishing():
    """Filtering must not delete a page that has one usable sentence."""
    thin = {"source_id": "t", "final_url": "https://x.test",
            "title": "T", "meta_description": "",
            "text_content": "Brightlake helps B2B software companies "
                            "automate customer onboarding and speed up time "
                            "to value for new accounts."}
    assert len(ET.evidence_excerpt(thin)) >= ET.MIN_USEFUL_EXCERPT_CHARS - 40
    assert ET.evidence_excerpt(thin)


def test_candidates_deduplicate_repeated_sentences():
    doc = dict(MARKETING_DOC)
    doc["text_content"] = (MARKETING_DOC["text_content"] * 3)
    texts = [c.text for c in ET.candidates(doc)]
    assert len(texts) == len(set(texts))


def test_extraction_is_bounded():
    doc = {"source_id": "b", "final_url": "https://x.test", "title": "B",
           "meta_description": "",
           "text_content": "The company reported revenue growth of 12% in "
                           "the quarter. " * 5000}
    assert len(ET.candidates(doc)) < 5000


# --- both derivations now read the same body ------------------------------
def test_observation_and_analyst_paths_agree_on_the_text():
    """Two derivations of one document must not disagree about what it says."""
    docs = [EARNINGS_DOC]
    obs = derive_observations(docs, company="Caterpillar Inc.")
    analyst = derive_analyst_evidence(docs)
    if obs and analyst:
        assert obs[0].excerpt == analyst[0].excerpt
