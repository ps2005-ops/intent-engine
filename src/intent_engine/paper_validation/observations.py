"""One row per (decision date, instrument): what was knowable, and what happened.

Built ONCE and shared by the historical replay and the forward registration,
so the two can never compute "the features at date d" two different ways.
A forward row is the same object with no outcome.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from intent_engine.paper_validation import features as F
from intent_engine.paper_validation import macro as M
from intent_engine.paper_validation import universe as U
from intent_engine.paper_validation.bars import Bars
from intent_engine.paper_validation.protocol import CADENCE, HORIZON

COMPANY_ECON_NAMES = ("econ_adverse_count", "econ_favourable_count",
                      "econ_signed_channels")


@dataclass
class Obs:
    k: int
    decision_date: str
    entry_date: str
    exit_date: str
    symbol: str
    universe: str
    family: str
    signal_scope: str
    business_model_class: str
    feats: Dict[str, float]
    ev_price: List[str]
    ev_macro: List[str]
    ev_engine: List[str]
    macro_missing: Tuple[str, ...]
    regimes: Tuple[str, ...]
    regime_label: str
    rf: Optional[float]
    econ: Optional[dict] = None
    ret: Optional[float] = None
    excess: Optional[float] = None
    y: Optional[int] = None
    p_clim: float = 0.5
    defensive: bool = False

    @property
    def resolved(self) -> bool:
        return self.y is not None


def schedule(spy: Bars, *, anchor: str, through: Optional[str] = None
             ) -> List[Tuple[int, str, str, str]]:
    """(k, decision, entry, exit) every CADENCE sessions on SPY.

    `exit` is '' when that session has not happened yet.
    """
    i0 = spy.first_index_after(
        (_dt.date.fromisoformat(anchor) - _dt.timedelta(days=1)).isoformat())
    out = []
    k, i = 0, i0
    while i is not None and i < len(spy):
        d = spy.dates[i]
        if through and d > through:
            break
        entry = spy.dates[i + 1] if i + 1 < len(spy) else ""
        ex = spy.dates[i + 1 + HORIZON] if i + 1 + HORIZON < len(spy) else ""
        out.append((k, d, entry, ex))
        k += 1
        i += CADENCE
    return out


def _rf(panel, as_of: str, entry: str, exit_: str) -> Tuple[Optional[float],
                                                             List[str]]:
    cell, _hist = M._latest(panel, "DFF", as_of)
    if cell is None or not entry or not exit_:
        return None, []
    days = (_dt.date.fromisoformat(exit_) - _dt.date.fromisoformat(entry)).days
    return (float(cell.value) / 100.0 * days / 360.0,
            [f"panel:DFF:{cell.observed_at}@{cell.vintage_at}"])


def build(*, bars: Dict[str, Bars], instruments: Sequence[U.Instrument],
          panel, dates: Sequence[Tuple[int, str, str, str]],
          profiles: Optional[Dict[str, object]] = None,
          macro_as_of: Optional[str] = None,
          log=lambda s: None) -> Tuple[List[Obs], List[dict]]:
    """Every observation for these dates. Returns (rows, voided cells).

    `macro_as_of` is for the forward path only: prices are read at the last
    COMPLETE bar `d`, while macro is read as known at the decision itself,
    which can be later (a Monday-evening decision after a Friday close).
    """
    spy = bars[U.BENCHMARK]
    rows: List[Obs] = []
    voids: List[dict] = []
    for n, (k, d, entry, ex) in enumerate(dates):
        ma = macro_as_of or d
        mf, mev, mmiss = M.macro_features(panel, ma)
        reading = M.regime(panel, ma)
        rfeat = M.regime_features(reading)
        rlabel = M.regime_label(reading)
        rf, rf_ev = _rf(panel, ma, entry, ex)
        econ_reader = None
        ts = spy.index_of(d)
        for ins in instruments:
            b = bars.get(ins.symbol)
            if b is None:
                continue
            t = b.index_of(d)
            if t is None or t < F.NEED - 1:
                continue        # not yet listed / not enough history
            ie = b.index_of(entry) if entry else None
            ix = b.index_of(ex) if ex else None
            if entry and ie is None:
                voids.append({"date": d, "symbol": ins.symbol,
                              "reason": f"no bar on entry session {entry}"})
                continue
            if ins.universe == U.COMPANY:
                rel = F.relative_features(b, t, spy, ts)
                if rel is None:
                    voids.append({"date": d, "symbol": ins.symbol,
                                  "reason": "calendar mismatch with SPY"})
                    continue
                pf, pev = rel
            else:
                pf, pid = F.price_features(b, t)
                pev = [pid]
            feats = dict(pf)
            feats.update(mf)
            feats.update(rfeat)
            econ = None
            ev_engine = [f"econ_regime:{ma}"]
            if ins.universe == U.COMPANY and profiles is not None:
                if econ_reader is None:
                    econ_reader = M.EconReader(panel, ma)
                econ = econ_reader.company(profiles[ins.symbol])
                feats["econ_adverse_count"] = float(len(econ["adverse"]))
                feats["econ_favourable_count"] = float(len(econ["favourable"]))
                feats["econ_signed_channels"] = float(econ["signed"])
                ev_engine = ev_engine + econ["evidence_ids"]
            o = Obs(k=k, decision_date=d, entry_date=entry, exit_date=ex,
                    symbol=ins.symbol, universe=ins.universe,
                    family=ins.family, signal_scope=ins.signal_scope,
                    business_model_class=ins.business_model_class,
                    feats=feats, ev_price=pev, ev_macro=mev + rf_ev,
                    ev_engine=ev_engine, macro_missing=tuple(mmiss),
                    regimes=tuple(reading.regimes), regime_label=rlabel,
                    rf=rf, econ=econ, defensive=ins.defensive)
            if ix is not None and ie is not None:
                o.ret = b.open_adj[ix] / b.open_adj[ie] - 1.0
                if ins.universe == U.COMPANY:
                    si, sx = spy.index_of(entry), spy.index_of(ex)
                    if si is None or sx is None:
                        voids.append({"date": d, "symbol": ins.symbol,
                                      "reason": "SPY bar missing"})
                        continue
                    o.excess = o.ret - (spy.open_adj[sx] / spy.open_adj[si]
                                        - 1.0)
                elif rf is not None:
                    o.excess = o.ret - rf
                if o.excess is not None:
                    o.y = 1 if o.excess > 0 else 0
            elif ex:
                voids.append({"date": d, "symbol": ins.symbol,
                              "reason": f"no bar on exit session {ex}"})
                continue
            rows.append(o)
        if n % 25 == 0:
            log(f"  observations: date {n + 1}/{len(dates)} {d} "
                f"rows={len(rows)}")
    _climatology(rows)
    return rows, voids


def _climatology(rows: List[Obs]) -> None:
    """p_clim: the family base rate from outcomes KNOWN at the decision date."""
    by_fam: Dict[str, List[Obs]] = {}
    for o in rows:
        by_fam.setdefault((o.universe, o.family), []).append(o)
    for fam_rows in by_fam.values():
        resolved = sorted((o for o in fam_rows if o.resolved),
                          key=lambda o: o.exit_date)
        exits = [o.exit_date for o in resolved]
        cum = [0]
        for o in resolved:
            cum.append(cum[-1] + o.y)
        import bisect
        for o in fam_rows:
            j = bisect.bisect_right(exits, o.decision_date)
            o.p_clim = (cum[j] + 1) / (j + 2)    # Laplace: 0.5 with no data


def macro_complete(o: Obs) -> bool:
    return not o.macro_missing
