"""The preview-only acceptance runner: who may run it, and what it costs.

The runner exists so a twenty-company matrix can be driven without moving the
public demo quota (ten analyses per IP per rolling hour). Every test below is
about a way it could become something other than that.
"""
from __future__ import annotations

import json

import pytest

from intent_engine.webapp import acceptance as A


# --- who may run it -----------------------------------------------------------

def test_absent_token_means_the_mechanism_does_not_exist():
    assert A.is_enabled(env="development", token="") is False
    assert A.is_enabled(env="development", token="   ") is False


def test_a_token_does_not_enable_it_on_production():
    """Two independent conditions. Neither alone is sufficient."""
    assert A.is_enabled(env="production", token="a-real-token") is False
    assert A.is_enabled(env="development", token="a-real-token") is True
    assert A.is_enabled(env="test", token="a-real-token") is True


@pytest.mark.parametrize("env,expected,presented", [
    ("production", "tok", "tok"),          # right token, wrong service
    ("development", "tok", ""),            # no token presented
    ("development", "tok", "wrong"),       # wrong token
    ("development", "", "anything"),       # not configured
    ("development", "tok", "to"),          # prefix of the real token
    ("development", "tok", "tok "),        # trailing space is stripped, ok
])
def test_authorise_refuses_everything_but_the_exact_token(env, expected,
                                                          presented):
    if presented.strip() == expected.strip() and expected and \
            env != "production":
        A.authorise(env=env, expected=expected, presented=presented)
        return
    with pytest.raises(A.AcceptanceRefused):
        A.authorise(env=env, expected=expected, presented=presented)


def test_refusal_never_explains_which_condition_failed():
    """An endpoint that distinguishes them tells a caller which it is."""
    messages = set()
    for env, expected, presented in [("production", "t", "t"),
                                     ("development", "t", "wrong"),
                                     ("development", "", "t")]:
        try:
            A.authorise(env=env, expected=expected, presented=presented)
        except A.AcceptanceRefused as exc:
            messages.add(str(exc))
    assert len(messages) == 1


def test_the_token_is_never_in_a_refusal():
    try:
        A.authorise(env="development", expected="SUPERSECRET",
                    presented="nope")
    except A.AcceptanceRefused as exc:
        assert "SUPERSECRET" not in str(exc)


# --- bounds -------------------------------------------------------------------

def _companies(n):
    return [{"name": f"Company {i}", "website": f"https://c{i}.example"}
            for i in range(n)]


def test_an_oversized_matrix_is_refused_not_truncated():
    with pytest.raises(A.AcceptanceRefused):
        A.plan(_companies(A.MAX_COMPANIES_CEILING + 1))


def test_the_configured_maximum_cannot_exceed_the_ceiling():
    with pytest.raises(A.AcceptanceRefused):
        A.plan(_companies(A.MAX_COMPANIES_CEILING + 1),
               max_companies=1000)


def test_concurrency_is_clamped_to_the_ceiling():
    assert A.plan(_companies(2), concurrency=99)["concurrency"] == \
        A.MAX_CONCURRENCY_CEILING
    assert A.plan(_companies(2), concurrency=0)["concurrency"] == 1


def test_budget_is_clamped():
    assert A.plan(_companies(2), budget=10_000)["budget"] <= \
        A.MAX_COMPANIES_CEILING


@pytest.mark.parametrize("companies", [
    [], None, "Datadog",
    [{"name": "", "website": "https://x.example"}],
    [{"name": "X", "website": "ftp://x.example"}],
    [{"name": "X", "website": ""}],
    ["Datadog"],
])
def test_a_malformed_request_is_refused(companies):
    with pytest.raises(A.AcceptanceRefused):
        A.plan(companies)


def test_a_duplicate_company_is_not_run_twice():
    plan = A.plan([{"name": "Datadog", "website": "https://d.example"},
                   {"name": "datadog", "website": "https://d.example"}])
    assert len(plan["companies"]) == 1


def test_names_and_urls_are_bounded():
    plan = A.plan([{"name": "x" * 500, "website": "https://" + "y" * 500}])
    assert len(plan["companies"][0]["name"]) <= 120
    assert len(plan["companies"][0]["website"]) <= 300


# --- the ledger ---------------------------------------------------------------

@pytest.fixture
def ledger_path(tmp_path):
    return tmp_path / "acceptance.jsonl"


