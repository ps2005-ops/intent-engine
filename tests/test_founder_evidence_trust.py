"""Three articles repeating one press release must not behave like three facts.

The graph projection built one EVIDENCE node and one SUPPORTS edge PER ROW, so
three sites carrying one announcement became three independent supports in the
structure every downstream reader counts — and `update_method` called the
belief SUPPORTED because it counts rows too.

Most of this file is about the ways that could be fixed BADLY: by changing the
wording without changing the weight, by flattening genuine corroboration along
with the re-reporting, by leaking wire vocabulary onto the page, or by
counting a citation change as a decision impact.
"""
import pytest

from intent_engine.business_graph import projections as bgp
from intent_engine.business_graph.model import EVIDENCE, HYPOTHESIS, SUPPORTS
from intent_engine.external_intel import decision_impact as di
from intent_engine.external_intel import evidence_trust as et
from intent_engine.external_intel import pack as ep
from intent_engine.external_intel import strategic_contract as sc


def _trust(standing, raw, events, weight, sentence, groups=None):
    groups = groups or [[f"ev_{i}" for i in range(raw)]]
    return {
        "contract": "evidence_trust.v1", "standing": standing,
        "raw_accounts": raw, "distinct_events": events,
        "independent_support": events, "weight": weight,
        "sentence": sentence,
        "events": [{"event_id": f"evt_{n}", "standing": standing,
                    "accounts": len(g), "weight": weight,
                    "evidence_ids": list(g)}
                   for n, g in enumerate(groups)],
    }


DEPENDENT = _trust(
    "DEPENDENT_REREPORTING", 3, 1, 1.0,
    "Several reports repeat the same underlying announcement, so we treat "
    "this as one observation rather than independent confirmation.")

INDEPENDENT = _trust(
    "INDEPENDENTLY_CORROBORATED", 2, 1, 2.0,
    "Separate sources independently support the same point.",
    groups=[["ev_0", "ev_1"]])

CONFLICTED = _trust(
    "CONFLICTED", 2, 1, 0.5,
    "Public sources disagree on this point, so the conclusion remains "
    "bounded.", groups=[["ev_0", "ev_1"]])


def _belief(trust=None, **kw):
    row = {
        "proposition": "Acme Corp is seeing demand strengthen",
        "subject": "Acme Corp", "confidence": 0.586,
        # It says SUPPORTED. The question every test here asks is: by what?
        "direction_of_last_change": "UP",
        "last_updated": "2026-08-05",
        "basis": "three further reports since it opened",
        "update_method": "CORROBORATED",
        "evidence_ids": ["ev_0", "ev_1", "ev_2"],
        "limitations": [],
    }
    if trust is not None:
        row["evidence_trust"] = trust
        row["evidence_ids"] = [i for e in trust["events"]
                               for i in e["evidence_ids"]]
    row.update(kw)
    return row


def _intel(beliefs, **kw):
    return sc.StrategicIntel(available=True, company_id="acme",
                             as_of="2026-08-07", beliefs=tuple(beliefs), **kw)


def _graph(beliefs):
    return bgp.from_strategic_dossier(
        company_id="acme", company_label="Acme Corp", beliefs=beliefs,
        as_of="2026-08-07", dossier_revision="r1")


def _blocks(beliefs):
    intel = _intel(beliefs)
    pack = ep.reasoning_pack(ep.build_context(strategic=intel,
                                              as_of="2026-08-07"))
    return [b for b in pack["blocks"] if b["context"] == ep.STRATEGIC]


# ===========================================================================
# 1. REASONING WEIGHT, NOT WORDING
# ===========================================================================
def test_three_same_origin_reports_are_one_support_in_the_graph():
    """The defect, stated as the structure that carried it."""
    graph = _graph([_belief(DEPENDENT)])
    hypothesis = graph.of_kind(HYPOTHESIS)[0]
    supports = graph.in_edges(hypothesis.node_id, SUPPORTS)
    assert len(supports) == 1
    assert len(graph.of_kind(EVIDENCE)) == 1


def test_a_dependent_cluster_does_not_mature_the_belief():
    """`update_method` says CORROBORATED and the sources say otherwise.

    The sources win: three rewrites of one announcement are not three later
    tests of the belief they opened.
    """
    graph = _graph([_belief(DEPENDENT)])
    standing = graph.of_kind(HYPOTHESIS)[0].confidence
    assert standing == "reported again, not independently confirmed"


