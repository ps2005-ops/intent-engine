"""Company suggestions while the customer types.

WHY IDENTITY IS A CUSTOMER FEATURE AND NOT A BACKEND CONCERN (§4)
-----------------------------------------------------------------
The worst thing this product can emit is a confident report about a different
company, and every mechanism protecting against that used to live AFTER the
form was submitted: resolve, and if it is ambiguous, interrupt with a chooser.
That is a good backstop and a poor experience — the customer types a name,
waits, and is then told their input was insufficient.

Moving the resolution into the typing turns the same machinery into a feature.
The customer picks a company that already carries its legal name, ticker,
country and domain, so the run opens on an identity that was CONFIRMED rather
than inferred, and the chooser becomes the rare case instead of the common one.

WHAT MAY APPEAR IN A SUGGESTION
-------------------------------
Only fields a source actually carries. A row from the SEC registrant table has
a legal name, a CIK and often a ticker; it does NOT have a domain, and the one
thing this module must never do is supply one — a guessed domain sends
retrieval at somebody else's website, which is the wrong-company failure
arriving by a different door. An absent field is absent in the row and the UI
renders nothing for it.

WHAT IT MAY NOT REACH (§82)
---------------------------
Public registries only: the curated entity registry, the validation manifest
and the SEC's public ticker table. No tenant data, no private documents, no
Personal AI memory, no other session's runs. The suggestion endpoint is
reachable by an anonymous demo guest, so anything it can see is public by
construction — enforced by this module importing nothing that holds tenant
state.
"""
from __future__ import annotations

import dataclasses
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "company_suggest.v1"

#: Where a suggestion came from, strongest identity first.
REGISTRY = "entity registry"
MANIFEST = "validation manifest"
REGISTRANT = "SEC registrant table"

SOURCE_RANK = {REGISTRY: 0, MANIFEST: 1, REGISTRANT: 2}

#: How well the typed text matched. Drives ordering within a source.
EXACT = 0
LEADING = 1
INITIALISM = 2
CONTAINS = 3


@dataclasses.dataclass(frozen=True)
class Suggestion:
    """One company a customer could mean. Every field is from a source."""
    legal_name: str
    common_name: str = ""
    ticker: str = ""
    country: str = ""
    city: str = ""
    domain: str = ""
    listing: str = ""              #: PUBLIC / PRIVATE where a source says so
    sector: str = ""
    entity_id: str = ""
    cik: str = ""
    source: str = REGISTRY
    match: int = CONTAINS

    def describe(self) -> str:
        """The second line under the name. Only what a source carries."""
        bits = [b for b in (self.ticker, self.country, self.city,
                            self.domain) if b]
        return " · ".join(bits)

    def as_dict(self) -> dict:
        return {"legal_name": self.legal_name, "common_name": self.common_name,
                "ticker": self.ticker, "country": self.country,
                "city": self.city, "domain": self.domain,
                "listing": self.listing, "sector": self.sector,
                "entity_id": self.entity_id, "cik": self.cik,
                "source": self.source, "describe": self.describe()}


_SUFFIXES = frozenset({
    "inc", "inc.", "incorporated", "corp", "corp.", "corporation", "co",
    "co.", "company", "ltd", "ltd.", "limited", "plc", "llc", "lp", "nv",
    "n.v.", "sa", "s.a.", "ag", "se", "group", "holdings", "holding",
    "the", "&", "and",
})


