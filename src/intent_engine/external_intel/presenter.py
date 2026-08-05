"""Turn the external intelligence pack into founder-facing prose.

WHY ONE PRESENTER FOR EVERY SURFACE
------------------------------------
The dashboard, the narrative, the Executive Brief and the Full Analysis all
need the same four sentences about a market move: what the fact is, so what,
which decision it changes, and what it does not establish. Writing those four
in four places is how three surfaces ended up disagreeing about the same
company two cycles ago. They are written once, here, and each surface chooses
how much of them to show.

THE SHAPE EVERY BLOCK HAS
-------------------------
    fact            what was measured, with its period and unit
    so_what         why it matters to somebody running this company
    decision        the choice it bears on -- never "monitor this"
    limitation      what it does NOT establish
    source          who published it
    freshness       how old it is, in words a reader can judge
    text_alternative  the chart's content as a sentence

The last one is not decoration. A chart with no text alternative is unreadable
to a screen reader and unreadable in a printed brief, and both of those are
real ways this product gets consumed.

WHAT IT REFUSES
---------------
No block is emitted for a context with no data. A surface asks for what is
relevant and gets a shorter list, rather than a full-length list padded with
"not available" -- padding is what made six live dashboards open with a stack
of cards whose entire content was the word "Unavailable".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .competitor_contract import corroborating, framing_only
from .pack import (
    COMPETITIVE, MACRO, MARKET, NON_CAUSAL_FRAME, STRATEGIC, ExternalContext,
)


@dataclass(frozen=True)
class Block:
    """One decision-useful statement about the outside world."""
    key: str
    context: str
    title: str
    fact: str
    so_what: str
    decision: str
    limitation: str = ""
    source: str = ""
    freshness: str = ""
    text_alternative: str = ""
    evidence_ids: tuple = ()
    chart: str = ""

    def as_dict(self) -> dict:
        return {"key": self.key, "context": self.context, "title": self.title,
                "fact": self.fact, "so_what": self.so_what,
                "decision": self.decision, "limitation": self.limitation,
                "source": self.source, "freshness": self.freshness,
                "text_alternative": self.text_alternative,
                "evidence_ids": list(self.evidence_ids), "chart": self.chart}


def _freshness_words(context: ExternalContext) -> str:
    age = context.market.age_days
    if age is None:
        return ""
    if context.market.stale:
        return (f"{age} days old — older than one trading week, so it may not "
                f"reflect recent sessions")
    if age <= 1:
        return "as at the most recent completed session"
    return f"{age} days old"


def _direction(value: float) -> str:
    return "rose" if value > 0 else "fell"


def market_blocks(context: ExternalContext) -> List[Block]:
    """What outside investors appear to be pricing, as decisions."""
    if not context.has_market:
        return []
    payload = context.market.payload or {}
    source = ((payload.get("source_lineage") or {}).get("provider")
              or "public price history")
    fresh = _freshness_words(context)
    blocks: List[Block] = []

    # 1. TRAJECTORY AGAINST THE BENCHMARK. The single most decision-relevant
    # market fact, because it separates "this company moved" from "everything
    # moved" -- and only the first is about the company.
    periods = payload.get("price_periods") or {}
    relative = payload.get("benchmark_relative_periods") or {}
    bench = (payload.get("benchmark") or {}).get("name", "the broad market")
    best = next((p for p in ("1y", "3m", "1m")
                 if (periods.get(p) or {}).get("value") is not None), "")
    if best:
        own = periods[best]
        rel = relative.get(best) or {}
        fact = (f"The shares {_direction(own['value'])} "
                f"{abs(own['value']):.1f}% over {own['period']}")
        if rel.get("value") is not None:
            ahead = "ahead of" if rel["value"] > 0 else "behind"
            fact += (f", {abs(rel['value']):.1f} percentage points {ahead} "
                     f"{bench}")
        fact += "."
        blocks.append(Block(
            key="market_trajectory", context=MARKET,
            title="Market expectations",
            fact=fact,
            so_what=(
                "The gap against the benchmark is the part that is about this "
                "company rather than about the market everything trades in. "
                + NON_CAUSAL_FRAME),
            decision=(
                "Whether the company's own account of its position is one "
                "outside investors currently share — and if not, which of the "
                "two the plan should be built on."),
            limitation=(
                "Price reflects expectations and positioning as well as "
                "results. It cannot distinguish a re-rating of this company "
                "from a re-rating of everything that looks like it."),
            source=source, freshness=fresh,
            text_alternative=_series_alternative(payload, bench),
            chart="market_trajectory" if payload.get("series") else ""))

    # 2. RISK EXPECTATIONS. Volatility and drawdown answer a different
    # question from direction: how wide a range a plan has to survive.
    vol = payload.get("annualized_volatility") or {}
    dd = payload.get("period_drawdown") or {}
    high = payload.get("distance_from_period_high") or {}
    if vol.get("value") is not None or dd.get("value") is not None:
        parts = []
        if vol.get("value") is not None:
            parts.append(f"Annualised volatility is about "
                         f"{vol['value']:.0f}%")
        if dd.get("value") is not None:
            parts.append(f"the shares fell {abs(dd['value']):.0f}% from peak "
                         f"to trough in {dd['period']}")
        if high.get("value") is not None and high["value"] < -1:
            parts.append(f"and they sit {abs(high['value']):.0f}% below the "
                         f"period's highest close")
        fact = "; ".join(parts) + "."
        note = vol.get("note", "")
        if "one session moved" in note:
            fact += (" Most of that volatility is one session, so it measures "
                     "a single event rather than a settled level of doubt.")
        blocks.append(Block(
            key="market_risk", context=MARKET,
            title="What the market's uncertainty implies",
            fact=fact,
            so_what=(
                "Volatility is the width of the range outsiders think this "
                "business could land in. A wide range raises the cost of "
                "raising money against the story and shortens how long "
                "investors will wait for it."),
            decision=(
                "Whether the plan should be fundable from operating cash "
                "rather than from a raise timed to a recovery in the price."),
            limitation=(
                "This describes the spread of expectations, not the "
                "probability of any outcome, and it says nothing about "
                "operating performance."),
            source=source, freshness=fresh,
            text_alternative=fact,
            chart="market_risk" if dd.get("value") is not None else ""))

    return blocks


def _series_alternative(payload: dict, bench: str) -> str:
    """The chart, as a sentence. Written even when a chart renders."""
    series = payload.get("series") or {}
    dates = series.get("dates") or []
    if not dates:
        return ""
    company = series.get("company_indexed") or []
    market = series.get("benchmark_indexed") or []
    if not company or not market:  # pragma: no cover
        return ""
    return (f"From {dates[0]} to {dates[-1]}, with both series set to 100 at "
            f"the start: this company ended at {company[-1]:.0f} and "
            f"{bench} ended at {market[-1]:.0f}.")


def macro_blocks(context: ExternalContext) -> List[Block]:
    """The outside conditions this company is actually exposed to."""
    blocks = []
    for factor in context.macro:
        d = factor.as_dict()
        direction = d["direction"] or "has not moved materially"
        blocks.append(Block(
            key=f"macro_{d['factor_key']}", context=MACRO,
            title="Macro and industry pressure",
            fact=(f"{d['factor']} is {direction}: {d['change_text']}, "
                  f"{d['comparison_note']}."),
            so_what=f"{d['company_exposure_mechanism']} "
                    f"{d['business_consequence']}",
            decision=d["affected_kpi_or_decision"],
            limitation=d["limitation"],
            source=f"{d['source']} ({d['series_id']})",
            freshness=f"reading dated {d['observation_date']}, "
                      f"{d['frequency']}",
            text_alternative=(f"{d['factor']}: {d['change_text']}, "
                              f"{direction}."),
            evidence_ids=tuple(d["evidence_ids"]),
            chart=f"macro_exposure_{d['factor_key']}"))
    return blocks


def competitor_blocks(context: ExternalContext) -> List[Block]:
    """The alternatives the same buyer could choose."""
    strong = corroborating(context.competitors)
    if not strong:
        return []
    names = ", ".join(c.name for c in strong[:4])
    lead = strong[0]
    d = lead.as_dict()
    framing = framing_only(context.competitors)
    limitation = d["limitation"]
    if framing:
        limitation += (" " + ", ".join(c.name for c in framing[:3])
                       + " appear in the same competitive discussion without "
                         "a stated overlap, so they frame the market here "
                         "without supporting a conclusion.")
    return [Block(
        key="competitive_pressure", context=COMPETITIVE,
        title="Competitive pressure",
        fact=(f"The alternatives this company's own evidence names are "
              f"{names}. The closest is {d['name']} — "
              f"{d['relationship_meaning']}. Stated in the source as: "
              f"“{d['overlap']}”"),
        so_what=(
            "These are the options a buyer weighs in the same decision, so "
            "they cap what differentiation is worth claiming and what a "
            "premium can be charged for."),
        decision=d["decision_implication"],
        limitation=limitation,
        source=", ".join(t for t in d["source_titles"] if t) or "retrieved "
                                                                "evidence",
        freshness=(f"stated in a source dated {d['date']}" if d["date"]
                   else ""),
        text_alternative=(f"Alternatives named: {names}. Closest: "
                          f"{d['name']} ({d['relationship']})."),
        evidence_ids=tuple(d["evidence_ids"]),
        chart="competitor_positioning")]


def strategic_blocks(context: ExternalContext) -> List[Block]:
    """What the market-learning engine currently believes about this company.

    THE FAMILY THAT REACHED THE REASONING LAYER AND NOT THE PAGE
    ------------------------------------------------------------
    `pack.reasoning_pack` has carried strategic blocks for as long as the
    contract has existed, so the model saw them. Every founder-visible surface
    — the dossier, the layers, the narrative — builds its sections from
    `presenter.blocks()`, and this family was not in it. `relevant_sections()`
    would name STRATEGIC as relevant and no surface could render a word of it.

    ONE BLOCK, NOT ONE PER BELIEF
    -----------------------------
    The other three families each contribute a single block and the surfaces
    budget on that basis; a dossier that emitted six would take six of the
    reading budget away from the company's own evidence. So the strongest
    belief leads and the rest are named after it, which is also the honest
    ordering — confidence here is a stated number, not a ranking the reader
    has to infer.

    A BELIEF IS NOT AN OBSERVATION, AND THE BLOCK SAYS SO TWICE
    -----------------------------------------------------------
    Once in the fact, which attributes the reading to the engine rather than
    stating it about the world, and once in the limitation, which says a
    freshly opened belief is an opening position rather than a tested one.
    Confidence in the high fifties printed without that reads as a finding.
    """
    if not context.has_strategic:
        return []
    intel = context.strategic
    beliefs = sorted(intel.beliefs,
                     key=lambda b: float(b.get("confidence") or 0),
                     reverse=True)
    if not beliefs:
        return []

    lead = beliefs[0]
    subject = intel.subject or "this company"
    confidence = float(lead.get("confidence") or 0)
    others = [str(b.get("proposition") or "") for b in beliefs[1:3]
              if b.get("proposition")]

    fact = (f"Reading strategic evidence about {subject}, the market-learning "
            f"engine holds that {lead.get('proposition', '')} — at "
            f"{confidence:.0%} confidence.")
    if others:
        fact += " It also holds: " + "; ".join(others) + "."

    untested = all(str(b.get("update_method") or "").upper() == "DECLARED"
                   or not b.get("direction_of_last_change")
                   for b in beliefs)
    limitation = (
        "These are readings held at a stated confidence, not observations, "
        "and they describe strategic posture rather than this company's "
        "operating results.")
    if untested:
        limitation += (" Every one of them was opened by the evidence behind "
                       "it and has not since been revised, so the confidence "
                       "is an opening position rather than a tested one.")
    stated = [x for b in beliefs for x in (b.get("limitations") or ()) if x]
    if stated:
        limitation += " Stated by the engine: " + "; ".join(stated[:2]) + "."

    return [Block(
        key="strategic_reading", context=STRATEGIC,
        title="What the market engine believes",
        fact=fact,
        so_what=(
            "This is an outside reading of the same company, built from "
            "public evidence on its own schedule. Where it agrees with this "
            "analysis it is corroboration from a separate path; where it "
            "disagrees, one of the two is working from something the other "
            "has not seen, and that gap is worth finding before acting."),
        decision=(
            "Whether to treat this quarter's evidence as a change in "
            "direction or as a single period — and which of these readings "
            "to go looking for evidence against first."),
        limitation=limitation,
        source="market-learning engine, from public evidence",
        freshness=(f"published {intel.as_of}"
                   + (f", {intel.age_days} days ago"
                      if intel.age_days is not None else "")),
        text_alternative=(f"{len(beliefs)} strategic reading(s) about "
                          f"{subject}; strongest at {confidence:.0%} "
                          f"confidence."),
        evidence_ids=tuple(x for b in beliefs
                           for x in (b.get("evidence_ids") or ())))]


def blocks(context: ExternalContext) -> List[Block]:
    """Every relevant block, in decision order.

    Strategic comes last deliberately: it is an outside reading of the
    company, and it qualifies the company's own evidence rather than leading
    it. `ExternalContext.changes_readiness` is the structural half of the
    same rule.
    """
    return (market_blocks(context) + macro_blocks(context)
            + competitor_blocks(context) + strategic_blocks(context))


def leading_blocks(context: ExternalContext) -> List[Block]:
    """At most one block per context, for surfaces with a reading budget.

    The primary narrative gets this rather than everything: three sections
    where one is relevant is the padding the brief is meant to avoid, and a
    founder reading a 60-second answer will not read six.
    """
    out, seen = [], set()
    for block in blocks(context):
        if block.context in seen:
            continue
        seen.add(block.context)
        out.append(block)
    return out


def market_context_dict(context: ExternalContext) -> dict:
    """The `brief.market_context` shape the dashboard already consumes.

    A compatibility surface, deliberately: `layers.build_dashboard` has four
    carefully-written states for an absent market section, tuned on six live
    companies, and rewriting them to take a new object would have thrown that
    away to no benefit.
    """
    if not context.has_market:
        return {"available": False, "reason": context.market.reason,
                "modules": {}, "limitations": []}
    payload = context.market.payload or {}
    modules: Dict[str, dict] = {}
    for block in market_blocks(context):
        modules[block.key] = {
            "what_changed": block.fact, "so_what": block.so_what,
            "what_to_watch": block.decision,
            "text_alternative": block.text_alternative,
            "source": block.source, "freshness": block.freshness,
            "limitation": block.limitation, "chart": block.chart}
    return {"available": bool(modules), "reason": "" if modules else
            "no market measurement in the snapshot was usable",
            "modules": modules,
            "limitations": list(payload.get("limitations") or ()),
            "as_of": context.market.as_of, "stale": context.market.stale,
            "age_days": context.market.age_days,
            "ticker": context.market.ticker}
