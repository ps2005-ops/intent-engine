"""The Executive Brief and the Full Analysis as distinct depths of ONE answer.

THE DEFECT THIS COVERS
----------------------
Measured on the deployed preview (Palantir, commit e55d3b3) the three depths
were inverted, and the deepest surface in the product was the summary:

    /runs/<id>   816 words   the 60-second narrative
    /full        789 words   the "complete dossier"
    /brief       396 words   the "decision document"

And `/brief` did not consume the shared decision at all. It said "none of it
supports a strategic view strongly enough to put one forward" and offered a
DIFFERENT decision -- "Whether to close the evidence gap publicly..." -- while
the primary screen carried a DECISION_READY choice about services-to-product.
One run, opposite answers: the same class of defect the primary page was fixed
for, one layer down.

The tests are organised by what can go wrong now:

    1  a depth is not deeper than the one above it
    2  a deep surface reaches its own conclusion
    3  depth is manufactured by repetition
    4  absence is rendered as silence, a zero, or generic prose
    5  the machinery reaches the reader

Section 6 breaks each guard and checks it fails.
"""
import html as _html
import re

import pytest

from intent_engine.founder_brief import dossier as D
from intent_engine.founder_brief import narrative as N
from intent_engine.strategic_intelligence.decision import (
    DECISION_READY, INVESTIGATION_REQUIRED, WITHHELD, FounderDecision,
    decision_of,
)
from tests.test_scrollable_narrative import _brief, _narrative, _report


def _dossier(report=None, company="Shopify", decision=None, market=None):
    report = report if report is not None else _report(company)
    decision = decision or decision_of(report)
    story = _narrative(report, company, decision)
    return D.build_dossier(company=company, report=report, decision=decision,
                           narrative=story, market=market)


def _text(markup: str) -> str:
    markup = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", " ", markup)
    markup = re.sub(r"(?i)</(p|li|h[1-6]|dd|dt|section)>", "\n", markup)
    return _html.unescape(re.sub(r"<[^>]+>", " ", markup))


def _rendered(dossier, depth, company="Shopify"):
    return D.render_dossier(
        dossier, depth=depth, run_id="run-1",
        lead=D.render_decision_lead(dossier.decision, company, depth=depth))


def _dossier_body(markup: str) -> str:
    for tag in ("main", "div"):
        parts = markup.split(f'<{tag} class="dos">')
        if len(parts) > 1:
            return parts[1]
    raise AssertionError("no dossier on this page")


def _served(tmp_path):
    """The three real routes for one run."""
    from tests.test_strategic_intelligence import _strategic_webapp_run
    app, client, run_id = _strategic_webapp_run(tmp_path)
    out = {}
    for label, path in (("narrative", "/answer"),
                        ("brief", "/brief"),
                        ("full", "/full")):
        _, _, body = client.request("GET", f"/runs/{run_id}{path}")
        out[label] = body
    return out


def _words(body: str, cls: str) -> int:
    # `/full` renders the dossier as a <div>, because that route already opens
    # its own <main> and two main landmarks on one page is a real defect.
    for tag in ("main", "div"):
        parts = body.split(f'<{tag} class="{cls}">')
        if len(parts) > 1:
            return len(_text(parts[1]).split())
    return 0


# --- 1. each depth is deeper than the one above -------------------------------

def test_the_full_analysis_is_deeper_than_the_executive_brief(tmp_path):
    pages = _served(tmp_path)
    brief, full = _words(pages["brief"], "dos"), _words(pages["full"], "dos")
    assert full > brief * 1.5, (brief, full)


def test_the_executive_brief_adds_material_the_narrative_does_not_have(
        tmp_path):
    """Depth is not length. The brief must carry ANALYSIS the 60-second screen
    does not: how the business works, what changed and when, what the evidence
    says, competitive position, market expectations, opportunity and risk."""
    pages = _served(tmp_path)
    narrative_ids = set(re.findall(r'<section id="([a-z_]+)"',
                                   pages["narrative"]))
    brief_ids = set(re.findall(r'<section id="([a-z_]+)"', pages["brief"]))
    added = brief_ids - narrative_ids
    assert len(added) >= 4, sorted(added)
    for expected in ("operating_model", "evidence_families"):
        assert expected in brief_ids, sorted(brief_ids)


