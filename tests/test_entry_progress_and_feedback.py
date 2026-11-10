"""Entity entry, the progress page, and the step-6 feedback workflow.

The three customer-facing seams this convergence run opened. Each test below
is either a defect that was observed on the deployed product or a boundary
that must not move — never a restatement of what the code obviously does.
"""
from __future__ import annotations

import pytest

from intent_engine.company_ingestion import suggest as CS
from intent_engine.founder_brief import absence
from intent_engine.webapp import autocomplete as AC
from intent_engine.webapp.feedback import (POSITIVE_TAGS, TAG_DEFECT,
                                           TAG_KEYS, FeedbackLog)


# ===========================================================================
# entity suggestion
# ===========================================================================
def test_a_partial_word_finds_the_company():
    """Autocomplete runs on every keystroke.

    Requiring whole words made the feature useless until the customer had
    finished typing the name they were asking for help with.
    """
    rows = CS.suggest("cloudfl", limit=5, allow_registrant=False)
    assert rows and rows[0].legal_name.lower().startswith("cloudflare")


def test_a_suggestion_carries_a_canonical_identity_not_just_a_name():
    """§4, §89. A name alone does not let a customer confirm anything."""
    row = CS.suggest("Cloudflare", limit=1, allow_registrant=False)[0]
    assert row.legal_name.endswith("Inc.")
    assert row.ticker and row.country and row.domain
    assert row.describe()


def test_a_domain_is_never_invented():
    """The wrong-company failure arriving through a guessed URL.

    Every field on a suggestion comes from a source that carries it. A row
    with no domain renders no domain, and the analysis opens on the CIK.
    """
    for row in CS.suggest("Toyota", limit=5, allow_registrant=False):
        assert not row.domain or "." in row.domain
        assert "example" not in row.domain


def test_a_middle_of_word_match_never_outranks_a_real_one():
    """"amd" sits inside "camden", and Camden National outranked AMD."""
    rows = CS.suggest("AMD", limit=4, allow_registrant=False)
    assert rows
    assert "advanced micro" in rows[0].legal_name.lower()


def test_two_real_companies_of_one_name_are_both_offered():
    """§6. Picking one produces a confident report about the wrong company."""
    names = {r.legal_name for r in CS.suggest("Sony", limit=6,
                                              allow_registrant=False)}
    assert len(names) > 1


def test_one_company_is_one_row_however_many_sources_hold_it():
    rows = CS.suggest("Shopify", limit=6, allow_registrant=False)
    leading = [r for r in rows if r.legal_name.lower().startswith("shopify")]
    assert len(leading) == 1, [r.legal_name for r in rows]


def test_a_shouting_registrant_title_is_made_readable():
    assert CS._readable("JOHNSON & JOHNSON") == "Johnson & Johnson"
    assert CS._readable("BANK OF AMERICA CORP /DE") == "Bank Of America Corp"
    # A correctly cased name is left exactly as its source wrote it.
    assert CS._readable("Vale S.A.") == "Vale S.A."
    assert CS._readable("eBay Inc.") == "eBay Inc."


def test_the_suggestion_endpoint_reaches_no_tenant_state():
    """§82. Enforced by what the module IMPORTS, not by a review note.

    Read from the parsed module rather than from its text. The first version
    grepped the source and failed on the docstring that EXPLAINS the rule —
    "no other session's runs" — which is the recurring shape of a structural
    guard that reads prose: it matches the comment describing the removal.
    """
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(CS))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported |= {f"{node.module}.{a.name}" for a in node.names}
    joined = " ".join(imported)
    for forbidden in ("webapp", "tenancy", "personal_ai", "auth",
                      "feedback", "executive.store"):
        assert forbidden not in joined, f"{forbidden} in {sorted(imported)}"


# ===========================================================================
# the combobox
# ===========================================================================
def test_the_form_still_works_without_the_script():
    """The enhancement may not become a dependency."""
    page = AC.inject('<html><head></head><body>'
                     '<form action="/analyze" method="post">'
                     '<span class="field grow"><label for="company_name">C'
                     '</label><input id="company_name" name="company_name" '
                     'placeholder="Cloudflare" autofocus required></span>'
                     '</form></body></html>')
    assert 'name="company_name"' in page
    assert "required" in page
    assert 'action="/analyze"' in page


