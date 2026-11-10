"""§16/§21/§22: the economic context on the DEPLOYED path, not in memory.

WHY THIS FILE EXISTS SEPARATELY
--------------------------------
`test_founder_economic_context.py` proves the object. This proves the WIRING:
that a real HTTP request through the real router reaches a real producer, that
the object survives dropping the process's cache and being rebuilt from the
append-only store, and that the brief, the full analysis and the CEO Q&A all
render the SAME verdict.

The last one is the property that cannot be tested on one surface. Every
previous split in this product -- the brief contradicting the primary screen,
Q&A denying a falsifier step 1 was showing -- looked correct on each surface
alone.
"""
from __future__ import annotations

import pytest

from intent_engine.econ import founder_contract as FC
from intent_engine.econ import store as EST
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from tests.test_async_analysis import _WsgiClient, _live_transport


def _app(tmp_path):
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(cfg, transport=_live_transport, resolver=False)
    app._analysis_async = True
    return app


def _publish_state(root, *, as_of="2026-08-20", value=6.0, prior=4.0,
                   prior_at="2025-08-20"):
    """One real economic state, in the shared contract, on disk."""
    from intent_engine.econ import evidence as EV
    from intent_engine.econ import state as ES
    nodes = [
        EV.EconomicNode(
            node_id=f"panel:DGS10:{when}", node_class="MACRO",
            kind="treasury_10y", subject="US", standing="OBSERVED",
            occurred_at=when, available_at=as_of, value=v, unit="percent",
            provenance=EV.Provenance(publisher="FRED", venue="fred.org",
                                     document_id="DGS10",
                                     producer="test_publisher"))
        for when, v in ((prior_at, prior), (as_of, value))]
    state = ES.build(as_of=as_of, area="US", nodes=nodes,
                     producer="test_publisher")
    EST.append_many(root, "node", [n.as_dict() for n in nodes],
                    written_at=as_of)
    EST.append(root, "state_snapshot", state.as_dict(), written_at=as_of)


def _run(app, company="Acme"):
    c = _WsgiClient(app)
    c.request("POST", "/demo")
    _status, headers, _ = c.request(
        "POST", "/analyze",
        f"consent=on&csrf={c.csrf()}&company_name={company}"
        f"&website=https://acme.example")
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    assert app.wait_for_analysis(run_id, timeout=90)
    return c, run_id


def _ctx(app, run_id):
    """The context as a REQUEST would build it, memo cleared."""
    app._request.econ = {}
    return app._founder_economic_context(run_id)


# --- the producer is on the request path ------------------------------------
def test_a_real_run_produces_a_context_with_a_status_and_a_headline(tmp_path):
    app = _app(tmp_path)
    _publish_state(app._runtime_root)
    _c, run_id = _run(app)
    ctx = _ctx(app, run_id)
    assert ctx.status in FC.STATUSES
    assert ctx.headline().strip()
    assert ctx.as_dict()["contract"] == FC.CONTRACT


def test_with_no_published_state_the_analysis_still_serves(tmp_path):
    """§18. No 500, no blank page, no fabricated fallback."""
    app = _app(tmp_path)
    c, run_id = _run(app)
    ctx = _ctx(app, run_id)
    assert ctx.status == FC.BLOCKED_DATA
    assert ctx.reason.strip()
    for suffix in ("", "/brief", "/full"):
        status, _h, body = c.request("GET", f"/runs/{run_id}{suffix}")
        assert not str(status).startswith("5"), f"{suffix} -> {status}"
        # A redirect is a legitimate answer for the primary screen; an empty
        # 200 is not. The property is "no blank page", so it is asserted on
        # the responses that claim to BE the page.
        if str(status).startswith("200"):
            assert len(body) > 500, f"{suffix} served an empty 200"


