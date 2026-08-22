"""Prediction generation -> eligibility -> resolution -> per/cross-company scoring.

All via injected fakes (a deterministic predict_fn and price function). No LLM,
no network. Proves the durable prediction spine round-trips the core Prediction
model and that private (strategic) predictions never enter the trading path.
"""
import pytest
from intent_engine.predictions.generation import (
    generate_predictions,
    intents_for_predictions,
    prediction_type,
)
from intent_engine.predictions.repository import PredictionRepository
from intent_engine.predictions.resolution import outcomes_for_company, resolve_due
from intent_engine.storage.durable import DurableStore
from intent_engine.universe.companies import (
    CompanyClass,
    CompanyProfile,
    CompanyPredictionUniverse,
    default_universe,
)
from intent_engine.universe.learning import (
    compute_company_state,
    cross_company_candidates,
)
from intent_engine.hosted.candidates import CandidateStore, LearningCandidate

AS_OF = "2026-07-24"


def _predict_up(company, state, as_of):
    return {"direction": "up", "probability": 0.72, "horizon_days": 21,
            "claim_text": f"{company.canonical_name} up over 21d"}


def test_generate_predictions_covers_public_and_private(tmp_path):
    store = DurableStore(f"sqlite:///{tmp_path}/d.db")
    repo = PredictionRepository(store)
    preds = generate_predictions(default_universe(), _predict_up, AS_OF, repo=repo)
    by_company = {p.entity_id: p for p in preds}
    # three public tradables get MARKET predictions (instrument set)...
    assert prediction_type(by_company["shopify"]) == "price_direction"
    assert by_company["shopify"].instrument == "SHOP"
    # ...the private company gets a STRATEGIC prediction (no instrument)
    assert prediction_type(by_company["stripe"]) == "strategic_event"
    assert by_company["stripe"].instrument is None
    # persisted + reloadable across a fresh store instance
    reopened = PredictionRepository(DurableStore(f"sqlite:///{tmp_path}/d.db"))
    assert reopened.get(by_company["cloudflare"].id).instrument == "NET"


def test_eligibility_excludes_private_and_produces_intents(tmp_path):
    preds = generate_predictions(default_universe(), _predict_up, AS_OF)
    intents, results = intents_for_predictions(preds, default_universe(),
                                               regime="calm", as_of=AS_OF)
    instruments = {i.instrument for i in intents}
    # The property is "every tradable, and no private company" -- not a literal
    # set, which pinned this test to the seed universe's size and broke the
    # moment breadth was added for measured coverage reasons.
    universe = default_universe()
    tradable_symbols = {c.tradable_instrument for c in universe.tradable()
                        if c.prediction_eligible}
    # Every intent is a tradable, and nothing is SILENTLY dropped -- but not
    # every tradable becomes an intent. Once the universe grew past the
    # portfolio cap (25 concurrent positions) the eligibility gate began
    # refusing the surplus, which is risk control working rather than a
    # defect. Asserting equality was only ever true while the universe was
    # smaller than the cap.
    assert instruments <= tradable_symbols
    refused = [r for r in results if not getattr(r, "eligible", True)]
    assert len(instruments) + len(refused) >= len(tradable_symbols)
    assert all(getattr(r, "reason", "") for r in refused), \
        "a refusal with no stated reason is a silent drop"
    assert "stripe" not in {i.instrument for i in intents}
    private = [c for c in universe.companies if not c.tradable_instrument]
    assert private, "the private-company case must still be represented"
    # every private/proxy prediction is a non-eligible result, never an intent
    tradable_symbols = {c.tradable_instrument for c in universe.tradable()
                        if c.prediction_eligible}
    assert all(i.instrument in tradable_symbols for i in intents)


