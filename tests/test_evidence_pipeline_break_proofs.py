"""Break each gate deliberately; prove the intended one fails.

A guard nobody has watched fail is a guard nobody knows is connected. Each
test below reintroduces a defect this cycle fixed — using the same real text
that exposed it — and asserts the specific gate that should stop it does.

Nothing here installs a permanent switch. Every break is local to its test,
and the restore is the absence of the break.
"""
import json

import pytest

from intent_engine.market import belief_formation as BF
from intent_engine.market import beliefs as B
from intent_engine.market import event_patterns as EP
from intent_engine.market import evidence_translation as ET
from intent_engine.market import expectation as EXP
from intent_engine.market import learning_cycle as LC
from intent_engine.market import learning_store as LS
from intent_engine.market import micro_evidence as ME
from intent_engine.market import strategic_export as SE
from intent_engine.market import strategic_publish as SP
from intent_engine.market import translation_report as TR
from intent_engine.strategic_intelligence import evidence_text as EText

AS_OF = "2026-08-05"

EARNINGS_BODY = (
    "UNITED STATES. SECURITIES AND EXCHANGE COMMISSION. FORM 8-K. "
    "PURSUANT TO SECTION 13 OR 15(D) OF THE SECURITIES EXCHANGE ACT OF 1934. "
    "REDMOND, Wash. — July 29, 2026 — Microsoft Corp. today announced the "
    "following results for the quarter ended June 30, 2026. "
    "When adjusting for these items, we exceeded expectations across "
    "revenue, operating income, and diluted earnings per share.")


def _ev(fact, etype, subject="caterpillar", role="regulatory_filing"):
    return ME.build(subject_company=subject, actor=subject,
                    evidence_type=etype, observed_at=AS_OF, available_at=AS_OF,
                    source="https://www.sec.gov/ex99.htm", fact=fact,
                    source_role=role, reliability=0.9, relevance=0.6)


# --- 1. production returns to 280-character meta-description excerpts ------
def test_break_the_excerpt_back_to_280_chars_and_the_event_is_lost():
    doc = {"source_id": "s", "final_url": "https://x.test/8k",
           "title": "8-K", "meta_description": "",
           "text_content": EARNINGS_BODY}
    broken = (doc["meta_description"] or doc["text_content"][:280]).strip()
    assert "exceeded expectations" not in broken          # the old behaviour
    assert ET.classify_type(broken) != ME.EARNINGS_SURPRISE

    restored = EText.evidence_excerpt(doc)
    assert "exceeded expectations" in restored
    assert ET.classify_type(restored) is not None


# --- 2. a furniture sentence is classified as an event --------------------
@pytest.mark.parametrize("furniture", [
    "Explore the Microsoft Store for apps and games on Windows.",
    "A featured collection of the latest Palantir blog posts.",
    "At Palantir, we believe that with good data and the right software, "
    "institutions solve their hardest problems.",
    "Palantir partners with world leading organizations.",
])
def test_break_furniture_into_evidence_and_a_gate_stops_it(furniture):
    rows = [{"evidence_text": furniture, "source": "https://x.test/p",
             "kind": "product", "published_at": AS_OF}]
    items, rejected, stats = ET.translate_with_stats(
        rows, subject_company="acme", as_of=AS_OF)
    assert items == [], f"{furniture!r} became evidence"
    assert stats.furniture_rejected or stats.unclassifiable


# --- 3. an event-bearing sentence is lost inside a whole blob -------------
def test_break_back_to_whole_blob_classification():
    """The blob classifies as nothing; the sentences classify correctly."""
    blob = " ".join(EARNINGS_BODY.split())
    sentences = [s for _, s in EText.split_sentences(blob)]
    per_sentence = [EP.classify_sentence(" ".join(s.split()))
                    for s in sentences]
    assert any(t == ME.EARNINGS_SURPRISE for t in per_sentence)
    # the blob as ONE candidate carries cover-page boilerplate and is refused
    assert EText.furniture_reason(blob)


