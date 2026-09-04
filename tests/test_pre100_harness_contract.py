"""The harness's own defects, pinned. §2.

Every one of these cost live quota in the previous execution, and none of
them was a product defect. A harness that cannot be trusted turns a 50-company
measurement into a 50-company investigation of the measurement.
"""
import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]
                       / "scripts"))

import pre100_convergence_batch as B                        # noqa: E402
import pre100_batch_journey as J                            # noqa: E402


# --- 1. quota detection ----------------------------------------------------

def test_our_own_field_name_is_not_a_quota_page():
    """`"quota_block": false` appears in every run.json. The first detector
    scanned json.dumps(row) and stopped a canary after a company that had
    completed in 146s with nine surfaces captured."""
    row = {"reliability": {"quota_block": False, "retry_required": 0},
           "routes": {"intro": {"status": 200, "text": "Adobe Inc. is a "
                                "software platform business."}}}
    assert B.quota_blocked(row) is False


def test_a_real_quota_page_is_quota_exhaustion():
    assert B.quota_blocked(
        {"routes": {"run": {"text": "Demo analysis limit reached for your "
                                    "network. You can try again in about 30 "
                                    "minutes."}}}) is True


def test_the_journeys_own_verdict_is_authoritative():
    assert B.quota_blocked({"reliability": {"quota_block": True}}) is True


# --- 2. selector -----------------------------------------------------------

@pytest.mark.parametrize("name", [
    "Amazon.com, Inc.", "Cloudflare, Inc.", "Meta Platforms, Inc.",
    "The Goldman Sachs Group, Inc.", "JPMorgan Chase & Co.", "NIKE, Inc.",
])
def test_a_company_name_with_a_comma_resolves(name):
    """`--only` split on commas, and these names contain one. A
    three-company canary silently ran one."""
    rows = B.load_universe([name])
    assert [r["entry_name"] for r in rows] == [name]


def test_tickers_are_the_preferred_selector():
    """§2: prefer ticker or exact manifest identity over parsing names."""
    rows = B.load_universe(["MSFT", "NET", "META", "AMZN", "JPM", "CAT", "GS"])
    assert len(rows) == 7


def test_the_slug_matches_the_journeys_slug():
    """Two implementations of one rule is a second place for it to be wrong:
    a directory mismatch makes the resume check re-run a captured company
    every window until the quota is gone."""
    import re
    for name in ("Amazon.com, Inc.", "J.P. Morgan & Co.", "AT&T Inc.",
                 "The Goldman Sachs Group, Inc."):
        expected = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        assert B._slug(name) == expected, name


# --- 3. surface completeness ----------------------------------------------

def test_the_journey_captures_every_surface_the_scorer_reads():
    """The journey fetched six; six scored dimensions read /brief. Microsoft
    scored core_min 3 with market_belief and recommendation both "surface
    did not render", on a run whose brief was one request away."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]
                           / "src"))
    from intent_engine.pre100 import quality as Q
    from intent_engine.pre100 import specificity as S
    needed = {s for _k, s, _c in Q.DIMENSIONS}
    needed |= {s for _f, s, _c in S.FIELDS}
    needed -= {"qa"}                       # captured as qa.json, not a route
    missing = needed - set(J.STEPS)
    assert not missing, f"the journey never fetches {sorted(missing)}"


# --- 4. stale log protection ----------------------------------------------

def test_the_batch_banners_carry_a_run_id():
    """`batch.log` is appended across invocations, so "wait for BATCH END"
    matched the PREVIOUS run's line the instant a new batch started."""
    source = pathlib.Path(B.__file__).read_text()
    assert 'log(f"BATCH START {batch_id}' in source
    assert 'BATCH END {batch_id}' in source


# --- 5. incomplete run handling -------------------------------------------

def test_a_run_that_never_opened_is_not_scored_as_a_company():
    """Five companies were logged "DONE ... in 1s" beside genuine nine-minute
    analyses and scored, putting zeros on the matrix that belong to the
    service."""
    source = pathlib.Path(B.__file__).read_text()
    assert 'row.get("error") and not row.get("run_id")' in source, (
        "a failed /analyze is still being scored as a company")


def test_a_failed_capture_persists_what_the_service_returned():
    """Five 500s produced a manifest with no run_id and nothing to diagnose
    from, because run.json is written only on the path that opens a run."""
    source = pathlib.Path(B.__file__).read_text()
    assert 'if not (company_dir / "run.json").exists():' in source


# --- 7. one batch, one owner ----------------------------------------------

def test_a_second_batch_refuses_to_start(tmp_path):
    first = B.BatchLock(tmp_path / ".lock")
    assert first.acquire() is True
    second = B.BatchLock(tmp_path / ".lock")
    assert second.acquire() is False, "two orchestrators can run at once"
    first.release()
    assert second.acquire() is True


def test_a_stale_lock_is_reclaimed(tmp_path):
    """A lock left by a killed process must not block the next session
    forever -- that turns a safety rail into an outage."""
    path = tmp_path / ".lock"
    path.write_text("999999 2026-08-22T00:00:00Z\n")   # a pid that is gone
    assert B.BatchLock(path).acquire() is True


