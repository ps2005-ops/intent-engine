"""Adversarial cases for evidence independence.

Every test here is written so that the OBVIOUS wrong implementation — count
the rows, or count the distinct URLs — fails it. A test that a row-counter
would also pass proves nothing about independence.
"""
import pytest

from intent_engine.company_ingestion import independence as IND


def doc(url, *, source_class="independent_reporting", text="",
        content_hash=None, filing=None, source_id=""):
    return {
        "source_id": source_id or url,
        "final_url": url,
        "original_url": url,
        "source_class": source_class,
        "text_content": text,
        # A distinct hash by default: tests that mean "same document" say so
        # explicitly, so nothing here relies on the hash accidentally matching.
        "content_hash": content_hash if content_hash is not None else url,
        "filing": filing,
    }


RELEASE = ("Acme Corporation today announced a definitive agreement to "
           "acquire Beta Systems for eight hundred million dollars in cash "
           "and stock, expanding its platform into industrial automation "
           "and adding four hundred engineers across three continents. "
           "The transaction is expected to close in the fourth quarter "
           "subject to customary regulatory approvals and conditions.")


# --- §10.1 same filing twice -------------------------------------------------
def test_the_same_filing_twice_is_one_observation():
    filing = doc("https://www.sec.gov/Archives/edgar/data/1/a.htm",
                 source_class="investor_material", text=RELEASE,
                 content_hash="H1", filing={"form": "10-K"})
    out = IND.assess([filing, dict(filing)])
    assert out["evidence_count"] == 2
    assert out["independent_evidence_count"] == 1
    assert out["duplicate_document_count"] == 1
    assert out["primary_source_count"] == 1


# --- §10.2 filing + an article quoting it ------------------------------------
def test_an_article_quoting_a_filing_is_not_a_second_observation():
    filing = doc("https://www.sec.gov/Archives/edgar/data/1/a.htm",
                 source_class="investor_material", text=RELEASE,
                 content_hash="H1", filing={"form": "8-K"})
    quoting = doc("https://news.example.com/story", text=RELEASE,
                  content_hash="H2")
    out = IND.assess([filing, quoting])
    assert out["republication_count"] == 1
    assert out["independent_evidence_count"] == 1


# --- §10.3 company release + syndicated copy ---------------------------------
def test_a_syndicated_copy_of_a_release_adds_nothing():
    release = doc("https://acme.com/press/acquisition",
                  source_class="company_owned", text=RELEASE,
                  content_hash="H1")
    wire = doc("https://finance.yahoo.com/news/acme-acquires",
               text=RELEASE, content_hash="H2")
    out = IND.assess([release, wire])
    assert out["republication_count"] == 1
    assert out["independent_evidence_count"] == 0
    assert out["corroboration_state"] == IND.SINGLE_SOURCE


# --- §10.4 two genuinely independent primary sources -------------------------
def test_two_unrelated_outside_sources_corroborate():
    out = IND.assess([
        doc("https://reuters.com/a", text="Acme raised prices twice this "
            "year according to three distributors we contacted."),
        doc("https://ft.com/b", text="Industrial buyers report a shortage "
            "of qualified integrators across the Midwest region."),
    ])
    assert out["independent_evidence_count"] == 2
    assert out["corroboration_state"] == IND.INDEPENDENTLY_CORROBORATED


# --- §10.5 self-report + independent customer evidence -----------------------
def test_a_self_report_does_not_corroborate_itself():
    out = IND.assess([
        doc("https://acme.com/customers", source_class="company_owned",
            text="Our customers love the platform and renew at high rates."),
        doc("https://g2.example.com/reviews", source_class="customer_voice",
            text="Deployment took nine months and support was slow to "
                 "respond during the migration window."),
    ])
    assert out["company_self_report_count"] == 1
    assert out["independent_external_count"] == 1
    assert out["independent_evidence_count"] == 1
    assert out["corroboration_state"] == IND.PARTIALLY_INDEPENDENT


# --- §10.6 different URLs, same origin ---------------------------------------
def test_different_urls_from_one_publisher_are_one_vantage_point():
    out = IND.assess([
        doc("https://news.example.com/story-1", text="First separate story."),
        doc("https://news.example.com/story-2", text="Second, different."),
        doc("https://www.example.com/story-3", text="Third, also different."),
    ])
    assert out["evidence_count"] == 3
    assert out["same_origin_count"] == 2
    assert out["independent_evidence_count"] == 1


# --- §10.7 unknown lineage ---------------------------------------------------
def test_unknown_lineage_is_reported_not_assumed():
    out = IND.assess([doc("https://a.example/x", source_class="")])
    assert out["unknown_lineage_count"] == 1
    assert out["independent_evidence_count"] == 0
    assert out["corroboration_state"] == IND.LINEAGE_UNAVAILABLE


# --- §10.8 contradictory independent sources ---------------------------------
def test_a_contradiction_stays_visible_beside_corroboration():
    out = IND.assess(
        [doc("https://reuters.com/a", text="Revenue grew by twelve percent."),
         doc("https://ft.com/b", text="Revenue fell over the same period.")],
        contradicting_ids=["https://ft.com/b"])
    assert out["corroboration_state"] == IND.INDEPENDENTLY_CORROBORATED
    # Both survive AND the conflict is still on the record: a single state
    # cannot say "two independent sources" and "they disagree" at once.
    assert out["contradicting_evidence_ids"] == ["https://ft.com/b"]
    assert out["independent_evidence_count"] == 2


