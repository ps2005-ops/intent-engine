"""V1.2 executive-first strategic report rendering.

A polished, progressively-disclosed executive intelligence view — not an
evidence dump. The first viewport carries the thesis, the most important
change, the key tension, the decision most affected, and confidence. Below it:
a tight executive summary, collapsed hypothesis cards that expand to the full
reasoning, a strongest-evidence-first drawer, a current-agenda section
(explicitly inferred from public signals), a chronological timeline, and a full
source library for auditability. Human-readable reasoning is always primary;
technical ids and signal traces live in a secondary appendix.
"""
from __future__ import annotations

import html as _html

from intent_engine.strategic_intelligence.editorial import (
    consolidate_limitations, deduplicate, is_meaningful, meaningful_items,
    shared_evidence,
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
.si .prov{color:#94a3b8;font-size:.74rem}
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
.si .chip,.si table.lib{background:#0f141c}.si .badge{background:#1c2530;color:#c7d2e0;border-color:#2c3644}}
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


def _pattern_block(pat):
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
        f'<p class="thesis" style="font-size:1rem">{_e(h["statement"])}</p>'
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
        f'<div><p><strong>Reasoning.</strong> {_e(h.get("reasoning",""))}</p>'
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

    top_change = (r.get("shifts") or [{}])[0].get("title", "")
    top_surprise = (r.get("surprises") or [{}])[0].get("finding", "")
    top_opp = (r.get("opportunities") or [{}])[0].get("statement", "")
    top_vuln = (r.get("vulnerabilities") or [{}])[0].get("exposed_layer", "")
    top_agenda = (r.get("agenda") or [{}])[0]
    agenda_line = top_agenda.get("inferred_discussion", "")
    if agenda_line and top_agenda.get("meeting_relevance"):
        agenda_line = (f'{agenda_line} <span class="badge">'
                       f'{_e(top_agenda["meeting_relevance"])}</span>')

    # The summary grid carries only the rows that have something in them. A row
    # reading "Biggest opportunity: —" costs the reader attention and returns
    # nothing, and a reader cannot tell an intentional dash from a bug.
    kv_rows = "".join(
        f'<b>{label}</b><span>{value if raw_html else _e(value)}</span>'
        for label, value, raw_html in (
            ("What changed recently", top_change, False),
            ("Most important surprise", top_surprise, False),
            ("Likely current discussion", agenda_line, True),
            ("Biggest opportunity", top_opp, False),
            ("Biggest vulnerability", top_vuln, False),
            ("Decision most affected", thesis.get("why_care", ""), False),
        ) if is_meaningful(value))

    # first viewport / hero — decisions & changes first
    hero = (
        f'<div class="hero"><div class="badges">'
        f'<span class="status st-{_e(status)}">{_e(_STATUS_LABEL.get(status,status))}</span>'
        + (f'<span class="badge">Last researched: {_e(freshness)}</span>'
           if is_meaningful(freshness) else '')
        + f'{coverage_badges}</div>'
        f'<h1>{_e(r.get("company_name",""))} — Strategic Intelligence</h1>'
        f'<p class="thesis">{_e(thesis.get("view",""))}</p>'
        + (f'<div class="kv">{kv_rows}</div>' if kv_rows else '')
        # Jump links only to sections that exist. Suppressing an empty section
        # while keeping its link would leave a control that silently does
        # nothing, which is a worse failure than the empty section was.
        + '<div class="actions">' + "".join(
            f'<a{"" if primary else " class=ghost"} href="#{anchor}">'
            f'{label}</a>'
            for anchor, label, present, primary in (
                ("hypotheses", "Explore reasoning", bool(hyps), True),
                ("agenda", "Current agenda", bool(r.get("agenda")), False),
                ("changed", "What changed", bool(r.get("what_changed")),
                 False),
                ("model", "Mental model",
                 bool((r.get("mental_model") or {}).get("components")), False),
                ("library", "Source library",
                 any(r.get("source_library", {}).values()), False),
            ) if present) + '</div>'
        + f'<p class="muted">Outside-in analysis of approved public sources and a '
        f'curated historical-pattern library. No private or internal knowledge '
        f'is claimed, and no model is trained on this company; likely-agenda '
        f'items are inferred from public signals, never from private '
        f'meetings.</p></div>')

    # executive summary (caps of 3)
    def _cap(items, n=3):
        return items[:n]
    top_h = "".join(
        f'<li><strong>{_e(h["title"])}</strong> '
        f'<span class="conf conf-{_e(h["confidence"])}">{_e(h["confidence"])}</span></li>'
        for h in _cap(hyps))
    top_agenda = "".join(f'<li>{_e(a["inferred_discussion"])}</li>'
                         for a in _cap(r.get("agenda", [])))
    top_dec = "".join(f'<li>{_e(d["decision"])}</li>'
                      for d in _cap(r.get("decision_implications", [])))
    # The summary preview shows the same caveats the limitations section
    # details, which is progressive disclosure — but it must not list the same
    # caveat twice within itself.
    top_unc = "".join(f'<li>{_e(g)}</li>' for g in
                      _cap(deduplicate(meaningful_items(
                          r.get("evidence_gaps", [])))))
    # An empty chip is a heading promising something that never arrives. Chips
    # with nothing in them are dropped, and if none survive the whole summary
    # goes with them rather than leaving a bare "Executive summary" heading.
    chips = "".join(
        f'<div class="chip"><b>{label}</b><ul>{items}</ul></div>'
        for label, items in (
            ("Key hypotheses", top_h),
            ("Likely leadership discussions", top_agenda),
            ("Decisions affected", top_dec),
            ("Major uncertainties", top_unc),
        ) if items)
    summary = (f'<h2>Executive summary</h2><div class="row">{chips}</div>'
               if chips else '')

    # hypotheses. Evidence cited under EVERY hypothesis is printed under the
    # first one and linked from the rest: a reader scrolling four cards saw
    # the identical six-source block four times and learned nothing after the
    # first. Volume of text and volume of insight had come apart.
    repeated = shared_evidence([h.get("strongest_support_ids", [])
                                for h in hyps])
    ubiquitous = {e for e, n in repeated.items() if n >= max(2, len(hyps))}
    hyp_html = ""
    for position, hypothesis in enumerate(hyps):
        card = dict(hypothesis)
        if position > 0 and ubiquitous:
            # Both id lists, not just the "strongest" one — the card renders
            # the full supporting set as well, so filtering one path left the
            # excerpt on the page anyway.
            for field in ("strongest_support_ids",
                          "supporting_observation_ids"):
                card[field] = [e for e in hypothesis.get(field, [])
                               if e not in ubiquitous]
            card["shared_evidence_note"] = (
                "Rests on the same evidence shown under the leading "
                "hypothesis, plus anything listed here.")
        hyp_html += _hypothesis_card(card, obs_by_id, pat_by_id)

    # current agenda
    agenda_cards = ""
    for a in r.get("agenda", []):
        sig = "".join(f"<li>{_e(s)}</li>" for s in a.get("public_signals", []))
        against = "".join(f"<li>{_e(s)}</li>" for s in a.get("evidence_against", []))
        agenda_cards += (
            f'<div class="agenda"><h3>{_e(a["inferred_discussion"])} '
            f'<span class="conf conf-{_e(a["confidence"])}">{_e(a["confidence"])}</span></h3>'
            f'<p class="muted"><strong>Why likely timely:</strong> {_e(a["why_timely"])}</p>'
            f'<div class="row"><div class="chip"><b>Public signals</b><ul>{sig}</ul></div>'
            f'<div class="chip"><b>Evidence against</b><ul>{against}</ul></div></div>'
            f'<p><strong>Affected functions:</strong> '
            f'{_e(", ".join(a.get("affected_functions", [])))}</p>'
            f'<p><strong>Likely decision:</strong> {_e(a["likely_decision"])}</p>'
            f'<p class="muted"><strong>What would confirm:</strong> '
            f'{_e(a["what_would_confirm"])}</p></div>')
    agenda_section = (
        f'<h2 id="agenda">Likely current leadership agenda</h2>'
        f'<p class="muted">Inferred from recent public signals — NOT knowledge '
        f'of any private meeting.</p>{agenda_cards or "<p class=muted>Not enough dated evidence to infer an agenda.</p>"}')

    # timeline
    tl = "".join(
        f'<li><span class="d">{_e(t["date"])}</span>'
        f'<span class="badge">{_CLASS_LABEL.get(t["source_class"], t["source_class"])}</span> '
        f'{_e(t["event"])}</li>' for t in timeline)
    timeline_section = (f'<h2 id="timeline">Strategic timeline</h2>'
                        f'<ul class="tl">{tl or "<li class=muted>No dated evidence.</li>"}</ul>')

    # blind spots — deduplicated, and absent entirely when there are none
    blinds = "".join(
        f'<div class="card"><h3>{_e(b["observed_tension"])}</h3>'
        f'<p><strong>Why it may matter:</strong> {_e(b["why_it_may_matter"])}</p>'
        f'<p class="muted"><strong>Counter-explanation:</strong> {_e(b["counter_explanation"])}</p>'
        f'<p><strong>Decision affected:</strong> {_e(b["decision_affected"])}</p></div>'
        for b in deduplicate(meaningful_items(r.get("blind_spots", []),
                                              key="observed_tension"),
                             key="observed_tension"))

    # leadership questions
    questions = "".join(
        f'<div class="card"><h3>{_e(q["question"])}</h3>'
        f'<p class="muted"><strong>Why we ask:</strong> {_e(q["why_it_matters"])}</p>'
        f'<p><strong>Decision affected:</strong> {_e(q["decision_affected"])}</p></div>'
        for q in deduplicate(meaningful_items(r.get("questions", []),
                                              key="question"),
                             key="question"))

    # source library
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
            f'<td>{_e(s.get("date",""))}</td><td>{_e(s.get("evidence_quality",""))}</td>'
            f'<td>{_e(", ".join(s.get("affected_hypotheses", [])))}</td></tr>'
            for s in rows)
        lib_html += (f'<h4>{title} ({len(rows)})</h4><table class="lib">'
                     f'<tr><th>Source</th><th>Class</th><th>Date</th>'
                     f'<th>Quality</th><th>Affected hypotheses</th></tr>{trs}</table>')
    library_section = (f'<details class="more" id="library"><summary>Source '
                       f'library — all considered sources</summary>{lib_html}'
                       f'</details>')

    # technical appendix (signal traces, quality gate)
    traces = "".join(f'<li><code>{_e(h["hypothesis_id"])}</code>: '
                     f'{_e(h.get("signal_trace",""))}</li>' for h in hyps)
    findings = "".join(f'<li>{_e(f["message"])}</li>'
                       for f in r.get("quality_findings", [])) or "<li>All gates passed.</li>"
    appendix = (f'<details class="more"><summary>Technical appendix — signal '
                f'traces &amp; quality gate</summary><ul>{traces}</ul>'
                f'<h4>Quality gate</h4><ul>{findings}</ul></details>')

    # strategic surprises
    surprises_html = "".join(
        f'<div class="card"><h3>{_e(s["finding"])} '
        f'<span class="badge">{_e(s.get("meeting_relevance",""))}</span></h3>'
        f'<p class="muted"><strong>Why it is surprising:</strong> '
        f'{_e(s["why_surprising"])}</p>'
        f'<div class="row"><div class="chip"><b>On one side</b>'
        + "".join(f'<div class="ev sup">“{_e(x["excerpt"])}” '
                  f'<span class="meta">{_e(x["source_title"])}</span></div>'
                  for x in s["evidence_side_a"]) + '</div>'
        f'<div class="chip"><b>On the other</b>'
        + "".join(f'<div class="ev con">“{_e(x["excerpt"])}” '
                  f'<span class="meta">{_e(x["source_title"])}</span></div>'
                  for x in s["evidence_side_b"]) + '</div></div>'
        f'<p><strong>What argues the other way:</strong> '
        f'{_e(s["alternative_explanation"])}</p>'
        f'<p><strong>Decision this affects:</strong> {_e(s["decision_affected"])}</p>'
        f'<p class="muted"><strong>What would resolve it:</strong> '
        f'{_e(s["what_would_resolve"])}</p></div>'
        for s in deduplicate(meaningful_items(r.get("surprises", []),
                                             key="finding"), key="finding"))

    # opportunities
    opp_html = "".join(
        f'<div class="card"><h3>{_e(o["statement"])}</h3>'
        f'<p><strong>Why now:</strong> {_e(o["why_now"])}</p>'
        f'<p><strong>The asymmetry:</strong> {_e(o["asymmetry"])}</p>'
        f'<p class="muted"><strong>Downside:</strong> {_e(o["downside"])} · '
        f'<strong>Difficulty:</strong> {_e(o["execution_difficulty"])}</p>'
        f'<p><strong>Decision this affects:</strong> {_e(o["decision_required"])}</p>'
        f'</div>' for o in deduplicate(
            meaningful_items(r.get("opportunities", []), key="statement"),
            key="statement"))

    # vulnerabilities
    vuln_html = "".join(
        f'<div class="card"><h3>Exposed: {_e(v["exposed_layer"])}</h3>'
        f'<p><strong>Mechanism:</strong> {_e(v["mechanism"])}</p>'
        f'<p class="muted"><strong>Why exposure may be rising:</strong> '
        f'{_e(v["why_increasing"])} ({_e(v["market_force"])})</p>'
        f'<p><strong>What argues against this:</strong> {_e(v["counterpoint"])}</p>'
        f'<p><strong>Watch:</strong> {_e(v["leading_indicator"])} · '
        f'<strong>Decision:</strong> {_e(v["decision_affected"])}</p></div>'
        for v in deduplicate(
            meaningful_items(r.get("vulnerabilities", []),
                             key="exposed_layer"), key="exposed_layer"))

    # underexamined questions
    uq_html = "".join(
        f'<div class="card"><h3>{_e(q["question"])}</h3>'
        f'<p class="muted"><strong>Why it may be underexamined:</strong> '
        f'{_e(q["why_underexamined"])}</p>'
        f'<p><strong>What answers would imply:</strong> {_e(q["what_answers_imply"])}</p>'
        f'<p><strong>Decision this affects:</strong> {_e(q["decision_affected"])}</p>'
        f'</div>' for q in deduplicate(
            meaningful_items(r.get("underexamined_questions", []),
                             key="question"), key="question"))

    # mental model panels
    mm = r.get("mental_model", {})
    panels = "".join(
        f'<div class="chip"><b>{_e(name.replace("_"," ").title())} '
        f'· {_e(c.get("confidence",""))}</b>{_e(c.get("current_state",""))}'
        + (f'<p class="muted">Was: {_e(c["prior_state"])}</p>'
           if c.get("prior_state") else "") + '</div>'
        for name, c in mm.get("components", {}).items())
    model_section = (f'<h2 id="model">Company mental model '
                     f'(v{mm.get("version",1)})</h2>'
                     f'<p class="muted">A living outside-in model — updated by '
                     f'new evidence, not rebuilt from zero.</p>'
                     f'<div class="row">{panels}</div>') if panels else ''

    # what changed our view
    changed = r.get("what_changed", [])
    changed_html = "".join(
        f'<div class="card"><h3>{_e(ch["component"].replace("_"," ").title())} '
        f'— {_e(ch["kind"])}</h3>'
        + (f'<p><strong>Previous view:</strong> {_e(ch["previous_view"])}</p>'
           if ch.get("previous_view") else "")
        + f'<p><strong>New view:</strong> {_e(ch["new_view"])}</p>'
        f'<p class="muted"><strong>Confidence:</strong> '
        f'{_e(ch["old_confidence"] or "—")} → {_e(ch["new_confidence"] or "—")} · '
        f'{_e(ch["reason"])}</p></div>' for ch in changed)
    changed_section = (
        f'<h2 id="changed">What changed our view?</h2>'
        + (changed_html if changed else
           '<p class="muted">First analysis of this company — no prior model '
           'to compare yet. Future evidence will update this.</p>'))

    # intelligence feed
    feed = r.get("feed", [])
    feed_html = "".join(
        f'<li><span class="d">{_e(f["date"])}</span> {_e(f["model_change"])} '
        f'<span class="badge">{_e(f["confidence_change"])}</span></li>'
        for f in feed)
    feed_section = (f'<h2 id="feed">Intelligence feed</h2>'
                    + (f'<ul class="tl">{feed_html}</ul>' if feed else
                       '<p class="muted">Updates will appear here as new '
                       'evidence changes the model.</p>'))

    # A heading is a promise that something follows. Sections with nothing in
    # them are not rendered at all — not as a heading with a dash under it,
    # which costs the reader attention and returns nothing, and which they
    # cannot distinguish from a rendering bug.
    def _titled(heading, content, anchor=""):
        if not content:
            return ''
        attr = f' id="{anchor}"' if anchor else ''
        return f'<h2{attr}>{heading}</h2>{content}'

    # Every caveat in one place. The same limitation restated under six
    # headings reads as six separate problems.
    limitations = consolidate_limitations(r.get("evidence_gaps", []),
                                          [f.get("message") for f in
                                           r.get("quality_findings", [])])
    limitations_section = _titled(
        "What this analysis cannot tell you",
        ("<ul>" + "".join(f'<li>{_e(x)}</li>' for x in limitations) + "</ul>")
        if limitations else '')

    return (
        f'{_CSS}<section class="si" aria-label="Strategic Intelligence Report">'
        f'{hero}{summary}'
        + _titled("Strategic surprises", surprises_html, "surprises")
        + _titled("Strategic hypotheses", hyp_html, "hypotheses")
        + _titled("Strategic opportunities", opp_html, "opportunities")
        + _titled("Where the company is exposed", vuln_html,
                  "vulnerabilities")
        + _titled("Questions that may be underexamined", uq_html)
        + _titled("Possible blind spots", blinds)
        + f'{model_section}{changed_section}{agenda_section}{feed_section}'
        f'{timeline_section}'
        + _titled("Questions for leadership", questions)
        + limitations_section
        + f'<h2>Source library &amp; provenance</h2>{library_section}{appendix}'
        f'</section>')
