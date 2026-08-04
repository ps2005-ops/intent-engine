"""The shared deep-intelligence model behind the Executive Brief and the
Full Analysis.

WHAT WAS WRONG
--------------
Measured on the deployed preview (Palantir, commit e55d3b3), the three depths
were inverted:

    /runs/<id>   816 words   the 60-second narrative
    /full        789 words   the "dossier"
    /brief       396 words   the "decision document"

The summary was the deepest surface in the product. Worse, `/brief` did not
consume the shared decision at all: it said "none of it supports a strategic
view strongly enough to put one forward" and then offered a DIFFERENT decision
("Whether to close the evidence gap publicly...") while the primary page
carried a DECISION_READY choice about services-to-product. Same run, opposite
answers -- the same class of defect the primary page was fixed for, one layer
down.

WHAT THIS MODULE DOES
---------------------
It assembles the canonical material ONCE, from the report the pipeline already
produced, and both deep surfaces render that one object at different depths.
Nothing here interprets: every string is lifted from the composed
`FounderDecision`, the report's own records, or the sentence-fitting helpers
the composer exposes.

The report is far richer than either surface was using. `mental_model` carries
six typed business-model components; `timeline` carries dated events;
`opportunities`, `vulnerabilities`, `blind_spots`, `surprises` and `questions`
each carry a claim AND why it matters. That is where the depth comes from --
not from saying the thesis again in longer words.

ABSENCE IS INTELLIGENCE, NOT SILENCE
------------------------------------
Competitor, market and macro material is frequently absent on a live run. A
missing family is rendered as a stated limitation WITH its decision
consequence, never as an empty heading and never as a zero. `evidence_families`
is the honest inventory: what was read, what was not, and what each absence
costs the reader.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from intent_engine.founder_brief.narrative import (
    PROVENANCE_LABEL, EvidenceItem, _dedupe, _evidence_index, _excerpt,
    _flat, _is_promotional, _observation_dicts,
)


#: Cover-page furniture common to every SEC filing. Matching any of these
#: means the extractor got the wrapper rather than the disclosure.
_FILING_BOILERPLATE = (
    "pursuant to section 13", "securities exchange act of 1934",
    "transition report pursuant", "quarterly report pursuant",
    "annual report pursuant", "commission file number",
    "registrant as specified in its charter",
    "incorporated by reference into the registration statement",
    "indicate by check mark", "☒", "☐", "[x]", "[ ]",
)


def _is_filing_boilerplate(text: str) -> bool:
    low = _flat(text).lower()
    if not low:
        return False
    return sum(1 for m in _FILING_BOILERPLATE if m in low) >= 2


def _readable_excerpt(obs) -> str:
    """What this source says, in the most readable form it has.

    `_excerpt` prefers the source's own words, which is right for a citation
    and wrong when extraction returned a nav dump -- "Acme home page. commerce
    infrastructure powering commerce. Shop Pay checkout and buyer identity,
    payments, capital, fulfillment, point of sale..." is a list of link labels,
    not a quotation. Where that fails the claim contract and the observation
    carries an analytic summary, the summary is the better citation.
    """
    from intent_engine.founder_brief.build import _is_consequence
    text = _excerpt(obs)
    # Extraction prefixes a scraped page with its own name -- "Acme home
    # page. ", "Acme api page. " -- and the body after it is the SAME list of
    # link labels on every page of the site. That prefix is the tell, so its
    # presence alone routes to the analytic summary; relying on the claim
    # contract let "commerce infrastructure powering commerce. Shop Pay
    # checkout, payments, capital, fulfillment, point of sale..." through as
    # a quotation.
    # A FILING'S COVER PAGE IS NOT ITS CONTENT. Live on the preview, the
    # single most valuable source in the run -- Palantir's 10-Q -- was cited
    # as "☒. QUARTERLY REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE
    # SECURITIES EXCHANGE ACT OF 1934. ☐. TRANSITION REPORT PURSUANT TO..."
    # which is the checkbox furniture every filing opens with and says
    # nothing about this company.
    if _is_filing_boilerplate(text):
        return _flat(obs.get("strategic_signal")) or ""
    scraped = bool(_re.match(r"^[^.]{0,60}\bpage\.\s", text))
    text = _re.sub(r"^[^.]{0,60}\bpage\.\s*", "", text).strip()
    if text and (scraped or not _is_consequence(text.rstrip("…"))):
        signal = _flat(obs.get("strategic_signal"))
        if signal:
            return signal
    return text
from intent_engine.strategic_intelligence.decision import (
    DECISION_READY, INVESTIGATION_REQUIRED, WITHHELD, as_clause,
    decision_from_dict, decision_of, end_sentence, lower_first,
)
from intent_engine.strategic_intelligence.editorial import SaidOnce

DOSSIER_VERSION = "founder_dossier.v1"

#: Which depth a section belongs to. The Executive Brief is a DECISION MEMO and
#: the Full Analysis is the dossier behind it, so some material appears only in
#: the deeper one -- that is what makes the deeper one deeper.
BRIEF = "brief"
FULL = "full"
BOTH = "both"

# Evidence families a reader is entitled to know the status of. Each carries
# what its ABSENCE costs, because "no competitor source" is only useful when a
# reader is told what that stops the analysis doing.
_FAMILIES = (
    ("company_owned", "The company's own pages",
     "Everything here is the company describing itself, so nothing has been "
     "checked against an outside account of it."),
    ("executive_statement", "Executive statements",
     "Leadership commentary is a claim about intent, not evidence of result."),
    ("investor_material", "Filings and investor material",
     "Without a filing there is no audited figure behind any economic "
     "statement, so revenue mix, margin and concentration stay unverifiable."),
    ("customer_voice", "Customer evidence",
     "Nothing here reports what buying and using this actually costs a "
     "customer, so adoption and retention claims cannot be tested."),
    ("competitor", "Competitor evidence",
     "No competitor's own account was read, so relative position rests on "
     "this company's framing of its market."),
    ("independent_reporting", "Independent reporting",
     "No outside party has reported on this, so nothing corrects for what the "
     "company chooses to emphasise."),
)


# --- data model ---------------------------------------------------------------

@dataclass
class Passage:
    """One block of the dossier. `depth` decides which surfaces render it."""
    key: str
    title: str
    depth: str = BOTH
    kind: str = "prose"            # prose | labelled | evidence | options | table
    paragraphs: tuple = ()
    items: tuple = ()
    options: tuple = ()
    note: str = ""
    evidence_ids: tuple = ()

    @property
    def is_substantive(self) -> bool:
        if self.options or self.items:
            return True
        return sum(len(p.split()) for p in self.paragraphs) >= 6

    def for_depth(self, depth: str) -> bool:
        return self.depth in (BOTH, depth)

    def as_dict(self) -> dict:
        return {"key": self.key, "title": self.title, "depth": self.depth,
                "kind": self.kind, "paragraphs": list(self.paragraphs),
                "items": [i.as_dict() if isinstance(i, EvidenceItem) else i
                          for i in self.items],
                "options": [o.as_dict() for o in self.options],
                "note": self.note, "evidence_ids": list(self.evidence_ids)}


@dataclass
class Dossier:
    company: str = ""
    readiness: str = INVESTIGATION_REQUIRED
    decision: object = None
    passages: tuple = ()
    families: tuple = ()
    version: str = DOSSIER_VERSION

    def passage(self, key: str) -> Optional[Passage]:
        for p in self.passages:
            if p.key == key:
                return p
        return None

    def at(self, depth: str) -> tuple:
        return tuple(p for p in self.passages
                     if p.for_depth(depth) and p.is_substantive)

    def words(self, depth: str) -> int:
        total = 0
        for p in self.at(depth):
            total += sum(len(x.split()) for x in p.paragraphs)
            for item in p.items:
                text = item.text if isinstance(item, EvidenceItem) else \
                    " ".join(str(v) for v in item.values())
                total += len(text.split())
            for option in p.options:
                total += len((option.description + " " + option.upside + " "
                              + option.downside).split())
        return total

    def as_dict(self) -> dict:
        return {"version": self.version, "company": self.company,
                "readiness": self.readiness,
                "passages": [p.as_dict() for p in self.passages],
                "families": list(self.families)}


# --- helpers ------------------------------------------------------------------

def _records(report: dict, key: str) -> List[dict]:
    out = []
    for item in (report.get(key) or ()):
        d = item.as_dict() if hasattr(item, "as_dict") else item
        if isinstance(d, dict):
            out.append(d)
    return out


def _sentence(text: str) -> str:
    text = _flat(text)
    return end_sentence(text[:1].upper() + text[1:]) if text else ""


def _decided(decision, hypotheses) -> dict:
    from intent_engine.founder_brief.narrative import _decided_hypothesis
    return _decided_hypothesis(decision, hypotheses)


import re as _re  # noqa: E402  (used only by the cleaner below)

#: Telemetry the reasoning layer appends to its own explanations. Live on
#: `/full`: "It directly tests the hypothesis that moving from selling a
#: product toward operating the rails beneath it; if it fails, that view is
#: wrong. 4 qualifying signal(s) matched: checkout_identity_rails,
#: infrastructure_positioning, platform_control, product_breadth" -- a broken
#: sentence, the library's pattern name, and four raw signal identifiers.
_SIGNAL_TAIL = _re.compile(
    r"\s*\d+\s+qualifying signal\(s\)[^.]*\.?\s*$", _re.I)
_HYPOTHESIS_CLAUSE = _re.compile(
    r"^it directly tests the hypothesis that .*?;\s*", _re.I)


def _readable_reason(text) -> str:
    """A "why it matters" a founder can read, or "".

    Two shapes are stripped rather than reworded: the trailing signal trace,
    and the "It directly tests the hypothesis that <pattern name>;" opening,
    whose subordinate clause is the library's own label for the shape and
    never parses as English.
    """
    out = _SIGNAL_TAIL.sub("", _flat(text))
    out = _HYPOTHESIS_CLAUSE.sub("", out).strip()
    if out.lower().startswith("if it fails"):
        out = out.split(",", 1)[-1].strip() if "," in out else ""
    return "" if len(out.split()) < 5 else out[:1].upper() + out[1:]


def evidence_families(report: dict) -> tuple:
    """What was read, what was not, and what each absence costs.

    Built from `source_class_coverage`, which the pipeline already computes, so
    the inventory and the evidence actually used cannot disagree.
    """
    coverage = report.get("source_class_coverage") or {}
    out = []
    for key, label, consequence in _FAMILIES:
        count = int(coverage.get(key) or 0)
        out.append({"key": key, "label": label, "count": count,
                    "present": count > 0,
                    "consequence": "" if count else consequence})
    return tuple(out)


# --- passage builders ---------------------------------------------------------

def _operating_model(company, report, said) -> Passage:
    """How the company actually creates and delivers value.

    `mental_model.components` is a typed, evidence-backed description of the
    business -- value proposition, growth engine, distribution, assets,
    products, competitive position -- and neither deep surface was reading it.
    Each component states its own plain-language stem and the observations
    behind it, so this is the causal business-model section without a word of
    new interpretation.
    """
    model = report.get("mental_model") or {}
    components = model.get("components") or {}
    items = []
    for name, comp in components.items():
        d = comp if isinstance(comp, dict) else getattr(comp, "as_dict",
                                                        lambda: {})()
        state = _flat(d.get("current_state"))
        # `current_state` is "<plain-language stem>: <detail>", and the stem is
        # what the component NAME already says. Rendered whole beside the
        # label it read "Value proposition: The core promise customers buy:
        # Shopify frames itself as..." -- the same idea three times.
        if ": " in state:
            state = state.split(": ", 1)[1]
        # `current_state` joins up to three signal sentences with "; ", and a
        # signal that carried no strategic summary falls back to its raw text,
        # which repeats the stem. One clear sentence per component reads as a
        # description of the business; three semicolon-joined ones read as a
        # dump with the heading stuttering through it.
        state = _flat(state.split(";")[0]).rstrip(".")
        if not state or said.has(state):
            continue
        # "Growth engine: Where new growth is coming from: <detail>." -- the
        # stem is already inside current_state, so the label is the component
        # name in a reader's words and the value is the sentence.
        said.remember(state)
        items.append({"label": name.replace("_", " ").capitalize(),
                      "text": _sentence(state),
                      "evidence_ids": list(
                          d.get("supporting_observation_ids") or ())[:3]})
    return Passage("operating_model", "How the business actually works",
                   depth=BOTH, kind="labelled", items=tuple(items[:6]))


def _what_changed(company, report, said) -> Passage:
    """Dated developments, oldest first — a chronology, not a snapshot.

    `timeline` carries real publication dates from the sources themselves,
    which is a different thing from the retrieval stamp the narrative
    correctly refuses to present as a change.
    """
    events = []
    for row in _records(report, "timeline"):
        date, event = _flat(row.get("date")), _flat(row.get("event"))
        if not date or not event or said.has(event):
            continue
        said.remember(event)
        events.append({"when": date, "what": _sentence(event),
                       "source": _flat(row.get("source_title"))})
    events.sort(key=lambda e: e["when"])
    return Passage("what_changed", "What changed, and when", depth=BOTH,
                   kind="dated", items=tuple(events[:8]))


def _customer_demand(company, report, index, said) -> Passage:
    """What customers say, kept apart from what the company says about them."""
    groups, seen = {}, SaidOnce()
    for obs in _observation_dicts(report):
        source_class = _flat(obs.get("source_class"))
        label = PROVENANCE_LABEL.get(source_class, "Unknown")
        text = _readable_excerpt(obs)
        # `seen` filters WITHIN this pass; `said` is only spent on what
        # survives selection, so a candidate dropped here does not silently
        # block the same sentence from appearing in a later passage.
        if not text or said.has(text) or seen.has(text) \
                or _is_promotional(text):
            continue
        seen.remember(text)
        groups.setdefault(label, []).append(EvidenceItem(
            text=text, source_title=_flat(obs.get("source_title")),
            provenance=label, date=_flat(obs.get("date")),
            evidence_id=_flat(obs.get("observation_id"))))
    # Independent voices first: they are the ones a reader cannot get from the
    # company, and burying them under eight company pages is how a page that
    # HAS customer evidence still reads as marketing.
    order = ["Customer evidence", "Independent evidence", "Competitor evidence",
             "Regulatory or investor filing", "Company claim"]
    items = []
    for label in order:
        items.extend(groups.get(label, [])[:2])
    # Claimed only once the selection is final, so `competitive` below cannot
    # re-show the same independent excerpts under a second heading -- which is
    # exactly what the first assembled dossier did.
    for item in items[:6]:
        said.remember(item.text)
    return Passage("customer_demand", "What the evidence actually says",
                   depth=BOTH, kind="evidence", items=tuple(items[:6]),
                   evidence_ids=tuple(i.evidence_id for i in items[:6]))


def _competitive(company, report, decision, hypotheses, families,
                 said) -> Passage:
    """Relative position, or a stated reason there is nothing to say.

    A generic competitor list is worse than none: it is the same paragraph for
    every company in a market. What is rendered here is what the RUN actually
    read -- a competitor's own words, an independent account, or the competing
    explanations of this company's own evidence.
    """
    paras, items = [], []
    index = _evidence_index(_observation_dicts(report))
    for obs in _observation_dicts(report):
        if _flat(obs.get("source_class")) not in ("competitor",
                                                  "independent_reporting"):
            continue
        text = _readable_excerpt(obs)
        if not text or said.has(text):
            continue
        said.remember(text)
        items.append(EvidenceItem(
            text=text, source_title=_flat(obs.get("source_title")),
            provenance=PROVENANCE_LABEL.get(_flat(obs.get("source_class")),
                                            "Unknown"),
            date=_flat(obs.get("date")),
            evidence_id=_flat(obs.get("observation_id"))))

    vulnerable = _records(report, "vulnerabilities")
    for row in vulnerable[:2]:
        layer, mechanism = _flat(row.get("exposed_layer")), _flat(
            row.get("mechanism"))
        if not (layer and mechanism) or said.has(mechanism):
            continue
        said.remember(mechanism)
        paras.append(end_sentence(
            f"The part of this most exposed to someone else's move is "
            f"{lower_first(layer)}: {as_clause(mechanism, company)}"))

    if not items:
        absent = next((f for f in families
                       if f["key"] == "competitor" and not f["present"]), None)
        if absent:
            paras.append(
                "No competitor's own account was retrieved for this run, so "
                "nothing here corrects for how this company frames its own "
                "market. Treat the positioning below as self-described, and "
                "read the decision knowing that a competitor moving first is "
                "the risk the evidence cannot price.")
    return Passage("competitive", "Where this sits against the alternatives",
                   depth=BOTH, kind="evidence", paragraphs=tuple(paras),
                   items=tuple(items[:4]),
                   evidence_ids=tuple(i.evidence_id for i in items[:4]))


def _market(company, market, said) -> Passage:
    """Market expectations in business language, or a stated limitation.

    Never a strategy name, a win rate, a Sharpe ratio or a recommendation --
    those are the trading system talking about itself. And never a zero: an
    absent series is an absent series.
    """
    ctx = market if isinstance(market, dict) else (
        market.as_dict() if market is not None else None)
    if not ctx:
        return Passage(
            "market", "What the market appears to expect", depth=BOTH,
            paragraphs=("No market snapshot has been published for this "
                        "company, so there is no read on what investors "
                        "currently expect. That is a gap in this analysis, not "
                        "a finding: it means the decision below is argued from "
                        "the business alone, with no check on whether the "
                        "market already believes it.",))
    if not ctx.get("available"):
        return Passage(
            "market", "What the market appears to expect", depth=BOTH,
            paragraphs=(end_sentence(
                f"Not established — {as_clause(ctx.get('reason', ''), company)}"),
                "Nothing is inferred from the absence. A missing price series "
                "is not a flat one."),
            note=_flat(ctx.get("disclaimer")))
    paras = []
    for name, module in (ctx.get("modules") or {}).items():
        changed, so_what = _flat(module.get("what_changed")), _flat(
            module.get("so_what"))
        if changed and not said.has(changed):
            said.remember(changed)
            paras.append(end_sentence(
                f"{_sentence(changed)} {so_what}".strip()))
    return Passage("market", "What the market appears to expect", depth=BOTH,
                   paragraphs=tuple(paras[:3]),
                   note=_flat(ctx.get("disclaimer")))


def _analogs(company, report, decision, hypotheses, said) -> Passage:
    """Where this has played out before, and where the comparison stops.

    An analog without its breaking point is an argument by anecdote, so the
    library's own "where the comparison breaks down" is rendered with it or
    the analog is not rendered at all.
    """
    items = []
    for pattern in _records(report, "patterns") + _records(
            report, "comparable_patterns"):
        mechanism = _flat(pattern.get("mechanism") or pattern.get("summary"))
        breaks = _flat(pattern.get("when_it_does_not_apply")
                       or pattern.get("breaks_down_when"))
        cases = pattern.get("historical_examples") or pattern.get("cases") or ()
        if not mechanism or said.has(mechanism):
            continue
        said.remember(mechanism)
        items.append({
            "label": "Seen before",
            "text": _sentence(mechanism),
            "breaks": _sentence(breaks) if breaks else "",
            # The library names a case "Amazon → AWS". An arrow is the
            # library's own notation, so the case is rendered as prose.
            "cases": "; ".join(
                f"{_flat(c.get('name', '')).replace('→', 'to')}"
                f"{' — ' + _flat(c.get('note')) if _flat(c.get('note')) else ''}"
                for c in list(cases)[:2] if isinstance(c, dict)
                and _flat(c.get("name"))),
        })
    return Passage("analogs", "Where this has played out before", depth=FULL,
                   kind="analog", items=tuple(items[:2]))


def _assumptions(company, decision, report, said) -> Passage:
    """The load-bearing beliefs. If one is wrong the decision changes."""
    rows = []
    for option in decision.options[:2]:
        text = _flat(option.key_assumption)
        if text and not said.has(text) and not text.startswith("That the"):
            said.remember(text)
            rows.append({"label": option.label, "text": _sentence(text)})
    for spot in _records(report, "blind_spots")[:2]:
        text = _flat(spot.get("counter_explanation"))
        if text and not said.has(text):
            said.remember(text)
            rows.append({"label": "Could also be true", "text": _sentence(text)})
    return Passage("assumptions", "What this rests on", depth=FULL,
                   kind="labelled", items=tuple(rows[:4]))


def _scenarios(company, decision, said) -> Passage:
    """Base, upside and downside — derived from the options, not invented.

    No numeric forecast appears here because none is available. Each scenario
    is a trigger, a mechanism and the indicator that would show it happening.
    """
    if decision.readiness != DECISION_READY or len(decision.options) < 2:
        return Passage("scenarios", "How this could go", depth=FULL)
    act, hold = decision.options[0], decision.options[1]
    # The option cards render upside and cost in full a few sections above, so
    # a scenario that quotes one back is the page saying it twice. Scenarios
    # earn their place by adding the INDICATOR and the timing, not the text.
    said.remember(act.upside)
    said.remember(hold.downside)
    watch = _flat(decision.falsifier) or _flat(
        act.watch_item) or "the check named above"
    rows = [
        {"label": "If the reading holds",
         "text": end_sentence(f"{_sentence(act.upside)} The indicator that "
                              f"this is happening: {lower_first(watch)}")},
        {"label": "If the plainer account holds",
         "text": end_sentence(f"{_sentence(hold.upside)} Acting early would "
                              f"then have cost what {act.label.lower()} "
                              f"commits")},
        {"label": "If it is settled too late",
         "text": end_sentence(
             f"The cost of deciding late is the cost of {lower_first(hold.label)} "
             f"turning out to be wrong, which the option comparison above "
             f"states in full")},
    ]
    return Passage("scenarios", "How this could go", depth=FULL,
                   kind="labelled", items=tuple(r for r in rows if r["text"]))


def _unknowns(company, report, decision, said) -> Passage:
    """Each gap with WHY it matters, so it reads as direction, not apology."""
    rows = []
    for spot in _records(report, "blind_spots"):
        why = _flat(spot.get("why_it_may_matter"))
        needed = [_flat(x) for x in (spot.get("evidence_needed") or ())]
        needed = [n for n in needed if n]
        if not needed or said.has(needed[0]):
            continue
        said.remember(needed[0])
        rows.append({"label": needed[0][:70],
                     "text": _sentence(why) if why else
                     "It is not observable in what was retrieved."})
    for gap in (report.get("evidence_gaps") or ())[:3]:
        text = _flat(gap)
        if text and not said.has(text):
            said.remember(text)
            rows.append({"label": "Not established", "text": _sentence(text)})
    return Passage("unknowns", "What is still unknown, and why it matters",
                   depth=FULL, kind="labelled", items=tuple(rows[:5]))


def _monitoring(company, report, decision, said) -> Passage:
    """A prioritised watch list: the question, and what it would settle."""
    rows = []
    for row in _records(report, "questions"):
        question = _flat(row.get("question"))
        why = _readable_reason(row.get("why_it_matters"))
        if not question or said.has(question):
            continue
        said.remember(question)
        rows.append({"label": question, "text": _sentence(why) if why else ""})
    return Passage("monitoring", "What to monitor, in priority order",
                   depth=FULL, kind="labelled", items=tuple(rows[:4]))


def _opportunity(company, report, said) -> Passage:
    rows = []
    for row in _records(report, "opportunities"):
        statement, why = _flat(row.get("statement")), _flat(row.get("why_now"))
        if not statement or said.has(statement):
            continue
        said.remember(statement)
        rows.append({"label": "Worth testing", "text": _sentence(statement),
                     "why": _sentence(why) if why else ""})
    return Passage("opportunity", "The opportunity this creates", depth=BOTH,
                   kind="labelled",
                   items=tuple({"label": r["label"],
                                "text": (r["text"] + " " + r["why"]).strip()}
                               for r in rows[:2]))


def _risk(company, report, decision, said) -> Passage:
    """The BUSINESS risk, not "the evidence is limited"."""
    paras = []
    for spot in _records(report, "blind_spots")[:2]:
        tension = _flat(spot.get("observed_tension"))
        why = _flat(spot.get("why_it_may_matter"))
        if not tension or said.has(tension):
            continue
        said.remember(tension)
        paras.append(end_sentence(
            f"{_sentence(tension)} {why}".strip()))
    return Passage("risk", "The risk that would cost the most", depth=BOTH,
                   paragraphs=tuple(paras[:2]))


def _what_was_read(company, documents, said) -> Passage:
    """The documents this run actually retrieved, by name and date.

    THE BOUNDED PATH HAS NO REPORT, so every passage above it is empty and the
    memo collapses onto the decision lead -- which, for three companies whose
    evidence genuinely differed (a 6-K, a 20-F, an AGM notice), rendered
    byte-identical pages once the name was masked. The old brief was
    company-specific only because it narrated source counts, which is exactly
    the narration this rebuild removed.

    What IS per-company on a bounded run is WHICH documents were readable.
    Naming them is a fact, not an interpretation, and it is the footing a
    reader needs to judge how far the bounded conclusion goes.
    """
    rows = []
    for doc in (documents or ()):
        if doc.get("retrieval_status") != "OK":
            continue
        title = _flat(doc.get("title") or doc.get("source_title"))
        if not title or said.has(title):
            continue
        said.remember(title)
        rows.append({"label": _flat(doc.get("date")) or "undated",
                     "text": _sentence(title)})
    return Passage("what_was_read", "What could actually be read", depth=BOTH,
                   kind="labelled", items=tuple(rows[:8]))


def _artefacts(company, decision, report, said) -> Passage:
    """Prepared work, each tied to the decision and to its evidence.

    The customer's question was whether the product researches or does
    something. Every artefact here names the decision it serves, what it is
    built from, and what the reader does with it -- and nothing leaves the
    page without explicit approval.
    """
    rows = []
    if decision.readiness == DECISION_READY and len(decision.options) >= 2:
        rows.append({
            "label": "Options comparison",
            "text": end_sentence(
                f"A one-page side-by-side of {decision.options[0].label} and "
                f"{lower_first(decision.options[1].label)}, each with its "
                f"upside, its cost, the assumption it rests on and the "
                f"sources behind it — for the meeting where this is argued")})
        rows.append({
            "label": "Decision memo",
            "text": end_sentence(
                f"The reading, the choice and the recommended next move, "
                f"written so the trade-off has to be made explicitly rather "
                f"than by default")})
    else:
        wanted = "; ".join(_flat(e).rstrip(".")
                           for e in decision.evidence_required[:3])
        if wanted:
            rows.append({"label": "Evidence request",
                         "text": end_sentence(
                             f"A numbered request for exactly what is "
                             f"missing: {wanted}")})
        rows.append({"label": "Investigation plan",
                     "text": end_sentence(
                         f"The one bounded check that would settle this, with "
                         f"what each result would favour")})
    questions = [_flat(q.get("question")) for q in _records(report, "questions")]
    questions = [q for q in questions if q][:3]
    if questions:
        rows.append({"label": "Board discussion questions",
                     "text": end_sentence("; ".join(
                         q.rstrip("?") for q in questions))})
    gaps = [_flat(g) for g in (report.get("evidence_gaps") or ())][:2]
    if gaps:
        rows.append({"label": "Diligence checklist",
                     "text": end_sentence("; ".join(
                         g.rstrip(".") for g in gaps if g))})
    return Passage("artefacts", "What this has prepared for you", depth=BOTH,
                   kind="labelled", items=tuple(rows[:4]),
                   note="Drafted here and nothing more. Nothing is sent, "
                        "published, scheduled or shared without your explicit "
                        "approval.")


def _evidence_appendix(report, index) -> Passage:
    """Every source used, with what kind of thing it is."""
    # DEDUPED BY SOURCE, NOT BY SENTENCE. This is the provenance list -- "every
    # source this rests on" -- so two pages of one site that extraction reduced
    # to the same nav text are still two sources and belong here once each,
    # while the SAME page must not appear twice.
    items = []
    seen = set()
    for obs in _observation_dicts(report):
        text = _readable_excerpt(obs)
        key = _flat(obs.get("source_title")).lower() or _flat(
            obs.get("observation_id"))
        if not text or not key or key in seen:
            continue
        seen.add(key)
        items.append(EvidenceItem(
            text=text, source_title=_flat(obs.get("source_title")),
            provenance=PROVENANCE_LABEL.get(_flat(obs.get("source_class")),
                                            "Unknown"),
            date=_flat(obs.get("date")),
            evidence_id=_flat(obs.get("observation_id"))))
    return Passage("evidence_appendix", "Every source this rests on",
                   depth=FULL, kind="evidence", items=tuple(items[:14]),
                   evidence_ids=tuple(i.evidence_id for i in items[:14]))


# --- assembly -----------------------------------------------------------------

def build_dossier(*, company: str, report: Optional[dict] = None,
                  decision=None, market=None, narrative=None,
                  documents=()) -> Dossier:
    """The canonical deep material, assembled once for both deep surfaces.

    `narrative` is the already-built primary screen. It is passed in so the
    deep layers can avoid REPEATING it: what the 60-second answer already said
    is remembered before anything here is composed, which is what makes the
    brief add to the narrative rather than restate it.
    """
    report = report or {}
    if decision is None:
        decision = decision_of(report)
    elif isinstance(decision, dict):
        decision = decision_from_dict(decision)

    hypotheses = [h.as_dict() if hasattr(h, "as_dict") else h
                  for h in (report.get("hypotheses") or ())]
    hypotheses = [h for h in hypotheses if isinstance(h, dict)]
    index = _evidence_index(_observation_dicts(report))
    families = evidence_families(report)

    # SEEDED WITH WHAT THE PRIMARY SCREEN ALREADY SAID.
    #
    # The brief is a decision memo for someone who has read the answer. Every
    # sentence it spends restating that answer is a sentence not spent on the
    # operating model, the competitive position or the assumptions -- and the
    # deployed brief spent nearly all of them that way.
    said = SaidOnce()
    if narrative is not None:
        for section in getattr(narrative, "sections", ()):
            for para in section.paragraphs:
                said.remember(para)
            # ...and its citations. The narrative already shows evidence for
            # and against, so re-showing the same excerpt under "what the
            # evidence actually says" is the brief echoing the summary.
            for item in section.items:
                if isinstance(item, EvidenceItem):
                    said.remember(item.text)

    built = [
        _operating_model(company, report, said),
        _what_was_read(company, documents, said),
        _what_changed(company, report, said),
        _customer_demand(company, report, index, said),
        _competitive(company, report, decision, hypotheses, families, said),
        _market(company, market, said),
        _analogs(company, report, decision, hypotheses, said),
        _opportunity(company, report, said),
        _risk(company, report, decision, said),
        _assumptions(company, decision, report, said),
        _scenarios(company, decision, said),
        _unknowns(company, report, decision, said),
        _monitoring(company, report, decision, said),
        _artefacts(company, decision, report, said),
        _evidence_appendix(report, index),
    ]
    return Dossier(company=company, readiness=decision.readiness,
                   decision=decision,
                   passages=tuple(p for p in built if p.is_substantive),
                   families=families)


# --- rendering ----------------------------------------------------------------

DOSSIER_CSS = """
<style>
main.dos{max-width:54rem;margin:0 auto;padding:1.5rem 1.15rem 4rem}
.dos h1{font-size:1.7rem;line-height:1.2;margin:.2rem 0 .2rem;
letter-spacing:-.015em}
.dos .kicker{font-size:.74rem;text-transform:uppercase;letter-spacing:.09em;
color:var(--muted);font-weight:700;margin:0 0 1.2rem}
.dos section{padding:1.4rem 0;border-top:1px solid var(--line)}
.dos section:first-of-type{border-top:0;padding-top:.3rem}
.dos h2{font-size:.74rem;text-transform:uppercase;letter-spacing:.09em;
color:var(--muted);margin:0 0 .6rem;font-weight:700}
.dos p{margin:0 0 .7rem;max-width:44rem}
.dos .lead p:first-child{font-size:1.15rem;line-height:1.5;font-weight:600}
.dos .lead{border-left:3px solid var(--accent);padding-left:1.1rem}
.fam{display:flex;flex-wrap:wrap;gap:.4rem;margin:.5rem 0 .2rem;padding:0}
.fam li{list-style:none;border:1px solid var(--line);border-radius:999px;
padding:.15rem .6rem;font-size:.8rem}
.fam .yes{border-color:var(--ok);color:var(--ok)}
.fam .no{border-color:var(--warn);color:var(--warn)}
.gap{color:var(--muted);font-size:.9rem;margin:.35rem 0 0}
.an{border:1px solid var(--line);border-radius:12px;padding:.9rem 1rem;
margin:.5rem 0;background:var(--card)}
.an .brk{color:var(--warn);font-size:.92rem;margin:.4rem 0 0}
.an .cases{color:var(--muted);font-size:.86rem;margin:.3rem 0 0}
@media print{.deeper{display:none}}
</style>
"""


def _p(text: str) -> str:
    from html import escape
    return f"<p>{escape(text)}</p>" if _flat(text) else ""


def render_families(families) -> str:
    """What was read and what was not — as chips, with the cost of each gap.

    A reader who cannot tell "no competitor said this" from "no competitor was
    asked" cannot judge the analysis at all.
    """
    from html import escape
    if not families:
        return ""
    chips = "".join(
        f'<li class="{"yes" if f["present"] else "no"}">{escape(f["label"])}'
        f'{" · " + str(f["count"]) if f["present"] else " — none"}</li>'
        for f in families)
    gaps = "".join(f'<p class="gap">{escape(f["consequence"])}</p>'
                   for f in families if not f["present"] and f["consequence"])
    return (f'<section id="evidence_families"><h2>What this was built from'
            f'</h2><ul class="fam">{chips}</ul>{gaps}</section>')


def render_dossier(dossier, *, depth: str, run_id: str = "",
                   citation_labels=None, lead: str = "") -> str:
    """The deep document at one depth. One `<main>`, one `<h1>`."""
    from html import escape

    from intent_engine.founder_brief.narrative import (
        _render_evidence, _render_options,
    )
    kicker = ("Executive brief — the decision memo" if depth == BRIEF
              else "Full analysis — the intelligence behind the decision")
    out = [DOSSIER_CSS, '<main class="dos">',
           f"<h1>{escape(dossier.company)}</h1>",
           f'<p class="kicker">{escape(kicker)}</p>']
    if lead:
        out.append(lead)

    for passage in dossier.at(depth):
        out.append(f'<section id="{escape(passage.key)}">')
        out.append(f"<h2>{escape(passage.title)}</h2>")
        if passage.kind == "evidence":
            out.append(_render_evidence(passage, run_id, citation_labels))
        elif passage.kind == "options":
            out.append(_render_options(passage.options))
        elif passage.kind == "labelled":
            out.append('<dl class="dl">')
            for item in passage.items:
                out.append(f'<div class="row"><dt class="k">'
                           f'{escape(str(item.get("label", "")))}</dt>'
                           f'<dd>{escape(str(item.get("text", "")))}</dd>'
                           f'</div>')
            out.append("</dl>")
        elif passage.kind == "dated":
            out.append('<ul class="ev">')
            for item in passage.items:
                src = (f'<span class="src">{escape(item["when"])}'
                       f'{" · " + escape(item["source"]) if item.get("source") else ""}'
                       f"</span>")
                out.append(f'<li>{escape(item["what"])}{src}</li>')
            out.append("</ul>")
        elif passage.kind == "analog":
            for item in passage.items:
                out.append('<div class="an">')
                out.append(_p(item["text"]))
                if item.get("breaks"):
                    out.append(f'<p class="brk">Where the comparison stops: '
                               f'{escape(item["breaks"])}</p>')
                if item.get("cases"):
                    out.append(f'<p class="cases">Seen at: '
                               f'{escape(item["cases"])}</p>')
                out.append("</div>")
        else:
            out.extend(_p(x) for x in passage.paragraphs)
        if passage.note:
            out.append(f'<p class="gap">{escape(passage.note)}</p>')
        out.append("</section>")

    out.append(render_families(dossier.families))
    if run_id:
        from intent_engine.founder_brief.render import _deeper
        out.append(_deeper(run_id))
    out.append("</main>")
    return "".join(out)


def render_decision_lead(decision, company: str = "", *, depth: str = BRIEF,
                         run_id: str = "") -> str:
    """The decision, rendered identically at both depths.

    The ANSWER is the same object the 60-second screen renders, so a reader
    moving down the layers meets one conclusion stated once and then supported
    -- never a second, quieter conclusion. `/brief` used to reach its own,
    contradicting one; this is the single place both deep surfaces get it.
    """
    from html import escape

    from intent_engine.founder_brief.narrative import _render_options
    said = SaidOnce()
    out = ['<section id="executive_answer" class="lead"><h2>The answer</h2>']
    if decision.readiness == WITHHELD:
        out.append(_p(f"No strategic reading of {company} cleared the "
                      f"evidence bar, so none is asserted here."))
        if decision.unsafe_because:
            out.append(_p(end_sentence(
                f"That absence is itself the finding: "
                f"{as_clause(decision.unsafe_because, company)}")))
    else:
        if decision.mechanism:
            out.append(_p(end_sentence(
                f"Across the public record for {company}, "
                f"{as_clause(decision.mechanism, company)}")))
            said.remember(decision.mechanism)
        # The headline names the reading when the option labels are generic
        # ("... — on whether <mechanism>"), and the line above just said it.
        # The narrative strips that tail for the same reason; this is the same
        # rule, applied where the deep layers get their headline.
        headline = _flat(decision.headline)
        if " — on whether " in headline:
            head, _, tail = headline.partition(" — on whether ")
            if said.has(tail):
                headline = end_sentence(head)
        out.append(_p(headline))
        if decision.readiness == INVESTIGATION_REQUIRED \
                and decision.unsafe_because:
            out.append(_p(end_sentence(
                f"It is not yet safe to act on, because "
                f"{as_clause(decision.unsafe_because, company)}")))
    if decision.limitation:
        out.append(_p(end_sentence(
            f"What most limits this: "
            f"{as_clause(decision.limitation, company)}")))
    out.append("</section>")

    if decision.readiness == DECISION_READY and len(decision.options) >= 2:
        from dataclasses import replace
        from intent_engine.founder_brief.narrative import _trim_option
        options = tuple(_trim_option(o) for o in decision.options[:2])
        # A watch item identical on both cards is the decision's one
        # falsification check, which "what to do next" states below.
        if len({_flat(o.watch_item) for o in options}) == 1:
            options = tuple(replace(o, watch_item="") for o in options)
        out.append('<section id="options"><h2>The options, and what each '
                   'costs</h2>')
        out.append(_render_options(options))
        out.append("</section>")

    moves = [decision.recommended_next_move,
             decision.what_each_result_would_favour, decision.reconsider_when]
    moves = [m for m in moves if _flat(m) and said.fresh(m)]
    if moves:
        out.append('<section id="next_move"><h2>What to do next</h2>')
        out.extend(_p(m) for m in moves)
        out.append("</section>")

    # The falsifier is usually the same sentence as the next check, and it
    # arrives as a QUESTION as often as a condition -- "Finding this would
    # break the reading: does a rising share of revenue come from rails?" is
    # neither grammatical nor new. Shown only when it is genuinely additional,
    # and phrased for whichever shape it is.
    falsifier = _flat(decision.falsifier)
    if falsifier and not said.has(falsifier):
        lead_in = ("The answer that would break this reading: "
                   if falsifier.rstrip().endswith("?")
                   else "Finding this would break the reading: ")
        out.append('<section id="could_be_wrong"><h2>What could make this '
                   f'wrong</h2>'
                   f'{_p(end_sentence(lead_in + as_clause(falsifier, company)))}'
                   "</section>")
    return "".join(out)