#: Punctuation that sits INSIDE a word and must not change what it matches.
#:
#: MEASURED LIVE 2026-09-04 on e4b5ad6b: "lowe" returned Lowes Companies Inc,
#: and "lowe's" returned NOTHING -- as did "Lowe's Companies", which is the
#: company's actual name and the obvious thing to type. The registrant table
#: spells it "LOWES COMPANIES INC" with no apostrophe, so `"lowes"
#: .startswith("lowe's")` was False and every branch of `_match` declined.
#:
#: 36 of 10,412 registrants carry an apostrophe -- Macy's, Dick's Sporting
#: Goods, Campbell's, Victoria's Secret, BJ's Wholesale, McDonald's -- and
#: the spelling a customer types is not the spelling the regulator filed.
#: Both sides are normalised, so it does not matter which one has it.
#:
#: The RIGHT SINGLE QUOTE is included because that is what a phone keyboard
#: and most word processors emit; a fix that only handled the ASCII form
#: would still fail the customers most likely to hit it.
_IN_WORD_PUNCTUATION = str.maketrans({"'": "", "\u2019": "", "\u02bc": ""})


def _words(text: str) -> List[str]:
    out = []
    for raw in str(text or "").lower().replace(",", " ").split():
        word = raw.strip(".,&").translate(_IN_WORD_PUNCTUATION)
        if word and word not in _SUFFIXES:
            out.append(word)
    return out


def _initialism(text: str) -> str:
    return "".join(w[0] for w in _words(text))


def _match(typed: str, name: str, ticker: str = "") -> Optional[int]:
    """How `typed` matches `name`, or None. Ordered strongest first."""
    typed_words = _words(typed)
    if not typed_words:
        return None
    name_words = _words(name)
    if not name_words:
        return None
    if typed_words == name_words:
        return EXACT
    if ticker and str(typed).strip().upper() == ticker.strip().upper():
        return EXACT
    if len(typed_words) <= len(name_words) \
            and name_words[:len(typed_words)] == typed_words:
        return LEADING
    # A PARTIAL LAST WORD IS STILL A LEADING MATCH.
    #
    # Autocomplete runs on every keystroke, so "cloudfl" must find Cloudflare.
    # Requiring whole words made the feature useless until the customer had
    # typed the name they were asking for help spelling.
    if len(typed_words) <= len(name_words) \
            and name_words[:len(typed_words) - 1] == typed_words[:-1] \
            and name_words[len(typed_words) - 1].startswith(typed_words[-1]):
        return LEADING
    if len(typed_words) == 1 and len(typed_words[0]) >= 2 \
            and _initialism(name) == typed_words[0]:
        return INITIALISM
    # CONTAINS MUST START AT A WORD.
    #
    # A bare substring test put Camden National Corp and Camden Property
    # Trust above Advanced Micro Devices for the query "AMD", because "amd"
    # sits inside "camden". A customer typing three letters is naming the
    # start of a word — the middle of one is a coincidence, and coincidences
    # outrank real answers when there are ten thousand rows to draw from.
    joined = " ".join(typed_words)
    haystack = " ".join(name_words)
    if any(word.startswith(typed_words[0]) for word in name_words) \
            and joined in haystack:
        return CONTAINS
    return None


# ===========================================================================
# sources
# ===========================================================================
def _from_registry(typed: str) -> List[Suggestion]:
    try:
        from intent_engine.company_ingestion import entities as E
    except Exception:                                       # noqa: BLE001
        return []
    out = []
    for profile in _registry_profiles(E):
        names = [profile.legal_name] + list(getattr(profile, "aliases", ()))
        best = None
        for name in names:
            rank = _match(typed, name)
            if rank is not None and (best is None or rank < best):
                best = rank
        if best is None:
            continue
        out.append(Suggestion(
            legal_name=profile.legal_name,
            common_name=_common(profile.legal_name),
            country=getattr(profile, "country", "") or "",
            domain=getattr(profile, "primary_domain", "") or "",
            entity_id=getattr(profile, "entity_id", "") or "",
            ticker=str(getattr(profile, "ticker", "") or ""),
            source=REGISTRY, match=best))
    return out


