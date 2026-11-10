"""The policies compared, under identical data access and execution.

Every policy sees the same observation rows (same features, same vintage
wall) and is executed by the same book. They differ only in how they turn a
row into LONG, SHORT or ABSTAIN and a probability.

PROVENANCE IS DECLARED, NOT IMPLIED
-----------------------------------
    EXISTING_ENGINE   code that already decides in this repository, called
                      unchanged (never a re-implementation that could drift)
    BASELINE          a textbook rule, the comparator a sceptic would choose
    NEW_IN_THIS_WORK  built here; credited to this work, never to the engine
    CONTROL           exists to show what no skill looks like
    NOT_IMPLEMENTED / PENDING_INPUT
                      named so their absence is a recorded result
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from intent_engine.market import signals as MS
from intent_engine.market import strategy_library as SL
from intent_engine.paper_validation import features as F
from intent_engine.paper_validation import leakage as LK
from intent_engine.paper_validation import macro as M
from intent_engine.paper_validation import model as MD
from intent_engine.paper_validation import universe as U
from intent_engine.paper_validation.observations import (COMPANY_ECON_NAMES,
                                                         Obs)
from intent_engine.paper_validation.protocol import MODEL_MARGIN, RULE_P

EXISTING_ENGINE = "EXISTING_ENGINE"
BASELINE = "BASELINE"
NEW_IN_THIS_WORK = "NEW_IN_THIS_WORK"
CONTROL = "CONTROL"
IMPLEMENTED = "IMPLEMENTED"
NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
PENDING_INPUT = "PENDING_INPUT"

LONG, SHORT, ABSTAIN = "LONG", "SHORT", "ABSTAIN"


@dataclass
class Decision:
    direction: str
    probability: Optional[float]
    evidence_ids: List[str]
    rationale: str
    abstention_reason: str = ""
    model_version: str = ""


@dataclass
class Policy:
    policy_id: str
    version: str
    provenance: str
    universes: Tuple[str, ...]
    feature_set: str
    thesis: str
    mechanism: str
    competing: Tuple[str, ...]
    invalidation: str
    status: str = IMPLEMENTED
    status_reason: str = ""

    def applies(self, universe: str) -> bool:
        return self.status == IMPLEMENTED and universe in self.universes

    def begin(self, rows: Sequence[Obs]) -> None:
        """Called once with every row (resolved or not) before deciding."""

    def decide_date(self, date_rows: Sequence[Obs], history) -> List[Decision]:
        return [self.decide(o, history) for o in date_rows]

    def decide(self, o: Obs, history) -> Decision:      # pragma: no cover
        raise NotImplementedError


def _dir(sign: float, p_long: float = RULE_P) -> Tuple[str, float]:
    return (LONG, p_long) if sign > 0 else (SHORT, 1.0 - p_long)


def _seed(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


# --- baselines ---------------------------------------------------------------

class Cash(Policy):
    def decide(self, o, history):
        return Decision(ABSTAIN, None, [], "cash", "cash holds no position")


class BuyHold(Policy):
    def decide(self, o, history):
        return Decision(LONG, RULE_P, list(o.ev_price), "always long")


class TSMom(Policy):
    def decide(self, o, history):
        x = o.feats["rel_r252_21" if o.universe == U.COMPANY else "r252_21"]
        d, p = _dir(x)
        return Decision(d, p, list(o.ev_price),
                        f"12-1 month return {x:+.3f}")


class Reversal(Policy):
    def decide(self, o, history):
        x = o.feats["rel_r21" if o.universe == U.COMPANY else "r21"]
        d, p = _dir(-x)
        return Decision(d, p, list(o.ev_price), f"1-month return {x:+.3f}")


class EconFactorCredit(Policy):
    def decide(self, o, history):
        if "d_baa_spread_91d" not in o.feats or \
                "d_baa_spread_91d" in o.macro_missing:
            return Decision(ABSTAIN, None, [], "",
                            "BAA10Y change not knowable at the decision")
        ev = [e for e in o.ev_macro if e.startswith("panel:BAA10Y:")]
        dx = o.feats["d_baa_spread_91d"]
        widening = dx > 0
        if widening == o.defensive:
            return Decision(LONG, RULE_P, ev,
                            f"BAA-10y moved {dx:+.2f}pp over 91d")
        return Decision(ABSTAIN, None, ev, "",
                        f"spread {'widening' if widening else 'narrowing'}: "
                        f"{'risk' if not o.defensive else 'defensive'} "
                        "asset not favoured")


# --- the engine's own policies, called unchanged -----------------------------

class IEMarketMomentum(Policy):
    """`market.strategy_library.baseline_momentum.v1`, the canonical market
    engine's control strategy, with the engine's own BASELINE_PROBABILITY."""

    def begin(self, rows):
        self._closes = {}

    def bind(self, bars):
        self._bars = bars

    def decide(self, o, history):
        b = self._bars[o.symbol]
        t = b.index_of(o.decision_date)
        closes = {b.dates[i]: b.close_adj[i] for i in range(max(0, t - 40),
                                                             t + 1)}
        sig = SL.baseline_momentum(closes, security=o.symbol,
                                   as_of=o.decision_date)
        ev = [f"px:{o.symbol}:{b.dates[max(0, t - 40)]}..{b.dates[t]}"]
        if not sig.fired:
            return Decision(ABSTAIN, None, ev, "", sig.reason)
        p = MS.BASELINE_PROBABILITY
        return Decision(LONG if sig.direction == SL.LONG else SHORT,
                        p if sig.direction == SL.LONG else 1 - p, ev,
                        f"{sig.strategy_key}: {sig.reason} ({sig.value:+.4f})")


class IEEconTransmission(Policy):
    """The economic engine's company reading. ANY adverse transmission ->
    expect the company to underperform SPY; otherwise abstain, as the
    product does."""

    def decide(self, o, history):
        e = o.econ or {}
        ev = [x for x in o.ev_engine if x.startswith("econ_state:")]
        if not e.get("adverse"):
            reason = ("no signed channel reaches this business model"
                      if not e.get("signed") else
                      "no condition moved materially in the adverse "
                      "direction")
            return Decision(ABSTAIN, None, ev, "", reason)
        lead = e.get("lead") or e["adverse"][0]
        return Decision(SHORT, 1.0 - RULE_P, ev,
                        f"{len(e['adverse'])} adverse channel(s); lead "
                        f"{lead['quantity']} {lead['direction']} "
                        f"({lead['channel']}): {lead['mechanism'][:140]}")


# --- new in this work ----------------------------------------------------------

class IEEconBayes(Policy):
    """Beta(1,1) per business-model class on whether a flagged company did
    underperform, using only flags whose windows closed by the decision."""

    THRESHOLD = 0.52

    def decide_date(self, date_rows, history):
        d = date_rows[0].decision_date if date_rows else ""
        past = history.resolved(d)
        stats: Dict[str, List[int]] = {}
        latest = ""
        for o in past:
            if o.universe != U.COMPANY or not (o.econ or {}).get("adverse"):
                continue
            s = stats.setdefault(o.business_model_class, [0, 0])
            s[0] += 1 - o.y      # underperformed = the flag was right
            s[1] += 1
            latest = max(latest, o.exit_date)
        out = []
        for o in date_rows:
            ev = [x for x in o.ev_engine if x.startswith("econ_state:")]
            if latest:
                ev = ev + [f"resolved_through:{latest}"]
            if not (o.econ or {}).get("adverse"):
                out.append(Decision(ABSTAIN, None, ev, "",
                                    "no adverse transmission to weigh"))
                continue
            k, n = stats.get(o.business_model_class, [0, 0])
            mu = (1 + k) / (2 + n)
            if mu > self.THRESHOLD:
                out.append(Decision(SHORT, 1.0 - mu, ev,
                                    f"posterior P(underperform | flag, "
                                    f"{o.business_model_class}) = {mu:.3f} "
                                    f"from {n} resolved flags"))
            else:
                out.append(Decision(ABSTAIN, 1.0 - mu, ev, "",
                                    f"posterior {mu:.3f} <= {self.THRESHOLD} "
                                    f"over {n} resolved flags for this class"))
        return out


class Logit(Policy):
    """Walk-forward L2 logistic per family; refit at each year's first date."""

    def __init__(self, *a, names_by_universe: Dict[str, Tuple[str, ...]],
                 shuffle_labels: bool = False, **kw):
        super().__init__(*a, **kw)
        self.names_by_universe = names_by_universe
        self.shuffle_labels = shuffle_labels
        self.models: Dict[Tuple[str, str], object] = {}
        self.fit_log: List[dict] = []
        self._year: Dict[Tuple[str, str], str] = {}

    def _complete(self, o: Obs, names) -> bool:
        return all(n in o.feats for n in names) and not (
            set(names) & set(o.macro_missing))

    def _refit(self, key, names, d, history) -> None:
        uni, fam = key
        train = [o for o in history.resolved(d)
                 if o.universe == uni and o.family == fam
                 and self._complete(o, names)]
        LK.assert_purged([o.exit_date for o in train], d)
        if len(train) < 40:
            self.models[key] = None
            self.fit_log.append({"date": d, "family": fam, "n": len(train),
                                 "fitted": False})
            return
        X = MD.matrix([o.feats for o in train], names)
        y = np.array([o.y for o in train], float)
        if self.shuffle_labels:
            rng = np.random.default_rng(_seed(self.policy_id, fam, d))
            y = rng.permutation(y)
        m = MD.fit(X, y, names)
        self.models[key] = m
        self.fit_log.append({"date": d, "family": fam, "n": len(train),
                             "fitted": True,
                             "train_through": max(o.exit_date for o in train)})

    def model_version(self, key) -> str:
        m = self.models.get(key)
        if m is None:
            return ""
        h = hashlib.sha256(repr((m.weights, m.bias, m.means, m.scales))
                           .encode()).hexdigest()[:12]
        return f"{self.policy_id}:{key[1]}:{h}"

    def decide_date(self, date_rows, history):
        out = []
        for o in date_rows:
            names = self.names_by_universe[o.universe]
            key = (o.universe, o.family)
            year = o.decision_date[:4]
            if self._year.get(key) != year:
                self._refit(key, names, o.decision_date, history)
                self._year[key] = year
            ev = list(o.ev_price) + (list(o.ev_macro)
                                     if self.feature_set in "BD" else [])
            if self.feature_set == "D":
                ev += list(o.ev_engine)
            m = self.models.get(key)
            if m is None:
                out.append(Decision(ABSTAIN, None, ev, "",
                                    "fewer than 40 resolved training rows"))
                continue
            if not self._complete(o, names):
                out.append(Decision(ABSTAIN, None, ev, "",
                                    "a declared feature was not knowable"))
                continue
            p = float(MD.predict(m, MD.matrix([o.feats], names))[0])
            p = min(max(p, 1e-4), 1 - 1e-4)
            mv = self.model_version(key)
            if p > 0.5 + MODEL_MARGIN:
                out.append(Decision(LONG, p, ev, f"p={p:.3f}", model_version=mv))
            elif p < 0.5 - MODEL_MARGIN:
                out.append(Decision(SHORT, p, ev, f"p={p:.3f}", model_version=mv))
            else:
                out.append(Decision(ABSTAIN, p, ev, "",
                                    f"p={p:.3f} inside the "
                                    f"{MODEL_MARGIN:.2f} margin",
                                    model_version=mv))
        return out


