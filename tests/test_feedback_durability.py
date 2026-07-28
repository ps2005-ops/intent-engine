"""Feedback durability, and the storage probe underneath it.

The defect: the success page said "Feedback recorded" because the code reached
the next line, which is not the same as the bytes surviving. On a deployment
whose runtime root is replaced on redeploy, the write succeeded, the page was
truthful about the function call, and the tester's feedback was gone.

Same shape as the error page that promised "it has been logged" while the
traceback was never written — a claim about internal state, shown to a user as
a fact, that nobody had checked.
"""
import io
import json

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from intent_engine.webapp.feedback import (
    CATEGORIES, FeedbackLog, FeedbackNotDurable, RATINGS,
)
from intent_engine.webapp.storage_state import (
    DURABLE_PROVEN, DURABLE_UNPROVEN, EPHEMERAL_LIKELY, NOT_WRITABLE,
    explain_storage, may_promise_persistence, probe_storage, read_boots,
    record_boot,
)


# --- the probe ---------------------------------------------------------------
def test_a_single_boot_can_never_prove_durability(tmp_path):
    record_boot(tmp_path, boot_id="only-boot")
    probe = probe_storage(tmp_path, boot_id="only-boot")
    assert probe["durability"] != DURABLE_PROVEN
    assert not probe["durable"]
    assert not may_promise_persistence(probe)


def test_an_earlier_boot_still_present_is_proof(tmp_path):
    record_boot(tmp_path, boot_id="previous-process")
    record_boot(tmp_path, boot_id="this-process")
    probe = probe_storage(tmp_path, boot_id="this-process")
    assert probe["durability"] == DURABLE_PROVEN
    assert probe["earlier_boots_observed"] == 1
    assert may_promise_persistence(probe)


def test_recording_twice_in_one_process_is_not_a_restart(tmp_path):
    """The worst possible bug in this file would be manufacturing a second
    boot and turning UNPROVEN into PROVEN by accident."""
    record_boot(tmp_path, boot_id="same-process")
    record_boot(tmp_path, boot_id="same-process")
    probe = probe_storage(tmp_path, boot_id="same-process")
    assert probe["boot_count"] == 1
    assert probe["durability"] != DURABLE_PROVEN


def test_unwritable_storage_is_detected(tmp_path):
    target = tmp_path / "readonly"
    target.mkdir()
    target.chmod(0o500)
    try:
        probe = probe_storage(target, boot_id="b")
        assert probe["durability"] == NOT_WRITABLE
        assert not probe["writable"]
        assert not may_promise_persistence(probe)
    finally:
        target.chmod(0o700)


def test_durability_is_never_inferred_from_the_path_name(tmp_path):
    """A relative "data" and an absolute "/var/data" get the same treatment:
    both are measured, neither is read as a claim."""
    relative = probe_storage(tmp_path / "data", boot_id="b")
    assert relative["durability"] in (DURABLE_UNPROVEN, EPHEMERAL_LIKELY)
    # the path is reported, but it is not what decided the verdict
    assert "runtime_root" in relative
    assert relative["durability"] != DURABLE_PROVEN


def test_a_torn_ledger_line_does_not_break_the_probe(tmp_path):
    record_boot(tmp_path, boot_id="good-boot")
    with (tmp_path / ".boot_ledger.jsonl").open("a") as handle:
        handle.write('{"boot_id": "torn\n')
    assert [b["boot_id"] for b in read_boots(tmp_path)] == ["good-boot"]


def test_every_state_has_a_plain_explanation():
    for state in (DURABLE_PROVEN, DURABLE_UNPROVEN, EPHEMERAL_LIKELY,
                  NOT_WRITABLE):
        text = explain_storage({"durability": state})
        assert text and "durab" in text.lower() or "storage" in text.lower()
        assert state not in text, "the state name is not for readers"


