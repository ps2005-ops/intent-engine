#!/usr/bin/env python3
"""§43: twelve mutations against the V2 reasoning layer's invariants.

Every proof declares its mutated symbol, the guard expected to fire, and the
production call path. `breakproof.Proof.validate()` REFUSES the proof before
it runs if the mutated symbol IS the guard -- so a proof that removes a check
and then calls it cannot be written here.

Each proof also runs a POSITIVE CONTROL on clean code first. A guard that
fires before the mutation is UNRELIABLE, not passing: a no-op mutation that
"passes" silently is the failure mode a break-proof harness exists to have.
"""
from __future__ import annotations

import importlib
import json
import pathlib
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from intent_engine.econ import breakproof as BP              # noqa: E402

OUT = REPO / "reports" / "break_proofs_asi2.json"
_SUB = ("We sell software on an annual subscription and recognise revenue "
        "ratably over the contract term.")


class Tree:
    """A private mirror of src/. Mutations never touch the shared worktree."""

    def __init__(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="bp_asi2_"))
        shutil.copytree(REPO / "src", self.root / "src")

    def path(self, rel):
        return self.root / "src" / rel[4:] if rel.startswith("src/") else \
            self.root / rel

    def mutate(self, rel, old, new):
        p = self.path(rel)
        s = p.read_text()
        if old not in s:
            return 0, 0
        before = len(s)
        p.write_text(s.replace(old, new, 1))
        return before, len(p.read_text())

    def load(self, module):
        for k in list(sys.modules):
            if k.startswith("intent_engine"):
                del sys.modules[k]
        sys.path.insert(0, str(self.root / "src"))
        try:
            return importlib.import_module(module)
        finally:
            sys.path.pop(0)

    def clean(self):
        shutil.rmtree(self.root, ignore_errors=True)
        for k in list(sys.modules):
            if k.startswith("intent_engine"):
                del sys.modules[k]
        sys.path.insert(0, str(REPO / "src"))


def run(proof, *, mutate, check, control):
    try:
        proof.validate()
        BP.assert_call_path_exists(REPO, proof)
    except BP.TautologicalProof as e:
        proof.verdict, proof.detail = BP.REFUSED, str(e)[:400]
        return proof
    for k in list(sys.modules):
        if k.startswith("intent_engine"):
            del sys.modules[k]
    try:
        control()
    except Exception as e:                                   # noqa: BLE001
        proof.verdict = BP.UNRELIABLE
        proof.detail = (f"the guard fired on CLEAN code: "
                        f"{type(e).__name__}: {e}")[:300]
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
        except Exception as e:                               # noqa: BLE001
            proof.verdict = BP.CAUGHT
            proof.detail = f"{type(e).__name__}: {e}"[:300]
            return proof
        proof.verdict = BP.NOT_CAUGHT
        proof.detail = "the mutation was applied and nothing refused it"
        return proof
    except BP.TautologicalProof as e:
        proof.verdict, proof.detail = BP.REFUSED, str(e)[:300]
        return proof
    finally:
        t.clean()


def _p(**kw):
    return BP.Proof(**kw)


def _select(mod_tree=None, *, name, text):
    mod = (mod_tree.load("intent_engine.executive.analysis_selection")
           if mod_tree else
           importlib.import_module("intent_engine.executive.analysis_selection"))
    body = f"{text} {_SUB}"
    return mod.select(name=name, published_text=body, evidence_text=body)


_MENTIONS = ("Carriers depend on freight capacity. Supply chains rely on "
             "lead times holding. Shippers depend on customs clearance.")
_OPAQUE = "We provide innovative solutions for the modern enterprise."
_PRICED = "Pricing is based on the number of managed endpoints."


# --- 01 the subject rule ----------------------------------------------------