def _registry_profiles(module) -> Sequence:
    """Every EntityProfile the registry module holds, however it holds them.

    Read by type rather than by a named collection: the registry is authored
    as module-level constants plus an index, and a suggestion source that
    depends on which of those is public breaks the first time the registry is
    reorganised.
    """
    seen, out = set(), []
    profile_type = getattr(module, "EntityProfile", None)
    if profile_type is None:
        return out
    for value in vars(module).values():
        candidates = ()
        if isinstance(value, profile_type):
            candidates = (value,)
        elif isinstance(value, (list, tuple, set)):
            candidates = tuple(v for v in value
                               if isinstance(v, profile_type))
        elif isinstance(value, dict):
            candidates = tuple(v for v in value.values()
                               if isinstance(v, profile_type))
        for profile in candidates:
            key = getattr(profile, "entity_id", "") or profile.legal_name
            if key not in seen:
                seen.add(key)
                out.append(profile)
    return out


#: The validation manifest, parsed once per file version.
#:
#: `manifest.load()` re-reads and re-parses the YAML on every call: measured
#: 2026-09-04 at 118.9ms for 100 companies, which was 118.7ms of a 118.9ms
#: suggestion. Autocomplete calls this on every keystroke, so the customer
#: paid a full YAML parse per character -- and on the preview's ~15% CPU
#: share that is over a second before anything can be shown.
#:
#: CACHED HERE RATHER THAN IN `manifest.load()`. Other callers legitimately
#: want a fresh read of a file that a human edits; this is a read-only
#: suggestion path where staleness within one process is harmless. Keyed on
#: (path, mtime, size) so an edited manifest is still picked up rather than
#: being served from a cache until the process restarts.
_MANIFEST_CACHE: Dict[tuple, object] = {}


def _cached_manifest():
    from intent_engine.validation import manifest as M
    import pathlib as _pl
    path = _pl.Path(M.MANIFEST_PATH)
    try:
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        key = (str(path), 0, 0)
    held = _MANIFEST_CACHE.get(key)
    if held is None:
        held = M.load()
        _MANIFEST_CACHE.clear()          # one version at a time, bounded
        _MANIFEST_CACHE[key] = held
    return held


def _from_manifest(typed: str) -> List[Suggestion]:
    try:
        man = _cached_manifest()
    except Exception:                                       # noqa: BLE001
        return []
    out = []
    for company in man.companies:
        names = [company.canonical_name] + list(company.aliases or ())
        best = None
        for name in names:
            rank = _match(typed, name, company.ticker or "")
            if rank is not None and (best is None or rank < best):
                best = rank
        if best is None:
            continue
        out.append(Suggestion(
            legal_name=company.canonical_name,
            common_name=_common(company.canonical_name),
            ticker=company.ticker or "", country=company.country or "",
            domain=company.domain or "", sector=_pretty(company.sector),
            listing=_pretty(company.public_private),
            entity_id=company.company_id, source=MANIFEST, match=best))
    return out


#: The SEC ticker table, parsed once. ~10k rows, one fetch per process.
_TICKERS: Optional[List[Tuple[str, str, str]]] = None


def _ticker_table(transport=None, resolver=None
                  ) -> List[Tuple[str, str, str]]:
    global _TICKERS
    if _TICKERS is not None:
        return _TICKERS
    rows: List[Tuple[str, str, str]] = []
    try:
        import json
        from intent_engine.company_ingestion.edgar import (TICKERS_URL,
                                                           _fetch_bytes)
        raw = _fetch_bytes(TICKERS_URL, transport=transport,
                           resolver=resolver)
        table = json.loads(raw.decode("utf-8", "replace"))
        for row in (table.values() if isinstance(table, dict) else table):
            try:
                rows.append((str(row["title"]).strip().rstrip("/").strip(),
                             str(row.get("ticker") or "").upper(),
                             str(int(row["cik_str"]))))
            except (KeyError, TypeError, ValueError):
                continue
    except Exception:                                       # noqa: BLE001
        rows = []
    _TICKERS = rows
    return rows


