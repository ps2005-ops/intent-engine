"""Whose demand, in which direction, and is it an observation at all.

WHY THIS IS NOT A KEYWORD LIST
------------------------------
Measured before this module existed: taking `demand_chain`'s phrase list and
using it as a detector scores PRECISION 0.50 on a labelled corpus. One in two
admissions is wrong, and the wrong ones are not random — they are the same
four mistakes every time:

    "We placed orders for new manufacturing equipment"
        the company BUYING. Capex, and it would enter the demand chain as
        customer demand strengthening.
    "Komatsu reported strong bookings growth"
        a rival's demand, attributed here because the sentence sits in our
        document.
    "We expect bookings to improve in the second half"
        an expectation admitted as an observation.
    "The engineering team reduced its ticket backlog by 40%"
        the same word from another domain entirely.

None of those is fixed by more phrases. Each is a different QUESTION about
the sentence, so this module asks them separately and refuses with the reason
that applies:

    is there a commercial demand object at all      NO_COMMERCIAL_OBJECT
    is the object in a commercial domain            NO_COMMERCIAL_OBJECT
    is it stated, or expected, or feared            SPECULATIVE
    whose demand is it                              WRONG_SUBJECT
    which side of the transaction are we on         WRONG_ROLE
    is anything actually said about it              GENERIC_LANGUAGE / NO_DIRECTION

THE ONE THAT MATTERS MOST
-------------------------
Role. "We placed orders" and "customer orders increased" share a noun and
share nothing else: the first is the company as BUYER and is a cost, the
second is the company as SELLER and is demand. Getting it backwards puts
procurement into a thesis about customers, with a citation attached.

WHAT THIS MODULE DOES NOT DO
----------------------------
It does not fold readings into states, and it does not decide that a rising
backlog beside falling bookings means demand is strong. It reads ONE sentence
and reports what that sentence supports. The chain is `demand_chain`'s job and
it needs these to be right first.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "demand_extraction.v1"

# --- economic role ----------------------------------------------------------
SELLER = "SELLER"
BUYER = "BUYER"
SUPPLIER = "SUPPLIER"
COMPETITOR = "COMPETITOR"
MARKET = "MARKET"
UNKNOWN_ROLE = "UNKNOWN"
ROLES = (SELLER, BUYER, SUPPLIER, COMPETITOR, MARKET, UNKNOWN_ROLE)

# --- what kind of claim -----------------------------------------------------
OBSERVATION = "OBSERVATION"
EXPECTATION = "EXPECTATION"
RISK = "RISK"
STANDINGS = (OBSERVATION, EXPECTATION, RISK)

# --- direction --------------------------------------------------------------
UP, DOWN, FLAT, UNKNOWN_DIRECTION = "UP", "DOWN", "FLAT", "UNKNOWN"
DIRECTIONS = (UP, DOWN, FLAT, UNKNOWN_DIRECTION)

# --- refusal reasons --------------------------------------------------------
#
# Deliberately not one bucket. `UNCLASSIFIABLE` was production's answer for
# 1,059 candidates a cycle, which is a number that cannot be acted on: a
# wrong-role refusal is a detector working correctly and a no-direction
# refusal is a sentence worth revisiting, and both looked identical.
WRONG_ROLE = "WRONG_ROLE"
WRONG_SUBJECT = "WRONG_SUBJECT"
SPECULATIVE = "SPECULATIVE"
GENERIC_LANGUAGE = "GENERIC_LANGUAGE"
NO_COMMERCIAL_OBJECT = "NO_COMMERCIAL_OBJECT"
NO_DIRECTION = "NO_DIRECTION"
REFUSAL_REASONS = (WRONG_ROLE, WRONG_SUBJECT, SPECULATIVE, GENERIC_LANGUAGE,
                   NO_COMMERCIAL_OBJECT, NO_DIRECTION)

# --- the demand objects -----------------------------------------------------
#
# Order matters and is load-bearing. "Order cancellations rose" is a
# CANCELLATION, not an ORDER, and "order backlog" is a BACKLOG — the more
# specific object must be tested first or the general one steals it.
#
# Each entry carries DISQUALIFIERS: the same word in another domain. This is
# where a keyword list fails and it is cheaper to state the exclusions with
# the object than to discover them in a dossier.
_OBJECTS: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ("CANCELLATIONS",
     # The gap is 60 rather than 40 because a real sentence puts the amount
     # between the verb and the object: "cancelled $180 million of
     # previously booked orders" is 44 characters wide and a 40 missed it.
     r"\bcancellations?\b|\bde-?bookings?\b|\bchurn(?:ed|\srate)?\b"
     r"|\bcancell?ed\b[^.]{0,60}\borders?\b",
     (r"\bcancell?ed\b[^.]{0,30}\b(supplier|vendor|procurement|internal|"
      r"program|project)\b",)),
    ("BACKLOG",
     r"\bbacklogs?\b|\border book\b",
     # The word belongs to four other industries and every one of them shows
     # up in filings that also discuss demand.
     (r"\b(ticket|court|case|engineering|maintenance|support|technical|"
      r"sprint|judicial|immigration|asylum|repair) backlogs?\b",)),
    ("COMMITTED_DEMAND",
     r"\b(?:remaining|unsatisfied) performance obligations?\b"
     r"|\bperformance obligations?\b|\bcontract liabilit(?:y|ies)\b"
     r"|\bdeferred revenue\b|\bunearned revenue\b|\bRPO\b"
     r"|\bcommitted (?:volume|spend|contracts?)\b|\btake[- ]or[- ]pay\b",
     ()),
    ("BOOKINGS",
     r"\bbookings?\b|\bbook[- ]to[- ]bill\b",
     ()),
    ("ORDERS",
     r"\border intake\b|\border rates?\b|\bnew orders\b|\bcustomer orders\b"
     r"|\borders? (?:received|placed with)\b|\border volume\b"
     r"|\border growth\b|\borders?\b",
     # Every one of these is the word doing a different job. "in order to"
     # alone appears in most filings.
     # "purchase orders" is deliberately NOT disqualified here. It IS an
     # order; it is simply one the company placed, and refusing it as
     # NO_COMMERCIAL_OBJECT loses that distinction. The role gate owns it and
     # reports WRONG_ROLE, which is the reason a reader can act on.
     (r"\b(court|executive|standing|gag|restraining|working) "
      r"orders?\b",
      r"\border of magnitude\b", r"\bin order to\b",
      r"\bworking order\b", r"\border to\b")),
    ("SHIPMENTS",
     r"\bshipments?\b|\bunits? shipped\b|\bdeliver(?:ies|y volume)\b"
     r"|\bdelivered volume\b",
     ()),
    ("CUSTOMER_INTENT",
     r"\b(?:qualified )?pipeline\b|\bletters? of intent\b"
     r"|\brequests? for proposals?\b|\bRFPs?\b|\bcustomer inquiries\b"
     r"|\btrial conversions?\b",
     # A pipeline is also a physical asset, and midstream companies file too.
     (r"\b(oil|gas|natural gas|crude|water|drug|product|refinery) "
      r"pipelines?\b",)),
    ("GUIDANCE",
     r"\bguidance\b|\boutlook for the\b|\bfull[- ]year expectations\b",
     ()),
    ("END_DEMAND",
     r"\bend[- ]market demand\b|\bend demand\b|\bconsumer demand\b"
     r"|\bunderlying demand\b|\bindustry demand\b",
     ()),
    ("REVENUE",
     r"\bsales and revenues?\b|\brevenues?\b|\bnet sales\b|\btotal sales\b",
     ()),
)
_COMPILED = tuple(
    (state, re.compile(pattern, re.I),
     tuple(re.compile(d, re.I) for d in disqualifiers))
    for state, pattern, disqualifiers in _OBJECTS)

#: States that are ABOUT the market rather than about one company's pipeline.
#: Detected so the reason can say so, then refused: the industry's end demand
#: is not this company's demand state, however much it bears on it.
_MARKET_STATES = frozenset({"END_DEMAND"})

#: A company's stated outlook IS an expectation. Every other state must be an
#: observation, which is why the speculation gate skips this one.
_EXPECTATION_STATES = frozenset({"GUIDANCE"})

# --- is it stated, expected, or feared --------------------------------------
# `estimat\w+` was here and had to come out. "Revenue topped estimates" and
# "earnings beat estimates" are RESULTS — the estimate is the thing that was
# beaten, not a forecast the company is making — and the word alone refused
# twelve real revenue sentences on the live corpus as speculation.
_EXPECTS = re.compile(
    r"\b(expects?|expected|expecting|anticipat\w+|forecast\w*|project(?:s|ed|"
    r"ing)?|believ\w+|plans? to|intends? to|outlook|guid\w+ to|"
    r"will\b|going to)\b", re.I)
_RISKS = re.compile(
    r"\b(could|may|might|risks?\b|if\b[^.]{0,60}\b(persist|continue|worsen|"
    r"extend)|potential\w*|possibl\w+|uncertain\w*)\b", re.I)

# --- whose demand -----------------------------------------------------------
#: Another actor's possessive right before the object — "Deere's order
#: backlog". The nearest governing subject owns the claim.
_POSSESSIVE = re.compile(r"\b([A-Z][\w&.\-]+(?:\s+[A-Z][\w&.\-]+)*)'s\b")
#: Another actor reporting its own results — "Komatsu reported strong
#: bookings growth". A reporting verb makes the subject unambiguous.
_REPORTED = re.compile(
    r"\b([A-Z][\w&.\-]+(?:\s+[A-Z][\w&.\-]+)*)\s+"
    r"(reported|posted|announced|disclosed|said|guided)\b")
_MARKET_SCOPE = re.compile(
    r"\b(industry[- ]wide|across the industry|industry\b[^.]{0,20}\borders\b|"
    r"market[- ]wide|sector[- ]wide|end[- ]market|economy[- ]wide|"
    r"across north america|global demand)\b", re.I)

#: Capitalised words that begin sentences and are not companies. Without this
#: "Customer orders increased" reads as a company called Customer.
_NOT_A_COMPANY = frozenset({
    "the", "we", "our", "a", "an", "in", "on", "at", "customer", "customers",
    "new", "net", "order", "orders", "bookings", "backlog", "sales",
    "revenue", "revenues", "units", "unit", "deliveries", "shipments",
    "management", "total", "contract", "contracts", "remaining",
    "unsatisfied", "qualified", "pipeline", "demand", "industry", "end",
    "second", "first", "third", "fourth", "full", "this", "that", "these",
    "those", "strong", "record", "gross", "adjusted", "operating", "during",
    "for", "as", "by", "with", "however", "additionally", "also", "while",
    "purchase", "supplier", "suppliers", "guidance", "outlook", "cancelled",
    "canceled", "cancellations", "performance", "deferred", "committed"})

# --- which side of the transaction ------------------------------------------
#: The company doing the buying. First person or an alias, governing a
#: purchase verb, anywhere before the object.
_WE_BUY = re.compile(
    r"\b(we|our|the company|the group)\b[^.]{0,60}?\b"
    r"(placed|issued|ordered|purchas\w+|procur\w+|award\w+ to)\b", re.I)
_BUY_OBJECT = re.compile(
    r"\bpurchase orders?\b|\bour orders? to\b|\borders? to (?:our )?"
    r"suppliers?\b|\bsupplier (?:orders?|shipments?|deliveries)\b"
    r"|\bsupplier contracts?\b|\bfrom (?:our )?suppliers?\b", re.I)
#: Inbound flow. "Supplier shipments to our plants" is a supply fact wearing
#: a demand word.
_INBOUND = re.compile(
    r"\b(?:to|into|at) (?:our|the company's|its) (?:plants?|factor\w+|"
    r"facilit\w+|warehouses?|sites?)\b", re.I)

# --- direction --------------------------------------------------------------
# `rais\w+`, `top\w+`, `beat` and `exceed\w+` were added after the live
# corpus refused "Raises 2026 Guidance" for having no direction. A company
# raising guidance is the most direction-bearing sentence a filing has.
_UP = re.compile(
    r"\b(increas\w+|ros\w*e|rise|rising|grew|grow\w*|growth|higher|up\b|"
    r"record\b|strengthen\w+|improv\w+|expand\w+|gain\w*|added|rais\w+|"
    r"boost\w*|lift\w*|topp?e?d?|beat|exceed\w+|surpass\w+)\b", re.I)
_DOWN = re.compile(
    r"\b(declin\w+|decreas\w+|fell|fall\w*|lower|down\b|weaken\w+|soft\w*|"
    r"reduc\w+|contract\w+|shrank|shrink\w*|slowed|slow\w*down|cut\b|"
    r"trimm?\w*|missed\b|shortfall)\b", re.I)
#: A balance stated without a change verb — "contract liabilities WERE
#: $7,280 million". A level is a real observation and its direction is FLAT,
#: not unknown: the sentence says what the number is.
_LEVEL = re.compile(
    r"\b(was|were|is|are|totall?ed|totals?|stood at|reached|remain\w*|"
    r"amounted to|ended at)\b", re.I)
_QUANTITY = re.compile(
    r"(\$\s?[\d,.]+\s*(?:billion|million|thousand|bn|m\b)?|\b[\d,.]+\s*%|"
    r"\b[\d][\d,.]*\s*(?:billion|million|units|vehicles|machines)\b)", re.I)

#: Demand-flavoured language with no object and no number. Named rather than
#: lumped with NO_COMMERCIAL_OBJECT so the refusal log can show how much of a
#: corpus is marketing.
_MARKETING = re.compile(
    r"\b(love|exciting|excited|thrilled|delighted|strong interest|"
    r"tremendous|incredible|amazing|healthy demand|demand remains|"
    r"robust demand|strong demand)\b", re.I)


@dataclass(frozen=True)
class Reading:
    """One sentence, read. `state` is None when the sentence was refused."""
    state: Optional[str]
    role: str = UNKNOWN_ROLE
    direction: str = UNKNOWN_DIRECTION
    standing: str = OBSERVATION
    quantitative: bool = False
    quantity: str = ""
    reason: str = ""
    basis: str = ""

    @property
    def admitted(self) -> bool:
        return self.state is not None

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "state": self.state, "role": self.role,
                "direction": self.direction, "standing": self.standing,
                "quantitative": self.quantitative, "quantity": self.quantity,
                "reason": self.reason, "basis": self.basis}


def _alias_match(name: str, aliases: Sequence[str]) -> bool:
    cleaned = re.sub(r"[^\w\s]", "", name or "").strip().lower()
    if not cleaned:
        return False
    for alias in aliases:
        a = re.sub(r"[^\w\s]", "", alias or "").strip().lower()
        if not a:
            continue
        if cleaned == a or cleaned.startswith(a + " ") or a.startswith(
                cleaned + " "):
            return True
    return False


def _object_of(text: str) -> Tuple[Optional[str], str]:
    """The demand object this sentence names, or None with a reason."""
    for state, pattern, disqualifiers in _COMPILED:
        hit = pattern.search(text)
        if not hit:
            continue
        if any(d.search(text) for d in disqualifiers):
            # The word is here and it belongs to another domain. Keep looking:
            # a sentence can mention a ticket backlog AND real bookings.
            continue
        return state, hit.group(0)
    return None, ""


def _owner(text: str, aliases: Sequence[str]) -> Tuple[str, str]:
    """Who the claim belongs to: SELLER (us), COMPETITOR, or MARKET."""
    if _MARKET_SCOPE.search(text):
        return MARKET, _MARKET_SCOPE.search(text).group(0)
    reported = _REPORTED.search(text)
    if reported and not _alias_match(reported.group(1), aliases):
        if reported.group(1).split()[0].lower() not in _NOT_A_COMPANY:
            return COMPETITOR, reported.group(1)
    for possessive in _POSSESSIVE.finditer(text):
        name = possessive.group(1)
        if name.split()[0].lower() in _NOT_A_COMPANY:
            continue
        if not _alias_match(name, aliases):
            return COMPETITOR, name
    return SELLER, ""


def _role_of(text: str, aliases: Sequence[str] = ()) -> Tuple[str, str]:
    """Which side of the transaction the subject company is on."""
    for alias in aliases:
        if not alias:
            continue
        # "Caterpillar ordered additional machine tools" — the company named
        # as the one doing the buying. Same fact as "we placed orders", said
        # in the third person, and a first-person-only rule missed it.
        governed = re.search(
            re.escape(alias) + r"\b[^.]{0,30}?\b(placed|issued|ordered|"
            r"purchas\w+|procur\w+)\b", text, re.I)
        if governed:
            return BUYER, governed.group(0)
    hit = _BUY_OBJECT.search(text)
    if hit:
        return (SUPPLIER if "supplier" in hit.group(0).lower() else BUYER,
                hit.group(0))
    hit = _INBOUND.search(text)
    if hit:
        return SUPPLIER, hit.group(0)
    hit = _WE_BUY.search(text)
    if hit:
        return BUYER, hit.group(0)
    return SELLER, ""


def _standing_of(text: str) -> str:
    if _RISKS.search(text):
        return RISK
    if _EXPECTS.search(text):
        return EXPECTATION
    return OBSERVATION


def _direction_of(text: str) -> str:
    up, down = bool(_UP.search(text)), bool(_DOWN.search(text))
    if up and not down:
        return UP
    if down and not up:
        return DOWN
    if up and down:
        # Both present: "backlog rose while bookings fell" is two claims and
        # this module reads one sentence. Refusing to pick is the honest
        # answer; the caller can split the sentence.
        return UNKNOWN_DIRECTION
    if _LEVEL.search(text):
        return FLAT
    if _QUANTITY.search(text):
        # A magnitude stated without a change verb — "customers cancelled
        # $180 million of previously booked orders". The sentence says what
        # the number IS, so the honest direction is FLAT. Inventing UP from
        # the fact that a cancellation happened would be reading the event's
        # sign off its name.
        return FLAT
    return UNKNOWN_DIRECTION


def read(text: str, *, aliases: Sequence[str] = ()) -> Reading:
    """Read one sentence. Every refusal carries the reason that applies."""
    sentence = " ".join((text or "").split())
    if not sentence:
        return Reading(None, reason=NO_COMMERCIAL_OBJECT)

    state, basis = _object_of(sentence)
    if state is None:
        return Reading(
            None,
            reason=(GENERIC_LANGUAGE if _MARKETING.search(sentence)
                    else NO_COMMERCIAL_OBJECT),
            basis=sentence[:160])

    standing = _standing_of(sentence)
    if standing != OBSERVATION and state not in _EXPECTATION_STATES:
        return Reading(None, standing=standing, reason=SPECULATIVE,
                       basis=basis, direction=_direction_of(sentence))

    owner, who = _owner(sentence, aliases)
    if owner in (COMPETITOR, MARKET) or state in _MARKET_STATES:
        return Reading(None, role=(MARKET if state in _MARKET_STATES
                                   else owner),
                       reason=WRONG_SUBJECT, basis=who or basis)

    role, evidence = _role_of(sentence, aliases)
    if role != SELLER:
        return Reading(None, role=role, reason=WRONG_ROLE,
                       basis=evidence or basis)

    direction = _direction_of(sentence)
    if direction == UNKNOWN_DIRECTION:
        return Reading(None, role=SELLER, reason=NO_DIRECTION, basis=basis)

    quantity = _QUANTITY.search(sentence)
    return Reading(state=state, role=SELLER, direction=direction,
                   standing=standing, quantitative=bool(quantity),
                   quantity=quantity.group(0) if quantity else "",
                   basis=basis)


def summarise(readings: Sequence[Reading]) -> dict:
    """Admissions and refusals, with refusals broken out by reason.

    The refusal breakdown is the point. A pipeline reporting only what it
    accepted cannot tell a detector that is working from one that is silent,
    and `UNCLASSIFIABLE` as a single bucket is what production had.
    """
    admitted = [r for r in readings if r.admitted]
    refused = [r for r in readings if not r.admitted]
    by_state: Dict[str, int] = {}
    by_reason: Dict[str, int] = {}
    for reading in admitted:
        by_state[reading.state] = by_state.get(reading.state, 0) + 1
    for reading in refused:
        by_reason[reading.reason] = by_reason.get(reading.reason, 0) + 1
    return {
        "contract": CONTRACT,
        "sentences": len(readings),
        "admitted": len(admitted),
        "refused": len(refused),
        "by_state": by_state,
        "by_reason": by_reason,
        "quantitative": sum(1 for r in admitted if r.quantitative),
        "qualitative": sum(1 for r in admitted if not r.quantitative),
        "note": ("a refusal reason is a finding, not a shrug: WRONG_ROLE is "
                 "a detector working and NO_DIRECTION is a sentence worth "
                 "revisiting, and one bucket cannot tell them apart"),
    }


def read_all(sentences: Sequence[str], *, aliases: Sequence[str] = ()
             ) -> List[Reading]:
    return [read(s, aliases=aliases) for s in sentences]
