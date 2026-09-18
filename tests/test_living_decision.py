"""E-LDR-001 — the three words this record exists to keep apart.

A RECOMMENDATION is what the engine concluded. A DECISION is what a human
chose. An ACTION is what was done. Every product in this category collapses
them and the collapse is invisible, because the screen looks identical. So the
state machine REFUSES the transitions rather than documenting them, and most of
this file is about those refusals and their negative controls.

The second half is about the other collapse: decision quality read off outcome
quality. A system that learns from realized outcomes reliably learns to take
the lucky bet.
"""
from __future__ import annotations

import io
import json

import pytest

from intent_engine.core.tenant import (
    SOURCE_SYNTHETIC_FIXTURE, ScopeAuditLog, ScopeRefused, TenantId, establish,
)
from intent_engine.executive import living_decision as L
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from intent_engine.webapp.tenancy import scope_for_session

ALPHA = {"user_id": "usr_alpha", "email": "founder@alpha.test"}
BETA = {"user_id": "usr_beta", "email": "founder@beta.test"}
QUESTION = "Should we hold the enterprise discount floor?"


@pytest.fixture
def audit(tmp_path):
    return ScopeAuditLog(tmp_path / "audit.jsonl")


def _scope(audit):
    return establish(tenant=TenantId.mint(),
                     establishment_source=SOURCE_SYNTHETIC_FIXTURE, audit=audit)


@pytest.fixture
def scope(audit):
    return _scope(audit)


@pytest.fixture
def opened(scope):
    return L.open_decision(scope=scope, company_id="acme", question=QUESTION,
                           owner="ceo", data_population="SYNTHETIC_ENTERPRISE")


# =============================================================================
# 1. A RECOMMENDATION IS NOT A DECISION IS NOT AN ACTION
# =============================================================================
def test_a_recommendation_cannot_jump_to_executing(opened, scope):
    """The gap in the transition table is the guard."""
    ready = L.revise(opened, scope=scope, status=L.RECOMMENDATION_READY,
                     recommendation="Hold the floor", reason="thesis formed")
    with pytest.raises(L.DecisionRefused) as exc:
        L.revise(ready, scope=scope, status=L.EXECUTING, reason="skip")
    assert exc.value.failure_state == L.TRANSITION_REFUSED


def test_the_legal_path_through_a_human_is_available(opened, scope):
    """The NEGATIVE CONTROL. Without it the test above is satisfied by a
    record that refuses every transition."""
    r = L.revise(opened, scope=scope, status=L.RECOMMENDATION_READY,
                 recommendation="Hold", reason="thesis")
    r = L.revise(r, scope=scope, status=L.HUMAN_DECIDED, decided_by="ceo",
                 reason="ceo chose")
    r = L.revise(r, scope=scope, status=L.ACTION_APPROVED, reason="approved")
    r = L.revise(r, scope=scope, status=L.EXECUTING, reason="rollout began")
    assert r.status == L.EXECUTING
    assert r.revision == 5


def test_a_decided_record_must_name_the_human_who_chose(opened, scope):
    ready = L.revise(opened, scope=scope, status=L.RECOMMENDATION_READY,
                     recommendation="Hold", reason="thesis")
    with pytest.raises(L.DecisionRefused) as exc:
        L.revise(ready, scope=scope, status=L.HUMAN_DECIDED,
                 reason="nobody chose")
    assert exc.value.failure_state == "NO_DECIDER"


def test_is_recommendation_only_reads_the_set_not_one_member(opened, scope):
    assert opened.is_recommendation_only is True
    ready = L.revise(opened, scope=scope, status=L.RECOMMENDATION_READY,
                     recommendation="Hold", reason="thesis")
    assert ready.is_recommendation_only is True
    decided = L.revise(ready, scope=scope, status=L.HUMAN_DECIDED,
                       decided_by="ceo", reason="chose")
    assert decided.is_recommendation_only is False


def test_the_not_yet_decided_membership_is_pinned():
    """WHICH states, not how many: a length assertion survives a swap."""
    assert L.NOT_YET_DECIDED == {L.OPEN, L.EVIDENCE_GATHERING,
                                 L.RECOMMENDATION_READY}
    assert L.HUMAN_DECIDED not in L.NOT_YET_DECIDED
    assert L.EXECUTING not in L.NOT_YET_DECIDED