# --- controls ------------------------------------------------------------------

class RandomControl(Policy):
    def decide(self, o, history):
        r = random.Random(_seed("random_control", o.decision_date, o.symbol))
        return Decision(LONG if r.random() < 0.5 else SHORT, 0.5,
                        list(o.ev_price), "seeded coin flip")


class PermutationControl(Policy):
    """As many shorts per date as the econ engine flags, on random names."""

    def decide_date(self, date_rows, history):
        flagged = sum(1 for o in date_rows if (o.econ or {}).get("adverse"))
        names = sorted(o.symbol for o in date_rows)
        d = date_rows[0].decision_date if date_rows else ""
        r = random.Random(_seed("permutation_control", d))
        pick = set(r.sample(names, flagged)) if flagged else set()
        out = []
        for o in date_rows:
            if o.symbol in pick:
                out.append(Decision(SHORT, 1.0 - RULE_P, list(o.ev_price),
                                    f"random {flagged} of {len(names)}"))
            else:
                out.append(Decision(ABSTAIN, None, list(o.ev_price), "",
                                    "not drawn"))
        return out


class Absent(Policy):
    def decide(self, o, history):     # pragma: no cover - never called
        raise RuntimeError(f"{self.policy_id} is {self.status}")


# --- the registry ----------------------------------------------------------------

