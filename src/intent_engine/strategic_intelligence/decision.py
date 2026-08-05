"""The founder's decision, composed once and used by every surface.

WHAT WAS WRONG
--------------
`implications[0]` is a decision TOPIC. The product presented it as a finished
decision:

    Whether to keep investing in depth or in adjacency.
    Whether to price the product separately from implementation.
    Whether enterprise or SMB requirements set the operating standard.

Those are questions. A founder reading one learns that a choice exists, which
they knew before opening the page. The topic names the subject; it does not
say what the options are, what each costs, which one the evidence leans
toward, what assumption each rests on, or what result would settle it. Every
surface -- deck, brief, full analysis, Q&A -- printed the question and called
it the answer, because every surface read the same field.

WHAT THIS MODULE DOES
---------------------
It composes the decision ONCE, from material the reasoning layer already
produced, and every surface renders that one object. Nothing is generated:

    topic          <- implications[0]            (internal; never the answer)
    mechanism      <- the pattern's reasoning, minus its self-description
    options        <- the topic's own branches, else the hypothesis and the
                      library's alternative explanation of the same evidence
    evidence       <- the hypothesis's supporting and counter observation ids
    falsifier      <- falsification_questions
    limitation     <- evidence_gaps
    consequence    <- the blind spot's `why_it_may_matter`

WHEN IT REFUSES
---------------
Two defensible options or none. A decision with one option is not a decision,
and inventing the second one -- which is what "balanced" prose does when the
evidence is one-sided -- is the failure this product exists to avoid. Where
the material cannot support two, readiness is INVESTIGATION_REQUIRED: the
founder is told what was verified, why committing is unsafe, exactly which
evidence is missing, one bounded thing to go and find out, and what each
result would favour. That is useful direction without a fabricated decision.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from intent_engine.strategic_intelligence import filing_hygiene as FH
from intent_engine.strategic_intelligence.concrete import reads_as_taxonomy

#: A choice can be made on what is known.
DECISION_READY = "DECISION_READY"
#: A real question exists; the public record cannot yet settle it.
INVESTIGATION_REQUIRED = "INVESTIGATION_REQUIRED"
#: No view was formed at all, so no decision is put forward.
WITHHELD = "WITHHELD"

READINESS_STATES = (DECISION_READY, INVESTIGATION_REQUIRED, WITHHELD)

_CONF_RANK = {"speculative": 0, "low": 1, "moderate": 2, "high": 3}

# Openers that mark a sentence as a decision topic rather than a claim. The
# same shapes the founder-brief contract rejects, listed here because this is
# where the topic is TAKEN APART rather than merely refused.
_TOPIC_OPENERS = (
    "whether to ", "how much to ", "how many to ", "how to ", "how fast to ",
    "how far to ", "how quickly to ",
)
# "How much roadmap and org focus to shift to enterprise" -- the opener and the
# infinitive are separated by the thing being decided about.
_SPLIT_OPENER = re.compile(r"^(?:whether|how(?:\s+\w+){0,3}?)\s+to\s+", re.I)
_BRANCH_SPLIT = re.compile(r"\s+(?:vs\.?|versus|or)\s+", re.I)
#: a branch shorter than this is not a course of action ("two", "absorb")
_MIN_BRANCH_WORDS = 3


def _get(obj, field_name, default=""):
    """Records from the reasoning layer, dicts once serialised. Same thing."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        value = obj.get(field_name, default)
    else:
        value = getattr(obj, field_name, default)
    return default if value is None else value


def _flat(text) -> str:
    return " ".join(str(text or "").split())


