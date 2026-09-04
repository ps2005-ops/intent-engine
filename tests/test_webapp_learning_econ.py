"""`/learning` answers the eleven questions from the shared economic core.

WHY THE QUESTIONS ARE ASSERTED RATHER THAN THE ANSWERS
-------------------------------------------------------
The answers depend on what the market engine has published, which is
different on every deployment and on every day. What must not vary is that
every question is ASKED and that an unanswerable one renders its absence and
a reason -- because a question that quietly disappears from the page is
indistinguishable from a question the engine has answered.

AND THE SURFACE MUST STAY AN OPERATOR SURFACE
----------------------------------------------
Nothing here may show a position, a book, a scheduler or an accuracy figure.
The last of those is asserted directly: before the declared minimum forward
sample, the calibration line must say PRE-CALIBRATION and must not contain a
percentage.
"""
import pytest

from intent_engine.econ import store as EST
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from tests.test_webapp_journeys import Client, _login, _no_network


@pytest.fixture
def app(tmp_path):
    config = AppConfig(env="test", secret="s" * 40,
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl",
                       ci_store_path=tmp_path / "ci.jsonl")
    application = WebApp(config, now_fn=lambda: 1000.0,
                         transport=_no_network, resolver=False)
    application.auth.create_user("founder@example.com", "password123")
    return application


def _published(app):
    """One real economic state, through the market-side producer."""
    from intent_engine.market import econ_bridge as MB
    from intent_engine.market import macro_state as MS
    observations = [
        MS.MacroObservation(
            state_kind=MS.INFLATION, series_id="CPI", label="consumer prices",
            value=333.9, unit="index", standing=MS.OBSERVED, area=MS.US,
            reference_period="2026-06-01", published_at="2026-06-15",
            source="a statistical agency"),
        MS.MacroObservation(
            state_kind=MS.INFLATION, series_id="CPI", label="consumer prices",
            value=334.4, unit="index", standing=MS.OBSERVED, area=MS.US,
            reference_period="2026-07-01", published_at="2026-07-15",
            source="a statistical agency"),
    ]
    return MB.publish_state(observations=observations, as_of="2026-08-27",
                            runtime_root=app._runtime_root)


def test_every_question_is_asked_even_when_the_core_is_empty(app):
    got = app._econ_intelligence("2026-08-27")
    asked = set(got["answers"])
    assert asked == {key for key, _ in app._ECON_QUESTIONS}
    assert len(asked) == 11
    for key, question in app._ECON_QUESTIONS:
        entry = got["answers"][key]
        assert entry["absent"] is True
        assert entry["reason"], (
            f"{question!r} is unanswerable and gives no reason; a blank is "
            "indistinguishable from a question nobody thought to ask")


def test_an_empty_core_says_so_rather_than_rendering_zeroes(app):
    block = app._econ_learning_block("2026-08-27")
    assert "not answerable yet" in block
    assert "no economic state has been published" in block


def test_a_published_state_answers_the_questions_it_can(app):
    report = _published(app)
    assert report["nodes_published"] == 2
    got = app._econ_intelligence("2026-08-27")
    assert got["available"] is True
    assert not got["answers"]["what_changed"]["absent"], (
        "a state with a measured, moving condition answered nothing about "
        "what changed")
    assert "inflation" in got["answers"]["what_changed"]["answer"]
    # Unanswerable questions stay visible, with their reason.
    assert got["answers"]["resolved"]["absent"] is True
    assert got["answers"]["resolved"]["reason"]


def test_the_page_never_reports_an_accuracy_before_the_minimum_sample(app):
    _published(app)
    block = app._econ_learning_block("2026-08-27")
    assert "PRE-CALIBRATION" in block
    assert "30 required" in block
    for banned in ("win rate", "Sharpe", "% correct", "alpha"):
        assert banned.lower() not in block.lower()


def test_the_block_carries_no_position_book_or_scheduler_DATA(app):
    """Asserted on the payload, not the prose.

    The rendered block SAYS the words "position", "book" and "scheduler" --
    in the sentence explaining that it shows none of them. Banning the words
    would fail on the disclaimer while a real leak inside a number went
    through, so the check is over the structured answers the page renders
    from, which is where a leak would actually arrive.
    """
    import json
    _published(app)
    data = app._econ_intelligence("2026-08-27")
    payload = json.dumps(data, default=str).lower()
    for banned in ("portfolio_value", "open_positions", "paper_book",
                   "win_rate", "sharpe", "orders_submitted", "strategy_id",
                   "leaderboard", "funnel"):
        assert banned not in payload, (
            f"{banned!r} reached the operator learning surface's data")
    # And the state it reads is allowlisted at its own boundary, so a new
    # upstream field cannot ride in unnoticed.
    from intent_engine.econ import state as ES
    from intent_engine.econ import store as EST
    snapshot = EST.load(app._runtime_root, "state_snapshot")[-1]
    ES.validate(snapshot)


def test_the_surface_is_gated_against_a_session_less_visitor(app):
    status, _, _ = Client(app).request("GET", "/learning")
    assert status.startswith("303") or status.startswith("404"), status


def test_a_logged_in_operator_sees_the_shared_core_section(app):
    _published(app)
    client = Client(app)
    _login(client)
    status, _, body = client.request("GET", "/learning")
    assert status.startswith("200"), status
    assert "Shared economic core" in body
    assert "PRE-CALIBRATION" in body
    # The eleven questions all render, answered or explicitly not.
    for _, question in app._ECON_QUESTIONS:
        assert question in body, f"{question!r} vanished from the page"
