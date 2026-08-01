"""The full strategic report — an argument, not a record layout.

The page is the eight moves an analyst makes in order: what we think is
happening, what happened, the evidence, why that evidence matters, what else
could explain it, what we still do not know, what to monitor, and where it all
came from. Each section is prose and each disappears entirely when it has
nothing to say, so a thin run reads as a short honest page rather than a set of
empty headings.

Two rules hold the structure together. No sentence is printed twice anywhere on
the page, deduplicated where it is written rather than after the fact (`_once`,
and `_claim_seen` for the same question asked with and without its reason).
And nothing describing the system's own machinery reaches the reader — signal
traces and snake_case identifiers are filtered at the point of use, not hidden
in an appendix that a founder would still open.
"""
from __future__ import annotations

import html as _html
import re

from intent_engine.strategic_intelligence.editorial import (
    consolidate_limitations, deduplicate, is_meaningful, lower_first,
    meaningful_items, reader_limitations, shared_evidence, strip_machinery,
)

_e = _html.escape

_STATUS_LABEL = {
    "COMPLETE": "Complete",
    "PARTIAL_STRATEGIC_EVIDENCE": "Partial — limited source diversity",
    "INSUFFICIENT_STRATEGIC_EVIDENCE": "Insufficient strategic evidence",
    "FAILED": "Could not form a strategic view",
}
_CLASS_LABEL = {
    "company_owned": "Company", "executive_statement": "Executive",
    "investor_material": "Investor", "customer_voice": "Customer",
    "competitor": "Competitor", "independent_reporting": "Independent",
    "historical_pattern": "Pattern",
}
_INDEPENDENT = ("independent_reporting", "customer_voice", "competitor")