def test_the_lock_records_its_holder(tmp_path):
    lock = B.BatchLock(tmp_path / ".lock")
    lock.acquire()
    assert str(os.getpid()) in (tmp_path / ".lock").read_text()


def test_workers_are_registered_on_disk(tmp_path):
    B.register(tmp_path, harness_run_id="x", company="Adobe Inc.",
               deployed_sha="f8c183f", state="START")
    rows = [json.loads(line) for line
            in (tmp_path / "workers.jsonl").read_text().splitlines()]
    assert rows[0]["company"] == "Adobe Inc."
    assert rows[0]["pid"] == os.getpid()
    assert rows[0]["deployed_sha"] == "f8c183f"


# --- resume ---------------------------------------------------------------

def test_an_empty_directory_does_not_count_as_captured(tmp_path):
    (tmp_path / "adobe_inc").mkdir()
    assert B.already_captured(tmp_path, "Adobe Inc.") is False


def test_a_complete_capture_counts(tmp_path):
    d = tmp_path / "adobe_inc"
    d.mkdir()
    (d / "intro.txt").write_text("x")
    (d / "run.json").write_text("{}")
    assert B.already_captured(tmp_path, "Adobe Inc.") is True


def test_a_run_that_never_opened_still_persists_its_body():
    """The first version of the NO-RUN branch logged and `continue`d, which
    discarded the body it exists to keep. Three empty directories proved it
    on the first clean canary."""
    source = pathlib.Path(B.__file__).read_text()
    branch = source[source.index('if row.get("error") and not row.get("run_id")'):]
    # THE STATEMENT, NOT THE WORD. The branch's own comment contains
    # "`continue`d", so slicing at the bare word cut the branch off inside
    # the comment and the assertion read four lines of prose.
    branch = branch[:branch.index("\n                continue")]
    assert '"run.json"' in branch and "write_manifest" in branch, (
        "a failed /analyze is discarded before its body is written")


def test_a_quota_429_is_deferred_not_counted_as_a_failure():
    """Three 429s were counted as "three consecutive failures to open a run"
    and stopped a 50-company programme over the preview behaving exactly as
    designed. §22: a quota window is not a stop condition."""
    source = pathlib.Path(B.__file__).read_text()
    i = source.index('if "HTTP 429" in str(row.get("error") or "")')
    j = source.index('if row.get("error") and not row.get("run_id")', i)
    branch = source[i:j]
    assert "queue.appendleft" in branch, "a 429 does not re-queue the company"
    assert "failures.append" not in branch, "a 429 counts as a strike"


def test_a_restart_casualty_is_requeued_not_scored():
    """§6/§10. The free preview restarts under memory pressure -- measured at
    62s uptime immediately after Salesforce scored 2.6 with its surfaces
    gone. A run whose instance died has produced no reading, not a bad one,
    and scoring it puts an infrastructure event on the quality matrix."""
    source = pathlib.Path(B.__file__).read_text()
    i = source.index("boot_after = boot_id()")
    j = source.index("# A 429 IS NOT A FAILURE", i)
    branch = source[i:j]
    assert "queue.append(company)" in branch, "a restart casualty is dropped"
    assert "RUN_RESTART_LOST" in branch
    assert "score_capture" not in branch, "a restart casualty is scored"


def test_the_batch_records_the_boot_it_ran_against():
    source = pathlib.Path(B.__file__).read_text()
    assert "boot_before = boot_id()" in source
    assert "boot_id=boot_before" in source


# --- 5. the harness must send what the real form sends ---------------------

def test_the_journey_posts_the_domain_the_customers_pick_carries():
    """A harness that sends less than the entry page does is not automating
    the customer flow, it is bypassing it.

    MEASURED across 132 stored captures: this journey posted `suggest_cik`
    and `suggest_ticker` and never `suggest_domain`, so every run opened on
    the domainless-filer path and was analysed from EDGAR alone. Every
    single-family run in the corpus (`families=investor`) ended in
    TRUE_EVIDENCE_SCARCITY or RETRIEVAL_TEMPORARILY_UNAVAILABLE -- 21 of 21,
    not one full analysis -- and no capture ever reached a company-published
    page. `capture.py` had already been repaired for exactly this; the batch
    drives THIS module, so the repair had no caller.
    """
    source = pathlib.Path(J.__file__).read_text()
    assert '"suggest_domain"' in source, \
        "the journey never posts suggest_domain"
    assert "_suggested_domain(name)" in source, \
        "the domain must come from the page's own autocomplete, not a table"


def test_the_journey_asks_the_products_own_autocomplete_for_the_domain():
    """One implementation, not a second copy that can drift from it."""
    import inspect
    src = inspect.getsource(J._suggested_domain)
    assert "from intent_engine.pre100.capture import suggested_domain" in src
    assert J._suggested_domain("a name no registry carries at all") == ""