def test_the_full_analysis_carries_the_appendix_and_the_brief_does_not(
        tmp_path):
    """The difference between the two deep layers is REASONING AND EVIDENCE,
    not tone."""
    pages = _served(tmp_path)
    assert 'id="evidence_appendix"' in pages["full"]
    assert 'id="evidence_appendix"' not in pages["brief"]
    for full_only in ("assumptions", "scenarios", "unknowns", "monitoring"):
        assert f'id="{full_only}"' in pages["full"], full_only


def test_the_brief_lands_inside_its_reading_budget(tmp_path):
    """600-1000 useful words for a rich result. Not a padding target: the
    floor catches a memo that omitted supported sections, the ceiling catches
    one that reached depth by repeating itself."""
    pages = _served(tmp_path)
    words = _words(pages["brief"], "dos")
    assert 500 <= words <= 1200, words


# --- 2. one answer at every depth ---------------------------------------------

def test_no_deep_surface_reaches_its_own_conclusion(tmp_path):
    """The exact live defect: `/brief` withheld while the primary page was
    DECISION_READY, and put forward a different decision entirely."""
    from tests.test_strategic_intelligence import _strategic_webapp_run
    app, client, run_id = _strategic_webapp_run(tmp_path)
    report = app._real_result(run_id)["strategic_report"]
    decision = decision_of(report)
    # "" IS NO LONGER A PAGE: the default route redirects into step 1 of the
    # six-step story. The surfaces under test are the same three documents.
    for path in ("/intro", "/brief", "/full"):
        _, _, body = client.request("GET", f"/runs/{run_id}{path}")
        text = _text(body)
        withholding = "cleared the evidence bar" in text or \
                      "no decision is put forward" in text.lower()
        assert withholding == (decision.readiness == WITHHELD), (path, text[:200])
        if decision.readiness == DECISION_READY:
            for option in decision.options[:2]:
                assert option.label[:28] in text, (path, option.label)


def test_the_recommendation_is_the_same_on_every_surface(tmp_path):
    from tests.test_strategic_intelligence import _strategic_webapp_run
    app, client, run_id = _strategic_webapp_run(tmp_path)
    decision = decision_of(app._real_result(run_id)["strategic_report"])
    if not decision.recommended_next_move:
        pytest.skip("this run recommends no move")
    stem = decision.recommended_next_move[:40]
    # "" IS NO LONGER A PAGE: the default route redirects into step 1 of the
    # six-step story. The surfaces under test are the same three documents.
    for path in ("/intro", "/brief", "/full"):
        _, _, body = client.request("GET", f"/runs/{run_id}{path}")
        assert stem in _text(body), path


@pytest.mark.parametrize("readiness", [INVESTIGATION_REQUIRED, WITHHELD])
def test_a_bounded_result_is_never_revived_by_a_deeper_layer(readiness):
    decision = FounderDecision(
        readiness=readiness, mechanism="the rails carry the value",
        unsafe_because="only one course of action is supported by what was "
                       "retrieved",
        evidence_required=("Revenue mix is not disclosed.",))
    book = _dossier(decision=decision)
    for depth in (D.BRIEF, D.FULL):
        text = _text(_rendered(book, depth))
        assert 'Option 1' not in text, depth
        assert "The choice:" not in text, depth
        if readiness == WITHHELD:
            assert "cleared the evidence bar" in text, depth


# --- 3. depth is not manufactured by repetition -------------------------------

def test_no_sentence_is_printed_twice_in_either_document(tmp_path):
    pages = _served(tmp_path)
    for label in ("brief", "full"):
        body = _dossier_body(pages[label])
        seen, repeats = {}, []
        for line in _text(body).splitlines():
            line = line.strip()
            if len(line.split()) < 8:
                continue
            key = " ".join(re.findall(r"[a-z0-9]+", line.lower()))
            if key in seen:
                repeats.append(line[:70])
            seen[key] = line
        assert not repeats, (label, repeats)