# --- the log -----------------------------------------------------------------
def test_a_record_carries_the_whole_contract(tmp_path):
    log = FeedbackLog(tmp_path)
    record = log.record(run_id="run-1", company="Palantir", page="brief",
                        rating="yes", comment="Clear and quick",
                        deployed_commit="abc1234",
                        analysis_version="1.5.0", category="clarity",
                        user_id="u1")
    stored = log.all()[0]
    for field in ("feedback_id", "run_id", "company", "page", "rating",
                  "comment", "submitted_at", "deployed_commit",
                  "analysis_version", "category", "schema_version"):
        assert field in stored, f"missing {field}"
    assert stored["feedback_id"] == record.feedback_id


def test_the_write_is_confirmed_by_reading_it_back(tmp_path):
    log = FeedbackLog(tmp_path)
    record = log.record(run_id="r", company="C", page="brief", rating="yes",
                        comment="")
    assert log.contains(record.feedback_id)


def test_an_unwritable_location_raises_rather_than_claiming_success(tmp_path):
    target = tmp_path / "readonly"
    target.mkdir()
    target.chmod(0o500)
    try:
        with pytest.raises(FeedbackNotDurable):
            FeedbackLog(target / "nested").record(
                run_id="r", company="C", page="brief", rating="yes",
                comment="")
    finally:
        target.chmod(0o700)


def test_records_are_append_only(tmp_path):
    log = FeedbackLog(tmp_path)
    for n in range(3):
        log.record(run_id=f"r{n}", company="C", page="brief", rating="yes",
                   comment=f"note {n}")
    assert len(log.all()) == 3
    assert [r["comment"] for r in log.all()] == ["note 0", "note 1", "note 2"]


def test_records_survive_a_new_log_object(tmp_path):
    FeedbackLog(tmp_path).record(run_id="r", company="C", page="brief",
                                 rating="no", comment="lost?")
    assert len(FeedbackLog(tmp_path).all()) == 1


@pytest.mark.parametrize("rating", RATINGS)
def test_every_declared_rating_is_accepted(tmp_path, rating):
    FeedbackLog(tmp_path).record(run_id="r", company="C", page="brief",
                                 rating=rating, comment="")


def test_an_unknown_rating_is_refused(tmp_path):
    with pytest.raises(ValueError):
        FeedbackLog(tmp_path).record(run_id="r", company="C", page="brief",
                                     rating="excellent", comment="")


def test_export_is_valid_jsonl(tmp_path):
    log = FeedbackLog(tmp_path)
    log.record(run_id="r1", company="C", page="brief", rating="yes",
               comment="a")
    log.record(run_id="r2", company="D", page="slides", rating="no",
               comment="b")
    lines = log.export_jsonl().splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["feedback_id"] for line in lines)


def test_operator_can_find_feedback_by_run_and_company(tmp_path):
    log = FeedbackLog(tmp_path)
    log.record(run_id="r1", company="Palantir", page="brief", rating="yes",
               comment="")
    log.record(run_id="r2", company="Shopify", page="brief", rating="no",
               comment="")
    assert len(log.find(run_id="r1")) == 1
    assert len(log.find(company="palantir")) == 1


# --- through the web app ------------------------------------------------------
class Client:
    def __init__(self, app):
        self.app, self.cookie = app, ""

    def request(self, method, path, body=""):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": self.cookie,
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}

        def sr(status, headers):
            out["status"], out["headers"] = status, headers
        payload = b"".join(self.app(env, sr)).decode()
        for k, v in out["headers"]:
            if k == "Set-Cookie" and v.startswith("sid="):
                self.cookie = "" if "Max-Age=0" in v else v.split(";")[0]
        return out["status"], dict(out["headers"]), payload

    def sid(self):
        return self.cookie.split("=", 1)[1] if self.cookie else None

    def csrf(self):
        return self.app.auth.csrf_token(self.sid())


def _no_network(url, timeout):
    raise OSError("test transport: network disabled")


def _app(tmp_path, *, durable):
    if durable:
        record_boot(tmp_path, boot_id="previous-process-boot")
    config = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl",
                       ci_store_path=tmp_path / "ci.jsonl")
    return WebApp(config, transport=_no_network, resolver=False)


