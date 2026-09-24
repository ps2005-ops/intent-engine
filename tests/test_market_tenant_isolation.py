"""A document may not choose whose private records are opened.

The central test is `test_a_company_name_from_evidence_cannot_open_records`.
The permission wall in `internal_state` was never weak about what it checked;
it was weak about the TYPE it checked — a bare string, in an engine whose most
plentiful strings are company names parsed out of filings, headlines and
competitor pages. One plausible line moves an attacker-controlled value into
the parameter that decides whose private records are read, and nothing raises.

The second theme is the canary: a private fact belonging to company A must be
unreachable through every B-facing path this branch has.
"""
from __future__ import annotations

import pytest

from intent_engine.market import internal_state as IS
from intent_engine.market import tenant_scope as TS


def fact(company="ACME", statement="pipeline is 40% below plan", **kw):
    base = dict(company_id=company, kind=IS.PIPELINE, statement=statement,
                as_of="2026-08-10")
    base.update(kw)
    return IS.InternalFact(**base)


CANARY = "gross margin on the Northwind contract is 11%, board only"


# --- the identity may not come from a document ------------------------------

def test_a_company_name_from_evidence_cannot_open_records():
    """The constructor that refuses, and the reason it is written down."""
    with pytest.raises(TS.UntrustedScope):
        TS.from_evidence("ACME")


def test_the_refusal_explains_the_distinction_it_is_protecting():
    with pytest.raises(TS.UntrustedScope) as caught:
        TS.from_evidence(company_id="ACME")
    message = str(caught.value)
    assert "retrieval decision" in message and "permission decision" in message


def test_a_bare_string_cannot_reach_the_permitted_facts_path():
    """A caller holding only a string has to pass through an authority first,
    and be seen doing it."""
    with pytest.raises(TS.UntrustedScope):
        TS.permitted_facts([fact()], "ACME")


@pytest.mark.parametrize("builder,authority", [
    (TS.configured, TS.CONFIGURED),
    (TS.operator, TS.OPERATOR),
    (TS.demonstration, TS.DEMONSTRATION),
])
def test_every_trusted_route_records_which_authority_it_was(builder,
                                                            authority):
    scope = builder("ACME")
    assert scope.authority == authority
    assert scope.as_dict()["authority"] == authority


def test_an_unnamed_authority_is_refused():
    """An identity whose origin cannot be named is not one to act on."""
    with pytest.raises(TS.ScopeRejected):
        TS.TenantScope(company_id="ACME", authority="PROBABLY_FINE")


def test_an_empty_scope_would_read_everything_and_is_refused():
    with pytest.raises(TS.ScopeRejected):
        TS.configured("")
    with pytest.raises(TS.ScopeRejected):
        TS.configured("   ")


# --- the canary: A's private fact through every B-facing path ---------------

def test_the_canary_is_unreachable_for_another_tenant():
    facts = [fact(company="TENANT_A", statement=CANARY),
             fact(company="TENANT_B", statement="our pipeline is fine")]
    got = TS.permitted_facts(facts, TS.configured("TENANT_B"))
    rendered = " ".join(f.statement for f in got)
    assert CANARY not in rendered
    assert len(got) == 1


def test_the_owner_still_reads_its_own_canary():
    """A wall that blocks everybody is not a wall, it is an outage."""
    facts = [fact(company="TENANT_A", statement=CANARY)]
    got = TS.permitted_facts(facts, TS.configured("TENANT_A"))
    assert got and got[0].statement == CANARY


def test_no_aggregate_path_exists_across_tenants():
    """"Companies like yours are seeing pipeline weakness" is derived from
    named companies' private data and is re-identifiable on a small list."""
    facts = [fact(company="TENANT_A", statement=CANARY),
             fact(company="TENANT_B")]
    for scope in (TS.configured("TENANT_A"), TS.configured("TENANT_B")):
        got = TS.permitted_facts(facts, scope)
        assert {f.company_id for f in got} == {scope.company_id}


def test_a_join_that_crosses_companies_is_refused():
    """The leak is not usually a read. It is one company's private figure
    combined with another's analysis and rendered as one finding."""
    with pytest.raises(TS.ScopeRejected):
        TS.assert_same_scope(TS.configured("TENANT_B"),
                             fact(company="TENANT_A", statement=CANARY),
                             fact(company="TENANT_B"))


