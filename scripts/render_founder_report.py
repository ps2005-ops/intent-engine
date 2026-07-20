#!/usr/bin/env python
"""Founder-readable weekly report renderer — approved 2026-07-19
(decision 3; format + honesty-marker treatment per
docs/report_mockup/DESIGN_NOTE.md, mockup approved as-is).

Deterministic transform: the production .txt report (already
language-walled at generation time) -> single-file HTML in the approved
mockup style. NO new data, NO new claims: every number/probability/date
comes from the parsed .txt; template prose is fixed strings approved with
the mockup. Track-record card is data-driven: renders "0 resolved — no
accuracy claimed" ONLY while the calibration section says "no resolutions
yet", and renders the ledger's own counts verbatim once they exist.

Parse failure on an unrecognized report shape RAISES (park, don't guess).

Usage: python scripts/render_founder_report.py --input reports/weekly_regime_report_YYYY-MM-DD.txt
       (writes <input>.founder.html next to it; --output to override)
"""

import argparse
import html
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from intent_engine.core.regime_report import assert_language_walls  # noqa: E402

SNAP_ROW_RE = re.compile(r"^(?P<label>[A-Z][^:]{3,40}):\s{2,}(?P<value>.+?)(?:\s+\[(?P<prov>[^\]]+)\])?\s*$")
PRED_RE = re.compile(r"^- P=(?P<p>0\.\d+) by (?P<by>\d{4}-\d{2}-\d{2}): (?P<claim>.+)$")

LABEL_PLAIN = {
    "Yield curve (T10Y2Y)": "Yield curve (10y − 2y)",
    "Credit spreads (HY OAS)": "Credit spreads (high-yield)",
    "Inflation trend (CPI YoY)": "Inflation trend (CPI YoY)",
    "Unemployment momentum": "Unemployment momentum",
}

CSS = """
  :root { --ink:#1a1d23; --muted:#6b7280; --line:#e5e7eb; --accent:#0f4c81;
          --honest:#8a6d1a; --honest-bg:#fdf6e3; --silent-bg:#f0f4f8; }
  body { font-family: Georgia, 'Times New Roman', serif; color: var(--ink);
         max-width: 720px; margin: 2.5rem auto; padding: 0 1.25rem; line-height: 1.55; }
  header { border-bottom: 3px double var(--ink); padding-bottom: .75rem; margin-bottom: 1.5rem; }
  h1 { font-size: 1.45rem; margin: 0; }
  .sub { color: var(--muted); font-size: .9rem; margin-top: .3rem; font-family: Helvetica, Arial, sans-serif; }
  h2 { font-family: Helvetica, Arial, sans-serif; font-size: .8rem; text-transform: uppercase;
       letter-spacing: .12em; color: var(--accent); margin: 1.8rem 0 .6rem; }
  table { width: 100%; border-collapse: collapse; font-size: .95rem; }
  td { padding: .45rem .3rem; border-bottom: 1px solid var(--line); vertical-align: top; }
  td.k { width: 38%; font-weight: bold; }
  td.prov { color: var(--muted); font-size: .78rem; font-family: Helvetica, Arial, sans-serif; text-align: right; width: 28%; }
  .badge { display: inline-block; font-family: Helvetica, Arial, sans-serif; font-size: .72rem;
           padding: .1rem .5rem; border-radius: 3px; }
  .badge.unavail { background: var(--honest-bg); color: var(--honest); border: 1px solid #e6d9a8; }
  .badge.ok { background: #eef6ee; color: #2f6b2f; border: 1px solid #cfe3cf; }
  .honest-card { background: var(--silent-bg); border-left: 4px solid var(--accent); padding: .8rem 1rem; font-size: .95rem; }
  .honest-card .why { color: var(--muted); font-size: .82rem; margin-top: .35rem; font-family: Helvetica, Arial, sans-serif; }
  .pred { border: 1px solid var(--line); border-radius: 4px; padding: .7rem .9rem; margin: .5rem 0; }
  .pred .p { font-family: Helvetica, Arial, sans-serif; font-weight: bold; color: var(--accent); }
  .pred .by { color: var(--muted); font-size: .82rem; font-family: Helvetica, Arial, sans-serif; }
  .gaps { border: 1px solid var(--line); border-radius: 4px; padding: .7rem .9rem; font-size: .9rem; color: var(--muted); }
  .gaps.active { background: var(--honest-bg); color: var(--honest); border-color: #e6d9a8; }
  footer { margin-top: 2rem; border-top: 1px solid var(--line); padding-top: .9rem;
           font-size: .82rem; color: var(--muted); font-family: Helvetica, Arial, sans-serif; }
"""

METHOD_FOOTER = (
    "<strong>Method, in one paragraph:</strong> real macro/market data (FRED, "
    "Tiingo; sources and dates shown inline) → deterministic regime indicators → "
    "a gate-tested structural-mechanism read against documented historical "
    "episodes → probabilistic claims recorded to an append-only ledger and graded "
    "by code, never by self-assessment. What's unavailable is labeled "
    "unavailable; what doesn't match, doesn't match; what hasn't resolved yet "
    "isn't a track record. Rendered 1:1 from the production run — no numbers "
    "added, adjusted, or invented for presentation.")