def _demo_run(client):
    csrf = client.csrf()
    _, headers, _ = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf}&company_name=Demo"
        f"&website=https://northwind-demo.example")
    return headers["Location"].split("/runs/")[1].split("/")[0]


def test_durable_storage_accepts_feedback_and_confirms_it(tmp_path):
    app = _app(tmp_path, durable=True)
    c = Client(app)
    c.request("POST", "/demo")
    run_id = _demo_run(c)
    status, _, body = c.request("POST", f"/runs/{run_id}/feedback",
                                f"csrf={c.csrf()}&useful=yes&note=Very clear")
    assert status.startswith("200")
    assert "saved and read back to confirm it" in body
    assert app.feedback_log.all()[0]["comment"] == "Very clear"


def test_unproven_storage_refuses_rather_than_pretending(tmp_path):
    app = _app(tmp_path, durable=False)
    c = Client(app)
    c.request("POST", "/demo")
    run_id = _demo_run(c)
    status, _, body = c.request("POST", f"/runs/{run_id}/feedback",
                                f"csrf={c.csrf()}&useful=yes&note=Lost?")
    assert status.startswith("503")
    assert "temporarily unavailable" in body
    # and crucially: nothing was recorded, and nothing said it was
    assert app.feedback_log.all() == []
    assert "saved" not in body.lower() or "not" in body.lower()


def test_the_form_is_switched_off_rather_than_shown_and_broken(tmp_path):
    app = _app(tmp_path, durable=False)
    c = Client(app)
    c.request("POST", "/demo")
    run_id = _demo_run(c)
    _, _, body = c.request("GET", f"/runs/{run_id}")
    assert "Feedback is temporarily unavailable" in body
    assert "Send feedback" not in body


def test_the_form_is_offered_when_storage_is_proven(tmp_path):
    app = _app(tmp_path, durable=True)
    c = Client(app)
    c.request("POST", "/demo")
    run_id = _demo_run(c)
    _, _, body = c.request("GET", f"/runs/{run_id}")
    assert "Send feedback" in body


def test_readyz_reports_measured_storage_state(tmp_path):
    app = _app(tmp_path, durable=True)
    _, _, body = Client(app).request("GET", "/readyz")
    payload = json.loads(body)
    assert payload["storage"]["durability"] == DURABLE_PROVEN
    assert payload["storage"]["accepting_feedback"] is True


def test_readyz_does_not_claim_durability_it_has_not_seen(tmp_path):
    app = _app(tmp_path, durable=False)
    _, _, body = Client(app).request("GET", "/readyz")
    payload = json.loads(body)
    assert payload["storage"]["durability"] != DURABLE_PROVEN
    assert payload["storage"]["accepting_feedback"] is False


def test_operator_can_read_and_export_feedback(tmp_path):
    app = _app(tmp_path, durable=True)
    c = Client(app)
    c.request("POST", "/demo")
    run_id = _demo_run(c)
    c.request("POST", f"/runs/{run_id}/feedback",
              f"csrf={c.csrf()}&useful=partly&note=Useful but dense")
    status, _, page = c.request("GET", "/feedback")
    assert status.startswith("200")
    assert "Useful but dense" in page
    status, headers, export = c.request("GET", "/feedback.jsonl")
    assert status.startswith("200")
    assert headers["Content-Type"] == "application/x-ndjson"
    assert json.loads(export.splitlines()[0])["comment"] == "Useful but dense"


def test_the_operator_view_states_the_storage_position(tmp_path):
    """A list of records without the durability state invites exactly the
    mistake the success page made."""
    app = _app(tmp_path, durable=False)
    c = Client(app)
    c.request("POST", "/demo")
    _, _, page = c.request("GET", "/feedback")
    assert "accepting feedback: no" in page


def test_feedback_requires_a_session(tmp_path):
    app = _app(tmp_path, durable=True)
    status, headers, _ = Client(app).request("GET", "/feedback")
    assert status.startswith("303")
    assert headers["Location"] == "/login"