def _lower_first(text: str, company: str = "") -> str:
    """Lowercase an opening word unless it is a name.

    Two wrong answers were both visible on composed output. Lowering whatever
    looks like "capital then lowercase" gives "while acme appears to be
    repositioning" -- it mangles the one word in the sentence that had to
    survive. Preserving anything not on a function-word list gives "If instead
    Breadth is defensive bundling", which reads as a typo.

    So: preserve what is recognisably a NAME -- an acronym, an internal
    capital, or this company -- and lower everything else. The residual error
    is a third party's name mid-sentence, which is rare in curated library
    prose and costs a lowercase letter rather than a mangled subject.
    """
    text = _flat(text)
    if not text:
        return ""
    first = text.split(" ", 1)[0]
    bare = first.strip(".,:;!?'\"")
    if not first[:1].isupper():
        return text
    keep = (bare.isupper()                       # AI, SMB, GMV
            or any(c.isupper() for c in bare[1:])  # iPhone, YouTube
            or (company and bare.lower().startswith(company.split()[0].lower())))
    return text if keep else text[0].lower() + text[1:]


def _clause(text: str, company: str = "") -> str:
    """A sentence made fit to sit inside another one.

    Two jobs, both visible on the first composed output: the opening capital
    has to give way, and the terminal stop has to go -- "If instead the
    products are packaging around what remains a services business. the
    commitment is spent against nothing." is two broken sentences wearing one
    sentence's punctuation.
    """
    return _lower_first(_flat(text).rstrip(" .;,"), company)


def _stop(text: str) -> str:
    """End a composed sentence exactly once.

    Falsification entries arrive as questions AND as conditions, so a template
    that appends its own full stop produced "...net-new revenue and roadmap?."
    """
    text = _flat(text)
    return text if not text or text[-1] in ".?!" else text + "."


def _claim(text: str) -> str:
    """A founder-facing claim, or "".

    The SAME contract the deck and the brief apply, imported rather than
    restated: a claim needs a finite assertion and may not be ontology
    vocabulary, a page title, a metadata sentence or a bare topic. Composing a
    decision out of strings that would be rejected downstream just moves the
    empty slide one layer earlier.
    """
    from intent_engine.founder_brief.build import _is_consequence
    text = _flat(text).rstrip()
    if not text or reads_as_taxonomy(text):
        return ""
    return text if _is_consequence(text) else ""


def as_clause(text: str, company: str = "") -> str:
    """Public: a sentence made fit to sit inside another one.

    Exposed because the narrative renderer builds sentences around the SAME
    composed strings. A renderer that lowercases and de-punctuates its own way
    is how one mechanism comes to read as two -- "If instead Breadth is
    defensive bundling" on one surface and "if instead breadth is..." on the
    next.
    """
    return _clause(text, company)


def end_sentence(text: str) -> str:
    """Public: end a composed sentence exactly once. See `_stop`."""
    return _stop(text)


def lower_first(text: str, company: str = "") -> str:
    """Public: lowercase an opening word unless it is a name. See `_lower_first`."""
    return _lower_first(text, company)


def mechanism_sentence(hypothesis) -> str:
    """The founder-usable half of a hypothesis's reasoning. See `_mechanism_of`.

    Public because the full analysis needs the same sentence, and computing it
    twice is how two surfaces come to describe one mechanism differently.
    """
    return _mechanism_of(hypothesis)


def _mechanism_of(hypothesis) -> str:
    """The business mechanism, with the library's self-description removed.

    Scaffold reasoning is two sentences welded together: "<signals> match the
    product→platform mechanism: value and lock-in migrate from the visible
    product to the rails underneath it." The first half is the analysis
    reporting that its own rule fired. The second half is the only part a
    founder can use, and it was never separated from the first, so the whole
    string was either shown (leaking the pattern id) or dropped (losing the
    mechanism). It is one colon.
    """
    reasoning = _flat(_get(hypothesis, "reasoning"))
    if ":" in reasoning:
        tail = reasoning.split(":", 1)[1].strip()
        claim = _claim(tail)
        if claim:
            return claim
    return _claim(reasoning) or _claim(_get(hypothesis, "statement"))


def _evidence_ids(hypothesis, kind: str) -> tuple:
    """Curated ids first, the full list as the fallback."""
    if kind == "support":
        ids = (list(_get(hypothesis, "strongest_support_ids", []) or [])
               or list(_get(hypothesis, "supporting_observation_ids", []) or []))
    else:
        ids = (list(_get(hypothesis, "strongest_counter_ids", []) or [])
               or list(_get(hypothesis, "counter_observation_ids", []) or []))
    return tuple(str(i) for i in ids if i)


