"""T017 bars: briefs, drafts, claims, quotes, review, handoff."""
import pytest

from intent_engine.crm import CRMService
from intent_engine.events import CompanyEventBus
from intent_engine.knowledge import KnowledgeService
from intent_engine.marketing import MarketingError, MarketingService, claim_identity

AS_OF = "2026-12-31T00:00:00+00:00"
QUOTE = "The premortem changed how we scoped the hire."


@pytest.fixture()
def rig(tmp_path):
    crm = CRMService(tmp_path / "crm.jsonl")
    know = KnowledgeService(tmp_path / "feedback.jsonl",
                            tmp_path / "knowledge.jsonl")
    bus = CompanyEventBus(tmp_path / "events")
    svc = MarketingService(tmp_path / "marketing.jsonl", crm_service=crm,
                           knowledge_service=know, event_bus=bus)
    return svc, crm, know, bus


def _campaign_with_brief(svc, **brief_kwargs):
    cid = svc.create_campaign("c", objective="explain the premortem",
                              channel="linkedin", owner="P")
    kw = dict(message="We publish the reasoning behind each premortem.",
              call_to_action="Read the method")
    kw.update(brief_kwargs)
    brief_rev = svc.create_brief(cid, **kw)
    return cid, brief_rev


DESCRIPTIVE = ("We publish the reasoning behind each premortem. "
               "Every claim is recorded on an append-only ledger.")


# --- briefs -------------------------------------------------------------------

def test_brief_assembled_deterministically_with_unavailable_marked(rig):
    svc, _, _, _ = rig
    cid, rev = _campaign_with_brief(svc)
    brief = svc.get_brief(cid)
    assert brief["revision"] == 1 and brief["revision_id"] == rev
    assert brief["audience"] == "UNAVAILABLE"
    assert "audience not defined" in brief["unavailable"]
    assert any("human claim approval" in r for r in brief["review_requirements"])


def test_brief_revision_preserves_history(rig):
    svc, _, _, _ = rig
    cid, rev1 = _campaign_with_brief(svc)
    rev2 = svc.revise_brief(cid, call_to_action="See the ledger")
    assert svc.get_brief(cid)["revision"] == 2
    kinds = [r.event_type for r in svc.get_history(cid)]
    assert kinds.count("marketing.brief_created") == 1
    assert kinds.count("marketing.brief_revised") == 1
    assert rev1 != rev2


# --- drafts -------------------------------------------------------------------

def test_draft_must_reference_exact_brief_revision(rig):
    svc, _, _, _ = rig
    cid, rev1 = _campaign_with_brief(svc)
    rev2 = svc.revise_brief(cid, call_to_action="See the ledger")
    with pytest.raises(MarketingError, match="EXACT current brief revision"):
        svc.create_draft(cid, DESCRIPTIVE, brief_revision_id=rev1)
    svc.create_draft(cid, DESCRIPTIVE, brief_revision_id=rev2)


def test_draft_revision_preserves_the_old_revision(rig):
    svc, _, _, _ = rig
    cid, rev = _campaign_with_brief(svc)
    d1 = svc.create_draft(cid, DESCRIPTIVE, brief_revision_id=rev)
    d2 = svc.revise_draft(cid, DESCRIPTIVE + " Method notes follow.",
                          brief_revision_id=rev)
    assert d1 != d2
    assert svc.get_draft(cid, revision_id=d1)["body"] == DESCRIPTIVE
    assert svc.get_draft(cid)["revision_id"] == d2


def test_unsupported_language_blocks_handoff_not_review(rig):
    svc, _, _, _ = rig
    cid, rev = _campaign_with_brief(svc)
    svc.create_draft(cid, "Our engine is the best and always accurate.",
                     brief_revision_id=rev)
    v = svc.get_draft(cid)["validation"]
    assert v["valid_for_review"] is True        # a human may still read it
    assert v["valid_for_handoff"] is False
    assert any("unsupported marketing language" in b
               for b in v["blocking_issues"])


def test_numeric_and_performance_claims_flagged_for_review(rig):
    svc, _, _, _ = rig
    cid, rev = _campaign_with_brief(svc)
    svc.create_draft(cid, "We reviewed 42 decisions this quarter.",
                     brief_revision_id=rev)
    v = svc.get_draft(cid)["validation"]
    classes = {c["claim_class"] for c in v["claim_references"]}
    assert "derived_metric" in classes
    assert any("CLAIM REVIEW REQUIRED" in b for b in v["blocking_issues"])
    kinds = [r.event_type for r in svc.get_history(cid)]
    assert "marketing.claim_flagged" in kinds


# --- claim gate reuse ---------------------------------------------------------

