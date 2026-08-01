"""The Research Asset Ledger — append-only, and its velocity accounting.

The property that matters: history is never mutated away. "Believed at 0.9" is
a much weaker statement than "held at 0.6, raised to 0.9 after the ablation",
and only the second lets a reader judge whether a conclusion was ever tested.
"""
import pytest

from intent_engine.market import assets as A


@pytest.fixture
def ledger(tmp_path):
    return A.AssetLedger(tmp_path / "assets.jsonl")


def _declare(ledger, aid="M1", cls=A.MEASUREMENT_TECHNIQUE, conf=0.6):
    return ledger.declare(
        asset_id=aid, title=f"{aid} title", asset_class=cls,
        claim="a claim", confidence=conf, first_observed="2026-07-01",
        evidence=("run-1",), scope="28-company universe",
        limitations="live path only", contradiction_conditions="a stable "
        "counter-example over >=5 observations", impact="ranks bottlenecks",
        sample_size=28, effective_sample_size=5)


# --- declaration ------------------------------------------------------------
def test_a_declared_asset_carries_every_required_field(ledger):
    asset = _declare(ledger)
    row = asset.as_dict()
    for field in ("asset_id", "title", "class", "claim", "status",
                  "confidence", "previous_confidence", "first_observed",
                  "last_validated", "evidence", "sample_size",
                  "effective_sample_size", "scope", "limitations",
                  "contradiction_conditions", "impact", "still_believed",
                  "revision_history"):
        assert field in row, field
    assert row["status"] == A.ACCEPTED
    assert row["still_believed"] is True


def test_declaring_twice_does_not_fork_history(ledger):
    """A rerunning cycle must not duplicate an asset."""
    _declare(ledger)
    _declare(ledger)
    assert len(ledger.all()) == 1
    assert len(ledger.get("M1").revisions) == 1


def test_an_unknown_class_is_rejected(ledger):
    with pytest.raises(A.LedgerError):
        ledger.declare(asset_id="X", title="t", asset_class="vibes",
                       claim="c", confidence=0.5, first_observed="2026-07-01")


# --- revision history -------------------------------------------------------
def test_confidence_history_is_preserved_not_overwritten(ledger):
    _declare(ledger, conf=0.6)
    ledger.revise(asset_id="M1", status=A.ACCEPTED, confidence=0.9,
                  reason="ablation confirmed it")
    asset = ledger.get("M1")
    assert asset.confidence == 0.9
    assert asset.previous_confidence == 0.6
    assert [r.confidence for r in asset.revisions] == [0.6, 0.9]
    assert asset.revisions[0].reason == "first established"


def test_a_revision_must_state_a_reason(ledger):
    _declare(ledger)
    with pytest.raises(A.LedgerError):
        ledger.revise(asset_id="M1", status=A.ACCEPTED, confidence=0.7,
                      reason="")


def test_revising_an_undeclared_asset_is_refused(ledger):
    with pytest.raises(A.LedgerError):
        ledger.revise(asset_id="ghost", status=A.ACCEPTED, confidence=0.5,
                      reason="x")


# --- knowledge decay lifecycle ---------------------------------------------
def test_contradicting_evidence_moves_accepted_to_under_review(ledger):
    _declare(ledger)
    ledger.revise(asset_id="M1", status=A.UNDER_REVIEW, confidence=0.4,
                  reason="three cycles contradict it")
    asset = ledger.get("M1")
    assert asset.status == A.UNDER_REVIEW
    assert asset.still_believed is False
    assert "contradict" in asset.under_review_reason


def test_review_resolves_to_confirmed_or_retired(ledger):
    for aid, end in (("M1", A.CONFIRMED), ("M2", A.RETIRED)):
        _declare(ledger, aid=aid)
        ledger.revise(asset_id=aid, status=A.UNDER_REVIEW, confidence=0.4,
                      reason="contradicted")
        ledger.revise(asset_id=aid, status=end, confidence=0.8 if
                      end == A.CONFIRMED else 0.1, reason="resolved")
        assert ledger.get(aid).status == end
    assert ledger.get("M1").still_believed is True
    assert ledger.get("M2").still_believed is False
    assert ledger.get("M2").retired_reason == "resolved"