def parse_report(text: str) -> dict:
    lines = text.splitlines()
    out = {"snapshot_date": None, "rows": [], "mechanisms": [], "none_matched": False,
           "gaps": [], "predictions": [], "no_predictions": False, "calibration": []}
    section = None
    for ln in lines:
        s = ln.rstrip()
        if s.startswith("REGIME SNAPSHOT"):
            m = re.search(r"as of (\d{4}-\d{2}-\d{2})", s)
            out["snapshot_date"] = m.group(1) if m else None
            section = "snap"; continue
        if s.startswith("Structural mechanisms possibly in play: none matched"):
            out["none_matched"] = True; section = None; continue
        if s.startswith("Structural mechanisms possibly in play:"):
            section = "mech"; continue
        if s.startswith("!! DATA GAPS DETECTED"):
            section = "gaps"; continue
        if s.startswith("RESOLVABLE PREDICTIONS"):
            section = "pred"; continue
        if s.startswith("CALIBRATION"):
            section = "cal"; continue
        if set(s) == {"-"} and s:  # separator rule
            continue
        if not s:
            continue
        if section == "snap":
            m = SNAP_ROW_RE.match(s)
            if not m:
                raise ValueError(f"Unrecognized snapshot row (parse-park, not guessed): {s!r}")
            out["rows"].append({"label": m.group("label").strip(), "value": m.group("value").strip(),
                                 "prov": (m.group("prov") or "").strip()})
        elif section == "mech" and s.startswith("- "):
            out["mechanisms"].append(s[2:])
        elif section == "gaps" and s.startswith("- "):
            out["gaps"].append(s[2:])
        elif section == "pred":
            if s == "None recorded this run.":
                out["no_predictions"] = True; continue
            m = PRED_RE.match(s)
            if not m:
                raise ValueError(f"Unrecognized prediction line (parse-park): {s!r}")
            out["predictions"].append(m.groupdict())
        elif section == "cal":
            out["calibration"].append(s)
    if out["snapshot_date"] is None:
        raise ValueError("No REGIME SNAPSHOT header found -- refusing to render an unrecognized report.")
    return out


def _snapshot_row_html(row: dict) -> str:
    label = html.escape(LABEL_PLAIN.get(row["label"], row["label"]))
    value, prov = row["value"], html.escape(row["prov"])
    if value == "unavailable":
        cell = ('<span class="badge unavail">UNAVAILABLE</span> — no verified number this run, '
                'so no claim is made (rather than showing a stale one).')
    else:
        cell = f'<span class="badge ok">{html.escape(value.upper() if len(value) < 16 else value)}</span>'
        if len(value) >= 16:
            cell = html.escape(value)
    return f'<tr><td class="k">{label}</td><td>{cell}</td><td class="prov">{prov}</td></tr>'


def render(parsed: dict) -> str:
    d = parsed["snapshot_date"]
    parts = [f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
             f'<title>Structural Regime Read — {d}</title><style>{CSS}</style></head><body>',
             f'<header><h1>Structural Regime Read</h1><div class="sub">As of {d} · every number '
             f'carries its source and date · what we can\'t verify, we say we can\'t verify</div></header>',
             '<h2>Where the regime stands</h2><table>']
    parts += [_snapshot_row_html(r) for r in parsed["rows"]]
    parts.append("</table>")

    parts.append("<h2>Structural mechanisms in play</h2>")
    if parsed["none_matched"]:
        parts.append('<div class="honest-card"><strong>None matched this run — and that\'s the finding.</strong> '
                     'The available signal didn\'t genuinely clear any documented mechanism\'s trigger conditions, '
                     'so the system says nothing rather than forcing a story.'
                     '<div class="why">Mechanism reads are matched by deterministic rules against a citation-carrying '
                     'library; silence on thin evidence is a designed, reliability-tested behavior.</div></div>')
    else:
        for mline in parsed["mechanisms"]:
            parts.append(f'<div class="pred">{html.escape(mline)}</div>')

    parts.append("<h2>Claims on the record</h2>")
    if parsed["no_predictions"]:
        parts.append('<div class="gaps">None recorded this run.</div>')
    for p in parsed["predictions"]:
        parts.append(f'<div class="pred"><span class="p">P = {p["p"]}</span> '
                     f'<span class="by">· resolves by {p["by"]} · graded automatically against real data</span><br>'
                     f'{html.escape(p["claim"])}</div>')

    parts.append("<h2>Data gaps</h2>")
    if parsed["gaps"]:
        parts.append('<div class="gaps active"><strong>Genuine data gaps this run — excluded from every '
                     'number above, never papered over:</strong><br>'
                     + "<br>".join(html.escape(g) for g in parsed["gaps"]) + "</div>")
    else:
        parts.append('<div class="gaps">No genuine data gaps detected in this run. (When a source series has '
                     'a real hole, it is listed here loudly and excluded from every number above.)</div>')

    parts.append("<h2>Track record</h2>")
    cal = parsed["calibration"]
    no_resolutions = any("no resolutions yet" in c for c in cal) and not any("resolved," in c for c in cal)
    if no_resolutions:
        parts.append('<div class="honest-card"><strong>0 predictions resolved so far — so no accuracy is '
                     'claimed, full stop.</strong> Every probability above is written to an append-only ledger '
                     'and graded by code against real market data on its resolve-by date. Calibration is '
                     'reported here as it accumulates, including against two dumb baselines the system has to '
                     'beat honestly.</div>')
    else:
        parts.append('<div class="honest-card">' + "<br>".join(html.escape(c) for c in cal) + "</div>")

    parts.append(f"<footer>{METHOD_FOOTER}</footer></body></html>")
    rendered = "\n".join(parts)
    assert_language_walls(rendered)  # A-M4 backstop on the final artifact
    return rendered


# ---------------------------------------------------------------------------
# C2 (PLAN_2026-07-21 / MARKETING_PLAN_V2 §3): productized premortem PDF.
#
# Deterministic transform PremortemResult -> structured PDF with the approved
# section set. NO new facts: every line comes from the result object or is
# fixed template prose. Honesty markers render in every section; the "what we
# could not verify" block is MANDATORY — it renders with an explicit label
# even when empty. No accuracy claim anywhere (checked before writing).
#
# The PDF writer below is deliberately dependency-free (plain-text streams,
# built-in Helvetica): the offline suite must pass on any machine with no
# new packages, and the byte-level simplicity keeps the artifact auditable.
# ---------------------------------------------------------------------------

