"""The observability registry may not drift from the code that binds."""
from intent_engine.market import belief_formation as BF
from intent_engine.market import mechanism_observability as MO
from intent_engine.market import observation_binding as OB


def test_all_sixteen_families_are_accounted_for():
    assert set(MO.REGISTRY) == set(BF.FAMILIES)
    assert len(MO.REGISTRY) == 16


def test_direct_is_exactly_what_the_binder_binds():
    direct = {f for f, c in MO.REGISTRY.items() if c.observability == MO.DIRECT}
    assert direct == set(OB.FALSIFIABLE)


def test_only_direct_may_be_called_calibrated():
    for f, c in MO.REGISTRY.items():
        assert c.calibrated_claim_allowed == (c.observability == MO.DIRECT), f
        assert MO.claim_standing(f) == (
            "CALIBRATED_PREDICTIVE" if c.observability == MO.DIRECT else "EXPLORATORY")


def test_every_unbound_family_names_its_next_work_and_bound_ones_name_none():
    for f, c in MO.REGISTRY.items():
        assert bool(c.needs) == (c.observability != MO.DIRECT), f


def test_proxy_contradiction_comes_from_a_type_the_classifier_emits():
    routed = {etype for etype, _, _ in BF._ROUTES}
    for c in MO.REGISTRY.values():
        if c.observability == MO.PROXY:
            assert c.contradicting_sources and set(c.contradicting_sources) <= routed
            assert not set(c.contradicting_sources) & set(c.sources)


def test_sources_are_the_routing_table():
    for f, c in MO.REGISTRY.items():
        assert set(c.sources) == {e for e, fam, _ in BF._ROUTES if fam == f}, f


def test_absence_never_contradicts():
    for c in MO.REGISTRY.values():
        assert "never contradicted" in c.inconclusive