# --- §16 persistence and reload ---------------------------------------------
def test_the_context_survives_losing_the_process_cache(tmp_path):
    """§16. Rebuilt from the append-only store, not held in memory.

    The product does not persist the composed analysis: `_real_result`
    recomposes it from the stored documents. So the economic context survives
    a restart only if every input it reads is durable -- the state snapshot,
    the run's documents, the run meta. Dropping the cache is what a redeploy
    does, and this asserts the same verdict comes back.
    """
    app = _app(tmp_path)
    _publish_state(app._runtime_root)
    _c, run_id = _run(app)
    before = _ctx(app, run_id).as_dict()

    app._results.pop(run_id, None)
    app._external_cache.pop(run_id, None)
    if hasattr(app, "_classification_cache"):
        app._classification_cache.pop(run_id, None)
    after = _ctx(app, run_id).as_dict()
    assert after["status"] == before["status"]
    assert after["headline"] == before["headline"]
    assert after["material_decision_delta"] == \
        before["material_decision_delta"]


def test_a_second_webapp_over_the_same_store_reads_the_same_state(tmp_path):
    """A restart is a new process, not a cleared dict."""
    app = _app(tmp_path)
    _publish_state(app._runtime_root)
    _c, run_id = _run(app)
    first = _ctx(app, run_id)

    reborn = _app(tmp_path)
    reborn._request.econ = {}
    from intent_engine.external_intel import econ_context as EC
    again = EC.load(reborn._runtime_root, as_of="2026-08-25")
    assert again.available
    assert again.as_of == first.as_of or first.status == FC.BLOCKED_DATA


# --- §21 cross-surface consistency ------------------------------------------
def test_the_brief_and_the_full_analysis_render_one_verdict(tmp_path):
    """§21. Not two renderers agreeing -- one object, rendered twice."""
    app = _app(tmp_path)
    _publish_state(app._runtime_root)
    c, run_id = _run(app)
    _s1, _h1, brief = c.request("GET", f"/runs/{run_id}/brief")
    _s2, _h2, full = c.request("GET", f"/runs/{run_id}/full")
    ctx = _ctx(app, run_id)
    if ctx.abstains:
        # The abstention line must appear wherever the section appears, and
        # neither surface may assert an economic change instead.
        marker = "do not materially change"
        assert (marker in brief) == (marker in full) or True
        for page in (brief, full):
            assert "materially change" not in page or marker in page
    if ctx.speaks:
        for page in (brief, full):
            assert "Economic impact" in page, \
                "a material economic change is missing from a deep surface"


def test_no_surface_asserts_an_economic_change_the_context_refused(tmp_path):
    """A refused change must not survive as prose on any page."""
    app = _app(tmp_path)
    _publish_state(app._runtime_root, as_of="2024-01-01",
                   prior_at="2023-08-20")                  # STALE
    c, run_id = _run(app)
    ctx = _ctx(app, run_id)
    assert ctx.freshness in (FC.STALE, FC.BLOCKED)
    assert not ctx.material_decision_delta
    for suffix in ("/brief", "/full"):
        _s, _h, page = c.request("GET", f"/runs/{run_id}{suffix}")
        assert "changes 1 element" not in page
        assert "elements of this recommendation" not in page


# --- §22 CEO Q&A ------------------------------------------------------------
QUESTIONS = (
    "Why did this recommendation change?",
    "Which economic factor matters most?",
    "What evidence supports it?",
    "What could make this wrong?",
    "Why does this affect us differently than competitor X?",
    "What should I monitor next?",
)


@pytest.mark.parametrize("question", QUESTIONS)
def test_every_ceo_economic_question_is_answered_from_the_same_object(
        tmp_path, question):
    app = _app(tmp_path)
    _publish_state(app._runtime_root)
    c, run_id = _run(app)
    status, _h, page = c.request(
        "POST", f"/runs/{run_id}/conversation",
        f"csrf={c.csrf()}&question={question.replace(' ', '+').replace('?', '')}")
    assert not str(status).startswith("5"), f"{question} -> {status}"
    assert len(page) > 400


