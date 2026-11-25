"""Media Generation (§7) — provider abstraction, ACCOUNT_OWNER_MANUAL fallback,
failure recovery, cost, budget ceiling, brand gate, no fabricated outcomes.
Offline: injected fake providers, no network."""
import pytest

from intent_engine.growth_os.foundation import Confidence, GrowthOSError, IntelStore, Provenance
from intent_engine.growth_os.brand import BrandMemoryService
from intent_engine.growth_os.media import (
    FakeMediaProvider,
    ManualExportProvider,
    MediaGenerationService,
    StoryBeat,
)
from intent_engine.growth_os.media.service import (
    MEDIA_BLOCKED_BRAND,
    MEDIA_BUDGET_SKIPPED,
    MEDIA_FAILED,
    MEDIA_MANUAL,
    MEDIA_READY,
)


def _svc(tmp_path, **kw):
    return MediaGenerationService(IntelStore(tmp_path / "media.jsonl"), **kw)


def _beats():
    return [
        StoryBeat("user_problem", "Founders can't trust black-box forecasts."),
        StoryBeat("evidence", "Calibration report", evidence_ref="rec-123"),
        StoryBeat("measurable_result", "Brier improved", evidence_ref="rec-456"),
        StoryBeat("cta", "See the reasoning."),
    ]


def _pkg(svc):
    return svc.build_package(fmt="data_story", title="Forecast Trust", beats=_beats(),
                             narration_script="Evidence over hype.",
                             captions=["Auditable forecasts."])


def test_result_beat_refuses_fabricated_outcome(tmp_path):
    svc = _svc(tmp_path)
    with pytest.raises(GrowthOSError):
        svc.build_package(fmt="data_story", title="x", beats=[
            StoryBeat("measurable_result", "We 10x'd a customer")])  # no evidence_ref


def test_generate_success_records_ready_and_cost(tmp_path):
    svc = _svc(tmp_path)
    rec = svc.generate(_pkg(svc), FakeMediaProvider(cost_cad=1.25))
    assert rec.event_type == MEDIA_READY
    assert rec.payload["asset_uri"] and rec.payload["cost_cad"] == 1.25
    assert svc.daily_cost() == 1.25


def test_provider_failure_is_recoverable(tmp_path):
    svc = _svc(tmp_path)
    rec = svc.generate(_pkg(svc), FakeMediaProvider(fail=True))
    assert rec.event_type == MEDIA_FAILED
    assert rec.payload["error"] and rec.payload["package"]      # package retained


def test_no_api_falls_back_to_account_owner_manual(tmp_path):
    svc = _svc(tmp_path)
    rec = svc.generate(_pkg(svc), ManualExportProvider())
    assert rec.event_type == MEDIA_MANUAL
    assert rec.payload["package"]["shot_list"] is not None      # export package present


def test_brand_gate_blocks_contradicting_narration(tmp_path):
    brand = BrandMemoryService(IntelStore(tmp_path / "brand.jsonl"))
    brand.propose(kind="messaging", key="honest", statement="No hype.",
                  provenance=Provenance(source="founder", method="manual"),
                  confidence=Confidence(0.9, basis="approved"),
                  contradicts=["guaranteed 10x"])
    brand.approve(kind="messaging", key="honest", actor="human",
                  provenance=Provenance(source="founder", method="manual"),
                  confidence=Confidence(0.9, basis="approved"))
    svc = _svc(tmp_path, brand_service=brand)
    pkg = svc.build_package(fmt="data_story", title="Bad", beats=_beats(),
                            narration_script="Guaranteed 10x returns!", captions=[])
    rec = svc.generate(pkg, FakeMediaProvider())
    assert rec.event_type == MEDIA_BLOCKED_BRAND


def test_budget_ceiling_stops_safely_and_keeps_work(tmp_path):
    svc = _svc(tmp_path, daily_budget_cad=1.0)
    rec = svc.generate(_pkg(svc), FakeMediaProvider(cost_cad=5.0), expected_cost_cad=5.0)
    assert rec.event_type == MEDIA_BUDGET_SKIPPED
    assert rec.payload["package"]                               # nothing lost
