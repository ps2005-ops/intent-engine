"""V2.0 — records, single-client boundary, state machine, non-execution."""
import pytest

from intent_engine.growth_studio.records import (
    LOOP_TRANSITIONS, StudioError, StudioEvent, require_scope,
)
from intent_engine.growth_studio.service import GrowthStudioService

SCOPE = {"audience": "founders", "channel": "linkedin", "objective": "o",
         "evidence_window": "2026-07-07..2026-07-20",
         "approval_state": "PENDING", "measurement_state": "PENDING",
         "funnel_target": "landing_viewed->analysis_started"}


def _svc(tmp_path):
    return GrowthStudioService(tmp_path / "studio.jsonl")


# --- single-client boundary ---------------------------------------------------

def test_product_id_is_locked_to_founder_intelligence():
    with pytest.raises(StudioError, match="single-client boundary"):
        StudioEvent(event_type="studio.item_created", actor_type="system",
                    actor_id="s", product_id="some-customer").validate()


def test_scope_fields_required():
    with pytest.raises(StudioError, match="missing scope fields"):
        require_scope({"channel": "linkedin"}, kind="GrowthHypothesis")


def test_hypothesis_must_target_funnel_transition_or_declare_brand():
    bad = dict(SCOPE, funnel_target="be more famous")
    with pytest.raises(StudioError, match="measurable funnel transition"):
        require_scope(bad, kind="GrowthHypothesis")
    ok = dict(SCOPE, funnel_target="BRAND_RESEARCH")
    require_scope(ok, kind="GrowthHypothesis")   # explicit brand experiment


# --- state machine ------------------------------------------------------------

def test_loop_transitions_enforced(tmp_path):
    svc = _svc(tmp_path)
    item = svc.create_item("GrowthHypothesis", SCOPE)
    with pytest.raises(StudioError, match="invalid transition"):
        svc.transition(item, "DRAFTED")           # cannot skip states
    svc.transition(item, "RESEARCHED")
    svc.transition(item, "HYPOTHESIS_PROPOSED")
    assert svc.store.item_state(item) == "HYPOTHESIS_PROPOSED"


def test_approved_is_terminal_for_the_system(tmp_path):
    svc = _svc(tmp_path)
    item = svc.create_item("GrowthHypothesis", SCOPE)
    for state in ("RESEARCHED", "HYPOTHESIS_PROPOSED", "STRATEGY_PROPOSED",
                  "CONCEPT_PROPOSED", "DRAFTED", "AWAITING_REVIEW",
                  "APPROVED_FOR_FUTURE_EXECUTION"):
        svc.transition(item, state, actor_type="human", actor_id="founder")
    # the Studio (system actor) may NOT record publication
    with pytest.raises(StudioError, match="never publishes"):
        svc.transition(item, "PUBLISHED_EXTERNALLY_RECORDED",
                       actor_type="system")
    # a human may record an external publication
    svc.record_publication(item, actor_type="human", actor_id="founder",
                           channel="linkedin", url_or_ref="manual:post-1",
                           published_at="2026-07-20T00:00:00+00:00")
    assert svc.store.item_state(item) == "PUBLISHED_EXTERNALLY_RECORDED"


def test_no_execution_surface_exists():
    forbidden = ("publish", "send", "post_to", "deploy", "modify_website",
                 "schedule_external", "email_contacts", "start_paid")
    surface = [n for n in dir(GrowthStudioService) if not n.startswith("_")]
    for name in surface:
        for verb in forbidden:
            assert not name.startswith(verb), f"execution surface: {name}"
    import inspect

    import intent_engine.growth_studio.cli as cli
    src = inspect.getsource(cli)
    for verb in ("publish", "send", "deploy"):
        assert f'add_parser("{verb}"' not in src


def test_manifest_only_for_approved_items_and_inert(tmp_path):
    svc = _svc(tmp_path)
    item = svc.create_item("GrowthHypothesis", SCOPE)
    with pytest.raises(StudioError, match="approved"):
        svc.create_manifest(item, channel="linkedin",
                            approved_draft_ref="draft-1")
    for state in ("RESEARCHED", "HYPOTHESIS_PROPOSED", "STRATEGY_PROPOSED",
                  "CONCEPT_PROPOSED", "DRAFTED", "AWAITING_REVIEW",
                  "APPROVED_FOR_FUTURE_EXECUTION"):
        svc.transition(item, state, actor_type="human", actor_id="founder")
    svc.create_manifest(item, channel="linkedin",
                        approved_draft_ref="draft-1")
    manifest = [r for r in svc.store.read_all()
                if r.event_type == "studio.manifest_created"][0]
    assert manifest.payload["inert"] is True


# --- observations -------------------------------------------------------------

def test_unavailable_metric_is_not_zero(tmp_path):
    svc = _svc(tmp_path)
    with pytest.raises(StudioError, match="unavailable is not zero"):
        svc.record_observation(source="s", metric="m", value=0,
                               window={"start": "a", "end": "b"},
                               evidence_refs=[], availability="UNAVAILABLE")
    obs = svc.record_observation(source="s", metric="m", value=None,
                                 window={"start": "a", "end": "b"},
                                 evidence_refs=[],
                                 availability="UNAVAILABLE")
    assert obs


def test_idempotent_rerun_no_duplicates(tmp_path):
    svc = _svc(tmp_path)
    a = svc.create_item("GrowthHypothesis", SCOPE)
    b = svc.create_item("GrowthHypothesis", SCOPE)
    assert a == b
    assert len([r for r in svc.store.read_all()
                if r.event_type == "studio.item_created"]) == 1