#: A 2-character prefix index over the registrant table, built once per
#: process and keyed on every string `_match` can accept a query through.
#:
#: WHY. `_from_registrant` called `_match` on all 10,412 rows for EVERY
#: KEYSTROKE. Measured 2026-09-04: 145ms per query locally once the table was
#: cached, and 1.5-3.1s live -- the preview runs at a ~15% CPU share, which
#: multiplies a CPU-bound scan by roughly ten. A suggestion list that arrives
#: three seconds after the keystroke is not a suggestion list; the customer
#: has finished typing and pressed submit.
#:
#: THE KEYS ARE DERIVED FROM `_match`, NOT GUESSED. Every branch that returns
#: a rank requires one of three things to be true, so the index carries all
#: three per row:
#:   - some WORD of the name starts with the first typed word
#:     (EXACT, LEADING, partial-last-word and CONTAINS all imply this);
#:   - the TICKER equals what was typed;
#:   - the INITIALISM equals what was typed (the one branch where no word
#:     need share a prefix -- "ibm" against International Business Machines).
#: A narrower index would silently stop finding companies, which is why the
#: equivalence is asserted by a test rather than argued here.
_PREFIX_INDEX: Dict[str, List[int]] = {}
_INDEXED_TABLE: List = []


def _index_keys(title: str, ticker: str) -> set:
    keys = set()
    for word in _words(title):
        if word:
            keys.add(word[:2])
    handle = (ticker or "").strip().lower()
    if handle:
        keys.add(handle[:2])
    initialism = _initialism(title) or ""
    if initialism:
        keys.add(initialism[:2])
    return keys


def _registrant_index(transport=None, resolver=None):
    """(rows, prefix -> row indices). Built once, then pure lookup."""
    global _INDEXED_TABLE, _PREFIX_INDEX
    table = list(_ticker_table(transport, resolver))
    if table and (not _PREFIX_INDEX or len(table) != len(_INDEXED_TABLE)):
        index: Dict[str, List[int]] = {}
        for position, (title, ticker, _cik) in enumerate(table):
            for key in _index_keys(title, ticker):
                index.setdefault(key, []).append(position)
        _INDEXED_TABLE, _PREFIX_INDEX = table, index
    return _INDEXED_TABLE, _PREFIX_INDEX


def _candidate_rows(typed: str, transport=None, resolver=None):
    """The rows worth testing for this query. A superset of the matches."""
    table, index = _registrant_index(transport, resolver)
    words = _words(typed)
    key = words[0][:2] if words else ""
    if len(key) < 2:
        # A one-character first word cannot address a two-character bucket.
        # Fall back to the whole table rather than return nothing: correctness
        # first, and `suggest` already refuses queries under two characters.
        return table
    return (table[i] for i in index.get(key, ()))


def _from_registrant(typed: str, *, limit: int, transport=None,
                     resolver=None) -> List[Suggestion]:
    out = []
    for title, ticker, cik in _candidate_rows(typed, transport, resolver):
        rank = _match(typed, title, ticker)
        if rank is None:
            continue
        shown = _readable(title)
        out.append(Suggestion(
            legal_name=shown, common_name=_common(shown), ticker=ticker,
            cik=cik, listing="Public", source=REGISTRANT, match=rank))
        if len(out) >= limit * 8:
            break
    return out