def test_the_combobox_declares_the_aria_the_pattern_needs():
    page = AC.inject('<html><head></head><body><form action="/analyze" '
                     'method="post"><span class="field grow">'
                     '<input id="company_name" name="company_name" '
                     'placeholder="Cloudflare" autofocus required></span>'
                     '</form></body></html>')
    # Some ARIA is in the markup and some is set on the options as they are
    # created; both forms are asserted, because a test that only knew about
    # the markup would pass a listbox whose rows announce nothing.
    for needed in ('role="listbox"', 'role="status"', "aria-expanded",
                   "aria-controls", "aria-activedescendant",
                   "setAttribute('role','option')", "aria-selected",
                   "ArrowDown", "ArrowUp", "Escape"):
        assert needed in page, needed


def test_a_confirmed_pick_rides_in_on_named_fields():
    page = AC.inject('<html><head></head><body><form action="/analyze" '
                     'method="post"><span class="field grow">'
                     '<input id="company_name" name="company_name" '
                     'placeholder="Cloudflare" autofocus required></span>'
                     '</form></body></html>')
    for field in ("suggest_confirmed", "suggest_domain", "suggest_cik",
                  "suggest_ticker"):
        assert f'name="{field}"' in page


# ===========================================================================
# feedback
# ===========================================================================
def test_every_defect_tag_maps_into_the_existing_taxonomy(tmp_path):
    """§50. A tag with no defect class is a sentiment counter."""
    for tag in TAG_KEYS:
        assert tag in TAG_DEFECT or tag in POSITIVE_TAGS, tag


def test_praise_is_never_counted_as_a_defect(tmp_path):
    log = FeedbackLog(tmp_path)
    log.record(run_id="r", company="C", page="connect", rating="yes",
               comment="", score="5", tags=("would_use", "excellent_insight"))
    signal = log.defect_signal()
    assert signal["by_defect_class"] == {}
    assert signal["praise"]["would_use"] == 1


def test_an_unknown_tag_never_costs_the_free_text(tmp_path):
    """A rejected submission loses the part that cannot be re-derived."""
    log = FeedbackLog(tmp_path)
    record = log.record(run_id="r", company="C", page="connect", rating="no",
                        comment="the history was the useful part",
                        tags=("not_a_real_tag", "wrong_fact"))
    assert record.tags == ("wrong_fact",)
    assert "history was the useful part" in record.comment


def test_feedback_is_confirmed_by_reading_it_back(tmp_path):
    log = FeedbackLog(tmp_path)
    record = log.record(run_id="r1", company="C", page="connect",
                        rating="partly", comment="ok", score="3")
    assert log.contains(record.feedback_id)
    assert log.find(run_id="r1")
    assert log.find(run_id="r2") == []


def test_one_sessions_feedback_is_not_visible_from_another_runs_query(tmp_path):
    """§49, §82. Scoped by run, and a run is scoped to its owner."""
    log = FeedbackLog(tmp_path)
    log.record(run_id="mine", company="A", page="connect", rating="yes",
               comment="private note")
    assert not log.find(run_id="theirs")
    assert "private note" not in str(log.find(run_id="theirs"))


def test_a_score_is_never_invented_for_a_record_that_carries_none(tmp_path):
    log = FeedbackLog(tmp_path)
    log.record(run_id="r", company="C", page="connect", rating="yes",
               comment="")
    assert log.summary()["mean_score"] is None
    assert log.summary()["scored"] == 0


def test_an_out_of_range_score_is_refused(tmp_path):
    log = FeedbackLog(tmp_path)
    with pytest.raises(ValueError):
        log.record(run_id="r", company="C", page="connect", rating="yes",
                   comment="", score="9")


# ===========================================================================
# customer-facing absence
# ===========================================================================
def test_an_absence_with_a_next_step_is_not_a_dead_end():
    resolved = ("No published price series was retrieved for this company. "
                "What would settle it: three years of reported results.")
    assert not absence.adjudicate(f"<p>{resolved}</p>")


def test_an_absence_with_nothing_after_it_is_a_dead_end():
    dead = "<p>No estimate was retrieved, so this is not measured here.</p>"
    found = absence.adjudicate(dead)
    assert found and found[0].phrase in ("no estimate", "is not measured")


def test_an_absence_in_a_heading_is_a_dead_end_whatever_follows_it():
    """§43. A slide whose title is a refusal has already failed."""
    page = ("<h2>No competitor was found</h2><p>What would settle it: one "
            "rival's annual filing.</p>")
    assert absence.headline_dead_end(page)


def test_the_sweep_reads_words_not_markup():
    """A stylesheet is not customer copy, and a false flag trains a reader
    to ignore the guard."""
    page = ('<style>.no-data{display:none}</style><p>Revenue grew.</p>')
    assert not absence.adjudicate(page)
