"""A-WIRE-001. The causal question the runtime actually asks, and its refusals.

Two populations of test, kept apart the way the code keeps them apart. The
EVENT_DERIVED cases use ledger rows shaped like the live ones and prove the
engine reaches a precise refusal. The SYNTHETIC_TEST cases fabricate panels to
prove every state is reachable — legitimate, and never counted as evidence
about the world.
"""
from __future__ import annotations

import pytest

from intent_engine.market import causal_diagnostics as CD
from intent_engine.market import causal_question as CQ
from intent_engine.market import synthetic_control as SC


def _event(company="acme", evidence_id="ev1", when="2026-03-02",
           kind="LAYOFF"):
    return {"record": "evidence", "subject_company": company,
            "evidence_id": evidence_id, "observed_at": when,
            "available_at": when, "evidence_type": kind,
            "source": "a filing"}


def _obs(series_id, period, value, *, kind="MARKET_RATE", unit="%"):
    return {"record": "macro_observation", "series_id": series_id,
            "reference_period": period, "value": value,
            "state_kind": kind, "unit": unit}


def _panel_rows(series, *, kind="MARKET_RATE", unit="%"):
    out = []
    for series_id, values in series.items():
        for i, v in enumerate(values):
            out.append(_obs(series_id, f"2026-01-{i + 1:02d}", v,
                            kind=kind, unit=unit))
    return out


# --- the contract refuses what it cannot represent -----------------------------

def test_a_question_must_declare_where_it_came_from():
    with pytest.raises(CQ.QuestionRejected):
        CQ.CausalQuestion(
            causal_question_id="q", company_id="acme",
            treatment_event_id="e", treatment_type="LAYOFF",
            treatment_at="2026-03-02", outcome_variable="acme:path",
            question_origin="MADE_UP")


def test_a_question_with_no_treatment_date_is_not_a_question():
    with pytest.raises(CQ.QuestionRejected):
        CQ.CausalQuestion(
            causal_question_id="q", company_id="acme",
            treatment_event_id="e", treatment_type="LAYOFF",
            treatment_at="", outcome_variable="acme:path",
            question_origin=CQ.EVENT_DERIVED)


def test_a_question_must_name_its_outcome_before_the_data_are_seen():
    with pytest.raises(CQ.QuestionRejected):
        CQ.CausalQuestion(
            causal_question_id="q", company_id="acme",
            treatment_event_id="e", treatment_type="LAYOFF",
            treatment_at="2026-03-02", outcome_variable="",
            question_origin=CQ.EVENT_DERIVED)


def test_synthetic_questions_do_not_describe_the_world():
    real = CQ.CausalQuestion(
        causal_question_id="q", company_id="a", treatment_event_id="e",
        treatment_type="LAYOFF", treatment_at="2026-03-02",
        outcome_variable="x", question_origin=CQ.EVENT_DERIVED)
    fake = CQ.CausalQuestion(
        causal_question_id="q", company_id="a", treatment_event_id="e",
        treatment_type="LAYOFF", treatment_at="2026-03-02",
        outcome_variable="x", question_origin=CQ.SYNTHETIC_TEST)
    assert real.describes_the_world
    assert not fake.describes_the_world


# --- the treatment date is read, never searched for ----------------------------

def test_the_treatment_date_is_the_events_own_date():
    got = CQ.questions_from_events([_event(when="2026-03-02")], as_of="2026-08")
    assert len(got) == 1
    assert got[0].treatment_at == "2026-03-02"
    assert got[0].treatment_type == "LAYOFF"
    assert got[0].question_origin == CQ.EVENT_DERIVED


def test_an_event_with_no_date_anchors_nothing():
    """A treatment assigned to 'today' because the record had no date is a
    fabricated treatment."""
    row = _event()
    row["observed_at"] = ""
    assert CQ.questions_from_events([row], as_of="2026-08") == []


def test_an_event_with_no_subject_anchors_nothing():
    row = _event()
    row["subject_company"] = ""
    assert CQ.questions_from_events([row], as_of="2026-08") == []


def test_questions_are_capped_without_being_selected():
    events = [_event(evidence_id=f"e{i}", when=f"2026-03-{i + 1:02d}")
              for i in range(10)]
    got = CQ.questions_from_events(events, as_of="2026-08", limit=3)
    assert [q.treatment_event_id for q in got] == ["e0", "e1", "e2"]


