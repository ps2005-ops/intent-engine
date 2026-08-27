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
#: The shared economic state, read from the canonical core. Distinct from
#: MACRO, which is this run's own reading of series the company's documents
#: happened to name. ECONOMY is what the whole engine knows about the economy,
#: and the company system's job against it is translation, not re-derivation.
ECONOMY = "economy"


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
    #: The shared economic state (`econ_context.EconContext`), and the
    #: quantities THIS company has evidenced exposure to. Both, because the
    #: state alone would let a surface render conditions nobody established a
    #: connection to -- which is the "interest rates affect technology
    #: companies" sentence `macro_contract` exists to refuse.
    economy: Optional[object] = None
    economy_exposures: Tuple[str, ...] = ()

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
    def has_economy(self) -> bool:
        """Available AND touching something this company is exposed to.

        The second half is the whole gate. A published economic state is
        available on every run once a market engine exists, and rendering it
        for a company with no evidenced exposure to any of it would put a
        macro paragraph on four hundred analyses that could have been written
        without reading any of them.
        """
        if not (self.economy is not None
                and getattr(self.economy, "available", False)):
            return False
        from .econ_context import relevant_to
        return any(r.get("measured") for r in
                   relevant_to(self.economy,
                               exposures=self.economy_exposures))

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
        if self.has_economy:
            out.append(ECONOMY)
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
        # A belief's confidence and a posture's weight are figures the
        # strategic dossier PUBLISHES, exactly as the price payload publishes
        # a period return. They are stored as probabilities and rendered as
        # percentages, so both forms are grounded — otherwise the gate would
        # flag "62% confidence" as an invented number and the honest way to
        # satisfy it would be to stop stating the confidence at all, which is
        # the opposite of what the gate is for.
        if self.strategic and self.strategic.available:
            def add_probability(value):
                add(value)
                try:
                    add(round(float(value) * 100))
                except (TypeError, ValueError):
                    return
            for belief in self.strategic.beliefs:
                add_probability(belief.get("confidence"))
            for posture in self.strategic.postures:
                add_probability(posture.get("leading_probability"))
                for alt in (posture.get("alternatives") or ()):
                    add_probability(alt.get("probability"))
                for moved in (posture.get("moved") or ()):
                    add_probability(moved.get("from"))
                    add_probability(moved.get("to"))
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
                  economy: Optional[object] = None,
                  economy_exposures: Sequence[str] = (),
                  as_of: str = "") -> ExternalContext:
    return ExternalContext(
        market=market or absent("No market context was assembled for this "
                                "run."),
        macro=tuple(macro or ()), competitors=tuple(competitors or ()),
        strategic=strategic, economy=economy,
        economy_exposures=tuple(economy_exposures or ()), as_of=as_of)


