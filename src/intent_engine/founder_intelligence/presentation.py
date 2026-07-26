"""Presentation view-models + stdlib HTML renderer (T023.5).

No web framework exists in this repository (see
`docs/T0235_DEPENDENCY_GAPS.md`), so the presentation layer is a pure
Python renderer that produces server-renderable HTML strings. It computes
NO domain intelligence — it renders the view-models the service already
assembled, in the trust sequence, with the honest availability/freshness
states and accessibility attributes (semantic headings, labelled regions,
text chart summaries, status conveyed by text not colour alone).

There is no company master score anywhere, and a model-generated summary is
labelled as such, never shown as a raw fact.
"""
from __future__ import annotations

import html as _html

from intent_engine.founder_intelligence.records import (
    AVAIL_OUT_OF_SCOPE, AVAIL_UNAVAILABLE, TRUST_SEQUENCE,
)

PRESENTATION_VERSION = "fi_presentation.v1"

# A calm, evidence-led palette — but availability is ALSO stated in text, so
# nothing depends on colour alone.
_AVAIL_LABEL = {
    "SUPPORTED": "Supported", "PARTIALLY_SUPPORTED": "Partially supported",
    "CONFLICTED": "Sources disagree", "STALE": "Stale",
    "UNAVAILABLE": "Not available", "OUT_OF_SCOPE": "Out of scope",
}


def _e(text) -> str:
    return _html.escape(str(text if text is not None else ""))


def result_view_model(run_result: dict) -> dict:
    """A flat, render-ready view model. No computation — a rearrangement of
    the service's output for display."""
    return {
        "company": run_result.get("identity", {}),
        "status": run_result.get("status"),
        "limitations": run_result.get("limitations", []),
        "sections": run_result.get("sections", []),
        "note": run_result.get("note", ""),
    }


def _render_card(card: dict) -> str:
    avail = card.get("availability", "UNAVAILABLE")
    parts = [f'<article class="card avail-{_e(avail).lower()}">']
    parts.append(f'<h4>{_e(card.get("headline"))}</h4>')
    # availability + confidence + freshness in TEXT (not colour alone)
    parts.append(f'<p class="state"><strong>State:</strong> '
                 f'{_e(_AVAIL_LABEL.get(avail, avail))}')
    if card.get("confidence"):
        parts.append(f' · <strong>Confidence:</strong> {_e(card["confidence"])}')
    claims = card.get("claims", [])
    if claims:
        fresh = claims[0].get("freshness_status")
        parts.append(f' · <strong>Freshness:</strong> {_e(fresh)}')
        parts.append(f' · <strong>Evidence:</strong> {len(claims)} artifact(s)')
    parts.append('</p>')
    if card.get("why_it_matters"):
        parts.append(f'<p class="why">{_e(card["why_it_matters"])}</p>')
    if card.get("alternative_explanation"):
        parts.append(f'<p class="alt"><strong>Alternative explanation:</strong> '
                     f'{_e(card["alternative_explanation"])}</p>')
    if card.get("question_to_investigate"):
        parts.append(f'<p class="q"><strong>Question to investigate:</strong> '
                     f'{_e(card["question_to_investigate"])}</p>')
    # evidence drawer — each claim's provenance, expandable
    if claims:
        parts.append('<details><summary>Show the evidence</summary><ul>')
        for c in claims:
            for ref in c.get("source_refs", []):
                parts.append(
                    f'<li>{_e(ref.get("subsystem"))} · '
                    f'{_e(ref.get("artifact_type"))} '
                    f'<code>{_e(ref.get("artifact_id"))}</code> · '
                    f'replay <code>{_e(ref.get("replay_id"))}</code> · '
                    f'as of {_e(ref.get("as_of"))} · '
                    f'{_e(ref.get("freshness_status"))}</li>')
        parts.append('</ul></details>')
    parts.append('</article>')
    return "".join(parts)