_CSS = """
<style>
.si{font:15px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
color:#1a2233;max-width:920px;margin:0 auto;padding:0 4px}
.si h1,.si h2,.si h3,.si h4{line-height:1.25;color:#0f1729}
.si h2{font-size:1.15rem;margin:2rem 0 .6rem;padding-top:1rem;
border-top:1px solid #e7ebf0}
.si .hero{background:linear-gradient(180deg,#f7f9fc,#eef2f8);border:1px solid #e2e8f0;
border-radius:14px;padding:20px 22px;margin:12px 0 8px}
.si .hero h1{font-size:1.5rem;margin:0 0 4px}
.si .thesis{font-size:1.12rem;font-weight:600;margin:.4rem 0 .8rem;color:#10203a}
.si .kv{display:grid;grid-template-columns:170px 1fr;gap:6px 14px;margin:.4rem 0}
.si .kv b{color:#475569;font-weight:600}
.si .badges{display:flex;flex-wrap:wrap;gap:6px;margin:.3rem 0}
.si .badge{font-size:.72rem;font-weight:600;padding:2px 9px;border-radius:999px;
background:#eef2f8;color:#334155;border:1px solid #dbe3ee}
.si .badge.ind{background:#eafaf1;color:#0f7a44;border-color:#bfe9d1}
.si .status{font-size:.78rem;font-weight:700;padding:3px 11px;border-radius:999px}
.si .st-COMPLETE{background:#e7f8ee;color:#0b7a3b}
.si .st-PARTIAL_STRATEGIC_EVIDENCE{background:#fff5e5;color:#a35b00}
.si .st-INSUFFICIENT_STRATEGIC_EVIDENCE,.si .st-FAILED{background:#fdeaea;color:#b3261e}
.si .actions{display:flex;flex-wrap:wrap;gap:8px;margin:.8rem 0}
.si .actions a{font-size:.85rem;font-weight:600;text-decoration:none;
padding:7px 13px;border-radius:9px;background:#0f172a;color:#fff}
.si .actions a.ghost{background:#fff;color:#0f172a;border:1px solid #cbd5e1}
.si .card{border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px;margin:10px 0;
background:#fff}
.si .card summary{cursor:pointer;list-style:none}
.si .card summary::-webkit-details-marker{display:none}
.si .conf{font-size:.72rem;font-weight:700;padding:2px 9px;border-radius:999px;
vertical-align:middle}
.si .conf-high{background:#e7f8ee;color:#0b7a3b}
.si .conf-moderate{background:#fff5e5;color:#a35b00}
.si .conf-low,.si .conf-speculative{background:#f1f3f7;color:#556}
.si .row{display:flex;gap:10px;flex-wrap:wrap;margin:.4rem 0}
.si .chip{flex:1 1 260px;background:#f8fafc;border:1px solid #e7ebf0;border-radius:9px;
padding:9px 11px;font-size:.86rem}
.si .chip b{display:block;color:#475569;font-size:.7rem;text-transform:uppercase;
letter-spacing:.03em;margin-bottom:2px}
.si .ev{border-left:3px solid #cbd5e1;padding:4px 0 4px 10px;margin:6px 0;font-size:.9rem}
.si .ev.sup{border-color:#34c77b}.si .ev.con{border-color:#e0803a}
.si .ev .meta{color:#64748b;font-size:.76rem;margin-top:2px}
.si details.more{margin:.5rem 0}
.si details.more>summary{color:#2563eb;font-weight:600;font-size:.85rem;cursor:pointer}
/* #94a3b8 measured 2.45:1 on white — under AA for text this small. */
.si .prov{color:#64748b;font-size:.74rem}
.si .tl{list-style:none;padding-left:0;margin:.4rem 0}
.si .tl li{position:relative;padding:6px 0 6px 18px;border-left:2px solid #dbe3ee;
margin-left:6px}
.si .tl li::before{content:'';position:absolute;left:-5px;top:11px;width:8px;height:8px;
border-radius:50%;background:#64748b}
.si .tl .d{font-weight:700;color:#334155;font-size:.8rem;margin-right:6px}
.si .agenda{background:#f7f9fc;border:1px solid #e2e8f0;border-radius:12px;
padding:12px 15px;margin:10px 0}
.si .muted{color:#64748b;font-size:.85rem}
.si table.lib{width:100%;border-collapse:collapse;font-size:.82rem}
.si table.lib th,.si table.lib td{text-align:left;padding:5px 8px;border-bottom:1px solid #eef2f7}
.si table.lib th{color:#475569;font-weight:600;font-size:.72rem;text-transform:uppercase}
@media(max-width:640px){.si .kv{grid-template-columns:1fr}.si{font-size:14px}}
@media(prefers-color-scheme:dark){
.si{color:#e5e9f0}.si h1,.si h2,.si h3,.si h4{color:#f1f5f9}
.si .hero{background:linear-gradient(180deg,#141a24,#0f141c);border-color:#232c3a}
.si .card,.si .agenda{background:#141a24;border-color:#232c3a}
.si .chip,.si table.lib{background:#0f141c}.si .badge{background:#1c2530;color:#c7d2e0;border-color:#2c3644}
/* Six selectors this block originally missed. The first is the one that
   mattered: .thesis kept #10203a — dark navy on the dark page, 1.13:1, the
   most prominent sentence in the document rendered invisible. */
.si .thesis{color:#e9eef6}
.si .muted,.si .ev .meta{color:#9aa7b8}
.si .kv b,.si table.lib th{color:#aebbcd}
.si table.lib th,.si table.lib td{border-bottom-color:#232c3a}
.si .actions a.ghost{background:#141a24;color:#e5e9f0;border-color:#2c3644}
.si .st-COMPLETE{background:#10301f;color:#5fd08d}
.si .st-PARTIAL_STRATEGIC_EVIDENCE{background:#33260d;color:#e0a44a}
.si .st-INSUFFICIENT_STRATEGIC_EVIDENCE,.si .st-FAILED{background:#3a1a1a;
color:#f08c86}
.si .chip b,.si .tl .d{color:#aebbcd}
.si .prov,.si .tl li::before{color:#8b98aa}
.si details.more>summary{color:#7aa2ff}
.si .badge.ind{background:#10301f;color:#5fd08d;border-color:#1d5237}
.si .conf-high{background:#10301f;color:#5fd08d}
.si .conf-moderate{background:#33260d;color:#e0a44a}
.si .conf-low,.si .conf-speculative{background:#1c2530;color:#aebbcd}}
</style>
"""


def _as_dict(report):
    return report.as_dict() if hasattr(report, "as_dict") else report


def _obs_ev(o, kind):
    cls = _CLASS_LABEL.get(o.get("source_class", ""), o.get("source_class", ""))
    meta = " · ".join(filter(None, [
        _e(o.get("source_title", "")), _e(cls), _e(o.get("date", "")),
        "freshness " + _e(o.get("freshness", "")) if o.get("freshness") else ""]))
    return (f'<div class="ev {kind}"><div>“{_e(o.get("excerpt") or o.get("text",""))}”</div>'
            f'<div class="meta">{meta}</div></div>')