def test_the_brief_does_not_restate_the_narrative(tmp_path):
    """The dossier is seeded with what the 60-second screen already said, so
    what the brief adds is genuinely additional."""
    pages = _served(tmp_path)
    narrative_lines = {
        " ".join(re.findall(r"[a-z0-9]+", ln.lower()))
        for ln in _text(pages["narrative"].split('<main class="nar">')[1])
        .splitlines() if len(ln.split()) >= 10}
    dossier_body = _dossier_body(pages["brief"])
    # Everything below the shared decision lead, which is SUPPOSED to restate
    # the answer -- that is what makes the memo readable on its own.
    below = dossier_body.split('id="operating_model"')[-1]
    below = below.split('<nav class="deeper"')[0]
    # NAVIGATION IS CHROME, NOT ANALYSIS. The secondary nav is deliberately
    # identical on every surface that carries it -- that is what makes it
    # navigable -- so comparing it against itself proves nothing and fails
    # for the one reason this test does not care about.
    below = re.sub(r"(?s)<nav\b.*?</nav>", " ", below)
    # The approval notice is a CONSENT notice, not analysis. It belongs
    # wherever artefacts are offered, on every surface that offers them.
    echoed = [ln for ln in _text(below).splitlines()
              if len(ln.split()) >= 10
              and "without your explicit approval" not in ln
              and " ".join(re.findall(r"[a-z0-9]+", ln.lower()))
              in narrative_lines]
    assert not echoed, echoed[:3]


def test_a_disclaimer_never_appears_more_than_once(tmp_path):
    pages = _served(tmp_path)
    for label in ("brief", "full"):
        text = _text(pages[label]).lower()
        for phrase in ("built only from public sources",
                       "nothing here comes from inside the company",
                       "descriptive market context"):
            assert text.count(phrase) <= 1, (label, phrase,
                                             text.count(phrase))


# --- 4. absence is stated, not silent -----------------------------------------

def test_every_missing_evidence_family_states_what_it_costs(tmp_path):
    pages = _served(tmp_path)
    text = _text(pages["brief"])
    assert "What this was built from" in text
    book = _dossier()
    for family in book.families:
        if not family["present"]:
            assert family["consequence"], family["key"]


def test_missing_market_data_is_a_limitation_not_a_zero():
    book = _dossier(market=None)
    text = _text(_rendered(book, D.BRIEF))
    assert "No market snapshot has been published" in text
    assert "0%" not in text and "$0" not in text


def test_an_unavailable_market_snapshot_never_becomes_a_number():
    book = _dossier(market={"available": False, "reason": "no series for this "
                                                          "ticker was found",
                            "disclaimer": "Descriptive market context, not an "
                                          "investment recommendation."})
    text = _text(_rendered(book, D.BRIEF))
    assert "Not established" in text
    assert "A missing price series is not a flat one." in text


def test_the_market_section_never_exposes_the_trading_engine():
    book = _dossier(market={
        "available": True,
        "modules": {"trajectory": {"what_changed": "The share price is 12% "
                                                   "above where it started "
                                                   "the quarter.",
                                   "so_what": "The market has already priced "
                                              "some of this in."}},
        "disclaimer": "Descriptive market context, not an investment "
                      "recommendation."})
    text = _text(_rendered(book, D.BRIEF)).lower()
    for banned in ("win rate", "sharpe", "alpha", "expectancy",
                   "paper trading", "strategy name", "profit factor"):
        assert banned not in text, banned


def test_competitor_absence_explains_what_it_costs_the_decision():
    report = dict(_report(), source_class_coverage={"company_owned": 9},
                  observations=[o for o in _report()["observations"]
                                if o.get("source_class") == "company_owned"])
    book = _dossier(report=report)
    text = _text(_rendered(book, D.BRIEF))
    # WHAT IT COSTS THE DECISION IS STILL SAID -- and it is now said as what
    # is MISSING from the read rather than as what the fetcher did. §13
    # forbids "No competitor's own account was retrieved for this run" on a
    # primary surface: it answers a question about retrieval in the section a
    # reader opened to learn about their market.
    assert "no rival's own account to check it against" in text
    assert "the risk this evidence cannot price" in text
    assert "What would improve it" in text
    assert "was retrieved for this run" not in text


# --- 5. the machinery never reaches the reader --------------------------------

