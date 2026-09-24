"""A labelled demand corpus, written BEFORE the detector that reads it.

WHY THIS FILE EXISTS AT ALL
---------------------------
The obvious way to finish demand extraction is to add "orders", "bookings"
and "shipments" to a pattern list. That produces a detector justified by the
sentences its author happened to imagine, and this project has already
shipped one of those: a relevance score that measured the label because the
system had supplied it.

So the labels come first and the rules come second. Every row here is a
sentence a real filing could contain, with the answer it must produce and the
REASON — because "no" is not one behaviour. A sentence about a company buying
equipment and a sentence about a court order are both refusals, and a
detector that gets them right for the wrong reason will get the next one
wrong.

THE CENTRAL DISTINCTION
-----------------------
"We placed orders for new manufacturing equipment" and "Customer orders
increased 18%" share a noun and share nothing else. The first is the company
as BUYER — procurement, a cost — and the second is the company as SELLER,
which is demand. A keyword list cannot tell them apart, and getting this one
backwards would put capex into the demand chain and then into a thesis about
customer demand strengthening.

WHAT EACH FIELD MEANS
---------------------
`state`      the demand state, or None when the sentence must be refused
`role`       the economic role the sentence assigns the SUBJECT company
`direction`  only when the text supports one; never inferred from sentiment
`standing`   OBSERVATION / EXPECTATION / RISK — kept apart on purpose
`reason`     for refusals, the reason code the pipeline must produce
"""
from __future__ import annotations

from typing import NamedTuple, Optional, Tuple

# --- economic roles ---------------------------------------------------------
SELLER = "SELLER"
BUYER = "BUYER"
SUPPLIER = "SUPPLIER"
COMPETITOR = "COMPETITOR"
MARKET = "MARKET"
UNKNOWN_ROLE = "UNKNOWN"

# --- what kind of claim the sentence makes ----------------------------------
OBSERVATION = "OBSERVATION"
EXPECTATION = "EXPECTATION"
RISK = "RISK"

# --- refusal reasons --------------------------------------------------------
WRONG_ROLE = "WRONG_ROLE"
WRONG_SUBJECT = "WRONG_SUBJECT"
SPECULATIVE = "SPECULATIVE"
GENERIC_LANGUAGE = "GENERIC_LANGUAGE"
NO_COMMERCIAL_OBJECT = "NO_COMMERCIAL_OBJECT"
NO_DIRECTION = "NO_DIRECTION"


class Row(NamedTuple):
    text: str
    state: Optional[str]
    role: str = UNKNOWN_ROLE
    direction: str = ""
    standing: str = OBSERVATION
    reason: str = ""
    note: str = ""


SUBJECT = "caterpillar"
ALIASES: Tuple[str, ...] = ("Caterpillar", "Caterpillar Inc", "CAT")


# --- TRUE POSITIVES ---------------------------------------------------------
# The company as SELLER, a demand object, and a direction the text states.
POSITIVES: Tuple[Row, ...] = (
    Row("Customer orders increased 18% year over year.",
        "ORDERS", SELLER, "UP"),
    Row("New orders rose to $12.4 billion in the second quarter.",
        "ORDERS", SELLER, "UP"),
    Row("Order intake declined 6% compared with the prior year.",
        "ORDERS", SELLER, "DOWN"),
    Row("Net new bookings grew 22% year over year.",
        "BOOKINGS", SELLER, "UP"),
    Row("Bookings fell to $3.1 billion from $3.6 billion.",
        "BOOKINGS", SELLER, "DOWN"),
    Row("Order backlog was $37.5 billion, an increase of $6.4 billion.",
        "BACKLOG", SELLER, "UP"),
    Row("Backlog increased to a record $37.5 billion.",
        "BACKLOG", SELLER, "UP"),
    Row("Remaining performance obligations were $12,300 million at quarter "
        "end.", "COMMITTED_DEMAND", SELLER, "FLAT"),
    Row("Contract liabilities were $7,280 million.",
        "COMMITTED_DEMAND", SELLER, "FLAT"),
    Row("Unsatisfied performance obligations totaled $44.1 billion.",
        "COMMITTED_DEMAND", SELLER, "FLAT"),
    Row("Units shipped increased 12% in the quarter.",
        "SHIPMENTS", SELLER, "UP"),
    Row("Deliveries to customers declined due to logistics constraints.",
        "SHIPMENTS", SELLER, "DOWN"),
    Row("Order cancellations rose to $410 million.",
        "CANCELLATIONS", SELLER, "UP"),
    # FLAT, not UP, and the label was wrong first. The sentence states a
    # MAGNITUDE of cancellations, not a change in them: nothing here says
    # cancellations rose. Reading UP off the fact that a cancellation
    # happened is taking the event's sign from its name, which is the same
    # move as reading "demand" off the word "demand".
    Row("Customers cancelled $180 million of previously booked orders.",
        "CANCELLATIONS", SELLER, "FLAT"),
    Row("Qualified pipeline grew 30% over the prior quarter.",
        "CUSTOMER_INTENT", SELLER, "UP"),
    Row("Sales and revenues for the second quarter were $20.5 billion, a 24% "
        "increase.", "REVENUE", SELLER, "UP"),
)


