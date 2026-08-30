"""D17. One question, one answer: does a supported reading of this company exist?

Live on `fbb62ff`, one Cloudflare run said all three of these at once:

    X-Ray:   "Supported in direction, not in size · Pricing decision"
    Brief:   "No strategic reading of Cloudflare, Inc. cleared the evidence
              bar, so none is asserted here."
    Slide 1: "not enough to read a strategy from."

Two decision objects, each internally honest, each deciding SEPARATELY whether
there was anything to say. Bank of America, which has no market snapshot,
showed both surfaces agreeing — which is what identified the trigger.

This file pins the contract, not the prose. A surface may still be richer or
terser than its neighbour; none of them may reach its own verdict on whether a
reading exists.
"""
import pytest

from intent_engine.executive import contract as ec
from intent_engine.strategic_intelligence.decision import (
    DECISION_READY, FounderDecision, WITHHELD)


def _run(supported):
    return FounderDecision(
        readiness=DECISION_READY if supported else WITHHELD,
        standing="SUPPORTED" if supported else "REFUSED")


def _market(supported):
    return {"readiness": DECISION_READY if supported else WITHHELD,
            "standing": "SUPPORTED" if supported else "REFUSED"}


# --- §14, the eight cases -------------------------------------------------

def test_case_1_run_supports_market_unavailable():
    c = ec.decide(run_decision=_run(True), market_decision=None)
    assert c.merge_state == ec.CURRENT_RUN_SUPPORTED and c.reading_exists


def test_case_2_run_bounded_market_supports():
    """The case that WAS D17."""
    c = ec.decide(run_decision=_run(False), market_decision=_market(True))
    assert c.merge_state == ec.MARKET_SUPPORTED
    assert c.reading_exists, (
        "a run that did not clear its own bar erased a market reading that "
        "did; that is the contradiction D17 named")
    assert c.run_contribution, (
        "the contract must say what THIS run failed to do, or the surfaces "
        "have nothing honest to put in place of the refusal")


def test_case_3_both_support():
    c = ec.decide(run_decision=_run(True), market_decision=_market(True))
    assert c.merge_state == ec.BOTH_SUPPORTED and c.reading_exists


def test_case_4_and_5_stale_or_invalid_market_is_never_inherited():
    stale = ec.decide(run_decision=_run(False), market_decision=_market(True),
                      market_usable=False, market_reason="snapshot is stale")
    assert not stale.reading_exists, (
        "a stale market snapshot was inherited as a supported reading")
    assert stale.market_note, "a snapshot ignored without a reason is silent"

    invalid = ec.decide(run_decision=_run(False),
                        market_decision=_market(True), market_usable=False)
    assert not invalid.reading_exists


def test_case_7_no_market_no_run_support_is_no_reading():
    """The Bank of America control. It must keep agreeing."""
    c = ec.decide(run_decision=_run(False), market_decision=None)
    assert not c.reading_exists
    assert c.merge_state == ec.MARKET_UNAVAILABLE


def test_a_supported_run_survives_an_unusable_market():
    """The market must not be able to DOWNGRADE a run that stands on its own."""
    c = ec.decide(run_decision=_run(True), market_decision=_market(True),
                  market_usable=False, market_reason="stale")
    assert c.reading_exists and c.merge_state == ec.CURRENT_RUN_SUPPORTED


# --- §15, the surfaces may not disagree -----------------------------------

def test_the_brief_does_not_deny_a_reading_the_contract_asserts():
    """The exact sentence pair that was live."""
    from intent_engine.founder_brief import dossier as fd

    decision = FounderDecision(readiness=WITHHELD, company_name="Cloudflare",
                               unsafe_because="no outside account tested it")
    contract = ec.decide(company="Cloudflare", run_decision=decision,
                         market_decision=_market(True))

    lead = fd.render_decision_lead(decision, "Cloudflare", contract=contract)
    assert "No strategic reading of Cloudflare cleared" not in lead, (
        "the brief denies a reading the X-Ray asserts")
    assert "exists" in lead.lower()
    # and it must still say what this run failed to do, not paper over it
    assert "did not add enough independent evidence" in lead