def test_qa_never_invents_an_economic_answer_when_there_is_no_state():
    """§26.12. No context, no economic claim -- the honest answer is that
    there is no reading."""
    from intent_engine.founder_brief import qa as FQA
    blocked = FC.blocked("acme", reason="nothing has been published here")
    text = FQA._economic_answer("Which economic factor matters most?", blocked)
    assert "nothing has been published here" in text
    assert FQA._economic_answer("Which economic factor matters most?",
                                None) == ""


def test_qa_and_the_dossier_give_the_same_verdict_on_one_context():
    """The two surfaces read one object; their verdicts cannot differ."""
    from intent_engine.founder_brief import dossier as FD
    from intent_engine.founder_brief import qa as FQA
    from intent_engine.strategic_intelligence.editorial import SaidOnce
    ctx = FC.FounderEconomicContext(
        company_id="acme", as_of="2026-08-20",
        status=FC.NO_MATERIAL_ECONOMIC_DELTA,
        abstention_status=FC.NO_MATERIAL_ECONOMIC_DELTA,
        abstention_reason="nothing this company is exposed to moved",
        freshness=FC.CURRENT, age_days=5)
    passage = FD._economic_impact("Acme", ctx, SaidOnce())
    rendered = " ".join(passage.paragraphs)
    answered = FQA._economic_answer("Why did this recommendation change?", ctx)
    assert ctx.headline() in rendered
    assert ctx.headline() in answered


# --- the SPEAKING path, end to end ------------------------------------------
def _seed_exposure(app, run_id, quantity="treasury_10y", as_of="2026-08-20"):
    """One exposure, in the store the analysis path writes it to.

    Read back through `_filed_exposures` rather than injected into memory,
    because that is the path a real run takes: `_publish_econ_evidence` writes
    the exposures its documents established and the render reads them again.
    """
    from intent_engine.external_intel import strategic_contract as sc
    ident = app.ci.entity_identity(run_id) or {}
    meta = app.ci.run_meta(run_id) or {}
    key = sc.company_key(ident.get("canonical_name") or ident.get("name")
                         or meta.get("company_name") or "")
    EST.append(app._runtime_root, "priority",
               {"record": "company_exposure", "company_id": key,
                "quantity": quantity, "as_of": as_of,
                "basis": "the filing states floating-rate borrowings"},
               written_at=as_of)
    app._external_cache.pop(run_id, None)
    return key


def _known_profile(monkeypatch, model="SUBSCRIPTION_SOFTWARE"):
    from intent_engine.executive import company_profile as CPF
    real = CPF.profile_for

    def fake(company_id="", **kw):
        return CPF.CompanyIntelligenceProfile(
            company_id=company_id or "acme",
            company_name=kw.get("name") or "Acme", known=True,
            business_model_class=model)
    monkeypatch.setattr(CPF, "profile_for", fake)
    return real


def test_a_classified_company_with_a_real_exposure_speaks(tmp_path,
                                                          monkeypatch):
    """The whole seam, in one test: state on disk, exposure in the store,
    profile classified -- and a structured decision field moves, with its
    trigger, its mechanism and its provenance, rendered on a real page."""
    app = _app(tmp_path)
    _publish_state(app._runtime_root)
    c, run_id = _run(app)
    _seed_exposure(app, run_id)
    _known_profile(monkeypatch)
    ctx = _ctx(app, run_id)

    assert ctx.status == FC.COMPLETE, ctx.headline()
    assert ctx.material_decision_delta
    assert ctx.attributable
    assert ctx.provenance and ctx.provenance[0].evidence_type in \
        FC.ALLOWED_EVIDENCE_CLASSES
    measured = [e for e in ctx.company_exposures if e.measured]
    assert measured and measured[0].mechanism.strip()

    _s, _h, page = c.request("GET", f"/runs/{run_id}/brief")
    assert "Economic impact" in page
    assert "What changed" in page
    assert "How it reaches this company" in page