from intent_engine.strategic_intelligence.concrete import (
    reads_as_taxonomy,
)


def _central_claim(r, thesis) -> str:
    """The same claim the presentation and the brief open with.

    This page used to select its own from thesis["view"], so one company got
    three different theses and this one was the scaffold. One analysis, one
    central claim.
    """
    from intent_engine.strategic_intelligence.concrete import (
        select_founder_claim_anchor,
    )
    anchor = select_founder_claim_anchor(r.get("observations") or [],
                                         company=r.get("company_name", ""))
    if anchor:
        return anchor["fact"]
    view = thesis.get("view", "") or ""
    return "" if reads_as_taxonomy(view) else view


def _reasoning_block(h) -> str:
    """The hypothesis's own reasoning, unless it is ontology.

    "Explicit consolidation language plus several product surfaces and a
    build-on surface match the tool-to-system-of-record mechanism" describes
    the pattern library matching itself. A reader cannot check it against the
    company, because none of it came from the company.
    """
    text = h.get("reasoning", "") or ""
    if not text or reads_as_taxonomy(text):
        return ""
    return f'<p><strong>Reasoning.</strong> {_e(text)}</p>'


def _pattern_block(pat):
    """The comparable-pattern chip, or nothing.

    It printed the pattern-library entry's own NAME to the reader -- "Point
    tool -> system of record" -- followed by the library's generic mechanism
    text. That is the internal taxonomy, not a finding about this company, and
    it is where "system of record" reached the full analysis on production.
    The historical examples survive only when the entry is not itself named in
    ontology vocabulary.
    """
    if not pat:
        return ""
    if reads_as_taxonomy(pat.get("name", "")) or reads_as_taxonomy(
            pat.get("mechanism", "")):
        return ""
    ex = "".join(f'<li>{_e(e.get("name",""))} — {_e(e.get("note",""))} '
                 f'<span class="prov">{_e(e.get("source",""))}</span></li>'
                 for e in pat.get("historical_examples", []))
    return (f'<div class="chip"><b>Comparable pattern</b>{_e(pat["name"])}'
            f'<p class="muted"><strong>Mechanism:</strong> {_e(pat["mechanism"])}</p>'
            f'<ul>{ex}</ul>'
            f'<p class="muted"><strong>Where it breaks down:</strong> '
            f'{_e(pat.get("when_it_does_not_apply",""))} '
            f'{_e(pat.get("limitations",""))}</p></div>')


