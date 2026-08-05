"""Commercial-event recognition: normalized action patterns, not phrase lists.

WHY NOT A PHRASE LIST
---------------------
The previous classifier was verb-first and it was measurably narrow in a
specific way: `"was awarded a contract"` classified and `"announced a contract
award"` did not. English says the same commercial fact in four shapes —

    active         Caterpillar won a multi-year contract
    passive        Caterpillar was awarded a multi-year contract
    nominalized    Caterpillar announced a multi-year contract award
    light verb     Caterpillar secured a multi-year agreement

— and a list of verbs only ever catches the first two. So a family is declared
once, as (ACTION, OBJECT): the ACTION alternatives cover the verb shapes and
the reporting frames that wrap them, and the OBJECT is the thing the event is
about. Adding a fifth phrasing to a family is one alternative, not a new rule.

THE PRECISION HALF IS THE POINT
-------------------------------
Recall was the stated problem, so the temptation is to loosen. Pushed far
enough to classify a real corpus, a loosened classifier labels
`"Palantir partners with world leading organizations"` a partnership event and
`"Invent with purpose"` a product event — the same failure as the risk-factor
competitor extraction that named Palantir's own CEO as a rival: real source,
real passage, false claim.

Two guards, both measured against the negative-control corpus:

  * every family requires an OBJECT as well as an ACTION, so a bare verb
    ("we partner with the best") cannot fire;
  * `_NON_EVENT` catches the standing-state phrasings that use event
    vocabulary to describe a permanent condition rather than something that
    happened ("our partners", "we launch products every day").

An honest UNKNOWN is cheaper than a false event. A false event updates a real
belief with a real citation attached, which is the most convincing kind of
wrong.
"""
from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

from . import micro_evidence as ME

PATTERN_VERSION = "commercial_event_patterns.v1"

# --- building blocks ------------------------------------------------------
# Reporting frames that wrap an event without being one. Kept separate so a
# family does not have to spell out "announced that it has ..." itself.
_SAY = (r"announc\w+|report\w+|said|says|state[sd]?|disclos\w+|confirm\w+|"
        r"reveal\w+|not\w*ed|unveil\w+|declar\w+")

# A number, money amount or duration — evidence that a sentence is about a
# specific transaction rather than a standing capability.
_QUANT = (r"(?:\$|€|£|¥)\s?[\d.,]+\s*(?:billion|bn|million|mm|m|k|thousand)?|"
          r"\b\d[\d.,]*\s*(?:billion|bn|million|percent|%|basis points|bps|"
          r"years?|months?|quarters?)\b|\bmulti-?year\b|\bfive-?year\b")


def _any(*alts: str) -> str:
    return "(?:" + "|".join(alts) + ")"


