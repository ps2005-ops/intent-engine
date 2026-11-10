"""Price features at a decision date, computed only from bars that existed then.

Every function takes the bar index of the decision date and reads indices
`<= t` only. That is checked two independent ways, because one check can be
fooled by the code it checks:

  * each feature set returns the evidence id of its price window,
    `px:<SYM>:<first>..<last>`, and `leakage.check_evidence` re-reads the
    LAST date against the decision date;
  * `leakage.truncation_invariant` recomputes the features on bars truncated
    at the decision date and requires identical output, which catches a read
    past `t` that the evidence id failed to record.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from intent_engine.paper_validation.bars import Bars

PRICE_NAMES = ("r21", "r63", "r252_21", "vol63", "ma200")
REL_NAMES = ("rel_r21", "rel_r63", "rel_r252_21", "vol63", "beta252")
NEED = 273   # 252 + 21: the 12-1 momentum window


def _ret(c, a: int, b: int) -> float:
    return c[b] / c[a] - 1.0


def _vol(c, t: int, n: int) -> float:
    rs = [math.log(c[k] / c[k - 1]) for k in range(t - n + 1, t + 1)]
    m = sum(rs) / len(rs)
    return math.sqrt(sum((x - m) ** 2 for x in rs) / (len(rs) - 1)) \
        * math.sqrt(252.0)


def price_window_id(b: Bars, t: int, need: int = NEED) -> str:
    return f"px:{b.symbol}:{b.dates[t - need + 1]}..{b.dates[t]}"


def price_features(b: Bars, t: int) -> Optional[Tuple[Dict[str, float], str]]:
    if t is None or t < NEED - 1:
        return None
    c = b.close_adj
    ma = sum(c[t - 199:t + 1]) / 200.0
    f = {"r21": _ret(c, t - 21, t), "r63": _ret(c, t - 63, t),
         "r252_21": _ret(c, t - 252, t - 21), "vol63": _vol(c, t, 63),
         "ma200": c[t] / ma - 1.0}
    return f, price_window_id(b, t)


def relative_features(b: Bars, t: int, spy: Bars, ts: int
                      ) -> Optional[Tuple[Dict[str, float], List[str]]]:
    """The company's price features relative to SPY on the same date."""
    if t is None or ts is None or t < NEED - 1 or ts < NEED - 1:
        return None
    if b.dates[t] != spy.dates[ts]:
        return None
    c, s = b.close_adj, spy.close_adj
    # Beta over the last 252 sessions on dates the two share.
    rb, rs = [], []
    for k in range(252):
        i, j = t - k, ts - k
        if b.dates[i] != spy.dates[j]:
            return None     # a calendar mismatch would misalign the pairs
        rb.append(c[i] / c[i - 1] - 1.0)
        rs.append(s[j] / s[j - 1] - 1.0)
    ms = sum(rs) / len(rs)
    mb = sum(rb) / len(rb)
    var = sum((x - ms) ** 2 for x in rs)
    beta = (sum((x - ms) * (y - mb) for x, y in zip(rs, rb)) / var) \
        if var else 1.0
    f = {"rel_r21": _ret(c, t - 21, t) - _ret(s, ts - 21, ts),
         "rel_r63": _ret(c, t - 63, t) - _ret(s, ts - 63, ts),
         "rel_r252_21": _ret(c, t - 252, t - 21) - _ret(s, ts - 252, ts - 21),
         "vol63": _vol(c, t, 63), "beta252": beta}
    return f, [price_window_id(b, t), price_window_id(spy, ts)]
