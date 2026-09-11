#!/usr/bin/env python3
"""Turn the frozen matrix into the qualification documents.

Reads what was persisted and formats it. It DECIDES nothing that the scorer
did not already decide, so a document can be regenerated from a frozen run
without touching the run.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEN = ["Highspot", "BigID", "Cyera", "Monte Carlo Data", "Veeam", "Druva",
       "Slalom", "Sigma Computing", "ZoomInfo", "Point B"]


def mark(v):
    return {"PASS": "PASS", "ABSTAIN": "ABSTAIN", "FAIL": "**FAIL**"}.get(v, v)


def three(row):
    return "".join("Y" if row.get(k) else "N" for k in
                   ("profile_available", "lens_available",
                    "decision_reading_available"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results",
                    default="docs/ADAPTIVE_STRATEGIC_INTELLIGENCE_RESULTS.json")
    ap.add_argument("--matrix", default="reports/adaptive_ten_matrix.json")
    ap.add_argument("--genericity",
                    default="reports/adaptive_genericity_matrix.json")
    ap.add_argument("--outdir", default="docs")
    a = ap.parse_args()

    res = json.loads((ROOT / a.results).read_text())
    raw = json.loads((ROOT / a.matrix).read_text())
    rows = {r["company"]: r for r in raw.get("rows", [])}
    scored = {r["company"]: r for r in res.get("rows", [])}
    outdir = ROOT / a.outdir

    # ---- the ten-company table ------------------------------------------
    head = ("| Company | Identity | Profile | Lens | Diff | Decision/Abst | "
            "Evidence | Chain | CEO | Strategy | Q&A | Follow-up | Result |")
    sep = "|" + "---|" * 13
    lines = [head, sep]
    for name in TEN:
        s = scored.get(name)
        if s is None:
            lines.append(f"| {name} | — | — | — | — | — | — | — | — | — | — "
                         f"| — | *not run* |")
            continue
        g = s["gates"]
        r = rows.get(name, {})
        lines.append(
            f"| {name} | {mark(g['identity'])} | {mark(g['company_profile'])} "
            f"| {mark(g['strategic_lens'])} | {mark(g['differentiation'])} "
            f"| {mark(g['thesis_or_abstention'])} | {mark(g['evidence'])} "
            f"| {mark(g['causal_chain'])} | {mark(g['ceo_role'])} "
            f"| {mark(g['strategy_role'])} | {mark(g['qa'])} "
            f"| {mark(g['followup'])} | **{s['result']}** |")

    # ---- detail ----------------------------------------------------------
    detail = ["", "### Per company", "",
              "| Company | P/L/D | model | source | lens | state | chain | "
              "spec | quotes | leaks | Q&A | CORE |", "|" + "---|" * 12]
    for name in TEN:
        r = rows.get(name)
        if r is None:
            continue
        detail.append(
            f"| {name} | `{three(r)}` | {r.get('business_model','—')} "
            f"| {r.get('profile_source','—')} | {r.get('primary_lens') or '—'} "
            f"| {r.get('decision_map_state','—')} "
            f"| {r.get('causal_chain_kind','—')} "
            f"| {r.get('specificity',0)} | {r.get('quote_count',0)}"
            f"{' (' + str(len(r.get('broken_quotes') or ())) + ' broken)' if (r.get('broken_quotes')) else ''} "
            f"| {len(r.get('leaks') or ())} | {r.get('qa_ok',0)}/6 "
            f"| {r.get('core_s','—')}s |")

    tal = res.get("gate_tallies", {})

    def tally(gate):
        b = tal.get(gate, {})
        return b.get("PASS", 0), b.get("ABSTAIN", 0), b.get("FAIL", 0)

    n = len(scored)
    verdict = ["", "### Numeric verdict", "", "```"]
    for label, gate in (("IDENTITY", "identity"),
                        ("PROFILE", "company_profile"),
                        ("PROFILE_AVAILABLE", "profile_available"),
                        ("LENS_AVAILABLE", "lens_available"),
                        ("DECISION_READING_AVAILABLE",
                         "decision_reading_available"),
                        ("STRATEGIC_LENS", "strategic_lens"),
                        ("WHY_THIS_COMPANY", "differentiation"),
                        ("DECISION_OR_DEFENSIBLE_ABSTENTION",
                         "thesis_or_abstention"),
                        ("CAUSAL_OR_INVESTIGATION", "causal_chain"),
                        ("EVIDENCE", "evidence"),
                        ("COUNTEREVIDENCE_OR_LIMITATION", "counterevidence"),
                        ("DECISION_VALUE", "decision_value"),
                        ("CEO_ROLE", "ceo_role"),
                        ("STRATEGY_ROLE", "strategy_role"),
                        ("QA", "qa"), ("FOLLOWUP_CONTEXT", "followup"),
                        ("NO_PRODUCT_DEFECT", "no_product_defect")):
        p, ab, f = tally(gate)
        extra = (f"   ({ab} defensible abstention)" if ab else "")
        extra += (f"   ({f} FAIL)" if f else "")
        verdict.append(f"{label + ':':36s}{p + ab}/{n}{extra}")
    qa_total = sum(r.get("qa_ok", 0) for r in rows.values())
    fu = sum(1 for r in rows.values() if r.get("followup_pass"))
    verdict += [f"{'QA_ANSWERS:':36s}{qa_total}/{6 * n}",
                f"{'FOLLOWUP:':36s}{fu}/{n}"]
    leaks = sum(len(r.get("leaks") or ()) for r in rows.values())
    broken = sum(len(r.get("broken_quotes") or ()) for r in rows.values())
    spin = sum(1 for r in rows.values() if r.get("spinner_after_terminal"))
    gen = {}
    gp = ROOT / a.genericity
    if gp.exists():
        gen = json.loads(gp.read_text())
    verdict += ["",
                f"{'RAW_ENUM/INTERNAL_TERM_LEAKS:':36s}{leaks}",
                f"{'ATTRIBUTION/SPAN_DEFECTS:':36s}{broken}",
                f"{'UNEXPLAINED_TEMPLATE_COLLAPSES:':36s}"
                f"{gen.get('collapses', 'n/a')}",
                f"{'PAIRS FLAGGED FOR INSPECTION:':36s}"
                f"{gen.get('inspect', 'n/a')}",
                f"{'ENDLESS_SPINNERS:':36s}{spin}", "```"]

    cores = [r["core_s"] for r in rows.values() if r.get("core_s")]
    perf = ["", "### Performance", "",
            "| metric | value |", "|---|---|"]
    if cores:
        srt = sorted(cores)
        p90 = srt[min(len(srt) - 1, int(round(0.9 * (len(srt) - 1))))]
        perf += [f"| CORE p50 | {statistics.median(cores):.1f}s |",
                 f"| CORE p90 | {p90:.1f}s |",
                 f"| CORE max | {max(cores):.1f}s |"]
    text = ("# Adaptive Strategic Intelligence — final ten-company matrix\n\n"
            f"Frozen SHA: `{raw.get('live_commit') or 'unrecorded'}`  \n"
            f"Service: {raw.get('base', '')}\n\n"
            + "\n".join(lines + detail + verdict + perf) + "\n")
    (outdir / "ADAPTIVE_STRATEGIC_INTELLIGENCE_MATRIX.md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