# --- comparability is decided on metadata, never on the numbers ----------------

def test_a_different_quantity_is_not_a_donor():
    rows = _panel_rows({"treated": [1.0] * 10})
    rows += [_obs("other", f"2026-01-{i + 1:02d}", 5.0, kind="INFLATION",
                  unit="index") for i in range(10)]
    included, decisions = CQ.comparable_units(rows, outcome_variable="treated")
    assert included == []
    assert any("not 'MARKET_RATE'" in d.reason for d in decisions)


def test_a_different_unit_is_not_a_donor():
    rows = _panel_rows({"treated": [1.0] * 10})
    rows += [_obs("other", f"2026-01-{i + 1:02d}", 5.0, unit="bn USD")
             for i in range(10)]
    included, decisions = CQ.comparable_units(rows, outcome_variable="treated")
    assert included == []
    assert any("not '%'" in d.reason for d in decisions)


def test_a_different_frequency_is_not_a_donor():
    rows = _panel_rows({"treated": [1.0] * 20})
    rows += [_obs("monthly", f"2026-01-{i + 1:02d}", 5.0) for i in range(3)]
    included, decisions = CQ.comparable_units(rows, outcome_variable="treated")
    assert included == []
    assert any("ragged panel" in d.reason for d in decisions)


def test_every_rejection_is_recorded_with_its_reason():
    """A thin pool must be visibly thin, not silently small."""
    rows = _panel_rows({"treated": [1.0] * 10, "peer": [2.0] * 10})
    rows += [_obs("wrong", f"2026-01-{i + 1:02d}", 5.0, kind="HOUSING",
                  unit="units") for i in range(10)]
    included, decisions = CQ.comparable_units(rows, outcome_variable="treated")
    assert included == ["peer"]
    assert {d.unit for d in decisions} == {"peer", "wrong"}
    assert all(d.reason.strip() for d in decisions)


# --- the live shape: treatments exist, outcomes do not -------------------------

def test_a_real_event_with_no_measured_outcome_is_panel_unavailable():
    """THE LIVE CASE.

    The ledger holds 423 dated company events and zero numeric values attached
    to any company. This is what the cycle actually reaches, and it names the
    one input that would change it.
    """
    question = CQ.questions_from_events([_event()], as_of="2026-08")[0]
    got = CQ.resolve(question, [], as_of="2026-08-10")
    assert got.state == CQ.PANEL_UNAVAILABLE
    assert got.missing_prerequisite == CQ.NO_OUTCOME_SERIES
    assert "acme" in got.information_requirement
    assert not got.estimated


def test_a_refusal_is_not_an_effect_of_zero():
    question = CQ.questions_from_events([_event()], as_of="2026-08")[0]
    row = CQ.resolve(question, []).as_dict()
    assert row["estimated"] is False
    assert row["fit"] is None
    assert row["diagnostics"] is None
    assert "not a zero effect" in row["note"]


def test_a_refusal_names_the_information_that_would_change_it():
    question = CQ.questions_from_events([_event()], as_of="2026-08")[0]
    got = CQ.resolve(question, [])
    assert got.information_requirement
    assert "series" in got.information_requirement


def test_no_comparable_unit_is_a_donor_problem_not_a_missing_panel():
    rows = _panel_rows({"acme:outcome_path": [1.0, 2.0, 1.5, 2.5, 2.0, 3.0,
                                              2.5, 3.5, 3.0, 4.0]})
    question = CQ.questions_from_events([_event()], as_of="2026-08")[0]
    got = CQ.resolve(question, rows)
    assert got.state == CQ.DONOR_SUPPORT_INSUFFICIENT
    assert got.missing_prerequisite == CQ.NO_COMPARABLE_UNITS


def test_a_pool_too_thin_for_a_placebo_stops_before_fitting():
    """A fit that could be produced and could not be defended is not produced.

    With n donors the most extreme achievable placebo rank is 1/(n+1), so below
    the pool size that can clear the threshold there is nothing to adjudicate.
    """
    series = {"acme:outcome_path": [float(i) for i in range(20)]}
    for j in range(3):
        series[f"peer{j}"] = [float(i) + j for i in range(20)]
    question = CQ.questions_from_events([_event(when="2026-01-12")],
                                        as_of="2026-08")[0]
    got = CQ.resolve(question, _panel_rows(series))
    assert got.state == CQ.DONOR_SUPPORT_INSUFFICIENT
    assert got.missing_prerequisite == CQ.TOO_FEW_DONORS
    assert got.fit is None
    assert "shortfall" in got.information_requirement


