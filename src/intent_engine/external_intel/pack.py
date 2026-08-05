"""The external intelligence pack: one object, three contexts, one gate.

WHAT THIS IS FOR
----------------
Market, macro and competitive context reach the founder surfaces through this
and nothing else. Assembling them once per run means the dashboard, the
narrative, the Executive Brief and the Full Analysis are reading the same
facts -- the drift between surfaces that cost two cycles came from each one
computing its own version of the answer.

THE RULES THAT LIVE HERE
------------------------
1. MARKET MOVEMENT IS NOT CAUSATION. A share price falling is evidence about
   what the market expects, not evidence that the strategy is failing. The
   product is not permitted to phrase it as the latter, and `causal_language`
   below is the check.

2. EXTERNAL CONTEXT DOES NOT OVERRIDE COMPANY EVIDENCE. It is context for a
   decision the company's own evidence drives. A bounded result stays bounded
   however rich the market data is -- `changes_readiness` is False, always.

3. EVERY NUMBER MUST BE IN THE PACK. `grounded_numbers` is the set of figures
   the sources actually published; `ungrounded_numbers` finds any figure in
   generated prose that is not one of them. A number that appears in a
   sentence and not in the data is a fabrication, whatever produced it.

4. SECTIONS APPEAR ONLY WHEN THEY CHANGE SOMETHING. `relevant_sections`
   returns the ones that earned their place, so a surface renders one section
   rather than three empty ones.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .competitor_contract import CLAIM_RELEVANT, Competitor, corroborating
from .macro_contract import MacroFactor
from .market_contract import MarketIntel, absent
from .strategic_contract import StrategicIntel

MARKET = "market"
MACRO = "macro"
COMPETITIVE = "competitive"
STRATEGIC = "strategic"


@dataclass(frozen=True)
class ExternalContext:
    """Everything outside the company, gathered once."""
    market: MarketIntel
    macro: Tuple[MacroFactor, ...] = ()
    competitors: Tuple[Competitor, ...] = ()
    as_of: str = ""
    #: The sanitized strategic dossier, when the market-learning engine has
    #: published one for this company. Optional by design — it arrives from a
    #: separate system, on its own schedule, and a founder analysis has never
    #: promised one. See `has_strategic` for why absence is silent here and
    #: loud for the other three families.
    strategic: Optional["StrategicIntel"] = None

    # --- relevance ----------------------------------------------------------
    @property
    def has_market(self) -> bool:
        return bool(self.market and self.market.available)

    @property
    def has_macro(self) -> bool:
        return bool(self.macro)

    @property
    def has_competitors(self) -> bool:
        return bool(corroborating(self.competitors))

    @property
    def has_strategic(self) -> bool:
        """Available AND carrying material.

        A dossier that validated cleanly and says nothing is not a section.
        The distinction matters more here than for market or macro: those are
        families a public company is EXPECTED to have, so their absence is
        itself a finding worth printing. A strategic dossier is produced by an
        upstream engine that may simply never have looked at this company, and
        printing "no strategic reading was published" on every analysis would
        report our own deployment topology as if it were intelligence about
        the company.
        """
        return bool(self.strategic and self.strategic.available
                    and self.strategic.has_material)

    def relevant_sections(self) -> List[str]:
        """Only the contexts that have something to say.

        "Do not add all three sections when only one is relevant" is the
        instruction; this is where that is decided once rather than three
        times with three different answers.
        """
        out = []
        if self.has_market:
            out.append(MARKET)
        if self.has_macro:
            out.append(MACRO)
        if self.has_competitors:
            out.append(COMPETITIVE)
        if self.has_strategic:
            out.append(STRATEGIC)
        return out

    @property
    def leading_macro(self) -> Optional[MacroFactor]:
        """The one macro factor most worth a founder's attention.

        A factor that has MOVED beats one that has not: a flat series is
        context, a moving one is news. Ties break on the order the exposure
        rules found them, which follows the evidence.
        """
        moved = [f for f in self.macro if f.observation.direction
                 and f.observation.direction != "broadly flat"]
        return (moved or list(self.macro) or [None])[0]

    @property
    def leading_competitor(self) -> Optional[Competitor]:
        strong = corroborating(self.competitors)
        return strong[0] if strong else None

    # --- numeric grounding --------------------------------------------------
    @property
    def grounded_numbers(self) -> set:
        """Every figure the sources actually published, as text.

        Both the rounded and unrounded forms, because prose quotes "22.7%"
        for a stored 22.73 and refusing that would make the gate unusable
        rather than strict.
        """
        out = set()

        def add(value):
            if value is None or isinstance(value, bool):
                return
            try:
                number = float(value)
            except (TypeError, ValueError):
                return
            for text in (f"{number:g}", f"{abs(number):g}",
                         f"{number:.1f}", f"{abs(number):.1f}",
                         f"{number:.0f}", f"{abs(number):.0f}",
                         f"{number:.2f}", f"{abs(number):.2f}"):
                out.add(text.lstrip("+"))

        payload = (self.market.payload or {}) if self.market else {}
        for group in ("price_periods", "benchmark_relative_periods"):
            for m in (payload.get(group) or {}).values():
                add(m.get("value"))
        for m in (payload.get("benchmark") or {}).get("periods", {}).values():
            add(m.get("value"))
        # The plotted series is published data too. Without it the chart's own
        # text alternative -- "this company ended at 106" -- failed the gate
        # that exists to catch invented numbers, which would have taught a
        # reader to ignore the gate.
        series = payload.get("series") or {}
        for key in ("company_indexed", "benchmark_indexed"):
            for value in series.get(key) or ():
                add(value)
        add(series.get("base"))
        # Digits inside a benchmark's NAME are an identifier, not a claim:
        # "S&P 500 tracking fund" is what the index is called.
        _add_tokens(out, (payload.get("benchmark") or {}).get("name", ""))
        for key in ("annualized_volatility", "period_drawdown",
                    "distance_from_period_high"):
            add((payload.get(key) or {}).get("value"))
        # Window descriptors are published too: "the last 252 sessions" names
        # the period a figure covers. Treating that 252 as an unsourced claim
        # would flag the very sentence that makes the figure interpretable.
        for group in ("price_periods", "benchmark_relative_periods"):
            for m in (payload.get(group) or {}).values():
                _add_tokens(out, m.get("period"))
        for key in ("annualized_volatility", "period_drawdown",
                    "distance_from_period_high"):
            m = payload.get(key) or {}
            _add_tokens(out, m.get("period"))
            _add_tokens(out, m.get("note"))
        for factor in self.macro:
            add(factor.observation.current_value)
            add(factor.observation.prior_value)
            if (factor.observation.current_value is not None
                    and factor.observation.prior_value is not None):
                add(factor.observation.current_value
                    - factor.observation.prior_value)
        return out

    def ungrounded_numbers(self, text: str) -> List[str]:
        """Figures in `text` that no source published.

        Years, small counts and ordinals are exempt: "three of four dated
        announcements" and "the 2026 filing" are prose, not claims about
        market data, and flagging them would train a reader to ignore this.
        """
        # Dates first. Scanning "from 2025-01-06 to 2026-02-24" for numbers
        # yields "-01", "-06", "-24" -- fragments of an ISO date read as
        # negative quantities nobody published. A gate that cries wolf on
        # every date is a gate a reader learns to ignore.
        text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", text or "")
        found = []
        for raw in re.findall(r"-?\d[\d,]*\.?\d*", text):
            token = raw.replace(",", "")
            try:
                number = float(token)
            except ValueError:  # pragma: no cover
                continue
            if number.is_integer() and (1900 <= number <= 2100
                                        or abs(number) <= 12):
                continue
            if _normalise(token) in {_normalise(g)
                                     for g in self.grounded_numbers}:
                continue
            found.append(raw)
        return found


def _add_tokens(out: set, text) -> None:
    """Every numeric token in a published STRING, as grounded.

    Period labels, notes and index names carry real figures that the prose
    quotes back. They are published by definition -- they came out of the
    export -- so they belong in the grounded set.
    """
    for token in re.findall(r"\d[\d,]*\.?\d*", str(text or "")):
        out.add(_normalise(token.replace(",", "")))


def _normalise(token: str) -> str:
    try:
        return f"{float(token):g}"
    except ValueError:  # pragma: no cover
        return token


#: Phrasings that turn a price movement into a verdict on the business. The
#: share price is evidence about what the market EXPECTS; it is not a
#: measurement of whether the strategy works, and the difference is the whole
#: reason market context is safe to show a founder at all.
_CAUSAL = (
    r"because\s+the\s+(?:shares?|stock|price)\s+(?:fell|rose|dropped)",
    r"(?:shares?|stock|price)\s+(?:fell|dropped|declined)[^.]{0,40}"
    r"(?:so|therefore|which\s+(?:means|shows|proves))",
    r"the\s+strategy\s+(?:is\s+)?(?:failing|failed|working|works)\s+"
    r"(?:because|as\s+shown\s+by)",
    r"prov(?:es|en|ing)\s+(?:that\s+)?the\s+(?:strategy|plan|business)",
    r"(?:shares?|stock)[^.]{0,30}(?:therefore|hence)[^.]{0,40}"
    r"(?:strategy|management|plan)",
)


def causal_language(text: str) -> List[str]:
    """Places where market movement is being presented as causation."""
    return [m.group(0) for pattern in _CAUSAL
            for m in re.finditer(pattern, text or "", re.I)]


#: The sentence the product uses instead. Kept as a constant so every surface
#: that needs it says the same thing.
NON_CAUSAL_FRAME = (
    "A share-price move records what the market expects, not whether the "
    "operating strategy is working; it is a reading to explain, not a verdict "
    "to accept.")


def build_context(*, market: Optional[MarketIntel] = None,
                  macro: Sequence[MacroFactor] = (),
                  competitors: Sequence[Competitor] = (),
                  strategic: Optional[StrategicIntel] = None,
                  as_of: str = "") -> ExternalContext:
    return ExternalContext(
        market=market or absent("No market context was assembled for this "
                                "run."),
        macro=tuple(macro or ()), competitors=tuple(competitors or ()),
        strategic=strategic, as_of=as_of)


def _strategic_blocks(intel: "StrategicIntel") -> List[dict]:
    """The strategic dossier as reasoning blocks, one role per kind.

    Each kind answers a different founder question, and they are kept apart
    because merging them is how a posture INFERENCE gets read as an observed
    ACTION:

        interactions            who acted, and who responded
        postures                what the actor's stance might be, with rivals
        mismatches              what was expected and did not happen
        reactions               what response is plausible next
        priorities              what observation would settle it

    Two invariants are enforced here rather than trusted upstream. A posture
    always travels with its live alternatives, so it cannot be printed as a
    settled fact. An interaction always travels with its alternative
    explanations, so an inferred objective cannot be printed as a known
    motive — that is the difference between "Company B matched the price" and
    "Company B is buying share", and only the first one was observed.
    """
    out: List[dict] = []
    for row in intel.interactions:
        facts = [f"{row.get('focal_actor', '')} — "
                 f"{row.get('initial_action', '')}."]
        if row.get("response"):
            facts.append(f"{row.get('responding_actor', '')} responded: "
                         f"{row['response']}.")
        if row.get("response_lag_days") is not None:
            facts.append(f"Response came {row['response_lag_days']} day(s) "
                         f"later.")
        if row.get("payoff_note"):
            facts.append(f"Effect on payoffs: {row['payoff_note']}")
        limitations = list(row.get("alternative_explanations") or ())
        if row.get("inferred_objective"):
            facts.append(f"One reading of the objective: "
                         f"{row['inferred_objective']}.")
            limitations.append(
                "The objective is inferred from the action, not stated by "
                "the actor. The alternatives above remain open.")
        out.append({
            "context": STRATEGIC,
            "role": ("A sequence of actions between named actors. It says "
                     "what was DONE and by whom; it does not establish why."),
            "facts": facts, "evidence_ids": list(row.get("evidence_ids")
                                                 or ()),
            "as_of": row.get("at", ""), "freshness": "", "stale": False,
            "limitations": limitations, "source": "",
        })
    for row in intel.postures:
        alts = row.get("alternatives") or []
        facts = [f"{row.get('subject', '')} — leading reading: "
                 f"{row.get('leading_state', '')} "
                 f"({float(row.get('leading_probability') or 0):.0%})."]
        if alts:
            facts.append("Live alternatives: " + ", ".join(
                f"{a.get('state')} ({float(a.get('probability') or 0):.0%})"
                for a in alts) + ".")
        for moved in (row.get("moved") or ()):
            facts.append(f"{moved.get('state')} moved "
                         f"{float(moved.get('from') or 0):.0%} → "
                         f"{float(moved.get('to') or 0):.0%}.")
        out.append({
            "context": STRATEGIC,
            "role": ("An inferred stance, held as a distribution. The "
                     "leading reading is not a finding, and the "
                     "alternatives are not rejected."),
            "facts": facts,
            "evidence_ids": list(row.get("evidence_ids") or ()),
            "as_of": row.get("as_of", ""), "freshness": "", "stale": False,
            "limitations": [row.get("certainty_note", "")],
            "source": "",
        })
    for row in intel.mismatches:
        facts = [f"{row.get('subject', '')} — expected "
                 f"{row.get('expected_event') or 'the preregistered outcome'}"
                 f"; observed {row.get('observed_direction') or 'otherwise'}."]
        if row.get("rationale"):
            facts.append(row["rationale"])
        out.append({
            "context": STRATEGIC,
            "role": ("An expectation committed BEFORE the observation, and "
                     "what actually happened. A mismatch is evidence; it is "
                     "not a verdict on the company."),
            "facts": facts,
            "evidence_ids": list(row.get("evidence_ids") or ()),
            "as_of": row.get("evaluated_at", ""), "freshness": "",
            "stale": False,
            "limitations": ([f"Falsifier stated in advance: "
                             f"{row['falsifier']}"]
                            if row.get("falsifier") else []),
            "source": "",
        })
    for row in intel.reactions:
        facts = [f"{row.get('responder', '')} — {row.get('response', '')}."]
        if row.get("payoff_effect"):
            facts.append(f"Effect if it happens: {row['payoff_effect']}.")
        if row.get("second_order"):
            facts.append(f"Then: {row['second_order']}.")
        limitations = []
        if row.get("is_prediction"):
            limitations.append(
                "This is a bounded expectation about a response that has NOT "
                "happened. It is a scenario to monitor, not an event.")
        if row.get("precedents"):
            facts.append(f"Precedent: {row['precedents']}.")
        else:
            limitations.append(
                "No precedent was matched, so the mechanism carries this "
                "reading on its own.")
        out.append({
            "context": STRATEGIC,
            "role": ("A plausible response by another actor, with its "
                     "confidence. It is a scenario, never a forecast."),
            "facts": facts,
            "evidence_ids": list(row.get("evidence_ids") or ()),
            "as_of": "", "freshness": "", "stale": False,
            "limitations": limitations, "source": "",
        })
    for row in intel.priorities:
        facts = [f"{row.get('candidate_observation', '')} would most reduce "
                 f"the uncertainty on {row.get('subject', '')}."]
        if row.get("expected_date"):
            facts.append(f"Expected {row['expected_date']}.")
        if row.get("falsifies"):
            facts.append(f"It would settle: {row['falsifies']}.")
        out.append({
            "context": STRATEGIC,
            "role": ("What to watch next, and why it is the observation "
                     "worth waiting for."),
            "facts": facts, "evidence_ids": [], "as_of": "",
            "freshness": "", "stale": False,
            "limitations": ([row["limitation"]] if row.get("limitation")
                            else []),
            "source": "",
        })
    for block in out:
        block["limitations"] = [x for x in block["limitations"] if x]
    return out


def reasoning_pack(context: ExternalContext) -> dict:
    """What the reasoning layer receives: facts, ids, freshness, limitations.

    Deliberately flat and deliberately labelled. Each block states its ROLE, so
    a consumer cannot mistake context for evidence about the company -- the
    failure mode being guarded is a model reading a price fall as proof of an
    operating problem.
    """
    blocks = []
    payload = (context.market.payload or {}) if context.has_market else {}
    if context.has_market:
        facts = []
        for label, m in (payload.get("price_periods") or {}).items():
            if m.get("value") is not None:
                facts.append(f"Share price {m['value']:+.2f}% over "
                             f"{m['period']}.")
        for label, m in (payload.get("benchmark_relative_periods")
                         or {}).items():
            if m.get("value") is not None:
                facts.append(
                    f"That is {abs(m['value']):.2f} percentage points "
                    f"{'ahead of' if m['value'] > 0 else 'behind'} "
                    f"{(payload.get('benchmark') or {}).get('name', 'the market')}"
                    f" over {m['period']}.")
        vol = payload.get("annualized_volatility") or {}
        if vol.get("value") is not None:
            facts.append(f"Annualised volatility {vol['value']:.1f}% "
                         f"({vol['period']}). {vol.get('note', '')}".strip())
        dd = payload.get("period_drawdown") or {}
        if dd.get("value") is not None:
            facts.append(f"Deepest fall from a peak in the period: "
                         f"{dd['value']:.1f}%.")
        regime = payload.get("market_regime") or {}
        if regime.get("label"):
            facts.append(f"The wider market is {regime['label']} — "
                         f"{regime.get('basis', '')}.")
        blocks.append({
            "context": MARKET,
            "role": ("Describes what OUTSIDE investors appear to expect. It "
                     "is not a measurement of whether this company's strategy "
                     "is working, and must not be written as one."),
            "facts": facts,
            "evidence_ids": list(payload.get("evidence_ids") or ()),
            "as_of": context.market.as_of,
            "freshness": (f"{context.market.age_days} days old"
                          if context.market.age_days is not None else ""),
            "stale": context.market.stale,
            # The STANDING limitation always leads, then whatever this
            # particular export could not measure. Carrying only the second
            # meant a clean series arrived with an empty limitations list --
            # so the reasoner was told what the data said and never told what
            # it cannot establish, which is the half that keeps a price move
            # from becoming a verdict.
            "limitations": ([
                "Price records what investors expect, not what the business "
                "has achieved. It cannot establish that a strategy is "
                "working or failing."]
                + list(payload.get("limitations") or ())
                + (["This snapshot is older than one trading week."]
                   if context.market.stale else [])),
            "source": (payload.get("source_lineage") or {}).get("provider",
                                                                ""),
        })
    if context.has_macro:
        for factor in context.macro:
            d = factor.as_dict()
            blocks.append({
                "context": MACRO,
                "role": ("An outside condition this company is exposed to "
                         "through a stated mechanism. It bounds a decision; "
                         "it does not establish that results have moved."),
                "facts": [f"{d['factor']}: {d['change_text']} "
                          f"({d['direction']}), {d['comparison_note']}.",
                          f"Exposure: {d['company_exposure_mechanism']}",
                          f"Consequence: {d['business_consequence']}"],
                "evidence_ids": d["evidence_ids"],
                "as_of": d["observation_date"],
                "freshness": d["frequency"],
                "stale": False,
                "limitations": [d["limitation"]],
                "source": d["source"],
            })
    if context.has_competitors:
        for competitor in corroborating(context.competitors):
            d = competitor.as_dict()
            blocks.append({
                "context": COMPETITIVE,
                "role": ("An alternative the same buyer could choose. It "
                         "constrains what differentiation is worth claiming; "
                         "it is not a measurement of relative share."),
                "facts": [f"{d['name']} — {d['relationship_meaning']}.",
                          f"Stated overlap: {d['overlap']}"],
                "evidence_ids": d["evidence_ids"],
                "as_of": d["date"],
                "freshness": "",
                "stale": False,
                "limitations": [d["limitation"]],
                "source": ", ".join(t for t in d["source_titles"] if t),
            })
    if context.has_strategic:
        blocks.extend(_strategic_blocks(context.strategic))
    return {
        "as_of": context.as_of,
        "sections": context.relevant_sections(),
        "blocks": blocks,
        "grounded_numbers": sorted(context.grounded_numbers),
        "non_causal_frame": NON_CAUSAL_FRAME,
        "rules": [
            "External context never overrides this company's own evidence.",
            "A share-price movement is not evidence that a strategy failed.",
            "No number may appear that is not in these blocks.",
            "A section that changes no decision is omitted, not padded.",
        ],
    }
