"""Public follow-up conversation (T023.5) — built on the T023 chain.

The public conversation reuses T023's closed-ClaimSet contract exactly, so
the public UI and the internal workspace share one provenance model:

    domain artifact -> SourceRef -> SourceClaim -> composition ->
        closed ClaimSet -> optional model wording ->
        deterministic claim validation -> cited answer

The ClaimSet is scoped to ONE run's claims — a conversation can never use
another run's or another company's claims. A fabricated claim id, a
fabricated statistic, or an unsupported causal claim is rejected. Unknown
questions return an honest insufficient-evidence response. There is no
general planner.
"""
from __future__ import annotations

import re

from intent_engine.agentos.model_boundary import model_provenance
from intent_engine.personal.conversation import (
    ClaimSet, validate_narrative,
)
from intent_engine.personal.records import (
    AVAIL_OUT_OF_SCOPE, AVAIL_UNAVAILABLE,
)
from intent_engine.founder_intelligence.records import FounderIntelligenceError

CONVERSATION_VERSION = "fi_conversation.v1"
NARRATIVE_PROMPT_VERSION = "fi_narrative.v1"

# Topics a follow-up can be about, and the natural phrasings people actually
# use. This replaced a flat keyword whitelist that a first-time tester broke
# immediately: "What does this company actually do?" contained none of the
# magic words and was rejected as UNSUPPORTED — the most basic question anyone
# asks about a company.
#
# Matching a topic does two things: it decides that the question IS answerable,
# and it decides WHICH claims are relevant. The old code did only the first,
# so "Explain this in simple terms" matched on "explain" and then returned
# every claim in the run — which is how a request for a plain-English summary
# came back as "Pricing model: not determinable from the approved sources".
_TOPICS = {
    "identity": ("what does", "what do they", "what is this company",
                 "what's this company", "who are they", "who is this company",
                 "what does this company do", "about this company",
                 "describe the company", "explain the company"),
    "products": ("product", "sell", "offering", "service", "platform",
                 "what do they sell", "software"),
    "customers": ("customer", "who buys", "client", "user base", "audience",
                  "who uses", "use case"),
    "risks": ("risk", "threat", "concern", "weakness", "danger", "downside",
              "what could go wrong", "vulnerab"),
    "recent_change": ("recent", "changed", "change", "latest", "new",
                      "happening", "news", "development"),
    "opportunity": ("opportunit", "growth", "upside", "expand", "potential"),
    # "Why do you think this?" is a request for the reasoning and what it rests
    # on — an evidence question in ordinary English, not a bare "why".
    "evidence": ("evidence", "source", "proof", "cite", "citation",
                 "how do you know", "where did", "back this up",
                 "why do you think", "what makes you think",
                 "what are you basing"),
    "confidence": ("confidence", "confident", "how sure", "how certain",
                   "reliable", "trust this"),
    "contradiction": ("contradict", "counter", "disagree", "against this",
                      "change your view", "challenge"),
    "leadership": ("leadership", "board", "executive", "management",
                   "should i ask", "investigate", "questions for"),
    "market": ("market", "competitor", "compare", "industry", "landscape",
               "rivals", "alternatives"),
    "summary": ("summar", "overview", "tldr", "tl;dr", "in short", "brief",
                "simple terms", "simply", "simpler", "easier to understand",
                "plain english", "explain this", "eli5", "recap",
                "the gist", "key points", "main points", "takeaway",
                "without jargon", "no jargon", "in plain terms",
                "less technical"),
    "limitation": ("limitation", "limited", "why so short", "missing",
                   "what don't you know", "what do you not know", "gap",
                   "incomplete", "not enough evidence"),
    "persona": ("persona", "who is this for", "buyer"),
    # "Why does this matter?" is one of the commonest follow-ups and matched
    # nothing at all before.
    "implication": ("why is this important", "why does this matter",
                    "why it matters", "so what", "importance", "impact",
                    "what does this mean", "significance"),
    "assumption": ("assumption", "assume", "hypothes"),
    # The main claim, asked directly. Distinct from `summary`: a reader asking
    # for the thesis wants the one sentence, not a condensed tour.
    "thesis": ("main finding", "main thesis", "central view", "key finding",
               "bottom line", "headline", "in one sentence", "the thesis",
               "most important finding", "what is the main"),
    "strongest_evidence": ("strongest evidence", "best evidence",
                           "most convincing", "strongest support",
                           "what supports", "what backs"),
    "weakest_evidence": ("weakest evidence", "weakest", "least confident",
                         "least sure", "shakiest", "thinnest",
                         "what weakens", "weakens it", "weakens this",
                         "most likely wrong", "least reliable"),
    "falsification": ("what would change", "change your mind",
                      "change the conclusion", "would prove you wrong",
                      "disprove", "falsif", "what would it take"),
    "monitoring": ("monitor", "watch", "track", "leading indicator",
                   "keep an eye", "early warning", "what should i watch"),
    # "Define X" — a request about one term. NOT "without jargon" or "in plain
    # terms", which are requests to rephrase the whole answer and belong under
    # `summary`; classifying them here answered "say that simply" with a
    # glossary entry.
    "definition": ("what does .* mean", "define", "definition", "what is a ",
                   "what is an ", "terminology", "what do you mean by"),
    "comparison": ("compare", "difference between", "versus", " vs ",
                   "how do these", "which of these", "relate to each other"),
    # "Which one is most important?" — a ranking request across findings.
    "ranking": ("most important", "which matters most", "rank", "priorit",
                "biggest", "top one", "which one is most"),
}