def test_no_internal_vocabulary_or_taxonomy_in_either_document(tmp_path):
    from intent_engine.founder_brief.contract import INTERNAL_VOCABULARY
    from intent_engine.strategic_intelligence.records import SOURCE_CLASSES
    pages = _served(tmp_path)
    for label in ("brief", "full"):
        body = _dossier_body(pages[label])
        # The legacy report still follows the dossier on /full; this asserts
        # the DOSSIER is clean, which is the part this cycle owns.
        body = body.split('<div class="si"')[0]
        text = _text(body)
        low = text.lower()
        for token in INTERNAL_VOCABULARY:
            assert token not in low, (label, token)
        # Only the underscore-bearing enums are unambiguous machine
        # vocabulary. "competitor" and "unknown" are ordinary English and
        # appear legitimately in prose ("turn partners into competitors").
        for source_class in SOURCE_CLASSES:
            if "_" in source_class:
                assert source_class not in low, (label, source_class)
        for state in (DECISION_READY, INVESTIGATION_REQUIRED, WITHHELD):
            assert state not in text, (label, state)
        # AN ARROW IS INTERNAL NOTATION IN PROSE AND AN AFFORDANCE IN A
        # CONTROL. This forbids "observation → hypothesis → decision" reaching
        # a reader, which is right; it must not forbid the "Next →" button,
        # which is the only way through the six-step story. So the navigation
        # is excluded and the document text is checked exactly as before.
        prose = re.sub(r"(?s)<nav\b.*?</nav>", " ", body)
        prose = re.sub(r"Next →|← Back|← Leave|← Previous|Next ⟶", " ",
                       _text(prose))
        assert "→" not in prose, label
        assert not re.search(r"qualifying signal", low), label


def test_source_counts_are_provenance_not_narration(tmp_path):
    """A count belongs on a chip that says what KIND of source it is, never in
    a sentence like "12 page(s) were read and 10 carried evidence"."""
    pages = _served(tmp_path)
    for label in ("brief", "full"):
        text = _text(_dossier_body(pages[label]))
        assert "page(s) were read" not in text, label
        assert "source(s)." not in text, label


def test_an_analog_always_states_where_the_comparison_stops():
    book = _dossier()
    passage = book.passage("analogs")
    if passage is None or not passage.items:
        pytest.skip("this fixture matched no comparable pattern")
    for item in passage.items:
        assert item["breaks"], item["text"][:60]
    text = _text(_rendered(book, D.FULL))
    assert "Where the comparison stops" in text


# --- 6. break every guard -----------------------------------------------------

def test_break_the_brief_repeats_the_narrative_verbatim():
    """Without the seeded ledger the dossier would restate the primary screen.
    Removing the seed must show up as overlap, or the seed is not the thing
    doing the work."""
    report = _report()
    decision = decision_of(report)
    story = _narrative(report, "Shopify", decision)
    seeded = D.build_dossier(company="Shopify", report=report,
                             decision=decision, narrative=story)
    unseeded = D.build_dossier(company="Shopify", report=report,
                               decision=decision, narrative=None)
    assert unseeded.words(D.BRIEF) > seeded.words(D.BRIEF)


def test_break_a_passage_with_nothing_behind_it_is_rendered():
    empty = D.Passage("x", "A heading over nothing")
    assert not empty.is_substantive
    thin = D.Passage("x", "Thin", paragraphs=("Four words only here.",))
    assert not thin.is_substantive
    real = D.Passage("x", "Real", paragraphs=(
        "This one states a consequence a founder can act on today.",))
    assert real.is_substantive


def test_break_the_full_analysis_loses_its_depth_markers():
    book = _dossier()
    full_only = {p.key for p in book.passages if p.depth == D.FULL}
    assert full_only, "nothing is full-only, so the layers cannot differ"
    assert not (full_only & {p.key for p in book.at(D.BRIEF)})


def test_break_signal_telemetry_reaches_a_monitoring_line():
    dirty = ("It directly tests the hypothesis that moving from selling a "
             "product toward operating the rails beneath it; if it fails, "
             "that view is wrong. 4 qualifying signal(s) matched: "
             "checkout_identity_rails, infrastructure_positioning")
    cleaned = D._readable_reason(dirty)
    assert "qualifying signal" not in cleaned
    assert "checkout_identity_rails" not in cleaned
    assert "directly tests the hypothesis" not in cleaned


def test_break_a_scraped_nav_dump_is_cited_as_a_quotation():
    obs = {"observation_id": "o1", "source_title": "Acme api",
           "source_class": "company_owned",
           "excerpt": "Acme api page. commerce infrastructure powering "
                      "commerce. Shop Pay checkout, payments, capital, "
                      "fulfillment, point of sale, Markets and Audiences.",
           "strategic_signal": "Acme presents payments and identity as "
                               "first-party rails across every surface."}
    assert D._readable_excerpt(obs).startswith("Acme presents payments")