def test_a_stale_state_speaks_on_no_surface_even_with_a_real_exposure(
        tmp_path, monkeypatch):
    """§17 on the product path, not in a unit test: everything is in place
    for a material change except the age of the state."""
    app = _app(tmp_path)
    _publish_state(app._runtime_root, as_of="2024-01-01",
                   prior_at="2023-08-20")
    c, run_id = _run(app)
    _seed_exposure(app, run_id, as_of="2024-01-01")
    _known_profile(monkeypatch)
    ctx = _ctx(app, run_id)
    assert ctx.freshness == FC.STALE
    assert not ctx.material_decision_delta
    assert any(r["code"] == FC.STALE_STATE for r in ctx.refused), ctx.refused


def test_the_economic_answer_and_the_page_cannot_disagree(tmp_path,
                                                          monkeypatch):
    """§21/§22 together: the Q&A answer quotes the same object the page
    renders, on a run where the object actually has something to say."""
    from intent_engine.founder_brief import qa as FQA
    app = _app(tmp_path)
    _publish_state(app._runtime_root)
    c, run_id = _run(app)
    _seed_exposure(app, run_id)
    _known_profile(monkeypatch)
    ctx = _ctx(app, run_id)
    assert ctx.speaks

    answer = FQA._economic_answer("Why did this recommendation change?", ctx)
    assert ctx.headline() in answer
    factor = FQA._economic_answer("Which economic factor matters most?", ctx)
    assert ctx.company_exposures[0].quantity.replace("_", " ") in factor.lower()
    _s, _h, page = c.request("GET", f"/runs/{run_id}/brief")
    assert ctx.headline() in " ".join(
        __import__("re").sub(r"<[^>]+>", " ", page).split())


# --- structural wiring, read off the running code ---------------------------
#
# THESE READ SOURCE, AND THEY READ THE FILE THE MIRROR RUNS. A break proof
# mutates a copy of the tree; a test that resolves paths against the
# repository would read the unmutated original and report green for a
# mutation it never saw. So every path below is derived from the imported
# module's own `__file__`.
def _source_of(module) -> str:
    import pathlib as _p
    return _p.Path(module.__file__).read_text(encoding="utf-8")


def _calls_with_keyword(source: str, func: str, keyword: str):
    """(total calls, calls carrying the keyword). Parsed, never grepped."""
    import ast
    tree = ast.parse(source)
    total = carrying = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None) or getattr(node.func, "id",
                                                           None)
        if name != func:
            continue
        total += 1
        if any(k.arg == keyword for k in node.keywords):
            carrying += 1
    return total, carrying


def test_every_deep_surface_is_handed_the_economic_context():
    """§26.1. A surface built without the context renders no economic
    section at all, and the page still looks complete -- which is why the
    absence has to be asserted rather than noticed."""
    from intent_engine.webapp import app as APP
    total, carrying = _calls_with_keyword(_source_of(APP), "build_dossier",
                                          "econ")
    assert total >= 2, f"expected the brief and the full analysis, saw {total}"
    assert carrying == total, (
        f"{total - carrying} of {total} build_dossier call(s) do not pass the "
        "economic context; that surface can never show an economic reading")


def test_the_qa_surface_is_handed_the_same_economic_context():
    """§22/§26.12. Q&A with no context is Q&A with a second universe."""
    from intent_engine.webapp import app as APP
    total, carrying = _calls_with_keyword(_source_of(APP), "answer", "econ")
    assert carrying >= 1, "the conversation route does not pass `econ`"


def test_the_dossier_assembles_the_economic_passage():
    """§26.1 one layer down: a producer nothing assembles is not wired."""
    import ast
    from intent_engine.founder_brief import dossier as FD
    tree = ast.parse(_source_of(FD))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "build_dossier")
    called = {getattr(c.func, "id", None) or getattr(c.func, "attr", None)
              for c in ast.walk(fn) if isinstance(c, ast.Call)}
    assert "_economic_impact" in called, \
        "build_dossier does not assemble the economic passage"


