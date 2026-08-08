"""No founder surface may lead with a grade.

MEASURED on the deployed preview: the brief headline rendered
`headline.confidence` -- the raw analyst grade -- as its own element at the
top of the primary founder surface. "Low" is not a finding. The reason is
the part a founder can act on, because it names the evidence that would
move it.
"""
import re

from tests.test_strategic_intelligence import _live_transport
from intent_engine.founder_brief.render import (
    confidence_sentence, is_bare_grade,
)


def test_bare_grades_are_recognised():
    for g in ("Low", "  medium ", "HIGH", "Limited confidence", "partial",
              "Low.", "uncertain"):
        assert is_bare_grade(g), g
    for s in ("Low, by construction",
              "The acquisition is verified; its effect is not.",
              "Only company-authored material was retrieved"):
        assert not is_bare_grade(s), s


def test_the_reason_leads_and_the_grade_trails():
    out = confidence_sentence(
        "Low", "No independent customer evidence was retrieved")
    assert out.startswith("No independent customer evidence")
    assert not out.lower().startswith("low")


def test_a_grade_with_no_reason_is_withheld_rather_than_shown_bare():
    assert confidence_sentence("Low", "") == ""
    assert confidence_sentence("Medium", None) == ""
    # a genuine sentence in the grade slot survives
    assert confidence_sentence("Low, by construction", "") == \
        "Low, by construction"


def test_the_grade_is_not_repeated_when_the_reason_already_says_it():
    out = confidence_sentence("Low", "Confidence is low because only the "
                                     "company has spoken")
    assert out.count("low") == 1


def test_no_founder_template_renders_a_grade_as_its_own_element():
    """Structural guard against reintroducing `<p>{confidence}</p>`."""
    from pathlib import Path
    import intent_engine.webapp.app as appmod
    src = Path(appmod.__file__).read_text(encoding="utf-8")
    offenders = re.findall(
        r"<(p|h2|h3)[^>]*>\s*(?:Confidence:?\s*&?a?m?p?;?\s*)?"
        r"\{_e\(str\(\w+\[.confidence.\]\)\)\}\s*</\1>", src)
    assert not offenders, offenders


# --- cross-layer regression on a genuinely grounded run ---------------------
def test_a_grounded_brief_never_renders_a_bare_grade(tmp_path):
    """The preview cannot produce this path without a key, so it is pinned
    here: on a COMPLETE grounded run the rendered founder brief must not
    show a confidence word standing on its own."""
    from tests.test_strategic_result_states import (
        RecordedClient, _decision_payload, _transport,
    )
    from intent_engine.company_ingestion.service import CompanyIngestionService
    from intent_engine.founder_intelligence.service import (
        FounderIntelligenceService,
    )
    from intent_engine.strategic_intelligence.observations import (
        derive_analyst_evidence,
    )
    from intent_engine.strategic_intelligence.analyst import ResultState

    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    ci = CompanyIngestionService(tmp_path / "ci.jsonl", transport=_transport,
                                 resolver=False)
    run = ci.create_run(company_name="Examplecorp",
                        website="https://example.test", user_id="u",
                        as_of="2026-08-02T00:00:00+00:00")
    rid = run["run_id"]
    cands = ci.discover(rid)
    ci.approve(rid, user_id="u",
               approved_ids=[c["candidate_id"] for c in cands][:14],
               rejected_ids=[])
    ci.fetch_approved(rid)
    ev = derive_analyst_evidence(list(ci.store.retrieved(rid)))
    ci._analyst_client = RecordedClient(_decision_payload(ev[0].observation_id))
    report = ci.compose(rid, fi_service=fi)["strategic_report"]
    assert report["result_state"] == ResultState.COMPLETE

    from intent_engine.founder_brief import build as fb
    from intent_engine.founder_brief import render as fr
    brief = fb.build(company="Examplecorp", mode=fb.classify_mode(
        is_public=False, evidence_count=len(ev)), report=report,
        observations=[e.__dict__ if hasattr(e, "__dict__") else e
                      for e in ev])
    # RENDERED THROUGH THE LIVE PRIMARY SURFACE. `render_brief` is gone: it
    # built the screen from `key_insight`, which is None whenever the thesis
    # view is withheld, so it printed a refusal while the composed decision
    # was DECISION_READY.
    from intent_engine.founder_brief import narrative as fn
    story = fn.build_narrative(company="Examplecorp", brief=brief,
                               report=report)
    html = fn.render_narrative(story, run_id=rid)

    # THE REFUSAL, which is what this test is named for: no paragraph and no
    # sentence on the page may be a confidence word standing alone.
    plain = re.sub(r"<[^>]+>", " ", html)
    for para in re.findall(r"<p[^>]*>(.*?)</p>", html, re.S):
        assert not fr.is_bare_grade(re.sub(r"<[^>]+>", "", para)), para
    for sentence in re.split(r"(?<=[.!?])\s+", plain):
        assert not fr.is_bare_grade(sentence), sentence

    # The grade and its reason are still CARRIED -- the primary screen states
    # the limitation rather than the grade, which is the actionable half, but
    # nothing upstream has quietly stopped computing it.
    assert brief.confidence and brief.confidence_reason
    assert not fr.is_bare_grade(brief.confidence_reason)


# --- operability: why is the backend off? -----------------------------------
def test_readyz_distinguishes_a_missing_key_from_a_broken_client(tmp_path,
                                                                 monkeypatch):
    """A whole cycle was spent guessing between two causes that need
    opposite fixes: add the variable, or fix the code."""
    import json as _json
    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig

    def _ready(app):
        out = []
        body = app({"REQUEST_METHOD": "GET", "PATH_INFO": "/readyz",
                    "SERVER_NAME": "t", "SERVER_PORT": "80",
                    "wsgi.url_scheme": "http", "QUERY_STRING": "",
                    "HTTP_HOST": "localhost"},
                   lambda s, h: out.append(s))
        return _json.loads(b"".join(body).decode())["capabilities"]

    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    caps = _ready(WebApp(cfg, transport=_live_transport, resolver=False))
    assert caps["strategic_reasoning"] is False
    assert caps["reasoning_key_present"] is False
    assert "not set" in caps["reasoning_unavailable_because"]

    monkeypatch.setenv("ANTHROPIC_API_KEY", "x" * 8)
    caps = _ready(WebApp(cfg, transport=_live_transport, resolver=False))
    assert caps["reasoning_key_present"] is True
    # env="test" refuses to build a client, so this is the "present but no
    # client" branch -- and the two are now distinguishable.
    assert caps["strategic_reasoning"] is False
    assert "present" in caps["reasoning_unavailable_because"]


def test_readyz_never_carries_the_key_itself(tmp_path, monkeypatch):
    import json as _json
    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig
    secret_value = "sk-ant-do-not-leak-me"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret_value)
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(cfg, transport=_live_transport, resolver=False)
    out = []
    body = app({"REQUEST_METHOD": "GET", "PATH_INFO": "/readyz",
                "SERVER_NAME": "t", "SERVER_PORT": "80",
                "wsgi.url_scheme": "http", "QUERY_STRING": "",
                "HTTP_HOST": "localhost"}, lambda s, h: out.append(s))
    raw = b"".join(body).decode()
    assert secret_value not in raw
    assert "sk-ant" not in raw