def test_the_brief_still_refuses_when_the_contract_refuses():
    """The fix must not turn every refusal into a claim."""
    from intent_engine.founder_brief import dossier as fd

    decision = FounderDecision(readiness=WITHHELD, company_name="Nowhere")
    contract = ec.decide(company="Nowhere", run_decision=decision,
                         market_decision=None)
    lead = fd.render_decision_lead(decision, "Nowhere", contract=contract)
    assert "No strategic reading of Nowhere cleared" in lead, (
        "a company with nothing behind it stopped saying so")


def test_without_a_contract_the_old_wording_stands():
    """None must mean "ask the old way", never a blank page."""
    from intent_engine.founder_brief import dossier as fd

    decision = FounderDecision(readiness=WITHHELD, company_name="Nowhere")
    lead = fd.render_decision_lead(decision, "Nowhere", contract=None)
    assert "No strategic reading of Nowhere cleared" in lead


@pytest.mark.parametrize("supported", [True, False])
def test_the_narrative_and_the_brief_reach_the_same_verdict(supported):
    """§15. Render two surfaces from ONE fixture and require agreement."""
    from intent_engine.founder_brief import build as fb
    from intent_engine.founder_brief import dossier as fd
    from intent_engine.founder_brief import narrative as fn

    decision = FounderDecision(readiness=WITHHELD, company_name="Acme")
    contract = ec.decide(company="Acme", run_decision=decision,
                         market_decision=_market(True) if supported else None)
    brief = fb.build(company="Acme", mode=fb.classify_mode(
        is_public=False, evidence_count=0, independent_sources=0,
        has_thesis=False), report={}, observations=[])
    lead = fd.render_decision_lead(decision, "Acme", contract=contract)
    story = fn.build_narrative(company="Acme", brief=brief, report={},
                               decision=decision, contract=contract)
    text = " ".join(p for s in story.sections for p in s.paragraphs)

    denies_lead = "No strategic reading of Acme cleared" in lead
    denies_story = "No strategic reading of Acme cleared" in text
    assert denies_lead == denies_story, (
        f"the brief and the primary screen disagree about whether a reading "
        f"exists (brief denies={denies_lead}, screen denies={denies_story})")
    assert denies_lead is not supported


def test_the_deck_does_not_deny_a_reading_the_contract_asserts():
    """The deck was the last surface still deciding this for itself.

    Live on 929a4b9, after the brief and primary screen were wired, slide 1
    still headed itself "The central strategic view" over "not enough to read
    a strategy from" for a run whose X-Ray gave a supported pricing decision.
    """
    from intent_engine.strategic_intelligence.slides import build_slides

    # The thesis carries the refusal AS its view -- which is exactly why a
    # guard that asked "is the view empty?" never fired live.
    report = {"company_name": "Cloudflare, Inc.",
              "thesis": {"view": "What Cloudflare, Inc. has published is not "
                                 "enough to read a strategy from, so none is "
                                 "put forward here.",
                         "view_withheld": True}}
    contract = ec.decide(company="Cloudflare, Inc.",
                         run_decision=_run(False),
                         market_decision=_market(True))
    text = " ".join(
        str(b) for s in build_slides(report, contract=contract)
        for b in (getattr(s, "bullets", None) or s.get("bullets", []) if
                  isinstance(s, dict) else getattr(s, "bullets", [])))
    assert "not enough to read a strategy from" not in text, (
        "the deck denies a reading the contract asserts")
    assert "Executive X-Ray" in text


def test_the_deck_still_refuses_when_the_contract_refuses():
    from intent_engine.strategic_intelligence.slides import build_slides

    report = {"company_name": "Nowhere", "thesis": {}}
    contract = ec.decide(company="Nowhere", run_decision=_run(False),
                         market_decision=None)
    text = " ".join(
        str(b) for s in build_slides(report, contract=contract)
        for b in (getattr(s, "bullets", None) or s.get("bullets", []) if
                  isinstance(s, dict) else getattr(s, "bullets", [])))
    assert "Executive X-Ray" not in text, (
        "a company with nothing behind it was pointed at a reading that does "
        "not exist")