def test_break_a_filing_cover_page_is_cited_as_its_content():
    """Live on the preview: the single most valuable source in the run --
    Palantir's 10-Q -- was cited as its checkbox furniture."""
    obs = {"observation_id": "o1", "source_title": "SEC 10-Q (2026-08-04)",
           "source_class": "investor_material",
           "excerpt": "\u2612. QUARTERLY REPORT PURSUANT TO SECTION 13 OR "
                      "15(d) OF THE SECURITIES EXCHANGE ACT OF 1934. "
                      "\u2610. TRANSITION REPORT PURSUANT TO SECTION 13",
           "strategic_signal": "Palantir discloses specific risks rather "
                               "than generic caveats."}
    assert D._readable_excerpt(obs).startswith("Palantir discloses")
    # ...and with nothing better behind it, the citation is dropped, not
    # rendered as furniture.
    assert D._readable_excerpt({k: v for k, v in obs.items()
                                if k != "strategic_signal"}) == ""


def test_break_a_gap_names_a_family_the_run_actually_retrieved():
    """Live on the preview once SEC filings started arriving: the brief listed
    "Filings and investor material - 1" and, four lines down, "no investor
    material ... has corroborated this yet"."""
    from intent_engine.strategic_intelligence.reasoning import (
        build_strategic_report,
    )
    from intent_engine.strategic_intelligence.shopify_fixture import (
        shopify_observations,
    )
    report = build_strategic_report(company_name="Shopify",
                                    observations=shopify_observations())
    retrieved = {o.source_class for o in report.observations}
    for gap in report.evidence_gaps:
        if "has corroborated this yet" not in gap:
            continue
        for present, words in (("investor_material", "investor material"),
                               ("customer_voice", "customer account"),
                               ("competitor", "competitor"),
                               ("independent_reporting", "independent report")):
            if present in retrieved:
                assert words not in gap, (present, gap)


def test_break_the_bounded_answer_states_its_reason_twice():
    """Live on Basecamp: the bounded headline EMBEDS the reason, and the line
    below restated the same clause in the next sentence."""
    reason = ("the public record carries what this company says about "
              "itself, not the mechanism behind it")
    decision = FounderDecision(readiness=INVESTIGATION_REQUIRED,
                               mechanism="the rails carry the value",
                               unsafe_because=reason)
    markup = D.render_decision_lead(decision, "Basecamp", depth=D.BRIEF)
    text = _text(markup)
    assert text.count(reason) == 1, text.count(reason)


def test_macro_is_named_only_when_the_evidence_names_it():
    """No generic GDP or interest-rate commentary. A macro factor earns a line
    when something the run RETRIEVED mentions it; otherwise the absence is
    stated once, with what it leaves untested."""
    book = _dossier()
    text = _text(_rendered(book, D.FULL))
    assert "Macro and regulatory exposure" in text
    assert "Nothing retrieved ties this decision to a macro or regulatory" \
        in text or "Named because the retrieved evidence mentions it" in text
    # ...and it is never a zero
    assert "0%" not in text

    # when the evidence DOES name one, the mechanism comes with it
    report = _report()
    obs = list(report["observations"])
    obs.append({"observation_id": "macro-1",
                "source_title": "SEC 10-Q", "source_class": "investor_material",
                "excerpt": "A material share of revenue depends on government "
                           "appropriation cycles that can slip a quarter.",
                "date": "2026-08-04"})
    named = _dossier(report=dict(report, observations=obs))
    macro = named.passage("macro")
    assert macro.items, "a named macro factor produced no line"
    assert macro.items[0]["label"] == "Public budget exposure"


def test_break_two_unrelated_companies_receive_the_same_deep_report():
    a = _text(_rendered(_dossier(company="Shopify"), D.FULL))
    b_report = dict(_report(), company_name="Northwind",
                    mental_model={}, opportunities=[], blind_spots=[],
                    timeline=[], questions=[])
    b = _text(_rendered(_dossier(report=b_report, company="Northwind"),
                        D.FULL, company="Northwind"))
    a_words = set(re.findall(r"[a-z]{6,}", a.lower()))
    b_words = set(re.findall(r"[a-z]{6,}", b.lower()))
    overlap = len(a_words & b_words) / max(len(a_words | b_words), 1)
    assert overlap < 0.8, overlap