def test_independent_corroboration_is_not_flattened():
    """The control. A fix that deflates ALL multi-source evidence has
    replaced one wrong answer with another."""
    dependent = _graph([_belief(DEPENDENT)]).of_kind(HYPOTHESIS)[0]
    independent = _graph([_belief(INDEPENDENT)]).of_kind(HYPOTHESIS)[0]
    assert independent.confidence == "supported by later evidence"
    assert independent.confidence != dependent.confidence


def test_the_independent_case_keeps_the_stronger_standing():
    assert et.read(INDEPENDENT).weight > et.read(DEPENDENT).weight
    assert et.read(INDEPENDENT).may_claim_independence
    assert not et.read(DEPENDENT).may_claim_independence


def test_conflicted_evidence_cannot_become_a_confident_conclusion():
    graph = _graph([_belief(CONFLICTED)])
    node = graph.of_kind(HYPOTHESIS)[0]
    assert node.confidence == "sources disagree"
    assert et.read(CONFLICTED).must_bound


def test_conflicted_does_not_silently_pick_the_first_source():
    """It must remain bounded rather than resolve to whichever arrived
    first."""
    block = _blocks([_belief(CONFLICTED)])[0]
    joined = " ".join(block["facts"]) + " ".join(block["limitations"])
    assert "disagree" in joined.lower()


# ===========================================================================
# 2. PROVENANCE SURVIVES NORMALIZATION
# ===========================================================================
def test_grouping_never_deletes_a_row():
    """Normalization groups; it does not discard. Every raw id must still be
    reachable, or the trust statement cannot be traced."""
    graph = _graph([_belief(DEPENDENT)])
    node = graph.of_kind(EVIDENCE)[0]
    assert list(node.attrs["evidence_ids"]) == ["ev_0", "ev_1", "ev_2"]


def test_the_rendered_block_still_carries_every_raw_id():
    block = _blocks([_belief(DEPENDENT)])[0]
    assert block["evidence_ids"] == ["ev_0", "ev_1", "ev_2"]


def test_the_block_reports_occurrences_apart_from_rows():
    """Both numbers, so nothing downstream has to divide."""
    block = _blocks([_belief(DEPENDENT)])[0]
    assert block["occurrences"] == 1
    assert len(block["evidence_ids"]) == 3


def test_the_walk_reaches_rows_from_a_founder_visible_statement():
    """§13's chain, in one assertion: rendered insight -> hypothesis node ->
    supporting occurrence -> event id -> evidence rows."""
    graph = _graph([_belief(DEPENDENT)])
    hypothesis = graph.of_kind(HYPOTHESIS)[0]
    edge = graph.in_edges(hypothesis.node_id, SUPPORTS)[0]
    occurrence = graph.node(edge.src)
    assert occurrence.attrs["event_id"] == "evt_0"
    assert occurrence.attrs["evidence_ids"] == ["ev_0", "ev_1", "ev_2"]


# ===========================================================================
# 3. ABSENT IS NOT SINGLE
# ===========================================================================
def test_an_unnormalized_dossier_is_unknown_rather_than_confirmed():
    """A producer that never normalized must not earn the standing of one
    that did."""
    trust = et.of_belief(_belief(None))
    assert trust.standing == et.UNKNOWN
    assert trust.weight == 0.0


def test_an_unnormalized_dossier_does_not_borrow_the_dependent_sentence():
    """'The reports do not independently confirm each other' is a claim ABOUT
    THE SOURCES. Nobody looked at these sources, so it may not be made."""
    unknown = et.limitation(et.UNRATED)
    dependent = et.limitation(et.read(DEPENDENT))
    assert unknown != dependent
    assert "not established" in unknown


def test_an_unnormalized_belief_still_renders_one_node_per_row():
    """This side may not GUESS a grouping. Without the producer's answer,
    each row stands alone exactly as before."""
    graph = _graph([_belief(None)])
    assert len(graph.of_kind(EVIDENCE)) == 3