# --- the families ---------------------------------------------------------
#
# Each entry is (evidence_type, action_pattern, object_pattern). A sentence
# classifies when BOTH match it. Order matters: the first family to match
# wins, so the specific ones come before the general ones.
_FAMILIES: Tuple[Tuple[str, str, str], ...] = (
    # --- earnings ---------------------------------------------------------
    (ME.EARNINGS_SURPRISE,
     _any(r"beat", r"exceed\w*", r"surpass\w*", r"came in (?:above|below)",
          r"missed", r"fell short of", r"outperform\w*", r"topped"),
     _any(r"(?:analyst|consensus|street|wall street)[\s']*"
          r"(?:estimates?|expectations?|forecasts?|views?)",
          r"\bexpectations?\b", r"\bestimates?\b", r"\bconsensus\b")),
    (ME.EARNINGS_RESULT,
     _any(r"report\w+", r"post\w+", r"deliver\w+", r"announc\w+", r"record\w+",
          r"increas\w+", r"grew", r"grow\w+", r"ros\w*e?", r"declin\w+",
          r"fell", r"was", r"were", r"totall?\w*", r"reach\w+"),
     _any(r"\b(?:first|second|third|fourth)[- ]quarter\b",
          r"\bq[1-4]\b", r"\bfull[- ]year (?:results|revenue|earnings)\b",
          r"\brevenues?\b", r"\bearnings\b", r"\bnet income\b",
          r"\bprofit per share\b", r"\bearnings per share\b", r"\beps\b",
          r"\boperating (?:income|margin)\b", r"\bsales and revenues\b")),
    # A results bullet has no verb at all: Caterpillar's release states
    # "Second-quarter 2026 profit per share of $7.77; adjusted profit per
    # share of $8.17." The dated period does the work a verb usually does, so
    # the period marker is the ACTION half here. The non-overlap rule still
    # applies, so a bare "Second Quarter." table heading cannot fire.
    (ME.EARNINGS_RESULT,
     _any(r"(?:first|second|third|fourth)[- ]quarter \d{4}",
          r"q[1-4] (?:fy)?\s?\d{2,4}", r"full[- ]year \d{4}",
          r"fiscal (?:year )?\d{4}"),
     _any(r"\b(?:revenues?|earnings|net income|profit per share|"
          r"earnings per share|eps|operating (?:income|margin)|"
          r"sales and revenues|free cash flow)\b(?:[^.]{0,60})"
          r"(?:\$|€|£)?[\d.,]+")),
    # --- guidance ---------------------------------------------------------
    (ME.GUIDANCE_REVISION,
     _any(r"rais\w+", r"lower\w+", r"cut", r"cuts", r"reduc\w+", r"updat\w+",
          r"revis\w+", r"reaffirm\w+", r"reiterat\w+", r"withdr\w+",
          r"narrow\w+", r"widen\w+", r"issu\w+", r"provid\w+", r"expect\w+",
          r"anticipat\w+", r"sees?", r"forecast\w*", r"project\w+",
          _SAY),
     _any(r"\b(?:its |the |full[- ]year |fy\s*\d*\s*|annual |quarterly )*"
          r"(?:outlook|guidance|forecast)\b",
          r"\bguidance (?:range|revision|increase|cut)\b",
          r"\boutlook for\b")),
    # --- pricing ----------------------------------------------------------
    (ME.PRICING_SIGNAL,
     _any(r"rais\w+", r"increas\w+", r"cut", r"cuts", r"cutting", r"reduc\w+",
          r"lower\w+", r"chang\w+", r"adjust\w+", r"repric\w+", r"hik\w+",
          r"discount\w*", r"introduc\w+", _SAY),
     _any(r"\b(?:list |subscription |sticker |wholesale |retail )?prices?\b",
          r"\bpricing\b", r"\bprice (?:increase|cut|reduction|change|rise)\b",
          r"\bprice list\b", r"\btariffs?\b", r"\bfees?\b",
          r"\bsubscription (?:cost|rate)s?\b")),
    # --- contracts and awards --------------------------------------------
    (ME.CONTRACT_AWARD,
     _any(r"award\w+", r"won", r"wins", r"winning", r"secur\w+",
          r"receiv\w+", r"select\w+", r"chos\w+", r"sign\w+", r"book\w+",
          r"extend\w+", r"renew\w+", r"grant\w+", _SAY),
     _any(r"\bcontracts?\b", r"\bcontract award\b", r"\bagreements?\b",
          r"\btask orders?\b", r"\bpurchase orders?\b",
          r"\b(?:idiq|ota|bpa)\b", r"\bdeals?\b", r"\bmandates?\b",
          r"\bsole[- ]source\b", r"\bframework\b")),
    # --- procurement ------------------------------------------------------
    (ME.PROCUREMENT_SIGNAL,
     _any(r"issu\w+", r"open\w+", r"clos\w+", r"publish\w+", r"solicit\w+",
          r"submit\w+", r"bid", r"bidding", r"tender\w*", _SAY),
     _any(r"\brequest for (?:proposals?|information|quotations?)\b",
          r"\brfp\b", r"\brfi\b", r"\brfq\b", r"\bsealed bid\b",
          r"\breverse auction\b", r"\bsolicitation\b",
          r"\bprocurement (?:process|vehicle|award|programme|program)\b",
          r"\btender (?:process|offer|award)\b")),
    # --- product ----------------------------------------------------------
    (ME.PRODUCT_LAUNCH,
     _any(r"launch\w*", r"unveil\w+", r"introduc\w+", r"releas\w+",
          r"ship\w+", r"roll\w*(?:ed|ing)? out", r"debut\w*",
          r"made? (?:it )?generally available", r"open\w+ up", _SAY),
     _any(r"\bnew (?:product|platform|service|feature|model|version|"
          r"offering|tool|capability|chip|device|application|app)s?\b",
          r"\b(?:product|platform|service|feature|model|version|offering)"
          r" launch\b", r"\bgeneral availability\b", r"\bnext[- ]generation\b",
          r"\blaunch of\b", r"\bavailability of\b")),
    # --- M&A --------------------------------------------------------------
    (ME.MA_ACTIVITY,
     _any(r"acquir\w+", r"purchas\w+", r"buy\w*", r"bought", r"merg\w+",
          r"divest\w+", r"spin\w*(?:ning)?[- ]off", r"sold", _SAY),
     _any(r"\bacquisitions?\b", r"\bmergers?\b", r"\bdivestitures?\b",
          r"\btakeovers?\b", r"\bstake in\b", r"\bassets? of\b",
          r"\ball[- ]cash (?:deal|transaction)\b", r"\bbusiness unit\b")),
    # --- partnerships -----------------------------------------------------
    (ME.PARTNERSHIP,
     _any(r"partner\w*", r"team\w*(?: up)?", r"collaborat\w+", r"alli\w+",
          r"join\w*(?: forces)?", r"expand\w+", r"deepen\w+", _SAY),
     _any(r"\b(?:strategic |new |multi-?year |global )?partnerships?\b",
          r"\bjoint ventures?\b", r"\balliances?\b",
          r"\bstrategic collaborations?\b",
          r"\bcollaboration (?:with|agreement)\b",
          r"\bforces with\b")),
    # --- workforce --------------------------------------------------------
    (ME.LAYOFF,
     _any(r"lay\w*(?: off)?", r"laid off", r"cut\w*", r"reduc\w+",
          r"eliminat\w+", r"elimin\w+", r"trim\w+", r"announc\w+", _SAY),
     _any(r"\bjob cuts?\b", r"\blayoffs?\b", r"\bredundanc\w+\b",
          r"\bworkforce reduction\b", r"\bheadcount\b", r"\bpositions?\b",
          r"\brestructuring (?:plan|programme|program)\b",
          r"\b\d[\d,]* (?:employees|jobs|roles|staff)\b")),
    (ME.HIRING,
     _any(r"hir\w+", r"add\w+", r"expand\w+", r"grew", r"grow\w+",
          r"recruit\w+", r"onboard\w+", _SAY),
     _any(r"\bhiring\b", r"\bheadcount growth\b", r"\bnew (?:hires|roles|"
          r"positions|engineers|employees)\b",
          r"\b\d[\d,]* (?:employees|engineers|staff|roles)\b",
          r"\bteam (?:by|to) \d\b", r"\bopen roles\b")),
    # --- executives -------------------------------------------------------
    #
    # NO REPORTING FRAME HERE. With `_SAY` in the action list, any sentence
    # quoting a named executive became an executive-change event: "'We are
    # advancing the frontier...,' said Satya Nadella, chairman and CEO" was
    # classified on the real corpus. A quote is not a change of office, so
    # this family takes only verbs that move somebody into or out of a role.
    (ME.EXECUTIVE_CHANGE,
     _any(r"appoint\w+", r"nam\w+", r"promot\w+", r"elect\w+",
          r"resign\w+", r"step\w*(?:ped|ping)? down", r"retir\w+",
          r"depart\w+", r"succeed\w+", r"will continue to serve",
          r"inform\w+ the compan\w+", r"stand for"),
     _any(r"\bchief \w+ officer\b", r"\bc[efot]o\b", r"\bpresident\b",
          r"\bchair(?:man|woman|person)?\b", r"\bboard of directors\b",
          r"\bdirector\b", r"\bexecutive (?:vice president|chairman)?\b",
          r"\bre-?election\b", r"\bsuccessor\b")),
    # --- capital returned to shareholders ---------------------------------
    # Separated from capex. Both spend cash and they mean opposite things: a
    # new fab is a bet on demand that has not arrived, a buyback is a decision
    # that there is nothing better to do with the money.
    (ME.CAPITAL_RETURN,
     _any(r"rais\w+", r"increas\w+", r"declar\w+", r"approv\w+",
          r"authoriz\w+", r"authoris\w+", r"expand\w+", r"deploy\w+",
          r"return\w*", r"repurchas\w+", r"vot\w+", r"boost\w+", r"cut",
          r"suspend\w+", _SAY),
     _any(r"\bdividends?\b", r"\bshare repurchases?\b", r"\bbuybacks?\b",
          r"\brepurchase program\w*\b", r"\bcapital return\b")),
    # --- capacity and capital --------------------------------------------
    (ME.CAPEX_SIGNAL,
     _any(r"invest\w+", r"commit\w+", r"spend\w*", r"spent", r"build\w*",
          r"built", r"expand\w+", r"add\w+", r"open\w+", r"deploy\w+",
          r"allocat\w+", r"increas\w+", r"rais\w+", r"plan\w*", _SAY),
     _any(r"\bcapital expenditures?\b", r"\bcapex\b",
          r"\bnew (?:plant|factory|fab|facility|data cent\w+|campus)\b",
          r"\bcapacity expansion\b", r"\bmanufacturing capacity\b",
          r"\bproduction capacity\b", r"\bcapital spending\b")),
    # --- regulatory -------------------------------------------------------
    (ME.REGULATORY_ACTION,
     _any(r"fin\w+", r"sanction\w*", r"charg\w+", r"su\w*ed", r"sues",
          r"investigat\w+", r"open\w+", r"approv\w+", r"block\w+",
          r"reject\w+", r"clear\w+", r"rul\w+", r"order\w+", r"issu\w+",
          r"settl\w+", _SAY),
     _any(r"\bregulators?\b", r"\bantitrust\b", r"\binvestigations?\b",
          r"\bconsent decree\b", r"\bsubpoenas?\b", r"\binjunctions?\b",
          r"\bfines?\b", r"\bpenalt\w+\b", r"\blawsuits?\b",
          r"\b(?:sec|ftc|doj|cma|european commission)\b",
          r"\bregulatory (?:approval|action|review|clearance)\b",
          r"\bcompliance order\b")),
    # --- customers and suppliers -----------------------------------------
    #
    # OBJECT BEFORE ACTION, and that is load-bearing. Without the ordering
    # rule these two families fire on any sentence where an executive is
    # quoted saying the word "customer": the real corpus produced
    # "'...ensuring every customer can turn tokens into business results,'
    # said Satya Nadella" as a CUSTOMER_COMMENT. The customer has to be the
    # one doing the speaking, switching or churning — otherwise this is the
    # company talking about its customers, which is a different claim with a
    # different reliability.
    (ME.CUSTOMER_COMMENT,
     _any(r"said", r"says", r"report\w+", r"complain\w+", r"switch\w+",
          r"churn\w+", r"cancel\w+", r"renew\w+", r"ad\w*opted",
          r"chose", r"select\w+", r"sign\w+"),
     _any(r"\bcustomers?\b", r"\bclients?\b", r"\bmerchants?\b",
          r"\bsubscribers?\b", r"\busers?\b", r"\baccounts?\b"),
     "object_first"),
    (ME.SUPPLIER_COMMENT,
     _any(r"said", r"says", r"report\w+", r"warn\w+", r"not\w*ed",
          r"rais\w+", r"cut", r"delay\w+", r"halt\w+", r"resum\w+"),
     _any(r"\bsuppliers?\b", r"\bvendors?\b", r"\bfoundr\w+\b",
          r"\bsupply chain\b", r"\bcomponent (?:supply|shortage)\b",
          r"\blead times?\b"),
     "object_first"),
    # --- inventory --------------------------------------------------------
    (ME.INVENTORY_CHANGE,
     _any(r"build\w*", r"built", r"draw\w*(?:n|ing)? down", r"rais\w+",
          r"increas\w+", r"reduc\w+", r"cut", r"clear\w+", r"destock\w*",
          r"restock\w*", r"ros\w*e?", r"fell", _SAY),
     _any(r"\binventor\w+\b", r"\bstock levels?\b", r"\bdestocking\b",
          r"\brestocking\b", r"\bchannel inventory\b", r"\bbacklog\b",
          r"\border book\b")),
    # --- patents ----------------------------------------------------------
    (ME.PATENT_ACTIVITY,
     _any(r"grant\w+", r"issu\w+", r"fil\w+", r"award\w+", r"appl\w+",
          r"invalidat\w+", r"uph\w+eld", _SAY),
     _any(r"\bpatents?\b", r"\bpatent (?:application|grant|filing|"
          r"portfolio)\b", r"\bintellectual property (?:suit|claim)\b")),
    # --- macro ------------------------------------------------------------
    (ME.MACRO_RELEASE,
     _any(r"ros\w*e?", r"fell", r"increas\w+", r"declin\w+", r"held",
          r"cut", r"rais\w+", r"came in", r"print\w+", r"was", r"were",
          _SAY),
     _any(r"\bconsumer price index\b", r"\bcpi\b", r"\bppi\b",
          r"\bunemployment rate\b", r"\bnonfarm payrolls\b",
          r"\bfederal funds rate\b", r"\bgdp\b", r"\binterest rates?\b",
          r"\bindustrial production\b", r"\bretail sales\b")),
    # --- competitor, last: the most general family -----------------------
    (ME.COMPETITOR_ACTION,
     _any(r"launch\w*", r"cut", r"rais\w+", r"enter\w+", r"exit\w+",
          r"expand\w+", r"target\w+", r"undercut\w*", r"respond\w+", _SAY),
     _any(r"\bcompetitors?\b", r"\brivals?\b", r"\bcompeting\b",
          r"\bmarket share\b", r"\bhead[- ]to[- ]head\b")),
)

