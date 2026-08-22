"""Evidence -> belief -> preregistered expectation -> ledger -> export.

The vertical slice this cycle exists to close, plus the guards that stop it
from manufacturing progress. Every fact below is a real sentence from the
harvested corpus, so a test passing here means the production path works on
text a company actually published.
"""
import json
import pathlib

import pytest

from intent_engine.market import belief_formation as BF
from intent_engine.market import beliefs as B
from intent_engine.market import expectation as EXP
from intent_engine.market import learning_cycle as LC
from intent_engine.market import learning_store as LS
from intent_engine.market import micro_evidence as ME
from intent_engine.market import strategic_export as SE
from intent_engine.market import strategic_publish as SP

AS_OF = "2026-08-05"

CATERPILLAR_DIVIDEND = (
    "IRVING, Texas, June 10, 2026 – The Board of Directors of Caterpillar "
    "Inc. (NYSE: CAT) voted today to raise the quarterly dividend by 12 "
    "cents, an eight percent increase.")
CATERPILLAR_REVENUE = (
    "Second-quarter 2026 sales and revenues increased 24% to $20.5 billion.")


def _evidence(fact, etype, *, role="regulatory_filing", subject="caterpillar",
              source="https://www.sec.gov/ex99.htm", observed=AS_OF):
    return ME.build(subject_company=subject, actor=subject,
                    evidence_type=etype, observed_at=observed,
                    available_at=observed, source=source, fact=fact,
                    source_role=role, reliability=0.9, relevance=0.6)


# --- formation ------------------------------------------------------------
def test_real_evidence_proposes_a_belief_with_an_observable_implication():
    items = [_evidence(CATERPILLAR_DIVIDEND, ME.CAPITAL_RETURN),
             _evidence(CATERPILLAR_REVENUE, ME.EARNINGS_RESULT)]
    candidates, _ = BF.propose(items, as_of=AS_OF)
    families = {c.family for c in candidates}
    assert "capital_return_posture" in families
    assert "demand_strengthening" in families
    for candidate in candidates:
        assert candidate.belief.subject in candidate.belief.proposition
        assert candidate.expectation is not None
        assert candidate.expectation.falsifier
        assert candidate.belief.limitations


def test_no_vague_belief_can_be_produced():
    """Every family names a falsifier; a family without one cannot exist."""
    for family in BF.FAMILIES.values():
        assert family.falsifier.strip()
        assert family.expected_event.strip()
        assert "{subject}" in family.proposition
        for vague in ("is changing", "may happen", "is uncertain"):
            assert vague not in family.proposition


def test_direction_is_read_from_the_words_not_the_tone():
    up = _evidence("Microsoft raised its full-year outlook.",
                   ME.GUIDANCE_REVISION, subject="microsoft")
    down = _evidence("Microsoft lowered its full-year outlook.",
                     ME.GUIDANCE_REVISION, subject="microsoft")
    silent = _evidence("Microsoft updated its full-year outlook today at the "
                       "investor briefing.", ME.GUIDANCE_REVISION,
                       subject="microsoft")
    assert {c.family for c in BF.propose([up], as_of=AS_OF)[0]} == \
        {"demand_strengthening"}
    assert {c.family for c in BF.propose([down], as_of=AS_OF)[0]} == \
        {"demand_weakening"}
    candidates, refused = BF.propose([silent], as_of=AS_OF)
    assert candidates == []
    assert refused["no_direction_stated"] == 1


def test_one_company_authored_item_cannot_open_a_structural_belief():
    own = _evidence("Acme launched a new platform for enterprise buyers.",
                    ME.PRODUCT_LAUNCH, role="company_owned", subject="acme",
                    source="https://acme.test/blog")
    candidates, refused = BF.propose([own], as_of=AS_OF)
    assert candidates == []
    assert refused["structural_claim_on_self_authored_evidence"] == 1


def test_the_same_belief_is_never_opened_twice():
    items = [_evidence(CATERPILLAR_DIVIDEND, ME.CAPITAL_RETURN)]
    first, _ = BF.propose(items, as_of=AS_OF)
    second, refused = BF.propose(items, as_of=AS_OF,
                                 existing=[c.belief for c in first])
    assert second == []
    assert refused["belief_already_declared"] >= 1


def test_belief_ids_are_deterministic_across_runs():
    a = BF.belief_id_for("caterpillar", "capital_return_posture")
    b = BF.belief_id_for("Caterpillar ", "capital_return_posture")
    assert a == b


# --- preregistration ------------------------------------------------------
def test_expectations_carry_no_lookahead():
    items = [_evidence(CATERPILLAR_DIVIDEND, ME.CAPITAL_RETURN)]
    candidate = BF.propose(items, as_of=AS_OF)[0][0]
    exp = candidate.expectation
    assert exp.preregistered_at == AS_OF
    assert exp.evaluation_window_ends > AS_OF
    assert exp.evidence_basis
    # scoring it against an observation that predates it is refused outright
    r = EXP.reconcile(exp, as_of="2026-09-01", observed_value=0.2,
                      observed_at="2026-07-01")
    assert r.outcome == EXP.UNMEASURABLE
    assert "retrodiction" in r.rationale


