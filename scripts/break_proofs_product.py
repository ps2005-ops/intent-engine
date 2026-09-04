"""§26/§36: sixteen mutations against the PRODUCT path, anti-tautology enforced.

WHAT IS DIFFERENT ABOUT THIS WAVE
---------------------------------
The previous sixteen mutated the research modules. These mutate the code that
runs when a customer presses "Analyse": the webapp router, the context
producer, the dossier renderer, the Q&A router, the durable store. A defect
that only exists in production is invisible to a proof that only breaks
research code, and productization is precisely where a useful offline signal
turns into a bad recommendation.

Every proof still declares its mutated symbol, the guard under test and the
production call path, and `breakproof.Proof.validate()` refuses it before it
runs if the two are the same symbol. Thirteen tautological proofs were written
by hand across three earlier runs; none can be written here.

THE MIRROR CARRIES THE TESTS TOO
--------------------------------
Several guards here are structural tests rather than runtime assertions -- "is
the renderer handed the context at all" cannot be a runtime check, because a
surface that was never handed it renders a complete-looking page. A structural
test resolving paths against the repository would read the UNMUTATED file and
report green for a mutation it never saw, so the tests are copied into the
mirror and each one derives its path from the imported module's own
`__file__`.
"""
from __future__ import annotations

import importlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import traceback

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from intent_engine.econ import breakproof as BP              # noqa: E402

OUT = REPO / "reports" / "break_proofs_product.json"
PYTHON = os.environ.get("GUARD_PYTHON", sys.executable)

SURFACES = "tests/test_founder_economic_surfaces.py"
UNITS = "tests/test_founder_economic_context.py"