# Topics that legitimately speak over the whole run rather than a slice of it.
_BROAD_TOPICS = ("summary", "identity", "limitation", "confidence", "evidence",
                 "thesis", "ranking", "comparison", "strongest_evidence",
                 "weakest_evidence", "falsification", "monitoring")

# Conversational references — a question that has no subject of its own and
# borrows the previous turn's. People do this constantly ("Why?", "Explain
# that.", "What weakens it?"), and treating each turn as if no conversation had
# happened is what makes an assistant feel like a search box.
_REFERENTIAL = (
    "why", "why?", "why is that", "how so", "explain that", "explain",
    "explain more", "tell me more", "go on", "and?", "so?", "what weakens it",
    "what weakens that", "what about it", "which one", "say more",
    "in plain english", "without jargon", "simpler", "why should i care",
    "what about the second point", "what about the first point",
    "what about the third point", "elaborate", "expand on that",
)

# Referential phrasings that also carry their own topic. The third field says
# whether the phrase stands on its own: "Why should I care?" means something
# without a previous turn, whereas a bare "Why?" does not — it is a pure
# pointer, and answering it with no antecedent means inventing the subject.
_REFERENTIAL_TOPIC_HINTS = (
    ("what weakens", "weakest_evidence", True),
    ("weakens it", "weakest_evidence", True),
    ("weakens that", "weakest_evidence", True),
    ("why should i care", "implication", True),
    ("without jargon", "summary", True),
    ("in plain english", "summary", True),
    ("simpler", "summary", True),
    ("which one", "ranking", True),
    ("explain more", "summary", True),
    ("tell me more", "summary", True),
    ("elaborate", "summary", True),
    ("expand on that", "summary", True),
    ("why", "implication", False),
)

# "the second point" and friends — an ordinal reference into the last answer.
_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
             "1st": 1, "2nd": 2, "3rd": 3, "last": -1}


# Internal topic name -> the words a reader would use. Every message that
# names a subject goes through this, so the classifier's vocabulary stays
# inside the classifier.
_SUBJECT_LABEL = {
    "identity": "what the company does",
    "products": "its products",
    "customers": "its customers",
    "risks": "risks",
    "recent_change": "recent changes",
    "opportunity": "opportunities",
    "evidence": "the evidence behind this",
    "confidence": "how confident this analysis is",
    "contradiction": "contradicting evidence",
    "leadership": "questions for leadership",
    "market": "its market and competitors",
    "summary": "a summary",
    "limitation": "the limits of this analysis",
    "persona": "who this is for",
    "implication": "why this matters",
    "assumption": "the assumptions behind this",
    "thesis": "the main finding",
    "strongest_evidence": "the strongest evidence",
    "weakest_evidence": "the weakest evidence",
    "falsification": "what would change this conclusion",
    "monitoring": "what to monitor",
    "definition": "that term",
    "comparison": "a comparison between these findings",
    "ranking": "which finding matters most",
}


