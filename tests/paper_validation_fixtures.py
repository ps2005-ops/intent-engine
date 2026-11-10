"""Offline fixtures for the paper-validation tests: synthetic bars and panel.

Deterministic random walks on a weekday calendar, plus a tiny macro panel,
so every test runs without a network and without the 200k-line real panel.
"""
from __future__ import annotations

import datetime as dt
import math
import random

from intent_engine.econ import panel as PN
from intent_engine.paper_validation.bars import Bars


def sessions(start="2010-01-04", n=700):
    d = dt.date.fromisoformat(start)
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def walk(symbol, dates, *, seed, drift=0.0003, vol=0.01, start=100.0):
    r = random.Random(seed)
    closes, opens = [], []
    px = start
    for _ in dates:
        o = px * math.exp(r.gauss(0, vol / 3))
        px = o * math.exp(drift + r.gauss(0, vol))
        opens.append(o)
        closes.append(px)
    return Bars(symbol, tuple(dates), tuple(opens), tuple(closes),
                "2026-11-09T00:00:00+00:00", "fixture", "fixture")


def panel(dates, *, dff=2.0):
    p = PN.Panel()
    for i, d in enumerate(dates):
        nxt = (dt.date.fromisoformat(d) + dt.timedelta(days=1)).isoformat()
        p.add(PN.Cell(series_id="DFF", observed_at=d, vintage_at=nxt,
                      value=dff, unit="percent", kind="policy_rate",
                      node_class="MACRO", frequency="DAILY"))
        p.add(PN.Cell(series_id="BAA10Y", observed_at=d, vintage_at=nxt,
                      value=2.0 + 0.5 * math.sin(i / 40.0), unit="percent",
                      kind="credit_spread_ig", node_class="MACRO",
                      frequency="DAILY"))
    return p.finalise()


def universe(n_sessions=700):
    from intent_engine.paper_validation import universe as U
    dates = sessions(n=n_sessions)
    bars = {"SPY": walk("SPY", dates, seed=1),
            "TLT": walk("TLT", dates, seed=2, drift=0.0001),
            "XLE": walk("XLE", dates, seed=3, vol=0.02)}
    etfs = [i for i in U.etfs() if i.symbol in bars]
    return dates, bars, etfs, panel(dates)
