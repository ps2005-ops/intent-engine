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

    strongest_sup = _obs_ev(sup[0], "sup") if sup else "<p class='muted'>—</p>"
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
        f'<div class="row"><div class="chip"><b>Why now</b>{_e(h.get("why_now","") or "—")}</div>'
        f'<div class="chip"><b>Decision affected</b>'
        f'{_e((h.get("decision_implications") or [""])[0])}</div></div>'
        f'<div class="row"><div class="chip"><b>Strongest support</b>{strongest_sup}</div>'
        f'<div class="chip"><b>Strongest counterpoint</b>{strongest_con}</div></div>'
        f'<p class="muted">▸ Expand for full reasoning, comparison, and all evidence.</p>'
        f'</summary>'
        f'<div><p><strong>Reasoning.</strong> {_e(h.get("reasoning",""))}</p>'
        f'<h4>Alternative explanations</h4><ul>{alts}</ul>'
        f'<h4>Comparison</h4>{_pattern_block(pat) if pat else ""}'
        f'<h4>Confidence: {_e(conf)}</h4><ul>{reasons}</ul>'
        f'<h4>What would change this view</h4><ul>{fals}</ul>'
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

    top_change = (r.get("shifts") or [{}])[0].get("title", "—")

    # first viewport / hero
    hero = (
        f'<div class="hero"><div class="badges">'
        f'<span class="status st-{_e(status)}">{_e(_STATUS_LABEL.get(status,status))}</span>'
        f'<span class="badge">Freshness: {_e(freshness)}</span>{coverage_badges}</div>'
        f'<h1>{_e(r.get("company_name",""))} — Strategic Intelligence</h1>'
        f'<p class="thesis">{_e(thesis.get("view",""))}</p>'
        f'<div class="kv">'
        f'<b>Most important change</b><span>{_e(top_change)}</span>'
        f'<b>Most important tension</b><span>{_e(thesis.get("tension",""))}</span>'
        f'<b>Decision most affected</b><span>{_e(thesis.get("why_care",""))}</span>'
        f'<b>Transition underway</b><span>{_e(thesis.get("transition",""))}</span>'
        f'</div>'
        f'<div class="actions"><a href="#hypotheses">Explore reasoning</a>'
        f'<a class="ghost" href="#agenda">Current agenda</a>'
        f'<a class="ghost" href="#timeline">Timeline</a>'
        f'<a class="ghost" href="#library">Source library</a></div>'
        f'<p class="muted">Outside-in analysis of approved public sources and a '
        f'curated historical-pattern library. No private or internal knowledge '
        f'is claimed; no model is trained on this company.</p></div>')

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
    top_unc = "".join(f'<li>{_e(g)}</li>' for g in _cap(r.get("evidence_gaps", [])))
    summary = (
        f'<h2>Executive summary</h2><div class="row">'
        f'<div class="chip"><b>Key hypotheses</b><ul>{top_h}</ul></div>'
        f'<div class="chip"><b>Likely leadership discussions</b><ul>{top_agenda or "<li>—</li>"}</ul></div>'
        f'<div class="chip"><b>Decisions affected</b><ul>{top_dec or "<li>—</li>"}</ul></div>'
        f'<div class="chip"><b>Major uncertainties</b><ul>{top_unc or "<li>—</li>"}</ul></div>'
        f'</div>')

    # hypotheses
    hyp_html = "".join(_hypothesis_card(h, obs_by_id, pat_by_id) for h in hyps)

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

    # blind spots
    blinds = "".join(
        f'<div class="card"><h3>{_e(b["observed_tension"])}</h3>'
        f'<p><strong>Why it may matter:</strong> {_e(b["why_it_may_matter"])}</p>'
        f'<p class="muted"><strong>Counter-explanation:</strong> {_e(b["counter_explanation"])}</p>'
        f'<p><strong>Decision affected:</strong> {_e(b["decision_affected"])}</p></div>'
        for b in r.get("blind_spots", [])) or "<p class='muted'>—</p>"

    # leadership questions
    questions = "".join(
        f'<div class="card"><h3>{_e(q["question"])}</h3>'
        f'<p class="muted"><strong>Why we ask:</strong> {_e(q["why_it_matters"])}</p>'
        f'<p><strong>Decision affected:</strong> {_e(q["decision_affected"])}</p></div>'
        for q in r.get("questions", [])) or "<p class='muted'>—</p>"

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
                       f'library — all considered sources</summary>{lib_html or "<p class=muted>—</p>"}'
                       f'</details>')

    # technical appendix (signal traces, quality gate)
    traces = "".join(f'<li><code>{_e(h["hypothesis_id"])}</code>: '
                     f'{_e(h.get("signal_trace",""))}</li>' for h in hyps)
    findings = "".join(f'<li>{_e(f["message"])}</li>'
                       for f in r.get("quality_findings", [])) or "<li>All gates passed.</li>"
    appendix = (f'<details class="more"><summary>Technical appendix — signal '
                f'traces &amp; quality gate</summary><ul>{traces}</ul>'
                f'<h4>Quality gate</h4><ul>{findings}</ul></details>')

    return (
        f'{_CSS}<section class="si" aria-label="Strategic Intelligence Report">'
        f'{hero}{summary}'
        f'<h2 id="hypotheses">Strategic hypotheses</h2>{hyp_html}'
        f'<h2>Possible blind spots</h2>{blinds}'
        f'{agenda_section}{timeline_section}'
        f'<h2>Questions for leadership</h2>{questions}'
        f'<h2>Source library &amp; provenance</h2>{library_section}{appendix}'
        f'</section>')