def _first_claim(items) -> str:
    for item in (items or ()):
        text = item if isinstance(item, str) else _get(item, "text")
        claim = _claim(text)
        if claim:
            return claim
    return ""


def _branches(topic: str) -> tuple:
    """The two courses of action a decision topic names, or ().

    "Whether to invest ahead of demand in owning checkout rails vs. deepening
    the core product" contains its own options, and reading them off the topic
    is strictly better than framing the choice around the analysis: the words
    are the ones a founder would use about their own roadmap.

    Deliberately strict. A topic that does not open with a decision word, or
    whose branches are a stub ("Whether to run one roadmap or two"), yields
    nothing -- and the caller falls back rather than shipping "two" as an
    option a founder is asked to weigh.
    """
    flat = _flat(topic).rstrip(".")
    low = flat.lower()
    if not low.startswith(_TOPIC_OPENERS) and not _SPLIT_OPENER.match(flat):
        return ()
    stem = _SPLIT_OPENER.sub("", flat, count=1).strip()
    parts = _BRANCH_SPLIT.split(stem, maxsplit=1)
    if len(parts) != 2:
        return ()
    left, right = (p.strip(" ,;.") for p in parts)
    for part in (left, right):
        if len(part.split()) < _MIN_BRANCH_WORDS or reads_as_taxonomy(part):
            return ()
    return (left, right)


#: a label may not END on one of these -- "Invest ahead of demand in owning"
_DANGLING = frozenset("""
a an the and or but of in on at to for with from by into onto over under as
that which while without toward towards than then its their our
""".split())


def _label(text: str, *, limit: int = 64) -> str:
    """A short handle for an option. Never the whole sentence -- a label a
    reader cannot scan is a paragraph wearing a label's clothes.

    Trailing function words are dropped after the cut: a label ending "in
    owning" reads as a truncation bug rather than as a shortened option, and
    it was one on the first composed output.
    """
    text = _flat(text).rstrip(" .;,")
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0]
    words = text.split()
    while len(words) > 2 and words[-1].strip(",;").lower() in _DANGLING:
        words.pop()
    text = " ".join(words).rstrip(" .;,")
    return text[:1].upper() + text[1:] if text else ""


@dataclass
class DecisionOption:
    """One course of action, with what it wins, what it costs, and what it
    assumes. An option that cannot state all three is not an option."""
    label: str = ""
    description: str = ""
    upside: str = ""
    downside: str = ""
    key_assumption: str = ""
    supporting_evidence_ids: tuple = ()
    contradicting_evidence_ids: tuple = ()
    watch_item: str = ""
    business_consequence: str = ""
    #: which side of the trade-off this is -- "act" on the reading, or "hold"
    #: for the competing account. Internal: a renderer needs it to refer back
    #: to the right one ("that the reading above holds" vs "that the competing
    #: account above holds"), and string-matching the assumption against the
    #: upside gets it wrong, because the holding option's upside restates the
    #: alternative it assumes.
    stance: str = ""

    @property
    def is_defensible(self) -> bool:
        """A founder can weigh this against another one.

        Description, upside and downside are all required: a trade-off with no
        cost is advocacy, and this is the exact check that stops a second
        option being conjured for symmetry.
        """
        return bool(self.description and self.upside and self.downside)

    def as_dict(self) -> dict:
        out = asdict(self)
        out["supporting_evidence_ids"] = list(self.supporting_evidence_ids)
        out["contradicting_evidence_ids"] = list(
            self.contradicting_evidence_ids)
        return out