def _hypothesis_card(h, obs_by_id, pat_by_id):
    sup_ids = h.get("strongest_support_ids") or h.get("supporting_observation_ids", [])
    con_ids = h.get("strongest_counter_ids") or h.get("counter_observation_ids", [])
    sup = [obs_by_id[i] for i in sup_ids if i in obs_by_id]
    con = [obs_by_id[i] for i in con_ids if i in obs_by_id]
    all_sup = [obs_by_id[i] for i in h.get("supporting_observation_ids", [])
               if i in obs_by_id]
    all_con = [obs_by_id[i] for i in h.get("counter_observation_ids", [])
               if i in obs_by_id]
    pat = pat_by_id.get(h.get("pattern_id", ""), {})
    conf = h.get("confidence", "")

    # A dash here reads as a rendering bug. When there is no strong support,
    # say so — that is itself a finding about the hypothesis.
    strongest_sup = (_obs_ev(sup[0], "sup") if sup else
                     '<p class="muted">No single strongest source; see all '
                     'evidence below.</p>')
    strongest_con = _obs_ev(con[0], "con") if con else \
        '<p class="muted">No strong counter-evidence retrieved; see gaps.</p>'

    alts = "".join(f"<li>{_e(a)}</li>" for a in h.get("alternative_explanations", []))
    fals = "".join(f"<li>{_e(x)}</li>" for x in h.get("falsification_questions", []))
    reasons = "".join(f"<li>{_e(x)}</li>" for x in h.get("confidence_reasons", []))
    gaps = "".join(f"<li>{_e(g)}</li>" for g in h.get("evidence_gaps", []))
    all_sup_html = "".join(_obs_ev(o, "sup") for o in all_sup)
    all_con_html = "".join(_obs_ev(o, "con") for o in all_con) or \
        '<p class="muted">None.</p>'

    return (
        f'<details class="card hypothesis">'
        f'<summary><h3 style="display:inline">{_e(h["title"])}</h3> '
        f'<span class="conf conf-{_e(conf)}">{_e(conf)}</span>'
        # How it is known, beside how much to trust it. Confidence alone left
        # a reader unable to tell the company's own account from an outside
        # observation, and those call for different decisions.
        + (f'<span class="prov">{_e(h["provenance"])}</span>'
           if is_meaningful(h.get("provenance")) else '')
        + f'<p class="thesis" style="font-size:1rem">{_e(h["statement"])}</p>'
        + ('<div class="row">'
           + (f'<div class="chip"><b>Why now</b>{_e(h["why_now"])}</div>'
              if is_meaningful(h.get("why_now")) else '')
           + (f'<div class="chip"><b>Decision affected</b>'
              f'{_e((h.get("decision_implications") or [""])[0])}</div>'
              if is_meaningful((h.get("decision_implications") or [""])[0])
              else '')
           + '</div>'
           if is_meaningful(h.get("why_now")) or is_meaningful(
               (h.get("decision_implications") or [""])[0]) else '') +
        f'<div class="row"><div class="chip"><b>Strongest support</b>{strongest_sup}</div>'
        f'<div class="chip"><b>Strongest counterpoint</b>{strongest_con}</div></div>'
        f'<p class="muted">▸ Expand for full reasoning, comparison, and all evidence.</p>'
        f'</summary>'
        f'<div>{_reasoning_block(h)}'
        f'<h4>Alternative explanations</h4><ul>{alts}</ul>'
        f'<h4>Comparison</h4>{_pattern_block(pat) if pat else ""}'
        f'<h4>Confidence: {_e(conf)}</h4><ul>{reasons}</ul>'
        f'<h4>What would change our mind?</h4><ul>{fals}</ul>'
        f'<details class="more"><summary>View all supporting evidence '
        f'({len(all_sup)})</summary>{all_sup_html}</details>'
        f'<details class="more"><summary>View all contradictions '
        f'({len(all_con)})</summary>{all_con_html}</details>'
        f'<details class="more"><summary>Evidence gaps</summary><ul>{gaps}</ul>'
        f'</details></div></details>')


