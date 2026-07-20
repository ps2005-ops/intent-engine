"""T014 bars: lifecycle fold + transition validation. Current state is a
fold over append-only facts; no mutable stage field exists."""
import pytest

from intent_engine.crm import CRMService, CRMTransitionError


@pytest.fixture()
def crm(tmp_path):
    return CRMService(tmp_path / "crm.jsonl")


def _rec(crm, a, *events):
    for ev in events:
        crm.record(a, ev, actor_type="human", actor_id="founder")


def test_full_valid_path_new_to_activated(crm):
    a = crm.create_prospect(email="j@a.com")
    st = crm.get_current_state(a)
    assert (st.relationship, st.opportunity, st.customer) == \
        ("new", "none", "not_customer")
    _rec(crm, a, "crm.contacted", "crm.qualified", "crm.opportunity_opened",
         "crm.proposal_sent", "crm.won", "crm.customer_activated")
    st = crm.get_current_state(a)
    assert (st.relationship, st.opportunity, st.customer) == \
        ("engaged", "won", "active")


def test_customer_risk_cycle_active_at_risk_recovered_churned(crm):
    a = crm.create_prospect(email="j@a.com")
    _rec(crm, a, "crm.qualified", "crm.opportunity_opened", "crm.won",
         "crm.customer_activated", "crm.customer_at_risk",
         "crm.customer_recovered", "crm.customer_at_risk", "crm.churned")
    st = crm.get_current_state(a)
    assert st.customer == "churned" and st.relationship == "closed"
    # history intact: every fact still present, in order
    types = [e.event_type for e in crm.get_history(a)]
    assert types.count("crm.customer_at_risk") == 2


def test_qualified_to_lost_closes_relationship(crm):
    a = crm.create_prospect(email="j@a.com")
    _rec(crm, a, "crm.qualified", "crm.lost")
    st = crm.get_current_state(a)
    assert st.opportunity == "lost" and st.closed_reason == "lost"


@pytest.mark.parametrize("events,bad", [
    ((), "crm.proposal_sent"),                              # proposal before opp
    (("crm.qualified",), "crm.proposal_sent"),              # proposal before opened
    ((), "crm.won"),                                        # won before qualified
    (("crm.qualified",), "crm.won"),                        # won before opened
    ((), "crm.customer_activated"),                         # activated before won
    (("crm.qualified", "crm.opportunity_opened", "crm.won",
      "crm.customer_activated"), "crm.customer_recovered"), # recovered before at_risk
    ((), "crm.customer_at_risk"),                           # at_risk before customer
    (("crm.qualified",), "crm.opportunity_opened", ),
])
def test_illegal_transitions_rejected(crm, events, bad):
    a = crm.create_prospect(email="j@a.com")
    _rec(crm, a, *events)
    if bad == "crm.opportunity_opened":                     # sanity: legal here
        crm.record(a, bad, actor_type="human", actor_id="founder")
        return
    with pytest.raises(CRMTransitionError):
        crm.record(a, bad, actor_type="human", actor_id="founder")


def test_terminal_states_reopen_only_explicitly(crm):
    a = crm.create_prospect(email="j@a.com")
    _rec(crm, a, "crm.qualified", "crm.lost")
    with pytest.raises(CRMTransitionError, match="closed"):
        crm.record(a, "crm.qualified", actor_type="human", actor_id="founder")
    # a system actor cannot reopen — deliberate human action only
    with pytest.raises(CRMTransitionError, match="human wall"):
        crm.record(a, "crm.reopened", actor_type="system", actor_id="bot")
    crm.record(a, "crm.reopened", actor_type="human", actor_id="founder")
    st = crm.get_current_state(a)
    assert st.relationship == "engaged" and st.opportunity == "none"
    crm.record(a, "crm.qualified", actor_type="human", actor_id="founder")


def test_owner_folded_from_events(crm):
    a = crm.create_prospect(email="j@a.com")
    crm.record(a, "crm.owner_assigned", actor_type="human", actor_id="founder",
               payload={"owner": "Pratham"})
    with pytest.raises(CRMTransitionError):
        crm.record(a, "crm.owner_assigned", actor_type="human",
                   actor_id="founder", payload={"owner": "Someone"})
    crm.record(a, "crm.owner_transferred", actor_type="human",
               actor_id="founder", payload={"owner": "Alex"})
    assert crm.get_current_state(a).owner == "Alex"


def test_tampered_history_fails_validated_fold(crm, tmp_path):
    from intent_engine.crm.events import CRMEvent
    a = crm.create_prospect(email="j@a.com")
    # bypass the service: hand-append an illegal fact
    crm.store.append(CRMEvent(crm_entity_id=a, event_type="crm.won",
                              actor_type="system", actor_id="tamper",
                              source="system"))
    with pytest.raises(CRMTransitionError, match="invalid at crm.won"):
        crm.get_current_state(a)


def test_note_allowed_on_closed_relationship(crm):
    a = crm.create_prospect(email="j@a.com")
    _rec(crm, a, "crm.qualified", "crm.disqualified")
    crm.record(a, "crm.note_added", actor_type="human", actor_id="founder",
               payload={"note": "may revisit next year"})
    assert crm.get_current_state(a).relationship == "closed"
