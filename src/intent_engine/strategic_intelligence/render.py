"""V1.2 strategic report rendering.

Human-readable reasoning is always primary; technical artifact/replay IDs live
in a secondary provenance disclosure. "Show evidence" explains *why a
conclusion is believed* — observed evidence, interpretation, the reasoning
connection, counter-evidence, the comparable historical pattern, and calibrated
confidence — not a list of identifiers.
"""
from __future__ import annotations

import html as _html

_e = _html.escape

_STATUS_LABEL = {
    "COMPLETE": "Complete strategic view",
    "PARTIAL_STRATEGIC_EVIDENCE": "Partial — limited source diversity",
    "INSUFFICIENT_STRATEGIC_EVIDENCE": "Insufficient strategic evidence",
    "FAILED": "Could not form a strategic view",
}

_CLASS_LABEL = {
    "company_owned": "Company-owned", "executive_statement": "Executive",
    "investor_material": "Investor material", "customer_voice": "Customer voice",
    "competitor": "Competitor", "independent_reporting": "Independent reporting",
    "historical_pattern": "Historical pattern",
    "unavailable_or_failed": "Unavailable/failed",
}


def _as_dict(report):
    return report.as_dict() if hasattr(report, "as_dict") else report


def _obs_line(o: dict) -> str:
    bits = [f'<strong>{_e(o.get("source_title") or o.get("origin", ""))}</strong>']
    cls = _CLASS_LABEL.get(o.get("source_class", ""), o.get("source_class", ""))
    bits.append(f'<em>{_e(cls)}</em>')
    if o.get("date"):
        bits.append(_e(o["date"]))
    bits.append(f'freshness {_e(o.get("freshness", ""))}')
    origin = o.get("origin", "")
    meta = " · ".join(bits)
    excerpt = _e(o.get("excerpt") or o.get("text", ""))
    prov = "".join(
        f'<li><code>{_e(r.get("artifact_type", ""))}:'
        f'{_e(r.get("artifact_id", ""))}</code>'
        f'{" · replay " + _e(r.get("replay_id", "")) if r.get("replay_id") else ""}'
        f'{" · " + _e(r.get("subsystem", "")) if r.get("subsystem") else ""}</li>'
        for r in o.get("source_refs", []))
    return (f'<div class="evidence-item"><p class="evidence-quote">'
            f'“{excerpt}”</p><p class="evidence-meta">{meta}'
            f'{" · " + _e(origin) if origin else ""}</p>'
            f'<details class="provenance"><summary>Provenance IDs</summary>'
            f'<ul>{prov or "<li>—</li>"}</ul></details></div>')


def _pattern_block(pat: dict) -> str:
    ex = "".join(
        f'<li>{_e(e.get("name", ""))} — {_e(e.get("note", ""))} '
        f'<code>{_e(e.get("source", ""))}</code></li>'
        for e in pat.get("historical_examples", []))
    return (f'<div class="pattern"><h4>Comparable pattern: {_e(pat["name"])}</h4>'
            f'<p><strong>Mechanism:</strong> {_e(pat["mechanism"])}</p>'
            f'<p><strong>Cited examples:</strong></p><ul>{ex}</ul>'
            f'<p><strong>Where it applies:</strong> '
            f'{_e(pat.get("when_it_applies", ""))}</p>'
            f'<p><strong>Where it breaks down:</strong> '
            f'{_e(pat.get("when_it_does_not_apply", ""))}</p>'
            f'<p><strong>Limitations:</strong> '
            f'{_e(pat.get("limitations", ""))}</p></div>')


