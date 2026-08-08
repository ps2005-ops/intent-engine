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
    # A pricing PAGE is not an action -- every company has one, and matching
    # it handed the takeover to an adversarial fixture whose only qualifying
    # "development" was a page called "Hostile Co pricing". Only a reported
    # CHANGE to pricing counts.
    ("pricing", r"\b(new pricing|pricing (change|update)s?|repricing|"
                r"price (increase|cut|change)s?|changes? to (our )?pricing|"
                r"updated? (our )?pricing|new plans?)\b"),
    ("partnership", r"\b(partner(s|ship)?\s+with|integrat\w+ with)\b"),
    ("leadership", r"\b(appoint\w+|joins as|new (ceo|cto|cfo)|steps down)\b"),
    # "expands" alone matches marketing copy; require a destination.
    ("expansion", r"\b(expand(s|ed|ing) (into|to)|enters? the)\b"),
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

# THE LIBRARY DESCRIBING ITS OWN MACHINERY.
#
# TAXONOMY_WORDS is a list of NOUNS, so it could only ever catch a spelling
# somebody had already read off a slide -- one entry per incident. The pattern
# library names itself in a regular way, and that regularity is the thing worth
# matching: "match the product→platform mechanism", "tool-to-system-of-record",
# "hyp-services_to_product". Each is an internal identifier whatever nouns it
# happens to contain, and a pattern added to the library tomorrow will be
# spelled the same way. Naming the SHAPE is the only version of this rule that
# holds without an incident first.
_PATTERN_SELF_DESCRIPTION = (
    # "...together match the product→platform mechanism", "matches the
    # segment-split mechanism" -- the analysis reporting on its own rule firing
    re.compile(r"\bmatch(?:es|ed|ing)?\s+the\b[^.:]{0,80}?\bmechanism\b", re.I),
    # internal record ids: hyp-…, obs-…, pat:…, blind-…
    re.compile(r"\b(?:hyp|obs|pat|blind)[-:][A-Za-z0-9_]+\b", re.I),
    re.compile(r"\bpattern[_\s-](?:id|library|name|label)\b", re.I),
)

# A COMPOUND IS AN IDENTIFIER ONLY WHEN IT IS ONE.
#
# Matching the SHAPE "x-to-y" was too broad by a mile: it read "harder-to-copy
# layers" and "a go-to-market choice" as internal vocabulary and deleted two
# genuine sentences from the library. An allowlist of English compounds is
# whack-a-mole -- there is no end to them.
#
# The library, though, knows its own ids. A compound is an identifier when its
# words are a pattern id's words, in any of the three spellings the codebase
# uses for the same thing: `tool_to_system_of_record`,
# "tool-to-system-of-record" and "product→platform". Exact, so no English
# compound can trip it, and systemic, because a pattern added tomorrow is
# covered the moment it is added.
_COMPOUND = re.compile(r"[A-Za-z]+(?:\s*(?:→|->|[-_])\s*[A-Za-z]+)+")


def _id_words(text: str) -> tuple:
    """A compound's words, with the joining "to" dropped."""
    words = [w for w in re.split(r"[^A-Za-z]+", text.lower()) if w]
    return tuple(w for w in words if w != "to")


def _pattern_id_words() -> frozenset:
    from intent_engine.strategic_intelligence.patterns import PATTERN_LIBRARY
    return frozenset(_id_words(p.pattern_id) for p in PATTERN_LIBRARY)


def _names_a_pattern_id(text: str) -> bool:
    known = _pattern_id_words()
    for match in _COMPOUND.finditer(text or ""):
        words = _id_words(match.group(0))
        if len(words) >= 2 and words in known:
            return True
    return False


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
    raw = (text or "")
    low = re.sub(r"[-_]+", " ", raw.lower())
    low = re.sub(r"\s+", " ", low)
    if any(word in low for word in TAXONOMY_WORDS):
        return True
    # Checked against the ORIGINAL, because the normalisation above is what
    # makes "tool-to-system-of-record" invisible to a hyphen-aware rule.
    if any(rule.search(raw) for rule in _PATTERN_SELF_DESCRIPTION):
        return True
    return _names_a_pattern_id(raw)


# --- title cleaning -----------------------------------------------------------

