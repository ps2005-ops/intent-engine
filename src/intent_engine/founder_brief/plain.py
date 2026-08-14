"""Every state this product holds, said the way an executive says it.

WHY A MODULE AND NOT A DICTIONARY IN EACH RENDERER
--------------------------------------------------
`causal_state=PANEL_UNAVAILABLE` on a customer screen is not terse, it is
untranslated. §17 requires that no enum, no code vocabulary and no pipeline
telemetry reaches a reader -- and the way that requirement fails in practice
is that each surface grows its own half-complete translation table, so the
X-Ray says one thing and the presentation says another about the same state.

One table. Every surface asks it. A state this table has never heard of
comes back as its own words rather than as an invented meaning, because
inventing a friendly sentence for an unrecognised state is how a surface
starts telling a reader something the engine never said.
"""
from __future__ import annotations

UNRECOGNISED = ""

#: The standing of the reading -- what the evidence entitles the product to
#: say. This is the guardrail from `decision_synthesis`, in English.
STANDING = {
    "SUPPORTED": (
        "Well supported",
        "The engine holds positions on this company and was able to resolve "
        "the causal question behind them from the public record."),
    "BOUNDED": (
        "Supported in direction, not in size",
        "The engine holds positions on this company, but the causal question "
        "behind them could not be answered from the public record -- so the "
        "direction is better founded than the magnitude."),
    "UNMEASURABLE": (
        "Not yet readable",
        "No evidence has been published for this company, so there is "
        "nothing for a reading to rest on."),
    "REFUSED": (
        "Withheld",
        "The published snapshot was not in a state this side will read, so no "
        "reading is put forward."),
}

#: What happened to the causal question. The refusals are the interesting
#: ones: each names a different missing thing, and collapsing them to "no
#: result" would send someone to fix the wrong layer.
CAUSAL = {
    "CAUSAL_ESTIMATED":
        "We asked the causal question and could answer it from the public "
        "record.",
    "CAUSAL_UNMEASURABLE":
        "We asked the causal question and cannot isolate the effect: the "
        "public record carries no comparable group observed over the same "
        "window. That is a limit of the available data, not a finding that "
        "the effect is absent.",
    "CAUSAL_NO_QUESTION":
        "The causal router ran and raised no question for this company in "
        "this cycle.",
    "CAUSAL_NOT_RUN":
        "No causal question was asked for this company in this cycle.",
}

#: Whether the economy reaches this company, and how.
ECONOMIC = {
    "ECONOMIC_STATE_AVAILABLE":
        "Measured economic conditions reach this business through an "
        "exposure its own model establishes.",
    "ECONOMIC_STATE_NO_RELEVANT_EXPOSURE":
        "The economy is measured, and none of it reaches this business "
        "through an exposure its evidence or its model establishes. That is "
        "a finding, not a gap.",
    "ECONOMIC_STATE_UNMEASURABLE":
        "Economic conditions were published for this company and could not "
        "be read.",
    "ECONOMIC_STATE_NOT_RUN":
        "The economic layer did not run for this company in this cycle.",
}

#: The operating posture the engine tracks.
HIDDEN = {
    "TRACKED_NO_IDENTIFIED_STATE":
        "We track this company's operating posture and cannot yet call it: "
        "the evidence has not moved it away from the starting assumption.",
    "HIDDEN_STATE_NOT_RUN":
        "Operating posture was not assessed in this cycle.",
    "HIDDEN_STATE_NONE_TRACKED":
        "No operating posture is tracked for this company.",
}

#: The decision in front of management, as a heading.
ARCHETYPE = {
    "PRICING": "Pricing",
    "CAPACITY": "Capacity",
    "PRODUCTIZATION": "Product",
    "MARKET_ENTRY": "Market entry",
    "CUSTOMER_SEGMENT": "Customer mix",
    "RETENTION": "Retention",
    "CAPITAL_ALLOCATION": "Capital allocation",
    "SALES_MOTION": "Sales motion",
    "SUPPLY_CHAIN": "Supply chain",
    "COST_STRUCTURE": "Cost structure",
    "M&A": "Acquisitions",
    "REGULATORY_RESPONSE": "Regulatory response",
    "COMPETITIVE_RESPONSE": "Competitive response",
    "INVENTORY": "Inventory",
    "R&D_ROADMAP": "Development roadmap",
    "UNKNOWN": "Not selected",
}

