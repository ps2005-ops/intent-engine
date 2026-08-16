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
    provenance_label,
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
    # EVERY SENTENCE HERE RENDERS WHEN THE FAMILY IS *ABSENT*, and this one
    # described the opposite situation -- "everything here is the company
    # describing itself" -- so it only became visible the first time a run had
    # NO company pages at all. Measured live on Caterpillar, whose site
    # answers 403 to automated requests: the brief asserted that everything
    # present was company-authored while nothing was present.
    ("company_owned", "The company's own pages",
     "We could not read anything the company publishes about itself, so its "
     "own account of its strategy is missing from this reading."),
    ("executive_statement", "Executive statements",
     "Leadership commentary is a claim about intent, not evidence of result."),
    ("investor_material", "Filings and investor material",
     "Without a filing there is no audited figure behind any economic "
     "statement, so revenue mix, margin and concentration stay unverifiable."),
    ("customer_voice", "Customer evidence",
     "Nothing here reports what buying and using this actually costs a "
     "customer, so adoption and retention claims cannot be tested."),
    ("competitor", "Another registrant's filing",
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


def evidence_families(report: dict, documents=()) -> tuple:
    """What was read, what was not, and what each absence costs.

    Built from `source_class_coverage`, which the pipeline already computes, so
    the inventory and the evidence actually used cannot disagree.
    """
    coverage = report.get("source_class_coverage") or {}
    # HOW HARD WE LOOKED, beside WHAT WE FOUND.
    #
    # THE DEFECT THIS CLOSES, found by driving the deployed product. This
    # section rendered "Another registrant's filing — none": a bare zero, on
    # the surface a chief executive actually reads. The measured coverage
    # state existed and reached only the provenance drawer, so the one
    # sentence that makes the zero readable was missing from the brief. This
    # module's own renderer says it: a reader who cannot tell "no competitor
    # said this" from "no competitor was asked" cannot judge the analysis.
    discovery = report.get("discovery_coverage")
    discovery = discovery if isinstance(discovery, dict) else {}
    # WHY the families are empty, when the reason is that retrieval FAILED.
    # Measured live: Caterpillar showed six empty families and no reason for
    # any of them, while the run had recorded that caterpillar.com answers
    # 403 to automated requests. Silence there reads as "this company has
    # published nothing", which is a claim about the company rather than
    # about our access to it -- the same error as a bare zero, one layer up.
    failures = report.get("retrieval_failures")
    failures = failures if isinstance(failures, dict) else {}
    blocked = _blocked_sentence(failures)
    # THE TYPED ACCOUNT, when the run produced one. `source_class_coverage`
    # counts observations only, so a filing we read and could not extract from
    # disappeared from this inventory while staying in the bibliography -- one
    # page of one analysis contradicting itself.
    typed = ((report.get("source_coverage") or {}).get("families")
             if isinstance(report.get("source_coverage"), dict) else None)
    typed = typed if isinstance(typed, dict) else {}
    # THE BIBLIOGRAPHY IS RIGHT HERE. `build_dossier` already receives the
    # retrieved documents to render the source list, and the whole defect was
    # that this inventory counted something else. When the report did not
    # carry the typed object -- an older run, or a path that rebuilt the
    # payload -- derive it from the same documents the page is about to list,
    # so the two sections cannot disagree.
    if not typed and documents:
        from intent_engine.company_ingestion import source_coverage as _SC
        typed = _SC.assess(
            documents=[d for d in documents if isinstance(d, dict)],
            observations=[{"source_class": o.get("source_class")}
                          for o in (report.get("observations") or ())
                          if isinstance(o, dict)],
            failures=failures)["families"]
    out = []
    for key, label, consequence in _FAMILIES:
        count = int(coverage.get(key) or 0)
        row = typed.get(key) or {}
        state = str(row.get("state") or "")
        docs = int(row.get("documents") or 0)
        # A family holding documents is never "none", whatever the
        # observation count says.
        present = bool(count) or bool(row.get("supports_analysis")) or docs > 0
        entry = {"key": key, "label": label, "count": count or docs,
                 "state": state, "documents": docs,
                 "present": present,
                 "consequence": "" if present else consequence}
        if not present and row.get("reason"):
            entry["consequence"] = f"{consequence} {row['reason']}"
        if docs and not count:
            entry["consequence"] = str(row.get("reason") or "")
        if not present and key == "competitor":
            entry["consequence"] = _search_sentence(discovery, consequence)
        elif not present and blocked and key in _FIRST_PARTY_FAMILIES:
            entry["consequence"] = f"{consequence} {blocked}"
        out.append(entry)
    return tuple(out)


#: Families that come from the COMPANY'S OWN publishing. A site that refuses
#: automated access explains these and nothing else -- a competitor's filing
#: is not missing because the subject's website said no.
_FIRST_PARTY_FAMILIES = frozenset({"company_owned", "executive_statement"})

#: Failure types that mean "the door was shut", as opposed to a slow or
#: malformed page. Only these license the sentence.
_ACCESS_DENIED = ("http_status", "blocked", "unsafe_redirect",
                  "javascript_only")


def _blocked_sentence(failures: dict) -> str:
    """The access failure, in the reader's terms. Empty when none was recorded.

    Deliberately does not quote a status code: a chief executive needs to know
    the site refused us, not which number it refused us with, and the evidence
    library already carries the per-source detail.
    """
    denied = sum(int(failures.get(k) or 0) for k in _ACCESS_DENIED)
    if not denied:
        return ""
    if failures.get("javascript_only"):
        return ("The company's site returns its content only to a full "
                "browser, so an automated read retrieves nothing.")
    return (f"This is not an absence of publishing: {denied} of the company's "
            f"own addresses refused automated access, so the material may "
            f"exist and be unreadable to us.")


def _search_sentence(discovery: dict, consequence: str) -> str:
    """The absence, plus whether we are entitled to call it a finding.

    Only a search that read everything it considered may say the company has
    no outside coverage. Everything else -- including no producer at all --
    is a fact about our retrieval, and saying the stronger thing is the
    flattering error this whole vocabulary exists to prevent.
    """
    from intent_engine.company_ingestion import relevance as _REL
    reading = _REL.zero_reading(
        independent_relevant=0,
        coverage=str(discovery.get("coverage") or _REL.DISCOVERY_NOT_RUN))
    considered = int(discovery.get("candidates_considered") or 0)
    read = int(discovery.get("candidates_fetched") or 0)
    effort = (f" We looked at {considered} filing(s) by other registrants and "
              f"read {read} in full." if considered else "")
    return f"{consequence} {reading['statement']}{effort}".strip()


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
        # The fifth and last call site, and the one that renders the evidence
        # list on /brief and /full — where the Figma leak was actually
        # visible. It assigns to a variable instead of inlining the lookup,
        # so a replace over `PROVENANCE_LABEL.get(...)` call shapes missed it
        # twice. Grep for the FIELD (`provenance=`), not for the call.
        label = provenance_label(
            source_class, title=_flat(obs.get("source_title")),
            focal=_flat(report.get("company_name")),
            excerpt=_flat(obs.get("excerpt")),
            origin=_flat(obs.get("origin")))
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
    order = ["Customer evidence", "Independent evidence", "Another registrant's filing",
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
                 said, external=None) -> Passage:
    """Relative position, or a stated reason there is nothing to say.

    A generic competitor list is worse than none: it is the same paragraph for
    every company in a market. What is rendered here is what the RUN actually
    read -- a competitor's own words, an independent account, or the competing
    explanations of this company's own evidence.
    """
    paras, items = [], []
    index = _evidence_index(_observation_dicts(report))

    # NAMED ALTERNATIVES FIRST, when the contract established any. This used
    # to depend entirely on whether a page whose source_class happened to be
    # `competitor` was retrieved -- Shopify had one and got a real section,
    # Palantir did not and got a stated absence, and the difference was
    # retrieval luck rather than anything about the two companies. The filing
    # they both file names their rivals in their own words.
    named_alternatives = False
    if external is not None and external.has_competitors:
        from intent_engine.external_intel import presenter as _pres
        named_alternatives = True
        for block in _pres.competitor_blocks(external):
            if said.has(block.fact):
                continue
            said.remember(block.fact)
            paras.append(end_sentence(f"{_sentence(block.fact)} "
                                      f"{block.so_what}"))
            if not said.has(block.decision):
                said.remember(block.decision)
                paras.append(end_sentence(
                    f"The choice that turns on: "
                    f"{lower_first(block.decision)}"))
            if block.limitation and not said.has(block.limitation):
                said.remember(block.limitation)
                paras.append(end_sentence(block.limitation))

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
            provenance=provenance_label(
                _flat(obs.get("source_class")),
                title=_flat(obs.get("source_title")),
                focal=_flat(report.get("company_name")),
                excerpt=_flat(obs.get("excerpt")),
                origin=_flat(obs.get("origin"))),
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

    # The absence notice fires on whether ALTERNATIVES were established, not
    # on whether `paras` is empty -- the vulnerabilities loop below also fills
    # `paras`, so keying off it suppressed the notice for a company that had a
    # vulnerability and no competitor, which is exactly when it is needed.
    if not items and not named_alternatives:
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


def _market(company, market, said, external=None) -> Passage:
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
    # WHAT CHANGED HERE. The old version printed each module's fact and its
    # "why this matters" and stopped, so a reader learned what the shares did
    # and never which choice it bore on. Every block now carries its decision
    # and what it cannot establish -- the second is what stops a price move
    # being read as a verdict on the operating strategy.
    paras, ids = [], []
    if external is not None:
        from intent_engine.external_intel import presenter as _pres
        for block in _pres.market_blocks(external):
            if said.has(block.fact):
                continue
            said.remember(block.fact)
            paras.append(end_sentence(f"{_sentence(block.fact)} "
                                      f"{block.so_what}".strip()))
            if not said.has(block.decision):
                said.remember(block.decision)
                paras.append(end_sentence(
                    f"That bears on one choice: {lower_first(block.decision)}"))
            if block.limitation and not said.has(block.limitation):
                said.remember(block.limitation)
                paras.append(end_sentence(block.limitation))
            ids.extend(block.evidence_ids)
    else:
        for name, module in (ctx.get("modules") or {}).items():
            changed, so_what = _flat(module.get("what_changed")), _flat(
                module.get("so_what"))
            if changed and not said.has(changed):
                said.remember(changed)
                paras.append(end_sentence(
                    f"{_sentence(changed)} {so_what}".strip()))
    stamp = []
    if ctx.get("as_of"):
        stamp.append(f"Market data as at {ctx['as_of']}")
    if ctx.get("stale"):
        stamp.append("older than one trading week, so it may not reflect "
                     "recent sessions")
    return Passage("market", "What the market appears to expect", depth=BOTH,
                   paragraphs=tuple(paras[:6]),
                   evidence_ids=tuple(dict.fromkeys(ids)),
                   note="; ".join(stamp) if stamp
                   else _flat(ctx.get("disclaimer")))


def _macro(company, report, decision, said, external=None) -> Passage:
    """Macro exposure — a factor, a mechanism, and a real current reading.

    THIS USED TO BE KEYWORD SPOTTING. A factor earned a line when a retrieved
    document happened to contain the word "interest rate", and what a reader
    got was the word back with a generic mechanism beside it -- no value, no
    direction, no date. There was no macro adapter wired into this path at
    all, so the honest output was almost always the limitation.

    `macro_intel.v1` replaces it: exposure is still established from this
    company's own evidence (never from its sector), and now a published
    series supplies the current reading, its direction and its date. A factor
    with an exposure but no readable series does not appear -- fail closed.
    """
    if external is not None and external.has_macro:
        from intent_engine.external_intel import presenter as _pres
        items, ids = [], []
        for block in _pres.macro_blocks(external):
            if said.has(block.fact):
                continue
            said.remember(block.fact)
            items.append({
                "label": block.fact,
                "text": end_sentence(
                    f"{block.so_what} The choice it bears on: "
                    f"{lower_first(block.decision)}")})
            ids.extend(block.evidence_ids)
        if items:
            note = _pres.macro_blocks(external)[0]
            # BOTH DEPTHS, now that it carries a real reading. The old
            # keyword-spotted version was FULL-only for a good reason -- a
            # generic mechanism with no value is not decision material for a
            # memo. A named exposure with a current figure and the choice it
            # bears on is exactly what an executive brief is for.
            return Passage(
                "macro", "Macro and industry exposure", depth=BOTH,
                kind="labelled", items=tuple(items[:3]),
                evidence_ids=tuple(dict.fromkeys(ids)),
                note=(f"Each factor is here because this company's own "
                      f"retrieved evidence establishes the exposure, not "
                      f"because it applies to companies generally. "
                      f"{note.source}. {note.limitation}"))
    hits, seen = [], SaidOnce()
    for obs in _observation_dicts(report):
        text = _readable_excerpt(obs)
        low = text.lower()
        for factor, mechanism in _MACRO_FACTORS:
            if factor not in low or seen.has(factor):
                continue
            seen.remember(factor)
            hits.append({"label": mechanism,
                         "text": _sentence(text)})
            break
    if hits:
        return Passage("macro", "Macro and regulatory exposure", depth=FULL,
                       kind="labelled", items=tuple(hits[:3]),
                       note="Named because the retrieved evidence mentions "
                            "it, not because it applies to companies "
                            "generally.")
    return Passage(
        "macro", "Macro and regulatory exposure", depth=FULL,
        paragraphs=("Nothing retrieved ties this decision to a macro or "
                    "regulatory factor, so none is asserted. That is a limit "
                    "on the evidence, not a finding that the business is "
                    "unexposed — rates, public and defence budgets, "
                    "procurement cycles and AI policy can all move a decision "
                    "like this one, and none of them was observable in what "
                    "this run could read.",))


#: A macro factor is only worth a line when the evidence NAMES it. The
#: mechanism beside each is how it would reach a decision -- without that, a
#: macro section is commentary that fits any company in any year.
_MACRO_FACTORS = (
    ("interest rate", "Cost of capital"),
    ("inflation", "Cost of capital"),
    ("defense spending", "Public budget exposure"),
    ("defence spending", "Public budget exposure"),
    ("government budget", "Public budget exposure"),
    ("appropriation", "Public budget exposure"),
    ("procurement", "Procurement cycle"),
    ("tariff", "Trade exposure"),
    ("regulation", "Regulatory exposure"),
    ("regulatory", "Regulatory exposure"),
    ("gdpr", "Regulatory exposure"),
    ("ai act", "AI policy exposure"),
    ("export control", "Trade exposure"),
    ("foreign exchange", "Currency exposure"),
    ("currency", "Currency exposure"),
)


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


def _checkable(text: str) -> bool:
    """Whether a reader could actually go and observe this.

    THE SAME FILTER THE DECK ALREADY APPLIES, arriving here late. Measured
    live at `bdbc0d0`: HubSpot's and Datadog's full analyses both told the
    reader to watch for "customers describing it as a companion to a system of
    record rather than the record itself" — `tool_to_system_of_record`'s own
    falsification question, in vocabulary the reader has never met and cannot
    check. The deck filters exactly this through `_watchable`; the dossier
    read the same field and did not.

    Dropped, never reworded: a watch item a reader cannot observe is worse
    than a shorter list, and generic filler is worse than both.
    """
    from intent_engine.strategic_intelligence.concrete import reads_as_taxonomy
    text = (text or "").strip()
    return bool(text) and not reads_as_taxonomy(text)


def _monitoring(company, report, decision, said) -> Passage:
    """A prioritised watch list: the question, and what it would settle."""
    rows = []
    for row in _records(report, "questions"):
        question = _flat(row.get("question"))
        why = _readable_reason(row.get("why_it_matters"))
        if not question or said.has(question) or not _checkable(question):
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


def _what_was_read(company, documents, observations, said) -> Passage:
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
    # ONLY WHEN THERE IS NOTHING BETTER. On a rich run this listed eight
    # undated entries -- "Careers.", "Palantir IR." -- that the evidence
    # sections and the appendix already cover properly. It exists for the
    # bounded path, where it is the only company-specific footing there is.
    if observations:
        return Passage("what_was_read", "What could actually be read")
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
    # Same rule as the watch list above: a question a board cannot investigate
    # is worse than one fewer question. See `_checkable`.
    questions = [q for q in questions if _checkable(q)][:3]
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
        # A filing whose extractable text is all cover-page furniture yields
        # no quotation -- but it WAS read, and dropping it hid the single most
        # authoritative source in the run from the provenance list. Listed
        # with no quotation rather than not listed.
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(EvidenceItem(
            text=text, source_title=_flat(obs.get("source_title")),
            provenance=provenance_label(
                _flat(obs.get("source_class")),
                title=_flat(obs.get("source_title")),
                focal=_flat(report.get("company_name")),
                excerpt=_flat(obs.get("excerpt")),
                origin=_flat(obs.get("origin"))),
            date=_flat(obs.get("date")),
            evidence_id=_flat(obs.get("observation_id"))))
    return Passage("evidence_appendix", "Every source this rests on",
                   depth=FULL, kind="evidence", items=tuple(items[:14]),
                   evidence_ids=tuple(i.evidence_id for i in items[:14]))


# --- assembly -----------------------------------------------------------------

def build_dossier(*, company: str, report: Optional[dict] = None,
                  decision=None, market=None, narrative=None,
                  documents=(), external=None) -> Dossier:
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
    families = evidence_families(report, documents or ())

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
        _what_was_read(company, documents, _observation_dicts(report), said),
        _what_changed(company, report, said),
        _customer_demand(company, report, index, said),
        _competitive(company, report, decision, hypotheses, families, said,
                     external),
        _market(company, market, said, external),
        _macro(company, report, decision, said, external),
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
                   citation_labels=None, lead: str = "",
                   wrap: bool = True, charts=None) -> str:
    """The deep document at one depth. One `<main>`, one `<h1>`.

    `wrap=False` emits a `<div>` instead, for a route that already opens its
    own `<main>`. The full-analysis page does, and rendering both put TWO main
    landmarks on the longest page in the product -- so a screen reader's "skip
    to main content" could land on either.

    `charts` maps an external-context block key to rendered SVG. A chart is
    placed after the passage's prose, so the conclusion is read first and the
    picture confirms it rather than having to be decoded.
    """
    from html import escape

    from intent_engine.founder_brief.narrative import (
        _render_evidence, _render_options,
    )
    kicker = ("Executive brief — the decision memo" if depth == BRIEF
              else "Full analysis — the intelligence behind the decision")
    tag = "main" if wrap else "div"
    out = [DOSSIER_CSS, f'<{tag} class="dos">',
           f"<h1>{escape(dossier.company)}</h1>",
           f'<p class="kicker">{escape(kicker)}</p>']
    if lead:
        out.append(lead)

    charts = charts or {}
    #: Which chart belongs under which passage. Only these three passages
    #: gain one -- a chart under a passage that does not discuss it is
    #: decoration, and decoration is what makes a reader stop trusting the
    #: ones that mean something.
    _CHART_FOR = {"market": ("market_trajectory", "market_risk"),
                  "macro": tuple(k for k in charts if k.startswith("macro_")),
                  "competitive": ("competitive_pressure",)}

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
        for key in _CHART_FOR.get(passage.key, ()):
            if charts.get(key):
                out.append(charts[key])
        if passage.note:
            out.append(f'<p class="gap">{escape(passage.note)}</p>')
        out.append("</section>")

    out.append(render_families(dossier.families))
    if run_id:
        from intent_engine.founder_brief.render import _deeper
        out.append(_deeper(run_id))
    out.append(f"</{tag}>")
    return "".join(out)


