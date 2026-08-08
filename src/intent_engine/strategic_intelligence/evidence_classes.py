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


#: Where a document is served from when it is a statutory filing rather than a
#: page about being a company that files. Accountability is a property of the
#: DOCUMENT, and this is the only signal that reliably carries it.
FILING_HOSTS = ("sec.gov", "sedarplus.ca", "sedar.com")


def is_regulatory_filing(url: str) -> bool:
    """True for a document served from a securities regulator's archive."""
    host = (url or "").lower()
    return any(h in host for h in FILING_HOSTS)


def has_accountable(coverage) -> bool:
    """True when the mixture claims legal accountability.

    CLASS ALONE IS NOT ENOUGH, and callers that can do better should pass
    `has_filing` to `evidence_standing` / `standing_limitation` instead.
    `discovery.py` assigns `investor_material` to any URL containing
    "investor", "shareholder", "/ir" or "earnings" — an ordinary
    investor-relations WEB PAGE — and `edgar.py` assigns the same class to a
    10-K. The two are indistinguishable here.

    Measured live on the deployed preview: Constellation Software, a TSX-only
    issuer with NO SEC filings in the run, was told "the company's filings
    carry this, so it is stated under legal obligation rather than in
    marketing". It has an investor-relations page; it had no filing. The
    product asserted accountability it had not obtained.
    """
    return any(c in coverage for c in ACCOUNTABLE_CLASSES)


def has_external(coverage) -> bool:
    """True when anything beyond the company's own website is present."""
    return any(c in coverage for c in EXTERNAL_CLASSES)


def evidence_standing(coverage, *, has_filing=None) -> str:
    """The strongest standing the evidence mixture supports.

    Returns one of `independent`, `accountable`, `asserted`, `none`. Callers
    use this to decide how far a reading may go — NOT whether to speak at all.

    `has_filing` is the authoritative answer to "was a statutory filing
    actually read". Pass it whenever the caller can see the source URLs; the
    class-based fallback exists only for callers that cannot.
    """
    if has_independent(coverage):
        return "independent"
    accountable = (has_accountable(coverage) if has_filing is None
                   else bool(has_filing))
    if accountable:
        return "accountable"
    # An investor-relations page that turned out NOT to be a filing is still
    # material the company published. Without this it fell through to "none",
    # whose line says the analysis "rests only on the company's own website" --
    # understating evidence the run did obtain, in the opposite direction to
    # the defect above but with the same cause: the class alone never said
    # whether a filing was read.
    if any(c in coverage for c in ASSERTED_CLASSES) or \
            (not accountable and has_accountable(coverage)):
        return "asserted"
    return "none"


def standing_limitation(coverage, *, has_filing=None) -> str:
    """The honest one-line limit of this evidence mixture, or "" if none.

    Written to be read by a founder, so it says what is missing and what that
    costs rather than naming a class. NOTHING here may describe evidence the
    run did not obtain: the limitation is the one line a reader uses to decide
    how far to trust everything above it, and a limitation that overstates the
    evidence is worse than no limitation at all.
    """
    standing = evidence_standing(coverage, has_filing=has_filing)
    if standing == "independent":
        return ""
    if standing == "accountable":
        return ("the company's filings carry this, so it is stated under legal "
                "obligation rather than in marketing — but no outside account "
                "has tested whether it is working")
    if standing == "asserted":
        # Deliberately does NOT mention filings. This is the branch a company
        # with an investor-relations page and no filing now lands in.
        return ("every source here is published by the company itself, so "
                "nothing in this reading has been checked against an outside "
                "account of it")
    return ("the analysis rests only on the company's own website; a filing, "
            "an investor statement, a customer or an independent report would "
            "be needed to test any of it")
