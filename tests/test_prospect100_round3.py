"""Round-3 repairs found by the 773-page browser matrix on the final code."""
from __future__ import annotations

import gzip
import os

from intent_engine.company_ingestion.fetch import safe_fetch

PAGE = (b"<html><body><h1>Barracuda</h1><p>Barracuda protects email, "
        b"applications and data for small and mid-sized businesses.</p>"
        b"</body></html>")


def _transport(body, encoding=""):
    headers = {"content-type": "text/html; charset=utf-8"}
    if encoding:
        headers["content-encoding"] = encoding

    def t(url, timeout, max_bytes=2_000_000):
        return 200, headers, body, False
    return t


def test_a_gzip_body_is_inflated_not_stored_as_glyphs():
    """barracuda.com answers gzip even when asked for none; four pages were
    stored as replacement glyphs and shown as "What changed, and when"."""
    r = safe_fetch("https://www.barracuda.com/", resolver=False,
                   transport=_transport(gzip.compress(PAGE), "gzip"))
    assert r["ok"], r
    assert "protects email" in r["body"]
    assert "�" not in r["body"]


def test_an_already_inflated_body_labelled_gzip_is_left_alone():
    r = safe_fetch("https://www.barracuda.com/", resolver=False,
                   transport=_transport(PAGE, "gzip"))
    assert r["ok"] and "protects email" in r["body"]


def test_binary_is_never_evidence_whatever_the_headers_say():
    r = safe_fetch("https://www.example.com/", resolver=False,
                   transport=_transport(os.urandom(8000)))
    assert not r["ok"] and r["failure_type"] == "parse_error", r


def test_the_feedback_button_has_a_colour_on_every_page():
    """/connect never defines --accent: the button was white on white
    (870 measurements, 87 companies, light theme)."""
    from intent_engine.founder_brief import steps
    css = " ".join(v for v in vars(steps).values() if isinstance(v, str))
    assert "background:var(--accent,#" in css.split(".fbx button{", 1)[1][:120]


def test_a_long_url_in_a_list_item_wraps():
    from intent_engine.webapp import app
    assert "li{overflow-wrap:break-word}" in app._A11Y_CSS


LENS = ("This company's own material is about mean time to repair, "
        "operational efficiency and workflow, which is what operations "
        "software sells.")


def test_a_page_paragraph_said_twice_is_printed_once():
    """The introduction printed the lens rationale under two headings."""
    from intent_engine.founder_brief.dossier import dedupe_page_paragraphs
    page = (f"<h2>Why this analysis is different</h2><p>{LENS}</p>"
            f"<h2>The lens this analysis is using</h2><p class='x'>{LENS}</p>"
            f"<p>{LENS} It also names the buyer it sells to, which is new.</p>")
    out = dedupe_page_paragraphs(page)
    assert out.count("mean time to repair") == 2      # first + the extended one
    assert "<p class='x'>" not in out


def test_a_macro_label_counts_as_said_so_the_chart_heading_goes():
    """A macro row's fact is its <dt> LABEL; only the <dd> text was
    remembered, so the chart heading re-printed the fact on ~30 companies."""
    from intent_engine.founder_brief import dossier as fd
    fact = ("Average interest rate on outstanding Treasury notes is rising: "
            "3.4 percent (from 3.1, +0.3), compared with the same month a "
            "year earlier.")
    passage = fd.Passage("macro", "Macro and industry exposure",
                         depth=fd.BOTH, kind="labelled",
                         items=({"label": fact,
                                 "text": "The company's customers depend on "
                                         "borrowing, so the cost of credit "
                                         "changes what they can afford."},))
    chart = (f'<figure class="xchart"><p class="xc-hd">{fact}</p><svg></svg>'
             f'<figcaption>A caption sentence the page has not said anywhere '
             f'above it at all.</figcaption></figure>')
    html = fd.render_dossier(fd.Dossier(company="Acme", passages=(passage,)),
                             depth=fd.FULL, wrap=False,
                             charts={"macro_interest_rates": chart})
    assert html.count("Average interest rate on outstanding") == 1, html
    assert "<figcaption>" in html          # the new caption stays


def test_the_bounded_read_lead_escapes_once():
    """Live (local pass 3): "period&#x27;s revenue" on 39 companies' /brief
    and /full -- `_p` escapes, and the bounded-read branch escaped first."""
    from types import SimpleNamespace as NS

    from intent_engine.executive import contract as ec
    from intent_engine.founder_brief import dossier as fd
    from intent_engine.strategic_intelligence.decision import (
        FounderDecision, WITHHELD,
    )
    decision = FounderDecision(readiness=WITHHELD, company_name="Acme")
    contract = ec.decide(company="Acme", run_decision=decision,
                         market_decision=None, bounded_read=True)
    action = NS(causal_confidence="BOUNDED",
                what_is_known="the installed base carries next period's "
                              "revenue",
                what_remains_unknown="x", why_it_matters="y",
                action_now="z", minimum_viable_experiment="m",
                kill_switch="k", falsifier="f")
    read = NS(puts_a_strategy_forward=True, level6_action=action,
              level5_decision=NS(text="The decision is what Acme's "
                                      "customers pay for."))
    lead = fd.render_decision_lead(decision, "Acme", contract=contract,
                                   read=read)
    assert "&amp;#x27;" not in lead and "&amp;" not in lead, lead
    assert "period&#x27;s" in lead or "period's" in lead