def render_decision_lead(decision, company: str = "", *, depth: str = BRIEF,
                         run_id: str = "", contract=None) -> str:
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
        # D17. "THIS RUN FOUND NOTHING" IS NOT "THERE IS NOTHING".
        #
        # This asserted the second because it could only see the first. On a
        # company the market engine has a published reading for, the X-Ray
        # said "Supported in direction, not in size · Pricing decision" while
        # this line said no reading had cleared the bar -- one product, two
        # opposite answers, two clicks apart.
        #
        # The refusal is still rendered when it is TRUE. What changed is that
        # whether a reading exists is no longer decided here; it is read from
        # the one contract every executive surface consults. The reasoning
        # prose below is untouched, because the brief's job is still to
        # explain what THIS run could and could not establish.
        if contract is not None and getattr(contract, "reading_exists", False):
            out.append(_p(
                f"A supported reading of {company} exists and is set out on "
                f"the Executive X-Ray."))
            out.append(_p(getattr(contract, "run_contribution", "") or
                          "This run did not add enough independent evidence "
                          "to strengthen it."))
            if decision.unsafe_because:
                out.append(_p(end_sentence(
                    f"What this run could not establish on its own: "
                    f"{as_clause(decision.unsafe_because, company)}")))
        else:
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
        said.remember(headline)
        # The bounded headline EMBEDS the reason ("No option is safe to commit
        # to yet: <reason> — so this is held open rather than settled"), so
        # restating it below printed the same clause twice in adjacent
        # sentences. Measured live on Basecamp.
        if decision.readiness == INVESTIGATION_REQUIRED \
                and decision.unsafe_because \
                and not said.has(decision.unsafe_because):
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
