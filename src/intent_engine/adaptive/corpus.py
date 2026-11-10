"""The evidence corpus: text that still knows which document it came from.

WHY A CORPUS AND NOT A STRING
-----------------------------
The producers here score signals over ALL of a company's retrieved text, which
is correct -- a business model is a property of the whole corpus, not of one
page. So the text was concatenated into one blob and the blob was scored.

Then a reader was shown a quotation from it, and there was no longer any way
to say which document the sentence came from. Measured on the deployed service
(Highspot, df8830f0), two of the three quotations on the primary screen were
drawn from a press-release index, and one of them began mid-word:

    "The evidence this rests on omers are transforming GTM performance."

A quotation with no source is not evidence, and a quotation cut by arithmetic
tells a reader the machine is not reading.

This module keeps the concatenation -- scoring is unchanged -- and remembers
the segment boundaries, so any offset in the joined text resolves back to the
document it belongs to, with that document's title, url, class and date.

WHAT IT DOES NOT DO
-------------------
It does not decide what a sentence means, whether a page is furniture, or
whether a source is independent. Those rules are owned by
`strategic_intelligence.evidence_text` and `source_semantics`, and a second
implementation of any of them is how two subsystems come to disagree about
what one page says.
"""
from __future__ import annotations

import dataclasses
from typing import List, Optional, Sequence, Tuple

CONTRACT = "adaptive_corpus.v1"

#: How the reader should weigh who wrote it. Mapped from `source_semantics`
#: authorship rather than re-derived here.
SUBJECT_PUBLISHED = "SUBJECT_PUBLISHED"
REGULATORY = "REGULATORY_FILING"
THIRD_PARTY = "THIRD_PARTY"
INFERRED = "INFERRED"

#: What a piece of evidence is doing for the claim beside it.
SUPPORTING = "SUPPORTING"
CONTRADICTING = "CONTRADICTING"
CONTEXT = "CONTEXT"
UNCERTAINTY = "UNCERTAINTY"


@dataclasses.dataclass(frozen=True)
class Source:
    """One retrieved document, and enough of it to attribute a sentence."""
    text: str
    title: str = ""
    url: str = ""
    source_class: str = ""
    date: str = ""

    @property
    def provenance(self) -> str:
        """Who is speaking, decided by the module that owns that rule."""
        try:
            from intent_engine.strategic_intelligence import source_semantics
            author = source_semantics.authorship(self.source_class)
            if author in (source_semantics.COMPANY,
                          source_semantics.EXECUTIVE):
                return (REGULATORY if "sec.gov" in (self.url or "").lower()
                        else SUBJECT_PUBLISHED)
            if author == source_semantics.UNKNOWN:
                return INFERRED
            return THIRD_PARTY
        except Exception:                                    # noqa: BLE001
            return INFERRED

    @property
    def subject_owned(self) -> bool:
        return self.provenance in (SUBJECT_PUBLISHED, REGULATORY)


@dataclasses.dataclass(frozen=True)
class EvidenceRef:
    """A claim, what supports it, and where that came from.

    `is_quote` is False when `passage` is empty and `paraphrase` carries the
    meaning instead. The renderer puts quotation marks around a passage and
    NEVER around a paraphrase: inventing quotation marks is inventing a
    source's words, which is worse than having none.
    """
    claim: str = ""
    passage: str = ""
    paraphrase: str = ""
    source_title: str = ""
    source_url: str = ""
    source_date: str = ""
    provenance: str = INFERRED
    role: str = SUPPORTING
    is_quote: bool = False

    def __bool__(self) -> bool:
        return bool(self.passage or self.paraphrase)

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


class Corpus:
    """Joined text that can still name the document behind any offset."""

    #: the separator between segments. Newlines rather than spaces so a
    #: sentence splitter cannot run one document's last sentence into the
    #: next document's first.
    JOIN = "\n\n"

    def __init__(self, sources: Sequence[Source]):
        self.sources: Tuple[Source, ...] = tuple(
            s for s in sources if str(getattr(s, "text", "") or "").strip())
        parts, spans, cursor = [], [], 0
        for source in self.sources:
            body = str(source.text)
            parts.append(body)
            spans.append((cursor, cursor + len(body), source))
            cursor += len(body) + len(self.JOIN)
        self.text: str = self.JOIN.join(parts)
        self._spans: Tuple[Tuple[int, int, Source], ...] = tuple(spans)

    def __len__(self) -> int:
        return len(self.text)

    @property
    def subject_only(self) -> "Corpus":
        """The same corpus with third-party documents removed.

        A rival's page describing ITS subscription revenue must never
        classify this company, and "the subject's text comes first" is not
        sufficient -- a scorer reads the whole string, so the rival simply
        needs more signal. Measured: the subject scored 9.0 and the rival
        13.0. Removal, not ordering.
        """
        return Corpus([s for s in self.sources if s.subject_owned])

    def source_at(self, offset: int) -> Optional[Source]:
        for start, end, source in self._spans:
            if start <= offset < end:
                return source
        return None

    def evidence_at(self, start: int, end: int, *, claim: str = "",
                    role: str = SUPPORTING,
                    paraphrase: str = "") -> EvidenceRef:
        """The cleanest quotable sentence around an offset, with its source."""
        from intent_engine.adaptive.spans import quote_around
        source = self.source_at(start)
        passage = quote_around(self.text, start, end)
        # A SPAN CONFINED TO ITS OWN DOCUMENT. `quote_around` reads a window
        # either side of the match, and a window can cross the join into a
        # neighbouring document -- which is how a sentence gets attributed to
        # a page it never appeared on.
        if source is not None and passage and passage not in source.text:
            local = quote_around(source.text,
                                 max(0, start - self._offset_of(source)),
                                 max(0, end - self._offset_of(source)))
            passage = local if local and local in source.text else ""
        return EvidenceRef(
            claim=claim, passage=passage,
            paraphrase="" if passage else paraphrase,
            source_title=(source.title if source else ""),
            source_url=(source.url if source else ""),
            source_date=(source.date if source else ""),
            provenance=(source.provenance if source else INFERRED),
            role=role, is_quote=bool(passage))

    def _offset_of(self, source: Source) -> int:
        for start, _end, candidate in self._spans:
            if candidate is source:
                return start
        return 0


def from_observations(observations, *, filings: str = "") -> Corpus:
    """A corpus from a run's observations, plus its CIK-verified filings.

    `filings` arrives already ownership-checked by `classification_inputs`,
    which resolves it against the filer's CIK -- so it is added as one
    regulatory source rather than being re-derived here.
    """
    sources: List[Source] = []
    if str(filings or "").strip():
        sources.append(Source(text=str(filings), title="Regulatory filings",
                              source_class="investor_material",
                              url="https://www.sec.gov/"))
    for o in (observations or ()):
        get = (o.get if isinstance(o, dict)
               else lambda k, d=None, obj=o: getattr(obj, k, d))
        text = " ".join(str(get("excerpt", "") or "").split())
        if not text:
            continue
        sources.append(Source(
            text=text,
            title=str(get("source_title", "") or ""),
            url=str(get("origin", "") or get("url", "") or ""),
            source_class=str(get("source_class", "") or ""),
            date=str(get("date", "") or "")))
    return Corpus(sources)
