"""The four capabilities the 50-company gauntlet measured as absent or wrong.

    Q&A absence          the whole reading REFUSED off another bundle's coverage
    adversary  0.0       a complete L0/L1/L2 engine whose output no surface saw
    impossible 0.0       no producer existed at all
    competition 6.8      filing headings and measures printed as rivals

Each is pinned at the seam that was actually broken, not at the surface where
it showed. Where the defect was a repair that shipped INERT, the test asserts
the production call site, because that is what was wrong both times.
"""
import re

import pytest

from intent_engine.demo_dossier import (assemble, market_unavailable,
                                        read_founder_snapshot)
from intent_engine.executive import decision_synthesis as DS
from intent_engine.executive.competitive_qualification import entity_type_of
from intent_engine.executive.economic_architecture import architecture_of
from intent_engine.executive.impossible_hypothesis import (
    CONCEIVABLE, LIVE, PLAUSIBLE, hypotheses_for)
from intent_engine.external_intel import founder_demo_snapshot as FDS
from intent_engine.founder_brief import qa as QA

CIK_ADOBE, CIK_CLOUDFLARE, CIK_MSFT = "796343", "1477333", "789019"

ADOBE = (
    "Adobe is a global technology company. We deliver end-to-end "
    "professional creative and marketing solutions to our customers. "
    "We have three reportable segments: Digital Media, Digital Experience "
    "and Publishing and Advertising. Digital Media is our largest segment. "
    "Digital Experience is the highest-margin business we operate. "
    "Revenue is derived from the sale of cloud-enabled software "
    "subscriptions, term-based, royalty, and perpetual software licenses. "
    "Our customers are creative professionals, marketers and enterprises "
    "of every size across many industries. ")
CLOUDFLARE = (
    "We provide a broad range of services to businesses of all sizes and "
    "in all geographies, making them more secure. Revenue is generated "
    "from pay-as-you-go and contracted customers and is comprised of "
    "subscription fees to access its network and products, support "
    "services, and usage-based fees. We operate in a very competitive "
    "and rapidly changing environment. ")


def _doc(cik, text, source_id="s1"):
    return {"source_id": source_id, "text_content": text,
            "final_url":
                f"https://www.sec.gov/Archives/edgar/data/{cik}/x/a.htm"}


def _arch(cik, text, company):
    return architecture_of([_doc(cik, text)], company=company,
                           subject_cik=cik)


# ---------------------------------------------------------------------------
# 1. THE Q&A SEAM. Two repairs shipped green and inert against this field.
# ---------------------------------------------------------------------------

def _dossier(evidence_ids=()):
    """A run the market bundle does not cover, exactly as production builds
    it: the SAME keyword set `webapp/app.py` passes at its one call site."""
    founder = read_founder_snapshot(FDS.build_payload(
        run_id="r1", company_id="acme", canonical_name="Acme, Inc.",
        domain="", report=None, context=None, scope=None,
        evidence_ids=list(evidence_ids),
        independence=None, claim_provenance=None,
        discovery=None, learning=None))
    market = market_unavailable("no snapshot was published", company_id="acme")
    return assemble(market, founder, known_as=("acme",), now="2026-08-21")


def test_the_call_site_supplies_the_runs_evidence_ids():
    """THE DEFECT ITSELF: the field the standing repair read was never fed.

    `build_payload` has always accepted `evidence_ids`; the only production
    caller never passed them, so `evidence_reference_ids` was NOT_ATTEMPTED/0
    for every company on every run and both repairs were unreachable.
    """
    import inspect

    from intent_engine.webapp import app as APP
    source = inspect.getsource(APP.WebApp._publish_demo_dossier)
    start = source.find("build_payload(")
    assert start != -1, "the production call site was not found"
    # BALANCED, NOT MATCHED BY A REGEX. The argument list spans several lines
    # and contains nested calls, and a regex that stops at the first `)`
    # reads a prefix -- which would pass while the keyword sits outside it.
    depth, end = 0, None
    for i in range(source.index("(", start), len(source)):
        depth += (source[i] == "(") - (source[i] == ")")
        if depth == 0:
            end = i
            break
    assert end is not None
    assert "evidence_ids=" in source[start:end], (
        "the only production caller of build_payload does not pass "
        "evidence_ids; the standing seam is unreachable again")


