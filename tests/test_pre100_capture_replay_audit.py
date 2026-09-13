"""The harness that stops us paying full price for the same evidence twice.

Every property here is one that cost a session to learn:

  - a route must be written the MOMENT it settles, because a preview restart
    destroyed a run and took its already-rendered surfaces with it;
  - collapse normalisation must mask longest-variant-first AND truncate at
    the first chrome marker, because four instruments were tried and three
    lied — one of them flatteringly;
  - a probe must report the DENOMINATOR it searched, because a grep whose
    pattern had silently narrowed returned nothing and was thirty seconds
    from being reported as a fix;
  - a surface naming a rival while another denies one is a contradiction
    regardless of which is right, because that pair shipped live 3 of 3.
"""
import json
import pathlib

import pytest

from intent_engine.pre100 import audit as A
from intent_engine.pre100 import capture as C
from intent_engine.pre100 import replay as R


# --- capture --------------------------------------------------------------

def test_a_route_is_on_disk_before_the_journey_finishes(tmp_path):
    """THE MEASURED FAILURE. Buffering a company's journey and writing at the
    end means a restart costs the whole company, including surfaces that had
    already rendered."""
    cap = C.Capture(tmp_path, "abc1234", "Meta Platforms, Inc.")
    cap.route("intro", 200, "https://x/intro", "<p>Meta introduction</p>")
    assert (cap.dir / "intro.txt").exists()
    assert (cap.dir / "manifest.json").exists(), (
        "the manifest is only written at the end, so a restart loses the "
        "run metadata for surfaces already captured")
    manifest = json.loads((cap.dir / "manifest.json").read_text())
    assert manifest["routes"]["intro"]["status"] == 200


def test_the_capture_records_which_sha_it_is_against(tmp_path):
    """Eight companies came to be spread across five builds because captures
    did not carry the SHA they were taken on."""
    cap = C.Capture(tmp_path, "fdbfe77", "Walmart Inc.")
    assert cap.manifest["deployed_sha"] == "fdbfe77"
    assert "fdbfe77" in str(cap.dir)


def test_the_raw_html_is_kept_beside_the_text(tmp_path):
    """Text loses charts, labels and structure. A section nobody thought to
    save is a section that costs a live run later."""
    cap = C.Capture(tmp_path, "abc1234", "Acme")
    cap.route("history", 200, "u", "<svg><title>chart</title></svg>")
    assert (cap.dir / "history.html").exists()
    assert "svg" in (cap.dir / "history.html").read_text()


def test_the_ten_board_questions_are_fixed_and_ordered():
    assert len(C.BOARD_QUESTIONS) == 10
    assert C.BOARD_QUESTIONS[0].startswith("What should management")


# --- collapse normalisation ----------------------------------------------

def test_variants_are_masked_longest_first():
    """Iteration order replaced "Caterpillar" before "Caterpillar Inc." and
    left a stray " Inc.", which deflated the measurement to 0/10."""
    out = A.normalise("Caterpillar Inc. builds machines", "Caterpillar Inc.")
    assert "inc." not in out, out
    assert "<co>" in out


def test_the_boilerplate_tail_is_truncated():
    """"Why this matters" varies by RUN rather than by company, so leaving it
    in made three identical answers score as distinct — the flattering
    error, and the one that nearly shipped."""
    a = A.normalise("Commit capital to capacity. Why this matters: one",
                    "Acme")
    b = A.normalise("Commit capital to capacity. Why this matters: two",
                    "Zenith")
    assert a == b, "run-varying chrome is still being compared"


def test_a_leading_word_that_is_also_a_word_is_not_masked():
    """"alpha" inside "Alphabet Inc." refused whole snapshots once, and
    "Bank of America" became the term "Bank". A first token is masked only
    when it is long enough not to be prose, and always on word boundaries."""
    assert "Bank" not in A.name_variants("Bank of America Corporation")
    assert "Alphabet" in A.name_variants("Alphabet Inc.")
    # and a boundary, so "Meta" does not eat "metadata"
    assert "metadata" in A.normalise("metadata and Meta", "Meta Platforms")


def test_strategic_nouns_are_never_normalised():
    out = A.normalise("Its order book and take-or-pay terms", "Acme")
    assert "order book" in out and "take-or-pay" in out


def test_identical_readings_score_as_identical():
    a = A.normalise("Acme is committing capital to capacity ahead of demand.",
                    "Acme")
    b = A.normalise("Beta is committing capital to capacity ahead of demand.",
                    "Beta")
    assert A.similarity(a, b) == 1.0


# --- mechanical audit -----------------------------------------------------

def test_giving_up_and_bounding_honestly_are_not_the_same():
    """A bounded honest answer is a pass; a give-up is not. Counting them
    together is what made "ban these strings" the wrong instruction."""
    gave_up = A.audit_route("full", "The analysis failed. " * 20)
    bounded = A.audit_route("full", "No estimate retrieved for this. " * 20)
    assert gave_up["failure_language"] and not gave_up["absence_language"]
    assert bounded["absence_language"] and not bounded["failure_language"]


def test_a_raw_enum_is_a_defect():
    assert A.audit_route("intro", "Our read: READ_BOUNDED " * 30)["raw_enums"]


def test_an_empty_route_is_flagged():
    assert A.audit_route("story", "short")["empty"] is True