@dataclass
class FounderDecision:
    """What the analysis says a founder should do about what it found."""
    topic: str = ""                     #: INTERNAL. Never rendered as the answer.
    mechanism: str = ""
    readiness: str = INVESTIGATION_REQUIRED
    options: tuple = ()
    recommended_next_move: str = ""
    recommendation_reason: str = ""
    limitation: str = ""
    falsifier: str = ""
    watch_items: tuple = ()
    # --- the honest investigation state -----------------------------------
    unsafe_because: str = ""
    evidence_required: tuple = ()
    what_each_result_would_favour: str = ""
    reconsider_when: str = ""
    verified: tuple = ()
    #: how the options were derived -- "topic" or "alternative". Internal.
    basis: str = ""

    @property
    def is_ready(self) -> bool:
        return self.readiness == DECISION_READY

    @property
    def undecided_question(self) -> str:
        """The topic, rendered ONLY as the open question it is.

        The topic still has to reach the founder -- "which decision remains
        unsafe" is unanswerable without it. What it may never do is stand
        where the answer goes, so it is available under this name, with a
        question mark, and nowhere else.
        """
        if self.is_ready or not self.topic:
            return ""
        text = _flat(self.topic).rstrip(".")
        return text + "?" if text else ""

    @property
    def headline(self) -> str:
        """One sentence stating the decision. Never the topic."""
        if self.readiness == WITHHELD:
            return ("No decision is put forward: the public record did not "
                    "carry enough to read one from.")
        # "versus", not "and". The founder-brief contract requires a decision
        # to name its alternative -- without one it is an instruction -- and
        # "the choice is between A and B" reads as a single compound thing.
        if self.is_ready and len(self.options) >= 2:
            # WHEN THE LABELS ARE GENERIC, THE HEADLINE MUST NOT BE.
            #
            # Options read off the decision topic are already in the
            # founder's own words ("invest ahead of demand in owning
            # checkout rails versus deepening the core product"). Options
            # derived from the competing explanation are not -- they are
            # "commit now" and "hold", which is the same sentence for eight
            # of the twelve patterns. A founder comparing two companies
            # would have seen one headline twice, so the reading being
            # decided about is named here.
            head = (f"The choice: {self.options[0].label} versus "
                    f"{_lower_first(self.options[1].label)}.")
            if self.basis == "alternative" and self.mechanism:
                head = (f"{head.rstrip('.')} — on whether "
                        f"{_clause(self.mechanism)}.")
            return head
        if self.unsafe_because:
            return (f"No option is safe to commit to yet: "
                    f"{_lower_first(self.unsafe_because)} — so this is held "
                    f"open rather than settled.")
        return ("No option is safe to commit to yet, so this is held open "
                "rather than settled.")

    def as_dict(self) -> dict:
        return {
            "topic": self.topic,
            "mechanism": self.mechanism,
            "readiness": self.readiness,
            "options": [o.as_dict() for o in self.options],
            "recommended_next_move": self.recommended_next_move,
            "recommendation_reason": self.recommendation_reason,
            "limitation": self.limitation,
            "falsifier": self.falsifier,
            "watch_items": list(self.watch_items),
            "unsafe_because": self.unsafe_because,
            "evidence_required": list(self.evidence_required),
            "what_each_result_would_favour": self.what_each_result_would_favour,
            "reconsider_when": self.reconsider_when,
            "verified": list(self.verified), "basis": self.basis,
            # derived, so a renderer never has to re-derive them and drift
            "headline": self.headline,
            "undecided_question": self.undecided_question,
        }


def decision_of(report) -> FounderDecision:
    """The one decision for a report, however that report reached this layer.

    `_build_thesis` composes it and every deterministic run carries it. A
    report assembled elsewhere -- a fixture, a stored artifact from before
    this field existed, an analysis built by another producer -- is composed
    from on the spot rather than left to fall back to the raw topic, because
    "the surface renders the topic when the decision is missing" is exactly
    the defect this replaces.
    """
    r = report.as_dict() if hasattr(report, "as_dict") else (report or {})
    thesis = r.get("thesis") or {}
    stored = thesis.get("decision")
    if stored:
        return decision_from_dict(stored)

    hypotheses = [h.as_dict() if hasattr(h, "as_dict") else h
                  for h in (r.get("hypotheses") or ())]
    hypotheses = [h for h in hypotheses if isinstance(h, dict)]
    # Same rule as the producer: the portfolio, not only its first entry.
    observations = [o.as_dict() if hasattr(o, "as_dict") else o
                    for o in (r.get("observations") or ())]
    # Filing furniture is filtered BEFORE the cap, not after: a 10-K's cover
    # page sorts first in the document, so taking [:3] and cleaning afterwards
    # left the slide with nothing. See `filing_hygiene` for the measurement.
    verified = tuple(FH.executive_safe(
        (o.get("excerpt") or o.get("text") or "")
        for o in observations if isinstance(o, dict) and not o.get("weak")
    ))[:3]
    return decide_across(
        r.get("company_name", ""), hypotheses,
        r.get("blind_spots") or (), evidence_gaps=r.get("evidence_gaps") or (),
        verified=verified)


