"""Wall tests for marketing/publer_pipeline.py (overnight deliverable d):
dry-run is the only reachable mode, approval metadata is mandatory, and
real mode is double-gated (flag file + --real) and deliberately unwired."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "publer_pipeline", Path(__file__).parent.parent / "marketing" / "publer_pipeline.py")
pipeline = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pipeline)


def test_payload_requires_per_item_approval():
    with pytest.raises(ValueError, match="approval"):
        pipeline.build_payload("post text", approved_by="")
    p = pipeline.build_payload("post text", approved_by="founder 2026-07-20")
    assert p["approved_by"] == "founder 2026-07-20"


def test_flag_file_does_not_exist_tonight():
    assert not pipeline.FLAG_FILE.exists(), (
        "PUBLISHING_ENABLED must not exist unless the founder created it")


def test_real_mode_double_gated():
    assert not pipeline.real_mode_permitted(False)
    # --real alone is not enough while the flag file is absent:
    assert not pipeline.real_mode_permitted(True) or pipeline.FLAG_FILE.exists()


def test_dry_run_logs_and_never_touches_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "DISPATCH_LOG", tmp_path / "dispatch.jsonl")
    payload = pipeline.build_payload("hello", "founder 2026-07-20", ["linkedin"])
    record = pipeline.dispatch(payload, real=False)
    assert record["mode"] == "DRY-RUN"
    out = capsys.readouterr().out
    assert "DRY-RUN" in out and "PUBLER_API_KEY" not in out
    rows = [json.loads(l) for l in (tmp_path / "dispatch.jsonl").read_text().splitlines()]
    assert rows[0]["payload"]["text"] == "hello"


def test_real_dispatch_unwired_even_if_forced(tmp_path, monkeypatch):
    # Simulate the founder flag existing: real mode must STILL refuse,
    # because the HTTP call is deliberately not implemented yet.
    monkeypatch.setattr(pipeline, "FLAG_FILE", tmp_path / "PUBLISHING_ENABLED")
    pipeline.FLAG_FILE.write_text("")
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    (tmp_path / ".env").write_text("PUBLER_API_KEY=test-key-not-real\n")
    payload = pipeline.build_payload("hello", "founder 2026-07-20")
    with pytest.raises(NotImplementedError, match="founder-present"):
        pipeline.dispatch(payload, real=True)