def test_a_run_with_its_own_evidence_is_not_refused():
    dossier = _dossier(evidence_ids=[f"src-{i}" for i in range(11)])
    block = ((dossier.founder_block or {}).get("blocks") or {})["evidence"]
    assert block["count"] == 11, block
    assert DS._standing_of(dossier) != DS.REFUSED


def test_a_run_with_its_own_evidence_is_not_unmeasurable_either():
    """The second inert repair sent this case to UNMEASURABLE, whose copy is
    'No evidence has been published for this company' -- the same false
    sentence wearing a different name."""
    dossier = _dossier(evidence_ids=["src-1", "src-2"])
    assert DS._standing_of(dossier) not in (DS.REFUSED, DS.UNMEASURABLE)


def test_a_run_with_nothing_from_either_side_is_still_refused():
    """The negative control. Absence must still be reportable, or this fix
    is just the old defect inverted."""
    assert DS._standing_of(_dossier(evidence_ids=())) == DS.REFUSED


def test_the_recommendation_no_longer_tells_a_read_company_not_to_act():
    decision = DS.compose(
        _dossier(evidence_ids=[f"s{i}" for i in range(11)])).as_dict()
    assert "Do not act on this reading" not in \
        (decision.get("recommended_next_move") or "")


# ---------------------------------------------------------------------------
# 2. THE IMPOSSIBLE HYPOTHESIS. Scored 0.0: nothing produced one.
# ---------------------------------------------------------------------------

def test_two_companies_do_not_get_the_same_heresies():
    """Selection is a function of the SUBJECT'S measured economics, so the
    collapse that produced one business-model sentence for five companies
    cannot reproduce here."""
    adobe = hypotheses_for("Adobe Inc.", _arch(CIK_ADOBE, ADOBE, "Adobe Inc."))
    cf = hypotheses_for("Cloudflare, Inc.",
                        _arch(CIK_CLOUDFLARE, CLOUDFLARE, "Cloudflare, Inc."))
    assert adobe and cf
    assert {h.kind for h in adobe} != {h.kind for h in cf}
    assert not ({h.mechanism for h in adobe} & {h.mechanism for h in cf})


def test_every_hypothesis_carries_a_mechanism_and_an_experiment():
    for h in hypotheses_for("Adobe Inc.", _arch(CIK_ADOBE, ADOBE,
                                                "Adobe Inc.")):
        assert h.mechanism and h.falsifier and h.smallest_experiment
        assert h.evidence_for and h.evidence_against
        assert h.plausibility in (CONCEIVABLE, PLAUSIBLE, LIVE)


def test_a_multi_engine_filer_gets_the_platform_heresy():
    kinds = {h.kind for h in hypotheses_for(
        "Adobe Inc.", _arch(CIK_ADOBE, ADOBE, "Adobe Inc."))}
    assert "platform_inversion" in kinds


def test_an_unreadable_company_gets_no_heresy_rather_than_a_generic_one():
    """The negative control. A heresy about a company we could not read is a
    heresy about nobody, and inventing one is the defect this replaces."""
    from intent_engine.executive.economic_architecture import (
        EconomicArchitecture)
    assert hypotheses_for("Nobody", EconomicArchitecture(company="Nobody")) \
        == ()


def test_the_filings_first_person_does_not_reach_the_reader():
    for h in hypotheses_for("Adobe Inc.", _arch(CIK_ADOBE, ADOBE,
                                                "Adobe Inc.")):
        assert not re.search(r"\bour\b|\bwe\b", h.mechanism, re.I), h.mechanism


# ---------------------------------------------------------------------------
# 3. THE ADVERSARY. A complete engine whose result no surface could see.
# ---------------------------------------------------------------------------

def test_the_canonical_read_exports_the_adversary_and_the_heresies():
    """The seam that kept both off every page: the read is what surfaces
    project from, and neither field was on it."""
    from intent_engine.executive.strategic_read import StrategicRead
    exported = StrategicRead(company="x").as_dict()
    for field in ("adversary", "impossible_hypotheses",
                  "economic_architecture"):
        assert field in exported, field


def test_the_composed_decision_carries_the_heresies():
    from intent_engine.strategic_intelligence.decision import FounderDecision
    assert "impossible_hypotheses" in FounderDecision(company="x").as_dict()


