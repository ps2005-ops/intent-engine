"""The one place a mechanism becomes words a founder reads.

WHY THIS MODULE EXISTS. Every founder-facing surface had the hypothesis and
the observation list and had to decide for itself which evidence to show for a
claim. They each decided differently, and — measured live at `bdbc0d0` — they
all decided wrong in the same way: an observation is one document carrying
every signal found anywhere in it, its `excerpt` is chosen once for the whole
document, and so the passage shown had nothing to do with the signal the
reading qualified on. HubSpot's 10-K genuinely says "Our customer platform
includes a system of record for maintaining a unified view of the customer
experience"; the reader was shown the document's opening sentence about an
"agentic customer platform" instead.

`reasoning._mechanism_evidence` captures the right sentence at the only point
that still knows which signal qualified. This module turns it into text. No
surface may phrase it a second way: two phrasings drift, and then the deck and
the brief disagree about why the same company got the same reading.
"""
from __future__ import annotations


def evidence_of(hypothesis) -> list:
    """`MechanismEvidence` dicts for a hypothesis, object or dict alike.

    Surfaces receive whichever form their caller had. Normalising here is what
    lets every one of them ask the same question.
    """
    raw = (hypothesis.get("mechanism_evidence")
           if isinstance(hypothesis, dict)
           else getattr(hypothesis, "mechanism_evidence", ())) or ()
    out = []
    for item in raw:
        d = item if isinstance(item, dict) else (
            item.as_dict() if hasattr(item, "as_dict") else None)
        if d and (d.get("quote") or "").strip():
            out.append(d)
    return out


def needs_mechanism(hypothesis) -> bool:
    """Whether this reading's pattern declares a mechanism gate at all.

    The distinction that keeps this honest. A GATED pattern asserts a
    structural force it proved, so it owes the reader the sentence that proved
    it, and must stay quiet if it cannot produce one. An UNGATED pattern is
    the recorded debt in `test_every_pattern_earns_its_mechanism` — it never
    claimed a mechanism, so suppressing it would delete working analysis to
    punish a gap that is already tracked somewhere else.
    """
    from intent_engine.strategic_intelligence.patterns import PATTERN_LIBRARY
    pid = (hypothesis.get("pattern_id") if isinstance(hypothesis, dict)
           else getattr(hypothesis, "pattern_id", "")) or ""
    for pattern in PATTERN_LIBRARY:
        if pattern.pattern_id == pid:
            return bool(pattern.required_signals
                        or pattern.required_any_signals)
    return False


def is_explained(hypothesis) -> bool:
    """Whether this reading can show what caused it.

    False is not a rendering bug to paper over — it means the reading rests on
    a pattern that declares no mechanism (the recorded debt) or on a span that
    could not be resolved. Either way the honest surface behaviour is to say
    less, not to substitute a passage that does not contain the claim.
    """
    return bool(evidence_of(hypothesis))


def because_line(hypothesis, *, limit: int = 1) -> str:
    """One sentence: what the source said, that made this reading true.

    Quoted, not paraphrased. A paraphrase is the analysis marking its own
    homework; the point of this line is that the founder can disagree with the
    company's words rather than with ours.
    """
    parts = []
    for item in evidence_of(hypothesis)[:limit]:
        quote = item["quote"].strip().rstrip(".")
        source = (item.get("source_title") or "").strip()
        parts.append(f'“{quote}.”' + (f" — {source}" if source else ""))
    return " ".join(parts)


def shown_because(hypothesis, *, limit: int = 2) -> list:
    """Reader-facing bullets: the mechanism, then the words evidencing it."""
    out = []
    for item in evidence_of(hypothesis)[:limit]:
        label = (item.get("label") or "").strip().rstrip(".")
        quote = item["quote"].strip().rstrip(".")
        source = (item.get("source_title") or "").strip()
        lead = f"{label[0].upper()}{label[1:]}. " if label else ""
        out.append(f'{lead}“{quote}.”' + (f" — {source}" if source else ""))
    return out


def citations(hypothesis) -> list:
    """Observation ids behind the mechanism, for surfaces that cite by id."""
    return [i["observation_id"] for i in evidence_of(hypothesis)
            if i.get("observation_id")]
