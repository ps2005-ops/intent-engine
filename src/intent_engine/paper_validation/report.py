"""Render the report's tables from the replay summary and the ledgers.

The numbers in REPORT.md are generated here from committed artifacts, not
typed, so a reader can regenerate every table and diff it against the page:

    PYTHONPATH=src python -m intent_engine.paper_validation.report
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import List

from intent_engine.paper_validation import ledger as LG

SUMMARY = pathlib.Path("reports/paper_validation/replay/summary.json")
ORDER = ("buy_and_hold", "cash", "tsmom_12_1", "reversal_1m",
         "econ_factor_credit", "ie_market_momentum", "ie_econ_transmission",
         "ie_econ_bayes", "logit_A", "logit_B", "logit_D", "random_control",
         "permutation_control", "shuffled_label_control")


def _f(x, fmt="+.2f"):
    return "n/a" if x is None else format(x, fmt)


def _ci(c, fmt="+.2f"):
    if not c or c[0] is None:
        return ""
    return f"[{format(c[0], fmt)}, {format(c[1], fmt)}]"


def book_table(u: dict) -> List[str]:
    out = ["| policy | provenance | net Sharpe [95% CI] | gross Sharpe | "
           "ann. excess return | vol | max DD | turnover | cost drag/yr | "
           "abstain | vs buy-and-hold Sharpe [CI] | Holm p |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    holm = u["holm"]["sharpe_vs_benchmark"]
    for pid in ORDER:
        v = u["policies"].get(pid)
        if not v:
            continue
        b = v["book"]
        vs = v.get("vs_benchmark", {})
        out.append(
            f"| {pid} | {v['provenance']} | {_f(b.get('sharpe'))} "
            f"{_ci(b.get('sharpe_ci'))} | {_f(b.get('gross_sharpe'))} | "
            f"{_f(b.get('ann_return'), '+.1%')} | {_f(b.get('ann_vol'), '.1%')}"
            f" | {_f(b.get('max_drawdown'), '.0%')} | "
            f"{_f(b.get('turnover'), '.2f')} | "
            f"{_f(b.get('cost_drag_annual'), '.2%')} | "
            f"{v['abstention_rate']:.0%} | {_f(vs.get('diff'))} "
            f"{_ci(vs.get('ci'))} | "
            f"{_f(holm.get(pid), '.3f') if pid in holm else '-'} |")
    return out


def forecast_table(u: dict) -> List[str]:
    out = ["| policy | forecasts | traded | hit rate [CI] | avg win | "
           "avg loss | EV/trade net [CI] | Brier | Brier (climatology) | "
           "Brier skill [CI] | log loss | calib. slope | Holm p (skill>0) |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    holm = u["holm"]["brier_skill"]
    for pid in ORDER:
        v = u["policies"].get(pid)
        if not v:
            continue
        f, t = v["forecast"], v["trades"]
        if not f.get("forecasts") and not t.get("traded"):
            continue
        out.append(
            f"| {pid} | {f.get('forecasts', 0)} | {t.get('traded', 0)} | "
            f"{_f(t.get('hit_rate'), '.3f')} {_ci(t.get('hit_rate_ci'), '.3f')}"
            f" | {_f(t.get('avg_win'), '+.2%')} | {_f(t.get('avg_loss'), '+.2%')}"
            f" | {_f(t.get('ev_per_trade'), '+.2%')} "
            f"{_ci(t.get('ev_ci'), '+.2%')} | {_f(f.get('brier'), '.4f')} | "
            f"{_f(f.get('brier_clim'), '.4f')} | "
            f"{_f(f.get('brier_skill'), '+.4f')} "
            f"{_ci(f.get('brier_skill_ci'), '+.4f')} | "
            f"{_f(f.get('log_loss'), '.4f')} | "
            f"{_f(f.get('calibration_slope'), '.2f')} | "
            f"{_f(holm.get(pid), '.3f') if pid in holm else '-'} |")
    return out


def regime_table(u: dict) -> List[str]:
    out = ["| policy | CALM periods | CALM Sharpe [CI] | CALM hit | "
           "STRESS periods | STRESS Sharpe [CI] | STRESS hit |",
           "|---|---|---|---|---|---|---|"]
    for pid in ORDER:
        v = u["policies"].get(pid)
        if not v or pid == "cash":
            continue
        c, s = v["by_regime"]["CALM"], v["by_regime"]["STRESS"]
        out.append(f"| {pid} | {c['periods']} | {_f(c.get('sharpe'))} "
                   f"{_ci(c.get('sharpe_ci'))} | {_f(c.get('hit_rate'), '.3f')}"
                   f" | {s['periods']} | {_f(s.get('sharpe'))} "
                   f"{_ci(s.get('sharpe_ci'))} | "
                   f"{_f(s.get('hit_rate'), '.3f')} |")
    return out


def ablation_table(u: dict) -> List[str]:
    out = ["| comparison (new vs reference, same rows) | dates | forecasts | "
           "Brier new | Brier ref | skill of new over ref [CI] | p (skill<=0) |",
           "|---|---|---|---|---|---|---|"]
    for k, v in u["ablation"].items():
        if not isinstance(v, dict):
            out.append(f"| {k} | - | - | - | - | {v} | - |")
            continue
        out.append(f"| {k} | {v.get('n_dates')} | {v.get('n_forecasts')} | "
                   f"{_f(v.get('brier'), '.4f')} | {_f(v.get('brier_ref'), '.4f')}"
                   f" | {_f(v.get('skill'), '+.4f')} "
                   f"{_ci(v.get('skill_ci'), '+.4f')} | "
                   f"{_f(v.get('p_one_sided'), '.3f')} |")
    return out


def controls_table(u: dict) -> List[str]:
    out = ["| comparison | Sharpe diff [CI] | ann. return diff [CI] | "
           "p (return diff<=0) |", "|---|---|---|---|"]
    for k, v in sorted(u.get("controls", {}).items()):
        if not any(k.startswith(p) for p in ("ie_", "econ_factor", "logit_",
                                             "tsmom", "reversal", "buy")):
            continue
        s, r = v["sharpe"], v["return"]
        out.append(f"| {k} | {_f(s['diff'])} {_ci(s['ci'])} | "
                   f"{_f(r['ann_return_diff'], '+.2%')} "
                   f"{_ci(r['ci'], '+.2%')} | {_f(r['p_one_sided'], '.3f')} |")
    return out


def reliability_table(u: dict, pid: str) -> List[str]:
    rel = u["policies"][pid]["forecast"].get("reliability") or []
    out = [f"| {pid} bin | n | mean p | observed | Wilson 95% (per forecast) |",
           "|---|---|---|---|---|"]
    for r in rel:
        out.append(f"| {r['bin']} | {r['n']} | {r['mean_p']:.3f} | "
                   f"{r['observed']:.3f} | [{r['wilson_low']:.3f}, "
                   f"{r['wilson_high']:.3f}] |")
    return out


def diagnostics_table(d: dict) -> List[str]:
    out = ["| family | train / test rows | test Brier of train base rate | "
           "set | in-sample Brier at L2 0.1 -> 1000 | out-of-sample Brier at "
           "L2 0.1 -> 1000 |", "|---|---|---|---|---|---|"]
    for fam, c in d["families"].items():
        for s in ("A", "B", "D"):
            ins = " / ".join(f"{r['in_sample']:.4f}" for r in c[s])
            oos = " / ".join(f"{r['out_of_sample']:.4f}" for r in c[s])
            out.append(f"| {fam} | {c['n_train']} / {c['n_test']} | "
                       f"{c['test_brier_train_base_rate']:.4f} | {s} | {ins} | "
                       f"{oos} |")
    return out


def ledger_lines() -> List[str]:
    out = []
    for path, kind in (("reports/paper_validation/forward_shadow_ledger.jsonl",
                        LG.FORWARD_SHADOW),
                       ("reports/paper_validation/rehearsal_ledger.jsonl",
                        LG.REHEARSAL)):
        p = pathlib.Path(path)
        if not p.exists():
            out.append(f"- `{path}`: absent")
            continue
        s = LG.summary(LG.Ledger(p, kind))
        out.append(f"- `{path}` ({kind}): {s['entries']} chained entries, "
                   f"{s['forecasts']} forecasts, by status {s['by_status']}")
    return out


def render(summary: dict) -> str:
    lines = [f"Protocol hash `{summary['protocol_hash']}`; common window from "
             f"{summary['window_start']}.", ""]
    for uni in ("etf", "company"):
        u = summary["universes"][uni]
        lines += [f"#### {uni.upper()} universe: {u['dates']} decision dates "
                  f"({u['first']} .. {u['last']}), {u['instruments']} "
                  "instruments", "", "Books (net of costs):", ""]
        lines += book_table(u) + ["", "Forecasts and trades:", ""]
        lines += forecast_table(u) + ["", "By regime at the decision "
                                      "(econ.regime, point in time):", ""]
        lines += regime_table(u) + ["", "Ablation (paired, same rows):", ""]
        lines += ablation_table(u) + ["", "Controls (paired, same dates):", ""]
        lines += controls_table(u) + [""]
        if uni == "company":
            a = u["abstention_quality"]
            lines += [f"Econ flag separation: flagged on {a['flag_share']:.0%} "
                      f"of company-dates; flagged minus unflagged mean "
                      f"relative return {a['flagged_minus_unflagged_mean']:+.2%}"
                      f" per period, 95% CI {_ci(a['ci'], '+.2%')}, over "
                      f"{a['dates_with_both']} dates with both groups "
                      f"(the engine's claim needs this NEGATIVE).", ""]
    lines += ["Reliability, logit_A (ETF):", ""]
    lines += reliability_table(summary["universes"]["etf"], "logit_A") + [""]
    lines += ["Post-hoc specification diagnostic (not used by any policy):", ""]
    lines += diagnostics_table(summary["diagnostics"]) + [""]
    lines += ["Ledgers:", ""] + ledger_lines()
    g = summary["guards"]
    lines += ["", f"Guards: oracle canary refused {g['canary']['refused']}/"
              f"{g['canary']['checked']} dates; truncation checks "
              f"{g['truncation']['checked']} with "
              f"{g['truncation']['violations']} violations; "
              f"{g['voids']} voided cells."]
    return "\n".join(lines)


BEGIN = "<!-- BEGIN GENERATED TABLES (report.py --splice) -->"
END = "<!-- END GENERATED TABLES -->"
REPORT = pathlib.Path("docs/engineering/paper_validation/REPORT.md")


def splice(report=REPORT) -> None:
    """Replace the generated section of REPORT.md with freshly rendered
    tables, leaving the hand-written narrative around it untouched."""
    text = pathlib.Path(report).read_text(encoding="utf-8")
    head, rest = text.split(BEGIN, 1)
    _old, tail = rest.split(END, 1)
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    pathlib.Path(report).write_text(
        head + BEGIN + "\n\n" + render(summary) + "\n\n" + END + tail,
        encoding="utf-8")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--splice" in argv:
        splice()
        return 0
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    sys.stdout.write(render(summary) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
