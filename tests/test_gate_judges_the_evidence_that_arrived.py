"""The readiness gate may not judge a document set the run has outgrown.

MEASURED LIVE on 10d1620, Meta Platforms, on the first run after the
evidence-gate header was deployed:

    compose=1  usable=1  families=investor  stored=7  attempt=1

One document went to the gate. Seven are in the store, three of them Meta's
own SEC filings. The customer was told the public evidence about Meta
Platforms was too thin to analyse, on a run that had read Meta's 10-K and its
10-Q.

WHAT THIS IS NOT. It is not a counting bug. Three offline reproductions
against those seven real documents were all wrong -- `usable_documents` keeps
7 of 7, `is_english` is True for 7 of 7, and raw-HTML truncation swept from
16MB down to 200KB keeps 7 of 7 -- and the gate re-run on the seven answers
`document_count: 7`. Composition happened before the evidence finished
arriving, and nothing looked again.
"""
import io

import pytest

from company_fixture_pages import BASE as FIXTURE_SITE, transport as fixture_transport

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig


@pytest.fixture
def app(tmp_path):
    return WebApp(AppConfig(env="test", secret="s" * 40, demo_mode=True,
                            web_store_path=tmp_path / "w.jsonl",
                            fi_store_path=tmp_path / "f.jsonl",
                            ci_store_path=tmp_path / "c.jsonl"),
                  transport=fixture_transport, resolver=False)


class Client:
    def __init__(self, app):
        self.app, self.cookies = app, {}

    def post(self, path, body=""):
        env = {"REQUEST_METHOD": "POST", "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": "; ".join(f"{k}={v}"
                                        for k, v in self.cookies.items()),
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}
        payload = b"".join(self.app(env, lambda s, h: out.update(
            status=s, headers=h))).decode()
        for key, value in out["headers"]:
            if key == "Set-Cookie":
                name, _, rest = value.partition("=")
                self.cookies[name] = rest.split(";")[0]
        return out["status"], dict(out["headers"]), payload


def _open_run(client):
    client.post("/demo", "")
    csrf = client.app.auth.csrf_token(client.cookies["sid"])
    _s, headers, _b = client.post(
        "/analyze",
        f"consent=on&csrf={csrf}&company_name=Brightlake&website={FIXTURE_SITE}")
    return headers["Location"].split("/runs/")[1].split("/")[0]


def _evidence_arrives_late(app, run_id, *, during_first_compose):
    """The live shape: the gate runs on a partial store, and the rest of the
    evidence is present by the time anyone looks.

    Shimmed at the COMPOSE BOUNDARY rather than on `store.retrieved`, because
    `retrieved` is called many times inside one composition and truncating a
    fixed number of those calls does not model anything -- the first attempt
    at this test truncated call one and the gate, several calls later, saw the
    full set, so the test failed while the repair worked.
    """
    real_compose = app.ci.compose_with_quality
    real_retrieved = app.ci.store.retrieved
    state = {"first": True}

    def shimmed(rid, **kwargs):
        if rid == run_id and state["first"]:
            state["first"] = False
            app.ci.store.retrieved = (
                lambda r: list(real_retrieved(r))[:during_first_compose]
                if r == run_id else real_retrieved(r))
            try:
                return real_compose(rid, **kwargs)
            finally:
                app.ci.store.retrieved = real_retrieved
        return real_compose(rid, **kwargs)
    app.ci.compose_with_quality = shimmed


def test_a_gate_that_saw_fewer_documents_is_run_again(app):
    """THE REPAIR. When the store outgrew the set the gate judged, the run
    composes once more against what actually arrived."""
    client = Client(app)
    run_id = _open_run(client)
    app.wait_for_analysis(run_id, timeout=60)
    stored = len(app.ci.store.retrieved(run_id))
    assert stored >= 2, f"fixture retrieved {stored}; need at least 2"

    app._results.pop(run_id, None)
    _evidence_arrives_late(app, run_id, during_first_compose=1)
    result = app._compose(run_id)
    inputs = result.get("readiness_inputs") or {}
    assert inputs.get("recomposed_from") == 1, (
        f"the gate judged {inputs.get('documents_at_compose')} of {stored} "
        f"documents and was never re-run: {inputs}")
    assert inputs.get("documents_at_compose") == stored


