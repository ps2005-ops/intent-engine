"""D14. A second run of the same company must not report a first observation.

Live on 554e317 the SECOND Cloudflare run of one session rendered, on one
card: "This is the baseline reading. There is no earlier view to compare it
against yet." · "10 source(s) we had not seen before" · "This did not add to
what the system knows."

Two defects wearing one symptom, and the order of attack matters. The lookup
is traced FIRST: fixing `hero`'s wording while `_prior_run` silently returns
None would have produced a card that reads correctly and is still comparing
against nothing -- the same shape as `DossierStore.previous` not existing
while its caller probed for it with `hasattr`, and as
`second_iteration.compare` having no production caller at all. Both of those
were green for months.
"""
import io

import pytest

from intent_engine.strategic_intelligence import second_iteration as SI
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from tests.test_strategic_intelligence import _live_transport


class _Client:
    def __init__(self, app):
        self.app, self.cookie = app, ""

    def request(self, method, path, body=""):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": self.cookie,
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}
        payload = b"".join(self.app(env, lambda s, h: out.update(
            status=s, headers=h))).decode()
        for key, value in out["headers"]:
            if key == "Set-Cookie" and value.startswith("sid="):
                self.cookie = ("" if "Max-Age=0" in value
                               else value.split(";")[0])
        return out["status"], dict(out["headers"]), payload

    def sid(self):
        return self.cookie.split("=", 1)[1] if self.cookie else None

    def csrf(self):
        return self.app.auth.csrf_token(self.sid())


@pytest.fixture
def app(tmp_path):
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    autorun_sources=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    return WebApp(cfg, transport=_live_transport, resolver=False)


def _analyse(client, company="Acme", website="https://acme.example"):
    status, headers, _ = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={client.csrf()}&company_name={company}"
        f"&website={website}")
    assert status.startswith("303"), status
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    # Drive it to a terminal state. A run still in flight redirects every
    # analysis surface to /progress, and asserting on that redirect is how a
    # check ends up passing against a page it never read.
    client.request("GET", f"/runs/{run_id}")
    return run_id


def _fresh(client, run_id):
    """Ask explicitly for another analysis of the same company.

    A plain re-submit CANNOT produce a second run: the id is
    `ci-run:{subject}:{user}:{as_of}` and `as_of` was truncated to the day, so
    the same company analysed twice by the same person on one day is one run.
    That is a good default and it is also why no reader could ever reach a
    second iteration -- and why `/fresh`, whose entire purpose is "give me
    another one", returned the run it was asked to replace.
    """
    status, headers, _ = client.request(
        "POST", f"/runs/{run_id}/fresh", f"csrf={client.csrf()}")
    assert status.startswith("303"), status
    return headers["Location"].split("/runs/")[1].split("/")[0]


@pytest.fixture
def two_runs(app):
    """Two runs of the SAME company, in one session, in order."""
    c = _Client(app)
    c.request("POST", "/demo")
    first = _analyse(c)
    second = _fresh(c, first)
    c.request("GET", f"/runs/{second}")
    assert first != second, (
        "an explicit fresh analysis returned the same run id, so a second "
        "observation of a company is unreachable")
    return c, first, second


def test_a_plain_resubmit_still_dedupes_to_one_run(app):
    """The default must stay. A refresh must not pay for the analysis twice."""
    c = _Client(app)
    c.request("POST", "/demo")
    assert _analyse(c) == _analyse(c), (
        "two identical submissions created two runs; the day-granular "
        "dedupe that protects against double-submits is gone")


def test_the_owner_index_actually_contains_both_runs(app, two_runs):
    """ARROW 1. Before blaming the lookup, prove its input exists."""
    c, first, second = two_runs
    session = app.auth.session(c.sid())
    owned = list(app.web_store.runs_owned_by(session["user_id"]))
    assert first in owned and second in owned, (
        f"the ownership index does not hold both runs: {owned}")
    assert owned.index(first) < owned.index(second), (
        "the ownership index does not preserve temporal order, so 'strictly "
        "earlier' cannot be read from it")


def test_the_prior_run_lookup_finds_the_earlier_run(app, two_runs):
    """ARROW 2. The defect, named. This is what returned None live."""
    c, first, second = two_runs
    session = app.auth.session(c.sid())
    prior_id, prior_report = app._prior_run(session, second)
    assert prior_id == first, (
        f"_prior_run returned {prior_id!r} for the second run of the same "
        f"company; the earlier run is {first!r}")
    assert isinstance(prior_report, dict) and prior_report


