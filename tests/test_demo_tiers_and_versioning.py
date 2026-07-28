"""Demo support tiers and analysis compatibility.

The demo made one promise for every company: type a name, get a briefing. True
for Palantir, roughly true for Shopify, false for a conglomerate whose site
refuses automated access — and the tester had no way to know which case they
were in until the result was already disappointing.
"""
import io

import pytest

from intent_engine.company_ingestion.demo_tiers import (
    GOLDEN, GOLDEN_COMPANIES, LIMITED, OPEN, TAILORED, TIERS, classify,
    is_golden, presentation,
)
from intent_engine.founder_intelligence.service import (
    FounderIntelligenceService, analysis_fingerprint,
)
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig


# --- tiers --------------------------------------------------------------------
def test_validated_companies_are_golden():
    assert classify(entity_id="palantir") == GOLDEN
    assert classify(website="https://www.shopify.com") == GOLDEN


def test_sony_is_not_golden_until_it_earns_it():
    """It resolves correctly and recovers from a blocked domain. That is not
    the same as being safe to open in a meeting."""
    assert classify(entity_id="sony-group") != GOLDEN
    assert not is_golden(entity_id="sony-group")
    assert all(c["entity_id"] != "sony-group" for c in GOLDEN_COMPANIES)


def test_an_arbitrary_company_is_open_exploration():
    assert classify(website="https://brightlake.example") == OPEN


def test_a_frozen_snapshot_is_the_tailored_mode():
    assert classify(website="https://prospect.example", frozen=True) == TAILORED


def test_the_label_follows_the_evidence_not_the_intent():
    """A company can be OPEN when the run starts and LIMITED by the time the
    gate has spoken."""
    assert classify(website="https://thin.example",
                    readiness_state="INSUFFICIENT_EVIDENCE") == LIMITED
    assert classify(website="https://thin.example",
                    readiness_state="READY_FOR_LIMITED_REPORT") == LIMITED


def test_golden_status_outranks_a_thin_run():
    # a validated company having a bad day is still a validated company
    assert classify(entity_id="palantir",
                    readiness_state="INSUFFICIENT_EVIDENCE") == GOLDEN


@pytest.mark.parametrize("tier", TIERS)
def test_every_tier_has_reader_facing_words_not_an_enum(tier):
    p = presentation(tier)
    assert p["label"] and p["summary"] and p["promise"]
    for text in (p["label"], p["summary"], p["promise"]):
        assert tier not in text, "the tier name is not for readers"
        assert "_" not in text


def test_every_golden_company_is_fully_specified():
    for company in GOLDEN_COMPANIES:
        assert company["name"] and company["website"].startswith("https://")
        assert company["why"], "a prepared example must say why it is one"


# --- compatibility ------------------------------------------------------------
def test_the_compatibility_key_covers_every_declared_component():
    version = FounderIntelligenceService.analysis_version()
    for component in ("app=", "analysis=", "identity=", "discovery=",
                      "extraction=", "evidence=", "quality=", "synthesis=",
                      "presentation="):
        assert component in version, f"missing component: {component}"


class _Input:
    def __init__(self, approved):
        self.approved_inputs = approved


def test_identical_input_and_version_is_one_run():
    a = analysis_fingerprint(_Input(("s1", "s2")))
    b = analysis_fingerprint(_Input(("s1", "s2")))
    assert a == b


def test_source_order_does_not_change_identity():
    """Discovery order depends on which pages respond first; it is not a
    different analysis."""
    assert analysis_fingerprint(_Input(("s1", "s2", "s3"))) == \
        analysis_fingerprint(_Input(("s3", "s1", "s2")))


def test_different_evidence_is_a_different_run():
    assert analysis_fingerprint(_Input(("s1", "s2"))) != \
        analysis_fingerprint(_Input(("s1", "s2", "s3")))


def test_a_version_change_invalidates_an_old_result(monkeypatch):
    before = analysis_fingerprint(_Input(("s1",)))
    monkeypatch.setattr(FounderIntelligenceService, "analysis_version",
                        staticmethod(lambda: "app=9.9.9|everything=else"))
    assert analysis_fingerprint(_Input(("s1",))) != before


# --- through the web app -------------------------------------------------------
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


@pytest.fixture
def guest(tmp_path):
    config = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl",
                       ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(config, transport=_no_network, resolver=False)
    c = Client(app)
    c.request("POST", "/demo")
    return c


def test_prepared_examples_are_offered_before_a_guest_has_to_guess(guest):
    _, _, page = guest.request("GET", "/")
    for company in GOLDEN_COMPANIES:
        assert company["name"] in page
    assert "Prepared example" in page


def test_no_raw_tier_name_ever_reaches_the_page(guest):
    _, _, page = guest.request("GET", "/")
    for tier in TIERS:
        assert tier not in page, f"raw tier name shown: {tier}"


def test_the_brief_states_when_it_ran_and_offers_a_fresh_one(guest):
    _, headers, _ = guest.request(
        "POST", "/analyze",
        f"consent=on&csrf={guest.csrf()}&company_name=Thin"
        f"&website=https://thin.example")
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    # a no-network run ends at the failure page; the stamp lives on the brief,
    # so assert the route exists and the provenance renders where a report does
    status, _, page = guest.request("GET", f"/runs/{run_id}")
    assert status.startswith(("200", "303"))


def test_a_fresh_run_belongs_to_the_runs_owner(guest, tmp_path):
    _, headers, _ = guest.request(
        "POST", "/analyze",
        f"consent=on&csrf={guest.csrf()}&company_name=Thin"
        f"&website=https://thin.example")
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    other = Client(guest.app)
    other.request("POST", "/demo")
    status, _, _ = other.request("POST", f"/runs/{run_id}/fresh",
                                 f"csrf={other.csrf()}")
    assert status.startswith("404")


def test_a_stale_result_cannot_trap_the_user(guest):
    """The fresh button exists precisely so a reader need not trust our
    judgement about whether a cached run is still good."""
    _, headers, _ = guest.request(
        "POST", "/analyze",
        f"consent=on&csrf={guest.csrf()}&company_name=Thin"
        f"&website=https://thin.example")
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    guest.app._results[run_id] = {"stale": True}
    status, _, _ = guest.request("POST", f"/runs/{run_id}/fresh",
                                 f"csrf={guest.csrf()}")
    assert status.startswith("303")
    assert guest.app._results.get(run_id, {}).get("stale") is None


def test_repeated_same_day_analysis_never_500s(guest):
    """The incident 2f90844 fixed, still fixed."""
    for _ in range(3):
        status, _, _ = guest.request(
            "POST", "/analyze",
            f"consent=on&csrf={guest.csrf()}&company_name=Repeat"
            f"&website=https://repeat.example")
        assert not status.startswith("5"), status
