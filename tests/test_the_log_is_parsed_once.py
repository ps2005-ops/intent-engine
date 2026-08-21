"""A growing log may not be re-parsed from the beginning on every read.

MEASURED. The parse cache is keyed on `(mtime_ns, size)` -- the exact pair
that changes on every append. So during the one activity that matters, an
analysis writing documents into the run, the cache missed on EVERY read:

    31 MB log, one document appended
      before:  run_state 45 ms, one /progress poll's four queries 153 ms
      after:   0 ms, 1 ms

and both numbers grew without bound with the log. `append` calls `read_all`
for its idempotency check, so writing N documents cost O(N^2) parsing on top.

The correctness argument is the append-only discipline itself: the prefix of
the file never changes, so rows already parsed are still right. Everything
that is NOT simple growth falls back to a full parse, and these pin that.
"""
import json

import pytest

from intent_engine.agentos.append_only import AppendOnlyStore, CorruptLogError


class _Event:
    __slots__ = ("n", "idempotency_key", "subject_id")

    def __init__(self, n, idempotency_key="", subject_id=""):
        self.n, self.idempotency_key, self.subject_id = n, idempotency_key, subject_id

    @classmethod
    def from_json(cls, line):
        data = json.loads(line)
        if not isinstance(data.get("n"), int):
            raise TypeError("n must be an int")
        return cls(data["n"], data.get("idempotency_key", ""),
                   data.get("subject_id", ""))

    def content_fingerprint(self):
        return str(self.n)


class _RecordError(Exception):
    """Distinct from ValueError on purpose.

    `json.JSONDecodeError` subclasses ValueError, so a store whose
    `record_error` IS ValueError re-raises malformed JSON untouched instead
    of wrapping it -- which would make this fixture, not the store, decide
    the outcome. The real IngestionEvent uses its own IngestionError.
    """


class _Store(AppendOnlyStore):
    event_cls = _Event
    record_error = _RecordError
    corrupt_error = CorruptLogError


def _write(path, ns, mode="w"):
    with open(path, mode, encoding="utf-8") as fh:
        for n in ns:
            fh.write(json.dumps({"n": n}) + "\n")


@pytest.fixture
def log(tmp_path):
    return tmp_path / "log.jsonl"


def test_growth_gives_the_same_rows_as_a_full_parse(log):
    _write(log, range(5))
    store = _Store(log)
    assert [e.n for e in store.read_all()] == list(range(5))
    _write(log, range(5, 9), mode="a")
    assert [e.n for e in store.read_all()] == list(range(9))
    # A store that has never cached anything must agree, row for row.
    assert [e.n for e in _Store(log).read_all()] == list(range(9))


def test_the_tail_is_the_only_thing_reparsed(log):
    """The saving is the point, so it is asserted rather than assumed."""
    _write(log, range(200))
    store = _Store(log)
    store.read_all()
    seen = []
    real = _Event.from_json
    try:
        _Event.from_json = classmethod(
            lambda cls, line: (seen.append(line), real(line))[1])
        _write(log, [200, 201], mode="a")
        rows = store.read_all()
    finally:
        _Event.from_json = real
    assert [e.n for e in rows] == list(range(202))
    assert len(seen) == 2, f"re-parsed {len(seen)} lines, not just the tail"


def test_a_shrinking_file_is_parsed_again_in_full(log):
    _write(log, range(9))
    store = _Store(log)
    store.read_all()
    _write(log, range(3))                       # truncated and rewritten
    assert [e.n for e in store.read_all()] == [0, 1, 2]


def test_a_same_size_rewrite_is_parsed_again_in_full(log):
    """Equal length is the case a naive offset check gets wrong."""
    _write(log, [1, 2, 3])
    store = _Store(log)
    assert [e.n for e in store.read_all()] == [1, 2, 3]
    _write(log, [4, 5, 6])                      # same bytes on disk, new rows
    assert [e.n for e in store.read_all()] == [4, 5, 6]


def test_corruption_in_the_tail_still_raises(log):
    _write(log, range(4))
    store = _Store(log)
    store.read_all()
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    with pytest.raises(CorruptLogError):
        store.read_all()


def test_a_deleted_log_forgets_what_it_had_cached(log):
    _write(log, range(4))
    store = _Store(log)
    store.read_all()
    log.unlink()
    assert store.read_all() == []
    _write(log, [99])
    assert [e.n for e in store.read_all()] == [99]


def test_multibyte_text_survives_an_offset_read(log):
    """The offset is a BYTE count, so a text-mode seek would be wrong."""
    with open(log, "w", encoding="utf-8") as fh:
        for n, word in enumerate(["café", "naïve", "日本語"]):
            fh.write(json.dumps({"n": n, "subject_id": word}) + "\n")
    store = _Store(log)
    assert len(store.read_all()) == 3
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"n": 3, "subject_id": "Ünicode"}) + "\n")
    rows = store.read_all()
    assert [e.subject_id for e in rows] == ["café", "naïve", "日本語", "Ünicode"]


def test_the_caller_cannot_mutate_the_cache(log):
    _write(log, range(3))
    store = _Store(log)
    store.read_all().append("junk")
    assert len(store.read_all()) == 3
