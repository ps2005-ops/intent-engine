"""T015 bars: calibration views. brier_summary stays authoritative; the
A-M5 gate (>=30 resolved) is exact; no accuracy claim anywhere."""
import pytest

from intent_engine.analytics import (
    CALIBRATION_GATE_RESOLVED, AnalyticsService, TOO_FEW,
)
from intent_engine.core.prediction_ledger import (
    record_prediction, resolve_prediction,
)

AS_OF = "2026-07-20T12:00:00+00:00"


@pytest.fixture()
def ledger(tmp_path):
    return tmp_path / "ledger.db"


def _svc(ledger):
    return AnalyticsService(ledger_path=ledger)


def _seed(ledger, n_resolved, n_unresolved=0, n_unresolvable=0):
    for i in range(n_resolved):
        p = record_prediction(source="premortem", entity_id="e",
                              claim_text=f"claim {i}", probability=0.6,
                              resolve_by="2026-07-01", path=ledger)
        resolve_prediction(p.id, "happened" if i % 2 else "did_not_happen",
                           path=ledger)
    for i in range(n_unresolved):
        record_prediction(source="premortem", entity_id="e",
                          claim_text=f"open {i}", probability=0.5,
                          resolve_by="2027-01-01", path=ledger)
    for i in range(n_unresolvable):
        p = record_prediction(source="premortem", entity_id="e",
                              claim_text=f"unres {i}", probability=0.5,
                              resolve_by="2026-07-01", path=ledger)
        resolve_prediction(p.id, "unresolvable", path=ledger)


def test_gate_constant_matches_am5():
    assert CALIBRATION_GATE_RESOLVED == 30


def test_zero_predictions_is_unavailable(ledger):
    m = _svc(ledger).calibration_metrics(as_of=AS_OF)
    assert m["calibration"].status == "UNAVAILABLE"


def test_29_resolved_is_too_few(ledger):
    _seed(ledger, 29)
    m = _svc(ledger).calibration_metrics(as_of=AS_OF)
    assert m["calibration"].status == TOO_FEW
    assert m["calibration"].value is None                 # no numbers rendered
    assert m["calibration"].numerator == 29
    assert m["predictions_resolved"].value == 29


def test_30_resolved_meets_count_gate_but_claims_nothing(ledger):
    _seed(ledger, 30)
    m = _svc(ledger).calibration_metrics(as_of=AS_OF)
    cal = m["calibration"]
    assert cal.status == "OK"
    assert cal.value["resolved_count"] == 30
    assert "mean_brier" in cal.value and "confidence_bands" in cal.value
    # count gate met != claim permitted: the founder review caveat is stated
    assert any("founder calibration review" in a for a in cal.annotations)
    assert any("probability quality only" in a for a in cal.annotations)


def test_unresolved_and_unresolvable_counted_separately_never_scored(ledger):
    _seed(ledger, 4, n_unresolved=3, n_unresolvable=2)
    m = _svc(ledger).calibration_metrics(as_of=AS_OF)
    assert m["predictions_resolved"].value == 4
    assert m["predictions_unresolved"].value == 3
    assert m["predictions_excluded_unresolvable"].value == 2
    assert m["predictions_total"].value == 9


def test_overdue_unresolved_identified(ledger):
    record_prediction(source="premortem", entity_id="e",
                      claim_text="past due", probability=0.5,
                      resolve_by="2026-07-01", path=ledger)     # overdue
    record_prediction(source="premortem", entity_id="e",
                      claim_text="future", probability=0.5,
                      resolve_by="2027-07-01", path=ledger)     # not yet
    m = _svc(ledger).calibration_metrics(as_of=AS_OF)
    assert m["predictions_overdue_unresolved"].value == 1


def test_confidence_bands_use_ledgered_probabilities(ledger):
    _seed(ledger, 30)
    m = _svc(ledger).calibration_metrics(as_of=AS_OF)
    bands = m["calibration"].value["confidence_bands"]
    assert set(bands) == {"60-70%"}                # all seeded at P=0.6
    assert bands["60-70%"]["count"] == 30


def test_brier_summary_remains_authoritative(ledger):
    from intent_engine.core.prediction_ledger import brier_summary
    _seed(ledger, 30)
    m = _svc(ledger).calibration_metrics(as_of=AS_OF)
    authoritative = brier_summary(path=ledger)
    assert m["calibration"].value["mean_brier"] == round(
        authoritative.mean_brier, 4)
    assert "brier_summary" in m["calibration"].provenance["source"]