from datetime import datetime, timezone  # noqa: E402

# Founder feedback 2026-07-20 (report v2): Company Snapshot, boxed
# Recommendation (decision framework, NOT a prediction), rule-computed
# Evidence Confidence (in the analysis, NOT the future), numbered
# Assumptions, facts/inference separation, risk-level grouping,
# "what would change this", Appendix + decision loop. The original
# 9-section DoD set is a strict subset of this order.
PREMORTEM_SECTION_ORDER = [
    "Company Snapshot", "Executive Summary", "Recommendation",
    "Evidence Confidence", "Decision", "Assumptions", "Mechanisms",
    "Evidence", "Contradictions", "Scenario tree", "Alternatives Considered",
    "Metrics to watch", "What would change this", "90-day checklist",
    "Prediction", "Decision lifecycle", "Appendix",
]

# T012: the nine-stage lifecycle the report is one point in. Presentation
# only — the three folded state axes are read from DecisionService and are
# NEVER collapsed into a stored status field here.
LIFECYCLE_STAGES = [
    "Decision framed", "Evidence gathered", "Recommendation issued",
    "Decision taken", "Execution started", "Monitoring",
    "Outcome resolved", "Calibration", "Lessons promoted",
]


def _lifecycle_items(state, event_types) -> list:
    """Deterministic mapping: folded three-axis state -> nine-stage display.
    Completed stages get checks, the current stage is a bold heading, future
    stages render subordinate ('not yet'); terminal decisions (declined /
    cancelled / superseded) mark unreachable stages honestly instead of
    pretending progress."""
    ds, es, ev = (state.decision_status, state.execution_status,
                  state.evaluation_status)
    evs = set(event_types)
    # Stage completion reads the EVENT HISTORY where folding is lossy: an
    # approved decision later superseded still WAS taken — the fold shows
    # ds="superseded", the events still show DecisionApproved.
    done = {
        1: True,                                   # a record exists
        2: True,                                   # this report is that pass
        3: "RecommendationIssued" in evs,
        4: bool({"DecisionApproved", "DecisionDeclined"} & evs)
           or ds in ("approved", "declined"),
        5: es in ("executing", "paused", "completed", "abandoned"),
        6: es == "completed" or ev in ("partially_resolved", "resolved",
                                       "calibrated"),
        7: ev in ("resolved", "calibrated"),
        8: ev == "calibrated",
        9: False,   # knowledge promotion is not built yet — never claimed
    }
    qualifiers = {}
    if ds == "declined" or "DecisionDeclined" in evs:
        qualifiers[4] = " (declined — the honest end of this lifecycle)"
    elif ds == "superseded" and done[4]:
        qualifiers[4] = " (later superseded)"
    if es == "paused":
        qualifiers[5] = " (currently paused)"
    if es == "abandoned":
        qualifiers[5] = " (execution abandoned)"
    if ev == "partially_resolved":
        qualifiers[7] = " (partially resolved)"

    terminal = ds in ("declined", "cancelled", "superseded")
    current = None if terminal else next(
        (n for n in range(1, 10) if not done[n]), None)

    items = []
    if terminal:
        items.append(f"This decision is {ds.upper()} — remaining stages are "
                     "not applicable, and are marked so rather than shown "
                     "as pending.")
    for n, name in enumerate(LIFECYCLE_STAGES, 1):
        label = f"{n}. {name}{qualifiers.get(n, '')}"
        if done[n]:
            items.append({"check": label})
        elif terminal:
            items.append({"cross": f"{n}. {name} — not applicable "
                                   f"(decision {ds})"})
        elif n == current:
            items.append({"h": f">> {label} — CURRENT STAGE"})
        elif n == 9:
            items.append({"sub": f"{n}. {name} — not yet (knowledge "
                                 "promotion is not built; stated honestly, "
                                 "never shown as reached)"})
        else:
            items.append({"sub": f"{n}. {name} — not yet"})
    return items

RISK_LEVELS = {"likely": "HIGH", "tail_risk": "TAIL", "possible": "MEDIUM",
               "unlikely": "LOW"}
_RISK_ORDER = ["HIGH", "TAIL", "MEDIUM", "LOW", "UNRATED"]


def _engine_version() -> str:
    try:
        m = re.search(r'^version\s*=\s*"([^"]+)"',
                      (REPO_ROOT / "pyproject.toml").read_text(), re.M)
        return m.group(1) if m else "unknown"
    except OSError:  # pragma: no cover
        return "unknown"

_PDF_ALLOWED_DISCLAIMERS = ["no accuracy is claimed", "no accuracy claimed"]
_PDF_FORBIDDEN_CLAIMS = ["accura", "track record", "hit rate", "win rate",
                         "correctly predicted", "proven", "success rate"]

_UNVERIFIED_VALUES = {"unclear", "uncertain", "none_apparent", "unknown"}


def _assert_no_accuracy_claim(text: str) -> None:
    lowered = text.lower()
    for allowed in _PDF_ALLOWED_DISCLAIMERS:
        lowered = lowered.replace(allowed, " ")
    hits = [p for p in _PDF_FORBIDDEN_CLAIMS if p in lowered]
    if hits:
        raise ValueError(f"Accuracy-claim wall violation in premortem PDF: {hits}")


def _could_not_verify_lines(unverified: list) -> list:
    """MANDATORY block. Renders an explicit label even when empty."""
    header = "WHAT WE COULD NOT VERIFY (said plainly, never papered over):"
    if not unverified:
        return [header, "NONE FLAGGED this run — every signal above carries a "
                        "value; nothing was silently dropped."]
    return [header] + [f"- {u}" for u in unverified]