def test_an_adversary_row_names_who_and_at_which_level():
    from intent_engine.executive.analysis_selection import AdversaryMove
    from intent_engine.executive.strategic_read import _adversary_row
    row = _adversary_row(AdversaryMove(
        level="L2", actor="Canva", objective="o", action="moves first",
        rationale="r", evidence="e", observable_signal="s", impact="i",
        countermeasure="c", kill_switch="k"))
    assert "Canva" in row["statement"] and "L2" in row["statement"]


@pytest.mark.parametrize("question,expected", [
    ("What is the impossible hypothesis?", "impossible_hypotheses"),
    ("What are we not considering?", "impossible_hypotheses"),
    ("How would they respond if we move?", "adversary"),
])
def test_qa_routes_each_question_to_its_own_producer(question, expected):
    """The heresy question was routed at `adversary` -- a different object
    answering a different question -- because no heresy producer existed."""
    intent = QA.intent_of(question)
    field = next(f for n, _m, f, _a in QA.INTENT_ROUTES if n == intent)
    assert field == expected


def test_a_populated_heresy_list_does_not_render_as_an_absence():
    """The vocabulary is part of the fix: a producer whose key names are
    absent from the row tuples renders as NOTHING, which is how a populated
    competitor list once answered 'no competitor has been selected'."""
    rows = [h.as_dict() for h in hypotheses_for(
        "Adobe Inc.", _arch(CIK_ADOBE, ADOBE, "Adobe Inc."))]
    answer, _ = QA._route_answer("What is the impossible hypothesis?",
                                 {"impossible_hypotheses": rows})
    assert answer and "No heretical reading" not in answer


def test_a_populated_adversary_list_does_not_render_as_an_absence():
    answer, _ = QA._route_answer(
        "How would they respond if we move?",
        {"adversary": [{"level": "L1", "actor": "Canva",
                        "statement": "Canva (L1) responds directly",
                        "action": "responds directly", "impact": "competed"}]})
    assert "Canva" in answer


# ---------------------------------------------------------------------------
# 4. COMPETITOR ACTOR VALIDATION. Structural, never a stoplist of names.
# ---------------------------------------------------------------------------

NOT_ACTORS = ("Banking Supervision", "Compensation Practices",
              "Net Interest Income", "Return on Equity", "Gross Margin",
              "Total Revenue", "Operating Income", "Risk Factors", "Item 1A",
              "Liquidity and Capital Resources", "Cloud Computing",
              "Digital Transformation", "Basel III", "the Dodd-Frank Act",
              "MiFID II", "S&P 500", "Nasdaq Composite", "Russell 2000",
              "Credit Risk Management", "Information Technology Management",
              "Regulatory Reporting", "Compliance Monitoring",
              "Model Validation", "Underwriting Standards")

#: EVERY ONE OF THESE IS A REAL FIRM, and each is here because a structural
#: test of the kind above has already refused one of them once: "Ning" ends
#: in -ing, "Standard" looked like an instrument noun, "Holding" is a gerund.
REAL_FIRMS = ("JPMorgan Chase", "Li Ning", "Canva", "Adobe Inc.",
              "Bank of America Corporation", "Charles Schwab",
              "Morgan Stanley", "Visa Inc.", "Berkshire Hathaway",
              "3M Company", "Alphabet Inc.", "Shopify Inc.", "Old Mutual",
              "Standard Chartered", "Take-Two Interactive", "Nintendo",
              "Carnival Corporation", "Salesforce", "ASML Holding",
              "Sea Limited", "Grifols", "Linde plc", "Honda Motor Co",
              "Taiwan Semiconductor Manufacturing", "SAP SE", "HDFC Bank",
              # THE TEN THE SUFFIX WALL REFUSED. Every one is a real filer
              # whose name merely ENDS like a process noun -- which is what
              # made "a long word ending in -ing is abstract" a wall rather
              # than a test.
              "Genting Berhad", "Sterling Infrastructure",
              "Corning Incorporated", "Reading International",
              "Sterling Bancorp", "Downing Renewables", "Fleming Companies",
              "Flushing Financial", "Herbalife Nutrition",
              "Ping An Insurance", "Franklin Resources", "Iron Mountain")


@pytest.mark.parametrize("name", NOT_ACTORS)
def test_a_heading_measure_rule_or_index_is_not_a_company(name):
    entity, _why = entity_type_of(name, clause=f"We compete with {name}.")
    assert entity != "COMPANY", f"{name} typed as a company"