# --- THE ROLE TRAP ----------------------------------------------------------
# Same nouns, company on the other side of the transaction. Every one of
# these is a cost or a supply fact, and every one would become "demand" under
# a keyword rule.
ROLE_TRAPS: Tuple[Row, ...] = (
    Row("We placed orders for new manufacturing equipment.",
        None, BUYER, reason=WRONG_ROLE,
        note="company as buyer: capex, not customer demand"),
    Row("Purchase orders issued by the company totaled $2.1 billion.",
        None, BUYER, reason=WRONG_ROLE),
    Row("Caterpillar ordered additional machine tools for its Texas plant.",
        None, BUYER, reason=WRONG_ROLE),
    Row("Our orders to suppliers were reduced in response to lower "
        "production.", None, BUYER, reason=WRONG_ROLE),
    Row("Supplier shipments to our plants were delayed by six weeks.",
        None, SUPPLIER, reason=WRONG_ROLE,
        note="inbound, not outbound: a supply constraint"),
    Row("We cancelled a supplier contract for hydraulic components.",
        None, BUYER, reason=WRONG_ROLE),
)


# --- THE SUBJECT TRAP -------------------------------------------------------
# A demand fact that belongs to somebody else. Nearest governing subject
# decides ownership; the sentence naming our company does not make it ours.
SUBJECT_TRAPS: Tuple[Row, ...] = (
    Row("Komatsu reported strong bookings growth in its mining segment.",
        None, COMPETITOR, reason=WRONG_SUBJECT),
    Row("Deere's order backlog fell 12% while Caterpillar's rose.",
        None, COMPETITOR, reason=WRONG_SUBJECT,
        note="both companies named; the leading claim is the rival's"),
    Row("Industry-wide equipment orders declined across North America.",
        None, MARKET, reason=WRONG_SUBJECT,
        note="the market's demand, not this company's pipeline"),
    Row("End-market demand for construction equipment remains soft.",
        None, MARKET, reason=WRONG_SUBJECT),
)


# --- SPECULATION ------------------------------------------------------------
# An expectation is not an observation, and a risk is not a decline. Both
# must survive as their own standing rather than being admitted or discarded.
SPECULATION: Tuple[Row, ...] = (
    Row("We expect bookings to improve in the second half.",
        None, SELLER, "UP", EXPECTATION, reason=SPECULATIVE),
    Row("Orders could decline if tariffs persist.",
        None, SELLER, "DOWN", RISK, reason=SPECULATIVE),
    Row("Management anticipates backlog will normalize next year.",
        None, SELLER, "DOWN", EXPECTATION, reason=SPECULATIVE),
    Row("Customers may cancel orders if lead times extend further.",
        None, SELLER, "UP", RISK, reason=SPECULATIVE),
)