def bp01():
    p = _p(name="01_subject_rule_dropped",
           description="a page ABOUT carriers becomes a dependency OF the "
                       "company, which is project44's confusion generalised",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/executive/decision_object.py",
           mutated_symbol="_subject_patterns",
           guard_under_test="test_mentioning_a_thing_is_not_depending_on_it",
           production_call_path="tests/test_decision_is_measured_in_this_"
                                "company_s_own_unit.py")

    def control():
        DO = importlib.import_module(
            "intent_engine.executive.decision_object")
        obj = DO.build(company="Freightwatch", published_text=_MENTIONS)
        if obj.dependencies:
            raise AssertionError("clean code already read a foreign subject")

    def mutate(t):
        return t.mutate("src/intent_engine/executive/decision_object.py",
                        'return rf"(?:{_FIRST_PERSON}|{full}(?:’s|\'s)?)"',
                        'return r"[a-z]+"')

    def check(t):
        DO = t.load("intent_engine.executive.decision_object")
        obj = DO.build(company="Freightwatch", published_text=_MENTIONS)
        assert not obj.dependencies, (
            f"a foreign subject's dependency was read: "
            f"{[d.value for d in obj.dependencies]}")
    return run(p, mutate=mutate, check=check, control=control)


# --- 02 the rehearsal wall --------------------------------------------------

def _docs():
    return [
        {"filed": "2024-02-01", "form": "10-K",
         "text": f"Acme is built for IT operations teams. {_SUB}"},
        {"filed": "2025-03-01", "form": "10-K",
         "text": (f"Acme is built for security operations teams. Pricing is "
                  f"based on the number of managed endpoints. {_SUB}")},
    ]


def bp02():
    p = _p(name="02_hindsight_wall_removed",
           description="the T0 reading is given a document filed after T0, so "
                       "the rehearsal becomes hindsight wearing a date",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/executive/learning_rehearsal.py",
           mutated_symbol="_text_before",
           guard_under_test="test_the_t0_reading_cannot_see_a_document_filed_"
                            "after_t0",
           production_call_path="tests/test_historical_learning_rehearsal_is_"
                                "labelled_and_walled.py")

    def control():
        LR = importlib.import_module(
            "intent_engine.executive.learning_rehearsal")
        seen = []
        LR.rehearse(company="Acme", documents=_docs(),
                    read=lambda x: seen.append(x) or _Read())
        if "managed endpoints" in (seen[0] if seen else ""):
            raise AssertionError("clean code already leaked the later filing")

    def mutate(t):
        return t.mutate("src/intent_engine/executive/learning_rehearsal.py",
                        "kept = [r for r in _dated(documents) if r[0] <= edge]",
                        "kept = list(_dated(documents))")

    def check(t):
        LR = t.load("intent_engine.executive.learning_rehearsal")
        seen = []
        LR.rehearse(company="Acme", documents=_docs(),
                    read=lambda x: seen.append(x) or _Read())
        assert "managed endpoints" not in (seen[0] if seen else ""), (
            "the T0 reading was given text filed after T0")
    return run(p, mutate=mutate, check=check, control=control)


class _Read:
    archetype = "PRICING"
    decision_question = "q"
    question_basis = {}
    information_priorities = ()


# --- 03 the rehearsal label -------------------------------------------------

def bp03():
    p = _p(name="03_rehearsal_label_forgeable",
           description="a rehearsal row emits a caller-supplied label, so it "
                       "can reach a calibration table as a forward result",
           target_kind=BP.PERSISTENCE,
           mutated_file="src/intent_engine/executive/learning_rehearsal.py",
           mutated_symbol="LearningDecisionDelta.as_dict",
           guard_under_test="test_the_label_cannot_be_overridden_by_"
                            "construction",
           production_call_path="tests/test_historical_learning_rehearsal_is_"
                                "labelled_and_walled.py")

    def control():
        LR = importlib.import_module(
            "intent_engine.executive.learning_rehearsal")
        if LR.LearningDecisionDelta(label="REAL_FORWARD").as_dict()["label"] \
                != LR.HISTORICAL_REHEARSAL:
            raise AssertionError("clean code already honoured a forged label")

    def mutate(t):
        return t.mutate(
            "src/intent_engine/executive/learning_rehearsal.py",
            '        out["evidence_that_caused_change"] = list(\n'
            '            self.evidence_that_caused_change)\n'
            '        out["label"] = HISTORICAL_REHEARSAL\n        return out',
            '        out["evidence_that_caused_change"] = list(\n'
            '            self.evidence_that_caused_change)\n'
            '        return out')

    def check(t):
        LR = t.load("intent_engine.executive.learning_rehearsal")
        assert LR.LearningDecisionDelta(
            label="REAL_FORWARD").as_dict()["label"] == \
            LR.HISTORICAL_REHEARSAL, "a forged label survived to the row"
    return run(p, mutate=mutate, check=check, control=control)