def test_claim_review_goes_through_the_existing_company_event_gate(rig):
    svc, _, _, bus = rig
    cid, rev = _campaign_with_brief(svc)
    text = "We reviewed 42 decisions this quarter."
    svc.create_draft(cid, text, brief_revision_id=rev)
    claim_id = claim_identity(text)
    svc.request_claim_review(cid, claim_id, text)
    types = [e.event_type for e in bus.store.read_all()]
    assert types == ["claim.review_requested"]      # ONE claim gate, not two
    # a system actor cannot approve — the T013 publisher wall holds
    from intent_engine.events import WallViolation
    with pytest.raises(WallViolation):
        bus.publish("claim.approved", subject_type="claim",
                    subject_id=claim_id, producer="approval_wall",
                    actor_type="system", actor_id="bot", source="system")
    bus.publish("claim.approved", subject_type="claim", subject_id=claim_id,
                producer="approval_wall", actor_type="human",
                actor_id="founder", source="cli")
    assert claim_id in svc.approved_claim_ids()
    assert svc.revalidate_draft(cid)["valid_for_handoff"] is True


def test_claim_rejection_blocks_and_revision_invalidates_approval(rig):
    svc, _, _, bus = rig
    cid, rev = _campaign_with_brief(svc)
    text = "We reviewed 42 decisions this quarter."
    svc.create_draft(cid, text, brief_revision_id=rev)
    claim_id = claim_identity(text)
    bus.publish("claim.approved", subject_type="claim", subject_id=claim_id,
                producer="approval_wall", actor_type="human",
                actor_id="founder", source="cli")
    assert svc.revalidate_draft(cid)["valid_for_handoff"] is True
    # a meaning-changing edit produces a different claim identity, so the
    # old approval no longer covers it
    svc.revise_draft(cid, "We reviewed 91 decisions this quarter.",
                     brief_revision_id=rev)
    assert svc.revalidate_draft(cid)["valid_for_handoff"] is False
    # explicit rejection also removes an approval
    bus.publish("claim.rejected", subject_type="claim", subject_id=claim_id,
                producer="approval_wall", actor_type="human",
                actor_id="founder", source="cli")
    assert claim_id not in svc.approved_claim_ids()


# --- quote gate reuse ---------------------------------------------------------

def _quoted_campaign(svc, know, consent=None, use="public"):
    fid = know.record_feedback("feedback.customer_reply", QUOTE,
                               actor_type="human", actor_id="founder")
    if consent:
        know.record_quote_consent(fid, consent, QUOTE, use,
                                  actor_type="human", actor_id="founder")
    cid, rev = _campaign_with_brief(svc)
    body = f'A customer told us: "{QUOTE}"'
    svc.create_draft(cid, body, brief_revision_id=rev,
                     quotes=[{"feedback_id": fid, "quote_text": QUOTE,
                              "intended_use": "public"}])
    return cid, fid


def test_unconsented_quote_blocks_handoff(rig):
    svc, _, know, _ = rig
    cid, _ = _quoted_campaign(svc, know)
    v = svc.get_draft(cid)["validation"]
    assert v["valid_for_handoff"] is False
    assert any("QUOTE CONSENT REQUIRED" in b for b in v["blocking_issues"])


def test_exact_human_consent_passes_and_marketing_cannot_approve(rig):
    svc, _, know, _ = rig
    cid, fid = _quoted_campaign(svc, know, consent="approved")
    v = svc.get_draft(cid)["validation"]
    assert v["quote_references"][0]["allowed"] is True
    assert not any("QUOTE" in b for b in v["blocking_issues"])
    # marketing has no approve-quote surface at all
    assert not [m for m in dir(svc) if "quote" in m and "approve" in m]


def test_internal_only_consent_fails_public_use(rig):
    svc, _, know, _ = rig
    cid, _ = _quoted_campaign(svc, know, consent="approved", use="internal")
    assert svc.get_draft(cid)["validation"]["valid_for_handoff"] is False


def test_consent_alone_is_not_enough_a_testimonial_is_also_a_claim(rig):
    """Two independent gates: consent says we may use the person's words;
    claim review says we may assert them publicly."""
    svc, _, know, bus = rig
    cid, _ = _quoted_campaign(svc, know, consent="approved")
    v = svc.get_draft(cid)["validation"]
    assert v["quote_references"][0]["allowed"] is True      # consent: yes
    assert any("testimonial" in b for b in v["blocking_issues"])  # claim: no


