"""A torn tail must not brick the log; interior corruption must still refuse.

MEASURED IN PRODUCTION, on the deployed preview at f8c183f: line 145 of
`data/company_ingestion.jsonl` became unparseable, and from that moment every
`POST /analyze` answered HTTP 500 -- for hours, across the whole 50-company
batch -- because `read_all` parses the entire log and raised on sight. The
same read sits behind `/progress`, `/runs/<id>` and the Q&A route, so one
unreadable byte took every surface of the product down at once.

These pin both halves: the tail is recoverable, and the interior is not.
"""
from __future__ import annotations

import json
import os

import pytest

from intent_engine.company_ingestion.records import IngestionEvent
from intent_engine.company_ingestion.store import (IngestionCorruptLogError,
                                                   IngestionStore)


def _event(n: int) -> IngestionEvent:
    return IngestionEvent(event_type="ci.run_created", actor_type="human",
                          actor_id="u1", run_id=f"r{n}", subject_type="run",
                          subject_id=f"r{n}", idempotency_key=f"k{n}",
                          payload={"n": n})


def _store(tmp_path, rows=3):
    store = IngestionStore(tmp_path / "ci.jsonl")
    for i in range(rows):
        store.append(_event(i))
    return store


def _fresh(store):
    """A new store object: no warm parse cache to read the answer out of."""
    return IngestionStore(store.path)


# --- the production failure, and that it is survivable ---------------------

def test_nul_padded_tail_is_dropped_and_the_log_still_reads(tmp_path):
    """The exact production signature: a trailing region of NUL bytes."""
    store = _store(tmp_path)
    with open(store.path, "ab") as f:
        f.write(b"\x00" * 64 + b"\n")

    rows = _fresh(store).read_all()

    assert [r.run_id for r in rows] == ["r0", "r1", "r2"]
    # and the file itself is repaired, not merely tolerated on every read
    assert b"\x00" not in store.path.read_bytes()


def test_half_written_json_tail_is_dropped(tmp_path):
    """ENOSPC leaves a real prefix of a real record, not only NULs."""
    store = _store(tmp_path)
    good = _event(9).to_json()
    with open(store.path, "a", encoding="utf-8") as f:
        f.write(good[:len(good) // 2])

    assert [r.run_id for r in _fresh(store).read_all()] == ["r0", "r1", "r2"]


def test_torn_tail_that_is_not_valid_utf8_is_dropped(tmp_path):
    """A torn multi-byte character used to escape as an UNHANDLED error.

    `raw.decode("utf-8")` sat outside the caught set, so this arrived at the
    request boundary as a raw 500 rather than as this store's own error.
    """
    store = _store(tmp_path)
    with open(store.path, "ab") as f:
        f.write(b'{"a": "\xe2\x82\n')          # euro sign cut mid-sequence

    assert [r.run_id for r in _fresh(store).read_all()] == ["r0", "r1", "r2"]


def test_the_log_accepts_writes_again_after_a_torn_tail(tmp_path):
    """Recovery is the point: `append` calls `read_all` for idempotency, so a
    log that cannot be read is a log that can never be written either."""
    store = _store(tmp_path)
    with open(store.path, "ab") as f:
        f.write(b"\x00" * 32 + b"\n")

    live = _fresh(store)
    live.append(_event(7))

    assert [r.run_id for r in _fresh(store).read_all()] == \
        ["r0", "r1", "r2", "r7"]


# --- the negative control: what must STILL refuse -------------------------

def test_interior_corruption_still_refuses(tmp_path):
    """A bad line with GOOD records after it is not a torn tail.

    Dropping it would silently lose acknowledged history, which is the thing
    an append-only ledger exists to prevent. This is the control that keeps
    the repair above from becoming "skip malformed lines".
    """
    store = _store(tmp_path)
    lines = store.path.read_text().splitlines()
    lines.insert(1, "}{ not json")
    store.path.write_text("\n".join(lines) + "\n")

    with pytest.raises(IngestionCorruptLogError) as exc:
        _fresh(store).read_all()
    assert "malformed" in str(exc.value)


def test_interior_corruption_is_not_truncated_away(tmp_path):
    """Refusing must also mean not destroying the evidence."""
    store = _store(tmp_path)
    lines = store.path.read_text().splitlines()
    lines.insert(1, "}{ not json")
    store.path.write_text("\n".join(lines) + "\n")
    before = store.path.read_bytes()

    with pytest.raises(IngestionCorruptLogError):
        _fresh(store).read_all()

    assert store.path.read_bytes() == before


def test_a_validation_failure_is_still_not_corruption(tmp_path):
    """`record_error` must keep travelling as itself, not become a tail."""
    store = _store(tmp_path)
    from intent_engine.company_ingestion.records import INGESTION_SCHEMA_VERSION
    with open(store.path, "a", encoding="utf-8") as f:
        row = json.loads(_event(4).to_json())
        row["schema_version"] = INGESTION_SCHEMA_VERSION + 5
        f.write(json.dumps(row) + "\n")

    from intent_engine.company_ingestion.records import IngestionError
    with pytest.raises(IngestionError):
        _fresh(store).read_all()


# --- prevention: a failed write leaves nothing behind ---------------------

def test_a_failed_append_leaves_no_partial_line(tmp_path, monkeypatch):
    """The torn tail had to be written by something, and this is it."""
    store = _store(tmp_path)
    before = store.path.read_bytes()
    real = os.fsync

    def _boom(fd):
        os.write(fd, b'{"partial": ')          # land bytes, then die
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "fsync", _boom)
    with pytest.raises(OSError):
        store.append(_event(5))
    monkeypatch.setattr(os, "fsync", real)

    assert store.path.read_bytes() == before
    assert [r.run_id for r in _fresh(store).read_all()] == ["r0", "r1", "r2"]


def test_normal_reads_are_unchanged(tmp_path):
    """Positive control: an intact log parses exactly as before."""
    store = _store(tmp_path, rows=5)
    assert [r.run_id for r in _fresh(store).read_all()] == \
        ["r0", "r1", "r2", "r3", "r4"]
    assert _fresh(store).find_by_idempotency_key("k3").run_id == "r3"