# In Title Case every content word is capitalised, so capitalisation carries
# no information and shape cannot tell "Codecov" from "Acquires". The default
# is therefore PRESERVE, and only words we positively recognise as ordinary
# English are lowered. Getting this backwards produced "Sentry acquired
# codecov", which mangles the one name the sentence exists to report.
_COMMON_WORDS = frozenset("""
a an the and or but nor so yet for of in on at to from by with without into
onto over under about across after before during through against between
among as is are was were be been being it its their our your his her this
that these those new more most all any each every other another such own same
than then when while where which who whom whose what how why
platform software product products service services solution solutions
company companies business team teams customer customers user users developer
developers tool tools app apps cloud data enterprise
blog news press release releases update updates announcement announcements
story stories post posts article articles page pages resources resource
today now available general availability version
""".split())

#: headline present tense -> the past tense a report uses
_TITLE_VERBS = {
    "acquires": "acquired", "acquire": "acquired",
    "launches": "launched", "launch": "launched",
    "announces": "announced", "announce": "announced",
    "introduces": "introduced", "introduce": "introduced",
    "introducing": "introduced",
    "raises": "raised", "raise": "raised",
    "partners": "partnered", "expands": "expanded",
    "appoints": "appointed", "unveils": "unveiled",
    "joins": "joined", "adds": "added",
}

#: site furniture that appears around a real title
_TITLE_NOISE = re.compile(
    r"^(?:home|blog|news|press|newsroom|media|press\s+release[s]?)\s*[:\-|]\s*",
    re.I)


def clean_title(title: str, company: str = "") -> str:
    """Turn a page title into a sentence a person would say.

    "Sentry Acquires Codecov | Sentry Blog" -> "Sentry acquired Codecov."

    General rules only, no per-company replacements: strip the site suffix,
    put a headline verb into the past, lower the words that are ordinary
    English, and leave everything else exactly as the company wrote it.
    """
    text = (title or "").strip()
    if not text:
        return ""
    text = re.split(r"\s*\|\s*", text)[0].strip()
    if company:
        text = re.sub(rf"\s+[–—-]\s+{re.escape(company)}\s*$", "", text,
                      flags=re.I).strip()
    text = _TITLE_NOISE.sub("", text).strip()
    if not text:
        return ""

    words, out = text.split(), []
    for index, word in enumerate(words):
        bare = word.strip(".,:;!?").lower()
        if index > 0 and bare in _TITLE_VERBS:
            out.append(_TITLE_VERBS[bare])
        elif index > 0 and bare in _COMMON_WORDS:
            out.append(word.lower())
        else:
            out.append(word)             # proper nouns, acronyms, unknowns
    sentence = " ".join(out).strip(" .,:;")
    if sentence and sentence[0].islower():
        sentence = sentence[0].upper() + sentence[1:]
    return (sentence + ".") if sentence else ""


# --- the takeover decision ----------------------------------------------------

def select_founder_claim_anchor(observations, *, company="") -> dict:
    """Decide whether a concrete fact is strong enough to lead the analysis.

    Returns the anchor, or {} to leave the existing path alone.

    THE GOVERNING RULE: only replace the fallback when there is a real fact
    strong enough to earn the takeover. Not an observation count, not a source
    count, not the presence of a pattern, and not a company name appearing in
    a title -- an actual reported action.

    Wiring this on anything weaker is what previously pushed thin and
    adversarial companies (a dental practice, a hostile site) into asserting a
    shape they could not fill.
    """
    developments = concrete_developments(observations)
    if not developments:
        return {}
    lead = developments[0]
    fact = clean_title(lead.get("title", ""), company)
    # A title that cleans down to nothing, or that names no company-specific
    # subject beyond the company itself, has not earned the takeover.
    if len(fact.split()) < 3:
        return {}
    # A TITLE STILL HAS TO BE A SENTENCE.
    #
    # "Palantir Partnership Vanguard" opened the deployed deck under the
    # heading "The insight" -- three nouns, retrieved from a page, presented
    # as the analysis's conclusion. `action_kind` had matched a word in it,
    # and nothing after that asked whether the result asserted anything.
    #
    # The claim gate's word floor cannot be used here: "Sentry acquired
    # Codecov." is three words and is exactly the fact this path exists to
    # find. What separates them is the verb -- one reports an action, the
    # other is a noun phrase -- so that is what is required.
    from intent_engine.founder_brief.build import _has_finite_verb
    if not _has_finite_verb(fact.lower()):
        return {}
    return {
        "fact": fact,
        "kind": lead["kind"],
        "observation_id": lead.get("observation_id", ""),
        "date": lead.get("date", ""),
        "supporting": [clean_title(d.get("title", ""), company)
                       for d in developments[1:3]],
        #: internal only -- never rendered
        "source": "concrete",
    }