def decision_from_dict(data) -> FounderDecision:
    """Rebuild the object from a serialised report."""
    if isinstance(data, FounderDecision):
        return data
    data = data or {}
    options = tuple(
        DecisionOption(
            label=o.get("label", ""), description=o.get("description", ""),
            upside=o.get("upside", ""), downside=o.get("downside", ""),
            key_assumption=o.get("key_assumption", ""),
            supporting_evidence_ids=tuple(
                o.get("supporting_evidence_ids") or ()),
            contradicting_evidence_ids=tuple(
                o.get("contradicting_evidence_ids") or ()),
            watch_item=o.get("watch_item", ""),
            business_consequence=o.get("business_consequence", ""),
            # Carried through the round trip. Dropping it here left every
            # option with an empty stance on the served page -- the decision
            # reaches a surface as a stored dict, not as the composed object --
            # so both cards pointed at "the competing account above" and one
            # of them meant the opposite.
            stance=o.get("stance", ""))
        for o in (data.get("options") or ()) if isinstance(o, dict))
    return FounderDecision(
        topic=data.get("topic", ""), mechanism=data.get("mechanism", ""),
        readiness=data.get("readiness", INVESTIGATION_REQUIRED),
        options=options,
        recommended_next_move=data.get("recommended_next_move", ""),
        recommendation_reason=data.get("recommendation_reason", ""),
        limitation=data.get("limitation", ""),
        falsifier=data.get("falsifier", ""),
        watch_items=tuple(data.get("watch_items") or ()),
        unsafe_because=data.get("unsafe_because", ""),
        evidence_required=tuple(data.get("evidence_required") or ()),
        what_each_result_would_favour=data.get(
            "what_each_result_would_favour", ""),
        reconsider_when=data.get("reconsider_when", ""),
        # Rehydration filters too: a decision serialised before this rule
        # existed still carries the cover page in its stored `verified`.
        verified=tuple(FH.executive_safe(data.get("verified") or ())),
        basis=data.get("basis", ""))


# --- composition --------------------------------------------------------------

def _readable_reason(reasons) -> str:
    """The first confidence reason that is about the EVIDENCE, in a reader's
    words.

    The first entry is always a signal-matching trace ("3 qualifying signal(s)
    matched: ..."), which is the system describing its own machinery.

    Two more shapes are refused, because confidence reasons are written for the
    reasoning layer and were never translated for a reader the way evidence
    gaps were. "all support comes from company-owned pages, which is one-sided;
    independent corroboration is missing" carries a word this product's own
    contract lists as internal vocabulary, and "corroborated across an
    independent vantage point (customer_voice, independent_reporting)" prints
    the source taxonomy verbatim. Both would have reached the founder on the
    new decision screen; the gaps say the same things in English and are
    already used where this returns "".
    """
    from intent_engine.founder_brief.contract import INTERNAL_VOCABULARY
    from intent_engine.strategic_intelligence.records import SOURCE_CLASSES
    for reason in (reasons or ()):
        low = str(reason).lower()
        if "signal" in low or "qualifying" in low or "capped" in low:
            continue
        if any(token in low for token in INTERNAL_VOCABULARY):
            continue
        if any(cls in low for cls in SOURCE_CLASSES):
            continue
        # "supported from 1 vantage point(s): the company" is counting, not
        # explaining, and the "(s)" is a template that never chose a plural.
        # A founder-facing sentence clears the same claim contract as every
        # other one on the page.
        if "(s)" in low:
            continue
        text = _flat(reason)
        if text and _claim(text):
            return text[:1].upper() + text[1:]
    return ""