def test_a_terminal_decision_goes_nowhere(opened, scope):
    dead = L.revise(opened, scope=scope, status=L.ABANDONED, reason="dropped")
    with pytest.raises(L.DecisionRefused):
        L.revise(dead, scope=scope, status=L.OPEN, reason="reopen")


# =============================================================================
# 2. AN IDENTICAL UPDATE IS NOT A REVISION — metamorphic
# =============================================================================
def test_a_revision_that_changes_nothing_is_refused(opened, scope):
    """A nightly re-derivation must not turn history into a heartbeat."""
    with pytest.raises(L.DecisionRefused) as exc:
        L.revise(opened, scope=scope, reason="re-derived, same answer")
    assert exc.value.failure_state == L.NO_CHANGE


def test_a_revision_that_changes_something_is_accepted(opened, scope):
    """NEGATIVE CONTROL for the no-op refusal."""
    r = L.revise(opened, scope=scope, recommendation="Hold", reason="thesis")
    assert r.revision == 2


def test_repeated_identical_updates_do_not_grow_the_store(tmp_path, scope,
                                                          opened):
    store = L.LivingDecisionStore(tmp_path)
    store.append(opened, scope=scope)
    for _ in range(3):
        with pytest.raises(L.DecisionRefused):
            L.revise(opened, scope=scope, reason="same")
    assert len(store.history(opened.decision_id, scope=scope)) == 1


# =============================================================================
# 3. DECISION QUALITY IS NOT OUTCOME QUALITY
# =============================================================================
def test_a_lucky_outcome_does_not_make_the_decision_good():
    retro = L.Retrospective(decision_quality=L.WEAK, outcome_quality=L.GOOD,
                            execution_quality=L.GOOD,
                            measurement_quality=L.GOOD)
    assert retro.decision_quality == L.WEAK
    assert retro.as_dict()["decision_quality"] == L.WEAK


def test_a_good_decision_with_a_bad_outcome_stays_good():
    retro = L.Retrospective(decision_quality=L.GOOD, outcome_quality=L.WEAK,
                            execution_quality=L.WEAK,
                            measurement_quality=L.GOOD)
    assert retro.decision_quality == L.GOOD
    assert retro.learnable() is True


def test_an_unmeasurable_outcome_is_not_learnable():
    assert L.Retrospective(decision_quality=L.GOOD,
                           measurement_quality=L.UNMEASURABLE
                           ).learnable() is False


def test_an_exogenous_shock_makes_the_episode_unlearnable():
    assert L.Retrospective(decision_quality=L.GOOD, outcome_quality=L.WEAK,
                           measurement_quality=L.GOOD,
                           exogenous_shock=True).learnable() is False


def test_an_unassessed_decision_is_not_learnable():
    """UNKNOWN is not GOOD. A policy may not learn from an unreviewed episode."""
    assert L.Retrospective(outcome_quality=L.GOOD,
                           measurement_quality=L.GOOD).learnable() is False


def test_an_unknown_quality_word_is_refused():
    with pytest.raises(L.DecisionRefused):
        L.Retrospective(decision_quality="PRETTY_GOOD")


# =============================================================================
# 4. WHAT WOULD CHANGE THIS DECISION — read, never invented
# =============================================================================
def test_what_would_change_this_is_read_off_the_record(opened, scope):
    r = L.revise(opened, scope=scope, alternatives=("Cut the floor to 12%",),
                 assumptions=("enterprise buyers are price-insensitive",),
                 falsifiers=("two enterprise losses citing price",),
                 kill_switches=("net retention below 1.0",),
                 information_gaps=("segment-level elasticity",),
                 reason="thesis")
    got = r.what_would_change_this()
    assert got["strongest_alternative"] == "Cut the floor to 12%"
    assert got["load_bearing_assumptions"] == [
        "enterprise buyers are price-insensitive"]
    assert got["falsifiers"] and got["reversal_triggers"]
    assert got["still_unknown"] == ["segment-level elasticity"]