def test_a_contradiction_is_computed_not_spotted():
    """3 of 3 companies named rivals on step 1 and denied them in Q&A."""
    found = A.contradictions({"intro": {"competitor": "CNH Industrial"},
                              "qa": {"competitor_denied": True}})
    assert found and found[0]["kind"] == "CROSS_SURFACE_CONTRADICTION"
    assert found[0]["named_on"] == ["intro"]


def test_agreement_is_not_reported_as_a_contradiction():
    assert A.contradictions({"intro": {"competitor": "CNH"},
                             "qa": {"competitor": "CNH"}}) == []


# --- the two capture layouts ---------------------------------------------

def test_either_harnesss_layout_reads(tmp_path):
    """Two harnesses wrote captures on the same day with different names.
    Normalising on READ means neither wave has to be re-run to compare."""
    theirs = tmp_path / "caterpillar"
    theirs.mkdir()
    (theirs / "run.json").write_text(json.dumps(
        {"company": "Caterpillar Inc.", "deployed_sha": "fdbfe77"}))
    (theirs / "connect.txt").write_text("Connect your company data. " * 20)
    report = A.audit_company(theirs)
    assert report["company"] == "Caterpillar Inc."
    step6 = [r for r in report["routes"] if r["route"] == "step6"][0]
    assert not step6.get("missing"), "connect.txt was not read as step6"


# --- replay ---------------------------------------------------------------

def _capture(tmp_path, **routes):
    d = tmp_path / "meta"
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({"company": "Meta"}))
    for name, text in routes.items():
        (d / f"{name}.txt").write_text(text)
    return d


def test_a_defect_that_reproduces_is_diagnosed_offline(tmp_path):
    d = _capture(tmp_path, full="Meta is committing capital to capacity.")
    out = R.find(d, "committing capital to capacity")
    assert out["status"] == R.REPRODUCED
    assert out["hits"][0]["route"] == "full"


def test_a_defect_that_does_not_reproduce_is_named(tmp_path):
    """"Could not reproduce" was previously indistinguishable from "did not
    look hard enough". RUNTIME_ONLY_DEFECT is the only kind that earns
    another live run."""
    d = _capture(tmp_path, full="A clean reading.")
    assert R.find(d, "take-or-pay")["status"] == R.NOT_REPRODUCED


def test_an_empty_capture_is_unreadable_not_a_pass(tmp_path):
    """THE GREP THAT SILENTLY NARROWED. A zero denominator must never read
    as absence."""
    d = tmp_path / "empty"
    d.mkdir()
    out = R.find(d, "anything")
    assert out["status"] == R.UNREADABLE
    assert out["searched_routes"] == 0


def test_the_denominator_is_always_reported(tmp_path):
    out = R.find(_capture(tmp_path, full="x", intro="y"), "zzz")
    assert out["searched_routes"] == 2


def test_a_delta_names_what_may_inherit_its_pass(tmp_path):
    before = _capture(tmp_path / "b", full="old reading", intro="same")
    after = _capture(tmp_path / "a", full="new reading", intro="same")
    out = R.delta(before, after)
    assert out["routes_changed"] == ["full"]
    assert "intro" in out["routes_unchanged_may_inherit_pass"]


@pytest.mark.parametrize("needle", ["WELLS FARGO", "wells fargo"])
def test_the_search_is_case_insensitive_by_default(tmp_path, needle):
    d = _capture(tmp_path, evidence="Sourced to WELLS FARGO & COMPANY/MN")
    assert R.find(d, needle)["status"] == R.REPRODUCED


# --- a lost run is not an answer -----------------------------------------

def test_a_lost_run_is_recognised():
    """MEASURED. A canary wave captured sixteen valid routes per company and
    then ten ERROR PAGES per company as "answers" — "This session does not
    have an analysis with that id" — and the audit compared them and reported
    a catastrophic collapse, because forty identical error pages are,
    technically, identical. It was the most alarming number of the session
    and it was entirely an artefact of a preview that had restarted."""
    assert C.run_is_gone(
        "That analysis is not available here. This session does not have an "
        "analysis with that id.")
    assert C.run_is_gone("Analyses are kept per session and are cleared when "
                         "the service restarts.")
    assert not C.run_is_gone(
        "Caterpillar is committing capital to capacity ahead of demand.")


def test_error_pages_are_not_loaded_as_answers(tmp_path):
    """The audit must refuse them, not compare them."""
    d = tmp_path / "co"
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps({"company": "Acme"}))
    (d / "qa.json").write_text(json.dumps([
        {"question": "What should management do?",
         "answer": "That analysis is not available here. This session does "
                   "not have an analysis with that id."}]))
    assert A.load_qa(d) == [], (
        "an error page was loaded as an answer, so a lost run reads as a "
        "collapse")


def test_a_real_answer_beside_an_error_page_survives(tmp_path):
    d = tmp_path / "co2"
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps({"company": "Acme"}))
    (d / "qa.json").write_text(json.dumps([
        {"question": "Q1", "answer": "A real strategic answer about Acme."},
        {"question": "Q2", "answer": "This session does not have an analysis "
                                     "with that id."}]))
    rows = A.load_qa(d)
    assert len(rows) == 1 and rows[0]["question"] == "Q1"