def _belief_blocks(intel: "StrategicIntel") -> List[dict]:
    """What the market engine currently thinks the evidence implies.

    THE DEFECT THIS CLOSES. `has_material` counted beliefs; this renderer read
    interactions, postures, mismatches, reactions and priorities and did not
    read beliefs. The market engine publishes beliefs. So a real dossier
    validated cleanly, was counted as carrying material, opened a strategic
    section, and put nothing under it — the third layer of a disconnection
    whose first two layers were a schema the consumer rejected and a refusal
    indistinguishable from absence.

    ROUTED THROUGH THE GRAPH, NOT THE DOSSIER JSON. The blocks are built from
    the `business_graph` projection, so a founder-visible sentence can be
    walked back to a hypothesis node, to the evidence nodes that support it,
    to an evidence id in the market ledger. Rendering the JSON directly would
    be one fewer hop and would break that chain on the first hop.

    A PROBABILITY IS NOT CONFIDENCE. The producer states 0.586 on every belief
    in the current corpus, because that is the prior a single evidence item
    opens one at. Printing "59% confident" would turn a prior into a
    measurement — the same error the market's own mechanism calibration
    refuses by declining to grade below five informative tests. The standing
    is a phrase chosen by testing status, and an untested belief cannot be
    dressed up by a high prior.

    The four layers stay separate: what the evidence WAS, what the engine
    currently READS from it, and what that would MEAN are three different
    claims, and only the first is observed.
    """
    from intent_engine.business_graph import projections as bgp
    from intent_engine.business_graph.model import HYPOTHESIS, SUPPORTS

    beliefs = list(intel.beliefs or ())
    if not beliefs:
        return []

    graph = bgp.from_strategic_dossier(
        company_id=intel.company_id, company_label=intel.company_id,
        beliefs=beliefs, as_of=intel.as_of, dossier_revision=intel.as_of)

    # The raw rows, indexed both ways the graph can name a belief: by the
    # proposition it became a node label from, and by its ledger id.
    _rows = {}
    for _row in beliefs:
        if _row.get("proposition"):
            _rows[str(_row["proposition"])] = _row
        if _row.get("belief_id"):
            _rows[str(_row["belief_id"])] = _row

    out: List[dict] = []
    for node in graph.of_kind(HYPOTHESIS):
        if node.attrs.get("origin") != "market_learning_engine":
            continue
        # Walked along the SUPPORTS edges pointing INTO the belief. Evidence
        # supports a hypothesis, so from the hypothesis it is an in-edge —
        # and `neighbours(node, kind)` filters by EDGE kind, not node kind, so
        # asking it for EVIDENCE silently returned nothing and the rendered
        # block carried no provenance at all. This hop is the whole chain:
        # sentence → hypothesis node → supporting evidence → ledger id.
        # A supporting node is now an OCCURRENCE carrying every account of
        # itself, so the walk collects `evidence_ids` from each. The number of
        # in-edges is the number of things that happened; the ids under them
        # are how many times each was written up. Both are kept: the first is
        # what may be reasoned from, the second is what may be traced.
        evidence_ids: List[str] = []
        occurrences = 0
        for edge in graph.in_edges(node.node_id, SUPPORTS):
            source_node = graph.node(edge.src)
            if not source_node:
                continue
            ids = source_node.attrs.get("evidence_ids")
            if ids:
                occurrences += 1
                evidence_ids.extend(str(i) for i in ids)
            elif source_node.attrs.get("evidence_id"):
                # An older dossier that was never normalized. One row, one
                # occurrence, and the standing below will say it is unrated.
                occurrences += 1
                evidence_ids.append(str(source_node.attrs["evidence_id"]))

        # "Reads" and "is", kept apart deliberately. The proposition is the
        # engine's reading; the basis is what it read it from.
        facts = [f"Market evidence currently supports this reading: "
                 f"{node.label}"]
        if node.attrs.get("basis"):
            facts.append(f"Basis: {node.attrs['basis']}")
        facts.append(f"Standing: {node.confidence}.")

        # HOW SOUND THAT EVIDENCE IS, on the primary surface rather than in an
        # appendix. Only when it changes how the line should be read: a note
        # on every block is a methodology lecture, and a reader told about
        # sourcing nine times stops reading the tenth.
        note = str(node.attrs.get("trust_sentence") or "")
        if note:
            facts.append(note)

        # A PRIOR AND A POSTERIOR MUST NOT READ THE SAME.
        #
        # DECLARED means the belief was opened by the evidence above and has
        # never been moved by anything since, so its standing is an OPENING
        # POSITION. Printed beside a belief that has survived three
        # contradictions with no distinction, it invites the reader to credit
        # an untested position with a track record. They are different claims.
        #
        # The row is looked up rather than read off the node because the graph
        # projection carries the reading, not its revision history.
        row = _rows.get(node.label) or _rows.get(
            str(node.attrs.get("belief_id") or "")) or {}
        declared = (str(row.get("update_method") or "").upper() == "DECLARED"
                    or not row.get("direction_of_last_change"))

        limitations = list(node.attrs.get("limitations") or ())
        # Standing-specific, so evidence that was examined and found thin does
        # not get the same sentence as evidence nobody examined.
        if node.attrs.get("trust_limitation"):
            limitations.append(str(node.attrs["trust_limitation"]))
        if declared:
            facts.append("This belief was opened by the evidence above and "
                         "has not yet been revised by anything since.")
            limitations.append(
                "The confidence is an opening position, not a tested one: no "
                "later observation has moved it up or down.")
        else:
            facts.append(
                f"Last revised {row.get('direction_of_last_change')} by "
                f"{str(row.get('update_method') or '').lower()}.")
        limitations.append(
            "This is a reading the market-learning engine holds, not an "
            "established fact about the company, and it does not by itself "
            "recommend an action.")
        out.append({
            "context": STRATEGIC,
            "role": ("What an outside learning engine currently reads from "
                     "this company's public evidence. It is a hypothesis "
                     "under test, not a finding, and it carries no "
                     "recommendation."),
            "facts": facts,
            "evidence_ids": evidence_ids,
            # The same sentence that is already in `facts`, named so a reader
            # of the STRUCTURE can find it. `semantic_state` classifies facts
            # by prefix, and a trust note starts with none of them — so
            # without this key the one line that bounds the conclusion would
            # fall through the classifier and register as no change at all.
            "evidence_standing": note,
            # How many things happened, beside how many times they were
            # written up. Kept apart so nothing downstream has to divide.
            "occurrences": occurrences,
            "as_of": node.as_of, "freshness": "", "stale": bool(intel.stale),
            "limitations": limitations,
            "source": "market-learning engine strategic dossier",
        })
    return out


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

    BELIEFS WERE THE MISSING KIND, AND THEY ARE THE ONLY ONE PRODUCED
    ----------------------------------------------------------------
    Every kind above was rendered before beliefs were, and beliefs are what
    the market engine actually emits: on the first real dossiers to cross this
    boundary — Microsoft, Caterpillar, Shopify — `strategic_beliefs` was
    populated and every other list was empty. So `has_strategic` reported True,
    the section was declared relevant, and this function returned zero blocks.
    A context that announces itself and then says nothing is worse than one
    that stays silent, because the silence at least reads as absence.
    """
    out: List[dict] = _belief_blocks(intel)
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
    if context.has_economy:
        from .econ_context import relevant_to, transmission_note
        rows = [r for r in relevant_to(context.economy,
                                       exposures=context.economy_exposures)]
        facts = []
        for row in rows:
            if not row.get("measured"):
                # NAMED, NOT DROPPED. "This company is exposed to real yields
                # and the engine does not measure them" is a research
                # priority; omitting it makes the company look less exposed
                # than it is.
                facts.append(
                    f"{row['quantity'].replace('_', ' ')}: not measured by "
                    f"the shared economic state ({row.get('reason', '')})")
                continue
            direction = str(row.get("direction", "")).upper()
            unit = row.get("unit") and " " + row["unit"] or ""
            value = ("" if row.get("value") is None
                     else f"{row['value']:g}{unit}")
            name = row["quantity"].replace("_", " ")
            if direction == "NO_PRIOR":
                # NEVER "broadly flat". There is no earlier observation, so
                # the honest sentence says the level and says that no change
                # is computable -- rendering it as flat is how an unmeasured
                # economy reads as a calm one.
                facts.append(
                    f"{name} stands at {value} (as of {row.get('as_of', '')}, "
                    f"{row.get('publisher', '')}); no earlier observation is "
                    "held, so no change is computable")
            else:
                moving = {"UP": "rising", "DOWN": "falling"}.get(
                    direction, "unchanged")
                prior = row.get("prior_value")
                move = ("" if prior is None
                        else f" from {prior:g} on {row.get('prior_as_of', '')}")
                facts.append(
                    f"{name} is {moving} to {value}{move} "
                    f"(as of {row.get('as_of', '')}, "
                    f"{row.get('publisher', '')})")
        blocks.append({
            "context": ECONOMY,
            "role": ("The economic state the whole engine holds, not this "
                     "run's own reading of it. It says what the economy is "
                     "doing; what that means for THIS company is the "
                     "question the analysis answers, and this block does not "
                     "answer it."),
            "facts": facts,
            "evidence_ids": [r.get("node_id") for r in rows
                             if r.get("node_id")],
            "as_of": getattr(context.economy, "as_of", ""),
            "freshness": "",
            "stale": False,
            "limitations": [
                "An economic condition moving is not evidence about this "
                "company's operations. The connection is the exposure "
                "mechanism, which is stated per quantity and rests on this "
                "company's own retrieved evidence.",
                "Conditions listed as not measured are gaps in the shared "
                "state, not readings of zero.",
            ],
            "note": transmission_note(
                context.economy, exposures=context.economy_exposures),
        })
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
