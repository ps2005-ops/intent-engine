"""Contracts: model parity, metrics, universe walls, policy honesty, the news slot."""
import ast
import pathlib
import random

import numpy as np
import pytest

from intent_engine.econ import forecast as FC
from intent_engine.paper_validation import evidence_channel as EC
from intent_engine.paper_validation import metrics as MT
from intent_engine.paper_validation import model as MD
from intent_engine.paper_validation import policies as PL
from intent_engine.paper_validation import protocol as PR
from intent_engine.paper_validation import universe as U

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / "src/intent_engine/paper_validation"
MANIFEST = ROOT / "docs/execution/v5/COMPANY_VALIDATION_MANIFEST.yaml"


class TestModelParity:
    def test_the_vectorised_fit_is_econ_forecast_fit(self):
        r = random.Random(7)
        names = ("a", "b", "c")
        rows = []
        for i in range(120):
            f = {"a": r.gauss(0, 1), "b": r.gauss(0, 3), "c": float(i % 2)}
            rows.append(FC.Row(origin=f"2020-{1 + i % 12:02d}-01", target="t",
                               horizon_days=21, features=f,
                               outcome=(f["a"] + r.gauss(0, 1)) > 0))
        ref = FC.fit(rows, names)
        X = np.array([[x.features[n] for n in names] for x in rows])
        y = np.array([1.0 if x.outcome else 0.0 for x in rows])
        got = MD.fit(X, y, names)
        assert np.allclose(got.weights, ref.weights, atol=1e-9)
        assert got.bias == pytest.approx(ref.bias, abs=1e-9)
        assert MD.predict(got, X[:5]) == pytest.approx(
            [ref.predict(x) for x in rows[:5]], abs=1e-9)


class TestMetrics:
    def test_brier_and_log_loss(self):
        assert MT.brier([0.5, 0.5], [1, 0]) == pytest.approx(0.25)
        assert MT.log_loss([0.5], [1]) == pytest.approx(np.log(2))

    def test_holm_is_monotone_and_capped(self):
        h = MT.holm({"a": 0.01, "b": 0.04, "c": 0.5})
        assert h["a"] == pytest.approx(0.03)
        assert h["b"] == pytest.approx(0.08)
        assert h["c"] == pytest.approx(0.5)

    def test_a_riskless_benchmark_compares_to_zero(self):
        a = np.array([0.01, -0.005, 0.02, 0.0, 0.015] * 10)
        out = MT.paired_sharpe_diff(a, np.zeros(len(a)))
        assert out["against"].startswith("zero")
        assert out["diff"] == pytest.approx(MT.sharpe(a))

    def test_block_indices_resample_whole_periods(self):
        idx = MT.block_indices(50, draws=20, block=6)
        assert idx.shape == (20, 50) and idx.max() < 50

    def test_drawdown_of_a_known_curve(self):
        s = MT.book_stats([0.10, -0.50, 0.0, 0.0])
        assert s["max_drawdown"] == pytest.approx(0.5)


class TestUniverseWalls:
    def test_no_private_company_receives_a_security(self):
        from intent_engine.validation import load
        m = load(MANIFEST)
        private = [c for c in m.companies
                   if str(c.public_private).upper().startswith("PRI")]
        assert private, "the manifest is expected to hold private companies"
        for c in private:
            with pytest.raises(U.PrivateCompanyRefused):
                U.listed_security(c)
        listed, refused = U.companies(m)
        ids = {i.company_id for i in listed}
        assert not ids & {c.company_id for c in private}
        assert {r["company_id"] for r in refused} >= {c.company_id
                                                      for c in private}

    def test_company_and_proxy_scopes_never_mix(self):
        for i in U.etfs():
            assert i.signal_scope in (U.MACRO_PROXY, U.SECTOR_PROXY)
            assert not i.business_model_class
        from intent_engine.validation import load
        listed, _ = U.companies(load(MANIFEST))
        assert all(i.signal_scope == U.COMPANY_SCOPE and i.business_model_class
                   for i in listed)


