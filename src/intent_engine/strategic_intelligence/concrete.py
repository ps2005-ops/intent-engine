"""Finding the concrete company facts a claim must be built from.

The deterministic path used to lead with a pattern title. Sentry's run had
retrieved a page called "Sentry Acquires Codecov" -- a named acquisition, the
single most concrete thing in the whole run -- and the presentation opened
instead with "broadening from a focused tool toward being the place a team's
work is stored", which is the `tool_to_system_of_record` scaffold and would
read identically for Notion, Linear or Atlassian.

A pattern may organise reasoning internally. It may not become the visible
claim. This module finds what the visible claim has to be made of.
"""
from __future__ import annotations

import re

# Verbs and nouns that mark a page as reporting something the company DID,
# rather than describing what it is. Ordered strongest first: an acquisition
# is a harder fact than a blog post about a launch.
_ACTION_PATTERNS = (
    ("acquisition", r"\b(acquir\w+|acquisition of|has acquired)\b"),
    ("funding", r"\b(series [a-e]\b|raises?|raised|funding round)\b"),
    ("launch", r"\b(launch\w*|introduc\w+|announc\w+|now available|"
                r"general availability|unveil\w+)\b"),
    ("pricing", r"\b(pricing|per seat|per user|free tier|plans?)\b"),
    ("partnership", r"\b(partner(s|ship)?\s+with|integrat\w+ with)\b"),
    ("leadership", r"\b(appoint\w+|joins as|new (ceo|cto|cfo)|steps down)\b"),
    ("expansion", r"\b(expands?|expanding into|enters? the)\b"),
)

#: words that make a sentence sound like an ontology rather than a company
TAXONOMY_WORDS = (
    "system of record", "adjacent tools", "platform surface",
    "place a team's work is stored", "source of truth", "build on",
    "rails beneath", "the rails its market runs on",
    "strategic surface", "productisation", "productization",
    "services motion", "wedge", "archetype", "transition label",
    "value proposition", "operating model", "leverage point",
    "strategic optionality", "adjacent capability",
)


def action_kind(text: str):
    """Which kind of concrete company action this text reports, if any."""
    low = " " + (text or "").lower() + " "
    for kind, pattern in _ACTION_PATTERNS:
        if re.search(pattern, low):
            return kind
    return None


def _get(observation, field, default=""):
    """Observations arrive as records from the reasoning layer and as plain
    dicts once a report has been serialised. Both are the same thing."""
    if isinstance(observation, dict):
        return observation.get(field, default)
    return getattr(observation, field, default)


def concrete_developments(observations) -> list:
    """Observations that report something the company actually DID.

    Ordered by how hard the fact is. A page titled "Sentry Acquires Codecov"
    outranks a product page, which outranks a mission statement.
    """
    rank = {kind: n for n, (kind, _) in enumerate(_ACTION_PATTERNS)}
    found = []
    for o in observations or ():
        title = _get(o, "source_title") or ""
        excerpt = _get(o, "excerpt") or ""
        kind = action_kind(title) or action_kind(excerpt)
        if not kind:
            continue
        found.append({
            "kind": kind,
            "title": title.strip(),
            "excerpt": excerpt.strip(),
            "observation_id": _get(o, "observation_id"),
            "date": _get(o, "date"),
            "source_class": _get(o, "source_class"),
        })
    found.sort(key=lambda d: (rank.get(d["kind"], 99), -len(d["excerpt"])))
    return found


def descriptive_subjects(observations, *, limit=3) -> list:
    """What the company says it does, in its own page titles.

    Used when nothing concrete was retrieved: naming the actual products and
    pages is still more specific than a pattern title, and it does not
    pretend an action took place.
    """
    out, seen = [], set()
    for o in observations or ():
        title = (_get(o, "source_title") or "").strip()
        if not title:
            continue
        # strip the trailing "| Company" site suffix
        head = re.split(r"\s+[|–—-]\s+", title)[0].strip()
        key = head.lower()
        if len(head) < 8 or key in seen:
            continue
        seen.add(key)
        out.append({"text": head,
                    "observation_id": _get(o, "observation_id")})
        if len(out) >= limit:
            break
    return out


def reads_as_taxonomy(text: str) -> bool:
    """True when a visible sentence is built from ontology vocabulary.

    Hyphens and underscores are normalised to spaces first: the reasoning
    layer writes both "system of record" and "tool-to-system-of-record", and
    only the second one reached a slide because the first spelling was the
    only one being matched.
    """
    low = re.sub(r"[-_]+", " ", (text or "").lower())
    low = re.sub(r"\s+", " ", low)
    return any(word in low for word in TAXONOMY_WORDS)
