"""The one language-wall scanner (T022).

Extracted from `scan_banned_language`, which appeared byte-identical in
all three agent contracts (`research/records.py`,
`product/records.py`, `executive/records.py`) — the SAME word-boundary +
phrase-matching algorithm, differing only in the tuple of banned terms.

The algorithm, unchanged: a multi-word term matches as a literal
substring; a single word matches on word boundaries, so `provenance` is
not `proven`, `nevertheless` is not `never`, and `mustard` is not `must`.
That distinction has cost five sessions, and it is preserved exactly.

Each agent keeps its OWN banned-term tuple — the vocabulary is domain
policy, not infrastructure — and passes it in. The kernel owns the
matcher, not the list.
"""
from __future__ import annotations

import re


def word_boundary_hit(text: str, term: str) -> bool:
    """A multi-word term is a literal substring; a single word is
    word-boundary matched."""
    lowered = (text or "").lower()
    if " " in term:
        return term in lowered
    return bool(re.search(rf"\b{re.escape(term)}\b", lowered))


def scan_banned_language(text: str, banned_terms) -> list:
    """Every banned term present in `text`, sorted and de-duplicated.

    Byte-for-byte the behaviour the three agents shared; the term tuple is
    the only per-agent input.
    """
    return sorted({term for term in banned_terms
                   if word_boundary_hit(text, term)})
