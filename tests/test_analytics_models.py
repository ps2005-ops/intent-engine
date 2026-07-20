"""T015 bars: metric model, versions, windows, honest unavailability."""
import json

import pytest

from intent_engine.analytics import (
    METRIC_VERSIONS, UNAVAILABLE, MetricResult, make_window,
)
from intent_engine.analytics.models import ratio_metric

AS_OF = "2026-07-20T12:00:00+00:00"


def test_metric_result_serializes_deterministically():
    m = MetricResult(metric_name="x", metric_version="x.v1",
                     computed_at=AS_OF, window={"start": None, "end": AS_OF},
                     value=3, provenance={"b": 1, "a": 2})
    assert m.to_json() == m.to_json()
    parsed = json.loads(m.to_json())
    assert parsed["metric_version"] == "x.v1"
    assert parsed["provenance"] == {"a": 2, "b": 1}


def test_version_registry_has_no_anonymous_versions():
    assert set(METRIC_VERSIONS) == {"decision_metrics", "calibration_metrics",
                                    "crm_funnel", "report_metrics",
                                    "consumer_health"}
    assert all(v.endswith(".v1") for v in METRIC_VERSIONS.values())


def test_unavailable_is_distinct_from_zero():
    zero = MetricResult(metric_name="x", metric_version="x.v1",
                        computed_at=AS_OF, window={}, value=0)
    unavailable = MetricResult(metric_name="x", metric_version="x.v1",
                               computed_at=AS_OF, window={},
                               status=UNAVAILABLE, value=None)
    assert zero.status == "OK" and zero.value == 0
    assert unavailable.status == UNAVAILABLE and unavailable.value is None


def test_division_by_zero_never_fabricates_a_percentage():
    w = make_window("all", AS_OF)
    r = ratio_metric("r", "x.v1", AS_OF, w, numerator=5, denominator=0)
    assert r.status == UNAVAILABLE and r.value is None
    assert any("empty denominator" in a for a in r.annotations)
    ok = ratio_metric("r", "x.v1", AS_OF, w, numerator=1, denominator=4)
    assert ok.value == 0.25


def test_window_specs_and_boundaries():
    w7 = make_window("7d", AS_OF)
    assert w7.start == "2026-07-13T12:00:00+00:00" and w7.end == AS_OF
    assert w7.contains("2026-07-13T12:00:00+00:00")     # inclusive start
    assert w7.contains(AS_OF)                            # inclusive end
    assert not w7.contains("2026-07-13T11:59:59+00:00")
    assert not w7.contains("2026-07-20T12:00:01+00:00")
    w_all = make_window("all", AS_OF)
    assert w_all.start is None and w_all.contains("1999-01-01T00:00:00+00:00")
    custom = make_window("2026-01-01T00:00:00+00:00..2026-02-01T00:00:00+00:00",
                         AS_OF)
    assert custom.contains("2026-02-01T00:00:00+00:00")
    with pytest.raises(ValueError, match="unknown window"):
        make_window("yesterday", AS_OF)


def test_window_never_contains_missing_timestamps():
    assert not make_window("all", AS_OF).contains(None)
    assert not make_window("all", AS_OF).contains("")