A_ETF = F.PRICE_NAMES
A_CO = F.REL_NAMES
B_ETF = A_ETF + M.MACRO_NAMES
B_CO = A_CO + M.MACRO_NAMES
D_ETF = B_ETF + M.REGIME_NAMES
D_CO = B_CO + M.REGIME_NAMES + COMPANY_ECON_NAMES

_E, _C = U.ETF, U.COMPANY
_BOTH = (_E, _C)


def registry() -> List[Policy]:
    return [
        Cash("cash", "v1", BASELINE, _BOTH, "-",
             "Holding nothing earns cash, which is zero excess return.",
             "none", ("any policy with positive net excess return",),
             "never invalidated; it is the floor"),
        BuyHold("buy_and_hold", "v1", BASELINE, _BOTH, "-",
                "Risk premia are positive on average; holding collects them.",
                "equity and term premia compensate for bearing risk",
                ("premia are negative over this window",),
                "net excess return <= 0 over the window"),
        TSMom("tsmom_12_1", "v1", BASELINE, _BOTH, "A",
              "An asset's 12-1 month trend persists over the next month.",
              "slow diffusion of information and hedging demand",
              ("trend reverses at one month", "trend is noise"),
              "net Sharpe <= 0 at >= 60 periods"),
        Reversal("reversal_1m", "v1", BASELINE, _BOTH, "A",
                 "Last month's move partially reverses next month.",
                 "liquidity provision earns the reversal",
                 ("monthly moves persist (momentum)",),
                 "net Sharpe <= 0 at >= 60 periods"),
        EconFactorCredit(
            "econ_factor_credit", "v1", BASELINE, (_E,), "B",
            "Widening credit spreads predict weaker risk assets and "
            "stronger havens over the next month.",
            "the spread prices default risk and risk appetite "
            "(Gilchrist-Zakrajsek); it moves before earnings do",
            ("spreads lag prices and carry no information",
             "spread widening is already priced the day it happens"),
            "Brier skill CI covers 0 at >= 60 periods"),
        IEMarketMomentum(
            "ie_market_momentum", "baseline_momentum.v1", EXISTING_ENGINE,
            _BOTH, "A",
            "Trailing 20-session direction persists (the canonical market "
            "engine's control strategy, recorded by the engine at 0.500).",
            "momentum (the engine states it as a control, no alpha claim)",
            ("20-session moves are noise", "they reverse"),
            "the engine's own: net expectancy <= 0 at n_eff >= 100"),
        IEEconTransmission(
            "ie_econ_transmission", "econ_decision.v1", EXISTING_ENGINE,
            (_C,), "D",
            "When a condition the business is exposed to moves materially "
            "in the direction that hurts its business-model class, the "
            "company underperforms the market over the next month.",
            "the canonical (channel, business model) transmission table "
            "in executive.company_profile, via econ_decision.transmissions",
            ("the move is already priced when it is published",
             "the channel matters at a horizon longer than a month",
             "flags fire on most companies most months, so the arm is a "
             "beta/size bet rather than a mechanism"),
            "flagged-minus-unflagged relative return CI covers 0 at >= 60 "
            "periods, or the arm does no better than the permutation "
            "control"),
        IEEconBayes(
            "ie_econ_bayes", "v1", NEW_IN_THIS_WORK, (_C,), "D",
            "The transmission flag is right more often for some business "
            "models than others, and resolved outcomes say which.",
            "Beta-Binomial learning over the engine's own flags",
            ("no class's flag is informative",),
            "Brier skill CI covers 0 at >= 60 periods"),
        Logit("logit_A", "v1", NEW_IN_THIS_WORK, _BOTH, "A",
              "Price history alone predicts the sign of next month's excess "
              "return.", "learned from resolved history",
              ("price features carry no information at one month",),
              "Brier skill vs climatology CI covers 0",
              names_by_universe={_E: A_ETF, _C: A_CO}),
        Logit("logit_B", "v1", NEW_IN_THIS_WORK, _BOTH, "B",
              "Macro conditions add to price history.",
              "learned from resolved history",
              ("macro is already in prices",),
              "no Brier improvement over logit_A",
              names_by_universe={_E: B_ETF, _C: B_CO}),
        Absent("logit_C", "v1", NEW_IN_THIS_WORK, _BOTH, "C",
               "News and company evidence add to macro and price.",
               "learned from resolved history", ("news is priced",),
               "no Brier improvement over logit_B",
               status=PENDING_INPUT,
               status_reason="the multi-source news/evidence channel "
                             "(prospect100/identity) is not wired; see "
                             "evidence_channel.PendingProvider"),
        Logit("logit_D", "v1", NEW_IN_THIS_WORK, _BOTH, "D",
              "The engine's reasoning (regime reading; company transmission "
              "counts) adds to macro and price.",
              "learned from resolved history",
              ("the engine's reading is a re-expression of macro features",),
              "no Brier improvement over logit_B",
              names_by_universe={_E: D_ETF, _C: D_CO}),
        Absent("causal_filtered", "v1", NEW_IN_THIS_WORK, _BOTH, "D",
               "Trade only signals a causal edge supports.", "-", (), "-",
               status=NOT_IMPLEMENTED,
               status_reason="no declared causal edge reaches a tradable "
                             "instrument: econ.transmission_seed edges are "
                             "household-to-company at evidence level 0-1, "
                             "below the causal-language floor, and none "
                             "names an asset return"),
        Absent("evidence_augmented", "v1", NEW_IN_THIS_WORK, _BOTH, "C",
               "Company news changes the decision.", "-", (), "-",
               status=PENDING_INPUT,
               status_reason="same as logit_C: no news provider is wired"),
        RandomControl("random_control", "v1", CONTROL, _BOTH, "-",
                      "No skill.", "none", (), "-"),
        PermutationControl(
            "permutation_control", "v1", CONTROL, (_C,), "-",
            "The econ arm's short count on random companies.", "none", (),
            "-"),
        Logit("shuffled_label_control", "v1", CONTROL, _BOTH, "B",
              "logit_B trained on permuted labels: what no information "
              "looks like through the same model.", "none", (), "-",
              names_by_universe={_E: B_ETF, _C: B_CO}, shuffle_labels=True),
    ]


def by_id(policies: Sequence[Policy]) -> Dict[str, Policy]:
    return {p.policy_id: p for p in policies}