# Compiled once. Patterns are anchored on word boundaries so "ships" cannot
# match inside "relationships" and "won" cannot match inside "wonder".
# A family may add "object_first", which requires the object to precede the
# action — see the customer/supplier families for why.
_COMPILED = tuple(
    (family[0], re.compile(r"(?<!\w)" + family[1] + r"(?!\w)", re.I),
     re.compile(family[2], re.I),
     family[3] if len(family) > 3 else "")
    for family in _FAMILIES)


# --- standing states that borrow event vocabulary -------------------------
#
# Every one of these was taken from the real corpus. They are the sentences a
# loosened classifier turns into events, and they are why recall is bought by
# selecting better text rather than by lowering this bar.
_NON_EVENT = tuple(re.compile(p, re.I) for p in (
    # habitual / standing capability, not a dated occurrence
    r"\b(?:we|our company|the company) (?:partner|work|help|serve|support|"
    r"build|make|offer|provide)s? (?:with )?(?:world|leading|the best|"
    r"organizations|companies|customers|businesses)",
    r"\bpartners? with (?:world|industry)[- ]?leading\b",
    r"\bevery (?:day|week|month|year|six months)\b",
    r"\bhas (?:always|long) (?:been|offered|provided)\b",
    r"\bis (?:the|a) (?:leading|premier|trusted|preferred|world's)\b",
    r"\bwe (?:believe|think|know|are proud)\b",
    # solicitations to the reader
    r"\b(?:sign up|get started|start (?:free|your)|book a demo|"
    r"contact sales|try it|learn how|find out how)\b",
    # generic capability copy
    r"\bcan (?:help|enable|allow|empower)\b",
    r"\bdesigned to\b", r"\bbuilt to\b", r"\ballows? you to\b",
    r"\bhelps? (?:you|businesses|companies|teams)\b",
    # forward-looking-statement legalese
    r"\bthese forward-looking statements\b",
    r"\bactual results (?:may|could) differ\b",
    # CONDITIONALS AND HYPOTHETICALS. Something that would happen if
    # something else happened has not happened. Both of these are real
    # corpus sentences that classified: "Factors that could affect the
    # availability of financing include..." fired PRODUCT_LAUNCH, and "If
    # the going concern assumption is not appropriate ... then adjustments
    # would be necessary" fired EARNINGS_RESULT.
    # INTERROGATIVE AND SPECULATIVE HEADLINES. A question about whether
    # something will happen is not a record that it did, and an invitation to
    # speculate is not an observation. Measured: "Will Duolingo (DUOL) Beat
    # Estimates Again in Its Next Earnings Report?" fired EARNINGS_SURPRISE
    # on the word pair "Beat"/"Estimates" and opened the belief "Duolingo,
    # Inc. is seeing demand strengthen rather than plateau" -- a claim about
    # trading conditions, from a sentence that asserts nothing whatsoever.
    #
    # This is the Caterpillar price-move failure in a different costume: event
    # vocabulary present, event absent. Same treatment.
    # Narrowed after measurement. A first version also refused sentences
    # beginning "when", "what", "why" and "how", which reads like a headline
    # rule and is not one: the corpus contains "When adjusting for these
    # items, we exceeded expectations across revenue..." -- a real Microsoft
    # earnings statement that happens to open with a subordinate clause. Only
    # forms that cannot be assertions are refused.
    r"\?",
    r"^will\b", r"^is it\b",
    r"\bhere'?s why\b", r"\bis it time to\b", r"\bwhat to (?:expect|know)\b",
    r"^if\b", r"^should\b", r"^were\b", r"^in the event\b",
    r"\bfactors that (?:could|may|might)\b",
    r"\b(?:could|would|might|may) (?:be|have|affect|include|result|differ|"
    r"require|cause|need|become)\b",
    r"\bgoing concern\b", r"\bthere (?:can|is) no assurance\b",
    r"\bno assurance (?:that|can)\b", r"\bsubject to (?:risks|change)\b",
    r"\bif the .{0,40}(?:assumption|condition)\b",
    # a reconciliation instruction, not a result
    r"\bplease see (?:a|the) reconciliation\b",
    r"\bsee the appendix\b",
    # EARNINGS-CALL LOGISTICS. "Microsoft will provide forward-looking
    # guidance in connection with this quarterly earnings announcement on its
    # earnings conference call and webcast" is an invitation to a call, and
    # it was reaching beliefs as an earnings result.
    r"\bwill provide forward-looking guidance\b",
    r"\bconference call and webcast\b", r"\bwebcast (?:will|is)\b",
    # SHARE-PLAN AND VALUATION MECHANICS. Every one of these fired on real
    # filings. An option's exercise price is not a product price; a
    # Black-Scholes risk-free rate is not a macro release.
    r"\bexercise price of\b", r"\bshall not be less than\b",
    r"\bblack[- ]?scholes\b", r"\bfair value of (?:these|the|such) option",
    r"\brisk[- ]free interest rate\b", r"\bgrant date fair value\b",
    r"\bweighted[- ]average (?:exercise|grant)\b",
    # RISK DISCLOSURES. A statement of what risk means is not an event.
    r"\bis the risk that\b", r"\bmarket risk is\b", r"\bwill fluctuate\b",
    r"\bability to (?:raise|continue|obtain|meet|attract|retain)\b",
    r"\bare exposed to\b", r"\bis exposed to\b",
))