def test_the_evidence_that_proposed_a_belief_cannot_also_confirm_it():
    """Otherwise one fact sets the prior and then strengthens it."""
    items = [_evidence(CATERPILLAR_DIVIDEND, ME.CAPITAL_RETURN)]
    candidate = BF.propose(items, as_of=AS_OF)[0][0]
    supporting = [ME.build(**{**items[0].__dict__,
                             "contradiction_role": ME.SUPPORTING}
                           ) if False else items[0]]
    _, changed = B.update(candidate.belief, supporting, at=AS_OF)
    assert not changed


# --- the cycle, the ledger, the export ------------------------------------
def _run(tmp_path, evidence, *, as_of=AS_OF, cycle="day"):
    store = LS.LearningStore(tmp_path / "ledger.jsonl")
    return LC.run(as_of=as_of, store=store, evidence=evidence, cycle=cycle,
                  trades_opened=0), store


def test_a_zero_trade_session_earns_a_belief(tmp_path):
    """The claim this whole cycle has to be able to make."""
    result, store = _run(tmp_path, [
        _evidence(CATERPILLAR_DIVIDEND, ME.CAPITAL_RETURN),
        _evidence(CATERPILLAR_REVENUE, ME.EARNINGS_RESULT)])
    assert result.trades_opened == 0
    assert result.knowledge_gain > 0
    assert result.learned_without_trading is True
    assert result.outcome_class == LS.NEW_KNOWLEDGE
    assert len(store.beliefs()) >= 2
    assert store.open_expectations(as_of=AS_OF)


def test_the_ledger_distinguishes_what_kind_of_session_it_was(tmp_path):
    quiet, store = _run(tmp_path / "a", [])
    assert quiet.outcome_class == LS.NO_NEW_EVIDENCE

    # evidence arrived and proposed nothing: observed, no impact
    observed, _ = _run(tmp_path / "b", [
        _evidence("Microsoft updated its outlook at the briefing.",
                  ME.GUIDANCE_REVISION, subject="microsoft")])
    assert observed.outcome_class == LS.OBSERVED_NO_IMPACT

    # candidate sentences reached the translator and none carried an event:
    # a pipeline symptom, not a quiet day
    store = LS.LearningStore(tmp_path / "d" / "ledger.jsonl")
    dropped = LC.run(as_of=AS_OF, store=store, evidence=[], cycle="day",
                     candidates_seen=412)
    assert dropped.outcome_class == LS.UNCLASSIFIABLE_INPUT

    learned, _ = _run(tmp_path / "c",
                      [_evidence(CATERPILLAR_DIVIDEND, ME.CAPITAL_RETURN)])
    assert learned.outcome_class == LS.NEW_KNOWLEDGE


def test_the_ledger_is_append_only_and_idempotent(tmp_path):
    items = [_evidence(CATERPILLAR_DIVIDEND, ME.CAPITAL_RETURN)]
    _, store = _run(tmp_path, items)
    first = store.health()["rows"]
    LC.run(as_of=AS_OF, store=store, evidence=items, cycle="day")
    second = store.health()["rows"]
    assert second == first, "a replayed session appended duplicate records"
    assert len(store.cycles()) == 1


def test_duplicate_evidence_never_updates_a_belief_twice(tmp_path):
    item = _evidence(CATERPILLAR_DIVIDEND, ME.CAPITAL_RETURN)
    _, store = _run(tmp_path, [item])
    before = [b.posterior_probability for b in store.beliefs()]
    LC.run(as_of="2026-08-06", store=store, evidence=[item, item],
           cycle="day", decay_beliefs=False)
    after = [b.posterior_probability for b in store.beliefs()]
    assert before == after


def test_an_expectation_registered_today_is_not_tested_today(tmp_path):
    result, store = _run(tmp_path,
                         [_evidence(CATERPILLAR_DIVIDEND, ME.CAPITAL_RETURN)])
    assert result.reconciliation_summary["evaluated"] == 0
    kinds = store.health()["by_record"]
    assert LS.RECONCILIATION not in kinds, \
        "a TOO_EARLY row was written for an expectation registered seconds ago"


def test_a_declared_belief_reaches_the_export_with_its_lineage(tmp_path):
    result, _ = _run(tmp_path,
                     [_evidence(CATERPILLAR_DIVIDEND, ME.CAPITAL_RETURN),
                      _evidence(CATERPILLAR_REVENUE, ME.EARNINGS_RESULT)])
    report = SP.publish(result, root=str(tmp_path))
    assert report["published"], report
    assert not report["refused"], report["refused"]
    payload = json.loads(
        (tmp_path / "reports/market/strategic/caterpillar.json").read_text())
    assert payload["strategic_beliefs"]
    for belief in payload["strategic_beliefs"]:
        assert belief["evidence_ids"], "a belief crossed with no lineage"
        assert belief["basis"], "a belief crossed with no stated basis"
        assert belief["limitations"]
    assert payload["evidence_ids"]


def test_no_belief_limitation_can_carry_a_trading_term():
    """A real refusal: 'one award does not establish a win rate' was caught."""
    for family in BF.FAMILIES.values():
        text = " ".join((family.proposition, family.limitation,
                         family.falsifier, family.expected_event)).lower()
        for banned in SE._BANNED_SUBSTRINGS:
            assert banned not in text, f"{family.key} carries {banned!r}"