#: A BANK IS A COMPANY THAT IS ALSO A FINANCIER, and typing it as one is
#: correct rather than a refusal -- `qualify` lets a financier through when
#: the subject sells financing, which is the case a bank's rival is in. The
#: property that matters is that a real filer is never turned into a THING:
#: an activity, a benchmark level, or a rule.
_NOT_AN_ACTOR = ("CATEGORY_OR_PRACTICE", "INDEX_OR_BENCHMARK_PROVIDER",
                 "PROGRAM_OR_POLICY")


@pytest.mark.parametrize("name", REAL_FIRMS)
def test_a_real_firm_is_never_reduced_to_a_thing(name):
    entity, why = entity_type_of(name, clause=f"We compete with {name}.")
    assert entity not in _NOT_AN_ACTOR, \
        f"{name} refused as {entity} ({why})"


# ---------------------------------------------------------------------------
# 5. MULTI-ENGINE. §7: a filer with several segments is not one business.
# ---------------------------------------------------------------------------

def test_a_multi_engine_filer_keeps_its_engines_apart():
    arch = _arch(CIK_ADOBE, ADOBE, "Adobe Inc.")
    assert arch.multi_engine
    assert arch.revenue_engine == "Digital Media"
    assert arch.profit_engine == "Digital Experience"
    assert arch.revenue_engine != arch.profit_engine


def test_a_divergent_profit_engine_produces_its_own_heresy():
    kinds = {h.kind for h in hypotheses_for(
        "Adobe Inc.", _arch(CIK_ADOBE, ADOBE, "Adobe Inc."))}
    assert "profit_engine_is_elsewhere" in kinds


def test_a_single_segment_filer_is_not_forced_into_three_engines():
    arch = _arch(CIK_CLOUDFLARE, CLOUDFLARE, "Cloudflare, Inc.")
    assert not arch.multi_engine


# ---------------------------------------------------------------------------
# 6. THE WIRING ITSELF.
#
# The first version of this file tested the PRODUCERS -- `hypotheses_for`,
# `_adversary_row` -- and the break proofs then reported NOT_CAUGHT when the
# compose call site was deleted, because a test of a helper cannot see
# whether anything calls it. That is precisely the defect this whole wave
# repairs: a correct producer nothing invokes. So the seam gets its own test.
# ---------------------------------------------------------------------------

def _composed_read():
    """A real `strategic_read.compose`, driven by one subject filing."""
    from intent_engine.executive import strategic_read as SR
    return SR.compose(
        company="Adobe Inc.", domain="adobe.com",
        documents=[_doc(CIK_ADOBE, ADOBE)],
        observations=[{"excerpt": ADOBE[:200], "source_class": "company_owned",
                       "observed_at": "2026-02-01"}],
        subject_cik=CIK_ADOBE)


def test_compose_puts_the_heresies_on_the_read():
    read = _composed_read()
    rows = list(getattr(read, "impossible_hypotheses", ()) or ())
    assert rows, "compose produced no heresies for a filing it could read"
    assert all(r.get("mechanism") and r.get("smallest_experiment")
               for r in rows)


def test_compose_puts_the_adversary_on_the_read():
    """The adversary rows are only produced once a rival is established, so
    this asserts the PROJECTION -- that whatever the engine returned reaches
    the read in the shape a surface can render, actor and level included."""
    from intent_engine.executive.analysis_selection import AdversaryMove
    from intent_engine.executive.strategic_read import _adversary_row
    import inspect

    from intent_engine.executive import strategic_read as SR
    source = inspect.getsource(SR.compose)
    assert "_adversary_row" in source, (
        "compose no longer projects the adversary onto the read; the L0/L1/L2"
        " engine is running for nobody again")
    row = _adversary_row(AdversaryMove(
        level="L1", actor="Canva", objective="o", action="responds",
        rationale="r", evidence="e", observable_signal="s", impact="i",
        countermeasure="c", kill_switch="k"))
    assert "Canva" in row["statement"]


def test_compose_carries_the_measured_architecture():
    read = _composed_read()
    arch = getattr(read, "economic_architecture", None)
    assert isinstance(arch, dict) and arch.get("measured"), arch


