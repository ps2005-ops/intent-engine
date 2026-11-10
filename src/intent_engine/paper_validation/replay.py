"""Walk-forward historical replay. Reported SEPARATELY from forward results.

ORDER OF OPERATIONS, PER DECISION DATE
--------------------------------------
1. every policy decides from that date's rows and the outcomes resolved by
   then (`History.resolved(d)` returns rows whose EXIT is on or before d);
2. every decision's evidence ids go through `leakage.check_evidence`;
3. the oracle canary goes through the same check and must be refused, or
   the replay stops: results from an unguarded path are not results;
4. a sample of rows is recomputed on truncated bars (truncation invariance).

Then each policy's book is executed: position in {-1, 0, +1} per
instrument, cost on the change in position, borrow on shorts (and on both
legs' short side for company pairs), book return = mean over instruments.

WHAT A REPLAY CANNOT SHOW
-------------------------
That nothing was fitted to this history. The rules and thresholds were
declared before this ran (protocol hash in the output), but the universe was
chosen in 2026 and the engine's transmission table was written after 2008
had happened. The forward ledger is the only evidence free of that.
"""
from __future__ import annotations

import bisect
import csv
import gzip
import json
import math
import pathlib
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from intent_engine.paper_validation import bars as BR
from intent_engine.paper_validation import features as F
from intent_engine.paper_validation import leakage as LK
from intent_engine.paper_validation import macro as M
from intent_engine.paper_validation import metrics as MT
from intent_engine.paper_validation import observations as OB
from intent_engine.paper_validation import policies as PL
from intent_engine.paper_validation import universe as U
from intent_engine.paper_validation.protocol import (BORROW_BPS_YEAR,
                                                     PROTOCOL,
                                                     declaration_hash)

OUT_DIR = pathlib.Path("reports/paper_validation/replay")
BPS = 1e-4


class History:
    def __init__(self, rows: Sequence[OB.Obs]):
        self._rows = sorted((o for o in rows if o.resolved),
                            key=lambda o: o.exit_date)
        self._exits = [o.exit_date for o in self._rows]

    def resolved(self, d: str) -> List[OB.Obs]:
        return self._rows[:bisect.bisect_right(self._exits, d)]


@dataclass
class Row:
    policy: str
    universe: str
    family: str
    symbol: str
    decision_date: str
    exit_date: str
    direction: str
    probability: Optional[float]
    p_clim: float
    excess: float
    y: int
    regime_label: str
    regimes: Tuple[str, ...]
    abstention_reason: str
    flagged: bool


def _slippage() -> float:
    from intent_engine.market.costs import DEFAULT
    return DEFAULT.slippage_bps_per_side + DEFAULT.commission_bps