# A possessive determiner in front of the object means the COMPANY is talking
# about its customers, not that a customer spoke. A closing quote between the
# two spans means the verb belongs to the attribution, not to the object.
_POSSESSIVE = re.compile(r"\b(?:our|its|their|your|his|her)\s*$", re.I)
_CLOSING_QUOTE = re.compile(r"[”\"'’]")


def is_standing_state(sentence: str) -> bool:
    """True when event vocabulary is describing a permanent condition."""
    text = " ".join((sentence or "").split())
    return any(p.search(text) for p in _NON_EVENT)


def classify_sentence(sentence: str) -> Optional[str]:
    """The commercial event this ONE sentence evidences, or None.

    None rather than a default. A default type is a claim about what the
    sentence is, and getting it wrong points a real belief update at the wrong
    proposition — with a citation attached, so nobody catches it.
    """
    return _match(sentence)[0]


def explain(sentence: str) -> Tuple[Optional[str], str, str]:
    """(type, action span, object span) — the classifier showing its working.

    Used by the corpus harness and by the operator report, so a disputed
    classification can be argued about in terms of the two spans that produced
    it rather than in terms of a regex.
    """
    return _match(sentence)


def _match(sentence: str) -> Tuple[Optional[str], str, str]:
    text = " ".join((sentence or "").split())
    if not text or is_standing_state(text):
        return None, "", ""
    for etype, action, obj, order in _COMPILED:
        hit = _non_overlapping(action, obj, text, order)
        if hit is not None:
            return etype, hit[0], hit[1]
    return None, "", ""