def is_referential(question: str) -> bool:
    """Whether a question depends on the previous turn to mean anything."""
    lowered = " ".join((question or "").lower().split()).strip(" ?.!")
    if not lowered:
        return False
    if lowered in _REFERENTIAL:
        return True
    # Short questions built out of pronouns and referring phrases. Containment
    # rather than prefix matching: people say "Say that without jargon", not
    # "Without jargon", and a prefix test silently missed every such phrasing.
    return (len(lowered.split()) <= 7
            and any(r in lowered for r in _REFERENTIAL))


def referenced_ordinal(question: str):
    """Which numbered item of the previous answer was referred to, if any."""
    lowered = " ".join((question or "").lower().split())
    for word, index in _ORDINALS.items():
        if f"the {word} " in lowered or lowered.endswith(f"the {word}") \
                or f"{word} point" in lowered or f"{word} one" in lowered:
            return index
    return None

# Kept for backwards compatibility with callers that imported it.
_SUPPORTED = tuple(sorted({p for ps in _TOPICS.values() for p in ps}))


def detect_topics(question: str, previous_topics=()) -> tuple:
    """Which topics a question is about. Empty when nothing is recognised.

    Deterministic and offline on purpose: a follow-up must behave the same way
    every time, and must not depend on a model being reachable.

    `previous_topics` carries the last turn's subject, so a bare "Why?" is
    answered about the thing just discussed rather than rejected. Without it,
    every turn starts from nothing and the product feels like a search box that
    forgets you between queries.
    """
    lowered = " ".join((question or "").lower().split())
    hits = [topic for topic, phrases in _TOPICS.items()
            if any(_phrase_matches(p, lowered) for p in phrases)]

    # Inheritance applies only when the question has NO subject of its own.
    # "Why do you think this? evidence" already names what it is about, and
    # borrowing on top of that narrowed it to the borrowed topic instead —
    # which turned a broad evidence question into one with no matching claims.
    # A question that names its subject does not need one.
    if not hits and is_referential(question):
        for phrase, topic, standalone in _REFERENTIAL_TOPIC_HINTS:
            if phrase in lowered and (standalone or previous_topics):
                hits.append(topic)
                break
        for topic in previous_topics:
            if topic not in hits:
                hits.append(topic)

    # Longest-phrase wins for the common "explain this simply" case, which
    # matches both `identity` and `summary`; summary is the better answer.
    if "summary" in hits and len(hits) > 1:
        hits = ["summary"] + [h for h in hits if h != "summary"]
    return tuple(hits)


def _phrase_matches(phrase: str, lowered: str) -> bool:
    """Most phrases are literal; a few need a wildcard for a middle term."""
    if ".*" in phrase:
        return bool(re.search(phrase, lowered))
    return phrase in lowered


def _relevant_claims(topics: tuple, speakable: tuple) -> tuple:
    """Narrow the run's claims to the ones the question is actually about.

    Returning everything is what produced an answer about pricing to a request
    for a simple explanation.
    """
    # A broad topic widens the scope only when there is nothing specific to
    # widen it FROM. "What are the biggest risks?" is a ranking question about
    # risks, not a request for everything ranked — treating the broad topic as
    # dominant is how a risk question came back leading with pricing.
    specific = tuple(t for t in topics if t not in _BROAD_TOPICS)
    if not topics or not specific:
        return speakable
    wanted = tuple(w for t in specific for w in _TOPICS[t])
    scoped = tuple(
        c for c in speakable
        if any(w in (getattr(c, "claim_id", "") or "").lower()
               or w in (getattr(c, "text", "") or "").lower()
               for w in wanted))
    # Never answer with something unrelated just to have an answer.
    return scoped


# Causal phrasings the workspace may not assert unless a source supports it.
_CAUSAL = ("reduces", "reducing", "causes", "causing", "because of you",
           "is lowering", "drives down", "hurts")


