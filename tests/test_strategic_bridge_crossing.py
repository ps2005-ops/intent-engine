"""The strategic bridge, measured with a dossier the market engine wrote.

WHY THIS FILE EXISTS SEPARATELY FROM THE CONTRACT TESTS
-------------------------------------------------------
Both ends of `strategic_market_intel.v1` were built, allowlisted, and covered
by tests, and the bridge carried nothing. Every test on each side constructed
its own payload, so the two halves were never measured against each other —
and the halves disagreed about the one thing no schema pins: which string the
key is derived FROM.

`fixtures/published_dossier_microsoft.json` is therefore not written by hand.
It is the output of a real market learning cycle over documents retrieved
through the production ingestion path, copied byte for byte. If the producer
changes what it emits, this file goes stale and these tests are how anyone
finds out.

The three failures it pins, all measured on that real output:

  1. The dossier could not be FOUND. The producer filed `microsoft.json` and
     this side asked for `microsoft-corporation.json`.
  2. Once found, it rendered NOTHING. `_strategic_blocks` had a branch for
     every kind except beliefs, and beliefs are the only kind the engine
     currently produces.
  3. What it did carry named the company "microsoft" — a database key as the
     subject of a sentence shown to a founder.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from intent_engine.external_intel import pack as ep
from intent_engine.external_intel import strategic_contract as sc

FIXTURE = (pathlib.Path(__file__).parent / "fixtures"
           / "published_dossier_microsoft.json")
PAYLOAD = json.loads(FIXTURE.read_text())
TODAY = "2026-08-06"


@pytest.fixture()
def published(tmp_path) -> pathlib.Path:
    """The real dossier, on disk, exactly as the producer wrote it."""
    out = tmp_path / "reports" / "market" / "strategic"
    out.mkdir(parents=True)
    (out / f"{PAYLOAD['company_id']}.json").write_text(json.dumps(PAYLOAD))
    return out


# --- 1. it can be found ---------------------------------------------------
@pytest.mark.parametrize("typed", [
    "Microsoft Corporation",   # the canonical legal name
    "Microsoft",               # what a founder actually types
    "microsoft",               # the market engine's own internal id
    "  MICROSOFT  ",
])
def test_the_dossier_is_found_by_any_name_the_company_is_known_by(
        published, typed):
    intel = sc.resolve(published, names=[typed], today=TODAY)
    assert intel.available, intel.reason
    assert intel.display_name == "Microsoft Corporation"


def test_the_join_that_used_to_fail_silently_now_holds(tmp_path):
    """The exact production pairing: producer key vs founder name.

    This is the miss as it actually occurred — a dossier filed under the
    market engine's internal id while the analysis asks by company name. It
    returned `available=False` with a reason that reads like an ordinary
    absence, on every company, forever.
    """
    out = tmp_path / "s"
    out.mkdir()
    legacy = dict(PAYLOAD, company_id="microsoft")
    (out / "microsoft.json").write_text(json.dumps(legacy))

    assert sc.company_key("Microsoft Corporation") != legacy["company_id"]
    intel = sc.resolve(out, names=["Microsoft Corporation"], today=TODAY)
    assert intel.available
    assert intel.company_id == "microsoft"


def test_a_company_nobody_published_is_still_a_clean_absence(published):
    intel = sc.resolve(published, names=["Stripe, Inc."], today=TODAY)
    assert not intel.available
    assert "No strategic reading has been published" in intel.reason


def test_an_analysis_with_no_company_name_says_so(published):
    intel = sc.resolve(published, names=["", "   "], today=TODAY)
    assert not intel.available
    assert "no company name" in intel.reason


# --- ambiguity is refused, never resolved ---------------------------------
def test_two_dossiers_claiming_one_company_are_both_refused(tmp_path):
    """Choosing one would attach another company's evidence to this analysis.

    The market side already paid for this lesson once, when a mis-resolved
    registrant produced perfectly-classified events about the wrong company.
    """
    out = tmp_path / "s"
    out.mkdir()
    for key in ("microsoft-usa", "microsoft-corp"):
        twin = dict(PAYLOAD, company_id=key,
                    subject_names=["Microsoft Corporation", "Microsoft"])
        (out / f"{key}.json").write_text(json.dumps(twin))

    intel = sc.resolve(out, names=["Microsoft Corporation"], today=TODAY)
    assert not intel.available
    assert "2 strategic dossiers claim" in intel.reason
    assert "microsoft-corp" in intel.reason


def test_a_file_at_the_expected_name_settles_it_without_a_scan(published):
    """A rival claim does not make the canonical file ambiguous.

    The scan finds dossiers we could not name; it is not a second opinion on
    one we could. Pinned because the precedence is load-bearing: without it a
    single stray file would black out a company that publishes correctly.
    """
    stray = dict(PAYLOAD, company_id="microsoft-usa",
                 subject_names=["Microsoft Corporation"])
    (published / "microsoft-usa.json").write_text(json.dumps(stray))

    intel = sc.resolve(published, names=["Microsoft Corporation"],
                       today=TODAY)
    assert intel.available
    assert intel.company_id == "microsoft-corporation"


def test_a_dossier_renamed_on_disk_is_not_rendered(published):
    """Two lookups must not be able to answer differently for one company."""
    moved = dict(PAYLOAD, subject_names=["Contoso Ltd"])
    (published / "contoso-ltd.json").write_text(json.dumps(moved))

    # Found by filename, refused by the identity it declares.
    intel = sc.resolve(published, names=["Contoso Ltd"], today=TODAY)
    assert not intel.available
    assert "not the company in this analysis" in intel.reason


def test_a_renamed_dossier_is_skipped_by_the_scan_and_reported(published):
    moved = dict(PAYLOAD, subject_names=["Contoso Ltd"])
    (published / "contoso-industries.json").write_text(json.dumps(moved))

    intel = sc.resolve(published, names=["Contoso Ltd"], today=TODAY)
    assert not intel.available
    assert "did not match their filename" in intel.reason


# --- 2. once found, it renders --------------------------------------------
def test_a_beliefs_only_dossier_renders_blocks(published):
    """`has_strategic` said True and the renderer produced nothing.

    Every list in this real dossier is empty except `strategic_beliefs`, so a
    renderer blind to beliefs declares the section relevant and then fills it
    with silence.
    """
    intel = sc.resolve(published, names=["Microsoft Corporation"],
                       today=TODAY)
    context = ep.build_context(strategic=intel, as_of=TODAY)
    assert context.has_strategic
    assert ep.STRATEGIC in context.relevant_sections()

    blocks = ep._strategic_blocks(intel)
    assert len(blocks) == len(intel.beliefs) > 0
    assert all(b["facts"] for b in blocks)


def test_every_belief_block_carries_its_evidence_and_its_basis(published):
    intel = sc.resolve(published, names=["Microsoft"], today=TODAY)
    for block in ep._strategic_blocks(intel):
        assert block["evidence_ids"], "a belief with no lineage is an opinion"
        assert any(f.startswith("Basis:") for f in block["facts"])
        assert block["as_of"]


def test_a_declared_belief_is_not_presented_as_a_tested_one(published):
    """A prior and a posterior must not read the same on the page.

    Every belief in a first session is DECLARED: opened by the evidence and
    never yet moved by anything. Printing "62% confidence" beside a belief
    that has survived three contradictions, with no distinction, invites the
    reader to credit an opening position with a track record.
    """
    intel = sc.resolve(published, names=["Microsoft"], today=TODAY)
    assert all(b.get("update_method") == "DECLARED" for b in intel.beliefs)

    for block in ep._strategic_blocks(intel):
        assert any("has not yet been revised" in f for f in block["facts"])
        assert any("opening position" in lim for lim in block["limitations"])


def test_a_revised_belief_states_its_direction_instead(tmp_path):
    revised = dict(PAYLOAD)
    revised["strategic_beliefs"] = [
        dict(revised["strategic_beliefs"][0],
             update_method="BAYESIAN", direction_of_last_change="WEAKENED")]
    out = tmp_path / "s"
    out.mkdir()
    (out / f"{revised['company_id']}.json").write_text(json.dumps(revised))

    intel = sc.resolve(out, names=["Microsoft Corporation"], today=TODAY)
    block = ep._strategic_blocks(intel)[0]
    assert any("Last revised WEAKENED" in f for f in block["facts"])
    assert not any("opening position" in lim for lim in block["limitations"])


# --- 3. the founder reads a company name, not a key -----------------------
def test_no_founder_facing_text_names_the_company_by_its_slug(published):
    intel = sc.resolve(published, names=["Microsoft Corporation"],
                       today=TODAY)
    rendered = " ".join(f for b in ep._strategic_blocks(intel)
                        for f in b["facts"])
    assert "Microsoft Corporation is" in rendered
    assert "microsoft is" not in rendered
    assert intel.subject == "Microsoft Corporation"


# --- the contract still refuses what it always refused --------------------
def test_the_real_dossier_passes_the_founder_side_allowlist():
    sc.validate(PAYLOAD)


def test_an_undeclared_field_in_a_real_dossier_still_fails_closed(tmp_path):
    rogue = dict(PAYLOAD, sharpe_ratio=1.4)
    out = tmp_path / "s"
    out.mkdir()
    (out / f"{rogue['company_id']}.json").write_text(json.dumps(rogue))

    intel = sc.resolve(out, names=["Microsoft Corporation"], today=TODAY)
    assert not intel.available
    assert "refused by the founder-side contract" in intel.reason


def test_a_trading_internal_in_prose_is_still_refused(tmp_path):
    leaked = dict(PAYLOAD)
    leaked["strategic_beliefs"] = [
        dict(leaked["strategic_beliefs"][0],
             basis="opened after the strategy's win rate improved")]
    out = tmp_path / "s"
    out.mkdir()
    (out / f"{leaked['company_id']}.json").write_text(json.dumps(leaked))

    intel = sc.resolve(out, names=["Microsoft Corporation"], today=TODAY)
    assert not intel.available
    assert "win rate" in intel.reason


def test_a_dossier_without_the_identity_fields_is_still_readable(tmp_path):
    """The producer and the consumer deploy separately and out of order.

    A dossier written before `subject_names` existed must still validate and
    still read; it simply cannot be found by a name it never stated.
    """
    old = {k: v for k, v in PAYLOAD.items()
           if k not in ("company_display_name", "subject_names")}
    old["company_id"] = "microsoft"
    out = tmp_path / "s"
    out.mkdir()
    (out / "microsoft.json").write_text(json.dumps(old))

    sc.validate(old)
    assert sc.resolve(out, names=["microsoft"], today=TODAY).available
    assert not sc.resolve(out, names=["Microsoft Corporation"],
                          today=TODAY).available


def test_a_stale_dossier_is_refused_however_well_it_resolves(published):
    intel = sc.resolve(published, names=["Microsoft Corporation"],
                       today="2026-10-01")
    assert not intel.available
    assert "days old" in intel.reason


def test_strategic_context_never_promotes_a_reading(published):
    intel = sc.resolve(published, names=["Microsoft Corporation"],
                       today=TODAY)
    assert intel.available
    assert intel.changes_readiness is False


# --- 4. and it reaches the page, not only the reasoning layer -------------
#
# `reasoning_pack` carried strategic blocks all along, so the model saw them.
# Every founder-visible surface builds from `presenter.blocks()`, and the
# strategic family had no presenter function at all — `relevant_sections()`
# named it relevant and no surface could render a word of it.
from intent_engine.external_intel import presenter as ps  # noqa: E402


def _context(published, name="Microsoft Corporation"):
    return ep.build_context(
        strategic=sc.resolve(published, names=[name], today=TODAY),
        as_of=TODAY)


def test_the_strategic_family_reaches_the_presenter(published):
    blocks = ps.blocks(_context(published))
    assert [b.key for b in blocks] == ["strategic_reading"]


def test_a_surface_with_a_reading_budget_still_gets_it(published):
    assert any(b.context == ep.STRATEGIC
               for b in ps.leading_blocks(_context(published)))


def test_the_strategic_block_answers_all_four_questions(published):
    block = ps.blocks(_context(published))[0]
    assert block.fact and block.so_what and block.decision
    assert block.limitation and block.text_alternative
    assert "monitor this" not in block.decision.lower()


def test_every_number_the_founder_reads_is_one_the_dossier_published(
        published):
    """A belief's confidence is a published figure, and must survive the gate.

    The gate exists to catch invented numbers. If a stated confidence failed
    it, the cheap way to pass would be to stop printing the confidence — which
    would leave a founder reading a proposition with no idea how strongly it
    is held.
    """
    context = _context(published)
    for block in ps.blocks(context):
        text = " ".join([block.fact, block.so_what, block.decision,
                         block.limitation, block.text_alternative])
        assert context.ungrounded_numbers(text) == [], block.key


def test_the_block_attributes_the_reading_rather_than_asserting_it(published):
    """"The engine holds that X" is a different claim from "X"."""
    block = ps.blocks(_context(published))[0]
    assert "the market-learning engine holds that" in block.fact
    assert "not observations" in block.limitation


def test_strategic_comes_after_the_company_and_its_market(published):
    """It qualifies a reading; it never leads one."""
    context = _context(published)
    assert ps.blocks(context)[-1].context == ep.STRATEGIC


def test_an_absent_dossier_produces_no_block_and_no_heading(tmp_path):
    empty = tmp_path / "s"
    empty.mkdir()
    context = _context(empty)
    assert not context.has_strategic
    assert ps.strategic_blocks(context) == []
    assert ep.STRATEGIC not in context.relevant_sections()