def test_an_empty_record_answers_honestly_rather_than_inventing(opened):
    got = opened.what_would_change_this()
    assert got["strongest_alternative"] == ""
    assert got["falsifiers"] == []


# =============================================================================
# 5. THE STORE — scoped, append-only, latest wins
# =============================================================================
def test_a_decision_cannot_be_opened_without_a_scope():
    with pytest.raises(ScopeRefused):
        L.open_decision(scope="tnt_01J", company_id="acme", question=QUESTION)


def test_a_bare_string_is_refused_at_every_store_seam(tmp_path, opened):
    store = L.LivingDecisionStore(tmp_path)
    for call in (lambda: store.all(scope="tnt_01J"),
                 lambda: store.append(opened, scope="tnt_01J"),
                 lambda: L.open_decisions(store, scope="tnt_01J")):
        with pytest.raises(ScopeRefused):
            call()


def test_two_tenants_never_see_each_others_decisions(tmp_path, audit):
    a, b = _scope(audit), _scope(audit)
    store = L.LivingDecisionStore(tmp_path)
    store.append(L.open_decision(scope=a, company_id="acme",
                                 question="Alpha's question"), scope=a)
    store.append(L.open_decision(scope=b, company_id="acme",
                                 question="Beta's question"), scope=b)
    a_rows = store.all(scope=a)
    b_rows = store.all(scope=b)
    assert [r["decision_question"] for r in a_rows] == ["Alpha's question"]
    assert [r["decision_question"] for r in b_rows] == ["Beta's question"]


def test_the_latest_revision_wins_and_history_keeps_every_one(tmp_path, scope,
                                                              opened):
    store = L.LivingDecisionStore(tmp_path)
    store.append(opened, scope=scope)
    ready = L.revise(opened, scope=scope, status=L.RECOMMENDATION_READY,
                     recommendation="Hold", reason="thesis formed")
    store.append(ready, scope=scope)
    rows = store.all(scope=scope)
    assert len(rows) == 1 and rows[0]["status"] == L.RECOMMENDATION_READY
    assert len(store.history(opened.decision_id, scope=scope)) == 2


def test_what_changed_is_computed_from_stored_rows(tmp_path, scope, opened):
    store = L.LivingDecisionStore(tmp_path)
    store.append(opened, scope=scope)
    store.append(L.revise(opened, scope=scope,
                          status=L.RECOMMENDATION_READY,
                          recommendation="Hold", reason="thesis formed"),
                 scope=scope)
    diffs = L.what_changed(store, opened.decision_id, scope=scope)
    assert len(diffs) == 1
    assert diffs[0]["reason"] == "thesis formed"
    assert "status" in diffs[0]["changed"]
    assert diffs[0]["changed"]["status"] == (L.OPEN, L.RECOMMENDATION_READY)
    # THE LOAD-BEARING HALF. Asserting the changed field is present survives a
    # `what_changed` that reports EVERY field as changed — a break proof caught
    # exactly that. What makes this a diff rather than a dump is the absence of
    # the fields that did not move.
    changed = diffs[0]["changed"]
    assert "decision_question" not in changed
    assert "company_id" not in changed
    assert "created_at" not in changed
    assert set(changed) <= {"status", "recommendation", "provenance"}


def test_a_single_revision_reports_no_change_rather_than_a_narrative(
        tmp_path, scope, opened):
    store = L.LivingDecisionStore(tmp_path)
    store.append(opened, scope=scope)
    assert L.what_changed(store, opened.decision_id, scope=scope) == ()


def test_the_consumers_separate_waiting_for_data_from_waiting_for_outcome(
        tmp_path, scope):
    store = L.LivingDecisionStore(tmp_path)
    gap = L.open_decision(scope=scope, company_id="acme", question="Gap?")
    gap = L.revise(gap, scope=scope, information_gaps=("elasticity",),
                   reason="gap found")
    store.append(gap, scope=scope)
    acting = L.open_decision(scope=scope, company_id="acme", question="Acting?")
    for status, kw in ((L.RECOMMENDATION_READY, {"recommendation": "go"}),
                       (L.HUMAN_DECIDED, {"decided_by": "ceo"}),
                       (L.ACTION_APPROVED, {}), (L.EXECUTING, {})):
        acting = L.revise(acting, scope=scope, status=status, reason=status,
                          **kw)
    store.append(acting, scope=scope)
    assert [r["decision_id"] for r in
            L.awaiting_information(store, scope=scope)] == [gap.decision_id]
    assert [r["decision_id"] for r in
            L.awaiting_outcome(store, scope=scope)] == [acting.decision_id]
    assert len(L.open_decisions(store, scope=scope)) == 2


