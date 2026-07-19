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