def run(*, bars: Dict[str, BR.Bars], panel, etfs, companies, profiles,
        anchor: str = PROTOCOL["replay"]["anchor"], through: str = "",
        policies: Optional[List[PL.Policy]] = None,
        log=print) -> dict:
    t0 = time.time()
    spy = bars[U.BENCHMARK]
    dates = [s for s in OB.schedule(spy, anchor=anchor, through=through or None)
             if s[3]]                                  # only completed windows
    log(f"replay: {len(dates)} decision dates {dates[0][1]}..{dates[-1][1]}")
    rows, voids = OB.build(bars=bars, instruments=list(etfs) + list(companies),
                           panel=panel, dates=dates, profiles=profiles,
                           log=log)
    rows = [o for o in rows if o.resolved]
    log(f"replay: {len(rows)} resolved observations, {len(voids)} voided "
        f"({time.time() - t0:.0f}s)")
    history = History(rows)
    by_date: Dict[str, List[OB.Obs]] = {}
    for o in rows:
        by_date.setdefault(o.decision_date, []).append(o)

    policies = policies or PL.registry()
    for p in policies:
        if isinstance(p, PL.IEMarketMomentum):
            p.bind(bars)
        p.begin(rows)

    out_rows: List[Row] = []
    canaries = {"checked": 0, "refused": 0}
    trunc = {"checked": 0, "violations": 0}
    leaks: List[str] = []
    for d in sorted(by_date):
        drows = by_date[d]
        # the canary, through the same checker every policy goes through
        c0 = drows[0]
        canary = LK.oracle_canary(c0.symbol, d, c0.exit_date, c0.excess)
        canaries["checked"] += 1
        if LK.canary_refused(canary):
            canaries["refused"] += 1
        # truncation invariance on one ETF and one company per date
        for o in drows[:1] + [x for x in drows if x.universe == U.COMPANY][:1]:
            b = bars[o.symbol]
            t = b.index_of(d)
            trunc["checked"] += 1
            if o.universe == U.ETF:
                ok = LK.truncation_invariant(F.price_features, b, t)
            else:
                ok = LK.truncation_invariant_relative(b, t, spy, d)
            if not ok:
                trunc["violations"] += 1
        for uni in (U.ETF, U.COMPANY):
            urows = [o for o in drows if o.universe == uni]
            if not urows:
                continue
            for p in policies:
                if not p.applies(uni):
                    continue
                decisions = p.decide_date(urows, history)
                for o, dec in zip(urows, decisions):
                    try:
                        LK.check_evidence(dec.evidence_ids, d)
                    except LK.LeakDetected as exc:
                        leaks.append(f"{p.policy_id} {o.symbol} {d}: {exc}")
                        continue
                    out_rows.append(Row(
                        p.policy_id, uni, o.family, o.symbol, d, o.exit_date,
                        dec.direction, dec.probability, o.p_clim, o.excess,
                        o.y, o.regime_label, o.regimes, dec.abstention_reason,
                        bool((o.econ or {}).get("adverse"))))
    if canaries["refused"] != canaries["checked"]:
        raise LK.LeakDetected(
            f"the oracle canary passed the leak checker on "
            f"{canaries['checked'] - canaries['refused']} date(s); the "
            "checker is not live and no result of this run may be reported")
    if leaks:
        raise LK.LeakDetected(f"{len(leaks)} decisions used future inputs: "
                              f"{leaks[:3]}")
    if trunc["violations"]:
        raise LK.LeakDetected(f"{trunc['violations']} feature rows changed "
                              "when the future was deleted")
    log(f"replay: {len(out_rows)} decisions; canary refused "
        f"{canaries['refused']}/{canaries['checked']}; truncation checks "
        f"{trunc['checked']} ({time.time() - t0:.0f}s)")
    fit_logs = {p.policy_id: p.fit_log for p in policies
                if isinstance(p, PL.Logit)}
    return {"rows": out_rows, "obs": rows, "voids": voids,
            "canaries": canaries, "truncation": trunc, "fit_logs": fit_logs,
            "policies": policies, "dates": dates}


# --- books -------------------------------------------------------------------

def _pos(direction: str) -> int:
    return {"LONG": 1, "SHORT": -1}.get(direction, 0)