def test_a_retired_asset_can_never_be_revived(ledger):
    """The project is explicitly forbidden to revive retired hypotheses, so
    the ledger cannot express it."""
    _declare(ledger)
    ledger.revise(asset_id="M1", status=A.RETIRED, confidence=0.0,
                  reason="falsified")
    with pytest.raises(A.LedgerError) as exc:
        ledger.revise(asset_id="M1", status=A.ACCEPTED, confidence=0.9,
                      reason="changed my mind")
    assert "never revived" in str(exc.value)


def test_confidence_belongs_to_evidence_not_age(ledger):
    """An asset nobody has re-tested is reported as never re-validated rather
    than allowed to pass for settled."""
    _declare(ledger, aid="M1")
    _declare(ledger, aid="M2")
    ledger.revise(asset_id="M2", status=A.ACCEPTED, confidence=0.8,
                  reason="re-validated on new data")
    assert ledger.get("M1").revalidated is False
    assert ledger.get("M2").revalidated is True
    assert ledger.summary()["never_revalidated"] == ["M1"]


def test_history_survives_a_reopen(ledger, tmp_path):
    _declare(ledger)
    ledger.revise(asset_id="M1", status=A.ACCEPTED, confidence=0.9,
                  reason="more evidence")
    reopened = A.AssetLedger(tmp_path / "assets.jsonl")
    assert [r.confidence for r in reopened.get("M1").revisions] == [0.6, 0.9]


def test_a_corrupt_line_is_skipped_never_silently_repaired(ledger, tmp_path):
    _declare(ledger)
    with open(tmp_path / "assets.jsonl", "a") as fh:
        fh.write("{not json\n")
    assert len(ledger.all()) == 1        # readable history still readable


# --- research velocity ------------------------------------------------------
def test_net_knowledge_gain_is_zero_when_nothing_was_learned():
    velocity = A.ResearchVelocity()
    assert velocity.net_knowledge_gain == 0
    assert "NO NEW KNOWLEDGE" in velocity.render()


def test_a_validated_negative_counts_as_much_as_a_positive():
    assert A.ResearchVelocity(new_negative=1).net_knowledge_gain == 1
    assert A.ResearchVelocity(new_positive=1).net_knowledge_gain == 1


def test_weakened_findings_reduce_velocity():
    """A day that undermines a held conclusion leaves the project knowing LESS
    than it thought. Recording that as progress is the accounting trick this
    metric exists to refuse."""
    assert A.ResearchVelocity(weakened=1).net_knowledge_gain == -1
    assert A.ResearchVelocity(new_positive=1,
                              weakened=2).net_knowledge_gain == -1


def test_placing_a_finding_under_review_also_reduces_velocity():
    assert A.ResearchVelocity(placed_under_review=1).net_knowledge_gain == -1


def test_retirement_is_neutral_because_the_knowledge_was_already_booked():
    """Counting it again would pay twice for one discovery; counting it
    negatively would punish the ledger for finishing its own process."""
    assert A.ResearchVelocity(retired=3).net_knowledge_gain == 0


def test_integrity_failures_and_techniques_count_as_knowledge():
    assert A.ResearchVelocity(integrity_failures_found=1,
                              techniques_adopted=2).net_knowledge_gain == 3


def test_velocity_is_derived_from_what_was_actually_appended(ledger):
    """Derived rather than hand-entered, so the number cannot drift from the
    ledger it claims to summarise."""
    _declare(ledger, aid="N1", cls=A.VALIDATED_NEGATIVE)
    _declare(ledger, aid="M1", cls=A.MEASUREMENT_TECHNIQUE)
    weaken = ledger.revise(asset_id="M1", status=A.ACCEPTED, confidence=0.3,
                           reason="new data undercuts it")
    strengthen = ledger.revise(asset_id="N1", status=A.ACCEPTED,
                               confidence=0.95, reason="replicated")
    velocity = A.velocity_from_revisions([weaken, strengthen], ledger)
    assert velocity.weakened == 1
    assert velocity.strengthened == 1
    assert velocity.net_knowledge_gain == 0


def test_the_ledger_summary_counts_by_status_and_class(ledger):
    _declare(ledger, aid="M1")
    _declare(ledger, aid="N1", cls=A.VALIDATED_NEGATIVE)
    ledger.revise(asset_id="N1", status=A.UNDER_REVIEW, confidence=0.3,
                  reason="contradicted")
    summary = ledger.summary()
    assert summary["total"] == 2
    assert summary["by_status"][A.UNDER_REVIEW] == 1
    assert summary["still_believed"] == 1
