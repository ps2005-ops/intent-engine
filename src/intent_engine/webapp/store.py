"""V1.0.1 webapp store — AgentOS AppendOnlyStore subclass, query methods only."""
from __future__ import annotations

from pathlib import Path

from intent_engine.agentos.append_only import AppendOnlyStore, CorruptLogError
from intent_engine.webapp.records import WebAppError, WebEvent

DEFAULT_WEB_PATH = Path("data/webapp.jsonl")


class WebAppCorruptLogError(CorruptLogError):
    """The webapp log contains a line that cannot be parsed."""


class WebStore(AppendOnlyStore):
    event_cls = WebEvent
    record_error = WebAppError
    corrupt_error = WebAppCorruptLogError

    def __init__(self, path=DEFAULT_WEB_PATH):
        super().__init__(path)

    # --- users ---------------------------------------------------------------
    def users(self) -> dict:
        """email -> latest user payload (append-only fold)."""
        out = {}
        for row in self.read_all():
            if row.event_type == "web.user_created":
                out[row.payload["email"]] = dict(row.payload)
        return out

    def user_by_email(self, email: str):
        return self.users().get(email)

    # --- ownership -----------------------------------------------------------
    def owner_of(self, run_id: str):
        for row in self.read_all():
            if row.event_type == "web.run_owned" and row.subject_id == run_id:
                return row.payload["user_id"]
        return None

    def runs_owned_by(self, user_id: str) -> list:
        return [row.subject_id for row in self.read_all()
                if row.event_type == "web.run_owned"
                and row.payload.get("user_id") == user_id]

    # --- sharing (hashes only; never the raw token) --------------------------
    def shares(self) -> dict:
        """token_hash -> current share state (created then maybe revoked)."""
        out = {}
        for row in self.read_all():
            if row.event_type == "web.share_created":
                out[row.payload["token_hash"]] = dict(row.payload)
            elif row.event_type == "web.share_revoked":
                if row.payload["token_hash"] in out:
                    out[row.payload["token_hash"]]["revoked"] = True
        return out

    def shares_for_run(self, run_id: str) -> list:
        return [s for s in self.shares().values() if s.get("run_id") == run_id]

    # --- access log ----------------------------------------------------------
    def access_log(self) -> list:
        return [row for row in self.read_all()
                if row.event_type in ("web.share_accessed", "web.share_denied")]