def _hypothesis_card(h: dict, obs_by_id: dict, pat_by_id: dict) -> str:
    supp = [obs_by_id[i] for i in h.get("supporting_observation_ids", [])
            if i in obs_by_id]
    counter = [obs_by_id[i] for i in h.get("counter_observation_ids", [])
               if i in obs_by_id]
    pat = pat_by_id.get(h.get("pattern_id", ""), {})

    supp_html = "".join(_obs_line(o) for o in supp) or "<p>—</p>"
    counter_html = ("".join(_obs_line(o) for o in counter) if counter else
                    '<p>No direct counter-evidence was retrieved; the open '
                    'evidence gaps below are held instead.</p>')
    alts = "".join(f"<li>{_e(a)}</li>"
                   for a in h.get("alternative_explanations", []))
    reasons = "".join(f"<li>{_e(r)}</li>"
                      for r in h.get("confidence_reasons", []))
    gaps = "".join(f"<li>{_e(g)}</li>" for g in h.get("evidence_gaps", []))
    implications = "".join(f"<li>{_e(x)}</li>"
                           for x in h.get("decision_implications", []))
    falsify = "".join(f"<li>{_e(q)}</li>"
                      for q in h.get("falsification_questions", []))
    classes = ", ".join(_CLASS_LABEL.get(c, c)
                        for c in h.get("source_classes", []))

    return (
        f'<article class="hypothesis" aria-label="Strategic hypothesis">'
        f'<h3>{_e(h["title"])} '
        f'<span class="confidence conf-{_e(h["confidence"])}">'
        f'{_e(h["confidence"])} confidence</span></h3>'
        f'<p class="statement">{_e(h["statement"])}</p>'
        f'<p><strong>Reasoning.</strong> {_e(h["reasoning"])}</p>'
        f'<p class="src-classes"><strong>Supported by:</strong> '
        f'{_e(classes or "—")}</p>'
        f'<details class="show-evidence"><summary>Show evidence — why we '
        f'believe this</summary>'
        f'<section><h4>Observed evidence</h4>{supp_html}</section>'
        f'<section><h4>Interpretation &amp; reasoning connection</h4>'
        f'<p>{_e(h["reasoning"])}</p></section>'
        f'<section><h4>Counter-evidence</h4>{counter_html}</section>'
        f'{_pattern_block(pat) if pat else ""}'
        f'<section><h4>Confidence: {_e(h["confidence"])}</h4>'
        f'<p>Why this level:</p><ul>{reasons}</ul>'
        f'<p>What is missing / would change the conclusion:</p>'
        f'<ul>{gaps}</ul></section>'
        f'</details>'
        f'<details class="alternatives"><summary>Alternative explanations'
        f'</summary><ul>{alts}</ul></details>'
        f'<p><strong>Decision implication.</strong></p><ul>{implications}</ul>'
        f'<p><strong>Falsification test.</strong></p><ul>{falsify}</ul>'
        f'</article>')


