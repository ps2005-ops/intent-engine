"""Does the memory survive the process that made it, and stay where it belongs?

Two proofs that the in-process tests cannot give, and that the product had
never had:

  PERSISTENCE   a decision recorded in one process is readable in a FRESH
                interpreter -- not from a module-level cache that happens to
                still be warm. The read runs in a subprocess with nothing
                inherited but the filesystem, because "learned is not saved"
                is a defect this codebase has already shipped once: an API
                that looked like a write path, with no write behind it.

  ISOLATION     that decision belongs to one company and one tenant. It must
                not surface under a different company in the same tenant, nor
                under the same company in a different tenant.

The isolation half is deliberately asymmetric: a leak is a security defect and
an over-refusal is a bug, so both directions are asserted. A test that only
proves the leak is absent passes just as well when NOTHING is readable.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

import pytest

from intent_engine.core.tenant import (
    SOURCE_SYNTHETIC_FIXTURE, ScopeAuditLog, TenantId, establish,
)
from intent_engine.executive import living_decision as L
from intent_engine.executive import personal_ai as PA

COMPANY = "cloudflare"
OTHERS = ("stripe", "toyota", "shopify")
ACTOR = "founder@alpha.test"
QUESTION = "Should we hold the enterprise discount floor?"
RECOMMENDATION = "expand into the mid-market"
CHOICE = "HOLD"


def _scope(audit, tenant=None):
    return establish(tenant=tenant or TenantId.mint(),
                     establishment_source=SOURCE_SYNTHETIC_FIXTURE,
                     audit=audit)


def _decide(store, scope, *, company=COMPANY, choice=CHOICE, actor=ACTOR):
    """Session A: open a decision, then have a named person decide it."""
    record = L.open_decision(scope=scope, company_id=company,
                             question=QUESTION, owner=actor)
    record = L.revise(record, scope=scope, status=L.RECOMMENDATION_READY,
                      recommendation=RECOMMENDATION)
    store.append(record, scope=scope)
    decided = L.record_human_decision(record, scope=scope, choice=choice,
                                      actor=actor)
    store.append(decided, scope=scope)
    return decided


# --- the write path refuses what it must -----------------------------------

def test_a_decision_must_name_the_person_who_made_it(tmp_path):
    audit = ScopeAuditLog(tmp_path / "a.jsonl")
    scope = _scope(audit)
    record = L.revise(
        L.open_decision(scope=scope, company_id=COMPANY, question=QUESTION),
        scope=scope, status=L.RECOMMENDATION_READY,
        recommendation=RECOMMENDATION)
    with pytest.raises(L.DecisionRefused) as exc:
        L.record_human_decision(record, scope=scope, choice=CHOICE, actor="")
    assert exc.value.failure_state == "NO_DECIDER"


def test_a_decision_must_say_what_was_chosen(tmp_path):
    audit = ScopeAuditLog(tmp_path / "a.jsonl")
    scope = _scope(audit)
    record = L.revise(
        L.open_decision(scope=scope, company_id=COMPANY, question=QUESTION),
        scope=scope, status=L.RECOMMENDATION_READY,
        recommendation=RECOMMENDATION)
    with pytest.raises(L.DecisionRefused) as exc:
        L.record_human_decision(record, scope=scope, choice="  ", actor=ACTOR)
    assert exc.value.failure_state == "NO_CHOICE"


def test_the_recommendation_survives_the_decision_that_overruled_it(tmp_path):
    """THE CONVERSION THE WRITE PATH REFUSES.

    The engine said expand; the founder chose to hold. Both facts have to
    still be on the record afterwards, or "did we follow the engine?" and
    "what changed your mind?" are unanswerable -- and a single field storing
    both makes the overwrite mandatory rather than accidental.
    """
    audit = ScopeAuditLog(tmp_path / "a.jsonl")
    scope = _scope(audit)
    store = L.LivingDecisionStore(tmp_path)
    decided = _decide(store, scope)

    assert decided.human_choice == CHOICE
    assert decided.recommendation == RECOMMENDATION      # NOT overwritten
    assert decided.decided_by == ACTOR
    assert decided.followed_recommendation is False


def test_an_undecided_record_does_not_claim_the_engine_was_ignored(tmp_path):
    """Negative control for the flag above: `followed_recommendation` must be
    None while nobody has decided. False would read as "they overruled us",
    which is a claim about a person who has not acted."""
    audit = ScopeAuditLog(tmp_path / "a.jsonl")
    scope = _scope(audit)
    record = L.revise(
        L.open_decision(scope=scope, company_id=COMPANY, question=QUESTION),
        scope=scope, status=L.RECOMMENDATION_READY,
        recommendation=RECOMMENDATION)
    assert record.followed_recommendation is None


def test_the_human_choice_survives_the_rehydration_seam():
    """`internal_view` rebuilds a record from a stored row using an explicit
    list of keys that are NOT constructor arguments. Adding `human_choice`
    to that list would compile, pass every other test, and silently reset an
    overruled recommendation to an accepted one -- so the list is asserted.
    """
    from intent_engine.webapp import internal_view

    assert "human_choice" not in internal_view._DERIVED_KEYS
    # and the derived flag must stay out, since it is recomputed
    assert "followed_recommendation" in internal_view._DERIVED_KEYS

    row = dict(decision_id="d1", company_id=COMPANY, decision_question=QUESTION,
               status=L.HUMAN_DECIDED, decided_by=ACTOR, human_choice=CHOICE,
               recommendation=RECOMMENDATION)
    rebuilt = L.LivingDecisionRecord(**internal_view._record_kwargs(row))
    assert rebuilt.human_choice == CHOICE
    assert rebuilt.followed_recommendation is False


# --- §6 persistence: a genuinely fresh process ------------------------------

_READER = textwrap.dedent("""
    import json, sys
    from intent_engine.core.tenant import (
        SOURCE_SYNTHETIC_FIXTURE, ScopeAuditLog, TenantId, establish)
    from intent_engine.executive import living_decision as L
    from intent_engine.executive import personal_ai as PA

    root, tenant, company = sys.argv[1], sys.argv[2], sys.argv[3]
    scope = establish(tenant=TenantId(tenant),
                      establishment_source=SOURCE_SYNTHETIC_FIXTURE,
                      audit=ScopeAuditLog(root + "/reader-audit.jsonl"))
    store = L.LivingDecisionStore(root)
    rows = [r for r in store.all(scope=scope)
            if r.get("company_id") == company]
    record = None
    if rows:
        latest = sorted(rows, key=lambda r: r.get("revision", 0))[-1]
        record = L.LivingDecisionRecord(**{
            k: v for k, v in latest.items()
            if k in L.LivingDecisionRecord.__dataclass_fields__})
    out = {}
    for q in PA.MEMORY_QUESTIONS:
        a = PA.answer(q, record=record)
        out[a.question_class] = {"answer": a.answer,
                                 "supported": a.supported,
                                 "gap": a.information_gap}
    out["_found"] = record is not None
    print(json.dumps(out))
