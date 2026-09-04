"""The frozen PRE-100 result, computed from the rows rather than narrated.

TWO RULES THIS FILE EXISTS TO ENFORCE.

  * Ten companies do not owe ten theses. A duplicate is a defect only when
    the companies do not share the mechanism the reading rests on, so
    duplicates are GROUPED and printed for judgement rather than counted as
    failures.
  * No aggregate may be more precise than the rows. A field the harness did
    not record prints as `--`, never as a zero.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics


def pct(n, d):
    return "--" if not d else f"{100.0 * n / d:.0f}%"


def quant(values, q):
    vals = sorted(v for v in values if isinstance(v, (int, float)))
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    idx = min(len(vals) - 1, int(round(q * (len(vals) - 1))))
    return vals[idx]


def cell(v, width=None):
    s = "--" if v in (None, "", []) else str(v)
    return s if width is None else s[:width]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--autocomplete", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    rows = json.loads(pathlib.Path(args.results).read_text("utf-8"))
    lines = []

    def out(s=""):
        lines.append(s)
        print(s)

    # ---- §25 the matrix --------------------------------------------------
    out("| Company | AC ms | Canonical identity | Business model | "
        "Elig | Chosen pattern | Ack s | CORE s | QA-ready s | Docs | Roles | "
        "Prov | Q&A | Timer | Leak | Result |")
    out("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        out(f"| {cell(r.get('company'))} | {cell(r.get('suggest_ms'))} | "
            f"{cell(r.get('chosen_identity'), 34)} | "
            f"{cell(r.get('business_model'))} | "
            f"{len(r.get('eligible_patterns') or []) or '--'} | "
            f"{cell(r.get('chosen_pattern'))} | "
            f"{cell(r.get('submit_ack_s'))} | {cell(r.get('core_ready_s'))} | "
            f"{cell(r.get('strategic_qa_ready_s'))} | "
            f"{cell(r.get('documents'))} | {cell(r.get('roles_filled'))} | "
            f"{'yes' if r.get('provenance_has_sources') else 'no'} | "
            f"{cell(r.get('qa_ok'))} | "
            f"{'yes' if r.get('timer_shown') else 'no'} | "
            f"{len(r.get('leaks') or [])} | {cell(r.get('result'))} |")

    # ---- §18 thesis audit ------------------------------------------------
    out()
    out("### Thesis audit")
    groups: dict = {}
    for r in rows:
        key = (r.get("headline_thesis") or "").strip()
        if key:
            groups.setdefault(key, []).append(r)
    out(f"- distinct headline theses: {len(groups)} across "
        f"{sum(len(v) for v in groups.values())} readings")
    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    out(f"- duplicated thesis groups: {len(dupes)}")
    for text, members in dupes.items():
        names = ", ".join(m.get("company") for m in members)
        models = {m.get("business_model") for m in members}
        patterns = {m.get("chosen_pattern") for m in members}
        out(f"  - **{names}** — models {sorted(models)}, "
            f"patterns {sorted(patterns)}")
        out(f"    > {text[:300]}")
        out("    SHARED MECHANISM? "
            + ("plausible — one business-model class and one pattern"
               if len(models) == 1 and len(patterns) == 1
               else "REVIEW — different classes or patterns reached one text"))
    mech = [r for r in rows if (r.get("mechanism") or "").strip()]
    out(f"- company-specific mechanism present: "
        f"{len(mech)}/{len(rows)} ({pct(len(mech), len(rows))})")
    unknown = [r.get("company") for r in rows
               if (r.get("business_model") or "UNKNOWN") == "UNKNOWN"]
    out(f"- classification reached the gate: "
        f"{len(rows) - len(unknown)}/{len(rows)}"
        + (f"; UNKNOWN: {unknown}" if unknown else ""))

    # ---- §26 aggregates --------------------------------------------------
    out()
    out("### Aggregates")
    ac = [r.get("suggest_ms") for r in rows if r.get("suggest_ms")]
    out(f"- autocomplete: median={quant(ac, 0.5)}ms p90={quant(ac, 0.9)}ms "
        f"(n={len(ac)})")
    core = [r.get("core_ready_s") for r in rows if r.get("core_ready_s")]
    out(f"- CORE: p50={quant(core, 0.5)}s p90={quant(core, 0.9)}s "
        f"max={max(core) if core else '--'}s "
        f"<=120s {pct(sum(1 for c in core if c <= 120), len(core))} "
        f"(n={len(core)})")
    qa_ready = [r.get("strategic_qa_ready_s") for r in rows
                if r.get("strategic_qa_ready_s")]
    out(f"- strategic Q&A ready: p50={quant(qa_ready, 0.5)}s "
        f"p90={quant(qa_ready, 0.9)}s (n={len(qa_ready)})")
    docs = [r.get("documents") for r in rows
            if isinstance(r.get("documents"), int)]
    out(f"- evidence: median documents="
        f"{statistics.median(docs) if docs else '--'}; "
        f"all-three-roles "
        f"{pct(sum(1 for r in rows if r.get('roles_filled') == 3), len(rows))}"
        f"; provenance "
        f"{pct(sum(1 for r in rows if r.get('provenance_has_sources')), len(rows))}")
    answered = [a for r in rows for a in (r.get("qa") or [])]
    ok = [a for a in answered if a.get("status") == 200 and not a.get("leaks")
          and a.get("names_company")]
    out(f"- Q&A: {len(ok)}/{len(answered)} substantive-and-owned "
        f"({pct(len(ok), len(answered))})")
    # A REPORT THAT NAMES NO COUNTER-ACCOUNT IS NOT THE SAME AS ONE THAT SAYS
    # IT LOOKED AND FOUND NONE. Only the missing section is a defect.
    counter: dict = {}
    for r in rows:
        counter[r.get("counterevidence") or "--"] = \
            counter.get(r.get("counterevidence") or "--", 0) + 1
    out(f"- counterevidence: " + ", ".join(
        f"{k}={v}" for k, v in sorted(counter.items())))
    terminal = [r for r in rows if r.get("result") in
                ("FULL_REPORT", "BOUNDED_ABSTENTION")]
    out(f"- terminal: {len(terminal)}/{len(rows)}")
    out(f"- identity bound: "
        f"{sum(1 for r in rows if r.get('autocomplete_found'))}/{len(rows)}")
    out(f"- foreign company on a report: "
        f"{sum(1 for r in rows if r.get('foreign_companies'))}")
    out(f"- spinner after terminal: "
        f"{sum(1 for r in rows if r.get('spinner_after_terminal'))}")
    out(f"- internal vocabulary leaks: "
        f"{sum(len(r.get('leaks') or []) for r in rows)}")
    out(f"- rows with defects: "
        f"{sum(1 for r in rows if r.get('defects'))}/{len(rows)}")
    for r in rows:
        for d in r.get("defects", []):
            out(f"  - {r.get('company')}: {d}")

    if args.autocomplete:
        proofs = json.loads(pathlib.Path(args.autocomplete).read_text("utf-8"))
        out()
        out("### Autocomplete prefix proof")
        for p in proofs:
            out(f"- `{p['typed']}` -> {p['best_match'] or '(none)'} "
                f"({p['ms']}ms, score {p['score']}, "
                f"{'OK' if p['resolves'] else 'MISS'})")
        ms = [p["ms"] for p in proofs]
        out(f"- median={quant(ms, 0.5)}ms p90={quant(ms, 0.9)}ms")

    if args.out:
        pathlib.Path(args.out).write_text("\n".join(lines) + "\n", "utf-8")
        print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