# --- 4. a nominalized contract award is missed ---------------------------
def test_break_recall_on_nominalized_phrasing():
    active = "Caterpillar was awarded a multi-year contract."
    nominal = "Caterpillar announced a multi-year contract award."
    assert EP.classify_sentence(active) == ME.CONTRACT_AWARD
    assert EP.classify_sentence(nominal) == ME.CONTRACT_AWARD


# --- 5. a duplicate sentence creates duplicate evidence ------------------
def test_break_dedupe_and_one_sentence_becomes_two_facts():
    fact = "Second-quarter 2026 sales and revenues increased 24% to $20.5bn."
    rows = [{"evidence_text": f"{fact} {fact}", "source": "https://x.test/a",
             "kind": "filing", "published_at": AS_OF}]
    items, _, stats = ET.translate_with_stats(
        rows, subject_company="caterpillar", as_of=AS_OF)
    assert len(items) == 1
    assert stats.duplicates >= 1


# --- 6. an incomplete sentence becomes a fact ----------------------------
@pytest.mark.parametrize("fragment", [
    "Second Quarter.", "Sales and Revenues.", "$20.5.",
    "Adjusted Profit Per Share.",
])
def test_break_fragments_into_facts(fragment):
    assert EText.furniture_reason(fragment) == "fragment"


# --- 7. the translation drop rate is hidden from reports -----------------
def test_break_observability_and_a_total_drop_becomes_invisible():
    rows = [{"company": "palantir", "evidence": 6,
             "candidate_sentences": 128, "evidence_translated": 0,
             "evidence_unclassifiable": 128}]
    stripped = {k: v for k, v in {"rows": rows, "companies": 1}.items()
                if k != "rows"}
    assert "candidate_sentences" not in json.dumps(stripped)   # the old bug
    payload = TR.summarise(rows)
    assert payload["candidate_sentences"] == 128
    assert "NONE carried a commercial event" in payload["verdict"]


# --- 8. evidence creates a vague, untestable belief ----------------------
def test_break_a_vague_belief_into_existence():
    """A family with no falsifier cannot be preregistered at all."""
    with pytest.raises(EXP.ExpectationRejected):
        EXP.preregister(hypothesis_id="b1", subject="acme",
                        expected_event="the company changes",
                        expected_direction=EXP.UP,
                        preregistered_at=AS_OF,
                        evaluation_window_ends="2026-12-01", falsifier="")


# --- 9. a company-authored item creates unjustified confidence ----------
def test_break_the_self_authored_ceiling():
    own = _ev("Acme launched a new platform for enterprise buyers.",
              ME.PRODUCT_LAUNCH, subject="acme", role="company_owned")
    candidates, refused = BF.propose([own], as_of=AS_OF)
    assert candidates == []
    assert refused["structural_claim_on_self_authored_evidence"] == 1

    # even a fast family opened by the company's own word stays near the fence
    fast = _ev("Acme raised its prices for enterprise customers.",
               ME.PRICING_SIGNAL, subject="acme", role="company_owned")
    candidates, _ = BF.propose([fast], as_of=AS_OF)
    assert candidates
    for candidate in candidates:
        assert candidate.belief.prior_probability <= BF.SELF_AUTHORED_CEILING
        assert any("own account of itself" in lim
                   for lim in candidate.belief.limitations)


# --- 10. an expectation is registered after the outcome is known --------
def test_break_preregistration_with_a_prior_observation():
    exp = EXP.preregister(
        hypothesis_id="b1", subject="acme", expected_event="revenue rises",
        expected_direction=EXP.UP, preregistered_at="2026-08-05",
        evaluation_window_ends="2026-12-01",
        falsifier="revenue is flat or falls")
    scored = EXP.reconcile(exp, as_of="2026-09-01", observed_value=0.4,
                           observed_at="2026-07-01")
    assert scored.outcome == EXP.UNMEASURABLE
    assert "retrodiction" in scored.rationale