# --- D22: the ROUTING sink, not just the renderers -------------------------

def test_the_insufficient_evidence_page_defers_to_the_contract(tmp_path):
    """D22. Every refusing ROUTE funnels into this one page.

    Caterpillar live: /slides redirects here when the deck is not ready, and
    this page said "There is not enough public evidence to build a briefing on
    this company" while the X-Ray for the same run gave a supported capacity
    decision. D17 was fixed at the surfaces that RENDER a verdict; this one
    decides before any renderer is reached.

    Fixed at the sink rather than at /slides on purpose: three routes reach it,
    and patching the caught one would have produced a fifth instance. This
    test therefore RENDERS THE PAGE -- an earlier version asserted on the
    contract object instead and stayed green when the page was mutated to
    ignore it.
    """
    import io

    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig
    from tests.test_strategic_intelligence import _live_transport

    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    autorun_sources=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(cfg, transport=_live_transport, resolver=False)

    env = {"REQUEST_METHOD": "POST", "PATH_INFO": "/demo", "CONTENT_LENGTH": "0",
           "HTTP_HOST": "127.0.0.1", "HTTP_COOKIE": "",
           "wsgi.input": io.BytesIO(b"")}
    out = {}
    b"".join(app(env, lambda st, h: out.update(status=st, headers=h)))
    sid = [v.split("=", 1)[1].split(";")[0]
           for k, v in out["headers"] if k == "Set-Cookie"][0]
    session = app.auth.session(sid)

    result = {"status": "PARTIAL", "sections": [],
              "company": "Caterpillar Inc."}

    supported = ec.decide(company="Caterpillar Inc.", run_decision=_run(False),
                          market_decision=_market(True))
    app._executive_contract = lambda run_id: supported
    _s, _h, body = app._insufficient_evidence_page(
        session, "r1", result,
        reason="The pages that could be read describe what the company "
               "offers, but none carried the dated, checkable material.")
    assert "A supported reading of Caterpillar Inc. exists" in body, (
        "the refusing route still asserts there is nothing to say about a "
        "company the contract has a supported reading for")
    assert "did not add enough independent evidence" in body

    # CONTROL: when the contract refuses, this page must keep refusing.
    refused = ec.decide(company="Nowhere", run_decision=_run(False),
                        market_decision=None)
    app._executive_contract = lambda run_id: refused
    _s, _h, body2 = app._insufficient_evidence_page(
        session, "r1", result, reason="nothing checkable was retrieved.")
    assert "A supported reading" not in body2, (
        "a company with nothing behind it was pointed at a reading that does "
        "not exist")


def test_the_verdict_site_register_lists_the_migrated_sites():
    """The register is the anti-D23 device; an empty one is worse than none."""
    import pathlib

    doc = pathlib.Path("docs/execution/pre100/EXECUTIVE_VERDICT_SITES.md")
    assert doc.exists(), "the verdict-site register is missing"
    text = doc.read_text()
    for site in ("render_decision_lead", "_executive_answer", "build_slides",
                 "_insufficient_evidence_page"):
        assert site in text, f"{site} is not in the verdict-site register"
    assert "MIGRATED" in text and "JUSTIFIED" in text


# --- D25 and the process fix ----------------------------------------------