def render_strategic_report(report) -> str:
    r = _as_dict(report)
    obs_by_id = {o["observation_id"]: o for o in r.get("observations", [])}
    pat_by_id = {p["pattern_id"]: p for p in r.get("patterns", [])}
    thesis = r.get("thesis", {})
    status = r.get("status", "")
    hyps = r.get("hypotheses", [])
    timeline = r.get("timeline", [])
    freshness = timeline[-1]["date"] if timeline else "—"

    coverage_badges = "".join(
        f'<span class="badge{" ind" if c in _INDEPENDENT else ""}">'
        f'{_CLASS_LABEL.get(c, c)} · {n}</span>'
        for c, n in sorted(r.get("source_class_coverage", {}).items()))

    # The first viewport: who this is about, what we think, and how it was
    # built. Nothing else.
    #
    # It used to carry a six-row label/value grid -- "What changed recently",
    # "Most important surprise", "Biggest opportunity", "Biggest
    # vulnerability" -- which was field serialization in the most prominent
    # place on the page AND a duplicate of the sections below it. A reader met
    # "Independent reporting describes retail moving toward AI shopping
    # agents" in the grid and then again, verbatim, under What happened.
    #
    # The decision the claim bears on is the one line worth surfacing here,
    # and it now reads as a sentence in the section below rather than as a
    # value beside a bold label.
    hero = (
        f'<div class="hero"><div class="badges">'
        f'<span class="status st-{_e(status)}">{_e(_STATUS_LABEL.get(status,status))}</span>'
        + (f'<span class="badge">Last researched: {_e(freshness)}</span>'
           if is_meaningful(freshness) else '')
        + f'{coverage_badges}</div>'
        f'<h1>{_e(r.get("company_name",""))} — Strategic Intelligence</h1>'
        f'<p class="thesis">{_e(_central_claim(r, thesis))}</p>'
        # "Outside-in analysis of approved public sources and a curated
        # historical-pattern library" describes the pipeline: "approved" is a
        # step in the run, and the pattern library is a component. What the
        # reader needs from this line is the boundary of what the product can
        # know, which is the second half and is worth saying plainly.
        + f'<p class="muted">Built only from public sources, each one listed '
        f'below. Nothing here comes from inside the company, and no part of '
        f'this is trained on it. Where the report describes what leadership '
        f'is likely weighing, that is inferred from what the company has '
        f'published — never from any private meeting.</p></div>')

    # ------------------------------------------------------------------
    # The report a reader actually reads.
    #
    # This page was fourteen sections of `<strong>Label:</strong> value`, one
    # per schema field -- "Exposed: X / Mechanism: Y / Why exposure may be
    # rising: Z" -- which is the record laid out sideways, not an argument.
    # The same conclusion appeared under several headings because several
    # fields happened to contain it.
    #
    # It is now eight sections in the order an analyst would argue in: what we
    # think, what happened, what we saw, why that supports the claim, what
    # else could explain it, what we still do not know, what to watch, and
    # where it all came from. Every section is prose, every section disappears
    # when it has nothing, and no sentence is printed twice anywhere on the
    # page (see `_once`).
    # ------------------------------------------------------------------
    seen: set = set()

    def _key(text: str) -> str:
        return " ".join((text or "").lower().split()).rstrip(".?!")

    def _first_key(text: str) -> str:
        return _key(re.split(r"(?<=[.?!])\s", (text or "").strip(), 1)[0])

    def _claim_seen(text: str) -> bool:
        """Has the page already made this point, in any wording?

        `_once` compares whole sentences, so "Does X? We ask because Y." and a
        bare "Does X?" were two different strings and both reached the page --
        the leadership questions and the hypotheses' falsification questions
        are frequently the same question. Comparing the first sentence catches
        that without needing the two lists to agree upstream.
        """
        return bool(_first_key(text)) and _first_key(text) in seen

    def _once(text: str) -> str:
        """A sentence the page has already used is not said again.

        The old page could state the same conclusion in the executive summary,
        the hypothesis card, the vulnerability card and the agenda, because
        four fields held it. Deduplicating at the point of writing is what
        makes each section carry something the last one did not.

        Keyed on the first sentence as well as the whole string, because a
        trailing clause was enough to defeat a whole-string key. On a live
        Airbnb report "What happened" and "Why that evidence matters" printed
        the identical sentence, differing only by the " (Recorded 2026-07-29.)"
        that the timeline appends. Whichever section writes it first keeps it,
        and the sections are written in reading order, so the dated statement
        of what happened wins over the undated restatement below it.
        """
        key, first = _key(text), _first_key(text)
        if not key or key in seen or (first and first in seen):
            return ""
        seen.add(key)
        seen.add(first)
        return text

    def _p(text, *, muted=False) -> str:
        text = _once(text) if is_meaningful(text) else ""
        cls = ' class="muted"' if muted else ""
        return f"<p{cls}>{_e(text)}</p>" if text else ""

    def _section(heading, body, anchor="") -> str:
        if not body:
            return ""
        attr = f' id="{anchor}"' if anchor else ""
        return f"<h2{attr}>{_e(heading)}</h2>{body}"

    def _sentences(items) -> str:
        return "".join(_p(x) for x in items)

    # 1 ── MAIN INTERPRETATION -----------------------------------------
    # The claim is already in the hero; this adds only what the hero could
    # not: how far to trust it, and the decision it bears on.
    lead = hyps[0] if hyps else {}
    interpretation = "".join([
        _p(thesis.get("transition", "")
           if not reads_as_taxonomy(thesis.get("transition", "")) else ""),
        _p(lead.get("statement", "")
           if not reads_as_taxonomy(lead.get("statement", "")) else ""),
        _p(f"This is held as a {lead['confidence']}-confidence reading of the "
           f"public evidence, not a settled fact."
           if lead.get("confidence") else ""),
        _p(f"It bears on one decision in particular: "
           f"{lower_first(thesis['why_care'])}"
           if is_meaningful(thesis.get("why_care")) else ""),
    ] + [
        # What leadership is likely weighing right now, inferred from public
        # signals only. Kept here rather than in its own section because it is
        # part of the interpretation, not a separate finding -- and said once.
        _p(f"On current evidence, leadership is likely weighing "
           f"{lower_first(a['inferred_discussion'])}"
           + (f" The decision in front of them: "
              f"{lower_first(a['likely_decision'])}"
              if is_meaningful(a.get("likely_decision")) else ""))
        for a in (r.get("agenda") or ())
        if is_meaningful(a.get("inferred_discussion"))
        and not reads_as_taxonomy(a.get("inferred_discussion", ""))
    ] + [
        _p("This is inferred from public signals, never from knowledge of any "
           "private meeting.", muted=True)
        if any(is_meaningful(a.get("inferred_discussion"))
               and not reads_as_taxonomy(a.get("inferred_discussion", ""))
               for a in (r.get("agenda") or ())) else "",
    ])

    # 2 ── WHAT HAPPENED ------------------------------------------------
    happened_items = []
    for shift in meaningful_items(r.get("shifts", []), key="title"):
        if reads_as_taxonomy(shift.get("title", "")):
            continue
        when = shift.get("date", "")
        happened_items.append(
            f"{shift['title'].rstrip('.')}."
            + (f" (Recorded {when}.)" if is_meaningful(when) else ""))
    for event in meaningful_items(timeline, key="event"):
        if reads_as_taxonomy(event.get("event", "")):
            continue
        happened_items.append(
            f"{event['event'].rstrip('.')}."
            + (f" (Recorded {event['date']}.)"
               if is_meaningful(event.get("date")) else ""))
    for change in r.get("what_changed", []) or ():
        if is_meaningful(change.get("new_view")):
            happened_items.append(
                f"Our reading of {change.get('component','').replace('_',' ')} "
                f"changed: {lower_first(change['new_view'])}"
                + (f" Previously: {lower_first(change['previous_view'])}"
                   if is_meaningful(change.get("previous_view")) else ""))
    # A surprise IS something that happened -- the finding belongs with the
    # other developments, and only its explanation belongs further down.
    for s in meaningful_items(r.get("surprises", []), key="finding"):
        if not reads_as_taxonomy(s.get("finding", "")):
            happened_items.append(s["finding"])
    happened = _sentences(happened_items)

    # 3 ── EVIDENCE -----------------------------------------------------
    # Quoted and attributed. This is the one place a page excerpt belongs:
    # as a quotation the reader can check, never as the analysis itself.
    # Evidence that CUTS AGAINST the claim is marked as such and shown beside
    # the evidence that supports it. A report that shows only what agrees with
    # it is advocacy, and the reader cannot tell which they are looking at
    # unless the page says so.
    counter_ids = {i for h in hyps
                   for i in (h.get("counter_observation_ids") or [])}
    evidence_rows, counter_rows = [], []
    for o in r.get("observations", []) or ():
        quote = (o.get("excerpt") or "").strip()
        if not is_meaningful(quote):
            continue
        if " ".join(quote.lower().split()) in seen:
            continue
        meta = " · ".join(x for x in [
            o.get("source_title", ""),
            _CLASS_LABEL.get(o.get("source_class", ""),
                             o.get("source_class", "")),
            o.get("date", "")] if x)
        against = o.get("observation_id") in counter_ids
        row = (f'<div class="ev {"con" if against else "sup"}">'
               f'<div>“{_e(quote)}”</div>'
               f'<div class="meta">{_e(meta)}</div></div>')
        # Separate budgets. A single shared cap filled with supporting quotes
        # first and pushed the contradicting evidence off the page entirely --
        # which is precisely the evidence a sceptical reader came for.
        if against:
            if len(counter_rows) < 3:
                counter_rows.append(row)
        elif len(evidence_rows) < 6:
            evidence_rows.append(row)
    evidence = ""
    if evidence_rows:
        evidence += ('<p class="muted">What supports the reading:</p>'
                     + "".join(evidence_rows))
    if counter_rows:
        evidence += ('<p class="muted">What cuts against it:</p>'
                     + "".join(counter_rows))
    if evidence and coverage_badges:
        evidence += (f'<p class="muted">Read across: '
                     f'{_e(", ".join(f"{n} {_CLASS_LABEL.get(c, c).lower()}" for c, n in sorted(r.get("source_class_coverage", {}).items()) if n))}.</p>')

    # 4 ── WHY THE EVIDENCE MATTERS -------------------------------------
    # The mechanism, not the restatement. Each observation now carries its
    # own consequence clause (see observations._SIGNAL_RELEVANCE), and the
    # hypothesis reasoning is used only when it is about the company rather
    # than about the pattern library matching itself.
    why_items = []
    for o in r.get("observations", []) or ():
        text = (o.get("text") or "").strip()
        if is_meaningful(text) and not reads_as_taxonomy(text):
            why_items.append(text)
    for h in hyps:
        reasoning = (h.get("reasoning") or "").strip()
        if is_meaningful(reasoning) and not reads_as_taxonomy(reasoning):
            why_items.append(reasoning)
    for v in meaningful_items(r.get("vulnerabilities", []),
                              key="exposed_layer"):
        mechanism = (v.get("mechanism") or "").strip()
        if is_meaningful(mechanism) and not reads_as_taxonomy(mechanism):
            why_items.append(
                f"{mechanism.rstrip('.')}, which is why "
                f"{lower_first(v.get('exposed_layer', 'this layer'))} is the "
                f"exposed part.")
    for o in meaningful_items(r.get("opportunities", []), key="statement"):
        if is_meaningful(o.get("why_now")) and not reads_as_taxonomy(
                o.get("statement", "")):
            why_items.append(f"{o['statement'].rstrip('.')} — "
                             f"{lower_first(o['why_now'])}")
    # A blind spot is a tension the evidence shows and the company may not be
    # pricing in. Dropping it lost a real finding; it belongs with the rest of
    # the reasoning, stated as one sentence rather than a four-field card.
    for b in meaningful_items(r.get("blind_spots", []),
                              key="observed_tension"):
        tension = (b.get("observed_tension") or "").strip()
        if not is_meaningful(tension) or reads_as_taxonomy(tension):
            continue
        why_items.append(
            f"{tension.rstrip('.')}"
            + (f", which matters because {lower_first(b['why_it_may_matter'])}"
               if is_meaningful(b.get("why_it_may_matter")) else "."))
    for s in meaningful_items(r.get("surprises", []), key="finding"):
        if is_meaningful(s.get("why_surprising")):
            why_items.append(s["why_surprising"])
    why = _sentences(why_items[:10])

    # The historical analogue, as a sentence rather than a labelled chip.
    # This is real comparative analysis and was worth keeping -- but only
    # when the library entry is named in language about companies rather than
    # about itself, which is the same gate `_pattern_block` applied.
    for h in hyps:
        pattern = pat_by_id.get(h.get("pattern_id", ""), {})
        if not pattern or reads_as_taxonomy(pattern.get("name", "")) \
                or reads_as_taxonomy(pattern.get("mechanism", "")):
            continue
        examples = [e.get("name", "") for e in
                    pattern.get("historical_examples", []) if e.get("name")]
        why += _p(
            f"This resembles a pattern seen before — {pattern['name']}: "
            f"{lower_first(pattern.get('mechanism', ''))}"
            + (f" It has played out at {', '.join(examples[:3])}."
               if examples else "")
            + (f" Where the comparison breaks down: "
               f"{lower_first(pattern['when_it_does_not_apply'])}"
               if is_meaningful(pattern.get("when_it_does_not_apply")) else ""))
        break              # one analogue, not one per hypothesis

    # 5 ── ALTERNATIVE EXPLANATIONS -------------------------------------
    # A report that argues one way and never the other is advocacy.
    alt_items = []
    for s in meaningful_items(r.get("surprises", []), key="finding"):
        if is_meaningful(s.get("alternative_explanation")):
            alt_items.append(s["alternative_explanation"])
    for v in meaningful_items(r.get("vulnerabilities", []),
                              key="exposed_layer"):
        if is_meaningful(v.get("counterpoint")):
            alt_items.append(v["counterpoint"])
    for b in meaningful_items(r.get("blind_spots", []),
                              key="observed_tension"):
        if is_meaningful(b.get("counter_explanation")):
            alt_items.append(b["counter_explanation"])
    for h in hyps:
        for a in h.get("alternative_explanations", []) or ():
            if is_meaningful(a) and not reads_as_taxonomy(a):
                alt_items.append(a)
    alternatives = _sentences(alt_items[:6])

    # 6 ── REMAINING UNCERTAINTY ----------------------------------------
    uncertainty_items = list(consolidate_limitations(
        r.get("evidence_gaps", []),
        reader_limitations(r.get("quality_findings", []))))
    for q in meaningful_items(r.get("underexamined_questions", []),
                              key="question"):
        if not reads_as_taxonomy(q.get("question", "")):
            uncertainty_items.append(
                f"{q['question'].rstrip('?')}? "
                f"{q.get('why_underexamined', '')}".strip())
    for h in hyps:
        for gap in h.get("evidence_gaps", []) or ():
            if is_meaningful(gap) and not reads_as_taxonomy(gap):
                uncertainty_items.append(gap)
    uncertainty = _sentences(uncertainty_items[:8])

    # 7 ── WHAT TO MONITOR ----------------------------------------------
    # Observable things, phrased as things to look for. A falsification
    # question written in the pattern library's vocabulary is not
    # observable by a reader and is dropped at this selection point too.
    monitor_items = []
    for v in meaningful_items(r.get("vulnerabilities", []),
                              key="exposed_layer"):
        indicator = (v.get("leading_indicator") or "").strip()
        if is_meaningful(indicator) and not reads_as_taxonomy(indicator):
            monitor_items.append(indicator.rstrip(".") + ".")
    for q in meaningful_items(r.get("questions", []), key="question"):
        if not reads_as_taxonomy(q.get("question", "")):
            # A question without its reason is a prompt, not a brief. The
            # old card carried "Why we ask:" beneath it; the reason belongs
            # in the same sentence rather than under a label.
            reason = strip_machinery(q.get("why_it_matters", ""))
            monitor_items.append(
                q["question"]
                + (f" We ask because {lower_first(reason)}"
                   if is_meaningful(reason) else ""))
    for a in r.get("agenda", []) or ():
        confirm = (a.get("what_would_confirm") or "").strip()
        if is_meaningful(confirm) and not reads_as_taxonomy(confirm):
            monitor_items.append(confirm)
    # What would settle a surprise, and what would change our mind about a
    # hypothesis, are both things to watch for rather than things we know.
    for s in meaningful_items(r.get("surprises", []), key="finding"):
        if is_meaningful(s.get("what_would_resolve")):
            monitor_items.append(s["what_would_resolve"])
    for h in hyps:
        for question in h.get("falsification_questions", []) or ():
            if is_meaningful(question) and not reads_as_taxonomy(question):
                monitor_items.append(question)
    monitor = _sentences(monitor_items[:8])

    # 8 ── SOURCES -------------------------------------------------------
    lib = r.get("source_library", {})
    lib_titles = {"used_in_reasoning": "Used in reasoning",
                  "corroborating": "Independent corroboration",
                  "contradicting": "Contradicting",
                  "contextual": "Contextual",
                  "rejected_low_relevance": "Rejected — low relevance/weak"}
    lib_html = ""
    for key, title in lib_titles.items():
        rows = lib.get(key, [])
        if not rows:
            continue
        trs = "".join(
            f'<tr><td>{_e(s.get("title",""))}</td>'
            f'<td>{_CLASS_LABEL.get(s.get("source_class",""), s.get("source_class",""))}</td>'
            f'<td>{_e(s.get("date",""))}</td>'
            f'<td>{_e(s.get("evidence_quality",""))}</td></tr>'
            for s in rows)
        # h3, not h4: these sit directly under the "Sources" h2, so an h4 was
        # a skipped level -- a screen reader announces a heading that has no
        # parent. The h4s inside a hypothesis block are correct because each
        # block is titled with its own h3.
        lib_html += (f'<h3>{title} ({len(rows)})</h3><table class="lib">'
                     f'<tr><th>Source</th><th>Class</th><th>Date</th>'
                     f'<th>Quality</th></tr>{trs}</table>')
    # No quality-gate block here. `consolidate_limitations` already folds
    # every quality finding into "What we still do not know", so repeating the
    # list under Sources printed "No independent corroboration" twice on one
    # page -- the same caveat read as two separate problems.
    sources = ""
    if lib_html:
        sources += (f'<details class="more" id="library"><summary>Every source '
                    f'considered, and how each was used</summary>{lib_html}'
                    f'</details>')

    return (
        f'{_CSS}<section class="si" aria-label="Strategic Intelligence Report">'
        f'{hero}'
        + _section("What we think is happening", interpretation,
                   "interpretation")
        + _section("What happened", happened, "changed")
        + _section("The evidence", evidence, "evidence")
        + _section("Why that evidence matters", why, "hypotheses")
        + _section("What else could explain it", alternatives, "alternatives")
        + _section("What we still do not know", uncertainty, "uncertainty")
        + _section("What to monitor", monitor, "monitor")
        + _section("Sources", sources, "sources")
        + f'</section>')