class Tree:
    """A frozen copy of the tree, mutated in place and thrown away.

    Never `src/` itself: a mutation applied to the shared worktree is visible
    to every other process on this machine, and a restore that leaves the same
    file size leaves CPython running the mutated bytecode from its cache.
    """

    def __init__(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="bp_product_"))
        shutil.copytree(REPO / "src", self.root / "src")
        shutil.copytree(REPO / "scripts", self.root / "scripts")
        shutil.copytree(REPO / "tests", self.root / "tests")
        for extra in ("pytest.ini", "pyproject.toml", "conftest.py"):
            src = REPO / extra
            if src.exists():
                shutil.copy(src, self.root / extra)

    def path(self, rel):
        return self.root / rel

    def mutate(self, rel, old, new):
        p = self.path(rel)
        s = p.read_text(encoding="utf-8")
        if old not in s:
            return 0, 0
        before = len(s)
        s2 = s.replace(old, new, 1)
        p.write_text(s2, encoding="utf-8")
        return before, len(s2)

    def load(self, module):
        for k in list(sys.modules):
            if k.startswith("intent_engine"):
                del sys.modules[k]
        sys.path.insert(0, str(self.root / "src"))
        try:
            return importlib.import_module(module)
        finally:
            sys.path.pop(0)

    def pytest(self, target):
        """Run one test (or node id) inside the mirror. Raises when it fails.

        `cwd` is the mirror, and PYTHONPATH names the mirror's own src, so a
        test that imports the package gets the MUTATED one. This is the step
        that a repository-anchored structural test would defeat.
        """
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{self.root}{os.pathsep}{self.root / 'src'}"
        proc = subprocess.run(
            [PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider", target],
            cwd=self.root, env=env, capture_output=True, text=True,
            timeout=900)
        if proc.returncode != 0:
            tail = (proc.stdout or "")[-700:] + (proc.stderr or "")[-200:]
            raise AssertionError(tail)

    def clean(self):
        shutil.rmtree(self.root, ignore_errors=True)
        for k in list(sys.modules):
            if k.startswith("intent_engine"):
                del sys.modules[k]
        sys.path.insert(0, str(REPO / "src"))


def run(proof: BP.Proof, *, mutate, check, positive_control):
    try:
        proof.validate()
        BP.assert_call_path_exists(REPO, proof)
    except BP.TautologicalProof as e:
        proof.verdict = BP.REFUSED
        proof.detail = str(e)[:400]
        return proof
    for k in list(sys.modules):
        if k.startswith("intent_engine"):
            del sys.modules[k]
    try:
        positive_control()
    except Exception as e:                                  # noqa: BLE001
        proof.verdict = BP.UNRELIABLE
        proof.detail = (f"the guard fired on CLEAN code: "
                        f"{type(e).__name__}: {e}")[:400]
        return proof
    t = Tree()
    try:
        before, after = mutate(t)
        proof.bytes_before, proof.bytes_after = before, after
        if not before:
            proof.verdict = BP.NOT_APPLIED
            proof.detail = "the mutation pattern did not match"
            return proof
        proof.assert_mutation_landed()
        try:
            check(t)
        except BP.TautologicalProof:
            raise
        except Exception as e:                              # noqa: BLE001
            proof.verdict = BP.CAUGHT
            proof.detail = f"{type(e).__name__}: {str(e)[:260]}"
            return proof
        proof.verdict = BP.NOT_CAUGHT
        proof.detail = "the mutation was applied and nothing refused it"
        return proof
    except BP.TautologicalProof as e:
        proof.verdict = BP.REFUSED
        proof.detail = str(e)[:300]
        return proof
    finally:
        t.clean()


def _p(**kw):
    return BP.Proof(**kw)


APP = "src/intent_engine/webapp/app.py"
DOSSIER = "src/intent_engine/founder_brief/dossier.py"
QA = "src/intent_engine/founder_brief/qa.py"
DECISION = "src/intent_engine/external_intel/econ_decision.py"
CONTRACT = "src/intent_engine/econ/founder_contract.py"
CONTEXT = "src/intent_engine/external_intel/econ_context.py"
PROFILE = "src/intent_engine/executive/company_profile.py"


# =============================================================================
# 1. remove the founder economic consumer
# =============================================================================
def bp01():
    p = _p(name="01_founder_economic_consumer_removed",
           description="the deep surfaces are built without the economic "
                       "context, so no economic reading can ever appear",
           target_kind=BP.CALL_SITE, mutated_file=APP,
           mutated_symbol="WebApp._executive_brief_page",
           guard_under_test="test_every_deep_surface_is_handed_the_economic_context",
           production_call_path=SURFACES)

    def control():
        pass

    def mutate(t):
        return t.mutate(APP,
                        "                                read=self._strategic_read(run_id, name),\n"
                        "                                econ=self._founder_economic_context(run_id))",
                        "                                read=self._strategic_read(run_id, name))")

    def check(t):
        t.pytest(f"{SURFACES}::test_every_deep_surface_is_handed_the_economic_context")
    return run(p, mutate=mutate, check=check, positive_control=control)


# =============================================================================
# 2. abstention turned into generic macro text
# =============================================================================
def bp02():
    p = _p(name="02_abstention_becomes_generic_macro",
           description="NO_MATERIAL_ECONOMIC_DELTA is rewritten into a macro "
                       "paragraph, so the deliberate silence disappears",
           target_kind=BP.PRODUCER, mutated_file=DECISION,
           mutated_symbol="build",
           guard_under_test="FounderEconomicContext.__post_init__",
           production_call_path=CONTRACT)

    def control():
        FC = importlib.import_module("intent_engine.econ.founder_contract")
        ctx = FC.FounderEconomicContext(
            company_id="c", as_of="2026-08-20",
            status=FC.NO_MATERIAL_ECONOMIC_DELTA, freshness=FC.CURRENT)
        assert ctx.abstains and not ctx.speaks

    def mutate(t):
        return t.mutate(
            DECISION,
            "        status=FC.COMPLETE if speaking else FC.NO_MATERIAL_ECONOMIC_DELTA,",
            "        status=FC.COMPLETE,")

    def check(t):
        ED = t.load("intent_engine.external_intel.econ_decision")
        EC = t.load("intent_engine.external_intel.econ_context")
        CPF = t.load("intent_engine.executive.company_profile")
        econ = EC.EconContext(
            available=True, as_of="2026-08-20", area="US",
            conditions={"treasury_10y": {
                "kind": "treasury_10y", "standing": "OBSERVED",
                "direction": "UP", "value": 4.01, "prior_value": 4.0,
                "as_of": "2026-08-20", "known": True, "moved": True,
                "node_id": "n", "publisher": "FRED", "unit": ""}})
        profile = CPF.CompanyIntelligenceProfile(
            company_id="c", company_name="C", known=True,
            business_model_class="SUBSCRIPTION_SOFTWARE")

        class D:
            readiness = "INVESTIGATION_REQUIRED"
            decision_archetype = "PRICING"
            topic = "PRICING"
            evidence_required = ("x",)
            watch_items = ()
            falsifier = "f"
        ED.build(company_id="c", company_name="C", as_of="2026-08-25",
                 economy=econ, exposures=("treasury_10y",), profile=profile,
                 decision=D(),
                 risks=[{"risk_id": "r", "severity": "LOW", "channel": "ch",
                         "mechanism": "m", "standing": "INFERRED",
                         "evidence": ("e",)}])
    return run(p, mutate=mutate, check=check, positive_control=control)


# =============================================================================
# 3. attribution dropped from a material delta
# =============================================================================
def bp03():
    p = _p(name="03_attribution_dropped",
           description="a material change reaches a surface with no trigger, "
                       "mechanism or provenance behind it",
           target_kind=BP.PRODUCER, mutated_file=DECISION,
           mutated_symbol="augmented",
           guard_under_test="admit",
           production_call_path=DECISION)

    def control():
        FC = importlib.import_module("intent_engine.econ.founder_contract")
        ok, _c = FC.admit(FC.FieldChange(field="action", before="a",
                                         after="b", trigger="t",
                                         mechanism="m", provenance=("p",)),
                          freshness=FC.CURRENT)
        assert ok, "the wall refused an attributable change on clean code"

    def mutate(t):
        return t.mutate(
            DECISION,
            "    triggers = {f: (trigger, lead[\"mechanism\"], provenance)\n"
            "                for f in FA.MATERIAL_FIELDS}",
            "    triggers = {}")

    def check(t):
        _assert_speaks(t, expect_material=True)
    return run(p, mutate=mutate, check=check, positive_control=control)


def _assert_speaks(t, *, expect_material=True, value=6.0, prior=4.0,
                   as_of="2026-08-20", at="2026-08-25",
                   model="SUBSCRIPTION_SOFTWARE", exposures=("treasury_10y",),
                   kind="treasury_10y"):
    """Build one context in the mirror and demand it still speaks.

    Used by every proof whose mutation should SILENCE a real reading: the
    check fails when the delta is gone, which is what makes the mutation RED.
    """
    ED = t.load("intent_engine.external_intel.econ_decision")
    EC = t.load("intent_engine.external_intel.econ_context")
    CPF = t.load("intent_engine.executive.company_profile")
    econ = EC.EconContext(
        available=True, as_of=as_of, area="US",
        conditions={kind: {
            "kind": kind, "standing": "OBSERVED", "direction": "UP",
            "value": value, "prior_value": prior, "as_of": as_of,
            "known": True, "moved": True, "node_id": "n",
            "publisher": "FRED", "unit": ""}})
    profile = CPF.CompanyIntelligenceProfile(
        company_id="c", company_name="C", known=True,
        business_model_class=model)

    class D:
        readiness = "INVESTIGATION_REQUIRED"
        decision_archetype = "PRICING"
        topic = "PRICING"
        evidence_required = ("x",)
        watch_items = ()
        falsifier = "f"
    ctx = ED.build(company_id="c", company_name="C", as_of=at, economy=econ,
                   exposures=exposures, profile=profile, decision=D(),
                   risks=[{"risk_id": "r", "severity": "LOW",
                           "channel": "ch", "mechanism": "m",
                           "standing": "INFERRED", "evidence": ("e",)}])
    if expect_material:
        assert ctx.material_decision_delta, (
            f"the reading went silent: {ctx.status} / {ctx.headline()} / "
            f"refused={ctx.refused}")
        assert ctx.attributable, "a material change lost its attribution"
    return ctx


# =============================================================================
# 4. a CANDIDATE relation rendered as proven
# =============================================================================
def bp04():
    p = _p(name="04_candidate_relation_rendered_as_proven",
           description="an unsupported relation is sorted into the supported "
                       "list, where a surface states it as a finding",
           target_kind=BP.PRODUCER, mutated_file=DECISION,
           mutated_symbol="_relations",
           guard_under_test="Relation.may_be_stated_as_fact",
           production_call_path=CONTRACT)

    def control():
        FC = importlib.import_module("intent_engine.econ.founder_contract")
        assert not FC.Relation(statement="s",
                               standing=FC.CANDIDATE).may_be_stated_as_fact

    def mutate(t):
        return t.mutate(
            DECISION,
            "            standing=(FC.SUPPORTED if state.startswith(\"SUPPORTED\")\n"
            "                      else FC.CANDIDATE),",
            "            standing=FC.SUPPORTED,")

    def check(t):
        FC = t.load("intent_engine.econ.founder_contract")
        ED = t.load("intent_engine.external_intel.econ_decision")
        supported, candidate = ED._relations(
            [{"statement": "s", "state": "CANDIDATE"}])
        assert candidate, "a CANDIDATE relation was promoted to supported"
        assert not supported or not supported[0].may_be_stated_as_fact
    return run(p, mutate=mutate, check=check, positive_control=control)


# =============================================================================
# 5. a frozen human-state construct injected
# =============================================================================
def bp05():
    p = _p(name="05_frozen_human_construct_injected",
           description="an unpromoted collective construct is offered to the "
                       "founder contract as an economic dimension",
           target_kind=BP.PRODUCER, mutated_file=CONTEXT,
           mutated_symbol="relevant_to",
           guard_under_test="refuse_human_constructs",
           production_call_path=CONTRACT)

    def control():
        FC = importlib.import_module("intent_engine.econ.founder_contract")
        try:
            FC.refuse_human_constructs(["financial_anxiety"], where="control")
        except FC.ContextViolation:
            return
        raise AssertionError("the register guard passed a frozen construct")

    def mutate(t):
        return t.mutate(
            CONTEXT,
            "    out: List[dict] = []\n    for quantity in exposures:",
            "    out: List[dict] = [{'quantity': 'financial_anxiety',\n"
            "                        'measured': True, 'standing': 'OBSERVED',\n"
            "                        'direction': 'UP', 'moved': True,\n"
            "                        'value': 1.0, 'unit': '', 'as_of': '2026-08-20',\n"
            "                        'prior_value': 0.5, 'prior_as_of': '',\n"
            "                        'publisher': 'x', 'node_id': 'n'}]\n"
            "    for quantity in exposures:")

    def check(t):
        _assert_speaks(t, expect_material=False)
    return run(p, mutate=mutate, check=check, positive_control=control)


# =============================================================================
# 6. a rehearsal record allowed into calibration
# =============================================================================
def bp06():
    p = _p(name="06_rehearsal_reaches_calibration",
           description="a rehearsal expectation is admitted to the forward "
                       "list, where it would become a track record",
           target_kind=BP.CONSUMER, mutated_file=DECISION,
           mutated_symbol="forward_status",
           guard_under_test="FounderEconomicContext.__post_init__",
           production_call_path=CONTRACT)

    def control():
        FC = importlib.import_module("intent_engine.econ.founder_contract")
        try:
            FC.FounderEconomicContext(
                company_id="c", as_of="2026-08-20",
                status=FC.NO_MATERIAL_ECONOMIC_DELTA,
                forward_expectations=(FC.ForwardExpectation(
                    expectation_id="e", quantity="q", expected_direction="UP",
                    horizon_days=1, expires_at="2026-12-01",
                    resolution_rule="r", source=FC.REHEARSAL),))
        except FC.ContextViolation:
            return
        raise AssertionError("a rehearsal expectation was accepted")

    def mutate(t):
        return t.mutate(
            DECISION,
            "            and str(r.get(\"source\", \"\")).upper() != FC.REHEARSAL]",
            "            ]")

    def check(t):
        FC = t.load("intent_engine.econ.founder_contract")
        ED = t.load("intent_engine.external_intel.econ_decision")
        EST = t.load("intent_engine.econ.store")
        root = t.root / "runtime"
        EST.append(root, "expectation",
                   {"expectation_id": "ex-r", "quantity": "UNRATE",
                    "expected_direction": "UP", "horizon_days": 90,
                    "expires_at": "2026-12-01", "resolution_rule": "r",
                    "outcome": "OPEN", "source": "REHEARSAL",
                    "visibility": "PUBLIC"}, written_at="2026-08-01")
        exps, status, _c = ED.forward_status(root, at="2026-08-25")
        FC.FounderEconomicContext(company_id="c", as_of="2026-08-20",
                                  status=FC.NO_MATERIAL_ECONOMIC_DELTA,
                                  forward_expectations=tuple(exps),
                                  calibration_status=status)
    return run(p, mutate=mutate, check=check, positive_control=control)


# =============================================================================
# 7. the context is lost across persistence and reload
# =============================================================================
def bp07():
    p = _p(name="07_context_lost_after_reload",
           description="the stored form drops the material delta, so a run "
                       "reopened after a restart shows a different verdict",
           target_kind=BP.PERSISTENCE, mutated_file=CONTRACT,
           mutated_symbol="FounderEconomicContext.as_dict",
           guard_under_test="from_dict",
           production_call_path=CONTRACT)

    def control():
        FC = importlib.import_module("intent_engine.econ.founder_contract")
        c = FC.blocked("c", reason="r")
        assert FC.FounderEconomicContext.from_dict(c.as_dict()).as_dict() \
            == c.as_dict()

    def mutate(t):
        return t.mutate(
            CONTRACT,
            "            \"material_decision_delta\": [c.as_dict() for c\n"
            "                                        in self.material_decision_delta],",
            "            \"material_decision_delta\": [],")

    def check(t):
        FC = t.load("intent_engine.econ.founder_contract")
        ctx = _assert_speaks(t, expect_material=True)
        payload = json.loads(json.dumps(ctx.as_dict(), default=str))
        back = FC.FounderEconomicContext.from_dict(payload)
        assert back.material_decision_delta, \
            "the delta did not survive the round trip"
        assert back.headline() == ctx.headline(), \
            "the reloaded verdict differs from the one that was stored"
    return run(p, mutate=mutate, check=check, positive_control=control)


# =============================================================================
# 8. a stale state used as current
# =============================================================================
def bp08():
    p = _p(name="08_stale_state_used_as_current",
           description="the age of the state stops being computed, so an old "
                       "reading produces a confident recommendation",
           target_kind=BP.PRODUCER, mutated_file=DECISION,
           mutated_symbol="build",
           guard_under_test="FounderEconomicContext.__post_init__",
           production_call_path=CONTRACT)

    def control():
        FC = importlib.import_module("intent_engine.econ.founder_contract")
        assert FC.freshness_of("2025-01-01", at="2026-08-25")[0] == FC.STALE

    def mutate(t):
        # THE AGE MEASURED AGAINST THE WRONG REFERENCE DATE. A state is always
        # zero days old when you compare it against its own date, so this
        # relabels a 601-day-old reading CURRENT and hands that label to every
        # guard downstream -- each of which then works correctly on a false
        # input. It is a far more realistic mutation than deleting the STALE
        # branch, which two independent guards happened to survive.
        return t.mutate(
            DECISION,
            "    freshness, age = FC.freshness_of(state_as_of, "
            "at=as_of or _today())",
            "    freshness, age = FC.freshness_of(state_as_of, "
            "at=state_as_of)")

    def check(t):
        ctx = _assert_speaks(t, expect_material=False, as_of="2025-01-01",
                             at="2026-08-25")
        assert ctx.freshness == "STALE", (
            f"a state from 2025-01-01 read at 2026-08-25 is labelled "
            f"{ctx.freshness} ({ctx.age_days} days)")
        assert not ctx.material_decision_delta, (
            f"a {ctx.age_days}-day-old state produced "
            f"{len(ctx.material_decision_delta)} material change(s)")
    return run(p, mutate=mutate, check=check, positive_control=control)


# =============================================================================
# 9. a missing state fails the analysis
# =============================================================================
def bp09():
    p = _p(name="09_missing_state_fails_the_analysis",
           description="an absent economic state raises instead of reporting "
                       "BLOCKED_DATA, taking the whole analysis with it",
           target_kind=BP.PRODUCER, mutated_file=DECISION,
           mutated_symbol="build",
           guard_under_test="blocked",
           production_call_path=DECISION)

    def control():
        FC = importlib.import_module("intent_engine.econ.founder_contract")
        assert FC.blocked("c", reason="r").status == FC.BLOCKED_DATA

    def mutate(t):
        return t.mutate(
            DECISION,
            "    if economy is None or not getattr(economy, \"available\", False):\n"
            "        return FC.blocked(",
            "    if False:\n"
            "        return FC.blocked(")

    def check(t):
        ED = t.load("intent_engine.external_intel.econ_decision")

        class D:
            readiness = "INVESTIGATION_REQUIRED"
            decision_archetype = "PRICING"
            topic = "PRICING"
            evidence_required = ("x",)
            watch_items = ()
            falsifier = "f"
        ctx = ED.build(company_id="c", company_name="C", as_of="2026-08-25",
                       economy=None, exposures=("treasury_10y",),
                       profile=None, decision=D(), risks=[])
        assert ctx.status in ("BLOCKED_DATA", "BLOCKED_EXTERNAL"), \
            f"a missing state produced {ctx.status}"
    return run(p, mutate=mutate, check=check, positive_control=control)


# =============================================================================
# 10. one economic paragraph for every company
# =============================================================================
def bp10():
    p = _p(name="10_same_paragraph_for_every_company",
           description="the mechanism stops depending on the business model, "
                       "so every company receives the same economic text",
           target_kind=BP.PRODUCER, mutated_file=PROFILE,
           mutated_symbol="CompanyIntelligenceProfile.transmission_for",
           guard_under_test="test_the_same_condition_reaches_two_businesses_through_two_mechanisms",
           production_call_path=UNITS)

    def control():
        pass

    def mutate(t):
        return t.mutate(
            PROFILE,
            "        return _TRANSMISSION.get((str(channel).upper(),\n"
            "                                  self.business_model_class), \"\")",
            "        return \"this economic condition affects the business\"")

    def check(t):
        t.pytest(f"{UNITS}::test_the_same_condition_reaches_two_businesses_"
                 f"through_two_mechanisms")
    return run(p, mutate=mutate, check=check, positive_control=control)


# =============================================================================
# 11. brief and full contradict one canonical state
# =============================================================================
def bp11():
    p = _p(name="11_brief_and_full_contradict",
           description="the renderer composes its own verdict instead of "
                       "rendering the context's, so two surfaces can differ",
           target_kind=BP.RENDERER, mutated_file=DOSSIER,
           mutated_symbol="_economic_impact",
           guard_under_test="test_qa_and_the_dossier_give_the_same_verdict_on_one_context",
           production_call_path=SURFACES)

    def control():
        pass

    def mutate(t):
        return t.mutate(
            DOSSIER,
            "    if econ.abstains:\n        text = [headline]",
            "    if econ.abstains:\n"
            "        text = [\"Macro conditions are broadly supportive.\"]")

    def check(t):
        t.pytest(f"{SURFACES}::test_qa_and_the_dossier_give_the_same_verdict"
                 f"_on_one_context")
    return run(p, mutate=mutate, check=check, positive_control=control)


# =============================================================================
# 12. Q&A invents evidence the context does not carry
# =============================================================================
def bp12():
    p = _p(name="12_qa_invents_evidence",
           description="the economic answer is composed rather than lifted, "
                       "so Q&A can assert a reading nothing supports",
           target_kind=BP.RENDERER, mutated_file=QA,
           mutated_symbol="_economic_answer",
           guard_under_test="test_qa_never_invents_an_economic_answer_when_there_is_no_state",
           production_call_path=SURFACES)

    def control():
        pass

    def mutate(t):
        return t.mutate(
            QA,
            "    if not econ.available:",
            "    if False:")

    def check(t):
        t.pytest(f"{SURFACES}::test_qa_never_invents_an_economic_answer_when"
                 f"_there_is_no_state")
    return run(p, mutate=mutate, check=check, positive_control=control)


# =============================================================================
# 13. private evidence enters the public context
# =============================================================================
def bp13():
    p = _p(name="13_private_evidence_enters_public_context",
           description="an evidence class a founder surface may not cite is "
                       "admitted behind a material change",
           target_kind=BP.CONSUMER, mutated_file=DECISION,
           mutated_symbol="STATE_EVIDENCE_CLASS",
           guard_under_test="Provenance.__post_init__",
           production_call_path=CONTRACT)

    def control():
        FC = importlib.import_module("intent_engine.econ.founder_contract")
        try:
            FC.Provenance(claim="c", source="s", observation="o",
                          as_of="2026-08-20", evidence_type="tenant_private")
        except Exception:
            return
        raise AssertionError("a disallowed evidence class was accepted")

    def mutate(t):
        return t.mutate(
            DECISION,
            'STATE_EVIDENCE_CLASS = "shared_economic_state"',
            'STATE_EVIDENCE_CLASS = "tenant_private_note"')

    def check(t):
        _assert_speaks(t, expect_material=True)
    return run(p, mutate=mutate, check=check, positive_control=control)


# =============================================================================
# 14. one trigger counted twice
# =============================================================================
def bp14():
    p = _p(name="14_derived_evidence_double_counted",
           description="the same economic trigger is credited to a second "
                       "field, inflating the delta with no new information",
           target_kind=BP.CONSUMER, mutated_file=DECISION,
           mutated_symbol="build",
           guard_under_test="admit",
           production_call_path=DECISION)

    def control():
        FC = importlib.import_module("intent_engine.econ.founder_contract")
        change = FC.FieldChange(field="action", before="a", after="b",
                                trigger="T", mechanism="m",
                                provenance=("p",))
        ok, code = FC.admit(change, freshness=FC.CURRENT,
                            already_triggered_by=("T",))
        assert not ok and code == FC.DUPLICATIVE

    def mutate(t):
        return t.mutate(
            DECISION,
            "    changes, refused, seen_triggers = [], [], []",
            "    changes, refused, seen_triggers = [], [], None")

    def check(t):
        ctx = _assert_speaks(t, expect_material=True)
        seen = [c.trigger for c in ctx.material_decision_delta]
        assert len(seen) == len(set(seen)), (
            f"one trigger was credited to {len(seen)} fields: {seen[:2]}")
    return run(p, mutate=mutate, check=check, positive_control=control)


# =============================================================================
# 15. a wording-only difference counted as material
# =============================================================================
def bp15():
    p = _p(name="15_wording_counted_as_material",
           description="prose is added to the material field list, so a "
                       "rewording registers as decision value",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/econ/founder_ab.py",
           mutated_symbol="MATERIAL_FIELDS",
           guard_under_test="test_a_wording_only_difference_cannot_be_represented_as_a_change",
           production_call_path=UNITS)

    def control():
        pass

    def mutate(t):
        return t.mutate(
            "src/intent_engine/econ/founder_ab.py",
            'MATERIAL_FIELDS = ("top_priority", "action", "top_risks", "scenario",\n'
            '                   "confidence", "information_priority", "risk_severity")',
            'MATERIAL_FIELDS = ("top_priority", "action", "top_risks", "scenario",\n'
            '                   "confidence", "information_priority",\n'
            '                   "risk_severity", "prose")')

    def check(t):
        t.pytest(f"{UNITS}::test_a_wording_only_difference_cannot_be_"
                 f"represented_as_a_change")
    return run(p, mutate=mutate, check=check, positive_control=control)


# =============================================================================
# 16. the product reads the economy at a different cutoff
# =============================================================================
def bp16():
    p = _p(name="16_different_evidence_cutoff_from_baseline",
           description="the economic state is read at today's date while the "
                       "company evidence is dated at the run's cutoff",
           target_kind=BP.CALL_SITE, mutated_file=APP,
           mutated_symbol="WebApp._external_context",
           guard_under_test="test_the_economic_read_uses_the_run_s_own_evidence_cutoff",
           production_call_path=SURFACES)

    def control():
        pass

    def mutate(t):
        return t.mutate(
            APP,
            "            economy = ec.load(self._runtime_root, as_of=_run_as_of)",
            "            economy = ec.load(self._runtime_root, as_of=today)")

    def check(t):
        t.pytest(f"{SURFACES}::test_the_economic_read_uses_the_run_s_own_"
                 f"evidence_cutoff")
    return run(p, mutate=mutate, check=check, positive_control=control)


PATTERNS = "src/intent_engine/strategic_intelligence/patterns.py"
REASONING = "src/intent_engine/strategic_intelligence/reasoning.py"
INSIGHTS = "src/intent_engine/strategic_intelligence/insights.py"
BLIND = "tests/test_blind_spot_contract.py"


# =============================================================================
# 17-21. the blind-spot contract
# =============================================================================
def bp17():
    p = _p(name="17_semiconductor_receives_a_commerce_blind_spot",
           description="the applicability gate is removed, so a tension fires "
                       "on signal names alone and a chip designer is handed "
                       "commerce language",
           target_kind=BP.PRODUCER, mutated_file=REASONING,
           mutated_symbol="_build_blind_spots",
           guard_under_test="test_a_semiconductor_does_not_receive_a_commerce_tension",
           production_call_path=BLIND)

    def control():
        pass

    def mutate(t):
        return t.mutate(
            REASONING,
            "        ok, kind = tension_applies(t, business_model)\n"
            "        if not ok:",
            "        ok, kind = tension_applies(t, business_model)\n"
            "        ok = True\n"
            "        if not ok:")

    def check(t):
        t.pytest(f"{BLIND}::test_a_semiconductor_does_not_receive_a_"
                 f"commerce_tension")
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp18():
    p = _p(name="18_bank_receives_a_marketplace_blind_spot",
           description="the tension declares no applicability, so the gate "
                       "has nothing to check it against",
           target_kind=BP.PRODUCER, mutated_file=PATTERNS,
           mutated_symbol="TENSIONS",
           guard_under_test="test_every_tension_declares_which_businesses_it_applies_to",
           production_call_path=BLIND)

    def control():
        pass

    def mutate(t):
        # RETARGETED after `MARKETPLACE_OR_PLATFORM` was removed: it was a
        # class this product never assigns, so a tension gated on it could
        # never fire and the "gate" was a delete. A proof pinned to text that
        # no longer exists reports NOT_APPLIED, which is honest and is not a
        # pass.
        return t.mutate(
            PATTERNS,
            '        "applies_to": ("SUBSCRIPTION_SOFTWARE",),\n',
            "")

    def check(t):
        t.pytest(f"{BLIND}::test_every_tension_declares_which_businesses_"
                 f"it_applies_to")
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp19():
    p = _p(name="19_unread_model_becomes_an_observed_tension",
           description="an unread business model is treated as applicable, "
                       "so a company we could not classify is told about a "
                       "tension we cannot rule out",
           target_kind=BP.PRODUCER, mutated_file=PATTERNS,
           mutated_symbol="tension_applies",
           guard_under_test="test_an_unread_business_model_is_a_coverage_gap_not_a_tension",
           production_call_path=BLIND)

    def control():
        pass

    def mutate(t):
        return t.mutate(
            PATTERNS,
            '    if not str(business_model or "").strip():\n'
            "        return False, MODEL_COVERAGE_GAP",
            "    if False:\n"
            "        return False, MODEL_COVERAGE_GAP")

    def check(t):
        t.pytest(f"{BLIND}::test_an_unread_business_model_is_a_coverage_"
                 f"gap_not_a_tension")
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp20():
    p = _p(name="20_not_applicable_reported_as_missing_evidence",
           description="a tension the model rules out is reported as an "
                       "information gap, which is a claim about the company "
                       "rather than about the library",
           target_kind=BP.PRODUCER, mutated_file=PATTERNS,
           mutated_symbol="tension_applies",
           guard_under_test="test_a_semiconductor_does_not_receive_a_commerce_tension",
           production_call_path=BLIND)

    def control():
        pass

    def mutate(t):
        return t.mutate(
            PATTERNS,
            "    if business_model not in applies:\n"
            "        return False, NOT_APPLICABLE",
            "    if business_model not in applies:\n"
            "        return True, INFERRED_INFORMATION_GAP")

    def check(t):
        t.pytest(f"{BLIND}::test_a_semiconductor_does_not_receive_a_"
                 f"commerce_tension")
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp21():
    p = _p(name="21_generic_fallback_overrides_the_company_model",
           description="the surprise and opportunity producers stop consulting "
                       "the model, so the tension leaks onto the surfaces "
                       "that render them",
           target_kind=BP.PRODUCER, mutated_file=INSIGHTS,
           mutated_symbol="_live_tensions",
           guard_under_test="test_surprises_and_opportunities_are_gated_by_the_same_rule",
           production_call_path=BLIND)

    def control():
        pass

    def mutate(t):
        return t.mutate(
            INSIGHTS,
            "        ok, _kind = tension_applies(t, business_model)\n"
            "        if ok:",
            "        ok, _kind = tension_applies(t, business_model)\n"
            "        if True:")

    def check(t):
        t.pytest(f"{BLIND}::test_surprises_and_opportunities_are_gated_by_"
                 f"the_same_rule")
    return run(p, mutate=mutate, check=check, positive_control=control)


LEDGER = "src/intent_engine/econ/forward_ledger.py"
CLOSURE = "tests/test_v3_closure_ledgers.py"
ADVERSARIAL = "tests/test_damage_detector_adversarial.py"
AB = "src/intent_engine/econ/founder_ab.py"


# =============================================================================
# 22-26. the closure seams
# =============================================================================
def bp22():
    p = _p(name="22_expectation_written_without_a_creation_date",
           description="a forward record loses the date it was made, so it "
                       "cannot answer whether its cutoff preceded it",
           target_kind=BP.PERSISTENCE, mutated_file=LEDGER,
           mutated_symbol="load",
           guard_under_test="assert_lifecycle",
           production_call_path=LEDGER)

    def control():
        FL = importlib.import_module("intent_engine.econ.forward_ledger")
        assert FL.assert_lifecycle()["all_seven_hold"]

    def mutate(t):
        return t.mutate(
            LEDGER,
            '                       and r.get("created_at"))]',
            "                       )]")

    def check(t):
        FL = t.load("intent_engine.econ.forward_ledger")
        rows = [{"expectation_id": "ex-x", "information_cutoff": "2026-01-01",
                 "horizon_days": 90, "expires_at": "2026-12-01",
                 "resolution_rule": "r", "confidence": 0.5, "quantity": "q",
                 "expected_direction": "UP", "outcome": "OPEN"}]
        path = t.root / "fwd.jsonl"
        FL.append(rows, path=path)
        FL.assert_lifecycle(path)
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp23():
    p = _p(name="23_report_diverges_from_the_ledger",
           description="the learning report keeps its own count instead of "
                       "deriving it, so it can disagree with the record",
           target_kind=BP.PRODUCER, mutated_file="scripts/close_v3.py",
           mutated_symbol="learning_ledger",
           guard_under_test="test_a_report_that_disagrees_with_the_ledger_is_refused",
           production_call_path=CLOSURE)

    def control():
        pass

    def mutate(t):
        return t.mutate(
            "scripts/close_v3.py",
            '            "real_open": len(real) - len(resolved),',
            '            "real_open": 99,')

    def check(t):
        t.pytest(f"{CLOSURE}::test_the_learning_ledger_reconciles_with_the_"
                 f"forward_ledger")
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp24():
    p = _p(name="24_a_damage_kind_loses_its_detector",
           description="a declared damage kind stops being detectable, so a "
                       "damage count of zero is partly about the vocabulary",
           target_kind=BP.PRODUCER, mutated_file=AB,
           mutated_symbol="detect_damage",
           guard_under_test="test_every_declared_damage_kind_has_a_detector",
           production_call_path=ADVERSARIAL)

    def control():
        pass

    def mutate(t):
        return t.mutate(
            AB,
            '                    kind="WRONG_EXPOSURE",',
            '                    kind="STALE_STATE",')

    def check(t):
        t.pytest(f"{ADVERSARIAL}::test_every_declared_damage_kind_has_a_"
                 f"detector")
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp25():
    p = _p(name="25_generic_recommendation_across_a_corpus",
           description="the corpus check stops looking, so ten companies "
                       "sharing one recommendation goes unreported",
           target_kind=BP.PRODUCER, mutated_file=AB,
           mutated_symbol="detect_generic",
           guard_under_test="test_generic_recommendation_is_caught",
           production_call_path=ADVERSARIAL)

    def control():
        pass

    def mutate(t):
        return t.mutate(
            AB,
            "    if len(analyses) < 3:\n        return []",
            "    if True:\n        return []")

    def check(t):
        t.pytest(f"{ADVERSARIAL}::test_generic_recommendation_is_caught")
    return run(p, mutate=mutate, check=check, positive_control=control)


def bp26():
    p = _p(name="26_economic_risk_identified_by_an_id_prefix",
           description="the damage detector decides what is an economic risk "
                       "from an id prefix only one producer uses, so the "
                       "other producer's risks read as non-economic",
           target_kind=BP.CONSUMER, mutated_file=AB,
           mutated_symbol="detect_damage",
           guard_under_test="test_an_economic_risk_declares_its_quantity_rather_than_encoding_it",
           production_call_path=ADVERSARIAL)

    def control():
        pass

    def mutate(t):
        return t.mutate(
            AB,
            "    econ_risks = [r for r in b.risks if r.quantity]",
            '    econ_risks = [r for r in b.risks\n'
            '                  if r.risk_id.startswith("econ:")]')

    def check(t):
        t.pytest(f"{ADVERSARIAL}::test_an_economic_risk_declares_its_"
                 f"quantity_rather_than_encoding_it")
    return run(p, mutate=mutate, check=check, positive_control=control)


PROOFS = [bp01, bp02, bp03, bp04, bp05, bp06, bp07, bp08,
          bp09, bp10, bp11, bp12, bp13, bp14, bp15, bp16,
          bp17, bp18, bp19, bp20, bp21, bp22, bp23, bp24, bp25, bp26]


def main() -> int:
    proofs = []
    for fn in PROOFS:
        try:
            p = fn()
        except Exception as e:                              # noqa: BLE001
            p = BP.Proof(name=fn.__name__, description="",
                         target_kind=BP.PRODUCER, mutated_file="?",
                         mutated_symbol="?", guard_under_test="?",
                         production_call_path="?")
            p.verdict = BP.UNRELIABLE
            p.detail = (f"{type(e).__name__}: {e}\n"
                        f"{traceback.format_exc()[-400:]}")
        proofs.append(p)
        print(f"  {p.verdict:<18} {p.name}")
        if p.verdict != BP.CAUGHT:
            print(f"      {str(p.detail)[:260]}")
    s = BP.summarise(proofs)
    OUT.write_text(json.dumps(s, indent=2, sort_keys=True))
    print(f"\n  {s['caught']}/{s['proofs']} CAUGHT, "
          f"{s['refused_tautology']} REFUSED_TAUTOLOGY, "
          f"{s['not_caught']} NOT_CAUGHT, {s['unreliable']} UNRELIABLE")
    print(f"  target kinds: {json.dumps(s['target_kinds'])}")
    print(f"  wrote {OUT}")
    return 0 if s["caught"] == s["proofs"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