def test_a_short_pre_period_is_a_history_problem_not_a_donor_problem():
    series = {"acme:outcome_path": [float(i) for i in range(20)]}
    for j in range(12):
        series[f"peer{j}"] = [float(i) + 0.3 * j for i in range(20)]
    question = CQ.questions_from_events([_event(when="2026-01-04")],
                                        as_of="2026-08")[0]
    got = CQ.resolve(question, _panel_rows(series))
    assert got.state == CQ.PANEL_UNAVAILABLE
    assert got.missing_prerequisite == CQ.SHORT_PRE_PERIOD
    assert "more observation" in got.information_requirement


def test_a_treatment_after_the_last_observation_has_no_post_period():
    series = {"acme:outcome_path": [float(i) for i in range(20)]}
    for j in range(12):
        series[f"peer{j}"] = [float(i) + 0.3 * j for i in range(20)]
    question = CQ.questions_from_events([_event(when="2026-06-01")],
                                        as_of="2026-08")[0]
    got = CQ.resolve(question, _panel_rows(series))
    assert got.state == CQ.PANEL_UNAVAILABLE
    assert got.missing_prerequisite == CQ.NO_POST_PERIOD


# --- the reachable end of the machine, on labelled synthetic panels ------------

def _synthetic_panel(effect):
    """A panel wide enough to adjudicate, built to prove a state is reachable.

    Labelled SYNTHETIC_TEST and excluded from every real count by
    `summarise`. Donors share three latent factors, which is both what makes
    them a usable pool and the only situation in which a synthetic control is
    the right method.
    """
    length, treatment = 24, 12
    factors = [[10 + 2 * ((i * 7) % 5) for i in range(length)],
               [20 - ((i * 3) % 4) for i in range(length)],
               [15 + ((i * 5) % 6) for i in range(length)]]
    series = {}
    for j in range(14):
        a = 1 / 3 + 0.08 * ((j * 5 % 7) - 3) / 3
        b = 1 / 3 + 0.08 * ((j * 3 % 5) - 2) / 2
        c = 1.0 - a - b
        own = [0.4 * ((j + i * 3) % 5) for i in range(length)]
        series[f"peer{j}"] = [a * factors[0][i] + b * factors[1][i]
                              + c * factors[2][i] + own[i]
                              for i in range(length)]
    treated = [0.5 * series["peer0"][i] + 0.3 * series["peer1"][i]
               + 0.2 * series["peer2"][i] + (0.15 if i % 2 else -0.15)
               + (effect if i >= treatment else 0.0)
               for i in range(length)]
    series["subject"] = treated
    question = CQ.CausalQuestion(
        causal_question_id="synthetic", company_id="subject",
        treatment_event_id="none", treatment_type="SYNTHETIC",
        treatment_at=f"2026-01-{treatment + 1:02d}",
        outcome_variable="subject", question_origin=CQ.SYNTHETIC_TEST)
    return question, _panel_rows(series)


def test_a_wide_panel_with_a_large_effect_reaches_an_estimate():
    question, rows = _synthetic_panel(effect=40.0)
    got = CQ.resolve(question, rows)
    assert got.state in (CQ.ESTIMATE_SUPPORTED, CQ.ESTIMATE_BOUNDED,
                         CQ.PLACEBO_UNRESOLVED), got.detail
    if got.estimated:
        assert got.fit is not None and got.fit.fitted
        assert got.diagnostics is not None
        assert got.donors_included >= 9


def test_the_estimate_cannot_be_supported_on_statistics_alone():
    """Two of a synthetic control's critical assumptions are facts about how
    the study was run. An untested critical assumption forbids a causal
    reading, so ESTIMATE_SUPPORTED is unreachable here — by design."""
    question, rows = _synthetic_panel(effect=40.0)
    got = CQ.resolve(question, rows)
    if got.estimated:
        assert got.state == CQ.ESTIMATE_BOUNDED


def test_a_panel_with_no_effect_does_not_reach_a_supported_estimate():
    """The negative control for the whole machine."""
    question, rows = _synthetic_panel(effect=0.0)
    got = CQ.resolve(question, rows)
    assert got.state != CQ.ESTIMATE_SUPPORTED


# --- persistence, three shapes, and telemetry ----------------------------------

