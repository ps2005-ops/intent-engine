"""Publishing one session's learning as per-company sanitized dossiers.

The contract had a producer function and no caller: only a test invoked
`strategic_export`, so the founder side had nothing to read however carefully
the schema was specified. These tests cover the step that closes that gap.
"""
from __future__ import annotations

import json

import pytest

from intent_engine.market import beliefs as B
from intent_engine.market import expectation as EXP
from intent_engine.market import hidden_state as HS
from intent_engine.market import learning_cycle as LC
from intent_engine.market import learning_store as LS
from intent_engine.market import strategic_export as SE
from intent_engine.market import strategic_publish as SEP


@pytest.fixture()
def store(tmp_path) -> LS.LearningStore:
    return LS.LearningStore(tmp_path / "learning.jsonl")


def seed(store, *, subject="Palantir", prior=0.62):
    b = B.create(belief_id="h1", proposition="a testable proposition",
                 subject=subject, prior=prior, at="2026-07-01")
    store.declare_belief(b)
    e = EXP.preregister(
        hypothesis_id="h1", subject=subject,
        expected_event="shares outperform the benchmark",
        expected_direction=EXP.UP, preregistered_at="2026-07-01",
        evaluation_window_ends="2026-08-01",
        falsifier="shares underperform over the window")
    store.record_expectation(e)
    return e


def run_session(store, expectation, *, as_of="2026-08-05"):
    return LC.run(as_of=as_of, store=store, trades_opened=0,
                  observations={expectation.expectation_id: {
                      "observed_value": -0.07, "observed_at": "2026-08-01"}})


# ------------------------------------------------------------ the central path
def test_a_zero_trade_session_publishes_a_real_dossier(store, tmp_path):
    """The proof the bridge exists at all: no trade, and a file with content."""
    e = seed(store)
    result = run_session(store, e)
    assert result.trades_opened == 0 and result.knowledge_gain > 0

    report = SEP.publish(result, root=tmp_path)
    assert report["published"] == ["palantir"]
    assert report["refused"] == []

    path = tmp_path / "reports/market/strategic/palantir.json"
    payload = json.loads(path.read_text())
    assert payload["export_version"] == SE.EXPORT_VERSION
    belief = payload["strategic_beliefs"][0]
    assert belief["confidence"] < 0.62
    assert belief["direction_of_last_change"] == "WEAKENED"
    # The method must be stated: §6 forbids presenting a heuristic update as
    # an empirical Bayesian one.
    assert belief["update_method"]


def test_the_published_dossier_passes_the_sanitiser_again(store, tmp_path):
    e = seed(store)
    SEP.publish(run_session(store, e), root=tmp_path)
    payload = json.loads(
        (tmp_path / "reports/market/strategic/palantir.json").read_text())
    SE.assert_sanitized(payload)          # raises if anything slipped through


# ------------------------------------------------------------------- silence
def test_a_company_with_nothing_to_say_gets_no_file(store, tmp_path):
    """An empty dossier published daily teaches a reader to stop opening it."""
    result = LC.run(as_of="2026-08-05", store=store, trades_opened=0)
    report = SEP.publish(result, root=tmp_path)
    assert report["published"] == []
    assert not (tmp_path / "reports/market/strategic").glob("*.json") \
        or not list((tmp_path / "reports/market/strategic").glob("*.json"))


def test_an_actor_alone_never_invents_a_company(store, tmp_path):
    """`focal_actor` may be a regulator or a buyer group.

    Publishing a strategic dossier keyed on one would invent a company the
    engine never evaluated.
    """
    e = seed(store)
    result = run_session(store, e)

    class _Interaction:
        focal_actor = "EU Commission"
        responding_actor = "Some Trade Body"
        initial_action = "opened a consultation"
        response = ""
        at = "2026-08-01"
        response_lag_days = None
        payoff_change = "UNKNOWN"
        payoff_note = ""
        inferred_objective = ""
        alternative_explanations = ()
        evidence_ids = ()
        status = "OBSERVED"

    result.interactions_seen = (_Interaction(),)
    report = SEP.publish(result, root=tmp_path)
    assert report["published"] == ["palantir"]
    assert not (tmp_path / "reports/market/strategic/eu-commission.json"
                ).exists()


def test_two_companies_get_two_dossiers(store, tmp_path):
    e1 = seed(store, subject="Palantir")
    b2 = B.create(belief_id="h2", proposition="another proposition",
                  subject="Shopify", prior=0.5, at="2026-07-01")
    store.declare_belief(b2)
    report = SEP.publish(run_session(store, e1), root=tmp_path)
    assert report["published"] == ["palantir", "shopify"]


# ---------------------------------------------------------------- fail closed
def test_a_leak_refuses_that_company_and_does_not_take_down_the_cycle(
        store, tmp_path, monkeypatch):
    """A leak is a safety stop, not a crash, and never a silent success.

    It must not be counted as a publish, and must not be indistinguishable
    from having nothing to say.
    """
    e = seed(store)
    result = run_session(store, e)

    def _leaky(**kwargs):
        raise SE.ExportLeak("unknown field 'win_rate' at root")

    monkeypatch.setattr(SE, "build_export", _leaky)
    report = SEP.publish(result, root=tmp_path)
    assert report["published"] == []
    assert len(report["refused"]) == 1
    assert "win_rate" in report["refused"][0]["reason"]
    assert report["companies_with_material"] == 1, (
        "a refusal must stay distinguishable from having nothing to say")