def build_premortem_sections(decision_text: str, context, result,
                             generated_at: str = None,
                             decision_service=None) -> dict:
    """PremortemResult -> {section_title: [items]}, in the approved order.

    Items are strings (body text) or dicts the PDF writer understands:
    {"h":}, {"check":}, {"cross":}, {"bullet":}, {"box": [...]},
    {"gauge": level}, {"bar": level, "text":}, {"tree": [(name,tag,deltas)]}.
    Every fact comes from the inputs; everything else is fixed template
    prose. No new facts, no forecasts, no accuracy claims.

    T011 Slice 2A: when the result carries a Decision Record (T010) the
    report renders its identity; with a `decision_service` it also renders
    the folded three-axis status, current owner, and supersession links —
    all READS of the record (folded by `DecisionService`, never inferred
    here). Absent record -> byte-identical output to before (additive
    default). The report never writes decision events.
    """
    intent, audit, scen = result.intent, result.risk_audit, result.scenario_set
    rm = result.ranked_mechanisms
    lp = result.ledgered_predictions
    drec = getattr(result, "decision_record", None)

    # -- Decision Record read (Slice 2A): identity, folded status, owner,
    # supersession links. Display strings only; the fold happens in
    # DecisionService (one source of truth), never re-implemented here.
    record_lines = []
    record_version_bullets = []
    record_state = None
    record_event_types = []
    if drec is not None:
        record_lines.append(f"Decision record: {drec.decision_key} "
                            f"({drec.decision_id})")
        record_version_bullets.append(
            {"bullet": f"Decision record: {drec.decision_key}; record schema "
                       f"v{drec.record_schema_version}"})
        if decision_service is not None:
            st = decision_service.get_current_state(drec.decision_id)
            record_state = st
            record_event_types = [e["event_type"] for e in
                                  decision_service.get_events(drec.decision_id)]
            record_lines.append(
                f"Status: decision={st.decision_status} / "
                f"execution={st.execution_status} / "
                f"evaluation={st.evaluation_status}")
            record_lines.append(
                f"Owner: {st.owner if st.owner else 'unassigned'}")
            rel = decision_service.get_related_decisions(drec.decision_id)
            for edge in rel["outgoing"] + rel["incoming"]:
                if edge["relationship_type"] in ("supersedes", "superseded_by"):
                    other = decision_service.get_decision(edge["decision_id"])
                    label = other.decision_key if other else edge["decision_id"]
                    verb = ("Supersedes" if edge["relationship_type"] == "supersedes"
                            else "Superseded by")
                    record_lines.append(f"{verb}: {label}")

    # -- shared derivations (computed once, used by several sections) --------
    unverified = []
    signal_lines = []

    def _signal(label, value):
        sval = ", ".join(value) if isinstance(value, list) else value
        if sval is None or str(sval) in _UNVERIFIED_VALUES:
            signal_lines.append(f"{label}: UNKNOWN — not enough signal in the "
                                "decision text; not guessed.")
            unverified.append(f"{label}: {sval if sval is not None else 'not extracted'}")
        else:
            signal_lines.append(f"{label}: {sval}")

    _signal("Scale efficiency", getattr(intent, "scale_efficiency", None))
    _signal("Leverage type", getattr(intent, "leverage_type", None) or None)
    _signal("Market timing signal", getattr(intent, "market_timing_signal", None))

    ctx_fields = [
        ("Revenue", context.revenue), ("Growth rate", context.growth_rate),
        ("Team size", context.team_size), ("Runway (months)", context.runway_months),
        ("Market", context.market),
        ("Competitive position", context.competitive_position),
        ("Primary goal", context.founder_goals
         or (", ".join(context.stated_priorities) or None)),
    ]
    n_ctx = sum(1 for _, v in ctx_fields if v is not None)

    sections = {}

    # -- Company Snapshot (feedback #8: written for one company) -------------
    snap = [{"h": "This analysis is grounded in the following business:"}]
    for label, v in ctx_fields:
        snap.append(f"{label}: {v if v is not None else 'not provided'}")
    if record_lines:
        # Slice 2A: decision identity + folded status header, in the box the
        # reader sees first. Reads only; absent record -> absent lines.
        snap.append({"h": "Decision record (event-sourced; status folded, "
                          "never stored)"})
        snap.extend(record_lines)
    sections["Company Snapshot"] = [{"box": snap}]

    sections["Executive Summary"] = [audit.narrative_summary]

    # -- Recommendation (feedback #1: a decision framework, not a prediction)
    rec = [{"h": "Decision framework — conditions, not a forecast"},
           "Proceed only if ALL of the following hold:"]
    for c in intent.constraints:
        rec.append({"check": f"This constraint still holds: {c}"})
    rec.append({"check": f"The key sensitivity clears: {audit.key_sensitivity}"})
    for fm in audit.failure_modes:
        if fm.likelihood in ("likely", "tail_risk"):
            rec.append({"check": f"A mitigation is in place for: {fm.description}"})
    rec += ["If any condition fails: delay or re-scope, and re-run this premortem.",
            "(Every condition above is drawn 1:1 from the stated constraints and "
            "the risks below. This box frames the decision; it does not forecast "
            "an outcome.)"]
    sections["Recommendation"] = [{"box": rec}]

    # -- Evidence Confidence (T012 Slice 2B: THREE separate axes) ------------
    # Splitting the old single gauge resolves V1-roadmap finding #7: a leg
    # that was not requested is a smaller examination (Reasoning Coverage),
    # never weaker evidence (Evidence Quality). Every level is computed by
    # rule from the report's own inputs — never model self-assessment.

    # Axis 1 — Evidence Quality: strength of the evidence actually available.
    eq_checks = []
    if n_ctx >= 4:
        eq_checks.append({"check": f"business context: {n_ctx} of "
                                   f"{len(ctx_fields)} fields provided"})
    else:
        eq_checks.append({"cross": f"business context sparse: {n_ctx} of "
                                   f"{len(ctx_fields)} fields provided"})
    if unverified:
        eq_checks.append({"cross": "structural signals incomplete: "
                                   + "; ".join(unverified)})
    else:
        eq_checks.append({"check": "structural signals fully extracted"})
    n_eq_cross = sum(1 for c in eq_checks if "cross" in c)
    eq_level = ("HIGH" if n_eq_cross == 0
                else "MEDIUM" if n_eq_cross == 1 else "LOW")

    # Axis 2 — Reasoning Coverage: how much of the examination actually ran.
    rc_checks = [
        {"check": f"scenario framing ran ({len(scen.scenarios)} scenarios)"},
        {"check": "assumptions enumerated (see the numbered box below)"},
    ]
    if rm is not None:
        rc_checks.append({"check": "documented mechanism library consulted"})
    else:
        rc_checks.append({"cross": "mechanism read not requested this run "
                                   "(a coverage gap, NOT weak evidence)"})
    if lp is not None:
        rc_checks.append({"check": "prediction-recording leg ran "
                                   "(append-only ledger)"})
    else:
        rc_checks.append({"cross": "prediction recording not requested this "
                                   "run (a coverage gap, NOT weak evidence)"})
    n_rc_cross = sum(1 for c in rc_checks if "cross" in c)
    rc_level = ("HIGH" if n_rc_cross == 0
                else "MEDIUM" if n_rc_cross == 1 else "LOW")

    # Axis 3 — Prediction Confidence: only what is explicitly ledgered.
    if lp:
        pc_head = {"h": f"Prediction Confidence: RECORDED — {len(lp)} "
                        f"ledgered claim(s)"}
        pc_lines = [
            "Stated probabilities are listed in the Prediction section; they "
            "were stated at creation, live on the append-only ledger, and are "
            "graded by code on their resolve-by dates. No accuracy claimed "
            "(0 resolved is 0 resolved).",
        ]
    else:
        pc_head = {"h": "Prediction Confidence: UNAVAILABLE"}
        pc_lines = [
            ("No prediction was recorded this run, so there is no ledgered "
             "claim to attach confidence to — saying so is the honest answer. "
             "No accuracy claimed."),
        ]

    sections["Evidence Confidence"] = [
        "Three separate reads, each computed by rule from this report's own "
        "inputs — never by model self-assessment. All three are confidence "
        "in the ANALYSIS given the available evidence — NOT confidence in "
        "the future.",
        {"gauge": eq_level, "label": "Evidence Quality"},
        "because:",
        *eq_checks,
        {"gauge": rc_level, "label": "Reasoning Coverage"},
        "Coverage measures how much of the examination ran. A leg that was "
        "not requested makes the examination smaller — it does not make the "
        "evidence weaker (it never lowers Evidence Quality above).",
        "because:",
        *rc_checks,
        pc_head,
        *pc_lines,
    ]

    # -- Decision ------------------------------------------------------------
    dec = [f"Decision under review: {decision_text}"]
    if intent.goals:
        dec.append("Goals: " + "; ".join(intent.goals))
    if intent.constraints:
        dec.append("Constraints: " + "; ".join(intent.constraints))
    dec.append(f"Stated risk tolerance: {intent.risk_tolerance}")
    sections["Decision"] = dec

    # -- Assumptions (feedback #4: numbered, re-run trigger) -----------------
    assumptions = []
    for c in intent.constraints:
        assumptions.append(f"{c} (stated constraint)")
    for label, v in ctx_fields:
        if v is not None:
            assumptions.append(f"{label} stays ~ {v} (provided input)")
    ass = [{"h": "Assumptions this analysis stands on"}]
    ass += [f"{i}. {a}" for i, a in enumerate(assumptions, 1)]
    ass.append("If any numbered assumption changes, this report should be "
               "re-run and superseded (\"re-run because assumption #N changed\").")
    sections["Assumptions"] = [{"box": ass}]

    # -- Mechanisms (feedback #7: educational NONE MATCHED) ------------------
    if rm is None:
        sections["Mechanisms"] = ["UNAVAILABLE — the mechanism read was not "
                                  "requested this run, so no claim is made."]
    elif not rm:
        sections["Mechanisms"] = [
            "NONE MATCHED — none of the documented mechanisms cleared their "
            "trigger conditions.",
            "That doesn't mean \"nothing is happening.\" It means the available "
            "evidence does not justify claiming a known historical pattern — "
            "and saying so is the honest answer."]
    else:
        sections["Mechanisms"] = [{"bullet": str(m)} for m in rm]

    # -- Evidence (feedback #3 facts vs interpretation, #10 risk levels) -----
    ev = [{"h": "Observed inputs (facts provided or extracted; honesty "
               "markers, never guesses)"}]
    ev += [{"bullet": s} for s in signal_lines]
    ev.append({"h": "Inference and possible consequence, grouped by risk level"})
    ev.append("(The grouping is a display mapping of the model's stated "
              "likelihoods — likely->HIGH, tail_risk->TAIL, possible->MEDIUM, "
              "unlikely->LOW. It adds no new information.)")
    by_level = {}
    for fm in audit.failure_modes:
        by_level.setdefault(RISK_LEVELS.get(fm.likelihood, "UNRATED"), []).append(fm)
    for lvl in _RISK_ORDER:
        for fm in by_level.get(lvl, []):
            ev.append({"bar": lvl, "text": f"Possible consequence: {fm.description}"})
            ev.append({"sub": f"Inference: {fm.rationale}"})
    sections["Evidence"] = ev

    sections["Contradictions"] = (
        [f"The single factor this decision is most sensitive to: {audit.key_sensitivity}", ""]
        + _could_not_verify_lines(unverified))

    sections["Scenario tree"] = [
        f"Primary founder priority (extracted): {scen.primary_priority}",
        {"tree": [(s.name, s.tag, s.key_deltas) for s in scen.scenarios]}]

    # -- Alternatives Considered (T012): structured inputs ONLY --------------
    # This section never invents an alternative and never asks the model a
    # second untracked question. It renders structured alternatives when a
    # caller supplies them (result.alternatives); otherwise it says so.
    alternatives = getattr(result, "alternatives", None) or []
    alt_items = []
    for i, alt in enumerate(alternatives, 1):
        get = (alt.get if isinstance(alt, dict)
               else lambda k, _a=alt: getattr(_a, k, None))
        alt_items.append({"h": f"{i}. {get('alternative')}"})
        for label, key in (("Why considered", "why_considered"),
                           ("Main advantage", "main_advantage"),
                           ("Main risk", "main_risk"),
                           ("Why not currently recommended",
                            "why_not_recommended"),
                           ("Would become preferable if", "preferable_if")):
            val = get(key)
            if val:
                alt_items.append({"bullet": f"{label}: {val}"})
    if not alt_items:
        alt_items = [
            "NONE DOCUMENTED — this run's structured analysis output contains "
            "no alternatives, and this report never invents one.",
            "The Recommendation box's delay / re-scope path remains the "
            "standing fallback. When a run supplies structured alternatives, "
            "they render here with their trade-offs.",
        ]
    sections["Alternatives Considered"] = alt_items

    sections["Metrics to watch"] = (
        [{"bullet": f"Key sensitivity to track: {audit.key_sensitivity}"}]
        + [{"bullet": f"Scenario delta to watch ({s.name}): {s.key_deltas}"}
           for s in scen.scenarios])

    # -- What would change this (feedback #5) --------------------------------
    sections["What would change this"] = (
        ["This assessment — and the recommendation box above — would change if:"]
        + [{"bullet": f"the key sensitivity resolves the other way: {audit.key_sensitivity}"},
           {"bullet": "any numbered assumption above breaks"}]
        + [{"bullet": f"observed results diverge from the {s.name} scenario band "
                      f"({s.key_deltas})"}
           for s in scen.scenarios if s.name in ("upside", "downside")]
        + [{"bullet": "a ledgered claim resolves against this read (graded by "
                      "code, visible on the ledger)"}])

    sections["90-day checklist"] = (
        [f"[ ] {t}" for t in audit.recommended_stress_tests]
        + ["[ ] Re-run this premortem if the key sensitivity above changes materially.",
           "[ ] Check the prediction ledger on each resolve-by date (graded by code)."])

    if lp is None:
        pred_lines = ["UNAVAILABLE — prediction recording was not requested this run."]
    elif not lp:
        pred_lines = ["None recorded this run."]
    else:
        pred_lines = [f"- P={p.probability:.2f} by {p.resolve_by}: {p.claim_text}"
                      for p in lp]
    pred_lines.append("Predictions live on an append-only ledger and are graded "
                      "by code. Nothing here is a forecast guarantee and no "
                      "accuracy is claimed (0 resolved is 0 resolved).")
    sections["Prediction"] = pred_lines

    # -- Decision lifecycle (T012): nine stages, position read from the fold -
    if record_state is not None:
        life = ["This report is one pass through a larger lifecycle. The "
                "position below is READ from the decision's event-sourced "
                "state (three independent axes, folded by DecisionService) — "
                "the report stores nothing and infers nothing."]
        life += _lifecycle_items(record_state, record_event_types)
    else:
        life = [
            "UNAVAILABLE — no Decision Record is attached to this run, so "
            "the lifecycle position is not tracked. The nine stages, for "
            "reference:",
        ] + [{"sub": f"{n}. {name}"}
             for n, name in enumerate(LIFECYCLE_STAGES, 1)]
    sections["Decision lifecycle"] = life

    # -- Appendix (feedback #9 auditable; #12 decision loop) -----------------
    ts = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    if rm is None:
        mech_status = "not requested this run (labeled UNAVAILABLE above)"
    elif not rm:
        mech_status = "library consulted; zero mechanisms cleared their triggers"
    else:
        mech_status = f"{len(rm)} mechanism(s) matched (listed above, cited)"
    if lp:
        ledger_status = f"{len(lp)} entr{'y' if len(lp) == 1 else 'ies'} recorded (source=premortem)"
    elif lp is None:
        ledger_status = "recording not requested this run"
    else:
        ledger_status = "requested; none recorded this run"
    sections["Appendix"] = [
        {"h": "Methodology"},
        "Founder-provided context -> structural extraction by a gate-tested "
        "analyzer (closed taxonomy; no forced matches) -> deterministic check "
        "against a documented mechanism library -> scenario framing -> "
        "probabilistic claims recorded to an append-only ledger and graded by "
        "code, never by self-assessment. What's unavailable is labeled "
        "unavailable; what doesn't match, doesn't match.",
        {"h": "Evidence sources"},
        {"bullet": "Business context: provided by the founder (Company Snapshot)"},
        {"bullet": "Structural signals: extracted from the decision text only"},
        {"bullet": "Mechanism library: mechanisms.json — every historical "
                   "instance carries a real citation"},
        {"h": "Mechanisms consulted"},
        mech_status,
        {"h": "Prediction ledger"},
        ledger_status,
        {"h": "Version & audit trail"},
        {"bullet": f"Engine version: {_engine_version()}"},
        *record_version_bullets,
        {"bullet": f"Analysis timestamp: {ts}"},
        {"bullet": "Report generator: scripts/render_founder_report.py "
                   "(deterministic; no numbers invented for presentation)"},
        {"h": "The decision loop"},
        "The full nine-stage lifecycle — and where this decision currently "
        "sits in it — is rendered in the Decision lifecycle section above. "
        "One loop, stated once.",
        "This report is one pass through that loop. The append-only ledger and "
        "the feedback survey close it: a report here is a living record that "
        "gets graded, not a static artifact.",
    ]

    return {k: sections[k] for k in PREMORTEM_SECTION_ORDER}