# --- 04 the name is not a ground -------------------------------------------

def bp04():
    p = _p(name="04_company_name_counted_as_a_ground",
           description="the name is left in before the name-swap test, so "
                       "every reading scores GROUNDED on its own title",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/executive/strategic_delta.py",
           mutated_symbol="ground.stripped",
           guard_under_test="test_grounding_does_not_count_the_company_name_"
                            "as_a_ground",
           production_call_path="tests/test_decision_is_measured_in_this_"
                                "company_s_own_unit.py")

    def control():
        SD = importlib.import_module("intent_engine.executive.strategic_delta")
        DO = importlib.import_module("intent_engine.executive.decision_object")
        obj = DO.build(company="Law Firm Software",
                       published_text="Law Firm Software is built for "
                                      "boutique law firms.")
        g = SD.ground("For Law Firm Software: what to charge, and for what?",
                      company="Law Firm Software", decision_object=obj)
        if g.verdict == SD.GROUNDED:
            raise AssertionError("clean code already grounded on the name")

    def mutate(t):
        return t.mutate("src/intent_engine/executive/strategic_delta.py",
                        "    terms, sources = company_terms(decision_object, "
                        "evidence_terms)",
                        "    stripped = text\n"
                        "    terms, sources = company_terms(decision_object, "
                        "evidence_terms)")

    def check(t):
        SD = t.load("intent_engine.executive.strategic_delta")
        DO = t.load("intent_engine.executive.decision_object")
        obj = DO.build(company="Law Firm Software",
                       published_text="Law Firm Software is built for "
                                      "boutique law firms.")
        g = SD.ground("For Law Firm Software: what to charge, and for what?",
                      company="Law Firm Software", decision_object=obj)
        assert g.verdict != SD.GROUNDED, (
            f"a reading was grounded on the company's own name: {g.grounds}")
    return run(p, mutate=mutate, check=check, control=control)


# --- 05 the fallback must not be silent ------------------------------------

def bp05():
    p = _p(name="05_class_prior_fallback_silent",
           description="the basis sentence stops saying the variables came "
                       "from the class, so a category reading looks like a "
                       "company reading",
           target_kind=BP.RENDERER,
           mutated_file="src/intent_engine/executive/analysis_selection.py",
           mutated_symbol="_basis_sentence",
           guard_under_test="test_an_unread_company_keeps_the_class_prior_"
                            "and_says_that_it_did",
           production_call_path="tests/test_decision_is_measured_in_this_"
                                "company_s_own_unit.py")

    def control():
        sel = _select(name="Opaque Co", text=_OPAQUE)
        if "not from this company" not in sel.question_basis["why"]:
            raise AssertionError("clean code already hid the fallback")

    def mutate(t):
        return t.mutate("src/intent_engine/executive/analysis_selection.py",
                        'f"business normally decides, not from this '
                        'company: "',
                        'f"business normally decides: "')

    def check(t):
        sel = _select(t, name="Opaque Co", text=_OPAQUE)
        assert "not from this company" in sel.question_basis["why"], (
            f"the class-prior fallback went unstated: "
            f"{sel.question_basis['why'][:160]}")
    return run(p, mutate=mutate, check=check, control=control)


# --- 06 a slot may not be claimed that was not established -----------------