def book(rows: Sequence[Row], obs_days: Dict[Tuple[str, str], int],
         universe: str) -> dict:
    """Per-period net returns of one policy's book in one universe."""
    slip = _slippage() * BPS
    legs = PROTOCOL["execution"]["company_legs"] if universe == U.COMPANY else 1
    by_date: Dict[str, List[Row]] = {}
    for r in rows:
        by_date.setdefault(r.decision_date, []).append(r)
    prev: Dict[str, int] = {}
    dates, rets, turns, costs, gross = [], [], [], [], []
    for d in sorted(by_date):
        rs = by_date[d]
        n = len(rs)
        tot = turn = cost = g = 0.0
        for r in rs:
            p = _pos(r.direction)
            dp = abs(p - prev.get(r.symbol, 0))
            days = obs_days.get((r.symbol, d), 30)
            borrow = 0.0
            if universe == U.COMPANY and p != 0:
                borrow = BORROW_BPS_YEAR * BPS * days / 365.0
            elif p < 0:
                borrow = BORROW_BPS_YEAR * BPS * days / 365.0
            c = dp * slip * legs + borrow
            tot += p * r.excess - c
            g += p * r.excess
            turn += dp
            cost += c
        held = {r.symbol for r in rs}
        for sym in list(prev):
            if sym not in held and prev[sym] != 0:
                # an instrument that dropped out is closed at the next open
                tot -= abs(prev[sym]) * slip * legs
                cost += abs(prev[sym]) * slip * legs
                turn += abs(prev[sym])
        prev = {r.symbol: _pos(r.direction) for r in rs}
        dates.append(d)
        rets.append(tot / n)
        gross.append(g / n)
        turns.append(turn / n)
        costs.append(cost / n)
    return {"dates": dates, "returns": rets, "turnover": turns,
            "costs": costs, "gross": gross}


def _trades(rows: Sequence[Row], universe: str) -> dict:
    slip = _slippage() * BPS
    legs = PROTOCOL["execution"]["company_legs"] if universe == U.COMPANY else 1
    traded = [r for r in rows if r.direction in ("LONG", "SHORT")]
    if not traded:
        return {"traded": 0}
    hits = [(r.direction == "LONG") == (r.y == 1) for r in traded]
    net = [_pos(r.direction) * r.excess - 2 * slip * legs for r in traded]
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x <= 0]
    hit = MT.date_grouped_mean([r.decision_date for r in traded],
                               [1.0 if h else 0.0 for h in hits])
    ev = MT.date_grouped_mean([r.decision_date for r in traded], net)
    return {"traded": len(traded),
            "hit_rate": hit["mean"], "hit_rate_ci": hit["ci"],
            "avg_win": float(np.mean(wins)) if wins else None,
            "avg_loss": float(np.mean(losses)) if losses else None,
            "ev_per_trade": ev["mean"], "ev_ci": ev["ci"],
            "long_share": sum(1 for r in traded if r.direction == "LONG")
            / len(traded)}


def _forecast_scores(rows: Sequence[Row]) -> dict:
    fr = [r for r in rows if r.probability is not None]
    if not fr:
        return {"forecasts": 0}
    p = [r.probability for r in fr]
    y = [r.y for r in fr]
    bs = MT.date_grouped_brier_skill([r.decision_date for r in fr], p,
                                     [r.p_clim for r in fr], y)
    return {"forecasts": len(fr), "brier": MT.brier(p, y),
            "log_loss": MT.log_loss(p, y),
            "brier_clim": MT.brier([r.p_clim for r in fr], y),
            "log_loss_clim": MT.log_loss([r.p_clim for r in fr], y),
            "brier_skill": bs["skill"], "brier_skill_ci": bs["skill_ci"],
            "brier_skill_p": bs["p_one_sided"],
            "calibration_slope": MT.calibration_slope(p, y),
            "reliability": MT.reliability(p, y), "base_rate": float(np.mean(y))}