def run_claim_set(question: str, run_claims: list,
                  previous_topics=()) -> ClaimSet:
    """Build a closed ClaimSet from THIS run's claims only."""
    topics = detect_topics(question, previous_topics)
    speakable = tuple(c for c in run_claims
                      if c.availability not in (AVAIL_OUT_OF_SCOPE,))

    if not topics:
        # Not "unsupported" — just not understood. The reply names things the
        # user can actually ask instead of describing our internals.
        from intent_engine.personal.adapters.base import out_of_scope_claim
        return ClaimSet(intent="UNRECOGNISED", claims=(out_of_scope_claim(
            "fi.unrecognised",
            "I can answer questions about this company and this analysis. I "
            "could not tell what you meant. Try \"What does this company "
            "do?\", \"Who are its customers?\", \"What are the main risks?\", "
            "or \"Summarise this simply\"."),))

    if not speakable:
        from intent_engine.personal.adapters.base import unavailable_claim
        return ClaimSet(intent="INSUFFICIENT", claims=(unavailable_claim(
            "fi.insufficient",
            "there is not yet enough supported evidence to answer this"),))

    relevant = _relevant_claims(topics, speakable)
    if not relevant:
        # Understood, but this run holds nothing on that subject. Saying so is
        # the honest answer; substituting an unrelated claim is not.
        from intent_engine.personal.adapters.base import unavailable_claim
        # `topics[0]` is an internal name. "this analysis does not contain
        # evidence about weakest_evidence" is the classifier talking to itself
        # in front of a customer.
        subject = _SUBJECT_LABEL.get(topics[0], topics[0].replace("_", " "))
        return ClaimSet(intent="INSUFFICIENT", claims=(unavailable_claim(
            "fi.insufficient",
            f"this analysis does not yet contain evidence about {subject} "
            f"for this company; the evidence library shows which sources "
            f"were retrieved and which failed"),))
    return ClaimSet(intent="SUPPORTED", claims=relevant)


def answer(question: str, *, run_claims: list, llm_client=None,
           model_version="fake-model.v0", previous_topics=()) -> dict:
    """A public follow-up turn. Rejects fabricated claims and unsupported
    causality; preserves disagreement."""
    lowered = " ".join((question or "").lower().split())
    claim_set = run_claim_set(question, run_claims, previous_topics)
    topics = detect_topics(question, previous_topics)

    provenance = None
    if llm_client is not None and claim_set.intent == "SUPPORTED":
        provenance = model_provenance(NARRATIVE_PROMPT_VERSION, model_version,
                                      authority="paraphrase over a closed, "
                                                "run-scoped ClaimSet")
        candidate = llm_client.call_tool(
            prompt_version=NARRATIVE_PROMPT_VERSION,
            user_message={"question": question,
                          "claims": claim_set.model_view()})
        body = validate_narrative(claim_set, candidate)
        # an unsupported causal claim in model prose is rejected
        joined = " ".join(p["text"] for p in body["paragraphs"]).lower()
        if any(marker in joined for marker in _CAUSAL) and not any(
                "caus" in c.text.lower() for c in claim_set.claims):
            raise FounderIntelligenceError(
                "the answer asserts a causal relationship no source supports "
                "— only the supported observation is permitted")
    else:
        body = {"paragraphs": [{"text": c.text, "availability": c.availability,
                                "citations": [r.as_dict()
                                              for r in c.source_refs],
                                "claim_ids": [c.claim_id]}
                               for c in claim_set.claims], "validated": True}

    conflicted = [c.claim_id for c in claim_set.claims
                  if c.availability == "CONFLICTED"]
    return {
        "conversation_version": CONVERSATION_VERSION,
        "intent": claim_set.intent,
        "answer": body,
        # Carried forward so the NEXT turn can resolve "Why?" against this one.
        # Internal — the renderer must never print it.
        "topics": topics,
        "preserved_conflicts": conflicted,
        "model_provenance": provenance,
        "note": "every paragraph cites a run-scoped source artifact; "
                "conflicts and unavailable results are preserved",
    }