# --- HOMONYMS ---------------------------------------------------------------
# The words are the same and the domain is not. These are the sentences a
# keyword list is guaranteed to get wrong.
HOMONYMS: Tuple[Row, ...] = (
    Row("The court order requires the company to disclose the settlement.",
        None, reason=NO_COMMERCIAL_OBJECT),
    Row("An executive order imposed new tariffs on imported steel.",
        None, reason=NO_COMMERCIAL_OBJECT),
    Row("The effect is an order of magnitude smaller than expected.",
        None, reason=NO_COMMERCIAL_OBJECT),
    Row("In order to reduce costs, the company consolidated two plants.",
        None, reason=NO_COMMERCIAL_OBJECT),
    Row("The engineering team reduced its ticket backlog by 40%.",
        None, reason=NO_COMMERCIAL_OBJECT,
        note="software ticket backlog is not committed demand"),
    Row("The court backlog delayed the ruling by two years.",
        None, reason=NO_COMMERCIAL_OBJECT),
    Row("We booked a $200 million restructuring charge.",
        None, reason=NO_COMMERCIAL_OBJECT,
        note="'booked' as accounting recognition, not a customer booking"),
)


# --- GENERIC MARKETING ------------------------------------------------------
# Commercially flavoured language carrying no observable quantity or state.
# Admitting these is how a dossier fills with sentiment.
GENERIC: Tuple[Row, ...] = (
    Row("Customers love the new excavator line.",
        None, SELLER, reason=GENERIC_LANGUAGE),
    Row("We are seeing exciting demand across the portfolio.",
        None, SELLER, reason=GENERIC_LANGUAGE),
    Row("Strong interest from customers continues to build.",
        None, SELLER, reason=GENERIC_LANGUAGE),
    Row("Demand remains healthy.",
        None, SELLER, reason=GENERIC_LANGUAGE,
        note="no stage, no quantity, no period"),
)


# --- CONTRADICTION SHAPES ---------------------------------------------------
# Pairs that must NOT collapse into one demand direction. These are the
# sentences the whole chain exists to keep apart: a rising backlog beside
# falling bookings is protected near-term revenue and deteriorating forward
# demand, which is a different statement from "demand is strong".
CONTRADICTIONS: Tuple[Tuple[Row, Row], ...] = (
    (Row("Bookings declined 9% year over year.", "BOOKINGS", SELLER, "DOWN"),
     Row("Backlog increased to a record $37.5 billion.",
         "BACKLOG", SELLER, "UP")),
    (Row("New orders grew 14% in the quarter.", "ORDERS", SELLER, "UP"),
     Row("Units shipped fell 5% on component shortages.",
         "SHIPMENTS", SELLER, "DOWN")),
    (Row("Backlog rose 8% sequentially.", "BACKLOG", SELLER, "UP"),
     Row("Order cancellations rose to $410 million.",
         "CANCELLATIONS", SELLER, "UP")),
)


#: Everything that must be REFUSED, with the reason each refusal must give.
NEGATIVES: Tuple[Row, ...] = (
    ROLE_TRAPS + SUBJECT_TRAPS + SPECULATION + HOMONYMS + GENERIC)

#: Everything, for a single precision/recall sweep.
ALL_ROWS: Tuple[Row, ...] = POSITIVES + NEGATIVES


def score(predict) -> dict:
    """Precision and recall of `predict` over the whole labelled corpus.

    `predict(text)` returns the demand state or None. Both halves are
    reported because a detector that refuses everything scores perfect
    precision, and one that accepts everything scores perfect recall.
    """
    tp = fp = fn = tn = 0
    wrong_state = []
    false_positives = []
    misses = []
    for row in ALL_ROWS:
        got = predict(row.text)
        if row.state is None:
            if got is None:
                tn += 1
            else:
                fp += 1
                false_positives.append((row.text, got, row.reason))
        else:
            if got == row.state:
                tp += 1
            elif got is None:
                fn += 1
                misses.append((row.text, row.state))
            else:
                fp += 1
                wrong_state.append((row.text, row.state, got))
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    return {
        "true_positives": tp, "false_positives": fp,
        "false_negatives": fn, "true_negatives": tn,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "wrong_state": wrong_state,
        "false_positive_examples": false_positives,
        "missed": misses,
    }