def test_a_run_whose_evidence_did_not_grow_composes_once(app):
    """THE NEGATIVE CONTROL, and the one that matters most: this must not
    become a second compose on every run. An extra synthesis per analysis is
    a real cost paid by every customer, for nothing."""
    client = Client(app)
    run_id = _open_run(client)
    app.wait_for_analysis(run_id, timeout=60)
    app._results.pop(run_id, None)
    result = app._compose(run_id)
    inputs = result.get("readiness_inputs") or {}
    assert "recomposed_from" not in inputs, inputs
    # AND IT MUST NOT EVEN RE-GATE. A break proof that flipped `stored >
    # seen` to `True` stayed green while only `recomposed_from` was
    # asserted, because the cost control below absorbed it -- so the test
    # was measuring the second guard and calling it the first.
    assert "regated_from" not in inputs, inputs
    assert inputs.get("documents_at_compose") == \
        len(app.ci.store.retrieved(run_id))


def test_the_gate_header_reports_both_numbers(app):
    """The measurement that found this stays readable after the repair --
    otherwise a regression is invisible again."""
    client = Client(app)
    run_id = _open_run(client)
    app.wait_for_analysis(run_id, timeout=60)
    gate = app.evidence_gate_summary(run_id)
    assert "compose=" in gate and "stored=" in gate, gate
    compose = int(gate.split("compose=")[1].split()[0])
    stored = int(gate.split("stored=")[1].split()[0])
    assert compose == stored, f"gate judged {compose} of {stored}: {gate}"


def test_a_fuller_set_that_still_fails_the_gate_costs_no_second_synthesis(app):
    """THE COST CONTROL, and it exists because the first version had none.

    MEASURED on b37bee2, 0d02c0b and e78c2a0: recomposing unconditionally
    made Meta's service stop answering `/runs/<id>/progress` from t=33 to
    t=349 -- five minutes of a single-worker deployment serving nobody -- and
    four consecutive Meta runs were unobservable. The same analysis finished
    in 48 and 52 seconds on the two SHAs before it.

    Re-running the GATE is cheap and fixes the number the customer reads.
    Re-running SYNTHESIS is the five minutes, and it is only worth paying
    when the fuller evidence actually changes the verdict.
    """
    client = Client(app)
    run_id = _open_run(client)
    app.wait_for_analysis(run_id, timeout=60)
    app._results.pop(run_id, None)

    composes = {"n": 0}
    real_compose = app.ci.compose_with_quality
    state = {"first": True}
    real_retrieved = app.ci.store.retrieved

    def counting(rid, **kwargs):
        composes["n"] += 1
        if rid == run_id and state["first"]:
            state["first"] = False
            app.ci.store.retrieved = (
                lambda r: list(real_retrieved(r))[:1] if r == run_id
                else real_retrieved(r))
            try:
                return real_compose(rid, **kwargs)
            finally:
                app.ci.store.retrieved = real_retrieved
        return real_compose(rid, **kwargs)
    app.ci.compose_with_quality = counting

    # The gate refuses whatever it is shown, so the fuller set changes the
    # NUMBERS and not the verdict -- the case where a second synthesis buys
    # the customer nothing.
    import intent_engine.company_ingestion.readiness as R
    real_assess = R.assess_readiness

    def refusing(**kwargs):
        out = dict(real_assess(**kwargs))
        out["may_synthesize"] = False
        return out
    app._readiness_on_current_evidence = (
        lambda rid: refusing(documents=app.ci.store.retrieved(rid),
                             identity=app.ci.entity_identity(rid),
                             failures=app.ci.store.failures(rid), attempt=1))

    result = app._compose(run_id)
    inputs = result.get("readiness_inputs") or {}
    assert composes["n"] == 1, (
        f"a second synthesis was paid for and changed no verdict "
        f"({composes['n']} composes)")
    assert inputs.get("regated_from") == 1, inputs
    assert inputs.get("documents_at_compose") == \
        len(app.ci.store.retrieved(run_id)), (
        "the numbers the customer reads were not corrected")