# --- 11. duplicate evidence updates a belief twice ----------------------
def test_break_duplicate_evidence_into_a_second_update(tmp_path):
    item = _ev("The Board voted today to raise the quarterly dividend.",
               ME.CAPITAL_RETURN)
    store = LS.LearningStore(tmp_path / "l.jsonl")
    LC.run(as_of=AS_OF, store=store, evidence=[item], cycle="day")
    before = {b.belief_id: b.posterior_probability for b in store.beliefs()}
    LC.run(as_of="2026-08-06", store=store, evidence=[item, item, item],
           cycle="day", decay_beliefs=False)
    after = {b.belief_id: b.posterior_probability for b in store.beliefs()}
    assert before == after


# --- 12. the learning ledger overwrites history -------------------------
def test_break_append_only_by_replaying_a_session(tmp_path):
    item = _ev("The Board voted today to raise the quarterly dividend.",
               ME.CAPITAL_RETURN)
    store = LS.LearningStore(tmp_path / "l.jsonl")
    LC.run(as_of=AS_OF, store=store, evidence=[item], cycle="day")
    first = store.path.read_text()
    LC.run(as_of=AS_OF, store=store, evidence=[item], cycle="day")
    assert store.path.read_text() == first, "history was rewritten or grew"


# --- 13. a no-trade session discards a valid belief update --------------
def test_break_the_no_trade_path(tmp_path):
    store = LS.LearningStore(tmp_path / "l.jsonl")
    result = LC.run(as_of=AS_OF, store=store, cycle="day", trades_opened=0,
                    evidence=[_ev("Second-quarter 2026 sales and revenues "
                                  "increased 24% to $20.5 billion.",
                                  ME.EARNINGS_RESULT)])
    assert result.trades_opened == 0
    assert result.learned_without_trading is True
    assert store.beliefs()


# --- 14. the strategic export carries a trading field -------------------
def test_break_the_export_with_a_trading_internal():
    with pytest.raises(SE.ExportLeak):
        SE.build_export(company_id="acme", as_of=AS_OF,
                        limitations=["our win rate on this signal is 61%"])
    with pytest.raises(SE.ExportLeak):
        payload = SE.build_export(company_id="acme", as_of=AS_OF)
        payload["position_size"] = 100
        SE.assert_sanitized(payload)


def test_break_the_export_with_operator_telemetry():
    """Translation counts are not founder-facing, at any depth."""
    with pytest.raises(SE.ExportLeak):
        payload = SE.build_export(company_id="acme", as_of=AS_OF)
        payload["translation"] = {"candidate_sentences": 400}
        SE.assert_sanitized(payload)


# --- 15. a belief crosses with no evidence lineage ----------------------
def test_break_belief_lineage(tmp_path):
    store = LS.LearningStore(tmp_path / "l.jsonl")
    result = LC.run(
        as_of=AS_OF, store=store, cycle="day",
        evidence=[_ev("The Board voted today to raise the quarterly "
                      "dividend by 12 cents.", ME.CAPITAL_RETURN)])
    SP.publish(result, root=str(tmp_path))
    payload = json.loads(
        (tmp_path / "reports/market/strategic/caterpillar.json").read_text())
    for belief in payload["strategic_beliefs"]:
        assert belief["evidence_ids"]
        assert belief["basis"]


# --- 16. a document about another company is attributed to this one -----
def test_break_subject_binding_with_another_registrants_filing():
    foreign = ("On November 14, 2022, the Company entered into a joint "
               "venture agreement with Infini Resources Pty Ltd. and "
               "Battery Age Minerals Ltd. to develop the property.")
    rows = [{"evidence_text": foreign, "source": "https://sec.gov/f.htm",
             "kind": "filing", "published_at": AS_OF}]
    items, rejected, stats = ET.translate_with_stats(
        rows, subject_company="acme", as_of=AS_OF,
        subject_aliases=("Acme Corporation", "Acme"))
    assert items == []
    assert stats.subject_mismatch == 1

    # ...but a terse exhibit that names NOBODY is kept, with the limitation
    terse = ("Second-quarter 2026 sales and revenues increased 24% to "
             "$20.5 billion.")
    rows = [{"evidence_text": terse, "source": "https://sec.gov/ex99.htm",
             "kind": "filing", "published_at": AS_OF}]
    items, _, stats = ET.translate_with_stats(
        rows, subject_company="acme", as_of=AS_OF,
        subject_aliases=("Acme Corporation", "Acme"))
    assert len(items) == 1
    assert stats.provenance_only == 1
    assert any("retrieval provenance" in lim for lim in items[0].limitations)