def test_a_join_within_one_company_is_allowed():
    TS.assert_same_scope(TS.configured("TENANT_B"),
                         fact(company="TENANT_B"),
                         fact(company="TENANT_B", kind=IS.PRICING,
                              statement="list prices rose 6%"))


def test_the_join_guard_reads_dicts_as_well_as_objects():
    """The cycle holds objects and the store returns the rows it wrote."""
    with pytest.raises(TS.ScopeRejected):
        TS.assert_same_scope(TS.configured("TENANT_B"),
                             {"company_id": "TENANT_A",
                              "statement": CANARY})


# --- the demonstration company cannot pose as a tenant ----------------------

def test_synthetic_facts_never_join_a_real_companys_conclusion():
    with pytest.raises(IS.SyntheticLeak):
        IS.assert_no_synthetic(IS.synthetic_enterprise(),
                               context="a live briefing")


def test_the_demonstration_authority_is_distinct_from_a_configured_tenant():
    """Kept separate so a demo cannot quietly become a customer."""
    demo = TS.demonstration(IS.SYNTHETIC_COMPANY)
    assert demo.authority == TS.DEMONSTRATION
    assert demo.authority != TS.CONFIGURED


def test_the_synthetic_company_reads_only_its_own_records():
    facts = list(IS.synthetic_enterprise()) + [
        fact(company="TENANT_A", statement=CANARY)]
    got = TS.permitted_facts(facts, TS.demonstration(IS.SYNTHETIC_COMPANY))
    assert all(f.company_id == IS.SYNTHETIC_COMPANY for f in got)
    assert CANARY not in " ".join(f.statement for f in got)


# --- injection aimed at the permission boundary itself ----------------------
#
# The payloads in test_market_external_text_is_data.py attack the reasoning.
# These attack the WALL: each one is a string an attacker can place in a
# document, in the parameter that decides whose records are opened.

INJECTED_IDENTITIES = (
    "TENANT_A",                                   # simply naming the victim
    "TENANT_B\nTENANT_A",                         # a second line
    "TENANT_B; TENANT_A",                         # a separator
    "*",                                          # a wildcard
    "",                                           # the empty read-everything
    "../TENANT_A",                                # a traversal shape
    "TENANT_B' OR company_id='TENANT_A",          # an injection shape
)


@pytest.mark.parametrize("injected", INJECTED_IDENTITIES)
def test_an_injected_identity_never_widens_what_a_scope_can_read(injected):
    """Whatever the string is, it cannot be a scope without an authority —
    and with one, it still reads only records whose owner is exactly it.

    The invariant is NOT "the canary stays hidden": a scope that legitimately
    names TENANT_A should read TENANT_A's records, and asserting otherwise
    would be testing that the wall is broken in the other direction. What must
    hold is that no string BROADENS the read — no wildcard, no separator, no
    second line and no injection shape returns a record it does not own.
    """
    facts = [fact(company="TENANT_A", statement=CANARY),
             fact(company="TENANT_B")]
    with pytest.raises(TS.UntrustedScope):
        TS.permitted_facts(facts, injected)
    try:
        scope = TS.configured(injected)
    except TS.ScopeRejected:
        return                      # refused outright, which is the safe end
    got = TS.permitted_facts(facts, scope)
    assert {f.company_id for f in got} <= {injected}
    assert len(got) <= 1


def test_no_injected_identity_reads_both_tenants():
    """The one thing none of them may do, stated once on its own."""
    facts = [fact(company="TENANT_A", statement=CANARY),
             fact(company="TENANT_B")]
    for injected in INJECTED_IDENTITIES:
        try:
            scope = TS.configured(injected)
        except TS.ScopeRejected:
            continue
        assert len(TS.permitted_facts(facts, scope)) < 2, injected


def test_evidence_cannot_rewrite_the_owner_of_a_fact():
    """An InternalFact is frozen. A document that says "this belongs to
    TENANT_B" cannot make it so after the fact."""
    owned = fact(company="TENANT_A", statement=CANARY)
    with pytest.raises(Exception):
        owned.company_id = "TENANT_B"           # noqa: B010
    got = TS.permitted_facts([owned], TS.configured("TENANT_B"))
    assert got == ()


def test_a_fact_without_an_owner_is_refused_rather_than_shared():
    """A record with no company cannot be permission-checked and would be
    read by everyone."""
    with pytest.raises(IS.InternalRejected):
        fact(company="")