def test_revoked_consent_blocks_future_handoff(rig):
    svc, _, know, bus = rig
    cid, fid = _quoted_campaign(svc, know, consent="approved")
    # clear the separate testimonial claim gate first
    for claim in svc.get_draft(cid)["validation"]["claim_references"]:
        if claim["requires_review"]:
            bus.publish("claim.approved", subject_type="claim",
                        subject_id=claim["claim_id"], producer="approval_wall",
                        actor_type="human", actor_id="founder", source="cli")
    assert svc.revalidate_draft(cid)["valid_for_handoff"] is True
    know.record_quote_consent(fid, "revoked", QUOTE, "public",
                              actor_type="human", actor_id="founder")
    assert svc.revalidate_draft(cid)["valid_for_handoff"] is False


def test_paraphrase_is_not_covered(rig):
    svc, _, know, _ = rig
    fid = know.record_feedback("feedback.customer_reply", QUOTE,
                               actor_type="human", actor_id="founder")
    know.record_quote_consent(fid, "approved", QUOTE, "public",
                              actor_type="human", actor_id="founder")
    cid, rev = _campaign_with_brief(svc)
    svc.create_draft(cid, "A customer said it reshaped their hiring plan.",
                     brief_revision_id=rev,
                     quotes=[{"feedback_id": fid, "quote_text": QUOTE,
                              "intended_use": "public"}])
    v = svc.get_draft(cid)["validation"]
    assert any("verbatim" in b for b in v["blocking_issues"])


# --- review + handoff ---------------------------------------------------------

def _approved_draft(svc):
    cid, rev = _campaign_with_brief(svc)
    d = svc.create_draft(cid, DESCRIPTIVE, brief_revision_id=rev)
    svc.request_draft_review(cid, d)
    svc.approve_draft(cid, d, actor_id="founder")
    return cid, d


def test_system_may_request_review_but_not_approve(rig):
    svc, _, _, _ = rig
    cid, rev = _campaign_with_brief(svc)
    d = svc.create_draft(cid, DESCRIPTIVE, brief_revision_id=rev)
    svc.request_draft_review(cid, d)                    # system: fine
    for actor in ("system", "agent"):
        with pytest.raises(MarketingError, match="human wall"):
            svc.approve_draft(cid, d, actor_id="bot", actor_type=actor)
    svc.approve_draft(cid, d, actor_id="founder")
    assert svc.get_state(cid).draft_status == "approved"


def test_approval_requires_review_request_and_exact_revision(rig):
    svc, _, _, _ = rig
    cid, rev = _campaign_with_brief(svc)
    d = svc.create_draft(cid, DESCRIPTIVE, brief_revision_id=rev)
    with pytest.raises(MarketingError, match="prior review request"):
        svc.approve_draft(cid, d, actor_id="founder")
    svc.request_draft_review(cid, d)
    with pytest.raises(MarketingError, match="EXACT current draft revision"):
        svc.approve_draft(cid, "not-the-revision", actor_id="founder")


def test_new_revision_invalidates_prior_approval_for_handoff(rig):
    svc, _, _, _ = rig
    cid, d = _approved_draft(svc)
    brief = svc.get_brief(cid)
    svc.revise_draft(cid, DESCRIPTIVE + " Updated.",
                     brief_revision_id=brief["revision_id"])
    blockers = svc.handoff_blockers(cid)
    assert any("later draft revision invalidated" in b for b in blockers)
    with pytest.raises(MarketingError, match="handoff blocked"):
        svc.create_handoff(cid, channel="linkedin")


def test_handoff_requires_approved_draft(rig):
    svc, _, _, _ = rig
    cid, rev = _campaign_with_brief(svc)
    svc.create_draft(cid, DESCRIPTIVE, brief_revision_id=rev)
    with pytest.raises(MarketingError, match="handoff blocked"):
        svc.create_handoff(cid, channel="linkedin")


def test_handoff_approval_is_human_and_rechecks_blockers(rig):
    svc, _, know, _ = rig
    cid, d = _approved_draft(svc)
    h = svc.create_handoff(cid, channel="linkedin",
                           external_target="linkedin.com/company/x")
    for actor in ("system", "agent"):
        with pytest.raises(MarketingError, match="human wall"):
            svc.approve_handoff(cid, h, actor_id="bot", actor_type=actor)
    svc.approve_handoff(cid, h, actor_id="founder")
    handoff = svc.get_handoff(h)
    assert handoff["handoff_status"] == "approved"
    assert handoff["human_approver"] == "founder"
    assert handoff["required_disclosures"] == ["no accuracy is claimed"]
    assert svc.get_state(cid).publishing_status == "approved_for_handoff"


def test_blocked_handoff_records_the_reason(rig):
    svc, _, _, _ = rig
    cid, rev = _campaign_with_brief(svc)
    svc.create_draft(cid, "Our results are guaranteed.", brief_revision_id=rev)
    with pytest.raises(MarketingError):
        svc.create_handoff(cid, channel="linkedin")
    kinds = [r.event_type for r in svc.get_history(cid)]
    assert "marketing.handoff_blocked" in kinds