# --- minimal dependency-free PDF writer -------------------------------------

def _pdf_escape(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _wrap(line: str, width: int = 92) -> list:
    if len(line) <= width:
        return [line]
    words, out, cur = line.split(" "), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            out.append(cur); cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        out.append(cur)
    return out


_GAUGE_LEVELS = ["HIGH", "MEDIUM", "LOW"]
_BAR_WIDTHS = {"HIGH": 130, "TAIL": 130, "MEDIUM": 85, "LOW": 45, "UNRATED": 60}
_BAR_GRAYS = {"HIGH": 0.2, "TAIL": 0.2, "MEDIUM": 0.45, "LOW": 0.65, "UNRATED": 0.5}


def _item_text(it) -> list:
    """All human-readable text inside one item (for walls/audit/tests)."""
    if isinstance(it, str):
        return [it]
    if "t" in it:
        return [it["t"]]
    if "h" in it:
        return [it["h"]]
    if "check" in it:
        return [it["check"]]
    if "cross" in it:
        return [it["cross"]]
    if "bullet" in it:
        return [it["bullet"]]
    if "bar" in it:
        return [it["text"]]
    if "sub" in it:
        return [it["sub"]]
    if "gauge" in it:
        return [f"{it.get('label', 'Overall evidence confidence')}: {it['gauge']}"]
    if "tree" in it:
        return [f"{n.upper()} — {t}: {d}" for n, t, d in it["tree"]]
    if "box" in it:
        return [s for sub in it["box"] for s in _item_text(sub)]
    return []


def write_pdf(sections: dict, out_path, title: str = "Pre-Mortem Report") -> None:
    """Structured PDF, Letter, Helvetica core fonts + ZapfDingbats
    check/cross marks, light vector visuals (confidence gauge, risk bars,
    boxed callouts, scenario tree). Uncompressed streams: the text is
    visible in the raw bytes, so the artifact stays auditable."""
    pages, cur = [], []
    top, bottom, lh = 738, 60, 14
    y = top

    def newpage():
        nonlocal cur, y
        if cur:
            pages.append(cur)
        cur, y = [], top

    def ensure(height):
        if y - height < bottom:
            newpage()

    def text_at(x, ypos, s, font="F1", size=10, gray=0.0):
        cur.append(f"{gray:.2f} g BT /{font} {size} Tf {x} {ypos} Td "
                   f"({_pdf_escape(s)}) Tj ET 0 g")

    def put(text, font="F1", size=10, x=54, gray=0.0):
        nonlocal y
        ensure(lh)
        text_at(x, y, text, font=font, size=size, gray=gray)
        y -= lh

    def put_wrapped(text, x=54, font="F1", size=10, gray=0.0):
        width = max(30, int((558 - x) / 5.4))
        for line in _wrap(str(text), width=width):
            put(line, font=font, size=size, x=x, gray=gray)

    def put_mark(text, mark, x=58):
        # mark: '3' = check, '7' = cross (ZapfDingbats)
        nonlocal y
        ensure(lh)
        text_at(x, y, mark, font="F3", size=9, gray=0.15 if mark == "3" else 0.35)
        width = max(30, int((558 - x - 16) / 5.4))
        lines = _wrap(str(text), width=width)
        text_at(x + 14, y, lines[0])
        y -= lh
        for cont in lines[1:]:
            put(cont, x=x + 14)

    def put_gauge(level, x=58, label="Overall evidence confidence"):
        nonlocal y
        ensure(3 * lh + 14)
        y -= 4
        for i, lbl in enumerate(_GAUGE_LEVELS):
            bx = x + i * 92
            if lbl == level:
                cur.append(f"0.20 g {bx} {y - 16} 84 18 re f 0 g")
                text_at(bx + 8, y - 11, lbl, font="F2", size=9, gray=1.0)
            else:
                cur.append(f"0.94 g {bx} {y - 16} 84 18 re f 0 g")
                cur.append(f"0.70 G {bx} {y - 16} 84 18 re S 0 G")
                text_at(bx + 8, y - 11, lbl, size=9, gray=0.55)
        y -= 16 + lh
        # The text label always accompanies the filled box: meaning is never
        # conveyed by the visual alone (accessibility bar).
        put(f"{label}: {level}", font="F2", size=10, x=x)

    def put_bar(level, text, x=58):
        nonlocal y
        ensure(2 * lh + 8)
        text_at(x, y, f"[{level}]", font="F2", size=9,
                gray=_BAR_GRAYS.get(level, 0.4))
        put_wrapped(text, x=x + 52)
        w = _BAR_WIDTHS.get(level, 60)
        g = _BAR_GRAYS.get(level, 0.5)
        if level == "TAIL":  # low probability, high impact: outline, not fill
            cur.append(f"0.30 G {x} {y + 6} {w} 4 re S 0 G")
        else:
            cur.append(f"{g:.2f} g {x} {y + 6} {w} 4 re f 0 g")
        y -= 8

    def put_tree(branches, x=70):
        nonlocal y
        ensure(len(branches) * 2 * lh + 10)
        y -= 2
        top_y = y - 4
        for name, tag, deltas in branches:
            branch_y = y - 5
            cur.append(f"0.55 G {x} {branch_y} m {x + 16} {branch_y} l S 0 G")
            put(f"{name.upper()} — {tag}", font="F2", size=10, x=x + 22)
            put_wrapped(deltas, x=x + 22, gray=0.35)
            y -= 4
        cur.append(f"0.55 G {x} {top_y} m {x} {y + lh} l S 0 G")
        y -= 4

    def measure(items, x=54):
        n = 0
        for it in items:
            if isinstance(it, str) or "t" in it:
                s = it if isinstance(it, str) else it["t"]
                n += len(_wrap(str(s), width=max(30, int((558 - x) / 5.4))))
            elif "h" in it:
                n += len(_wrap(it["h"], width=max(30, int((558 - x) / 5.4))))
            elif "check" in it or "cross" in it or "bullet" in it:
                s = it.get("check") or it.get("cross") or it.get("bullet")
                n += len(_wrap(str(s), width=max(30, int((558 - x - 16) / 5.4))))
            elif "sub" in it:
                n += len(_wrap(it["sub"], width=max(30, int((558 - x - 56) / 5.4))))
            else:
                n += 3
        return n

    def put_box(items, x=58):
        nonlocal y
        height = measure(items, x=x + 6) * lh + 16
        ensure(min(height, top - bottom - lh))
        y -= 4
        box_top = y
        cur.append(f"0.955 g 50 {box_top - height + 10} 512 {height} re f 0 g")
        cur.append(f"0.70 G 50 {box_top - height + 10} 512 {height} re S 0 G")
        y -= 8
        render_items(items, x=x)
        y -= 6

    def render_items(items, x=54):
        for it in items:
            if isinstance(it, str):
                put_wrapped(it, x=x)
            elif "t" in it:
                put_wrapped(it["t"], x=x)
            elif "h" in it:
                put_wrapped(it["h"], x=x, font="F2", size=10.5)
            elif "sub" in it:
                put_wrapped(it["sub"], x=x + 56, gray=0.30)
            elif "check" in it:
                put_mark(it["check"], "3", x=x + 4)
            elif "cross" in it:
                put_mark(it["cross"], "7", x=x + 4)
            elif "bullet" in it:
                put_mark(it["bullet"], "l", x=x + 4)   # dingbat small square
            elif "gauge" in it:
                put_gauge(it["gauge"], x=x + 4,
                          label=it.get("label", "Overall evidence confidence"))
            elif "bar" in it:
                put_bar(it["bar"], it["text"], x=x + 4)
            elif "tree" in it:
                put_tree(it["tree"], x=x + 16)
            elif "box" in it:
                put_box(it["box"], x=x + 4)

    def first_item_height(items):
        """Height of the first element, so a section heading is never left
        stranded at the foot of a page ('keep with next')."""
        if not items:
            return 0
        it = items[0]
        if isinstance(it, dict):
            if "tree" in it:
                return len(it["tree"]) * 2 * lh + 10
            if "gauge" in it:
                return 3 * lh + 14
            if "box" in it:
                return min(measure(it["box"], x=64) * lh + 16, top - bottom - lh)
            if "bar" in it:
                return 2 * lh + 8
        return len(_wrap(str(_item_text(it)[0] if _item_text(it) else ""))) * lh

    put(title, font="F2", size=16)
    y -= 8
    for sec_title in sections:
        y -= 6
        items = sections[sec_title]
        ensure(min(2 * lh + first_item_height(items), top - bottom - lh))
        put(sec_title, font="F2", size=13)
        y -= 2
        render_items(items)
    newpage()

    def enc(s: str) -> bytes:
        return s.encode("cp1252", errors="replace")

    n_pages = len(pages)
    objs = {}  # obj number -> bytes body
    objs[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n_pages))
    objs[2] = enc(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>")
    objs[3] = (b"<< /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >> "
               b"/F2 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >> "
               b"/F3 << /Type /Font /Subtype /Type1 /BaseFont /ZapfDingbats >> >>")
    for i, page in enumerate(pages):
        pnum, cnum = 4 + 2 * i, 5 + 2 * i
        stream = enc("\n".join(page))
        objs[pnum] = enc(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                         f"/Resources << /Font 3 0 R >> /Contents {cnum} 0 R >>")
        objs[cnum] = enc(f"<< /Length {len(stream)} >>\nstream\n") + stream + b"\nendstream"

    buf = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objs):
        offsets[num] = len(buf)
        buf += f"{num} 0 obj\n".encode() + objs[num] + b"\nendobj\n"
    xref_at = len(buf)
    n_objs = max(objs) + 1
    buf += f"xref\n0 {n_objs}\n0000000000 65535 f \n".encode()
    for num in range(1, n_objs):
        buf += f"{offsets[num]:010d} 00000 n \n".encode()
    buf += (f"trailer\n<< /Size {n_objs} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF"
            .encode())
    Path(out_path).write_bytes(bytes(buf))


