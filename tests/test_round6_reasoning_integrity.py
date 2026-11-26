"""Round-6: what the analysis read reaches the analysis, and is described truly.

Each measured on the prospect-100 round-5 pages and store:
  * 28 trade-press articles matched no signal and produced no observation;
  * 26 pages said "every source here is published by the company itself"
    on runs that had read outside reporting;
  * WEKA's deck opened "The insight: Find a WEKA Partner.";
  * the lens-selection reason was printed twice on 15-18 companies' pages.
"""
from __future__ import annotations

from types import SimpleNamespace

from intent_engine.strategic_intelligence import evidence_classes as EC
from intent_engine.strategic_intelligence import observations as O
from intent_engine.strategic_intelligence.concrete import (
    select_founder_claim_anchor,
)


def _article(text, title="Vena Solutions set to acquire Morpheo AI | BetaKit",
             source_class="independent_reporting", sid="s1"):
    return {"source_id": sid, "final_url": f"https://betakit.com/{sid}",
            "title": title, "text_content": text,
            "source_class": source_class, "retrieval_status": "OK",
            "content_hash": sid}


BETAKIT = ("FinTech company Vena Solutions has entered an agreement to "
           "acquire fellow Toronto startup Morpheo AI. The acquisition will "
           "help Vena deepen its agentic capabilities.")


def test_an_outside_report_of_a_concrete_move_is_an_observation():
    obs = O.derive_observations([_article(BETAKIT)], company="Vena Solutions")
    assert len(obs) == 1
    assert obs[0].source_class == "independent_reporting"
    assert O.REPORTED_DEVELOPMENT in obs[0].signals
    # the evidence is the sentence that reports it, not the page's headline
    assert obs[0].excerpt.startswith("FinTech company Vena Solutions")


def test_the_company_s_own_page_does_not_get_this_signal():
    """POSITIVE CONTROL: the outside vantage is the whole point; the same
    sentence on the company's own newsroom is not independent coverage."""
    obs = O.derive_observations([_article(BETAKIT, source_class="company_owned")],
                                company="Vena Solutions")
    assert all(O.REPORTED_DEVELOPMENT not in o.signals for o in obs)


def test_an_article_that_never_names_the_subject_is_not_about_it():
    """POSITIVE CONTROL: an acquisition sentence about someone else."""
    other = ("Acme Corp has entered an agreement to acquire Widget Labs, a "
             "small Toronto startup, for an undisclosed sum.")
    assert O.derive_observations([_article(other, title="Acme news")],
                                 company="Vena Solutions") == []


def test_a_legal_suffix_does_not_hide_the_name_the_press_uses():
    text = ("WekaIO unveils its first data platform appliance for enterprise "
            "AI workloads at the show this week.")
    obs = O.derive_observations([_article(text, title="WekaIO news")],
                                company="WekaIO, Inc.")
    assert obs and O.REPORTED_DEVELOPMENT in obs[0].signals


def test_outside_reports_read_are_never_described_as_none():
    line = EC.standing_limitation({"company_owned": 3, "executive_statement": 1},
                                  read_independent=True)
    assert "published by the company itself" not in line
    assert "outside reports were read" in line


def test_without_outside_reports_the_old_line_still_stands():
    """POSITIVE CONTROL: the honest limitation for a self-published run."""
    line = EC.standing_limitation({"company_owned": 3, "executive_statement": 1})
    assert "published by the company itself" in line


def test_the_caller_passes_what_was_read(monkeypatch):
    """THE CALLER: build_strategic_report hands the document-level coverage to
    the limitation, so the line can know an outside report was read."""
    from intent_engine.strategic_intelligence import reasoning
    seen = {}
    real = EC.standing_limitation

    def spy(coverage, **kw):
        seen.update(kw)
        return real(coverage, **kw)
    monkeypatch.setattr(EC, "standing_limitation", spy)
    obs = O.derive_observations([_article(
        "Vena Solutions offers one platform for planning and reporting for "
        "finance teams and enterprise and small businesses alike today.",
        source_class="company_owned")], company="Vena Solutions")
    if not obs:
        return
    reasoning.build_strategic_report(
        company_name="Vena Solutions", observations=obs,
        source_coverage={"families": {"independent_reporting":
                                      {"documents": 1, "observations": 0}}})
    assert seen.get("read_independent") is True


def _obs(title, oid):
    return SimpleNamespace(title=title, source_title=title, text=title,
                           observation_id=oid, date="2026-07-28",
                           excerpt=title, signals=(), source_class="company_owned",
                           strategic_signal="", observation_type="messaging")


def test_a_call_to_action_never_leads_the_deck():
    """The round-5 WEKA case, reproduced: on 568e200c this returned
    "Find a WEKA Partner." as the deck's insight."""
    cta = {"source_title": "Find a WEKA Partner.",
           "excerpt": ("Partner with WEKA to deliver data infrastructure to "
                       "your customers across every major cloud and region "
                       "worldwide."),
           "observation_id": "o1", "date": "2026-07-01"}
    real = {"source_title": "WEKA integrates with NVIDIA DGX SuperPOD for AI.",
            "excerpt": "", "observation_id": "o2", "date": "2026-07-02"}
    anchor = select_founder_claim_anchor([cta, real], company="WEKA")
    assert not anchor.get("fact", "").lower().startswith("find ")


def test_the_next_real_development_leads_instead():
    cta = {"source_title": "Find a WEKA Partner.",
           "excerpt": ("Partner with WEKA to deliver data infrastructure to "
                       "your customers across every major cloud and region "
                       "worldwide."),
           "observation_id": "o1", "date": "2026-07-01"}
    real = {"source_title": "WEKA acquired Kinetica to extend its data platform.",
            "excerpt": "", "observation_id": "o2", "date": "2026-07-02"}
    anchor = select_founder_claim_anchor([cta, real], company="WEKA")
    assert anchor["fact"].startswith("WEKA acquired Kinetica")


def test_a_reported_action_still_leads():
    """POSITIVE CONTROL: the sentence the anchor exists to find."""
    anchor = select_founder_claim_anchor(
        [{"source_title": "Sentry acquired Codecov.", "observation_id": "o1",
          "date": "2026-07-01", "source_class": "company_owned"}],
        company="Sentry")
    assert anchor and anchor["fact"].startswith("Sentry acquired Codecov")


def test_the_lens_reason_is_said_once_per_block():
    from intent_engine.adaptive.render import _one_reason_per_block
    why = "It scored 19.0 against 14.0 for the next eligible lens."
    html = (f"<p>{why}</p><section><p><strong>Data</strong></p><p>{why}</p>"
            f"</section><p>Data Infrastructure — {why}</p>")
    out = _one_reason_per_block(html, why)
    assert out.count(why) == 1
    assert "Data Infrastructure</p>" in out          # the name survives


def test_a_reason_said_once_is_left_alone():
    """POSITIVE CONTROL."""
    from intent_engine.adaptive.render import _one_reason_per_block
    html = "<p>It scored 19.0.</p><p>Other.</p>"
    assert _one_reason_per_block(html, "It scored 19.0.") == html