def _render_section(section: dict) -> str:
    avail = section.get("availability", "SUPPORTED")
    parts = [f'<section aria-labelledby="s-{_e(section["kind"])}" '
             f'class="section avail-{_e(avail).lower()}">']
    parts.append(f'<h3 id="s-{_e(section["kind"])}">{_e(section["title"])}</h3>')
    if avail in (AVAIL_UNAVAILABLE, AVAIL_OUT_OF_SCOPE) and not section.get("cards"):
        parts.append(f'<p class="unavailable">{_e(_AVAIL_LABEL.get(avail, avail))}'
                     f' — {_e(section.get("note", ""))}</p>')
    for card in section.get("cards", []):
        parts.append(_render_card(card))
    for lim in section.get("limitations", []):
        parts.append(f'<p class="limitation"><em>Limitation:</em> {_e(lim)}</p>')
    parts.append('</section>')
    return "".join(parts)


_BASE_CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:820px;
margin:0 auto;padding:2rem;color:#1a1a2e;line-height:1.55}
h1{font-size:1.9rem}h3{margin-top:2.2rem;border-bottom:1px solid #e6e6ef;
padding-bottom:.3rem}.card{border:1px solid #e6e6ef;border-radius:10px;
padding:1rem 1.2rem;margin:.8rem 0;background:#fff}
.state{font-size:.85rem;color:#555}.why{color:#333}.alt,.q{font-size:.9rem;
color:#444}.limitation{font-size:.85rem;color:#666}
.unavailable{color:#666;font-style:italic}
details summary{cursor:pointer;font-size:.85rem;color:#3a3a8c}
code{background:#f4f4fa;padding:.05rem .3rem;border-radius:4px;font-size:.8rem}
.avail-conflicted{border-left:3px solid #b8860b}
.avail-stale{border-left:3px solid #999}
.trust-note{background:#f6f8ff;border-radius:10px;padding:1rem;font-size:.9rem}
/* --- shared product shell (nav, forms, controls, lifecycle states) --------- */
nav{display:flex;flex-wrap:wrap;gap:.55rem;align-items:center;font-size:.85rem;
background:#f6f8ff;border:1px solid #e6e6ef;border-radius:10px;padding:.55rem .9rem;
margin-bottom:1.6rem;color:#555}
nav a{color:#3a3a8c;text-decoration:none}nav a:hover{text-decoration:underline}
nav form{display:inline;margin:0}
nav button{background:transparent;color:#3a3a8c;border:0;padding:.1rem .2rem;
font:inherit;font-weight:500;cursor:pointer;text-decoration:underline}
nav button:hover{color:#2d2d70}
label{display:block;margin:.4rem 0 .3rem;font-weight:500}
input[type=text],input[type=email],input[type=password],input[type=url],
input:not([type]),textarea,select{width:100%;max-width:34rem;box-sizing:border-box;
padding:.55rem .7rem;border:1px solid #cfd0dc;border-radius:8px;font:inherit;
background:#fff;color:inherit}
textarea{min-height:6rem;resize:vertical}
input:focus,textarea:focus,select:focus{outline:2px solid #6b6be0;
outline-offset:1px;border-color:#6b6be0}
input[type=checkbox]{width:auto;margin-right:.5rem;vertical-align:baseline}
button{background:#3a3a8c;color:#fff;border:0;border-radius:8px;padding:.6rem 1.15rem;
font:inherit;font-weight:600;cursor:pointer}
button:hover{background:#2d2d70}
button:disabled{background:#b9b9d4;cursor:not-allowed}
.btn-row{display:flex;flex-wrap:wrap;gap:.6rem;align-items:center;margin:1.2rem 0}
[role=alert]{background:#fff4f4;border:1px solid #f0c9c9;color:#8a1f1f;
border-radius:8px;padding:.7rem .9rem;margin:1rem 0}
[role=status]{background:#f0f6ff;border:1px solid #cfe0f5;border-radius:8px;
padding:.7rem .9rem;margin:1rem 0}
.coverage{background:#fffaf0;border:1px solid #f0e0c0;border-radius:8px;
padding:.7rem .9rem;margin:1rem 0}
details{border:1px solid #e6e6ef;border-radius:10px;padding:.6rem .9rem;
margin:1.2rem 0;background:#fafaff}
details>summary{cursor:pointer;font-weight:600;color:#3a3a8c}
ul.source-list{list-style:none;padding:0;margin:.3rem 0 1.2rem}
ul.source-list li{margin:.35rem 0}
ul.source-list li label{display:block;font-weight:400;border:1px solid #e6e6ef;
border-radius:8px;padding:.55rem .7rem;background:#fff;cursor:pointer;line-height:1.4}
ul.source-list li label:hover{border-color:#c3c3e6;background:#fbfbff}
ul.source-list .tag{display:inline-block;font-size:.72rem;font-weight:600;
border-radius:999px;padding:.05rem .5rem;margin-left:.35rem;vertical-align:middle}
.tag-authoritative{background:#e7f6ec;color:#1c6b3a}
.tag-external{background:#f3eefc;color:#5b3aa0}
.tag-unverified{background:#f4f4f4;color:#666}
.stage{font-size:1rem;margin:1rem 0}
.step-badge{display:inline-block;background:#eeeefc;border-radius:999px;
padding:.15rem .75rem;font-size:.85rem;font-weight:600;color:#2d2d70}
.count-note{font-size:.85rem;color:#555}
"""


def render_result_html(run_result: dict) -> str:
    """A complete, openable result page in the trust sequence. Stdlib only."""
    vm = result_view_model(run_result)
    company = vm["company"]
    sections = sorted(vm["sections"],
                      key=lambda s: TRUST_SEQUENCE.index(s["kind"])
                      if s["kind"] in TRUST_SEQUENCE else 99)
    body = [
        '<main>',
        f'<h1>{_e(company.get("normalized_name", "Company"))}</h1>',
        f'<p class="state">Domain: <code>{_e(company.get("canonical_domain"))}'
        f'</code> · Identity confidence: {_e(company.get("identity_confidence"))}'
        f' · Status: {_e(vm["status"])}</p>',
        '<div class="trust-note">This is an outside-in view from '
        'public information and currently approved sources. Every conclusion '
        'shows its evidence, confidence, and limitations. No autonomous '
        'actions. No invented internal data. No hidden certainty. There is no '
        'overall company score.</div>',
    ]
    for section in sections:
        body.append(_render_section(section))
    body.append('</main>')
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{_e(company.get("normalized_name", "Company"))} — '
            f'Founder Intelligence</title><style>{_BASE_CSS}</style></head>'
            f'<body>{"".join(body)}</body></html>')


def render_landing_html() -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Understand your company from the outside in</title>'
        f'<style>{_BASE_CSS}</style></head><body><main>'
        '<h1>Understand your company from the outside in.</h1>'
        '<p>Enter your company and receive an evidence-backed view of how your '
        'market, customers, and public signals appear from outside the '
        'organization.</p>'
        '<form action="/analyze" method="post" aria-label="Analyze a company">'
        '<p><label for="company_name">Company name</label>'
        '<input id="company_name" name="company_name" required></p>'
        '<p><label for="website">Company website</label>'
        '<input id="website" name="website" type="url" required></p>'
        '<p><label for="role">Your role (optional)</label>'
        '<input id="role" name="requester_role"></p>'
        '<p><label for="q">What are you trying to understand? (optional)</label>'
        '<input id="q" name="business_question"></p>'
        '<p><label><input type="checkbox" name="consent" required> I approve '
        'analysis of this company using public and official sources — its '
        'website and, for public companies, SEC filings.</label></p>'
        '<button type="submit">Analyze my company</button></form>'
        '<p class="trust-note">Every conclusion shows its evidence, confidence, '
        'and limitations. No autonomous actions. No invented internal data. '
        'No hidden certainty.</p>'
        '</main></body></html>')


def render_report_preview(run_result: dict) -> dict:
    """A shareable executive brief view model — a SUBSET of sections, with
    no private notes, no internal memory, no secrets. Sharing disabled by
    default (export/preview only; public links are a dependency gap)."""
    keep = {"company_understanding", "what_stood_out", "possible_blind_spots",
            "executive_confidence", "leadership_questions"}
    sections = [s for s in run_result.get("sections", []) if s["kind"] in keep]
    return {
        "report_version": PRESENTATION_VERSION,
        "company": run_result.get("identity", {}),
        "sections": sections,
        "limitations": run_result.get("limitations", []),
        "sharing": "disabled by default — export/preview only; public "
                   "share-links are a recorded dependency gap",
    }