# ---------------------------------------------------------------------------
# 7. A DOSSIER IS NOT A MARKET READING.
#
# Found by the full guard, not by design: lifting a run with its own evidence
# out of REFUSED also lifted the composed decision over a dossier whose
# MARKET side is unavailable, and `_executive_contract` was passing that
# object as the published market reading with `market_usable=True`. A run
# whose own decision was WITHHELD was then told "A supported reading exists
# and is set out on the Executive X-Ray" -- two surfaces of one run
# disagreeing, which is the one thing the contract exists to prevent.
# ---------------------------------------------------------------------------

def test_the_contract_is_not_told_a_market_reading_exists_without_one():
    import inspect

    from intent_engine.webapp import app as APP
    source = inspect.getsource(APP.WebApp._executive_contract)
    assert "AVAILABLE" in source and "STALE" in source, (
        "the contract is being handed a dossier as a market reading without "
        "checking that the market side published anything")


def test_an_unpublished_market_side_does_not_claim_a_supported_reading():
    from intent_engine.executive import contract as EC
    decided = EC.decide(company="Acme, Inc.", run_decision=None,
                        market_decision=None, market_usable=False,
                        bounded_read=False)
    assert not decided.reading_exists
    assert decided.readiness == EC.WITHHELD


def test_a_genuinely_published_market_reading_still_counts():
    """NEGATIVE CONTROL: the repair must not switch the market engine off."""
    from intent_engine.executive import contract as EC
    decided = EC.decide(company="Cloudflare, Inc.", run_decision=None,
                        market_decision={"standing": "SUPPORTED"},
                        market_usable=True)
    assert decided.reading_exists


# ---------------------------------------------------------------------------
# 8. THE CUSTOMER'S FULL ANALYSIS, not the operator's.
#
# The first wiring of both capabilities went into `founder_brief/deep.py`,
# which renders `/demo-dossiers/<id>/full` -- an OPERATOR route. The customer
# journey captures `/runs/<id>/full`, which renders `founder_brief/dossier.py`
# from the canonical read. A repair rendered on the wrong one of two surfaces
# with the same name is the inert repair this session has now caught three
# times, so the customer surface gets its own test.
# ---------------------------------------------------------------------------

class _FakeRead:
    """Only what these two passages project from."""
    adversary = ({"level": "L1", "actor": "Canva",
                  "action": "responds directly to a price move",
                  "rationale": "it shares this business model",
                  "impact": "the gain is partly competed away",
                  "observable_signal": "a matching change in pricing pages",
                  "countermeasure": "sequence the move",
                  "statement": "Canva (L1) responds directly"},)
    impossible_hypotheses = ({
        "hypothesis": "Adobe may be a Digital Experience business.",
        "mechanism": "Its filing identifies two different segments.",
        "why_missed": "revenue is reported first",
        "evidence_for": "the filing separates them",
        "evidence_against": "comparable margins would contradict it",
        "falsifier": "comparable operating margins falsify this",
        "smallest_experiment": "compare three years of segment margin",
        "upside": "capital compounds faster", "downside": "access is lost",
        "plausibility": "LIVE"},)


def test_the_customer_full_analysis_carries_both():
    from intent_engine.founder_brief import dossier as FD
    from intent_engine.strategic_intelligence.editorial import SaidOnce

    read, said = _FakeRead(), SaidOnce()
    adversary = FD._adversary("Adobe Inc.", read, said)
    heresy = FD._impossible("Adobe Inc.", read, SaidOnce())
    assert adversary.is_substantive, "the adversary passage renders nothing"
    assert heresy.is_substantive, "the heresy passage renders nothing"
    blob = " ".join(adversary.paragraphs)
    assert "Canva" in blob and "L1" in blob
    assert "Digital Experience" in " ".join(heresy.paragraphs)


def test_build_dossier_includes_both_passages():
    """The passage functions existing is not the same as being CALLED."""
    import inspect

    from intent_engine.founder_brief import dossier as FD
    source = inspect.getsource(FD.build_dossier)
    assert "_adversary(" in source and "_impossible(" in source, (
        "build_dossier does not assemble the two new passages, so they "
        "cannot reach the customer's Full Analysis")


def test_an_empty_read_yields_no_passage_rather_than_an_empty_heading():
    from intent_engine.founder_brief import dossier as FD
    from intent_engine.strategic_intelligence.editorial import SaidOnce

    class _Bare:
        adversary = ()
        impossible_hypotheses = ()

    assert not FD._adversary("X", _Bare(), SaidOnce()).is_substantive
    assert not FD._impossible("X", _Bare(), SaidOnce()).is_substantive
