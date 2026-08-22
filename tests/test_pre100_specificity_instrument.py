"""The specificity instrument, with the controls §11 requires of a scorer.

This programme has twice had an INSTRUMENT invent a defect: a cue pointed at
a surface the product does not write on scored 0-3 across all fifty
companies, and a uniform result was read as a uniform failure. So each claim
this instrument can make gets a positive control (it fires when the defect is
present) and a negative control (it stays quiet when it is not).
"""
from intent_engine.pre100 import quality as Q
from intent_engine.pre100.specificity import (SIMILAR, _normalise, compare,
                                              extract)

TEMPLATE = ("{c} is a software platform business that runs on recurring "
            "software subscription: revenue is contracted and renews")


def _row(company, **fields):
    return {"company": company, "fields": fields}


def test_it_finds_the_defect_it_was_written_for():
    """POSITIVE CONTROL: the real Adobe/Cloudflare collapse."""
    report = compare([
        _row("Adobe Inc.", business_model=TEMPLATE.format(c="Adobe Inc.")),
        _row("Cloudflare, Inc.",
             business_model=TEMPLATE.format(c="Cloudflare, Inc.")),
    ])
    assert report["byte_identical_count"] == 1
    found = report["byte_identical"][0]
    assert found["field"] == "business_model"
    assert {found["a"], found["b"]} == {"Adobe Inc.", "Cloudflare, Inc."}


def test_it_stays_quiet_when_the_companies_genuinely_differ():
    """NEGATIVE CONTROL. An instrument that always fires measures itself."""
    report = compare([
        _row("Adobe Inc.",
             business_model="Adobe Inc. sells creative and marketing "
                            "software across three reportable segments"),
        _row("Cloudflare, Inc.",
             business_model="Cloudflare bills pay-as-you-go and contracted "
                            "customers usage-based fees for network access"),
    ])
    assert report["byte_identical_count"] == 0
    assert report["near_identical_count"] == 0


def test_the_company_name_is_not_what_makes_two_sentences_different():
    """The defect wore the company's name in every instance. A comparison
    that counts the name as content can never see it."""
    a = _normalise(TEMPLATE.format(c="Adobe Inc."), "Adobe Inc.")
    b = _normalise(TEMPLATE.format(c="Cloudflare, Inc."), "Cloudflare, Inc.")
    assert a == b


def test_universal_chrome_does_not_make_two_companies_look_identical():
    """The exclusion is required, or every pair duplicates on navigation."""
    chrome = ("Home · Your analyses · Guest demo session Leave demo "
              "Back to the analysis Sources Executive brief ")
    report = compare([
        _row("Adobe Inc.", board_answer=chrome + "Adobe should hold the "
             "subscription price and test the enterprise tier this quarter"),
        _row("Cloudflare, Inc.", board_answer=chrome + "Cloudflare should "
             "move contracted customers onto usage pricing before renewal"),
    ])
    assert report["byte_identical_count"] == 0


def test_a_passage_that_normalises_to_nothing_is_not_a_duplicate():
    """Two rows that are ONLY chrome would otherwise report as identical,
    which measures the filter rather than the product."""
    chrome = "Home · Your analyses Sources Executive brief"
    report = compare([_row("A Inc.", board_answer=chrome),
                      _row("B Inc.", board_answer=chrome)])
    assert report["byte_identical_count"] == 0
    assert report["field_coverage"]["board_answer"] == 0


def test_near_duplicates_are_caught_not_only_byte_identical_ones():
    base = ("is a semiconductor business that runs on the design and "
            "manufacture of a physical product sold into a capacity "
            "constrained supply chain and priced by wafer starts")
    report = compare([
        _row("Intel Corporation", business_model="Intel Corporation " + base),
        _row("Broadcom Inc.",
             business_model="Broadcom Inc. " + base + " each quarter"),
    ])
    assert report["near_identical_count"] == 1
    assert report["near_identical"][0]["similarity"] >= SIMILAR


