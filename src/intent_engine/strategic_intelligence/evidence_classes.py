"""What a source class is worth, in one place.

The tiers below were five separate `_INDEPENDENT` tuples — in `model.py`,
`insights.py`, `quality.py`, `render.py` and `reasoning.py` — which is how the
defect below survived: correcting one of them corrected nothing.

THE DEFECT THIS EXISTS TO FIX. `edgar.py` files a 10-K as
`source_class="investor_material"`. That class is EXTERNAL but not INDEPENDENT,
so a run that retrieved a company's annual report reported "every source here
is published by the company itself" and withheld every option. Measured live on
2026-08-05 (Datadog, preview commit 16dc4b8): the analysis quoted the 10-K and
still concluded it was not safe to act on.

The correction is NOT to call a filing independent. It is management-authored,
and a company describing its own strategy in Item 1 is still the company
talking. What a filing has that marketing does not is ACCOUNTABILITY: it is
made under securities law, a material misstatement carries legal exposure, and
the financial and risk sections follow a required structure. So the model needs
three tiers, not two:

    INDEPENDENT   someone outside the company said it
    ACCOUNTABLE   the company said it, under legal obligation to be accurate
    ASSERTED      the company said it, in material it controls entirely

A filing therefore raises what a reading can support without ever standing in
for outside corroboration. One filing can justify a BOUNDED interpretation of
what the company reports about itself; it cannot settle whether customers
agree, whether competitors will respond, or whether management is right.
"""
from __future__ import annotations

# Genuinely outside the company's own publishing.
INDEPENDENT_CLASSES = ("independent_reporting", "customer_voice", "competitor")

# Management-authored, but made under legal accountability. A regulatory filing
# is the whole point of this tier: `investor_material` is what `edgar.py`
# assigns to a 10-K/10-Q/8-K and to an earnings-release exhibit.
ACCOUNTABLE_CLASSES = ("investor_material",)

# Management-authored, in material the company controls entirely.
ASSERTED_CLASSES = ("company_owned", "executive_statement")

# Anything not written by the company about itself. Kept as the union so the
# existing "is there anything beyond the website" question keeps its meaning.
EXTERNAL_CLASSES = (
    "executive_statement", "investor_material",
    "customer_voice", "competitor", "independent_reporting",
)


def has_independent(coverage) -> bool:
    """True when something outside the company reported on it."""
    return any(c in coverage for c in INDEPENDENT_CLASSES)


def has_accountable(coverage) -> bool:
    """True when a source carries legal accountability (a filing)."""
    return any(c in coverage for c in ACCOUNTABLE_CLASSES)


def has_external(coverage) -> bool:
    """True when anything beyond the company's own website is present."""
    return any(c in coverage for c in EXTERNAL_CLASSES)


def evidence_standing(coverage) -> str:
    """The strongest standing the evidence mixture supports.

    Returns one of `independent`, `accountable`, `asserted`, `none`. Callers
    use this to decide how far a reading may go — NOT whether to speak at all.
    """
    if has_independent(coverage):
        return "independent"
    if has_accountable(coverage):
        return "accountable"
    if any(c in coverage for c in ASSERTED_CLASSES):
        return "asserted"
    return "none"


def standing_limitation(coverage) -> str:
    """The honest one-line limit of this evidence mixture, or "" if none.

    Written to be read by a founder, so it says what is missing and what that
    costs rather than naming a class.
    """
    standing = evidence_standing(coverage)
    if standing == "independent":
        return ""
    if standing == "accountable":
        return ("the company's filings carry this, so it is stated under legal "
                "obligation rather than in marketing — but no outside account "
                "has tested whether it is working")
    if standing == "asserted":
        return ("every source here is published by the company itself, so "
                "nothing in this reading has been checked against an outside "
                "account of it")
    return ("the analysis rests only on the company's own website; a filing, "
            "an investor statement, a customer or an independent report would "
            "be needed to test any of it")
