"""Retrieval layer: find similar past business decisions to ground the simulation.

Uses TF-IDF + cosine similarity, not a true semantic embedding model (see PROGRESS.md
for the full reasoning). Short version: sentence-transformers (the spec's suggested
local option) measured at ~3.5s of fresh-process import+model-load overhead alone,
paid on every CLI invocation since this isn't a long-running server -- unacceptable
against a 7-9s latency budget that's already tight. TF-IDF's fresh-process cost is
~0.8s, almost entirely import time, and doesn't need network access or an API key.
The semantic-similarity gap matters less here than generically: the reference corpus
is small (18 entries), hand-curated, and uses consistent business-decision vocabulary
we wrote ourselves, not noisy scraped text -- a reasonable, cheaply-falsifiable bet.
"""

import json
from pathlib import Path
from typing import List, NamedTuple, Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DATA_PATH = Path(__file__).parent / "data" / "reference_decisions.json"

# Below this cosine similarity, a "match" is more noise than signal for a corpus
# this size and vocabulary-dependent; still returned (so there's always grounding
# context) but bucketed as "loose match" rather than "strong match". Calibrated by
# eyeballing real matches: 0.795 (near-duplicate decision) should read as strong,
# 0.187 (different topic, matched mostly on generic SaaS vocabulary) should not.
_STRONG_MATCH_THRESHOLD = 0.35


class ReferenceDecision(NamedTuple):
    id: str
    decision_text: str
    context_at_decision: dict
    outcome: str
    lesson: str


class RetrievedMatch(NamedTuple):
    reference: ReferenceDecision
    similarity: float


def _load_reference_decisions() -> List[ReferenceDecision]:
    with open(DATA_PATH) as f:
        raw = json.load(f)
    return [ReferenceDecision(**entry) for entry in raw]


def retrieve_similar(decision_text: str, top_k: int = 3) -> List[RetrievedMatch]:
    references = _load_reference_decisions()
    corpus_texts = [r.decision_text for r in references]

    vectorizer = TfidfVectorizer()
    corpus_matrix = vectorizer.fit_transform(corpus_texts)
    query_vector = vectorizer.transform([decision_text])
    scores = cosine_similarity(query_vector, corpus_matrix)[0]

    ranked = sorted(zip(scores, references), key=lambda pair: pair[0], reverse=True)
    return [RetrievedMatch(reference=ref, similarity=float(score)) for score, ref in ranked[:top_k]]


def _bucket_similarity(score: float) -> str:
    return "strong match" if score >= _STRONG_MATCH_THRESHOLD else "loose match"


def _format_delta(current: Optional[int], past: Optional[int], label: str, suffix: str = "") -> Optional[str]:
    if current is None or past is None:
        return None
    return f"{label} {past}{suffix} vs. your {current}{suffix}"


def format_retrieval_digest(
    matches: List[RetrievedMatch],
    current_team_size: Optional[int],
    current_runway_months: Optional[int],
) -> str:
    """Format matches into short digest lines for injection into the main prompt.

    Pure string formatting, no LLM call -- mirrors causal_model._format_causal_context.
    Deltas are computed against the reference's context_at_decision snapshot (the
    business's numbers when THAT decision was made), not current-day figures for that
    reference business, so the comparison is apples-to-apples with the current decision.
    """
    lines = []
    for match in matches:
        ref = match.reference
        ctx = ref.context_at_decision
        bucket = _bucket_similarity(match.similarity)

        deltas = [
            d
            for d in (
                _format_delta(current_team_size, ctx.get("team_size"), "team"),
                _format_delta(current_runway_months, ctx.get("runway_months"), "runway", suffix="mo"),
            )
            if d
        ]
        tag = f"[{bucket}" + (f", {', '.join(deltas)}]" if deltas else "]")

        lines.append(f"{tag} {ref.decision_text} -> {ref.outcome} Lesson: {ref.lesson}")
    return "\n".join(lines)
