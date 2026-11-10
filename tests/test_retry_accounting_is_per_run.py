"""One service serves every run, so a ledger on the service is a leak.

MEASURED IN THE CODE, NOT THE TEST. `webapp/app.py` builds exactly ONE
`CompanyIngestionService` for the whole process. A RetryLedger held on that
service is therefore shared by every customer: the first analysis spends the
per-host and run retry budgets, and every later analysis in that process gets
a retry policy that never retries — a repair that works once per deploy and
then silently stops. That is the same shape as a fix that ships inert, and it
is only visible if something asserts the second run's budget.
"""
import ast
import pathlib

from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.company_ingestion.transient import RetryLedger

APP = (pathlib.Path(__file__).resolve().parents[1]
       / "src/intent_engine/webapp/app.py")


def test_two_runs_do_not_share_a_ledger(tmp_path):
    ci = CompanyIngestionService(tmp_path / "ci.jsonl", resolver=False)
    first = ci.retry_ledger_for("run-a")
    second = ci.retry_ledger_for("run-b")
    assert first is not second
    assert ci.retry_ledger_for("run-a") is first, "must be stable per run"


def test_a_spent_budget_does_not_follow_the_next_run(tmp_path):
    ci = CompanyIngestionService(tmp_path / "ci.jsonl", resolver=False)
    first = ci.retry_ledger_for("run-a")
    first.charge("www.sec.gov", first.policy.total_retry_budget_s)
    assert first.remaining("www.sec.gov") == 0.0
    second = ci.retry_ledger_for("run-b")
    assert second.remaining("www.sec.gov") == \
        second.policy.total_retry_budget_s, \
        "the next customer inherited the previous customer's spent budget"


def test_an_injected_ledger_is_honoured_for_every_run(tmp_path):
    """A test that passes a ledger wants to read it, so injection wins."""
    mine = RetryLedger()
    ci = CompanyIngestionService(tmp_path / "ci.jsonl", resolver=False,
                                 retry_ledger=mine)
    assert ci.retry_ledger_for("run-a") is mine
    assert ci.retry_ledger_for("run-b") is mine


def test_the_webapp_builds_exactly_one_service(tmp_path):
    """THE PREMISE OF THIS FILE, asserted rather than remembered. If the
    webapp ever built a service per run, the sharing hazard would be gone
    and these tests would be guarding nothing — and if it builds more than
    one, two of them would disagree about a run's retry budget."""
    tree = ast.parse(APP.read_text())
    built = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "CompanyIngestionService"]
    assert len(built) == 1, f"{len(built)} services constructed in the webapp"


def test_telemetry_reaches_a_surface(tmp_path):
    """§4: the retry record must reach diagnostics. A counter that exists
    only inside a local variable answered no question anybody asked."""
    ci = CompanyIngestionService(tmp_path / "ci.jsonl", resolver=False)
    ledger = ci.retry_ledger_for("run-a")
    ledger.record(host="www.sec.gov", url="https://www.sec.gov/x",
                  attempt_count=3, final_status=429, retry_exhausted=True,
                  elapsed_retry_time=3.0)
    ledger.charge("www.sec.gov", 3.0)
    per_run = ci.retrieval_telemetry("run-a")
    assert per_run["retry"]["total_retries"] == 1
    assert per_run["retry"]["events"][-1]["attempt_count"] == 3
    assert per_run["retry"]["events"][-1]["retry_exhausted"] is True
    assert "filing_cache" in per_run

    overview = ci.retrieval_telemetry_overview()
    assert overview["runs_with_a_ledger"] == 1
    assert overview["total_retries"] == 1
    assert overview["retry_seconds_by_host"]["www.sec.gov"] == 3.0


def test_the_status_route_carries_it():
    """Operator-only by design: §16 forbids asking a customer to understand
    a 429, and an operator staring at a thin run needs exactly this to tell
    'sec.gov asked us to wait' from 'this company published nothing'."""
    source = APP.read_text()
    assert "retrieval_telemetry_overview()" in source
    assert '"retrieval": retrieval,' in source