def bp06():
    p = _p(name="06_unestablished_slot_claimed_as_the_company_s",
           description="question_basis credits the company with a slot it "
                       "never filled, which is the one outcome forbidden",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/executive/analysis_selection.py",
           mutated_symbol="question_basis",
           guard_under_test="test_an_unread_company_keeps_the_class_prior_"
                            "and_says_that_it_did",
           production_call_path="tests/test_decision_is_measured_in_this_"
                                "company_s_own_unit.py")

    def control():
        sel = _select(name="Opaque Co", text=_OPAQUE)
        if sel.question_basis["slots_from_company"]:
            raise AssertionError("clean code already claimed an empty slot")

    def mutate(t):
        return t.mutate(
            "src/intent_engine/executive/analysis_selection.py",
            "    (from_company if getattr(unit, \"known\", False) else "
            "from_prior).append(",
            "    (from_company if True else from_prior).append(")

    def check(t):
        sel = _select(t, name="Opaque Co", text=_OPAQUE)
        assert not sel.question_basis["slots_from_company"], (
            "a slot nothing established was credited to the company")
    return run(p, mutate=mutate, check=check, control=control)


# --- 07 the buyer may not reach a decision it does not bear on -------------

def bp07():
    p = _p(name="07_buyer_injected_into_every_decision",
           description="naming a customer inside a capital question adds a "
                       "noun and no meaning -- template injection",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/executive/analysis_selection.py",
           mutated_symbol="_BUYER_BEARS_ON",
           guard_under_test="test_a_buyer_does_not_reach_a_decision_it_does_"
                            "not_bear_on",
           production_call_path="tests/test_v2_does_not_reopen_the_forty_s_"
                                "closed_defects.py")

    def control():
        A = importlib.import_module(
            "intent_engine.executive.analysis_selection")
        if "CAPITAL_ALLOCATION" in A._BUYER_BEARS_ON:
            raise AssertionError("clean code already injects the buyer")

    def mutate(t):
        return t.mutate("src/intent_engine/executive/analysis_selection.py",
                        '_BUYER_BEARS_ON = ("PRICING", "PRODUCTIZATION", '
                        '"CUSTOMER_SEGMENT",',
                        '_BUYER_BEARS_ON = ("CAPITAL_ALLOCATION", "PRICING", '
                        '"PRODUCTIZATION", "CUSTOMER_SEGMENT",')

    def check(t):
        A = t.load("intent_engine.executive.analysis_selection")
        assert "CAPITAL_ALLOCATION" not in A._BUYER_BEARS_ON, (
            "the buyer reached a decision its identity does not bear on")
    return run(p, mutate=mutate, check=check, control=control)


# --- 08 a billing unit measures a decision, it does not select one ---------

def bp08():
    p = _p(name="08_billing_unit_selects_the_archetype",
           description="stating a price unit moves WHICH decision the company "
                       "faces, making the repair a new keyword channel",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/executive/analysis_selection.py",
           mutated_symbol="_score_archetypes",
           guard_under_test="test_a_billing_unit_does_not_change_which_"
                            "decision_is_faced",
           production_call_path="tests/test_v2_does_not_reopen_the_forty_s_"
                                "closed_defects.py")

    def control():
        a = _select(name="Unit Co", text="We provide software to enterprises.")
        b = _select(name="Unit Co",
                    text=f"We provide software to enterprises. {_PRICED}")
        if a.archetype != b.archetype:
            raise AssertionError("clean code already lets the unit select")

    def mutate(t):
        return t.mutate(
            "src/intent_engine/executive/analysis_selection.py",
            '    shown = _evidence_archetypes(own_text)',
            '    shown = _evidence_archetypes(own_text)\n'
            '    if "managed endpoints" in (own_text or "").lower():\n'
            '        shown["M&A"] = (9, ("managed endpoints",))')

    def check(t):
        a = _select(t, name="Unit Co", text="We provide software to "
                                            "enterprises.")
        b = _select(t, name="Unit Co",
                    text=f"We provide software to enterprises. {_PRICED}")
        assert a.archetype == b.archetype, (
            f"stating a billing unit changed the decision: "
            f"{a.archetype} -> {b.archetype}")
    return run(p, mutate=mutate, check=check, control=control)


# --- 09 an ungrounded reading must ask for something -----------------------

