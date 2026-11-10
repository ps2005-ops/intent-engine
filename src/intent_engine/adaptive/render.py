"""The adaptive block, rendered. HTML only -- it decides nothing.

WHY THE RENDERER MAKES NO DECISIONS
-----------------------------------
Every choice this block presents -- which lens, which decision, which links,
whether the difference is real -- was already made and already explained by a
producer that could be tested. If this file also decided, the reasons shown to
the reader would be about a different computation from the one that ran, which
is a whole class of defect that cannot be caught by reading either half.

So the only judgement here is typographic.

ACCESSIBILITY AND THEME ARE NOT A LATER PASS
--------------------------------------------
Colours are declared as tokens on `:root` and re-declared under BOTH
`prefers-color-scheme: dark` and an explicit `[data-theme]`, because the
recorded failure is a light theme shipping three sub-floor contrast tokens
while a suite that only measured dark stayed green. Every interactive element
is a real control with a visible focus ring; every section is a landmark with
a heading, in document order.
"""
from __future__ import annotations

import re

import html
from typing import Optional

CSS = """
<style>
.adaptive{--ad-fg:#16181d;--ad-muted:#585d68;--ad-line:#d8dbe2;
  --ad-panel:#f6f7f9;--ad-accent:#1d4ed8;--ad-accent-fg:#ffffff;
  --ad-warn-bg:#fdf6e3;--ad-warn-fg:#6b4d00;--ad-warn-line:#e0c97a;
  --ad-ok:#1a6b3c;--ad-bg:#ffffff}
@media (prefers-color-scheme:dark){
  .adaptive:not([data-theme="light"]){--ad-fg:#e8eaef;--ad-muted:#a4abb8;
    --ad-line:#3a3f4a;--ad-panel:#1c1f26;--ad-accent:#7ea6ff;
    --ad-accent-fg:#10131a;--ad-warn-bg:#2b2410;--ad-warn-fg:#f0d68a;
    --ad-warn-line:#6b5a20;--ad-ok:#6ee7a8;--ad-bg:#12141a}}
[data-theme="dark"] .adaptive{--ad-fg:#e8eaef;--ad-muted:#a4abb8;
  --ad-line:#3a3f4a;--ad-panel:#1c1f26;--ad-accent:#7ea6ff;
  --ad-accent-fg:#10131a;--ad-warn-bg:#2b2410;--ad-warn-fg:#f0d68a;
  --ad-warn-line:#6b5a20;--ad-ok:#6ee7a8;--ad-bg:#12141a}
.adaptive{color:var(--ad-fg);background:var(--ad-bg);
  max-width:44rem;margin:0 auto;padding:0 4vw 1rem;
  font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.adaptive *{box-sizing:border-box;max-width:100%}
.adaptive h1{font-size:clamp(1.6rem,5vw,2.3rem);line-height:1.2;margin:.2em 0}
.adaptive h2{font-size:clamp(1.05rem,3.4vw,1.25rem);line-height:1.3;
  margin:1.9em 0 .5em;letter-spacing:.01em}
.adaptive h3{font-size:1rem;margin:1.2em 0 .35em}
.adaptive p{margin:.55em 0;overflow-wrap:break-word}
.ad-lens{display:block;font-size:clamp(.95rem,3vw,1.15rem);
  color:var(--ad-accent);font-weight:600;margin:.1em 0 .3em}
.ad-sub{color:var(--ad-muted);font-size:.9rem;margin:.1em 0 1.1em}
.ad-panel{background:var(--ad-panel);border:1px solid var(--ad-line);
  border-radius:10px;padding:1rem 1.1rem;margin:1rem 0}
.ad-panel>*:first-child{margin-top:0}
.ad-panel>*:last-child{margin-bottom:0}
.ad-bounded{border:1px dashed var(--ad-line);border-radius:10px;
  padding:.2rem 1.1rem 1rem;margin:1.2rem 0}
.ad-note{font-size:.85rem;color:var(--ad-muted);margin:.2em 0 .8em}
.ad-domain{border-style:dashed}
.ad-flag{background:var(--ad-warn-bg);color:var(--ad-warn-fg);
  border:1px solid var(--ad-warn-line);border-radius:8px;
  padding:.6rem .85rem;margin:.7rem 0;font-size:.9rem}
.ad-label{display:block;font-size:.72rem;letter-spacing:.10em;
  text-transform:uppercase;color:var(--ad-muted);margin:0 0 .25em}
.ad-chain{list-style:none;padding:0;margin:.6rem 0}
.ad-chain li{border-left:3px solid var(--ad-line);padding:.15rem 0 .8rem .9rem;
  margin:0;position:relative}
.ad-chain li:last-child{padding-bottom:0}
.ad-chain .ad-label{margin-bottom:.15em}
.ad-standing{display:inline-block;font-size:.7rem;letter-spacing:.06em;
  border:1px solid var(--ad-line);border-radius:999px;padding:.05em .5em;
  color:var(--ad-muted);margin-left:.4em;white-space:nowrap}
.ad-opp{border:1px solid var(--ad-line);border-radius:10px;
  padding:.85rem 1rem;margin:.7rem 0}
.ad-opp h3{margin-top:0}
.ad-rank{display:inline-block;min-width:1.6em;font-variant-numeric:tabular-nums;
  color:var(--ad-muted);font-size:.85rem}
.ad-bars{list-style:none;padding:0;margin:.5rem 0 0;font-size:.8rem;
  color:var(--ad-muted)}
.ad-bars li{display:flex;gap:.5rem;align-items:center;margin:.15rem 0}
.ad-bars span:first-child{flex:0 0 9.5rem}
.ad-meter{flex:1 1 auto;height:.45rem;background:var(--ad-line);
  border-radius:999px;overflow:hidden;min-width:3rem}
.ad-meter i{display:block;height:100%;background:var(--ad-accent)}
.ad-roles{display:flex;flex-wrap:wrap;gap:.4rem;margin:.5rem 0 0;padding:0;
  list-style:none}
.ad-roles a,.ad-roles strong{display:inline-block;font-size:.85rem;
  border:1px solid var(--ad-line);border-radius:999px;padding:.25em .8em;
  text-decoration:none;color:var(--ad-fg)}
.ad-roles strong{background:var(--ad-accent);color:var(--ad-accent-fg);
  border-color:var(--ad-accent)}
.ad-roles a:hover{border-color:var(--ad-accent);color:var(--ad-accent)}
.ad-roles li{display:inline-block;margin:0}
.ad-ask{font:inherit;font-size:.85rem;text-align:left;cursor:pointer;
  background:transparent;color:var(--ad-fg);border:1px solid var(--ad-line);
  border-radius:999px;padding:.3em .9em}
.ad-ask:hover{border-color:var(--ad-accent);color:var(--ad-accent)}
.ad-role-future{display:inline-block;font-size:.85rem;opacity:.6;
  border:1px dashed var(--ad-line);border-radius:999px;padding:.25em .8em}
.adaptive a:focus-visible,.adaptive button:focus-visible,
.adaptive summary:focus-visible{outline:3px solid var(--ad-accent);
  outline-offset:2px;border-radius:4px}
.adaptive details{margin:.7rem 0}
.adaptive summary{cursor:pointer;color:var(--ad-accent);font-size:.9rem}
.ad-quote{border-left:3px solid var(--ad-line);margin:.6rem 0;
  padding:.1rem 0 .1rem .9rem;color:var(--ad-muted);font-size:.88rem}
.ad-future{font-size:.7rem;letter-spacing:.08em;text-transform:uppercase;
  color:var(--ad-muted);border:1px dashed var(--ad-line);border-radius:999px;
  padding:.1em .55em;margin-left:.35em}
@media (max-width:420px){
  .ad-bars span:first-child{flex:0 0 7rem}
  .adaptive{padding:0 5vw 1rem}}
</style>
"""