def test_the_persisted_row_carries_its_origin_and_its_record():
    question = CQ.questions_from_events([_event()], as_of="2026-08")[0]
    row = CQ.resolve(question, []).as_dict()
    assert row["record"] == "causal_resolution"
    assert row["contract"] == CQ.CONTRACT
    assert row["question_origin"] == CQ.EVENT_DERIVED
    assert row["describes_the_world"] is True
    assert row["question"]["treatment_at"] == "2026-03-02"


def test_the_row_is_json_serialisable_and_keeps_its_donor_decisions():
    import json

    question, rows = _synthetic_panel(effect=40.0)
    row = CQ.resolve(question, rows).as_dict()
    again = json.loads(json.dumps(row))
    assert again["state"] == row["state"]
    assert again["donors_included"] == row["donors_included"]


def test_summary_excludes_synthetic_questions_from_the_real_count():
    """THE assertion that stops the test suite reporting itself as a finding."""
    real = CQ.resolve(CQ.questions_from_events([_event()], as_of="x")[0], [])
    question, rows = _synthetic_panel(effect=40.0)
    fake = CQ.resolve(question, rows)
    got = CQ.summarise([real, fake])
    assert got["questions"] == 1
    assert got["synthetic_excluded"] == 1
    assert got["by_state"][CQ.PANEL_UNAVAILABLE] == 1


def test_summary_names_every_state_and_prerequisite_even_at_zero():
    got = CQ.summarise([])
    assert set(got["by_state"]) == set(CQ.STATES)
    assert set(got["by_missing_prerequisite"]) == set(CQ.PREREQUISITES)
    assert all(v == 0 for v in got["by_state"].values())
    assert got["questions"] == 0


def test_summary_surfaces_the_information_that_would_unblock_the_engine():
    events = [_event(company=f"c{i}", evidence_id=f"e{i}") for i in range(3)]
    resolutions = [CQ.resolve(q, [])
                   for q in CQ.questions_from_events(events, as_of="x")]
    got = CQ.summarise(resolutions)
    assert got["questions"] == 3
    assert got["estimated"] == 0
    assert got["by_missing_prerequisite"][CQ.NO_OUTCOME_SERIES] == 3
    assert len(got["information_requirements"]) == 3


# --- the production caller exists ----------------------------------------------

def test_the_cycle_step_actually_calls_the_causal_path():
    """Reads the parse tree, not the source text.

    The first version of this test asserted that the strings
    "causal_question" and "CQ.resolve" appeared in
    `inspect.getsource(knowledge_step)`. A break proof that disabled the caller
    left it GREEN, because the strings were still there — which is the
    guard-matches-the-comment failure this repository has recorded before, and
    it was sitting inside the test for the node whose whole purpose is that a
    capability has a real production caller.

    An AST walk cannot be satisfied by a comment, and `_reachable` refuses a
    call parked under `if False:`.
    """
    import ast
    import pathlib as _pathlib

    from intent_engine.market import steps

    tree = ast.parse(_pathlib.Path(steps.__file__).read_text(encoding="utf-8"))
    function = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef)
                    and n.name == "knowledge_step")

    def _reachable(node):
        """Nodes that actually run: not under `if False` or `while False`."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.If, ast.While)):
                test = child.test
                dead = (isinstance(test, ast.Constant) and not test.value)
                if dead:
                    yield from _reachable(ast.Module(body=child.orelse,
                                                     type_ignores=[]))
                    continue
            yield child
            yield from _reachable(child)

    nodes = list(_reachable(function))

    imported = [n for n in nodes if isinstance(n, ast.ImportFrom)
                and any(a.name == "causal_question" for a in n.names)]
    assert imported, "knowledge_step does not import causal_question"

    calls = [n for n in nodes if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)
             and n.func.attr in ("resolve", "questions_from_events",
                                 "summarise")
             and isinstance(n.func.value, ast.Name)
             and n.func.value.id == "CQ"]
    assert {c.func.attr for c in calls} >= {"questions_from_events", "resolve"}

    written = [n for n in nodes if isinstance(n, ast.Subscript)
               and isinstance(n.slice, ast.Constant)
               and n.slice.value == "causal_resolution"]
    assert written, "knowledge_step never writes payload['causal_resolution']"


def test_the_caller_assertion_fails_when_the_call_is_parked_under_if_false():
    """The negative control for the guard above.

    Without this, an assertion that accepted anything would satisfy the test
    and the break proof would go on reporting NOT_CAUGHT for the wrong reason.
    """
    import ast

    tree = ast.parse(
        "def knowledge_step(ctx):\n"
        "    if False:\n"
        "        from . import causal_question as CQ\n"
        "        payload['causal_resolution'] = CQ.resolve(q, o)\n"
        "    return {}\n")
    function = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef))

    def _reachable(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.If, ast.While)):
                if isinstance(child.test, ast.Constant) and not child.test.value:
                    yield from _reachable(ast.Module(body=child.orelse,
                                                     type_ignores=[]))
                    continue
            yield child
            yield from _reachable(child)

    nodes = list(_reachable(function))
    assert not [n for n in nodes if isinstance(n, ast.ImportFrom)
                and any(a.name == "causal_question" for a in n.names)]


def test_the_step_emits_a_causal_block_from_ledger_rows(monkeypatch):
    """The step's own fold, exercised on rows shaped like the live ledger."""
    from intent_engine.market import causal_question as module

    rows = [_event(company=f"c{i}", evidence_id=f"e{i}") for i in range(3)]
    observations = _panel_rows({"BOC_X": [1.0] * 10})
    questions = module.questions_from_events(rows, as_of="2026-08-10",
                                             limit=25)
    resolutions = [module.resolve(q, observations, as_of="2026-08-10")
                   for q in questions]
    block = {**module.summarise(resolutions),
             "resolutions": [r.as_dict() for r in resolutions[:5]]}
    assert block["questions"] == 3
    assert block["estimated"] == 0
    assert block["by_state"][module.PANEL_UNAVAILABLE] == 3
    assert len(block["resolutions"]) == 3
    assert all(r["record"] == "causal_resolution" for r in block["resolutions"])