def bp09():
    p = _p(name="09_ungrounded_reading_asks_for_nothing",
           description="a company we could not read gets a confident question "
                       "and no next step -- the frozen 40's 29 companies",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/executive/strategic_delta.py",
           mutated_symbol="information_priorities",
           guard_under_test="test_an_ungrounded_reading_names_what_would_"
                            "have_to_be_learned",
           production_call_path="tests/test_decision_is_measured_in_this_"
                                "company_s_own_unit.py")

    def control():
        sel = _select(name="Opaque Co", text=_OPAQUE)
        if not sel.information_priorities:
            raise AssertionError("clean code already asks for nothing")

    def mutate(t):
        return t.mutate("src/intent_engine/executive/strategic_delta.py",
                        "    return tuple(rows[:limit])",
                        "    return ()")

    def check(t):
        sel = _select(t, name="Opaque Co", text=_OPAQUE)
        assert sel.information_priorities, (
            "nothing was established and nothing was asked for")
    return run(p, mutate=mutate, check=check, control=control)


# --- 10 a buyer that names everybody is not a buyer ------------------------

def bp10():
    p = _p(name="10_generic_buyer_accepted",
           description='"built for businesses" is accepted as this company\'s '
                       "buyer, which names nobody",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/executive/decision_object.py",
           mutated_symbol="_GENERIC_BUYER",
           guard_under_test="test_a_buyer_that_names_everybody_is_refused",
           production_call_path="tests/test_decision_is_measured_in_this_"
                                "company_s_own_unit.py")

    def control():
        DO = importlib.import_module(
            "intent_engine.executive.decision_object")
        obj = DO.build(company="Anyco",
                       published_text="Anyco is built for businesses of all "
                                      "sizes.")
        if obj.buyer.known:
            raise AssertionError("clean code already accepted a generic buyer")

    def mutate(t):
        return t.mutate(
            "src/intent_engine/executive/decision_object.py",
            "company companies business businesses organisation organisations "
            "organization", "zzz")

    def check(t):
        DO = t.load("intent_engine.executive.decision_object")
        obj = DO.build(company="Anyco",
                       published_text="Anyco is built for businesses of all "
                                      "sizes.")
        assert not obj.buyer.known, (
            f"a buyer naming everybody was accepted: {obj.buyer.value!r}")
    return run(p, mutate=mutate, check=check, control=control)


# --- 11 marketing copy is not a buyer --------------------------------------

def bp11():
    p = _p(name="11_marketing_adjective_becomes_a_buyer",
           description='"built for the best experience" yields a BUYER of '
                       '"best experience", which is a promise about a website',
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/executive/decision_object.py",
           mutated_symbol="_EVALUATIVE",
           guard_under_test="test_marketing_adjectives_do_not_become_a_buyer",
           production_call_path="tests/test_decision_is_measured_in_this_"
                                "company_s_own_unit.py")

    def control():
        DO = importlib.import_module(
            "intent_engine.executive.decision_object")
        obj = DO.build(company="Anyco",
                       published_text="Anyco is built for the best experience "
                                      "on every device, and we mean it.")
        if obj.buyer.known and "best" in obj.buyer.value.lower():
            raise AssertionError("clean code already read marketing copy")

    def mutate(t):
        return t.mutate("src/intent_engine/executive/decision_object.py",
                        '_EVALUATIVE = frozenset("""\nbest better great good '
                        'ideal perfect right leading innovative modern',
                        '_EVALUATIVE = frozenset("""\nzzzplaceholder')

    def check(t):
        DO = t.load("intent_engine.executive.decision_object")
        obj = DO.build(company="Anyco",
                       published_text="Anyco is built for the best experience "
                                      "on every device, and we mean it.")
        assert not (obj.buyer.known and "best" in obj.buyer.value.lower()), (
            f"marketing copy became a buyer: {obj.buyer.value!r}")
    return run(p, mutate=mutate, check=check, control=control)


# --- 13 the subject anchor on the buyer rules ------------------------------

