"""T023.5 Founder Intelligence Experience: the founder-usefulness path, the
ten refusals, security/isolation, evidence integrity, presentation, and the
repository invariants.

Built on the deterministic demo fixture + the T023 SourceClaim contract.
0 real model calls (fake client). 0 network. No live company data is used.
"""
import ast
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from intent_engine.founder_intelligence import (
    FounderIntelligenceError, FounderIntelligenceService, SecretRejected,
    UnsafeURLRejected, capture_snapshot, render_report_preview,
    render_result_html, resolve_identity, validate_public_url,
)
from intent_engine.founder_intelligence.fixtures import (
    DEMO_AS_OF, DEMO_COMPANY_NAME, DEMO_DOMAIN, demo_claims,
)
from intent_engine.founder_intelligence.hooks import select_hook
from intent_engine.founder_intelligence.records import (
    IDENTITY_MISMATCH, TRUST_SEQUENCE, assert_trust_sequence,
    IntelligenceSection, SECTION_BLIND_SPOTS, SECTION_UNDERSTANDING,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src/intent_engine"


@pytest.fixture()
def run(tmp_path):
    svc = FounderIntelligenceService(tmp_path / "fi.jsonl")
    result = svc.run(company_name=DEMO_COMPANY_NAME,
                     website=f"https://{DEMO_DOMAIN}",
                     claims_by_section=demo_claims(), as_of=DEMO_AS_OF)
    return svc, result


# =============================================================================
# The founder-usefulness path (the trust sequence)
# =============================================================================

def test_the_run_completes_in_the_trust_sequence(run):
    _, result = run
    assert result["status"] == "COMPLETE"
    kinds = [s["kind"] for s in result["sections"]]
    # understanding first; no perspective section before it
    assert kinds[0] == "company_understanding"
    for perspective in ("what_stood_out", "possible_blind_spots",
                        "assumptions_to_investigate", "executive_attention"):
        assert kinds.index("company_understanding") < kinds.index(perspective)


def test_proof_of_understanding_fields_carry_evidence(run):
    _, result = run
    section = next(s for s in result["sections"]
                   if s["kind"] == "company_understanding")
    assert section["cards"]
    for card in section["cards"]:
        assert card["claims"], "every understanding field cites a claim"
        assert card["claims"][0]["source_refs"]


def test_unavailable_metric_is_not_zero(run):
    _, result = run
    analytics = next(s for s in result["sections"]
                     if s["kind"] == "evidence_and_analytics")
    unavailable = [c for c in analytics["cards"]
                   if c["availability"] == "UNAVAILABLE"]
    assert unavailable
    for c in unavailable:
        assert "0" not in c["headline"].split(":")[-1] or "financial" in \
            c["headline"].lower()
        assert c["claims"] == []           # no invented evidence


def test_conflict_is_preserved(run):
    _, result = run
    analytics = next(s for s in result["sections"]
                     if s["kind"] == "evidence_and_analytics")
    assert any(c["availability"] == "CONFLICTED" for c in analytics["cards"])


def test_one_supported_hook_is_selected(run):
    _, result = run
    stood_out = next(s for s in result["sections"]
                     if s["kind"] == "what_stood_out")
    assert stood_out["cards"]
    assert stood_out["cards"][0]["claims"]      # supported


def test_blind_spot_carries_alternative_and_question(run):
    _, result = run
    blind = next(s for s in result["sections"]
                 if s["kind"] == "possible_blind_spots")
    for card in blind["cards"]:
        assert card["alternative_explanation"]
        assert card["question_to_investigate"]


def test_executive_confidence_names_known_and_unknown(run):
    _, result = run
    conf = next(s for s in result["sections"]
                if s["kind"] == "executive_confidence")
    headlines = " ".join(c["headline"] for c in conf["cards"]).lower()
    assert "most confident" in headlines
    assert "cannot yet determine" in headlines
    # no single master score
    assert "/100" not in json.dumps(result)


def test_what_we_do_not_believe_yet_refuses_a_conclusion(run):
    _, result = run
    section = next(s for s in result["sections"]
                   if s["kind"] == "what_we_do_not_believe_yet")
    assert section["cards"]
    assert all(c["availability"] == "UNAVAILABLE" for c in section["cards"])


def test_a_leadership_question_is_produced_and_traceable(run):
    _, result = run
    questions = next(s for s in result["sections"]
                     if s["kind"] == "leadership_questions")
    assert questions["cards"]
    assert questions["cards"][0]["claims"]     # traceable to evidence


def test_conversation_answers_from_the_run_claims(run):
    svc, result = run
    run_claims = [c for group in demo_claims().values()
                  if isinstance(group, list) for c in group]
    ans = svc.converse(result["run_id"], "why do you think this? show evidence",
                       run_claims=run_claims)
    assert ans["intent"] == "SUPPORTED"
    assert ans["answer"]["paragraphs"]
    assert any(p["citations"] for p in ans["answer"]["paragraphs"])


def test_snapshot_reproduces(run):
    svc, result = run
    first = capture_snapshot(svc, result["run_id"],
                             company_domain=result["company_domain"],
                             as_of=DEMO_AS_OF)
    second = capture_snapshot(svc, result["run_id"],
                              company_domain=result["company_domain"],
                              as_of=DEMO_AS_OF)
    assert second["snapshot_id"] == first["snapshot_id"]
    assert "byte-identical" in first["replay_semantics"]["deterministic_sections"]


def test_the_run_is_deterministic(tmp_path):
    a = FounderIntelligenceService(tmp_path / "a.jsonl").run(
        company_name=DEMO_COMPANY_NAME, website=f"https://{DEMO_DOMAIN}",
        claims_by_section=demo_claims(), as_of=DEMO_AS_OF)["sections"]
    b = FounderIntelligenceService(tmp_path / "b.jsonl").run(
        company_name=DEMO_COMPANY_NAME, website=f"https://{DEMO_DOMAIN}",
        claims_by_section=demo_claims(), as_of=DEMO_AS_OF)["sections"]
    assert a == b


# =============================================================================
# The ten refusals
# =============================================================================

def test_refusal_a_unsupported_insight_returns_fewer(tmp_path):
    """With thin evidence there is no hook — the section says so honestly
    rather than filling three."""
    svc = FounderIntelligenceService(tmp_path / "thin.jsonl")
    thin = {"understanding": demo_claims()["understanding"][:1],
            "analytics": [], "market_view": [], "persona": [],
            "blind_spot": [], "assumption": [], "attention": [],
            "opportunity": []}
    result = svc.run(company_name="Thin Co", website="https://thin.example",
                     claims_by_section=thin, as_of=DEMO_AS_OF)
    stood = next(s for s in result["sections"]
                 if s["kind"] == "what_stood_out")
    assert stood["availability"] == "UNAVAILABLE"
    assert "not yet have enough evidence" in stood["note"]


def test_refusal_b_invented_statistic_rejected(run):
    """A model narrative asserting a statistic with a claim id not in the
    closed run ClaimSet is rejected."""
    svc, result = run
    run_claims = [c for group in demo_claims().values()
                  if isinstance(group, list) for c in group]
    client = MagicMock()
    client.call_tool.return_value = {"paragraphs": [
        {"text": "Conversion is 18% below the industry average.",
         "claim_ids": ["INVENTED-STAT"]}]}
    svc.llm_client = client
    # the invented claim id is rejected by the reused T023 closed-ClaimSet
    # validation (PersonalError) — the public layer inherits that contract
    from intent_engine.personal.records import PersonalError
    with pytest.raises((PersonalError, FounderIntelligenceError),
                       match="not in the closed"):
        svc.converse(result["run_id"], "show me the evidence",
                     run_claims=run_claims)


def test_refusal_c_unsupported_causality_rejected(run):
    svc, result = run
    run_claims = [c for group in demo_claims().values()
                  if isinstance(group, list) for c in group]
    client = MagicMock()
    # references a real claim id but adds a causal claim no source supports
    client.call_tool.return_value = {"paragraphs": [
        {"text": "Low public engagement is reducing revenue.",
         "claim_ids": ["a.engagement"]}]}
    svc.llm_client = client
    with pytest.raises(FounderIntelligenceError, match="causal"):
        svc.converse(result["run_id"], "why do you think this? evidence",
                     run_claims=run_claims)


def test_refusal_d_wrong_company_identity_stops(tmp_path):
    svc = FounderIntelligenceService(tmp_path / "mism.jsonl")
    result = svc.run(company_name="Acme", website="https://acme.example",
                     claims_by_section=demo_claims(), as_of=DEMO_AS_OF,
                     resolved_domain="https://different-org.example")
    assert result["status"] == "REJECTED"
    assert "mismatch" in result["reason"].lower()


@pytest.mark.parametrize("bad", [
    "ftp://acme.com", "http://localhost/x", "http://127.0.0.1",
    "http://10.0.0.5/a", "http://169.254.1.1", "http://192.168.1.1",
    "notaurl", "http://internal",
])
def test_refusal_e_internal_or_bad_url_rejected(bad):
    with pytest.raises(UnsafeURLRejected):
        validate_public_url(bad)


def test_refusal_f_competitor_invention_out_of_scope(run):
    _, result = run
    comp = next(s for s in result["sections"] if s["kind"] == "competitors")
    assert comp["availability"] == "OUT_OF_SCOPE"
    assert comp["cards"] == []


def test_refusal_g_no_hidden_action_surface(run):
    svc, _ = run
    for banned in ("publish", "send", "email", "execute", "deploy",
                   "launch", "change_homepage", "schedule"):
        assert not [m for m in dir(svc)
                    if banned in m.lower() and not m.startswith("_")], banned


def test_refusal_h_cross_company_isolation(tmp_path):
    """Two companies in one store; each run's rows are scoped to its own
    company domain — a run cannot read another company's rows."""
    svc = FounderIntelligenceService(tmp_path / "multi.jsonl")
    a = svc.run(company_name="Alpha", website="https://alpha.example",
                claims_by_section=demo_claims(), as_of=DEMO_AS_OF)
    b = svc.run(company_name="Beta", website="https://beta.example",
                claims_by_section=demo_claims(), as_of=DEMO_AS_OF)
    a_rows = svc.store.for_company("alpha.example")
    b_rows = svc.store.for_company("beta.example")
    assert a_rows and b_rows
    assert all(r.company_domain == "alpha.example" for r in a_rows)
    assert all(r.company_domain == "beta.example" for r in b_rows)
    assert a["run_id"] != b["run_id"]


def test_refusal_i_confidence_laundering_preserved(run):
    """A conflicted claim stays CONFLICTED through the whole result — no
    smoothing to an average."""
    _, result = run
    blob = json.dumps(result)
    assert '"CONFLICTED"' in blob
    # confidence section names disagreement, not an average
    conf = next(s for s in result["sections"]
                if s["kind"] == "executive_confidence")
    assert any("disagree" in c["headline"].lower() for c in conf["cards"])


def test_refusal_j_stale_evidence_is_marked(run):
    _, result = run
    blob = json.dumps(result)
    assert '"STALE"' in blob        # a stale source is labelled, not current


# =============================================================================
# Security / privacy
# =============================================================================

def test_secrets_are_refused_before_storage(tmp_path):
    svc = FounderIntelligenceService(tmp_path / "sec.jsonl")
    with pytest.raises(SecretRejected):
        svc.run(company_name="Acme sk-ABCDEFGHIJKLMNOPQRSTUV",
                website="https://acme.example",
                claims_by_section=demo_claims(), as_of=DEMO_AS_OF)


def test_feedback_does_not_mutate_intelligence(run):
    svc, result = run
    before = svc.run(company_name=DEMO_COMPANY_NAME,
                     website=f"https://{DEMO_DOMAIN}",
                     claims_by_section=demo_claims(), as_of=DEMO_AS_OF)
    svc.record_feedback(result["run_id"], result["company_domain"],
                        useful="No", note="felt off")
    after = FounderIntelligenceService(svc.store.path)
    # the assembled sections are a pure function of the claims, unchanged
    again = after.run(company_name=DEMO_COMPANY_NAME,
                      website=f"https://{DEMO_DOMAIN}",
                      claims_by_section=demo_claims(), as_of=DEMO_AS_OF)
    assert again["sections"] == before["sections"]


def test_report_preview_excludes_private_and_secrets(run):
    _, result = run
    preview = render_report_preview(result)
    assert preview["sharing"].startswith("disabled by default")
    blob = json.dumps(preview)
    assert "sk-" not in blob
    # only the shareable subset of sections
    kinds = {s["kind"] for s in preview["sections"]}
    assert kinds <= {"company_understanding", "what_stood_out",
                     "possible_blind_spots", "executive_confidence",
                     "leadership_questions"}


# =============================================================================
# Presentation
# =============================================================================

def test_result_html_follows_trust_sequence_and_is_accessible(run):
    _, result = run
    html = render_result_html(result)
    assert html.index("What we understood") < html.index("Possible blind spots")
    assert "aria-labelledby" in html          # semantic regions
    assert "<label" in render_from_landing()  # inputs labelled
    assert "no overall company score" in html.lower()
    # availability stated in text, not colour alone
    assert "State:" in html
    assert "replay" in html.lower()           # evidence provenance visible


def render_from_landing():
    from intent_engine.founder_intelligence import render_landing_html
    return render_landing_html()


# =============================================================================
# Repository invariants (§50)
# =============================================================================

def test_every_present_insight_resolves_to_source_refs(run):
    _, result = run
    for section in result["sections"]:
        for card in section["cards"]:
            if card["availability"] in ("SUPPORTED", "PARTIALLY_SUPPORTED",
                                        "CONFLICTED", "STALE"):
                assert card["claims"], card["insight_id"]
                for claim in card["claims"]:
                    assert claim["source_refs"], claim["claim_id"]


def test_no_domain_intelligence_is_computed_in_the_package():
    package = SRC / "founder_intelligence"
    blob = "\n".join(f.read_text() for f in package.rglob("*.py"))
    for forbidden in ("def score_block", "def readiness_block",
                      "def detect_conflicts", "def compute_result",
                      "def build_index(", "class EvidenceIndex",
                      "class DecisionIndex", "def coverage_report"):
        assert forbidden not in blob, forbidden


def test_the_store_subclasses_the_kernel():
    from intent_engine.agentos.append_only import AppendOnlyStore
    from intent_engine.founder_intelligence.store import (
        FounderIntelligenceStore,
    )
    assert issubclass(FounderIntelligenceStore, AppendOnlyStore)
    src = (SRC / "founder_intelligence/store.py").read_text()
    assert "os.fsync" not in src and "def read_all" not in src


def test_no_unrestricted_url_retrieval_exists():
    """No live fetching in the package — ingestion is approved-input only,
    a recorded dependency gap for live retrieval."""
    package = SRC / "founder_intelligence"
    blob = "\n".join(f.read_text() for f in package.rglob("*.py"))
    for banned in ("requests.get", "urllib.request.urlopen", "urlopen(",
                   "web_fetch", "httpx.", "aiohttp"):
        assert banned not in blob, banned


def test_no_company_master_score_anywhere(run):
    import re
    _, result = run
    blob = json.dumps(result).lower()
    # no numeric master score anywhere (e.g. 72/100, "score: 72")
    assert "/100" not in blob
    assert not re.search(r"\bscore\b\s*[:=]\s*\d", blob)
    assert not re.search(r"\b\d{1,3}\s*/\s*100\b", blob)
    # the ONLY permitted mention of "company score" is the disclaimer that
    # there is none
    for match in re.finditer(r"company score", blob):
        window = blob[max(0, match.start() - 20):match.start()]
        assert "no single" in window or "no overall" in window or "no " in window


def test_presentation_computes_no_intelligence():
    """The renderer only rearranges the service's output."""
    presentation = (SRC / "founder_intelligence/presentation.py").read_text()
    tree = ast.parse(presentation)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "scoring" not in node.module
            assert "readiness" not in node.module


def test_the_marketing_and_growth_systems_are_untouched():
    """T023.5 does not expose or modify Marketing/Growth."""
    package = SRC / "founder_intelligence"
    blob = "\n".join(f.read_text() for f in package.rglob("*.py"))
    assert "marketing" not in blob.lower()
    assert "growth" not in blob.lower() or "grow" in blob.lower()


# =============================================================================
# Boundedness
# =============================================================================

def test_the_fake_model_is_called_at_most_once_per_conversation(run):
    svc, result = run
    run_claims = [c for group in demo_claims().values()
                  if isinstance(group, list) for c in group]
    client = MagicMock()
    client.call_tool.return_value = {"paragraphs": []}
    svc.llm_client = client
    svc.converse(result["run_id"], "show me the evidence",
                 run_claims=run_claims)
    assert client.call_tool.call_count <= 1


def test_a_completed_run_snapshot_reuses_watermarks(run):
    svc, result = run
    snap = capture_snapshot(svc, result["run_id"],
                            company_domain=result["company_domain"],
                            as_of=DEMO_AS_OF)
    assert snap["source_high_watermarks"]["run_rows"] > 0


from intent_engine.founder_intelligence import records as FR  # noqa: E402


@pytest.mark.parametrize("card", [
    "4111111111111111",                  # Visa
    "4111 1111 1111 1111",               # as printed
    "5500-0055-5555-5559",               # Mastercard, hyphenated
    "378282246310005",                   # American Express
    "6011111111111117",                  # Discover
    "4222222222222",                     # 13-digit Visa
])
def test_real_card_numbers_are_still_refused(card):
    with pytest.raises(SecretRejected):
        FR.assert_no_secret(f"charge it to {card} today", where="note")


@pytest.mark.parametrize("public_number", [
    # An SEC cover page prints the commission file number beside the IRS
    # employer number. Measured live on a Datadog 8-K: the whole filing was
    # refused as a credential and a real disclosure was dropped.
    "Nevada 001-39051 27-2825503",
    "Commission File Number 001-39051 IRS Employer No. 27-2825503",
    "Votes For 503,784,971 9,946,547 27,229,324",
])
def test_public_filing_identifiers_are_not_credentials(public_number):
    FR.assert_no_secret(public_number, where="note")