def test_the_first_run_has_no_prior(app, two_runs):
    """The wall must not invent one backwards."""
    c, first, _second = two_runs
    session = app.auth.session(c.sid())
    prior_id, _ = app._prior_run(session, first)
    assert prior_id is None, (
        f"the FIRST run was given {prior_id!r} as a prior; a later run must "
        f"never be used as an earlier one")


def test_a_different_company_is_never_used_as_a_prior(app):
    """§4. A Caterpillar prior must never be offered for Cloudflare."""
    c = _Client(app)
    c.request("POST", "/demo")
    _analyse(c, "Caterpillar", "https://caterpillar.example")
    other = _analyse(c, "Cloudflare", "https://cloudflare.example")
    session = app.auth.session(c.sid())
    prior_id, _ = app._prior_run(session, other)
    assert prior_id is None, (
        "a run of a different company was accepted as the prior")


def test_a_stranger_s_run_is_never_used_as_a_prior(app):
    """A cross-tenant prior is a leak wearing a delta."""
    owner = _Client(app)
    owner.request("POST", "/demo")
    _analyse(owner)
    stranger = _Client(app)
    stranger.request("POST", "/demo")
    theirs = _analyse(stranger)
    session = app.auth.session(stranger.sid())
    prior_id, _ = app._prior_run(session, theirs)
    assert prior_id is None, (
        "another account's run was used as this reader's prior")


def test_the_second_run_is_not_reported_as_a_first_observation(app, two_runs):
    """ARROW 3-8. The whole vertical, ending at the state the card renders."""
    c, _first, second = two_runs
    session = app.auth.session(c.sid())
    from intent_engine.strategic_intelligence.decision import decision_of
    _, report, _ = app._founder_layers(second)
    delta = app._second_iteration_delta(session, second, decision_of(report))
    assert delta, "no delta was composed at all"
    assert delta.get("state") != SI.FIRST_OBSERVATION, (
        "the second run of the same company reports FIRST_OBSERVATION; the "
        "prior-run lookup found nothing where a prior exists")


def test_a_baseline_card_makes_no_claim_about_a_prior():
    """§5 STATE EXCLUSIVITY, over every state rather than the one that broke.

    `hero` rendered all seven lines unconditionally, so FIRST_OBSERVATION --
    whose whole meaning is "there is nothing to compare against" -- also
    announced novelty and a decision effect relative to the prior it had just
    said did not exist. The novelty count is the tell: it is measured against
    the previous run's documents, so on a baseline it is the entire corpus.
    """
    from intent_engine.founder_brief import xray

    comparative_keys = ("new_information", "what_it_tested", "what_changed",
                        "decision_effect")
    for state in (SI.FIRST_OBSERVATION, SI.INCOMPARABLE):
        card = SI.hero({"state": state, "new_evidence": 10,
                        "reobserved_evidence": 0, "changed_fields": ["x"],
                        "recommendation_changed": False,
                        "statement": "s"})
        for key in comparative_keys:
            assert not card[key], (
                f"{state} rendered {key}={card[key]!r}; that is a claim about "
                f"a prior this state says it does not have")

    # And the same through the renderer the customer actually reads.
    body = xray._second_iteration_body(
        {"second_iteration": {"state": SI.FIRST_OBSERVATION,
                              "new_evidence": 10, "changed_fields": [],
                              "statement": "s"}})
    assert "had not seen before" not in body, (
        "the baseline card still advertises evidence new relative to a prior")
    assert "did not add to what the system knows" not in body, (
        "the baseline card still says it failed to add to a stock of "
        "knowledge that does not exist yet")


def test_a_comparative_state_still_says_everything_it_should():
    """The suppression must not silence a real second look."""
    card = SI.hero({"state": SI.NEW_INFORMATION_CHANGED_VIEW,
                    "new_evidence": 3, "changed_fields": ["recommended_next_move"],
                    "recommendation_changed": True, "statement": "s"})
    assert "3 source(s)" in card["new_information"]
    assert card["what_changed"]
    assert card["decision_effect"] == "the recommendation changed"