def summarise(result: dict, *, window_start: str =
              PROTOCOL["replay"]["common_window_start"]) -> dict:
    rows: List[Row] = [r for r in result["rows"]
                       if r.decision_date >= window_start]
    obs_days = {}
    import datetime as _dt
    for o in result["obs"]:
        obs_days[(o.symbol, o.decision_date)] = (
            _dt.date.fromisoformat(o.exit_date)
            - _dt.date.fromisoformat(o.entry_date)).days
    out = {"protocol_hash": declaration_hash(), "window_start": window_start,
           "universes": {}}
    pols = {p.policy_id: p for p in result["policies"]}
    for uni in (U.ETF, U.COMPANY):
        urows = [r for r in rows if r.universe == uni]
        all_dates = sorted({r.decision_date for r in urows})
        idx = MT.block_indices(len(all_dates))
        per: Dict[str, dict] = {}
        series: Dict[str, np.ndarray] = {}
        for pid, p in pols.items():
            if not p.applies(uni):
                continue
            prow = [r for r in urows if r.policy == pid]
            bk = book(prow, obs_days, uni)
            pos = {d: i for i, d in enumerate(bk["dates"])}
            r_full = np.array([bk["returns"][pos[d]] if d in pos else 0.0
                               for d in all_dates])
            series[pid] = r_full
            stats = MT.book_stats(r_full, idx)
            g_full = np.array([bk["gross"][pos[d]] if d in pos else 0.0
                               for d in all_dates])
            stats["gross_sharpe"] = MT.sharpe(g_full)
            stats["turnover"] = float(np.mean(bk["turnover"])) \
                if bk["turnover"] else 0.0
            stats["cost_drag_annual"] = float(np.mean(bk["costs"]) * MT.PPY) \
                if bk["costs"] else 0.0
            ab = [r for r in prow if r.direction == "ABSTAIN"]
            per[pid] = {"provenance": p.provenance, "feature_set": p.feature_set,
                        "decisions": len(prow), "abstained": len(ab),
                        "abstention_rate": len(ab) / len(prow) if prow else 0,
                        "book": stats, "trades": _trades(prow, uni),
                        "forecast": _forecast_scores(prow),
                        "by_regime": _by_regime(prow, bk, all_dates)}
        # Buy-and-hold is the benchmark in BOTH universes. In the company
        # universe it is long the 2026 survivors against SPY, which is exactly
        # the drift a survivorship-biased list hands every long-leaning
        # policy; a policy has to beat THAT, not zero, before its edge is its
        # own. Zero is reported beside it, labelled.
        bench = "buy_and_hold"
        for pid in per:
            per[pid]["vs_zero"] = MT.paired_sharpe_diff(
                series[pid], np.zeros(len(all_dates)), idx)
            if pid == bench:
                continue
            per[pid]["vs_benchmark"] = MT.paired_sharpe_diff(
                series[pid], series[bench], idx)
            per[pid]["vs_benchmark"]["benchmark"] = bench
            per[pid]["vs_benchmark_return"] = MT.paired_mean_diff(
                series[pid], series[bench], idx)
        controls = {}
        if uni == U.COMPANY and "permutation_control" in series:
            for pid in ("ie_econ_transmission", "ie_econ_bayes"):
                if pid in series:
                    controls[f"{pid}_vs_permutation_control"] = {
                        "sharpe": MT.paired_sharpe_diff(
                            series[pid], series["permutation_control"], idx),
                        "return": MT.paired_mean_diff(
                            series[pid], series["permutation_control"], idx)}
        if "random_control" in series:
            for pid in series:
                if pid not in ("random_control", "cash"):
                    controls[f"{pid}_vs_random_control"] = {
                        "sharpe": MT.paired_sharpe_diff(
                            series[pid], series["random_control"], idx),
                        "return": MT.paired_mean_diff(
                            series[pid], series["random_control"], idx)}
        out["universes"][uni] = {
            "controls": controls,
            "dates": len(all_dates),
            "first": all_dates[0] if all_dates else "",
            "last": all_dates[-1] if all_dates else "",
            "instruments": len({r.symbol for r in urows}),
            "policies": per,
            "holm": _holm(per),
            "ablation": _ablation(urows),
            "abstention_quality": _abstention_quality(urows, uni)}
    out["not_run"] = {p.policy_id: {"status": p.status,
                                    "reason": p.status_reason}
                      for p in result["policies"]
                      if p.status != PL.IMPLEMENTED}
    out["guards"] = {"canary": result["canaries"],
                     "truncation": result["truncation"],
                     "voids": len(result["voids"])}
    return out


