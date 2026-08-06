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


# Landing-page styling. Restraint is the point: one column, generous spacing,
# one primary action, and type that carries the hierarchy instead of borders
# and cards doing it. The old page read like an internal form because every
# element had the same visual weight.
# EVERY COLOUR HERE IS A VARIABLE because this sheet had none, and the landing
# page is the one screen every visitor sees before deciding whether to trust
# the product. Measured live on preview-v3 at c57af3b, in dark mode: the
# example-analysis quote rendered #1a1a2e on #0f141c — 1.08:1, invisible — the
# lede 1.68:1, and the consent label 1.9:1, so a visitor in dark mode could not
# read the sentence describing what they were about to consent to.
#
# The generic dark floor in `webapp.app._A11Y_CSS` could not save it: these
# selectors (`form.analyze label`, `.sample-quote`) are more specific than the
# floor's, so the floor lost the cascade to literals it had no rule for. The
# fix is the one that file already documents for `.brief` and `.deck` —
# re-point the variables, do not restyle each rule from outside.
_LANDING_CSS = """
:root{--l-ink:#1a1a2e;--l-muted:#4a4a63;--l-lede:#3a3a52;--l-label:#444;
  --l-faint:#555;--l-head:#77778f;--l-line:#e9e9f2;--l-field-bg:#fff;
  --l-field-line:#d5d5e2;--l-place:#9a9ab0;--l-link:#3a3a8c;--l-accent:#2f2f7a;
  --l-accent-ink:#fff}
main{max-width:44rem}
h1{font-size:2.3rem;line-height:1.15;letter-spacing:-.02em;margin:.2em 0 .5rem}
.lede{font-size:1.12rem;line-height:1.6;color:var(--l-lede);
  margin-bottom:2.4rem}
.try-line{font-size:.92rem;color:var(--l-faint);margin:-1.4rem 0 2rem}
button.linkish{background:none;border:0;padding:0;font:inherit;
  color:var(--l-link);text-decoration:underline;cursor:pointer}
form.golden{display:none}
form.analyze{margin:0 0 2.6rem}
.field-row{display:flex;gap:1rem;flex-wrap:wrap}
.field-row .field{flex:1 1 15rem;display:flex;flex-direction:column}
form.analyze label{font-size:.85rem;color:var(--l-label);margin-bottom:.25rem}
form.analyze input[type=text],form.analyze input[type=url],
form.analyze input:not([type]){width:100%;padding:.65rem .75rem;
  border:1px solid var(--l-field-line);border-radius:8px;font-size:1rem;
  background:var(--l-field-bg);color:var(--l-ink)}
form.analyze input::placeholder{color:var(--l-place)}
details.opt{margin:1rem 0 .4rem;font-size:.92rem}
details.opt summary{cursor:pointer;color:var(--l-link)}
.consent{font-size:.88rem;color:var(--l-label);margin:1rem 0 1.2rem}
form.analyze button[type=submit]{background:var(--l-accent);
  color:var(--l-accent-ink);border:0;
  border-radius:8px;padding:.7rem 1.4rem;font-size:1rem;cursor:pointer}
.sample{border-top:1px solid var(--l-line);padding-top:1.6rem;margin-top:.5rem}
.sample h2,.assurance h2{font-size:.8rem;text-transform:uppercase;
  letter-spacing:.08em;color:var(--l-head);font-weight:600}
.sample-quote{font-size:1.12rem;line-height:1.55;color:var(--l-ink);
  border-left:3px solid var(--l-accent);padding-left:1rem;margin:.8rem 0 1rem}
.sample-note{color:var(--l-muted);line-height:1.6}
.assurance{border-top:1px solid var(--l-line);padding-top:1.6rem;
  margin-top:2.4rem}
.assurance p{color:var(--l-muted);line-height:1.6}
.assurance .more{font-size:.92rem}
@media (max-width:640px){h1{font-size:1.75rem}.field-row{display:block}
  .field-row .field{margin-bottom:.9rem}}
@media (prefers-color-scheme:dark){
:root{--l-ink:#f3f4f6;--l-muted:#c3cad6;--l-lede:#c3cad6;--l-label:#c3cad6;
  --l-faint:#c3cad6;--l-head:#c3cad6;--l-line:#3a4454;--l-field-bg:#1b2230;
  --l-field-line:#606e88;--l-place:#9aa4b5;--l-link:#7aa2ff;
  --l-accent:#7aa2ff;--l-accent-ink:#0f141c}}
"""


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
/* On a phone every nav item is a thumb target, and at the shell's 0.85rem
   they were 18-20px tall -- under the 24px minimum, on the control a reader
   uses to get out of a page. Desktop is unchanged: the extra height comes
   from padding that only applies where pointing is imprecise. */