class TestPolicyHonesty:
    def test_absent_policies_are_named_with_reasons(self):
        reg = PL.by_id(PL.registry())
        assert reg["causal_filtered"].status == PL.NOT_IMPLEMENTED
        assert reg["logit_C"].status == PL.PENDING_INPUT
        assert reg["evidence_augmented"].status == PL.PENDING_INPUT
        for p in reg.values():
            if p.status != PL.IMPLEMENTED:
                assert p.status_reason and not p.applies("etf")

    def test_the_engine_policies_call_the_engine(self, monkeypatch):
        from intent_engine.market import strategy_library as SL
        calls = []
        real = SL.baseline_momentum

        def spy(*a, **kw):
            calls.append(kw.get("security"))
            return real(*a, **kw)

        monkeypatch.setattr(SL, "baseline_momentum", spy)
        from paper_validation_fixtures import universe
        from intent_engine.paper_validation import observations as OB
        dates, bars, etfs, panel = universe()
        rows, _ = OB.build(bars=bars, instruments=etfs, panel=panel,
                           dates=[(0, dates[400], "", "")])
        p = PL.by_id(PL.registry())["ie_market_momentum"]
        p.bind(bars)
        p.decide_date(rows, None)
        assert sorted(calls) == sorted(o.symbol for o in rows)

    def test_rule_probability_and_costs_are_the_engines_own(self):
        from intent_engine.market import costs as MC
        from intent_engine.market import signals as MS
        assert PR.RULE_P == MS.BASELINE_PROBABILITY
        assert PR.SLIPPAGE_BPS == MC.DEFAULT.slippage_bps_per_side
        assert PR.PROTOCOL["execution"]["commission_bps"] == \
            MC.DEFAULT.commission_bps

    def test_new_work_is_never_labelled_as_the_engine(self):
        reg = PL.by_id(PL.registry())
        assert reg["ie_econ_bayes"].provenance == PL.NEW_IN_THIS_WORK
        for pid in ("logit_A", "logit_B", "logit_D"):
            assert reg[pid].provenance == PL.NEW_IN_THIS_WORK
        assert reg["ie_econ_transmission"].provenance == PL.EXISTING_ENGINE


class TestPackageWalls:
    def test_the_package_never_imports_a_broker_or_an_order_surface(self):
        banned = {"intent_engine.paper.broker", "intent_engine.paper.execution",
                  "intent_engine.paper.orders"}
        for path in PKG.glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert node.module not in banned, (path.name, node.module)
                    if node.module == "intent_engine.paper":
                        assert not {a.name for a in node.names} & {
                            "broker", "execution", "orders"}
                if isinstance(node, ast.Import):
                    for a in node.names:
                        assert a.name not in banned, (path.name, a.name)

    def test_the_package_reads_no_credential(self):
        for path in PKG.glob("*.py"):
            src = path.read_text()
            assert "os.environ" not in src and "getenv" not in src, path.name
            assert ".env" not in src.replace(".environ", ""), path.name


class TestProtocol:
    def test_the_declaration_is_hashed_and_a_change_is_visible(self, monkeypatch):
        h = PR.declaration_hash()
        PR.assert_unchanged(h)
        monkeypatch.setitem(PR.PROTOCOL["execution"], "slippage_bps_per_side",
                            1.0)
        with pytest.raises(PR.ProtocolChanged):
            PR.assert_unchanged(h)


class TestNewsSlot:
    def test_the_pending_provider_says_so_and_cannot_be_read(self):
        p = EC.PendingProvider()
        assert p.status() == EC.PENDING
        with pytest.raises(EC.ProviderBreach):
            p.items("x", cutoff="2026-01-01")

    def test_an_item_knowable_after_the_cutoff_is_a_breach(self):
        it = EC.EvidenceItem("n1", "acme", "2026-01-05", "2026-01-06", "wire",
                             "third_party", 0.5)
        with pytest.raises(EC.ProviderBreach, match="knowable"):
            EC.news_features(EC.FixtureProvider([it]), "acme",
                             cutoff="2026-01-05", window_start="2025-12-01")

    def test_features_count_independent_origins_and_return_dated_ids(self):
        items = [EC.EvidenceItem(f"n{i}", "acme", "2026-01-0%d" % i,
                                 "2026-01-0%d" % i, origin, cls, s)
                 for i, (origin, cls, s) in enumerate(
                     [("acme", "company_published", 1.0),
                      ("wire", "third_party", -0.5),
                      ("paper", "third_party", -0.5)], 1)]
        f, ids = EC.news_features(EC.FixtureProvider(items), "acme",
                                  cutoff="2026-01-05",
                                  window_start="2025-12-01")
        assert f["news_items_30d"] == 3
        assert f["news_independent_origins_30d"] == 2   # own release excluded
        assert all(i.startswith("news:") for i in ids)
        from intent_engine.paper_validation import leakage as LK
        LK.check_evidence(ids, "2026-01-05")