def _e(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def _meter(label: str, value: float) -> str:
    pct = max(0, min(100, int(round(float(value or 0.0) * 100))))
    return (f'<li><span>{_e(label)}</span>'
            f'<span class="ad-meter" role="img" '
            f'aria-label="{_e(label)}: {pct} out of 100">'
            f'<i style="width:{pct}%"></i></span>'
            f'<span aria-hidden="true">{pct}</span></li>')


def headline(company: str, adaptive) -> str:
    """The company and the lens, in place of a generic product title.

    When no lens was selected the company stands alone. Printing a lens name
    we did not earn would be the exact opposite of what this section is for.
    """
    lens_name = getattr(adaptive, "headline_lens", "")
    sel = getattr(adaptive, "lens_selection", None)
    conf = getattr(sel, "confidence", "")
    out = [f'<h1>{_e(company)}</h1>']
    if lens_name:
        out.append(f'<span class="ad-lens">{_e(lens_name)}</span>')
        secondary = list(getattr(sel, "secondary_names", ()) or ())
        out.append(
            f'<p class="ad-sub">Lens selected from this company’s own '
            f'published material — {_e(conf)} confidence'
            + (f'. Also reading through {_e(", ".join(secondary))}'
               if secondary else '')
            + '.</p>')
    else:
        out.append(
            '<p class="ad-sub">No strategic lens was selected for this '
            'company. What follows is the general reading, and it is '
            'labelled as one.</p>')
    return "".join(out)


def why_different(company: str, adaptive) -> str:
    d = getattr(adaptive, "differentiation", None)
    if d is None:
        return ""
    out = ['<section class="ad-panel" aria-labelledby="ad-why">',
           f'<h2 id="ad-why" style="margin-top:0">Why this analysis is '
           f'different for {_e(company)}</h2>']
    if d.generic_interpretation:
        out.append('<span class="ad-label">Generic interpretation</span>'
                   f'<p>{_e(d.generic_interpretation)}</p>')
    if d.company_specific_difference:
        out.append('<span class="ad-label">What is different here</span>'
                   f'<p>{_e(d.company_specific_difference)}</p>')
    else:
        out.append(f'<p>{_e(d.flag_reason)}</p>')
    if d.decision_implication:
        out.append('<span class="ad-label">Decision consequence</span>'
                   f'<p>{_e(d.decision_implication)}</p>')
    # THE FOURTH PART, AND IT BELONGS HERE RATHER THAN ONLY LOWER DOWN.
    # A reader meeting "this analysis is different" immediately asks "says
    # who?" -- and the answer was three sections away, which is far enough
    # that most readers never connected the two.
    sel = getattr(adaptive, "lens_selection", None)
    if sel is not None and sel.primary_name:
        out.append('<span class="ad-label">Why Intent Engine reads it this '
                   'way</span>'
                   f'<p>{_e(sel.why_selected)}</p>')
    if d.flagged and d.company_specific_difference:
        out.append(f'<p class="ad-flag">{_e(d.flag_reason)}</p>')
    if d.evidence:
        out.append('<details><summary>The evidence this rests on</summary>')
        for span in d.evidence:
            out.append(f'<p class="ad-quote">{_e(span)}</p>')
        out.append('</details>')
    out.append('</section>')
    return "".join(out)


def lens_block(adaptive) -> str:
    sel = getattr(adaptive, "lens_selection", None)
    if sel is None:
        return ""
    out = ['<section aria-labelledby="ad-lens-h">',
           '<h2 id="ad-lens-h">The lens this analysis is using</h2>']
    if sel.primary_name:
        out.append(f'<p><strong>{_e(sel.primary_name)}</strong></p>')
    out.append(f'<p>{_e(sel.why_selected)}</p>')
    if sel.evidence_span:
        out.append(f'<p class="ad-quote">{_e(sel.evidence_span)}</p>')
    refusals = list(sel.why_others_were_not_selected or ())
    if refusals:
        out.append('<details><summary>What was considered and not '
                   'selected</summary><ul>')
        for line in refusals:
            out.append(f'<li>{_e(line)}</li>')
        out.append('</ul></details>')
    out.append('</section>')
    return "".join(out)


def opportunities(adaptive) -> str:
    """The decision map, in whichever of its three states this run is in.

    BRANCHING ON STATE IS THE WHOLE POINT. An empty `opportunities` tuple and
    an empty map are different facts about a company -- "we understand this
    business and cannot yet say what to do" is not "we could not get far
    enough to say even that" -- and rendering one card for both is what makes
    a careful product look like a broken one. Measured live: the first
    version showed "no decision opportunity cleared the bar" followed by
    three rejected candidates, on the screen that matters most.
    """
    m = getattr(adaptive, "opportunity_map", None)
    if m is None:
        return ""
    from intent_engine.adaptive import opportunity as O

    if m.state == O.DECISION_READING:
        out = ['<section aria-labelledby="ad-opp-h">',
               '<h2 id="ad-opp-h">Where better intelligence could change a '
               'decision</h2>']
        for index, o in enumerate(m.opportunities, start=1):
            out.append('<article class="ad-opp">')
            out.append(f'<h3><span class="ad-rank">{index:02d}</span> '
                       f'{_e(o.decision_description)}</h3>')
            if o.why_now:
                out.append('<span class="ad-label">Why now</span>'
                           f'<p>{_e(o.why_now)}</p>')
            out.append(f'<p class="ad-sub" style="margin:.4em 0">Owner: '
                       f'{_e(o.decision_owner_role.upper())} · domain: '
                       f'{_e(o.decision_domain)} · priority '
                       f'{o.decision_priority:.2f}</p>')
            if o.contradicting_evidence:
                out.append('<span class="ad-label">What argues against it'
                           '</span>'
                           f'<p>{_e(o.contradicting_evidence)}</p>')
            if o.recommended_information_next:
                out.append('<span class="ad-label">What to find out next'
                           '</span>'
                           f'<p>{_e(o.recommended_information_next)}</p>')
            out.append('<details><summary>How this was ranked</summary>'
                       f'<p>{_e(o.score_reason)}</p><ul class="ad-bars">')
            for label, value in (("Materiality", o.materiality),
                                 ("Change velocity", o.change_velocity),
                                 ("Company exposure", o.company_exposure),
                                 ("Actionability", o.actionability),
                                 ("Evidence strength", o.evidence_strength)):
                out.append(_meter(label, value))
            out.append('</ul></details></article>')
        for line in (m.withheld or ()):
            out.append(f'<p class="ad-quote">{_e(line)}</p>')
        out.append('</section>')
        return "".join(out)

    if m.state == O.POTENTIAL_DOMAINS:
        out = ['<section class="ad-bounded" aria-labelledby="ad-opp-h">',
               '<h2 id="ad-opp-h">Potential decision domains</h2>',
               '<p class="ad-note">Areas this company model suggests are '
               'worth investigating — <strong>not current '
               'recommendations</strong>.</p>',
               f'<p>{_e(m.reason)}</p>']
        for index, d in enumerate(m.domains, start=1):
            out.append('<article class="ad-opp ad-domain">')
            out.append(f'<h3><span class="ad-rank">{index:02d}</span> '
                       f'{_e(d.domain[0].upper() + d.domain[1:])}</h3>')
            out.append(f'<p>{_e(d.why_it_could_matter)}</p>')
            out.append(f'<p class="ad-sub">Would sit with: '
                       f'{_e(d.owner_role.upper())}</p>')
            out.append('<span class="ad-label">What would make this a '
                       'recommendation</span>'
                       f'<p>{_e(d.what_would_make_it_a_recommendation)}</p>')
            out.append('</article>')
        out.append('</section>')
        return "".join(out)

    return ('<section aria-labelledby="ad-opp-h">'
            '<h2 id="ad-opp-h">Decision domains</h2>'
            f'<p>{_e(m.reason)}</p></section>')


#: The provenance marker meaning "this run read it in this company own
#: material". No rung below may promote a class prior into a
#: company-specific fact, so every fallback is checked against it.
SUBJECT_PROV = "SUBJECT_EVIDENCE"


def bounded_block(company: str, adaptive) -> str:
    """What we know, what we cannot yet conclude, and what would change that.

    Shown ONLY when there is no decision reading. It is the positive form of
    an abstention: a reader should finish it knowing that the product
    understood their company and declined to guess, which is a different
    impression from a page with gaps in it.
    """
    m = getattr(adaptive, "opportunity_map", None)
    if m is None or getattr(m, "has_reading", False):
        return ""
    p = getattr(adaptive, "profile", None)
    sel = getattr(adaptive, "lens_selection", None)
    said = getattr(p, "self_description", None)
    out = ['<section class="ad-panel" aria-labelledby="ad-bounded-h">',
           f'<h2 id="ad-bounded-h" style="margin-top:0">What we can and '
           f'cannot say about {_e(company)}</h2>']

    out.append('<span class="ad-label">What we know</span><ul>')
    # How many entries existed before any company-specific fact, so the
    # fallback rungs fire only when the rungs above them found nothing.
    before_facts = len(out)
    if said is not None and said.value:
        out.append(f'<li>{_e(said.value)}</li>')
    model = str(getattr(p, "business_model_class", "") or "")
    if model and model != "UNKNOWN":
        out.append(f'<li>It is a {_e(model.replace("_", " ").lower())} '
                   f'business, read from its own account of how it is '
                   f'paid.</li>')
    for fact in (tuple(getattr(p, "critical_dependencies", ()) or ())[:2]):
        out.append(f'<li>It names {_e(fact.value)} as something it depends '
                   f'on.</li>')

    # THE FALLBACK HIERARCHY, AND WHY IT NEEDS MORE THAN ONE RUNG.
    #
    # MEASURED LIVE (807a4143): Cyera and Druva were the only two companies
    # whose run produced no self-description, so this block fell back to the
    # class prior and the lens. Both are subscription software and both route
    # to a data lens, so their blocks scored 0.927 similarity -- the cohort's
    # only genericity collapse. The cause was not a template. It was a
    # hierarchy exactly one rung deep.
    #
    # Every rung below is EVIDENCE-BACKED and provenance-checked: something
    # this run read in this company own material, never a sentence composed
    # to make two companies look different. Where the evidence genuinely says
    # the same thing about two companies, this block says the same thing --
    # which is the correct outcome and is what the pairwise test asserts.
    if len(out) <= before_facts:
        for fact in (getattr(p, "strategic_assets", ()) or ())[:2]:
            if (getattr(fact, "value", "")
                    and getattr(fact, "provenance", "") == SUBJECT_PROV):
                out.append(f'<li>It claims {_e(fact.value)} as its own.</li>')
        job = getattr(p, "customer_job", None)
        if (getattr(job, "value", "")
                and getattr(job, "provenance", "") == SUBJECT_PROV):
            out.append(f'<li>The job it says it does for a customer: '
                       f'{_e(job.value)}</li>')
        tech = getattr(p, "technology_exposure", None)
        if (getattr(tech, "value", "")
                and getattr(tech, "provenance", "") == SUBJECT_PROV):
            out.append(f'<li>{_e(tech.value)}</li>')
        # LAST RUNG: the words this company uses that the LENS did not
        # supply. `carried_by` is what the differentiation layer found was
        # company-specific, which is the one list here that cannot be a
        # class prior by construction.
        carried = [str(w) for w in (getattr(
            getattr(adaptive, "differentiation", None), "carried_by", ())
            or ()) if str(w)][:4]
        if carried:
            out.append('<li>What this run read as specific to it: '
                       + _e(", ".join(carried)) + '.</li>')
    out.append('</ul>')

    if sel is not None and sel.primary_name:
        out.append('<span class="ad-label">The lens this points to</span>'
                   f'<p>{_e(sel.primary_name)} — {_e(sel.why_selected)}</p>')

    # SCOPED, BECAUSE THE PAGE DOES NOT STOP HERE. A bounded run still
    # carries the founder layer's class-economics direction further down,
    # badged BOUNDED. An unqualified "we cannot say what management should
    # do" above a "what we recommend" below is one run saying two things.
    out.append('<span class="ad-label">What we cannot yet conclude</span>'
               '<p>Which of these is live for this management, or which way '
               'it should go. Knowing what kind of business this is tells us '
               'which decisions tend to matter for a business like it — and '
               'any direction stated elsewhere on this page rests on that, '
               'not on anything this run established about this company in '
               'particular.</p>')
    if m.evidence_limitation:
        out.append('<span class="ad-label">Why not</span>'
                   f'<p>{_e(m.evidence_limitation)}</p>')
    if m.what_would_unlock_a_decision:
        out.append('<span class="ad-label">What would unlock a decision'
                   '</span>'
                   f'<p>{_e(m.what_would_unlock_a_decision)}</p>')
    out.append('</section>')
    return "".join(out)


def causal_chain(adaptive) -> str:
    c = getattr(adaptive, "causal_chain", None)
    if c is None:
        return ""
    from intent_engine.adaptive import causal as C
    kind = getattr(c, "kind", "")
    investigating = kind == C.INVESTIGATION_CHAIN
    # THREE STATES, THREE HEADINGS. MEASURED LIVE (807a4143, Point B): the
    # body said "No chain is shown, of either kind ... nothing to follow and
    # nothing to ask about that would not be a guess" underneath the heading
    # "From the change to the decision". The body was right and the heading
    # promised settled causality, which is the two-way branch this layer
    # replaced everywhere else and had left standing here. A heading is the
    # part a reader scanning the page actually reads.
    heading = {
        C.INVESTIGATION_CHAIN: "What would be worth investigating",
        C.NO_CHAIN: "No supported chain yet",
    }.get(kind, "From the change to the decision")
    bounded = kind in (C.INVESTIGATION_CHAIN, C.NO_CHAIN)
    out = [f'<section class="{"ad-bounded" if bounded else ""}" '
           f'aria-labelledby="ad-chain-h">',
           f'<h2 id="ad-chain-h">{heading}</h2>']
    if investigating:
        out.append('<p class="ad-note">A line of enquiry, not a causal '
                   'claim. Nothing below asserts that one thing caused '
                   'another.</p>')
    if not c.links:
        out.append(f'<p>{_e(c.reason)}</p></section>')
        return "".join(out)
    out.append('<ol class="ad-chain">')
    for link in c.links:
        out.append('<li>'
                   f'<span class="ad-label">{_e(link.label)}</span>'
                   f'<p>{_e(link.text)}'
                   f'<span class="ad-standing">{_e(link.standing.lower())}'
                   f'</span>'
                   + ('<span class="ad-standing">could be any company'
                      '</span>' if link.generic else '')
                   + '</p></li>')
    out.append('</ol>')
    if c.stopped_because:
        out.append(f'<p class="ad-sub">{_e(c.stopped_because)}</p>')
    if c.reason:
        out.append(f'<p class="ad-flag">{_e(c.reason)}</p>')
    out.append('</section>')
    return "".join(out)


def role_switch(run_id: str, adaptive, *, current: str, base: str,
                csrf: str = "", lens_selection=None) -> str:
    """The role selector. Live roles link; future roles are shown, not hidden.

    A reader should be able to see the shape of what is coming without being
    misled into thinking it is already connected to their systems.
    """
    from intent_engine.adaptive import roles as R
    rv = getattr(adaptive, "role", None)
    out = ['<section aria-labelledby="ad-role-h">',
           '<h2 id="ad-role-h">Read this as</h2>',
           '<ul class="ad-roles">']
    for r in R.ROLES:
        if r.status == R.LIVE:
            if r.role_id == current:
                out.append(f'<strong aria-current="true">{_e(r.title)}'
                           f'</strong>')
            else:
                out.append(f'<a href="{_e(base)}?role={_e(r.role_id)}">'
                           f'{_e(r.title)}</a>')
        else:
            out.append(f'<span class="ad-role-future">{_e(r.title)}'
                       f'<span class="ad-future">future</span></span>')
    out.append('</ul>')
    if rv is not None and rv.why:
        out.append(f'<p class="ad-sub">{_e(rv.why)}</p>')
    # THE QUESTIONS ARE ASKABLE, not a printed list.
    #
    # They were rendered as `<li>` text, which is the shape of a suggestion
    # nobody takes: a reader who wants the answer has to retype the question
    # into a box further down the page. Each is now a one-click submission to
    # the canonical conversation route, so the role lens and the selected
    # lens actually change what a reader can DO and not only what they read.
    #
    # The lens's own topics come after the role's, and duplicates are dropped:
    # both producers legitimately want to ask about the same decision, and
    # printing it twice reads as padding.
    asks, seen = [], set()
    entry = getattr(lens_selection, "lens", None)
    for question in (tuple(getattr(rv, "questions", ()) or ())
                     + tuple(getattr(entry, "preferred_q_and_a_topics", ())
                             or ())):
        key = str(question).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        asks.append(str(question))
    if asks:
        out.append('<span class="ad-label">What this reader would ask'
                   '</span><ul class="ad-roles">')
        for question in asks[:6]:
            out.append(
                f'<li><form action="/runs/{_e(run_id)}/conversation" '
                f'method="post" style="display:inline">'
                f'<input type="hidden" name="csrf" value="{_e(csrf)}">'
                f'<input type="hidden" name="question" '
                f'value="{_e(question)}">'
                f'<button type="submit" class="ad-ask">{_e(question)}'
                f'</button></form></li>')
        out.append('</ul>')
    out.append('</section>')
    return "".join(out)


def value_block(company: str, adaptive) -> str:
    """Where Intent Engine could create value -- current versus future.

    The split is the honest part. Everything on the left is running today on
    public evidence; everything on the right needs data this product has not
    been given and is labelled so plainly that nobody could read it as a
    claim about what is connected now.
    """
    sel = getattr(adaptive, "lens_selection", None)
    lens_obj = getattr(sel, "lens", None)
    m = getattr(adaptive, "opportunity_map", None)
    top = getattr(m, "top", None)
    out = ['<section class="ad-panel" aria-labelledby="ad-value-h">',
           f'<h2 id="ad-value-h" style="margin-top:0">Where Intent Engine '
           f'could create value for {_e(company)}</h2>',
           '<span class="ad-label">Current — external evidence only'
           '</span><ul>',
           '<li>Monitoring the outside record for changes that reach this '
           'company through the mechanism above</li>',
           '<li>Testing the assumption the current plan rests on against '
           'what the record actually says</li>']
    if lens_obj is not None:
        for domain in lens_obj.decision_domains[:2]:
            out.append(f'<li>Watching {_e(domain)}</li>')
    out.append('<li>Provenance on every claim, so a disagreement is about '
               'the evidence rather than about the tool</li></ul>')
    out.append('<span class="ad-label">Future — with permissioned '
               'internal data<span class="ad-future">not connected</span>'
               '</span><ul>'
               '<li>CRM and pipeline, to test whether the outside reading '
               'shows up in this company’s own funnel</li>'
               '<li>Product usage and support, to see the same change from '
               'the customer side</li>'
               '<li>Finance, to attach a magnitude to an exposure that is '
               'currently directional</li>'
               '<li>Prior decisions, so a recommendation can be checked '
               'against what was already tried</li></ul>')
    if top is not None:
        out.append(f'<p class="ad-sub">The decision category this would '
                   f'improve first: {_e(top.decision_domain)}. No return is '
                   f'claimed for it, because none has been measured.</p>')
    else:
        # LOWER CASE, AND DELIBERATELY. A sentence beginning "None has been
        # measured" is correct English and puts the bare token `None` on a
        # customer page, where the raw-internals detector -- rightly -- reads
        # it as a rendered Python object. The detector is the more valuable
        # of the two, so the copy moves.
        out.append('<p class="ad-sub">No return is claimed for any of this, '
                   'because none has been measured.</p>')
    out.append('</section>')
    return "".join(out)


def _one_quote_per_passage(html: str) -> str:
    """The same sentence may be the best evidence for two sections. It is
    still ONE quotation on the page.

    MEASURED LIVE (Highspot, 7e6f3c9c): "Highspot helps enablement teams scale
    their impact with AI that identifies skill gaps..." rendered under the
    lens block AND under "the evidence this rests on". Deduping inside each
    producer could not see it, because neither producer rendered it twice --
    the PAGE did. So the rule lives where the page is assembled, and it uses
    the same prefix comparison `spans.dedupe_passages` uses, because three
    producers quote at three different budgets and the two copies are not
    byte-equal.
    """
    seen = []

    def keep(match):
        text = " ".join(re.sub(r"<[^>]+>", " ", match.group(1)).split())
        key = text.rstrip(" \u2026.").casefold()
        if not key:
            return match.group(0)
        if len(key) >= 12 and any(key.startswith(k) or k.startswith(key)
                                  for k in seen):
            return ""
        seen.append(key)
        return match.group(0)

    return re.sub(r'<p class="ad-quote">(.*?)</p>', keep, html, flags=re.S)


def block(company: str, run_id: str, adaptive, *, role_id: str = "ceo",
          base: str = "", csrf: str = "") -> str:
    """The whole adaptive block, in the order the composer put it in.

    Sections are emitted in COMPOSITION ORDER rather than in a fixed order, so
    the reordering the composer and the role lens computed is the reordering
    the reader actually meets. A block that computed an order and then
    rendered a constant one would be adaptation nobody could see.
    """
    renderers = {
        "why_this_is_different": lambda: why_different(company, adaptive),
        "strategic_lens": lambda: lens_block(adaptive),
        "decision_opportunity_map": lambda: opportunities(adaptive),
        "causal_chain": lambda: causal_chain(adaptive),
        # Rendered only when there is no decision reading; returns "" when
        # there is, so it costs nothing on a full run.
        "what_would_change_our_mind": lambda: bounded_block(company,
                                                            adaptive),
    }
    order = list(getattr(getattr(adaptive, "role", None), "order", ())
                 or getattr(getattr(adaptive, "composition", None),
                            "included_ids", ()) or ())
    seen, parts = set(), []
    for module_id in order:
        fn = renderers.get(module_id)
        if fn is None or module_id in seen:
            continue
        seen.add(module_id)
        parts.append(fn())
    for module_id, fn in renderers.items():        # nothing silently dropped
        if module_id not in seen:
            parts.append(fn())
    parts.append(role_switch(
        run_id, adaptive, current=role_id, base=base, csrf=csrf,
        lens_selection=getattr(adaptive, "lens_selection", None)))
    parts.append(value_block(company, adaptive))
    return _one_quote_per_passage("".join(p for p in parts if p))