def test_qa_does_not_deny_a_reading_the_contract_asserts():
    """D25, the fifth site. Q&A answered "I am not going to give you a
    strategic read on this company, because the public evidence does not
    support one -- the same reason the summary above withheld it" while the
    X-Ray gave a supported pricing decision. The trailing clause is the tell:
    it cited a refusal the summary had stopped making."""
    from intent_engine.founder_brief import build as fb
    from intent_engine.founder_brief import qa as fqa

    brief = fb.build(company="Cloudflare, Inc.", mode=fb.classify_mode(
        is_public=True, evidence_count=0, independent_sources=0,
        has_thesis=False), report={}, observations=[])
    assert brief.key_insight is None, "fixture no longer exercises D25"

    supported = ec.decide(company="Cloudflare, Inc.", run_decision=_run(False),
                          market_decision=_market(True))
    ans = fqa.answer("What should we do?", brief, contract=supported)
    assert "not going to give you a strategic read" not in ans.direct_answer, (
        "Q&A denies a reading the contract asserts")
    assert "A supported reading of Cloudflare, Inc. exists" in ans.direct_answer
    assert "did not add enough independent evidence" in (ans.so_what or "")

    # CONTROL: no market reading -> Q&A must still refuse.
    refused = ec.decide(company="Nowhere", run_decision=_run(False),
                        market_decision=None)
    ans2 = fqa.answer("What should we do?", brief, contract=refused)
    assert "not going to give you a strategic read" in ans2.direct_answer, (
        "Q&A stopped refusing for a company with nothing behind it")

    # CONTROL: no contract at all -> unchanged behaviour, never a blank.
    ans3 = fqa.answer("What should we do?", brief)
    assert ans3.direct_answer


def test_every_strategic_surface_is_declared_in_the_verdict_register():
    """THE PROCESS FIX, not another row.

    The same defect class has now been found five times: X-Ray/brief (D13,
    D17), the deck (D17), the insufficient-evidence routing sink (D22) and
    CEO Q&A (D25). The register written in batch 28 did not prevent D25 --
    Q&A was inside the sweep's SEARCH SCOPE but was never given a row, so it
    was looked at and not recorded.

    A human-maintained list is not enough. This walks the actual dispatch
    table and requires every customer-facing strategic surface to be declared,
    so adding one without saying where its executive verdict comes from is a
    test failure rather than a live contradiction found by a customer.
    """
    import inspect
    import pathlib
    import re

    from intent_engine.webapp.app import WebApp

    register = pathlib.Path(
        "docs/execution/pre100/EXECUTIVE_VERDICT_SITES.md").read_text()

    source = inspect.getsource(WebApp._route)
    handlers = set(re.findall(
        r'\("GET", "runs", \d+\)[^\n]*\n\s*return self\.(_[a-z_]+)\(', source))
    handlers |= set(re.findall(
        r'\("POST", "runs", \d+\)[^\n]*\n\s*return self\.(_[a-z_]+)\(', source))
    assert handlers, "route table shape changed; this gate is not looking at it"

    # Surfaces that state a strategic conclusion. Anything here must appear in
    # the register; anything genuinely non-strategic is declared below and the
    # declaration is itself reviewed when this list changes.
    NON_STRATEGIC = {
        "_sources_page", "_source_detail", "_evidence", "_progress",
        "_share_create", "_share_revoke", "_feedback", "_retry_evidence",
        "_fresh_analysis", "_sources_approve", "_report",
        # Measurement, not a verdict. `/timing` serves lifecycle timestamps,
        # a document count, run state, and the provenance of each. It asserts
        # nothing about the COMPANY -- no thesis, no decision, no findings --
        # so there is no executive verdict for it to source. Declared here
        # rather than in the register because putting a benchmark surface
        # into a register of strategic conclusions makes that register mean
        # less.
        "_timing_json",
        # The same reasoning, for the progress poller. `/progress.json`
        # serves the stage ladder, an elapsed line and ONE instruction --
        # where to navigate when the run becomes readable. Every field is
        # produced by the same calls `_progress` makes, and `_progress` is
        # declared non-strategic four lines above: a surface cannot become a
        # verdict site by being rendered as JSON instead of as HTML.
        "_progress_json",
        # A MOUNT, NOT A SURFACE. `_with_ask` wraps a page that is itself
        # declared here or in the register, and adds one control: a box to
        # type a question into. It asserts nothing about the company -- the
        # ANSWER is produced by `/conversation`, which is a POST route with
        # its own accountability. Declaring the wrapper as a verdict site
        # would make the register describe where a text input lives.
        "_with_ask",
    }
    undeclared = [h for h in sorted(handlers)
                  if h not in NON_STRATEGIC and h not in register]
    assert not undeclared, (
        "these customer-facing run surfaces state a strategic conclusion and "
        "are not declared in EXECUTIVE_VERDICT_SITES.md: "
        + ", ".join(undeclared)
        + " — declare where each one's executive verdict comes from")


