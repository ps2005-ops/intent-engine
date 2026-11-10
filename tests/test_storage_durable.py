"""Durable store — append-only, replayable, idempotent, backend-portable.

Exercises the SQLite backend (the one CI can run without a server). The
Postgres backend shares 100% of the SQL and logic — only the driver and two
DDL tokens differ — so these invariants carry to Postgres.
"""
import pytest

from intent_engine.storage.durable import (
    DurableStore,
    IdempotencyConflict,
    StorageError,
    resolve_database_url,
)
from intent_engine.storage.health import check_health


def _store(tmp_path):
    return DurableStore(f"sqlite:///{tmp_path}/durable.db")


# --- url resolution ----------------------------------------------------------

def test_resolve_url_precedence(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert resolve_database_url().startswith("sqlite:///")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    assert resolve_database_url() == "postgresql://u:p@h/db"
    # explicit arg wins over env
    assert resolve_database_url("sqlite:///x.db") == "sqlite:///x.db"


def test_resolve_url_rejects_unknown_scheme():
    with pytest.raises(StorageError):
        resolve_database_url("mysql://nope")


# --- append / read / latest --------------------------------------------------

def test_append_and_get_roundtrip(tmp_path):
    s = _store(tmp_path)
    rec = s.append("paper_order", "o1", {"symbol": "SHOP", "qty": 3},
                   status="submitted", company_id="shopify", ref_id="pred1")
    assert rec.stream == "paper_order" and rec.record_id == "o1"
    assert rec.status == "submitted" and rec.company_id == "shopify"
    got = s.get("paper_order", "o1")
    assert got.payload == {"symbol": "SHOP", "qty": 3}


def test_latest_wins_but_history_is_replayable(tmp_path):
    s = _store(tmp_path)
    s.append("paper_order", "o1", {"status": "new"}, status="new")
    s.append("paper_order", "o1", {"status": "filled"}, status="filled")
    # latest collapses to the newest row per record_id...
    latest = s.latest("paper_order")
    assert len(latest) == 1 and latest[0].payload["status"] == "filled"
    # ...but the full history is preserved (append-only, replayable)
    history = s.read("paper_order")
    assert [r.payload["status"] for r in history] == ["new", "filled"]


def test_filter_by_company_and_ref(tmp_path):
    s = _store(tmp_path)
    s.append("prediction", "p1", {"x": 1}, company_id="shopify", ref_id="r1")
    s.append("prediction", "p2", {"x": 2}, company_id="cloudflare", ref_id="r2")
    assert {r.record_id for r in s.read("prediction", company_id="shopify")} == {"p1"}
    assert {r.record_id for r in s.read("prediction", ref_id="r2")} == {"p2"}


def test_count_and_streams(tmp_path):
    s = _store(tmp_path)
    s.append("a", "1", {})
    s.append("a", "2", {})
    s.append("b", "1", {})
    assert s.count("a") == 2 and s.count("b") == 1
    assert s.streams() == ["a", "b"]


# --- idempotency (the twice-fired-job guarantee) -----------------------------

def test_idempotent_same_key_same_payload_writes_once(tmp_path):
    s = _store(tmp_path)
    first = s.append("paper_order", "o1", {"qty": 3}, idem_key="cid-abc")
    second = s.append("paper_order", "o1", {"qty": 3}, idem_key="cid-abc")
    assert second.seq == first.seq            # same row returned
    assert s.count("paper_order") == 1        # nothing written the 2nd time


def test_idempotent_conflict_on_different_payload(tmp_path):
    s = _store(tmp_path)
    s.append("paper_order", "o1", {"qty": 3}, idem_key="cid-abc")
    with pytest.raises(IdempotencyConflict):
        s.append("paper_order", "o1", {"qty": 5}, idem_key="cid-abc")


def test_idempotent_ignores_wall_clock_write_stamps(tmp_path):
    # A record re-written a second later differs only by its "when-written"
    # stamp (created_at/at/...). That must dedupe to a no-op, NOT raise — the
    # 30-day replay surfaced daily crashes when a re-proposed candidate and a
    # re-recorded rejection collided on a stable idem_key with a fresh clock.
    s = _store(tmp_path)
    first = s.append("learning_candidate", "c1",
                     {"statement": "x", "sample_size": 5,
                      "created_at": "2026-01-02T13:00:00+00:00"},
                     idem_key="cand:c1:sig")
    second = s.append("learning_candidate", "c1",
                      {"statement": "x", "sample_size": 5,
                       "created_at": "2026-01-03T13:00:01+00:00"},  # later stamp
                      idem_key="cand:c1:sig")
    assert second.seq == first.seq                 # same row, no write
    assert s.count("learning_candidate") == 1
    # a genuine content change under the same key still conflicts loudly
    with pytest.raises(IdempotencyConflict):
        s.append("learning_candidate", "c1",
                 {"statement": "x", "sample_size": 6,   # evidence changed
                  "created_at": "2026-01-03T13:00:01+00:00"},
                 idem_key="cand:c1:sig")


def test_persistence_survives_new_store_instance(tmp_path):
    # A fresh runner = a brand-new process opening the same DATABASE_URL.
    url = f"sqlite:///{tmp_path}/durable.db"
    DurableStore(url).append("company_state", "shopify", {"thesis": "v1"})
    reopened = DurableStore(url)
    got = reopened.get("company_state", "shopify")
    assert got is not None and got.payload["thesis"] == "v1"


# --- health check ------------------------------------------------------------

def test_health_ok_and_hides_credentials(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/durable.db"
    rep = check_health(url)
    assert rep["ok"] is True and rep["roundtrip"] is True
    assert rep["backend"] == "sqlite"
    assert "__health__" not in rep["streams"]


def test_health_target_never_leaks_postgres_password():
    rep = check_health("postgresql://user:supersecret@db.example/intent")
    # It will fail to connect (no server), but must NOT leak the password.
    assert "supersecret" not in str(rep)
    assert rep["backend"] == "postgres"
    assert rep["target"] == "postgresql://db.example/intent"