#: The market/founder crossing.
CROSSING = {
    "MARKET_AND_FOUNDER":
        "Market intelligence and this analysis both cover this company.",
    "FOUNDER_AVAILABLE_MARKET_UNAVAILABLE":
        "This analysis covers the company; the market engine does not "
        "currently publish it, so the market half of the read is absent.",
    "MARKET_AVAILABLE_FOUNDER_UNAVAILABLE":
        "The market engine covers this company; no analysis has been run "
        "here yet.",
    "NEITHER": "Neither side covers this company yet.",
}

_TABLES = (STANDING, CAUSAL, ECONOMIC, HIDDEN, ARCHETYPE, CROSSING)


def say(state: str, table: dict, *, default: str = "") -> str:
    """One state, in English. An unrecognised state keeps its own words.

    Deliberately NOT a friendly guess: a state this build has never seen is
    information -- probably that a producer moved ahead of this surface --
    and the honest rendering of it is the token itself, softened only in
    punctuation. See `failure-pages: suppress only when understood`.
    """
    value = table.get(str(state or ""))
    if isinstance(value, tuple):
        value = value[1]
    if value:
        return value
    if default:
        return default
    token = str(state or "").strip()
    return (f"The engine reported a state this screen does not have wording "
            f"for yet: {token}." if token else "")


def label(state: str) -> str:
    """The short label for a standing -- for a chip, not a sentence."""
    row = STANDING.get(str(state or ""))
    return row[0] if row else (str(state or "").replace("_", " ").capitalize())


def enum_free(text: str) -> bool:
    """Would this string put a raw enum in front of a reader?

    Used by the tests that pin §17. An ALL_CAPS_TOKEN with an underscore is
    the shape that has actually reached a page here.
    """
    for word in str(text or "").replace("(", " ").replace(")", " ").split():
        bare = word.strip(".,:;\"'")
        if "_" in bare and bare.replace("_", "").isalpha() and bare.isupper():
            return False
    return True


def humanise(text: str) -> str:
    """Last-resort softening of a token that reached a renderer anyway."""
    return str(text or "").replace("_", " ").lower()


def _get(decision, name, default=None):
    """Read a field off a FounderDecision or off its serialised dict."""
    if isinstance(decision, dict):
        return decision.get(name, default)
    return getattr(decision, name, default)


def key_risk(decision) -> str:
    """The one thing most likely to make this wrong. One source, five views.

    The X-Ray, the full analysis, the deck and the CEO answer all need this
    and each had its own fallback chain -- so the screen showed the
    adversarial kill switch while "what is the biggest risk?" answered "no
    risk has been recorded", for the same company on the same data. Two
    answers to one question is the failure the single-decision object exists
    to prevent, and the fix is that they ask here.

    Order: the guardrail on acting under an unresolved question, then the
    branch the commitment has to survive, then the falsifier. Empty only
    when the decision genuinely carries none of the three.
    """
    rails = tuple(_get(decision, "guardrails", ()) or ())
    if rails:
        return str(rails[0])
    for scenario in (_get(decision, "scenarios", ()) or ()):
        row = scenario if isinstance(scenario, dict) else {}
        if row.get("name") == "ADVERSARIAL":
            second = row.get("second_order", "")
            stop = row.get("kill_switch", "")
            if second:
                return (f"{second}. {stop}" if stop else str(second))
    falsifier = str(_get(decision, "falsifier", "") or "")
    return falsifier


def prose(text: str) -> str:
    """Source punctuation, as a reader expects to see it.

    The economics and vocabulary tables are written in this repository's
    comment style, which uses `--` for an aside. Correct in a source file,
    wrong on a customer screen -- it renders as two hyphens mid-sentence.
    Applied at the render boundary so every surface gets it once, rather
    than each table being rewritten and the next one added forgetting.
    """
    return str(text or "").replace(" -- ", " — ")


def escape(text) -> str:
    """Escape for HTML and fix source punctuation, in that order.

    Both renderers bind their `_e` to this, so a string cannot reach a page
    through one of them without passing both rules.
    """
    from html import escape as _html_escape
    return _html_escape(prose(str(text if text is not None else "")))