@media (max-width:600px){
nav{gap:.35rem .9rem;padding:.5rem .8rem}
nav a,nav button{display:inline-flex;align-items:center;min-height:44px;
padding:.1rem .15rem}}
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
/* PANELS THAT SET A LIGHT BACKGROUND AND NO COLOUR. Under a dark scheme the
   background stayed light while the text inherited the dark scheme's
   near-white, so each of these rendered white-on-white. Measured live on
   preview-v3 at 20ffb9c, on the PROGRESS page — the screen every visitor
   watches for the whole analysis: the stage line "Writing the founder
   briefing." inside [role=status] at 1.01:1, and the .coverage note "This
   preview stores runs in memory..." at 1.06:1. Both invisible.

   The generic floor in `webapp.app._A11Y_CSS` covers .card/.chip/details and
   could not reach these: it has no rule for [role=status], [role=alert],
   .coverage or a source-list label. Give each a dark counterpart here, beside
   the light one it corrects, so the two cannot drift apart. */
@media (prefers-color-scheme:dark){
[role=alert]{background:#2a1717;border-color:#5b2b2b;color:#ffb4b4}
[role=status]{background:#161c26;border-color:#3a4454;color:#f3f4f6}
.coverage{background:#1f1b12;border-color:#4a3f28;color:#f3f4f6}
details{background:#161c26;border-color:#3a4454}
ul.source-list li label{background:#1b2230;border-color:#3a4454;color:#f3f4f6}
ul.source-list li label:hover{background:#222b3b;border-color:#4a5568}
.tag-authoritative{background:#14351f;color:#8fe0ac}
.tag-external{background:#241a3a;color:#c4a9f5}
.tag-unverified{background:#22262e;color:#c3cad6}
.step-badge{background:#1e2440;color:#c9cdff}
.count-note{color:#c3cad6}}
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
        '<title>Founder Intelligence — read a company from the outside</title>'
        f'<style>{_BASE_CSS}{_LANDING_CSS}</style></head><body><main>'
        # 1. The promise, in terms of what you get rather than what it is.
        '<h1>Read a company the way its competitors wish they could.</h1>'
        '<p class="lede">Give us a company. We read its public evidence — its '
        'own pages, its filings and results where they exist, and what others '
        'report about it — and explain what management appears to be doing, '
        'what the business model says about why, and what the market may be '
        'missing.</p>'
        # 2. The input. One job on this screen.
        '<form action="/analyze" method="post" aria-label="Analyze a company" '
        'class="analyze">'
        '<div class="field-row">'
        '<span class="field"><label for="company_name">Company</label>'
        '<input id="company_name" name="company_name" '
        'placeholder="Cloudflare" required></span>'
        '<span class="field"><label for="website">Website</label>'
        '<input id="website" name="website" type="url" '
        'placeholder="https://www.cloudflare.com" required></span>'
        '</div>'
        '<details class="opt"><summary>Add context (optional)</summary>'
        '<p><label for="role">Your role</label>'
        '<input id="role" name="requester_role" '
        'placeholder="founder, investor, product lead"></label></p>'
        '<p><label for="q">What are you trying to work out?</label>'
        '<input id="q" name="business_question" '
        'placeholder="are they moving upmarket?"></p></details>'
        '<p class="consent"><label><input type="checkbox" name="consent" '
        'required> Analyse this company from public and official sources.'
        '</label></p>'
        '<button type="submit">Read this company</button></form>'
        # 3. What the result actually looks like. Concrete, not adjectives.
        '<section class="sample" aria-label="What you get back">'
        '<h2>What comes back</h2>'
        # The quote sat here unlabelled, so it read as something the product
        # had just produced about someone. It is an example, from a particular
        # moment, and saying so is what stops it implying a live result.
        #
        # The company is deliberately not named. It is a console maker, and
        # `test_sony_is_not_offered_as_a_prepared_example` keeps that company
        # off this page on purpose -- it is the hardest case the product
        # handles, so putting its name under "what comes back" would be
        # showcasing the weakest example rather than a representative one.
        '<p class="sample-note"><strong>Example analysis.</strong> Real '
        'output, on a consumer hardware and games company, built from public '
        'sources. Kept here as an illustration rather than refreshed, so it '
        'is not a current reading of anyone.</p>'
        '<p class="sample-quote">“Withholding first-party titles from day-one '
        'subscription is not caution — it is the one lever protecting the '
        'software margin that the discounted-hardware strategy depends on.”'
        '</p>'
        '<p class="sample-note">One conclusion like that, then why it follows: '
        'the recent evidence behind it, how the company actually earns, the '
        'trade-off leadership is managing, who is forced to respond, and what '
        'would prove the reading wrong.</p></section>'
        # 4. How evidence is handled — brief, and load-bearing for trust.
        '<section class="assurance" aria-label="How evidence is handled">'
        '<h2>Where it comes from</h2>'
        '<p>Only public sources, each one linked. Where the evidence is thin, '
        'it says so and stops rather than filling the gap. It has no access to '
        'anything inside a company and never claims otherwise.</p>'
        '<p class="more"><a href="/onboarding">How it works in detail</a></p>'
        '</section>'
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