def test_qa_does_not_collapse_every_question_into_one_refusal():
    """D28. Live on a28549c four different hostile questions returned the
    identical sentence "There is not enough public evidence to answer that
    confidently." on a run whose X-Ray asserted a supported pricing decision.

    D25 fixed only the _STRATEGIC_INTENT branch -- the case that was tested.
    Everything else fell through to the general fallback and still
    contradicted the contract. This asserts the fallback, not the branch.
    """
    from intent_engine.founder_brief import build as fb
    from intent_engine.founder_brief import qa as fqa

    brief = fb.build(company="Cloudflare, Inc.", mode=fb.classify_mode(
        is_public=True, evidence_count=0, independent_sources=0,
        has_thesis=False), report={}, observations=[])
    supported = ec.decide(company="Cloudflare, Inc.", run_decision=_run(False),
                          market_decision=_market(True))

    hostile = ["Biggest risk?", "What proves this wrong?",
               "Did you find none or fail to find it?"]
    answers = [fqa.answer(q, brief, contract=supported).direct_answer
               for q in hostile]
    for a in answers:
        assert "not enough public evidence to answer that confidently" not in a, (
            "Q&A still contradicts the contract on a non-strategic question")
        assert "A supported reading of Cloudflare, Inc. exists" in a

    # CONTROL: with no reading anywhere, the honest refusal must survive.
    refused = ec.decide(company="Nowhere", run_decision=_run(False),
                        market_decision=None)
    a = fqa.answer("Biggest risk?", brief, contract=refused).direct_answer
    assert "not enough public evidence" in a


# --- D28(b): the behaviour class, not the example -------------------------

def _composed(**over):
    """A composed decision shaped like the live one the X-Ray renders.

    STARTED FROM THE REAL SERIALISATION, not hand-listed. A composed decision
    carries every dataclass field; a fixture listing only the ones a test
    happened to need makes the completeness rule below fail for a correctly
    routed intent — the same "fixture does not match production" defect this
    file exists to prevent, arriving from the other direction.
    """
    from intent_engine.strategic_intelligence.decision import FounderDecision
    base = dict(FounderDecision().as_dict())
    base.update({"key_risk": "Renewal concentration in the enterprise base.",
            "falsifier": "A quarter where net retention falls below 100%.",
            "information_gaps": ["No independent pricing account exists."],
            "economic_history": {"statement": "Replay is not yet valid here."},
            "second_iteration": {"statement": "Nothing new arrived."},
            "competitors": ["Akamai", "Fastly"],
            "monitoring": ["Enterprise renewal disclosures."],
            "recommended_next_move": "Hold price and instrument churn."})
    base.update(over)
    return base


def test_every_declared_intent_routes_to_a_canonical_field():
    """§13. The completeness property, so a new intent cannot ship unrouted.

    This is the Q&A twin of the verdict-site register test. D28(b) existed
    because Q&A had exactly TWO intents and every other category fell to one
    generic sentence; a router that silently grows a marker set without a
    field is the same defect returning.
    """
    from intent_engine.founder_brief import qa as fqa

    decision = _composed()
    for name, markers, field, absent in fqa.INTENT_ROUTES:
        assert markers, f"{name} declares no markers"
        assert absent, f"{name} has no absence sentence"
        assert field in decision, (
            f"{name} routes to {field!r}, which the composed decision does "
            f"not carry — the router would answer from nothing")
        # every declared intent must actually be reachable from its markers
        assert fqa.intent_of(markers[0]) == name, (
            f"{name} is declared but its own first marker does not reach it")


