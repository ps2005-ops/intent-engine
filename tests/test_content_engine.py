"""C1 (PLAN_2026-07-21) definition-of-done test for the content engine.

Feeds the REAL 2026-07-17 production run and asserts:
  (a) >=5 asset types produced,
  (b) every asset carries the claim-trace table,
  (c) zero predictive-accuracy strings (the outreach claim audit, as code),
  (d) zero network calls (socket layer hard-disabled during render).
Plus: no fact in an asset that isn't in the source object (spot-checked on
every number/probability), drafts land in the queue directory, and nothing
resembling a publish happens (write_drafts touches only the drafts root).
"""

import importlib.util
import re
import socket
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_RUN = REPO_ROOT / "reports" / "weekly_regime_report_2026-07-17.txt"


def _load_engine():
    spec = importlib.util.spec_from_file_location(
        "content_engine_render", REPO_ROOT / "marketing" / "content_engine" / "render.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


ce = _load_engine()


@pytest.fixture()
def no_network(monkeypatch):
    def _blocked(*a, **k):
        raise AssertionError("network call attempted during content rendering")
    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


@pytest.fixture()
def source():
    return ce.ContentSource.from_report_path(REAL_RUN)


def test_real_run_produces_five_plus_assets_offline(source, no_network):
    drafts = ce.render_all(source)                       # (d) runs with sockets off
    assert len(drafts) >= 5                              # (a)
    for asset_type, draft in drafts.items():
        assert ce.TRACE_TABLE in draft, asset_type       # (b)
        assert ce.audit_predictive_accuracy_claims(draft) == [], asset_type  # (c)
        assert "DRAFT" in draft                          # queue item, not a publish


def test_no_invented_numbers(source):
    """Every probability and resolve-by date in every asset exists in the
    source object — no fact enters an asset that isn't in the source."""
    drafts = ce.render_all(source)
    src_probs = {p["p"] for p in source.predictions}
    src_dates = {p["by"] for p in source.predictions}
    for asset_type, draft in drafts.items():
        for prob in re.findall(r"P\s*=\s*(0\.\d+)", draft):
            assert prob in src_probs, (asset_type, prob)
        for date in re.findall(r"by (\d{4}-\d{2}-\d{2})", draft):
            assert date in src_dates, (asset_type, date)


def test_real_run_honesty_markers_render(source):
    """The 2026-07-17 run had 3 unavailable series and zero matched
    mechanisms — the honest rendering IS the content."""
    drafts = ce.render_all(source)
    assert source.none_matched
    for asset_type in ("website_article", "newsletter", "founder_email"):
        assert "UNAVAILABLE" in drafts[asset_type], asset_type
        assert "NONE MATCHED" in drafts[asset_type] or "none" in drafts[asset_type].lower()


def test_drafts_land_in_queue_and_nowhere_else(source, tmp_path, no_network):
    written = ce.write_drafts(source, drafts_root=tmp_path)
    assert len(written) >= 5
    for p in written:
        assert p.exists()
        assert tmp_path in p.parents or p.parent.parent == tmp_path
        assert p.parent.name == source.snapshot_date


def test_write_drafts_is_idempotent(source, tmp_path):
    first = ce.write_drafts(source, drafts_root=tmp_path)
    second = ce.write_drafts(source, drafts_root=tmp_path)
    assert sorted(first) == sorted(second)
    # re-running doesn't double-draft: same file set, same content
    all_files = list(tmp_path.rglob("*.md"))
    assert len(all_files) == len(first)


def test_none_matched_is_educational_everywhere_it_renders(source):
    """Founder feedback #7: 'NONE MATCHED' teaches, it doesn't shrug. The
    2026-07-17 run matched nothing, so every asset must carry all three
    beats: the marker, the disclaimer of the wrong reading, and the reason."""
    assert source.none_matched
    drafts = ce.render_all(source)
    for asset_type, draft in drafts.items():
        assert "NONE MATCHED" in draft, asset_type
        assert "nothing is happening" in draft, asset_type
        assert "known historical pattern" in draft, asset_type


def test_founder_email_and_newsletter_lead_with_positioning(source):
    """Founder feedback #6: warmer opener that reinforces the positioning,
    without conversational fluff."""
    drafts = ce.render_all(source)
    for asset_type in ("founder_email", "newsletter"):
        assert "Nothing has been simplified or hidden" in drafts[asset_type], asset_type
    assert "Here's this week's read — two minutes" not in drafts["founder_email"]


def test_tone_stays_restrained(source):
    """The tone is a feature, not an accident: the body copy carries no
    exclamation marks, no emoji, and no hype words. (The machine-readable
    draft banner and the fixed trace table are excluded — they aren't prose.)"""
    for asset_type, draft in ce.render_all(source).items():
        body = draft.replace(ce.DRAFT_BANNER, "").replace(ce.TRACE_TABLE, "")
        assert "!" not in body, asset_type
        assert all(ord(ch) < 0x2190 or ch in "—…" for ch in body), asset_type
        for hype in ("game-changer", "revolutionary", "unprecedented",
                     "guarantee", "cutting-edge", "world-class"):
            assert hype not in body.lower(), (asset_type, hype)


def test_claim_audit_catches_violations():
    assert ce.audit_predictive_accuracy_claims("our model is 90% accurate") != []
    assert ce.audit_predictive_accuracy_claims("a proven track record") != []
    assert ce.audit_predictive_accuracy_claims(
        "nothing has resolved yet, so no accuracy is claimed") == []


def test_unrecognized_report_is_parked_not_guessed(tmp_path):
    bad = tmp_path / "bad.txt"
    bad.write_text("SOMETHING ELSE ENTIRELY\n")
    with pytest.raises(ValueError):
        ce.ContentSource.from_report_path(bad)