def render_strategic_report(report) -> str:
    """Return the HTML body (a <section>) for the strategic report."""
    r = _as_dict(report)
    obs_by_id = {o["observation_id"]: o for o in r.get("observations", [])}
    pat_by_id = {p["pattern_id"]: p for p in r.get("patterns", [])}
    thesis = r.get("thesis", {})

    coverage = " · ".join(
        f"{_CLASS_LABEL.get(c, c)}: {n}"
        for c, n in sorted(r.get("source_class_coverage", {}).items()))
    findings = r.get("quality_findings", [])
    findings_html = ("".join(
        f'<li>{_e(f["message"])}</li>' for f in findings)
        if findings else "<li>All strategic quality gates passed.</li>")

    shifts = "".join(
        f'<li><strong>{_e(s["title"])}</strong> '
        f'<em>({_e(_CLASS_LABEL.get(s.get("source_class",""), ""))}'
        f'{", " + _e(s["date"]) if s.get("date") else ""})</em><br>'
        f'{_e(s.get("evidence", ""))}</li>'
        for s in r.get("shifts", [])) or "<li>—</li>"

    hyps = "".join(_hypothesis_card(h, obs_by_id, pat_by_id)
                   for h in r.get("hypotheses", []))

    patterns = "".join(_pattern_block(p) for p in r.get("patterns", []))

    blinds = "".join(
        f'<article class="blind-spot"><h3>{_e(b["observed_tension"])}</h3>'
        f'<p><strong>Why it may matter:</strong> {_e(b["why_it_may_matter"])}'
        f'</p><p><strong>Counter-explanation:</strong> '
        f'{_e(b["counter_explanation"])}</p>'
        f'<p><strong>Evidence needed:</strong></p><ul>'
        + "".join(f"<li>{_e(x)}</li>" for x in b.get("evidence_needed", []))
        + f'</ul><p><strong>Decision affected:</strong> '
        f'{_e(b["decision_affected"])}</p></article>'
        for b in r.get("blind_spots", [])) or "<p>—</p>"

    questions = "".join(
        f'<article class="question"><h3>{_e(q["question"])}</h3>'
        f'<p><strong>Why we ask:</strong> {_e(q["why_it_matters"])}</p>'
        f'<p><strong>Triggered by:</strong></p><ul>'
        + "".join(f"<li>{_e(t)}</li>"
                  for t in q.get("evidence_that_triggered_it", []))
        + '</ul><p><strong>What different answers imply:</strong></p><ul>'
        + "".join(f"<li>{_e(p)}</li>"
                  for p in q.get("possible_answer_paths", []))
        + f'</ul><p><strong>Decision affected:</strong> '
        f'{_e(q["decision_affected"])}</p></article>'
        for q in r.get("questions", [])) or "<p>—</p>"

    gaps = "".join(f"<li>{_e(g)}</li>"
                   for g in r.get("evidence_gaps", [])) or "<li>—</li>"

    decisions = "".join(
        f'<article class="decision"><h3>{_e(d["decision"])}</h3>'
        f'<p><strong>Options that appear to exist:</strong></p><ul>'
        + "".join(f"<li>{_e(o)}</li>" for o in d.get("options", []))
        + '</ul><p><strong>Evidence needed before choosing:</strong></p><ul>'
        + "".join(f"<li>{_e(x)}</li>" for x in d.get("evidence_needed", []))
        + '</ul><p><strong>Leading indicators to monitor:</strong></p><ul>'
        + "".join(f"<li>{_e(w)}</li>" for w in d.get("watch", []))
        + '</ul></article>'
        for d in r.get("decision_implications", [])) or "<p>—</p>"

    status = r.get("status", "")
    return (
        f'<section class="strategic-report" aria-label="Strategic '
        f'Intelligence Report">'
        f'<p class="status status-{_e(status)}"><strong>Report status: '
        f'{_e(_STATUS_LABEL.get(status, status))}</strong></p>'
        f'<p class="coverage">Evidence source classes — {_e(coverage)}</p>'
        f'<p class="disclaimer">Outside-in analysis of approved public '
        f'sources and a curated historical-pattern library. It does not '
        f'claim private or internal knowledge, and no model is trained on '
        f'this company.</p>'

        f'<h2>1 · Executive thesis</h2>'
        f'<p class="thesis-view">{_e(thesis.get("view", ""))}</p>'
        f'<p><strong>Transition underway:</strong> '
        f'{_e(thesis.get("transition", ""))}</p>'
        f'<p><strong>Most important tension:</strong> '
        f'{_e(thesis.get("tension", ""))}</p>'
        f'<p><strong>Why leadership should care:</strong> '
        f'{_e(thesis.get("why_care", ""))}</p>'

        f'<h2>2 · What changed or appears to be changing</h2><ul>{shifts}</ul>'
        f'<h2>3 · Strategic hypotheses</h2>{hyps}'
        f'<h2>4 · Market and comparable patterns</h2>{patterns}'
        f'<h2>5 · Possible blind spots</h2>{blinds}'
        f'<h2>6 · Questions we would ask the leadership team</h2>{questions}'
        f'<h2>7 · Evidence gaps</h2><ul>{gaps}</ul>'
        f'<h2>8 · Decision implications</h2>{decisions}'
        f'<details class="quality"><summary>Report quality gate</summary>'
        f'<ul>{findings_html}</ul></details>'
        f'</section>')