def flatten_sections(sections: dict) -> str:
    """Every human-readable string in the report, including section titles
    and text nested inside boxes/gauges/bars/trees. This is what the walls
    and the claim audit run against — a visual element must never become a
    place where an unchecked claim can hide."""
    out = []
    for title, items in sections.items():
        out.append(title)
        for it in items:
            out.extend(_item_text(it))
    return "\n".join(out)


def render_premortem_pdf(decision_text: str, context, result, out_path,
                         title: str = "Pre-Mortem Report",
                         generated_at: str = None,
                         decision_service=None) -> dict:
    """The C2 entry point: PremortemResult -> productized PDF. Returns the
    section dict that was rendered (for callers/tests). `decision_service`
    (T011 Slice 2A): read-only Decision Record wiring, see
    build_premortem_sections."""
    sections = build_premortem_sections(decision_text, context, result,
                                        generated_at=generated_at,
                                        decision_service=decision_service)
    flat = flatten_sections(sections)
    assert_language_walls(flat)
    _assert_no_accuracy_claim(flat)
    write_pdf(sections, out_path, title=title)
    return sections


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", default=None)
    args = ap.parse_args(argv)
    in_path = Path(args.input)
    out_path = Path(args.output) if args.output else in_path.with_suffix(".founder.html")
    out_path.write_text(render(parse_report(in_path.read_text())))
    print(f"founder report written: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