# --- the report surface --------------------------------------------------------

def test_the_report_carries_the_causal_block():
    """Calls the real projection. An earlier version of this test fell back to
    grepping report.py for the string when it could not find the function —
    which is the guard-reads-the-comment failure this codebase has recorded
    before, written into a test for the node that exists to prevent it."""
    from intent_engine.market import report

    question = CQ.questions_from_events([_event()], as_of="2026-08")[0]
    resolutions = [CQ.resolve(question, [])]
    knowledge = {"causal_resolution": {
        **CQ.summarise(resolutions),
        "resolutions": [r.as_dict() for r in resolutions]}}
    block = report._knowledge_summary(knowledge)["causal_resolution"]
    assert block["questions"] == 1
    assert block["estimated"] == 0
    assert block["by_missing_prerequisite"][CQ.NO_OUTCOME_SERIES] == 1
    assert block["information_requirements"]


def test_the_report_block_is_empty_rather_than_absent_when_nothing_ran():
    """Two different nothings, and the surface already distinguished them.

    An empty knowledge payload returns a whole-block `present: False` sentinel
    with a reason — the knowledge step did not run. A payload that ran and
    carried no causal block returns an empty causal block inside a present
    summary. This test asserted the first shape for the second case and was
    wrong about the code, not the other way round.
    """
    from intent_engine.market import report

    absent = report._knowledge_summary({})
    assert absent["present"] is False
    assert absent["reason"]
    assert "causal_resolution" not in absent

    ran = report._knowledge_summary({"macro_state": {"error": "feed down"}})
    assert ran["causal_resolution"] == {}


def test_the_report_shows_the_synthetic_count_even_at_zero():
    """A surface that showed it only when non-zero could not tell a reader
    that no fabricated question was mixed into the real ones."""
    from intent_engine.market import report

    question = CQ.questions_from_events([_event()], as_of="2026-08")[0]
    knowledge = {"causal_resolution": CQ.summarise([CQ.resolve(question, [])])}
    block = report._knowledge_summary(knowledge)["causal_resolution"]
    assert block["synthetic_excluded"] == 0


def test_the_surface_shows_zero_estimates_beside_the_reason():
    """Zero estimates alone is indistinguishable from the capability not
    running. The prerequisite counts are what make it a finding."""
    events = [_event(company=f"c{i}", evidence_id=f"e{i}") for i in range(4)]
    resolutions = [CQ.resolve(q, [])
                   for q in CQ.questions_from_events(events, as_of="x")]
    got = CQ.summarise(resolutions)
    assert got["estimated"] == 0
    assert sum(got["by_missing_prerequisite"].values()) == 4
    assert got["information_requirements"]