def test_the_report_names_which_field_is_collapsing():
    report = compare([
        _row("A Inc.", business_model=TEMPLATE.format(c="A Inc."),
             recommendation="A Inc. should raise price in the enterprise"),
        _row("B Inc.", business_model=TEMPLATE.format(c="B Inc."),
             recommendation="B Inc. should cut its acquisition spend"),
    ])
    assert report["worst_fields"] == ["business_model"]


def test_extract_uses_the_same_locator_as_the_quality_gate():
    """One locator. If the two instruments disagree about where a field is,
    one of them is scoring a passage the other says does not exist."""
    shared = {k: c for k, _s, c in Q.DIMENSIONS}
    from intent_engine.pre100.specificity import FIELDS
    for field, _surface, cue in FIELDS:
        if field in shared and field in ("business_model",):
            assert cue == shared[field], field


def test_a_field_only_one_company_rendered_is_not_evidence():
    report = compare([_row("A Inc.", adversary="If we move, what do they do "
                           "— the nearest rival matches within a quarter"),
                      _row("B Inc.")])
    assert report["field_coverage"]["adversary"] == 1
    assert report["byte_identical_count"] == 0


def test_extract_returns_empty_rather_than_the_whole_surface():
    assert extract(r"nothing here", "some unrelated page text") == ""


# --- the quality gate's own controls ---------------------------------------

def test_every_core_dimension_has_an_instrument():
    """§26 named three dimensions nothing scored, and the gate failed fifty
    companies on `economic_reasoning` because no cue was pointed at it."""
    assert not set(Q.CORE) - {k for k, _s, _c in Q.DIMENSIONS}


def test_a_whole_surface_dimension_scores_the_surface_not_one_character():
    row = Q.score_dimension("presentation", "slides", ".",
                            text="Adobe Inc. " + ("x " * 800),
                            company="Adobe Inc.")
    assert row["score"] and row["score"] >= 8
    assert len(row["passage"]) > 1


def test_a_surface_that_did_not_render_is_not_a_zero():
    row = Q.score_dimension("qa", "qa", ".", text="", company="A Inc.")
    assert row["score"] is Q.NOT_MEASURED


# --- the instrument must stay able to see its own defect ------------------
#
# Widening the business-model locator to include the subject also pulled in
# the "SEC CIK 0000796343" that precedes it on the intro. Adobe and
# Salesforce still shared their sentence VERBATIM and the comparison reported
# them as distinct, because a ten-digit number differed. A guard that cannot
# fail is not a guard, and this one had been silently switched off by a
# change made two files away for a different reason.

REAL_INTRO = ("SEC CIK {cik} {name} is a software platform business that "
              "runs on recurring software subscription: revenue is "
              "contracted and renews, so the installed base carries next "
              "period's revenue before any new sale")


def test_an_identifier_does_not_hide_a_shared_sentence():
    report = compare([
        _row("Adobe Inc.",
             business_model=REAL_INTRO.format(cik="0000796343",
                                              name="Adobe Inc.")),
        _row("Salesforce, Inc.",
             business_model=REAL_INTRO.format(cik="0001108524",
                                              name="Salesforce, Inc.")),
    ])
    assert report["byte_identical_count"] == 1, (
        "a differing CIK hid a byte-identical business-model sentence")


def test_the_identifier_strip_does_not_erase_real_numbers():
    """NEGATIVE CONTROL. Stripping identifiers must not strip the figures
    that make a passage specific, or every quantified page collapses."""
    report = compare([
        _row("A Inc.", recommendation="What to do next: hold price while "
                       "the 2026 renewal cohort settles at 41% gross margin"),
        _row("B Inc.", recommendation="What to do next: hold price while "
                       "the 2026 renewal cohort settles at 63% gross margin"),
    ])
    assert report["byte_identical_count"] == 0