# ------------------------------------------------------------- the filename key
@pytest.mark.parametrize("name,key", [
    ("Palantir", "palantir"),
    ("Palantir Technologies", "palantir-technologies"),
    ("  Shopify  ", "shopify"),
    ("Berkshire Hathaway Inc.", "berkshire-hathaway-inc"),
    ("AT&T", "at-t"),
    ("", ""),
])
def test_company_key_is_pinned_on_both_sides(name, key):
    """The founder side derives this key independently, from the same table.

    A drift fails SILENTLY — no file is found, and "no dossier published" is a
    legitimate state — so both sides are checked against one table rather than
    against each other.
    """
    assert SEP.company_key(name) == key


def test_punctuation_and_case_do_not_split_one_company_in_two(store):
    assert SEP.company_key("Palantir") == SEP.company_key("PALANTIR!")


# ------------------------------------------------ the live objects stay private
def test_the_session_report_never_carries_the_live_objects(store):
    """`as_dict` is the operator-facing report and is written to disk.

    Putting the belief store in it would put the whole ledger into every cycle
    JSON, so the carry fields are deliberately outside it.
    """
    e = seed(store)
    payload = run_session(store, e).as_dict()
    for field in ("beliefs_after", "hidden_states_after", "interactions_seen",
                  "reconciliations_seen", "priorities_seen"):
        assert field not in payload


def test_hidden_states_reach_the_dossier_with_their_alternatives(store,
                                                                 tmp_path):
    e = seed(store)
    result = run_session(store, e)
    belief = HS.uniform(subject="Palantir", at="2026-08-05")
    result.hidden_states_after = (belief,)
    SEP.publish(result, root=tmp_path)
    payload = json.loads(
        (tmp_path / "reports/market/strategic/palantir.json").read_text())
    posture = payload["hidden_states"][0]
    assert posture["certainty_note"], "a posture must never read as certain"
    assert posture["alternatives"], "rival postures must remain live"


# ------------------------------------------------- the identity of the subject
#
# THE BRIDGE CARRIED NOTHING, AND NOTHING REPORTED IT.
#
# `company_key` is pinned identically on both sides (above), and the join
# still never matched on a single real company. Both sides computed the key
# correctly from DIFFERENT STRINGS: this engine keys on its internal universe
# id ("microsoft"), and the founder side knows the company by the name its
# operator typed ("Microsoft Corporation"). Pinning a shared function does not
# pin a shared input, and the miss renders as "no strategic reading has been
# published", which is a sentence the product is supposed to be able to say.
def test_the_dossier_is_filed_under_the_name_the_other_side_can_derive(
        store, tmp_path):
    e = seed(store, subject="palantir")
    result = run_session(store, e)
    report = SEP.publish(
        result, root=tmp_path,
        identities={"palantir": ("Palantir Technologies Inc.",
                                 ("Palantir", "Palantir Technologies"))})

    assert report["published"] == ["palantir-technologies-inc"]
    assert report["unnamed"] == []
    assert (tmp_path / "reports/market/strategic"
            / "palantir-technologies-inc.json").exists()


def test_the_dossier_states_who_it_is_about(store, tmp_path):
    """A key is not an identity unless both sides derive it from one string."""
    e = seed(store, subject="palantir")
    result = run_session(store, e)
    SEP.publish(result, root=tmp_path,
                identities={"palantir": ("Palantir Technologies Inc.",
                                         ("Palantir",))})
    payload = json.loads(
        (tmp_path / "reports/market/strategic"
         / "palantir-technologies-inc.json").read_text())

    assert payload["company_display_name"] == "Palantir Technologies Inc."
    # The internal id is kept among the names, so a consumer holding only the
    # old key can still find the dossier it used to read.
    assert "palantir" in payload["subject_names"]
    assert "Palantir Technologies Inc." in payload["subject_names"]


def test_a_founder_never_reads_the_internal_slug(store, tmp_path):
    """The subject of the sentence must be the company, not its key.

    Measured on the first real dossiers: "microsoft is seeing demand
    strengthen rather than plateau" — a correct claim about a database key.
    """
    b = B.create(belief_id="h9",
                 proposition="microsoft is seeing demand strengthen",
                 subject="microsoft", prior=0.6, at="2026-07-01")
    store.declare_belief(b)
    result = LC.run(as_of="2026-08-05", store=store, trades_opened=0)
    SEP.publish(result, root=tmp_path,
                identities={"microsoft": ("Microsoft Corporation", ())})
    payload = json.loads(
        (tmp_path / "reports/market/strategic"
         / "microsoft-corporation.json").read_text())

    belief = payload["strategic_beliefs"][0]
    assert belief["proposition"] == (
        "Microsoft Corporation is seeing demand strengthen")
    assert belief["subject"] == "Microsoft Corporation"


def test_a_proposition_that_does_not_open_with_the_subject_is_left_alone():
    """The substitution is positional and exact, never search-and-replace."""
    show, sentence = SE._displayer("microsoft", "Microsoft Corporation")
    assert sentence("microsoft is hiring") == "Microsoft Corporation is hiring"
    # Not a template rendering, so it is not ours to rewrite.
    assert sentence("Demand at microsoft is strengthening") == (
        "Demand at microsoft is strengthening")
    assert show("microsoft") == "Microsoft Corporation"
    assert show("microsoft azure") == "microsoft azure"


def test_a_dossier_with_no_identity_is_published_and_reported_as_unfindable(
        store, tmp_path):
    """Back-compatible, and honest about what the omission costs.

    Publishing under the internal id still produces a correct dossier. It
    simply cannot be found by company name, and that is said out loud rather
    than left to surface as another silent absence.
    """
    e = seed(store, subject="palantir")
    result = run_session(store, e)
    report = SEP.publish(result, root=tmp_path)

    assert report["published"] == ["palantir"]
    assert report["unnamed"] == ["palantir"]
    payload = json.loads((tmp_path / "reports/market/strategic"
                          / "palantir.json").read_text())
    assert payload["company_display_name"] == "palantir"