def test_progress_survives_a_restart(ledger_path):
    first = A.Ledger(ledger_path, run_id="r1")
    first.record(A.Entry(requested_company="Datadog", website="https://d",
                         state=A.USEFUL_FULL))
    reopened = A.Ledger(ledger_path, run_id="r1")
    assert reopened.get("Datadog").state == A.USEFUL_FULL


def test_another_runs_entries_are_not_read(ledger_path):
    A.Ledger(ledger_path, run_id="r1").record(
        A.Entry(requested_company="Datadog", website="https://d"))
    assert A.Ledger(ledger_path, run_id="r2").entries == {}


def test_resume_skips_completed_and_retries_failed(ledger_path):
    ledger = A.Ledger(ledger_path, run_id="r1")
    ledger.record(A.Entry(requested_company="Done", website="https://a",
                          state=A.USEFUL_FULL))
    ledger.record(A.Entry(requested_company="Broke", website="https://b",
                          state=A.FAILED))
    ledger.record(A.Entry(requested_company="Slow", website="https://c",
                          state=A.TIMED_OUT))
    companies = [{"name": "Done", "website": "https://a"},
                 {"name": "Broke", "website": "https://b"},
                 {"name": "Slow", "website": "https://c"},
                 {"name": "New", "website": "https://d"}]
    pending = [c["name"] for c in ledger.pending(companies)]
    assert pending == ["Broke", "Slow", "New"]


def test_an_interrupted_entry_is_resumed(ledger_path):
    ledger = A.Ledger(ledger_path, run_id="r1")
    ledger.record(A.Entry(requested_company="Half", website="https://a",
                          state=A.RUNNING))
    assert [c["name"] for c in ledger.pending(
        [{"name": "Half", "website": "https://a"}])] == ["Half"]


def test_force_fresh_reruns_everything(ledger_path):
    ledger = A.Ledger(ledger_path, run_id="r1")
    ledger.record(A.Entry(requested_company="Done", website="https://a",
                          state=A.USEFUL_FULL))
    assert ledger.pending([{"name": "Done", "website": "https://a"}],
                          force_fresh=True)


def test_a_withheld_result_is_not_retried(ledger_path):
    """Withholding is an outcome, not a failure to retry into submission."""
    ledger = A.Ledger(ledger_path, run_id="r1")
    ledger.record(A.Entry(requested_company="Quiet", website="https://a",
                          state=A.WITHHELD))
    assert ledger.pending([{"name": "Quiet", "website": "https://a"}]) == []


def test_cancellation_persists(ledger_path):
    ledger = A.Ledger(ledger_path, run_id="r1")
    ledger.cancel()
    assert A.Ledger(ledger_path, run_id="r1").cancelled is True


def test_a_corrupted_tail_costs_only_its_own_line(ledger_path):
    ledger = A.Ledger(ledger_path, run_id="r1")
    ledger.record(A.Entry(requested_company="Good", website="https://a",
                          state=A.USEFUL_FULL))
    with open(ledger_path, "a", encoding="utf-8") as handle:
        handle.write('{"run_id": "r1", "kind": "entry", "entry": {trunc\n')
    reopened = A.Ledger(ledger_path, run_id="r1")
    assert reopened.get("Good").state == A.USEFUL_FULL


def test_an_entry_with_unknown_fields_is_skipped_not_fatal(ledger_path):
    with open(ledger_path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"run_id": "r1", "kind": "entry",
                                 "entry": {"nonsense": 1}}) + "\n")
    assert A.Ledger(ledger_path, run_id="r1").entries == {}


def test_the_summary_counts_every_attempt(ledger_path):
    ledger = A.Ledger(ledger_path, run_id="r1")
    for name, state in [("a", A.USEFUL_FULL), ("b", A.USEFUL_BOUNDED),
                        ("c", A.FAILED), ("d", A.TIMED_OUT)]:
        ledger.record(A.Entry(requested_company=name, website="https://x",
                              state=state))
    summary = ledger.summary()
    assert summary["attempted"] == 4 and summary["useful"] == 2
    assert summary["useful_rate"] == 0.5


# --- deterministic scoring ----------------------------------------------------

_FULL = ("<main>Datadog. The answer is here and it is long enough to read. "
         "Why this matters now. What changed. The decision this bears on. "
         "The options, and what each costs. What most limits this. "
         "What supports this. " + "filler words to pass the floor " * 30 +
         "</main>")