def _non_overlapping(action: "re.Pattern", obj: "re.Pattern", text: str,
                     order: str = "") -> Optional[Tuple[str, str]]:
    """Require the ACTION and the OBJECT to be different spans of the text.

    One word satisfying both halves is not an event, it is a coincidence of
    vocabulary — and it fired twice on the real corpus. "Restructuring costs -
    divestiture of certain non-U.S. entities", a line item in a reconciliation
    table, matched the M&A family because `divest\\w+` and `\\bdivestitures?\\b`
    both landed on the single word "divestiture". "Shopify's VP of
    Partnerships believes AI will..." matched the partnership family the same
    way, on "Partnerships".

    Requiring two spans is what makes a family mean "somebody DID something TO
    something" rather than "this sentence mentions a noun".
    """
    for a in action.finditer(text):
        for o in obj.finditer(text):
            if order == "object_first":
                # "customers switched", not "switched ... customers". The
                # window keeps the subject next to its verb rather than
                # pairing a noun in one clause with a verb in another.
                if not (o.end() <= a.start() and a.start() - o.end() <= 40):
                    continue
                if _POSSESSIVE.search(text[max(0, o.start() - 14):o.start()]):
                    continue          # "our customers" is the company talking
                if _CLOSING_QUOTE.search(text[o.end():a.start()]):
                    continue          # '..., " said X' is an attribution
                return a.group(0), o.group(0)
            if a.end() <= o.start() or o.end() <= a.start():
                return a.group(0), o.group(0)
    return None


def has_quantity(sentence: str) -> bool:
    """A figure, sum or duration — a specific transaction, not a posture."""
    return re.search(_QUANT, sentence or "", re.I) is not None