# =============================================================================
# 6. THROUGH THE REAL REQUEST PATH
# =============================================================================
def _cfg(tmp_path):
    return AppConfig(env="test", secret="s" * 40,
                     web_store_path=tmp_path / "web.jsonl",
                     fi_store_path=tmp_path / "fi.jsonl")


def _get(app, path, *, session=None, query=""):
    sid = None
    if session is not None:
        sid = "sid-" + session["user_id"]
        app.auth._sessions[sid] = {**session, "expires": app.auth.now() + 3600,
                                   "csrf": "c" * 8}
    environ = {"REQUEST_METHOD": "GET", "PATH_INFO": path,
               "QUERY_STRING": query, "wsgi.input": io.BytesIO(b""),
               "CONTENT_LENGTH": "0", "HTTP_HOST": "localhost",
               "SERVER_NAME": "localhost", "SERVER_PORT": "80",
               "wsgi.url_scheme": "http"}
    if sid:
        environ["HTTP_COOKIE"] = f"sid={sid}"
    got = {}

    def start(status, headers, exc_info=None):
        got["status"] = status

    body = b"".join(app(environ, start))
    return got.get("status", ""), body.decode("utf-8")


@pytest.fixture
def served(tmp_path):
    app = WebApp(_cfg(tmp_path))
    alpha = scope_for_session(ALPHA, directory=app._tenant_directory,
                              audit=app._scope_audit)
    store = L.LivingDecisionStore(app.config.web_store_path.parent)
    rec = L.open_decision(scope=alpha, company_id="acme", question=QUESTION,
                          owner="ceo")
    rec = L.revise(rec, scope=alpha, status=L.RECOMMENDATION_READY,
                   recommendation="Hold the floor",
                   information_gaps=("segment elasticity",),
                   reason="thesis formed")
    store.append(rec, scope=alpha)
    import types
    return types.SimpleNamespace(app=app, alpha=alpha, record=rec)


def test_the_request_path_lists_open_decisions_under_scope(served):
    status, body = _get(served.app, "/decisions", session=ALPHA,
                        query="format=json")
    assert status.startswith("200")
    got = json.loads(body)
    assert got["scoped"] is True and got["state"] == "OPEN_DECISIONS"
    assert got["open"][0]["decision_question"] == QUESTION
    assert got["awaiting_information"] == [served.record.decision_id]


def test_the_rendered_page_says_a_recommendation_is_not_a_decision(served):
    _, html = _get(served.app, "/decisions", session=ALPHA)
    assert "recommendation only" in html
    assert "no human has chosen" in html


def test_another_tenant_sees_no_decisions_rather_than_alphas(served):
    got = json.loads(_get(served.app, "/decisions", session=BETA,
                          query="format=json")[1])
    assert got["scoped"] is True
    assert got["state"] == "NO_OPEN_DECISIONS"
    assert got["open"] == []
    assert QUESTION not in json.dumps(got)


def test_a_scopeless_reader_is_told_unavailable_not_shown_an_empty_list(served):
    """An empty list reads as 'you have no open decisions'. That is a claim,
    and a reader holding no authority has not established it."""
    got = json.loads(_get(served.app, "/decisions",
                          session={"user_id": "anon_x"},
                          query="format=json")[1])
    assert got["scoped"] is False
    assert got["state"] == "DECISIONS_UNAVAILABLE"
    assert got["reason"] == "SCOPELESS_READ"
    assert got["state"] != "NO_OPEN_DECISIONS"


def test_the_request_writes_a_receipt(served):
    _get(served.app, "/decisions", session=ALPHA, query="format=json")
    ops = [r["operation"] for r in served.app._tenant_receipts.all()]
    assert "decisions.read" in ops