def test_risk_uncertainty_falsifier_and_history_do_not_collapse():
    """D28(b). Live on 5e2b625 three different questions returned the same
    paragraph, because there was no router at all."""
    from intent_engine.founder_brief import build as fb
    from intent_engine.founder_brief import qa as fqa

    brief = fb.build(company="Cloudflare, Inc.", mode=fb.classify_mode(
        is_public=True, evidence_count=0, independent_sources=0,
        has_thesis=False), report={}, observations=[])
    contract = ec.decide(company="Cloudflare, Inc.", run_decision=_run(False),
                         market_decision=_market(True))
    decision = _composed()

    asked = {q: fqa.answer(q, brief, contract=contract,
                           decision=decision).direct_answer
             for q in ("What is the biggest risk?",
                       "What is the biggest uncertainty?",
                       "What proves this wrong?",
                       "What happened historically?",
                       "What should we monitor next?",
                       "What should we do?")}
    assert len(set(asked.values())) == len(asked), (
        "semantically different questions collapsed onto one answer:\n"
        + "\n".join(f"  {q!r} -> {a!r}" for q, a in asked.items()))
    assert "Renewal concentration" in asked["What is the biggest risk?"]
    assert "net retention" in asked["What proves this wrong?"]


def test_an_empty_category_says_which_category_is_empty():
    """Absence for ONE intent may not become the universal canned paragraph."""
    from intent_engine.founder_brief import build as fb
    from intent_engine.founder_brief import qa as fqa

    brief = fb.build(company="Acme", mode=fb.classify_mode(
        is_public=False, evidence_count=0, independent_sources=0,
        has_thesis=False), report={}, observations=[])
    bare = {k: ("" if not isinstance(v, (list, dict)) else type(v)())
            for k, v in _composed().items()}

    risk = fqa.answer("Biggest risk?", brief, decision=bare).direct_answer
    falsifier = fqa.answer("What proves this wrong?", brief,
                           decision=bare).direct_answer
    assert risk != falsifier, "two empty categories gave the same sentence"
    assert "risk" in risk.lower() and "falsifier" in falsifier.lower()


def test_the_router_never_invents_when_the_decision_is_absent():
    """No composed decision -> no routed answer, never a fabricated one."""
    from intent_engine.founder_brief import qa as fqa

    routed, matched = fqa._route_answer("Biggest risk?", None)
    assert matched == "biggest_risk" and routed == ""


def test_a_demo_guest_cannot_read_operator_plumbing(tmp_path):
    """D29. Measured live on 2cce6d9: /dashboard, /learning and /assistant all
    404'd for an anonymous guest while /status.json answered 200 with the
    deployed commit, the market engine's portfolio value and paper P&L, and
    scheduler job state.

    Enumerated rather than testing the one route that leaked: the gate is a
    list, and /feedback exports the same material one route over.
    """
    import io

    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig
    from tests.test_strategic_intelligence import _live_transport

    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    autorun_sources=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(cfg, transport=_live_transport, resolver=False)

    cookie = ""
    def get(path, method="POST"):
        nonlocal cookie
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": "0", "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": cookie, "wsgi.input": io.BytesIO(b"")}
        out = {}
        body = b"".join(app(env, lambda st, h: out.update(
            status=st, headers=h))).decode()
        for k, v in out["headers"]:
            if k == "Set-Cookie" and v.startswith("sid="):
                cookie = v.split(";")[0]
        return out["status"], body

    get("/demo")  # anonymous demo session — a session, but not an operator
    # /feedback is deliberately absent: the operator sessions that legitimately
    # read it are anonymous-flagged in this build, so gating it locks out the
    # operator. Its exposure is recorded as unverified, not assumed safe.
    for path in ("/dashboard", "/learning", "/assistant", "/status.json"):
        status, body = get(path, method="GET")
        assert not status.startswith("200"), (
            f"{path} served operator material to a demo guest: {body[:120]}")