# --- §10.A ten duplicates ----------------------------------------------------
def test_ten_duplicates_do_not_add_independence():
    base = [doc("https://reuters.com/a", text="A distinct first report."),
            doc("https://ft.com/b", text="A distinct second report.")]
    before = IND.assess(base)
    after = IND.assess(base + [dict(base[0]) for _ in range(10)])
    assert after["evidence_count"] == 12
    assert (after["independent_evidence_count"]
            == before["independent_evidence_count"] == 2)
    assert after["duplicate_document_count"] == 10


def test_the_same_document_mirrored_on_two_domains_is_one_observation():
    """Identical bytes at two addresses is one observation, not two.

    Written because a break proof that added SAME_DOCUMENT to the
    independence-bearing set went NOT_CAUGHT: every duplicate in the suite
    shared an origin with its original, so origin grouping absorbed the
    mutation and the lineage rule was never the thing under test. A press
    release mirrored on a second domain is the case that separates them.
    """
    body = "The board approved a two hundred million dollar buyback today."
    out = IND.assess([
        doc("https://acme.com/press/buyback", source_class="company_owned",
            text=body, content_hash="SAME"),
        doc("https://mirror.example/acme-buyback",
            source_class="independent_reporting", text=body,
            content_hash="SAME"),
    ])
    assert out["duplicate_document_count"] == 1
    assert out["independent_evidence_count"] == 0


def test_rows_with_no_url_collapse_into_one_unknown_origin():
    """Ten pasted documents of unknown provenance are not ten vantage points.

    Also written after a NOT_CAUGHT: counting independence per ROW rather
    than per ORIGIN is invisible while every row carries a URL, because
    `classify` has already collapsed same-origin rows by then. Rows with no
    URL are the only place the aggregation is load-bearing.
    """
    rows = [{"source_id": f"pasted-{i}", "final_url": "", "original_url": "",
             "source_class": "independent_reporting",
             "text_content": f"A distinct pasted observation number {i}.",
             "content_hash": f"H{i}"} for i in range(10)]
    out = IND.assess(rows)
    assert out["evidence_count"] == 10
    assert out["independent_evidence_count"] == 1


# --- §10.B ten irrelevant documents ------------------------------------------
def test_ten_more_company_pages_do_not_raise_corroboration():
    base = [doc("https://reuters.com/a", text="A distinct first report.")]
    noise = [doc(f"https://acme.com/careers/{i}", source_class="company_owned",
                 text=f"Job posting number {i} for a role in engineering.")
             for i in range(10)]
    before = IND.assess(base)
    after = IND.assess(base + noise)
    assert after["evidence_count"] == 11
    assert (IND.CORROBORATION_ORDER[after["corroboration_state"]]
            <= IND.CORROBORATION_ORDER[before["corroboration_state"]])
    assert after["independent_evidence_count"] == 1


# --- §10.C syndication never strengthens -------------------------------------
def test_replacing_an_independent_source_with_a_syndication_never_helps():
    shared = "The company said it would open two plants in Ohio next year."
    independent = [doc("https://reuters.com/a", text=shared),
                   doc("https://ft.com/b", text="Separately reported detail "
                       "about supplier concentration in the region.")]
    syndicated = [doc("https://reuters.com/a", text=shared),
                  doc("https://ft.com/b", text=shared)]
    strong = IND.assess(independent)
    weak = IND.assess(syndicated)
    assert (IND.CORROBORATION_ORDER[weak["corroboration_state"]]
            < IND.CORROBORATION_ORDER[strong["corroboration_state"]])
    assert weak["independent_evidence_count"] == 1


# --- §10.D two unknowns are not independence ---------------------------------
def test_a_second_unknown_url_does_not_manufacture_independence():
    one = IND.assess([doc("https://a.example/x", source_class="")])
    two = IND.assess([doc("https://a.example/x", source_class=""),
                      doc("https://b.example/y", source_class="")])
    assert two["unknown_lineage_count"] == 2
    assert (two["independent_evidence_count"]
            == one["independent_evidence_count"] == 0)
    assert two["corroboration_state"] == IND.LINEAGE_UNAVAILABLE


# --- missing is not zero -----------------------------------------------------
def test_an_empty_set_is_unavailable_not_uncorroborated():
    out = IND.assess([])
    assert out["state"] == "MEASURED"
    assert out["corroboration_state"] == IND.LINEAGE_UNAVAILABLE
    assert out["concentration_ratio"] is None


def test_concentration_is_none_not_zero_when_there_is_nothing_to_concentrate():
    assert IND.assess([])["concentration_ratio"] is None
    out = IND.assess([doc("https://a.example/1", text="one"),
                      doc("https://a.example/2", text="two")])
    assert out["concentration_ratio"] == 1.0


@pytest.mark.parametrize("state", IND.CORROBORATION_STATES)
def test_every_corroboration_state_is_ordered(state):
    assert state in IND.CORROBORATION_ORDER