# ===========================================================================
def suggest(typed: str, *, limit: int = 8, allow_registrant: bool = True,
            transport=None, resolver=None) -> Tuple[Suggestion, ...]:
    """Companies the customer could mean, best first. Never raises.

    Two typed characters is the floor: one character matches thousands of
    filers and the list is noise, which trains the customer to ignore it.
    """
    typed = " ".join(str(typed or "").split())
    if len(typed) < 2:
        return ()
    rows: List[Suggestion] = []
    for source in (_from_registry, _from_manifest):
        try:
            rows.extend(source(typed))
        except Exception:                                   # noqa: BLE001
            continue
    if allow_registrant:
        try:
            rows.extend(_from_registrant(typed, limit=limit,
                                         transport=transport,
                                         resolver=resolver))
        except Exception:                                   # noqa: BLE001
            pass
    # DEDUPE ACROSS SOURCES, KEEPING THE RICHEST ROW.
    #
    # Cloudflare is in all three. The registry and manifest rows carry a
    # domain and a country; the registrant row carries a CIK and a ticker.
    # Showing three rows for one company is the ambiguity signal firing on a
    # company that is not ambiguous, so they are merged into the strongest
    # identity, enriched with whatever the weaker rows knew that it did not.
    merged: Dict[str, Suggestion] = {}
    for row in sorted(rows, key=lambda r: (r.match,
                                           SOURCE_RANK.get(r.source, 9))):
        key = " ".join(_words(row.legal_name))
        held = merged.get(key)
        if held is None:
            merged[key] = row
            continue
        merged[key] = dataclasses.replace(
            held,
            ticker=held.ticker or row.ticker,
            country=held.country or row.country,
            city=held.city or row.city,
            domain=held.domain or row.domain,
            listing=held.listing or row.listing,
            sector=held.sector or row.sector,
            entity_id=held.entity_id or row.entity_id,
            cik=held.cik or row.cik)
    ordered = sorted(merged.values(),
                     key=lambda r: (r.match, SOURCE_RANK.get(r.source, 9),
                                    len(r.legal_name)))
    return tuple(ordered[:limit])


def _common(legal: str) -> str:
    """The name a person would say. Empty when it equals the legal name."""
    words = str(legal or "").replace(",", " ").split()
    kept = [w for w in words if w.strip(".,&").lower() not in _SUFFIXES]
    common = " ".join(kept).strip()
    return "" if common.lower() == str(legal or "").strip().lower() else common


def _pretty(token: str) -> str:
    flat = str(token or "").replace("_", " ").strip()
    return flat.capitalize() if flat and flat.isupper() else flat


#: Tokens that are acronyms or legal forms, not words, so title-casing them
#: produces "Plc" and "Usa". Everything not listed here is a word.
_KEEP_UPPER = frozenset({
    "USA", "US", "UK", "AG", "NV", "SA", "SE", "LLC", "GMBH", "REIT",
    "ADR", "II", "III", "IV", "S.A.", "N.V.", "AI", "IT", "HP", "IBM",
    "AT&T", "3M", "CVS", "UPS", "PNC", "KKR", "EOG", "DXC", "NA", "FSB",
})

#: EDGAR appends the state of incorporation to some registrant titles —
#: "BANK OF AMERICA CORP /DE", "GENERAL MOTORS CO /DE/". It is filing-index
#: furniture, not part of the name, and it reaches a customer as noise.
_STATE_SUFFIX = None


def _readable(legal: str) -> str:
    """An EDGAR registrant title, as a person would write it.

    The regulator's table is upper-case, so "JOHNSON & JOHNSON" and
    "CATERPILLAR INC" reach the suggestion list SHOUTING while the curated
    rows beside them are properly cased. Only ALL-CAPS titles are touched: a
    correctly cased name is left exactly as its source wrote it, because
    re-casing "eBay" or "Vale S.A." would be a regression, not a repair.
    """
    import re as _re
    flat = " ".join(str(legal or "").split())
    flat = _re.sub(r"\s*/[A-Z]{2}/?$", "", flat).strip()
    letters = [c for c in flat if c.isalpha()]
    if not letters or any(c.islower() for c in letters):
        return flat
    out = []
    for word in flat.split(" "):
        bare = word.strip(".,").upper()
        if bare in _KEEP_UPPER or not any(c.isalpha() for c in word):
            out.append(word.upper() if bare in _KEEP_UPPER else word)
        else:
            out.append(word.capitalize())
    return " ".join(out)
