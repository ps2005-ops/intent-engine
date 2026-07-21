"""T017 bars: the Marketing Plan's C3, C6, C7, C8 generators. Drafts
only; every asset carries the trace table and passes the C1 content
engine's own claim audit."""
from pathlib import Path

import pytest

from intent_engine.analytics import AnalyticsService
from intent_engine.core.prediction_ledger import (
    record_prediction, resolve_prediction,
)
from intent_engine.marketing import MarketingError
from intent_engine.marketing.generators import (
    C3_ASSET_TYPES, drafts_from_commits, fan_out_prediction,
    render_leaderboard_page, render_mechanism_library_page,
    render_predictions_page, render_public_pages, render_roadmap_page,
)

AS_OF = "2026-12-31T00:00:00+00:00"
REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def ledger(tmp_path):
    return tmp_path / "ledger.db"


# --- C3: ledger -> content fan-out -------------------------------------------

def test_c3_fans_one_prediction_into_the_full_draft_set(ledger, tmp_path):
    p = record_prediction(source="premortem", entity_id="acme",
                          claim_text="Burn exceeds plan for two quarters",
                          probability=0.6, resolve_by="2027-01-15",
                          path=ledger, decision_id="D" * 26)
    written = fan_out_prediction(p, drafts_root=tmp_path / "drafts")
    assert set(written) == set(C3_ASSET_TYPES)
    body = written["newsletter"].read_text()
    assert p.claim_text in body
    assert "no accuracy is claimed" in body.lower()
    assert "Claim-trace table" in body
    assert p.decision_id in written["markdown_page"].read_text()


def test_c3_is_idempotent_and_publishes_nothing(ledger, tmp_path):
    p = record_prediction(source="premortem", entity_id="acme",
                          claim_text="A resolvable claim", probability=0.5,
                          resolve_by="2027-01-15", path=ledger)
    first = fan_out_prediction(p, drafts_root=tmp_path / "drafts")
    before = {k: v.read_bytes() for k, v in first.items()}
    second = fan_out_prediction(p, drafts_root=tmp_path / "drafts")
    assert {k: v.read_bytes() for k, v in second.items()} == before
    files = list((tmp_path / "drafts").rglob("*.md"))
    assert len(files) == len(C3_ASSET_TYPES)      # no duplicates
    # the ledger itself is untouched by drafting
    from intent_engine.core.prediction_ledger import list_predictions
    assert len(list_predictions(path=ledger)) == 1


# --- C6: commit-triggered content --------------------------------------------

FIXTURE_COMMITS = [
    {"sha": "abc1234", "subject": "T016: append-only feedback ledger"},
    {"sha": "def5678", "subject": "T015: calibration views behind the gate"},
]


def test_c6_changelog_and_social_drafts_from_a_commit_range(tmp_path):
    written = drafts_from_commits(FIXTURE_COMMITS,
                                  drafts_root=tmp_path / "drafts",
                                  label="2026-07-21")
    assert set(written) == {"changelog", "linkedin", "x_thread"}
    changelog = written["changelog"].read_text()
    assert "abc1234" in changelog and "feedback ledger" in changelog
    assert "Claim-trace table" in changelog
    for path in written.values():
        assert "DRAFT" in path.read_text()


def test_c6_empty_range_is_an_explicit_error(tmp_path):
    with pytest.raises(MarketingError, match="no commits"):
        drafts_from_commits([], drafts_root=tmp_path, label="empty")


def test_c6_reads_real_git_history(tmp_path):
    from intent_engine.marketing.generators import read_commits
    commits = read_commits("HEAD~2..HEAD")
    assert len(commits) >= 1
    assert all(c["sha"] and c["subject"] for c in commits)


# --- C7: public pages ---------------------------------------------------------

def _seed(ledger, n_resolved):
    for i in range(n_resolved):
        p = record_prediction(source="market", entity_id="e",
                              claim_text=f"c{i}", probability=0.6,
                              resolve_by="2026-07-01", path=ledger)
        resolve_prediction(p.id, "happened", path=ledger)


def test_c7_predictions_page_shows_raw_rows_and_the_gate(ledger):
    _seed(ledger, 3)
    analytics = AnalyticsService(ledger_path=ledger)
    page = render_predictions_page(ledger, analytics_service=analytics,
                                   as_of=AS_OF)
    assert "Rows on the ledger: 3" in page
    assert "TOO FEW RESOLVED TO CLAIM CALIBRATION" in page
    assert "resolved rows: 3" in page


def test_c7_leaderboard_asserts_no_ranking_below_the_gate(ledger):
    _seed(ledger, 5)
    analytics = AnalyticsService(ledger_path=ledger)
    page = render_leaderboard_page(ledger, analytics_service=analytics,
                                   as_of=AS_OF)
    assert "TOO FEW RESOLVED TO CLAIM CALIBRATION" in page
    assert "No ranking is asserted" in page
    for banned in ("beats", "outperform", "win rate"):
        assert banned not in page.lower()


def test_c7_gate_language_comes_from_the_analytics_view_not_a_copy(ledger):
    """The page never re-derives the threshold: with 30 resolved rows the
    analytics view flips and the page follows it."""
    _seed(ledger, 30)
    analytics = AnalyticsService(ledger_path=ledger)
    page = render_predictions_page(ledger, analytics_service=analytics,
                                   as_of=AS_OF)
    assert "TOO FEW RESOLVED TO CLAIM CALIBRATION" not in page
    assert "Status: OK" in page
    assert "founder calibration review" in page       # the caveat travels


def test_c7_without_analytics_defaults_to_the_honest_position(ledger):
    page = render_predictions_page(ledger)
    assert "Too few resolved to claim calibration" in page


def test_c7_mechanism_library_page_is_read_only(tmp_path):
    lib = REPO_ROOT / "src/intent_engine/core/data/mechanisms.json"
    before = lib.read_bytes()
    page = render_mechanism_library_page()
    assert "Documented mechanisms:" in page
    assert "not a claim about any future case" in page
    assert lib.read_bytes() == before


def test_c7_renders_all_pages_to_a_drafts_dir(ledger, tmp_path):
    pages = render_public_pages(ledger, drafts_root=tmp_path / "drafts")
    assert set(pages) == {"predictions", "leaderboard", "mechanism_library"}
    assert (tmp_path / "drafts" / "pages" / "predictions.md").exists()


# --- C8: public roadmap page --------------------------------------------------

def test_c8_roadmap_page_regenerates_from_roadmap_md(tmp_path):
    page = render_roadmap_page(drafts_root=tmp_path / "drafts")
    assert "# Public roadmap" in page
    for heading in ("## Done", "## In progress", "## Next", "## Ideas"):
        assert heading in page
    assert "T010" in page                    # a real DONE task
    assert "maintained by hand" in page
    assert (tmp_path / "drafts" / "pages" / "roadmap.md").exists()


def test_c8_uses_the_same_parser_as_the_nightly_loop(tmp_path):
    roadmap = tmp_path / "ROADMAP.md"
    roadmap.write_text(
        "## T900 — A task\n\n- **Status**: RUNNABLE\n- **Priority**: 1\n\n"
        "## T901 — Another\n\n- **Status**: DONE\n- **Priority**: 2\n")
    page = render_roadmap_page(roadmap)
    assert "T900" in page and "T901" in page
    next_block = page.split("## Next")[1].split("##")[0]
    assert "T900" in next_block and "T901" not in next_block