def bp13():
    p = _p(name="13_buyer_read_from_a_foreign_subject",
           description="a sentence about somebody else's tooling becomes who "
                       "this company sells to, and the page calls it GROUNDED",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/executive/decision_object.py",
           mutated_symbol="_first_match.needs_subject",
           guard_under_test="test_a_buyer_is_not_read_from_a_sentence_about_"
                            "somebody_else",
           production_call_path="tests/test_decision_is_measured_in_this_"
                                "company_s_own_unit.py")
    # The live fixture ("the rest of the group") is now refused by the
    # ANAPHORIC guard as well, so it no longer isolates the subject anchor.
    # This sentence has a foreign subject and a perfectly well-formed
    # population as its object, so only the subject rule can refuse it.
    text = ("The tools and infrastructure in this campaign are widely shared "
            "and are used by ransomware operators, according to researchers.")

    def control():
        DO = importlib.import_module(
            "intent_engine.executive.decision_object")
        if DO.build(company="Arctic Wolf", published_text=text).buyer.known:
            raise AssertionError("clean code already read a foreign subject")

    def mutate(t):
        return t.mutate("src/intent_engine/executive/decision_object.py",
                        "            if needs_subject and not names_itself:",
                        "            if False:")

    def check(t):
        DO = t.load("intent_engine.executive.decision_object")
        obj = DO.build(company="Arctic Wolf", published_text=text)
        assert not obj.buyer.known, (
            f"a buyer was read from a sentence about somebody else: "
            f"{obj.buyer.value!r}")
    return run(p, mutate=mutate, check=check, control=control)


# --- 14 the word boundaries under the subject anchor -----------------------

def bp14():
    p = _p(name="14_first_person_without_word_boundaries",
           description='"we" matches inside "however", so every sentence on '
                       "the internet names the company in the first person",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/executive/decision_object.py",
           mutated_symbol="_FIRST_PERSON",
           guard_under_test="test_the_first_person_pattern_requires_word_"
                            "boundaries",
           production_call_path="tests/test_decision_is_measured_in_this_"
                                "company_s_own_unit.py")

    def control():
        import re as _re
        DO = importlib.import_module(
            "intent_engine.executive.decision_object")
        if _re.search(DO._subject_patterns("Acme"), "however"):
            raise AssertionError("clean code already matches inside a word")

    def mutate(t):
        return t.mutate(
            "src/intent_engine/executive/decision_object.py",
            '_FIRST_PERSON = r"(?<![a-z])(?:we|our|ours|us)(?![a-z])"',
            '_FIRST_PERSON = r"(?:we|our|ours|us)"')

    def check(t):
        import re as _re
        DO = t.load("intent_engine.executive.decision_object")
        assert not _re.search(DO._subject_patterns("Acme"), "however"), (
            "the first-person pattern matched inside 'however'")
    return run(p, mutate=mutate, check=check, control=control)


# --- 12 the delta comparator must be a real second reading -----------------

def bp12():
    p = _p(name="12_delta_compared_against_a_placeholder",
           description="the prior question becomes a constant, so the delta "
                       "measures the placeholder and not the class prior",
           target_kind=BP.PRODUCER,
           mutated_file="src/intent_engine/executive/analysis_selection.py",
           mutated_symbol="select.prior_question",
           guard_under_test="test_the_delta_comparator_is_a_real_second_"
                            "reading",
           production_call_path="tests/test_decision_is_measured_in_this_"
                                "company_s_own_unit.py")

    def control():
        sel = _select(name="Procore",
                      text="Pricing is based on annual construction volume.")
        if "For Procore" not in sel.delta.prior_question:
            raise AssertionError("clean code already uses a placeholder")

    def mutate(t):
        return t.mutate(
            "src/intent_engine/executive/analysis_selection.py",
            "    prior_question = _decision_question(profile, archetype, "
            "facts, None)",
            '    prior_question = "the class prior question"')

    def check(t):
        sel = _select(t, name="Procore",
                      text="Pricing is based on annual construction volume.")
        assert "For Procore" in sel.delta.prior_question, (
            f"the comparator is not a real reading: "
            f"{sel.delta.prior_question!r}")
    return run(p, mutate=mutate, check=check, control=control)


# --- 15/16: the two found live on the twenty-five --------------------------