_BOUNDED = ("<main>Limited analysis of Caterpillar. There is not enough "
            "public evidence to build a briefing. What was found. Pages "
            "read. What was missing. What you can do. "
            + "filler words to pass the floor " * 30 + "</main>")


def test_a_complete_result_scores_useful_full():
    assert A.score(_FULL, company="Datadog")["state"] == A.USEFUL_FULL


def test_an_honest_bounded_result_scores_useful_bounded():
    assert A.score(_BOUNDED, company="Caterpillar")["state"] == \
        A.USEFUL_BOUNDED


# THE FIXTURE ABOVE WAS WRITTEN TO SATISFY THE MARKERS, which is why it could
# not catch the markers being wrong. Below is the wording the product actually
# renders -- `narrative.py` writes "No strategic reading of {company} cleared
# the evidence bar" and labels its next step "What you do next" -- taken from
# the deployed page for Constellation Software on preview-v3 at c57af3b.
#
# That page is a CORRECT refusal: it names what it read, names what is missing,
# declines to invent options, and prepares an evidence request. The runner
# scored it FAILED on two markers that were guesses at the phrasing ("no
# strategic reading" in lowercase, and "What you can do"), so an honest
# withheld result counted against the useful rate.
_LIVE_WITHHELD = (
    "<main>Constellation Software serves more than one clearly different "
    "buyer, so one roadmap has to serve buyers who want different things. "
    "The answer. No strategic reading of Constellation Software cleared the "
    "evidence bar, so none is asserted here. That absence is itself the "
    "finding: what Constellation Software has published is not enough to read "
    "a strategy from. The options, and what each costs. No options are put "
    "forward. Nothing was established firmly enough for one course of action "
    "to be weighed against another. The minimum needed before any of this "
    "becomes decidable: every source here is published by the company itself. "
    "What was found. The reading could not be settled on what is public. "
    "What it prepared. A numbered request for exactly what is missing. "
    "What you do next. " + "filler words to pass the floor " * 30 + "</main>")


def test_the_live_withheld_page_is_scored_useful_bounded():
    verdict = A.score(_LIVE_WITHHELD, company="Constellation Software")
    assert verdict["state"] == A.USEFUL_BOUNDED, verdict["reasons"]


@pytest.mark.parametrize("marker,rendered", [
    # left: what the runner looks for. right: what the product writes.
    ("No strategic reading", "No strategic reading of Acme cleared the "
                             "evidence bar, so none is asserted here."),
    ("What you do next", "<dt class=\"k\">What you do next</dt>"),
])
def test_every_bounded_marker_is_wording_the_product_really_emits(marker,
                                                                  rendered):
    assert marker in rendered
    assert any(marker in markers
               for markers in A._BOUNDED_MARKERS.values()), (
        f"{marker!r} is rendered by the product but no bounded marker "
        "matches it")


def test_a_raw_framework_error_is_never_useful():
    verdict = A.score("<main>Bad Request approve at least one source</main>",
                      company="Datadog")
    assert verdict["state"] == A.FAILED
    assert any("raw framework error" in r for r in verdict["reasons"])


def test_a_result_that_never_names_the_company_is_not_useful():
    verdict = A.score(_FULL, company="Cloudflare")
    assert verdict["state"] == A.FAILED
    assert any("not named" in r for r in verdict["reasons"])


def test_a_nearly_empty_result_is_not_useful():
    verdict = A.score("<main>Datadog. Done.</main>", company="Datadog")
    assert verdict["state"] == A.FAILED
    assert any("words of content" in r for r in verdict["reasons"])


def test_a_stylesheet_in_main_is_a_failure():
    html = _FULL.replace("<main>", "<main><style>.a{color:red}</style>")
    verdict = A.score(html, company="Datadog")
    assert verdict["state"] == A.FAILED
    assert any("stylesheet" in r for r in verdict["reasons"])


def test_every_failure_records_why():
    verdict = A.score("<main>Datadog said nothing useful at all.</main>",
                      company="Datadog")
    assert verdict["state"] == A.FAILED
    assert verdict["reasons"], "a matrix row must be arguable"


def test_scoring_reads_only_main():
    """Navigation and footers must not satisfy a check."""
    html = ("<nav>The answer. Why this matters. The decision this bears on."
            "</nav><main>Datadog. Nothing else.</main>")
    assert A.score(html, company="Datadog")["state"] == A.FAILED