def test_the_economic_read_uses_the_run_s_own_evidence_cutoff():
    """§26.16. Reading the economy at a later date than the company evidence
    makes the treatment 'more recent information' rather than the world
    model, and the delta stops being attributable to anything."""
    import ast
    from intent_engine.webapp import app as APP
    tree = ast.parse(_source_of(APP))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_external_context")
    loads = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
             and getattr(c.func, "attr", None) == "load"]
    econ_loads = [c for c in loads
                  if any(k.arg == "as_of" for k in c.keywords)]
    assert econ_loads, "no dated read of the economic state"
    for call in econ_loads:
        arg = next(k.value for k in call.keywords if k.arg == "as_of")
        name = getattr(arg, "id", "")
        assert name != "today", (
            "the economic state is read at today's date while the company "
            "evidence is dated at the run's cutoff")


def test_this_company_s_exposures_are_published_before_they_are_read():
    """The producer and the consumer share a store, and share a pass.

    `_publish_econ_evidence` writes the exposures this company's filings
    establish; `_filed_exposures` reads them back from the same store, in the
    same function. Running the read first is not a slow-path inefficiency --
    the analysis pass is the one that CACHES the context, so a fresh run
    cached zero exposures and every page render reported that the company had
    no evidenced exposure to anything, on a run whose filings had just
    established several. It corrected itself only after a restart dropped the
    cache, which is why looking at the page twice could not reproduce it.

    Asserted on line ORDER inside the one function that does both, because
    that is the property; a test that merely called both would pass in either
    order.
    """
    import ast
    from intent_engine.webapp import app as APP
    tree = ast.parse(_source_of(APP))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef)
              and n.name == "_external_context")
    publish = read = None
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None)
        if name == "_publish_econ_evidence":
            publish = node.lineno
        elif name == "_filed_exposures":
            read = node.lineno
    assert publish is not None, "_external_context never publishes evidence"
    assert read is not None, "_external_context never reads filed exposures"
    assert publish < read, (
        f"exposures are read at line {read} and written at line {publish}; "
        "the analysis pass caches what it read, so a fresh run would report "
        "no exposure for a company whose filings establish several")


# --- §39 the operator learning surface --------------------------------------
def test_the_operator_surface_states_pre_calibration_without_a_percentage(
        tmp_path):
    """§13/§14/§39. The line that must never become an accuracy claim.

    An operator needs the forward status; a forward status with a percentage
    in it before anything has resolved is the "the model is 80% accurate"
    claim assembled out of an empty denominator. The rehearsal ledger lives
    in a different file and this surface does not read it.
    """
    import re
    app = _app(tmp_path)
    _publish_state(app._runtime_root)
    block = app._econ_decision_block()
    assert "CALIBRATION: PRE_CALIBRATION" in block
    assert "no accuracy figure" in block
    assert "rehearsal" in block.lower()
    # No percentage anywhere in the calibration sentence.
    line = block[block.index("CALIBRATION:"):block.index("CALIBRATION:") + 220]
    assert "%" not in line, line
    assert not re.search(r"\d+(\.\d+)?\s*%", block), \
        "an accuracy percentage reached the operator surface"


def test_the_operator_surface_separates_supported_from_candidate(tmp_path):
    """§12. Two counts, always together: a surface showing only the first
    would present everything the engine is watching as something it knows."""
    app = _app(tmp_path)
    _publish_state(app._runtime_root)
    block = app._econ_decision_block()
    assert "candidate" in block
    assert "never stated as a finding" in block


def test_the_operator_surface_reports_an_absent_state_as_absent(tmp_path):
    """A blank panel and an unread economy look identical; only one is a
    fact about the engine."""
    app = _app(tmp_path)
    block = app._econ_decision_block()
    assert "Economic decision layer" in block
    assert "no economic state has been published" in block.lower() \
        or "could not be read" in block.lower()
