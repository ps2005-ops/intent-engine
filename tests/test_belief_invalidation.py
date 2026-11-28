"""A belief built from a non-event is withdrawn by an appended record.

Positional: only rows BEFORE the invalidation are masked, because belief ids
are keyed on (subject, family) and a later, genuinely evidenced belief about
the same company reuses the id.
"""
import json

from intent_engine.market import learning_store as LS

BID = "bel_jpm_margin"


def _seed(path):
    rows = [
        {"record": "evidence", "evidence_id": "ev_fund",
         "fact": "Weil Company Inc. Reduces Position in JPMorgan Chase & Co. $JPM - marketbeat.com."},
        {"record": "belief", "belief_id": BID, "subject": "jpmorgan",
         "proposition": "jpmorgan is protecting margin by taking cost out"},
        {"record": "expectation", "expectation_id": "exp_1", "hypothesis_id": BID,
         "metric": "margin_protection", "evidence_basis": ["ev_fund"]},
        {"record": "knowledge_effect", "effect_id": "ke_1", "target_id": BID,
         "target_type": "BELIEF", "effect_type": "CREATED"},
        {"record": "knowledge_effect", "effect_id": "ke_other", "target_id": "bel_other",
         "target_type": "BELIEF", "effect_type": "CREATED"},
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _kinds(store):
    return [r["record"] for r in store._rows()]


def test_invalidation_masks_belief_expectation_and_its_effects_only(tmp_path):
    p = tmp_path / "ledger.jsonl"; _seed(p)
    before = p.read_text()
    store = LS.LearningStore(p)
    assert store.invalidate_belief(BID, reason="fund holding notice", rule="r1",
                                   evidence_ids=["ev_fund"], at="2026-11-26")
    assert p.read_text().startswith(before)          # nothing rewritten
    kinds = _kinds(store)
    assert "belief" not in kinds and "belief_invalidated" in kinds
    assert "expectation" not in kinds and "expectation_invalidated" in kinds
    effects = {r["effect_id"]: r["record"] for r in store._rows()
               if r.get("effect_id")}
    assert effects == {"ke_1": "knowledge_effect_invalidated",
                       "ke_other": "knowledge_effect"}
    assert BID not in store.belief_ids()
    assert store.knowledge_effect_ids() == frozenset({"ke_other"}) or \
        "ke_1" not in store.knowledge_effect_ids()


def test_invalidation_is_idempotent(tmp_path):
    p = tmp_path / "ledger.jsonl"; _seed(p)
    store = LS.LearningStore(p)
    assert store.invalidate_belief(BID, reason="x", rule="r1", evidence_ids=[], at="d")
    assert not store.invalidate_belief(BID, reason="x", rule="r1", evidence_ids=[], at="d")
    assert sum(1 for l in p.read_text().splitlines()
               if json.loads(l)["record"] == "belief_invalidation") == 1


def test_a_later_genuine_belief_with_the_same_id_survives(tmp_path):
    p = tmp_path / "ledger.jsonl"; _seed(p)
    store = LS.LearningStore(p)
    store.invalidate_belief(BID, reason="x", rule="r1", evidence_ids=[], at="d")
    with p.open("a") as fh:   # a real layoff later re-opens the same family
        fh.write(json.dumps({"record": "belief", "belief_id": BID,
                             "subject": "jpmorgan", "proposition": "real"}) + "\n")
    live = [r for r in store._rows() if r["record"] == "belief"]
    assert [r["proposition"] for r in live] == ["real"]
    assert BID in store.belief_ids()
    # and it can be invalidated again if that one also proves bad
    assert store.invalidate_belief(BID, reason="y", rule="r1", evidence_ids=[], at="e")


def test_unknown_belief_is_not_invalidated(tmp_path):
    p = tmp_path / "ledger.jsonl"; _seed(p)
    assert not LS.LearningStore(p).invalidate_belief(
        "bel_missing", reason="x", rule="r1", evidence_ids=[], at="d")