""")


def _read_in_fresh_process(root, tenant_value, company):
    """Ask the five memory questions in an interpreter that has never seen
    the writing process. Nothing crosses but the filesystem."""
    env = dict(os.environ)
    src = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", _READER, str(root), tenant_value, company],
        capture_output=True, text=True, env=env, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_a_decision_survives_the_process_that_recorded_it(tmp_path):
    """§6. Session A decides HOLD. Session B is a new interpreter and asks."""
    audit = ScopeAuditLog(tmp_path / "a.jsonl")
    tenant = TenantId.mint()
    scope = _scope(audit, tenant)
    store = L.LivingDecisionStore(tmp_path)
    _decide(store, scope)

    out = _read_in_fresh_process(tmp_path, tenant.value, COMPANY)

    assert out["_found"] is True, "the record did not survive the process"
    decided = out[PA.WHAT_WE_DECIDED]
    assert decided["supported"] is True
    assert CHOICE in decided["answer"]
    assert ACTOR in decided["answer"]
    # and the overruled recommendation is still legible in a fresh process
    assert RECOMMENDATION in decided["answer"]

    # WHAT DID WE ACTUALLY DO? Nothing was executed, and the answer must not
    # borrow the decision to fill the gap.
    did = out[PA.WHAT_WE_DID]
    assert did["supported"] is False
    assert did["gap"] == PA.NO_ACTION_RECORDED

    # nor may any later stage be reported as established
    for stage in (PA.WHAT_HAPPENED, PA.WHAT_WE_LEARNED):
        assert out[stage]["supported"] is False, stage


# --- §7 isolation ------------------------------------------------------------

def test_one_company_s_decision_does_not_appear_under_another(tmp_path):
    """Same tenant, same reader, different company. The decision is HOLD for
    Cloudflare; Stripe, Toyota and Shopify have decided nothing."""
    audit = ScopeAuditLog(tmp_path / "a.jsonl")
    tenant = TenantId.mint()
    scope = _scope(audit, tenant)
    store = L.LivingDecisionStore(tmp_path)
    _decide(store, scope)

    for other in OTHERS:
        out = _read_in_fresh_process(tmp_path, tenant.value, other)
        assert out["_found"] is False, f"{other} inherited a decision"
        assert out[PA.WHAT_WE_DECIDED]["supported"] is False
        assert CHOICE not in out[PA.WHAT_WE_DECIDED]["answer"]

    # NEGATIVE CONTROL. Without this, the loop above passes just as well when
    # nothing at all is readable -- which is the failure mode that makes an
    # isolation test worthless.
    mine = _read_in_fresh_process(tmp_path, tenant.value, COMPANY)
    assert mine["_found"] is True


def test_another_tenant_cannot_read_this_decision(tmp_path):
    """Same company, same filesystem, different tenant."""
    audit = ScopeAuditLog(tmp_path / "a.jsonl")
    alpha = TenantId.mint()
    beta = TenantId.mint()
    store = L.LivingDecisionStore(tmp_path)
    _decide(store, _scope(audit, alpha))

    theirs = _read_in_fresh_process(tmp_path, beta.value, COMPANY)
    assert theirs["_found"] is False
    assert CHOICE not in theirs[PA.WHAT_WE_DECIDED]["answer"]

    ours = _read_in_fresh_process(tmp_path, alpha.value, COMPANY)
    assert ours["_found"] is True


def test_a_company_alias_does_not_widen_the_read(tmp_path):
    """"cloudflare-inc" is not "cloudflare" here. The store matches company
    ids exactly, and a substring match is how one company was once served
    another's rows."""
    audit = ScopeAuditLog(tmp_path / "a.jsonl")
    tenant = TenantId.mint()
    store = L.LivingDecisionStore(tmp_path)
    _decide(store, _scope(audit, tenant))

    for alias in ("cloudflare-inc", "cloud", "flare", "CLOUDFLARE"):
        out = _read_in_fresh_process(tmp_path, tenant.value, alias)
        assert out["_found"] is False, f"{alias!r} matched {COMPANY!r}"