# --- 17. the subject's name inside ANOTHER company's name ---------------
#
# The guard in 16 was a plain substring test, and this is the document that
# walked through it. Discovery for the software company "Linear" resolved to
# an SEC registrant called "Linear Minerals Corp.", whose filing contains the
# token "Linear" twenty-six times — as its own short name: "the Linear
# shareholders", "Linear transferred the assets". Every occurrence satisfied
# `"linear" in body.lower()`, so a lithium miner's joint ventures and option
# agreements became beliefs about a project-tracking company, correctly
# classified and properly cited.
LINEAR_MINERALS = (
    "LINEAR MINERALS CORP. (formerly FE Battery Metals Corp.). Condensed "
    "interim financial statements. These condensed interim financial "
    "statements of Linear Minerals Corp. have been prepared by management. "
    "Linear Minerals Corp. (\"Linear Minerals\" or the \"Company\") is a "
    "junior exploration company. Common shares of Westlinear (the Spinco "
    "shares) were distributed to the Linear shareholders on a pro rata "
    "basis. Linear transferred the Pontax West lithium property to "
    "Westlinear, and Linear retained its working capital.")


def test_break_subject_binding_when_another_company_extends_the_name():
    """A longer company name that starts with ours is a collision, not a hit."""
    assert ET.subject_binding(LINEAR_MINERALS, ("Linear", "linear")) == \
        ET.OTHER_NAMED

    rows = [{"evidence_text": LINEAR_MINERALS, "kind": "filing",
             "source": "https://www.sec.gov/Archives/edgar/data/1066130/x.htm",
             "published_at": AS_OF}]
    items, _, stats = ET.translate_with_stats(
        rows, subject_company="linear", as_of=AS_OF,
        subject_aliases=("Linear", "linear"))
    assert items == []
    assert stats.subject_mismatch == 1


def test_the_subject_named_as_a_company_survives_the_collision_rule():
    """The rule must not refuse a company for naming its own subsidiaries.

    "Microsoft Ireland Operations Limited" extends "Microsoft" exactly the way
    "Linear Minerals Corp." extends "Linear". The difference is that this
    document also names Microsoft Corporation itself, and a document that
    names the subject as a company has named it.
    """
    body = ("MICROSOFT CORPORATION. Form 10-K. Microsoft Ireland Operations "
            "Limited and Microsoft Global Finance are consolidated "
            "subsidiaries. Revenue increased 18% to $70.1 billion.")
    assert ET.subject_binding(
        body, ("Microsoft Corporation", "Microsoft", "microsoft")) == ET.NAMED


def test_a_dateline_before_the_company_name_still_names_the_company():
    """`_OTHER_ENTITY` captures leading capitals; the name is the TAIL.

    A masking version of this guard read "Calif. — NVIDIA Corporation" as a
    foreign entity and refused NVIDIA's own filing.
    """
    body = ("SANTA CLARA, Calif. — NVIDIA Corporation today reported record "
            "revenue for the second quarter.")
    assert ET.subject_binding(
        body, ("NVIDIA Corporation", "NVIDIA", "nvidia")) == ET.NAMED


def test_an_alias_inside_a_longer_word_is_not_a_naming():
    """Word boundaries, not substrings: "linearity" does not name Linear."""
    body = ("The study measured linearity and linearisation error across "
            "the sample. No company is named in this passage.")
    assert ET.subject_binding(body, ("Linear", "linear")) == ET.UNNAMED