def _options_from_topic(topic, hypothesis, mechanism, alternative,
                        consequence, falsifiers, company="") -> tuple:
    """Two options in the founder's own vocabulary, read off the topic."""
    branches = _branches(topic)
    if not branches:
        return ()
    left, right = branches
    support = _evidence_ids(hypothesis, "support")
    counter = _evidence_ids(hypothesis, "counter")
    watch_a = falsifiers[0] if falsifiers else ""
    watch_b = falsifiers[-1] if len(falsifiers) > 1 else watch_a

    first = _act_option(
        _label(left), f"This path commits to {_clause(left, company)}.",
        mechanism, alternative, support, counter, watch_a, consequence, company)
    second = _hold_option(
        _label(right),
        f"This path commits to {_clause(right, company)} instead.",
        mechanism, alternative, counter, support, watch_b, consequence, company)
    return (first, second)


# THE TWO SIDES ARE THE SAME TWO SIDES.
#
# Whether the options are read off the topic or off the competing explanation,
# one of them acts on the reading and the other does not, and the trade-off
# between them is identical: the mechanism is what acting wins and what
# waiting costs, the alternative explanation is what acting risks and what
# waiting protects. Writing that once means the two sources cannot drift into
# describing different trade-offs for the same evidence.

def _act_option(label, description, mechanism, alternative, support, counter,
                watch, consequence, company="") -> DecisionOption:
    return DecisionOption(
        label=label,
        description=_claim(_stop(description)),
        upside=_claim(_stop(f"If this reading holds, "
                            f"{_clause(mechanism, company)}"))
        if mechanism else "",
        downside=_claim(f"If instead {_clause(alternative, company)}, the "
                        f"commitment is spent against nothing.")
        if alternative else "",
        key_assumption=mechanism,
        supporting_evidence_ids=support, contradicting_evidence_ids=counter,
        watch_item=watch, business_consequence=consequence, stance="act")


def _hold_option(label, description, mechanism, alternative, support, counter,
                 watch, consequence, company="") -> DecisionOption:
    return DecisionOption(
        label=label,
        description=_claim(_stop(description)),
        upside=_claim(f"If {_clause(alternative, company)}, nothing has been "
                      f"committed against it.") if alternative else "",
        downside=_claim(_stop(
            f"If this reading holds instead, waiting costs whatever follows "
            f"from it: {_clause(mechanism, company)}")) if mechanism else "",
        key_assumption=alternative,
        supporting_evidence_ids=support, contradicting_evidence_ids=counter,
        watch_item=watch, business_consequence=consequence, stance="hold")


def _options_from_alternatives(hypothesis, mechanism, alternative,
                               consequence, falsifiers, company="") -> tuple:
    """The choice the evidence itself poses: act on the reading, or hold.

    The library's alternative explanation is not a rhetorical hedge -- it is a
    competing account of the SAME evidence, curated alongside the pattern, and
    a founder who believes it does something different tomorrow. That makes it
    the second option, and it is available for every pattern in the library
    because a hypothesis without one does not validate.
    """
    if not (mechanism and alternative):
        return ()
    support = _evidence_ids(hypothesis, "support")
    counter = _evidence_ids(hypothesis, "counter")
    watch_a = falsifiers[0] if falsifiers else ""
    watch_b = falsifiers[-1] if len(falsifiers) > 1 else watch_a

    # DESCRIPTION IS THE ACTION, NOT THE READING.
    #
    # Both descriptions used to open "Plan as though ...: <mechanism>", which
    # is the SAME sentence the option's upside states -- so option one's card
    # carried the mechanism three times over (description, upside, key
    # assumption) and the deck showed all three. The description now says what
    # management would actually do; what the option wins stays on the upside,
    # where a reader looking for the trade-off goes to find it.
    first = _act_option(
        "Commit to the reading now",
        "Management plans, resources and prices as though this is already "
        "true, without waiting for an outside source to confirm it.",
        mechanism, alternative, support, counter, watch_a, consequence, company)
    second = _hold_option(
        "Hold and verify first",
        f"Plan as though the plainer account is right: "
        f"{_clause(alternative, company)}",
        mechanism, alternative, counter, support, watch_b, consequence, company)
    return (first, second)


