"""Round-2 shared repairs from the prospect-100 pass 3 audit."""
from __future__ import annotations

from intent_engine.founder_brief import dossier as fd
from intent_engine.strategic_intelligence.decision import (
    FounderDecision, WITHHELD,
)
from intent_engine.strategic_intelligence.editorial import SaidOnce

GAP = ("We found signs of this shape for ConnectWise, LLC, but did not verify "
       "that it names two clearly different buyer groups")


def test_prepared_artefacts_do_not_restate_the_unknowns():
    """Live (local pass 3): one near-miss sentence printed under "What is
    still unknown", then in the evidence request, then in the diligence
    checklist -- three times on one page."""
    decision = FounderDecision(readiness=WITHHELD, company_name="ConnectWise",
                               evidence_required=[GAP])
    report = {"evidence_gaps": [GAP, "Segment revenue is not disclosed."]}
    said = SaidOnce(seed=[GAP])          # "What is still unknown" said it
    passage = fd._artefacts("ConnectWise", decision, report, said)
    text = " ".join(str(i.get("text", "")) for i in passage.items)
    assert GAP.split(",")[0] not in text, text
    # positive control: a gap the page has NOT stated still reaches the list
    assert "Segment revenue is not disclosed" in text


def test_a_gap_the_page_never_stated_is_still_requested():
    decision = FounderDecision(readiness=WITHHELD, company_name="Acme",
                               evidence_required=[GAP])
    passage = fd._artefacts("Acme", decision, {"evidence_gaps": []},
                            SaidOnce())
    text = " ".join(str(i.get("text", "")) for i in passage.items)
    assert "did not verify" in text


def test_chrome_targets_and_long_tokens_are_in_the_shared_sheet():
    """Measured at 10 widths x 2 themes: nav and aside links and <summary>
    toggles were 16-17px tall; a 75-character filing URL in .muted pushed
    Altana's /full 267px off a 320px screen."""
    from intent_engine.webapp import app
    css = app._A11Y_CSS
    assert ".muted{overflow-wrap:anywhere" in css
    assert "nav a[href],aside a[href]" in css
    assert "summary{min-height:24px}" in css


def test_the_manifest_is_parsed_once_per_file_version(tmp_path):
    """Profiled: six YAML parses per /full request were 89% of the page."""
    import shutil
    import time as _t

    from intent_engine.validation import manifest as M
    copy = tmp_path / "m.yaml"
    shutil.copy(M.MANIFEST_PATH, copy)
    first = M.load(copy)
    assert M.load(copy) is first, "an unchanged file was parsed again"
    # An edited manifest is re-read, never served stale.
    _t.sleep(0.01)
    copy.write_text(copy.read_text(encoding="utf-8") + "\n# edited\n",
                    encoding="utf-8")
    assert M.load(copy) is not first


SENT = ("Workday is the enterprise AI platform for managing people, money "
        "and agents across the whole organisation.")


def test_a_paragraph_the_page_already_said_is_dropped_but_new_ones_kept():
    seen = list(fd._lead_sentences(f"<p>{SENT}</p>"))
    extra = (SENT + " It also sells planning software to finance teams in "
             "regulated industries, which no other passage has said.")
    kept = fd._fresh_paragraphs([SENT, extra], seen)
    assert kept == [extra]


def test_the_appendix_lists_a_quoted_source_without_quoting_it_again():
    from intent_engine.founder_brief.narrative import EvidenceItem
    item = EvidenceItem(text=SENT, provenance="Regulatory or investor filing")
    passage = fd.Passage("evidence_appendix", "Every source this rests on",
                         kind="evidence", items=(item,))
    seen = list(fd._sentence_keys(SENT))          # quoted earlier on the page
    html = fd._render_appendix(passage, "", None, seen)
    assert "quoted above" in html and "<q>" not in html
    # positive control: not yet quoted -> quoted here
    assert "<q>" in fd._render_appendix(passage, "", None, [])


def test_a_company_imperative_does_not_crash_the_understanding_section():
    """Live (local re-render): Wood Mackenzie's copy said "you must", the
    validator raised inside composition, and every page answered 500."""
    from intent_engine.founder_intelligence import understanding as U
    from intent_engine.founder_intelligence.records import AVAIL_SUPPORTED

    class _Claim:
        def __init__(self, cid, text):
            self.claim_id, self.text = cid, text
            self.availability, self.confidence = AVAIL_SUPPORTED, "MEDIUM"

        def validate(self):          # a claim validates itself; this one is fine
            return None

    try:
        section = U.assemble_understanding(
            [_Claim("a", "To stay competitive you must adopt our platform."),
             _Claim("b", "Wood Mackenzie publishes energy research.")])
    except Exception as exc:                      # noqa: BLE001
        raise AssertionError(f"one company sentence broke the section: {exc}")
    headlines = [c.headline for c in section.cards]
    assert "Wood Mackenzie publishes energy research." in headlines
    assert not any("you must" in h for h in headlines)


def test_the_retry_key_names_everything_its_payload_records():
    import inspect

    from intent_engine.company_ingestion import service
    src = inspect.getsource(service)
    # The KEY's own derivation, not the payload beside it: the payload has
    # always carried retry_pass and reason, which is why a first version of
    # this test passed on the defective code.
    start = src.index("target_key = hashlib.sha256(")
    derivation = src[start:src.index("hexdigest()", start)]
    assert "retry_pass" in derivation and "reason" in derivation, derivation


def test_a_run_that_retrieved_nothing_still_has_an_evidence_page(tmp_path):
    """Live (local re-render): Wood Mackenzie and Presidio answered 404 on
    /evidence -- naming an internal key -- and /sources redirects there."""
    import sys as _sys
    _sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from test_strategic_intelligence import _WsgiClient
    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(cfg, transport=lambda *a, **k: (_ for _ in ()).throw(
        OSError("refused")), resolver=False)
    c = _WsgiClient(app)
    c.request("POST", "/demo")
    session = app.auth.session(c.cookie.split("=", 1)[1])
    run = app.ci.create_run(company_name="Nowhere Analytics",
                            website="https://nowhere.example",
                            user_id=session["user_id"],
                            as_of="2026-11-09T00:00:00+00:00")
    from intent_engine.webapp.store import WebEvent
    app.web_store.append(WebEvent(
        event_type="web.run_owned", actor_type="human",
        actor_id=session["user_id"], subject_type="run",
        subject_id=run["run_id"], idempotency_key=f"own:{run['run_id']}",
        payload={"user_id": session["user_id"], "run_id": run["run_id"]}))
    status, _h, body = c.request("GET", f"/runs/{run['run_id']}/evidence")
    assert str(status).startswith("200"), status
    text = body if isinstance(body, str) else body.decode()
    assert "retrieved no evidence" in text
    assert "No analysis is stored here" not in text