def test_resolution_scores_and_links_pnl(tmp_path):
    store = DurableStore(f"sqlite:///{tmp_path}/d.db")
    repo = PredictionRepository(store)
    preds = generate_predictions(default_universe(), _predict_up, AS_OF, repo=repo)

    # price rises 10% for SHOP over the horizon -> an "up" prediction happened
    def price_at(symbol, day):
        base = {"SHOP": 100.0, "NET": 50.0, "DUOL": 200.0}[symbol]
        return base * (1.10 if day > AS_OF else 1.0)

    res = resolve_due(repo, price_at, "2026-09-01", store=store)
    assert res["resolved_count"] == 3          # 3 market preds resolved
    assert res["skipped_strategic"] == 1       # stripe left for strategic rubric
    outs = outcomes_for_company(store, "shopify")
    assert len(outs) == 1 and outs[0]["outcome"] == "happened"
    # brier for a correct 0.72 call = (0.72-1)^2
    assert abs(outs[0]["brier_component"] - (0.72 - 1.0) ** 2) < 1e-9


def test_company_state_and_cross_company_pattern():
    # two peers in the same group, both overconfident -> a cross-company candidate
    def outs(company_id, accuracy):
        # build outcomes: some happened, some not, all stated at 0.9 confidence
        n = 10
        hits = int(accuracy * n)
        rows = []
        for i in range(n):
            happened = i < hits
            rows.append({"company_id": company_id, "outcome":
                         "happened" if happened else "did_not_happen",
                         "probability": 0.9, "horizon_days": 21,
                         "brier_component": (0.9 - 1) ** 2 if happened
                         else (0.9 - 0) ** 2,
                         "trade_pnl": 5.0 if happened else -5.0,
                         "market_return": 0.02 if happened else -0.02})
        return rows

    s1 = compute_company_state("shopify", outs("shopify", 0.5),
                               peer_group="ecommerce_platform")
    s2 = compute_company_state("bigco", outs("bigco", 0.5),
                               peer_group="ecommerce_platform")
    assert s1.avg_confidence == pytest.approx(0.9)
    assert s1.directional_accuracy == 0.5
    assert "overconfident" in s1.notes[0]
    cands = cross_company_candidates([s1, s2])
    assert len(cands) == 1
    assert set(cands[0].supporting_companies) == {"shopify", "bigco"}
    assert cands[0].peer_group == "ecommerce_platform"


def test_one_company_cannot_make_a_cross_company_rule():
    s1 = compute_company_state("solo", [
        {"company_id": "solo", "outcome": "did_not_happen", "probability": 0.9,
         "horizon_days": 21, "brier_component": 0.81} for _ in range(5)],
        peer_group="infra")
    # only one supporting company -> no cross-company candidate
    assert cross_company_candidates([s1]) == []


def test_reproposing_unchanged_candidate_on_a_later_day_is_a_noop(tmp_path):
    """The after-close job re-proposes each company's candidate daily. When the
    evidence is unchanged (no new resolution that day) only `created_at` differs
    — that must dedupe, not raise. The 30-day replay caught this crashing the
    after-close job on any day a company's metrics were flat."""
    store = DurableStore(f"sqlite:///{tmp_path}/d.db")
    cs = CandidateStore(store)

    def cand(day):                      # identical evidence, different created_at
        return LearningCandidate(
            id="cand:shopify:overconfidence", scope="company",
            company_id="shopify", source="company_scoring", statement="s",
            hypothesis="h", evidence={"brier": 0.2, "paper_pnl": -5.0},
            sample_size=10, status="proposed",
            created_at=f"2026-01-{day:02d}T13:00:00+00:00")

    assert cs.propose(cand(2)) is not None
    cs.propose(cand(3))                 # next day, same evidence -> no crash
    cs.propose(cand(4))
    assert len(cs.all_latest()) == 1    # one candidate, not three, not a crash

    # genuinely new evidence still versions (append-only, latest-wins)
    grew = cand(5).model_copy(update={"sample_size": 11})
    cs.propose(grew)
    assert cs.get("cand:shopify:overconfidence").sample_size == 11