def decide_across(company_name, hypotheses, blind_spots=(),
                  evidence_gaps=(), verified=()) -> FounderDecision:
    """The portfolio's decision, not just its top-ranked hypothesis's.

    Measured on the deployed preview: Shopify and Palantir both ranked
    `tool_to_system_of_record` first, whose mechanism is the library
    describing itself and is correctly filtered -- so both said "the public
    record carries what this company says about itself, not the mechanism
    behind it" while the SAME page printed a mechanism for the hypothesis
    ranked second. Refusing to decide because the top-ranked reading cannot
    be explained, when a ranked reading below it can, is a refusal the
    evidence does not call for.

    Ranking still decides the central claim. This decides only which reading
    the DECISION is about, and the composed object carries its own mechanism
    and evidence, so what a reader sees stays self-consistent.
    """
    ordered = list(hypotheses or ())
    if not ordered:
        return compose_decision(company_name, None, blind_spots,
                                evidence_gaps=evidence_gaps, verified=verified)
    first = None
    for hypothesis in ordered:
        decision = compose_decision(company_name, hypothesis, blind_spots,
                                    evidence_gaps=evidence_gaps,
                                    verified=verified)
        if decision.is_ready:
            return decision
        if first is None:
            first = decision
    return first


def compose_decision(company_name, hypothesis, blind_spots=(),
                     evidence_gaps=(), verified=()) -> FounderDecision:
    """The one decision object every surface renders.

    `company_name` is carried for the withheld sentence only; nothing here is
    per-company, and nothing is hardcoded for any one company.
    """
    blind = list(blind_spots or ())
    gaps = [g for g in (evidence_gaps or ()) if _flat(g)]
    # THE chokepoint: this is the one decision object every surface renders,
    # so filing furniture is refused here rather than at each caller. Filtering
    # only `decision_of` left the live decision page and slide 1 still showing
    # a 10-K cover page -- the unit tests passed and the product did not
    # change, which is why this is filtered where every surface converges.
    verified = tuple(FH.executive_safe(
        _flat(v) for v in (verified or ()) if _flat(v)))

    if hypothesis is None:
        return FounderDecision(
            readiness=WITHHELD, verified=verified,
            limitation=_flat(gaps[0]) if gaps else "",
            unsafe_because=(f"What {company_name} has published is not enough "
                            f"to read a strategy from."),
            evidence_required=tuple(_flat(g) for g in gaps[:3]))

    topic = _flat(_first(_get(hypothesis, "decision_implications", [])))
    mechanism = _mechanism_of(hypothesis)
    alternative = _first_claim(_get(hypothesis, "alternative_explanations", []))
    falsifiers = tuple(
        f for f in (_flat(q) for q in
                    _get(hypothesis, "falsification_questions", []) or ())
        if f and not reads_as_taxonomy(f))
    consequence = ""
    for spot in blind:
        consequence = _claim(_get(spot, "why_it_may_matter"))
        if consequence:
            break
    limitation = _flat(gaps[0]) if gaps else _flat(
        _first(_get(hypothesis, "evidence_gaps", [])))

    options = _options_from_topic(topic, hypothesis, mechanism, alternative,
                                  consequence, falsifiers, company_name)
    basis = "topic" if options else ""
    if not options:
        options = _options_from_alternatives(
            hypothesis, mechanism, alternative, consequence, falsifiers,
            company_name)
        basis = "alternative" if options else ""
    options = tuple(o for o in options if o.is_defensible)

    confidence = str(_get(hypothesis, "confidence", "")).lower()
    reason = _readable_reason(_get(hypothesis, "confidence_reasons", []))
    falsifier = falsifiers[0] if falsifiers else ""
    watch_items = tuple(dict.fromkeys(
        list(falsifiers) + [_flat(e) for spot in blind
                            for e in _get(spot, "evidence_needed", []) or ()]
    ))[:3]

    decision = FounderDecision(
        topic=topic, mechanism=mechanism, options=options,
        limitation=limitation, falsifier=falsifier, watch_items=watch_items,
        recommendation_reason=reason, verified=verified, basis=basis,
        evidence_required=tuple(_flat(g) for g in gaps[:3]) or (
            tuple(_flat(g) for g in
                  _get(hypothesis, "evidence_gaps", [])[:3])))

    # TWO DEFENSIBLE OPTIONS, OR NONE.
    #
    # Speculative confidence is excluded even when two options composed
    # cleanly: the options would be real and the evidence behind choosing
    # between them would not, which is a more expensive mistake than saying so.
    if len(options) >= 2 and _CONF_RANK.get(confidence, 0) >= 1:
        decision.readiness = DECISION_READY
        # Phrased to carry a falsification QUESTION and a falsification
        # CONDITION equally: the library holds both ("Is enterprise becoming a
        # majority of net-new revenue?" and "Published pricing that assumes no
        # implementation engagement"), and a template that says "the question
        # is:" turns the second one into broken English.
        decision.recommended_next_move = (
            _stop(f"One check separates them: "
                  f"{_clause(falsifier, company_name)}")
            if falsifier else
            (_stop(f"Commit to {_clause(options[0].label, company_name)} only "
                   f"once this closes: "
                   f"{_clause(decision.evidence_required[0], company_name)}")
             if decision.evidence_required else ""))
        return decision

    decision.readiness = INVESTIGATION_REQUIRED
    decision.unsafe_because = _unsafe_because(
        options, confidence, reason, mechanism, alternative)
    decision.recommended_next_move = (
        _stop(f"One bounded check comes before any commitment: "
              f"{_clause(falsifier, company_name)}")
        if falsifier else
        (_stop(f"The gap that has to close first is this: "
               f"{_clause(decision.evidence_required[0], company_name)}")
         if decision.evidence_required else ""))
    decision.what_each_result_would_favour = _what_would_favour(
        mechanism, alternative, company_name)
    decision.reconsider_when = (
        "Reconsider this once a source outside the company reports on it, or "
        "once the check above returns an answer either way.")
    return decision