# ===========================================================================
# 4. THE WIRE VOCABULARY NEVER REACHES THE PAGE
# ===========================================================================
@pytest.mark.parametrize("trust", [DEPENDENT, INDEPENDENT, CONFLICTED])
def test_no_internal_standing_name_reaches_a_rendered_block(trust):
    block = _blocks([_belief(trust)])
    rendered = " ".join(block[0]["facts"] + block[0]["limitations"])
    assert et.contains_internal_vocabulary(rendered) == ()


def test_the_founder_sentence_is_plain_language():
    block = _blocks([_belief(DEPENDENT)])[0]
    assert any("same underlying announcement" in f for f in block["facts"])


def test_a_single_unremarkable_source_says_nothing_at_all():
    """A trust note on every claim is a methodology lecture, and a reader
    told about sourcing nine times stops reading the tenth."""
    single = _trust("SINGLE_SOURCE", 1, 1, 1.0, "One source reports this.",
                    groups=[["ev_0"]])
    assert et.sentence(et.read(single)) == ""


# ===========================================================================
# 5. DECISION IMPACT — MEASURED, AND NOT BY CITATION COUNT
# ===========================================================================
def _state(belief):
    return di.semantic_state(ep.build_context(strategic=_intel([belief]),
                                              as_of="2026-08-07"))


def test_normalized_trust_changes_a_decision_field_not_only_a_citation():
    """The comparison is over semantic fields. A change that only moved a
    citation would show UNCHANGED everywhere, which is the honest reading and
    the one this must be able to produce."""
    before, after = _state(_belief(None)), _state(_belief(DEPENDENT))
    monitoring = di.compare_field(di.MONITORING_PRIORITY,
                                  before[di.MONITORING_PRIORITY],
                                  after[di.MONITORING_PRIORITY])
    assert monitoring.change == di.REVERSED


def test_the_bounding_sentence_reaches_the_decision_comparison():
    """It starts with none of the classifier's prefixes, so without a named
    key the one line that bounds the conclusion would be invisible to the
    metric — and the metric would be measuring its own blind spot."""
    after = _state(_belief(DEPENDENT))
    assert after[di.BOUNDED_CONCLUSION]


def test_independent_corroboration_does_not_weaken_the_reading():
    """The direction matters, not merely that something moved."""
    before, after = _state(_belief(None)), _state(_belief(INDEPENDENT))
    monitoring = di.compare_field(di.MONITORING_PRIORITY,
                                  before[di.MONITORING_PRIORITY],
                                  after[di.MONITORING_PRIORITY])
    assert monitoring.change == di.UNCHANGED


def test_a_longer_block_alone_is_not_an_impact():
    """The easy way to fake this metric is to wire it to 'something
    changed'. Boilerplate must still compare UNCHANGED."""
    delta = di.compare_field(
        di.BOUNDED_CONCLUSION,
        ["Separate sources independently support the same point."],
        ["Separate sources independently support the same point."])
    assert delta.change == di.UNCHANGED


# ===========================================================================
# 6. THE CONSUMER DOES NOT RE-DERIVE WHAT IT CONSUMES
# ===========================================================================
def test_the_founder_side_never_classifies_from_a_source_count():
    """Counting rows locally is the arithmetic that is wrong in the first
    place. If this side ever starts classifying, the standing it produces
    would disagree with the market's — silently."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(et))
    # Names and attributes only — the prose explains at length WHY this side
    # does not look at publishers, and a substring check over the file would
    # be failed by the explanation itself.
    # Names and attributes only. String CONSTANTS are excluded on purpose:
    # `INTERNAL_TERMS` is the guard list, so it legitimately spells out the
    # very vocabulary this test forbids the code from acting on.
    referenced = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    referenced |= {n.attr for n in ast.walk(tree)
                   if isinstance(n, ast.Attribute)}
    referenced |= {f.name for f in ast.walk(tree)
                   if isinstance(f, ast.FunctionDef)}
    forbidden = {"publisher", "publishers", "source_role", "source_roles",
                 "dependency_classes", "classify"}
    assert not (forbidden & {str(r).lower() for r in referenced})


def test_a_standing_the_producer_did_not_send_is_not_invented():
    assert et.read({"standing": "MADE_UP"}).standing == et.UNKNOWN
    assert et.read({}).standing == et.UNKNOWN
    assert et.read(None).standing == et.UNKNOWN