def bp15():
    p = _p(name="15_unrecognisable_legal_name_shown_alone",
           description="a person types 1Password and every heading reads "
                       "AgileBits Inc., which shares no word with it",
           target_kind=BP.RENDERER,
           mutated_file="src/intent_engine/company_ingestion/name_entry.py",
           mutated_symbol="resolve.company_name",
           guard_under_test="test_a_legal_name_sharing_no_word_with_the_"
                            "typed_name_carries_it",
           production_call_path="tests/test_a_reader_can_tell_it_is_the_"
                                "right_company.py")

    def control():
        NE = importlib.import_module(
            "intent_engine.company_ingestion.name_entry")
        E = importlib.import_module("intent_engine.company_ingestion.entities")
        prof = next(x for x in E.REGISTRY if x.entity_id == "onepassword")
        if "1Password" not in NE._recognisable(prof):
            raise AssertionError("clean code already drops the typed name")

    def mutate(t):
        return t.mutate("src/intent_engine/company_ingestion/name_entry.py",
                        "            EXACT_MATCH, company_name=_recognisable"
                        "(profile),",
                        "            EXACT_MATCH, company_name=profile."
                        "legal_name,")

    def check(t):
        NE = t.load("intent_engine.company_ingestion.name_entry")
        import inspect
        src = inspect.getsource(NE.resolve)
        assert "_recognisable(profile)" in src, (
            "the run's display name is the bare legal name again")
    return run(p, mutate=mutate, check=check, control=control)


def bp16():
    p = _p(name="16_quote_ends_on_a_joining_word",
           description="a truncated quotation ends on 'and', so the reader is "
                       "left holding a conjunction",
           target_kind=BP.RENDERER,
           mutated_file="src/intent_engine/adaptive/spans.py",
           mutated_symbol="_drop_dangling",
           guard_under_test="test_a_truncated_quote_does_not_end_on_a_"
                            "joining_word",
           production_call_path="tests/test_a_reader_can_tell_it_is_the_"
                                "right_company.py")
    body = ("Being CISO for a security technology vendor can be an "
            "interesting position My job combines the usual CISO "
            "responsibilities alongside daily self and team development "
            "across every region we operate in")

    def control():
        SP = importlib.import_module("intent_engine.adaptive.spans")
        out = SP.trim_to_word(body, 95).rstrip(" \u2026").rstrip()
        if out.split()[-1].lower() in SP._DANGLING:
            raise AssertionError("clean code already ends on a joining word")

    def mutate(t):
        # A SHORT, ESCAPE-FREE ANCHOR. The full return line carries an
        # ellipsis escape, and matching it through two levels of quoting
        # silently produced a pattern that never matched -- NOT_APPLIED
        # reported as NOT_CAUGHT once the bytes did change elsewhere.
        return t.mutate("src/intent_engine/adaptive/spans.py",
                        "return _drop_dangling(head[:cut]",
                        "return (head[:cut]")

    def check(t):
        SP = t.load("intent_engine.adaptive.spans")
        out = SP.trim_to_word(body, 95).rstrip(" \u2026").rstrip()
        last = out.split()[-1].lower().strip(",;:")
        assert last not in SP._DANGLING, f"quote ends on {last!r}"
    return run(p, mutate=mutate, check=check, control=control)


def main() -> int:
    proofs = [bp01(), bp02(), bp03(), bp04(), bp05(), bp06(),
              bp07(), bp08(), bp09(), bp10(), bp11(), bp12(),
              bp13(), bp14(), bp15(), bp16()]
    rows = []
    for p in proofs:
        rows.append({"name": p.name, "verdict": p.verdict,
                     "detail": p.detail, "target_kind": p.target_kind,
                     "mutated_symbol": p.mutated_symbol,
                     "guard_under_test": p.guard_under_test,
                     "bytes_before": p.bytes_before,
                     "bytes_after": p.bytes_after})
        print(f"{p.name:48s} {p.verdict:18s} {p.detail[:70]}", flush=True)
    held = sum(1 for r in rows if r["verdict"] == BP.CAUGHT)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"contract": "break_proofs_asi2.v1", "held": held,
         "total": len(rows), "proofs": rows}, indent=2))
    print(f"\nHELD {held}/{len(rows)}  ->  {OUT}")
    return 0 if held == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