def _unsafe_because(options, confidence, reason, mechanism,
                    alternative) -> str:
    """Why committing is unsafe -- the actual reason, not a disclaimer.

    Four causes, and a founder is owed the one that applies: the evidence is
    too thin to choose, only one course of action could be supported, the
    public record carries no competing account, or nothing outside the company
    has spoken. Collapsing them into "insufficient evidence" tells a reader
    nothing about what would fix it.
    """
    # Each of these has to survive a slide bullet, so each is one short
    # sentence. A reason a reader has to scroll to finish is a reason they do
    # not read, and this is the sentence the whole bounded state rests on.
    if not mechanism:
        return ("the public record carries what this company says about "
                "itself, not the mechanism behind it")
    if not alternative:
        return ("only one course of action is supported by what was "
                "retrieved, and one option is not a decision")
    if len(options) < 2:
        return ("the second course of action cannot say what it would cost, "
                "so the two are not comparable")
    if _CONF_RANK.get(confidence, 0) < 1:
        return ("the reading behind it is speculative, so choosing would be a "
                "preference rather than a decision")
    return _lower_first(reason) if reason else (
        "the evidence retrieved does not separate the options")


def _what_would_favour(mechanism, alternative, company="") -> str:
    """Which result points which way -- stated before the check is run, so the
    answer cannot be read to suit whichever way it lands."""
    if not (mechanism and alternative):
        return ""
    return (f"Evidence that {_clause(mechanism, company)} favours acting on "
            f"it; evidence that {_clause(alternative, company)} favours "
            f"holding.")


def _first(items):
    for item in (items or ()):
        if item:
            return item
    return ""
