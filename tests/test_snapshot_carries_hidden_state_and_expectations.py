"""Pre-100 Batch 3: two blocks the executive product could never show.

Both were measured against the live ledger before anything was wired:

  * hidden_states were produced for 22 of 26 companies and shipped to the
    strategic export, but `market_demo_snapshot.v1` had no field for them, so
    the founder product could not render a posture the engine had inferred.

  * 76 preregistered expectations sat in the ledger while `build_snapshot` was
    handed `information_priorities` -- a different thing, empty in 26/26
    exports. "No expectations" was a wiring artefact, not a finding.

The None/()/refusal distinction is the load-bearing part and is asserted here
directly: a block nobody ran must never look like a block that ran and found
nothing.
"""
from intent_engine.market import demo_snapshot_export as DSE
from intent_engine.market import strategic_publish as SP


def _hidden(state="PLATFORM_EXPANDING", subject="Cloudflare, Inc."):
    return {"leading_state": state, "subject": subject,
            "leading_probability": 0.54, "as_of": "2026-08-13",
            "evidence_ids": ["ev_a1021df24dfcecc6"]}


def test_hidden_states_reach_the_snapshot_named_by_their_posture():
    """A hidden state carries no id; the posture IS its identity."""
    snap = DSE.build_snapshot(company_id="cloudflare-inc", as_of="2026-08-14",
                              hidden_states=[_hidden()])
    block = snap["hidden_state_refs"]
    assert block["state"] == DSE.REF_AVAILABLE
    assert block["count"] == 1
    assert block["ids"] == ["PLATFORM_EXPANDING"]


def test_hidden_states_not_passed_still_read_as_did_not_run():
    """The regression that matters: the None branch must survive the wiring."""
    snap = DSE.build_snapshot(company_id="cloudflare-inc", as_of="2026-08-14")
    block = snap["hidden_state_refs"]
    assert block["state"] == DSE.REF_UNAVAILABLE
    assert "did not run" in block["note"]


def test_rows_that_cannot_be_named_are_not_reported_as_zero_findings():
    """THE SILENT ZERO THIS RUN HIT.

    Wiring hidden_states with the wrong id field produced AVAILABLE count 0 --
    indistinguishable from "the subsystem ran and found nothing". That is the
    missing-vs-zero confusion arriving through the other door.
    """
    block = DSE._block([{"unexpected": "shape"}], "leading_state")
    assert block["count"] == 0
    assert "wiring defect" in block["note"]
    assert "1 row(s) present" in block["note"]


def test_a_genuine_empty_stays_a_genuine_empty():
    """NEGATIVE CONTROL for the guard above: it must not fire on real zeros."""
    block = DSE._block([], "leading_state")
    assert block["state"] == DSE.REF_AVAILABLE
    assert block["count"] == 0
    assert block["note"] == ""


def test_expectations_are_filtered_to_their_own_subject():
    """An expectation belongs to whoever it is about.

    Publishing the ledger's whole expectation set under one company would
    attribute another company's preregistered test to this one.
    """
    mine = {"expectation_id": "exp_mine", "subject": "cloudflare"}
    theirs = {"expectation_id": "exp_theirs", "subject": "jpmorgan"}
    got = SP._expectations_for([mine, theirs], "cloudflare")
    assert [e["expectation_id"] for e in got] == ["exp_mine"]


def test_expectations_reach_the_snapshot_as_their_own_ids():
    snap = DSE.build_snapshot(
        company_id="cloudflare-inc", as_of="2026-08-14",
        expectations=[{"expectation_id": "exp_1", "subject": "cloudflare"}])
    assert snap["expectation_refs"]["ids"] == ["exp_1"]


def test_the_store_can_hand_back_the_expectations_themselves(tmp_path):
    """`expectation_ids` existed and this did not, which is why the publisher
    reached for information_priorities instead."""
    from intent_engine.market import learning_store as LS
    store = LS.LearningStore(tmp_path / "ledger.jsonl")
    assert hasattr(store, "expectations")
    assert store.expectations() == ()