def _by_regime(prow: Sequence[Row], bk: dict, all_dates) -> dict:
    lab = {}
    for r in prow:
        lab[r.decision_date] = r.regime_label
    pos = {d: i for i, d in enumerate(bk["dates"])}
    out = {}
    for label in ("CALM", "MIXED", "STRESS"):
        ds = [d for d in all_dates if lab.get(d) == label and d in pos]
        rr = np.array([bk["returns"][pos[d]] for d in ds])
        cell = {"periods": len(ds)}
        if len(ds) >= PROTOCOL["metrics"]["min_periods_for_regime_cell"]:
            cell.update({"ann_return": float(rr.mean() * MT.PPY),
                         "sharpe": MT.sharpe(rr),
                         "sharpe_ci": MT.ci(np.array(
                             [MT.sharpe(rr[i]) for i in
                              MT.block_indices(len(rr), draws=500)]))})
            tr = [r for r in prow if r.decision_date in set(ds)
                  and r.direction in ("LONG", "SHORT")]
            if tr:
                cell["hit_rate"] = float(np.mean(
                    [(r.direction == "LONG") == (r.y == 1) for r in tr]))
            fr = [r for r in prow if r.decision_date in set(ds)
                  and r.probability is not None]
            if fr:
                cell["brier"] = MT.brier([r.probability for r in fr],
                                         [r.y for r in fr])
                cell["brier_clim"] = MT.brier([r.p_clim for r in fr],
                                              [r.y for r in fr])
        else:
            cell["note"] = "INSUFFICIENT"
        out[label] = cell
    return out


def _holm(per: Dict[str, dict]) -> dict:
    pv_sh = {k: v["vs_benchmark"]["p_one_sided"] for k, v in per.items()
             if "vs_benchmark" in v and v["provenance"] != PL.CONTROL}
    pv_bs = {k: v["forecast"]["brier_skill_p"] for k, v in per.items()
             if v["forecast"].get("forecasts") and v["provenance"] != PL.CONTROL}
    return {"sharpe_vs_benchmark": MT.holm(pv_sh),
            "brier_skill": MT.holm(pv_bs)}


def _ablation(urows: Sequence[Row]) -> dict:
    """Paired Brier comparisons on the rows BOTH arms forecast."""
    def keyed(pid):
        return {(r.symbol, r.decision_date): r for r in urows
                if r.policy == pid and r.probability is not None}
    arms = {a: keyed(a) for a in ("logit_A", "logit_B", "logit_D",
                                  "shuffled_label_control")}
    out = {}
    for new, ref in (("logit_B", "logit_A"), ("logit_D", "logit_B"),
                     ("logit_D", "logit_A"),
                     ("shuffled_label_control", "logit_B")):
        common = sorted(set(arms[new]) & set(arms[ref]))
        if not common:
            out[f"{new}_vs_{ref}"] = {"n": 0}
            continue
        a = [arms[new][k] for k in common]
        b = [arms[ref][k] for k in common]
        s = MT.date_grouped_brier_skill([k[1] for k in common],
                                        [r.probability for r in a],
                                        [r.probability for r in b],
                                        [r.y for r in a])
        out[f"{new}_vs_{ref}"] = s
    out["logit_C"] = "NOT_MEASURED: news/company-evidence provider PENDING"
    return out


def _abstention_quality(urows: Sequence[Row], uni: str) -> dict:
    """Does the econ flag separate outcomes? Flagged minus unflagged mean
    relative return, per date, then a block bootstrap over dates."""
    if uni != U.COMPANY:
        return {}
    by_date: Dict[str, List[Row]] = {}
    for r in urows:
        if r.policy == "ie_econ_transmission":
            by_date.setdefault(r.decision_date, []).append(r)
    diffs, dates, share = [], [], []
    for d, rs in sorted(by_date.items()):
        f = [r.excess for r in rs if r.flagged]
        u = [r.excess for r in rs if not r.flagged]
        share.append(len(f) / len(rs))
        if f and u:
            diffs.append(float(np.mean(f) - np.mean(u)))
            dates.append(d)
    if not diffs:
        return {"dates_with_both": 0, "flag_share": float(np.mean(share))
                if share else None}
    x = np.array(diffs)
    idx = MT.block_indices(len(x))
    return {"dates_with_both": len(x), "flag_share": float(np.mean(share)),
            "flagged_minus_unflagged_mean": float(x.mean()),
            "ci": MT.ci(x[idx].mean(axis=1)),
            "p_ge_zero": float((x[idx].mean(axis=1) >= 0).mean())}


