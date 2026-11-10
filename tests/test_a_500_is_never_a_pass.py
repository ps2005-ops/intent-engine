"""A route the server marked 5xx may never be scored as a company that worked.

MEASURED on 743df06. Pfizer Inc.:

    /runs/<id>   HTTP 500   513 chars   "Something went wrong on our side"
    /full        HTTP 200 21,718 chars   a real analysis
    X-Analysis-Outcome: FULL_ANALYSIS   -- on the 500

The analysis was healthy (`compose=12 usable=12 families=5`). The screen the
customer lands on was not. Nothing in the instrument read the HTTP status, so
the only thing that caught this was the error page happening to be short --
a wordier error page would have scored as a pass.
"""
import json

from intent_engine.pre100.verdict import verdict

REAL = ("Something went wrong on our side Something went wrong on our side "
        "What did work. Your request was received and the company you "
        "entered was recorded. What did not. The analysis did not complete. "
        "Why. This is a fault in the product, not in what you entered.")


def _company(tmp_path, *, run_status=200, run_chars=4000, stated="FULL_ANALYSIS",
             run_text=None):
    d = tmp_path / "pfizer_inc"
    d.mkdir(parents=True, exist_ok=True)
    routes = {}
    for name in ("run", "intro", "slides", "full", "story", "history",
                 "connect"):
        status = run_status if name == "run" else 200
        chars = run_chars if name == "run" else 6000
        routes[name] = {"status": status, "chars": chars,
                        "outcome": stated,
                        "final_url": f"https://x/runs/r1/{name}"}
        body = (run_text if name == "run" and run_text is not None
                else f"Pfizer Inc. is a pharmaceutical business. " * 150)
        (d / f"{name}.txt").write_text(body, "utf-8")
    (d / "manifest.json").write_text(json.dumps({
        "company": "Pfizer Inc.", "deployed_sha": "test", "status": "READY",
        "run_id": "r1", "routes": routes, "outcome": stated,
        "outcome_by_route": {k: stated for k in routes},
        "outcome_disagreement": [], "seconds": 100, "first_useful": 100,
        "qa_complete": True, "answers_captured": 10, "errors": [],
        "evidence_gate": "compose=12 usable=12 families=a|b|c stored=12",
    }), "utf-8")
    (d / "qa.json").write_text(json.dumps(
        [{"question": f"q{i}", "answer": "A real answer about Pfizer. " * 12}
         for i in range(10)]), "utf-8")
    return d


def _codes(d):
    return [f["code"] for f in verdict(str(d)).get("failures", [])]


def test_a_healthy_capture_is_the_control(tmp_path):
    """This must be able to pass, or the tests below prove nothing."""
    codes = _codes(_company(tmp_path))
    assert "ROUTE_ERROR" not in codes, codes
    assert "STATED_SUCCESS_OVER_SERVER_ERROR" not in codes, codes


def test_a_server_error_on_a_required_route_fails(tmp_path):
    codes = _codes(_company(tmp_path, run_status=500))
    assert "ROUTE_ERROR" in codes, codes


def test_a_success_claimed_on_a_server_error_is_a_defect(tmp_path):
    codes = _codes(_company(tmp_path, run_status=500))
    assert "STATED_SUCCESS_OVER_SERVER_ERROR" in codes, codes


def test_a_wordy_error_page_does_not_slip_past_the_thinness_check(tmp_path):
    """THE REASON STATUS HAD TO BE READ.

    Pfizer's error page was 513 characters and THIN_ROUTE caught it. Make the
    same error page long enough to pass that check and the old instrument had
    nothing left; this one still fails it.
    """
    d = _company(tmp_path, run_status=500, run_chars=9000,
                 run_text=REAL * 40)
    codes = _codes(d)
    assert "THIN_ROUTE" not in codes, codes
    assert "ROUTE_ERROR" in codes, codes