def write(result: dict, summary: dict, out_dir=OUT_DIR) -> dict:
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dpath = out / "decisions.csv.gz"
    with open(dpath, "wb") as fh, gzip.GzipFile(filename="", mode="wb",
                                                fileobj=fh, mtime=0) as gz:
        import io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["policy", "universe", "family", "symbol", "decision_date",
                    "exit_date", "direction", "probability", "p_clim",
                    "excess", "y", "regime", "abstention_reason"])
        for r in result["rows"]:
            w.writerow([r.policy, r.universe, r.family, r.symbol,
                        r.decision_date, r.exit_date, r.direction,
                        "" if r.probability is None else f"{r.probability:.5f}",
                        f"{r.p_clim:.5f}", f"{r.excess:.6f}", r.y,
                        r.regime_label, r.abstention_reason])
        gz.write(buf.getvalue().encode("utf-8"))
    spath = out / "summary.json"
    spath.write_text(json.dumps(clean(summary), indent=1, sort_keys=True),
                     encoding="utf-8")
    fpath = out / "fit_log.json"
    fpath.write_text(json.dumps(result["fit_logs"], indent=1,
                                sort_keys=True), encoding="utf-8")
    return {"decisions": str(dpath), "summary": str(spath),
            "fit_log": str(fpath)}


def _json(o):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, tuple):
        return list(o)
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return str(o)


def clean(o):
    """JSON-safe: NaN and inf become null, numpy and tuples become Python."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if (math.isnan(f) or math.isinf(f)) else f
    return o


def diagnose_specification(result: dict, *, split: str = "2015-01-01") -> dict:
    """POST-HOC DIAGNOSTIC, never a result: is a losing model misspecified
    or overfitted? Sweep L2 over three orders of magnitude, train on outcomes
    known before `split`, test on decisions after it, per family, and read
    the IN-SAMPLE curve ([[misspecified-not-overfitted]]): flat in-sample
    means nothing to fit; in-sample improving while out-of-sample degrades
    means overfitting. No penalty chosen here feeds back into any policy."""
    from intent_engine.paper_validation import model as MD
    obs = result["obs"]
    out = {"label": "POST_HOC_DIAGNOSTIC (not used by any policy)",
           "split": split, "families": {}}
    for uni, sets in ((U.ETF, {"A": PL.A_ETF, "B": PL.B_ETF, "D": PL.D_ETF}),
                      (U.COMPANY, {"A": PL.A_CO, "B": PL.B_CO,
                                   "D": PL.D_CO})):
        for fam in U.families(uni):
            tr = [o for o in obs if o.universe == uni and o.family == fam
                  and o.exit_date < split]
            te = [o for o in obs if o.universe == uni and o.family == fam
                  and o.decision_date >= split]
            if len(tr) < 40 or not te:
                continue
            ytr = np.array([o.y for o in tr], float)
            yte = np.array([o.y for o in te], float)
            base = float(ytr.mean())
            cell = {"n_train": len(tr), "n_test": len(te),
                    "test_brier_train_base_rate":
                        float(((base - yte) ** 2).mean())}
            for name, names in sets.items():
                sweep = MD.l2_sweep(MD.matrix([o.feats for o in tr], names),
                                    ytr, names,
                                    MD.matrix([o.feats for o in te], names),
                                    yte)
                cell[name] = [{"l2": a, "in_sample": round(b, 5),
                               "out_of_sample": round(c, 5)}
                              for a, b, c in sweep]
            out["families"][f"{uni}/{fam}"] = cell
    return out
